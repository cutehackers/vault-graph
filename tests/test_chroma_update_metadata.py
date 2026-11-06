"""Risk B2: Chroma `update(ids, metadatas)` changes metadata and leaves stored vectors unchanged."""

from pathlib import Path
from typing import Any

import chromadb
import pytest

from tests.test_vector_store_contract import make_query, make_record
from vault_graph.errors import VectorStoreError
from vault_graph.operation.scope.vault_catalog import QueryScope
from vault_graph.storage.interfaces.vector_store import (
    VectorEmbeddingRecord,
    VectorMetadataRecord,
    VectorMetadataUpdater,
)
from vault_graph.storage.local.chroma_vector_store import COLLECTION_PREFIX, ChromaVectorStore

SCOPE = QueryScope(vault_ids=("default",), content_scopes=("wiki",))


def metadata_record(record: VectorEmbeddingRecord, **changes: Any) -> VectorMetadataRecord:
    values: dict[str, Any] = {
        "vector_id": record.vector_id,
        "vault_id": record.vault_id,
        "document_id": record.document_id,
        "chunk_id": record.chunk_id,
        "content_scope": record.content_scope,
        "embedding_spec": record.embedding.model_spec,
        "source_chunk_hash": record.source_chunk_hash,
        "chunker_version": record.chunker_version,
        "metadata_index_revision": record.metadata_index_revision,
        "vector_index_revision": record.vector_index_revision,
        "backend_schema_version": record.backend_schema_version,
        "source_role": record.source_role,
        "provenance_family_id": record.provenance_family_id,
    }
    values.update(changes)
    return VectorMetadataRecord(**values)


def stored(path: Path) -> dict[str, tuple[tuple[float, ...], dict[str, Any]]]:
    client = chromadb.PersistentClient(path=str(path))
    try:
        result: dict[str, tuple[tuple[float, ...], dict[str, Any]]] = {}
        for collection in client.list_collections():
            if not collection.name.startswith(f"{COLLECTION_PREFIX}_"):
                continue
            loaded = collection.get(include=["embeddings", "metadatas"])
            vectors, metadatas = loaded["embeddings"], loaded["metadatas"]
            assert vectors is not None and metadatas is not None
            for record_id, vector, metadata in zip(loaded["ids"], vectors, metadatas, strict=True):
                result[str(record_id)] = (tuple(float(value) for value in vector), dict(metadata))
        return result
    finally:
        close = getattr(client, "close", None)
        if callable(close):
            close()


def test_update_metadata_keeps_vectors_and_changes_metadata(tmp_path: Path) -> None:
    path = tmp_path / "chroma"
    store = ChromaVectorStore(path, initialize=True)
    first = make_record(vault_id="default", path="wiki/a.md", text="alpha beta", content_scope="wiki")
    second = make_record(vault_id="default", path="wiki/b.md", text="gamma delta", content_scope="wiki")
    store.apply_vector_revision(vector_index_revision="vector-1", records=(first, second), tombstones=())
    hits_before = store.search(make_query(text="alpha beta", scope=SCOPE))
    store.close()
    before = stored(path)

    store = ChromaVectorStore(path, initialize=True)
    assert isinstance(store, VectorMetadataUpdater)
    assert store.supports_metadata_update() is True
    store.update_metadata(
        (
            metadata_record(
                first,
                metadata_index_revision="metadata-2",
                vector_index_revision="vector-2",
                source_role="operation_log",
                provenance_family_id="family:new",
            ),
        )
    )
    hits_after = store.search(make_query(text="alpha beta", scope=SCOPE))
    store.close()
    after = stored(path)

    assert {key: vector for key, (vector, _) in after.items()} == {key: vector for key, (vector, _) in before.items()}
    assert after[first.vector_id][1] == {
        **before[first.vector_id][1],
        "metadata_index_revision": "metadata-2",
        "vector_index_revision": "vector-2",
        "source_role": "operation_log",
        "provenance_family_id": "family:new",
    }
    assert after[second.vector_id][1] == before[second.vector_id][1]
    assert [(hit.vector_id, hit.score) for hit in hits_after] == [(hit.vector_id, hit.score) for hit in hits_before]
    assert hits_after[0].source_role == "operation_log"
    read_only_hits = ChromaVectorStore(path, read_only=True).search(make_query(text="alpha beta", scope=SCOPE))
    # The read-only path scores the payload table in Python, so scores match Chroma's only to float32 precision.
    assert [hit.vector_id for hit in read_only_hits] == [hit.vector_id for hit in hits_before]
    assert [hit.score for hit in read_only_hits] == pytest.approx([hit.score for hit in hits_before], abs=1e-6)
    assert read_only_hits[0].provenance_family_id == "family:new"


def test_update_metadata_rejects_unknown_vector(tmp_path: Path) -> None:
    store = ChromaVectorStore(tmp_path / "chroma", initialize=True)
    record = make_record(vault_id="default", path="wiki/a.md", text="alpha", content_scope="wiki")
    store.apply_vector_revision(vector_index_revision="vector-1", records=(record,), tombstones=())
    missing = make_record(vault_id="default", path="wiki/missing.md", text="beta", content_scope="wiki")

    with pytest.raises(VectorStoreError, match="unknown vector"):
        store.update_metadata((metadata_record(missing),))
    store.close()


def test_read_only_store_does_not_support_metadata_update(tmp_path: Path) -> None:
    store = ChromaVectorStore(tmp_path / "chroma", read_only=True)

    assert store.supports_metadata_update() is False
