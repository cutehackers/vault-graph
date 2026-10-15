"""Revision-bound legacy graph queries over the document graph projection."""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import tempfile
import threading
import uuid
import weakref
from dataclasses import asdict, replace
from pathlib import Path
from types import TracebackType
from typing import Any, Literal, cast

from graph_document import DocumentGraphSnapshot, GraphLimits, ReadLimits

from vault_graph.errors import GraphReadOnlyViolation, GraphStoreError, GraphStoreUnavailable
from vault_graph.extraction.graph_occurrences import (
    EntityOccurrence,
    RelationshipOccurrence,
    entity_occurrence_key,
)
from vault_graph.extraction.vault_graph_document_adapter import RestoredGraph, VaultGraphDocumentAdapter
from vault_graph.graph.graph_contracts import (
    EntityRecord,
    GraphApplyResult,
    GraphEvidenceRef,
    GraphExtractionSpec,
    GraphManifest,
    GraphReconcilePlan,
    GraphRevision,
    GraphTombstone,
    RelationshipRecord,
)
from vault_graph.graph.graph_identity import graph_scope_key, stable_entity_id, stable_relationship_id
from vault_graph.graph.graph_query import (
    GraphEntityIdentity,
    GraphEntityQuery,
    GraphEntityQueryResult,
    GraphRelationshipIdentity,
    GraphRelationshipQuery,
    GraphRelationshipQueryResult,
)
from vault_graph.ingestion.vault_catalog import QueryScope
from vault_graph.storage.interfaces.evidence_owner_lookup import EvidenceOwnerRecord
from vault_graph.storage.interfaces.graph_store import GraphStore
from vault_graph.storage.interfaces.metadata_store import MetadataStore
from vault_graph.storage.interfaces.store_health import StoreHealth
from vault_graph.storage.local.sqlite_graph_store import GRAPH_SCHEMA_VERSION, SCHEMA, SQLiteGraphStore


def _canonical(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


class _ClosingConnection(sqlite3.Connection):
    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> Literal[False]:
        try:
            return super().__exit__(exc_type, exc_value, traceback)
        finally:
            self.close()


class _MemoryGraphStore(SQLiteGraphStore):
    """Reuse the existing query SQL without writing a second durable graph DB."""

    def __init__(self) -> None:
        self._database_path = Path("/dev/null")
        self._initialize = True
        self._read_only = False
        self._uri = f"file:vault-graph-{uuid.uuid4().hex}?mode=memory&cache=shared"
        self._keeper = sqlite3.connect(self._uri, uri=True, check_same_thread=False)
        self._keeper.row_factory = sqlite3.Row
        self._keeper.executescript(SCHEMA)
        self._keeper.execute(
            "INSERT INTO graph_metadata (key, value) VALUES ('schema_version', ?)",
            (GRAPH_SCHEMA_VERSION,),
        )
        self._keeper.commit()
        self._validation_entities: dict[tuple[str, str], EntityRecord | None] | None = None
        self._validation_relationships: dict[tuple[str, str], RelationshipRecord | None] | None = None

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self._uri, uri=True, factory=_ClosingConnection)
        connection.row_factory = sqlite3.Row
        return connection

    def close(self) -> None:
        self._keeper.close()

    def get_entity(self, *, vault_id: str, entity_id: str) -> EntityRecord | None:
        cache = self._validation_entities
        if cache is None:
            return super().get_entity(vault_id=vault_id, entity_id=entity_id)
        key = (vault_id, entity_id)
        if key not in cache:
            cache[key] = super().get_entity(vault_id=vault_id, entity_id=entity_id)
        return cache[key]

    def get_relationship(self, *, source_vault_id: str, relationship_id: str) -> RelationshipRecord | None:
        cache = self._validation_relationships
        if cache is None:
            return super().get_relationship(source_vault_id=source_vault_id, relationship_id=relationship_id)
        key = (source_vault_id, relationship_id)
        if key not in cache:
            cache[key] = super().get_relationship(source_vault_id=source_vault_id, relationship_id=relationship_id)
        return cache[key]


def _scope(data: dict[str, Any]) -> QueryScope:
    return QueryScope(
        vault_ids=tuple(data["vault_ids"]),
        content_scopes=tuple(data["content_scopes"]),
        include_cross_vault=data["include_cross_vault"],
    )


