"""Vault Graph adapter for domain-neutral Chroma vector storage."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from pathlib import Path
from typing import Any, cast

from vector_search import ChromaVectorStore as GenericChromaVectorStore
from vector_search import CollectionSpec, StoredVector, VectorDeletion, VectorSearchError

from vault_graph.embeddings.text_embeddings import EmbeddingModelSpec
from vault_graph.errors import VectorStoreError
from vault_graph.ingestion.document_authority import DocumentRole
from vault_graph.ingestion.vault_catalog import QueryScope
from vault_graph.storage.interfaces.store_health import StoreHealth
from vault_graph.storage.interfaces.vector_store import (
    VectorEmbeddingRecord,
    VectorHit,
    VectorManifestRecord,
    VectorQuery,
    VectorStore,
    VectorTombstone,
)

CHROMA_VECTOR_SCHEMA_VERSION = "chroma-vector-v2"
CHROMA_BACKEND = "chroma"
COLLECTION_PREFIX = "vault_graph"
SQLITE_VECTOR_ID_BATCH_SIZE = 500


class ChromaVectorStore(VectorStore):
    def __init__(self, path: Path, *, initialize: bool = False, read_only: bool = False) -> None:
        self._store = GenericChromaVectorStore(
            path,
            initialize=initialize,
            read_only=read_only,
            collection_prefix=COLLECTION_PREFIX,
            payload_table="vault_graph_vector_payloads",
            expected_collection_metadata={
                "vault_graph_backend": CHROMA_BACKEND,
                "vault_graph_schema_version": CHROMA_VECTOR_SCHEMA_VERSION,
            },
            schema_version=CHROMA_VECTOR_SCHEMA_VERSION,
            payload_key_by_collection=False,
            dimension_metadata_key="embedding_dimensions",
            default_distance_metric="cosine",
        )

    def _query_batch_size(self) -> int:
        return SQLITE_VECTOR_ID_BATCH_SIZE

    def apply_vector_revision(
        self,
        *,
        vector_index_revision: str,
        records: tuple[VectorEmbeddingRecord, ...],
        tombstones: tuple[VectorTombstone, ...],
    ) -> None:
        if not vector_index_revision:
            raise VectorStoreError("vector_index_revision is required")
        for record in records:
            if record.vector_index_revision != vector_index_revision:
                raise VectorStoreError("record vector_index_revision must match revision being applied")
        try:
            self._store.apply(
                tuple(
                    (
                        _collection_spec(record.embedding.model_spec),
                        StoredVector(record.vector_id, record.embedding.values, _metadata_for_record(record)),
                    )
                    for record in records
                ),
                tuple(
                    VectorDeletion(
                        _collection_spec(row.embedding_spec),
                        row.vector_id,
                        {
                            "vector_id": row.vector_id,
                            "vault_id": row.vault_id,
                            "chunk_id": row.chunk_id,
                            "embedding_model_name": row.embedding_spec.model_name,
                            "embedding_model_version": row.embedding_spec.model_version,
                            "embedding_dimensions": row.embedding_spec.dimensions,
                            "embedding_spec_version": row.embedding_spec.spec_version,
                        },
                    )
                    for row in tombstones
                ),
            )
        except VectorSearchError as exc:
            raise VectorStoreError(str(exc)) from exc

    def search(self, query: VectorQuery) -> tuple[VectorHit, ...]:
        try:
            matches = self._store.search(
                _collection_spec(query.embedding_spec),
                query.query_vector.values,
                query.limit,
                predicate=lambda metadata: (
                    _metadata_in_scope(metadata, query.scope)
                    and (not query.source_roles or str(metadata["source_role"]) in query.source_roles)
                ),
                tie_key=lambda metadata, record_id: (str(metadata["vault_id"]), str(metadata["chunk_id"]), record_id),
                vector_id_batch_size=self._query_batch_size(),
            )
        except VectorSearchError as exc:
            raise VectorStoreError(str(exc)) from exc
        return tuple(
            VectorHit(
                vector_id=row.record_id,
                vault_id=str(row.metadata["vault_id"]),
                document_id=str(row.metadata["document_id"]),
                chunk_id=str(row.metadata["chunk_id"]),
                content_scope=str(row.metadata["content_scope"]),
                score=row.score,
                rank=row.rank,
                embedding_spec=query.embedding_spec,
                metadata_index_revision=str(row.metadata["metadata_index_revision"]),
                vector_index_revision=str(row.metadata["vector_index_revision"]),
                backend=CHROMA_BACKEND,
                source_role=cast(DocumentRole, str(row.metadata["source_role"])),
                provenance_family_id=str(row.metadata["provenance_family_id"]),
            )
            for row in matches
        )

    def export_manifest(self, scope: QueryScope) -> tuple[VectorManifestRecord, ...]:
        try:
            rows = self._store.export_manifest(lambda metadata: _metadata_in_scope(metadata, scope))
        except VectorSearchError as exc:
            raise VectorStoreError(str(exc)) from exc
        manifest = tuple(_manifest_record_from_metadata(row.record_id, row.metadata) for row in rows)
        return tuple(sorted(manifest, key=lambda row: (row.vault_id, row.chunk_id, row.vector_id)))

    def health(self) -> StoreHealth:
        result = self._store.health()
        return StoreHealth(result.ok, result.backend, result.schema_version, result.schema_compatible, result.message)

    def close(self) -> None:
        self._store.close()


def _collection_spec(spec: EmbeddingModelSpec) -> CollectionSpec:
    digest = hashlib.sha256(
        "|".join((spec.model_name, spec.model_version, str(spec.dimensions), spec.spec_version)).encode("utf-8")
    ).hexdigest()[:32]
    return CollectionSpec(
        name=f"{COLLECTION_PREFIX}_{digest}",
        dimensions=spec.dimensions,
        metadata={
            "vault_graph_backend": CHROMA_BACKEND,
            "vault_graph_schema_version": CHROMA_VECTOR_SCHEMA_VERSION,
            "embedding_model_name": spec.model_name,
            "embedding_model_version": spec.model_version,
            "embedding_dimensions": spec.dimensions,
            "embedding_spec_version": spec.spec_version,
        },
    )


def _metadata_for_record(record: VectorEmbeddingRecord) -> dict[str, str | int]:
    spec = record.embedding.model_spec
    return {
        "vector_id": record.vector_id,
        "vault_id": record.vault_id,
        "document_id": record.document_id,
        "chunk_id": record.chunk_id,
        "content_scope": record.content_scope,
        "embedding_model_name": spec.model_name,
        "embedding_model_version": spec.model_version,
        "embedding_dimensions": spec.dimensions,
        "embedding_spec_version": spec.spec_version,
        "source_chunk_hash": record.source_chunk_hash,
        "chunker_version": record.chunker_version,
        "metadata_index_revision": record.metadata_index_revision,
        "vector_index_revision": record.vector_index_revision,
        "backend_schema_version": CHROMA_VECTOR_SCHEMA_VERSION,
        "source_role": record.source_role,
        "provenance_family_id": record.provenance_family_id,
    }


def _manifest_record_from_metadata(record_id: str, metadata: Mapping[str, Any]) -> VectorManifestRecord:
    return VectorManifestRecord(
        vector_id=record_id,
        vault_id=str(metadata["vault_id"]),
        document_id=str(metadata["document_id"]),
        chunk_id=str(metadata["chunk_id"]),
        content_scope=str(metadata["content_scope"]),
        embedding_spec=EmbeddingModelSpec(
            model_name=str(metadata["embedding_model_name"]),
            model_version=str(metadata["embedding_model_version"]),
            dimensions=int(metadata["embedding_dimensions"]),
            spec_version=str(metadata["embedding_spec_version"]),
        ),
        source_chunk_hash=str(metadata["source_chunk_hash"]),
        chunker_version=str(metadata["chunker_version"]),
        metadata_index_revision=str(metadata["metadata_index_revision"]),
        vector_index_revision=str(metadata["vector_index_revision"]),
        backend=CHROMA_BACKEND,
        backend_schema_version=str(metadata["backend_schema_version"]),
        source_role=cast(DocumentRole, str(metadata["source_role"])),
        provenance_family_id=str(metadata["provenance_family_id"]),
    )


def _metadata_in_scope(metadata: Mapping[str, Any], scope: QueryScope) -> bool:
    record_scope = str(metadata["content_scope"])
    return str(metadata["vault_id"]) in scope.vault_ids and any(
        record_scope == query_scope or record_scope.startswith(f"{query_scope}/")
        for query_scope in scope.content_scopes
    )
