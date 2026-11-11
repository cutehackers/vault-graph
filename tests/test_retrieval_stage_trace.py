"""Spec 2026-11-11 §4.1.2: a search can report each stage's ranks so the evaluation tool can tell a candidate
loss (the answer is in no signal's list) from a rank loss (it is a candidate but folds below the cut)."""

from dataclasses import replace
from pathlib import Path

from tests.fakes.deterministic_text_embeddings import DeterministicTextEmbeddings
from tests.fakes.in_memory_keyword_index import InMemoryKeywordIndex
from tests.fakes.in_memory_vector_store import InMemoryVectorStore
from tests.fakes.search_readiness import ready_report
from tests.test_retrieval_service_search import StaticGraphCandidateProvider, StaticReadiness
from tests.test_sqlite_metadata_store import make_chunk, make_document
from tests.test_vector_indexer import SPEC
from vault_graph.operation.scope.vault_catalog import VaultCatalog, VaultCatalogEntry
from vault_graph.retrieval.search.graph_candidates import GraphCandidateResult
from vault_graph.retrieval.search.retrieval_candidate import RetrievalCandidate
from vault_graph.retrieval.search.retrieval_result import RetrievalSignal
from vault_graph.retrieval.search.retrieval_service import RetrievalService
from vault_graph.retrieval.search.search_response import SearchResponse
from vault_graph.storage.interfaces.keyword_index import KeywordHit
from vault_graph.storage.interfaces.vector_store import VectorHit, VectorQuery
from vault_graph.storage.local.sqlite_metadata_store import SQLiteMetadataStore

DOC_A = "default:wiki/a.md"
DOC_B = "default:wiki/b.md"
DOC_C = "default:wiki/c.md"


class StaticVectorStore(InMemoryVectorStore):
    def __init__(self, hits: tuple[VectorHit, ...]) -> None:
        super().__init__()
        self._hits = hits

    def search(self, query: VectorQuery) -> tuple[VectorHit, ...]:
        return self._hits[: query.limit]


def _keyword_hit(document_id: str, chunk_id: str, rank: int) -> KeywordHit:
    return KeywordHit(
        vault_id="default",
        document_id=document_id,
        chunk_id=chunk_id,
        rank=rank,
        score=-float(10 - rank),
        backend="memory-keyword",
        index_revision="metadata-1",
        matched_fields=("text",),
        provenance_family_id=f"family:{document_id}",
    )


def _vector_hit(document_id: str, chunk_id: str, rank: int) -> VectorHit:
    return VectorHit(
        vector_id=f"vector-{chunk_id}",
        vault_id="default",
        document_id=document_id,
        chunk_id=chunk_id,
        content_scope="wiki",
        score=1.0 - rank / 10,
        rank=rank,
        embedding_spec=SPEC,
        metadata_index_revision="metadata-1",
        vector_index_revision="vector-1",
        backend="memory-vector",
    )


def _graph_candidate(document_id: str, chunk_id: str, rank: int) -> RetrievalCandidate:
    return RetrievalCandidate(
        vault_id="default",
        document_id=document_id,
        chunk_id=chunk_id,
        signals=(
            RetrievalSignal(
                kind="graph",
                source_id=f"graph:default:rel:{chunk_id}",
                rank=rank,
                score=0.9,
                backend="graph-projection-v1",
                index_revision="graph-1",
                explanation="graph neighbour",
            ),
        ),
    )


