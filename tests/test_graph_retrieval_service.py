from dataclasses import replace
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
from vault_graph.projection.rustworkx_projection import RustworkxGraphProjection
from vault_graph.storage.local.sqlite_metadata_store import SQLiteMetadataStore


class StaticGraphReadiness:
    def __init__(self, report: GraphReadiness) -> None:
        self._report = report

    def check(self, *, requested_scope: QueryScope, actual_scopes: tuple[QueryScope, ...]) -> GraphReadiness:
        return self._report


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


def test_decision_trace_does_not_exist_before_task_8(tmp_path: Path) -> None:
    scope = QueryScope(vault_ids=("default",), content_scopes=("wiki",))
    service = make_service(tmp_path=tmp_path, scopes=(scope,), entities=(), relationships=(), metadata_refs=())

    assert hasattr(service, "decision_trace")


def make_service(
    *,
    tmp_path: Path,
    scopes: tuple[QueryScope, ...],
    entities: tuple[EntityRecord, ...],
    relationships: tuple[RelationshipRecord, ...],
    metadata_refs: tuple[GraphEvidenceRef, ...],
    freshness: str = "fresh",
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
        projection=RustworkxGraphProjection(),
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
    seen_documents: set[tuple[str, str]] = set()
    seen_chunks: set[tuple[str, str]] = set()
    for ref in refs:
        path = ref.path or "wiki/page.md"
        document_key = (ref.evidence_vault_id, ref.document_id)
        if document_key not in seen_documents:
            document = make_document(ref.evidence_vault_id, path, f"doc:{ref.content_hash}")
            documents.append(replace(document, document_id=ref.document_id))
            seen_documents.add(document_key)
        chunk_key = (ref.evidence_vault_id, ref.chunk_id)
        if chunk_key not in seen_chunks:
            document = next(item for item in documents if item.vault_id == ref.evidence_vault_id)
            chunk = make_chunk(document, text=ref.excerpt or "relationship evidence")
            chunks.append(replace(chunk, chunk_id=ref.chunk_id, content_hash=ref.content_hash))
            seen_chunks.add(chunk_key)
    if documents or chunks:
        store.apply_metadata_revision(index_revision="metadata-1", documents=documents, chunks=chunks, tombstones=[])
