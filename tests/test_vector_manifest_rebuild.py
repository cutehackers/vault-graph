"""A-15: the incremental vector plan reads the manifest table, never a Chroma listing."""

import sqlite3
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest
from vector_search import ChromaVectorStore as GenericChromaVectorStore

from tests.fakes.deterministic_text_embeddings import DeterministicTextEmbeddings
from tests.test_vector_indexer import SPEC, ChunkStore, chunk
from vault_graph.indexing.ingestion.document_normalizer import ChunkSnapshot
from vault_graph.indexing.vector_index_adapter import VectorIndexer, VectorRevisionPlan
from vault_graph.operation.scope.vault_catalog import QueryScope
from vault_graph.storage.interfaces.text_embeddings import EmbeddingInput, EmbeddingVector
from vault_graph.storage.interfaces.vector_manifest_store import VectorManifestRow
from vault_graph.storage.interfaces.vector_store import VectorManifestRecord
from vault_graph.storage.local.chroma_vector_store import COLLECTION_PREFIX, ChromaVectorStore
from vault_graph.storage.local.sqlite_vector_manifest_store import (
    ChromaSQLiteListing,
    ManifestTrackedVectorStore,
    SQLiteVectorManifestStore,
    manifest_path_for_vector_path,
)
from vault_graph.storage.local.vector_store_adapter import CHROMA_BACKEND

SCOPES = (QueryScope(vault_ids=("alpha", "beta"), content_scopes=("wiki",)),)


def open_store(vector_path: Path) -> ManifestTrackedVectorStore:
    return ManifestTrackedVectorStore(
        ChromaVectorStore(vector_path, initialize=True),
        manifest=SQLiteVectorManifestStore(manifest_path_for_vector_path(vector_path)),
        listing=ChromaSQLiteListing(vector_path, collection_prefix=COLLECTION_PREFIX, backend=CHROMA_BACKEND),
        backend=CHROMA_BACKEND,
    )


def chunks() -> tuple[ChunkSnapshot, ...]:
    return tuple(
        chunk(vault_id=vault, path=f"wiki/p{index}.md", text=f"text {index}")
        for vault in ("alpha", "beta")
        for index in range(5)
    )


def indexed(tmp_path: Path) -> tuple[Path, tuple[ChunkSnapshot, ...]]:
    vector_path = tmp_path / "vector" / "chroma"
    store = open_store(vector_path)
    VectorIndexer(
        chunk_store=ChunkStore(chunks()), vector_store=store, text_embeddings=DeterministicTextEmbeddings(SPEC)
    ).apply(scopes=SCOPES)
    store.close()
    # The next run changes one chunk and drops another.
    changed = tuple(
        replace(item, text="changed", content_hash="hash:changed") if item.path == "wiki/p1.md" else item
        for item in chunks()
        if not (item.vault_id == "beta" and item.path == "wiki/p4.md")
    )
    return vector_path, changed


def as_rows(records: tuple[VectorManifestRecord, ...]) -> tuple[VectorManifestRow, ...]:
    return tuple(VectorManifestRow.from_record(record) for record in records)


def plan_key(plan: VectorRevisionPlan) -> tuple[Any, ...]:
    return (
        tuple((item.vault_id, item.chunk_id) for item in plan.upsert_chunks),
        plan.tombstones,
        plan.unchanged_count,
    )


def incremental_plan(vector_path: Path, current: tuple[ChunkSnapshot, ...]) -> VectorRevisionPlan:
    store = open_store(vector_path)
    try:
        return VectorIndexer(
            chunk_store=ChunkStore(current), vector_store=store, text_embeddings=DeterministicTextEmbeddings(SPEC)
        ).plan(scopes=SCOPES)
    finally:
        store.close()


def chroma_plan(vector_path: Path, current: tuple[ChunkSnapshot, ...]) -> VectorRevisionPlan:
    store = ChromaVectorStore(vector_path, initialize=True)
    try:
        return VectorIndexer(
            chunk_store=ChunkStore(current), vector_store=store, text_embeddings=DeterministicTextEmbeddings(SPEC)
        ).plan(scopes=SCOPES)
    finally:
        store.close()


