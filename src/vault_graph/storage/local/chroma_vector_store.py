"""Compatibility import path for Vault Graph's vector storage adapter."""

from __future__ import annotations

from vault_graph.errors import VectorStoreError
from vault_graph.storage.interfaces.text_embeddings import EmbeddingModelSpec
from vault_graph.storage.interfaces.vector_store import (
    VectorMetadataRecord,
    VectorMetadataUpdater,
)
from vault_graph.storage.local.vector_store_adapter import (
    CHROMA_BACKEND,
    CHROMA_VECTOR_SCHEMA_VERSION,
    COLLECTION_PREFIX,
    _collection_spec,
    key_metadata,
)
from vault_graph.storage.local.vector_store_adapter import ChromaVectorStore as _VaultChromaVectorStore

SQLITE_VECTOR_ID_BATCH_SIZE = 500
# Stays below Chroma's max batch size (5461 for the SQLite backend) without asking the client.
METADATA_UPDATE_BATCH_SIZE = 1000


class ChromaVectorStore(_VaultChromaVectorStore, VectorMetadataUpdater):
    def _query_batch_size(self) -> int:
        return SQLITE_VECTOR_ID_BATCH_SIZE

    def supports_metadata_update(self) -> bool:
        return not self._read_only

    def update_metadata(self, records: tuple[VectorMetadataRecord, ...]) -> None:
        """Replace metadata with Chroma `collection.update(ids, metadatas)`. Vectors stay as stored (risk B2)."""
        if self._read_only:
            raise VectorStoreError("read-only ChromaVectorStore cannot update metadata")
        by_spec: dict[EmbeddingModelSpec, list[VectorMetadataRecord]] = {}
        for record in records:
            by_spec.setdefault(record.embedding_spec, []).append(record)
        try:
            for spec, rows in by_spec.items():
                collection = self._store._collection(_collection_spec(spec))
                for start in range(0, len(rows), METADATA_UPDATE_BATCH_SIZE):
                    batch = rows[start : start + METADATA_UPDATE_BATCH_SIZE]
                    ids = [row.vector_id for row in batch]
                    found = set() if collection is None else set(collection.get(ids=ids, include=[])["ids"])
                    missing = [vector_id for vector_id in ids if vector_id not in found]
                    if missing:
                        raise VectorStoreError(f"metadata update for unknown vector: {missing[0]}")
                    assert collection is not None
                    collection.update(ids=ids, metadatas=[_metadata_for_update(row) for row in batch])
        except VectorStoreError:
            raise
        except Exception as exc:
            raise VectorStoreError(f"vector metadata update failed: {exc}") from exc


def _metadata_for_update(record: VectorMetadataRecord) -> dict[str, str | int]:
    """The same keys `apply_vector_revision` writes, so an update leaves no stale key."""
    spec = record.embedding_spec
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
        **key_metadata(record.embedding_key, record.metadata_fingerprint),
    }


__all__ = ["CHROMA_BACKEND", "CHROMA_VECTOR_SCHEMA_VERSION", "COLLECTION_PREFIX", "ChromaVectorStore"]
