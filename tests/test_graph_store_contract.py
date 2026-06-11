from collections.abc import Callable
from pathlib import Path

import pytest

from tests.fakes.in_memory_graph_store import InMemoryGraphStore
from vault_graph.errors import GraphReadOnlyViolation, GraphStoreError
from vault_graph.graph.graph_contracts import (
    EntityRecord,
    GraphEvidenceRef,
    GraphReconcilePlan,
    GraphRevision,
    GraphTombstone,
    RelationshipRecord,
    current_graph_extraction_spec,
)
from vault_graph.graph.graph_identity import (
    graph_scope_key,
    stable_entity_id,
    stable_evidence_ref_id,
    stable_graph_tombstone_id,
    stable_relationship_id,
)
from vault_graph.ingestion.vault_catalog import QueryScope
from vault_graph.storage.interfaces.graph_store import GraphEntityIdentity, GraphRelationshipIdentity, GraphStore
from vault_graph.storage.local.sqlite_graph_store import SQLiteGraphStore


def make_entity(
    vault_id: str,
    *,
    name: str = "GraphRAG",
    document_id: str | None = None,
    chunk_id: str | None = None,
    content_hash: str | None = None,
    path: str = "wiki/graphrag.md",
) -> EntityRecord:
    spec = current_graph_extraction_spec()
    entity_id = stable_entity_id(
        vault_id=vault_id,
        entity_type="concept",
        normalized_name=name.casefold(),
        canonical_path=path,
    )
    resolved_document_id = document_id or f"{vault_id}-doc"
    resolved_chunk_id = chunk_id or f"{vault_id}-chunk"
    resolved_content_hash = content_hash or f"{vault_id}-hash"
    evidence = GraphEvidenceRef(
        evidence_ref_id=stable_evidence_ref_id(
            owner_kind="entity",
            owner_vault_id=vault_id,
            owner_id=entity_id,
            evidence_vault_id=vault_id,
            document_id=resolved_document_id,
            chunk_id=resolved_chunk_id,
            anchor="graphrag",
        ),
        owner_kind="entity",
        owner_vault_id=vault_id,
        owner_id=entity_id,
        evidence_vault_id=vault_id,
        document_id=resolved_document_id,
        chunk_id=resolved_chunk_id,
        content_hash=resolved_content_hash,
        section="GraphRAG",
        anchor="graphrag",
        path=path,
        excerpt="GraphRAG evidence",
    )
    return EntityRecord(
        vault_id=vault_id,
        entity_id=entity_id,
        type="concept",
        name=name,
        normalized_name=name.casefold(),
        aliases=("Graph RAG",),
        canonical_path=path,
        evidence_refs=(evidence,),
        confidence=0.9,
        extraction_method="test",
        graph_extraction_spec_version=spec.spec_version,
        graph_extraction_spec_digest=spec.spec_digest,
        status="active",
        created_at="2026-06-10T00:00:00+00:00",
        updated_at="2026-06-10T00:00:00+00:00",
        graph_index_revision="graph-1",
    )


def make_relationship(source: EntityRecord, target: EntityRecord) -> RelationshipRecord:
    spec = current_graph_extraction_spec()
    relationship_id = stable_relationship_id(
        relationship_type="depends_on",
        source_vault_id=source.vault_id,
        source_entity_id=source.entity_id,
        target_vault_id=target.vault_id,
        target_entity_id=target.entity_id,
    )
    evidence = GraphEvidenceRef(
        evidence_ref_id=stable_evidence_ref_id(
            owner_kind="relationship",
            owner_vault_id=source.vault_id,
            owner_id=relationship_id,
            evidence_vault_id=source.vault_id,
            document_id=f"{source.vault_id}-doc",
            chunk_id=f"{source.vault_id}-chunk",
            anchor="dependency",
        ),
        owner_kind="relationship",
        owner_vault_id=source.vault_id,
        owner_id=relationship_id,
        evidence_vault_id=source.vault_id,
        document_id=f"{source.vault_id}-doc",
        chunk_id=f"{source.vault_id}-chunk",
        content_hash=f"{source.vault_id}-hash",
        section="Dependency",
        anchor="dependency",
        path="wiki/graphrag.md",
        excerpt="Dependency evidence",
    )
    return RelationshipRecord(
        relationship_id=relationship_id,
        type="depends_on",
        source_vault_id=source.vault_id,
        source_entity_id=source.entity_id,
        target_vault_id=target.vault_id,
        target_entity_id=target.entity_id,
        evidence_refs=(evidence,),
        status="stated",
        confidence=0.8,
        extraction_method="test",
        graph_extraction_spec_version=spec.spec_version,
        graph_extraction_spec_digest=spec.spec_digest,
        created_at="2026-06-10T00:00:00+00:00",
        updated_at="2026-06-10T00:00:00+00:00",
        graph_index_revision="graph-1",
    )


