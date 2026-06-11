from __future__ import annotations

from pathlib import Path

from tests.fakes.in_memory_graph_store import InMemoryGraphStore
from tests.fakes.in_memory_keyword_index import InMemoryKeywordIndex
from tests.fakes.search_readiness import ready_report
from tests.test_graph_retrieval_service import (
    StaticGraphReadiness,
    apply_metadata_refs,
    make_graph_readiness,
)
from tests.test_graph_store_contract import make_entity, make_plan, make_relationship
from tests.test_metadata_evidence_resolution import make_chunk, make_document
from vault_graph.app.graph_retrieval_service import GraphRetrievalService
from vault_graph.errors import GraphStoreError
from vault_graph.graph.graph_contracts import EntityRecord, RelationshipRecord
from vault_graph.graph.graph_query import GraphEntityQuery, GraphEntityQueryResult
from vault_graph.ingestion.vault_catalog import QueryScope, VaultCatalog, VaultCatalogEntry
from vault_graph.projection.rustworkx_projection import RustworkxGraphProjection
from vault_graph.retrieval.graph_candidates import GraphSearchCandidateProvider
from vault_graph.retrieval.retrieval_service import RetrievalService
from vault_graph.retrieval.search_readiness import SearchReadinessReport
from vault_graph.storage.interfaces.keyword_index import KeywordHit
from vault_graph.storage.local.sqlite_metadata_store import SQLiteMetadataStore


class StaticSearchReadiness:
    def check(self, *, actual_scopes: tuple[QueryScope, ...]) -> SearchReadinessReport:
        return ready_report(vector_ok=False)


class FailingFindEntitiesGraphStore(InMemoryGraphStore):
    def find_entities(self, query: GraphEntityQuery) -> GraphEntityQueryResult:
        raise GraphStoreError("graph lookup failed")


def test_search_include_graph_adds_graph_signal_without_hiding_keyword_signal(tmp_path: Path) -> None:
    service, scope, relationship = _search_service_with_graph(tmp_path, keyword_on_graph_evidence=True)

    response = service.search(query_text="GraphRAG", requested_scope=scope, include_graph=True)

    assert response.result_count == 1
    assert tuple(signal.kind for signal in response.results[0].signals) == ("keyword", "graph")
    assert any(
        signal.source_id.startswith(f"graph:default:{relationship.relationship_id}")
        for signal in response.results[0].signals
    )
    assert any(revision.kind == "graph" for revision in response.store_revisions)


def test_search_include_graph_preserves_graph_signal_explanation(tmp_path: Path) -> None:
    service, scope, _ = _search_service_with_graph(tmp_path, keyword_on_graph_evidence=True)

    response = service.search(query_text="GraphRAG", requested_scope=scope, include_graph=True)

    graph_signal = next(signal for signal in response.results[0].signals if signal.kind == "graph")
    assert graph_signal.explanation == "GraphRAG -> Search via depends_on"


def test_search_graph_target_not_found_degrades_to_keyword_vector(tmp_path: Path) -> None:
    service, scope, _ = _search_service_with_graph(tmp_path, graph_entities=())

    response = service.search(query_text="MissingGraphTarget", requested_scope=scope, include_graph=True)

    assert response.result_count == 1
    assert tuple(signal.kind for signal in response.results[0].signals) == ("keyword",)
    assert any(warning.code == "graph_target_not_found" for warning in response.warnings)
    assert any(revision.kind == "graph" and revision.revision == "graph-1" for revision in response.store_revisions)


def test_search_include_cross_vault_marks_actual_graph_scope(tmp_path: Path) -> None:
    service, scope, _ = _search_service_with_graph(tmp_path, keyword_on_graph_evidence=True)

    response = service.search(
        query_text="GraphRAG",
        requested_scope=scope,
        include_graph=True,
        include_cross_vault=True,
    )

    assert response.requested_scope.include_cross_vault is True
    assert response.actual_scopes[0].include_cross_vault is True


def test_search_graph_query_failure_degrades_to_keyword_vector(tmp_path: Path) -> None:
    service, scope, _ = _search_service_with_graph(tmp_path, graph_store=FailingFindEntitiesGraphStore())

    response = service.search(query_text="GraphRAG", requested_scope=scope, include_graph=True)

    assert response.result_count == 1
    assert tuple(signal.kind for signal in response.results[0].signals) == ("keyword",)
    assert any(warning.code == "graph_query_failed" for warning in response.warnings)


def test_search_graph_missing_degrades_to_keyword_vector(tmp_path: Path) -> None:
    _assert_graph_readiness_degrades_to_keyword(tmp_path, freshness="missing", warning_code="graph_empty")


def test_search_graph_empty_degrades_to_keyword_vector(tmp_path: Path) -> None:
    _assert_graph_readiness_degrades_to_keyword(tmp_path, freshness="empty", warning_code="graph_empty")


