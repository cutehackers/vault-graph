"""Storage interface contracts."""

from vault_graph.storage.interfaces.graph_store import (
    GraphEntityIdentity,
    GraphEntityMatch,
    GraphEntityQuery,
    GraphEntityQueryResult,
    GraphRelationshipIdentity,
    GraphRelationshipQuery,
    GraphRelationshipQueryResult,
    GraphStore,
)
from vault_graph.storage.interfaces.keyword_index import KeywordHit, KeywordIndex, KeywordQuery

__all__ = [
    "GraphEntityIdentity",
    "GraphEntityMatch",
    "GraphEntityQuery",
    "GraphEntityQueryResult",
    "GraphRelationshipIdentity",
    "GraphRelationshipQuery",
    "GraphRelationshipQueryResult",
    "GraphStore",
    "KeywordHit",
    "KeywordIndex",
    "KeywordQuery",
]
