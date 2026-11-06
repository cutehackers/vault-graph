"""Embedding cache in Graph Home `cache/embeddings.sqlite3` (spec 4.3.5, A-17)."""

from __future__ import annotations

import sqlite3
from array import array
from pathlib import Path

from tests.fakes.deterministic_text_embeddings import DeterministicTextEmbeddings
from vault_graph.indexing.vector_index_adapter import embedding_key_for_text
from vault_graph.storage.interfaces.text_embeddings import EmbeddingInput, EmbeddingModelSpec, EmbeddingVector
from vault_graph.storage.local.embedding_cache import CachedTextEmbeddings, SQLiteEmbeddingCache

SPEC = EmbeddingModelSpec(model_name="deterministic", model_version="v1", dimensions=4, spec_version="spec-v1")
OTHER_SPEC = EmbeddingModelSpec(model_name="deterministic", model_version="v2", dimensions=4, spec_version="spec-v2")


class _Counting(DeterministicTextEmbeddings):
    def __init__(self, spec: EmbeddingModelSpec) -> None:
        super().__init__(spec)
        self.embedded: list[str] = []

    def embed(self, inputs: tuple[EmbeddingInput, ...]) -> tuple[EmbeddingVector, ...]:
        self.embedded.extend(item.text for item in inputs)
        return super().embed(inputs)


def _cached(
    path: Path, spec: EmbeddingModelSpec = SPEC, warnings: list[str] | None = None
) -> tuple[CachedTextEmbeddings, _Counting]:
    inner = _Counting(spec)
    sink = warnings if warnings is not None else []
    return (
        CachedTextEmbeddings(
            inner,
            SQLiteEmbeddingCache(path),
            key_for=embedding_key_for_text,
            run_id="run-1",
            warn=sink.append,
        ),
        inner,
    )


def _inputs(*texts: str) -> tuple[EmbeddingInput, ...]:
    return tuple(EmbeddingInput(f"id-{index}", text) for index, text in enumerate(texts))


def _float32(values: tuple[float, ...]) -> tuple[float, ...]:
    return tuple(array("f", values))


def test_second_embed_reads_cache_and_skips_model(tmp_path: Path) -> None:
    path = tmp_path / "cache" / "embeddings.sqlite3"
    first, first_inner = _cached(path)
    cold = first.embed(_inputs("alpha", "beta"))
    assert first_inner.embedded == ["alpha", "beta"]

    second, second_inner = _cached(path)
    warm = second.embed(_inputs("alpha", "beta"))

    assert second_inner.embedded == []
    assert [vector.values for vector in warm] == [vector.values for vector in cold]
    assert [vector.input_id for vector in warm] == ["id-0", "id-1"]
    assert all(vector.model_spec == SPEC for vector in warm)


def test_only_misses_go_to_model(tmp_path: Path) -> None:
    path = tmp_path / "embeddings.sqlite3"
    first, _ = _cached(path)
    first.embed(_inputs("alpha"))

    second, inner = _cached(path)
    result = second.embed(_inputs("alpha", "gamma"))

    assert inner.embedded == ["gamma"]
    assert [vector.input_id for vector in result] == ["id-0", "id-1"]


def test_cached_and_fresh_vectors_are_float32_values(tmp_path: Path) -> None:
    path = tmp_path / "embeddings.sqlite3"
    cached, inner = _cached(path)
    fresh = cached.embed(_inputs("alpha"))[0]
    expected = _float32(DeterministicTextEmbeddings(SPEC).embed(_inputs("alpha"))[0].values)

    assert fresh.values == expected
    again, _ = _cached(path)
    assert again.embed(_inputs("alpha"))[0].values == expected
    assert inner.embedded == ["alpha"]


