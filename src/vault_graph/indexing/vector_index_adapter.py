from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import PurePosixPath
from typing import Protocol

from text_embeddings import EmbeddingInput as GenericEmbeddingInput
from text_embeddings import EmbeddingModelSpec as GenericEmbeddingModelSpec
from text_embeddings import EmbeddingVector as GenericEmbeddingVector
from vector_index import IndexedItem, IndexItem, VectorIndexError, embed_items, model_space_id, plan_index

from vault_graph.errors import TextEmbeddingsError, VectorStoreError
from vault_graph.indexing.ingestion.document_chunking import contextual_embedding_text
from vault_graph.indexing.ingestion.document_normalizer import ChunkSnapshot, stable_id
from vault_graph.operation.scope.vault_catalog import QueryScope
from vault_graph.storage.interfaces.text_embeddings import (
    EmbeddingInput,
    EmbeddingModelSpec,
    EmbeddingVector,
    TextEmbeddings,
)
from vault_graph.storage.interfaces.vector_store import (
    VectorEmbeddingRecord,
    VectorManifestRecord,
    VectorStore,
    VectorTombstone,
)


class ChunkListingStore(Protocol):
    def list_chunks(self, scope: QueryScope) -> tuple[ChunkSnapshot, ...]: ...


@dataclass(frozen=True)
class VectorRevisionPlan:
    vector_index_revision: str
    mode: str
    scopes: tuple[QueryScope, ...]
    embedding_spec: EmbeddingModelSpec
    embedding_batch_size: int
    embedding_parallelism: int | None
    embedding_lazy_load: bool
    upsert_chunks: tuple[ChunkSnapshot, ...]
    tombstones: tuple[VectorTombstone, ...]
    unchanged_count: int
    warnings: tuple[str, ...]

    @property
    def upsert_count(self) -> int:
        return len(self.upsert_chunks)

    @property
    def tombstone_count(self) -> int:
        return len(self.tombstones)

    @property
    def embedding_count(self) -> int:
        return len(self.upsert_chunks)


@dataclass(frozen=True)
class VectorApplyResult:
    vector_index_revision: str
    mode: str
    scopes: tuple[QueryScope, ...]
    embedding_spec: EmbeddingModelSpec
    embedding_batch_size: int
    embedding_parallelism: int | None
    embedding_lazy_load: bool
    upsert_count: int
    tombstone_count: int
    unchanged_count: int
    embedding_count: int
    warnings: tuple[str, ...]
    failed: bool
    error: str | None

    @classmethod
    def from_plan(cls, plan: VectorRevisionPlan, *, failed: bool, error: str | None) -> VectorApplyResult:
        return cls(
            vector_index_revision=plan.vector_index_revision,
            mode=plan.mode,
            scopes=plan.scopes,
            embedding_spec=plan.embedding_spec,
            embedding_batch_size=plan.embedding_batch_size,
            embedding_parallelism=plan.embedding_parallelism,
            embedding_lazy_load=plan.embedding_lazy_load,
            upsert_count=plan.upsert_count,
            tombstone_count=plan.tombstone_count,
            unchanged_count=plan.unchanged_count,
            embedding_count=plan.embedding_count,
            warnings=plan.warnings,
            failed=failed,
            error=error,
        )


