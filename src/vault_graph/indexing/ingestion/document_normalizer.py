from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from vault_graph.indexing.ingestion.document_authority import DocumentRole, classify_document_role
from vault_graph.indexing.ingestion.document_chunking import CHUNKER_VERSION, chunk_document
from vault_graph.indexing.ingestion.document_models import ExtractedDocument, SourceDocument, SourceLocator
from vault_graph.indexing.ingestion.document_readers import MarkdownDocumentReader
from vault_graph.indexing.ingestion.vault_loader import LoadedVaultDocument

PARSER_VERSION = "markdown-structural-blocks-v2"


@dataclass(frozen=True)
class DocumentSnapshot:
    vault_id: str
    document_id: str
    path: str
    kind: str
    frontmatter: dict[str, Any]
    frontmatter_hash: str
    content_hash: str
    raw_sha256: str
    parser_version: str
    last_seen_at: str
    last_indexed_at: str | None
    vault_revision: str | None
    index_revision: str | None
    source_role: DocumentRole = "canonical_knowledge"
    provenance_family_id: str = ""
    format: str = "markdown"
    reader_name: str = "legacy-markdown-reader"
    reader_version: str = "legacy-v1"
    extraction_options_digest: str = "legacy-options-v1"


@dataclass(frozen=True)
class ChunkSnapshot:
    vault_id: str
    chunk_id: str
    document_id: str
    path: str
    section: str | None
    anchor: str | None
    text: str
    token_count: int
    content_hash: str
    chunker_version: str
    index_revision: str | None
    source_role: DocumentRole = "canonical_knowledge"
    provenance_family_id: str = ""
    section_path: tuple[str, ...] = ()
    source_locators: tuple[SourceLocator, ...] = ()
    document_order: int = 0


@dataclass(frozen=True)
class NormalizedDocument:
    document: DocumentSnapshot
    chunks: tuple[ChunkSnapshot, ...]
    warnings: tuple[str, ...] = ()


def stable_id(*parts: str) -> str:
    return hashlib.sha256(":".join(parts).encode("utf-8")).hexdigest()


class DocumentNormalizer:
    def normalize(self, loaded: LoadedVaultDocument | ExtractedDocument) -> NormalizedDocument:
        extracted, legacy_content_hash, legacy_raw_sha256 = _extracted_input(loaded)
        now = datetime.now(UTC).isoformat()
        source = extracted.source
        document_id = stable_id("document", source.vault_id, source.path)
        source_role = classify_document_role(path=source.path, frontmatter=extracted.frontmatter.data)
        provenance_family_id = stable_id("provenance-family", source.vault_id, source.path)
        document = DocumentSnapshot(
            vault_id=source.vault_id,
            document_id=document_id,
            path=source.path,
            kind=source.path.split("/", 1)[0],
            frontmatter=dict(extracted.frontmatter.data),
            frontmatter_hash=extracted.frontmatter.frontmatter_hash,
            content_hash=legacy_content_hash or hashlib.sha256(extracted.frontmatter.body.encode("utf-8")).hexdigest(),
            raw_sha256=legacy_raw_sha256 or source.raw_sha256,
            parser_version=extracted.parser_version,
            last_seen_at=now,
            last_indexed_at=None,
            vault_revision=None,
            index_revision=None,
            source_role=source_role,
            provenance_family_id=provenance_family_id,
            format=extracted.format,
            reader_name=extracted.reader_name,
            reader_version=extracted.reader_version,
            extraction_options_digest=extracted.extraction_options_digest,
        )
        chunks = tuple(
            ChunkSnapshot(
                vault_id=source.vault_id,
                chunk_id=stable_id(
                    "chunk",
                    CHUNKER_VERSION,
                    source.vault_id,
                    source.path,
                    draft.boundary_key,
                ),
                document_id=document_id,
                path=source.path,
                section=draft.section,
                anchor=draft.anchor,
                text=draft.text,
                token_count=draft.token_count,
                content_hash=stable_id("chunk-content", draft.text),
                chunker_version=CHUNKER_VERSION,
                index_revision=None,
                source_role=source_role,
                provenance_family_id=provenance_family_id,
                section_path=draft.section_path,
                source_locators=draft.source_locators,
                document_order=draft.document_order,
            )
            for draft in chunk_document(extracted)
        )
        warnings = tuple(f"{warning.code}: {warning.message}" for warning in extracted.warnings)
        return NormalizedDocument(document=document, chunks=chunks, warnings=warnings)


def _extracted_input(
    loaded: LoadedVaultDocument | ExtractedDocument,
) -> tuple[ExtractedDocument, str | None, str | None]:
    if isinstance(loaded, ExtractedDocument):
        return loaded, None, None
    if loaded.extracted_document is not None:
        return loaded.extracted_document, None, None

    raw_bytes = loaded.text.encode("utf-8")
    source = SourceDocument(
        vault_id=loaded.vault_id,
        root_path=loaded.root_path,
        path=loaded.path,
        suffix=".md",
        raw_bytes=raw_bytes,
        raw_sha256=hashlib.sha256(raw_bytes).hexdigest(),
    )
    return MarkdownDocumentReader().read(source), loaded.content_hash, loaded.raw_sha256
