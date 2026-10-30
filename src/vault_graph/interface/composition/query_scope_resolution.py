"""Query scope resolution, plus the project-to-Vault choice for a working folder.

``resolve_project_vaults`` applies the phase 1 order of spec 4.2.2: a ``vault-map.json``
project wins. Only when the map is absent or has no project for the folder does
``project-bindings.json`` decide. Nothing here writes to the Graph Home.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from vault_graph.operation.scope.query_scope_resolution import actual_query_scopes
from vault_graph.operation.scope.vault_catalog import VaultCatalog
from vault_graph.project.context.project_binding_reader import MappedVault, ProjectBindingReader, VaultMapReader

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
    "ProjectVaultResolution",
    "ProjectVaultSource",
    "actual_query_scopes",
    "registered_vault_ids",
    "resolve_project_vaults",
]
