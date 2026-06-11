from __future__ import annotations

from vault_graph.errors import GraphReadOnlyViolation, GraphStoreError
from vault_graph.graph.graph_contracts import (
    EntityRecord,
    GraphApplyResult,
    GraphEvidenceRef,
    GraphExtractionSpec,
    GraphManifest,
    GraphManifestEntity,
    GraphManifestEvidence,
    GraphManifestRelationship,
    GraphReconcilePlan,
    GraphRecordScope,
    GraphRevision,
    GraphTombstone,
    RelationshipRecord,
    current_graph_extraction_spec,
)
from vault_graph.graph.graph_identity import graph_scope_key
from vault_graph.ingestion.vault_catalog import QueryScope
from vault_graph.storage.interfaces.graph_store import GraphEntityIdentity, GraphRelationshipIdentity
from vault_graph.storage.interfaces.store_health import StoreHealth


class InMemoryGraphStore:
    def __init__(self, *, read_only: bool = False, health_override: StoreHealth | None = None) -> None:
        self._read_only = read_only
        self._health_override = health_override
        self._entities: dict[tuple[str, str], EntityRecord] = {}
        self._relationships: dict[tuple[str, str], RelationshipRecord] = {}
        self._evidence_refs: dict[tuple[str, str, str, str, str, str, str], GraphEvidenceRef] = {}
        self._evidence_by_id: dict[str, GraphEvidenceRef] = {}
        self._revisions: dict[tuple[str, str], GraphRevision] = {}
        self._tombstones: dict[str, GraphTombstone] = {}
        self._tombstones_by_record_scope: dict[tuple[str, str, str, str], str] = {}
        self._specs: dict[str, GraphExtractionSpec] = {}
        self._record_scopes: dict[tuple[str, str, str, str], GraphRecordScope] = {}

    def health(self) -> StoreHealth:
        if self._health_override is not None:
            return self._health_override
        return StoreHealth(
            ok=True,
            backend="memory-graph",
            schema_version="memory-graph-v1",
            schema_compatible=True,
            message="ok",
        )

    def stored_specs(self) -> tuple[GraphExtractionSpec, ...]:
        return tuple(sorted(self._specs.values(), key=lambda spec: (spec.spec_version, spec.spec_digest)))

    def latest_revisions(self, scopes: tuple[QueryScope, ...]) -> tuple[GraphRevision, ...]:
        _ensure_actual_scopes(scopes)
        revisions: list[GraphRevision] = []
        for scope in scopes:
            revision = self._revisions.get((scope.vault_ids[0], graph_scope_key(scope)))
            if revision is not None:
                revisions.append(revision)
        return tuple(revisions)

    def current_manifest(self, scopes: tuple[QueryScope, ...]) -> GraphManifest:
        _ensure_actual_scopes(scopes)
        scope_keys = {graph_scope_key(scope) for scope in scopes}
        scopes_by_key = {graph_scope_key(scope): scope for scope in scopes}
        selected_vault_ids = {vault_id for scope in scopes for vault_id in scope.vault_ids}
        include_cross_vault = any(scope.include_cross_vault for scope in scopes)
        entity_rows: list[GraphManifestEntity] = []
        relationship_rows: list[GraphManifestRelationship] = []
        evidence_ids: set[str] = set()

        for membership in self._record_scopes.values():
            if membership.actual_scope not in scope_keys:
                continue
            if membership.record_kind == "entity":
                entity = self._entities.get((membership.record_vault_id, membership.record_id))
                if entity is None:
                    continue
                entity_rows.append(_entity_manifest_row(entity=entity, membership=membership))
                evidence_ids.update(ref.evidence_ref_id for ref in entity.evidence_refs)
            if membership.record_kind == "relationship":
                relationship = self._relationships.get((membership.record_vault_id, membership.record_id))
                if relationship is None:
                    continue
                scope = scopes_by_key[membership.actual_scope]
                if not _relationship_allowed(
                    relationship=relationship,
                    scope=scope,
                    selected_vault_ids=selected_vault_ids,
                    include_cross_vault=include_cross_vault,
                ):
                    continue
                relationship_rows.append(_relationship_manifest_row(relationship=relationship, membership=membership))
                evidence_ids.update(ref.evidence_ref_id for ref in relationship.evidence_refs)

        evidence_rows = tuple(
            _evidence_manifest_row(ref)
            for ref in sorted(
                (
                    self._evidence_by_id[evidence_id]
                    for evidence_id in evidence_ids
                    if evidence_id in self._evidence_by_id
                ),
                key=lambda ref: ref.evidence_ref_id,
            )
        )
        revision_rows = self.latest_revisions(scopes)
        return GraphManifest(
            requested_scope=_combined_scope(scopes),
            actual_scopes=scopes,
            entity_rows=tuple(sorted(entity_rows, key=lambda row: (row.vault_id, row.entity_id))),
            relationship_rows=tuple(
                sorted(relationship_rows, key=lambda row: (row.source_vault_id, row.relationship_id))
            ),
            evidence_rows=evidence_rows,
            tombstone_rows=tuple(
                sorted(
                    (tombstone for tombstone in self._tombstones.values() if tombstone.actual_scope in scope_keys),
                    key=lambda tombstone: tombstone.tombstone_id,
                )
            ),
            graph_store_schema_version=self.health().schema_version,
            graph_extraction_spec_version=current_graph_extraction_spec().spec_version,
            graph_extraction_spec_digest=current_graph_extraction_spec().spec_digest,
            revision_rows=revision_rows,
        )

    def get_entity(self, *, vault_id: str, entity_id: str) -> EntityRecord | None:
        return self._entities.get((vault_id, entity_id))

    def get_relationship(self, *, source_vault_id: str, relationship_id: str) -> RelationshipRecord | None:
        return self._relationships.get((source_vault_id, relationship_id))

    def resolve_entities(self, identities: tuple[GraphEntityIdentity, ...]) -> tuple[EntityRecord, ...]:
        return tuple(
            entity
            for identity in identities
            if (entity := self.get_entity(vault_id=identity.vault_id, entity_id=identity.entity_id)) is not None
        )

    def resolve_relationships(
        self,
        identities: tuple[GraphRelationshipIdentity, ...],
    ) -> tuple[RelationshipRecord, ...]:
        return tuple(
            relationship
            for identity in identities
            if (
                relationship := self.get_relationship(
                    source_vault_id=identity.source_vault_id,
                    relationship_id=identity.relationship_id,
                )
            )
            is not None
        )

    def apply_reconcile_plan(self, plan: GraphReconcilePlan) -> GraphApplyResult:
        if self._read_only:
            raise GraphReadOnlyViolation("graph store is read-only")
        _ensure_actual_scopes(plan.actual_scopes)
        self._specs[plan.graph_extraction_spec.spec_digest] = plan.graph_extraction_spec
        revisions_by_scope = {revision.actual_scope: revision for revision in plan.graph_revision_rows}
        for entity in plan.entity_upserts:
            self._entities[(entity.vault_id, entity.entity_id)] = entity
            self._record_entity_scopes(entity=entity, plan=plan, revisions_by_scope=revisions_by_scope)
        for relationship in plan.relationship_upserts:
            self._relationships[(relationship.source_vault_id, relationship.relationship_id)] = relationship
            self._record_relationship_scopes(
                relationship=relationship,
                plan=plan,
                revisions_by_scope=revisions_by_scope,
            )
        for ref in plan.evidence_ref_upserts:
            self._store_evidence_ref(ref)
        for tombstone in plan.entity_tombstones + plan.relationship_tombstones:
            tombstone_key = (
                tombstone.record_kind,
                tombstone.record_vault_id,
                tombstone.record_id,
                tombstone.actual_scope,
            )
            previous_tombstone_id = self._tombstones_by_record_scope.get(tombstone_key)
            if previous_tombstone_id is not None and previous_tombstone_id != tombstone.tombstone_id:
                self._tombstones.pop(previous_tombstone_id, None)
            self._tombstones[tombstone.tombstone_id] = tombstone
            self._tombstones_by_record_scope[tombstone_key] = tombstone.tombstone_id
            if tombstone.record_kind == "entity":
                self._tombstone_entity(tombstone)
            if tombstone.record_kind == "relationship":
                self._tombstone_relationship(tombstone)
        for revision in plan.graph_revision_rows:
            self._revisions[(revision.vault_id, revision.actual_scope)] = revision
        return GraphApplyResult(
            graph_run_id=plan.graph_run_id,
            applied_entity_upsert_count=len(plan.entity_upserts),
            applied_relationship_upsert_count=len(plan.relationship_upserts),
            applied_evidence_ref_upsert_count=len(plan.evidence_ref_upserts),
            applied_tombstone_count=len(plan.entity_tombstones) + len(plan.relationship_tombstones),
            graph_revision_rows=plan.graph_revision_rows,
            warnings=(),
        )

    def _store_evidence_ref(self, ref: GraphEvidenceRef) -> None:
        key = (
            ref.owner_kind,
            ref.owner_vault_id,
            ref.owner_id,
            ref.evidence_vault_id,
            ref.document_id,
            ref.chunk_id,
            ref.anchor or "",
        )
        self._evidence_refs[key] = ref
        self._evidence_by_id[ref.evidence_ref_id] = ref

    def _record_entity_scopes(
        self,
        *,
        entity: EntityRecord,
        plan: GraphReconcilePlan,
        revisions_by_scope: dict[str, GraphRevision],
    ) -> None:
        for scope in plan.actual_scopes:
            if scope.vault_ids[0] != entity.vault_id:
                continue
            actual_scope = graph_scope_key(scope)
            revision = revisions_by_scope[actual_scope]
            record_scope = GraphRecordScope(
                record_kind="entity",
                record_vault_id=entity.vault_id,
                record_id=entity.entity_id,
                actual_scope=actual_scope,
                metadata_index_revision=revision.metadata_index_revision,
                graph_index_revision=revision.graph_index_revision,
                graph_extraction_spec_digest=plan.graph_extraction_spec.spec_digest,
            )
            self._record_scopes[(record_scope.record_kind, entity.vault_id, entity.entity_id, actual_scope)] = (
                record_scope
            )
            self._clear_tombstone_for_record_scope(
                record_kind="entity",
                record_vault_id=entity.vault_id,
                record_id=entity.entity_id,
                actual_scope=actual_scope,
            )

    def _record_relationship_scopes(
        self,
        *,
        relationship: RelationshipRecord,
        plan: GraphReconcilePlan,
        revisions_by_scope: dict[str, GraphRevision],
    ) -> None:
        for scope in plan.actual_scopes:
            if scope.vault_ids[0] != relationship.source_vault_id:
                continue
            actual_scope = graph_scope_key(scope)
            revision = revisions_by_scope[actual_scope]
            record_scope = GraphRecordScope(
                record_kind="relationship",
                record_vault_id=relationship.source_vault_id,
                record_id=relationship.relationship_id,
                actual_scope=actual_scope,
                metadata_index_revision=revision.metadata_index_revision,
                graph_index_revision=revision.graph_index_revision,
                graph_extraction_spec_digest=plan.graph_extraction_spec.spec_digest,
            )
            self._record_scopes[
                (
                    record_scope.record_kind,
                    relationship.source_vault_id,
                    relationship.relationship_id,
                    actual_scope,
                )
            ] = record_scope
            self._clear_tombstone_for_record_scope(
                record_kind="relationship",
                record_vault_id=relationship.source_vault_id,
                record_id=relationship.relationship_id,
                actual_scope=actual_scope,
            )

    def _clear_tombstone_for_record_scope(
        self,
        *,
        record_kind: str,
        record_vault_id: str,
        record_id: str,
        actual_scope: str,
    ) -> None:
        key = (record_kind, record_vault_id, record_id, actual_scope)
        tombstone_id = self._tombstones_by_record_scope.pop(key, None)
        if tombstone_id is not None:
            self._tombstones.pop(tombstone_id, None)

    def _tombstone_entity(self, tombstone: GraphTombstone) -> None:
        entity = self._entities.get((tombstone.record_vault_id, tombstone.record_id))
        if entity is None:
            return
        self._entities[(entity.vault_id, entity.entity_id)] = type(entity)(
            vault_id=entity.vault_id,
            entity_id=entity.entity_id,
            type=entity.type,
            name=entity.name,
            normalized_name=entity.normalized_name,
            aliases=entity.aliases,
            canonical_path=entity.canonical_path,
            evidence_refs=entity.evidence_refs,
            confidence=entity.confidence,
            extraction_method=entity.extraction_method,
            graph_extraction_spec_version=entity.graph_extraction_spec_version,
            graph_extraction_spec_digest=entity.graph_extraction_spec_digest,
            status="tombstoned",
            created_at=entity.created_at,
            updated_at=tombstone.tombstoned_at,
            graph_index_revision=tombstone.graph_index_revision,
        )

    def _tombstone_relationship(self, tombstone: GraphTombstone) -> None:
        relationship = self._relationships.get((tombstone.record_vault_id, tombstone.record_id))
        if relationship is None:
            return
        self._relationships[(relationship.source_vault_id, relationship.relationship_id)] = type(relationship)(
            relationship_id=relationship.relationship_id,
            type=relationship.type,
            source_vault_id=relationship.source_vault_id,
            source_entity_id=relationship.source_entity_id,
            target_vault_id=relationship.target_vault_id,
            target_entity_id=relationship.target_entity_id,
            evidence_refs=relationship.evidence_refs,
            status="deprecated",
            confidence=relationship.confidence,
            extraction_method=relationship.extraction_method,
            graph_extraction_spec_version=relationship.graph_extraction_spec_version,
            graph_extraction_spec_digest=relationship.graph_extraction_spec_digest,
            created_at=relationship.created_at,
            updated_at=tombstone.tombstoned_at,
            graph_index_revision=tombstone.graph_index_revision,
        )


