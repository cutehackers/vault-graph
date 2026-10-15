"""Compatibility import path for Vault Graph's vector storage adapter."""

from vault_graph.vault_adapter.vector_store import (
    CHROMA_BACKEND,
    CHROMA_VECTOR_SCHEMA_VERSION,
    COLLECTION_PREFIX,
)
from vault_graph.vault_adapter.vector_store import (
    ChromaVectorStore as _VaultChromaVectorStore,
)

SQLITE_VECTOR_ID_BATCH_SIZE = 500


class ChromaVectorStore(_VaultChromaVectorStore):
    def _query_batch_size(self) -> int:
        return SQLITE_VECTOR_ID_BATCH_SIZE


__all__ = ["CHROMA_BACKEND", "CHROMA_VECTOR_SCHEMA_VERSION", "COLLECTION_PREFIX", "ChromaVectorStore"]
