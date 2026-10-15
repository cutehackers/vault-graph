"""Local vector storage independent of embedding and document domains."""

from vector_search.chroma_store import ChromaVectorStore
from vector_search.contracts import (
    CollectionSpec,
    ManifestRecord,
    StoredVector,
    StoreHealth,
    VectorDeletion,
    VectorMatch,
    VectorStore,
)
from vector_search.errors import VectorSearchError

__all__ = [
    "ChromaVectorStore",
    "CollectionSpec",
    "ManifestRecord",
    "StoreHealth",
    "StoredVector",
    "VectorDeletion",
    "VectorMatch",
    "VectorStore",
    "VectorSearchError",
]
