from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from vault_graph.ingestion.markdown_parser import parse_sections
from vault_graph.ingestion.vault_loader import LoadedVaultDocument

PARSER_VERSION = "markdown-frontmatter-v1"
CHUNKER_VERSION = "heading-section-v1"


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


@dataclass(frozen=True)
class NormalizedDocument:
    document: DocumentSnapshot
    chunks: tuple[ChunkSnapshot, ...]


def stable_id(*parts: str) -> str:
    return hashlib.sha256(":".join(parts).encode("utf-8")).hexdigest()


class DocumentNormalizer:
    def normalize(self, loaded: LoadedVaultDocument) -> NormalizedDocument:
        now = datetime.now(UTC).isoformat()
        document_id = stable_id("document", loaded.vault_id, loaded.path)
        document = DocumentSnapshot(
            vault_id=loaded.vault_id,
            document_id=document_id,
            path=loaded.path,
            kind=loaded.path.split("/", 1)[0],
            frontmatter=dict(loaded.frontmatter.data),
            frontmatter_hash=loaded.frontmatter.frontmatter_hash,
            content_hash=loaded.content_hash,
            raw_sha256=loaded.raw_sha256,
            parser_version=PARSER_VERSION,
            last_seen_at=now,
            last_indexed_at=None,
            vault_revision=None,
            index_revision=None,
        )
        chunks = tuple(
            ChunkSnapshot(
                vault_id=loaded.vault_id,
                chunk_id=stable_id("chunk", loaded.vault_id, loaded.path, section.anchor or "body", str(index)),
                document_id=document_id,
                path=loaded.path,
                section=section.heading,
                anchor=section.anchor,
                text=section.text,
                token_count=len(section.text.split()),
                content_hash=stable_id("chunk-content", section.text),
                chunker_version=CHUNKER_VERSION,
                index_revision=None,
            )
            for index, section in enumerate(parse_sections(loaded.frontmatter.body))
        )
        return NormalizedDocument(document=document, chunks=chunks)
