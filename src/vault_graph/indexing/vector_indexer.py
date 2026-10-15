"""Compatibility path for Vault-specific vector indexing."""

from vault_graph.vault_adapter.vector_index import (
    ChunkListingStore,
    VectorApplyResult,
    VectorIndexer,
    VectorRevisionPlan,
    stable_vector_id,
)

__all__ = ["ChunkListingStore", "VectorApplyResult", "VectorIndexer", "VectorRevisionPlan", "stable_vector_id"]
