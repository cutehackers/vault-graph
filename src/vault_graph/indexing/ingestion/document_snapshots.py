"""Normalized document and chunk records shared by document_authority and document_normalizer."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePosixPath
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

# What one chunk holds (spec 2026-11-05 §10.2 원인7·8):
# - "body": text of the document. Every chunker except the wiki page chunker writes only this kind.
# - "page_card": one per wiki page, built from frontmatter and the file name. It stands for its whole
#   document, so result assembly groups it with the document's other chunks.
# - "template": the page's template sections (Claim Evidence, Sources, Related, ...). Keyword search
#   reads it. The vector index leaves it out, so its text is in no embedding input.
ChunkKind = Literal["body", "page_card", "template"]
ALL_CHUNK_KINDS: tuple[ChunkKind, ...] = ("body", "page_card", "template")

# "hub" marks navigation pages that list many other pages: wiki/overview.md, wiki/index.md,
# wiki/log.md, wiki/inbox.md and wiki/maps/**. Ranking may give them a lower weight (§10.2 원인7).
# Every other document is "regular". The kind follows from the path alone, so stores written before
# it have it too.
DocumentKind = Literal["regular", "hub"]
HUB_PAGE_PATHS: frozenset[str] = frozenset({"wiki/overview.md", "wiki/index.md", "wiki/log.md", "wiki/inbox.md"})
HUB_PAGE_DIRECTORIES: tuple[str, ...] = ("wiki/maps/",)


def document_kind_for_path(path: str) -> DocumentKind:
    """The `DocumentKind` of a Vault-relative path: hub for a navigation page, else regular."""
    normalized = PurePosixPath(path.replace("\\", "/")).as_posix()
    if normalized in HUB_PAGE_PATHS or normalized.startswith(HUB_PAGE_DIRECTORIES):
        return "hub"
    return "regular"


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

    @property
    def document_kind(self) -> DocumentKind:
        return document_kind_for_path(self.path)


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
    chunk_kind: ChunkKind = "body"

    @property
    def document_kind(self) -> DocumentKind:
        """The kind of the chunk's document. See `DocumentKind`."""
        return document_kind_for_path(self.path)


@dataclass(frozen=True)
class NormalizedDocument:
    document: DocumentSnapshot
    chunks: tuple[ChunkSnapshot, ...]
    warnings: tuple[str, ...] = ()
