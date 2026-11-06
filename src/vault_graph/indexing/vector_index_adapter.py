from __future__ import annotations

import hashlib
import json
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import PurePosixPath
from typing import Protocol, runtime_checkable

from text_embeddings import EmbeddingInput as GenericEmbeddingInput
from text_embeddings import EmbeddingModelSpec as GenericEmbeddingModelSpec
from text_embeddings import EmbeddingVector as GenericEmbeddingVector
from vector_index import IndexedItem, IndexItem, VectorIndexError, model_space_id, plan_index
from vector_index.indexing import (
    DEFAULT_TOKEN_BUDGET,
    EmbeddingBatch,
    estimate_tokens_from_bytes,
    iter_embedding_batches,
)

from vault_graph.errors import TextEmbeddingsError, VectorStoreError
from vault_graph.indexing.ingestion.chunker_selection import embedding_input_for
from vault_graph.indexing.ingestion.document_chunking import CHUNKER_VERSION
from vault_graph.indexing.ingestion.document_normalizer import ChunkSnapshot, stable_id
from vault_graph.indexing.ingestion.session_exchange_v1_chunker import SESSION_EXCHANGE_V1_VERSION
from vault_graph.indexing.ingestion.session_exchange_v2_chunker import (
    SESSION_EXCHANGE_V2_VERSION,
    count_over_model_limit,
    model_limit_warning,
)
from vault_graph.operation.scope.vault_catalog import QueryScope
from vault_graph.storage.interfaces.text_embeddings import (
    EmbeddingInput,
    EmbeddingModelSpec,
    EmbeddingVector,
    TextEmbeddings,
)
from vault_graph.storage.interfaces.vector_manifest_store import VectorManifestRow, VectorManifestSource
from vault_graph.storage.interfaces.vector_store import (
    VectorEmbeddingRecord,
    VectorManifestRecord,
    VectorMetadataRecord,
    VectorMetadataUpdater,
    VectorStore,
    VectorTombstone,
)

# Records per `update_metadata` call. Below Chroma's max batch size, and no model memory is involved.
METADATA_UPDATE_BATCH_SIZE = 1000


SESSION_WINDOW_CHUNKER_VERSIONS = frozenset({SESSION_EXCHANGE_V1_VERSION, SESSION_EXCHANGE_V2_VERSION})


class ChunkListingStore(Protocol):
    def list_chunks(self, scope: QueryScope) -> tuple[ChunkSnapshot, ...]: ...


