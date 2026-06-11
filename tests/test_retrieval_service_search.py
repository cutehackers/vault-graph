from dataclasses import replace
from pathlib import Path

import pytest

from tests.fakes.deterministic_text_embeddings import DeterministicTextEmbeddings
from tests.fakes.in_memory_keyword_index import InMemoryKeywordIndex
from tests.fakes.in_memory_vector_store import InMemoryVectorStore
from tests.fakes.search_readiness import ready_report
from tests.test_sqlite_metadata_store import make_chunk, make_document
from tests.test_vector_indexer import SPEC
from vault_graph.embeddings.text_embeddings import EmbeddingInput
from vault_graph.errors import SearchError
from vault_graph.indexing.vector_indexer import stable_vector_id
from vault_graph.ingestion.vault_catalog import QueryScope, VaultCatalog, VaultCatalogEntry
from vault_graph.retrieval.graph_candidates import GraphCandidateResult
from vault_graph.retrieval.retrieval_candidate import RetrievalCandidate
from vault_graph.retrieval.retrieval_result import RetrievalSignal
from vault_graph.retrieval.retrieval_service import RetrievalService
from vault_graph.retrieval.search_readiness import SearchReadinessReport, SearchScopeReadiness
from vault_graph.retrieval.search_response import SearchStoreRevision, SearchWarning
from vault_graph.storage.interfaces.keyword_index import KeywordHit
from vault_graph.storage.interfaces.store_health import StoreHealth
from vault_graph.storage.interfaces.vector_store import VectorEmbeddingRecord, VectorHit, VectorQuery
from vault_graph.storage.local.sqlite_metadata_store import SQLiteMetadataStore


class StaticReadiness:
    def __init__(self, report: SearchReadinessReport) -> None:
        self._report = report

    def check(self, *, actual_scopes: tuple[QueryScope, ...]) -> SearchReadinessReport:
        return self._report


class FailingVectorStore(InMemoryVectorStore):
    def search(self, query: VectorQuery) -> tuple[VectorHit, ...]:
        from vault_graph.errors import VectorStoreError

        raise VectorStoreError("client failed")


class FailingGraphCandidateProvider:
    def candidates(self, **_: object) -> GraphCandidateResult:
        raise AssertionError("graph provider must not be called by default search")


class StaticGraphCandidateProvider:
    def __init__(self, result: GraphCandidateResult) -> None:
        self.result = result
        self.calls: list[dict[str, object]] = []

    def candidates(
        self,
        *,
        query_text: str,
        requested_scope: QueryScope,
        actual_scopes: tuple[QueryScope, ...],
        limit: int,
        include_cross_vault: bool,
    ) -> GraphCandidateResult:
        self.calls.append(
            {
                "query_text": query_text,
                "requested_scope": requested_scope,
                "actual_scopes": actual_scopes,
                "limit": limit,
                "include_cross_vault": include_cross_vault,
            }
        )
        return self.result


def _catalog(tmp_path: Path, vault_id: str = "default") -> VaultCatalog:
    root = tmp_path / vault_id
    root.mkdir()
    return VaultCatalog.from_entries(
        entries=[VaultCatalogEntry.from_root(vault_id=vault_id, root_path=root)],
        active_vault_id=vault_id,
    )


def _metadata_store(tmp_path: Path) -> tuple[SQLiteMetadataStore, str, str]:
    store = SQLiteMetadataStore(tmp_path / "metadata.sqlite3", initialize=True)
    document = make_document("default", "wiki/page.md", "hash-1")
    chunk = make_chunk("default", document.document_id, document.path)
    store.apply_metadata_revision(index_revision="metadata-1", documents=[document], chunks=[chunk], tombstones=[])
    return store, document.document_id, chunk.chunk_id


def _keyword_hit(document_id: str, chunk_id: str, rank: int = 1) -> KeywordHit:
    return KeywordHit(
        vault_id="default",
        document_id=document_id,
        chunk_id=chunk_id,
        rank=rank,
        score=-1.0,
        backend="memory-keyword",
        index_revision="metadata-1",
        matched_fields=("text",),
    )


