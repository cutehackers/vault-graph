from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

from vault_graph.errors import GraphRecordInvalid
from vault_graph.graph.graph_identity import graph_scope_key
from vault_graph.ingestion.vault_catalog import QueryScope

OWNER_KINDS = ("entity", "relationship")
ENTITY_STATUSES = ("active", "tombstoned")
RELATIONSHIP_STATUSES = ("stated", "inferred", "contested", "deprecated")
TOMBSTONE_RECORD_KINDS = ("entity", "relationship")


def _require_non_empty(value: str, field_name: str) -> None:
    if not value:
        raise GraphRecordInvalid(f"{field_name} is required")


def _require_digest(value: str, field_name: str) -> None:
    _require_non_empty(value, field_name)
    if len(value) != 64:
        raise GraphRecordInvalid(f"{field_name} must be a sha256 digest")


def _as_tuple[T](values: tuple[T, ...], field_name: str) -> tuple[T, ...]:
    if not isinstance(values, tuple):
        raise GraphRecordInvalid(f"{field_name} must be a tuple")
    return values


def _require_effective_scopes(scopes: tuple[QueryScope, ...]) -> None:
    _as_tuple(scopes, "effective_scopes")
    for scope in scopes:
        if len(scope.vault_ids) != 1:
            raise GraphRecordInvalid("effective_scopes must be per-Vault scopes")


@dataclass(frozen=True)
class GraphExtractionSpec:
    spec_version: str
    spec_digest: str
    entity_schema_version: str
    relationship_schema_version: str
    entity_extractor_name: str
    entity_extractor_version: str
    relationship_extractor_name: str
    relationship_extractor_version: str
    relationship_status_rules_version: str
    confidence_rules_version: str
    serialized_spec: str

    def __post_init__(self) -> None:
        _require_non_empty(self.spec_version, "spec_version")
        _require_digest(self.spec_digest, "spec_digest")

    @classmethod
    def from_payload(cls, payload: dict[str, object]) -> GraphExtractionSpec:
        serialized_spec = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        spec_digest = hashlib.sha256(serialized_spec.encode("utf-8")).hexdigest()
        return cls(
            spec_version=str(payload["spec_version"]),
            spec_digest=spec_digest,
            entity_schema_version=str(payload["entity_schema_version"]),
            relationship_schema_version=str(payload["relationship_schema_version"]),
            entity_extractor_name=str(payload["entity_extractor_name"]),
            entity_extractor_version=str(payload["entity_extractor_version"]),
            relationship_extractor_name=str(payload["relationship_extractor_name"]),
            relationship_extractor_version=str(payload["relationship_extractor_version"]),
            relationship_status_rules_version=str(payload["relationship_status_rules_version"]),
            confidence_rules_version=str(payload["confidence_rules_version"]),
            serialized_spec=serialized_spec,
        )

    def payload(self) -> dict[str, object]:
        loaded = json.loads(self.serialized_spec)
        if not isinstance(loaded, dict):
            raise GraphRecordInvalid("serialized_spec must decode to a mapping")
        return loaded


def current_graph_extraction_spec() -> GraphExtractionSpec:
    return GraphExtractionSpec.from_payload(
        {
            "spec_version": "graph-extraction-spec-v1",
            "entity_schema_version": "entity-schema-v1",
            "relationship_schema_version": "relationship-schema-v1",
            "entity_extractor_name": "phase-3b-local-entity-extractor",
            "entity_extractor_version": "contract-v1",
            "relationship_extractor_name": "phase-3b-local-relationship-extractor",
            "relationship_extractor_version": "contract-v1",
            "relationship_status_rules_version": "relationship-status-rules-v1",
            "confidence_rules_version": "confidence-rules-v1",
        }
    )


