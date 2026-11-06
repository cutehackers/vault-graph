from __future__ import annotations

from pathlib import Path

import pytest

from vector_search import ChromaVectorStore, CollectionSpec, StoredVector

# More rows than SQLite's default variable limit (32,766) so an unpaged metadata read can hit it.
_ROW_COUNT = 33_000


@pytest.fixture(scope="module")
def large_store(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, CollectionSpec]:
    path = tmp_path_factory.mktemp("paging") / "vectors"
    spec = CollectionSpec("vectors_model_a", 2, metadata={"model": "a", "version": "1"})
    writer = ChromaVectorStore(path, initialize=True)
    writer.apply(
        tuple((spec, StoredVector(f"r{index:05d}", (1.0, 0.0), {"order": index})) for index in range(_ROW_COUNT))
    )
    writer.close()
    return path, spec


def test_export_manifest_returns_every_row_of_a_collection_above_the_sqlite_variable_limit(
    large_store: tuple[Path, CollectionSpec],
) -> None:
    path, _ = large_store
    store = ChromaVectorStore(path)
    rows = store.export_manifest()
    store.close()
    assert len(rows) == _ROW_COUNT
    assert rows[0].record_id == "r00000"
    assert rows[-1].record_id == f"r{_ROW_COUNT - 1:05d}"


def test_unpaged_metadata_read_outcome_is_recorded(
    large_store: tuple[Path, CollectionSpec], record_property: object
) -> None:
    """Records whether a limit-free ``get`` fails on this Chroma build (spec risk B1); it does not assert either way."""

    path, spec = large_store
    store = ChromaVectorStore(path)
    collection = store._require_client().get_collection(spec.name)
    try:
        loaded = collection.get(include=["metadatas"])
        outcome = f"ok: {len(loaded.get('ids') or [])} rows"
    except Exception as exc:  # noqa: BLE001 - the outcome itself is what we record
        outcome = f"error: {exc}"
    finally:
        store.close()
    record_property("unpaged_get_outcome", outcome)  # type: ignore[operator]
    print(f"unpaged get with {_ROW_COUNT} rows -> {outcome}")


def test_export_manifest_applies_the_predicate_across_pages(large_store: tuple[Path, CollectionSpec]) -> None:
    path, _ = large_store
    store = ChromaVectorStore(path)
    rows = store.export_manifest(lambda metadata: int(metadata["order"]) % 1000 == 0)
    store.close()
    assert [row.record_id for row in rows] == [f"r{index:05d}" for index in range(0, _ROW_COUNT, 1000)]