def forbid_chroma_listing(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail(*args: object, **kwargs: object) -> None:
        raise AssertionError("Chroma listing called during the incremental plan")

    monkeypatch.setattr(ChromaVectorStore, "export_manifest", fail)
    monkeypatch.setattr(GenericChromaVectorStore, "export_manifest", fail)
    monkeypatch.setattr(ChromaSQLiteListing, "rows", fail)


def test_apply_fills_the_table_to_match_chroma(tmp_path: Path) -> None:
    vector_path, _ = indexed(tmp_path)
    manifest = SQLiteVectorManifestStore(manifest_path_for_vector_path(vector_path))
    listing = ChromaSQLiteListing(vector_path, collection_prefix=COLLECTION_PREFIX, backend=CHROMA_BACKEND)

    assert manifest_path_for_vector_path(vector_path) == tmp_path / "vector" / "manifest.sqlite3"
    assert manifest.rows(("alpha", "beta")) == as_rows(listing.rows(("alpha", "beta")))
    assert {vault: manifest.count(vault) for vault in ("alpha", "beta")} == {"alpha": 5, "beta": 5}
    assert dict(listing.counts(("alpha", "beta"))) == {"alpha": 5, "beta": 5}


def test_incremental_plan_never_lists_chroma(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    vector_path, current = indexed(tmp_path)
    expected = plan_key(chroma_plan(vector_path, current))
    forbid_chroma_listing(monkeypatch)

    plan = incremental_plan(vector_path, current)

    assert plan_key(plan) == expected
    assert plan.upsert_count == 2
    assert plan.tombstone_count == 3
    assert plan.warnings == ()


def test_deleted_table_is_rebuilt_and_plan_is_the_same(tmp_path: Path) -> None:
    vector_path, current = indexed(tmp_path)
    expected = plan_key(incremental_plan(vector_path, current))
    manifest_path_for_vector_path(vector_path).unlink()

    plan = incremental_plan(vector_path, current)

    assert plan_key(plan) == expected
    assert plan.warnings == ("vector manifest table rebuilt from the vector store for alpha, beta: table missing",)
    assert SQLiteVectorManifestStore(manifest_path_for_vector_path(vector_path)).count("alpha") == 5


def test_deleted_row_is_rebuilt_and_plan_is_the_same(tmp_path: Path) -> None:
    vector_path, current = indexed(tmp_path)
    expected = plan_key(incremental_plan(vector_path, current))
    with sqlite3.connect(manifest_path_for_vector_path(vector_path)) as connection:
        connection.execute(
            "DELETE FROM vector_manifest WHERE vector_id = "
            "(SELECT vector_id FROM vector_manifest WHERE vault_id = 'alpha' LIMIT 1)"
        )
    connection.close()

    plan = incremental_plan(vector_path, current)

    assert plan_key(plan) == expected
    assert plan.warnings == (
        "vector manifest table rebuilt from the vector store for alpha: row count differs from the vector store",
    )
    assert SQLiteVectorManifestStore(manifest_path_for_vector_path(vector_path)).count("alpha") == 5


def test_rebuild_pages_through_chroma(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from vault_graph.storage.local import sqlite_vector_manifest_store

    vector_path, _ = indexed(tmp_path)
    listing = ChromaSQLiteListing(vector_path, collection_prefix=COLLECTION_PREFIX, backend=CHROMA_BACKEND)
    whole = listing.rows(("alpha", "beta"))
    monkeypatch.setattr(sqlite_vector_manifest_store, "CHROMA_PAGE_SIZE", 2)

    assert listing.rows(("alpha", "beta")) == whole
    assert len(whole) == 10


def test_only_batches_chroma_accepted_reach_the_table(tmp_path: Path) -> None:
    class FailingSecondBatch(DeterministicTextEmbeddings):
        calls = 0

        def embed(self, inputs: tuple[EmbeddingInput, ...]) -> tuple[EmbeddingVector, ...]:
            FailingSecondBatch.calls += 1
            if FailingSecondBatch.calls > 1:
                raise RuntimeError("model crashed")
            return super().embed(inputs)

    vector_path = tmp_path / "vector" / "chroma"
    store = open_store(vector_path)
    result = VectorIndexer(
        chunk_store=ChunkStore(chunks()),
        vector_store=store,
        text_embeddings=FailingSecondBatch(SPEC),
        embedding_batch_size=3,
    ).apply(scopes=SCOPES)
    store.close()

    manifest = SQLiteVectorManifestStore(manifest_path_for_vector_path(vector_path))
    listing = ChromaSQLiteListing(vector_path, collection_prefix=COLLECTION_PREFIX, backend=CHROMA_BACKEND)
    assert result.failed is True
    assert sum(manifest.count(vault) for vault in ("alpha", "beta")) == 3
    assert manifest.rows(("alpha", "beta")) == as_rows(listing.rows(("alpha", "beta")))
