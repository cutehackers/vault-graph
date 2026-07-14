from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from vault_graph.cli.main import app

runner = CliRunner()


def test_cli_mcp_config_prints_codex_stdio_config(tmp_path: Path) -> None:
    result = runner.invoke(app, ["mcp", "config", "--state", str(tmp_path / "state"), "--print"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["mcpServers"]["vault-graph"]["command"] == "vg"


def test_cli_mcp_config_requires_print(tmp_path: Path) -> None:
    result = runner.invoke(app, ["mcp", "config", "--state", str(tmp_path / "state")])

    assert result.exit_code == 1
    assert "mcp_config_requires_print" in result.stdout


def test_cli_mcp_register_writes_explicit_config_path(tmp_path: Path) -> None:
    config_path = tmp_path / "codex.json"

    result = runner.invoke(
        app,
        ["mcp", "register", "--state", str(tmp_path / "state"), "--config-path", str(config_path)],
    )

    assert result.exit_code == 0
    assert config_path.exists()
    assert "changed: True" in result.stdout


def test_cli_mcp_register_dry_run_writes_nothing(tmp_path: Path) -> None:
    config_path = tmp_path / "codex.json"

    result = runner.invoke(
        app,
        [
            "mcp",
            "register",
            "--state",
            str(tmp_path / "state"),
            "--config-path",
            str(config_path),
            "--dry-run",
        ],
    )

    assert result.exit_code == 0
    assert not config_path.exists()
    assert "dry_run: True" in result.stdout


def test_cli_setup_help_exposes_easy_mcp_flag() -> None:
    result = runner.invoke(app, ["setup", "--help"])

    assert result.exit_code == 0
    assert "--mcp" in result.stdout