class VectorIndexer:
    def __init__(
        self,
        *,
        chunk_store: ChunkListingStore,
        vector_store: VectorStore,
        text_embeddings: TextEmbeddings,
        embedding_batch_size: int = 256,
        embedding_parallelism: int | None = None,
        embedding_lazy_load: bool = True,
    ) -> None:
        self._chunk_store = chunk_store
        self._vector_store = vector_store
        self._text_embeddings = text_embeddings
        self._embedding_batch_size = embedding_batch_size
        self._embedding_parallelism = embedding_parallelism
        self._embedding_lazy_load = embedding_lazy_load

    def plan(self, *, scopes: tuple[QueryScope, ...], full: bool = False) -> VectorRevisionPlan:
        embedding_spec = self._text_embeddings.model_spec()
        backend_health = self._vector_store.health()
        backend_schema_version = backend_health.schema_version
        desired_chunks = _unique_chunks(_chunks_for_scopes(chunk_store=self._chunk_store, scopes=scopes))
        current_rows = _unique_manifest_rows(_manifest_for_scopes(vector_store=self._vector_store, scopes=scopes))
        desired = tuple(
            IndexItem(
                chunk.vault_id,
                chunk.chunk_id,
                stable_vector_id(vault_id=chunk.vault_id, chunk_id=chunk.chunk_id, embedding_spec=embedding_spec),
                contextual_embedding_text(section_path=chunk.section_path, text=chunk.text),
                _chunk_fingerprint(chunk, backend_schema_version),
            )
            for chunk in desired_chunks
        )
        if len({item.record_id for item in desired}) != len(desired):
            raise VectorStoreError("vector_id collision in indexing scope")
        current = tuple(
            IndexedItem(
                row.vault_id,
                row.chunk_id,
                row.vector_id,
                model_space_id(_generic_spec(row.embedding_spec)),
                _row_fingerprint(row),
            )
            for row in current_rows
        )
        generic_plan = plan_index(
            desired,
            current,
            collection_ids=tuple(dict.fromkeys(vault for scope in scopes for vault in scope.vault_ids)),
            input_kind="snapshot",
            space_id=model_space_id(_generic_spec(embedding_spec)),
            full=full,
        )
        chunk_by_key = {(chunk.vault_id, chunk.chunk_id): chunk for chunk in desired_chunks}
        row_by_key = {(row.vault_id, row.vector_id): row for row in current_rows}
        upsert_chunks = [chunk_by_key[(item.collection_id, item.item_id)] for item in generic_plan.upserts]
        tombstones = [
            _tombstone_for_row(row_by_key[(row.collection_id, row.record_id)]) for row in generic_plan.deletions
        ]
        unchanged_count = generic_plan.unchanged_count

        warnings = () if backend_health.ok and backend_health.schema_compatible else (backend_health.message,)
        return VectorRevisionPlan(
            vector_index_revision=f"vector-{datetime.now(UTC).strftime('%Y%m%d%H%M%S%f')}",
            mode="full" if full else "incremental",
            scopes=scopes,
            embedding_spec=embedding_spec,
            embedding_batch_size=self._embedding_batch_size,
            embedding_parallelism=self._embedding_parallelism,
            embedding_lazy_load=self._embedding_lazy_load,
            upsert_chunks=tuple(sorted(upsert_chunks, key=_chunk_sort_key)),
            tombstones=_unique_tombstones(tuple(tombstones)),
            unchanged_count=unchanged_count,
            warnings=warnings,
        )

    def apply(self, *, scopes: tuple[QueryScope, ...], full: bool = False) -> VectorApplyResult:
        plan = self.plan(scopes=scopes, full=full)
        try:
            embeddings = self._embed_chunks(plan.upsert_chunks)
            records = tuple(
                self._record_for_chunk(
                    plan=plan,
                    chunk=chunk,
                    embedding=embeddings[_embedding_input_id(chunk)],
                )
                for chunk in plan.upsert_chunks
            )
            self._vector_store.apply_vector_revision(
                vector_index_revision=plan.vector_index_revision,
                records=records,
                tombstones=plan.tombstones,
            )
            return VectorApplyResult.from_plan(plan, failed=False, error=None)
        except Exception as exc:
            return VectorApplyResult.from_plan(plan, failed=True, error=str(exc))

    def _embed_chunks(self, chunks: tuple[ChunkSnapshot, ...]) -> dict[str, EmbeddingVector]:
        _validate_unique_chunk_ids(chunks)
        items = tuple(
            IndexItem(
                chunk.vault_id,
                chunk.chunk_id,
                chunk.chunk_id,
                contextual_embedding_text(section_path=chunk.section_path, text=chunk.text),
                chunk.content_hash,
            )
            for chunk in chunks
        )
        try:
            vectors = embed_items(
                items, _EmbeddingProvider(self._text_embeddings), batch_size=self._embedding_batch_size
            )
        except VectorIndexError as exc:
            message = str(exc).replace("input item IDs", "input chunk IDs")
            raise TextEmbeddingsError(message) from exc
        return {
            _embedding_input_id(chunk): EmbeddingVector(
                _embedding_input_id(chunk),
                vectors[(chunk.vault_id, chunk.chunk_id)].values,
                self._text_embeddings.model_spec(),
            )
            for chunk in chunks
        }

    def _record_for_chunk(
        self,
        *,
        plan: VectorRevisionPlan,
        chunk: ChunkSnapshot,
        embedding: EmbeddingVector,
    ) -> VectorEmbeddingRecord:
        return VectorEmbeddingRecord(
            vector_id=stable_vector_id(
                vault_id=chunk.vault_id,
                chunk_id=chunk.chunk_id,
                embedding_spec=plan.embedding_spec,
            ),
            vault_id=chunk.vault_id,
            document_id=chunk.document_id,
            chunk_id=chunk.chunk_id,
            content_scope=_content_scope_for_path(chunk.path),
            embedding=embedding,
            source_chunk_hash=chunk.content_hash,
            chunker_version=chunk.chunker_version,
            metadata_index_revision=chunk.index_revision or "unknown",
            vector_index_revision=plan.vector_index_revision,
            backend_schema_version=self._vector_store.health().schema_version,
            source_role=chunk.source_role,
            provenance_family_id=_family_id_for_chunk(chunk),
        )


def stable_vector_id(*, vault_id: str, chunk_id: str, embedding_spec: EmbeddingModelSpec) -> str:
    return stable_id("vector", vault_id, chunk_id, _embedding_spec_key(embedding_spec))


def _embedding_spec_key(spec: EmbeddingModelSpec) -> str:
    return "|".join((spec.model_name, spec.model_version, str(spec.dimensions), spec.spec_version))


