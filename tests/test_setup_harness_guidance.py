from __future__ import annotations

from pathlib import Path
from typing import Any, cast

from typer.testing import CliRunner

from tests.test_setup_service import RecordingIndexFactory
from vault_graph.app.setup_service import SetupRequest, SetupService
from vault_graph.cli.main import app

runner = CliRunner()


def test_setup_service_does_not_install_harness_guidance_by_default(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    project = tmp_path / "project"
    project.mkdir()

    SetupService(index_factory=cast(Any, RecordingIndexFactory())).setup(
        request=SetupRequest(
            vault_path=vault,
            state_path=tmp_path / "state",
            agent=None,
        )
    )

    assert not (project / "AGENTS.md").exists()


def test_harness_cli_preview_and_install_require_explicit_target(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    state = tmp_path / "state"
    result = runner.invoke(app, ["init", "--vault", str(vault), "--state", str(state)])
    assert result.exit_code == 0
    project = tmp_path / "project"
    project.mkdir()

    preview = runner.invoke(
        app,
        ["harness", "guidance", "preview", "--target", str(project), "--file-name", "AGENTS.md", "--state", str(state)],
    )
    assert preview.exit_code == 0
    assert not (project / "AGENTS.md").exists()

    install = runner.invoke(
        app,
        ["harness", "guidance", "install", "--target", str(project), "--file-name", "AGENTS.md", "--state", str(state)],
    )
    assert install.exit_code == 0
    assert (project / "AGENTS.md").exists()


def test_harness_cli_rejects_registered_vault_target(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    state = tmp_path / "state"
    assert runner.invoke(app, ["init", "--vault", str(vault), "--state", str(state)]).exit_code == 0

    result = runner.invoke(
        app,
        ["harness", "guidance", "install", "--target", str(vault), "--file-name", "AGENTS.md", "--state", str(state)],
    )

    assert result.exit_code == 1
    assert "harness_guidance_target_inside_vault" in result.stdout
