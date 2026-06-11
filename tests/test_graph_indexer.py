from tests.fakes.in_memory_graph_store import InMemoryGraphStore
from vault_graph.extraction.entity_extractor import DeterministicEntityExtractor
from vault_graph.extraction.graph_occurrences import (
    EntityOccurrence,
    RelationshipOccurrence,
    entity_occurrence_key,
)
from vault_graph.extraction.graph_source_store import GraphExtractionContext, PreviewGraphSourceStore
from vault_graph.extraction.relationship_extractor import DeterministicRelationshipExtractor
from vault_graph.graph.graph_contracts import GraphExtractionSpec, current_graph_extraction_spec
from vault_graph.graph.graph_identity import graph_scope_key
from vault_graph.indexing.graph_indexer import GraphIndexer
from vault_graph.ingestion.document_normalizer import ChunkSnapshot, DocumentSnapshot
from vault_graph.ingestion.vault_catalog import QueryScope


def document(
    vault_id: str,
    path: str,
    *,
    frontmatter: dict[str, object] | None = None,
    parser_version: str = "markdown-frontmatter-v1",
) -> DocumentSnapshot:
    return DocumentSnapshot(
        vault_id=vault_id,
        document_id=f"{vault_id}:{path}",
        path=path,
        kind=path.split("/", 1)[0],
        frontmatter=frontmatter or {},
        frontmatter_hash="frontmatter",
        content_hash="content",
        raw_sha256="raw",
        parser_version=parser_version,
        last_seen_at="2026-06-11T00:00:00+00:00",
        last_indexed_at=None,
        vault_revision=None,
        index_revision="metadata-1",
    )


def chunk(
    doc: DocumentSnapshot,
    *,
    text: str = "Body",
    section: str | None = "Architecture",
    content_hash: str | None = None,
    index_revision: str = "metadata-1",
    chunker_version: str = "heading-section-v1",
) -> ChunkSnapshot:
    return ChunkSnapshot(
        vault_id=doc.vault_id,
        chunk_id=f"chunk:{doc.document_id}",
        document_id=doc.document_id,
        path=doc.path,
        section=section,
        anchor=section.casefold().replace(" ", "-") if section else None,
        text=text,
        token_count=len(text.split()),
        content_hash=content_hash or f"hash:{doc.document_id}",
        chunker_version=chunker_version,
        index_revision=index_revision,
    )


def indexer(
    *,
    source_store: PreviewGraphSourceStore,
    graph_store: InMemoryGraphStore,
    spec: GraphExtractionSpec | None = None,
) -> GraphIndexer:
    return GraphIndexer(
        source_store=source_store,
        graph_store=graph_store,
        entity_extractor=DeterministicEntityExtractor(),
        relationship_extractor=DeterministicRelationshipExtractor(),
        graph_extraction_spec=spec or current_graph_extraction_spec(),
        metadata_schema_version="metadata-v1",
        now=lambda: "2026-06-11T00:00:00+00:00",
        graph_run_id_factory=lambda: "graph-run-1",
        graph_revision_factory=lambda: "graph-1",
    )


def test_graph_plan_creates_reconcile_plan_without_applying() -> None:
    doc = document("default", "wiki/source.md", frontmatter={"tags": ["GraphRAG"]})
    source_chunk = chunk(doc, text="See [[Missing]].")
    source_store = PreviewGraphSourceStore(chunks=(source_chunk,), documents=(doc,))
    graph_store = InMemoryGraphStore()
    scope = QueryScope(vault_ids=("default",), content_scopes=("wiki",))

    report = indexer(source_store=source_store, graph_store=graph_store).plan(
        requested_scope=scope,
        actual_scopes=(scope,),
    )

    assert report.reconcile_plan.entity_upserts
    assert {entity.type for entity in report.reconcile_plan.entity_upserts} >= {"WikiPage", "Concept"}
    assert {relationship.type for relationship in report.reconcile_plan.relationship_upserts} >= {"mentions"}
    assert any("unresolved_local_link" in warning for warning in report.warnings)
    assert graph_store.current_manifest((scope,)).entity_rows == ()


