from __future__ import annotations

import json
import sqlite3
from dataclasses import replace
from pathlib import Path

from vault_graph.errors import GraphReadOnlyViolation, GraphStoreError, GraphStoreUnavailable
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

GRAPH_SQLITE_BACKEND = "sqlite-graph"
GRAPH_SCHEMA_VERSION = "sqlite-graph-v1"

SCHEMA = """
CREATE TABLE IF NOT EXISTS graph_metadata (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS graph_specs (
  spec_digest TEXT PRIMARY KEY,
  spec_version TEXT NOT NULL,
  entity_schema_version TEXT NOT NULL,
  relationship_schema_version TEXT NOT NULL,
  entity_extractor_name TEXT NOT NULL,
  entity_extractor_version TEXT NOT NULL,
  relationship_extractor_name TEXT NOT NULL,
  relationship_extractor_version TEXT NOT NULL,
  relationship_status_rules_version TEXT NOT NULL,
  confidence_rules_version TEXT NOT NULL,
  serialized_spec TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS graph_entities (
  vault_id TEXT NOT NULL,
  entity_id TEXT NOT NULL,
  type TEXT NOT NULL,
  name TEXT NOT NULL,
  normalized_name TEXT NOT NULL,
  aliases_json TEXT NOT NULL,
  canonical_path TEXT,
  confidence REAL NOT NULL,
  extraction_method TEXT NOT NULL,
  graph_extraction_spec_version TEXT NOT NULL,
  graph_extraction_spec_digest TEXT NOT NULL,
  status TEXT NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  graph_index_revision TEXT NOT NULL,
  PRIMARY KEY (vault_id, entity_id)
);

CREATE TABLE IF NOT EXISTS graph_relationships (
  source_vault_id TEXT NOT NULL,
  relationship_id TEXT NOT NULL,
  type TEXT NOT NULL,
  source_entity_id TEXT NOT NULL,
  target_vault_id TEXT NOT NULL,
  target_entity_id TEXT NOT NULL,
  status TEXT NOT NULL,
  confidence REAL NOT NULL,
  extraction_method TEXT NOT NULL,
  graph_extraction_spec_version TEXT NOT NULL,
  graph_extraction_spec_digest TEXT NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  graph_index_revision TEXT NOT NULL,
  PRIMARY KEY (source_vault_id, relationship_id)
);

CREATE TABLE IF NOT EXISTS graph_evidence_refs (
  evidence_ref_id TEXT PRIMARY KEY,
  owner_kind TEXT NOT NULL,
  owner_vault_id TEXT NOT NULL,
  owner_id TEXT NOT NULL,
  evidence_vault_id TEXT NOT NULL,
  document_id TEXT NOT NULL,
  chunk_id TEXT NOT NULL,
  content_hash TEXT NOT NULL,
  section TEXT,
  anchor TEXT,
  anchor_key TEXT NOT NULL,
  path TEXT,
  excerpt TEXT,
  UNIQUE (owner_kind, owner_vault_id, owner_id, evidence_vault_id, document_id, chunk_id, anchor_key)
);

CREATE TABLE IF NOT EXISTS graph_record_scopes (
  record_kind TEXT NOT NULL,
  record_vault_id TEXT NOT NULL,
  record_id TEXT NOT NULL,
  effective_scope TEXT NOT NULL,
  metadata_index_revision TEXT NOT NULL,
  graph_index_revision TEXT NOT NULL,
  graph_extraction_spec_digest TEXT NOT NULL,
  PRIMARY KEY (record_kind, record_vault_id, record_id, effective_scope)
);

CREATE TABLE IF NOT EXISTS graph_revisions (
  graph_run_id TEXT NOT NULL,
  vault_id TEXT NOT NULL,
  effective_scope TEXT NOT NULL,
  graph_store_schema_version TEXT NOT NULL,
  graph_extraction_spec_version TEXT NOT NULL,
  graph_extraction_spec_digest TEXT NOT NULL,
  graph_index_revision TEXT NOT NULL,
  metadata_index_revision TEXT NOT NULL,
  parser_version TEXT NOT NULL,
  chunker_version TEXT NOT NULL,
  entity_count INTEGER NOT NULL,
  relationship_count INTEGER NOT NULL,
  stale_count INTEGER NOT NULL,
  tombstone_count INTEGER NOT NULL,
  updated_at TEXT NOT NULL,
  PRIMARY KEY (vault_id, effective_scope, graph_index_revision)
);

CREATE TABLE IF NOT EXISTS graph_tombstones (
  tombstone_id TEXT PRIMARY KEY,
  record_kind TEXT NOT NULL,
  record_vault_id TEXT NOT NULL,
  record_id TEXT NOT NULL,
  effective_scope TEXT NOT NULL,
  reason TEXT NOT NULL,
  graph_run_id TEXT NOT NULL,
  graph_index_revision TEXT NOT NULL,
  graph_extraction_spec_version TEXT NOT NULL,
  graph_extraction_spec_digest TEXT NOT NULL,
  tombstoned_at TEXT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_graph_tombstones_record_scope
  ON graph_tombstones (record_kind, record_vault_id, record_id, effective_scope);

CREATE INDEX IF NOT EXISTS idx_graph_entities_name ON graph_entities (vault_id, normalized_name);
CREATE INDEX IF NOT EXISTS idx_graph_entities_type_name ON graph_entities (vault_id, type, normalized_name);
CREATE INDEX IF NOT EXISTS idx_graph_relationships_source ON graph_relationships (source_vault_id, source_entity_id);
CREATE INDEX IF NOT EXISTS idx_graph_relationships_target ON graph_relationships (target_vault_id, target_entity_id);
CREATE INDEX IF NOT EXISTS idx_graph_relationships_type_status ON graph_relationships (type, status);
CREATE INDEX IF NOT EXISTS idx_graph_evidence_chunk ON graph_evidence_refs (evidence_vault_id, document_id, chunk_id);
CREATE INDEX IF NOT EXISTS idx_graph_evidence_owner ON graph_evidence_refs (owner_kind, owner_vault_id, owner_id);
CREATE INDEX IF NOT EXISTS idx_graph_record_scopes_scope ON graph_record_scopes (effective_scope, record_kind);
CREATE INDEX IF NOT EXISTS idx_graph_revisions_scope ON graph_revisions (vault_id, effective_scope, updated_at);
"""

