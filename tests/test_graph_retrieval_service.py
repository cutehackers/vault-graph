from dataclasses import asdict, replace
from pathlib import Path

import pytest

from tests.fakes.in_memory_graph_store import InMemoryGraphStore
from tests.test_graph_store_contract import make_entity, make_plan, make_relationship
from tests.test_metadata_evidence_resolution import make_chunk, make_document
from vault_graph.app.graph_retrieval_service import GraphRetrievalService
from vault_graph.errors import GraphStoreError
from vault_graph.graph.graph_contracts import (
    EntityRecord,
    GraphEvidenceRef,
    RelationshipRecord,
    current_graph_extraction_spec,
)
from vault_graph.graph.graph_identity import graph_scope_key
from vault_graph.graph.graph_readiness import GraphReadiness, GraphScopeReadiness
from vault_graph.ingestion.vault_catalog import QueryScope, VaultCatalog, VaultCatalogEntry
from vault_graph.projection.graph_projection import (
    GRAPH_PROJECTION_VERSION,
    GraphPath,
    GraphProjection,
    GraphProjectionInput,
    GraphProjectionResult,
)
from vault_graph.projection.rustworkx_projection import RustworkxGraphProjection
from vault_graph.storage.local.sqlite_metadata_store import SQLiteMetadataStore


class StaticGraphReadiness:
    def __init__(self, report: GraphReadiness) -> None:
        self._report = report

    def check(self, *, requested_scope: QueryScope, actual_scopes: tuple[QueryScope, ...]) -> GraphReadiness:
        return self._report


class OrderedProjection:
    def __init__(self, target_order: tuple[str, ...]) -> None:
        self._target_order = target_order
        self.requests: list[GraphProjectionInput] = []

    def project(self, request: GraphProjectionInput) -> GraphProjectionResult:
        self.requests.append(request)
        nodes_by_identity = {(node.vault_id, node.entity_id): node for node in request.nodes}
        edge_by_target_name = {
            nodes_by_identity[(edge.target_vault_id, edge.target_entity_id)].name: edge
            for edge in request.relationships
        }
        paths = tuple(
            GraphPath(
                seed=request.seeds[0],
                target=nodes_by_identity[(edge.target_vault_id, edge.target_entity_id)],
                edges=(edge,),
                depth=1,
                score=0.5,
                explanation=f"1-edge graph path via {edge.relationship_type}",
            )
            for target_name in self._target_order
            if (edge := edge_by_target_name.get(target_name)) is not None
        )
        return GraphProjectionResult(
            projection_build_id="ordered-projection",
            graph_projection_version=GRAPH_PROJECTION_VERSION,
            source_graph_revisions=request.source_graph_revisions,
            node_count=len(request.nodes),
            edge_count=len(request.relationships),
            truncated=False,
            paths=paths,
        )


def make_graph_readiness(
    *,
    actual_scopes: tuple[QueryScope, ...],
    freshness: str = "fresh",
    stale_count: int = 0,
    warnings: tuple[str, ...] = (),
) -> GraphReadiness:
    scope_rows = tuple(
        GraphScopeReadiness(
            vault_id=scope.vault_ids[0],
            actual_scope=graph_scope_key(scope),
            freshness=freshness,
            stale_count=stale_count,
            tombstone_count=0,
            last_graph_revision="graph-1" if freshness == "fresh" else None,
            warnings=warnings,
        )
        for scope in actual_scopes
    )
    spec = current_graph_extraction_spec()
    return GraphReadiness(
        backend_name="memory-graph",
        backend_available=backend_available_for_freshness(freshness),
        schema_version="memory-graph-v1",
        schema_compatible=freshness != "incompatible",
        graph_extraction_spec_version=spec.spec_version,
        graph_extraction_spec_digest=spec.spec_digest,
        graph_extraction_spec_compatible=freshness != "incompatible",
        freshness=freshness,
        stale_count=stale_count,
        tombstone_count=0,
        last_graph_revision="graph-1" if freshness == "fresh" else None,
        affected_vault_ids=tuple(vault_id for scope in actual_scopes for vault_id in scope.vault_ids),
        scope_readiness=scope_rows,
        warnings=warnings,
        recovery_hint="ok" if freshness == "fresh" else "run `vg index`",
    )


def backend_available_for_freshness(freshness: str) -> bool:
    return freshness not in {"missing", "unavailable"}