def make_revision(scope: QueryScope, *, entity_count: int, relationship_count: int) -> GraphRevision:
    spec = current_graph_extraction_spec()
    return GraphRevision(
        graph_run_id="graph-run-1",
        vault_id=scope.vault_ids[0],
        actual_scope=graph_scope_key(scope),
        graph_store_schema_version="memory-graph-v1",
        graph_extraction_spec_version=spec.spec_version,
        graph_extraction_spec_digest=spec.spec_digest,
        graph_index_revision="graph-1",
        metadata_index_revision="metadata-1",
        parser_version="markdown-frontmatter-v1",
        chunker_version="heading-section-v1",
        entity_count=entity_count,
        relationship_count=relationship_count,
        stale_count=0,
        tombstone_count=0,
        updated_at="2026-06-10T00:00:00+00:00",
    )


def make_plan(
    *,
    entities: tuple[EntityRecord, ...],
    relationships: tuple[RelationshipRecord, ...],
    scope: QueryScope | None = None,
) -> GraphReconcilePlan:
    resolved_scope = scope or _scope_for_records(entities=entities, relationships=relationships)
    evidence_refs = tuple(ref for entity in entities for ref in entity.evidence_refs) + tuple(
        ref for relationship in relationships for ref in relationship.evidence_refs
    )
    return GraphReconcilePlan(
        requested_scope=resolved_scope,
        actual_scopes=(resolved_scope,),
        graph_run_id="graph-run-1",
        entity_upserts=entities,
        relationship_upserts=relationships,
        evidence_ref_upserts=evidence_refs,
        entity_tombstones=(),
        relationship_tombstones=(),
        graph_revision_rows=(
            make_revision(resolved_scope, entity_count=len(entities), relationship_count=len(relationships)),
        ),
        graph_extraction_spec=current_graph_extraction_spec(),
        projection_cache_invalidations=(),
    )


def _scope_for_records(
    *,
    entities: tuple[EntityRecord, ...],
    relationships: tuple[RelationshipRecord, ...],
) -> QueryScope:
    if entities:
        return QueryScope(vault_ids=(entities[0].vault_id,), content_scopes=("wiki",))
    if relationships:
        return QueryScope(vault_ids=(relationships[0].source_vault_id,), content_scopes=("wiki",))
    return QueryScope(vault_ids=("default",), content_scopes=("wiki",))


def graph_store_contract(factory: Callable[[], GraphStore]) -> None:
    store = factory()
    source = make_entity("default")
    target = make_entity("default", name="Context Pack")
    relationship = make_relationship(source, target)
    result = store.apply_reconcile_plan(make_plan(entities=(source, target), relationships=(relationship,)))

    assert result.applied_entity_upsert_count == 2
    assert result.applied_relationship_upsert_count == 1
    assert result.applied_evidence_ref_upsert_count == 3
    assert store.get_entity(vault_id="default", entity_id=source.entity_id) == source
    assert (
        store.get_relationship(source_vault_id="default", relationship_id=relationship.relationship_id)
        == relationship
    )
    assert store.resolve_entities((GraphEntityIdentity("default", source.entity_id),)) == (source,)
    assert store.resolve_relationships((GraphRelationshipIdentity("default", relationship.relationship_id),)) == (
        relationship,
    )
    manifest = store.current_manifest((QueryScope(vault_ids=("default",), content_scopes=("wiki",)),))
    assert tuple(row.entity_id for row in manifest.entity_rows) == (target.entity_id, source.entity_id)
    assert tuple(row.relationship_id for row in manifest.relationship_rows) == (relationship.relationship_id,)
    assert len(manifest.evidence_rows) == 3
    assert {row.metadata_index_revision for row in manifest.entity_rows} == {"metadata-1"}
    assert {row.graph_index_revision for row in manifest.relationship_rows} == {"graph-1"}
    assert {row.graph_extraction_spec_digest for row in manifest.entity_rows} == {
        current_graph_extraction_spec().spec_digest,
    }
    assert {row.content_hash for row in manifest.evidence_rows} == {"default-hash"}
    assert manifest.relationship_rows[0].source_vault_id == "default"
    assert manifest.relationship_rows[0].target_vault_id == "default"
    assert (
        store.latest_revisions((QueryScope(vault_ids=("default",), content_scopes=("wiki",)),))[0].graph_index_revision
        == "graph-1"
    )


