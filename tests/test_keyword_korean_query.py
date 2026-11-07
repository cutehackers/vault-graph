"""Spec 2026-11-05 §10.2 원인6: Korean query normalization at query time, without a new dependency."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.test_sqlite_metadata_store import make_chunk, make_document
from vault_graph.operation.scope.vault_catalog import QueryScope
from vault_graph.storage.interfaces.keyword_index import KeywordQuery
from vault_graph.storage.local.sqlite_keyword_index import QueryTerm, SQLiteKeywordIndex, query_terms
from vault_graph.storage.local.sqlite_metadata_store import SQLiteMetadataStore


@pytest.mark.parametrize(
    ("query_text", "expected"),
    [
        # A particle is stripped and a stem of three or more Hangul letters becomes a prefix term.
        ("아이디어를", (QueryTerm("아이디어", prefix=True),)),
        ("아이디어", (QueryTerm("아이디어", prefix=True),)),
        ("검색에서", (QueryTerm("검색에서", prefix=True), QueryTerm("검색", prefix=False))),
        # Stems of two letters or fewer stay exact, and the original word is kept next to them.
        ("색인을", (QueryTerm("색인을", prefix=True), QueryTerm("색인", prefix=False))),
        # A stem shorter than two letters is not stripped: "회의" is not "회" + "의".
        ("회의", (QueryTerm("회의", prefix=False),)),
        # Common verb endings.
        ("결정한", (QueryTerm("결정한", prefix=True), QueryTerm("결정", prefix=False))),
        ("정리하는", (QueryTerm("정리하는", prefix=True), QueryTerm("정리", prefix=False))),
        # Mixed tokens drop a trailing particle. Latin text never becomes a prefix term.
        ("MCP를", (QueryTerm("MCP를", prefix=False), QueryTerm("MCP", prefix=False))),
        ("vault graph", (QueryTerm("vault", prefix=False), QueryTerm("graph", prefix=False))),
        # Duplicates fold in first-seen order.
        ("세션 세션을", (QueryTerm("세션", prefix=False), QueryTerm("세션을", prefix=True))),
        ("", ()),
    ],
)
def test_query_terms_strip_particles_and_mark_hangul_prefixes(query_text: str, expected: tuple[QueryTerm, ...]) -> None:
    assert query_terms(query_text) == expected


def test_query_terms_are_deterministic() -> None:
    text = "임베딩 모델을 바꾼 결정과 아이디어를 정리하는 방법"
    assert query_terms(text) == query_terms(text)


def _index(tmp_path: Path, texts: dict[str, str]) -> SQLiteKeywordIndex:
    database_path = tmp_path / "metadata.sqlite3"
    store = SQLiteMetadataStore(database_path, initialize=True)
    documents = [make_document("default", f"wiki/{name}.md", name) for name in texts]
    chunks = [
        make_chunk("default", document.document_id, document.path, text=text)
        for document, text in zip(documents, texts.values(), strict=True)
    ]
    store.apply_metadata_revision(index_revision="metadata-1", documents=documents, chunks=chunks, tombstones=[])
    return SQLiteKeywordIndex(database_path)


def _paths(index: SQLiteKeywordIndex, query_text: str) -> set[str]:
    hits = index.search(
        KeywordQuery(
            query_text=query_text, scope=QueryScope(vault_ids=("default",), content_scopes=("wiki",)), limit=10
        )
    )
    return {hit.document_id.split(":", 1)[1] for hit in hits}


def test_particle_query_matches_bare_word_and_bare_query_matches_particle_word(tmp_path: Path) -> None:
    index = _index(
        tmp_path,
        {
            "bare": "새 아이디어 목록",
            "particle": "아이디어를 모은다",
            "other": "관계없는 문장",
        },
    )

    assert _paths(index, "아이디어를") == {"wiki/bare.md", "wiki/particle.md"}
    assert _paths(index, "아이디어") == {"wiki/bare.md", "wiki/particle.md"}


def test_two_letter_stem_matches_exact_word_only(tmp_path: Path) -> None:
    index = _index(tmp_path, {"exact": "색인 속도", "longer": "색인기 설정", "particle": "색인을 만든다"})

    assert _paths(index, "색인을") == {"wiki/exact.md", "wiki/particle.md"}


def test_prefix_term_reports_matched_field(tmp_path: Path) -> None:
    index = _index(tmp_path, {"particle": "아이디어를 모은다"})

    hits = index.search(
        KeywordQuery(
            query_text="아이디어", scope=QueryScope(vault_ids=("default",), content_scopes=("wiki",)), limit=10
        )
    )

    assert hits[0].matched_fields == ("text",)
