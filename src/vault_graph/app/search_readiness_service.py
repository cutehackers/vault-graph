from __future__ import annotations

from vault_graph.embeddings.text_embeddings import TextEmbeddings
from vault_graph.indexing.vector_indexer import VectorIndexer
from vault_graph.ingestion.vault_catalog import QueryScope
from vault_graph.retrieval.search_readiness import SearchReadinessReport, SearchScopeReadiness
from vault_graph.retrieval.search_response import SearchStoreRevision
from vault_graph.storage.interfaces.keyword_index import KeywordIndex
from vault_graph.storage.interfaces.metadata_store import MetadataStore
from vault_graph.storage.interfaces.store_health import StoreHealth
from vault_graph.storage.interfaces.vector_store import VectorStore


class ReadOnlySearchReadiness:
    def __init__(
        self,
        *,
        metadata_store: MetadataStore,
        keyword_index: KeywordIndex,
        vector_store: VectorStore | None = None,
        text_embeddings: TextEmbeddings | None = None,
    ) -> None:
        self._metadata_store = metadata_store
        self._keyword_index = keyword_index
        self._vector_store = vector_store
        self._text_embeddings = text_embeddings

    def check(self, *, effective_scopes: tuple[QueryScope, ...]) -> SearchReadinessReport:
        metadata_health = self._metadata_store.health()
        keyword_health = self._keyword_index.health()
        vector_health = self._vector_store.health() if self._vector_store is not None else None
        if not metadata_health.ok or not metadata_health.schema_compatible:
            return SearchReadinessReport(
                metadata_health=metadata_health,
                keyword_health=keyword_health,
                vector_health=vector_health,
                vector_stale_count=None,
                can_embed_without_download=False,
                store_revisions=(),
                scope_readiness=(),
            )
        if not keyword_health.ok or not keyword_health.schema_compatible:
            return SearchReadinessReport(
                metadata_health=metadata_health,
                keyword_health=keyword_health,
                vector_health=vector_health,
                vector_stale_count=None,
                can_embed_without_download=False,
                store_revisions=(),
                scope_readiness=(),
            )
        can_embed = self._text_embeddings.can_embed_without_download() if self._text_embeddings is not None else False
        scope_readiness = self._scope_readiness(effective_scopes=effective_scopes, vector_health=vector_health)
        stale_counts = tuple(item.vector_stale_count for item in scope_readiness if item.vector_stale_count is not None)
        stale_count = sum(stale_counts) if stale_counts else None
        store_revisions = self._store_revisions(effective_scopes=effective_scopes, vector_health=vector_health)
        return SearchReadinessReport(
            metadata_health=metadata_health,
            keyword_health=keyword_health,
            vector_health=vector_health,
            vector_stale_count=stale_count,
            can_embed_without_download=can_embed,
            store_revisions=store_revisions,
            scope_readiness=scope_readiness,
        )

    def _scope_readiness(
        self,
        *,
        effective_scopes: tuple[QueryScope, ...],
        vector_health: StoreHealth | None,
    ) -> tuple[SearchScopeReadiness, ...]:
        readiness: list[SearchScopeReadiness] = []
        for scope in effective_scopes:
            stale_count = self._vector_stale_count(scope=scope, vector_health=vector_health)
            readiness.append(
                SearchScopeReadiness(
                    scope_key=_scope_key(scope),
                    vault_ids=scope.vault_ids,
                    vector_stale_count=stale_count,
                )
            )
        return tuple(readiness)

    def _vector_stale_count(self, *, scope: QueryScope, vector_health: StoreHealth | None) -> int | None:
        if self._vector_store is None or self._text_embeddings is None or vector_health is None:
            return None
        if not vector_health.ok or not vector_health.schema_compatible:
            return None
        plan = VectorIndexer(
            chunk_store=self._metadata_store,
            vector_store=self._vector_store,
            text_embeddings=self._text_embeddings,
        ).plan(scopes=(scope,), full=False)
        return plan.upsert_count + plan.tombstone_count

    def _store_revisions(
        self,
        *,
        effective_scopes: tuple[QueryScope, ...],
        vector_health: StoreHealth | None,
    ) -> tuple[SearchStoreRevision, ...]:
        revisions: list[SearchStoreRevision] = []
        for scope in effective_scopes:
            scope_key = _scope_key(scope)
            chunks = self._metadata_store.list_chunks(scope)
            metadata_revision = _revision_from_values(
                tuple(chunk.index_revision for chunk in chunks),
                fallback=f"empty:{self._metadata_store.health().schema_version}",
            )
            vault_id = scope.vault_ids[0] if len(scope.vault_ids) == 1 else None
            revisions.append(
                SearchStoreRevision(kind="metadata", revision=metadata_revision, scope_key=scope_key, vault_id=vault_id)
            )
            revisions.append(
                SearchStoreRevision(
                    kind="keyword",
                    revision=self._keyword_index.index_revision(scope),
                    scope_key=scope_key,
                    vault_id=vault_id,
                )
            )
            if self._vector_store is not None and vector_health is not None and vector_health.ok:
                manifest = self._vector_store.export_manifest(scope)
                vector_revision = _revision_from_values(
                    tuple(row.vector_index_revision for row in manifest),
                    fallback=f"empty:{vector_health.schema_version}",
                )
                revisions.append(
                    SearchStoreRevision(
                        kind="vector",
                        revision=vector_revision,
                        scope_key=scope_key,
                        vault_id=vault_id,
                    )
                )
        return tuple(revisions)


def _scope_key(scope: QueryScope) -> str:
    return f"{','.join(scope.vault_ids)}:{','.join(scope.content_scopes)}"


def _revision_from_values(values: tuple[str | None, ...], *, fallback: str) -> str:
    revisions = tuple(sorted({value for value in values if value}))
    return ",".join(revisions) if revisions else fallback
