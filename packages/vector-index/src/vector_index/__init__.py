"""Incremental indexing of caller-prepared text, bounded by explicit collection scopes."""

from .chroma_index_store import ChromaIndexStore
from .indexing import (
    IndexedItem,
    IndexedVector,
    IndexItem,
    IndexPlan,
    IndexStore,
    VectorIndex,
    VectorIndexError,
    embed_items,
    model_space_id,
    plan_index,
)

__all__ = [
    "ChromaIndexStore",
    "IndexedItem",
    "IndexedVector",
    "IndexItem",
    "IndexPlan",
    "IndexStore",
    "VectorIndex",
    "VectorIndexError",
    "embed_items",
    "model_space_id",
    "plan_index",
]
