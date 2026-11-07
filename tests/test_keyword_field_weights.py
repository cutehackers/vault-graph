"""Spec 2026-11-05 §10.2 원인5: per-column bm25 weights, a slim frontmatter column and the keyword rebuild."""

from __future__ import annotations

import sqlite3
from dataclasses import replace
from pathlib import Path

from tests.test_sqlite_metadata_store import make_chunk, make_document
from vault_graph.indexing.ingestion.document_normalizer import ChunkSnapshot, DocumentSnapshot
from vault_graph.operation.scope.vault_catalog import QueryScope
from vault_graph.storage.interfaces.keyword_index import KeywordQuery
from vault_graph.storage.local.sqlite_keyword_index import (
    KEYWORD_COLUMN_WEIGHTS,
    KEYWORD_SCHEMA_VERSION,
    SQLiteKeywordIndex,
    keyword_aliases,
    keyword_frontmatter,
)
from vault_graph.storage.local.sqlite_metadata_store import SQLiteMetadataStore

SCOPE = QueryScope(vault_ids=("default",), content_scopes=("wiki",))


def _page(path: str, frontmatter: dict[str, object]) -> DocumentSnapshot:
    return replace(make_document("default", path, f"hash:{path}"), frontmatter=frontmatter)


def _store(tmp_path: Path, pages: list[tuple[DocumentSnapshot, str]]) -> SQLiteKeywordIndex:
    database_path = tmp_path / "metadata.sqlite3"
    store = SQLiteMetadataStore(database_path, initialize=True)
    chunks = [make_chunk("default", page.document_id, page.path, text=text) for page, text in pages]
    store.apply_metadata_revision(
        index_revision="metadata-1", documents=[page for page, _ in pages], chunks=chunks, tombstones=[]
    )
    return SQLiteKeywordIndex(database_path)


def _ranked_paths(index: SQLiteKeywordIndex, query_text: str) -> list[str]:
    hits = index.search(KeywordQuery(query_text=query_text, scope=SCOPE, limit=10))
    return [hit.document_id.split(":", 1)[1] for hit in hits]


def test_column_weights_favor_names_over_body() -> None:
    weights = dict(KEYWORD_COLUMN_WEIGHTS)

    assert tuple(weights) == ("path", "section", "title", "aliases", "frontmatter", "text")
    assert weights["title"] == weights["aliases"] == 10.0
    assert weights["path"] == 5.0
    assert weights["section"] == weights["frontmatter"] == weights["text"] == 1.0


def test_title_match_ranks_above_body_match(tmp_path: Path) -> None:
    index = _store(
        tmp_path,
        [
            (_page("wiki/body.md", {"title": "Notes"}), "fusion fusion fusion ranking notes"),
            (_page("wiki/titled.md", {"title": "Fusion"}), "a long page body about many other topics and words"),
        ],
    )

    assert _ranked_paths(index, "fusion") == ["wiki/titled.md", "wiki/body.md"]


def test_alias_match_ranks_above_body_match(tmp_path: Path) -> None:
    index = _store(
        tmp_path,
        [
            (_page("wiki/body.md", {"title": "Notes"}), "rrf rrf rrf merges ranked lists"),
            (
                _page("wiki/aliased.md", {"title": "Reciprocal Rank Fusion", "aliases": ["RRF"]}),
                "a long page body about many other topics and words",
            ),
        ],
    )

    hits = index.search(KeywordQuery(query_text="RRF", scope=SCOPE, limit=10))

    assert [hit.document_id.split(":", 1)[1] for hit in hits] == ["wiki/aliased.md", "wiki/body.md"]
    assert hits[0].matched_fields == ("aliases",)


def test_file_name_match_ranks_above_body_match(tmp_path: Path) -> None:
    index = _store(
        tmp_path,
        [
            (_page("wiki/notes.md", {"title": "Notes"}), "chroma chroma chroma stores vectors"),
            (_page("wiki/chroma.md", {"title": "Vector store"}), "a long page body about many other topics and words"),
        ],
    )

    assert _ranked_paths(index, "chroma") == ["wiki/chroma.md", "wiki/notes.md"]


def test_keyword_frontmatter_keeps_only_tags_and_summary() -> None:
    document = _page(
        "wiki/page.md",
        {
            "title": "Page",
            "aliases": ["Alias"],
            "tags": ["retrieval", "ranking"],
            "summary": "How pages are ranked.",
            "related": ["wiki/unrelated-neighbor"],
            "session_id": "6b689ea0",
        },
    )
    chunk = make_chunk("default", document.document_id, document.path)

    assert keyword_frontmatter(document, chunk) == "retrieval ranking\nHow pages are ranked."
    assert keyword_aliases(document) == "Alias"


