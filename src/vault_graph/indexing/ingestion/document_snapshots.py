"""Normalized document and chunk records shared by document_authority and document_normalizer."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from vault_graph.indexing.ingestion.document_models import SourceLocator

DocumentRole = Literal[
    "raw_evidence",
    "canonical_knowledge",
    "source_manifest",
    "operating_contract",
    "generated_view",
    "operation_log",
    "audit_record",
]

ALL_DOCUMENT_ROLES: tuple[DocumentRole, ...] = (
    "raw_evidence",
    "canonical_knowledge",
    "source_manifest",
    "operating_contract",
    "generated_view",
    "operation_log",
    "audit_record",
)


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
    # Parent unit and exchange keywords of a session window (spec 2026-11-05 §4.2.6-6·8).
    # Generic documents keep None and an empty tuple.
    parent_key: str | None = None
    parent_locators: tuple[SourceLocator, ...] = ()
    keyword_metadata: str | None = None


@dataclass(frozen=True)
class NormalizedDocument:
    document: DocumentSnapshot
    chunks: tuple[ChunkSnapshot, ...]
    warnings: tuple[str, ...] = ()
