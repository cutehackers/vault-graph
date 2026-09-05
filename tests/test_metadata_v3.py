from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from vault_graph.errors import MetadataStoreError
from vault_graph.ingestion.document_models import SourceLocator
from vault_graph.ingestion.document_normalizer import ChunkSnapshot, DocumentSnapshot
from vault_graph.ingestion.vault_catalog import QueryScope
from vault_graph.storage.local.sqlite_metadata_store import SCHEMA_VERSION, SQLiteMetadataStore


def _document() -> DocumentSnapshot:
    return DocumentSnapshot(
        vault_id="default",
        document_id="document-1",
        path="wiki/page.md",
        kind="wiki",
        frontmatter={"title": "Page"},
        frontmatter_hash="frontmatter",
        content_hash="document-content",
        raw_sha256="raw",
        parser_version="markdown-structural-blocks-v2",
        last_seen_at="2026-08-05T00:00:00+00:00",
        last_indexed_at=None,
        vault_revision=None,
        index_revision=None,
        format="markdown",
        reader_name="markdown",
        reader_version="markdown-reader-v2",
        extraction_options_digest="options-v2",
    )


def _chunk(document: DocumentSnapshot) -> ChunkSnapshot:
    return ChunkSnapshot(
        vault_id=document.vault_id,
        chunk_id="chunk-1",
        document_id=document.document_id,
        path=document.path,
        section="Retrieval",
        anchor="retrieval",
        text="Body",
        token_count=1,
        content_hash="chunk-content",
        chunker_version="document-block-window-v2",
        index_revision=None,
        section_path=("Architecture", "Retrieval"),
        source_locators=(
            SourceLocator(
                scheme="pdf",
                coordinates=(("page", "4"), ("block", "2")),
                start_offset=10,
                end_offset=14,
                offset_unit="char",
            ),
        ),
        document_order=3,
    )


def _make_v2_database(path: Path) -> None:
    with sqlite3.connect(path) as connection:
        connection.executescript(
            """
            CREATE TABLE documents (
              vault_id TEXT NOT NULL, document_id TEXT NOT NULL, path TEXT NOT NULL,
              kind TEXT NOT NULL, frontmatter_json TEXT NOT NULL, frontmatter_hash TEXT NOT NULL,
              content_hash TEXT NOT NULL, raw_sha256 TEXT NOT NULL, parser_version TEXT NOT NULL,
              last_seen_at TEXT NOT NULL, last_indexed_at TEXT, vault_revision TEXT,
              index_revision TEXT, source_role TEXT NOT NULL, provenance_family_id TEXT NOT NULL,
              is_tombstoned INTEGER NOT NULL DEFAULT 0, PRIMARY KEY (vault_id, path), UNIQUE (document_id)
            );
            CREATE TABLE content_blobs (blob_hash TEXT PRIMARY KEY, text TEXT NOT NULL, byte_count INTEGER NOT NULL);
            CREATE TABLE chunks (
              vault_id TEXT NOT NULL, chunk_id TEXT NOT NULL, document_id TEXT NOT NULL,
              path TEXT NOT NULL, section TEXT, anchor TEXT, blob_hash TEXT NOT NULL,
              token_count INTEGER NOT NULL, content_hash TEXT NOT NULL, chunker_version TEXT NOT NULL,
              index_revision TEXT, source_role TEXT NOT NULL, provenance_family_id TEXT NOT NULL,
              PRIMARY KEY (vault_id, chunk_id)
            );
            CREATE TABLE index_revisions (index_revision TEXT PRIMARY KEY, created_at TEXT NOT NULL);
            """
        )


def test_read_only_v2_health_is_incompatible_and_does_not_upgrade(tmp_path: Path) -> None:
    database_path = tmp_path / "metadata.sqlite3"
    _make_v2_database(database_path)
    before = database_path.read_bytes()

    health = SQLiteMetadataStore(database_path, initialize=False).health()

    assert health.schema_version == SCHEMA_VERSION
    assert health.schema_compatible is False
    assert "Run `vg index`" in health.message
    assert database_path.read_bytes() == before


def test_initialized_open_upgrades_v2_columns_idempotently(tmp_path: Path) -> None:
    database_path = tmp_path / "metadata.sqlite3"
    _make_v2_database(database_path)

    first = SQLiteMetadataStore(database_path, initialize=True)
    second = SQLiteMetadataStore(database_path, initialize=True)

    assert first.health().schema_compatible is True
    assert second.health().schema_compatible is True
    with second.connect_for_tests() as connection:
        document_columns = {str(row[1]) for row in connection.execute("PRAGMA table_info(documents)")}
        chunk_columns = {str(row[1]) for row in connection.execute("PRAGMA table_info(chunks)")}
    assert {"format", "reader_name", "reader_version", "extraction_options_digest"} <= document_columns
    assert {"section_path_json", "source_locators_json", "document_order"} <= chunk_columns


def test_section_path_locators_and_reader_lineage_round_trip(tmp_path: Path) -> None:
    store = SQLiteMetadataStore(tmp_path / "metadata.sqlite3", initialize=True)
    document = _document()
    chunk = _chunk(document)
    store.apply_metadata_revision(index_revision="metadata-1", documents=[document], chunks=[chunk], tombstones=[])

    restored = store.resolve_chunk(vault_id=document.vault_id, chunk_id=chunk.chunk_id)
    restored_document = store.resolve_document(document.document_id)

    assert restored is not None
    assert restored.section_path == chunk.section_path
    assert restored.source_locators == chunk.source_locators
    assert restored.document_order == 3
    assert restored_document is not None
    assert restored_document.reader_version == document.reader_version
    assert restored_document.extraction_options_digest == document.extraction_options_digest


def test_malformed_locator_json_fails_closed(tmp_path: Path) -> None:
    database_path = tmp_path / "metadata.sqlite3"
    store = SQLiteMetadataStore(database_path, initialize=True)
    document = _document()
    chunk = _chunk(document)
    store.apply_metadata_revision(index_revision="metadata-1", documents=[document], chunks=[chunk], tombstones=[])
    with store.connect_for_tests() as connection:
        connection.execute(
            "UPDATE chunks SET source_locators_json = ? WHERE chunk_id = ?",
            ('[{"scheme":"pdf","coordinates":[["page","4"]]}]', chunk.chunk_id),
        )

    with pytest.raises(MetadataStoreError, match="source_locators_json"):
        store.list_chunks(QueryScope(vault_ids=(document.vault_id,), content_scopes=("wiki",)))
