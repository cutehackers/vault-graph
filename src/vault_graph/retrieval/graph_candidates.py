from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from vault_graph.errors import GraphStoreError, SearchError
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


class GraphSearchCandidateProvider:
    def __init__(self, *, graph_retrieval_service: GraphSearchSource) -> None:
        self._graph_retrieval_service = graph_retrieval_service

    def candidates(
        self,
        *,
        query_text: str,
        requested_scope: QueryScope,
        actual_scopes: tuple[QueryScope, ...],
        limit: int,
        include_cross_vault: bool,
    ) -> GraphCandidateResult:
        try:
            return self._graph_retrieval_service.graph_candidates_for_search(
                query_text=query_text,
                requested_scope=requested_scope,
                actual_scopes=actual_scopes,
                limit=limit,
                include_cross_vault=include_cross_vault,
            )
        except SearchError as exc:
            return _failed_result(
                code="graph_unavailable",
                message=f"Graph retrieval is unavailable; keyword/vector results returned: {exc}",
                actual_scopes=actual_scopes,
            )
        except GraphStoreError as exc:
            return _failed_result(
                code="graph_query_failed",
                message=f"Graph query failed; keyword/vector results returned: {exc}",
                actual_scopes=actual_scopes,
            )


def _failed_result(*, code: str, message: str, actual_scopes: tuple[QueryScope, ...]) -> GraphCandidateResult:
    return GraphCandidateResult(
        candidates=(),
        warnings=(
            SearchWarning(
                code=code,
                message=message,
                severity="warning",
                affected_vault_ids=_affected_vault_ids(actual_scopes),
            ),
        ),
        store_revisions=(),
    )


def _affected_vault_ids(actual_scopes: tuple[QueryScope, ...]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(vault_id for scope in actual_scopes for vault_id in scope.vault_ids)) or ("unknown",)
