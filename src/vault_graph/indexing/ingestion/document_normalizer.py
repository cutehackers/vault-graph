from __future__ import annotations

import hashlib
from datetime import UTC, datetime

from vault_graph.indexing.ingestion.chunker_selection import chunker_selection
from vault_graph.indexing.ingestion.document_authority import classify_document_role
from vault_graph.indexing.ingestion.document_chunking import (
    ChunkDraft,
    DocumentChunker,
    DocumentChunkPlan,
    PlanningDocumentChunker,
)
from vault_graph.indexing.ingestion.document_models import ExtractedDocument, SourceDocument
from vault_graph.indexing.ingestion.document_readers import MarkdownDocumentReader
from vault_graph.indexing.ingestion.document_snapshots import ChunkSnapshot as ChunkSnapshot
from vault_graph.indexing.ingestion.document_snapshots import DocumentSnapshot as DocumentSnapshot
from vault_graph.indexing.ingestion.document_snapshots import NormalizedDocument as NormalizedDocument
from vault_graph.indexing.ingestion.vault_loader import LoadedVaultDocument

PARSER_VERSION = "markdown-structural-blocks-v2"


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
        selection = chunker_selection(extracted)
        chunker_version = selection.chunker.version
        plan = _chunk_plan(selection.chunker, extracted)
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
                chunk_id=_chunk_id(chunker_version, source.vault_id, source.path, draft),
                document_id=document_id,
                path=source.path,
                section=draft.section,
                anchor=draft.anchor,
                text=draft.text,
                token_count=draft.token_count,
                content_hash=stable_id("chunk-content", draft.text),
                chunker_version=chunker_version,
                index_revision=None,
                source_role=source_role,
                provenance_family_id=provenance_family_id,
                section_path=draft.section_path,
                source_locators=draft.source_locators,
                document_order=draft.document_order,
                parent_key=draft.parent_key,
                parent_locators=draft.parent_locators,
                keyword_metadata=draft.keyword_metadata,
            )
            for draft in plan.drafts
        )
        warnings = tuple(f"{warning.code}: {warning.message}" for warning in extracted.warnings)
        if selection.warning is not None:
            warnings = (*warnings, selection.warning)
        warnings = (*warnings, *plan.warnings)
        return NormalizedDocument(document=document, chunks=chunks, warnings=warnings)


def _chunk_plan(chunker: DocumentChunker[ChunkDraft], extracted: ExtractedDocument) -> DocumentChunkPlan:
    if isinstance(chunker, PlanningDocumentChunker):
        return chunker.plan(extracted)
    return DocumentChunkPlan(drafts=chunker.chunk(extracted))


def _chunk_id(chunker_version: str, vault_id: str, path: str, draft: ChunkDraft) -> str:
    """Generic chunks follow (path, boundary). A chunker that sets `id_key` names its own id parts."""
    if draft.id_key is not None:
        return stable_id("chunk", chunker_version, vault_id, *draft.id_key)
    return stable_id("chunk", chunker_version, vault_id, path, draft.boundary_key)


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
