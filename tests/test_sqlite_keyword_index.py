from pathlib import Path

from tests.test_sqlite_metadata_store import make_chunk, make_document
from vault_graph.ingestion.vault_catalog import QueryScope
from vault_graph.storage.interfaces.keyword_index import KeywordQuery
from vault_graph.storage.local.sqlite_keyword_index import SQLiteKeywordIndex
from vault_graph.storage.local.sqlite_metadata_store import SQLiteMetadataStore


def test_keyword_search_returns_current_chunk_candidates(tmp_path: Path) -> None:
    database_path = tmp_path / "metadata.sqlite3"
    metadata_store = SQLiteMetadataStore(database_path, initialize=True)
    document = make_document("default", "wiki/page.md", "hash-1")
    chunk = make_chunk("default", document.document_id, document.path)
    metadata_store.apply_metadata_revision(
        index_revision="metadata-1", documents=[document], chunks=[chunk], tombstones=[]
    )
    keyword_index = SQLiteKeywordIndex(database_path)

    hits = keyword_index.search(
        KeywordQuery(query_text="Body", scope=QueryScope(vault_ids=("default",), content_scopes=("wiki",)), limit=10)
    )

    assert tuple((hit.vault_id, hit.document_id, hit.chunk_id) for hit in hits) == (
        ("default", document.document_id, chunk.chunk_id),
    )
    assert hits[0].backend == "sqlite-fts5"
    assert hits[0].index_revision == "metadata-1"
    assert hits[0].matched_fields == ("text",)
    assert keyword_index.index_revision(QueryScope(vault_ids=("default",), content_scopes=("wiki",))) == "metadata-1"


def test_keyword_search_filters_vault_before_limit(tmp_path: Path) -> None:
    database_path = tmp_path / "metadata.sqlite3"
    metadata_store = SQLiteMetadataStore(database_path, initialize=True)
    first = make_document("first", "wiki/same.md", "hash-first")
    second = make_document("second", "wiki/same.md", "hash-second")
    first_chunk = make_chunk("first", first.document_id, first.path)
    second_chunk = make_chunk("second", second.document_id, second.path)
    metadata_store.apply_metadata_revision(
        index_revision="metadata-1",
        documents=[first, second],
        chunks=[first_chunk, second_chunk],
        tombstones=[],
    )
    keyword_index = SQLiteKeywordIndex(database_path)

    hits = keyword_index.search(
        KeywordQuery(query_text="Body", scope=QueryScope(vault_ids=("second",), content_scopes=("wiki",)), limit=1)
    )

    assert tuple(hit.vault_id for hit in hits) == ("second",)


def test_keyword_search_filters_content_scope_before_limit(tmp_path: Path) -> None:
    database_path = tmp_path / "metadata.sqlite3"
    metadata_store = SQLiteMetadataStore(database_path, initialize=True)
    raw_doc = make_document("default", "raw/source.md", "hash-raw")
    wiki_doc = make_document("default", "wiki/page.md", "hash-wiki")
    metadata_store.apply_metadata_revision(
        index_revision="metadata-1",
        documents=[raw_doc, wiki_doc],
        chunks=[
            make_chunk("default", raw_doc.document_id, raw_doc.path),
            make_chunk("default", wiki_doc.document_id, wiki_doc.path),
        ],
        tombstones=[],
    )
    keyword_index = SQLiteKeywordIndex(database_path)

    hits = keyword_index.search(
        KeywordQuery(query_text="Body", scope=QueryScope(vault_ids=("default",), content_scopes=("wiki",)), limit=1)
    )

    assert tuple(hit.document_id for hit in hits) == (wiki_doc.document_id,)


def test_tombstoned_documents_are_removed_from_keyword_projection(tmp_path: Path) -> None:
    database_path = tmp_path / "metadata.sqlite3"
    metadata_store = SQLiteMetadataStore(database_path, initialize=True)
    document = make_document("default", "wiki/page.md", "hash-1")
    chunk = make_chunk("default", document.document_id, document.path)
    metadata_store.apply_metadata_revision(
        index_revision="metadata-1", documents=[document], chunks=[chunk], tombstones=[]
    )
    metadata_store.apply_metadata_revision(
        index_revision="metadata-2",
        documents=[],
        chunks=[],
        tombstones=[("default", "wiki/page.md")],
    )
    keyword_index = SQLiteKeywordIndex(database_path)

    hits = keyword_index.search(
        KeywordQuery(query_text="Body", scope=QueryScope(vault_ids=("default",), content_scopes=("wiki",)), limit=10)
    )

    assert hits == ()


def test_missing_keyword_projection_health_is_visible(tmp_path: Path) -> None:
    keyword_index = SQLiteKeywordIndex(tmp_path / "missing.sqlite3")

    health = keyword_index.health()

    assert health.ok is False
    assert health.schema_compatible is False
    assert "not initialized" in health.message


def test_keyword_schema_version_mismatch_is_visible(tmp_path: Path) -> None:
    database_path = tmp_path / "metadata.sqlite3"
    metadata_store = SQLiteMetadataStore(database_path, initialize=True)
    with metadata_store.connect_for_tests() as connection:
        connection.execute(
            """
            UPDATE keyword_projection_metadata
            SET value = 'old-version'
            WHERE key = 'schema_version'
            """
        )
    keyword_index = SQLiteKeywordIndex(database_path)

    health = keyword_index.health()

    assert health.ok is False
    assert health.schema_compatible is False
    assert "schema version mismatch" in health.message
