from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from vault_graph.cli.main import app

runner = CliRunner()


def test_cli_setup_dry_run_prints_onboarding_report_without_writing_state(tmp_path: Path) -> None:
    vault_root = tmp_path / "vault"
    vault_root.mkdir()
    state_path = tmp_path / "state"

    result = runner.invoke(
        app,
        [
            "setup",
            "--vault",
            str(vault_root),
            "--state",
            str(state_path),
            "--vault-id",
            "main",
            "--dry-run",
            "--print-mcp-config",
        ],
    )

    assert result.exit_code == 0
    assert "vault_id: main" in result.stdout
    assert "dry_run: True" in result.stdout
    assert "mcp_config:" in result.stdout
    assert not state_path.exists()
