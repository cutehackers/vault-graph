from __future__ import annotations

from pathlib import Path

import pytest

from vault_graph.ingestion.document_normalizer import ChunkSnapshot, DocumentSnapshot
from vault_graph.ingestion.vault_catalog import QueryScope, VaultCatalog, VaultCatalogEntry
from vault_graph.mcp.mcp_errors import McpProtocolError
from vault_graph.mcp.mcp_uri import McpResourceUri, parse_mcp_resource_uri
from vault_graph.mcp.metadata_resource_reader import MetadataResourceReader
from vault_graph.storage.interfaces.metadata_store import DocumentState, EvidenceReference
from vault_graph.storage.interfaces.store_health import StoreHealth


def make_catalog(tmp_path: Path) -> VaultCatalog:
    main = tmp_path / "main"
    work = tmp_path / "work"
    main.mkdir()
    work.mkdir()
    return VaultCatalog.from_entries(
        entries=(
            VaultCatalogEntry.from_root(vault_id="main", root_path=main, display_name="Main"),
            VaultCatalogEntry.from_root(vault_id="work", root_path=work, display_name="Work"),
        ),
        active_vault_id="main",
    )


def make_document(
    *,
    vault_id: str = "main",
    document_id: str = "doc-1",
    path: str = "wiki/page.md",
    frontmatter: dict[str, object] | None = None,
) -> DocumentSnapshot:
    return DocumentSnapshot(
        vault_id=vault_id,
        document_id=document_id,
        path=path,
        kind=path.split("/", 1)[0],
        frontmatter=frontmatter or {},
        frontmatter_hash=f"frontmatter-{document_id}",
        content_hash=f"content-{document_id}",
        raw_sha256=f"raw-{document_id}",
        parser_version="parser-v1",
        last_seen_at="2026-06-17T00:00:00+00:00",
        last_indexed_at="2026-06-17T00:01:00+00:00",
        vault_revision=f"git-{vault_id}",
        index_revision=f"metadata-{vault_id}",
    )


def make_chunk(document: DocumentSnapshot, *, chunk_id: str, text: str) -> ChunkSnapshot:
    return ChunkSnapshot(
        vault_id=document.vault_id,
        chunk_id=chunk_id,
        document_id=document.document_id,
        path=document.path,
        section="Section",
        anchor="section",
        text=text,
        token_count=len(text.split()),
        content_hash=f"chunk-content-{chunk_id}",
        chunker_version="heading-section-v1",
        index_revision=document.index_revision,
    )


class FakeMetadataStore:
    def __init__(
        self,
        *,
        documents: tuple[DocumentSnapshot, ...],
        chunks: tuple[ChunkSnapshot, ...] = (),
        tombstoned_paths: tuple[tuple[str, str], ...] = (),
        missing_evidence: tuple[str, ...] = (),
    ) -> None:
        self.documents = {document.document_id: document for document in documents}
        self.by_path = {(document.vault_id, document.path): document for document in documents}
        self.chunks = chunks
        self.tombstoned_paths = set(tombstoned_paths)
        self.missing_evidence = set(missing_evidence)
        self.calls: list[str] = []

    def apply_metadata_revision(
        self,
        *,
        index_revision: str,
        documents: list[DocumentSnapshot],
        chunks: list[ChunkSnapshot],
        tombstones: list[tuple[str, str]],
    ) -> None:
        raise AssertionError("not used by metadata resource reader tests")

    def document_state(self, vault_id: str, path: str) -> DocumentState:
        self.calls.append(f"document_state:{vault_id}:{path}")
        document = self.by_path.get((vault_id, path))
        if document is None or (vault_id, path) in self.tombstoned_paths:
            return DocumentState(vault_id, path, None, None, None, None, None, None, True)
        return DocumentState(
            vault_id=document.vault_id,
            path=document.path,
            document_id=document.document_id,
            frontmatter_hash=document.frontmatter_hash,
            content_hash=document.content_hash,
            raw_sha256=document.raw_sha256,
            parser_version=document.parser_version,
            chunker_version="heading-section-v1",
            is_tombstoned=False,
        )

    def list_document_states(self, vault_ids: tuple[str, ...]) -> tuple[DocumentState, ...]:
        raise AssertionError("not used by metadata resource reader tests")

    def list_chunks(self, scope: QueryScope) -> tuple[ChunkSnapshot, ...]:
        raise AssertionError("not used by metadata resource reader tests")

    def resolve_document(self, document_id: str) -> DocumentSnapshot | None:
        self.calls.append(f"resolve_document:{document_id}")
        return self.documents.get(document_id)

    def list_document_chunks(self, *, vault_id: str, document_id: str) -> tuple[ChunkSnapshot, ...]:
        self.calls.append(f"list_document_chunks:{vault_id}:{document_id}")
        return tuple(chunk for chunk in self.chunks if chunk.vault_id == vault_id and chunk.document_id == document_id)

    def resolve_chunk(self, *, vault_id: str, chunk_id: str) -> ChunkSnapshot | None:
        raise AssertionError("not used by metadata resource reader tests")

    def resolve_chunk_evidence(
        self,
        *,
        vault_id: str,
        document_id: str,
        chunk_id: str,
    ) -> EvidenceReference | None:
        self.calls.append(f"resolve_chunk_evidence:{vault_id}:{document_id}:{chunk_id}")
        if chunk_id in self.missing_evidence:
            return None
        chunk = next(
            (
                item
                for item in self.chunks
                if item.vault_id == vault_id and item.document_id == document_id and item.chunk_id == chunk_id
            ),
            None,
        )
        if chunk is None:
            return None
        return EvidenceReference(
            vault_id=vault_id,
            document_id=document_id,
            chunk_id=chunk_id,
            path=chunk.path,
            section=chunk.section,
            anchor=chunk.anchor,
            content_hash=chunk.content_hash,
            raw_sha256=f"raw-{document_id}",
            metadata_index_revision=chunk.index_revision,
            vault_revision=f"git-{vault_id}",
        )

    def health(self) -> StoreHealth:
        self.calls.append("health")
        return StoreHealth(
            ok=True,
            backend="sqlite",
            schema_version="metadata-v1",
            schema_compatible=True,
            message="ok",
        )