REQUIRED_TABLES = {
    "graph_metadata",
    "graph_specs",
    "graph_entities",
    "graph_relationships",
    "graph_evidence_refs",
    "graph_record_scopes",
    "graph_revisions",
    "graph_tombstones",
}

REQUIRED_COLUMNS = {
    "graph_metadata": {"key", "value"},
    "graph_specs": {
        "spec_digest",
        "spec_version",
        "entity_schema_version",
        "relationship_schema_version",
        "entity_extractor_name",
        "entity_extractor_version",
        "relationship_extractor_name",
        "relationship_extractor_version",
        "relationship_status_rules_version",
        "confidence_rules_version",
        "serialized_spec",
    },
    "graph_entities": {
        "vault_id",
        "entity_id",
        "type",
        "name",
        "normalized_name",
        "aliases_json",
        "canonical_path",
        "confidence",
        "extraction_method",
        "graph_extraction_spec_version",
        "graph_extraction_spec_digest",
        "status",
        "created_at",
        "updated_at",
        "graph_index_revision",
    },
    "graph_relationships": {
        "source_vault_id",
        "relationship_id",
        "type",
        "source_entity_id",
        "target_vault_id",
        "target_entity_id",
        "status",
        "confidence",
        "extraction_method",
        "graph_extraction_spec_version",
        "graph_extraction_spec_digest",
        "created_at",
        "updated_at",
        "graph_index_revision",
    },
    "graph_evidence_refs": {
        "evidence_ref_id",
        "owner_kind",
        "owner_vault_id",
        "owner_id",
        "evidence_vault_id",
        "document_id",
        "chunk_id",
        "content_hash",
        "section",
        "anchor",
        "anchor_key",
        "path",
        "excerpt",
    },
    "graph_record_scopes": {
        "record_kind",
        "record_vault_id",
        "record_id",
        "effective_scope",
        "metadata_index_revision",
        "graph_index_revision",
        "graph_extraction_spec_digest",
    },
    "graph_revisions": {
        "graph_run_id",
        "vault_id",
        "effective_scope",
        "graph_store_schema_version",
        "graph_extraction_spec_version",
        "graph_extraction_spec_digest",
        "graph_index_revision",
        "metadata_index_revision",
        "parser_version",
        "chunker_version",
        "entity_count",
        "relationship_count",
        "stale_count",
        "tombstone_count",
        "updated_at",
    },
    "graph_tombstones": {
        "tombstone_id",
        "record_kind",
        "record_vault_id",
        "record_id",
        "effective_scope",
        "reason",
        "graph_run_id",
        "graph_index_revision",
        "graph_extraction_spec_version",
        "graph_extraction_spec_digest",
        "tombstoned_at",
    },
}


