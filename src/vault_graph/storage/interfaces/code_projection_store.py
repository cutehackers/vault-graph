"""Stable storage boundary for the rebuildable code projection."""

from __future__ import annotations

from typing import Protocol

from vault_graph.code_index.code_models import (
    CodeApplyResult,
    CodeFileSnapshot,
    CodeManifest,
    CodeReconcilePlan,
    CodeSymbolHit,
    CodeSymbolQuery,
    CodeSymbolRecord,
    CodeTraversalQuery,
    CodeTraversalResult,
    PendingCodeReference,
)
from vault_graph.storage.interfaces.store_health import StoreHealth


class CodeProjectionStore(Protocol):
    """Read/write contract implemented by the local SQLite projection."""

    def health(self) -> StoreHealth:
        """Report schema, parser, policy, and endpoint compatibility."""

        ...

    def current_manifest(self, repository_ids: tuple[str, ...]) -> CodeManifest:
        """Return the active manifest, optionally narrowed to repositories."""

        ...

    def pending_paths(self, repository_ids: tuple[str, ...]) -> tuple[str, ...]:
        """Return source-relative paths that still have unresolved references."""

        ...

    def file_snapshots(self, repository_ids: tuple[str, ...]) -> tuple[CodeFileSnapshot, ...]:
        """Return indexed file fingerprints for verification and carry-forward."""

        ...

    def symbols(self, repository_ids: tuple[str, ...]) -> tuple[CodeSymbolRecord, ...]:
        """Return indexed structural symbols for a repository scope."""

        ...

    def pending_references(self, repository_ids: tuple[str, ...]) -> tuple[PendingCodeReference, ...]:
        """Return unresolved references for a repository scope."""

        ...

    def record_freshness(self, state: str, warnings: tuple[str, ...] = ()) -> None:
        """Persist the result of the last staged run."""

        ...

    def last_freshness(self) -> tuple[str, tuple[str, ...]]:
        """Return the last persisted run freshness state and diagnostics."""

        ...

    def apply_reconcile_plan(self, plan: CodeReconcilePlan) -> CodeApplyResult:
        """Apply one complete desired-state transaction to the code projection."""

        ...

    def search_symbols(self, query: CodeSymbolQuery) -> tuple[CodeSymbolHit, ...]:
        """Search metadata-only symbol fields through the structural index."""

        ...

    def get_symbol(self, symbol_id: str) -> CodeSymbolRecord | None:
        """Resolve one symbol identity."""

        ...

    def traverse(self, query: CodeTraversalQuery) -> CodeTraversalResult:
        """Traverse confident or explicitly requested uncertain relationships."""

        ...


__all__ = ["CodeProjectionStore"]