def test_rebuilt_cache_gives_same_vectors(tmp_path: Path) -> None:
    path = tmp_path / "embeddings.sqlite3"
    first, _ = _cached(path)
    before = first.embed(_inputs("alpha", "beta"))
    path.unlink()

    rebuilt, inner = _cached(path)
    after = rebuilt.embed(_inputs("alpha", "beta"))

    assert inner.embedded == ["alpha", "beta"]
    assert [vector.values for vector in after] == [vector.values for vector in before]


def test_model_spec_change_does_not_mix_vectors(tmp_path: Path) -> None:
    path = tmp_path / "embeddings.sqlite3"
    first, _ = _cached(path, SPEC)
    first.embed(_inputs("alpha"))

    other, inner = _cached(path, OTHER_SPEC)
    other.embed(_inputs("alpha"))

    assert inner.embedded == ["alpha"]
    assert SQLiteEmbeddingCache(path).count() == 2


def test_queries_bypass_cache(tmp_path: Path) -> None:
    path = tmp_path / "embeddings.sqlite3"
    cached, inner = _cached(path)
    cached.embed_query("alpha")
    cached.embed_query("alpha")

    assert inner.embedded == ["alpha", "alpha"]
    assert not path.exists() or SQLiteEmbeddingCache(path).count() == 0


def test_retain_deletes_keys_outside_the_kept_set(tmp_path: Path) -> None:
    path = tmp_path / "embeddings.sqlite3"
    cached, _ = _cached(path)
    cached.embed(_inputs("alpha", "beta", "gamma"))
    keep = {embedding_key_for_text(SPEC, "alpha")}

    removed = SQLiteEmbeddingCache(path).retain(keep)

    assert removed == 2
    assert SQLiteEmbeddingCache(path).count() == 1
    again, inner = _cached(path)
    again.embed(_inputs("alpha", "beta"))
    assert inner.embedded == ["beta"]


def test_row_with_wrong_dimensions_is_a_miss(tmp_path: Path) -> None:
    path = tmp_path / "embeddings.sqlite3"
    cached, _ = _cached(path)
    cached.embed(_inputs("alpha"))
    with sqlite3.connect(path) as connection:
        connection.execute("UPDATE embeddings SET dimensions = 3, vector = ?", (array("f", (1.0, 2.0, 3.0)).tobytes(),))
    connection.close()

    again, inner = _cached(path)
    again.embed(_inputs("alpha"))

    assert inner.embedded == ["alpha"]


def test_corrupt_cache_embeds_without_cache_and_warns_once(tmp_path: Path) -> None:
    path = tmp_path / "embeddings.sqlite3"
    path.write_bytes(b"this is not a sqlite database" * 100)
    warnings: list[str] = []
    cached, inner = _cached(path, warnings=warnings)

    first = cached.embed(_inputs("alpha"))
    cached.embed(_inputs("alpha", "beta"))

    assert inner.embedded == ["alpha", "alpha", "beta"]
    assert first[0].input_id == "id-0"
    assert len(warnings) == 1
    assert "\n" not in warnings[0]
    assert "embedding cache" in warnings[0]
    assert cached.cache_failed


def test_remove_files_lets_next_run_build_a_new_cache(tmp_path: Path) -> None:
    path = tmp_path / "embeddings.sqlite3"
    path.write_bytes(b"garbage" * 200)
    cached, _ = _cached(path)
    cached.embed(_inputs("alpha"))

    SQLiteEmbeddingCache(path).remove_files()

    assert not path.exists()
    fresh, inner = _cached(path)
    fresh.embed(_inputs("alpha"))
    fresh.embed(_inputs("alpha"))
    assert inner.embedded == ["alpha"]


def test_last_used_run_is_recorded(tmp_path: Path) -> None:
    path = tmp_path / "embeddings.sqlite3"
    cached, _ = _cached(path)
    cached.embed(_inputs("alpha"))
    with sqlite3.connect(path) as connection:
        runs = connection.execute("SELECT last_used_run FROM embeddings").fetchall()
    connection.close()
    assert runs == [("run-1",)]
