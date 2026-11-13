from collections.abc import Sequence
from dataclasses import replace
from pathlib import Path

import pytest

from tests.fakes.deterministic_text_embeddings import DeterministicTextEmbeddings
from tests.fakes.in_memory_keyword_index import InMemoryKeywordIndex
from tests.fakes.in_memory_vector_store import InMemoryVectorStore
from tests.fakes.search_readiness import ready_report
from tests.test_sqlite_metadata_store import make_chunk, make_document
from tests.test_vector_indexer import SPEC
from vault_graph.errors import SearchError
from vault_graph.indexing.ingestion.document_normalizer import ChunkSnapshot
from vault_graph.indexing.vector_index_adapter import stable_vector_id
from vault_graph.operation.readiness.search_readiness import SearchReadinessReport, SearchScopeReadiness
from vault_graph.operation.scope.vault_catalog import QueryScope, VaultCatalog, VaultCatalogEntry
from vault_graph.retrieval.search.context_expansion import ContextExpander
from vault_graph.retrieval.search.graph_candidates import GraphCandidateResult
from vault_graph.retrieval.search.reranker import Reranker, RerankError, RerankerUnavailableError
from vault_graph.retrieval.search.retrieval_candidate import RetrievalCandidate
from vault_graph.retrieval.search.retrieval_result import RetrievalSignal
from vault_graph.retrieval.search.retrieval_service import RetrievalService
from vault_graph.retrieval.search.search_response import SearchResponse, SearchStoreRevision, SearchWarning
from vault_graph.storage.interfaces.keyword_index import KeywordHit
from vault_graph.storage.interfaces.store_health import StoreHealth
from vault_graph.storage.interfaces.text_embeddings import EmbeddingInput, EmbeddingVector
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
        provenance_family_id=f"family:{document_id}",
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


def test_search_keeps_matched_evidence_and_reports_bounded_context(tmp_path: Path) -> None:
    catalog = _catalog(tmp_path)
    store = SQLiteMetadataStore(tmp_path / "metadata.sqlite3", initialize=True)
    document = make_document("default", "wiki/context.md", "context")
    previous = replace(
        make_chunk("default", document.document_id, document.path, chunk_id="previous", text="Previous"),
        section_path=("A",),
        document_order=0,
        content_hash="previous-hash",
    )
    matched = replace(
        make_chunk("default", document.document_id, document.path, chunk_id="matched", text="Matched"),
        section_path=("A", "B"),
        document_order=1,
        content_hash="matched-hash",
    )
    following = replace(
        make_chunk("default", document.document_id, document.path, chunk_id="following", text="Following"),
        section_path=("C",),
        document_order=2,
        content_hash="following-hash",
    )
    store.apply_metadata_revision(
        index_revision="metadata-1",
        documents=[document],
        chunks=[previous, matched, following],
        tombstones=[],
    )
    service = RetrievalService(
        catalog=catalog,
        metadata_store=store,
        keyword_index=InMemoryKeywordIndex((_keyword_hit(document.document_id, matched.chunk_id),)),
        readiness=StaticReadiness(ready_report(vector_ok=False)),
        context_expander=ContextExpander(metadata_store=store),
        context_max_tokens=1,
    )

    response = service.search(query_text="Matched", requested_scope=catalog.default_scope())

    assert response.results[0].evidence[0].chunk_id == "matched"
    assert response.results[0].matched_chunk_id == "matched"
    assert response.results[0].context_chunk_ids == ("previous",)
    assert response.results[0].context_policy_version == "parent-neighbor-v1"
    assert any(warning.code == "context_budget_omitted" for warning in response.warnings)