def graph_store_multi_scope_contract(factory: Callable[[], GraphStore]) -> None:
    store = factory()
    first_scope = QueryScope(vault_ids=("first",), content_scopes=("wiki",))
    second_scope = QueryScope(vault_ids=("second",), content_scopes=("wiki",))
    first = make_entity("first", name="Shared")
    second = make_entity("second", name="Shared")
    plan = GraphReconcilePlan(
        requested_scope=QueryScope(vault_ids=("first", "second"), content_scopes=("wiki",)),
        actual_scopes=(first_scope, second_scope),
        graph_run_id="graph-run-1",
        entity_upserts=(first, second),
        relationship_upserts=(),
        evidence_ref_upserts=first.evidence_refs + second.evidence_refs,
        entity_tombstones=(),
        relationship_tombstones=(),
        graph_revision_rows=(
            make_revision(first_scope, entity_count=1, relationship_count=0),
            make_revision(second_scope, entity_count=1, relationship_count=0),
        ),
        graph_extraction_spec=current_graph_extraction_spec(),
        projection_cache_invalidations=(),
    )

    store.apply_reconcile_plan(plan)

    first_manifest = store.current_manifest((first_scope,))
    second_manifest = store.current_manifest((second_scope,))

    assert tuple(row.vault_id for row in first_manifest.entity_rows) == ("first",)
    assert tuple(row.vault_id for row in second_manifest.entity_rows) == ("second",)


def test_in_memory_graph_store_satisfies_contract() -> None:
    graph_store_contract(lambda: InMemoryGraphStore())


def test_in_memory_graph_store_scopes_multi_scope_records() -> None:
    graph_store_multi_scope_contract(lambda: InMemoryGraphStore())


def test_sqlite_graph_store_scopes_multi_scope_records(tmp_path: Path) -> None:
    graph_store_multi_scope_contract(lambda: SQLiteGraphStore.open_writable(tmp_path / "graph.sqlite3"))


def test_read_only_graph_store_rejects_apply() -> None:
    store = InMemoryGraphStore(read_only=True)
    source = make_entity("default")

    with pytest.raises(GraphReadOnlyViolation):
        store.apply_reconcile_plan(make_plan(entities=(source,), relationships=()))


def test_current_manifest_rejects_global_all_vault_scope() -> None:
    store = InMemoryGraphStore()

    with pytest.raises(GraphStoreError, match="per-Vault actual scopes"):
        store.current_manifest((QueryScope(vault_ids=("first", "second"), content_scopes=("wiki",)),))


def test_tombstones_are_scoped_records() -> None:
    store = InMemoryGraphStore()
    source = make_entity("default")
    scope = QueryScope(vault_ids=("default",), content_scopes=("wiki",))
    spec = current_graph_extraction_spec()
    tombstone = GraphTombstone(
        tombstone_id=stable_graph_tombstone_id(
            record_kind="entity",
            record_vault_id="default",
            record_id=source.entity_id,
            actual_scope=graph_scope_key(scope),
        ),
        record_kind="entity",
        record_vault_id="default",
        record_id=source.entity_id,
        actual_scope=graph_scope_key(scope),
        reason="missing_from_scope",
        graph_run_id="graph-run-2",
        graph_index_revision="graph-2",
        graph_extraction_spec_version=spec.spec_version,
        graph_extraction_spec_digest=spec.spec_digest,
        tombstoned_at="2026-06-10T00:01:00+00:00",
    )
    plan = GraphReconcilePlan(
        requested_scope=scope,
        actual_scopes=(scope,),
        graph_run_id="graph-run-2",
        entity_upserts=(),
        relationship_upserts=(),
        evidence_ref_upserts=(),
        entity_tombstones=(tombstone,),
        relationship_tombstones=(),
        graph_revision_rows=(make_revision(scope, entity_count=0, relationship_count=0),),
        graph_extraction_spec=spec,
        projection_cache_invalidations=(),
    )

    result = store.apply_reconcile_plan(plan)
    repeat = store.apply_reconcile_plan(plan)

    assert result.applied_tombstone_count == 1
    assert repeat.applied_tombstone_count == 1
    assert store.current_manifest((scope,)).tombstone_rows[0].record_vault_id == "default"
    assert len(store.current_manifest((scope,)).tombstone_rows) == 1


