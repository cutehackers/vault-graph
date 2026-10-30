"""Read Protocol for explicit project bindings, owned by project context (M12)."""

from __future__ import annotations

from typing import Protocol

from vault_graph.project.context.project_binding import ProjectBinding


class ProjectBindingReader(Protocol):
    """Read already-validated project bindings. Integration configuration implements it."""

    def entries(self) -> tuple[ProjectBinding, ...]: ...

    def resolve(self, repository_id: str) -> ProjectBinding:
        """Return the binding or raise ``ValueError`` when the repository has none."""
        ...


__all__ = ["ProjectBindingReader"]
