import json
from pathlib import Path

from pytest import MonkeyPatch
from typer.testing import CliRunner

from tests.fakes.deterministic_text_embeddings import DeterministicTextEmbeddings
from tests.fakes.in_memory_graph_store import InMemoryGraphStore
from tests.test_vector_indexer import SPEC
from vault_graph.cli.main import app
from vault_graph.embeddings.text_embeddings import EmbeddingInput, EmbeddingVector
from vault_graph.errors import TextEmbeddingsError

runner = CliRunner()


class _ConfiguredDeterministicTextEmbeddings(DeterministicTextEmbeddings):
    class Config:
        embedding_batch_size = 256
        embedding_parallelism = None
        embedding_lazy_load = True

    config = Config()


class _FailingTextEmbeddings(_ConfiguredDeterministicTextEmbeddings):
    def embed(self, inputs: tuple[EmbeddingInput, ...]) -> tuple[EmbeddingVector, ...]:
        raise TextEmbeddingsError("model unavailable")


def _deterministic_text_embeddings(_: object) -> _ConfiguredDeterministicTextEmbeddings:
    return _ConfiguredDeterministicTextEmbeddings(SPEC)


def _failing_text_embeddings(_: object) -> _FailingTextEmbeddings:
    return _FailingTextEmbeddings(SPEC)


def write_page(root: Path, path: str, body: str) -> None:
    file_path = root / path
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(body, encoding="utf-8")


def test_cli_index_dry_run_reports_graph_plan_without_graph_db(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    monkeypatch.setattr("vault_graph.cli.main._text_embeddings", _deterministic_text_embeddings)
    vault_root = tmp_path / "vault"
    write_page(vault_root, "wiki/page.md", "# Page\nBody\n")
    state_path = tmp_path / "state"
    runner.invoke(app, ["init", "--vault", str(vault_root), "--state", str(state_path)])

    result = runner.invoke(app, ["index", "--state", str(state_path), "--dry-run"])

    assert result.exit_code == 0
    assert "graph_mode: incremental" in result.stdout
    assert "graph_entities_upserted:" in result.stdout
    assert "graph_failed: False" in result.stdout
    assert not (state_path / "graph" / "graph.sqlite3").exists()


def test_cli_index_applies_graph_and_status_becomes_fresh(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    monkeypatch.setattr("vault_graph.cli.main._text_embeddings", _deterministic_text_embeddings)
    vault_root = tmp_path / "vault"
    write_page(vault_root, "wiki/page.md", "# Page\nBody\n")
    state_path = tmp_path / "state"
    runner.invoke(app, ["init", "--vault", str(vault_root), "--state", str(state_path)])

    result = runner.invoke(app, ["index", "--state", str(state_path)])
    status = runner.invoke(app, ["status", "--state", str(state_path), "--format", "json"])

    assert result.exit_code == 0
    assert "graph_relationships_upserted:" in result.stdout
    assert "graph_failed: False" in result.stdout
    assert (state_path / "graph" / "graph.sqlite3").exists()
    assert json.loads(status.stdout)["graph"]["freshness"] == "fresh"


def test_cli_index_graph_failure_returns_nonzero_and_records_status(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    monkeypatch.setattr("vault_graph.cli.main._text_embeddings", _deterministic_text_embeddings)
    monkeypatch.setattr(
        "vault_graph.cli.main.SQLiteGraphStore.open_writable",
        lambda _: InMemoryGraphStore(read_only=True),
    )
    vault_root = tmp_path / "vault"
    write_page(vault_root, "wiki/page.md", "# Page\nBody\n")
    state_path = tmp_path / "state"
    runner.invoke(app, ["init", "--vault", str(vault_root), "--state", str(state_path)])

    result = runner.invoke(app, ["index", "--state", str(state_path)])
    status_text = runner.invoke(app, ["status", "--state", str(state_path)])
    status_json = runner.invoke(app, ["status", "--state", str(state_path), "--format", "json"])

    assert result.exit_code == 1
    assert "index_revision: metadata-" in result.stdout
    assert "graph_failed: True" in result.stdout
    assert "graph_last_error:" in status_text.stdout
    assert json.loads(status_json.stdout)["graph"]["last_error"] is not None


def test_cli_index_vector_failure_still_prints_graph_success(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    monkeypatch.setattr("vault_graph.cli.main._text_embeddings", _failing_text_embeddings)
    vault_root = tmp_path / "vault"
    write_page(vault_root, "wiki/page.md", "# Page\nBody\n")
    state_path = tmp_path / "state"
    runner.invoke(app, ["init", "--vault", str(vault_root), "--state", str(state_path)])

    result = runner.invoke(app, ["index", "--state", str(state_path)])

    assert result.exit_code == 1
    assert "vector_failed: True" in result.stdout
    assert "graph_failed: False" in result.stdout
    assert "graph_entities_upserted:" in result.stdout
