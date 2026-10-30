"""Graph run status port. Composition injects the local JSON store (보완4)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from vault_graph.operation.scope.vault_catalog import QueryScope
from vault_graph.retrieval.graph.graph_contracts import GraphExtractionSpec


@dataclass(frozen=True)
class GraphRunStatus:
    scope_key: str
    graph_spec_key: str
    last_success_revision: str | None = None
    last_success_at: str | None = None
    last_error: str | None = None
    last_error_at: str | None = None


class GraphStatusStore(Protocol):
    def read(self, *, scope_key: str, graph_spec_key: str) -> GraphRunStatus: ...

    def record_success(self, *, scope_key: str, graph_spec_key: str, graph_index_revision: str) -> None: ...

    def record_failure(self, *, scope_key: str, graph_spec_key: str, error: str) -> None: ...


def graph_spec_key(spec: GraphExtractionSpec) -> str:
    return f"{spec.spec_version}|{spec.spec_digest}"


def graph_scope_status_key(scope: QueryScope) -> str:
    cross_vault = "cross" if scope.include_cross_vault else "local"
    return f"{','.join(scope.vault_ids)}:{','.join(scope.content_scopes)}:{cross_vault}"