@dataclass(frozen=True)
class GraphEvidenceRef:
    evidence_ref_id: str
    owner_kind: str
    owner_vault_id: str
    owner_id: str
    evidence_vault_id: str
    document_id: str
    chunk_id: str
    content_hash: str
    section: str | None = None
    anchor: str | None = None
    path: str | None = None
    excerpt: str | None = None

    def __post_init__(self) -> None:
        _require_non_empty(self.evidence_ref_id, "evidence_ref_id")
        _require_non_empty(self.owner_vault_id, "owner_vault_id")
        _require_non_empty(self.owner_id, "owner_id")
        _require_non_empty(self.evidence_vault_id, "evidence_vault_id")
        _require_non_empty(self.document_id, "document_id")
        _require_non_empty(self.chunk_id, "chunk_id")
        _require_non_empty(self.content_hash, "content_hash")
        if self.owner_kind not in OWNER_KINDS:
            raise GraphRecordInvalid(f"unsupported owner kind: {self.owner_kind}")


@dataclass(frozen=True)
class EntityRecord:
    vault_id: str
    entity_id: str
    type: str
    name: str
    normalized_name: str
    aliases: tuple[str, ...]
    canonical_path: str | None
    evidence_refs: tuple[GraphEvidenceRef, ...]
    confidence: float
    extraction_method: str
    graph_extraction_spec_version: str
    graph_extraction_spec_digest: str
    status: str
    created_at: str
    updated_at: str
    graph_index_revision: str

    def __post_init__(self) -> None:
        _require_non_empty(self.vault_id, "vault_id")
        _require_non_empty(self.entity_id, "entity_id")
        _require_non_empty(self.type, "type")
        _require_non_empty(self.name, "name")
        _require_non_empty(self.normalized_name, "normalized_name")
        _require_non_empty(self.extraction_method, "extraction_method")
        _require_non_empty(self.graph_extraction_spec_version, "graph_extraction_spec_version")
        _require_digest(self.graph_extraction_spec_digest, "graph_extraction_spec_digest")
        _require_non_empty(self.created_at, "created_at")
        _require_non_empty(self.updated_at, "updated_at")
        _require_non_empty(self.graph_index_revision, "graph_index_revision")
        _as_tuple(self.aliases, "aliases")
        _as_tuple(self.evidence_refs, "evidence_refs")
        if not self.evidence_refs:
            raise GraphRecordInvalid("entity evidence_refs must be non-empty")
        if self.status not in ENTITY_STATUSES:
            raise GraphRecordInvalid(f"unsupported entity status: {self.status}")
        if not 0 <= self.confidence <= 1:
            raise GraphRecordInvalid("confidence must be between 0 and 1")
        for ref in self.evidence_refs:
            if ref.owner_kind != "entity" or ref.owner_vault_id != self.vault_id or ref.owner_id != self.entity_id:
                raise GraphRecordInvalid("entity evidence owner must match entity identity")


@dataclass(frozen=True)
class RelationshipRecord:
    relationship_id: str
    type: str
    source_vault_id: str
    source_entity_id: str
    target_vault_id: str
    target_entity_id: str
    evidence_refs: tuple[GraphEvidenceRef, ...]
    status: str
    confidence: float
    extraction_method: str
    graph_extraction_spec_version: str
    graph_extraction_spec_digest: str
    created_at: str
    updated_at: str
    graph_index_revision: str

    def __post_init__(self) -> None:
        _require_non_empty(self.relationship_id, "relationship_id")
        _require_non_empty(self.type, "type")
        _require_non_empty(self.source_vault_id, "source_vault_id")
        _require_non_empty(self.source_entity_id, "source_entity_id")
        _require_non_empty(self.target_vault_id, "target_vault_id")
        _require_non_empty(self.target_entity_id, "target_entity_id")
        _require_non_empty(self.extraction_method, "extraction_method")
        _require_non_empty(self.graph_extraction_spec_version, "graph_extraction_spec_version")
        _require_digest(self.graph_extraction_spec_digest, "graph_extraction_spec_digest")
        _require_non_empty(self.created_at, "created_at")
        _require_non_empty(self.updated_at, "updated_at")
        _require_non_empty(self.graph_index_revision, "graph_index_revision")
        _as_tuple(self.evidence_refs, "evidence_refs")
        if not self.evidence_refs:
            raise GraphRecordInvalid("relationship evidence_refs must be non-empty")
        if self.status not in RELATIONSHIP_STATUSES:
            raise GraphRecordInvalid(f"unsupported relationship status: {self.status}")
        if not 0 <= self.confidence <= 1:
            raise GraphRecordInvalid("confidence must be between 0 and 1")
        for ref in self.evidence_refs:
            if (
                ref.owner_kind != "relationship"
                or ref.owner_vault_id != self.source_vault_id
                or ref.owner_id != self.relationship_id
            ):
                raise GraphRecordInvalid("relationship evidence owner must match relationship identity")


