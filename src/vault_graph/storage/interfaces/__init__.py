"""Storage interface contracts."""

from vault_graph.storage.interfaces.graph_store import GraphEntityIdentity, GraphRelationshipIdentity, GraphStore
from vault_graph.storage.interfaces.keyword_index import KeywordHit, KeywordIndex, KeywordQuery

__all__ = [
    "GraphEntityIdentity",
    "GraphRelationshipIdentity",
    "GraphStore",
    "KeywordHit",
    "KeywordIndex",
    "KeywordQuery",
]
