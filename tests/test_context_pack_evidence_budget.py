from __future__ import annotations

from pathlib import Path
from typing import cast

import pytest

from tests.test_sqlite_metadata_store import make_chunk, make_document
from vault_graph.context import ContextEvidenceRef, ContextPackBudget
from vault_graph.context.context_pack_builder import MetadataContextEvidenceResolver
from vault_graph.errors import ContextPackError
from vault_graph.ingestion.document_normalizer import ChunkSnapshot
from vault_graph.storage.interfaces.metadata_store import EvidenceReference, MetadataStore
from vault_graph.storage.local.sqlite_metadata_store import SQLiteMetadataStore


class RecordingMetadataStore:
    def __init__(self, *, chunk: ChunkSnapshot | None, evidence: EvidenceReference | None) -> None:
        self.chunk = chunk
        self.evidence = evidence
        self.calls: list[tuple[str, str, str | None]] = []

    def resolve_chunk(self, *, vault_id: str, chunk_id: str) -> ChunkSnapshot | None:
        self.calls.append(("resolve_chunk", vault_id, chunk_id))
        return self.chunk

    def resolve_chunk_evidence(
        self,
        *,
        vault_id: str,
        document_id: str,
        chunk_id: str,
    ) -> EvidenceReference | None:
        self.calls.append(("resolve_chunk_evidence", vault_id, chunk_id))
        return self.evidence


def make_chunk_snapshot(*, text: str = "one two three", token_count: int = 3) -> ChunkSnapshot:
    return ChunkSnapshot(
        vault_id="main",
        chunk_id="chunk-1",
        document_id="doc-1",
        path="wiki/page.md",
        section="Section",
        anchor="section",
        text=text,
        token_count=token_count,
        content_hash="chunk-hash",
        chunker_version="chunker",
        index_revision="metadata-1",
    )


def make_evidence_reference(*, metadata_index_revision: str | None = "metadata-1") -> EvidenceReference:
    return EvidenceReference(
        vault_id="main",
        document_id="doc-1",
        chunk_id="chunk-1",
        path="wiki/page.md",
        section="Section",
        anchor="section",
        content_hash="chunk-hash",
        raw_sha256="raw-sha",
        metadata_index_revision=metadata_index_revision,
        vault_revision="vault-rev",
    )


def test_metadata_context_evidence_resolver_reads_metadata_store_protocol() -> None:
    chunk = make_chunk_snapshot(text="one two three", token_count=3)
    evidence = make_evidence_reference(metadata_index_revision="metadata-1")
    store = RecordingMetadataStore(chunk=chunk, evidence=evidence)
    resolver = MetadataContextEvidenceResolver(metadata_store=cast(MetadataStore, store))

    resolved = resolver.resolve(ContextEvidenceRef("main", evidence.document_id, evidence.chunk_id))

    assert resolved is not None
    assert resolved.path == "wiki/page.md"
    assert resolved.text == "one two three"
    assert resolved.token_count == 3
    assert resolved.metadata_index_revision == "metadata-1"
    assert [call[0] for call in store.calls] == ["resolve_chunk", "resolve_chunk_evidence"]


def test_metadata_context_evidence_resolver_reads_sqlite_metadata_store(tmp_path: Path) -> None:
    store = SQLiteMetadataStore(tmp_path / "metadata.sqlite3", initialize=True)
    document = make_document("main", "wiki/page.md", "hash-1")
    chunk = make_chunk("main", document.document_id, document.path)
    store.apply_metadata_revision(index_revision="metadata-1", documents=[document], chunks=[chunk], tombstones=[])
    resolver = MetadataContextEvidenceResolver(metadata_store=store)

    resolved = resolver.resolve(ContextEvidenceRef("main", document.document_id, chunk.chunk_id))

    assert resolved is not None
    assert resolved.path == "wiki/page.md"
    assert resolved.metadata_index_revision == "metadata-1"


def test_metadata_context_evidence_resolver_returns_none_when_chunk_missing() -> None:
    resolver = MetadataContextEvidenceResolver(
        metadata_store=cast(MetadataStore, RecordingMetadataStore(chunk=None, evidence=make_evidence_reference()))
    )

    assert resolver.resolve(ContextEvidenceRef("main", "doc-1", "chunk-1")) is None


def test_metadata_context_evidence_resolver_returns_none_when_evidence_missing() -> None:
    resolver = MetadataContextEvidenceResolver(
        metadata_store=cast(MetadataStore, RecordingMetadataStore(chunk=make_chunk_snapshot(), evidence=None))
    )

    assert resolver.resolve(ContextEvidenceRef("main", "doc-1", "chunk-1")) is None


@pytest.mark.parametrize(
    "chunk",
    [
        make_chunk_snapshot(text="text", token_count=1).__class__(
            **{
                **make_chunk_snapshot(text="text", token_count=1).__dict__,
                "document_id": "other-doc",
            }
        ),
        make_chunk_snapshot(text="text", token_count=1).__class__(
            **{
                **make_chunk_snapshot(text="text", token_count=1).__dict__,
                "path": "wiki/other.md",
            }
        ),
        make_chunk_snapshot(text="text", token_count=1).__class__(
            **{
                **make_chunk_snapshot(text="text", token_count=1).__dict__,
                "content_hash": "other-hash",
            }
        ),
    ],
)
def test_metadata_context_evidence_resolver_returns_none_when_chunk_and_evidence_mismatch(
    chunk: ChunkSnapshot,
) -> None:
    resolver = MetadataContextEvidenceResolver(
        metadata_store=cast(MetadataStore, RecordingMetadataStore(chunk=chunk, evidence=make_evidence_reference()))
    )

    assert resolver.resolve(ContextEvidenceRef("main", "doc-1", "chunk-1")) is None


@pytest.mark.parametrize(
    "kwargs",
    [
        {"max_tokens": 0},
        {"max_evidence_items": 0},
        {"max_excerpt_tokens": 0},
        {"used_tokens": -1},
        {"omitted_items": -1},
    ],
)
def test_context_pack_budget_rejects_invalid_values(kwargs: dict[str, int]) -> None:
    with pytest.raises(ContextPackError):
        ContextPackBudget(**kwargs)
