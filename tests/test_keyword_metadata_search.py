"""Spec 2026-11-05 §4.2.6-8, A-6: exchange metadata is searchable only through the keyword `frontmatter` column."""

from __future__ import annotations

import json
import re
from dataclasses import replace
from pathlib import Path

from tests.test_parent_key_result_grouping import (
    EDITED_FILE,
    SESSION_PATH,
    TOOL_NAMES,
    exchange_metadata,
    general_document_with_chunks,
    keyword_search,
    session_document,
    session_windows,
)
from tests.test_sqlite_metadata_store import make_chunk, make_document
from vault_graph.indexing.ingestion.chunker_selection import embedding_input_for
from vault_graph.operation.scope.vault_catalog import QueryScope
from vault_graph.storage.interfaces.keyword_index import KeywordQuery
from vault_graph.storage.local.sqlite_keyword_index import SQLiteKeywordIndex, keyword_frontmatter
from vault_graph.storage.local.sqlite_metadata_store import SQLiteMetadataStore

RAW_SCOPE = QueryScope(vault_ids=("default",), content_scopes=("raw", "wiki"))


def test_keyword_frontmatter_appends_chunk_metadata_after_document_frontmatter() -> None:
    document = session_document()
    window = session_windows(document)[0]

    value = keyword_frontmatter(document, window)

    assert value == json.dumps(document.frontmatter, sort_keys=True) + "\n" + exchange_metadata()


def test_keyword_frontmatter_of_general_chunk_is_document_frontmatter_only() -> None:
    document = replace(make_document("default", "wiki/page.md", "hash"), frontmatter={"title": "Page", "tags": ["a"]})
    chunk = make_chunk("default", document.document_id, document.path)

    assert keyword_frontmatter(document, chunk) == json.dumps(document.frontmatter, sort_keys=True)


def test_edited_file_path_finds_exchange_through_frontmatter_column_only(tmp_path: Path) -> None:
    response = keyword_search(tmp_path, EDITED_FILE)

    top_five = response.results[:5]
    assert any(":ex-1:" in result.evidence[0].chunk_id for result in top_five)
    hits = SQLiteKeywordIndex(tmp_path / "metadata.sqlite3").search(
        KeywordQuery(query_text="sqlite_keyword_index", scope=RAW_SCOPE, limit=10)
    )
    ex1_hits = [hit for hit in hits if ":ex-1:" in hit.chunk_id]
    assert len(ex1_hits) == 3
    assert all(hit.matched_fields == ("frontmatter",) for hit in ex1_hits)


def test_edited_file_path_is_not_in_window_text_or_embedding_input(tmp_path: Path) -> None:
    keyword_search(tmp_path, EDITED_FILE)
    store = SQLiteMetadataStore(tmp_path / "metadata.sqlite3")

    windows = [chunk for chunk in store.list_chunks(RAW_SCOPE) if chunk.path == SESSION_PATH]

    assert len(windows) == 4
    for window in windows:
        assert EDITED_FILE not in window.text
        assert EDITED_FILE not in embedding_input_for(window)


def test_tool_name_search_returns_no_tool_name_only_window(tmp_path: Path) -> None:
    response = keyword_search(tmp_path, "Bash")
    store = SQLiteMetadataStore(tmp_path / "metadata.sqlite3")

    assert response.results
    for result in response.results:
        chunk = store.resolve_chunk(vault_id=result.vault_id, chunk_id=result.evidence[0].chunk_id)
        assert chunk is not None
        words = set(re.findall(r"\w+", chunk.text)) - {"Tools", "user", "assistant", *TOOL_NAMES}
        assert words, f"window holds only tool names: {chunk.text!r}"


def test_general_document_keyword_hits_are_unchanged(tmp_path: Path) -> None:
    database_path = tmp_path / "metadata.sqlite3"
    store = SQLiteMetadataStore(database_path, initialize=True)
    document, chunks = general_document_with_chunks()
    store.apply_metadata_revision(index_revision="metadata-1", documents=[document], chunks=chunks, tombstones=[])

    hits = SQLiteKeywordIndex(database_path).search(KeywordQuery(query_text="frontmatter", scope=RAW_SCOPE, limit=10))

    assert [(hit.chunk_id, hit.matched_fields) for hit in hits] == [
        ("wiki-chunk-0", ("text",)),
        ("wiki-chunk-1", ("text",)),
    ]