def test_related_returns_evidence_linked_items(tmp_path: Path) -> None:
    scope = QueryScope(vault_ids=("default",), content_scopes=("wiki",))
    source = make_entity("default", name="GraphRAG")
    target = make_entity("default", name="Search")
    relationship = make_relationship(source, target)
    service = make_service(
        tmp_path=tmp_path,
        scopes=(scope,),
        entities=(source, target),
        relationships=(relationship,),
        metadata_refs=relationship.evidence_refs,
    )

    response = service.related(target="GraphRAG", requested_scope=scope)

    assert response.result_count == 1
    assert response.items[0].entity.entity_id == target.entity_id
    assert response.items[0].relationship_path == (relationship,)
    assert response.items[0].evidence[0].metadata_index_revision == "metadata-1"
    assert response.warnings == ()


def test_related_target_not_found_returns_warning_without_results(tmp_path: Path) -> None:
    scope = QueryScope(vault_ids=("default",), content_scopes=("wiki",))
    service = make_service(tmp_path=tmp_path, scopes=(scope,), entities=(), relationships=(), metadata_refs=())

    response = service.related(target="GraphRAG", requested_scope=scope)

    assert response.items == ()
    assert response.resolved_target is None
    assert response.warnings[0].code == "target_not_found"


def test_related_ambiguous_target_returns_candidates_without_guessing(tmp_path: Path) -> None:
    first_scope = QueryScope(vault_ids=("first",), content_scopes=("wiki",))
    second_scope = QueryScope(vault_ids=("second",), content_scopes=("wiki",))
    first = make_entity("first", name="GraphRAG")
    second = make_entity("second", name="GraphRAG")
    service = make_service(
        tmp_path=tmp_path,
        scopes=(first_scope, second_scope),
        entities=(first, second),
        relationships=(),
        metadata_refs=(),
    )

    response = service.related(
        target="GraphRAG",
        requested_scope=QueryScope(vault_ids=("first", "second"), content_scopes=("wiki",)),
    )

    assert response.items == ()
    assert response.resolved_target is None
    assert sorted(entity.vault_id for entity in response.target_candidates) == ["first", "second"]
    assert response.warnings[0].code == "ambiguous_graph_target"


def test_related_drops_relationship_path_when_relationship_evidence_is_missing(tmp_path: Path) -> None:
    scope = QueryScope(vault_ids=("default",), content_scopes=("wiki",))
    source = make_entity("default", name="GraphRAG")
    target = make_entity("default", name="Search")
    relationship = make_relationship(source, target)
    service = make_service(
        tmp_path=tmp_path,
        scopes=(scope,),
        entities=(source, target),
        relationships=(relationship,),
        metadata_refs=(),
    )

    response = service.related(target="GraphRAG", requested_scope=scope)

    assert response.items == ()
    assert response.warnings[0].code == "graph_evidence_missing"


def test_related_stale_graph_scope_returns_no_normal_results(tmp_path: Path) -> None:
    scope = QueryScope(vault_ids=("default",), content_scopes=("wiki",))
    source = make_entity("default", name="GraphRAG")
    service = make_service(
        tmp_path=tmp_path,
        scopes=(scope,),
        entities=(source,),
        relationships=(),
        metadata_refs=(),
        freshness="stale",
    )

    response = service.related(target="GraphRAG", requested_scope=scope)

    assert response.items == ()
    assert response.warnings[0].code == "graph_stale"


def test_related_depth_above_two_fails(tmp_path: Path) -> None:
    scope = QueryScope(vault_ids=("default",), content_scopes=("wiki",))
    service = make_service(tmp_path=tmp_path, scopes=(scope,), entities=(), relationships=(), metadata_refs=())

    with pytest.raises(GraphStoreError, match="unsupported graph projection depth"):
        service.related(target="GraphRAG", requested_scope=scope, depth=3)


