from pathlib import Path

from typer.testing import CliRunner

from vault_graph.cli.main import app

runner = CliRunner()


def test_phase_2a_does_not_add_search_command() -> None:
    result = runner.invoke(app, ["search", "query"])

    assert result.exit_code != 0
    assert "No such command" in result.output


def test_phase_2a_status_remains_metadata_only(tmp_path: Path) -> None:
    vault_root = tmp_path / "vault"
    vault_root.mkdir()
    state_path = tmp_path / "state"
    runner.invoke(app, ["init", "--vault", str(vault_root), "--state", str(state_path)])

    result = runner.invoke(app, ["status", "--state", str(state_path)])

    assert result.exit_code == 0
    assert "metadata_ok:" in result.stdout
    assert "vector_ok:" not in result.stdout
    assert "vector_schema_compatible:" not in result.stdout
