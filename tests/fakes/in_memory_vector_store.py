from __future__ import annotations

from vault_graph.embeddings.text_embeddings import EmbeddingModelSpec, EmbeddingVector
from vault_graph.errors import VectorStoreError
from vault_graph.ingestion.vault_catalog import QueryScope
from vault_graph.storage.interfaces.store_health import StoreHealth
from vault_graph.storage.interfaces.vector_store import (
    VectorEmbeddingRecord,
    VectorHit,
    VectorManifestRecord,
    VectorQuery,
    VectorTombstone,
)


class InMemoryVectorStore:
    def __init__(self) -> None:
        self._records: dict[tuple[str, str], VectorEmbeddingRecord] = {}
        self._embedding_spec: EmbeddingModelSpec | None = None

    def apply_vector_revision(
        self,
        *,
        vector_index_revision: str,
        records: tuple[VectorEmbeddingRecord, ...],
        tombstones: tuple[VectorTombstone, ...],
    ) -> None:
        if not vector_index_revision:
            raise VectorStoreError("vector_index_revision is required")
        next_embedding_spec = self._validated_embedding_spec(records)
        for record in records:
            if record.vector_index_revision != vector_index_revision:
                raise VectorStoreError("record vector_index_revision must match revision being applied")
        for tombstone in tombstones:
            self._records.pop((tombstone.vault_id, tombstone.chunk_id), None)
        for record in records:
            self._records[(record.vault_id, record.chunk_id)] = record
        self._embedding_spec = next_embedding_spec

    def search(self, query: VectorQuery) -> tuple[VectorHit, ...]:
        if self._embedding_spec is not None and query.embedding_spec != self._embedding_spec:
            raise VectorStoreError("embedding model spec mismatch")
        scoped_records = tuple(record for record in self._records.values() if _record_in_scope(record, query.scope))
        scored = sorted(
            ((_dot_product(query.query_vector, record.embedding), record) for record in scoped_records),
            key=lambda item: (-item[0], item[1].vault_id, item[1].chunk_id, item[1].vector_id),
        )
        return tuple(
            VectorHit(
                vector_id=record.vector_id,
                vault_id=record.vault_id,
                document_id=record.document_id,
                chunk_id=record.chunk_id,
                content_scope=record.content_scope,
                score=score,
                rank=rank,
                embedding_spec=record.embedding.model_spec,
                metadata_index_revision=record.metadata_index_revision,
                vector_index_revision=record.vector_index_revision,
                backend="memory-vector",
            )
            for rank, (score, record) in enumerate(scored[: query.limit], start=1)
        )

    def health(self) -> StoreHealth:
        return StoreHealth(
            ok=True,
            backend="memory-vector",
            schema_version="memory-vector-v1",
            schema_compatible=True,
            message="ok",
        )

    def export_manifest(self, scope: QueryScope) -> tuple[VectorManifestRecord, ...]:
        records = sorted(
            (record for record in self._records.values() if _record_in_scope(record, scope)),
            key=lambda record: (record.vault_id, record.chunk_id, record.vector_id),
        )
        return tuple(
            VectorManifestRecord(
                vector_id=record.vector_id,
                vault_id=record.vault_id,
                document_id=record.document_id,
                chunk_id=record.chunk_id,
                content_scope=record.content_scope,
                embedding_spec=record.embedding.model_spec,
                metadata_index_revision=record.metadata_index_revision,
                vector_index_revision=record.vector_index_revision,
                backend="memory-vector",
            )
            for record in records
        )

    def _validated_embedding_spec(self, records: tuple[VectorEmbeddingRecord, ...]) -> EmbeddingModelSpec | None:
        next_embedding_spec = self._embedding_spec
        for record in records:
            if next_embedding_spec is None:
                next_embedding_spec = record.embedding.model_spec
            elif next_embedding_spec != record.embedding.model_spec:
                raise VectorStoreError("embedding model spec mismatch")
        return next_embedding_spec


def _record_in_scope(record: VectorEmbeddingRecord, scope: QueryScope) -> bool:
    return record.vault_id in scope.vault_ids and _content_scope_in_scope(
        record_scope=record.content_scope,
        query_scopes=scope.content_scopes,
    )


def _content_scope_in_scope(*, record_scope: str, query_scopes: tuple[str, ...]) -> bool:
    return any(
        record_scope == query_scope or record_scope.startswith(f"{query_scope}/") for query_scope in query_scopes
    )


def _dot_product(left: EmbeddingVector, right: EmbeddingVector) -> float:
    if left.model_spec != right.model_spec:
        raise VectorStoreError("embedding model spec mismatch")
    return sum(left_value * right_value for left_value, right_value in zip(left.values, right.values, strict=True))