@runtime_checkable
class ModelTokenCounter(Protocol):
    """Optional embedding provider part: the number of model tokens the model's tokenizer makes of a text."""

    def count_model_tokens(self, text: str) -> int: ...


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
    # Chunks whose embedding key matches the stored vector but whose metadata fingerprint does not.
    # Written with `update_metadata`, without opening the embedding model (spec 4.3.2).
    metadata_update_chunks: tuple[ChunkSnapshot, ...] = ()

    @property
    def upsert_count(self) -> int:
        return len(self.upsert_chunks)

    @property
    def metadata_update_count(self) -> int:
        return len(self.metadata_update_chunks)

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
    # "plan" when the plan could not be made: nothing was written to the vector store.
    # "apply" when embedding or writing failed: the staged vector store may be partly written.
    failed_stage: str | None = None
    metadata_update_count: int = 0

    @classmethod
    def from_plan(
        cls, plan: VectorRevisionPlan, *, failed: bool, error: str | None, failed_stage: str | None = None
    ) -> VectorApplyResult:
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
            failed_stage=failed_stage if failed else None,
            metadata_update_count=plan.metadata_update_count,
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
        embedding_token_budget: int = DEFAULT_TOKEN_BUDGET,
    ) -> None:
        self._chunk_store = chunk_store
        self._vector_store = vector_store
        self._text_embeddings = text_embeddings
        # Item cap per embedding batch. The token budget caps items x largest estimated tokens.
        self._embedding_batch_size = embedding_batch_size
        self._embedding_token_budget = embedding_token_budget
        self._embedding_parallelism = embedding_parallelism
        self._embedding_lazy_load = embedding_lazy_load

    def plan(self, *, scopes: tuple[QueryScope, ...], full: bool = False) -> VectorRevisionPlan:
        embedding_spec = self._text_embeddings.model_spec()
        backend_health = self._vector_store.health()
        backend_schema_version = backend_health.schema_version
        desired_chunks = _unique_chunks(_chunks_for_scopes(chunk_store=self._chunk_store, scopes=scopes))
        manifest_rows, manifest_warnings = _manifest_for_scopes(vector_store=self._vector_store, scopes=scopes)
        current_rows = _unique_manifest_rows(manifest_rows)
        desired = tuple(
            IndexItem(
                chunk.vault_id,
                chunk.chunk_id,
                stable_vector_id(vault_id=chunk.vault_id, chunk_id=chunk.chunk_id, embedding_spec=embedding_spec),
                embedding_input_for(chunk),
                embedding_key(chunk, embedding_spec),
                metadata_fingerprint=_chunk_metadata_fingerprint(chunk, backend_schema_version),
            )
            for chunk in desired_chunks
        )
        if len({item.record_id for item in desired}) != len(desired):
            raise VectorStoreError("vector_id collision in indexing scope")
        chunk_by_key = {(chunk.vault_id, chunk.chunk_id): chunk for chunk in desired_chunks}
        item_by_key = {(item.collection_id, item.item_id): item for item in desired}
        # Keys are filled only where a metadata-only write can keep them: a manifest table store
        # whose vector store updates metadata. Elsewhere filling would re-embed.
        keeps_keys = isinstance(self._vector_store, VectorManifestSource) and _supports_metadata_update(
            self._vector_store
        )
        current = tuple(
            IndexedItem(
                row.vault_id,
                row.chunk_id,
                row.vector_id,
                model_space_id(_generic_spec(row.embedding_spec)),
                *_stored_keys(
                    row,
                    chunk=chunk_by_key.get((row.vault_id, row.chunk_id)),
                    item=item_by_key.get((row.vault_id, row.chunk_id)),
                    embedding_spec=embedding_spec,
                    backend_schema_version=backend_schema_version,
                    keeps_keys=keeps_keys,
                ),
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
        row_by_key = {(row.vault_id, row.vector_id): row for row in current_rows}
        upsert_chunks = [chunk_by_key[(item.collection_id, item.item_id)] for item in generic_plan.upserts]
        tombstones = [
            _tombstone_for_row(row_by_key[(row.collection_id, row.record_id)]) for row in generic_plan.deletions
        ]
        metadata_update_chunks = [
            chunk_by_key[(item.collection_id, item.item_id)] for item in generic_plan.metadata_updates
        ]
        if metadata_update_chunks and not _supports_metadata_update(self._vector_store):
            # A store without metadata-only writes gets the earlier behavior: replace and re-embed.
            upsert_chunks.extend(metadata_update_chunks)
            tombstones.extend(
                _tombstone_for_row(row_by_key[(item.collection_id, item.record_id)])
                for item in generic_plan.metadata_updates
            )
            metadata_update_chunks = []
        unchanged_count = generic_plan.unchanged_count

        health_warnings = () if backend_health.ok and backend_health.schema_compatible else (backend_health.message,)
        warnings = health_warnings + manifest_warnings + _model_limit_warnings(upsert_chunks, self._text_embeddings)
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
            metadata_update_chunks=tuple(sorted(metadata_update_chunks, key=_chunk_sort_key)),
        )

    def apply(self, *, scopes: tuple[QueryScope, ...], full: bool = False) -> VectorApplyResult:
        try:
            plan = self.plan(scopes=scopes, full=full)
        except Exception as exc:
            return self.plan_failure(scopes=scopes, full=full, error=str(exc))
        try:
            # One store write per embedding batch bounds memory to one batch of vectors.
            # Tombstones go with the first write: stores delete before they upsert, so a
            # replaced record is removed before any batch writes it again.
            tombstones = plan.tombstones
            wrote = False
            for batch in self._embedding_batches(plan.upsert_chunks):
                self._vector_store.apply_vector_revision(
                    vector_index_revision=plan.vector_index_revision,
                    records=tuple(
                        self._record_for_chunk(plan=plan, chunk=chunk, embedding=embedding)
                        for chunk, embedding in batch
                    ),
                    tombstones=tombstones,
                )
                tombstones = ()
                wrote = True
            if not wrote:
                self._vector_store.apply_vector_revision(
                    vector_index_revision=plan.vector_index_revision,
                    records=(),
                    tombstones=tombstones,
                )
            self._update_metadata(plan)
            return VectorApplyResult.from_plan(plan, failed=False, error=None)
        except Exception as exc:
            return VectorApplyResult.from_plan(plan, failed=True, error=str(exc), failed_stage="apply")

    def _update_metadata(self, plan: VectorRevisionPlan) -> None:
        if not plan.metadata_update_chunks:
            return
        store = self._vector_store
        if not isinstance(store, VectorMetadataUpdater):
            raise VectorStoreError("vector store cannot update metadata")
        backend_schema_version = store.health().schema_version
        chunks = plan.metadata_update_chunks
        for start in range(0, len(chunks), METADATA_UPDATE_BATCH_SIZE):
            store.update_metadata(
                tuple(
                    VectorMetadataRecord(
                        vector_id=stable_vector_id(
                            vault_id=chunk.vault_id, chunk_id=chunk.chunk_id, embedding_spec=plan.embedding_spec
                        ),
                        vault_id=chunk.vault_id,
                        document_id=chunk.document_id,
                        chunk_id=chunk.chunk_id,
                        content_scope=_content_scope_for_path(chunk.path),
                        embedding_spec=plan.embedding_spec,
                        source_chunk_hash=chunk.content_hash,
                        chunker_version=chunk.chunker_version,
                        metadata_index_revision=chunk.index_revision or "unknown",
                        vector_index_revision=plan.vector_index_revision,
                        backend_schema_version=backend_schema_version,
                        source_role=chunk.source_role,
                        provenance_family_id=_family_id_for_chunk(chunk),
                        embedding_key=embedding_key(chunk, plan.embedding_spec),
                        metadata_fingerprint=_chunk_metadata_fingerprint(chunk, backend_schema_version),
                    )
                    for chunk in chunks[start : start + METADATA_UPDATE_BATCH_SIZE]
                )
            )

    def plan_failure(self, *, scopes: tuple[QueryScope, ...], full: bool, error: str) -> VectorApplyResult:
        """A failed result for a run whose plan could not be made. Nothing was written."""
        return VectorApplyResult(
            vector_index_revision="",
            mode="full" if full else "incremental",
            scopes=scopes,
            embedding_spec=self._text_embeddings.model_spec(),
            embedding_batch_size=self._embedding_batch_size,
            embedding_parallelism=self._embedding_parallelism,
            embedding_lazy_load=self._embedding_lazy_load,
            upsert_count=0,
            tombstone_count=0,
            unchanged_count=0,
            embedding_count=0,
            warnings=(),
            failed=True,
            error=error,
            failed_stage="plan",
        )

    def _embedding_batches(
        self, chunks: tuple[ChunkSnapshot, ...]
    ) -> Iterator[tuple[tuple[ChunkSnapshot, EmbeddingVector], ...]]:
        _validate_unique_chunk_ids(chunks)
        chunk_by_key = {(chunk.vault_id, chunk.chunk_id): chunk for chunk in chunks}
        items = tuple(
            IndexItem(
                chunk.vault_id,
                chunk.chunk_id,
                chunk.chunk_id,
                embedding_input_for(chunk),
                chunk.content_hash,
            )
            for chunk in chunks
        )
        batches = iter_embedding_batches(
            items,
            _EmbeddingProvider(self._text_embeddings),
            token_budget=self._embedding_token_budget,
            max_batch_items=self._embedding_batch_size,
        )
        spec = self._text_embeddings.model_spec()
        while True:
            try:
                batch: EmbeddingBatch = next(batches)
            except StopIteration:
                return
            except VectorIndexError as exc:
                message = str(exc).replace("input item IDs", "input chunk IDs")
                raise TextEmbeddingsError(message) from exc
            yield tuple(
                (
                    chunk_by_key[(item.collection_id, item.item_id)],
                    EmbeddingVector(
                        _embedding_input_id(chunk_by_key[(item.collection_id, item.item_id)]), vector.values, spec
                    ),
                )
                for item, vector in zip(batch.items, batch.vectors, strict=True)
            )

    def _record_for_chunk(
        self,
        *,
        plan: VectorRevisionPlan,
        chunk: ChunkSnapshot,
        embedding: EmbeddingVector,
    ) -> VectorEmbeddingRecord:
        backend_schema_version = self._vector_store.health().schema_version
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
            backend_schema_version=backend_schema_version,
            source_role=chunk.source_role,
            provenance_family_id=_family_id_for_chunk(chunk),
            embedding_key=embedding_key(chunk, plan.embedding_spec),
            metadata_fingerprint=_chunk_metadata_fingerprint(chunk, backend_schema_version),
        )


