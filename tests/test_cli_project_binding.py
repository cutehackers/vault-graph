from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from vault_graph.cli.main import app


def test_cli_project_binding_persists_and_lists_explicit_authorities(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    repository = tmp_path / "repository"
    vault.mkdir()
    repository.mkdir()
    state = tmp_path / "state"
    runner = CliRunner()
    assert runner.invoke(app, ["init", "--vault", str(vault), "--state", str(state)]).exit_code == 0
    assert (
        runner.invoke(
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
            ],
        ).exit_code
        == 0
    )

    bound = runner.invoke(
        app,
        [
            "project",
            "bind",
            "demo",
            "--vault-id",
            "default",
            "--scope",
            "wiki",
            "--evidence-mapping",
            "code:run=vault:default:decision-1:chunk-1",
            "--state",
            str(state),
            "--format",
            "json",
        ],
    )
    listed = runner.invoke(app, ["project", "bindings", "--state", str(state), "--format", "json"])

    assert bound.exit_code == 0, bound.output
    assert listed.exit_code == 0, listed.output
    assert '"repository_id": "demo"' in listed.output
    assert '"vault_ids": [' in listed.output
    assert '"evidence_mappings": [' in listed.output


def test_cli_project_binding_accepts_explicit_evidence_mapping(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    repository = tmp_path / "repository"
    vault.mkdir()
    repository.mkdir()
    state = tmp_path / "state"
    runner = CliRunner()
    assert runner.invoke(app, ["init", "--vault", str(vault), "--state", str(state)]).exit_code == 0
    assert (
        runner.invoke(
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
            ],
        ).exit_code
        == 0
    )

    result = runner.invoke(
        app,
        [
            "project",
            "bind",
            "demo",
            "--vault-id",
            "default",
            "--evidence-mapping",
            "code:run=vault:default:decision-1:chunk-1",
            "--state",
            str(state),
            "--format",
            "json",
        ],
    )

    assert result.exit_code == 0, result.output
    assert '"evidence_mappings": [' in result.output
