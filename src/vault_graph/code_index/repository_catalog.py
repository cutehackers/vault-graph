"""Registration and safety boundary for source repositories.

The repository catalog is configuration state owned by Vault Graph.  It stores
only canonical repository paths and scan policy; repository files remain an
external read-only authority.  All mutations validate the complete catalog
before writing the YAML document.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

import yaml

from vault_graph.app.catalog_service import CatalogService
from vault_graph.app.path_guard import assert_target_outside_vaults
from vault_graph.code_index.code_models import CodeRepositoryEntry
from vault_graph.errors import CatalogError
from vault_graph.ingestion.vault_catalog import VaultCatalog

SUPPORTED_CODE_LANGUAGES = ("python", "dart")
SUPPORTED_GIT_REVISION_POLICIES = ("head", "head-and-working-tree", "content-hash")


@runtime_checkable
class CodeRepositoryCatalog(Protocol):
    """Stable interface used by scanners and application adapters."""

    def entries(self) -> tuple[CodeRepositoryEntry, ...]: ...

    def resolve(self, repository_id: str) -> CodeRepositoryEntry: ...

    def save(self, entry: CodeRepositoryEntry) -> None: ...

    def remove(self, repository_id: str) -> None: ...


class CodeRepositoryCatalogService:
    """Load and safely mutate the repository registration catalog."""

    def __init__(
        self,
        *,
        graph_home_path: Path | None = None,
        catalog_service: CatalogService | None = None,
    ) -> None:
        if catalog_service is not None and graph_home_path is not None:
            if catalog_service.graph_home_path != graph_home_path.expanduser().resolve():
                raise ValueError("graph_home_path and catalog_service must refer to the same state")
        self.catalog_service = catalog_service or CatalogService(
            graph_home_path=graph_home_path if graph_home_path is not None else Path("~/.local/state/vault-graph")
        )
        self.graph_home_path = self.catalog_service.graph_home_path
        self.config_path = self.catalog_service.code_config_path

    def load(self) -> CodeRepositoryCatalog:
        vault_catalog = self._load_vault_catalog()
        self.catalog_service.assert_graph_home_write_target_safe(target_path=self.config_path, catalog=vault_catalog)
        entries = self._read_entries()
        self._validate_entries(entries, vault_catalog=vault_catalog)
        return _YamlCodeRepositoryCatalog(entries=entries, service=self)

    def add(self, entry: CodeRepositoryEntry) -> CodeRepositoryCatalog:
        catalog = self.load()
        normalized = _normalize_entry(entry)
        if any(existing.repository_id == normalized.repository_id for existing in catalog.entries()):
            raise CatalogError(f"duplicate repository_id: {normalized.repository_id}")
        entries = (*catalog.entries(), normalized)
        self._validate_entries(entries, vault_catalog=self._load_vault_catalog())
        self._write_entries(entries)
        return self.load()

    def remove(self, repository_id: str) -> CodeRepositoryCatalog:
        catalog = self.load()
        if not isinstance(repository_id, str) or not repository_id.strip():
            raise CatalogError("repository_id is required")
        if not any(entry.repository_id == repository_id for entry in catalog.entries()):
            raise CatalogError(f"unknown repository_id: {repository_id}")
        entries = tuple(entry for entry in catalog.entries() if entry.repository_id != repository_id)
        self._validate_entries(entries, vault_catalog=self._load_vault_catalog())
        self._write_entries(entries)
        return self.load()

    def _save_entry(self, entry: CodeRepositoryEntry) -> None:
        catalog = self.load()
        normalized = _normalize_entry(entry)
        entries = tuple(
            normalized if current.repository_id == normalized.repository_id else current
            for current in catalog.entries()
        )
        if all(current.repository_id != normalized.repository_id for current in catalog.entries()):
            entries = (*catalog.entries(), normalized)
        self._validate_entries(entries, vault_catalog=self._load_vault_catalog())
        self._write_entries(entries)

    def _remove_entry(self, repository_id: str) -> None:
        self.remove(repository_id)

    def _load_vault_catalog(self) -> VaultCatalog:
        return self.catalog_service.load_catalog()

    def _read_entries(self) -> tuple[CodeRepositoryEntry, ...]:
        if not self.config_path.exists():
            return ()
        try:
            loaded = yaml.safe_load(self.config_path.read_text(encoding="utf-8")) or {}
        except (OSError, UnicodeDecodeError, yaml.YAMLError) as exc:
            raise CatalogError(f"cannot read code repository catalog: {self.config_path}") from exc
        if not isinstance(loaded, dict):
            raise CatalogError(f"code repository catalog must be a mapping: {self.config_path}")
        raw_entries = loaded.get("repositories", [])
        if raw_entries is None:
            raw_entries = []
        if not isinstance(raw_entries, list):
            raise CatalogError(f"repositories must be a list: {self.config_path}")
        entries: list[CodeRepositoryEntry] = []
        for index, raw_entry in enumerate(raw_entries):
            if not isinstance(raw_entry, dict):
                raise CatalogError(f"repository entry {index} must be a mapping")
            entries.append(_entry_from_mapping(raw_entry, index=index))
        return tuple(entries)

    def _write_entries(self, entries: tuple[CodeRepositoryEntry, ...]) -> None:
        vault_catalog = self._load_vault_catalog()
        self._validate_entries(entries, vault_catalog=vault_catalog)
        self.catalog_service.assert_graph_home_write_target_safe(target_path=self.config_path, catalog=vault_catalog)
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "repositories": [
                {
                    "repository_id": entry.repository_id,
                    "root_path": str(entry.root_path),
                    "display_name": entry.display_name,
                    "enabled": entry.enabled,
                    "include_globs": list(entry.include_globs),
                    "exclude_globs": list(entry.exclude_globs),
                    "languages": list(entry.languages),
                    "state_namespace": entry.state_namespace,
                    "git_revision_policy": entry.git_revision_policy,
                    "watch": entry.watch,
                }
                for entry in entries
            ]
        }
        temporary_path = self.config_path.with_name(f".{self.config_path.name}.tmp")
        self.catalog_service.assert_graph_home_write_target_safe(target_path=temporary_path, catalog=vault_catalog)
        try:
            temporary_path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
            temporary_path.replace(self.config_path)
        finally:
            if temporary_path.exists():
                temporary_path.unlink()

    def _validate_entries(self, entries: Iterable[CodeRepositoryEntry], *, vault_catalog: VaultCatalog) -> None:
        entries_tuple = tuple(entries)
        by_id: set[str] = set()
        state_namespaces: set[str] = set()
        canonical_roots: list[Path] = []
        vault_roots = tuple(entry.root_path for entry in vault_catalog.entries())
        for entry in entries_tuple:
            normalized = _normalize_entry(entry)
            if normalized.repository_id in by_id:
                raise CatalogError(f"duplicate repository_id: {normalized.repository_id}")
            by_id.add(normalized.repository_id)
            namespace_key = _state_namespace_key(normalized.state_namespace)
            if namespace_key in state_namespaces:
                raise CatalogError(f"duplicate state_namespace: {normalized.state_namespace}")
            state_namespaces.add(namespace_key)
            if not normalized.root_path.exists() or not normalized.root_path.is_dir():
                raise CatalogError(f"repository root does not exist or is not a directory: {normalized.root_path}")
            if (
                normalized.root_path == self.graph_home_path
                or self.graph_home_path in normalized.root_path.parents
                or normalized.root_path in self.graph_home_path.parents
            ):
                raise CatalogError(f"code repository root must stay outside Graph Data Home: {normalized.root_path}")
            assert_target_outside_vaults(target_path=normalized.root_path, vault_roots=vault_roots)
            _validate_entry_policy(normalized)
            for previous_root in canonical_roots:
                if normalized.root_path == previous_root:
                    raise CatalogError(f"duplicate canonical root: {normalized.root_path}")
                if normalized.root_path in previous_root.parents or previous_root in normalized.root_path.parents:
                    raise CatalogError(f"repository roots overlap: {previous_root} and {normalized.root_path}")
            canonical_roots.append(normalized.root_path)


class _YamlCodeRepositoryCatalog:
    def __init__(self, *, entries: tuple[CodeRepositoryEntry, ...], service: CodeRepositoryCatalogService) -> None:
        self._entries = entries
        self._service = service

    def entries(self) -> tuple[CodeRepositoryEntry, ...]:
        return self._entries

    def resolve(self, repository_id: str) -> CodeRepositoryEntry:
        for entry in self._entries:
            if entry.repository_id == repository_id:
                return entry
        raise CatalogError(f"unknown repository_id: {repository_id}")

    def save(self, entry: CodeRepositoryEntry) -> None:
        self._service._save_entry(entry)
        self._entries = self._service.load().entries()

    def remove(self, repository_id: str) -> None:
        self._service._remove_entry(repository_id)
        self._entries = self._service.load().entries()


def repository_policy_revision(entry: CodeRepositoryEntry) -> str:
    """Return a stable digest for the scanner policy affecting a repository."""

    payload = {
        "exclude_globs": list(entry.exclude_globs),
        "include_globs": list(entry.include_globs),
        "languages": list(entry.languages),
        "git_revision_policy": entry.git_revision_policy,
    }
    serialized = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return f"code-policy-v1:{hashlib.sha256(serialized.encode('utf-8')).hexdigest()}"


def _entry_from_mapping(raw_entry: dict[str, Any], *, index: int) -> CodeRepositoryEntry:
    try:
        return _normalize_entry(
            CodeRepositoryEntry(
                repository_id=str(raw_entry["repository_id"]),
                root_path=Path(str(raw_entry["root_path"])),
                display_name=str(raw_entry.get("display_name") or raw_entry["repository_id"]),
                enabled=raw_entry.get("enabled", True),
                include_globs=raw_entry.get("include_globs", ()),
                exclude_globs=raw_entry.get("exclude_globs", ()),
                languages=raw_entry.get("languages", ()),
                state_namespace=str(raw_entry.get("state_namespace") or raw_entry["repository_id"]),
                git_revision_policy=str(raw_entry.get("git_revision_policy", "head-and-working-tree")),
                watch=raw_entry.get("watch", False),
            )
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise CatalogError(f"invalid repository entry {index}") from exc


def _normalize_entry(entry: CodeRepositoryEntry) -> CodeRepositoryEntry:
    if not isinstance(entry, CodeRepositoryEntry):
        raise CatalogError("repository entry must be a CodeRepositoryEntry")
    try:
        normalized = CodeRepositoryEntry(
            repository_id=entry.repository_id.strip(),
            root_path=entry.root_path.expanduser().resolve(),
            display_name=entry.display_name.strip(),
            enabled=entry.enabled,
            include_globs=tuple(entry.include_globs),
            exclude_globs=tuple(entry.exclude_globs),
            languages=tuple(entry.languages),
            state_namespace=entry.state_namespace.strip(),
            git_revision_policy=entry.git_revision_policy.strip(),
            watch=entry.watch,
        )
    except (AttributeError, TypeError, ValueError) as exc:
        raise CatalogError("invalid code repository entry") from exc
    return normalized


def _validate_entry_policy(entry: CodeRepositoryEntry) -> None:
    if not entry.languages:
        raise CatalogError(f"languages is required for repository: {entry.repository_id}")
    unsupported = tuple(language for language in entry.languages if language not in SUPPORTED_CODE_LANGUAGES)
    if unsupported:
        raise CatalogError(f"unsupported language for repository {entry.repository_id}: {unsupported[0]}")
    if entry.git_revision_policy not in SUPPORTED_GIT_REVISION_POLICIES:
        raise CatalogError(f"unsupported git_revision_policy for repository {entry.repository_id}")
    _validate_state_namespace(entry.state_namespace, repository_id=entry.repository_id)
    for field_name, patterns in (("include", entry.include_globs), ("exclude", entry.exclude_globs)):
        for pattern in patterns:
            _validate_glob_pattern(pattern, field_name=field_name)
    for symlink in entry.root_path.rglob("*"):
        if not symlink.is_symlink():
            continue
        resolved = symlink.resolve(strict=False)
        if resolved != entry.root_path and entry.root_path not in resolved.parents:
            raise CatalogError(f"repository glob would follow symlink outside repository: {symlink}")


def _validate_state_namespace(value: str, *, repository_id: str) -> None:
    path = Path(value)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise CatalogError(f"data_home_namespace must stay inside Graph Data Home: {repository_id}")


def _state_namespace_key(value: str) -> str:
    return "/".join(Path(value).parts)


def _validate_glob_pattern(pattern: str, *, field_name: str) -> None:
    if not isinstance(pattern, str) or not pattern.strip():
        raise CatalogError(f"{field_name} glob must not be empty")
    path = Path(pattern)
    if pattern.strip() in {".", ".."} or path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise CatalogError(f"{field_name} glob must stay inside the repository root: {pattern!r}")