def test_knowledge_search_keeps_family_siblings_and_attaches_source_references(tmp_path: Path) -> None:
    """Spec 2026-11-05 §10.2 원인2: pages that only share a provenance family are separate results."""
    catalog = _catalog(tmp_path)
    store = SQLiteMetadataStore(tmp_path / "metadata.sqlite3", initialize=True)
    family_id = "family:shared"
    first_document = replace(
        make_document("default", "wiki/first.md", "first"),
        source_role="canonical_knowledge",
        provenance_family_id=family_id,
    )
    second_document = replace(
        make_document("default", "wiki/second.md", "second"),
        source_role="canonical_knowledge",
        provenance_family_id=family_id,
    )
    source_document = replace(
        make_document("default", "raw/source.md", "source"),
        source_role="raw_evidence",
        provenance_family_id=family_id,
    )
    documents = (first_document, second_document, source_document)
    chunks = tuple(
        replace(
            make_chunk("default", document.document_id, document.path, text="alpha"),
            source_role=document.source_role,
            provenance_family_id=family_id,
        )
        for document in documents
    )
    store.apply_metadata_revision(
        index_revision="metadata-1",
        documents=list(documents),
        chunks=list(chunks),
        tombstones=[],
    )
    hits = tuple(
        replace(
            _keyword_hit(document.document_id, chunk.chunk_id, rank),
            provenance_family_id=family_id,
        )
        for rank, (document, chunk) in enumerate(zip(documents[:2], chunks[:2], strict=True), start=1)
    )
    service = RetrievalService(
        catalog=catalog,
        metadata_store=store,
        keyword_index=InMemoryKeywordIndex(hits),
        readiness=StaticReadiness(ready_report(vector_ok=False)),
    )

    response = service.search(query_text="alpha", requested_scope=catalog.default_scope())

    assert [result.evidence[0].path for result in response.results] == ["wiki/first.md", "wiki/second.md"]
    assert response.result_family_duplication == 0.5
    assert all(result.provenance_family_id == family_id for result in response.results)
    assert {item.path for item in response.results[0].supporting_evidence} == {"raw/source.md"}


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


class QueryOnlyTextEmbeddings(DeterministicTextEmbeddings):
    """Fails on document embedding, so a search that embeds its query with ``embed`` fails."""

    def __init__(self) -> None:
        super().__init__(SPEC)
        self.queries: list[str] = []

    def embed(self, inputs: tuple[EmbeddingInput, ...]) -> tuple[EmbeddingVector, ...]:
        raise AssertionError("search must embed the query with embed_query")

    def embed_query(self, text: str) -> EmbeddingVector:
        self.queries.append(text)
        return DeterministicTextEmbeddings(SPEC).embed_query(text)


def test_vector_search_embeds_the_query_with_embed_query(tmp_path: Path) -> None:
    catalog = _catalog(tmp_path)
    store, document_id, chunk_id = _metadata_store(tmp_path)
    chunk = store.resolve_chunk(vault_id="default", chunk_id=chunk_id)
    assert chunk is not None
    vector = DeterministicTextEmbeddings(SPEC).embed((EmbeddingInput(input_id="default:chunk", text=chunk.text),))[0]
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
    embeddings = QueryOnlyTextEmbeddings()
    service = RetrievalService(
        catalog=catalog,
        metadata_store=store,
        keyword_index=InMemoryKeywordIndex(()),
        vector_store=vector_store,
        text_embeddings=embeddings,
        readiness=StaticReadiness(ready_report(vector_ok=True, vector_stale_count=0, can_embed_without_download=True)),
    )

    response = service.search(
        query_text="Body", requested_scope=catalog.default_scope(), limit=10, output_format="text"
    )

    assert embeddings.queries == ["Body"]
    assert response.result_count == 1
    assert tuple(signal.kind for signal in response.results[0].signals) == ("vector",)
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
        provenance_family_id=f"family:{vault_id}:{document_id}",
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