def parse_uri(uri: str, catalog: VaultCatalog) -> McpResourceUri:
    return parse_mcp_resource_uri(uri, catalog=catalog)


def assert_not_found(exc_info: pytest.ExceptionInfo[McpProtocolError]) -> None:
    assert exc_info.value.kind == "not_found"
    assert exc_info.value.payload.code == "resource_not_found"


def test_document_resource_reads_indexed_metadata_and_chunks_only(tmp_path: Path) -> None:
    catalog = make_catalog(tmp_path)
    document = make_document()
    store = FakeMetadataStore(
        documents=(document,),
        chunks=(
            make_chunk(document, chunk_id="chunk-1", text="# Heading\nOne"),
            make_chunk(document, chunk_id="chunk-2", text="Two"),
        ),
    )
    reader = MetadataResourceReader(catalog=catalog, metadata_store=store)

    body = reader.read_document(parse_uri("vault://main/documents/wiki%2Fpage.md", catalog))

    assert body.uri == "vault://main/documents/wiki%2Fpage.md"
    assert body.content_mime_type == "text/markdown"
    assert body.text == "# Heading\nOne\n\nTwo"
    assert body.metadata["vault_id"] == "main"
    assert body.metadata["document_id"] == "doc-1"
    assert body.metadata["path"] == "wiki/page.md"
    assert body.metadata["resource_kind"] == "document"
    assert body.metadata["document_kind"] == "wiki"
    assert body.metadata["frontmatter_hash"] == "frontmatter-doc-1"
    assert body.metadata["content_hash"] == "content-doc-1"
    assert body.metadata["raw_sha256"] == "raw-doc-1"
    assert body.metadata["parser_version"] == "parser-v1"
    assert body.metadata["chunker_version"] == "heading-section-v1"
    assert body.metadata["metadata_index_revision"] == "metadata-main"
    assert body.metadata["vault_revision"] == "git-main"
    assert body.metadata["chunk_count"] == 2
    evidence_refs = body.metadata["evidence_refs"]
    assert isinstance(evidence_refs, list)
    assert len(evidence_refs) == 2
    assert store.calls[:3] == [
        "document_state:main:wiki/page.md",
        "resolve_document:doc-1",
        "list_document_chunks:main:doc-1",
    ]


def test_page_resource_requires_wiki_document(tmp_path: Path) -> None:
    catalog = make_catalog(tmp_path)
    document = make_document(path="docs/page.md")
    reader = MetadataResourceReader(catalog=catalog, metadata_store=FakeMetadataStore(documents=(document,)))

    with pytest.raises(McpProtocolError) as exc_info:
        reader.read_page(parse_uri("vault://main/documents/docs%2Fpage.md", catalog))

    assert_not_found(exc_info)