@dataclass(frozen=True)
class GraphRevision:
    graph_run_id: str
    vault_id: str
    effective_scope: str
    graph_store_schema_version: str
    graph_extraction_spec_version: str
    graph_extraction_spec_digest: str
    graph_index_revision: str
    metadata_index_revision: str
    parser_version: str
    chunker_version: str
    entity_count: int
    relationship_count: int
    stale_count: int
    tombstone_count: int
    updated_at: str

    def __post_init__(self) -> None:
        for field_name in (
            "graph_run_id",
            "vault_id",
            "effective_scope",
            "graph_store_schema_version",
            "graph_extraction_spec_version",
            "graph_index_revision",
            "metadata_index_revision",
            "parser_version",
            "chunker_version",
            "updated_at",
        ):
            _require_non_empty(str(getattr(self, field_name)), field_name)
        _require_digest(self.graph_extraction_spec_digest, "graph_extraction_spec_digest")


@dataclass(frozen=True)
class GraphTombstone:
    tombstone_id: str
    record_kind: str
    record_vault_id: str
    record_id: str
    effective_scope: str
    reason: str
    graph_run_id: str
    graph_index_revision: str
    graph_extraction_spec_version: str
    graph_extraction_spec_digest: str
    tombstoned_at: str

    def __post_init__(self) -> None:
        _require_non_empty(self.tombstone_id, "tombstone_id")
        _require_non_empty(self.record_vault_id, "record_vault_id")
        _require_non_empty(self.record_id, "record_id")
        _require_non_empty(self.effective_scope, "effective_scope")
        _require_non_empty(self.reason, "reason")
        _require_non_empty(self.graph_run_id, "graph_run_id")
        _require_non_empty(self.graph_index_revision, "graph_index_revision")
        _require_non_empty(self.graph_extraction_spec_version, "graph_extraction_spec_version")
        _require_digest(self.graph_extraction_spec_digest, "graph_extraction_spec_digest")
        _require_non_empty(self.tombstoned_at, "tombstoned_at")
        if self.record_kind not in TOMBSTONE_RECORD_KINDS:
            raise GraphRecordInvalid(f"unsupported tombstone record kind: {self.record_kind}")


@dataclass(frozen=True)
class GraphRecordScope:
    record_kind: str
    record_vault_id: str
    record_id: str
    effective_scope: str
    metadata_index_revision: str
    graph_index_revision: str
    graph_extraction_spec_digest: str

    def __post_init__(self) -> None:
        if self.record_kind not in TOMBSTONE_RECORD_KINDS:
            raise GraphRecordInvalid(f"unsupported graph record kind: {self.record_kind}")
        _require_non_empty(self.record_vault_id, "record_vault_id")
        _require_non_empty(self.record_id, "record_id")
        _require_non_empty(self.effective_scope, "effective_scope")
        _require_non_empty(self.metadata_index_revision, "metadata_index_revision")
        _require_non_empty(self.graph_index_revision, "graph_index_revision")
        _require_digest(self.graph_extraction_spec_digest, "graph_extraction_spec_digest")


@dataclass(frozen=True)
class GraphManifestEntity:
    vault_id: str
    entity_id: str
    evidence_ref_ids: tuple[str, ...]
    evidence_content_hashes: tuple[str, ...]
    status: str
    graph_extraction_spec_digest: str
    metadata_index_revision: str
    graph_index_revision: str

    def __post_init__(self) -> None:
        _as_tuple(self.evidence_ref_ids, "evidence_ref_ids")
        _as_tuple(self.evidence_content_hashes, "evidence_content_hashes")