def test_keyword_only_search_returns_evidence_chunk(tmp_path: Path) -> None:
    catalog = _catalog(tmp_path)
    store, document_id, chunk_id = _metadata_store(tmp_path)
    service = RetrievalService(
        catalog=catalog,
        metadata_store=store,
        keyword_index=InMemoryKeywordIndex((_keyword_hit(document_id, chunk_id),)),
        readiness=StaticReadiness(ready_report(vector_ok=False)),
    )

    response = service.search(
        query_text="Body",
        requested_scope=catalog.default_scope(),
        limit=10,
        output_format="text",
    )

    assert response.result_count == 1
    assert response.results[0].kind == "evidence_chunk"
    assert response.results[0].evidence[0].vault_id == "default"
    assert response.results[0].signals[0].kind == "keyword"
    assert response.degraded is True
    assert response.warnings[0].code == "vector_unavailable"


def test_empty_query_fails_before_candidate_lookup(tmp_path: Path) -> None:
    catalog = _catalog(tmp_path)
    store, document_id, chunk_id = _metadata_store(tmp_path)
    service = RetrievalService(
        catalog=catalog,
        metadata_store=store,
        keyword_index=InMemoryKeywordIndex((_keyword_hit(document_id, chunk_id),)),
        readiness=StaticReadiness(ready_report(vector_ok=False)),
    )

    with pytest.raises(SearchError, match="query_text is required"):
        service.search(query_text=" ", requested_scope=catalog.default_scope(), limit=10, output_format="text")


def test_keyword_and_vector_signals_merge_by_vault_chunk(tmp_path: Path) -> None:
    catalog = _catalog(tmp_path)
    store, document_id, chunk_id = _metadata_store(tmp_path)
    embeddings = DeterministicTextEmbeddings(SPEC)
    chunk = store.resolve_chunk(vault_id="default", chunk_id=chunk_id)
    assert chunk is not None
    vector = embeddings.embed((EmbeddingInput(input_id="default:chunk", text=chunk.text),))[0]
    record = VectorEmbeddingRecord(
        vector_id=stable_vector_id(vault_id="default", chunk_id=chunk_id, embedding_spec=SPEC),
        vault_id="default",
        document_id=document_id,
        chunk_id=chunk_id,
        content_scope="wiki",
        embedding=vector,
        source_chunk_hash=chunk.content_hash,
        chunker_version=chunk.chunker_version,
        metadata_index_revision="metadata-1",
        vector_index_revision="vector-1",
        backend_schema_version="memory-vector-v1",
    )
    vector_store = InMemoryVectorStore()
    vector_store.apply_vector_revision(vector_index_revision="vector-1", records=(record,), tombstones=())
    service = RetrievalService(
        catalog=catalog,
        metadata_store=store,
        keyword_index=InMemoryKeywordIndex((_keyword_hit(document_id, chunk_id),)),
        vector_store=vector_store,
        text_embeddings=embeddings,
        readiness=StaticReadiness(ready_report(vector_ok=True, vector_stale_count=0, can_embed_without_download=True)),
    )

    response = service.search(
        query_text="Body", requested_scope=catalog.default_scope(), limit=10, output_format="text"
    )

    assert response.result_count == 1
    assert tuple(signal.kind for signal in response.results[0].signals) == ("keyword", "vector")
    assert response.degraded is False


def test_vector_query_failure_degrades_with_visible_warning(tmp_path: Path) -> None:
    catalog = _catalog(tmp_path)
    store, document_id, chunk_id = _metadata_store(tmp_path)
    service = RetrievalService(
        catalog=catalog,
        metadata_store=store,
        keyword_index=InMemoryKeywordIndex((_keyword_hit(document_id, chunk_id),)),
        vector_store=FailingVectorStore(),
        text_embeddings=DeterministicTextEmbeddings(SPEC),
        readiness=StaticReadiness(ready_report(vector_ok=True, vector_stale_count=0, can_embed_without_download=True)),
    )

    response = service.search(
        query_text="Body", requested_scope=catalog.default_scope(), limit=10, output_format="text"
    )

    assert response.degraded is True
    assert any(warning.code == "vector_query_failed" for warning in response.warnings)
    assert response.result_count == 1


