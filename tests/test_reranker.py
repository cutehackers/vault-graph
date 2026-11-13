"""Spec 2026-11-13 cross-encoder-rerank A3, A4, A5, A12: reranking reorders the top results only, by RRF."""

from collections.abc import Sequence
from dataclasses import replace
from pathlib import Path

import pytest

from tests.fakes.in_memory_keyword_index import InMemoryKeywordIndex
from tests.fakes.search_readiness import ready_report
from tests.test_retrieval_service_search import StaticReadiness
from tests.test_sqlite_metadata_store import make_chunk, make_document
from vault_graph.indexing.ingestion.document_normalizer import ChunkSnapshot, DocumentSnapshot
from vault_graph.operation.scope.vault_catalog import VaultCatalog, VaultCatalogEntry
from vault_graph.retrieval.search.candidate_ranking import FusedCandidate
from vault_graph.retrieval.search.evidence_result_assembly import EvidenceResultAssembly
from vault_graph.retrieval.search.reranker import (
    RERANK_DEPTH,
    RERANK_WEIGHT,
    RRF_K,
    RerankError,
    blend_order,
    rerank_results,
)
from vault_graph.retrieval.search.retrieval_result import RetrievalResult, RetrievalSignal
from vault_graph.retrieval.search.retrieval_service import RetrievalService
from vault_graph.storage.interfaces.keyword_index import KeywordHit
from vault_graph.storage.interfaces.metadata_store import EvidenceReference
from vault_graph.storage.local.sqlite_metadata_store import SQLiteMetadataStore


class ReversingReranker:
    """Puts the passages in reverse order, the worst case for the search order."""

    preset = "fake-reversing"

    def __init__(self) -> None:
        self.calls: list[tuple[str, list[str]]] = []

    def rerank(self, query: str, passages: Sequence[str]) -> list[int]:
        self.calls.append((query, list(passages)))
        return list(reversed(range(len(passages))))


class BrokenReranker:
    preset = "fake-broken"

    def rerank(self, query: str, passages: Sequence[str]) -> list[int]:
        return [0] * len(passages)


def _result(vault_id: str, number: int) -> RetrievalResult:
    chunk_id = f"chunk-{number}"
    return RetrievalResult(
        result_id=f"{vault_id}:{chunk_id}:rank-{number}",
        vault_id=vault_id,
        kind="evidence_chunk",
        title=f"wiki/{number}.md",
        summary=f"summary {number}",
        rank=number,
        evidence=(
            EvidenceReference(
                vault_id=vault_id,
                document_id=f"{vault_id}:wiki/{number}.md",
                chunk_id=chunk_id,
                path=f"wiki/{number}.md",
                section=None,
                anchor=None,
                content_hash=f"hash-{number}",
                raw_sha256=f"raw-{number}",
                metadata_index_revision="metadata-1",
                vault_revision=None,
            ),
        ),
        signals=(),
        relationship_status="not_applicable",
        warnings=(),
        store_revisions=(),
    )


def _results(count: int, vault_ids: tuple[str, ...] = ("main",)) -> tuple[RetrievalResult, ...]:
    return tuple(_result(vault_ids[(number - 1) % len(vault_ids)], number) for number in range(1, count + 1))


def _passages(results: tuple[RetrievalResult, ...]) -> tuple[str, ...]:
    return tuple(f"passage {result.rank}" for result in results)


def _reversed_rrf_order(count: int) -> list[int]:
    """Search ranks in the order the RRF formula gives when the model reverses ``count`` results."""
    return sorted(
        range(1, count + 1),
        key=lambda rank: (-(1 / (RRF_K + rank) + RERANK_WEIGHT / (RRF_K + count + 1 - rank)), rank),
    )


def _chunk_numbers(results: tuple[RetrievalResult, ...]) -> list[int]:
    return [int(result.evidence[0].chunk_id.removeprefix("chunk-")) for result in results]


@pytest.mark.parametrize("count", [0, 1])
def test_one_result_or_none_does_not_ask_the_model(count: int) -> None:
    reranker = ReversingReranker()
    results = _results(count)

    reranked = rerank_results(query_text="q", results=results, passages=_passages(results), reranker=reranker)

    assert reranker.calls == []
    assert reranked.results == results
    assert reranked.trace is None


def test_fewer_results_than_depth_are_all_reranked_by_the_rrf_formula() -> None:
    reranker = ReversingReranker()
    results = _results(5)

    reranked = rerank_results(query_text="q", results=results, passages=_passages(results), reranker=reranker)

    assert reranker.calls == [("q", [f"passage {number}" for number in range(1, 6)])]
    assert _chunk_numbers(reranked.results) == _reversed_rrf_order(5)
    assert {result.evidence[0].chunk_id for result in reranked.results} == {
        result.evidence[0].chunk_id for result in results
    }
    assert [result.rank for result in reranked.results] == [1, 2, 3, 4, 5]
    assert [result.result_id for result in reranked.results] == [
        f"main:chunk-{number}:rank-{rank}" for rank, number in enumerate(_reversed_rrf_order(5), start=1)
    ]