def test_refill_round_finds_a_second_document_and_trace_describes_that_round(tmp_path: Path) -> None:
    catalog = _catalog(tmp_path)
    store = SQLiteMetadataStore(tmp_path / "metadata.sqlite3", initialize=True)
    crowded = make_document("default", "wiki/crowded.md", "crowded")
    other = make_document("default", "wiki/other.md", "other")
    crowded_chunks = [
        make_chunk("default", crowded.document_id, crowded.path, chunk_id=f"crowded-{index}", text=f"c{index}")
        for index in range(20)
    ]
    other_chunk = make_chunk("default", other.document_id, other.path, chunk_id="other-0", text="other")
    store.apply_metadata_revision(
        index_revision="metadata-1",
        documents=[crowded, other],
        chunks=[*crowded_chunks, other_chunk],
        tombstones=[],
    )
    hits = tuple(
        _keyword_hit(chunk.document_id, chunk.chunk_id, rank=rank)
        for rank, chunk in enumerate([*crowded_chunks, other_chunk], start=1)
    )
    service = RetrievalService(
        catalog=catalog,
        metadata_store=store,
        keyword_index=InMemoryKeywordIndex(hits),
        readiness=StaticReadiness(ready_report(vector_ok=False)),
    )

    plain = service.search(query_text="c", requested_scope=catalog.default_scope(), limit=2)
    traced = service.search(query_text="c", requested_scope=catalog.default_scope(), limit=2, trace=True)

    assert [result.evidence[0].document_id for result in plain.results] == [crowded.document_id, other.document_id]
    assert plain.stage_trace is None
    assert traced.results == plain.results
    assert traced.stage_trace is not None
    assert traced.stage_trace.refilled is True
    assert traced.stage_trace.candidate_limit == 80
    assert len(traced.stage_trace.signal_ranks) == 21
    assert [entry.document_id for entry in traced.stage_trace.document_ranks] == [
        crowded.document_id,
        other.document_id,
    ]


class ReversingReranker:
    preset = "fake-reversing"

    def __init__(self) -> None:
        self.calls: list[tuple[str, list[str]]] = []

    def rerank(self, query: str, passages: Sequence[str]) -> list[int]:
        self.calls.append((query, list(passages)))
        return list(reversed(range(len(passages))))


class CountingMetadataStore(SQLiteMetadataStore):
    resolve_chunk_calls = 0

    def resolve_chunk(self, *, vault_id: str, chunk_id: str) -> ChunkSnapshot | None:
        self.resolve_chunk_calls += 1
        return super().resolve_chunk(vault_id=vault_id, chunk_id=chunk_id)


def _four_pages(store: SQLiteMetadataStore) -> list[ChunkSnapshot]:
    documents = [make_document("default", f"wiki/page-{index}.md", f"hash-{index}") for index in range(1, 5)]
    chunks = [
        make_chunk("default", document.document_id, document.path, chunk_id=f"chunk-{index}", text=f"text {index}")
        for index, document in enumerate(documents, start=1)
    ]
    store.apply_metadata_revision(index_revision="metadata-1", documents=documents, chunks=chunks, tombstones=[])
    return chunks


def _ranked_service(
    catalog: VaultCatalog,
    store: SQLiteMetadataStore,
    chunks: list[ChunkSnapshot],
    reranker: Reranker | None,
    *,
    reranker_config_error: str | None = None,
) -> RetrievalService:
    return RetrievalService(
        catalog=catalog,
        metadata_store=store,
        keyword_index=InMemoryKeywordIndex(
            tuple(_keyword_hit(chunk.document_id, chunk.chunk_id, rank=rank) for rank, chunk in enumerate(chunks, 1))
        ),
        readiness=StaticReadiness(ready_report(vector_ok=False)),
        reranker=reranker,
        reranker_config_error=reranker_config_error,
    )


