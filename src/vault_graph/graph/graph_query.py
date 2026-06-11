from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from vault_graph.errors import GraphStoreError
from vault_graph.graph.graph_contracts import EntityRecord, RelationshipRecord
from vault_graph.ingestion.vault_catalog import QueryScope

GraphEntityMatchKind = Literal["entity_id", "canonical_path", "normalized_name", "alias", "contains"]
GraphRelationshipDirection = Literal["out", "in", "both"]

MAX_GRAPH_TARGET_CANDIDATE_LIMIT = 50
DEFAULT_GRAPH_ENTITY_SCAN_LIMIT = 5000
MAX_GRAPH_ENTITY_SCAN_LIMIT = 5000
DEFAULT_GRAPH_RELATIONSHIP_READ_LIMIT = 200
MAX_GRAPH_RELATIONSHIP_READ_LIMIT = 200


@dataclass(frozen=True)
class GraphEntityIdentity:
    vault_id: str
    entity_id: str


@dataclass(frozen=True)
class GraphRelationshipIdentity:
    source_vault_id: str
    relationship_id: str


@dataclass(frozen=True)
class GraphEntityQuery:
    text: str
    actual_scopes: tuple[QueryScope, ...]
    types: tuple[str, ...] = ()
    limit: int = 20
    scan_limit: int = DEFAULT_GRAPH_ENTITY_SCAN_LIMIT

    def __post_init__(self) -> None:
        if not self.text.strip():
            raise GraphStoreError("graph entity query text is required")
        _require_actual_scopes(self.actual_scopes)
        if self.limit <= 0:
            raise GraphStoreError("graph entity query limit must be positive")
        if self.limit > MAX_GRAPH_TARGET_CANDIDATE_LIMIT:
            raise GraphStoreError("graph entity query limit is out of range")
        if self.scan_limit <= 0 or self.scan_limit > MAX_GRAPH_ENTITY_SCAN_LIMIT:
            raise GraphStoreError("graph entity query scan_limit is out of range")


@dataclass(frozen=True)
class GraphEntityMatch:
    entity: EntityRecord
    match_kind: GraphEntityMatchKind
    match_rank: int
    matched_value: str

    def __post_init__(self) -> None:
        if self.match_rank <= 0:
            raise GraphStoreError("graph entity match_rank must be positive")
        if not self.matched_value:
            raise GraphStoreError("graph entity matched_value is required")


@dataclass(frozen=True)
class GraphEntityQueryResult:
    matches: tuple[GraphEntityMatch, ...]
    truncated: bool
    affected_vault_ids: tuple[str, ...]


@dataclass(frozen=True)
class GraphRelationshipQuery:
    seeds: tuple[GraphEntityIdentity, ...]
    actual_scopes: tuple[QueryScope, ...]
    direction: GraphRelationshipDirection = "both"
    relationship_types: tuple[str, ...] = ()
    statuses: tuple[str, ...] = ("stated", "inferred", "contested")
    include_cross_vault: bool = False
    limit: int = DEFAULT_GRAPH_RELATIONSHIP_READ_LIMIT

    def __post_init__(self) -> None:
        if not self.seeds:
            raise GraphStoreError("graph relationship query seeds are required")
        _require_actual_scopes(self.actual_scopes)
        if self.direction not in ("out", "in", "both"):
            raise GraphStoreError("unsupported graph relationship direction")
        if self.limit <= 0:
            raise GraphStoreError("graph relationship query limit must be positive")
        if self.limit > MAX_GRAPH_RELATIONSHIP_READ_LIMIT:
            raise GraphStoreError("graph relationship query limit is out of range")


@dataclass(frozen=True)
class GraphRelationshipQueryResult:
    relationships: tuple[RelationshipRecord, ...]
    truncated: bool
    omitted_cross_vault_count: int
    affected_vault_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.omitted_cross_vault_count < 0:
            raise GraphStoreError("omitted_cross_vault_count must not be negative")
        if not isinstance(self.relationships, tuple):
            raise GraphStoreError("relationships must be an immutable tuple")


def _require_actual_scopes(scopes: tuple[QueryScope, ...]) -> None:
    if not scopes:
        raise GraphStoreError("actual_scopes are required")
    for scope in scopes:
        if len(scope.vault_ids) != 1:
            raise GraphStoreError("GraphStore operations require per-Vault actual scopes")
