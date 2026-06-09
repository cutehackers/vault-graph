from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from vault_graph.errors import SearchError
from vault_graph.ingestion.vault_catalog import QueryScope
from vault_graph.retrieval.retrieval_result import RetrievalResult, RetrievalSeverity

SearchOutputFormat = Literal["text", "json"]


@dataclass(frozen=True)
class SearchStoreRevision:
    kind: str
    revision: str
    scope_key: str
    vault_id: str | None = None

    def __post_init__(self) -> None:
        _require_non_empty(self.kind, "kind")
        _require_non_empty(self.revision, "revision")
        _require_non_empty(self.scope_key, "scope_key")


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
    effective_scopes: tuple[QueryScope, ...]
    limit: int
    output_format: SearchOutputFormat

    def __post_init__(self) -> None:
        if not self.query_text.strip():
            raise SearchError("query_text is required")
        if self.limit <= 0:
            raise SearchError("limit must be positive")
        if self.output_format not in ("text", "json"):
            raise SearchError("unsupported_format")


@dataclass(frozen=True)
class SearchResponse:
    query_text: str
    requested_scope: QueryScope
    effective_scopes: tuple[QueryScope, ...]
    limit: int
    result_count: int
    candidate_count: int
    dropped_candidate_count: int
    results: tuple[RetrievalResult, ...]
    warnings: tuple[SearchWarning, ...]
    degraded: bool
    store_revisions: tuple[SearchStoreRevision, ...]
    generated_at: str

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
