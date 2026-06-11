from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from vault_graph.errors import SearchError
from vault_graph.graph.graph_contracts import EntityRecord, RelationshipRecord
from vault_graph.ingestion.vault_catalog import QueryScope
from vault_graph.projection.graph_projection import GRAPH_PROJECTION_VERSION
from vault_graph.storage.interfaces.metadata_store import EvidenceReference

GraphOutputFormat = Literal["text", "json"]
GraphWarningSeverity = Literal["info", "warning", "error"]


@dataclass(frozen=True)
class GraphRetrievalWarning:
    code: str
    message: str
    severity: GraphWarningSeverity
    affected_vault_ids: tuple[str, ...]
    scope_key: str | None = None
    entity_id: str | None = None
    relationship_id: str | None = None
    evidence_ref_id: str | None = None

    def __post_init__(self) -> None:
        _require_non_empty(self.code, "graph warning code")
        _require_non_empty(self.message, "graph warning message")
        if not self.affected_vault_ids:
            raise SearchError("graph warning affected_vault_ids is required")


@dataclass(frozen=True)
class GraphRetrievalRevision:
    kind: Literal["metadata", "graph", "projection"]
    revision: str
    scope_key: str
    vault_id: str | None = None

    def __post_init__(self) -> None:
        _require_non_empty(self.revision, "graph retrieval revision")
        _require_non_empty(self.scope_key, "graph retrieval revision scope_key")


@dataclass(frozen=True)
class RelatedRequest:
    target: str
    requested_scope: QueryScope
    actual_scopes: tuple[QueryScope, ...]
    depth: int = 1
    direction: Literal["out", "in", "both"] = "both"
    relationship_types: tuple[str, ...] = ()
    include_cross_vault: bool = False
    limit: int = 10
    output_format: GraphOutputFormat = "text"


@dataclass(frozen=True)
class RelatedItem:
    rank: int
    entity: EntityRecord
    relationship_path: tuple[RelationshipRecord, ...]
    evidence: tuple[EvidenceReference, ...]
    score: float
    explanation: str

    def __post_init__(self) -> None:
        if self.rank <= 0:
            raise SearchError("related item rank must be positive")
        if not self.relationship_path:
            raise SearchError("related item relationship_path is required")
        if not self.evidence:
            raise SearchError("related item relationship evidence is required")
        _require_non_empty(self.explanation, "related item explanation")


@dataclass(frozen=True)
class RelatedResponse:
    target: str
    resolved_target: EntityRecord | None
    target_candidates: tuple[EntityRecord, ...]
    requested_scope: QueryScope
    actual_scopes: tuple[QueryScope, ...]
    projection_build_id: str | None
    graph_projection_version: str
    result_count: int
    items: tuple[RelatedItem, ...]
    warnings: tuple[GraphRetrievalWarning, ...]
    store_revisions: tuple[GraphRetrievalRevision, ...]
    generated_at: str

    def __post_init__(self) -> None:
        _require_non_empty(self.target, "related target")
        if self.graph_projection_version != GRAPH_PROJECTION_VERSION:
            raise SearchError("graph_projection_version must match current graph projection version")
        if self.result_count != len(self.items):
            raise SearchError("result_count must match items")
        if not isinstance(self.items, tuple):
            raise SearchError("items must be an immutable tuple")
        if not isinstance(self.warnings, tuple):
            raise SearchError("warnings must be an immutable tuple")
        if not isinstance(self.store_revisions, tuple):
            raise SearchError("store_revisions must be an immutable tuple")


@dataclass(frozen=True)
class DecisionTraceStep:
    rank: int
    role: str
    entity: EntityRecord
    relationship_path: tuple[RelationshipRecord, ...]
    evidence: tuple[EvidenceReference, ...]
    relationship_status: str
    explanation: str

    def __post_init__(self) -> None:
        if self.rank <= 0:
            raise SearchError("decision trace step rank must be positive")
        _require_non_empty(self.role, "decision trace step role")
        _require_non_empty(self.relationship_status, "decision trace relationship_status")
        _require_non_empty(self.explanation, "decision trace step explanation")
        if not self.evidence:
            if self.relationship_path:
                raise SearchError("decision trace relationship evidence is required")
            raise SearchError("decision trace entity evidence is required")


@dataclass(frozen=True)
class DecisionTraceResponse:
    topic: str
    trace_kind: Literal["decision", "topic"]
    resolved_target: EntityRecord | None
    target_candidates: tuple[EntityRecord, ...]
    requested_scope: QueryScope
    actual_scopes: tuple[QueryScope, ...]
    projection_build_id: str | None
    graph_projection_version: str
    steps: tuple[DecisionTraceStep, ...]
    warnings: tuple[GraphRetrievalWarning, ...]
    store_revisions: tuple[GraphRetrievalRevision, ...]
    generated_at: str

    def __post_init__(self) -> None:
        _require_non_empty(self.topic, "decision trace topic")
        if self.graph_projection_version != GRAPH_PROJECTION_VERSION:
            raise SearchError("graph_projection_version must match current graph projection version")
        if not isinstance(self.steps, tuple):
            raise SearchError("steps must be an immutable tuple")
        if not isinstance(self.warnings, tuple):
            raise SearchError("warnings must be an immutable tuple")
        if not isinstance(self.store_revisions, tuple):
            raise SearchError("store_revisions must be an immutable tuple")


def _require_non_empty(value: str, field_name: str) -> None:
    if not value:
        raise SearchError(f"{field_name} is required")