def _model_limit_warnings(chunks: list[ChunkSnapshot], text_embeddings: TextEmbeddings) -> tuple[str, ...]:
    """One line when session windows embedded in this run have a model input over 512 tokens (spec §4.2.6-11).

    Counts with the provider's tokenizer when it has one, else with the byte estimate the embedding
    batches use. The line says which.
    """
    if isinstance(text_embeddings, ModelTokenCounter):
        count_tokens = text_embeddings.count_model_tokens
        method = "the model tokenizer"
    else:
        count_tokens = estimate_tokens_from_bytes
        method = "a byte estimate (UTF-8 bytes / 3)"
    count = count_over_model_limit(
        (embedding_input_for(chunk) for chunk in chunks if chunk.chunker_version in SESSION_WINDOW_CHUNKER_VERSIONS),
        count_tokens,
    )
    warning = model_limit_warning(count)
    return () if warning is None else (f"{warning}; counted with {method}",)


def stable_vector_id(*, vault_id: str, chunk_id: str, embedding_spec: EmbeddingModelSpec) -> str:
    return stable_id("vector", vault_id, chunk_id, _embedding_spec_key(embedding_spec))


def embedding_key(chunk: ChunkSnapshot, embedding_spec: EmbeddingModelSpec) -> str:
    """Spec 4.3.2: equal keys mean an equal model input, so the stored vector stays valid."""
    return embedding_key_for_text(embedding_spec, embedding_input_for(chunk))


