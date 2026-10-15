"""Compatibility path for Vault-specific vector indexing."""

from vault_graph.indexing.vector_index_adapter import (
    ChunkListingStore,
    VectorApplyResult,
    VectorIndexer,
    VectorRevisionPlan,
    stable_vector_id,
)

__all__ = ["ChunkListingStore", "VectorApplyResult", "VectorIndexer", "VectorRevisionPlan", "stable_vector_id"]
