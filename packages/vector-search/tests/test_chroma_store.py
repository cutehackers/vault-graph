from __future__ import annotations

import hashlib
import sqlite3
from pathlib import Path

import pytest

from vector_search import ChromaVectorStore, CollectionSpec, StoredVector, VectorDeletion, VectorSearchError


@pytest.fixture
def spec() -> CollectionSpec:
    return CollectionSpec("vectors_model_a", 2, metadata={"model": "a", "version": "1"})


def _snapshot(path: Path) -> dict[str, str]:
    return {
        str(file.relative_to(path)): hashlib.sha256(file.read_bytes()).hexdigest()
        for file in path.rglob("*")
        if file.is_file()
    }


def test_readonly_reopen_filters_ranks_and_does_not_write(tmp_path: Path, spec: CollectionSpec) -> None:
    path = tmp_path / "vectors"
    writer = ChromaVectorStore(path, initialize=True)
    writer.apply(
        (
            (spec, StoredVector("z", (1.0, 0.0), {"category": "keep", "order": "z"})),
            (spec, StoredVector("a", (1.0, 0.0), {"category": "keep", "order": "a"})),
            (spec, StoredVector("n", (1.0, 0.0), {"category": "omit", "order": "n"})),
        )
    )
    writer.close()
    before = _snapshot(path)
    reader = ChromaVectorStore(path, read_only=True)
    hits = reader.search(
        spec,
        (1.0, 0.0),
        2,
        predicate=lambda metadata: metadata["category"] == "keep",
        tie_key=lambda metadata, record_id: (metadata["order"], record_id),
        vector_id_batch_size=1,
    )
    assert tuple((hit.record_id, hit.rank) for hit in hits) == (("a", 1), ("z", 2))
    assert all(abs(hit.score - 1.0) < 1e-6 for hit in hits)
    assert tuple(row.record_id for row in reader.export_manifest()) == ("a", "n", "z")
    assert _snapshot(path) == before


def test_delete_requires_matching_metadata_and_retains_payload(tmp_path: Path, spec: CollectionSpec) -> None:
    path = tmp_path / "vectors"
    writer = ChromaVectorStore(path, initialize=True)
    writer.apply(((spec, StoredVector("a", (1.0, 0.0), {"owner": "one"})),))
    writer.apply(deletions=(VectorDeletion(spec, "a", {"owner": "other"}),))
    writer.close()
    assert [row.record_id for row in ChromaVectorStore(path, read_only=True).search(spec, (1.0, 0.0), 1)] == ["a"]
    writer = ChromaVectorStore(path)
    writer.apply(deletions=(VectorDeletion(spec, "a", {"owner": "one"}),))
    writer.close()
    assert ChromaVectorStore(path, read_only=True).export_manifest() == ()


def test_collection_compatibility_rejects_metadata_and_dimensions(tmp_path: Path, spec: CollectionSpec) -> None:
    path = tmp_path / "vectors"
    writer = ChromaVectorStore(path, initialize=True)
    writer.apply(((spec, StoredVector("a", (1.0, 0.0), {"owner": "one"})),))
    writer.close()
    reader = ChromaVectorStore(path, read_only=True)
    with pytest.raises(VectorSearchError, match="metadata incompatible"):
        reader.search(CollectionSpec(spec.name, 2, metadata={"model": "b"}), (1.0, 0.0), 1)
    with pytest.raises(VectorSearchError, match="dimensions incompatible"):
        reader.search(CollectionSpec(spec.name, 3, metadata=spec.metadata), (1.0, 0.0, 0.0), 1)


def test_missing_readonly_store_does_not_create_files(tmp_path: Path, spec: CollectionSpec) -> None:
    path = tmp_path / "missing"
    reader = ChromaVectorStore(path, read_only=True)
    assert reader.search(spec, (1.0, 0.0), 1) == ()
    assert reader.export_manifest() == ()
    assert not reader.health().ok
    assert not path.exists()


def test_same_record_id_in_distinct_collections_keeps_each_payload(tmp_path: Path, spec: CollectionSpec) -> None:
    path = tmp_path / "vectors"
    second = CollectionSpec("vectors_model_b", 2, metadata={"model": "b"})
    writer = ChromaVectorStore(path, initialize=True)
    writer.apply(
        (
            (spec, StoredVector("same", (1.0, 0.0), {"model": "a"})),
            (second, StoredVector("same", (0.0, 1.0), {"model": "b"})),
        )
    )
    writer.close()
    reader = ChromaVectorStore(path, read_only=True)
    assert reader.search(spec, (1.0, 0.0), 1)[0].score == pytest.approx(1.0)
    assert reader.search(second, (1.0, 0.0), 1)[0].score == pytest.approx(0.0)


@pytest.mark.parametrize(
    "metadata",
    (
        {"model": "wrong"},
        {"_vector_dimensions": 3},
        {"_vector_distance_metric": "l2"},
    ),
)
def test_conflicting_collection_metadata_rejected_before_store_mutation(
    tmp_path: Path, metadata: dict[str, str | int]
) -> None:
    path = tmp_path / "vectors"
    spec = CollectionSpec("vectors_model_a", 2, metadata=metadata)
    store = ChromaVectorStore(path, expected_collection_metadata={"model": "expected"})
    with pytest.raises(VectorSearchError, match="collection metadata incompatible"):
        store.apply(((spec, StoredVector("item", (1.0, 0.0), {"owner": "one"})),))
    assert not path.exists()


