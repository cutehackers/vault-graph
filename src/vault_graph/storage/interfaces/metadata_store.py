from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from vault_graph.ingestion.document_normalizer import ChunkSnapshot, DocumentSnapshot
from vault_graph.storage.interfaces.store_health import StoreHealth


@dataclass(frozen=True)
class EvidenceReference:
    vault_id: str
    document_id: str
    chunk_id: str
    path: str
    section: str | None
    anchor: str | None
    content_hash: str
    raw_sha256: str
    metadata_index_revision: str | None
    vault_revision: str | None


@dataclass(frozen=True)
class DocumentState:
    vault_id: str
    path: str
    document_id: str | None
    frontmatter_hash: str | None
    content_hash: str | None
    raw_sha256: str | None
    parser_version: str | None
    chunker_version: str | None
    is_tombstoned: bool


class MetadataStore(Protocol):
    def apply_metadata_revision(
        self,
        *,
        index_revision: str,
        documents: list[DocumentSnapshot],
        chunks: list[ChunkSnapshot],
        tombstones: list[tuple[str, str]],
    ) -> None: ...

    def document_state(self, vault_id: str, path: str) -> DocumentState: ...

    def list_document_states(self, vault_ids: tuple[str, ...]) -> tuple[DocumentState, ...]: ...

    def resolve_document(self, document_id: str) -> DocumentSnapshot | None: ...

    def resolve_chunk(self, *, vault_id: str, chunk_id: str) -> ChunkSnapshot | None: ...

    def resolve_chunk_evidence(
        self,
        *,
        vault_id: str,
        document_id: str,
        chunk_id: str,
    ) -> EvidenceReference | None: ...

    def health(self) -> StoreHealth: ...
