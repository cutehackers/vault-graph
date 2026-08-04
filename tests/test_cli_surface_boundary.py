from pathlib import Path

from typer.testing import CliRunner

from vault_graph.cli.main import app

runner = CliRunner()


def test_cli_surface_exposes_context_and_answer_command() -> None:
    result = runner.invoke(app, ["--help"])

    assert result.exit_code == 0
    assert "search" in result.output
    assert "related" in result.output
    assert "decision-trace" in result.output
    assert "serve" in result.output
    assert "ask" in result.output
    assert "context" in result.output


def test_cli_status_exposes_vector_fields(tmp_path: Path) -> None:
    vault_root = tmp_path / "vault"
    vault_root.mkdir()
    graph_home_path = tmp_path / "state"
    runner.invoke(app, ["init", "--vault", str(vault_root), "--graph-home", str(graph_home_path)])

    result = runner.invoke(app, ["status", "--graph-home", str(graph_home_path)])

    assert result.exit_code == 0
    assert "metadata_ok:" in result.stdout
    assert "vector_ok:" in result.stdout
    assert "vector_schema_compatible:" in result.stdout


def test_cli_uses_graph_home_without_state_alias() -> None:
    help_result = runner.invoke(app, ["status", "--help"])
    legacy_result = runner.invoke(app, ["status", "--state", "/tmp/legacy-state"])

    assert "--graph-home" in help_result.stdout
    assert "--state" not in help_result.stdout
    assert legacy_result.exit_code != 0
    assert "No such option: --state" in legacy_result.output