def test_decision_trace_prefers_decision_entity(tmp_path: Path) -> None:
    scope = QueryScope(vault_ids=("default",), content_scopes=("wiki",))
    decision = typed_entity(
        make_entity(
            "default",
            name="Use GraphRAG",
            document_id="decision-doc",
            chunk_id="decision-chunk",
            content_hash="decision-hash",
            path="wiki/decisions/use-graphrag.md",
        ),
        entity_type="Decision",
    )
    wiki = typed_entity(
        make_entity(
            "default",
            name="Use GraphRAG",
            document_id="wiki-doc",
            chunk_id="wiki-chunk",
            content_hash="wiki-hash",
            path="wiki/use-graphrag.md",
        ),
        entity_type="WikiPage",
    )
    service = make_service(
        tmp_path=tmp_path,
        scopes=(scope,),
        entities=(wiki, decision),
        relationships=(),
        metadata_refs=decision.evidence_refs + wiki.evidence_refs,
    )

    response = service.decision_trace(topic="Use GraphRAG", requested_scope=scope)

    assert response.trace_kind == "decision"
    assert response.resolved_target == decision
    assert response.steps[0].role == "decision"
    assert response.steps[0].relationship_path == ()
    assert response.steps[0].evidence[0].document_id == "decision-doc"


def test_decision_trace_prefers_decision_alias_over_wikipage_name(tmp_path: Path) -> None:
    scope = QueryScope(vault_ids=("default",), content_scopes=("wiki",))
    decision = replace(
        typed_entity(
            make_entity(
                "default",
                name="Adopt GraphRAG",
                document_id="decision-doc",
                chunk_id="decision-chunk",
                content_hash="decision-hash",
                path="wiki/decisions/use-graphrag.md",
            ),
            entity_type="Decision",
        ),
        aliases=("Use GraphRAG",),
    )
    wiki = typed_entity(
        make_entity(
            "default",
            name="Use GraphRAG",
            document_id="wiki-doc",
            chunk_id="wiki-chunk",
            content_hash="wiki-hash",
            path="wiki/use-graphrag.md",
        ),
        entity_type="WikiPage",
    )
    service = make_service(
        tmp_path=tmp_path,
        scopes=(scope,),
        entities=(wiki, decision),
        relationships=(),
        metadata_refs=decision.evidence_refs + wiki.evidence_refs,
    )

    response = service.decision_trace(topic="Use GraphRAG", requested_scope=scope)

    assert response.trace_kind == "decision"
    assert response.resolved_target == decision
    assert response.steps[0].evidence[0].document_id == "decision-doc"


def test_decision_trace_falls_back_to_topic_trace_with_warning(tmp_path: Path) -> None:
    scope = QueryScope(vault_ids=("default",), content_scopes=("wiki",))
    topic = typed_entity(
        make_entity(
            "default",
            name="GraphRAG",
            document_id="topic-doc",
            chunk_id="topic-chunk",
            content_hash="topic-hash",
        ),
        entity_type="Concept",
    )
    service = make_service(
        tmp_path=tmp_path,
        scopes=(scope,),
        entities=(topic,),
        relationships=(),
        metadata_refs=topic.evidence_refs,
    )

    response = service.decision_trace(topic="GraphRAG", requested_scope=scope)

    assert response.trace_kind == "topic"
    assert response.resolved_target == topic
    assert response.steps[0].role == "topic"
    assert response.warnings[0].code == "topic_not_durable_decision"


def test_decision_trace_omits_initial_step_when_entity_evidence_is_missing(tmp_path: Path) -> None:
    scope = QueryScope(vault_ids=("default",), content_scopes=("wiki",))
    decision = typed_entity(
        make_entity(
            "default",
            name="Use GraphRAG",
            document_id="decision-doc",
            chunk_id="decision-chunk",
            content_hash="decision-hash",
            path="wiki/decisions/use-graphrag.md",
        ),
        entity_type="Decision",
    )
    service = make_service(
        tmp_path=tmp_path,
        scopes=(scope,),
        entities=(decision,),
        relationships=(),
        metadata_refs=(),
    )

    response = service.decision_trace(topic="Use GraphRAG", requested_scope=scope)

    assert response.steps == ()
    assert response.warnings[0].code == "graph_evidence_missing"
    assert response.warnings[0].entity_id == decision.entity_id


