from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from vault_graph.errors import CatalogError

DEFAULT_CONTENT_SCOPES = ("raw", "wiki", "docs", "scratch/reports")
ALLOWED_CONTENT_ROOTS = ("raw", "wiki", "docs", "scratch")


@dataclass(frozen=True)
class QueryScope:
    vault_ids: tuple[str, ...]
    content_scopes: tuple[str, ...] = DEFAULT_CONTENT_SCOPES
    include_cross_vault: bool = False

    def __post_init__(self) -> None:
        if not self.vault_ids:
            raise CatalogError("QueryScope requires at least one vault_id")
        for content_scope in self.content_scopes:
            _validate_content_scope_value(content_scope)


@dataclass(frozen=True)
class VaultCatalogEntry:
    vault_id: str
    root_path: Path
    display_name: str
    enabled: bool
    content_scopes: tuple[str, ...]
    state_namespace: str
    git_revision_policy: str

    @classmethod
    def from_root(
        cls,
        *,
        vault_id: str,
        root_path: Path,
        display_name: str | None = None,
        enabled: bool = True,
        content_scopes: Iterable[str] = DEFAULT_CONTENT_SCOPES,
        state_namespace: str | None = None,
        git_revision_policy: str = "head",
    ) -> VaultCatalogEntry:
        if not vault_id:
            raise CatalogError("vault_id is required")
        resolved_root = root_path.expanduser().resolve()
        if not resolved_root.exists() or not resolved_root.is_dir():
            raise CatalogError(f"vault root does not exist: {resolved_root}")
        scope_tuple = tuple(content_scopes)
        if not scope_tuple:
            raise CatalogError(f"content_scopes is required for vault_id: {vault_id}")
        for content_scope in scope_tuple:
            _validate_content_scope(root_path=resolved_root, content_scope=content_scope)
        return cls(
            vault_id=vault_id,
            root_path=resolved_root,
            display_name=display_name or vault_id,
            enabled=enabled,
            content_scopes=scope_tuple,
            state_namespace=state_namespace or vault_id,
            git_revision_policy=git_revision_policy,
        )


class VaultCatalog:
    def __init__(self, *, entries: tuple[VaultCatalogEntry, ...], active_vault_id: str) -> None:
        if not entries:
            raise CatalogError("VaultCatalog requires at least one entry")
        self._entries = entries
        self._active_vault_id = active_vault_id
        self._by_id = {entry.vault_id: entry for entry in entries}
        if len(self._by_id) != len(entries):
            raise CatalogError("duplicate vault_id in VaultCatalog")
        if active_vault_id not in self._by_id:
            raise CatalogError(f"active vault_id is not registered: {active_vault_id}")

    @classmethod
    def from_entries(cls, *, entries: Iterable[VaultCatalogEntry], active_vault_id: str) -> VaultCatalog:
        return cls(entries=tuple(entries), active_vault_id=active_vault_id)

    @classmethod
    def load(cls, path: Path) -> VaultCatalog:
        if not path.exists():
            raise CatalogError(f"VaultCatalog config does not exist: {path}")
        loaded = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        if not isinstance(loaded, dict):
            raise CatalogError(f"VaultCatalog config must be a mapping: {path}")
        entries = [
            VaultCatalogEntry.from_root(
                vault_id=str(item["vault_id"]),
                root_path=Path(str(item["root_path"])),
                display_name=str(item["display_name"]) if item.get("display_name") is not None else None,
                enabled=bool(item.get("enabled", True)),
                content_scopes=item.get("content_scopes", DEFAULT_CONTENT_SCOPES),
                state_namespace=str(item["state_namespace"]) if item.get("state_namespace") is not None else None,
                git_revision_policy=str(item.get("git_revision_policy", "head")),
            )
            for item in loaded.get("vaults", [])
            if isinstance(item, dict)
        ]
        return cls.from_entries(entries=entries, active_vault_id=str(loaded.get("active_vault_id", "default")))

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        payload: dict[str, Any] = {
            "active_vault_id": self._active_vault_id,
            "vaults": [
                {
                    "vault_id": entry.vault_id,
                    "root_path": str(entry.root_path),
                    "display_name": entry.display_name,
                    "enabled": entry.enabled,
                    "content_scopes": list(entry.content_scopes),
                    "state_namespace": entry.state_namespace,
                    "git_revision_policy": entry.git_revision_policy,
                }
                for entry in self._entries
            ],
        }
        path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")

    @property
    def active_vault_id(self) -> str:
        return self._active_vault_id

    def entries(self) -> tuple[VaultCatalogEntry, ...]:
        return self._entries

    def resolve(self, vault_id: str) -> VaultCatalogEntry:
        try:
            return self._by_id[vault_id]
        except KeyError as exc:
            raise CatalogError(f"unknown vault_id: {vault_id}") from exc

    def default_scope(self) -> QueryScope:
        entry = self.resolve(self._active_vault_id)
        return QueryScope(vault_ids=(entry.vault_id,), content_scopes=entry.content_scopes)

    def scope_for_vault_ids(self, vault_ids: Iterable[str]) -> QueryScope:
        entries = tuple(self.resolve(vault_id) for vault_id in vault_ids)
        if not entries:
            raise CatalogError("QueryScope requires at least one vault_id")
        return QueryScope(
            vault_ids=tuple(entry.vault_id for entry in entries),
            content_scopes=_union_content_scopes(entries),
        )

    def scope_for_all_enabled(self) -> QueryScope:
        enabled = tuple(entry for entry in self._entries if entry.enabled)
        if not enabled:
            raise CatalogError("no enabled VaultCatalog entries")
        return QueryScope(
            vault_ids=tuple(entry.vault_id for entry in enabled),
            content_scopes=_union_content_scopes(enabled),
        )


def _union_content_scopes(entries: tuple[VaultCatalogEntry, ...]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(scope for entry in entries for scope in entry.content_scopes))


def _validate_content_scope(*, root_path: Path, content_scope: str) -> None:
    _validate_content_scope_value(content_scope)
    scope_path = Path(content_scope)
    if scope_path.is_absolute():
        raise CatalogError(f"content scope must stay inside Vault root: {content_scope}")
    resolved_scope = (root_path / scope_path).resolve()
    if resolved_scope != root_path and root_path not in resolved_scope.parents:
        raise CatalogError(f"content scope must stay inside Vault root: {content_scope}")


def _validate_content_scope_value(content_scope: str) -> None:
    if not content_scope:
        raise CatalogError("content scope is required")
    parts = Path(content_scope).parts
    if not parts or any(part in {"", ".", ".."} for part in parts):
        raise CatalogError(f"unsupported content scope: {content_scope}")
    if parts[0] not in ALLOWED_CONTENT_ROOTS:
        raise CatalogError(f"unsupported content scope: {content_scope}")
    if parts[0] == "scratch" and (len(parts) < 2 or parts[1] != "reports"):
        raise CatalogError(f"unsupported content scope: {content_scope}")
