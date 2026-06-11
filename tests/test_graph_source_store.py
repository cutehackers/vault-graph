from typing import cast

from vault_graph.extraction.graph_source_store import MetadataGraphSourceStore, PreviewGraphSourceStore
from vault_graph.ingestion.document_normalizer import ChunkSnapshot, DocumentSnapshot
from vault_graph.ingestion.vault_catalog import QueryScope
from vault_graph.storage.interfaces.metadata_store import MetadataStore


def document(vault_id: str, path: str, document_id: str) -> DocumentSnapshot:
    return DocumentSnapshot(
        vault_id=vault_id,
        document_id=document_id,
        path=path,
        kind=path.split("/", 1)[0],
        frontmatter={"title": path},
        frontmatter_hash="frontmatter",
        content_hash="content",
        raw_sha256="raw",
        parser_version="markdown-frontmatter-v1",
        last_seen_at="2026-06-11T00:00:00+00:00",
        last_indexed_at=None,
        vault_revision=None,
        index_revision="metadata-1",
    )


def chunk(vault_id: str, document_id: str, path: str) -> ChunkSnapshot:
    return ChunkSnapshot(
        vault_id=vault_id,
        chunk_id=f"{vault_id}-chunk",
        document_id=document_id,
        path=path,
        section="Title",
        anchor="title",
        text="# Title\nBody",
        token_count=3,
        content_hash=f"{vault_id}-hash",
        chunker_version="heading-section-v1",
        index_revision="metadata-1",
    )


class FakeMetadataStore:
    def __init__(self) -> None:
        self.documents = {
            "shared": document("first", "wiki/page.md", "shared"),
        }

    def list_chunks(self, scope: QueryScope) -> tuple[ChunkSnapshot, ...]:
        return (chunk("first", "shared", "wiki/page.md"),)

    def resolve_document(self, document_id: str) -> DocumentSnapshot | None:
        return self.documents.get(document_id)


def test_metadata_graph_source_resolution_is_vault_scoped() -> None:
    source = MetadataGraphSourceStore(cast(MetadataStore, FakeMetadataStore()))

    assert source.resolve_document(vault_id="first", document_id="shared") is not None
    assert source.resolve_document(vault_id="second", document_id="shared") is None


def test_preview_graph_source_lists_chunks_and_documents_without_metadata_store() -> None:
    doc = document("default", "wiki/page.md", "doc")
    source = PreviewGraphSourceStore(chunks=(chunk("default", "doc", "wiki/page.md"),), documents=(doc,))

    assert source.list_chunks(QueryScope(vault_ids=("default",), content_scopes=("wiki",)))
    assert source.resolve_document(vault_id="default", document_id="doc") == doc
