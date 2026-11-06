import sys
import types
from dataclasses import replace
from pathlib import Path
from typing import Any, cast

import pytest
from vector_index.indexing import estimate_tokens_from_bytes

from tests.fakes.deterministic_text_embeddings import DeterministicTextEmbeddings
from tests.fakes.in_memory_vector_store import InMemoryVectorStore
from vault_graph.errors import TextEmbeddingsError
from vault_graph.indexing.ingestion.document_chunking import contextual_embedding_text
from vault_graph.indexing.ingestion.document_normalizer import ChunkSnapshot
from vault_graph.indexing.vector_index_adapter import VectorIndexer
from vault_graph.interface.composition.adapters import text_embeddings as adapter
from vault_graph.interface.composition.adapters.text_embeddings import (
    EMBEDDING_PRESETS,
    FastEmbedTextEmbeddingsConfig,
    _default_backend_factory,
)
from vault_graph.operation.scope.vault_catalog import QueryScope
from vault_graph.storage.interfaces.text_embeddings import EmbeddingInput, EmbeddingModelSpec, EmbeddingVector
from vault_graph.storage.interfaces.vector_store import VectorEmbeddingRecord, VectorTombstone

SPEC = EmbeddingModelSpec(model_name="deterministic", model_version="v1", dimensions=4, spec_version="spec-v1")
SCOPE = QueryScope(vault_ids=("default",), content_scopes=("wiki",))


class ChunkStore:
    def __init__(self, chunks: tuple[ChunkSnapshot, ...]) -> None:
        self.chunks = chunks

    def list_chunks(self, scope: QueryScope) -> tuple[ChunkSnapshot, ...]:
        return tuple(chunk for chunk in self.chunks if chunk.vault_id in scope.vault_ids)


class RecordingVectorStore(InMemoryVectorStore):
    def __init__(self) -> None:
        super().__init__()
        self.calls: list[tuple[tuple[VectorEmbeddingRecord, ...], tuple[VectorTombstone, ...]]] = []

    def apply_vector_revision(
        self,
        *,
        vector_index_revision: str,
        records: tuple[VectorEmbeddingRecord, ...],
        tombstones: tuple[VectorTombstone, ...],
    ) -> None:
        self.calls.append((records, tombstones))
        super().apply_vector_revision(
            vector_index_revision=vector_index_revision, records=records, tombstones=tombstones
        )


class FailingAfter(DeterministicTextEmbeddings):
    def __init__(self, model_spec: EmbeddingModelSpec, *, ok_calls: int) -> None:
        super().__init__(model_spec)
        self._ok_calls = ok_calls

    def embed(self, inputs: tuple[EmbeddingInput, ...]) -> tuple[EmbeddingVector, ...]:
        if self._ok_calls == 0:
            raise TextEmbeddingsError("model crashed")
        self._ok_calls -= 1
        return super().embed(inputs)


def chunk(name: str, text: str) -> ChunkSnapshot:
    path = f"wiki/{name}.md"
    return ChunkSnapshot(
        vault_id="default",
        chunk_id=f"default:{path}:chunk",
        document_id=f"default:{path}:document",
        path=path,
        section="Page",
        anchor="page",
        text=text,
        token_count=len(text.split()),
        content_hash=f"hash:{name}:{text}",
        chunker_version="heading-section-v1",
        index_revision="metadata-1",
    )


def chunks(count: int) -> tuple[ChunkSnapshot, ...]:
    return tuple(chunk(f"page{index:02d}", "w " * (3 + 5 * index)) for index in range(count))


def _tokens(record: VectorEmbeddingRecord, by_chunk: dict[str, ChunkSnapshot]) -> int:
    source = by_chunk[record.chunk_id]
    return estimate_tokens_from_bytes(contextual_embedding_text(section_path=source.section_path, text=source.text))


def test_each_token_budget_batch_is_one_store_write() -> None:
    desired = chunks(12)
    store = RecordingVectorStore()
    indexer = VectorIndexer(
        chunk_store=ChunkStore(desired),
        vector_store=store,
        text_embeddings=DeterministicTextEmbeddings(SPEC),
        embedding_batch_size=4,
        embedding_token_budget=60,
    )

    result = indexer.apply(scopes=(SCOPE,))

    assert result.failed is False
    by_chunk = {item.chunk_id: item for item in desired}
    assert len(store.calls) > 1
    for records, _ in store.calls:
        assert 1 <= len(records) <= 4
        assert len(records) * max(_tokens(record, by_chunk) for record in records) <= 60
    written = [record.chunk_id for records, _ in store.calls for record in records]
    assert sorted(written) == sorted(by_chunk)
    assert len(store.export_manifest(SCOPE)) == 12