def test_results_beyond_depth_keep_their_order_after_the_reranked_ones() -> None:
    reranker = ReversingReranker()
    results = _results(RERANK_DEPTH + 5)

    reranked = rerank_results(query_text="q", results=results, passages=_passages(results), reranker=reranker)

    assert len(reranker.calls[0][1]) == RERANK_DEPTH
    assert _chunk_numbers(reranked.results) == [
        *_reversed_rrf_order(RERANK_DEPTH),
        *range(RERANK_DEPTH + 1, RERANK_DEPTH + 6),
    ]
    assert [result.rank for result in reranked.results] == list(range(1, RERANK_DEPTH + 6))
    assert reranked.results[-1].result_id == f"main:chunk-{RERANK_DEPTH + 5}:rank-{RERANK_DEPTH + 5}"


def test_mixed_vault_results_keep_their_vault() -> None:
    results = _results(6, vault_ids=("personal", "team"))
    vault_by_chunk = {result.evidence[0].chunk_id: result.vault_id for result in results}

    reranked = rerank_results(
        query_text="q", results=results, passages=_passages(results), reranker=ReversingReranker()
    )

    assert _chunk_numbers(reranked.results) == _reversed_rrf_order(6)
    for result in reranked.results:
        assert result.vault_id == vault_by_chunk[result.evidence[0].chunk_id]
        assert result.evidence[0].vault_id == result.vault_id
        assert result.result_id.startswith(f"{result.vault_id}:")


def test_blend_follows_the_rrf_formula_and_keeps_search_order_on_ties() -> None:
    # The model swaps the first two. With weight 1 their scores are equal, so search rank 1 stays first.
    assert blend_order([2, 1, 3], k=60, weight=1.0) == [0, 1, 2]
    # With weight 2 the model's choice wins: 1/61 + 2/62 < 1/62 + 2/61.
    assert blend_order([2, 1, 3], k=60, weight=2.0) == [1, 0, 2]
    # Small k: search rank 3 that the model puts first passes search rank 2 that the model puts last.
    assert blend_order([2, 3, 1], k=10, weight=1.0) == [0, 2, 1]


def test_trace_records_ranks_before_and_from_the_model() -> None:
    results = _results(3)

    reranked = rerank_results(
        query_text="q", results=results, passages=_passages(results), reranker=ReversingReranker()
    )

    assert reranked.trace is not None
    assert reranked.trace.preset == "fake-reversing"
    assert reranked.trace.reranked_count == 3
    assert reranked.trace.elapsed_seconds >= 0
    assert [(entry.rank, entry.before_rank, entry.model_rank) for entry in reranked.trace.entries] == [
        (1, 1, 3),
        (2, 3, 1),
        (3, 2, 2),
    ]
    assert [entry.result_id for entry in reranked.trace.entries] == [result.result_id for result in reranked.results]


def test_model_output_that_is_not_an_order_raises_rerank_error() -> None:
    results = _results(3)

    with pytest.raises(RerankError):
        rerank_results(query_text="q", results=results, passages=_passages(results), reranker=BrokenReranker())


def _catalog(tmp_path: Path) -> VaultCatalog:
    root = tmp_path / "vault"
    root.mkdir()
    return VaultCatalog.from_entries(
        entries=[VaultCatalogEntry.from_root(vault_id="default", root_path=root)], active_vault_id="default"
    )


def _keyword_hit(chunk: ChunkSnapshot, rank: int) -> KeywordHit:
    return KeywordHit(
        vault_id=chunk.vault_id,
        document_id=chunk.document_id,
        chunk_id=chunk.chunk_id,
        rank=rank,
        score=-float(10 - rank),
        backend="memory-keyword",
        index_revision="metadata-1",
        matched_fields=("text",),
        provenance_family_id=chunk.provenance_family_id,
    )


def _titled_pages(store: SQLiteMetadataStore) -> tuple[list[DocumentSnapshot], list[ChunkSnapshot]]:
    titles = ["Graph Home", "Vault catalog", "Search readiness", "Context pack"]
    documents = [
        replace(make_document("default", f"wiki/page-{index}.md", f"hash-{index}"), frontmatter={"title": title})
        for index, title in enumerate(titles)
    ]
    chunks = [
        make_chunk("default", document.document_id, document.path, chunk_id=f"chunk-{index}", text=f"body {index}")
        for index, document in enumerate(documents)
    ]
    store.apply_metadata_revision(index_revision="metadata-1", documents=documents, chunks=chunks, tombstones=[])
    return documents, chunks