def test_reranking_reorders_before_the_limit_and_trace_follows_the_final_order(tmp_path: Path) -> None:
    catalog = _catalog(tmp_path)
    store = SQLiteMetadataStore(tmp_path / "metadata.sqlite3", initialize=True)
    chunks = _four_pages(store)
    reranker = ReversingReranker()

    response = _ranked_service(catalog, store, chunks, reranker).search(
        query_text="text", requested_scope=catalog.default_scope(), limit=2, trace=True
    )

    # The model reverses four results. RRF with equal weights gives 1, 4, 2, 3, so page 4 makes the cut.
    assert reranker.calls == [("text", ["text 1", "text 2", "text 3", "text 4"])]
    assert [result.evidence[0].chunk_id for result in response.results] == ["chunk-1", "chunk-4"]
    assert [result.rank for result in response.results] == [1, 2]
    assert response.results[1].result_id == "default:chunk-4:rank-2"
    assert response.stage_trace is not None
    assert [entry.path for entry in response.stage_trace.document_ranks] == [
        "wiki/page-1.md",
        "wiki/page-4.md",
        "wiki/page-2.md",
        "wiki/page-3.md",
    ]
    assert [entry.rank for entry in response.stage_trace.document_ranks] == [1, 2, 3, 4]
    assert response.stage_trace.document_ranks[1].result_id == "default:chunk-4:rank-2"
    rerank = response.stage_trace.rerank
    assert rerank is not None
    assert rerank.preset == reranker.preset
    assert rerank.reranked_count == 4
    assert [(entry.before_rank, entry.model_rank, entry.rank) for entry in rerank.entries] == [
        (1, 4, 1),
        (4, 1, 2),
        (2, 3, 3),
        (3, 2, 4),
    ]


def test_search_without_reranker_keeps_the_search_order(tmp_path: Path) -> None:
    catalog = _catalog(tmp_path)
    store = SQLiteMetadataStore(tmp_path / "metadata.sqlite3", initialize=True)
    chunks = _four_pages(store)

    response = _ranked_service(catalog, store, chunks, None).search(
        query_text="text", requested_scope=catalog.default_scope(), limit=2, trace=True
    )

    assert [result.evidence[0].chunk_id for result in response.results] == ["chunk-1", "chunk-2"]
    assert response.stage_trace is not None
    assert [entry.path for entry in response.stage_trace.document_ranks] == [
        "wiki/page-1.md",
        "wiki/page-2.md",
        "wiki/page-3.md",
        "wiki/page-4.md",
    ]
    assert response.stage_trace.rerank is None


def test_reranked_search_reads_no_extra_chunks(tmp_path: Path) -> None:
    catalog = _catalog(tmp_path)
    store = CountingMetadataStore(tmp_path / "metadata.sqlite3", initialize=True)
    chunks = _four_pages(store)

    _ranked_service(catalog, store, chunks, None).search(
        query_text="text", requested_scope=catalog.default_scope(), limit=10
    )
    plain_calls = store.resolve_chunk_calls
    store.resolve_chunk_calls = 0
    _ranked_service(catalog, store, chunks, ReversingReranker()).search(
        query_text="text", requested_scope=catalog.default_scope(), limit=10
    )

    assert store.resolve_chunk_calls == plain_calls


def test_single_result_search_does_not_ask_the_reranker(tmp_path: Path) -> None:
    catalog = _catalog(tmp_path)
    store, document_id, chunk_id = _metadata_store(tmp_path)
    reranker = ReversingReranker()
    service = RetrievalService(
        catalog=catalog,
        metadata_store=store,
        keyword_index=InMemoryKeywordIndex((_keyword_hit(document_id, chunk_id),)),
        readiness=StaticReadiness(ready_report(vector_ok=False)),
        reranker=reranker,
    )

    response = service.search(query_text="Body", requested_scope=catalog.default_scope(), limit=10, trace=True)

    assert reranker.calls == []
    assert response.result_count == 1
    assert response.results[0].rank == 1


def test_evidence_mode_reranks_session_exchanges_by_their_quoted_window(tmp_path: Path) -> None:
    catalog = _catalog(tmp_path)
    store = SQLiteMetadataStore(tmp_path / "metadata.sqlite3", initialize=True)
    session = replace(make_document("default", "raw/sessions/s.md", "session"), source_role="raw_evidence")
    windows = [
        replace(
            make_chunk("default", session.document_id, session.path, chunk_id=f"window-{index}", text=f"turn {index}"),
            parent_key=f"exchange-{index}",
            section=f"question {index}",
            source_role="raw_evidence",
        )
        for index in range(1, 4)
    ]
    store.apply_metadata_revision(index_revision="metadata-1", documents=[session], chunks=windows, tombstones=[])
    reranker = ReversingReranker()
    service = _ranked_service(catalog, store, windows, reranker)

    response = service.search(query_text="turn", requested_scope=catalog.default_scope(), limit=10, mode="evidence")

    assert reranker.calls == [("turn", ["turn 1", "turn 2", "turn 3"])]
    # Three reversed results with equal weights: 1 and 3 tie above 2, and search rank 1 wins the tie.
    assert [result.evidence[0].chunk_id for result in response.results] == ["window-1", "window-3", "window-2"]
    assert [result.rank for result in response.results] == [1, 2, 3]