def test_tombstones_go_with_the_first_batch_only() -> None:
    first = chunks(6)
    store = RecordingVectorStore()
    VectorIndexer(
        chunk_store=ChunkStore(first), vector_store=store, text_embeddings=DeterministicTextEmbeddings(SPEC)
    ).apply(scopes=(SCOPE,))
    changed = tuple(replace(item, text=item.text + "changed", content_hash=item.content_hash + "x") for item in first)
    store.calls.clear()

    result = VectorIndexer(
        chunk_store=ChunkStore(changed),
        vector_store=store,
        text_embeddings=DeterministicTextEmbeddings(SPEC),
        embedding_batch_size=2,
    ).apply(scopes=(SCOPE,))

    assert result.failed is False
    assert result.tombstone_count == 6
    assert len(store.calls) == 3
    assert len(store.calls[0][1]) == 6
    assert all(tombstones == () for _, tombstones in store.calls[1:])
    assert {row.source_chunk_hash for row in store.export_manifest(SCOPE)} == {item.content_hash for item in changed}


def test_tombstones_without_upserts_are_one_write() -> None:
    store = RecordingVectorStore()
    VectorIndexer(
        chunk_store=ChunkStore(chunks(3)), vector_store=store, text_embeddings=DeterministicTextEmbeddings(SPEC)
    ).apply(scopes=(SCOPE,))
    store.calls.clear()

    VectorIndexer(
        chunk_store=ChunkStore(()), vector_store=store, text_embeddings=DeterministicTextEmbeddings(SPEC)
    ).apply(scopes=(SCOPE,))

    assert len(store.calls) == 1
    assert store.calls[0][0] == ()
    assert len(store.calls[0][1]) == 3


def test_failure_in_a_later_batch_keeps_earlier_batches_and_reports_apply_stage() -> None:
    store = RecordingVectorStore()
    indexer = VectorIndexer(
        chunk_store=ChunkStore(chunks(6)),
        vector_store=store,
        text_embeddings=FailingAfter(SPEC, ok_calls=1),
        embedding_batch_size=2,
    )

    result = indexer.apply(scopes=(SCOPE,))

    assert result.failed is True
    assert result.failed_stage == "apply"
    assert result.error == "model crashed"
    assert len(store.calls) == 1
    assert len(store.export_manifest(SCOPE)) == 2


# Config: token budget and ONNX CPU memory arena ----------------------------------------------


def _config(tmp_path: Path, **kwargs: Any) -> FastEmbedTextEmbeddingsConfig:
    return FastEmbedTextEmbeddingsConfig(preset=EMBEDDING_PRESETS["e5-small"], cache_dir=tmp_path, **kwargs)


def test_config_defaults_keep_batch_size_and_add_token_budget(tmp_path: Path) -> None:
    config = _config(tmp_path, embedding_batch_size=32)

    assert config.embedding_batch_size == 32
    assert config.embedding_token_budget == 8_192
    assert config.cpu_mem_arena is True


def test_token_budget_must_be_positive(tmp_path: Path) -> None:
    with pytest.raises(TextEmbeddingsError, match="embedding_token_budget"):
        _config(tmp_path, embedding_token_budget=0)


@pytest.mark.parametrize("arena", [True, False])
def test_cpu_mem_arena_reaches_fastembed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, arena: bool) -> None:
    constructions: list[dict[str, object]] = []
    module = types.ModuleType("fastembed")

    class TextEmbedding:
        def __init__(self, **kwargs: object) -> None:
            constructions.append(kwargs)

    cast(Any, module).TextEmbedding = TextEmbedding
    monkeypatch.setitem(sys.modules, "fastembed", module)
    preset = replace(EMBEDDING_PRESETS["e5-small"], fastembed_registration="builtin")
    monkeypatch.setattr(adapter, "_REGISTERED_CUSTOM_MODELS", set())

    _default_backend_factory(
        FastEmbedTextEmbeddingsConfig(preset=preset, cache_dir=tmp_path, cpu_mem_arena=arena), tmp_path / "snapshot"
    )

    assert constructions[0]["enable_cpu_mem_arena"] is arena


def test_index_service_passes_its_token_budget_to_the_vector_indexer(tmp_path: Path) -> None:
    from vault_graph.indexing.index_service import IndexService
    from vault_graph.operation.scope.vault_catalog import VaultCatalog, VaultCatalogEntry
    from vault_graph.storage.local.sqlite_metadata_store import SQLiteMetadataStore

    root = tmp_path / "vault"
    (root / "wiki").mkdir(parents=True)
    catalog = VaultCatalog.from_entries(
        entries=[VaultCatalogEntry.from_root(vault_id="main", root_path=root)], active_vault_id="main"
    )
    service = IndexService(
        catalog=catalog,
        metadata_store=SQLiteMetadataStore(tmp_path / "metadata.sqlite3", initialize=True),
        vector_store=InMemoryVectorStore(),
        text_embeddings=DeterministicTextEmbeddings(SPEC),
        embedding_token_budget=1_000,
    )

    assert service._vector_indexer(chunk_store=object())._embedding_token_budget == 1_000
