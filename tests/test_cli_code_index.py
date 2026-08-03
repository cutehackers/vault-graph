from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from vault_graph.cli.main import app


def test_code_repository_add_and_list_json(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    repository = tmp_path / "repository"
    vault.mkdir()
    repository.mkdir()
    state = tmp_path / "state"
    runner = CliRunner()

    assert runner.invoke(app, ["init", "--vault", str(vault), "--state", str(state)]).exit_code == 0
    added = runner.invoke(
        app,
        [
            "code",
            "repository",
            "add",
            "demo",
            "--path",
            str(repository),
            "--language",
            "python",
            "--state",
            str(state),
            "--format",
            "json",
        ],
    )
    listed = runner.invoke(app, ["code", "repository", "list", "--state", str(state), "--format", "json"])

    assert added.exit_code == 0, added.output
    assert listed.exit_code == 0, listed.output
    assert '"repository_id": "demo"' in listed.output
