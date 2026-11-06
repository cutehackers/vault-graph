"""Pick the chunk planner for one document and the model input for one chunk (spec 2026-11-05 §4.2.6-1·2)."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from vault_graph.indexing.ingestion.document_chunking import (
    ChunkDraft,
    DocumentChunker,
    DocumentWindowChunker,
    contextual_embedding_text,
)
from vault_graph.indexing.ingestion.document_models import ExtractedDocument
from vault_graph.indexing.ingestion.document_snapshots import ChunkSnapshot

SESSION_SCHEMA_PREFIX = "vault-session/"
SESSION_SCHEMA_V1 = "vault-session/v1"
SESSION_SCHEMA_V2 = "vault-session/v2"
KNOWN_SESSION_SCHEMAS: frozenset[str] = frozenset({SESSION_SCHEMA_V1, SESSION_SCHEMA_V2})

_GENERIC_CHUNKER: DocumentChunker[ChunkDraft] = DocumentWindowChunker()

# Session exchange chunkers by frontmatter `schema`. `session-exchange-v1` and `session-exchange-v2`
# register here when they land. Until then a known session schema uses the generic chunker.
_SESSION_CHUNKERS: Mapping[str, DocumentChunker[ChunkDraft]] = {}

_CHUNKERS_BY_VERSION: Mapping[str, DocumentChunker[ChunkDraft]] = {
    chunker.version: chunker for chunker in (_GENERIC_CHUNKER, *_SESSION_CHUNKERS.values())
}

# Every chunker version this code can write, in a fixed order. The incremental precheck hashes them.
CHUNKER_VERSIONS: tuple[str, ...] = tuple(_CHUNKERS_BY_VERSION)


@dataclass(frozen=True)
class ChunkerSelection:
    chunker: DocumentChunker[ChunkDraft]
    warning: str | None = None


def chunker_selection(extracted: ExtractedDocument) -> ChunkerSelection:
    """The chunker for this document, plus one warning line for an unknown session schema."""
    schema = extracted.frontmatter.data.get("schema")
    if not isinstance(schema, str) or not schema.startswith(SESSION_SCHEMA_PREFIX):
        return ChunkerSelection(_GENERIC_CHUNKER)
    session_chunker = _SESSION_CHUNKERS.get(schema)
    if session_chunker is not None:
        return ChunkerSelection(session_chunker)
    if schema in KNOWN_SESSION_SCHEMAS:
        return ChunkerSelection(_GENERIC_CHUNKER)
    return ChunkerSelection(
        _GENERIC_CHUNKER,
        warning=(
            f"unknown_session_schema: {extracted.source.path} has schema {schema}; "
            f"chunked with {_GENERIC_CHUNKER.version}"
        ),
    )


def select_chunker(extracted: ExtractedDocument) -> DocumentChunker[ChunkDraft]:
    return chunker_selection(extracted).chunker


def embedding_input_for(chunk: ChunkSnapshot) -> str:
    """The model input of one stored chunk, as the chunker that made it defines it.

    A version no current chunker writes (an older store) keeps the generic contextual input.
    """
    chunker = _CHUNKERS_BY_VERSION.get(chunk.chunker_version)
    if chunker is None:
        return contextual_embedding_text(section_path=chunk.section_path, text=chunk.text)
    return chunker.embedding_input(chunk.section_path, chunk.text)
