from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from vault_graph.errors import SearchError
from vault_graph.operation.readiness.search_readiness import SearchStoreRevision as SearchStoreRevision
from vault_graph.operation.scope.vault_catalog import QueryScope
from vault_graph.retrieval.search.retrieval_result import RetrievalResult, RetrievalSeverity, RetrievalSignalKind

SearchOutputFormat = Literal["text", "json"]
SearchMode = Literal["knowledge", "evidence", "operating", "audit", "all"]


@dataclass(frozen=True)
class SignalRankTrace:
    """One chunk's rank in one signal's candidate list (keyword, vector or graph)."""

    kind: RetrievalSignalKind
    vault_id: str
    document_id: str
    chunk_id: str
    rank: int
    score: float


@dataclass(frozen=True)
class FusedRankTrace:
    """One chunk's rank after the signals are fused, before role filtering and the fold into documents."""

    vault_id: str
    document_id: str
    chunk_id: str
    rank: int
    fused_score: float


@dataclass(frozen=True)
class DocumentRankTrace:
    """One result's rank after chunks fold into documents, before the request limit cuts the list."""

    rank: int
    result_id: str
    vault_id: str
    document_id: str
    path: str
    evidence_document_ids: tuple[str, ...]


@dataclass(frozen=True)
class SearchStageTrace:
    """Spec 2026-11-11 §4.1.2: ranks at each search stage, for the evaluation tool only.

    Built only when a search asks for it. It describes the last candidate round, so after a refill it holds
    the larger candidate lists. ``candidate_limit`` is the per-signal list size of that round.
    """

    signal_ranks: tuple[SignalRankTrace, ...]
    fused_ranks: tuple[FusedRankTrace, ...]
    document_ranks: tuple[DocumentRankTrace, ...]
    candidate_limit: int
    refilled: bool


@dataclass(frozen=True)
class SearchWarning:
    code: str
    message: str
    severity: RetrievalSeverity
    affected_vault_ids: tuple[str, ...]
    scope_key: str | None = None
    document_id: str | None = None
    chunk_id: str | None = None
    source_id: str | None = None

    def __post_init__(self) -> None:
        _require_non_empty(self.code, "code")
        _require_non_empty(self.message, "message")
        if not isinstance(self.affected_vault_ids, tuple):
            raise SearchError("affected_vault_ids must be an immutable tuple")
        if not self.affected_vault_ids:
            raise SearchError("affected_vault_ids is required")


@dataclass(frozen=True)
class SearchRequest:
    query_text: str
    requested_scope: QueryScope
    actual_scopes: tuple[QueryScope, ...]
    limit: int
    output_format: SearchOutputFormat
    include_graph: bool = False
    include_cross_vault: bool = False
    mode: SearchMode = "knowledge"
    include_retired: bool = False
    trace: bool = False

    def __post_init__(self) -> None:
        if not self.query_text.strip():
            raise SearchError("query_text is required")
        if self.limit <= 0:
            raise SearchError("limit must be positive")
        if self.output_format not in ("text", "json"):
            raise SearchError("unsupported_format")
        if self.mode not in ("knowledge", "evidence", "operating", "audit", "all"):
            raise SearchError("unsupported_search_mode")


@dataclass(frozen=True)
class SearchResponse:
    query_text: str
    requested_scope: QueryScope
    actual_scopes: tuple[QueryScope, ...]
    limit: int
    result_count: int
    candidate_count: int
    dropped_candidate_count: int
    results: tuple[RetrievalResult, ...]
    warnings: tuple[SearchWarning, ...]
    degraded: bool
    store_revisions: tuple[SearchStoreRevision, ...]
    generated_at: str
    result_family_duplication: float = 0.0
    stage_trace: SearchStageTrace | None = None

    def __post_init__(self) -> None:
        if not self.query_text.strip():
            raise SearchError("query_text is required")
        if self.limit <= 0:
            raise SearchError("limit must be positive")
        if self.result_count != len(self.results):
            raise SearchError("result_count must match results")
        if self.candidate_count < 0:
            raise SearchError("candidate_count must not be negative")
        if self.dropped_candidate_count < 0:
            raise SearchError("dropped_candidate_count must not be negative")
        if not isinstance(self.results, tuple):
            raise SearchError("results must be an immutable tuple")
        if not isinstance(self.warnings, tuple):
            raise SearchError("warnings must be an immutable tuple")
        if not isinstance(self.store_revisions, tuple):
            raise SearchError("store_revisions must be an immutable tuple")


def _require_non_empty(value: str, field_name: str) -> None:
    if not value:
        raise SearchError(f"{field_name} is required")