def _chunks_for_scopes(*, chunk_store: ChunkListingStore, scopes: tuple[QueryScope, ...]) -> tuple[ChunkSnapshot, ...]:
    return tuple(chunk for scope in scopes for chunk in chunk_store.list_chunks(scope))


def _manifest_for_scopes(
    *,
    vector_store: VectorStore,
    scopes: tuple[QueryScope, ...],
) -> tuple[VectorManifestRecord, ...]:
    return tuple(row for scope in scopes for row in vector_store.export_manifest(scope))


def _unique_chunks(chunks: tuple[ChunkSnapshot, ...]) -> tuple[ChunkSnapshot, ...]:
    by_key: dict[tuple[str, str], ChunkSnapshot] = {}
    for chunk in chunks:
        key = (chunk.vault_id, chunk.chunk_id)
        if key in by_key:
            raise VectorStoreError(f"duplicate chunk_id in vector indexing scope: {chunk.chunk_id}")
        by_key[key] = chunk
    return tuple(sorted(by_key.values(), key=_chunk_sort_key))


def _unique_manifest_rows(rows: tuple[VectorManifestRecord, ...]) -> tuple[VectorManifestRecord, ...]:
    by_key = {row.vector_id: row for row in rows}
    return tuple(sorted(by_key.values(), key=lambda row: (row.vault_id, row.chunk_id, row.vector_id)))


def _tombstone_for_row(row: VectorManifestRecord) -> VectorTombstone:
    return VectorTombstone(
        vector_id=row.vector_id,
        vault_id=row.vault_id,
        chunk_id=row.chunk_id,
        embedding_spec=row.embedding_spec,
    )


def _unique_tombstones(tombstones: tuple[VectorTombstone, ...]) -> tuple[VectorTombstone, ...]:
    by_key = {
        (tombstone.vector_id, tombstone.vault_id, tombstone.chunk_id, tombstone.embedding_spec): tombstone
        for tombstone in tombstones
    }
    return tuple(sorted(by_key.values(), key=lambda item: (item.vault_id, item.chunk_id, item.vector_id)))


def _validate_unique_chunk_ids(chunks: tuple[ChunkSnapshot, ...]) -> None:
    seen: set[tuple[str, str]] = set()
    for chunk in chunks:
        key = (chunk.vault_id, chunk.chunk_id)
        if key in seen:
            raise VectorStoreError(f"duplicate chunk_id in vector indexing batch: {chunk.chunk_id}")
        seen.add(key)


def _embedding_input_id(chunk: ChunkSnapshot) -> str:
    return f"{chunk.vault_id}:{chunk.chunk_id}"


def _content_scope_for_path(path: str) -> str:
    parent = PurePosixPath(path).parent.as_posix()
    if parent == ".":
        return path.split("/", 1)[0]
    return parent


def _family_id_for_chunk(chunk: ChunkSnapshot) -> str:
    return chunk.provenance_family_id or stable_id("provenance-family", chunk.vault_id, chunk.document_id)


def _chunk_sort_key(chunk: ChunkSnapshot) -> tuple[str, str, str]:
    return (chunk.vault_id, chunk.path, chunk.chunk_id)


def _generic_spec(spec: EmbeddingModelSpec) -> GenericEmbeddingModelSpec:
    return GenericEmbeddingModelSpec(spec.model_name, spec.model_version, spec.dimensions, spec.spec_version)


def _fingerprint(values: tuple[str, ...]) -> str:
    return hashlib.sha256(json.dumps(values).encode()).hexdigest()


def _chunk_fingerprint(chunk: ChunkSnapshot, backend_schema_version: str) -> str:
    return _fingerprint(
        (
            chunk.content_hash,
            chunk.chunker_version,
            chunk.index_revision or "unknown",
            backend_schema_version,
            chunk.source_role,
            _family_id_for_chunk(chunk),
        )
    )


def _row_fingerprint(row: VectorManifestRecord) -> str:
    return _fingerprint(
        (
            row.source_chunk_hash,
            row.chunker_version,
            row.metadata_index_revision,
            row.backend_schema_version,
            row.source_role,
            row.provenance_family_id,
        )
    )


class _EmbeddingProvider:
    def __init__(self, provider: TextEmbeddings) -> None:
        self._provider = provider

    def model_spec(self) -> GenericEmbeddingModelSpec:
        return _generic_spec(self._provider.model_spec())

    def embed(self, inputs: tuple[GenericEmbeddingInput, ...]) -> tuple[GenericEmbeddingVector, ...]:
        originals = tuple(EmbeddingInput(item.input_id, item.text) for item in inputs)
        outputs = self._provider.embed(originals)
        # Unknown IDs remain unknown, so the core rejects the response before writes.
        return tuple(
            GenericEmbeddingVector(output.input_id, output.values, _generic_spec(output.model_spec))
            for output in outputs
        )
