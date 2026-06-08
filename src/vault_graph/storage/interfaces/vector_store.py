from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from vault_graph.embeddings.text_embeddings import EmbeddingModelSpec, EmbeddingVector
from vault_graph.errors import CatalogError, VectorStoreError
from vault_graph.ingestion.vault_catalog import QueryScope
from vault_graph.storage.interfaces.store_health import StoreHealth


@dataclass(frozen=True)
class VectorEmbeddingRecord:
    vector_id: str
    vault_id: str
    document_id: str
    chunk_id: str
    content_scope: str
    embedding: EmbeddingVector
    metadata_index_revision: str
    vector_index_revision: str

    def __post_init__(self) -> None:
        _require_non_empty(self.vector_id, "vector_id")
        _require_non_empty(self.vault_id, "vault_id")
        _require_non_empty(self.document_id, "document_id")
        _require_non_empty(self.chunk_id, "chunk_id")
        _require_non_empty(self.content_scope, "content_scope")
        _require_non_empty(self.metadata_index_revision, "metadata_index_revision")
        _require_non_empty(self.vector_index_revision, "vector_index_revision")
        _validate_content_scope(vault_id=self.vault_id, content_scope=self.content_scope)


@dataclass(frozen=True)
class VectorTombstone:
    vault_id: str
    chunk_id: str

    def __post_init__(self) -> None:
        _require_non_empty(self.vault_id, "vault_id")
        _require_non_empty(self.chunk_id, "chunk_id")


@dataclass(frozen=True)
class VectorQuery:
    query_vector: EmbeddingVector
    scope: QueryScope
    limit: int
    embedding_spec: EmbeddingModelSpec

    def __post_init__(self) -> None:
        if self.limit <= 0:
            raise VectorStoreError("limit must be positive")
        if self.query_vector.model_spec != self.embedding_spec:
            raise VectorStoreError("query vector model spec must match embedding_spec")


@dataclass(frozen=True)
class VectorHit:
    vector_id: str
    vault_id: str
    document_id: str
    chunk_id: str
    content_scope: str
    score: float
    rank: int
    embedding_spec: EmbeddingModelSpec
    metadata_index_revision: str
    vector_index_revision: str
    backend: str

    def __post_init__(self) -> None:
        _require_non_empty(self.vector_id, "vector_id")
        _require_non_empty(self.vault_id, "vault_id")
        _require_non_empty(self.document_id, "document_id")
        _require_non_empty(self.chunk_id, "chunk_id")
        _require_non_empty(self.content_scope, "content_scope")
        _require_non_empty(self.metadata_index_revision, "metadata_index_revision")
        _require_non_empty(self.vector_index_revision, "vector_index_revision")
        _require_non_empty(self.backend, "backend")
        if self.rank <= 0:
            raise VectorStoreError("rank must be positive")
        _validate_content_scope(vault_id=self.vault_id, content_scope=self.content_scope)


@dataclass(frozen=True)
class VectorManifestRecord:
    vector_id: str
    vault_id: str
    document_id: str
    chunk_id: str
    content_scope: str
    embedding_spec: EmbeddingModelSpec
    metadata_index_revision: str
    vector_index_revision: str
    backend: str

    def __post_init__(self) -> None:
        _require_non_empty(self.vector_id, "vector_id")
        _require_non_empty(self.vault_id, "vault_id")
        _require_non_empty(self.document_id, "document_id")
        _require_non_empty(self.chunk_id, "chunk_id")
        _require_non_empty(self.content_scope, "content_scope")
        _require_non_empty(self.metadata_index_revision, "metadata_index_revision")
        _require_non_empty(self.vector_index_revision, "vector_index_revision")
        _require_non_empty(self.backend, "backend")
        _validate_content_scope(vault_id=self.vault_id, content_scope=self.content_scope)


class VectorStore(Protocol):
    def apply_vector_revision(
        self,
        *,
        vector_index_revision: str,
        records: tuple[VectorEmbeddingRecord, ...],
        tombstones: tuple[VectorTombstone, ...],
    ) -> None: ...

    def search(self, query: VectorQuery) -> tuple[VectorHit, ...]: ...

    def health(self) -> StoreHealth: ...

    def export_manifest(self, scope: QueryScope) -> tuple[VectorManifestRecord, ...]: ...


def _require_non_empty(value: str, field_name: str) -> None:
    if not value:
        raise VectorStoreError(f"{field_name} is required")


def _validate_content_scope(*, vault_id: str, content_scope: str) -> None:
    try:
        QueryScope(vault_ids=(vault_id,), content_scopes=(content_scope,))
    except CatalogError as exc:
        raise VectorStoreError(str(exc)) from exc
