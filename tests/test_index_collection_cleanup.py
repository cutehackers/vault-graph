"""`vg index` removes empty old-model collections from the unpublished generation (spec 4.7, A-23..A-27)."""

import json
import subprocess
from pathlib import Path
from typing import Any

import chromadb
import pytest
from typer.testing import CliRunner

from tests.fakes.deterministic_text_embeddings import DeterministicTextEmbeddings
from tests.test_vector_indexer import SECOND_SPEC, SPEC
from vault_graph.errors import TextEmbeddingsError, VectorStoreError
from vault_graph.indexing.publication.projection_generation import ProjectionGenerationManager
from vault_graph.interface.cli.main import app
from vault_graph.storage.interfaces.text_embeddings import EmbeddingInput, EmbeddingModelSpec, EmbeddingVector
from vault_graph.storage.local.vector_store_adapter import ChromaVectorStore, _collection_spec

runner = CliRunner()
SPEC_A = _collection_spec(SPEC).name
SPEC_B = _collection_spec(SECOND_SPEC).name


class _Config:
    embedding_batch_size = 256
    embedding_parallelism = None
    embedding_lazy_load = True


class _Embeddings(DeterministicTextEmbeddings):
    config = _Config()


class _FailingEmbeddings(_Embeddings):
    def embed(self, inputs: tuple[EmbeddingInput, ...]) -> tuple[EmbeddingVector, ...]:
        raise TextEmbeddingsError("model unavailable")


def _use(monkeypatch: pytest.MonkeyPatch, spec: EmbeddingModelSpec, *, failing: bool = False) -> None:
    kind = _FailingEmbeddings if failing else _Embeddings

    def factory(_: object) -> _Embeddings:
        return kind(spec)

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


def _home(tmp_path: Path, *vault_ids: str) -> Path:
    graph_home = tmp_path / "state"
    for index, vault_id in enumerate(vault_ids):
        root = tmp_path / vault_id
        _write(root, "wiki/page.md", f"# {vault_id}\nBody of {vault_id}.\n")
        if index == 0:
            args = ["init", "--vault-id", vault_id, "--vault", str(root), "--graph-home", str(graph_home)]
        else:
            args = ["vault", "add", vault_id, "--path", str(root), "--graph-home", str(graph_home)]
        result = runner.invoke(app, args)
        assert result.exit_code == 0, result.stdout
    return graph_home


def _index(graph_home: Path, *extra: str) -> Any:
    return runner.invoke(app, ["index", "--graph-home", str(graph_home), *extra])


def _active_root(graph_home: Path) -> Path:
    layout = ProjectionGenerationManager(graph_home).active_layout()
    assert layout is not None
    return layout.root_path


def _close(client: Any) -> None:
    # `ClientAPI` stubs omit close(); the runtime client has it.
    client.close()


def _collections(generation_root: Path) -> set[str]:
    client = chromadb.PersistentClient(path=str((generation_root / "vector" / "chroma").resolve()))
    try:
        return {collection.name for collection in client.list_collections()}
    finally:
        _close(client)


def _published_with_spec_a(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, *vault_ids: str) -> Path:
    graph_home = _home(tmp_path, *(vault_ids or ("default",)))
    _use(monkeypatch, SPEC)
    result = _index(graph_home, "--all-vaults")
    assert result.exit_code == 0, result.stdout
    assert _collections(_active_root(graph_home)) == {SPEC_A}
    assert "removed_vector_collections" not in result.stdout
    assert "vector collection cleanup failed" not in result.stdout
    return graph_home


def test_reindex_with_new_spec_removes_old_empty_collection_from_new_generation_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    graph_home = _published_with_spec_a(tmp_path, monkeypatch)
    previous_root = _active_root(graph_home)
    _use(monkeypatch, SECOND_SPEC)

    result = _index(graph_home, "--all-vaults")

    assert result.exit_code == 0, result.stdout
    assert "removed_vector_collections: 1" in result.stdout
    assert _active_root(graph_home) != previous_root
    assert _collections(_active_root(graph_home)) == {SPEC_B}
    assert _collections(previous_root) == {SPEC_A}