class FailingReranker:
    """Raises a queued error per call, then reverses like `ReversingReranker` once the queue is empty."""

    preset = "fake-failing"

    def __init__(self, *errors: Exception) -> None:
        self.errors = list(errors)
        self.calls = 0

    def rerank(self, query: str, passages: Sequence[str]) -> list[int]:
        self.calls += 1
        if self.errors:
            raise self.errors.pop(0)
        return list(reversed(range(len(passages))))


RERANKER_WARNING_CODES = {"reranker_unavailable", "rerank_failed", "reranker_config_invalid"}


def _search_four(service: RetrievalService, catalog: VaultCatalog) -> SearchResponse:
    return service.search(query_text="text", requested_scope=catalog.default_scope(), limit=2, trace=True)


def _reranker_warnings(response: SearchResponse) -> list[SearchWarning]:
    """The fixture searches without vectors, so other warnings are present too."""
    return [warning for warning in response.warnings if warning.code in RERANKER_WARNING_CODES]


@pytest.mark.parametrize(
    ("error", "code"),
    [
        (RerankerUnavailableError("model files missing"), "reranker_unavailable"),
        (RerankError("inference failed"), "rerank_failed"),
    ],
)
def test_reranker_failure_keeps_the_search_order_with_one_warning(tmp_path: Path, error: Exception, code: str) -> None:
    catalog = _catalog(tmp_path)
    store = SQLiteMetadataStore(tmp_path / "metadata.sqlite3", initialize=True)
    chunks = _four_pages(store)
    reranker = FailingReranker(error)
    service = _ranked_service(catalog, store, chunks, reranker)

    failed = _search_four(service, catalog)
    retried = _search_four(service, catalog)

    assert [result.evidence[0].chunk_id for result in failed.results] == ["chunk-1", "chunk-2"]
    assert [warning.code for warning in _reranker_warnings(failed)] == [code]
    assert failed.stage_trace is not None
    assert failed.stage_trace.rerank is None
    # The failure applies to that query only: the next query asks the model again.
    assert reranker.calls == 2
    assert [result.evidence[0].chunk_id for result in retried.results] == ["chunk-1", "chunk-4"]
    assert _reranker_warnings(retried) == []


def test_unavailable_warning_names_the_use_command(tmp_path: Path) -> None:
    catalog = _catalog(tmp_path)
    store = SQLiteMetadataStore(tmp_path / "metadata.sqlite3", initialize=True)
    chunks = _four_pages(store)
    service = _ranked_service(catalog, store, chunks, FailingReranker(RerankerUnavailableError("missing")))

    response = _search_four(service, catalog)

    assert "vg reranker use fake-failing" in _reranker_warnings(response)[0].message


def test_reranker_config_error_searches_without_reranking_and_warns(tmp_path: Path) -> None:
    catalog = _catalog(tmp_path)
    store = SQLiteMetadataStore(tmp_path / "metadata.sqlite3", initialize=True)
    chunks = _four_pages(store)
    service = _ranked_service(catalog, store, chunks, None, reranker_config_error="unknown model 'nope'")

    response = _search_four(service, catalog)

    assert [result.evidence[0].chunk_id for result in response.results] == ["chunk-1", "chunk-2"]
    assert [warning.code for warning in _reranker_warnings(response)] == ["reranker_config_invalid"]
    assert "unknown model 'nope'" in _reranker_warnings(response)[0].message