def _ensure_actual_scopes(scopes: tuple[QueryScope, ...]) -> None:
    for scope in scopes:
        if len(scope.vault_ids) != 1:
            raise GraphStoreError("GraphStore operations require per-Vault actual scopes")


def _entity_manifest_row(*, entity: EntityRecord, membership: GraphRecordScope) -> GraphManifestEntity:
    return GraphManifestEntity(
        vault_id=entity.vault_id,
        entity_id=entity.entity_id,
        evidence_ref_ids=tuple(ref.evidence_ref_id for ref in entity.evidence_refs),
        evidence_content_hashes=tuple(ref.content_hash for ref in entity.evidence_refs),
        status=entity.status,
        graph_extraction_spec_digest=membership.graph_extraction_spec_digest,
        metadata_index_revision=membership.metadata_index_revision,
        graph_index_revision=membership.graph_index_revision,
    )


def _relationship_manifest_row(
    *,
    relationship: RelationshipRecord,
    membership: GraphRecordScope,
) -> GraphManifestRelationship:
    return GraphManifestRelationship(
        source_vault_id=relationship.source_vault_id,
        source_entity_id=relationship.source_entity_id,
        target_vault_id=relationship.target_vault_id,
        target_entity_id=relationship.target_entity_id,
        relationship_id=relationship.relationship_id,
        type=relationship.type,
        status=relationship.status,
        evidence_ref_ids=tuple(ref.evidence_ref_id for ref in relationship.evidence_refs),
        evidence_content_hashes=tuple(ref.content_hash for ref in relationship.evidence_refs),
        graph_extraction_spec_digest=membership.graph_extraction_spec_digest,
        metadata_index_revision=membership.metadata_index_revision,
        graph_index_revision=membership.graph_index_revision,
    )


