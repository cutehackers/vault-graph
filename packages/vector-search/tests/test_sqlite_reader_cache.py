"""Spec 2026-11-11 §4.2.6: read-only search reads the database again only when its files change."""

from __future__ import annotations

from pathlib import Path

import pytest

from vector_search import ChromaVectorStore, CollectionSpec, StoredVector
from vector_search.sqlite_reader import ChromaSQLiteReader


@pytest.fixture
def spec() -> CollectionSpec:
    return CollectionSpec("vectors_model_a", 2, metadata={"model": "a"})


def _count_reads(monkeypatch: pytest.MonkeyPatch) -> dict[str, int]:
    counts = {"manifest": 0, "vectors": 0}
    read_manifest = ChromaSQLiteReader._read_manifest
    read_vectors = ChromaSQLiteReader._vectors

    def counting_manifest(self: ChromaSQLiteReader) -> object:
        counts["manifest"] += 1
        return read_manifest(self)

    def counting_vectors(self: ChromaSQLiteReader, *args: object) -> object:
        counts["vectors"] += 1
        return read_vectors(self, *args)  # type: ignore[arg-type]

    monkeypatch.setattr(ChromaSQLiteReader, "_read_manifest", counting_manifest)
    monkeypatch.setattr(ChromaSQLiteReader, "_vectors", counting_vectors)
    return counts


def test_repeated_search_on_unchanged_files_reads_the_database_once(
    tmp_path: Path, spec: CollectionSpec, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "vectors"
    writer = ChromaVectorStore(path, initialize=True)
    writer.apply(
        ((spec, StoredVector("a", (1.0, 0.0), {"order": "a"})), (spec, StoredVector("b", (0.0, 1.0), {"order": "b"})))
    )
    writer.close()
    counts = _count_reads(monkeypatch)

    first = ChromaVectorStore(path, read_only=True).search(spec, (1.0, 0.0), 2)
    second = ChromaVectorStore(path, read_only=True).search(spec, (1.0, 0.0), 2)
    ChromaVectorStore(path, read_only=True).export_manifest()

    assert first == second
    assert [hit.record_id for hit in first] == ["a", "b"]
    assert counts == {"manifest": 1, "vectors": 1}


def test_search_after_a_write_reads_the_new_records(tmp_path: Path, spec: CollectionSpec) -> None:
    path = tmp_path / "vectors"
    writer = ChromaVectorStore(path, initialize=True)
    writer.apply(((spec, StoredVector("a", (0.0, 1.0), {"order": "a"})),))
    writer.close()
    reader = ChromaVectorStore(path, read_only=True)
    assert [hit.record_id for hit in reader.search(spec, (1.0, 0.0), 2)] == ["a"]

    writer = ChromaVectorStore(path)
    writer.apply(((spec, StoredVector("b", (1.0, 0.0), {"order": "b"})),))
    writer.close()

    assert [hit.record_id for hit in reader.search(spec, (1.0, 0.0), 2)] == ["b", "a"]
    assert [row.record_id for row in reader.export_manifest()] == ["a", "b"]