def test_decision_trace_orders_relationship_roles_by_priority(tmp_path: Path) -> None:
    scope = QueryScope(vault_ids=("default",), content_scopes=("wiki",))
    decision = typed_entity(
        make_entity(
            "default",
            name="Use GraphRAG",
            document_id="decision-doc",
            chunk_id="decision-chunk",
            content_hash="decision-hash",
            path="wiki/decisions/use-graphrag.md",
        ),
        entity_type="Decision",
    )
    superseded = make_entity("default", name="Old Search", path="wiki/old-search.md")
    dependency = make_entity("default", name="Vector Search", path="wiki/vector-search.md")
    related = make_entity("default", name="RAG", path="wiki/rag.md")
    blocked = make_entity("default", name="Slow Query", path="wiki/slow-query.md")
    relationships = (
        relationship_with_type(decision, related, "related_to"),
        relationship_with_type(decision, dependency, "depends_on"),
        relationship_with_type(decision, superseded, "supersedes"),
        relationship_with_type(decision, blocked, "blocks"),
    )
    service = make_service(
        tmp_path=tmp_path,
        scopes=(scope,),
        entities=(decision, superseded, dependency, related, blocked),
        relationships=relationships,
        metadata_refs=decision.evidence_refs
        + tuple(ref for relationship in relationships for ref in relationship.evidence_refs),
    )

    response = service.decision_trace(topic="Use GraphRAG", requested_scope=scope)

    assert tuple(step.role for step in response.steps[1:]) == (
        "supersedes",
        "depends_on",
        "blocks",
        "related_to",
    )


def test_decision_trace_preserves_projection_rank_after_role_and_score(tmp_path: Path) -> None:
    scope = QueryScope(vault_ids=("default",), content_scopes=("wiki",))
    decision = typed_entity(
        make_entity(
            "default",
            name="Use GraphRAG",
            document_id="decision-doc",
            chunk_id="decision-chunk",
            content_hash="decision-hash",
            path="wiki/decisions/use-graphrag.md",
        ),
        entity_type="Decision",
    )
    alpha = make_entity("default", name="Alpha", path="wiki/alpha.md")
    zulu = make_entity("default", name="Zulu", path="wiki/zulu.md")
    relationships = (
        relationship_with_type(decision, alpha, "depends_on"),
        relationship_with_type(decision, zulu, "depends_on"),
    )
    service = make_service(
        tmp_path=tmp_path,
        scopes=(scope,),
        entities=(decision, alpha, zulu),
        relationships=relationships,
        metadata_refs=decision.evidence_refs
        + tuple(ref for relationship in relationships for ref in relationship.evidence_refs),
        projection=OrderedProjection(("Zulu", "Alpha")),
    )

    response = service.decision_trace(topic="Use GraphRAG", requested_scope=scope)

    assert tuple(step.entity.name for step in response.steps[1:]) == ("Zulu", "Alpha")


def test_decision_trace_requests_only_remaining_path_limit_after_initial_step(tmp_path: Path) -> None:
    scope = QueryScope(vault_ids=("default",), content_scopes=("wiki",))
    decision = typed_entity(
        make_entity(
            "default",
            name="Use GraphRAG",
            document_id="decision-doc",
            chunk_id="decision-chunk",
            content_hash="decision-hash",
            path="wiki/decisions/use-graphrag.md",
        ),
        entity_type="Decision",
    )
    alpha = make_entity("default", name="Alpha", path="wiki/alpha.md")
    zulu = make_entity("default", name="Zulu", path="wiki/zulu.md")
    relationships = (
        relationship_with_type(decision, alpha, "depends_on"),
        relationship_with_type(decision, zulu, "depends_on"),
    )
    projection = OrderedProjection(("Alpha", "Zulu"))
    service = make_service(
        tmp_path=tmp_path,
        scopes=(scope,),
        entities=(decision, alpha, zulu),
        relationships=relationships,
        metadata_refs=decision.evidence_refs
        + tuple(ref for relationship in relationships for ref in relationship.evidence_refs),
        projection=projection,
    )

    response = service.decision_trace(topic="Use GraphRAG", requested_scope=scope, limit=2)

    assert len(response.steps) == 2
    assert response.steps[0].role == "decision"
    assert projection.requests[0].limit == 1


def test_decision_trace_does_not_synthesize_recommendation(tmp_path: Path) -> None:
    scope = QueryScope(vault_ids=("default",), content_scopes=("wiki",))
    decision = typed_entity(
        make_entity(
            "default",
            name="Use GraphRAG",
            document_id="decision-doc",
            chunk_id="decision-chunk",
            content_hash="decision-hash",
            path="wiki/decisions/use-graphrag.md",
        ),
        entity_type="Decision",
    )
    service = make_service(
        tmp_path=tmp_path,
        scopes=(scope,),
        entities=(decision,),
        relationships=(),
        metadata_refs=decision.evidence_refs,
    )

    response = service.decision_trace(topic="Use GraphRAG", requested_scope=scope)

    assert {"answer", "recommendation", "final"}.isdisjoint(field_names(asdict(response)))


