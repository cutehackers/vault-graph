"""Spec 2026-11-05 §10.2 원인5: a query that names a page's title or alias lifts that page by a fixed amount."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from tests.fakes.search_readiness import ready_report
from tests.test_document_result_ranking import StaticReadiness, _catalog, _chunk, _document
from vault_graph.indexing.ingestion.document_normalizer import ChunkSnapshot, DocumentSnapshot
from vault_graph.operation.scope.vault_catalog import QueryScope
from vault_graph.retrieval.search.candidate_ranking import (
    RANK_CONSTANT,
    TITLE_CONTAINED_MIN_TERMS,
    TITLE_MATCH_CONTAINED_RANK,
    TITLE_MATCH_EXACT_RANK,
    TITLE_SIGNAL_WEIGHT,
    document_names,
    title_match_rank,
    title_signal_score,
)
from vault_graph.retrieval.search.retrieval_service import RetrievalService
from vault_graph.retrieval.search.search_response import SearchResponse
from vault_graph.storage.interfaces.keyword_index import KeywordHit, KeywordQuery
from vault_graph.storage.interfaces.store_health import StoreHealth
from vault_graph.storage.local.sqlite_metadata_store import SQLiteMetadataStore


@pytest.mark.parametrize(
    ("query_text", "names", "expected"),
    [
        # Equal after NFKC, case folding and punctuation: exact.
        ("Agent Context Pack", ("Agent Context Pack",), TITLE_MATCH_EXACT_RANK),
        ("agent-context  pack?", ("Agent Context Pack",), TITLE_MATCH_EXACT_RANK),
        # A Korean particle on either side does not matter.
        ("세션 메모리 색인을", ("세션 메모리 색인",), TITLE_MATCH_EXACT_RANK),
        # An alias counts like the title.
        ("RRF", ("Reciprocal Rank Fusion", "RRF"), TITLE_MATCH_EXACT_RANK),
        # The whole title inside a longer query, as consecutive words: contained.
        ("how does agent context pack ranking work", ("Agent Context Pack",), TITLE_MATCH_CONTAINED_RANK),
        ("세션 메모리 색인에서 창 크기", ("세션 메모리 색인",), TITLE_MATCH_CONTAINED_RANK),
        # A one-word title inside a longer query is too weak a sign.
        ("rebuild the index now", ("Index",), None),
        # Words out of order or missing: no match.
        ("pack context agent", ("Agent Context Pack",), None),
        ("agent pack", ("Agent Context Pack",), None),
        ("", ("Agent Context Pack",), None),
        ("anything", (), None),
    ],
)
def test_title_match_rank(query_text: str, names: tuple[str, ...], expected: int | None) -> None:
    assert title_match_rank(query_text, names) == expected


def test_title_signal_is_one_more_rank_fused_list() -> None:
    assert TITLE_CONTAINED_MIN_TERMS == 2
    assert (TITLE_MATCH_EXACT_RANK, TITLE_MATCH_CONTAINED_RANK) == (1, 2)
    assert TITLE_SIGNAL_WEIGHT == 1.0
    assert title_signal_score(None) == 0.0
    assert title_signal_score(1) == TITLE_SIGNAL_WEIGHT / (RANK_CONSTANT + 1)
    assert title_signal_score(2) == TITLE_SIGNAL_WEIGHT / (RANK_CONSTANT + 2)


def test_document_names_are_title_then_aliases_with_file_stem_fallback() -> None:
    titled = _document("default", "wiki/a-page.md", frontmatter={"title": "A Page", "aliases": ["AP", "", 3]})
    single_alias = _document("default", "wiki/b.md", frontmatter={"title": "B", "aliases": "Bee"})
    untitled = _document("default", "wiki/c-page.md")

    assert document_names(titled) == ("A Page", "AP", "3")
    assert document_names(single_alias) == ("B", "Bee")
    assert document_names(untitled) == ("c-page",)
    assert document_names(None) == ()


class FixedKeywordIndex:
    """Returns hits in a fixed order, so the test controls the keyword ranks."""

    def __init__(self, chunks: list[ChunkSnapshot]) -> None:
        self._chunks = chunks

    def search(self, query: KeywordQuery) -> tuple[KeywordHit, ...]:
        return tuple(
            KeywordHit(
                vault_id=chunk.vault_id,
                document_id=chunk.document_id,
                chunk_id=chunk.chunk_id,
                rank=rank,
                score=-float(10 - rank),
                backend="fixed",
                index_revision="metadata-1",
                matched_fields=("text",),
                source_role=chunk.source_role,
                provenance_family_id=chunk.provenance_family_id,
            )
            for rank, chunk in enumerate(self._chunks, start=1)
        )

    def index_revision(self, scope: QueryScope) -> str:
        return "metadata-1"

    def health(self) -> StoreHealth:
        return StoreHealth(ok=True, backend="fixed", schema_version="fixed", schema_compatible=True, message="ok")


def _search_fixed(
    tmp_path: Path, documents: list[DocumentSnapshot], chunks: list[ChunkSnapshot], query_text: str
) -> SearchResponse:
    store = SQLiteMetadataStore(tmp_path / "metadata.sqlite3", initialize=True)
    store.apply_metadata_revision(index_revision="metadata-1", documents=documents, chunks=chunks, tombstones=[])
    catalog = _catalog(tmp_path)
    service = RetrievalService(
        catalog=catalog,
        metadata_store=store,
        keyword_index=FixedKeywordIndex(chunks),
        readiness=StaticReadiness(ready_report(vector_ok=False)),
    )
    return service.search(query_text=query_text, requested_scope=catalog.scope_for_vault_ids(("default",)))


def _paths(response: SearchResponse) -> list[str]:
    return [result.evidence[0].path for result in response.results]


def test_exact_title_lifts_page_above_better_ranked_pages(tmp_path: Path) -> None:
    first = _document("default", "wiki/first.md", frontmatter={"title": "First"})
    second = _document("default", "wiki/second.md", frontmatter={"title": "Second"})
    named = _document("default", "wiki/named.md", frontmatter={"title": "Agent Context Pack"})
    chunks = [_chunk(first, 0, "a"), _chunk(second, 0, "b"), _chunk(named, 0, "c")]

    assert _paths(_search_fixed(tmp_path, [first, second, named], chunks, "Agent Context Pack")) == [
        "wiki/named.md",
        "wiki/first.md",
        "wiki/second.md",
    ]


def test_title_signal_counts_once_per_document_however_many_chunks_match(tmp_path: Path) -> None:
    # The page card and two windows of the named page all match. The title signal is added to the document
    # score once, so the order is the same as with one matching chunk.
    first = _document("default", "wiki/first.md", frontmatter={"title": "First"})
    named = _document("default", "wiki/named.md", frontmatter={"title": "Agent Context Pack"})
    card = replace(_chunk(named, 0, "Agent Context Pack"), chunk_kind="page_card")
    chunks = [_chunk(first, 0, "a"), card, _chunk(named, 1, "b"), _chunk(named, 2, "c")]

    response = _search_fixed(tmp_path, [first, named], chunks, "Agent Context Pack")
    again = tmp_path / "again"
    again.mkdir()

    assert _paths(response) == ["wiki/named.md", "wiki/first.md"]
    assert _paths(_search_fixed(again, [first, named], chunks, "Agent Context Pack")) == _paths(response)


def test_without_a_title_match_the_fused_order_stays(tmp_path: Path) -> None:
    first = _document("default", "wiki/first.md", frontmatter={"title": "First"})
    named = _document("default", "wiki/named.md", frontmatter={"title": "Agent Context Pack"})
    chunks = [_chunk(first, 0, "a"), _chunk(named, 0, "b")]

    assert _paths(_search_fixed(tmp_path, [first, named], chunks, "context")) == ["wiki/first.md", "wiki/named.md"]
