from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from vault_graph.graph.graph_contracts import (
    EntityRecord,
    GraphApplyResult,
    GraphExtractionSpec,
    GraphManifest,
    GraphReconcilePlan,
    GraphRevision,
    RelationshipRecord,
)
from vault_graph.ingestion.vault_catalog import QueryScope
from vault_graph.storage.interfaces.store_health import StoreHealth


@dataclass(frozen=True)
class GraphEntityIdentity:
    vault_id: str
    entity_id: str


@dataclass(frozen=True)
class GraphRelationshipIdentity:
    source_vault_id: str
    relationship_id: str


class GraphStore(Protocol):
    def health(self) -> StoreHealth:
        raise NotImplementedError

    def stored_specs(self) -> tuple[GraphExtractionSpec, ...]:
        raise NotImplementedError

    def latest_revisions(self, scopes: tuple[QueryScope, ...]) -> tuple[GraphRevision, ...]:
        raise NotImplementedError

    def current_manifest(self, scopes: tuple[QueryScope, ...]) -> GraphManifest:
        raise NotImplementedError

    def get_entity(self, *, vault_id: str, entity_id: str) -> EntityRecord | None:
        raise NotImplementedError

    def get_relationship(self, *, source_vault_id: str, relationship_id: str) -> RelationshipRecord | None:
        raise NotImplementedError

    def resolve_entities(self, identities: tuple[GraphEntityIdentity, ...]) -> tuple[EntityRecord, ...]:
        raise NotImplementedError

    def resolve_relationships(
        self,
        identities: tuple[GraphRelationshipIdentity, ...],
    ) -> tuple[RelationshipRecord, ...]:
        raise NotImplementedError

    def apply_reconcile_plan(self, plan: GraphReconcilePlan) -> GraphApplyResult:
        raise NotImplementedError