def test_exact_title_query_follows_the_rrf_formula_when_the_model_reverses(tmp_path: Path) -> None:
    catalog = _catalog(tmp_path)
    store = SQLiteMetadataStore(tmp_path / "metadata.sqlite3", initialize=True)
    documents, chunks = _titled_pages(store)
    # The titled page is the last keyword hit, so only the title signal puts it first.
    hits = tuple(_keyword_hit(chunk, rank) for rank, chunk in enumerate(reversed(chunks), start=1))

    def search(reranker: ReversingReranker | None) -> list[str]:
        service = RetrievalService(
            catalog=catalog,
            metadata_store=store,
            keyword_index=InMemoryKeywordIndex(hits),
            readiness=StaticReadiness(ready_report(vector_ok=False)),
            reranker=reranker,
        )
        response = service.search(query_text="Graph Home", requested_scope=catalog.default_scope(), limit=10)
        return [result.evidence[0].document_id for result in response.results]

    plain = search(None)
    reranked = search(ReversingReranker())

    assert plain[0] == documents[0].document_id
    assert reranked == [plain[rank - 1] for rank in _reversed_rrf_order(len(plain))]
    assert reranked[0] == documents[0].document_id


def test_rerank_passages_use_text_already_read(tmp_path: Path) -> None:
    store = SQLiteMetadataStore(tmp_path / "metadata.sqlite3", initialize=True)
    long_body = " ".join(f"word{index}" for index in range(80))
    page = replace(
        make_document("default", "wiki/page.md", "page"),
        frontmatter={"title": "Page title", "summary": "Page summary"},
    )
    card_page = replace(
        make_document("default", "wiki/card.md", "card"),
        frontmatter={"title": "Card title", "summary": "Card summary"},
    )
    session = replace(make_document("default", "raw/sessions/s.md", "session"), source_role="raw_evidence")
    body = make_chunk("default", page.document_id, page.path, chunk_id="body", text=long_body)
    card = replace(
        make_chunk("default", card_page.document_id, card_page.path, chunk_id="card", text="Card title Card summary"),
        chunk_kind="page_card",
    )
    window = replace(
        make_chunk("default", session.document_id, session.path, chunk_id="window", text="user: hi\nassistant: yo"),
        parent_key="exchange-1",
        source_role="raw_evidence",
    )
    store.apply_metadata_revision(
        index_revision="metadata-1",
        documents=[page, card_page, session],
        chunks=[body, card, window],
        tombstones=[],
    )
    candidates = tuple(
        FusedCandidate(
            vault_id="default",
            document_id=chunk.document_id,
            chunk_id=chunk.chunk_id,
            fused_score=1.0 / rank,
            best_signal_rank=rank,
            signals=(
                RetrievalSignal(
                    kind="keyword",
                    source_id=chunk.chunk_id,
                    rank=rank,
                    score=1.0,
                    backend="memory-keyword",
                    index_revision="metadata-1",
                    explanation="keyword match",
                ),
            ),
        )
        for rank, chunk in enumerate([body, card, window], start=1)
    )

    results, passages, _, _ = EvidenceResultAssembly(store).resolve_results(
        candidates=candidates, mode="all", allowed_roles=("canonical_knowledge", "raw_evidence")
    )

    passage_by_chunk = {result.evidence[0].chunk_id: passage for result, passage in zip(results, passages, strict=True)}
    assert passage_by_chunk["body"] == f"Page title\nPage summary\n{long_body}"
    assert len(long_body) > 240
    assert passage_by_chunk["card"] == "Card title Card summary"
    assert passage_by_chunk["window"] == "user: hi\nassistant: yo"


def _file_state(*roots: Path) -> dict[str, tuple[int, int]]:
    return {
        str(path): (path.stat().st_mtime_ns, path.stat().st_size) for root in roots for path in sorted(root.rglob("*"))
    }


def test_reranked_search_writes_nothing(tmp_path: Path) -> None:
    catalog = _catalog(tmp_path)
    graph_home = tmp_path / "graph-home"
    models_dir = tmp_path / "models"
    graph_home.mkdir()
    models_dir.mkdir()
    (models_dir / "model.onnx").write_bytes(b"fake")
    store = SQLiteMetadataStore(graph_home / "metadata.sqlite3", initialize=True)
    _, chunks = _titled_pages(store)
    hits = tuple(_keyword_hit(chunk, rank) for rank, chunk in enumerate(chunks, start=1))

    def search(reranker: ReversingReranker | None) -> None:
        RetrievalService(
            catalog=catalog,
            metadata_store=store,
            keyword_index=InMemoryKeywordIndex(hits),
            readiness=StaticReadiness(ready_report(vector_ok=False)),
            reranker=reranker,
        ).search(query_text="body", requested_scope=catalog.default_scope(), limit=10)

    search(None)
    before = _file_state(tmp_path / "vault", graph_home, models_dir)
    reranker = ReversingReranker()
    search(reranker)

    assert reranker.calls
    assert _file_state(tmp_path / "vault", graph_home, models_dir) == before
