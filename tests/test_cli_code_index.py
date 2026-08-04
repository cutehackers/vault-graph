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

    assert runner.invoke(app, ["init", "--vault", str(vault), "--graph-home", str(state)]).exit_code == 0
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
            "--graph-home",
            str(state),
            "--format",
            "json",
        ],
    )
    listed = runner.invoke(app, ["code", "repository", "list", "--graph-home", str(state), "--format", "json"])

    assert added.exit_code == 0, added.output
    assert listed.exit_code == 0, listed.output
    assert '"repository_id": "demo"' in listed.output


def test_code_repository_add_renders_validation_and_duplicate_errors(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    repository = tmp_path / "repository"
    vault.mkdir()
    repository.mkdir()
    state = tmp_path / "state"
    runner = CliRunner()
    assert runner.invoke(app, ["init", "--vault", str(vault), "--graph-home", str(state)]).exit_code == 0

    invalid = runner.invoke(
        app,
        [
            "code",
            "repository",
            "add",
            "bad",
            "--path",
            str(repository),
            "--language",
            "rust",
            "--graph-home",
            str(state),
        ],
    )
    first = runner.invoke(
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
            "--graph-home",
            str(state),
        ],
    )
    duplicate = runner.invoke(
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
            "--graph-home",
            str(state),
        ],
    )
    missing = runner.invoke(app, ["code", "repository", "remove", "missing", "--graph-home", str(state)])

    assert invalid.exit_code != 0
    assert "unsupported language" in invalid.output
    assert first.exit_code == 0, first.output
    assert duplicate.exit_code != 0
    assert "duplicate repository_id" in duplicate.output
    assert missing.exit_code != 0
    assert "unknown repository_id" in missing.output