def test_zero_result_search_still_reports_store_revisions(tmp_path: Path) -> None:
    catalog = _catalog(tmp_path)
    store, _, _ = _metadata_store(tmp_path)
    service = RetrievalService(
        catalog=catalog,
        metadata_store=store,
        keyword_index=InMemoryKeywordIndex(()),
        readiness=StaticReadiness(ready_report(vector_ok=False)),
    )

    response = service.search(
        query_text="missing", requested_scope=catalog.default_scope(), limit=10, output_format="text"
    )

    assert response.result_count == 0
    assert {revision.kind for revision in response.store_revisions} >= {"metadata", "keyword"}
    assert all(revision.scope_key for revision in response.store_revisions)


def _multi_vault_catalog(tmp_path: Path) -> VaultCatalog:
    first = tmp_path / "first-root"
    second = tmp_path / "second-root"
    first.mkdir()
    second.mkdir()
    return VaultCatalog.from_entries(
        entries=[
            VaultCatalogEntry.from_root(vault_id="first", root_path=first, content_scopes=("wiki",)),
            VaultCatalogEntry.from_root(vault_id="second", root_path=second, content_scopes=("docs",)),
        ],
        active_vault_id="first",
    )


def _hit(vault_id: str, document_id: str, chunk_id: str, rank: int) -> KeywordHit:
    return KeywordHit(
        vault_id=vault_id,
        document_id=document_id,
        chunk_id=chunk_id,
        rank=rank,
        score=-float(rank),
        backend="memory-keyword",
        index_revision="metadata-1",
        matched_fields=("text",),
    )


def test_all_vault_search_does_not_widen_content_scopes_per_vault(tmp_path: Path) -> None:
    catalog = _multi_vault_catalog(tmp_path)
    store = SQLiteMetadataStore(tmp_path / "metadata.sqlite3", initialize=True)
    first_allowed = make_document("first", "wiki/allowed.md", "first-allowed")
    first_leak = make_document("first", "docs/leak.md", "first-leak")
    second_allowed = make_document("second", "docs/allowed.md", "second-allowed")
    second_leak = make_document("second", "wiki/leak.md", "second-leak")
    documents = [first_allowed, first_leak, second_allowed, second_leak]
    chunks = [make_chunk(document.vault_id, document.document_id, document.path) for document in documents]
    store.apply_metadata_revision(index_revision="metadata-1", documents=documents, chunks=chunks, tombstones=[])
    keyword_hits = tuple(
        _hit(chunk.vault_id, chunk.document_id, chunk.chunk_id, rank) for rank, chunk in enumerate(chunks, start=1)
    )
    content_scope_by_key = {(chunk.vault_id, chunk.chunk_id): chunk.path.split("/", 1)[0] for chunk in chunks}
    service = RetrievalService(
        catalog=catalog,
        metadata_store=store,
        keyword_index=InMemoryKeywordIndex(keyword_hits, content_scope_by_key=content_scope_by_key),
        readiness=StaticReadiness(ready_report(vector_ok=False, scope_key="first:wiki|second:docs")),
    )

    response = service.search(
        query_text="Body",
        requested_scope=catalog.scope_for_all_enabled(),
        limit=10,
        output_format="json",
    )

    assert tuple(scope.vault_ids for scope in response.actual_scopes) == (("first",), ("second",))
    assert tuple(scope.content_scopes for scope in response.actual_scopes) == (("wiki",), ("docs",))
    assert sorted(result.evidence[0].path for result in response.results) == ["docs/allowed.md", "wiki/allowed.md"]