def test_conflicting_deletion_does_not_apply_earlier_valid_change(tmp_path: Path) -> None:
    path = tmp_path / "vectors"
    valid = CollectionSpec("vectors_model_a", 2, metadata={"model": "expected"})
    writer = ChromaVectorStore(path, initialize=True, expected_collection_metadata={"model": "expected"})
    writer.apply(((valid, StoredVector("original", (1.0, 0.0), {"owner": "one"})),))
    writer.close()
    before = _snapshot(path)
    conflicting = CollectionSpec("vectors_model_b", 2, metadata={"model": "wrong"})
    writer = ChromaVectorStore(path, expected_collection_metadata={"model": "expected"})
    with pytest.raises(VectorSearchError, match="collection metadata incompatible"):
        writer.apply(
            ((valid, StoredVector("new", (0.0, 1.0), {"owner": "two"})),),
            (VectorDeletion(conflicting, "original"),),
        )
    assert _snapshot(path) == before


def test_queue_fallback_uses_collection_identity_when_ids_repeat(tmp_path: Path) -> None:
    path = tmp_path / "vectors"
    first = CollectionSpec("vectors_first", 2)
    second = CollectionSpec("vectors_second", 2)
    writer = ChromaVectorStore(path, initialize=True, payload_key_by_collection=False)
    writer.apply(
        (
            (first, StoredVector("same", (1.0, 0.0), {"group": "first"})),
            (second, StoredVector("same", (0.0, 1.0), {"group": "second"})),
        )
    )
    writer.close()
    with sqlite3.connect(path / "chroma.sqlite3") as connection:
        connection.execute("DROP TABLE vector_search_payloads")
    before = _snapshot(path)
    reader = ChromaVectorStore(path, read_only=True, payload_key_by_collection=False)
    assert reader.search(first, (1.0, 0.0), 1)[0].score == pytest.approx(1.0)
    assert reader.search(second, (1.0, 0.0), 1)[0].score == pytest.approx(0.0)
    assert _snapshot(path) == before


def test_incompatible_upsert_does_not_apply_prior_valid_deletion(tmp_path: Path) -> None:
    path = tmp_path / "vectors"
    first = CollectionSpec("vectors_first", 2, metadata={"model": "one"})
    second = CollectionSpec("vectors_second", 2, metadata={"model": "two"})
    writer = ChromaVectorStore(path, initialize=True)
    writer.apply(
        (
            (first, StoredVector("old", (1.0, 0.0), {"owner": "one"})),
            (second, StoredVector("other", (0.0, 1.0), {"owner": "two"})),
        )
    )
    writer.close()
    before = _snapshot(path)
    incompatible = CollectionSpec(second.name, 2, metadata={"model": "wrong"})
    writer = ChromaVectorStore(path)
    with pytest.raises(VectorSearchError, match="collection metadata incompatible"):
        writer.apply(
            ((incompatible, StoredVector("new", (1.0, 0.0), {"owner": "new"})),),
            (VectorDeletion(first, "old", {"owner": "one"}),),
        )
    writer.close()
    assert _snapshot(path) == before


@pytest.mark.parametrize("bad_value", (float("nan"), float("inf"), -float("inf")))
def test_nonfinite_vectors_rejected_before_deletion_and_search(tmp_path: Path, bad_value: float) -> None:
    path = tmp_path / "vectors"
    spec = CollectionSpec("vectors_first", 2)
    writer = ChromaVectorStore(path, initialize=True)
    writer.apply(((spec, StoredVector("old", (1.0, 0.0), {"owner": "one"})),))
    writer.close()
    before = _snapshot(path)
    writer = ChromaVectorStore(path)
    with pytest.raises(VectorSearchError, match="finite"):
        writer.apply(
            ((spec, StoredVector("new", (bad_value, 0.0), {"owner": "new"})),),
            (VectorDeletion(spec, "old", {"owner": "one"}),),
        )
    with pytest.raises(VectorSearchError, match="finite"):
        writer.search(spec, (bad_value, 0.0), 1)
    assert _snapshot(path) == before


def test_legacy_collection_markers_require_explicit_compatibility_settings(tmp_path: Path) -> None:
    path = tmp_path / "vectors"
    spec = CollectionSpec("vectors_legacy", 2, metadata={"custom_dimensions": 2})
    writer = ChromaVectorStore(path, initialize=True)
    writer.apply(((spec, StoredVector("item", (1.0, 0.0), {"owner": "one"})),))
    writer.close()
    with sqlite3.connect(path / "chroma.sqlite3") as connection:
        connection.execute(
            "DELETE FROM collection_metadata WHERE key IN ('_vector_dimensions', '_vector_distance_metric')"
        )
    before = _snapshot(path)
    with pytest.raises(VectorSearchError, match="dimensions incompatible"):
        ChromaVectorStore(path, read_only=True).search(spec, (1.0, 0.0), 1)
    compatible = ChromaVectorStore(
        path, read_only=True, dimension_metadata_key="custom_dimensions", default_distance_metric="cosine"
    )
    assert compatible.search(spec, (1.0, 0.0), 1)[0].record_id == "item"
    assert _snapshot(path) == before
