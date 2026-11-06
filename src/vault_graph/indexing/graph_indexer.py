from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import PurePosixPath
from typing import Protocol, runtime_checkable

from vault_graph.errors import GraphIndexingError, GraphRecordInvalid, GraphStoreError
from vault_graph.indexing.extraction.entity_extractor import EntityExtractor
from vault_graph.indexing.extraction.graph_occurrences import (
    EntityOccurrence,
    RelationshipOccurrence,
    entity_occurrence_key,
)
from vault_graph.indexing.extraction.graph_source_store import GraphExtractionContext, GraphSourceStore
from vault_graph.indexing.extraction.relationship_extractor import RelationshipExtractor
from vault_graph.indexing.ingestion.document_normalizer import ChunkSnapshot, DocumentSnapshot
from vault_graph.operation.scope.vault_catalog import QueryScope
from vault_graph.retrieval.graph.graph_contracts import (
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
from vault_graph.retrieval.graph.graph_identity import (
    graph_scope_key,
    stable_entity_id,
    stable_evidence_ref_id,
    stable_graph_tombstone_id,
    stable_relationship_id,
)
from vault_graph.storage.interfaces.graph_store import GraphStore


@dataclass(frozen=True)
class GraphIndexPlanReport:
    reconcile_plan: GraphReconcilePlan
    mode: str
    stale_count: int
    warnings: tuple[str, ...]


@dataclass(frozen=True)
class GraphIndexApplyResult:
    reconcile_plan: GraphReconcilePlan | None
    apply_result: GraphApplyResult | None
    mode: str
    stale_count: int
    warnings: tuple[str, ...]
    failed: bool
    error: str | None


@dataclass(frozen=True)
class GraphDocumentChanges:
    """Files one metadata run wrote or removed, as ``(vault_id, path)``.

    With these the graph re-extracts only the documents they touch (spec 2026-11-05 §4.3.3).
    ``index_revision`` is the metadata revision of that run.
    """

    index_revision: str
    changed_paths: tuple[tuple[str, str], ...]
    deleted_paths: tuple[tuple[str, str], ...]


# (owner_kind, owner_vault_id, owner_id): the key of one entity or relationship.
GraphOwner = tuple[str, str, str]


@runtime_checkable
class DocumentReconcileGraphStore(Protocol):
    """A graph store that can rebuild the records some documents touch without reading the whole scope."""

    def evidence_paths(self, *, vault_id: str) -> frozenset[str]: ...

    def evidence_owners_by_path(self, *, vault_id: str, paths: tuple[str, ...]) -> dict[str, frozenset[GraphOwner]]: ...

    def document_entity_owners(self, *, vault_id: str, canonical_paths: tuple[str, ...]) -> frozenset[GraphOwner]: ...

    def evidence_refs_for_owners(self, owners: tuple[GraphOwner, ...]) -> tuple[GraphEvidenceRef, ...]: ...

    def owner_statuses(self, *, actual_scope: str, owners: tuple[GraphOwner, ...]) -> dict[GraphOwner, str]: ...

    def scope_record_counts(self, *, actual_scope: str) -> tuple[int, int]: ...

    def apply_owner_reconcile_plan(
        self,
        plan: GraphReconcilePlan,
        *,
        owners: tuple[GraphOwner, ...],
        kept_evidence_ref_ids: frozenset[str],
    ) -> GraphApplyResult: ...


@dataclass(frozen=True)
class _ScopeSource:
    scope: QueryScope
    chunks: tuple[ChunkSnapshot, ...]
    documents_by_id: dict[str, DocumentSnapshot]
    documents: tuple[DocumentSnapshot, ...]
    context: GraphExtractionContext
    metadata_index_revision: str
    parser_version: str
    chunker_version: str


@dataclass(frozen=True)
class _ScopeDesired:
    scope: QueryScope
    chunks: tuple[ChunkSnapshot, ...]
    documents: tuple[DocumentSnapshot, ...]
    entity_occurrences: tuple[EntityOccurrence, ...]
    relationship_occurrences: tuple[RelationshipOccurrence, ...]
    metadata_index_revision: str
    parser_version: str
    chunker_version: str


@dataclass(frozen=True)
class _ScopeRebuild:
    """The records one scope's changed documents touch, rebuilt from all their evidence."""

    source: _ScopeSource
    owners: frozenset[GraphOwner]
    entity_records: tuple[EntityRecord, ...]
    relationship_records: tuple[RelationshipRecord, ...]
    evidence_refs: tuple[GraphEvidenceRef, ...]
    evidence_ref_upserts: tuple[GraphEvidenceRef, ...]
    entity_tombstones: tuple[GraphTombstone, ...]
    relationship_tombstones: tuple[GraphTombstone, ...]
    entity_count: int
    relationship_count: int
    warnings: tuple[str, ...]


@dataclass(frozen=True)
class _DocumentPlan:
    report: GraphIndexPlanReport
    owners: tuple[GraphOwner, ...]
    kept_evidence_ref_ids: frozenset[str]


class GraphIndexer:
    def __init__(
        self,
        *,
        source_store: GraphSourceStore,
        graph_store: GraphStore,
        entity_extractor: EntityExtractor,
        relationship_extractor: RelationshipExtractor,
        graph_extraction_spec: GraphExtractionSpec,
        metadata_schema_version: str,
        now: Callable[[], str] | None = None,
        graph_run_id_factory: Callable[[], str] | None = None,
        graph_revision_factory: Callable[[], str] | None = None,
    ) -> None:
        self._source_store = source_store
        self._graph_store = graph_store
        self._entity_extractor = entity_extractor
        self._relationship_extractor = relationship_extractor
        self._graph_extraction_spec = graph_extraction_spec
        self._metadata_schema_version = metadata_schema_version
        self._now = now or (lambda: datetime.now(UTC).isoformat())
        self._graph_run_id_factory = graph_run_id_factory or (
            lambda: f"graph-run-{datetime.now(UTC).strftime('%Y%m%d%H%M%S%f')}"
        )
        self._graph_revision_factory = graph_revision_factory or (
            lambda: f"graph-{datetime.now(UTC).strftime('%Y%m%d%H%M%S%f')}"
        )

    def plan(
        self,
        *,
        requested_scope: QueryScope,
        actual_scopes: tuple[QueryScope, ...],
        full: bool = False,
        changes: GraphDocumentChanges | None = None,
    ) -> GraphIndexPlanReport:
        """Plan one graph run.

        With ``changes`` and a store that supports it, only the documents the changes touch are
        re-extracted (spec 2026-11-05 §4.3.3). Otherwise every chunk of every scope is.
        """
        _ensure_actual_scopes(actual_scopes)
        document_plan = self._document_plan(
            requested_scope=requested_scope, actual_scopes=actual_scopes, full=full, changes=changes
        )
        if document_plan is not None:
            return document_plan.report
        return self._whole_scope_plan(requested_scope=requested_scope, actual_scopes=actual_scopes, full=full)

    def _whole_scope_plan(
        self,
        *,
        requested_scope: QueryScope,
        actual_scopes: tuple[QueryScope, ...],
        full: bool,
    ) -> GraphIndexPlanReport:
        graph_run_id = self._graph_run_id_factory()
        graph_index_revision = self._graph_revision_factory()
        graph_health = self._graph_store.health()
        scope_desired = tuple(self._desired_for_scope(scope) for scope in actual_scopes)
        entity_records, entity_refs, entity_key_to_id = self._entity_records(
            occurrences=tuple(occurrence for desired in scope_desired for occurrence in desired.entity_occurrences),
            graph_index_revision=graph_index_revision,
        )
        relationship_records, relationship_refs = self._relationship_records(
            occurrences=tuple(
                occurrence for desired in scope_desired for occurrence in desired.relationship_occurrences
            ),
            entity_key_to_id=entity_key_to_id,
            graph_index_revision=graph_index_revision,
        )
        manifest = self._graph_store.current_manifest(actual_scopes)
        lineages_by_scope = {graph_scope_key(desired.scope): desired for desired in scope_desired}
        stale_scopes = _stale_revision_scopes(
            manifest=manifest,
            lineages_by_scope=lineages_by_scope,
            graph_store_schema_version=graph_health.schema_version,
            graph_extraction_spec=self._graph_extraction_spec,
        )
        entity_upserts, entity_stale_count = _entity_upserts(
            desired=entity_records,
            manifest=manifest,
            lineages_by_scope=lineages_by_scope,
            stale_scopes=stale_scopes,
            full=full,
        )
        relationship_upserts, relationship_stale_count = _relationship_upserts(
            desired=relationship_records,
            manifest=manifest,
            lineages_by_scope=lineages_by_scope,
            stale_scopes=stale_scopes,
            full=full,
        )
        entity_tombstones, relationship_tombstones = _tombstones(
            manifest=manifest,
            desired_entities=entity_records,
            desired_relationships=relationship_records,
            graph_run_id=graph_run_id,
            graph_index_revision=graph_index_revision,
            graph_extraction_spec=self._graph_extraction_spec,
            now=self._now(),
        )
        changed_scope_keys = _changed_scope_keys(
            actual_scopes=actual_scopes,
            entity_upserts=entity_upserts,
            relationship_upserts=relationship_upserts,
            entity_tombstones=entity_tombstones,
            relationship_tombstones=relationship_tombstones,
        )
        graph_revision_rows = tuple(
            _revision_row(
                desired=desired,
                graph_run_id=graph_run_id,
                graph_index_revision=graph_index_revision,
                graph_store_schema_version=graph_health.schema_version,
                graph_extraction_spec=self._graph_extraction_spec,
                entity_records=entity_records,
                relationship_records=relationship_records,
                stale_count=entity_stale_count + relationship_stale_count,
                tombstone_count=_scope_tombstone_count(
                    scope=desired.scope,
                    entity_tombstones=entity_tombstones,
                    relationship_tombstones=relationship_tombstones,
                ),
                updated_at=self._now(),
            )
            for desired in scope_desired
        )
        warnings = _warnings_for_unresolved_links(
            tuple(occurrence for desired in scope_desired for occurrence in desired.entity_occurrences)
        )
        plan = GraphReconcilePlan(
            requested_scope=requested_scope,
            actual_scopes=actual_scopes,
            graph_run_id=graph_run_id,
            entity_upserts=entity_upserts,
            relationship_upserts=relationship_upserts,
            evidence_ref_upserts=_unique_evidence_refs(entity_refs + relationship_refs),
            entity_tombstones=entity_tombstones,
            relationship_tombstones=relationship_tombstones,
            graph_revision_rows=graph_revision_rows,
            graph_extraction_spec=self._graph_extraction_spec,
            projection_cache_invalidations=tuple(
                f"graph-projection:{scope_key}" for scope_key in sorted(changed_scope_keys)
            ),
        )
        return GraphIndexPlanReport(
            reconcile_plan=plan,
            mode="full" if full else "incremental",
            stale_count=entity_stale_count + relationship_stale_count + len(stale_scopes),
            warnings=warnings,
        )

    def apply(
        self,
        *,
        requested_scope: QueryScope,
        actual_scopes: tuple[QueryScope, ...],
        full: bool = False,
        changes: GraphDocumentChanges | None = None,
    ) -> GraphIndexApplyResult:
        document_plan: _DocumentPlan | None = None
        try:
            _ensure_actual_scopes(actual_scopes)
            document_plan = self._document_plan(
                requested_scope=requested_scope, actual_scopes=actual_scopes, full=full, changes=changes
            )
            report = (
                document_plan.report
                if document_plan is not None
                else self._whole_scope_plan(requested_scope=requested_scope, actual_scopes=actual_scopes, full=full)
            )
        except (GraphIndexingError, GraphStoreError, GraphRecordInvalid) as exc:
            return GraphIndexApplyResult(
                reconcile_plan=None,
                apply_result=None,
                mode="full" if full else "incremental",
                stale_count=0,
                warnings=(),
                failed=True,
                error=str(exc),
            )
        try:
            if document_plan is not None and isinstance(self._graph_store, DocumentReconcileGraphStore):
                apply_result = self._graph_store.apply_owner_reconcile_plan(
                    report.reconcile_plan,
                    owners=document_plan.owners,
                    kept_evidence_ref_ids=document_plan.kept_evidence_ref_ids,
                )
            else:
                apply_result = self._graph_store.apply_reconcile_plan(report.reconcile_plan)
        except (GraphIndexingError, GraphStoreError, GraphRecordInvalid) as exc:
            return GraphIndexApplyResult(
                reconcile_plan=report.reconcile_plan,
                apply_result=None,
                mode=report.mode,
                stale_count=report.stale_count,
                warnings=report.warnings,
                failed=True,
                error=str(exc),
            )
        return GraphIndexApplyResult(
            reconcile_plan=report.reconcile_plan,
            apply_result=apply_result,
            mode=report.mode,
            stale_count=report.stale_count,
            warnings=report.warnings,
            failed=False,
            error=None,
        )

    def _desired_for_scope(self, scope: QueryScope) -> _ScopeDesired:
        source = self._scope_source(scope)
        entity_occurrences, relationship_occurrences = self._extract(source, source.chunks)
        return _ScopeDesired(
            scope=scope,
            chunks=source.chunks,
            documents=source.documents,
            entity_occurrences=entity_occurrences,
            relationship_occurrences=relationship_occurrences,
            metadata_index_revision=source.metadata_index_revision,
            parser_version=source.parser_version,
            chunker_version=source.chunker_version,
        )

    def _scope_source(self, scope: QueryScope) -> _ScopeSource:
        chunks = self._source_store.list_chunks(scope)
        documents_by_id: dict[str, DocumentSnapshot] = {}
        resolved: set[tuple[str, str]] = set()
        for chunk in chunks:
            if (chunk.vault_id, chunk.document_id) in resolved:
                continue
            resolved.add((chunk.vault_id, chunk.document_id))
            document = self._source_store.resolve_document(vault_id=chunk.vault_id, document_id=chunk.document_id)
            if document is not None:
                documents_by_id[document.document_id] = document
        documents = tuple(sorted(documents_by_id.values(), key=lambda item: (item.vault_id, item.path)))
        return _ScopeSource(
            scope=scope,
            chunks=chunks,
            documents_by_id=documents_by_id,
            documents=documents,
            context=GraphExtractionContext(scope=scope, current_documents=documents, source_store=self._source_store),
            metadata_index_revision=_revision_from_values(
                tuple(chunk.index_revision for chunk in chunks),
                fallback=f"empty:{self._metadata_schema_version}",
            ),
            parser_version=_revision_from_values(
                tuple(document.parser_version for document in documents),
                fallback="unknown",
            ),
            chunker_version=_revision_from_values(
                tuple(chunk.chunker_version for chunk in chunks),
                fallback="empty",
            ),
        )

    def _extract(
        self, source: _ScopeSource, chunks: Iterable[ChunkSnapshot]
    ) -> tuple[tuple[EntityOccurrence, ...], tuple[RelationshipOccurrence, ...]]:
        entity_occurrences: list[EntityOccurrence] = []
        relationship_occurrences: list[RelationshipOccurrence] = []
        for chunk in chunks:
            document = source.documents_by_id.get(chunk.document_id)
            entities = self._entity_extractor.extract(
                chunk=chunk,
                document=document,
                context=source.context,
                scope=source.scope,
                spec=self._graph_extraction_spec,
            )
            entity_occurrences.extend(entities)
            relationship_occurrences.extend(
                self._relationship_extractor.extract(
                    chunk=chunk,
                    document=document,
                    entities=entities,
                    context=source.context,
                    scope=source.scope,
                    spec=self._graph_extraction_spec,
                )
            )
        return tuple(entity_occurrences), tuple(relationship_occurrences)

    def _document_plan(
        self,
        *,
        requested_scope: QueryScope,
        actual_scopes: tuple[QueryScope, ...],
        full: bool,
        changes: GraphDocumentChanges | None,
    ) -> _DocumentPlan | None:
        """Plan from the changed documents (spec 2026-11-05 §4.3.3), or None to plan whole scopes.

        Whole scopes are planned for a full run, without ``changes``, for a store without document
        reconcile, and when a scope's graph does not show the metadata as it was before this run: no
        recorded revision, another graph schema or extraction spec, a metadata revision the graph never
        saw, or a document set that differs by more than this run's paths.
        """
        store = self._graph_store
        if full or changes is None or not isinstance(store, DocumentReconcileGraphStore):
            return None
        schema_version = store.health().schema_version
        recorded = {revision.actual_scope: revision for revision in store.latest_revisions(actual_scopes)}
        sources = tuple(self._scope_source(scope) for scope in actual_scopes)
        for source in sources:
            if not _graph_follows_metadata(
                store=store,
                source=source,
                revision=recorded.get(graph_scope_key(source.scope)),
                schema_version=schema_version,
                spec=self._graph_extraction_spec,
                changes=changes,
            ):
                return None
        graph_run_id = self._graph_run_id_factory()
        graph_index_revision = self._graph_revision_factory()
        now = self._now()
        rebuilds = tuple(
            self._rebuild_scope(
                store=store,
                source=source,
                changes=changes,
                graph_run_id=graph_run_id,
                graph_index_revision=graph_index_revision,
                now=now,
            )
            for source in sources
        )
        entity_upserts = tuple(
            sorted(
                (record for rebuild in rebuilds for record in rebuild.entity_records),
                key=lambda item: (item.vault_id, item.entity_id),
            )
        )
        relationship_upserts = tuple(
            sorted(
                (record for rebuild in rebuilds for record in rebuild.relationship_records),
                key=lambda item: (item.source_vault_id, item.relationship_id),
            )
        )
        entity_tombstones = tuple(tombstone for rebuild in rebuilds for tombstone in rebuild.entity_tombstones)
        relationship_tombstones = tuple(
            tombstone for rebuild in rebuilds for tombstone in rebuild.relationship_tombstones
        )
        changed_scope_keys = sorted(
            graph_scope_key(rebuild.source.scope)
            for rebuild in rebuilds
            if rebuild.entity_records
            or rebuild.relationship_records
            or rebuild.entity_tombstones
            or rebuild.relationship_tombstones
        )
        plan = GraphReconcilePlan(
            requested_scope=requested_scope,
            actual_scopes=actual_scopes,
            graph_run_id=graph_run_id,
            entity_upserts=entity_upserts,
            relationship_upserts=relationship_upserts,
            evidence_ref_upserts=tuple(ref for rebuild in rebuilds for ref in rebuild.evidence_ref_upserts),
            entity_tombstones=entity_tombstones,
            relationship_tombstones=relationship_tombstones,
            graph_revision_rows=tuple(
                GraphRevision(
                    graph_run_id=graph_run_id,
                    vault_id=rebuild.source.scope.vault_ids[0],
                    actual_scope=graph_scope_key(rebuild.source.scope),
                    graph_store_schema_version=schema_version,
                    graph_extraction_spec_version=self._graph_extraction_spec.spec_version,
                    graph_extraction_spec_digest=self._graph_extraction_spec.spec_digest,
                    graph_index_revision=graph_index_revision,
                    metadata_index_revision=rebuild.source.metadata_index_revision,
                    parser_version=rebuild.source.parser_version,
                    chunker_version=rebuild.source.chunker_version,
                    entity_count=rebuild.entity_count,
                    relationship_count=rebuild.relationship_count,
                    stale_count=0,
                    tombstone_count=len(rebuild.entity_tombstones) + len(rebuild.relationship_tombstones),
                    updated_at=self._now(),
                )
                for rebuild in rebuilds
            ),
            graph_extraction_spec=self._graph_extraction_spec,
            projection_cache_invalidations=tuple(f"graph-projection:{scope_key}" for scope_key in changed_scope_keys),
        )
        return _DocumentPlan(
            report=GraphIndexPlanReport(
                reconcile_plan=plan,
                mode="incremental",
                stale_count=0,
                warnings=tuple(sorted({warning for rebuild in rebuilds for warning in rebuild.warnings})),
            ),
            owners=tuple(sorted({owner for rebuild in rebuilds for owner in rebuild.owners})),
            kept_evidence_ref_ids=frozenset(
                ref.evidence_ref_id for rebuild in rebuilds for ref in rebuild.evidence_refs
            ),
        )

    def _rebuild_scope(
        self,
        *,
        store: DocumentReconcileGraphStore,
        source: _ScopeSource,
        changes: GraphDocumentChanges,
        graph_run_id: str,
        graph_index_revision: str,
        now: str,
    ) -> _ScopeRebuild:
        """Rebuild every entity and relationship that the changed documents had or now have evidence for.

        Re-extracted documents: the changed and deleted ones, the ones whose evidence names a changed
        document's entity (they link to it), and, when a path appears or disappears, the ones whose text
        or frontmatter contains its file name (a link may now resolve differently). A touched record is
        rebuilt from all its evidence, so the chunks of other documents that hold its evidence are
        extracted too, keeping only their occurrences of touched records. A touched record left with no
        evidence is tombstoned, as a full run does.
        """
        scope = source.scope
        vault_id = scope.vault_ids[0]
        scope_key = graph_scope_key(scope)
        paths = _reextracted_paths(store=store, source=source, touched=_touched_paths(scope, changes))
        old_owners: set[GraphOwner] = set()
        if paths:
            for owners in store.evidence_owners_by_path(vault_id=vault_id, paths=tuple(sorted(paths))).values():
                old_owners.update(owners)
        entity_occurrences, relationship_occurrences = self._extract(
            source, (chunk for chunk in source.chunks if chunk.path in paths)
        )
        key_to_id = _entity_ids(entity_occurrences)
        owners = frozenset(
            old_owners
            | {_entity_owner(occurrence, key_to_id) for occurrence in entity_occurrences}
            | {
                owner
                for occurrence in relationship_occurrences
                if (owner := _relationship_owner(occurrence, key_to_id)) is not None
            }
        )
        stored_refs = store.evidence_refs_for_owners(tuple(sorted(owners)))
        other_chunk_ids = {
            ref.chunk_id for ref in stored_refs if ref.evidence_vault_id == vault_id and ref.path not in paths
        }
        other_entities, other_relationships = self._extract(
            source,
            (chunk for chunk in source.chunks if chunk.chunk_id in other_chunk_ids and chunk.path not in paths),
        )
        key_to_id.update(_entity_ids(other_entities))
        warnings = _warnings_for_unresolved_links(entity_occurrences)
        entity_occurrences += tuple(
            occurrence for occurrence in other_entities if _entity_owner(occurrence, key_to_id) in owners
        )
        relationship_occurrences += tuple(
            occurrence for occurrence in other_relationships if _relationship_owner(occurrence, key_to_id) in owners
        )
        entity_records, entity_refs, record_key_to_id = self._entity_records(
            occurrences=entity_occurrences, graph_index_revision=graph_index_revision
        )
        relationship_records, relationship_refs = self._relationship_records(
            occurrences=relationship_occurrences,
            entity_key_to_id={**key_to_id, **record_key_to_id},
            graph_index_revision=graph_index_revision,
        )
        evidence_refs = _unique_evidence_refs(entity_refs + relationship_refs)
        stored_by_id = {ref.evidence_ref_id: ref for ref in stored_refs}
        desired = {("entity", record.vault_id, record.entity_id) for record in entity_records} | {
            ("relationship", record.source_vault_id, record.relationship_id) for record in relationship_records
        }
        statuses = store.owner_statuses(actual_scope=scope_key, owners=tuple(sorted(owners)))
        retired = {"entity": "tombstoned", "relationship": "deprecated"}
        tombstones = tuple(
            _tombstone(
                record_kind=owner[0],
                record_vault_id=owner[1],
                record_id=owner[2],
                actual_scope=scope_key,
                graph_run_id=graph_run_id,
                graph_index_revision=graph_index_revision,
                graph_extraction_spec=self._graph_extraction_spec,
                now=now,
            )
            for owner in sorted(owners - desired)
            if statuses.get(owner, retired[owner[0]]) != retired[owner[0]]
        )
        live = {owner for owner, status in statuses.items() if status != retired[owner[0]]}
        entity_total, relationship_total = store.scope_record_counts(actual_scope=scope_key)
        return _ScopeRebuild(
            source=source,
            owners=owners,
            entity_records=entity_records,
            relationship_records=relationship_records,
            evidence_refs=evidence_refs,
            evidence_ref_upserts=tuple(ref for ref in evidence_refs if stored_by_id.get(ref.evidence_ref_id) != ref),
            entity_tombstones=tuple(tombstone for tombstone in tombstones if tombstone.record_kind == "entity"),
            relationship_tombstones=tuple(
                tombstone for tombstone in tombstones if tombstone.record_kind == "relationship"
            ),
            entity_count=entity_total - sum(1 for owner in live if owner[0] == "entity") + len(entity_records),
            relationship_count=relationship_total
            - sum(1 for owner in live if owner[0] == "relationship")
            + len(relationship_records),
            warnings=warnings,
        )

    def _entity_records(
        self,
        *,
        occurrences: tuple[EntityOccurrence, ...],
        graph_index_revision: str,
    ) -> tuple[tuple[EntityRecord, ...], tuple[GraphEvidenceRef, ...], dict[tuple[str, str, str, str], str]]:
        grouped: dict[tuple[str, str, str, str], list[EntityOccurrence]] = {}
        for occurrence in occurrences:
            grouped.setdefault(entity_occurrence_key(occurrence), []).append(occurrence)
        records: list[EntityRecord] = []
        refs: list[GraphEvidenceRef] = []
        key_to_id: dict[tuple[str, str, str, str], str] = {}
        for key, values in sorted(grouped.items()):
            values = sorted(values, key=_entity_occurrence_sort_key)
            representative = max(values, key=lambda item: item.confidence)
            entity_id = stable_entity_id(
                vault_id=key[0],
                entity_type=key[1],
                normalized_name=key[2],
                canonical_path=key[3] or None,
            )
            key_to_id[key] = entity_id
            evidence_refs = tuple(
                _entity_evidence_ref(occurrence=occurrence, entity_id=entity_id) for occurrence in values
            )
            refs.extend(evidence_refs)
            records.append(
                EntityRecord(
                    vault_id=representative.vault_id,
                    entity_id=entity_id,
                    type=representative.entity_type,
                    name=representative.name,
                    normalized_name=representative.normalized_name,
                    aliases=tuple(sorted({alias for occurrence in values for alias in occurrence.aliases})),
                    canonical_path=representative.canonical_path,
                    evidence_refs=_unique_evidence_refs(evidence_refs),
                    confidence=max(occurrence.confidence for occurrence in values),
                    extraction_method=representative.extraction_method,
                    graph_extraction_spec_version=self._graph_extraction_spec.spec_version,
                    graph_extraction_spec_digest=self._graph_extraction_spec.spec_digest,
                    status="active",
                    created_at=self._now(),
                    updated_at=self._now(),
                    graph_index_revision=graph_index_revision,
                )
            )
        return tuple(records), tuple(refs), key_to_id

    def _relationship_records(
        self,
        *,
        occurrences: tuple[RelationshipOccurrence, ...],
        entity_key_to_id: dict[tuple[str, str, str, str], str],
        graph_index_revision: str,
    ) -> tuple[tuple[RelationshipRecord, ...], tuple[GraphEvidenceRef, ...]]:
        grouped: dict[tuple[str, str], list[RelationshipOccurrence]] = {}
        for occurrence in occurrences:
            if occurrence.source_vault_id != occurrence.target_vault_id:
                continue
            source_entity_id = entity_key_to_id.get(occurrence.source_entity_key)
            target_entity_id = entity_key_to_id.get(occurrence.target_entity_key)
            if source_entity_id is None or target_entity_id is None:
                continue
            relationship_id = stable_relationship_id(
                relationship_type=occurrence.relationship_type,
                source_vault_id=occurrence.source_vault_id,
                source_entity_id=source_entity_id,
                target_vault_id=occurrence.target_vault_id,
                target_entity_id=target_entity_id,
            )
            grouped.setdefault((occurrence.source_vault_id, relationship_id), []).append(occurrence)
        records: list[RelationshipRecord] = []
        refs: list[GraphEvidenceRef] = []
        for (source_vault_id, relationship_id), values in sorted(grouped.items()):
            values = sorted(values, key=_relationship_occurrence_sort_key)
            representative = max(values, key=lambda item: item.confidence)
            source_entity_id = entity_key_to_id[representative.source_entity_key]
            target_entity_id = entity_key_to_id[representative.target_entity_key]
            evidence_refs = tuple(
                _relationship_evidence_ref(occurrence=occurrence, relationship_id=relationship_id)
                for occurrence in values
            )
            refs.extend(evidence_refs)
            records.append(
                RelationshipRecord(
                    relationship_id=relationship_id,
                    type=representative.relationship_type,
                    source_vault_id=source_vault_id,
                    source_entity_id=source_entity_id,
                    target_vault_id=representative.target_vault_id,
                    target_entity_id=target_entity_id,
                    evidence_refs=_unique_evidence_refs(evidence_refs),
                    status=representative.status,
                    confidence=max(occurrence.confidence for occurrence in values),
                    extraction_method=representative.extraction_method,
                    graph_extraction_spec_version=self._graph_extraction_spec.spec_version,
                    graph_extraction_spec_digest=self._graph_extraction_spec.spec_digest,
                    created_at=self._now(),
                    updated_at=self._now(),
                    graph_index_revision=graph_index_revision,
                )
            )
        return tuple(records), tuple(refs)


def _entity_evidence_ref(*, occurrence: EntityOccurrence, entity_id: str) -> GraphEvidenceRef:
    return GraphEvidenceRef(
        evidence_ref_id=stable_evidence_ref_id(
            owner_kind="entity",
            owner_vault_id=occurrence.vault_id,
            owner_id=entity_id,
            evidence_vault_id=occurrence.evidence_vault_id,
            document_id=occurrence.document_id,
            chunk_id=occurrence.chunk_id,
            anchor=occurrence.anchor,
        ),
        owner_kind="entity",
        owner_vault_id=occurrence.vault_id,
        owner_id=entity_id,
        evidence_vault_id=occurrence.evidence_vault_id,
        document_id=occurrence.document_id,
        chunk_id=occurrence.chunk_id,
        content_hash=occurrence.content_hash,
        section=occurrence.section,
        anchor=occurrence.anchor,
        path=occurrence.path,
    )


def _relationship_evidence_ref(*, occurrence: RelationshipOccurrence, relationship_id: str) -> GraphEvidenceRef:
    return GraphEvidenceRef(
        evidence_ref_id=stable_evidence_ref_id(
            owner_kind="relationship",
            owner_vault_id=occurrence.source_vault_id,
            owner_id=relationship_id,
            evidence_vault_id=occurrence.evidence_vault_id,
            document_id=occurrence.document_id,
            chunk_id=occurrence.chunk_id,
            anchor=occurrence.anchor,
        ),
        owner_kind="relationship",
        owner_vault_id=occurrence.source_vault_id,
        owner_id=relationship_id,
        evidence_vault_id=occurrence.evidence_vault_id,
        document_id=occurrence.document_id,
        chunk_id=occurrence.chunk_id,
        content_hash=occurrence.content_hash,
        section=occurrence.section,
        anchor=occurrence.anchor,
        path=occurrence.path,
    )


def _entity_upserts(
    *,
    desired: tuple[EntityRecord, ...],
    manifest: GraphManifest,
    lineages_by_scope: dict[str, _ScopeDesired],
    stale_scopes: set[str],
    full: bool,
) -> tuple[tuple[EntityRecord, ...], int]:
    current = {(row.vault_id, row.entity_id): row for row in manifest.entity_rows}
    upserts: list[EntityRecord] = []
    stale_count = 0
    scope_by_vault_id = {
        desired_scope.scope.vault_ids[0]: graph_scope_key(desired_scope.scope)
        for desired_scope in lineages_by_scope.values()
    }
    for record in desired:
        row = current.get((record.vault_id, record.entity_id))
        scope_key = scope_by_vault_id[record.vault_id]
        stale = row is not None and (
            full
            or scope_key in stale_scopes
            or row.status != "active"
            or row.graph_extraction_spec_digest != record.graph_extraction_spec_digest
            or row.metadata_index_revision != lineages_by_scope[scope_key].metadata_index_revision
            or set(row.evidence_ref_ids) != {ref.evidence_ref_id for ref in record.evidence_refs}
            or set(row.evidence_content_hashes) != {ref.content_hash for ref in record.evidence_refs}
        )
        if row is None or stale:
            upserts.append(record)
        if stale:
            stale_count += 1
    return tuple(sorted(upserts, key=lambda item: (item.vault_id, item.entity_id))), stale_count


def _relationship_upserts(
    *,
    desired: tuple[RelationshipRecord, ...],
    manifest: GraphManifest,
    lineages_by_scope: dict[str, _ScopeDesired],
    stale_scopes: set[str],
    full: bool,
) -> tuple[tuple[RelationshipRecord, ...], int]:
    current = {(row.source_vault_id, row.relationship_id): row for row in manifest.relationship_rows}
    upserts: list[RelationshipRecord] = []
    stale_count = 0
    scope_by_vault_id = {
        desired_scope.scope.vault_ids[0]: graph_scope_key(desired_scope.scope)
        for desired_scope in lineages_by_scope.values()
    }
    for record in desired:
        row = current.get((record.source_vault_id, record.relationship_id))
        scope_key = scope_by_vault_id[record.source_vault_id]
        stale = row is not None and (
            full
            or scope_key in stale_scopes
            or row.status != record.status
            or row.type != record.type
            or row.source_entity_id != record.source_entity_id
            or row.target_vault_id != record.target_vault_id
            or row.target_entity_id != record.target_entity_id
            or row.graph_extraction_spec_digest != record.graph_extraction_spec_digest
            or row.metadata_index_revision != lineages_by_scope[scope_key].metadata_index_revision
            or set(row.evidence_ref_ids) != {ref.evidence_ref_id for ref in record.evidence_refs}
            or set(row.evidence_content_hashes) != {ref.content_hash for ref in record.evidence_refs}
        )
        if row is None or stale:
            upserts.append(record)
        if stale:
            stale_count += 1
    return tuple(sorted(upserts, key=lambda item: (item.source_vault_id, item.relationship_id))), stale_count


def _tombstones(
    *,
    manifest: GraphManifest,
    desired_entities: tuple[EntityRecord, ...],
    desired_relationships: tuple[RelationshipRecord, ...],
    graph_run_id: str,
    graph_index_revision: str,
    graph_extraction_spec: GraphExtractionSpec,
    now: str,
) -> tuple[tuple[GraphTombstone, ...], tuple[GraphTombstone, ...]]:
    desired_entity_keys = {(record.vault_id, record.entity_id) for record in desired_entities}
    desired_relationship_keys = {(record.source_vault_id, record.relationship_id) for record in desired_relationships}
    scope_by_vault_id = {scope.vault_ids[0]: graph_scope_key(scope) for scope in manifest.actual_scopes}
    entity_tombstones = tuple(
        _tombstone(
            record_kind="entity",
            record_vault_id=row.vault_id,
            record_id=row.entity_id,
            actual_scope=scope_by_vault_id[row.vault_id],
            graph_run_id=graph_run_id,
            graph_index_revision=graph_index_revision,
            graph_extraction_spec=graph_extraction_spec,
            now=now,
        )
        for row in manifest.entity_rows
        if row.status != "tombstoned" and (row.vault_id, row.entity_id) not in desired_entity_keys
    )
    relationship_tombstones = tuple(
        _tombstone(
            record_kind="relationship",
            record_vault_id=row.source_vault_id,
            record_id=row.relationship_id,
            actual_scope=scope_by_vault_id[row.source_vault_id],
            graph_run_id=graph_run_id,
            graph_index_revision=graph_index_revision,
            graph_extraction_spec=graph_extraction_spec,
            now=now,
        )
        for row in manifest.relationship_rows
        if row.status != "deprecated" and (row.source_vault_id, row.relationship_id) not in desired_relationship_keys
    )
    return entity_tombstones, relationship_tombstones


def _tombstone(
    *,
    record_kind: str,
    record_vault_id: str,
    record_id: str,
    actual_scope: str,
    graph_run_id: str,
    graph_index_revision: str,
    graph_extraction_spec: GraphExtractionSpec,
    now: str,
) -> GraphTombstone:
    return GraphTombstone(
        tombstone_id=stable_graph_tombstone_id(
            record_kind=record_kind,
            record_vault_id=record_vault_id,
            record_id=record_id,
            actual_scope=actual_scope,
        ),
        record_kind=record_kind,
        record_vault_id=record_vault_id,
        record_id=record_id,
        actual_scope=actual_scope,
        reason="missing_from_scope",
        graph_run_id=graph_run_id,
        graph_index_revision=graph_index_revision,
        graph_extraction_spec_version=graph_extraction_spec.spec_version,
        graph_extraction_spec_digest=graph_extraction_spec.spec_digest,
        tombstoned_at=now,
    )


def _revision_row(
    *,
    desired: _ScopeDesired,
    graph_run_id: str,
    graph_index_revision: str,
    graph_store_schema_version: str,
    graph_extraction_spec: GraphExtractionSpec,
    entity_records: tuple[EntityRecord, ...],
    relationship_records: tuple[RelationshipRecord, ...],
    stale_count: int,
    tombstone_count: int,
    updated_at: str,
) -> GraphRevision:
    vault_id = desired.scope.vault_ids[0]
    return GraphRevision(
        graph_run_id=graph_run_id,
        vault_id=vault_id,
        actual_scope=graph_scope_key(desired.scope),
        graph_store_schema_version=graph_store_schema_version,
        graph_extraction_spec_version=graph_extraction_spec.spec_version,
        graph_extraction_spec_digest=graph_extraction_spec.spec_digest,
        graph_index_revision=graph_index_revision,
        metadata_index_revision=desired.metadata_index_revision,
        parser_version=desired.parser_version,
        chunker_version=desired.chunker_version,
        entity_count=sum(1 for record in entity_records if record.vault_id == vault_id),
        relationship_count=sum(1 for record in relationship_records if record.source_vault_id == vault_id),
        stale_count=stale_count,
        tombstone_count=tombstone_count,
        updated_at=updated_at,
    )


def _stale_revision_scopes(
    *,
    manifest: GraphManifest,
    lineages_by_scope: dict[str, _ScopeDesired],
    graph_store_schema_version: str,
    graph_extraction_spec: GraphExtractionSpec,
) -> set[str]:
    revisions_by_scope = {revision.actual_scope: revision for revision in manifest.revision_rows}
    stale_scopes: set[str] = set()
    for scope_key, desired in lineages_by_scope.items():
        revision = revisions_by_scope.get(scope_key)
        if revision is None:
            continue
        if (
            revision.graph_store_schema_version != graph_store_schema_version
            or revision.graph_extraction_spec_digest != graph_extraction_spec.spec_digest
            or revision.metadata_index_revision != desired.metadata_index_revision
            or revision.parser_version != desired.parser_version
            or revision.chunker_version != desired.chunker_version
        ):
            stale_scopes.add(scope_key)
    return stale_scopes


def _changed_scope_keys(
    *,
    actual_scopes: tuple[QueryScope, ...],
    entity_upserts: tuple[EntityRecord, ...],
    relationship_upserts: tuple[RelationshipRecord, ...],
    entity_tombstones: tuple[GraphTombstone, ...],
    relationship_tombstones: tuple[GraphTombstone, ...],
) -> set[str]:
    scope_by_vault_id = {scope.vault_ids[0]: graph_scope_key(scope) for scope in actual_scopes}
    keys = {scope_by_vault_id[record.vault_id] for record in entity_upserts}
    keys.update(scope_by_vault_id[record.source_vault_id] for record in relationship_upserts)
    keys.update(tombstone.actual_scope for tombstone in entity_tombstones + relationship_tombstones)
    return keys


def _scope_tombstone_count(
    *,
    scope: QueryScope,
    entity_tombstones: tuple[GraphTombstone, ...],
    relationship_tombstones: tuple[GraphTombstone, ...],
) -> int:
    scope_key = graph_scope_key(scope)
    return sum(1 for tombstone in entity_tombstones + relationship_tombstones if tombstone.actual_scope == scope_key)


def _warnings_for_unresolved_links(occurrences: tuple[EntityOccurrence, ...]) -> tuple[str, ...]:
    warnings = {
        (
            "unresolved_local_link",
            occurrence.vault_id,
            occurrence.path,
            occurrence.chunk_id,
            occurrence.name,
        )
        for occurrence in occurrences
        if occurrence.extraction_method == "unresolved-local-link-concept-v1"
    }
    return tuple(
        f"{code}:{vault_id}:{path}:{chunk_id}:{message}" for code, vault_id, path, chunk_id, message in sorted(warnings)
    )


def _unique_evidence_refs(refs: tuple[GraphEvidenceRef, ...]) -> tuple[GraphEvidenceRef, ...]:
    return tuple({ref.evidence_ref_id: ref for ref in refs}.values())


def _revision_from_values(values: tuple[str | None, ...], *, fallback: str) -> str:
    revisions = tuple(sorted({value for value in values if value}))
    return ",".join(revisions) if revisions else fallback


def _ensure_actual_scopes(scopes: tuple[QueryScope, ...]) -> None:
    for scope in scopes:
        if len(scope.vault_ids) != 1:
            raise GraphIndexingError("GraphIndexer requires per-Vault actual scopes")


def _entity_occurrence_sort_key(occurrence: EntityOccurrence) -> tuple[str, str, str, str, str]:
    return (
        occurrence.vault_id,
        occurrence.path,
        occurrence.chunk_id,
        occurrence.extraction_method,
        occurrence.name,
    )


def _relationship_occurrence_sort_key(occurrence: RelationshipOccurrence) -> tuple[str, str, str, str]:
    return (
        occurrence.source_vault_id,
        occurrence.path,
        occurrence.chunk_id,
        occurrence.extraction_method,
    )


def _graph_follows_metadata(
    *,
    store: DocumentReconcileGraphStore,
    source: _ScopeSource,
    revision: GraphRevision | None,
    schema_version: str,
    spec: GraphExtractionSpec,
    changes: GraphDocumentChanges,
) -> bool:
    """Whether the scope's graph shows the metadata as it was before this run.

    Every metadata revision of the current chunks except this run's must be one the graph recorded,
    and the documents with graph evidence must differ from the current documents only by this run's
    paths. A metadata run that never reached the graph fails one of the two.
    """
    if revision is None:
        return False
    if revision.graph_store_schema_version != schema_version or revision.graph_extraction_spec_digest != (
        spec.spec_digest
    ):
        return False
    current_revisions = {chunk.index_revision for chunk in source.chunks if chunk.index_revision}
    if not current_revisions - {changes.index_revision} <= set(revision.metadata_index_revision.split(",")):
        return False
    scope = source.scope
    graph_paths = {path for path in store.evidence_paths(vault_id=scope.vault_ids[0]) if _path_in_scope(path, scope)}
    return graph_paths ^ set(source.context.current_document_paths) <= _touched_paths(scope, changes)


def _touched_paths(scope: QueryScope, changes: GraphDocumentChanges) -> set[str]:
    vault_id = scope.vault_ids[0]
    return {
        path
        for key_vault_id, path in changes.changed_paths + changes.deleted_paths
        if key_vault_id == vault_id and _path_in_scope(path, scope)
    }


def _reextracted_paths(*, store: DocumentReconcileGraphStore, source: _ScopeSource, touched: set[str]) -> set[str]:
    """``touched`` plus the documents whose extraction depends on them.

    A document that links to a touched one holds evidence for that document's entity. A document
    that names the file of a path that appeared or disappeared may now resolve its link differently;
    a link resolves by exact path or by file name, so its text or frontmatter contains the file name.
    """
    if not touched:
        return set()
    scope = source.scope
    vault_id = scope.vault_ids[0]
    paths = set(touched)
    targets = store.document_entity_owners(vault_id=vault_id, canonical_paths=tuple(sorted(touched)))
    paths.update(
        ref.path
        for ref in store.evidence_refs_for_owners(tuple(sorted(targets)))
        if ref.path is not None and ref.evidence_vault_id == vault_id
    )
    had_evidence = store.evidence_owners_by_path(vault_id=vault_id, paths=tuple(sorted(touched)))
    current = set(source.context.current_document_paths)
    moved = {path for path in touched if (path in had_evidence) != (path in current)}
    names = {PurePosixPath(path).name.removesuffix(".md") for path in moved}
    if names:
        paths.update(chunk.path for chunk in source.chunks if any(name in chunk.text for name in names))
        paths.update(
            document.path for document in source.documents if any(name in str(document.frontmatter) for name in names)
        )
    return {path for path in paths if _path_in_scope(path, scope)}


def _entity_id(key: tuple[str, str, str, str]) -> str:
    return stable_entity_id(vault_id=key[0], entity_type=key[1], normalized_name=key[2], canonical_path=key[3] or None)


def _entity_ids(occurrences: Iterable[EntityOccurrence]) -> dict[tuple[str, str, str, str], str]:
    return {key: _entity_id(key) for key in {entity_occurrence_key(occurrence) for occurrence in occurrences}}


def _entity_owner(occurrence: EntityOccurrence, key_to_id: dict[tuple[str, str, str, str], str]) -> GraphOwner:
    return ("entity", occurrence.vault_id, key_to_id[entity_occurrence_key(occurrence)])


def _relationship_owner(
    occurrence: RelationshipOccurrence, key_to_id: dict[tuple[str, str, str, str], str]
) -> GraphOwner | None:
    """The relationship an occurrence becomes, or None when GraphIndexer drops it."""
    if occurrence.source_vault_id != occurrence.target_vault_id:
        return None
    source_entity_id = key_to_id.get(occurrence.source_entity_key)
    target_entity_id = key_to_id.get(occurrence.target_entity_key)
    if source_entity_id is None or target_entity_id is None:
        return None
    return (
        "relationship",
        occurrence.source_vault_id,
        stable_relationship_id(
            relationship_type=occurrence.relationship_type,
            source_vault_id=occurrence.source_vault_id,
            source_entity_id=source_entity_id,
            target_vault_id=occurrence.target_vault_id,
            target_entity_id=target_entity_id,
        ),
    )


def _path_in_scope(path: str, scope: QueryScope) -> bool:
    return any(path == content_scope or path.startswith(f"{content_scope}/") for content_scope in scope.content_scopes)
