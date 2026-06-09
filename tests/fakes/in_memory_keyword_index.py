from __future__ import annotations

from vault_graph.ingestion.vault_catalog import QueryScope
from vault_graph.storage.interfaces.keyword_index import KeywordHit, KeywordQuery
from vault_graph.storage.interfaces.store_health import StoreHealth


class InMemoryKeywordIndex:
    def __init__(
        self,
        hits: tuple[KeywordHit, ...] = (),
        *,
        content_scope_by_key: dict[tuple[str, str], str] | None = None,
    ) -> None:
        self._hits = hits
        self._content_scope_by_key = content_scope_by_key or {}

    def search(self, query: KeywordQuery) -> tuple[KeywordHit, ...]:
        scoped = tuple(
            hit
            for hit in self._hits
            if hit.vault_id in query.scope.vault_ids
            and _content_scope_in_scope(
                record_scope=self._content_scope_by_key.get((hit.vault_id, hit.chunk_id), "wiki"),
                query_scopes=query.scope.content_scopes,
            )
        )
        return scoped[: query.limit]

    def index_revision(self, scope: QueryScope) -> str:
        scoped = tuple(
            hit
            for hit in self._hits
            if hit.vault_id in scope.vault_ids
            and _content_scope_in_scope(
                record_scope=self._content_scope_by_key.get((hit.vault_id, hit.chunk_id), "wiki"),
                query_scopes=scope.content_scopes,
            )
        )
        revisions = tuple(sorted({hit.index_revision for hit in scoped}))
        return ",".join(revisions) if revisions else "empty:memory-keyword-v1"

    def health(self) -> StoreHealth:
        return StoreHealth(
            ok=True,
            backend="memory-keyword",
            schema_version="v1",
            schema_compatible=True,
            message="ok",
        )


def _content_scope_in_scope(*, record_scope: str, query_scopes: tuple[str, ...]) -> bool:
    return any(
        record_scope == query_scope or record_scope.startswith(f"{query_scope}/") for query_scope in query_scopes
    )
