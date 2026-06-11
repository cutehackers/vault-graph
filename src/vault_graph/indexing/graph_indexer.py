from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime

from vault_graph.errors import GraphIndexingError, GraphRecordInvalid, GraphStoreError
from vault_graph.extraction.entity_extractor import EntityExtractor
from vault_graph.extraction.graph_occurrences import EntityOccurrence, RelationshipOccurrence, entity_occurrence_key
from vault_graph.extraction.graph_source_store import GraphExtractionContext, GraphSourceStore
from vault_graph.extraction.relationship_extractor import RelationshipExtractor
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
from vault_graph.graph.graph_identity import (
    graph_scope_key,
    stable_entity_id,
    stable_evidence_ref_id,
    stable_graph_tombstone_id,
    stable_relationship_id,
)
from vault_graph.ingestion.document_normalizer import ChunkSnapshot, DocumentSnapshot
from vault_graph.ingestion.vault_catalog import QueryScope
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
class _ScopeDesired:
    scope: QueryScope
    chunks: tuple[ChunkSnapshot, ...]
    documents: tuple[DocumentSnapshot, ...]
    entity_occurrences: tuple[EntityOccurrence, ...]
    relationship_occurrences: tuple[RelationshipOccurrence, ...]
    metadata_index_revision: str
    parser_version: str
    chunker_version: str


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
    ) -> GraphIndexPlanReport:
        _ensure_actual_scopes(actual_scopes)
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
    ) -> GraphIndexApplyResult:
        try:
            report = self.plan(requested_scope=requested_scope, actual_scopes=actual_scopes, full=full)
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
        chunks = self._source_store.list_chunks(scope)
        documents_by_id = {
            document.document_id: document
            for chunk in chunks
            if (
                document := self._source_store.resolve_document(
                    vault_id=chunk.vault_id,
                    document_id=chunk.document_id,
                )
            )
            is not None
        }
        documents = tuple(sorted(documents_by_id.values(), key=lambda item: (item.vault_id, item.path)))
        context = GraphExtractionContext(scope=scope, current_documents=documents, source_store=self._source_store)
        entity_occurrences: list[EntityOccurrence] = []
        relationship_occurrences: list[RelationshipOccurrence] = []
        for chunk in chunks:
            document = documents_by_id.get(chunk.document_id)
            entities = self._entity_extractor.extract(
                chunk=chunk,
                document=document,
                context=context,
                scope=scope,
                spec=self._graph_extraction_spec,
            )
            entity_occurrences.extend(entities)
            relationship_occurrences.extend(
                self._relationship_extractor.extract(
                    chunk=chunk,
                    document=document,
                    entities=entities,
                    context=context,
                    scope=scope,
                    spec=self._graph_extraction_spec,
                )
            )
        return _ScopeDesired(
            scope=scope,
            chunks=chunks,
            documents=documents,
            entity_occurrences=tuple(entity_occurrences),
            relationship_occurrences=tuple(relationship_occurrences),
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
        excerpt=occurrence.excerpt,
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
        excerpt=occurrence.excerpt,
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
    desired_relationship_keys = {
        (record.source_vault_id, record.relationship_id) for record in desired_relationships
    }
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
        f"{code}:{vault_id}:{path}:{chunk_id}:{message}"
        for code, vault_id, path, chunk_id, message in sorted(warnings)
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
