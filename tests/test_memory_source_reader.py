from __future__ import annotations

from typing import Any

import pytest

from tests.test_sqlite_metadata_store import make_chunk, make_document
from vault_graph.errors import MemoryProjectionError
from vault_graph.ingestion.document_normalizer import ChunkSnapshot, DocumentSnapshot
from vault_graph.ingestion.vault_catalog import QueryScope
from vault_graph.memory.memory_source_reader import MemorySourceReader, document_resource_kinds_for_document
from vault_graph.storage.interfaces.metadata_store import EvidenceReference


class FakeMetadataStore:
    def __init__(
        self,
        *,
        documents: tuple[DocumentSnapshot, ...] = (),
        chunks: tuple[ChunkSnapshot, ...] = (),
        missing_evidence: tuple[str, ...] = (),
    ) -> None:
        self.documents = documents
        self.chunks = chunks
        self.missing_evidence = missing_evidence
        self.list_document_scopes: list[QueryScope] = []
        self.chunk_reads: list[tuple[str, str]] = []
        self.evidence_reads: list[str] = []

    def list_documents(self, scope: QueryScope) -> tuple[DocumentSnapshot, ...]:
        self.list_document_scopes.append(scope)
        return self.documents

    def list_document_chunks(self, *, vault_id: str, document_id: str) -> tuple[ChunkSnapshot, ...]:
        self.chunk_reads.append((vault_id, document_id))
        return tuple(chunk for chunk in self.chunks if chunk.vault_id == vault_id and chunk.document_id == document_id)

    def resolve_chunk_evidence(self, *, vault_id: str, document_id: str, chunk_id: str) -> EvidenceReference | None:
        del document_id
        self.evidence_reads.append(chunk_id)
        if chunk_id in self.missing_evidence:
            return None
        chunk = next(chunk for chunk in self.chunks if chunk.vault_id == vault_id and chunk.chunk_id == chunk_id)
        return EvidenceReference(
            vault_id=chunk.vault_id,
            document_id=chunk.document_id,
            chunk_id=chunk.chunk_id,
            path=chunk.path,
            section=chunk.section,
            anchor=chunk.anchor,
            content_hash=chunk.content_hash,
            raw_sha256="raw-sha",
            metadata_index_revision=chunk.index_revision,
            vault_revision="vault-1",
        )

    def __getattr__(self, name: str) -> Any:
        raise AssertionError(f"unexpected metadata store call: {name}")


def test_list_documents_delegates_to_metadata_store() -> None:
    document = make_document("main", "wiki/page.md", "hash")
    store = FakeMetadataStore(documents=(document,))
    scope = QueryScope(vault_ids=("main",), content_scopes=("wiki",))

    documents = MemorySourceReader(metadata_store=store).list_documents(scope=scope)

    assert documents == (document,)
    assert store.list_document_scopes == [scope]


def test_read_document_loads_bounded_evidence_and_all_headings() -> None:
    document = make_document("main", "wiki/page.md", "hash")
    chunks = (
        make_chunk("main", document.document_id, document.path, chunk_id="c1", text="One"),
        make_chunk("main", document.document_id, document.path, chunk_id="c2", text="Two"),
        make_chunk("main", document.document_id, document.path, chunk_id="c3", text="Three"),
    )
    store = FakeMetadataStore(chunks=chunks)

    read = MemorySourceReader(metadata_store=store).read_document(document=document, max_evidence_chunks=2)

    assert [ref.chunk_id for ref in read.evidence] == ["c1", "c2"]
    assert [heading.chunk_id for heading in read.headings] == ["c1", "c2", "c3"]
    assert read.body_excerpt == "One"


def test_read_document_prefers_matched_heading_chunk_ids() -> None:
    document = make_document("main", "wiki/page.md", "hash")
    chunks = (
        make_chunk("main", document.document_id, document.path, chunk_id="early", text="Early"),
        make_chunk("main", document.document_id, document.path, chunk_id="late", text="Late"),
    )
    store = FakeMetadataStore(chunks=chunks)

    read = MemorySourceReader(metadata_store=store).read_document(
        document=document,
        max_evidence_chunks=1,
        preferred_chunk_ids=("late",),
    )

    assert [ref.chunk_id for ref in read.evidence] == ["late"]


def test_read_document_warns_for_unresolved_evidence() -> None:
    document = make_document("main", "wiki/page.md", "hash")
    chunk = make_chunk("main", document.document_id, document.path, chunk_id="missing", text="Body")
    store = FakeMetadataStore(chunks=(chunk,), missing_evidence=("missing",))

    read = MemorySourceReader(metadata_store=store).read_document(document=document)

    assert read.evidence == ()
    assert read.warnings[0].code == "unresolved_evidence"


def test_read_document_warns_for_document_with_no_chunks() -> None:
    document = make_document("main", "wiki/page.md", "hash")

    read = MemorySourceReader(metadata_store=FakeMetadataStore()).read_document(document=document)

    assert read.evidence == ()
    assert read.warnings[0].code == "document_has_no_chunks"


def test_read_document_body_excerpt_is_deterministic_and_capped() -> None:
    document = make_document("main", "wiki/page.md", "hash")
    text = "  " + ("x" * 400)
    chunk = make_chunk("main", document.document_id, document.path, chunk_id="chunk", text=text)

    read = MemorySourceReader(metadata_store=FakeMetadataStore(chunks=(chunk,))).read_document(document=document)

    assert read.body_excerpt == "x" * 280


def test_read_document_rejects_non_positive_evidence_limit() -> None:
    document = make_document("main", "wiki/page.md", "hash")

    with pytest.raises(MemoryProjectionError, match="invalid_memory_evidence_limit"):
        MemorySourceReader(metadata_store=FakeMetadataStore()).read_document(document=document, max_evidence_chunks=0)


def test_source_reader_has_no_scope_level_read_documents_method() -> None:
    assert not hasattr(MemorySourceReader(metadata_store=FakeMetadataStore()), "read_documents")


def test_document_resource_kinds_for_document_matches_existing_resource_classifiers() -> None:
    assert document_resource_kinds_for_document(make_document("main", "wiki/page.md", "hash")) == (
        "document",
        "page",
    )
    assert document_resource_kinds_for_document(make_document("main", "raw/source.md", "hash")) == (
        "document",
        "source",
    )
    decision = make_document("main", "wiki/decisions/use-mcp.md", "hash")
    issue = make_document("main", "wiki/issues/open.md", "hash")

    assert document_resource_kinds_for_document(decision) == ("document", "page", "decision")
    assert document_resource_kinds_for_document(issue) == ("document", "page", "issue")
