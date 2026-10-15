import hashlib
from dataclasses import replace
from pathlib import Path

import pytest
from text_embeddings import EmbeddingInput, EmbeddingModelSpec, EmbeddingVector
from vector_search import ChromaVectorStore

from vector_index import ChromaIndexStore, IndexItem, VectorIndex, VectorIndexError


class Provider:
    def __init__(self, version: str = "v1") -> None:
        self.spec = EmbeddingModelSpec("fixture", version, 2, "v1")
        self.calls = 0

    def model_spec(self) -> EmbeddingModelSpec:
        return self.spec

    def embed(self, inputs: tuple[EmbeddingInput, ...]) -> tuple[EmbeddingVector, ...]:
        self.calls += 1
        return tuple(
            EmbeddingVector(item.input_id, (1.0, 0.0) if item.text == "east" else (0.0, 1.0), self.spec)
            for item in inputs
        )


def fingerprints(path: Path) -> dict[str, str]:
    return {
        str(row.relative_to(path)): hashlib.sha256(row.read_bytes()).hexdigest()
        for row in path.rglob("*")
        if row.is_file()
    }


def test_index_search_reopen_partial_update_model_change_and_scope_delete(tmp_path: Path) -> None:
    path = tmp_path / "vectors"
    store = ChromaVectorStore(path, initialize=True)
    codec = ChromaIndexStore(store)
    provider = Provider()
    index = VectorIndex(codec, provider, batch_size=1)
    items = (
        IndexItem("notes", "a", "same-id", "east", "east-v1"),
        IndexItem("other", "a", "same-id", "north", "north-v1"),
    )
    plan = index.plan(items, collection_ids=("notes", "other"), input_kind="snapshot")
    index.apply(plan)
    with pytest.raises(VectorIndexError, match="stale"):
        index.apply(plan)
    assert len(codec.manifest(("notes", "other"))) == 2
    assert index.plan(items, collection_ids=("notes", "other"), input_kind="snapshot").unchanged_count == 2
    spec = codec.collection_spec(plan.space_id, 2)
    hits = store.search(spec, (1.0, 0.0), 1, predicate=lambda metadata: metadata["collection_id"] == "notes")
    assert hits[0].metadata["item_id"] == "a"
    assert hits[0].score == pytest.approx(1.0)
    store.close()

    before = fingerprints(path)
    reader = ChromaVectorStore(path, read_only=True)
    assert reader.search(spec, (1.0, 0.0), 1)[0].score == pytest.approx(1.0)
    assert fingerprints(path) == before
    reader.close()

    store = ChromaVectorStore(path)
    codec = ChromaIndexStore(store)
    index = VectorIndex(codec, Provider("v2"))
    changed = (replace(items[0], text="north", fingerprint="north-v2"),)
    second = index.plan(changed, collection_ids=("notes",), input_kind="changes")
    assert len(second.deletions) == 1
    index.apply(second)
    assert len(codec.manifest(("notes", "other"))) == 2
    assert codec.manifest(("other",))[0].space_id == plan.space_id
    empty = index.plan((), collection_ids=("notes",), input_kind="snapshot")
    index.apply(empty)
    assert codec.manifest(("notes",)) == ()
    assert len(codec.manifest(("other",))) == 1
    store.close()


@pytest.mark.parametrize("wrong_collection", [True, False])
def test_manifest_rejects_copied_metadata_with_wrong_physical_identity(tmp_path: Path, wrong_collection: bool) -> None:
    from vector_search import CollectionSpec, StoredVector

    from vector_index import VectorIndexError

    store = ChromaVectorStore(tmp_path / "vectors", initialize=True)
    codec = ChromaIndexStore(store)
    expected = codec.collection_spec("declared", 2)
    spec = CollectionSpec("vectors_wrong", 2, metadata={"space_id": "declared"}) if wrong_collection else expected
    store.apply(
        (
            (
                spec,
                StoredVector(
                    "forged",
                    (1.0, 0.0),
                    {
                        "collection_id": "notes",
                        "item_id": "a",
                        "record_id": "claimed",
                        "space_id": "declared",
                        "fingerprint": "same",
                        "dimensions": 2,
                    },
                ),
            ),
        )
    )
    with pytest.raises(VectorIndexError, match="storage identity"):
        codec.manifest(("notes",))
    store.close()
