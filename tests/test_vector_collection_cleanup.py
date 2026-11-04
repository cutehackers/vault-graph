from pathlib import Path
from typing import Any

import chromadb
import pytest

from tests.test_vector_store_contract import SECOND_SPEC, SPEC, make_query, make_record
from vault_graph.errors import VectorStoreError
from vault_graph.operation.scope.vault_catalog import QueryScope
from vault_graph.storage.interfaces.text_embeddings import EmbeddingModelSpec
from vault_graph.storage.interfaces.vector_store import VectorEmbeddingRecord, VectorTombstone
from vault_graph.storage.local.vector_store_adapter import ChromaVectorStore, _collection_spec

THIRD_SPEC = EmbeddingModelSpec(
    model_name="third-model",
    model_version="v3",
    dimensions=SPEC.dimensions,
    spec_version="third-spec-v1",
)
WIKI = QueryScope(vault_ids=("default",), content_scopes=("wiki",))


def _record(spec: EmbeddingModelSpec, path: str = "wiki/page.md") -> VectorEmbeddingRecord:
    return make_record(vault_id="default", path=path, text="alpha", content_scope="wiki", model_spec=spec)


def _tombstone(record: VectorEmbeddingRecord) -> VectorTombstone:
    return VectorTombstone(
        vector_id=record.vector_id,
        vault_id=record.vault_id,
        chunk_id=record.chunk_id,
        embedding_spec=record.embedding.model_spec,
    )


def _close(client: Any) -> None:
    # `ClientAPI` stubs omit close(); the runtime client has it.
    client.close()


def _collection_names(path: Path) -> set[str]:
    client = chromadb.PersistentClient(path=str(path.resolve()))
    try:
        return {collection.name for collection in client.list_collections()}
    finally:
        _close(client)


def _seed(path: Path) -> tuple[ChromaVectorStore, VectorEmbeddingRecord]:
    """Current-spec collection with a record, one empty old collection, one old collection with a record."""

    store = ChromaVectorStore(path, initialize=True)
    current = _record(SPEC)
    emptied = _record(SECOND_SPEC)
    store.apply_vector_revision(
        vector_index_revision="vector-1",
        records=(current, emptied, _record(THIRD_SPEC, "wiki/other.md")),
        tombstones=(),
    )
    store.apply_vector_revision(vector_index_revision="vector-2", records=(), tombstones=(_tombstone(emptied),))
    return store, current


def test_removes_only_empty_old_prefixed_collections(tmp_path: Path) -> None:
    path = tmp_path / "chroma"
    store, current = _seed(path)
    client = chromadb.PersistentClient(path=str(path.resolve()))
    client.create_collection(name="other_prefix_empty", embedding_function=None)
    _close(client)

    removed = store.remove_empty_collections(keep=SPEC)

    assert removed == (_collection_spec(SECOND_SPEC).name,)
    assert _collection_names(path) == {
        _collection_spec(SPEC).name,
        _collection_spec(THIRD_SPEC).name,
        "other_prefix_empty",
    }
    # The generic store's own client stays usable after the second client opened and closed (spec 7.10).
    store.apply_vector_revision(
        vector_index_revision="vector-1", records=(_record(SPEC, "wiki/new.md"),), tombstones=()
    )
    hits = store.search(make_query(text="alpha", scope=WIKI))
    assert current.vector_id in {hit.vector_id for hit in hits}
    assert len(hits) == 2
    store.close()


def test_keeps_current_spec_collection_even_when_empty(tmp_path: Path) -> None:
    path = tmp_path / "chroma"
    store = ChromaVectorStore(path, initialize=True)
    current = _record(SPEC)
    store.apply_vector_revision(vector_index_revision="vector-1", records=(current,), tombstones=())
    store.apply_vector_revision(vector_index_revision="vector-2", records=(), tombstones=(_tombstone(current),))

    assert store.remove_empty_collections(keep=SPEC) == ()
    assert _collection_names(path) == {_collection_spec(SPEC).name}
    store.close()


def test_read_only_store_raises_and_deletes_nothing(tmp_path: Path) -> None:
    path = tmp_path / "chroma"
    writer, _ = _seed(path)
    writer.close()
    before = _collection_names(path)
    reader = ChromaVectorStore(path, read_only=True)

    with pytest.raises(VectorStoreError):
        reader.remove_empty_collections(keep=SPEC)

    assert _collection_names(path) == before
    assert len(before) == 3


def test_missing_store_folder_removes_nothing(tmp_path: Path) -> None:
    path = tmp_path / "missing"
    store = ChromaVectorStore(path)

    assert store.remove_empty_collections(keep=SPEC) == ()
    assert not path.exists()


def test_old_records_survive_cleanup(tmp_path: Path) -> None:
    path = tmp_path / "chroma"
    store, _ = _seed(path)

    store.remove_empty_collections(keep=SPEC)

    manifest = store.export_manifest(WIKI)
    assert {row.embedding_spec for row in manifest} == {SPEC, THIRD_SPEC}
    store.close()
