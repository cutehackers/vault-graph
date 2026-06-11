from pathlib import Path

from typer.testing import CliRunner

from vault_graph.cli.main import app

runner = CliRunner()


def test_cli_surface_exposes_search_but_not_answer_or_context_commands() -> None:
    result = runner.invoke(app, ["--help"])

    assert result.exit_code == 0
    assert "search" in result.output
    assert "related" in result.output
    assert "decision-trace" in result.output
    assert "ask" not in result.output
    assert "context" not in result.output


def test_cli_status_exposes_vector_fields(tmp_path: Path) -> None:
    vault_root = tmp_path / "vault"
    vault_root.mkdir()
    state_path = tmp_path / "state"
    runner.invoke(app, ["init", "--vault", str(vault_root), "--state", str(state_path)])

    result = runner.invoke(app, ["status", "--state", str(state_path)])

    assert result.exit_code == 0
    assert "metadata_ok:" in result.stdout
    assert "vector_ok:" in result.stdout
    assert "vector_schema_compatible:" in result.stdout
