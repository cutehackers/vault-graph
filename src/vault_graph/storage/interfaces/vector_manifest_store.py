"""Vector manifest table: what the vector store of one projection generation holds.

The incremental vector plan reads this table instead of listing the vector store
(spec 4.3.1). The table lives inside the generation, so it rolls back with it.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from vault_graph.storage.interfaces.vector_store import VectorManifestRecord, VectorTombstone


@dataclass(frozen=True)
class VectorManifestRow(VectorManifestRecord):
    """One table row per stored vector.

    A subclass of `VectorManifestRecord` so the plan reads rows as records. `embedding_key` and
    `metadata_fingerprint` (spec 4.3.2) are empty for rows rebuilt from the vector store, which
    does not keep them.
    """

    embedding_key: str = ""
    metadata_fingerprint: str = ""

    @classmethod
    def from_record(cls, record: VectorManifestRecord) -> VectorManifestRow:
        if isinstance(record, VectorManifestRow):
            return record
        return cls(
            vector_id=record.vector_id,
            vault_id=record.vault_id,
            document_id=record.document_id,
            chunk_id=record.chunk_id,
            content_scope=record.content_scope,
            embedding_spec=record.embedding_spec,
            source_chunk_hash=record.source_chunk_hash,
            chunker_version=record.chunker_version,
            metadata_index_revision=record.metadata_index_revision,
            vector_index_revision=record.vector_index_revision,
            backend=record.backend,
            backend_schema_version=record.backend_schema_version,
            source_role=record.source_role,
            provenance_family_id=record.provenance_family_id,
        )


class VectorManifestStore(Protocol):
    def rows(self, vault_ids: tuple[str, ...]) -> tuple[VectorManifestRow, ...]: ...

    def apply(
        self,
        upserts: tuple[VectorManifestRow, ...],
        metadata_updates: tuple[VectorManifestRow, ...],
        deletions: tuple[VectorTombstone, ...],
    ) -> None:
        """Write one store batch. A deletion removes a row only when vault, chunk and spec match."""
        ...

    def count(self, vault_id: str) -> int: ...

    def exists(self) -> bool: ...

    def replace_vault_rows(self, vault_ids: tuple[str, ...], rows: tuple[VectorManifestRow, ...]) -> None:
        """Drop every row of `vault_ids`, then insert `rows`. Creates the table when missing."""
        ...


class VectorBackendListing(Protocol):
    """Reads the vector store itself, used only to check and rebuild the table."""

    def counts(self, vault_ids: tuple[str, ...]) -> Mapping[str, int]: ...

    def rows(self, vault_ids: tuple[str, ...]) -> tuple[VectorManifestRecord, ...]: ...


@dataclass(frozen=True)
class VectorManifestRead:
    rows: tuple[VectorManifestRecord, ...]
    warnings: tuple[str, ...] = ()


@runtime_checkable
class VectorManifestSource(Protocol):
    """A vector store that answers the plan's manifest read from its table."""

    def manifest_rows(self, vault_ids: tuple[str, ...]) -> VectorManifestRead: ...
