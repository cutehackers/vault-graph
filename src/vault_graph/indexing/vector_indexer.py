from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import PurePosixPath
from typing import Protocol

from vault_graph.embeddings.text_embeddings import EmbeddingInput, EmbeddingModelSpec, EmbeddingVector, TextEmbeddings
from vault_graph.errors import TextEmbeddingsError, VectorStoreError
from vault_graph.ingestion.document_normalizer import ChunkSnapshot, stable_id
from vault_graph.ingestion.vault_catalog import QueryScope
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
        desired_keys = {(chunk.vault_id, chunk.chunk_id) for chunk in desired_chunks}
        current_rows = _unique_manifest_rows(_manifest_for_scopes(vector_store=self._vector_store, scopes=scopes))
        current_by_vector_id = {row.vector_id: row for row in current_rows}

        upsert_chunks: list[ChunkSnapshot] = []
        tombstones: list[VectorTombstone] = []
        unchanged_count = 0
        for chunk in desired_chunks:
            desired_vector_id = stable_vector_id(
                vault_id=chunk.vault_id,
                chunk_id=chunk.chunk_id,
                embedding_spec=embedding_spec,
            )
            current = current_by_vector_id.get(desired_vector_id)
            same_chunk_old_spec_rows = tuple(
                row
                for row in current_rows
                if row.vault_id == chunk.vault_id
                and row.chunk_id == chunk.chunk_id
                and row.embedding_spec != embedding_spec
            )
            tombstones.extend(_tombstone_for_row(row) for row in same_chunk_old_spec_rows)
            if full or current is None or not _manifest_matches_chunk(
                current,
                chunk=chunk,
                embedding_spec=embedding_spec,
                backend_schema_version=backend_schema_version,
            ):
                if current is not None:
                    tombstones.append(_tombstone_for_row(current))
                upsert_chunks.append(chunk)
            else:
                unchanged_count += 1

        for row in current_rows:
            if (row.vault_id, row.chunk_id) not in desired_keys:
                tombstones.append(_tombstone_for_row(row))

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
        vectors: dict[str, EmbeddingVector] = {}
        for batch in _chunk_batches(chunks, self._embedding_batch_size):
            outputs = self._text_embeddings.embed(
                tuple(EmbeddingInput(input_id=_embedding_input_id(chunk), text=chunk.text) for chunk in batch)
            )
            expected_ids = {_embedding_input_id(chunk) for chunk in batch}
            output_ids = {output.input_id for output in outputs}
            if output_ids != expected_ids:
                raise TextEmbeddingsError("embedding output IDs must match input chunk IDs")
            for output in outputs:
                if output.model_spec != self._text_embeddings.model_spec():
                    raise TextEmbeddingsError("embedding model spec mismatch")
                vectors[output.input_id] = output
        return vectors

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


def _manifest_matches_chunk(
    row: VectorManifestRecord,
    *,
    chunk: ChunkSnapshot,
    embedding_spec: EmbeddingModelSpec,
    backend_schema_version: str,
) -> bool:
    return (
        row.embedding_spec == embedding_spec
        and row.source_chunk_hash == chunk.content_hash
        and row.chunker_version == chunk.chunker_version
        and row.metadata_index_revision == (chunk.index_revision or "unknown")
        and row.backend_schema_version == backend_schema_version
    )


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


def _chunk_batches(chunks: tuple[ChunkSnapshot, ...], batch_size: int) -> tuple[tuple[ChunkSnapshot, ...], ...]:
    return tuple(chunks[index : index + batch_size] for index in range(0, len(chunks), batch_size))


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


def _chunk_sort_key(chunk: ChunkSnapshot) -> tuple[str, str, str]:
    return (chunk.vault_id, chunk.path, chunk.chunk_id)