def _service(tmp_path: Path) -> tuple[RetrievalService, VaultCatalog]:
    root = tmp_path / "default"
    root.mkdir()
    catalog = VaultCatalog.from_entries(
        entries=[VaultCatalogEntry.from_root(vault_id="default", root_path=root)],
        active_vault_id="default",
    )
    store = SQLiteMetadataStore(tmp_path / "metadata.sqlite3", initialize=True)
    documents = [make_document("default", path, path) for path in ("wiki/a.md", "wiki/b.md", "wiki/c.md")]
    chunks = [
        make_chunk("default", DOC_A, "wiki/a.md", chunk_id="a1", text="alpha one"),
        make_chunk("default", DOC_A, "wiki/a.md", chunk_id="a2", text="alpha two"),
        make_chunk("default", DOC_B, "wiki/b.md", chunk_id="b1", text="beta"),
        make_chunk("default", DOC_C, "wiki/c.md", chunk_id="c1", text="gamma"),
    ]
    store.apply_metadata_revision(index_revision="metadata-1", documents=documents, chunks=chunks, tombstones=[])
    service = RetrievalService(
        catalog=catalog,
        metadata_store=store,
        keyword_index=InMemoryKeywordIndex(
            (_keyword_hit(DOC_B, "b1", 1), _keyword_hit(DOC_A, "a1", 2), _keyword_hit(DOC_C, "c1", 3))
        ),
        vector_store=StaticVectorStore((_vector_hit(DOC_A, "a2", 1), _vector_hit(DOC_A, "a1", 2))),
        text_embeddings=DeterministicTextEmbeddings(SPEC),
        readiness=StaticReadiness(ready_report(vector_ok=True, vector_stale_count=0, can_embed_without_download=True)),
        graph_candidate_provider=StaticGraphCandidateProvider(
            GraphCandidateResult(candidates=(_graph_candidate(DOC_A, "a1", 1),), warnings=(), store_revisions=())
        ),
    )
    return service, catalog


def _search(service: RetrievalService, catalog: VaultCatalog, *, trace: bool, limit: int = 10) -> SearchResponse:
    return service.search(
        query_text="alpha",
        requested_scope=catalog.default_scope(),
        limit=limit,
        include_graph=True,
        trace=trace,
    )


def test_search_without_trace_returns_no_stage_trace(tmp_path: Path) -> None:
    service, catalog = _service(tmp_path)

    response = _search(service, catalog, trace=False)

    assert response.stage_trace is None


def test_trace_does_not_change_results_or_their_order(tmp_path: Path) -> None:
    service, catalog = _service(tmp_path)

    plain = _search(service, catalog, trace=False)
    traced = _search(service, catalog, trace=True)

    assert traced.results == plain.results
    assert replace(traced, stage_trace=None, generated_at=plain.generated_at) == plain


def test_trace_reports_each_signal_rank(tmp_path: Path) -> None:
    service, catalog = _service(tmp_path)

    trace = _search(service, catalog, trace=True).stage_trace

    assert trace is not None
    assert [(entry.kind, entry.chunk_id, entry.rank) for entry in trace.signal_ranks] == [
        ("keyword", "b1", 1),
        ("keyword", "a1", 2),
        ("keyword", "c1", 3),
        ("vector", "a2", 1),
        ("vector", "a1", 2),
        ("graph", "a1", 1),
    ]
    assert trace.signal_ranks[0].document_id == DOC_B
    assert trace.signal_ranks[0].vault_id == "default"


def test_trace_reports_fused_chunk_ranks(tmp_path: Path) -> None:
    service, catalog = _service(tmp_path)

    trace = _search(service, catalog, trace=True).stage_trace

    assert trace is not None
    assert [entry.rank for entry in trace.fused_ranks] == [1, 2, 3, 4]
    assert trace.fused_ranks[0].chunk_id == "a1"
    assert trace.fused_ranks[0].document_id == DOC_A
    assert trace.fused_ranks[-1].chunk_id == "c1"
    assert {entry.chunk_id for entry in trace.fused_ranks[1:3]} == {"a2", "b1"}
    scores = [entry.fused_score for entry in trace.fused_ranks]
    assert scores == sorted(scores, reverse=True)


def test_trace_reports_document_ranks_past_the_limit(tmp_path: Path) -> None:
    service, catalog = _service(tmp_path)

    response = _search(service, catalog, trace=True, limit=1)

    assert response.result_count == 1
    assert response.stage_trace is not None
    assert [(entry.rank, entry.document_id) for entry in response.stage_trace.document_ranks] == [
        (1, DOC_A),
        (2, DOC_B),
        (3, DOC_C),
    ]
    assert response.stage_trace.document_ranks[0].path == "wiki/a.md"
    assert response.stage_trace.document_ranks[0].result_id == response.results[0].result_id


def test_trace_writes_no_usage_record(tmp_path: Path) -> None:
    service, catalog = _service(tmp_path)

    _search(service, catalog, trace=True)

    assert not any(path.name == "usage" for path in tmp_path.rglob("*"))
