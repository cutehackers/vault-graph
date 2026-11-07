"""Stored chunk kind of wiki page chunks (spec 2026-11-05 §10.2 원인7·8)."""

from __future__ import annotations

import hashlib
import sqlite3
from dataclasses import replace
from pathlib import Path

from vault_graph.indexing.ingestion.document_models import SourceDocument
from vault_graph.indexing.ingestion.document_normalizer import DocumentNormalizer, NormalizedDocument
from vault_graph.indexing.ingestion.document_readers import MarkdownDocumentReader
from vault_graph.operation.scope.vault_catalog import QueryScope
from vault_graph.storage.local.sqlite_metadata_store import SQLiteMetadataStore

_PAGE = """---
title: Overview
summary: Map of the wiki.
---

# Overview

## Areas

The wiki covers retrieval, sessions and memory.

## Sources

- raw/sources/a.md
"""

_SCOPE = QueryScope(vault_ids=("default",), content_scopes=("wiki",))


def _normalized() -> NormalizedDocument:
    raw = _PAGE.encode("utf-8")
    source = SourceDocument(
        vault_id="default",
        root_path=Path("/vault"),
        path="wiki/overview.md",
        suffix=".md",
        raw_bytes=raw,
        raw_sha256=hashlib.sha256(raw).hexdigest(),
    )
    return DocumentNormalizer().normalize(MarkdownDocumentReader().read(source))


def _store(tmp_path: Path) -> tuple[SQLiteMetadataStore, NormalizedDocument]:
    store = SQLiteMetadataStore(tmp_path / "metadata.sqlite3", initialize=True)
    normalized = _normalized()
    store.apply_metadata_revision(
        index_revision="metadata-1",
        documents=[normalized.document],
        chunks=list(normalized.chunks),
        tombstones=[],
    )
    return store, normalized


def test_chunk_kind_and_hub_flag_round_trip(tmp_path: Path) -> None:
    store, normalized = _store(tmp_path)
    expected = tuple(replace(chunk, index_revision="metadata-1") for chunk in normalized.chunks)

    listed = store.list_chunks(_SCOPE)
    by_document = store.list_document_chunks(vault_id="default", document_id=normalized.document.document_id)
    resolved = tuple(store.resolve_chunk(vault_id="default", chunk_id=chunk.chunk_id) for chunk in expected)

    assert [chunk.chunk_kind for chunk in expected] == ["page_card", "body", "template"]
    assert listed == expected
    assert by_document == expected
    assert resolved == expected
    assert {chunk.document_kind for chunk in listed} == {"hub"}
    document = store.resolve_document(normalized.document.document_id)
    assert document is not None and document.document_kind == "hub"


def test_store_without_chunk_kind_column_reads_body_and_upgrades_on_writable_open(tmp_path: Path) -> None:
    _store(tmp_path)
    database_path = tmp_path / "metadata.sqlite3"
    with sqlite3.connect(database_path) as connection:
        connection.execute("ALTER TABLE chunks DROP COLUMN chunk_kind")

    reader = SQLiteMetadataStore(database_path, initialize=False)

    assert reader.health().ok is True
    assert {chunk.chunk_kind for chunk in reader.list_chunks(_SCOPE)} == {"body"}

    writer, normalized = _store(tmp_path)
    assert [chunk.chunk_kind for chunk in writer.list_chunks(_SCOPE)] == [
        chunk.chunk_kind for chunk in normalized.chunks
    ]