def test_keyword_frontmatter_appends_chunk_keyword_metadata() -> None:
    document = _page("raw/sessions/s.md", {"session_id": "6b689ea0", "project": "vault-graph"})
    chunk = replace(make_chunk("default", document.document_id, document.path), keyword_metadata="files: a.py")

    assert keyword_frontmatter(document, chunk) == "files: a.py"


def test_frontmatter_fields_outside_the_slim_set_are_not_searchable(tmp_path: Path) -> None:
    index = _store(
        tmp_path,
        [(_page("wiki/page.md", {"title": "Page", "related": ["wiki/neighbor"], "owner": "agent"}), "Body")],
    )

    assert _ranked_paths(index, "neighbor") == []
    assert _ranked_paths(index, "agent") == []


def _old_schema_store(database_path: Path, pages: list[tuple[DocumentSnapshot, ChunkSnapshot]]) -> None:
    """A store as `sqlite-keyword-v2` wrote it: no aliases column and the full frontmatter JSON."""
    store = SQLiteMetadataStore(database_path, initialize=True)
    store.apply_metadata_revision(
        index_revision="metadata-1",
        documents=[page for page, _ in pages],
        chunks=[chunk for _, chunk in pages],
        tombstones=[],
    )
    with sqlite3.connect(database_path) as connection:
        connection.executescript(
            """
            DROP TABLE keyword_chunks;
            DELETE FROM keyword_rows;
            CREATE VIRTUAL TABLE keyword_chunks USING fts5(
              path, section, title, frontmatter, text,
              content='', contentless_delete=1, tokenize='unicode61'
            );
            UPDATE keyword_projection_metadata SET value = 'sqlite-keyword-v2' WHERE key = 'schema_version';
            """
        )


def test_old_keyword_schema_is_reported_until_a_writable_open_rebuilds_it(tmp_path: Path) -> None:
    database_path = tmp_path / "metadata.sqlite3"
    page = _page("wiki/fusion.md", {"title": "Fusion", "aliases": ["RRF"], "tags": ["ranking"]})
    chunk = replace(make_chunk("default", page.document_id, page.path, text="Body text"), index_revision="metadata-1")
    _old_schema_store(database_path, [(page, chunk)])
    index = SQLiteKeywordIndex(database_path)

    assert index.health().schema_compatible is False

    SQLiteMetadataStore(database_path, initialize=True)

    health = index.health()
    assert (health.ok, health.schema_compatible, health.schema_version) == (True, True, KEYWORD_SCHEMA_VERSION)
    hits = index.search(KeywordQuery(query_text="RRF", scope=SCOPE, limit=10))
    assert [(hit.chunk_id, hit.matched_fields, hit.index_revision) for hit in hits] == [
        (chunk.chunk_id, ("aliases",), "metadata-1")
    ]
    assert _ranked_paths(index, "ranking") == ["wiki/fusion.md"]
    assert _ranked_paths(index, "Body") == ["wiki/fusion.md"]


def test_rebuild_runs_once_and_keeps_rows_of_later_revisions(tmp_path: Path) -> None:
    database_path = tmp_path / "metadata.sqlite3"
    page = _page("wiki/fusion.md", {"title": "Fusion"})
    _old_schema_store(database_path, [(page, make_chunk("default", page.document_id, page.path))])
    store = SQLiteMetadataStore(database_path, initialize=True)
    other = _page("wiki/other.md", {"title": "Other"})
    store.apply_metadata_revision(
        index_revision="metadata-2",
        documents=[other],
        chunks=[make_chunk("default", other.document_id, other.path)],
        tombstones=[],
    )

    SQLiteMetadataStore(database_path, initialize=True)

    index = SQLiteKeywordIndex(database_path)
    assert sorted(_ranked_paths(index, "Body")) == ["wiki/fusion.md", "wiki/other.md"]
    with sqlite3.connect(database_path) as connection:
        count = connection.execute("SELECT COUNT(*) FROM keyword_rows").fetchone()[0]
    assert count == 2


def test_hygiene_report_names_the_current_keyword_schema_version() -> None:
    from vault_graph.operation.diagnostics import projection_hygiene_service
    from vault_graph.storage.local import sqlite_keyword_index

    assert projection_hygiene_service.KEYWORD_SCHEMA_VERSION == sqlite_keyword_index.KEYWORD_SCHEMA_VERSION