@pytest.mark.parametrize(
    ("method_name", "path", "frontmatter"),
    [
        ("read_source", "raw/source.md", {}),
        ("read_source", "wiki/source.md", {"type": "source"}),
        ("read_decision", "wiki/decisions/accepted.md", {}),
        ("read_decision", "wiki/other.md", {"type": "decision"}),
        ("read_issue", "wiki/issues/open.md", {}),
        ("read_issue", "wiki/other.md", {"type": "issue"}),
    ],
)
def test_document_id_resources_validate_expected_classification(
    tmp_path: Path,
    method_name: str,
    path: str,
    frontmatter: dict[str, object],
) -> None:
    catalog = make_catalog(tmp_path)
    document = make_document(document_id="doc-1", path=path, frontmatter=frontmatter)
    reader = MetadataResourceReader(catalog=catalog, metadata_store=FakeMetadataStore(documents=(document,)))
    uri_kind = {"read_source": "sources", "read_decision": "decisions", "read_issue": "issues"}[method_name]

    body = getattr(reader, method_name)(parse_uri(f"vault://main/{uri_kind}/doc-1", catalog))

    expected_resource_kind = "source" if uri_kind == "sources" else uri_kind.rstrip("s")
    assert body.metadata["document_id"] == "doc-1"
    assert body.metadata["resource_kind"] == expected_resource_kind


def test_classification_mismatch_is_not_found(tmp_path: Path) -> None:
    catalog = make_catalog(tmp_path)
    document = make_document(document_id="doc-1", path="wiki/page.md")
    reader = MetadataResourceReader(catalog=catalog, metadata_store=FakeMetadataStore(documents=(document,)))

    with pytest.raises(McpProtocolError) as exc_info:
        reader.read_decision(parse_uri("vault://main/decisions/doc-1", catalog))

    assert_not_found(exc_info)


def test_missing_or_tombstoned_path_resource_is_not_found(tmp_path: Path) -> None:
    catalog = make_catalog(tmp_path)
    document = make_document()
    reader = MetadataResourceReader(
        catalog=catalog,
        metadata_store=FakeMetadataStore(documents=(document,), tombstoned_paths=(("main", "wiki/page.md"),)),
    )

    with pytest.raises(McpProtocolError) as exc_info:
        reader.read_document(parse_uri("vault://main/documents/wiki%2Fpage.md", catalog))

    assert_not_found(exc_info)


def test_document_from_different_vault_is_not_found(tmp_path: Path) -> None:
    catalog = make_catalog(tmp_path)
    document = make_document(vault_id="work", document_id="doc-1", path="wiki/page.md")
    reader = MetadataResourceReader(catalog=catalog, metadata_store=FakeMetadataStore(documents=(document,)))

    with pytest.raises(McpProtocolError) as exc_info:
        reader.read_source(parse_uri("vault://main/sources/doc-1", catalog))

    assert_not_found(exc_info)


def test_document_with_no_chunks_returns_missing_evidence_warning(tmp_path: Path) -> None:
    catalog = make_catalog(tmp_path)
    document = make_document()
    reader = MetadataResourceReader(catalog=catalog, metadata_store=FakeMetadataStore(documents=(document,), chunks=()))

    body = reader.read_document(parse_uri("vault://main/documents/wiki%2Fpage.md", catalog))

    assert body.text == ""
    assert body.metadata["chunk_count"] == 0
    assert [warning.code for warning in body.warnings] == ["missing_evidence"]


def test_same_logical_path_in_two_vaults_resolves_separate_documents(tmp_path: Path) -> None:
    catalog = make_catalog(tmp_path)
    main_doc = make_document(vault_id="main", document_id="main-doc", path="wiki/same.md")
    work_doc = make_document(vault_id="work", document_id="work-doc", path="wiki/same.md")
    reader = MetadataResourceReader(
        catalog=catalog,
        metadata_store=FakeMetadataStore(
            documents=(main_doc, work_doc),
            chunks=(
                make_chunk(main_doc, chunk_id="main-chunk", text="Main"),
                make_chunk(work_doc, chunk_id="work-chunk", text="Work"),
            ),
        ),
    )

    main_body = reader.read_document(parse_uri("vault://main/documents/wiki%2Fsame.md", catalog))
    work_body = reader.read_document(parse_uri("vault://work/documents/wiki%2Fsame.md", catalog))

    assert main_body.metadata["document_id"] == "main-doc"
    assert main_body.text == "Main"
    assert work_body.metadata["document_id"] == "work-doc"
    assert work_body.text == "Work"