def make_service(
    *,
    tmp_path: Path,
    scopes: tuple[QueryScope, ...],
    entities: tuple[EntityRecord, ...],
    relationships: tuple[RelationshipRecord, ...],
    metadata_refs: tuple[GraphEvidenceRef, ...],
    freshness: str = "fresh",
    projection: GraphProjection | None = None,
) -> GraphRetrievalService:
    catalog = make_catalog(tmp_path=tmp_path, vault_ids=tuple(scope.vault_ids[0] for scope in scopes))
    metadata_store = SQLiteMetadataStore(tmp_path / "metadata.sqlite3", initialize=True)
    apply_metadata_refs(metadata_store, metadata_refs)
    graph_store = InMemoryGraphStore()
    for scope in scopes:
        scoped_entities = tuple(entity for entity in entities if entity.vault_id == scope.vault_ids[0])
        scoped_relationships = tuple(
            relationship for relationship in relationships if relationship.source_vault_id == scope.vault_ids[0]
        )
        graph_store.apply_reconcile_plan(
            make_plan(entities=scoped_entities, relationships=scoped_relationships, scope=scope)
        )
    return GraphRetrievalService(
        catalog=catalog,
        metadata_store=metadata_store,
        graph_store=graph_store,
        graph_readiness=StaticGraphReadiness(make_graph_readiness(actual_scopes=scopes, freshness=freshness)),
        projection=projection or RustworkxGraphProjection(),
    )


def make_catalog(*, tmp_path: Path, vault_ids: tuple[str, ...]) -> VaultCatalog:
    entries: list[VaultCatalogEntry] = []
    for vault_id in vault_ids:
        root = tmp_path / vault_id
        root.mkdir(exist_ok=True)
        entries.append(VaultCatalogEntry.from_root(vault_id=vault_id, root_path=root, content_scopes=("wiki",)))
    return VaultCatalog.from_entries(entries=entries, active_vault_id=vault_ids[0] if vault_ids else "default")


def apply_metadata_refs(store: SQLiteMetadataStore, refs: tuple[GraphEvidenceRef, ...]) -> None:
    documents = []
    chunks = []
    documents_by_key = {}
    seen_documents: set[tuple[str, str]] = set()
    seen_chunks: set[tuple[str, str]] = set()
    for ref in refs:
        path = ref.path or "wiki/page.md"
        document_key = (ref.evidence_vault_id, ref.document_id)
        if document_key not in seen_documents:
            document = make_document(ref.evidence_vault_id, path, f"doc:{ref.content_hash}")
            document = replace(document, document_id=ref.document_id)
            documents.append(document)
            documents_by_key[document_key] = document
            seen_documents.add(document_key)
        chunk_key = (ref.evidence_vault_id, ref.chunk_id)
        if chunk_key not in seen_chunks:
            document = documents_by_key[document_key]
            chunk = make_chunk(document, text=ref.excerpt or "relationship evidence")
            chunks.append(replace(chunk, chunk_id=ref.chunk_id, content_hash=ref.content_hash))
            seen_chunks.add(chunk_key)
    if documents or chunks:
        store.apply_metadata_revision(index_revision="metadata-1", documents=documents, chunks=chunks, tombstones=[])


def typed_entity(entity: EntityRecord, *, entity_type: str) -> EntityRecord:
    return replace(entity, type=entity_type)


def relationship_with_type(
    source: EntityRecord,
    target: EntityRecord,
    relationship_type: str,
) -> RelationshipRecord:
    relationship = make_relationship(source, target)
    relationship_id = f"{relationship.relationship_id}-{relationship_type}"
    evidence_refs = tuple(
        replace(
            ref,
            evidence_ref_id=f"{ref.evidence_ref_id}-{relationship_type}",
            owner_id=relationship_id,
            document_id=f"{relationship_type}-doc",
            chunk_id=f"{relationship_type}-chunk",
            content_hash=f"{relationship_type}-hash",
            anchor=relationship_type,
            path=f"wiki/{relationship_type}.md",
        )
        for ref in relationship.evidence_refs
    )
    return replace(
        relationship,
        relationship_id=relationship_id,
        type=relationship_type,
        evidence_refs=evidence_refs,
    )


def field_names(value: object) -> set[str]:
    names: set[str] = set()
    if isinstance(value, dict):
        names.update(str(key) for key in value)
        for child in value.values():
            names.update(field_names(child))
    elif isinstance(value, list | tuple):
        for child in value:
            names.update(field_names(child))
    return names