def _entity(data: dict[str, Any]) -> EntityRecord:
    return EntityRecord(
        **{key: value for key, value in data.items() if key not in {"aliases", "evidence_refs"}},
        aliases=tuple(data["aliases"]),
        evidence_refs=tuple(GraphEvidenceRef(**ref) for ref in data["evidence_refs"]),
    )


def _relationship(data: dict[str, Any]) -> RelationshipRecord:
    return RelationshipRecord(
        **{key: value for key, value in data.items() if key != "evidence_refs"},
        evidence_refs=tuple(GraphEvidenceRef(**ref) for ref in data["evidence_refs"]),
    )


def _plan(data: dict[str, Any]) -> GraphReconcilePlan:
    return GraphReconcilePlan(
        requested_scope=_scope(data["requested_scope"]),
        actual_scopes=tuple(_scope(scope) for scope in data["actual_scopes"]),
        graph_run_id=data["graph_run_id"],
        entity_upserts=tuple(_entity(entity) for entity in data["entity_upserts"]),
        relationship_upserts=tuple(_relationship(edge) for edge in data["relationship_upserts"]),
        evidence_ref_upserts=tuple(GraphEvidenceRef(**ref) for ref in data["evidence_ref_upserts"]),
        entity_tombstones=tuple(GraphTombstone(**row) for row in data["entity_tombstones"]),
        relationship_tombstones=tuple(GraphTombstone(**row) for row in data["relationship_tombstones"]),
        graph_revision_rows=tuple(GraphRevision(**row) for row in data["graph_revision_rows"]),
        graph_extraction_spec=GraphExtractionSpec(**data["graph_extraction_spec"]),
        projection_cache_invalidations=tuple(data["projection_cache_invalidations"]),
    )


def _snapshot_plan(source_store: GraphStore, scope: QueryScope) -> GraphReconcilePlan:
    manifest = source_store.current_manifest((scope,))
    revisions = manifest.revision_rows
    if len(revisions) != 1:
        raise GraphStoreUnavailable("scope needs exactly one revision for compatibility checkpoint")
    spec = next(
        (item for item in source_store.stored_specs() if item.spec_digest == revisions[0].graph_extraction_spec_digest),
        None,
    )
    if spec is None:
        raise GraphStoreUnavailable("graph extraction spec is missing")
    entities = tuple(
        entity
        for row in manifest.entity_rows
        if (entity := source_store.get_entity(vault_id=row.vault_id, entity_id=row.entity_id)) is not None
    )
    relationships = tuple(
        edge
        for row in manifest.relationship_rows
        if (
            edge := source_store.get_relationship(
                source_vault_id=row.source_vault_id, relationship_id=row.relationship_id
            )
        )
        is not None
    )
    refs = {ref.evidence_ref_id: ref for entity in entities for ref in entity.evidence_refs}
    refs.update({ref.evidence_ref_id: ref for edge in relationships for ref in edge.evidence_refs})
    return GraphReconcilePlan(
        requested_scope=scope,
        actual_scopes=(scope,),
        graph_run_id=revisions[0].graph_run_id,
        entity_upserts=entities,
        relationship_upserts=relationships,
        evidence_ref_upserts=tuple(refs[key] for key in sorted(refs)),
        entity_tombstones=tuple(row for row in manifest.tombstone_rows if row.record_kind == "entity"),
        relationship_tombstones=tuple(row for row in manifest.tombstone_rows if row.record_kind == "relationship"),
        graph_revision_rows=tuple(replace(row, graph_store_schema_version=GRAPH_SCHEMA_VERSION) for row in revisions),
        graph_extraction_spec=spec,
        projection_cache_invalidations=(),
    )


