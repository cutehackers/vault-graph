"""Query scope resolution, plus the project-to-Vault choice for a working folder.

``resolve_project_vaults`` applies the phase 1 order of spec 4.2.2: a ``vault-map.json``
project wins. Only when the map is absent or has no project for the folder does
``project-bindings.json`` decide. Nothing here writes to the Graph Home.

``default_query_vaults`` applies the search order of spec V2 when a request names no scope:
the registered Vaults linked to the ``cwd`` project, else None so the caller uses the active Vault.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from vault_graph.errors import VaultGraphError
from vault_graph.interface.composition.vault_labels import VaultLabel, vault_labels
from vault_graph.operation.integration.vault_map import open_vault_map
from vault_graph.operation.scope.query_scope_resolution import actual_query_scopes
from vault_graph.operation.scope.vault_catalog import VaultCatalog
from vault_graph.project.context.project_binding_reader import MappedVault, ProjectBindingReader, VaultMapReader
from vault_graph.storage.interfaces.metadata_store import MetadataStore

PROJECT_SCOPE_WARNING_CODE = "project_vault_scope"

ProjectVaultSource = Literal["vault-map", "project-bindings"]


@dataclass(frozen=True)
class ProjectVaultResolution:
    """Registered Graph Home Vault ids linked to a folder.

    ``project_id`` is the map project id or the bound repository id. ``unregistered_vaults``
    lists map Vaults whose real path matches no registered Vault. ``reason`` explains an
    empty result.
    """

    source: ProjectVaultSource | None
    project_id: str | None
    vault_ids: tuple[str, ...]
    unregistered_vaults: tuple[MappedVault, ...] = ()
    reason: str | None = None


def resolve_project_vaults(
    cwd: Path,
    *,
    vault_map: VaultMapReader | None,
    vault_catalog: VaultCatalog,
    bindings: ProjectBindingReader | None = None,
    repository_roots: Mapping[str, Path] | None = None,
) -> ProjectVaultResolution:
    reasons: list[str] = []
    if vault_map is not None:
        match = vault_map.find_project(cwd)
        if match.project_id is not None:
            registered, unregistered = registered_vault_ids(match.vaults, vault_catalog)
            return ProjectVaultResolution(
                source="vault-map",
                project_id=match.project_id,
                vault_ids=registered,
                unregistered_vaults=unregistered,
                reason=None if registered else "No vault of the map project is registered in the Graph Home.",
            )
        if match.candidates:
            return ProjectVaultResolution(source=None, project_id=None, vault_ids=(), reason=match.reason)
        if match.reason is not None:
            reasons.append(match.reason)
    repository_id = _bound_repository(cwd, bindings, repository_roots or {})
    if bindings is not None and repository_id is not None:
        return ProjectVaultResolution(
            source="project-bindings",
            project_id=repository_id,
            vault_ids=bindings.resolve(repository_id).vault_ids,
        )
    reasons.append(f"{cwd} has no project binding.")
    return ProjectVaultResolution(source=None, project_id=None, vault_ids=(), reason=" ".join(reasons))


def registered_vault_ids(
    vaults: tuple[MappedVault, ...], vault_catalog: VaultCatalog
) -> tuple[tuple[str, ...], tuple[MappedVault, ...]]:
    """Split map Vaults into registered ids and unregistered Vaults by comparing real paths."""
    by_path = {_real(entry.root_path): entry.vault_id for entry in vault_catalog.entries()}
    registered: list[str] = []
    unregistered: list[MappedVault] = []
    for vault in vaults:
        vault_id = by_path.get(_real(vault.path))
        if vault_id is None:
            unregistered.append(vault)
        elif vault_id not in registered:
            registered.append(vault_id)
    return tuple(registered), tuple(unregistered)


@dataclass(frozen=True)
class DefaultQueryVaults:
    """Vault ids for a request without ``scope``.

    ``vault_ids`` is None when ``cwd`` belongs to no map project: the caller uses the active Vault.
    An empty tuple means the project has no searchable Vault: the caller returns no results.
    """

    vault_ids: tuple[str, ...] | None
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class ProjectQuerySelection:
    """Default Vault ids, result labels and warnings read from one ``vault-map.json`` opening."""

    vault_ids: tuple[str, ...] | None
    labels: Mapping[str, VaultLabel] = field(default_factory=dict)
    warnings: tuple[str, ...] = ()


def default_query_vault_ids(
    cwd: Path, *, vault_map: VaultMapReader | None, vault_catalog: VaultCatalog
) -> tuple[str, ...] | None:
    return default_query_vaults(cwd, vault_map=vault_map, vault_catalog=vault_catalog).vault_ids


def default_query_vaults(
    cwd: Path,
    *,
    vault_map: VaultMapReader | None,
    vault_catalog: VaultCatalog,
    is_indexed: Callable[[str], bool] | None = None,
) -> DefaultQueryVaults:
    """Return every registered, enabled Vault of the ``cwd`` map project, in map order.

    Map Vaults that are unregistered, disabled or (when ``is_indexed`` is given) not indexed are
    named in the warnings. A project with no registered Vault does not fall back to the active Vault.
    """
    resolution = resolve_project_vaults(cwd, vault_map=vault_map, vault_catalog=vault_catalog)
    if resolution.source is None:
        return DefaultQueryVaults(vault_ids=None)
    names = _map_names_by_vault_id(vault_map, vault_catalog)
    warnings: list[str] = []
    unregistered = [vault.name for vault in resolution.unregistered_vaults]
    if unregistered:
        warnings.append(
            f"Vault {', '.join(unregistered)} of project {resolution.project_id} is not registered "
            "in the Graph Home and was not searched. Run `vg setup`."
        )
    disabled = [vault_id for vault_id in resolution.vault_ids if not vault_catalog.resolve(vault_id).enabled]
    if disabled:
        warnings.append(
            f"Vault {', '.join(names.get(vault_id, vault_id) for vault_id in disabled)} of project "
            f"{resolution.project_id} is disabled and was not searched."
        )
    vault_ids = tuple(vault_id for vault_id in resolution.vault_ids if vault_id not in disabled)
    if is_indexed is not None:
        unindexed = [vault_id for vault_id in vault_ids if not is_indexed(vault_id)]
        if unindexed:
            warnings.append(
                f"Vault {', '.join(names.get(vault_id, vault_id) for vault_id in unindexed)} of project "
                f"{resolution.project_id} is not indexed and returned no results. Run `vg index`."
            )
    if not vault_ids and not unregistered:
        warnings.append(f"Project {resolution.project_id} has no searchable Vault. Run `vg setup`.")
    return DefaultQueryVaults(vault_ids=vault_ids, warnings=tuple(warnings))


def project_query_selection(
    cwd: Path | None,
    *,
    catalog: VaultCatalog,
    vault_map_file: Path,
    is_indexed: Callable[[str], bool] | None = None,
) -> ProjectQuerySelection:
    """Open ``vault-map.json`` once for one request.

    ``cwd`` None means the request named its own scope: only labels are read, and no warning is
    added, so explicit-scope output changes only by the two label fields. A missing map is normal.
    A damaged map gives one warning, and the active Vault is used.
    """
    opening = open_vault_map(vault_map_file)
    labels = vault_labels(opening.vault_map, catalog)
    if cwd is None:
        return ProjectQuerySelection(vault_ids=None, labels=labels)
    warnings = (opening.warning,) if opening.warning else ()
    if opening.vault_map is None:
        return ProjectQuerySelection(vault_ids=None, labels=labels, warnings=warnings)
    resolved = default_query_vaults(cwd, vault_map=opening.vault_map, vault_catalog=catalog, is_indexed=is_indexed)
    return ProjectQuerySelection(vault_ids=resolved.vault_ids, labels=labels, warnings=warnings + resolved.warnings)


def metadata_index_check(metadata_store: MetadataStore) -> Callable[[str], bool]:
    """Return ``is_indexed`` for ``default_query_vaults``: a Vault is indexed when it has a document.

    A metadata read error counts as indexed. The search itself then reports the unreadable store.
    """

    def is_indexed(vault_id: str) -> bool:
        try:
            states = metadata_store.list_document_states((vault_id,))
        except (VaultGraphError, sqlite3.Error):
            return True
        return any(state.document_id is not None for state in states)

    return is_indexed


def project_scope_warning_json(message: str) -> dict[str, object]:
    """A project scope warning in the search warning JSON shape. It names Vaults by map name, not by id."""
    return {
        "code": PROJECT_SCOPE_WARNING_CODE,
        "message": message,
        "severity": "warning",
        "affected_vault_ids": [],
        "scope_key": None,
        "document_id": None,
        "chunk_id": None,
        "source_id": None,
    }


def empty_project_search_json(*, query_text: str, limit: int, warnings: tuple[str, ...]) -> dict[str, object]:
    """Search JSON with no results for a project whose Vaults are not searchable. Same keys as a search."""
    return {
        "query_text": query_text,
        "requested_scope": {"vault_ids": [], "content_scopes": [], "include_cross_vault": False},
        "actual_scopes": [],
        "limit": limit,
        "result_count": 0,
        "candidate_count": 0,
        "dropped_candidate_count": 0,
        "results": [],
        "warnings": [project_scope_warning_json(message) for message in warnings],
        "degraded": bool(warnings),
        "store_revisions": [],
        "generated_at": datetime.now(UTC).isoformat(),
        "result_family_duplication": 0.0,
    }


def _map_names_by_vault_id(vault_map: VaultMapReader | None, vault_catalog: VaultCatalog) -> dict[str, str]:
    return {vault_id: label.name for vault_id, label in vault_labels(vault_map, vault_catalog).items()}


def _bound_repository(
    cwd: Path, bindings: ProjectBindingReader | None, repository_roots: Mapping[str, Path]
) -> str | None:
    if bindings is None:
        return None
    bound = {binding.repository_id for binding in bindings.entries()}
    folder = _real(cwd)
    matches = [
        repository_id
        for repository_id, root in repository_roots.items()
        if repository_id in bound and (folder == _real(root) or _real(root) in folder.parents)
    ]
    return matches[0] if len(matches) == 1 else None


def _real(path: Path) -> Path:
    try:
        return path.expanduser().resolve()
    except (OSError, RuntimeError):
        return path.expanduser().absolute()


__all__ = [
    "PROJECT_SCOPE_WARNING_CODE",
    "DefaultQueryVaults",
    "ProjectQuerySelection",
    "ProjectVaultResolution",
    "ProjectVaultSource",
    "actual_query_scopes",
    "default_query_vault_ids",
    "default_query_vaults",
    "empty_project_search_json",
    "metadata_index_check",
    "project_query_selection",
    "project_scope_warning_json",
    "registered_vault_ids",
    "resolve_project_vaults",
]