def test_vector_stale_warning_is_attributed_to_only_the_stale_vault_scope(tmp_path: Path) -> None:
    catalog = _multi_vault_catalog(tmp_path)
    store = SQLiteMetadataStore(tmp_path / "metadata.sqlite3", initialize=True)
    first_doc = make_document("first", "wiki/allowed.md", "first")
    second_doc = make_document("second", "docs/allowed.md", "second")
    first_chunk = make_chunk("first", first_doc.document_id, first_doc.path)
    second_chunk = make_chunk("second", second_doc.document_id, second_doc.path)
    store.apply_metadata_revision(
        index_revision="metadata-1",
        documents=[first_doc, second_doc],
        chunks=[first_chunk, second_chunk],
        tombstones=[],
    )
    readiness = SearchReadinessReport(
        metadata_health=StoreHealth(
            ok=True, backend="metadata", schema_version="v1", schema_compatible=True, message="ok"
        ),
        keyword_health=StoreHealth(
            ok=True, backend="keyword", schema_version="v1", schema_compatible=True, message="ok"
        ),
        vector_health=StoreHealth(ok=True, backend="vector", schema_version="v1", schema_compatible=True, message="ok"),
        vector_stale_count=1,
        can_embed_without_download=True,
        store_revisions=(SearchStoreRevision(kind="metadata", revision="metadata-1", scope_key="first:wiki"),),
        scope_readiness=(
            SearchScopeReadiness(scope_key="first:wiki", vault_ids=("first",), vector_stale_count=1),
            SearchScopeReadiness(scope_key="second:docs", vault_ids=("second",), vector_stale_count=0),
        ),
    )
    service = RetrievalService(
        catalog=catalog,
        metadata_store=store,
        keyword_index=InMemoryKeywordIndex(
            (
                _hit("first", first_doc.document_id, first_chunk.chunk_id, 1),
                _hit("second", second_doc.document_id, second_chunk.chunk_id, 2),
            )
        ),
        readiness=StaticReadiness(readiness),
    )

    response = service.search(
        query_text="Body",
        requested_scope=catalog.scope_for_all_enabled(),
        limit=10,
        output_format="json",
    )

    stale_warning = next(warning for warning in response.warnings if warning.code == "vector_stale")
    assert stale_warning.affected_vault_ids == ("first",)
    assert stale_warning.scope_key == "first:wiki"


def test_same_chunk_id_across_vaults_does_not_collapse_keyword_vector_fusion(tmp_path: Path) -> None:
    first = tmp_path / "first-root"
    second = tmp_path / "second-root"
    first.mkdir()
    second.mkdir()
    catalog = VaultCatalog.from_entries(
        entries=[
            VaultCatalogEntry.from_root(vault_id="first", root_path=first),
            VaultCatalogEntry.from_root(vault_id="second", root_path=second),
        ],
        active_vault_id="first",
    )
    store = SQLiteMetadataStore(tmp_path / "metadata.sqlite3", initialize=True)
    first_doc = make_document("first", "wiki/same.md", "first")
    second_doc = make_document("second", "wiki/same.md", "second")
    first_chunk = replace(
        make_chunk("first", first_doc.document_id, first_doc.path), chunk_id="shared-chunk", text="GraphRAG first"
    )
    second_chunk = replace(
        make_chunk("second", second_doc.document_id, second_doc.path), chunk_id="shared-chunk", text="GraphRAG second"
    )
    store.apply_metadata_revision(
        index_revision="metadata-1",
        documents=[first_doc, second_doc],
        chunks=[first_chunk, second_chunk],
        tombstones=[],
    )
    embeddings = DeterministicTextEmbeddings(SPEC)
    vector_store = InMemoryVectorStore()
    vector_records = []
    for chunk in (first_chunk, second_chunk):
        embedding = embeddings.embed((EmbeddingInput(input_id=f"{chunk.vault_id}:{chunk.chunk_id}", text=chunk.text),))[
            0
        ]
        vector_records.append(
            VectorEmbeddingRecord(
                vector_id=stable_vector_id(vault_id=chunk.vault_id, chunk_id=chunk.chunk_id, embedding_spec=SPEC),
                vault_id=chunk.vault_id,
                document_id=chunk.document_id,
                chunk_id=chunk.chunk_id,
                content_scope="wiki",
                embedding=embedding,
                source_chunk_hash=chunk.content_hash,
                chunker_version=chunk.chunker_version,
                metadata_index_revision="metadata-1",
                vector_index_revision="vector-1",
                backend_schema_version="memory-vector-v1",
            )
        )
    vector_store.apply_vector_revision(vector_index_revision="vector-1", records=tuple(vector_records), tombstones=())
    service = RetrievalService(
        catalog=catalog,
        metadata_store=store,
        keyword_index=InMemoryKeywordIndex(
            (
                _hit("first", first_doc.document_id, "shared-chunk", 1),
                _hit("second", second_doc.document_id, "shared-chunk", 2),
            )
        ),
        vector_store=vector_store,
        text_embeddings=embeddings,
        readiness=StaticReadiness(ready_report(vector_ok=True, vector_stale_count=0, can_embed_without_download=True)),
    )

    response = service.search(
        query_text="GraphRAG",
        requested_scope=catalog.scope_for_all_enabled(),
        limit=10,
        output_format="json",
    )

    assert sorted((result.vault_id, result.evidence[0].chunk_id) for result in response.results) == [
        ("first", "shared-chunk"),
        ("second", "shared-chunk"),
    ]
    assert len({result.result_id for result in response.results}) == 2
    assert all(result.vault_id in signal.source_id for result in response.results for signal in result.signals)