def test_second_identical_plan_after_apply_has_no_upserts_then_changed_chunk_is_stale() -> None:
    doc = document("default", "wiki/source.md")
    first_chunk = chunk(doc)
    scope = QueryScope(vault_ids=("default",), content_scopes=("wiki",))
    graph_store = InMemoryGraphStore()
    first_source = PreviewGraphSourceStore(chunks=(first_chunk,), documents=(doc,))
    first = indexer(source_store=first_source, graph_store=graph_store)

    graph_store.apply_reconcile_plan(first.plan(requested_scope=scope, actual_scopes=(scope,)).reconcile_plan)

    second = indexer(source_store=first_source, graph_store=graph_store).plan(
        requested_scope=scope,
        actual_scopes=(scope,),
    )
    changed_source = PreviewGraphSourceStore(
        chunks=(chunk(doc, content_hash="changed-hash"),),
        documents=(doc,),
    )
    changed = indexer(source_store=changed_source, graph_store=graph_store).plan(
        requested_scope=scope,
        actual_scopes=(scope,),
    )

    assert second.reconcile_plan.entity_upserts == ()
    assert second.reconcile_plan.relationship_upserts == ()
    assert changed.reconcile_plan.entity_upserts
    assert changed.stale_count > 0


def test_missing_current_records_create_scope_tombstones() -> None:
    doc = document("default", "wiki/source.md")
    source_chunk = chunk(doc)
    scope = QueryScope(vault_ids=("default",), content_scopes=("wiki",))
    graph_store = InMemoryGraphStore()
    first = indexer(
        source_store=PreviewGraphSourceStore(chunks=(source_chunk,), documents=(doc,)),
        graph_store=graph_store,
    )
    graph_store.apply_reconcile_plan(first.plan(requested_scope=scope, actual_scopes=(scope,)).reconcile_plan)

    empty_report = indexer(
        source_store=PreviewGraphSourceStore(chunks=(), documents=()),
        graph_store=graph_store,
    ).plan(requested_scope=scope, actual_scopes=(scope,))

    assert empty_report.reconcile_plan.entity_tombstones
    assert {tombstone.actual_scope for tombstone in empty_report.reconcile_plan.entity_tombstones} == {
        graph_scope_key(scope),
    }


def test_all_vault_planning_keeps_entity_ids_namespaced() -> None:
    first_doc = document("first", "wiki/shared.md")
    second_doc = document("second", "wiki/shared.md")
    first_chunk = chunk(first_doc, section="Shared")
    second_chunk = chunk(second_doc, section="Shared")
    first_scope = QueryScope(vault_ids=("first",), content_scopes=("wiki",))
    second_scope = QueryScope(vault_ids=("second",), content_scopes=("wiki",))
    requested_scope = QueryScope(vault_ids=("first", "second"), content_scopes=("wiki",))

    report = indexer(
        source_store=PreviewGraphSourceStore(
            chunks=(first_chunk, second_chunk),
            documents=(first_doc, second_doc),
        ),
        graph_store=InMemoryGraphStore(),
    ).plan(requested_scope=requested_scope, actual_scopes=(first_scope, second_scope))

    shared_heading_ids = {
        entity.entity_id for entity in report.reconcile_plan.entity_upserts if entity.type == "Concept"
    }
    assert len(report.reconcile_plan.graph_revision_rows) == 2
    assert len(shared_heading_ids) == 2


def test_resolvable_link_and_frontmatter_relationship_persist_relationship_rows() -> None:
    source = document("default", "wiki/source.md", frontmatter={"depends_on": "target"})
    target = document("default", "wiki/target.md", frontmatter={"title": "Target Page"})
    source_chunk = chunk(source, text="See [[target]].")
    target_chunk = chunk(target)
    scope = QueryScope(vault_ids=("default",), content_scopes=("wiki",))
    graph_store = InMemoryGraphStore()
    source_store = PreviewGraphSourceStore(chunks=(source_chunk, target_chunk), documents=(source, target))

    result = indexer(source_store=source_store, graph_store=graph_store).apply(
        requested_scope=scope,
        actual_scopes=(scope,),
    )
    manifest = graph_store.current_manifest((scope,))

    assert result.failed is False
    assert {row.type for row in manifest.relationship_rows} >= {"links_to", "depends_on"}


