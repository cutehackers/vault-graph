from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol

from vault_graph.errors import GraphStoreError

GRAPH_PROJECTION_VERSION = "graph-projection-v1"
MAX_GRAPH_PROJECTION_DEPTH = 2
DEFAULT_GRAPH_RELATED_DEPTH = 1
DEFAULT_GRAPH_RESULT_LIMIT = 10
MAX_GRAPH_RESULT_LIMIT = 50
DEFAULT_GRAPH_TARGET_LIMIT = 20
DEFAULT_GRAPH_RELATIONSHIP_READ_LIMIT = 200
DEFAULT_GRAPH_PROJECTION_EDGE_LIMIT = 500
MAX_GRAPH_PROJECTION_EDGE_LIMIT = 500

GraphProjectionDirection = Literal["out", "in", "both"]


@dataclass(frozen=True)
class GraphProjectionNode:
    vault_id: str
    entity_id: str
    type: str
    name: str
    normalized_name: str


@dataclass(frozen=True)
class GraphProjectionEdge:
    source_vault_id: str
    source_entity_id: str
    target_vault_id: str
    target_entity_id: str
    relationship_id: str
    relationship_type: str
    status: str
    confidence: float
    evidence_ref_ids: tuple[str, ...]
    graph_index_revision: str


@dataclass(frozen=True)
class GraphPath:
    seed: GraphProjectionNode
    target: GraphProjectionNode
    edges: tuple[GraphProjectionEdge, ...]
    depth: int
    score: float
    explanation: str


@dataclass(frozen=True)
class GraphProjectionInput:
    seeds: tuple[GraphProjectionNode, ...]
    nodes: tuple[GraphProjectionNode, ...]
    relationships: tuple[GraphProjectionEdge, ...]
    actual_scope_keys: tuple[str, ...]
    source_graph_revisions: tuple[str, ...]
    max_depth: int
    direction: GraphProjectionDirection
    relationship_types: tuple[str, ...]
    statuses: tuple[str, ...]
    include_cross_vault: bool
    limit: int
    edge_limit: int

    def __post_init__(self) -> None:
        if not self.seeds:
            raise GraphStoreError("graph projection seeds are required")
        if not self.nodes:
            raise GraphStoreError("graph projection nodes are required")
        seed_keys = {(seed.vault_id, seed.entity_id) for seed in self.seeds}
        node_keys = {(node.vault_id, node.entity_id) for node in self.nodes}
        if not seed_keys <= node_keys:
            raise GraphStoreError("graph projection seeds must be present in nodes")
        if self.max_depth <= 0 or self.max_depth > MAX_GRAPH_PROJECTION_DEPTH:
            raise GraphStoreError("unsupported graph projection depth")
        if self.direction not in ("out", "in", "both"):
            raise GraphStoreError("unsupported graph projection direction")
        if self.limit <= 0:
            raise GraphStoreError("graph projection limit must be positive")
        if self.limit > MAX_GRAPH_RESULT_LIMIT:
            raise GraphStoreError("graph projection limit is out of range")
        if self.edge_limit <= 0:
            raise GraphStoreError("graph projection edge_limit must be positive")
        if self.edge_limit > MAX_GRAPH_PROJECTION_EDGE_LIMIT:
            raise GraphStoreError("graph projection edge_limit is out of range")


@dataclass(frozen=True)
class GraphProjectionResult:
    projection_build_id: str
    graph_projection_version: str
    source_graph_revisions: tuple[str, ...]
    node_count: int
    edge_count: int
    truncated: bool
    paths: tuple[GraphPath, ...]


class GraphProjection(Protocol):
    def project(self, request: GraphProjectionInput) -> GraphProjectionResult:
        raise NotImplementedError
