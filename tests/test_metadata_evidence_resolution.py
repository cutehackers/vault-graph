from pathlib import Path

from vault_graph.ingestion.document_normalizer import ChunkSnapshot, DocumentSnapshot
from vault_graph.storage.interfaces.metadata_store import EvidenceReference
from vault_graph.storage.local.sqlite_metadata_store import SQLiteMetadataStore


def make_document(vault_id: str, path: str, content_hash: str) -> DocumentSnapshot:
    return DocumentSnapshot(
        vault_id=vault_id,
        document_id=f"{vault_id}:{path}:document",
        path=path,
        kind=path.split("/", 1)[0],
        frontmatter={},
        frontmatter_hash="frontmatter",
        content_hash=content_hash,
        raw_sha256=f"raw:{content_hash}",
        parser_version="parser",
        last_seen_at="2026-06-08T00:00:00+00:00",
        last_indexed_at=None,
        vault_revision="vault-rev-1",
        index_revision=None,
    )


def make_chunk(document: DocumentSnapshot, text: str = "Body") -> ChunkSnapshot:
    return ChunkSnapshot(
        vault_id=document.vault_id,
        chunk_id=f"{document.vault_id}:{document.path}:chunk",
        document_id=document.document_id,
        path=document.path,
        section="Section",
        anchor="section",
        text=text,
        token_count=len(text.split()),
        content_hash=f"chunk:{document.content_hash}",
        chunker_version="chunker",
        index_revision=None,
    )


def test_resolve_chunk_evidence_joins_document_and_chunk(tmp_path: Path) -> None:
    store = SQLiteMetadataStore(tmp_path / "metadata.sqlite3", initialize=True)
    document = make_document("default", "wiki/page.md", "document-hash")
    chunk = make_chunk(document)
    store.apply_metadata_revision(index_revision="metadata-1", documents=[document], chunks=[chunk], tombstones=[])

    evidence = store.resolve_chunk_evidence(
        vault_id="default",
        document_id=document.document_id,
        chunk_id=chunk.chunk_id,
    )

    assert evidence == EvidenceReference(
        vault_id="default",
        document_id=document.document_id,
        chunk_id=chunk.chunk_id,
        path="wiki/page.md",
        section="Section",
        anchor="section",
        content_hash=chunk.content_hash,
        raw_sha256=document.raw_sha256,
        metadata_index_revision="metadata-1",
        vault_revision="vault-rev-1",
    )


def test_resolve_chunk_evidence_rejects_mismatched_ids(tmp_path: Path) -> None:
    store = SQLiteMetadataStore(tmp_path / "metadata.sqlite3", initialize=True)
    first = make_document("first", "wiki/same.md", "first-hash")
    second = make_document("second", "wiki/same.md", "second-hash")
    first_chunk = make_chunk(first)
    second_chunk = make_chunk(second)
    store.apply_metadata_revision(
        index_revision="metadata-1",
        documents=[first, second],
        chunks=[first_chunk, second_chunk],
        tombstones=[],
    )

    assert (
        store.resolve_chunk_evidence(
            vault_id="first",
            document_id=second.document_id,
            chunk_id=first_chunk.chunk_id,
        )
        is None
    )
    assert (
        store.resolve_chunk_evidence(
            vault_id="first",
            document_id=first.document_id,
            chunk_id=second_chunk.chunk_id,
        )
        is None
    )


def test_resolve_chunk_evidence_returns_none_after_tombstone(tmp_path: Path) -> None:
    store = SQLiteMetadataStore(tmp_path / "metadata.sqlite3", initialize=True)
    document = make_document("default", "wiki/page.md", "document-hash")
    chunk = make_chunk(document)
    store.apply_metadata_revision(index_revision="metadata-1", documents=[document], chunks=[chunk], tombstones=[])
    store.apply_metadata_revision(
        index_revision="metadata-2",
        documents=[],
        chunks=[],
        tombstones=[("default", "wiki/page.md")],
    )

    assert (
        store.resolve_chunk_evidence(
            vault_id="default",
            document_id=document.document_id,
            chunk_id=chunk.chunk_id,
        )
        is None
    )


def test_resolve_chunk_evidence_returns_none_for_replaced_chunk(tmp_path: Path) -> None:
    store = SQLiteMetadataStore(tmp_path / "metadata.sqlite3", initialize=True)
    document = make_document("default", "wiki/page.md", "document-hash")
    old_chunk = make_chunk(document)
    new_chunk = ChunkSnapshot(
        vault_id=document.vault_id,
        chunk_id=f"{document.vault_id}:{document.path}:new-chunk",
        document_id=document.document_id,
        path=document.path,
        section="New Section",
        anchor="new-section",
        text="New body",
        token_count=2,
        content_hash="chunk:new-document-hash",
        chunker_version="chunker",
        index_revision=None,
    )

    store.apply_metadata_revision(index_revision="metadata-1", documents=[document], chunks=[old_chunk], tombstones=[])
    store.apply_metadata_revision(index_revision="metadata-2", documents=[document], chunks=[new_chunk], tombstones=[])

    assert (
        store.resolve_chunk_evidence(
            vault_id="default",
            document_id=document.document_id,
            chunk_id=old_chunk.chunk_id,
        )
        is None
    )
    assert store.resolve_chunk_evidence(
        vault_id="default",
        document_id=document.document_id,
        chunk_id=new_chunk.chunk_id,
    ) == EvidenceReference(
        vault_id="default",
        document_id=document.document_id,
        chunk_id=new_chunk.chunk_id,
        path="wiki/page.md",
        section="New Section",
        anchor="new-section",
        content_hash="chunk:new-document-hash",
        raw_sha256=document.raw_sha256,
        metadata_index_revision="metadata-2",
        vault_revision="vault-rev-1",
    )


def test_resolve_chunk_evidence_rejects_chunk_path_mismatch(tmp_path: Path) -> None:
    store = SQLiteMetadataStore(tmp_path / "metadata.sqlite3", initialize=True)
    document = make_document("default", "wiki/page.md", "document-hash")
    chunk = ChunkSnapshot(
        vault_id=document.vault_id,
        chunk_id=f"{document.vault_id}:wiki/other.md:chunk",
        document_id=document.document_id,
        path="wiki/other.md",
        section="Other",
        anchor="other",
        text="Other body",
        token_count=2,
        content_hash="chunk:other",
        chunker_version="chunker",
        index_revision=None,
    )
    store.apply_metadata_revision(index_revision="metadata-1", documents=[document], chunks=[chunk], tombstones=[])

    assert (
        store.resolve_chunk_evidence(
            vault_id=document.vault_id,
            document_id=document.document_id,
            chunk_id=chunk.chunk_id,
        )
        is None
    )
