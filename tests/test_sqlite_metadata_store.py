from pathlib import Path

from vault_graph.ingestion.document_normalizer import ChunkSnapshot, DocumentSnapshot
from vault_graph.ingestion.vault_catalog import QueryScope
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


def make_chunk(
    vault_id: str,
    document_id: str,
    path: str,
    *,
    chunk_id: str | None = None,
    text: str = "Body",
) -> ChunkSnapshot:
    return ChunkSnapshot(
        vault_id=vault_id,
        chunk_id=chunk_id or f"{vault_id}:{path}:chunk",
        document_id=document_id,
        path=path,
        section="Section",
        anchor="section",
        text=text,
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


def test_list_document_chunks_returns_only_requested_document(tmp_path: Path) -> None:
    store = SQLiteMetadataStore(tmp_path / "metadata.sqlite3", initialize=True)
    first = make_document("default", "wiki/first.md", "hash-1")
    second = make_document("default", "wiki/second.md", "hash-2")
    first_chunk = make_chunk("default", first.document_id, first.path, chunk_id="first", text="First")
    second_chunk = make_chunk("default", second.document_id, second.path, chunk_id="second", text="Second")
    store.apply_metadata_revision(
        index_revision="rev-1",
        documents=[first, second],
        chunks=[first_chunk, second_chunk],
        tombstones=[],
    )

    chunks = store.list_document_chunks(vault_id="default", document_id=first.document_id)

    assert [chunk.chunk_id for chunk in chunks] == ["first"]
    assert chunks[0].text == "First"


def test_list_document_chunks_is_scoped_by_vault_id(tmp_path: Path) -> None:
    store = SQLiteMetadataStore(tmp_path / "metadata.sqlite3", initialize=True)
    first = make_document("first", "wiki/same.md", "hash-first")
    second = make_document("second", "wiki/same.md", "hash-second")
    first_chunk = make_chunk("first", first.document_id, first.path, chunk_id="shared", text="First")
    second_chunk = make_chunk("second", second.document_id, second.path, chunk_id="shared", text="Second")
    store.apply_metadata_revision(
        index_revision="rev-1",
        documents=[first, second],
        chunks=[first_chunk, second_chunk],
        tombstones=[],
    )

    chunks = store.list_document_chunks(vault_id="first", document_id=first.document_id)

    assert len(chunks) == 1
    assert chunks[0].vault_id == "first"
    assert chunks[0].text == "First"


def test_list_document_chunks_returns_empty_for_tombstoned_document(tmp_path: Path) -> None:
    store = SQLiteMetadataStore(tmp_path / "metadata.sqlite3", initialize=True)
    document = make_document("default", "wiki/page.md", "hash")
    chunk = make_chunk("default", document.document_id, document.path)
    store.apply_metadata_revision(index_revision="rev-1", documents=[document], chunks=[chunk], tombstones=[])
    store.apply_metadata_revision(
        index_revision="rev-2",
        documents=[],
        chunks=[],
        tombstones=[("default", document.path)],
    )

    assert store.list_document_chunks(vault_id="default", document_id=document.document_id) == ()


def test_list_document_chunks_missing_database_does_not_create_file(tmp_path: Path) -> None:
    database_path = tmp_path / "metadata.sqlite3"
    store = SQLiteMetadataStore(database_path)

    assert store.list_document_chunks(vault_id="default", document_id="missing") == ()
    assert not database_path.exists()


def test_list_document_chunks_preserves_indexed_document_order(tmp_path: Path) -> None:
    store = SQLiteMetadataStore(tmp_path / "metadata.sqlite3", initialize=True)
    document = make_document("default", "wiki/page.md", "hash")
    first_chunk = make_chunk("default", document.document_id, document.path, chunk_id="z-last-lexical", text="First")
    second_chunk = make_chunk("default", document.document_id, document.path, chunk_id="a-first-lexical", text="Second")
    store.apply_metadata_revision(
        index_revision="rev-1",
        documents=[document],
        chunks=[first_chunk, second_chunk],
        tombstones=[],
    )

    chunks = store.list_document_chunks(vault_id="default", document_id=document.document_id)

    assert [chunk.text for chunk in chunks] == ["First", "Second"]


def test_list_documents_returns_non_tombstoned_documents_for_scope(tmp_path: Path) -> None:
    store = SQLiteMetadataStore(tmp_path / "metadata.sqlite3", initialize=True)
    current = make_document("default", "wiki/current.md", "current")
    tombstoned = make_document("default", "wiki/tombstoned.md", "tombstoned")
    store.apply_metadata_revision(index_revision="rev-1", documents=[current, tombstoned], chunks=[], tombstones=[])
    store.apply_metadata_revision(
        index_revision="rev-2",
        documents=[],
        chunks=[],
        tombstones=[("default", tombstoned.path)],
    )

    documents = store.list_documents(QueryScope(vault_ids=("default",), content_scopes=("wiki",)))

    assert len(documents) == 1
    assert documents[0].document_id == current.document_id
    assert documents[0].path == current.path


def test_list_documents_preserves_document_snapshot_fields(tmp_path: Path) -> None:
    store = SQLiteMetadataStore(tmp_path / "metadata.sqlite3", initialize=True)
    document = DocumentSnapshot(
        vault_id="default",
        document_id="doc-1",
        path="wiki/page.md",
        kind="wiki",
        frontmatter={"type": "decision", "status": "accepted"},
        frontmatter_hash="frontmatter-hash",
        content_hash="content-hash",
        raw_sha256="raw-sha",
        parser_version="parser-v1",
        last_seen_at="2026-06-05T00:00:00+00:00",
        last_indexed_at="will-be-overwritten",
        vault_revision="vault-rev",
        index_revision="old-index",
    )
    store.apply_metadata_revision(index_revision="metadata-1", documents=[document], chunks=[], tombstones=[])

    listed = store.list_documents(QueryScope(vault_ids=("default",), content_scopes=("wiki",)))

    assert len(listed) == 1
    assert listed[0].vault_id == document.vault_id
    assert listed[0].document_id == document.document_id
    assert listed[0].path == document.path
    assert listed[0].kind == document.kind
    assert listed[0].frontmatter == document.frontmatter
    assert listed[0].frontmatter_hash == document.frontmatter_hash
    assert listed[0].content_hash == document.content_hash
    assert listed[0].raw_sha256 == document.raw_sha256
    assert listed[0].parser_version == document.parser_version
    assert listed[0].last_seen_at == document.last_seen_at
    assert listed[0].last_indexed_at is not None
    assert listed[0].vault_revision == document.vault_revision
    assert listed[0].index_revision == "metadata-1"


def test_list_documents_filters_by_vault_id_and_content_scope(tmp_path: Path) -> None:
    store = SQLiteMetadataStore(tmp_path / "metadata.sqlite3", initialize=True)
    main_wiki = make_document("main", "wiki/page.md", "main-wiki")
    main_docs = make_document("main", "docs/page.md", "main-docs")
    work_wiki = make_document("work", "wiki/page.md", "work-wiki")
    store.apply_metadata_revision(
        index_revision="rev-1",
        documents=[main_wiki, main_docs, work_wiki],
        chunks=[],
        tombstones=[],
    )

    documents = store.list_documents(QueryScope(vault_ids=("main",), content_scopes=("wiki",)))

    assert len(documents) == 1
    assert documents[0].document_id == main_wiki.document_id
    assert documents[0].path == main_wiki.path


def test_list_documents_orders_by_vault_path_and_document_id(tmp_path: Path) -> None:
    store = SQLiteMetadataStore(tmp_path / "metadata.sqlite3", initialize=True)
    b_doc = make_document("work", "wiki/b.md", "b")
    a_doc = make_document("main", "wiki/a.md", "a")
    c_doc = make_document("main", "wiki/c.md", "c")
    store.apply_metadata_revision(index_revision="rev-1", documents=[b_doc, c_doc, a_doc], chunks=[], tombstones=[])

    documents = store.list_documents(QueryScope(vault_ids=("work", "main"), content_scopes=("wiki",)))

    assert [(document.vault_id, document.path, document.document_id) for document in documents] == [
        ("main", "wiki/a.md", a_doc.document_id),
        ("main", "wiki/c.md", c_doc.document_id),
        ("work", "wiki/b.md", b_doc.document_id),
    ]


def test_list_documents_returns_empty_for_missing_database_without_creating_file(tmp_path: Path) -> None:
    database_path = tmp_path / "metadata.sqlite3"
    store = SQLiteMetadataStore(database_path)

    assert store.list_documents(QueryScope(vault_ids=("default",), content_scopes=("wiki",))) == ()
    assert not database_path.exists()