def test_search_without_include_graph_does_not_call_graph_candidate_provider(tmp_path: Path) -> None:
    catalog = _catalog(tmp_path)
    store, document_id, chunk_id = _metadata_store(tmp_path)
    service = RetrievalService(
        catalog=catalog,
        metadata_store=store,
        keyword_index=InMemoryKeywordIndex((_keyword_hit(document_id, chunk_id),)),
        readiness=StaticReadiness(ready_report(vector_ok=False)),
        graph_candidate_provider=FailingGraphCandidateProvider(),
    )

    response = service.search(
        query_text="Body",
        requested_scope=catalog.default_scope(),
        limit=10,
        output_format="text",
    )

    assert response.result_count == 1
    assert tuple(signal.kind for signal in response.results[0].signals) == ("keyword",)


def test_retrieval_candidate_seam_preserves_signal_explanations(tmp_path: Path) -> None:
    catalog = _catalog(tmp_path)
    store, document_id, chunk_id = _metadata_store(tmp_path)
    graph_signal = RetrievalSignal(
        kind="graph",
        source_id=f"graph:default:rel-1:{chunk_id}",
        rank=1,
        score=0.8,
        backend="graph-projection-v1",
        index_revision="graph-1",
        explanation="GraphRAG -> Search via depends_on",
    )
    graph_provider = StaticGraphCandidateProvider(
        GraphCandidateResult(
            candidates=(
                RetrievalCandidate(
                    vault_id="default",
                    document_id=document_id,
                    chunk_id=chunk_id,
                    signals=(graph_signal,),
                ),
            ),
            warnings=(
                SearchWarning(
                    code="graph_test_warning",
                    message="graph warning",
                    severity="warning",
                    affected_vault_ids=("default",),
                ),
            ),
            store_revisions=(
                SearchStoreRevision(
                    kind="graph",
                    revision="graph-1",
                    scope_key="default:wiki:local",
                    vault_id="default",
                ),
            ),
        )
    )
    service = RetrievalService(
        catalog=catalog,
        metadata_store=store,
        keyword_index=InMemoryKeywordIndex((_keyword_hit(document_id, chunk_id),)),
        readiness=StaticReadiness(ready_report(vector_ok=False)),
        graph_candidate_provider=graph_provider,
    )

    response = service.search(
        query_text="Body",
        requested_scope=catalog.default_scope(),
        limit=10,
        output_format="text",
        include_graph=True,
    )

    assert graph_provider.calls[0]["query_text"] == "Body"
    assert response.results[0].signals[-1] == graph_signal
    assert response.results[0].signals[-1].explanation == "GraphRAG -> Search via depends_on"
    assert any(warning.code == "graph_test_warning" for warning in response.warnings)
    assert any(revision.kind == "graph" for revision in response.store_revisions)