def _evidence_manifest_row(ref: GraphEvidenceRef) -> GraphManifestEvidence:
    return GraphManifestEvidence(
        evidence_ref_id=ref.evidence_ref_id,
        owner_kind=ref.owner_kind,
        owner_vault_id=ref.owner_vault_id,
        owner_id=ref.owner_id,
        evidence_vault_id=ref.evidence_vault_id,
        document_id=ref.document_id,
        chunk_id=ref.chunk_id,
        content_hash=ref.content_hash,
        anchor=ref.anchor,
    )


def _relationship_allowed(
    *,
    relationship: RelationshipRecord,
    scope: QueryScope,
    selected_vault_ids: set[str],
    include_cross_vault: bool,
) -> bool:
    evidence_vault_ids = {ref.evidence_vault_id for ref in relationship.evidence_refs}
    if include_cross_vault:
        return (
            relationship.source_vault_id in selected_vault_ids
            and relationship.target_vault_id in selected_vault_ids
            and evidence_vault_ids <= selected_vault_ids
        )
    local_vault_id = scope.vault_ids[0]
    return (
        relationship.source_vault_id == local_vault_id
        and relationship.target_vault_id == local_vault_id
        and evidence_vault_ids == {local_vault_id}
    )


def _combined_scope(scopes: tuple[QueryScope, ...]) -> QueryScope:
    vault_ids = tuple(dict.fromkeys(vault_id for scope in scopes for vault_id in scope.vault_ids))
    content_scopes = tuple(dict.fromkeys(content_scope for scope in scopes for content_scope in scope.content_scopes))
    return QueryScope(
        vault_ids=vault_ids,
        content_scopes=content_scopes,
        include_cross_vault=any(scope.include_cross_vault for scope in scopes),
    )