def embedding_key_for_text(embedding_spec: EmbeddingModelSpec, embedding_input: str) -> str:
    """The embedding key of one model input. The embedding cache (spec 4.3.5) stores vectors under it."""
    return hashlib.sha256(f"{_embedding_spec_key(embedding_spec)}\n{embedding_input}".encode()).hexdigest()


def _embedding_spec_key(spec: EmbeddingModelSpec) -> str:
    return "|".join((spec.model_name, spec.model_version, str(spec.dimensions), spec.spec_version))


def _chunks_for_scopes(*, chunk_store: ChunkListingStore, scopes: tuple[QueryScope, ...]) -> tuple[ChunkSnapshot, ...]:
    return tuple(chunk for scope in scopes for chunk in chunk_store.list_chunks(scope))


def _manifest_for_scopes(
    *,
    vector_store: VectorStore,
    scopes: tuple[QueryScope, ...],
) -> tuple[tuple[VectorManifestRecord, ...], tuple[str, ...]]:
    """Stored vectors in `scopes` and any warning from reading them.

    A store with a manifest table answers from the table, so planning never lists the vector store.
    """
    if isinstance(vector_store, VectorManifestSource):
        read = vector_store.manifest_rows(tuple(dict.fromkeys(vault for scope in scopes for vault in scope.vault_ids)))
        rows = tuple(row for scope in scopes for row in read.rows if _row_in_scope(row, scope))
        return rows, read.warnings
    return tuple(row for scope in scopes for row in vector_store.export_manifest(scope)), ()


def _row_in_scope(row: VectorManifestRecord, scope: QueryScope) -> bool:
    return row.vault_id in scope.vault_ids and any(
        row.content_scope == content_scope or row.content_scope.startswith(f"{content_scope}/")
        for content_scope in scope.content_scopes
    )


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


def _chunk_metadata_fingerprint(chunk: ChunkSnapshot, backend_schema_version: str) -> str:
    return _fingerprint(
        (
            chunk.index_revision or "unknown",
            backend_schema_version,
            chunk.source_role,
            _family_id_for_chunk(chunk),
            chunk.chunker_version,
        )
    )


def _row_metadata_fingerprint(row: VectorManifestRecord) -> str:
    return _fingerprint(
        (
            row.metadata_index_revision,
            row.backend_schema_version,
            row.source_role,
            row.provenance_family_id,
            row.chunker_version,
        )
    )


def _stored_keys(
    row: VectorManifestRecord,
    *,
    chunk: ChunkSnapshot | None,
    item: IndexItem | None,
    embedding_spec: EmbeddingModelSpec,
    backend_schema_version: str,
    keeps_keys: bool,
) -> tuple[str, str]:
    """The stored row's embedding key and metadata fingerprint, as the generic plan compares them.

    A row without an embedding key comes from a generation before spec 4.3.2 or from a store that
    does not keep keys. Its key is the desired chunk's key when the embedding input is known to be
    equal. For a table store the metadata fingerprint is then empty, so the plan writes the key once.
    Otherwise the key can never match and the chunk is embedded again.
    """
    if isinstance(row, VectorManifestRow) and row.embedding_key:
        return row.embedding_key, row.metadata_fingerprint or _row_metadata_fingerprint(row)
    if (
        chunk is not None
        and item is not None
        and item.record_id == row.vector_id
        and _same_embedding_input(row, chunk, embedding_spec, backend_schema_version)
    ):
        return item.fingerprint, "" if keeps_keys else _row_metadata_fingerprint(row)
    return f"legacy:{_row_fingerprint(row)}", _row_metadata_fingerprint(row)


def _same_embedding_input(
    row: VectorManifestRecord, chunk: ChunkSnapshot, embedding_spec: EmbeddingModelSpec, backend_schema_version: str
) -> bool:
    """The first transition run rule (spec 4.3.2), plus the earlier whole-fingerprint match."""
    if row.embedding_spec != embedding_spec:
        return False
    if (
        row.chunker_version == CHUNKER_VERSION
        and chunk.chunker_version == CHUNKER_VERSION
        and row.source_chunk_hash == chunk.content_hash
    ):
        return True
    return _row_fingerprint(row) == _chunk_fingerprint(chunk, backend_schema_version)


def _supports_metadata_update(store: VectorStore) -> bool:
    return isinstance(store, VectorMetadataUpdater) and store.supports_metadata_update()


def _chunk_fingerprint(chunk: ChunkSnapshot, backend_schema_version: str) -> str:
    """The whole-record fingerprint used before spec 4.3.2. Only matches rows that have no embedding key."""
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