def tombstone_idempotence_contract(factory: Callable[[], GraphStore]) -> None:
    store = factory()
    source = make_entity("default")
    scope = QueryScope(vault_ids=("default",), content_scopes=("wiki",))
    spec = current_graph_extraction_spec()
    first = GraphTombstone(
        tombstone_id="first-tombstone-id",
        record_kind="entity",
        record_vault_id="default",
        record_id=source.entity_id,
        actual_scope=graph_scope_key(scope),
        reason="missing_from_scope",
        graph_run_id="graph-run-2",
        graph_index_revision="graph-2",
        graph_extraction_spec_version=spec.spec_version,
        graph_extraction_spec_digest=spec.spec_digest,
        tombstoned_at="2026-06-10T00:01:00+00:00",
    )
    second = GraphTombstone(
        tombstone_id="second-tombstone-id",
        record_kind="entity",
        record_vault_id="default",
        record_id=source.entity_id,
        actual_scope=graph_scope_key(scope),
        reason="still_missing_from_scope",
        graph_run_id="graph-run-3",
        graph_index_revision="graph-3",
        graph_extraction_spec_version=spec.spec_version,
        graph_extraction_spec_digest=spec.spec_digest,
        tombstoned_at="2026-06-10T00:02:00+00:00",
    )
    for tombstone in (first, second):
        store.apply_reconcile_plan(
            GraphReconcilePlan(
                requested_scope=scope,
                actual_scopes=(scope,),
                graph_run_id=tombstone.graph_run_id,
                entity_upserts=(),
                relationship_upserts=(),
                evidence_ref_upserts=(),
                entity_tombstones=(tombstone,),
                relationship_tombstones=(),
                graph_revision_rows=(make_revision(scope, entity_count=0, relationship_count=0),),
                graph_extraction_spec=spec,
                projection_cache_invalidations=(),
            )
        )

    manifest = store.current_manifest((scope,))

    assert tuple(row.tombstone_id for row in manifest.tombstone_rows) == ("second-tombstone-id",)


def test_in_memory_tombstones_are_latest_per_record_scope() -> None:
    tombstone_idempotence_contract(lambda: InMemoryGraphStore())


def test_sqlite_tombstones_are_latest_per_record_scope(tmp_path: Path) -> None:
    tombstone_idempotence_contract(lambda: SQLiteGraphStore.open_writable(tmp_path / "graph.sqlite3"))


def tombstone_repair_contract(factory: Callable[[], GraphStore]) -> None:
    store = factory()
    scope = QueryScope(vault_ids=("default",), content_scopes=("wiki",))
    source = make_entity("default")
    target = make_entity("default", name="Target")
    relationship = make_relationship(source, target)
    spec = current_graph_extraction_spec()
    entity_tombstone = GraphTombstone(
        tombstone_id=stable_graph_tombstone_id(
            record_kind="entity",
            record_vault_id="default",
            record_id=source.entity_id,
            actual_scope=graph_scope_key(scope),
        ),
        record_kind="entity",
        record_vault_id="default",
        record_id=source.entity_id,
        actual_scope=graph_scope_key(scope),
        reason="missing_from_scope",
        graph_run_id="graph-run-2",
        graph_index_revision="graph-2",
        graph_extraction_spec_version=spec.spec_version,
        graph_extraction_spec_digest=spec.spec_digest,
        tombstoned_at="2026-06-10T00:01:00+00:00",
    )
    relationship_tombstone = GraphTombstone(
        tombstone_id=stable_graph_tombstone_id(
            record_kind="relationship",
            record_vault_id="default",
            record_id=relationship.relationship_id,
            actual_scope=graph_scope_key(scope),
        ),
        record_kind="relationship",
        record_vault_id="default",
        record_id=relationship.relationship_id,
        actual_scope=graph_scope_key(scope),
        reason="missing_from_scope",
        graph_run_id="graph-run-2",
        graph_index_revision="graph-2",
        graph_extraction_spec_version=spec.spec_version,
        graph_extraction_spec_digest=spec.spec_digest,
        tombstoned_at="2026-06-10T00:01:00+00:00",
    )
    tombstone_plan = GraphReconcilePlan(
        requested_scope=scope,
        actual_scopes=(scope,),
        graph_run_id="graph-run-2",
        entity_upserts=(),
        relationship_upserts=(),
        evidence_ref_upserts=(),
        entity_tombstones=(entity_tombstone,),
        relationship_tombstones=(relationship_tombstone,),
        graph_revision_rows=(make_revision(scope, entity_count=0, relationship_count=0),),
        graph_extraction_spec=spec,
        projection_cache_invalidations=(),
    )

    store.apply_reconcile_plan(tombstone_plan)
    store.apply_reconcile_plan(make_plan(entities=(source, target), relationships=(relationship,), scope=scope))

    manifest = store.current_manifest((scope,))
    assert manifest.tombstone_rows == ()
    assert store.get_entity(vault_id="default", entity_id=source.entity_id).status == "active"  # type: ignore[union-attr]
    assert (
        store.get_relationship(source_vault_id="default", relationship_id=relationship.relationship_id).status  # type: ignore[union-attr]
        == "stated"
    )


def test_in_memory_active_upsert_clears_scoped_tombstones() -> None:
    tombstone_repair_contract(lambda: InMemoryGraphStore())


def test_sqlite_active_upsert_clears_scoped_tombstones(tmp_path: Path) -> None:
    tombstone_repair_contract(lambda: SQLiteGraphStore.open_writable(tmp_path / "graph.sqlite3"))
