from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from vault_graph.errors import KeywordIndexError
from vault_graph.ingestion.vault_catalog import QueryScope
from vault_graph.storage.interfaces.store_health import StoreHealth


@dataclass(frozen=True)
class KeywordQuery:
    query_text: str
    scope: QueryScope
    limit: int

    def __post_init__(self) -> None:
        if not self.query_text.strip():
            raise KeywordIndexError("query_text is required")
        if self.limit <= 0:
            raise KeywordIndexError("limit must be positive")


@dataclass(frozen=True)
class KeywordHit:
    vault_id: str
    document_id: str
    chunk_id: str
    rank: int
    score: float
    backend: str
    index_revision: str
    matched_fields: tuple[str, ...]

    def __post_init__(self) -> None:
        _require_non_empty(self.vault_id, "vault_id")
        _require_non_empty(self.document_id, "document_id")
        _require_non_empty(self.chunk_id, "chunk_id")
        _require_non_empty(self.backend, "backend")
        _require_non_empty(self.index_revision, "index_revision")
        if self.rank <= 0:
            raise KeywordIndexError("rank must be positive")
        if not isinstance(self.matched_fields, tuple):
            raise KeywordIndexError("matched_fields must be an immutable tuple")


class KeywordIndex(Protocol):
    def search(self, query: KeywordQuery) -> tuple[KeywordHit, ...]: ...

    def index_revision(self, scope: QueryScope) -> str: ...

    def health(self) -> StoreHealth: ...


def _require_non_empty(value: str, field_name: str) -> None:
    if not value:
        raise KeywordIndexError(f"{field_name} is required")
