"""Read Protocols for project-to-Vault links, owned by project context (M12).

Integration configuration (M17) implements them: ``project-bindings.json`` through
``ProjectBindingReader`` and ``vault-map.json`` through ``VaultMapReader``.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, runtime_checkable

from vault_graph.project.context.project_binding import ProjectBinding


class ProjectBindingReader(Protocol):
    """Read already-validated project bindings. Integration configuration implements it."""

    def entries(self) -> tuple[ProjectBinding, ...]: ...

    def resolve(self, repository_id: str) -> ProjectBinding:
        """Return the binding or raise ``ValueError`` when the repository has none."""
        ...


@dataclass(frozen=True)
class MappedVault:
    """One Vault listed in ``vault-map.json``. ``path`` is resolved to its real location."""

    name: str
    path: Path
    role: str


@dataclass(frozen=True)
class MappedProjectMatch:
    """The ``vault-map.json`` project found for a folder.

    ``project_id`` is None when no project is chosen. ``candidates`` then lists the ids
    that matched in the same stage, so callers can tell "several match" from "none".
    """

    project_id: str | None
    stage: str | None
    vaults: tuple[MappedVault, ...]
    candidates: tuple[str, ...] = ()
    reason: str | None = None


@runtime_checkable
class VaultMapReader(Protocol):
    """Read project-to-Vault links from ``vault-map.json`` without writing anything."""

    @property
    def vaults(self) -> tuple[MappedVault, ...]: ...

    def find_project(self, cwd: Path) -> MappedProjectMatch: ...

    def vaults_for(self, cwd: Path) -> tuple[MappedVault, ...]: ...


__all__ = ["MappedProjectMatch", "MappedVault", "ProjectBindingReader", "VaultMapReader"]
