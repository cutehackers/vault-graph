"""`vg index` with the Graph Home embedding cache (spec 4.3.5, A-17)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import chromadb
import pytest
from typer.testing import CliRunner

from tests.fakes.deterministic_text_embeddings import DeterministicTextEmbeddings
from tests.test_vector_indexer import SPEC
from vault_graph.errors import TextEmbeddingsError
from vault_graph.indexing.publication.projection_generation import ProjectionGenerationManager
from vault_graph.interface.cli.main import app
from vault_graph.storage.interfaces.text_embeddings import EmbeddingInput, EmbeddingVector
from vault_graph.storage.local.embedding_cache import SQLiteEmbeddingCache

runner = CliRunner()


class _Config:
    embedding_batch_size = 2
    embedding_parallelism = None
    embedding_lazy_load = True


class _Embeddings(DeterministicTextEmbeddings):
    config = _Config()
    inputs: list[str] = []
    # Embedding calls allowed before the model "dies". None means no limit.
    calls_before_failure: int | None = None

    def embed(self, inputs: tuple[EmbeddingInput, ...]) -> tuple[EmbeddingVector, ...]:
        if _Embeddings.calls_before_failure is not None:
            if _Embeddings.calls_before_failure == 0:
                raise TextEmbeddingsError("model died")
            _Embeddings.calls_before_failure -= 1
        _Embeddings.inputs.extend(item.text for item in inputs)
        return super().embed(inputs)


def _use(monkeypatch: pytest.MonkeyPatch) -> None:
    def factory(_: object) -> _Embeddings:
        return _Embeddings(SPEC)

    _Embeddings.inputs = []
    _Embeddings.calls_before_failure = None
    monkeypatch.setattr("vault_graph.interface.cli.main._text_embeddings", factory)
    monkeypatch.setattr("vault_graph.interface.cli.main._search_text_embeddings", factory)
    monkeypatch.setattr(
        "vault_graph.interface.composition.read_only_service_factory.ReadOnlyServiceFactory._search_text_embeddings",
        lambda self, catalog_service: factory(catalog_service),
    )
    monkeypatch.setattr("vault_graph.interface.composition.recall_index_refresh._catch_up_text_embeddings", factory)


def _write(root: Path, path: str, body: str) -> None:
    target = root / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(body, encoding="utf-8")


def _home(tmp_path: Path) -> tuple[Path, Path]:
    graph_home = tmp_path / "state"
    root = tmp_path / "vault"
    for index in range(5):
        _write(root, f"wiki/page-{index}.md", f"# Page {index}\nBody number {index} with its own words.\n")
    args = ["init", "--vault-id", "default", "--vault", str(root), "--graph-home", str(graph_home)]
    result = runner.invoke(app, args)
    assert result.exit_code == 0, result.stdout
    return graph_home, root


def _index(graph_home: Path, *extra: str) -> Any:
    return runner.invoke(app, ["index", "--graph-home", str(graph_home), "--all-vaults", *extra])


def _cache_path(graph_home: Path) -> Path:
    return graph_home / "cache" / "embeddings.sqlite3"


def _vectors(graph_home: Path) -> dict[str, tuple[float, ...]]:
    layout = ProjectionGenerationManager(graph_home).active_layout()
    assert layout is not None
    client = chromadb.PersistentClient(path=str((layout.root_path / "vector" / "chroma").resolve()))
    try:
        vectors: dict[str, tuple[float, ...]] = {}
        for collection in client.list_collections():
            rows = collection.get(include=["embeddings"])
            embeddings = rows["embeddings"]
            assert embeddings is not None
            for record_id, values in zip(rows["ids"], embeddings, strict=True):
                vectors[record_id] = tuple(float(value) for value in values)
        return vectors
    finally:
        client.close()  # type: ignore[attr-defined]


def test_warm_cache_full_reindex_sends_nothing_to_model(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    graph_home, _ = _home(tmp_path)
    _use(monkeypatch)
    assert _index(graph_home).exit_code == 0
    assert _Embeddings.inputs
    cold = _vectors(graph_home)

    _Embeddings.inputs = []
    result = _index(graph_home, "--full")

    assert result.exit_code == 0, result.stdout
    assert _Embeddings.inputs == []
    assert _vectors(graph_home) == cold


def test_deleted_cache_rebuilds_same_vectors(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    graph_home, _ = _home(tmp_path)
    _use(monkeypatch)
    assert _index(graph_home).exit_code == 0
    before = _vectors(graph_home)
    _cache_path(graph_home).unlink()

    _Embeddings.inputs = []
    result = _index(graph_home, "--full")

    assert result.exit_code == 0, result.stdout
    assert len(_Embeddings.inputs) == len(before)
    assert _vectors(graph_home) == before
    assert SQLiteEmbeddingCache(_cache_path(graph_home)).count() == len(before)


def test_publish_prunes_cache_to_active_vectors(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    graph_home, root = _home(tmp_path)
    _use(monkeypatch)
    assert _index(graph_home).exit_code == 0
    (root / "wiki" / "page-0.md").unlink()
    _write(root, "wiki/page-1.md", "# Page 1\nRewritten body.\n")

    result = _index(graph_home)

    assert result.exit_code == 0, result.stdout
    # Without pruning the removed page and the old text of page 1 would stay in the cache.
    assert SQLiteEmbeddingCache(_cache_path(graph_home)).count() == len(_vectors(graph_home))


def test_failed_run_resumes_from_cache(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    graph_home, _ = _home(tmp_path)
    _use(monkeypatch)
    _Embeddings.calls_before_failure = 1

    failed = _index(graph_home)

    assert failed.exit_code != 0
    saved = SQLiteEmbeddingCache(_cache_path(graph_home)).count()
    assert saved == len(_Embeddings.inputs) > 0

    _Embeddings.calls_before_failure = None
    _Embeddings.inputs = []
    assert _index(graph_home).exit_code == 0
    total = len(_vectors(graph_home))
    assert len(_Embeddings.inputs) == total - saved


def test_corrupt_cache_indexes_with_one_warning(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    graph_home, _ = _home(tmp_path)
    _use(monkeypatch)
    cache = _cache_path(graph_home)
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_bytes(b"not a database" * 200)

    result = _index(graph_home)

    assert result.exit_code == 0, result.stdout
    # CliRunner output includes standard error.
    assert result.output.count("embedding cache") == 1
    assert _vectors(graph_home)
    # The successful publish drops the corrupt file, so the next run builds a new cache.
    _Embeddings.inputs = []
    assert _index(graph_home, "--full").exit_code == 0
    assert SQLiteEmbeddingCache(cache).count() == len(_vectors(graph_home))