def test_search_graph_stale_degrades_to_keyword_vector(tmp_path: Path) -> None:
    _assert_graph_readiness_degrades_to_keyword(tmp_path, freshness="stale", warning_code="graph_stale")


def test_search_graph_incompatible_degrades_to_keyword_vector(tmp_path: Path) -> None:
    _assert_graph_readiness_degrades_to_keyword(tmp_path, freshness="incompatible", warning_code="graph_unavailable")


def test_search_graph_unavailable_degrades_to_keyword_vector(tmp_path: Path) -> None:
    _assert_graph_readiness_degrades_to_keyword(tmp_path, freshness="unavailable", warning_code="graph_unavailable")


def test_graph_signal_weight_does_not_outrank_stronger_direct_evidence(tmp_path: Path) -> None:
    service, scope, _ = _search_service_with_graph(tmp_path, keyword_on_graph_evidence=False)

    response = service.search(query_text="GraphRAG", requested_scope=scope, include_graph=True)

    assert response.result_count == 2
    assert tuple(signal.kind for signal in response.results[0].signals) == ("keyword",)
    assert tuple(signal.kind for signal in response.results[1].signals) == ("graph",)


def _assert_graph_readiness_degrades_to_keyword(tmp_path: Path, *, freshness: str, warning_code: str) -> None:
    service, scope, _ = _search_service_with_graph(tmp_path, freshness=freshness)

    response = service.search(query_text="GraphRAG", requested_scope=scope, include_graph=True)

    assert response.result_count == 1
    assert tuple(signal.kind for signal in response.results[0].signals) == ("keyword",)
    assert any(warning.code == warning_code for warning in response.warnings)


def _search_service_with_graph(
    tmp_path: Path,
    *,
    keyword_on_graph_evidence: bool = False,
    graph_entities: tuple[EntityRecord, ...] | None = None,
    graph_store: InMemoryGraphStore | None = None,
    freshness: str = "fresh",
) -> tuple[RetrievalService, QueryScope, RelationshipRecord]:
    scope = QueryScope(vault_ids=("default",), content_scopes=("wiki",))
    catalog = _catalog(tmp_path)
    source = make_entity("default", name="GraphRAG")
    target = make_entity("default", name="Search")
    relationship = make_relationship(source, target)
    selected_entities = (source, target) if graph_entities is None else graph_entities
    selected_store = graph_store or InMemoryGraphStore()
    selected_store.apply_reconcile_plan(
        make_plan(entities=selected_entities, relationships=(relationship,), scope=scope)
    )

    metadata_store = SQLiteMetadataStore(tmp_path / "metadata.sqlite3", initialize=True)
    apply_metadata_refs(metadata_store, relationship.evidence_refs)
    direct_document = make_document("default", "wiki/direct.md", "direct-hash")
    direct_chunk = make_chunk(direct_document, text="GraphRAG direct evidence")
    metadata_store.apply_metadata_revision(
        index_revision="metadata-1",
        documents=[direct_document],
        chunks=[direct_chunk],
        tombstones=[],
    )
    graph_ref = relationship.evidence_refs[0]
    keyword_document_id = graph_ref.document_id if keyword_on_graph_evidence else direct_document.document_id
    keyword_chunk_id = graph_ref.chunk_id if keyword_on_graph_evidence else direct_chunk.chunk_id

    graph_service = GraphRetrievalService(
        catalog=catalog,
        metadata_store=metadata_store,
        graph_store=selected_store,
        graph_readiness=StaticGraphReadiness(make_graph_readiness(actual_scopes=(scope,), freshness=freshness)),
        projection=RustworkxGraphProjection(),
    )
    return (
        RetrievalService(
            catalog=catalog,
            metadata_store=metadata_store,
            keyword_index=InMemoryKeywordIndex((_keyword_hit(keyword_document_id, keyword_chunk_id),)),
            readiness=StaticSearchReadiness(),
            graph_candidate_provider=GraphSearchCandidateProvider(graph_retrieval_service=graph_service),
        ),
        scope,
        relationship,
    )


def _catalog(tmp_path: Path) -> VaultCatalog:
    root = tmp_path / "vault"
    root.mkdir()
    return VaultCatalog.from_entries(
        entries=[VaultCatalogEntry.from_root(vault_id="default", root_path=root, content_scopes=("wiki",))],
        active_vault_id="default",
    )


def _keyword_hit(document_id: str, chunk_id: str) -> KeywordHit:
    return KeywordHit(
        vault_id="default",
        document_id=document_id,
        chunk_id=chunk_id,
        rank=1,
        score=-1.0,
        backend="memory-keyword",
        index_revision="metadata-1",
        matched_fields=("text",),
    )