def test_failed_vector_step_and_dry_run_leave_active_generation_unchanged(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    graph_home = _published_with_spec_a(tmp_path, monkeypatch)
    active = _active_root(graph_home)

    _use(monkeypatch, SECOND_SPEC, failing=True)
    failed = _index(graph_home, "--all-vaults")
    assert failed.exit_code == 1
    assert "removed_vector_collections" not in failed.stdout
    assert _active_root(graph_home) == active
    assert _collections(active) == {SPEC_A}

    _use(monkeypatch, SECOND_SPEC)
    planned = _index(graph_home, "--all-vaults", "--dry-run")
    assert planned.exit_code == 0, planned.stdout
    assert "removed_vector_collections" not in planned.stdout
    assert _active_root(graph_home) == active
    assert _collections(active) == {SPEC_A}


def test_partial_reindex_keeps_old_collection_until_last_vault_moves(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    graph_home = _published_with_spec_a(tmp_path, monkeypatch, "first", "second")
    _use(monkeypatch, SECOND_SPEC)

    partial = _index(graph_home, "--vault-id", "first")
    assert partial.exit_code == 0, partial.stdout
    assert "removed_vector_collections" not in partial.stdout
    assert _collections(_active_root(graph_home)) == {SPEC_A, SPEC_B}

    rest = _index(graph_home, "--vault-id", "second")
    assert rest.exit_code == 0, rest.stdout
    assert "removed_vector_collections: 1" in rest.stdout
    assert _collections(_active_root(graph_home)) == {SPEC_B}


def test_cleanup_failure_still_publishes_and_prints_warning(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    graph_home = _published_with_spec_a(tmp_path, monkeypatch)
    previous_root = _active_root(graph_home)
    _use(monkeypatch, SECOND_SPEC)

    def fail(self: ChromaVectorStore, *, keep: EmbeddingModelSpec) -> tuple[str, ...]:
        # The same message shape the real adapter raises.
        raise VectorStoreError("vector collection cleanup failed: disk is read-only")

    monkeypatch.setattr(ChromaVectorStore, "remove_empty_collections", fail)

    result = _index(graph_home, "--all-vaults")

    assert result.exit_code == 0, result.stdout
    assert "warning: vector collection cleanup failed: disk is read-only\n" in result.stdout
    assert result.stdout.count("vector collection cleanup failed") == 1
    assert "removed_vector_collections" not in result.stdout
    assert _active_root(graph_home) != previous_root
    assert _collections(_active_root(graph_home)) == {SPEC_A, SPEC_B}


def test_read_paths_do_not_remove_collections(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    graph_home = _published_with_spec_a(tmp_path, monkeypatch)
    # An empty old-model collection in the active generation, as a read path would see it.
    active = _active_root(graph_home)
    client = chromadb.PersistentClient(path=str((active / "vector" / "chroma").resolve()))
    client.create_collection(name=SPEC_B, embedding_function=None)
    _close(client)
    before = _collections(active)
    calls: list[EmbeddingModelSpec] = []
    real = ChromaVectorStore.remove_empty_collections

    def record(self: ChromaVectorStore, *, keep: EmbeddingModelSpec) -> tuple[str, ...]:
        calls.append(keep)
        return real(self, keep=keep)

    monkeypatch.setattr(ChromaVectorStore, "remove_empty_collections", record)
    monkeypatch.setattr("vault_graph.interface.cli.hook_commands.start_catch_up_index", lambda *args, **kwargs: None)

    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "-C", str(repo), "init", "-q"], check=True)
    vault_map = tmp_path / "vault-map.json"
    vault_map.write_text(
        json.dumps(
            {
                "version": 2,
                "vaults": {"default": {"path": str(tmp_path / "default"), "role": "personal"}},
                "projects": {"repo": {"root": str(repo), "vaults": ["default"]}},
            }
        ),
        encoding="utf-8",
    )

    search = runner.invoke(app, ["search", "--graph-home", str(graph_home), "Body"])
    status = runner.invoke(app, ["status", "--graph-home", str(graph_home)])
    hook = runner.invoke(
        app,
        ["hook", "session-start", "--graph-home", str(graph_home), "--vault-map", str(vault_map)],
        input=json.dumps({"cwd": str(repo), "session_id": "session-1", "source": "startup"}),
    )

    assert search.exit_code == 0, search.stdout
    assert status.exit_code == 0, status.stdout
    assert hook.exit_code == 0, hook.output
    assert calls == []
    assert _active_root(graph_home) == active
    assert _collections(active) == before