class DocumentGraphStore:
    """GraphStore compatibility backed by verified document graph revisions."""

    def __init__(
        self,
        directory: Path,
        *,
        metadata_store: MetadataStore,
        graph_limits: GraphLimits,
        read_limits: ReadLimits,
        read_only: bool,
    ) -> None:
        self._directory = directory.expanduser().resolve()
        self._marker = self._directory / "compatibility.json"
        self._read_only = read_only
        self._poisoned = False
        self._closed = False
        self._manifest_cache: tuple[tuple[QueryScope, ...], GraphManifest] | None = None
        self._max_compat_bytes = max(1_048_576, read_limits.max_serialized_utf8_bytes * 8)
        self._lock = threading.RLock()
        self._check_paths(directory)
        self._adapter = VaultGraphDocumentAdapter(
            metadata_store=metadata_store,
            db_path=self._directory / "derived.sqlite3",
            manifest_dir=self._directory / "manifests",
            graph_limits=graph_limits,
            read_limits=read_limits,
        )
        self._query = _MemoryGraphStore()
        try:
            self._state = self._load_state()
            for plan_data in self._state["plans"]:
                self._query.apply_reconcile_plan(_plan(plan_data))
            restored_graphs = self._validate_collections()
            self._prune_historical_active_evidence(restored_graphs)
            self._query._read_only = True
        except (KeyError, TypeError, ValueError, IndexError) as exc:
            self._query.close()
            raise GraphStoreUnavailable(f"document graph compatibility checkpoint invalid: {exc}") from exc
        except Exception:
            self._query.close()
            raise
        self._finalizer = weakref.finalize(self, self._query.close)

    @classmethod
    def open_read_only(
        cls,
        directory: Path,
        *,
        metadata_store: MetadataStore,
        graph_limits: GraphLimits,
        read_limits: ReadLimits,
    ) -> DocumentGraphStore:
        return cls(
            directory,
            metadata_store=metadata_store,
            graph_limits=graph_limits,
            read_limits=read_limits,
            read_only=True,
        )

    @classmethod
    def open_writable(
        cls,
        directory: Path,
        *,
        metadata_store: MetadataStore,
        graph_limits: GraphLimits,
        read_limits: ReadLimits,
    ) -> DocumentGraphStore:
        return cls(
            directory,
            metadata_store=metadata_store,
            graph_limits=graph_limits,
            read_limits=read_limits,
            read_only=False,
        )

    def close(self) -> None:
        with self._lock:
            if not self._closed:
                self._closed = True
                self._manifest_cache = None
                self._finalizer()

    def _assert_usable(self) -> None:
        if self._closed:
            raise GraphStoreUnavailable("document graph store is closed")
        if self._poisoned:
            raise GraphStoreUnavailable("document graph store must be reopened after failed publication")

    def current_document_evidence_refs(self) -> tuple[GraphEvidenceRef, ...]:
        """Return live evidence from the verified document snapshots for hygiene checks."""
        with self._lock:
            self._assert_usable()
            restored_graphs = self._validate_collections()
            refs: dict[str, GraphEvidenceRef] = {}
            for restored in restored_graphs:
                for ref in restored.evidence_refs:
                    previous = refs.setdefault(ref.evidence_ref_id, ref)
                    if previous != ref:
                        raise GraphStoreUnavailable("document graph evidence ID collision")
            return tuple(refs[key] for key in sorted(refs))

    def _check_paths(self, original: Path) -> None:
        if original.is_symlink() or any(parent.is_symlink() for parent in original.parents):
            raise GraphStoreUnavailable("document graph path crosses a symlink")
        for path in (self._directory / "derived.sqlite3", self._directory / "manifests", self._marker):
            if path.is_symlink():
                raise GraphStoreUnavailable("document graph path crosses a symlink")

    def _load_state(self) -> dict[str, Any]:
        if not self._marker.exists():
            if self._read_only or (self._directory / "derived.sqlite3").exists():
                raise GraphStoreUnavailable("document graph compatibility manifest is missing")
            return {"version": 1, "plans": [], "collections": {}}
        try:
            with self._marker.open("rb") as stream:
                file_size = os.fstat(stream.fileno()).st_size
                if file_size > self._max_compat_bytes:
                    raise ValueError("compatibility manifest exceeds read limit")
                content = stream.read(file_size + 1)
                if len(content) != file_size or stream.read(1):
                    raise ValueError("compatibility manifest changed during read")
            wrapped = json.loads(content.decode("utf-8"))
            payload = wrapped["payload"]
            if payload["version"] != 1 or hashlib.sha256(_canonical(payload).encode()).hexdigest() != wrapped["digest"]:
                raise ValueError("manifest digest mismatch")
            if not isinstance(payload["plans"], list) or not isinstance(payload["collections"], dict):
                raise ValueError("manifest shape mismatch")
            return cast(dict[str, Any], payload)
        except (OSError, UnicodeError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise GraphStoreUnavailable(f"document graph compatibility manifest invalid: {exc}") from exc

    def _validate_collections(self) -> tuple[RestoredGraph, ...]:
        self._query._validation_entities = {}
        self._query._validation_relationships = {}
        try:
            return self._validate_collections_uncached()
        finally:
            self._query._validation_entities = None
            self._query._validation_relationships = None

    def _validate_collections_uncached(self) -> tuple[RestoredGraph, ...]:
        restored_graphs: list[RestoredGraph] = []
        plan_scopes: dict[str, GraphRevision] = {}
        for raw_plan in self._state["plans"]:
            plan = _plan(raw_plan)
            if len(plan.actual_scopes) != 1 or len(plan.graph_revision_rows) != 1:
                raise GraphStoreUnavailable("compatibility checkpoint must contain one actual scope per plan")
            scope = plan.actual_scopes[0]
            key = graph_scope_key(scope)
            if plan.requested_scope != scope or key in plan_scopes:
                raise GraphStoreUnavailable("compatibility checkpoint has a duplicate or inconsistent scope")
            revision = plan.graph_revision_rows[0]
            if (
                revision.actual_scope != key
                or revision.graph_extraction_spec_digest != plan.graph_extraction_spec.spec_digest
            ):
                raise GraphStoreUnavailable("compatibility checkpoint revision or spec differs from scope")
            plan_scopes[key] = revision
        if set(plan_scopes) != set(self._state["collections"]):
            raise GraphStoreUnavailable("compatibility checkpoint scope and document collections differ")
        if not plan_scopes and (self._marker.exists() or (self._directory / "derived.sqlite3").exists()):
            raise GraphStoreUnavailable("document graph cache exists without a compatibility scope")
        for key, entry in self._state["collections"].items():
            scope = _scope(entry["scope"])
            expected_collection_id = _canonical(
                (
                    scope.vault_ids[0],
                    _canonical(tuple(sorted(scope.content_scopes))),
                    str(scope.include_cross_vault),
                    self._adapter._profile.profile_digest,
                )
            )
            if key != graph_scope_key(scope) or entry["collection_id"] != expected_collection_id:
                raise GraphStoreUnavailable("document collection identity differs from compatibility scope")
            if self._query.latest_revisions((scope,)) != (plan_scopes[key],):
                raise GraphStoreUnavailable("compatibility revision differs from checkpoint scope")
            snapshot, restored, mapping = self._adapter.read_verified_snapshot(collection_id=entry["collection_id"])
            if restored.graph_revision != entry["graph_revision"] or restored.read_digest != entry["read_digest"]:
                raise GraphStoreUnavailable("document graph revision differs from compatibility manifest")
            self._validate_entity_contributions(snapshot, mapping)
            manifest = self._query.current_manifest((scope,))
            tombstoned_entities = {
                (row.record_vault_id, row.record_id) for row in manifest.tombstone_rows if row.record_kind == "entity"
            }
            tombstoned_relationships = {
                (row.record_vault_id, row.record_id)
                for row in manifest.tombstone_rows
                if row.record_kind == "relationship"
            }
            entities = {
                (row.vault_id, row.entity_id): self._query.get_entity(vault_id=row.vault_id, entity_id=row.entity_id)
                for row in manifest.entity_rows
                if (row.vault_id, row.entity_id) not in tombstoned_entities
            }
            relationships = {
                (row.source_vault_id, row.relationship_id): self._query.get_relationship(
                    source_vault_id=row.source_vault_id, relationship_id=row.relationship_id
                )
                for row in manifest.relationship_rows
                if (row.source_vault_id, row.relationship_id) not in tombstoned_relationships
            }
            if {(node.vault_id, node.entity_id) for node in restored.nodes} != set(entities):
                raise GraphStoreUnavailable("document graph entity identities differ from compatibility manifest")
            for node in restored.nodes:
                entity = entities[(node.vault_id, node.entity_id)]
                if entity is None or (entity.status, node.type, node.name, node.normalized_name) != (
                    "active",
                    entity.type,
                    entity.name,
                    entity.normalized_name,
                ):
                    raise GraphStoreUnavailable("document graph entity fields differ from compatibility manifest")
            if {(edge.source_vault_id, edge.relationship_id) for edge in restored.relationships} != set(relationships):
                raise GraphStoreUnavailable("document graph relationship identities differ from compatibility manifest")
            for edge in restored.relationships:
                relationship = relationships[(edge.source_vault_id, edge.relationship_id)]
                if relationship is None or (
                    edge.relationship_type,
                    edge.source_entity_id,
                    edge.target_vault_id,
                    edge.target_entity_id,
                    edge.status,
                    edge.confidence,
                ) != (
                    relationship.type,
                    relationship.source_entity_id,
                    relationship.target_vault_id,
                    relationship.target_entity_id,
                    relationship.status,
                    relationship.confidence,
                ):
                    raise GraphStoreUnavailable("document graph relationship fields differ from compatibility manifest")
                legacy_ref_ids = {ref.evidence_ref_id for ref in relationship.evidence_refs}
                if not set(edge.evidence_ref_ids) <= legacy_ref_ids:
                    raise GraphStoreUnavailable(
                        "document graph relationship evidence differs from compatibility manifest"
                    )
            legacy_refs = {
                ref.evidence_ref_id: ref
                for record in (*tuple(entities.values()), *tuple(relationships.values()))
                if record is not None
                for ref in record.evidence_refs
            }
            actual_refs = {ref.evidence_ref_id: ref for ref in restored.evidence_refs}
            if any(legacy_refs.get(key) != ref for key, ref in actual_refs.items()):
                raise GraphStoreUnavailable(
                    "document graph evidence differs from compatibility manifest: "
                    f"unexpected={sorted(set(actual_refs) - set(legacy_refs))}"
                )
            restored_graphs.append(restored)
        return tuple(restored_graphs)

    def _validate_entity_contributions(self, snapshot: DocumentGraphSnapshot | None, mapping: dict[str, Any]) -> None:
        if snapshot is None:
            return
        generic_nodes = {(node.kind, node.key): node for node in snapshot.nodes}
        grouped: dict[tuple[str, str, str, str], list[EntityOccurrence]] = {}
        relationship_values: list[RelationshipOccurrence] = []
        for record in mapping["documents"].values():
            for raw in record["entities"]:
                occurrence = EntityOccurrence(**{**raw, "aliases": tuple(raw["aliases"])})
                grouped.setdefault(entity_occurrence_key(occurrence), []).append(occurrence)
            for raw in record["relationships"]:
                relationship_values.append(
                    RelationshipOccurrence(
                        **{
                            **raw,
                            "source_entity_key": tuple(raw["source_entity_key"]),
                            "target_entity_key": tuple(raw["target_entity_key"]),
                        }
                    )
                )
        ids: dict[tuple[str, str, str, str], str] = {}
        for key, values in grouped.items():
            generic_key = _canonical(key)
            node = generic_nodes.get(("legacy", generic_key))
            expected_names = tuple(sorted({name for value in values for name in (value.name, *value.aliases)}))
            if node is None or node.aliases != expected_names:
                raise GraphStoreUnavailable("document graph aliases differ from occurrence mapping")
            values.sort(
                key=lambda value: (value.vault_id, value.path, value.chunk_id, value.extraction_method, value.name)
            )
            representative = max(values, key=lambda value: value.confidence)
            entity_id = stable_entity_id(
                vault_id=key[0], entity_type=key[1], normalized_name=key[2], canonical_path=key[3] or None
            )
            ids[key] = entity_id
            entity = self._query.get_entity(vault_id=key[0], entity_id=entity_id)
            if entity is None or (
                entity.aliases,
                entity.canonical_path,
                entity.confidence,
                entity.extraction_method,
            ) != (
                tuple(sorted({alias for value in values for alias in value.aliases})),
                representative.canonical_path,
                representative.confidence,
                representative.extraction_method,
            ):
                raise GraphStoreUnavailable("legacy entity fields differ from document graph contribution")
        grouped_relationships: dict[tuple[str, str], list[RelationshipOccurrence]] = {}
        for relation_occurrence in relationship_values:
            if relation_occurrence.source_vault_id != relation_occurrence.target_vault_id:
                continue
            source_id = ids.get(relation_occurrence.source_entity_key)
            target_id = ids.get(relation_occurrence.target_entity_key)
            if source_id is None or target_id is None:
                continue
            relationship_id = stable_relationship_id(
                relationship_type=relation_occurrence.relationship_type,
                source_vault_id=relation_occurrence.source_vault_id,
                source_entity_id=source_id,
                target_vault_id=relation_occurrence.target_vault_id,
                target_entity_id=target_id,
            )
            grouped_relationships.setdefault((relation_occurrence.source_vault_id, relationship_id), []).append(
                relation_occurrence
            )
        for (vault_id, relationship_id), relation_group in grouped_relationships.items():
            relation_group.sort(
                key=lambda value: (value.source_vault_id, value.path, value.chunk_id, value.extraction_method)
            )
            relation_representative = max(relation_group, key=lambda value: value.confidence)
            relationship = self._query.get_relationship(source_vault_id=vault_id, relationship_id=relationship_id)
            if relationship is None or relationship.extraction_method != relation_representative.extraction_method:
                raise GraphStoreUnavailable("legacy relationship fields differ from document graph contribution")

    def _prune_historical_active_evidence(self, restored_graphs: tuple[RestoredGraph, ...]) -> None:
        active_owners: dict[tuple[str, str, str], set[str]] = {}
        for restored in restored_graphs:
            for node in restored.nodes:
                active_owners.setdefault(("entity", node.vault_id, node.entity_id), set())
            for edge in restored.relationships:
                active_owners.setdefault(("relationship", edge.source_vault_id, edge.relationship_id), set())
            for ref in restored.evidence_refs:
                active_owners.setdefault((ref.owner_kind, ref.owner_vault_id, ref.owner_id), set()).add(
                    ref.evidence_ref_id
                )
        with self._query._connect() as connection:
            for (kind, vault_id, owner_id), live_ids in active_owners.items():
                rows = connection.execute(
                    """SELECT evidence_ref_id FROM graph_evidence_refs
                    WHERE owner_kind = ? AND owner_vault_id = ? AND owner_id = ?""",
                    (kind, vault_id, owner_id),
                ).fetchall()
                for row in rows:
                    if row["evidence_ref_id"] not in live_ids:
                        connection.execute(
                            "DELETE FROM graph_evidence_refs WHERE evidence_ref_id = ?", (row["evidence_ref_id"],)
                        )

    def _publish(self, state: dict[str, Any]) -> None:
        self._directory.mkdir(parents=True, exist_ok=True)
        content = _canonical(state)
        wrapped = _canonical({"digest": hashlib.sha256(content.encode()).hexdigest(), "payload": state})
        name: str | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w", encoding="utf-8", dir=self._directory, prefix=".compatibility-", delete=False
            ) as stream:
                name = stream.name
                stream.write(wrapped)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(name, self._marker)
            fd = os.open(self._directory, os.O_RDONLY)
            try:
                os.fsync(fd)
            finally:
                os.close(fd)
        finally:
            if name is not None and os.path.exists(name):
                os.unlink(name)

    def health(self) -> StoreHealth:
        with self._lock:
            self._assert_usable()
            return self._query.health()

    def stored_specs(self) -> tuple[GraphExtractionSpec, ...]:
        with self._lock:
            self._assert_usable()
            return self._query.stored_specs()

    def latest_revisions(self, scopes: tuple[QueryScope, ...]) -> tuple[GraphRevision, ...]:
        with self._lock:
            self._assert_usable()
            return self._query.latest_revisions(scopes)

    def evidence_lookup_revisions(self) -> tuple[tuple[str, str], ...]:
        """Expose native document revisions separately from legacy compatibility revisions."""
        with self._lock:
            self._assert_usable()
            return tuple(
                sorted((key, str(entry["graph_revision"])) for key, entry in self._state["collections"].items())
            )

    def lookup_evidence_owners(
        self,
        *,
        vault_id: str,
        document_id: str,
        chunk_id: str,
        scopes: tuple[QueryScope, ...],
        include_cross_vault: bool,
        limit: int,
    ) -> tuple[EvidenceOwnerRecord, ...]:
        with self._lock:
            self._assert_usable()
            return self._query.lookup_evidence_owners(
                vault_id=vault_id,
                document_id=document_id,
                chunk_id=chunk_id,
                scopes=scopes,
                include_cross_vault=include_cross_vault,
                limit=limit,
            )

    def current_manifest(self, scopes: tuple[QueryScope, ...]) -> GraphManifest:
        with self._lock:
            self._assert_usable()
            if self._manifest_cache is not None and self._manifest_cache[0] == scopes:
                return self._manifest_cache[1]
            manifest = self._query.current_manifest(scopes)
            self._manifest_cache = (scopes, manifest)
            return manifest

    def get_entity(self, *, vault_id: str, entity_id: str) -> EntityRecord | None:
        with self._lock:
            self._assert_usable()
            return self._query.get_entity(vault_id=vault_id, entity_id=entity_id)

    def get_relationship(self, *, source_vault_id: str, relationship_id: str) -> RelationshipRecord | None:
        with self._lock:
            self._assert_usable()
            return self._query.get_relationship(source_vault_id=source_vault_id, relationship_id=relationship_id)

    def resolve_entities(self, identities: tuple[GraphEntityIdentity, ...]) -> tuple[EntityRecord, ...]:
        with self._lock:
            self._assert_usable()
            return self._query.resolve_entities(identities)

    def resolve_relationships(
        self, identities: tuple[GraphRelationshipIdentity, ...]
    ) -> tuple[RelationshipRecord, ...]:
        with self._lock:
            self._assert_usable()
            return self._query.resolve_relationships(identities)

    def find_entities(self, query: GraphEntityQuery) -> GraphEntityQueryResult:
        with self._lock:
            self._assert_usable()
            return self._query.find_entities(query)

    def relationships_for_entities(self, query: GraphRelationshipQuery) -> GraphRelationshipQueryResult:
        with self._lock:
            self._assert_usable()
            return self._query.relationships_for_entities(query)

    def apply_reconcile_plan(self, plan: GraphReconcilePlan) -> GraphApplyResult:
        if self._read_only:
            raise GraphReadOnlyViolation("document graph store is read-only")
        with self._lock:
            self._assert_usable()
            self._manifest_cache = None
            self._check_paths(self._directory)
            self._query._read_only = False
            try:
                result = self._query.apply_reconcile_plan(plan)
                collections = dict(self._state["collections"])
                for scope in plan.actual_scopes:
                    batch = self._adapter.materialize_documents(scope)
                    prior = collections.get(graph_scope_key(scope))
                    expected_revision = prior["graph_revision"] if prior else 0
                    synced = self._adapter.sync(batch, expected_revision=expected_revision)
                    restored = self._adapter.restore_snapshot(collection_id=batch.collection_id)
                    collections[graph_scope_key(scope)] = {
                        "scope": asdict(scope),
                        "collection_id": batch.collection_id,
                        "graph_revision": synced.graph_revision,
                        "read_digest": restored.read_digest,
                    }
                new_state = {
                    "version": 1,
                    "plans": [
                        asdict(_snapshot_plan(self._query, _scope(entry["scope"])))
                        for _, entry in sorted(collections.items())
                    ],
                    "collections": collections,
                }
                old_state = self._state
                self._state = new_state
                try:
                    restored_graphs = self._validate_collections()
                    self._prune_historical_active_evidence(restored_graphs)
                    new_state["plans"] = [
                        asdict(_snapshot_plan(self._query, _scope(entry["scope"])))
                        for _, entry in sorted(collections.items())
                    ]
                    self._publish(new_state)
                except Exception:
                    self._state = old_state
                    raise
                return result
            except Exception as exc:
                self._poisoned = True
                if isinstance(exc, GraphStoreError):
                    raise
                raise GraphStoreUnavailable(str(exc)) from exc
            finally:
                self._query._read_only = True

    def bootstrap_from_legacy(self, source_store: GraphStore, scopes: tuple[QueryScope, ...]) -> None:
        """Import legacy compatibility records once, preserving identity and timestamps."""
        if self._read_only or self._state["plans"]:
            raise GraphStoreUnavailable("bootstrap requires an empty writable document graph store")
        self._assert_usable()
        for scope in scopes:
            self.apply_reconcile_plan(_snapshot_plan(source_store, scope))
