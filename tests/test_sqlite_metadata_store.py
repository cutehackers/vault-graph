from pathlib import Path

from vault_graph.ingestion.document_normalizer import ChunkSnapshot, DocumentSnapshot
from vault_graph.storage.local.sqlite_metadata_store import SQLiteMetadataStore


def make_document(vault_id: str, path: str, content_hash: str) -> DocumentSnapshot:
    return DocumentSnapshot(
        vault_id=vault_id,
        document_id=f"{vault_id}:{path}",
        path=path,
        kind=path.split("/", 1)[0],
        frontmatter={},
        frontmatter_hash="frontmatter",
        content_hash=content_hash,
        raw_sha256=f"raw:{content_hash}",
        parser_version="parser",
        last_seen_at="2026-06-05T00:00:00+00:00",
        last_indexed_at=None,
        vault_revision=None,
        index_revision=None,
    )


def make_chunk(vault_id: str, document_id: str, path: str) -> ChunkSnapshot:
    return ChunkSnapshot(
        vault_id=vault_id,
        chunk_id=f"{vault_id}:{path}:chunk",
        document_id=document_id,
        path=path,
        section="Section",
        anchor="section",
        text="Body",
        token_count=1,
        content_hash="chunk",
        chunker_version="chunker",
        index_revision=None,
    )


def test_store_upserts_and_resolves_document(tmp_path: Path) -> None:
    store = SQLiteMetadataStore(tmp_path / "metadata.sqlite3", initialize=True)
    document = make_document("default", "wiki/page.md", "hash-1")
    chunk = make_chunk("default", document.document_id, document.path)

    store.apply_metadata_revision(index_revision="rev-1", documents=[document], chunks=[chunk], tombstones=[])

    resolved = store.resolve_document(document_id=document.document_id)
    assert resolved is not None
    assert resolved.vault_id == "default"
    assert resolved.path == "wiki/page.md"
    assert store.health().ok is True


def test_store_keeps_same_relative_path_separate_by_vault_id(tmp_path: Path) -> None:
    store = SQLiteMetadataStore(tmp_path / "metadata.sqlite3", initialize=True)
    first = make_document("first", "wiki/same.md", "hash-first")
    second = make_document("second", "wiki/same.md", "hash-second")

    store.apply_metadata_revision(index_revision="rev-1", documents=[first, second], chunks=[], tombstones=[])

    first_resolved = store.resolve_document(document_id=first.document_id)
    second_resolved = store.resolve_document(document_id=second.document_id)

    assert first_resolved is not None
    assert second_resolved is not None
    assert first_resolved.content_hash == "hash-first"
    assert second_resolved.content_hash == "hash-second"


def test_resolve_chunk_is_scoped_by_vault_id(tmp_path: Path) -> None:
    store = SQLiteMetadataStore(tmp_path / "metadata.sqlite3", initialize=True)
    first = make_document("first", "wiki/same.md", "hash-first")
    second = make_document("second", "wiki/same.md", "hash-second")
    shared_chunk_id = "shared-chunk"
    first_chunk = ChunkSnapshot(
        vault_id=first.vault_id,
        chunk_id=shared_chunk_id,
        document_id=first.document_id,
        path=first.path,
        section="First",
        anchor="first",
        text="First body",
        token_count=2,
        content_hash="first-chunk",
        chunker_version="chunker",
        index_revision=None,
    )
    second_chunk = ChunkSnapshot(
        vault_id=second.vault_id,
        chunk_id=shared_chunk_id,
        document_id=second.document_id,
        path=second.path,
        section="Second",
        anchor="second",
        text="Second body",
        token_count=2,
        content_hash="second-chunk",
        chunker_version="chunker",
        index_revision=None,
    )
    store.apply_metadata_revision(
        index_revision="rev-1",
        documents=[first, second],
        chunks=[first_chunk, second_chunk],
        tombstones=[],
    )

    resolved_first = store.resolve_chunk(vault_id="first", chunk_id=shared_chunk_id)
    resolved_second = store.resolve_chunk(vault_id="second", chunk_id=shared_chunk_id)

    assert resolved_first is not None
    assert resolved_second is not None
    assert resolved_first.content_hash == "first-chunk"
    assert resolved_second.content_hash == "second-chunk"


def test_store_tombstones_only_named_vault_and_path(tmp_path: Path) -> None:
    store = SQLiteMetadataStore(tmp_path / "metadata.sqlite3", initialize=True)
    first = make_document("first", "wiki/same.md", "hash-first")
    second = make_document("second", "wiki/same.md", "hash-second")
    store.apply_metadata_revision(index_revision="rev-1", documents=[first, second], chunks=[], tombstones=[])

    store.apply_metadata_revision(
        index_revision="rev-2",
        documents=[],
        chunks=[],
        tombstones=[("first", "wiki/same.md")],
    )

    assert store.document_state("first", "wiki/same.md").is_tombstoned is True
    assert store.document_state("second", "wiki/same.md").is_tombstoned is False


def test_store_does_not_initialize_by_default(tmp_path: Path) -> None:
    database_path = tmp_path / "metadata.sqlite3"
    store = SQLiteMetadataStore(database_path)

    assert store.list_document_states(("default",)) == ()
    assert not database_path.exists()


def test_tombstoned_document_does_not_resolve_as_fresh(tmp_path: Path) -> None:
    store = SQLiteMetadataStore(tmp_path / "metadata.sqlite3", initialize=True)
    document = make_document("default", "wiki/page.md", "hash")
    chunk = make_chunk("default", document.document_id, document.path)
    store.apply_metadata_revision(index_revision="rev-1", documents=[document], chunks=[chunk], tombstones=[])

    store.apply_metadata_revision(
        index_revision="rev-2",
        documents=[],
        chunks=[],
        tombstones=[("default", "wiki/page.md")],
    )

    assert store.resolve_document(document.document_id) is None
    assert store.resolve_chunk(vault_id="default", chunk_id=chunk.chunk_id) is None
    assert store.export_documents() == ()
