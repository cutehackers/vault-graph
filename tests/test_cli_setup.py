from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from tests.fakes.deterministic_text_embeddings import DeterministicTextEmbeddings
from tests.test_vector_indexer import SPEC
from vault_graph.cli.main import app

runner = CliRunner()


class _ConfiguredDeterministicTextEmbeddings(DeterministicTextEmbeddings):
    class Config:
        embedding_batch_size = 256
        embedding_parallelism = None
        embedding_lazy_load = True

    config = Config()


def _deterministic_text_embeddings(_: object) -> _ConfiguredDeterministicTextEmbeddings:
    return _ConfiguredDeterministicTextEmbeddings(SPEC)


def test_cli_setup_dry_run_prints_onboarding_report_without_writing_state(tmp_path: Path) -> None:
    vault_root = tmp_path / "vault"
    vault_root.mkdir()
    graph_home_path = tmp_path / "state"

    result = runner.invoke(
        app,
        [
            "setup",
            "--vault",
            str(vault_root),
            "--graph-home",
            str(graph_home_path),
            "--vault-id",
            "main",
            "--dry-run",
            "--print-mcp-config",
        ],
    )

    assert result.exit_code == 0
    assert "vault_id: main" in result.stdout
    assert "ready: False" in result.stdout
    assert "dry_run: True" in result.stdout
    assert "recovery_hint: run setup without --dry-run" in result.stdout
    assert "mcp_config:" in result.stdout
    assert not graph_home_path.exists()


def test_cli_setup_mcp_dry_run_uses_default_codex_config_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    vault_root = tmp_path / "vault"
    vault_root.mkdir()
    graph_home_path = tmp_path / "state"
    codex_home = tmp_path / "codex-home"
    codex_home.mkdir()
    monkeypatch.setenv("CODEX_HOME", str(codex_home))

    result = runner.invoke(
        app,
        [
            "setup",
            "--vault",
            str(vault_root),
            "--graph-home",
            str(graph_home_path),
            "--vault-id",
            "main",
            "--mcp",
            "--dry-run",
        ],
    )

    assert result.exit_code == 0
    assert f"mcp_config_path: {codex_home / 'config.toml'}" in result.stdout
    assert "mcp_changed: True" in result.stdout
    assert not (codex_home / "config.toml").exists()
    assert not graph_home_path.exists()


def test_cli_setup_legacy_home_stops_with_rebuild_onboarding_hint(tmp_path: Path) -> None:
    vault_root = tmp_path / "vault"
    vault_root.mkdir()
    graph_home_path = tmp_path / "legacy"
    (graph_home_path / "configs").mkdir(parents=True)
    catalog_path = graph_home_path / "configs" / "vaults.yaml"
    catalog_path.write_text("vaults: []\n", encoding="utf-8")

    result = runner.invoke(
        app,
        [
            "setup",
            "--vault",
            str(vault_root),
            "--graph-home",
            str(graph_home_path),
        ],
    )

    assert result.exit_code == 1
    assert "legacy_data_home_detected" in result.stdout
    assert "new --graph-home PATH" in result.stdout
    assert catalog_path.read_text(encoding="utf-8") == "vaults: []\n"


def test_cli_setup_completes_first_run_and_is_idempotent(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("vault_graph.cli.main._text_embeddings", _deterministic_text_embeddings)
    vault_root = tmp_path / "vault"
    (vault_root / "wiki").mkdir(parents=True)
    (vault_root / "wiki" / "page.md").write_text("# Page\nOnboarding evidence\n", encoding="utf-8")
    graph_home_path = tmp_path / "graph-home"

    first = runner.invoke(
        app,
        [
            "setup",
            "--vault",
            str(vault_root),
            "--graph-home",
            str(graph_home_path),
            "--agent",
            "codex",
        ],
    )
    second = runner.invoke(
        app,
        [
            "setup",
            "--vault",
            str(vault_root),
            "--graph-home",
            str(graph_home_path),
            "--agent",
            "codex",
        ],
    )

    assert first.exit_code == 0, first.stdout
    assert second.exit_code == 0, second.stdout
    assert "ready: True" in first.stdout
    assert "ready: True" in second.stdout
    assert (graph_home_path / "data-home.json").exists()
    assert (graph_home_path / "configs" / "vaults.yaml").exists()
    assert (graph_home_path / "projections" / "active.json").exists()
    assert len(list((graph_home_path / "projections" / "generations").iterdir())) >= 1
    catalog_text = (graph_home_path / "configs" / "vaults.yaml").read_text(encoding="utf-8")
    assert catalog_text.count("\n- vault_id: default") == 1
