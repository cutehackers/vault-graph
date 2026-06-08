from pathlib import Path

from pytest import MonkeyPatch
from typer.testing import CliRunner

from tests.fakes.deterministic_text_embeddings import DeterministicTextEmbeddings
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


def _failing_text_embeddings(_: object) -> _FailingTextEmbeddings:
    return _FailingTextEmbeddings(SPEC)


def write_page(root: Path, path: str, body: str) -> None:
    file_path = root / path
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(body, encoding="utf-8")


def test_cli_index_dry_run_reports_vector_plan_without_writes(tmp_path: Path) -> None:
    vault_root = tmp_path / "vault"
    write_page(vault_root, "wiki/page.md", "# Page\nBody\n")
    state_path = tmp_path / "state"
    runner.invoke(app, ["init", "--vault", str(vault_root), "--state", str(state_path)])

    result = runner.invoke(app, ["index", "--state", str(state_path), "--dry-run"])

    assert result.exit_code == 0
    assert "vector_mode: incremental" in result.stdout
    assert "vector_upserts: 1" in result.stdout
    assert "embedding_batch_size: 256" in result.stdout
    assert not (state_path / "metadata").exists()
    assert not (state_path / "vector").exists()


def test_cli_index_dry_run_does_not_initialize_existing_empty_chroma_path(tmp_path: Path) -> None:
    vault_root = tmp_path / "vault"
    write_page(vault_root, "wiki/page.md", "# Page\nBody\n")
    state_path = tmp_path / "state"
    runner.invoke(app, ["init", "--vault", str(vault_root), "--state", str(state_path)])
    (state_path / "vector" / "chroma").mkdir(parents=True)

    result = runner.invoke(app, ["index", "--state", str(state_path), "--dry-run"])

    assert result.exit_code == 0
    assert not (state_path / "vector" / "chroma" / "chroma.sqlite3").exists()


def test_cli_index_returns_nonzero_when_vector_step_fails(
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
    assert "index_revision: metadata-" in result.stdout
    assert "vector_failed: True" in result.stdout
    assert "vector_last_error: model unavailable" in result.stdout
    assert (state_path / "metadata" / "metadata.sqlite3").exists()


def test_cli_status_reports_vector_fields(tmp_path: Path) -> None:
    vault_root = tmp_path / "vault"
    vault_root.mkdir()
    state_path = tmp_path / "state"
    runner.invoke(app, ["init", "--vault", str(vault_root), "--state", str(state_path)])

    result = runner.invoke(app, ["status", "--state", str(state_path)])

    assert result.exit_code == 0
    assert "vector_ok:" in result.stdout
    assert "vector_backend: chroma" in result.stdout
    assert "embedding_model: sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2" in result.stdout
    assert "embedding_model_version: faf4aa4225822f3bc6376869cb1164e8e3feedd0" in result.stdout
    assert "embedding_dimensions: 384" in result.stdout
    assert "vector_status_scope: default:raw,wiki,docs,scratch/reports" in result.stdout


def test_cli_status_supports_vault_scope_flags(tmp_path: Path) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"
    first.mkdir()
    second.mkdir()
    state_path = tmp_path / "state"
    runner.invoke(app, ["init", "--vault-id", "first", "--vault", str(first), "--state", str(state_path)])
    runner.invoke(app, ["vault", "add", "second", "--path", str(second), "--state", str(state_path)])

    one = runner.invoke(app, ["status", "--state", str(state_path), "--vault-id", "second"])
    all_vaults = runner.invoke(app, ["status", "--state", str(state_path), "--all-vaults"])

    assert one.exit_code == 0
    assert "vector_status_scope: second:" in one.stdout
    assert all_vaults.exit_code == 0
    assert "vector_status_scope: first,second:" in all_vaults.stdout