@dataclass(frozen=True)
class GraphManifestRelationship:
    source_vault_id: str
    source_entity_id: str
    target_vault_id: str
    target_entity_id: str
    relationship_id: str
    type: str
    status: str
    evidence_ref_ids: tuple[str, ...]
    evidence_content_hashes: tuple[str, ...]
    graph_extraction_spec_digest: str
    metadata_index_revision: str
    graph_index_revision: str

    def __post_init__(self) -> None:
        _as_tuple(self.evidence_ref_ids, "evidence_ref_ids")
        _as_tuple(self.evidence_content_hashes, "evidence_content_hashes")


@dataclass(frozen=True)
class GraphManifestEvidence:
    evidence_ref_id: str
    owner_kind: str
    owner_vault_id: str
    owner_id: str
    evidence_vault_id: str
    document_id: str
    chunk_id: str
    content_hash: str
    anchor: str | None


@dataclass(frozen=True)
class GraphManifest:
    requested_scope: QueryScope
    effective_scopes: tuple[QueryScope, ...]
    entity_rows: tuple[GraphManifestEntity, ...]
    relationship_rows: tuple[GraphManifestRelationship, ...]
    evidence_rows: tuple[GraphManifestEvidence, ...]
    tombstone_rows: tuple[GraphTombstone, ...]
    graph_store_schema_version: str
    graph_extraction_spec_version: str
    graph_extraction_spec_digest: str
    revision_rows: tuple[GraphRevision, ...]

    def __post_init__(self) -> None:
        _require_effective_scopes(self.effective_scopes)
        _as_tuple(self.entity_rows, "entity_rows")
        _as_tuple(self.relationship_rows, "relationship_rows")
        _as_tuple(self.evidence_rows, "evidence_rows")
        _as_tuple(self.tombstone_rows, "tombstone_rows")
        _as_tuple(self.revision_rows, "revision_rows")


@dataclass(frozen=True)
class GraphApplyResult:
    graph_run_id: str
    applied_entity_upsert_count: int
    applied_relationship_upsert_count: int
    applied_evidence_ref_upsert_count: int
    applied_tombstone_count: int
    graph_revision_rows: tuple[GraphRevision, ...]
    warnings: tuple[str, ...]

    def __post_init__(self) -> None:
        _as_tuple(self.graph_revision_rows, "graph_revision_rows")
        _as_tuple(self.warnings, "warnings")


@dataclass(frozen=True)
class GraphReconcilePlan:
    requested_scope: QueryScope
    effective_scopes: tuple[QueryScope, ...]
    graph_run_id: str
    entity_upserts: tuple[EntityRecord, ...]
    relationship_upserts: tuple[RelationshipRecord, ...]
    evidence_ref_upserts: tuple[GraphEvidenceRef, ...]
    entity_tombstones: tuple[GraphTombstone, ...]
    relationship_tombstones: tuple[GraphTombstone, ...]
    graph_revision_rows: tuple[GraphRevision, ...]
    graph_extraction_spec: GraphExtractionSpec
    projection_cache_invalidations: tuple[str, ...]

    def __post_init__(self) -> None:
        _require_non_empty(self.graph_run_id, "graph_run_id")
        _require_effective_scopes(self.effective_scopes)
        _as_tuple(self.entity_upserts, "entity_upserts")
        _as_tuple(self.relationship_upserts, "relationship_upserts")
        _as_tuple(self.evidence_ref_upserts, "evidence_ref_upserts")
        _as_tuple(self.entity_tombstones, "entity_tombstones")
        _as_tuple(self.relationship_tombstones, "relationship_tombstones")
        _as_tuple(self.graph_revision_rows, "graph_revision_rows")
        _as_tuple(self.projection_cache_invalidations, "projection_cache_invalidations")
        if tuple(graph_scope_key(scope) for scope in self.effective_scopes) != tuple(
            revision.effective_scope for revision in self.graph_revision_rows
        ):
            raise GraphRecordInvalid("graph revision scopes must match effective scopes")
