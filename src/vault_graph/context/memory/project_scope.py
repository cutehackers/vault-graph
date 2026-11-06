"""Which Vault pages belong to a project: the one rule for recall, L3 lists and cleanup bundles.

Spec 2026-11-05 §4.4.2. Search does not use this rule: every page stays searchable.

1. A page whose ``project`` names this project is in. One that names only other projects is out.
2. A page without ``project`` is in when its Vault is linked to this project alone.
3. A page without ``project`` in a Vault linked to two or more projects follows the Vault's ``sharable``.

``VaultProjectScope`` values are built by integration configuration (M17 ``vault_map.py``) from
``vault-map.json``. A Vault with no links there (``UNMAPPED_VAULT_SCOPE``) was reached through
this project's own binding, so rule 2 applies to it.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Protocol


class VaultProjectScope(Protocol):
    """The projects linked to one Vault and whether its pages without ``project`` are shared."""

    @property
    def linked_projects(self) -> frozenset[str]: ...

    @property
    def sharable(self) -> bool: ...


@dataclass(frozen=True)
class FixedVaultProjectScope:
    linked_projects: frozenset[str] = frozenset()
    sharable: bool = False


UNMAPPED_VAULT_SCOPE: VaultProjectScope = FixedVaultProjectScope()


def page_in_project(
    frontmatter: Mapping[str, object], project_id: str | None, *, vault_scope: VaultProjectScope
) -> bool:
    projects = page_projects(frontmatter.get("project"))
    if projects:
        return project_id is not None and project_id in projects
    linked = vault_scope.linked_projects
    if len(linked) >= 2:
        return vault_scope.sharable
    return not linked or linked == {project_id}


def page_projects(value: object) -> frozenset[str]:
    """Project ids named by a ``project`` value: a string or a list. Blank items do not count."""
    values = value if isinstance(value, list) else [value]
    return frozenset(text for item in values if item is not None and (text := str(item).strip()))


__all__ = [
    "UNMAPPED_VAULT_SCOPE",
    "FixedVaultProjectScope",
    "VaultProjectScope",
    "page_in_project",
    "page_projects",
]