def test_lineage_and_spec_changes_make_records_stale_without_using_graph_revision_only() -> None:
    doc = document("default", "wiki/source.md")
    scope = QueryScope(vault_ids=("default",), content_scopes=("wiki",))
    graph_store = InMemoryGraphStore()
    first_source = PreviewGraphSourceStore(chunks=(chunk(doc),), documents=(doc,))
    graph_store.apply_reconcile_plan(
        indexer(source_store=first_source, graph_store=graph_store).plan(
            requested_scope=scope,
            actual_scopes=(scope,),
        ).reconcile_plan
    )

    metadata_changed = PreviewGraphSourceStore(chunks=(chunk(doc, index_revision="metadata-2"),), documents=(doc,))
    parser_changed_doc = document("default", "wiki/source.md", parser_version="parser-v2")
    parser_changed = PreviewGraphSourceStore(chunks=(chunk(parser_changed_doc),), documents=(parser_changed_doc,))
    chunker_changed = PreviewGraphSourceStore(
        chunks=(chunk(doc, chunker_version="chunker-v2"),),
        documents=(doc,),
    )
    legacy_spec = GraphExtractionSpec.from_payload(
        {
            "spec_version": "graph-extraction-spec-legacy",
            "entity_schema_version": "entity-schema-v1",
            "relationship_schema_version": "relationship-schema-v1",
            "entity_extractor_name": "legacy",
            "entity_extractor_version": "legacy",
            "relationship_extractor_name": "legacy",
            "relationship_extractor_version": "legacy",
            "relationship_status_rules_version": "relationship-status-rules-v1",
            "confidence_rules_version": "confidence-rules-v1",
        }
    )

    assert indexer(source_store=metadata_changed, graph_store=graph_store).plan(
        requested_scope=scope,
        actual_scopes=(scope,),
    ).stale_count
    assert indexer(source_store=parser_changed, graph_store=graph_store).plan(
        requested_scope=scope,
        actual_scopes=(scope,),
    ).stale_count
    assert indexer(source_store=chunker_changed, graph_store=graph_store).plan(
        requested_scope=scope,
        actual_scopes=(scope,),
    ).stale_count
    assert indexer(source_store=first_source, graph_store=graph_store, spec=legacy_spec).plan(
        requested_scope=scope,
        actual_scopes=(scope,),
    ).stale_count


def test_projection_invalidations_are_keys_only() -> None:
    doc = document("default", "wiki/source.md")
    source_chunk = chunk(doc)
    scope = QueryScope(vault_ids=("default",), content_scopes=("wiki",))

    report = indexer(
        source_store=PreviewGraphSourceStore(chunks=(source_chunk,), documents=(doc,)),
        graph_store=InMemoryGraphStore(),
    ).plan(requested_scope=scope, actual_scopes=(scope,))

    assert report.reconcile_plan.projection_cache_invalidations == (
        f"graph-projection:{graph_scope_key(scope)}",
    )


def test_graph_indexer_preserves_relationship_occurrence_status() -> None:
    class ContestedRelationshipExtractor:
        def extract(
            self,
            *,
            chunk: ChunkSnapshot,
            document: DocumentSnapshot | None,
            entities: tuple[EntityOccurrence, ...],
            context: GraphExtractionContext,
            scope: QueryScope,
            spec: GraphExtractionSpec,
        ) -> tuple[RelationshipOccurrence, ...]:
            source = next(entity for entity in entities if entity.extraction_method == "document-identity-v1")
            target = next(entity for entity in entities if entity.entity_type == "Concept")
            return (
                RelationshipOccurrence(
                    relationship_type="mentions",
                    source_vault_id=source.vault_id,
                    source_entity_key=entity_occurrence_key(source),
                    target_vault_id=target.vault_id,
                    target_entity_key=entity_occurrence_key(target),
                    evidence_vault_id=chunk.vault_id,
                    document_id=chunk.document_id,
                    chunk_id=chunk.chunk_id,
                    content_hash=chunk.content_hash,
                    section=chunk.section,
                    anchor=chunk.anchor,
                    path=chunk.path,
                    excerpt=chunk.text,
                    status="contested",
                    confidence=0.5,
                    extraction_method="test-contested-relationship-v1",
                ),
            )

    doc = document("default", "wiki/source.md")
    source_chunk = chunk(doc)
    scope = QueryScope(vault_ids=("default",), content_scopes=("wiki",))
    report = GraphIndexer(
        source_store=PreviewGraphSourceStore(chunks=(source_chunk,), documents=(doc,)),
        graph_store=InMemoryGraphStore(),
        entity_extractor=DeterministicEntityExtractor(),
        relationship_extractor=ContestedRelationshipExtractor(),
        graph_extraction_spec=current_graph_extraction_spec(),
        metadata_schema_version="metadata-v1",
    ).plan(requested_scope=scope, actual_scopes=(scope,))

    assert report.reconcile_plan.relationship_upserts[0].status == "contested"
