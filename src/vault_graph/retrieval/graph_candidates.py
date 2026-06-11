from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from vault_graph.ingestion.vault_catalog import QueryScope
from vault_graph.retrieval.retrieval_candidate import RetrievalCandidate
from vault_graph.retrieval.search_response import SearchStoreRevision, SearchWarning


@dataclass(frozen=True)
class GraphCandidateResult:
    candidates: tuple[RetrievalCandidate, ...]
    warnings: tuple[SearchWarning, ...]
    store_revisions: tuple[SearchStoreRevision, ...]


class GraphCandidateProvider(Protocol):
    def candidates(
        self,
        *,
        query_text: str,
        requested_scope: QueryScope,
        actual_scopes: tuple[QueryScope, ...],
        limit: int,
        include_cross_vault: bool,
    ) -> GraphCandidateResult:
        raise NotImplementedError


class GraphSearchSource(Protocol):
    def graph_candidates_for_search(
        self,
        *,
        query_text: str,
        requested_scope: QueryScope,
        actual_scopes: tuple[QueryScope, ...],
        limit: int,
        include_cross_vault: bool,
    ) -> GraphCandidateResult:
        raise NotImplementedError