class SQLiteGraphStore:
    def __init__(self, database_path: Path, *, initialize: bool, read_only: bool) -> None:
        self._database_path = database_path.expanduser().resolve()
        self._initialize = initialize
        self._read_only = read_only
        if initialize:
            self._database_path.parent.mkdir(parents=True, exist_ok=True)
            with self._connect() as connection:
                connection.executescript(SCHEMA)
                connection.execute(
                    """
                    INSERT INTO graph_metadata (key, value)
                    VALUES ('schema_version', ?)
                    ON CONFLICT(key) DO UPDATE SET value = excluded.value
                    """,
                    (GRAPH_SCHEMA_VERSION,),
                )

    @classmethod
    def open_read_only(cls, database_path: Path) -> SQLiteGraphStore:
        return cls(database_path, initialize=False, read_only=True)

    @classmethod
    def open_writable(cls, database_path: Path) -> SQLiteGraphStore:
        return cls(database_path, initialize=True, read_only=False)

    def health(self) -> StoreHealth:
        if not self._database_path.exists():
            return StoreHealth(
                ok=False,
                backend=GRAPH_SQLITE_BACKEND,
                schema_version=GRAPH_SCHEMA_VERSION,
                schema_compatible=False,
                message="not initialized",
            )
        try:
            with self._connect() as connection:
                tables = {
                    str(row["name"])
                    for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
                }
                missing = REQUIRED_TABLES - tables
                if missing:
                    return _incompatible_health(f"schema incompatible: missing {', '.join(sorted(missing))}")
                for table_name, required_columns in REQUIRED_COLUMNS.items():
                    columns = {
                        str(row["name"])
                        for row in connection.execute(f"PRAGMA table_info({table_name})").fetchall()
                    }
                    missing_columns = required_columns - columns
                    if missing_columns:
                        return _incompatible_health(
                            f"schema incompatible: {table_name} missing {', '.join(sorted(missing_columns))}"
                        )
                row = connection.execute(
                    "SELECT value FROM graph_metadata WHERE key = 'schema_version'",
                ).fetchone()
        except (FileNotFoundError, sqlite3.Error) as exc:
            return StoreHealth(
                ok=False,
                backend=GRAPH_SQLITE_BACKEND,
                schema_version=GRAPH_SCHEMA_VERSION,
                schema_compatible=False,
                message=str(exc),
            )
        if row is None or str(row["value"]) != GRAPH_SCHEMA_VERSION:
            return _incompatible_health("schema incompatible: graph schema version mismatch")
        return StoreHealth(
            ok=True,
            backend=GRAPH_SQLITE_BACKEND,
            schema_version=GRAPH_SCHEMA_VERSION,
            schema_compatible=True,
            message="ok",
        )

    def stored_specs(self) -> tuple[GraphExtractionSpec, ...]:
        if not self._database_path.exists():
            return ()
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT spec_version, spec_digest, entity_schema_version, relationship_schema_version,
                       entity_extractor_name, entity_extractor_version, relationship_extractor_name,
                       relationship_extractor_version, relationship_status_rules_version,
                       confidence_rules_version, serialized_spec
                FROM graph_specs
                ORDER BY spec_version, spec_digest
                """
            ).fetchall()
        return tuple(_spec_from_row(row) for row in rows)

    def latest_revisions(self, scopes: tuple[QueryScope, ...]) -> tuple[GraphRevision, ...]:
        _ensure_effective_scopes(scopes)
        if not self._database_path.exists():
            return ()
        revisions: list[GraphRevision] = []
        with self._connect() as connection:
            for scope in scopes:
                row = connection.execute(
                    """
                    SELECT graph_run_id, vault_id, effective_scope, graph_store_schema_version,
                           graph_extraction_spec_version, graph_extraction_spec_digest, graph_index_revision,
                           metadata_index_revision, parser_version, chunker_version, entity_count,
                           relationship_count, stale_count, tombstone_count, updated_at
                    FROM graph_revisions
                    WHERE vault_id = ? AND effective_scope = ?
                    ORDER BY updated_at DESC, graph_index_revision DESC
                    LIMIT 1
                    """,
                    (scope.vault_ids[0], graph_scope_key(scope)),
                ).fetchone()
                if row is not None:
                    revisions.append(_revision_from_row(row))
        return tuple(revisions)

    def current_manifest(self, scopes: tuple[QueryScope, ...]) -> GraphManifest:
        _ensure_effective_scopes(scopes)
        if not self._database_path.exists():
            return _empty_manifest(scopes=scopes)
        scope_keys = {graph_scope_key(scope) for scope in scopes}
        scopes_by_key = {graph_scope_key(scope): scope for scope in scopes}
        selected_vault_ids = {vault_id for scope in scopes for vault_id in scope.vault_ids}
        include_cross_vault = any(scope.include_cross_vault for scope in scopes)
        entity_rows: list[GraphManifestEntity] = []
        relationship_rows: list[GraphManifestRelationship] = []
        evidence_ids: set[str] = set()
        with self._connect() as connection:
            memberships = _record_scopes(connection, scope_keys=scope_keys)
            for membership in memberships:
                if membership.record_kind == "entity":
                    entity = self.get_entity(vault_id=membership.record_vault_id, entity_id=membership.record_id)
                    if entity is None:
                        continue
                    entity_rows.append(_entity_manifest_row(entity=entity, membership=membership))
                    evidence_ids.update(ref.evidence_ref_id for ref in entity.evidence_refs)
                if membership.record_kind == "relationship":
                    relationship = self.get_relationship(
                        source_vault_id=membership.record_vault_id,
                        relationship_id=membership.record_id,
                    )
                    if relationship is None:
                        continue
                    scope = scopes_by_key[membership.effective_scope]
                    if not _relationship_allowed(
                        relationship=relationship,
                        scope=scope,
                        selected_vault_ids=selected_vault_ids,
                        include_cross_vault=include_cross_vault,
                    ):
                        continue
                    relationship_rows.append(
                        _relationship_manifest_row(relationship=relationship, membership=membership)
                    )
                    evidence_ids.update(ref.evidence_ref_id for ref in relationship.evidence_refs)
            evidence_rows = _manifest_evidence_rows(connection, evidence_ids=evidence_ids)
            tombstone_rows = _manifest_tombstones(connection, scope_keys=scope_keys)
        revision_rows = self.latest_revisions(scopes)
        spec = current_graph_extraction_spec()
        if revision_rows:
            spec_version = revision_rows[0].graph_extraction_spec_version
            spec_digest = revision_rows[0].graph_extraction_spec_digest
        else:
            spec_version = spec.spec_version
            spec_digest = spec.spec_digest
        return GraphManifest(
            requested_scope=_combined_scope(scopes),
            effective_scopes=scopes,
            entity_rows=tuple(sorted(entity_rows, key=lambda row: (row.vault_id, row.entity_id))),
            relationship_rows=tuple(
                sorted(relationship_rows, key=lambda row: (row.source_vault_id, row.relationship_id))
            ),
            evidence_rows=evidence_rows,
            tombstone_rows=tombstone_rows,
            graph_store_schema_version=GRAPH_SCHEMA_VERSION,
            graph_extraction_spec_version=spec_version,
            graph_extraction_spec_digest=spec_digest,
            revision_rows=revision_rows,
        )

    def get_entity(self, *, vault_id: str, entity_id: str) -> EntityRecord | None:
        if not self._database_path.exists():
            return None
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT vault_id, entity_id, type, name, normalized_name, aliases_json, canonical_path,
                       confidence, extraction_method, graph_extraction_spec_version,
                       graph_extraction_spec_digest, status, created_at, updated_at, graph_index_revision
                FROM graph_entities
                WHERE vault_id = ? AND entity_id = ?
                """,
                (vault_id, entity_id),
            ).fetchone()
            if row is None:
                return None
            evidence_refs = _evidence_refs_for_owner(
                connection,
                owner_kind="entity",
                owner_vault_id=vault_id,
                owner_id=entity_id,
            )
        return _entity_from_row(row, evidence_refs=evidence_refs)

    def get_relationship(self, *, source_vault_id: str, relationship_id: str) -> RelationshipRecord | None:
        if not self._database_path.exists():
            return None
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT source_vault_id, relationship_id, type, source_entity_id, target_vault_id,
                       target_entity_id, status, confidence, extraction_method,
                       graph_extraction_spec_version, graph_extraction_spec_digest, created_at,
                       updated_at, graph_index_revision
                FROM graph_relationships
                WHERE source_vault_id = ? AND relationship_id = ?
                """,
                (source_vault_id, relationship_id),
            ).fetchone()
            if row is None:
                return None
            evidence_refs = _evidence_refs_for_owner(
                connection,
                owner_kind="relationship",
                owner_vault_id=source_vault_id,
                owner_id=relationship_id,
            )
        return _relationship_from_row(row, evidence_refs=evidence_refs)

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
        _ensure_effective_scopes(plan.effective_scopes)
        revisions_by_scope = {
            revision.effective_scope: replace(revision, graph_store_schema_version=GRAPH_SCHEMA_VERSION)
            for revision in plan.graph_revision_rows
        }
        try:
            with self._connect() as connection:
                _upsert_spec(connection, plan.graph_extraction_spec)
                for entity in plan.entity_upserts:
                    _upsert_entity(connection, entity)
                    _upsert_record_scopes(
                        connection,
                        record_kind="entity",
                        record_vault_id=entity.vault_id,
                        record_id=entity.entity_id,
                        plan=plan,
                        revisions_by_scope=revisions_by_scope,
                    )
                for relationship in plan.relationship_upserts:
                    _upsert_relationship(connection, relationship)
                    _upsert_record_scopes(
                        connection,
                        record_kind="relationship",
                        record_vault_id=relationship.source_vault_id,
                        record_id=relationship.relationship_id,
                        plan=plan,
                        revisions_by_scope=revisions_by_scope,
                    )
                for ref in plan.evidence_ref_upserts:
                    _upsert_evidence_ref(connection, ref)
                for tombstone in plan.entity_tombstones + plan.relationship_tombstones:
                    _upsert_tombstone(connection, tombstone)
                    _apply_tombstone_status(connection, tombstone)
                for revision in revisions_by_scope.values():
                    _upsert_revision(connection, revision)
        except sqlite3.Error as exc:
            raise GraphStoreUnavailable(str(exc)) from exc
        return GraphApplyResult(
            graph_run_id=plan.graph_run_id,
            applied_entity_upsert_count=len(plan.entity_upserts),
            applied_relationship_upsert_count=len(plan.relationship_upserts),
            applied_evidence_ref_upsert_count=len(plan.evidence_ref_upserts),
            applied_tombstone_count=len(plan.entity_tombstones) + len(plan.relationship_tombstones),
            graph_revision_rows=tuple(revisions_by_scope.values()),
            warnings=(),
        )

    def _connect(self) -> sqlite3.Connection:
        if not self._database_path.exists() and not self._initialize:
            raise FileNotFoundError(self._database_path)
        if self._read_only:
            connection = sqlite3.connect(f"file:{self._database_path}?mode=ro", uri=True)
        else:
            connection = sqlite3.connect(self._database_path)
        connection.row_factory = sqlite3.Row
        return connection


def _incompatible_health(message: str) -> StoreHealth:
    return StoreHealth(
        ok=False,
        backend=GRAPH_SQLITE_BACKEND,
        schema_version=GRAPH_SCHEMA_VERSION,
        schema_compatible=False,
        message=message,
    )


def _ensure_effective_scopes(scopes: tuple[QueryScope, ...]) -> None:
    for scope in scopes:
        if len(scope.vault_ids) != 1:
            raise GraphStoreError("GraphStore operations require per-Vault effective scopes")


def _empty_manifest(*, scopes: tuple[QueryScope, ...]) -> GraphManifest:
    spec = current_graph_extraction_spec()
    return GraphManifest(
        requested_scope=_combined_scope(scopes),
        effective_scopes=scopes,
        entity_rows=(),
        relationship_rows=(),
        evidence_rows=(),
        tombstone_rows=(),
        graph_store_schema_version=GRAPH_SCHEMA_VERSION,
        graph_extraction_spec_version=spec.spec_version,
        graph_extraction_spec_digest=spec.spec_digest,
        revision_rows=(),
    )


def _spec_from_row(row: sqlite3.Row) -> GraphExtractionSpec:
    return GraphExtractionSpec(
        spec_version=str(row["spec_version"]),
        spec_digest=str(row["spec_digest"]),
        entity_schema_version=str(row["entity_schema_version"]),
        relationship_schema_version=str(row["relationship_schema_version"]),
        entity_extractor_name=str(row["entity_extractor_name"]),
        entity_extractor_version=str(row["entity_extractor_version"]),
        relationship_extractor_name=str(row["relationship_extractor_name"]),
        relationship_extractor_version=str(row["relationship_extractor_version"]),
        relationship_status_rules_version=str(row["relationship_status_rules_version"]),
        confidence_rules_version=str(row["confidence_rules_version"]),
        serialized_spec=str(row["serialized_spec"]),
    )


def _revision_from_row(row: sqlite3.Row) -> GraphRevision:
    return GraphRevision(
        graph_run_id=str(row["graph_run_id"]),
        vault_id=str(row["vault_id"]),
        effective_scope=str(row["effective_scope"]),
        graph_store_schema_version=str(row["graph_store_schema_version"]),
        graph_extraction_spec_version=str(row["graph_extraction_spec_version"]),
        graph_extraction_spec_digest=str(row["graph_extraction_spec_digest"]),
        graph_index_revision=str(row["graph_index_revision"]),
        metadata_index_revision=str(row["metadata_index_revision"]),
        parser_version=str(row["parser_version"]),
        chunker_version=str(row["chunker_version"]),
        entity_count=int(row["entity_count"]),
        relationship_count=int(row["relationship_count"]),
        stale_count=int(row["stale_count"]),
        tombstone_count=int(row["tombstone_count"]),
        updated_at=str(row["updated_at"]),
    )


def _entity_from_row(row: sqlite3.Row, *, evidence_refs: tuple[GraphEvidenceRef, ...]) -> EntityRecord:
    aliases = json.loads(str(row["aliases_json"]))
    if not isinstance(aliases, list):
        aliases = []
    return EntityRecord(
        vault_id=str(row["vault_id"]),
        entity_id=str(row["entity_id"]),
        type=str(row["type"]),
        name=str(row["name"]),
        normalized_name=str(row["normalized_name"]),
        aliases=tuple(str(alias) for alias in aliases),
        canonical_path=str(row["canonical_path"]) if row["canonical_path"] is not None else None,
        evidence_refs=evidence_refs,
        confidence=float(row["confidence"]),
        extraction_method=str(row["extraction_method"]),
        graph_extraction_spec_version=str(row["graph_extraction_spec_version"]),
        graph_extraction_spec_digest=str(row["graph_extraction_spec_digest"]),
        status=str(row["status"]),
        created_at=str(row["created_at"]),
        updated_at=str(row["updated_at"]),
        graph_index_revision=str(row["graph_index_revision"]),
    )


def _relationship_from_row(row: sqlite3.Row, *, evidence_refs: tuple[GraphEvidenceRef, ...]) -> RelationshipRecord:
    return RelationshipRecord(
        relationship_id=str(row["relationship_id"]),
        type=str(row["type"]),
        source_vault_id=str(row["source_vault_id"]),
        source_entity_id=str(row["source_entity_id"]),
        target_vault_id=str(row["target_vault_id"]),
        target_entity_id=str(row["target_entity_id"]),
        evidence_refs=evidence_refs,
        status=str(row["status"]),
        confidence=float(row["confidence"]),
        extraction_method=str(row["extraction_method"]),
        graph_extraction_spec_version=str(row["graph_extraction_spec_version"]),
        graph_extraction_spec_digest=str(row["graph_extraction_spec_digest"]),
        created_at=str(row["created_at"]),
        updated_at=str(row["updated_at"]),
        graph_index_revision=str(row["graph_index_revision"]),
    )


def _evidence_ref_from_row(row: sqlite3.Row) -> GraphEvidenceRef:
    return GraphEvidenceRef(
        evidence_ref_id=str(row["evidence_ref_id"]),
        owner_kind=str(row["owner_kind"]),
        owner_vault_id=str(row["owner_vault_id"]),
        owner_id=str(row["owner_id"]),
        evidence_vault_id=str(row["evidence_vault_id"]),
        document_id=str(row["document_id"]),
        chunk_id=str(row["chunk_id"]),
        content_hash=str(row["content_hash"]),
        section=str(row["section"]) if row["section"] is not None else None,
        anchor=str(row["anchor"]) if row["anchor"] is not None else None,
        path=str(row["path"]) if row["path"] is not None else None,
        excerpt=str(row["excerpt"]) if row["excerpt"] is not None else None,
    )


def _evidence_refs_for_owner(
    connection: sqlite3.Connection,
    *,
    owner_kind: str,
    owner_vault_id: str,
    owner_id: str,
) -> tuple[GraphEvidenceRef, ...]:
    rows = connection.execute(
        """
        SELECT evidence_ref_id, owner_kind, owner_vault_id, owner_id, evidence_vault_id, document_id,
               chunk_id, content_hash, section, anchor, path, excerpt
        FROM graph_evidence_refs
        WHERE owner_kind = ? AND owner_vault_id = ? AND owner_id = ?
        ORDER BY evidence_ref_id
        """,
        (owner_kind, owner_vault_id, owner_id),
    ).fetchall()
    return tuple(_evidence_ref_from_row(row) for row in rows)


def _record_scopes(connection: sqlite3.Connection, *, scope_keys: set[str]) -> tuple[GraphRecordScope, ...]:
    if not scope_keys:
        return ()
    placeholders = ", ".join("?" for _ in scope_keys)
    rows = connection.execute(
        f"""
        SELECT record_kind, record_vault_id, record_id, effective_scope, metadata_index_revision,
               graph_index_revision, graph_extraction_spec_digest
        FROM graph_record_scopes
        WHERE effective_scope IN ({placeholders})
        ORDER BY record_kind, record_vault_id, record_id, effective_scope
        """,
        tuple(sorted(scope_keys)),
    ).fetchall()
    return tuple(
        GraphRecordScope(
            record_kind=str(row["record_kind"]),
            record_vault_id=str(row["record_vault_id"]),
            record_id=str(row["record_id"]),
            effective_scope=str(row["effective_scope"]),
            metadata_index_revision=str(row["metadata_index_revision"]),
            graph_index_revision=str(row["graph_index_revision"]),
            graph_extraction_spec_digest=str(row["graph_extraction_spec_digest"]),
        )
        for row in rows
    )


def _manifest_evidence_rows(
    connection: sqlite3.Connection,
    *,
    evidence_ids: set[str],
) -> tuple[GraphManifestEvidence, ...]:
    if not evidence_ids:
        return ()
    placeholders = ", ".join("?" for _ in evidence_ids)
    rows = connection.execute(
        f"""
        SELECT evidence_ref_id, owner_kind, owner_vault_id, owner_id, evidence_vault_id, document_id,
               chunk_id, content_hash, anchor
        FROM graph_evidence_refs
        WHERE evidence_ref_id IN ({placeholders})
        ORDER BY evidence_ref_id
        """,
        tuple(sorted(evidence_ids)),
    ).fetchall()
    return tuple(
        GraphManifestEvidence(
            evidence_ref_id=str(row["evidence_ref_id"]),
            owner_kind=str(row["owner_kind"]),
            owner_vault_id=str(row["owner_vault_id"]),
            owner_id=str(row["owner_id"]),
            evidence_vault_id=str(row["evidence_vault_id"]),
            document_id=str(row["document_id"]),
            chunk_id=str(row["chunk_id"]),
            content_hash=str(row["content_hash"]),
            anchor=str(row["anchor"]) if row["anchor"] is not None else None,
        )
        for row in rows
    )


def _manifest_tombstones(connection: sqlite3.Connection, *, scope_keys: set[str]) -> tuple[GraphTombstone, ...]:
    if not scope_keys:
        return ()
    placeholders = ", ".join("?" for _ in scope_keys)
    rows = connection.execute(
        f"""
        SELECT tombstone_id, record_kind, record_vault_id, record_id, effective_scope, reason, graph_run_id,
               graph_index_revision, graph_extraction_spec_version, graph_extraction_spec_digest, tombstoned_at
        FROM graph_tombstones
        WHERE effective_scope IN ({placeholders})
        ORDER BY tombstone_id
        """,
        tuple(sorted(scope_keys)),
    ).fetchall()
    return tuple(_tombstone_from_row(row) for row in rows)


def _tombstone_from_row(row: sqlite3.Row) -> GraphTombstone:
    return GraphTombstone(
        tombstone_id=str(row["tombstone_id"]),
        record_kind=str(row["record_kind"]),
        record_vault_id=str(row["record_vault_id"]),
        record_id=str(row["record_id"]),
        effective_scope=str(row["effective_scope"]),
        reason=str(row["reason"]),
        graph_run_id=str(row["graph_run_id"]),
        graph_index_revision=str(row["graph_index_revision"]),
        graph_extraction_spec_version=str(row["graph_extraction_spec_version"]),
        graph_extraction_spec_digest=str(row["graph_extraction_spec_digest"]),
        tombstoned_at=str(row["tombstoned_at"]),
    )


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


def _upsert_spec(connection: sqlite3.Connection, spec: GraphExtractionSpec) -> None:
    connection.execute(
        """
        INSERT INTO graph_specs (
          spec_digest, spec_version, entity_schema_version, relationship_schema_version,
          entity_extractor_name, entity_extractor_version, relationship_extractor_name,
          relationship_extractor_version, relationship_status_rules_version, confidence_rules_version,
          serialized_spec
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(spec_digest) DO UPDATE SET
          spec_version = excluded.spec_version,
          entity_schema_version = excluded.entity_schema_version,
          relationship_schema_version = excluded.relationship_schema_version,
          entity_extractor_name = excluded.entity_extractor_name,
          entity_extractor_version = excluded.entity_extractor_version,
          relationship_extractor_name = excluded.relationship_extractor_name,
          relationship_extractor_version = excluded.relationship_extractor_version,
          relationship_status_rules_version = excluded.relationship_status_rules_version,
          confidence_rules_version = excluded.confidence_rules_version,
          serialized_spec = excluded.serialized_spec
        """,
        (
            spec.spec_digest,
            spec.spec_version,
            spec.entity_schema_version,
            spec.relationship_schema_version,
            spec.entity_extractor_name,
            spec.entity_extractor_version,
            spec.relationship_extractor_name,
            spec.relationship_extractor_version,
            spec.relationship_status_rules_version,
            spec.confidence_rules_version,
            spec.serialized_spec,
        ),
    )


def _upsert_entity(connection: sqlite3.Connection, entity: EntityRecord) -> None:
    connection.execute(
        """
        INSERT INTO graph_entities (
          vault_id, entity_id, type, name, normalized_name, aliases_json, canonical_path, confidence,
          extraction_method, graph_extraction_spec_version, graph_extraction_spec_digest, status,
          created_at, updated_at, graph_index_revision
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(vault_id, entity_id) DO UPDATE SET
          type = excluded.type,
          name = excluded.name,
          normalized_name = excluded.normalized_name,
          aliases_json = excluded.aliases_json,
          canonical_path = excluded.canonical_path,
          confidence = excluded.confidence,
          extraction_method = excluded.extraction_method,
          graph_extraction_spec_version = excluded.graph_extraction_spec_version,
          graph_extraction_spec_digest = excluded.graph_extraction_spec_digest,
          status = excluded.status,
          updated_at = excluded.updated_at,
          graph_index_revision = excluded.graph_index_revision
        """,
        (
            entity.vault_id,
            entity.entity_id,
            entity.type,
            entity.name,
            entity.normalized_name,
            json.dumps(list(entity.aliases), sort_keys=True),
            entity.canonical_path,
            entity.confidence,
            entity.extraction_method,
            entity.graph_extraction_spec_version,
            entity.graph_extraction_spec_digest,
            entity.status,
            entity.created_at,
            entity.updated_at,
            entity.graph_index_revision,
        ),
    )


def _upsert_relationship(connection: sqlite3.Connection, relationship: RelationshipRecord) -> None:
    connection.execute(
        """
        INSERT INTO graph_relationships (
          source_vault_id, relationship_id, type, source_entity_id, target_vault_id, target_entity_id,
          status, confidence, extraction_method, graph_extraction_spec_version,
          graph_extraction_spec_digest, created_at, updated_at, graph_index_revision
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(source_vault_id, relationship_id) DO UPDATE SET
          type = excluded.type,
          source_entity_id = excluded.source_entity_id,
          target_vault_id = excluded.target_vault_id,
          target_entity_id = excluded.target_entity_id,
          status = excluded.status,
          confidence = excluded.confidence,
          extraction_method = excluded.extraction_method,
          graph_extraction_spec_version = excluded.graph_extraction_spec_version,
          graph_extraction_spec_digest = excluded.graph_extraction_spec_digest,
          updated_at = excluded.updated_at,
          graph_index_revision = excluded.graph_index_revision
        """,
        (
            relationship.source_vault_id,
            relationship.relationship_id,
            relationship.type,
            relationship.source_entity_id,
            relationship.target_vault_id,
            relationship.target_entity_id,
            relationship.status,
            relationship.confidence,
            relationship.extraction_method,
            relationship.graph_extraction_spec_version,
            relationship.graph_extraction_spec_digest,
            relationship.created_at,
            relationship.updated_at,
            relationship.graph_index_revision,
        ),
    )


def _upsert_evidence_ref(connection: sqlite3.Connection, ref: GraphEvidenceRef) -> None:
    connection.execute(
        """
        INSERT INTO graph_evidence_refs (
          evidence_ref_id, owner_kind, owner_vault_id, owner_id, evidence_vault_id, document_id,
          chunk_id, content_hash, section, anchor, anchor_key, path, excerpt
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(evidence_ref_id) DO UPDATE SET
          owner_kind = excluded.owner_kind,
          owner_vault_id = excluded.owner_vault_id,
          owner_id = excluded.owner_id,
          evidence_vault_id = excluded.evidence_vault_id,
          document_id = excluded.document_id,
          chunk_id = excluded.chunk_id,
          content_hash = excluded.content_hash,
          section = excluded.section,
          anchor = excluded.anchor,
          anchor_key = excluded.anchor_key,
          path = excluded.path,
          excerpt = excluded.excerpt
        """,
        (
            ref.evidence_ref_id,
            ref.owner_kind,
            ref.owner_vault_id,
            ref.owner_id,
            ref.evidence_vault_id,
            ref.document_id,
            ref.chunk_id,
            ref.content_hash,
            ref.section,
            ref.anchor,
            ref.anchor or "",
            ref.path,
            ref.excerpt,
        ),
    )


def _upsert_record_scopes(
    connection: sqlite3.Connection,
    *,
    record_kind: str,
    record_vault_id: str,
    record_id: str,
    plan: GraphReconcilePlan,
    revisions_by_scope: dict[str, GraphRevision],
) -> None:
    for scope in plan.effective_scopes:
        if scope.vault_ids[0] != record_vault_id:
            continue
        effective_scope = graph_scope_key(scope)
        revision = revisions_by_scope[effective_scope]
        connection.execute(
            """
            INSERT INTO graph_record_scopes (
              record_kind, record_vault_id, record_id, effective_scope, metadata_index_revision,
              graph_index_revision, graph_extraction_spec_digest
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(record_kind, record_vault_id, record_id, effective_scope) DO UPDATE SET
              metadata_index_revision = excluded.metadata_index_revision,
              graph_index_revision = excluded.graph_index_revision,
              graph_extraction_spec_digest = excluded.graph_extraction_spec_digest
            """,
            (
                record_kind,
                record_vault_id,
                record_id,
                effective_scope,
                revision.metadata_index_revision,
                revision.graph_index_revision,
                plan.graph_extraction_spec.spec_digest,
            ),
        )


def _upsert_tombstone(connection: sqlite3.Connection, tombstone: GraphTombstone) -> None:
    connection.execute(
        """
        DELETE FROM graph_tombstones
        WHERE record_kind = ?
          AND record_vault_id = ?
          AND record_id = ?
          AND effective_scope = ?
          AND tombstone_id != ?
        """,
        (
            tombstone.record_kind,
            tombstone.record_vault_id,
            tombstone.record_id,
            tombstone.effective_scope,
            tombstone.tombstone_id,
        ),
    )
    connection.execute(
        """
        INSERT INTO graph_tombstones (
          tombstone_id, record_kind, record_vault_id, record_id, effective_scope, reason, graph_run_id,
          graph_index_revision, graph_extraction_spec_version, graph_extraction_spec_digest, tombstoned_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(tombstone_id) DO UPDATE SET
          reason = excluded.reason,
          graph_run_id = excluded.graph_run_id,
          graph_index_revision = excluded.graph_index_revision,
          graph_extraction_spec_version = excluded.graph_extraction_spec_version,
          graph_extraction_spec_digest = excluded.graph_extraction_spec_digest,
          tombstoned_at = excluded.tombstoned_at
        """,
        (
            tombstone.tombstone_id,
            tombstone.record_kind,
            tombstone.record_vault_id,
            tombstone.record_id,
            tombstone.effective_scope,
            tombstone.reason,
            tombstone.graph_run_id,
            tombstone.graph_index_revision,
            tombstone.graph_extraction_spec_version,
            tombstone.graph_extraction_spec_digest,
            tombstone.tombstoned_at,
        ),
    )


def _apply_tombstone_status(connection: sqlite3.Connection, tombstone: GraphTombstone) -> None:
    if tombstone.record_kind == "entity":
        connection.execute(
            """
            UPDATE graph_entities
            SET status = 'tombstoned', updated_at = ?, graph_index_revision = ?
            WHERE vault_id = ? AND entity_id = ?
            """,
            (tombstone.tombstoned_at, tombstone.graph_index_revision, tombstone.record_vault_id, tombstone.record_id),
        )
    if tombstone.record_kind == "relationship":
        connection.execute(
            """
            UPDATE graph_relationships
            SET status = 'deprecated', updated_at = ?, graph_index_revision = ?
            WHERE source_vault_id = ? AND relationship_id = ?
            """,
            (tombstone.tombstoned_at, tombstone.graph_index_revision, tombstone.record_vault_id, tombstone.record_id),
        )


def _upsert_revision(connection: sqlite3.Connection, revision: GraphRevision) -> None:
    connection.execute(
        """
        INSERT INTO graph_revisions (
          graph_run_id, vault_id, effective_scope, graph_store_schema_version, graph_extraction_spec_version,
          graph_extraction_spec_digest, graph_index_revision, metadata_index_revision, parser_version,
          chunker_version, entity_count, relationship_count, stale_count, tombstone_count, updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(vault_id, effective_scope, graph_index_revision) DO UPDATE SET
          graph_run_id = excluded.graph_run_id,
          graph_store_schema_version = excluded.graph_store_schema_version,
          graph_extraction_spec_version = excluded.graph_extraction_spec_version,
          graph_extraction_spec_digest = excluded.graph_extraction_spec_digest,
          metadata_index_revision = excluded.metadata_index_revision,
          parser_version = excluded.parser_version,
          chunker_version = excluded.chunker_version,
          entity_count = excluded.entity_count,
          relationship_count = excluded.relationship_count,
          stale_count = excluded.stale_count,
          tombstone_count = excluded.tombstone_count,
          updated_at = excluded.updated_at
        """,
        (
            revision.graph_run_id,
            revision.vault_id,
            revision.effective_scope,
            revision.graph_store_schema_version,
            revision.graph_extraction_spec_version,
            revision.graph_extraction_spec_digest,
            revision.graph_index_revision,
            revision.metadata_index_revision,
            revision.parser_version,
            revision.chunker_version,
            revision.entity_count,
            revision.relationship_count,
            revision.stale_count,
            revision.tombstone_count,
            revision.updated_at,
        ),
    )
