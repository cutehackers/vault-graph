from __future__ import annotations

import json
import os
import stat
from pathlib import Path

import pytest
from typer.testing import CliRunner

from vault_graph.errors import McpConfigError
from vault_graph.interface.cli.main import app
from vault_graph.operation.integration.mcp.mcp_config_registration import (
    McpConfigRegistrar,
    McpUnregistrationRequest,
)

runner = CliRunner()


@pytest.fixture
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    monkeypatch.setenv("HOME", str(fake_home))
    monkeypatch.delenv("CLAUDE_CONFIG_DIR", raising=False)
    return fake_home


def _claude_config(path: Path) -> str:
    text = (
        json.dumps(
            {
                "numStartups": 3,
                "projects": {"/work/한글": {"allowedTools": []}},
                "mcpServers": {
                    "other": {"type": "stdio", "command": "other"},
                    "vault-graph": {"type": "stdio", "command": "/opt/vg", "args": ["serve", "--mcp"]},
                    "later": {"type": "stdio", "command": "later"},
                },
                "theme": "dark",
            },
            indent=2,
            ensure_ascii=False,
        )
        + "\n"
    )
    path.write_text(text, encoding="utf-8")
    return text


def test_unregister_removes_only_vault_graph_and_keeps_other_keys(home: Path) -> None:
    config_path = home / ".claude.json"
    original = _claude_config(config_path)
    os.chmod(config_path, 0o600)

    report = McpConfigRegistrar().unregister(McpUnregistrationRequest(agent="claude", config_path=config_path))

    assert report.changed is True
    assert report.dry_run is False
    text = config_path.read_text(encoding="utf-8")
    payload = json.loads(text)
    assert list(payload) == ["numStartups", "projects", "mcpServers", "theme"]
    assert list(payload["mcpServers"]) == ["other", "later"]
    assert payload["projects"] == {"/work/한글": {"allowedTools": []}}
    assert "한글" in text
    assert stat.S_IMODE(config_path.stat().st_mode) == 0o600
    assert report.backup_path is not None
    assert report.backup_path.read_text(encoding="utf-8") == original
    assert stat.S_IMODE(report.backup_path.stat().st_mode) == 0o600


def test_unregister_dry_run_writes_nothing(home: Path) -> None:
    config_path = home / ".claude.json"
    original = _claude_config(config_path)

    report = McpConfigRegistrar().unregister(
        McpUnregistrationRequest(agent="claude", config_path=config_path, dry_run=True)
    )

    assert report.changed is True
    assert report.dry_run is True
    assert report.backup_path is None
    assert config_path.read_text(encoding="utf-8") == original
    assert sorted(path.name for path in home.iterdir()) == [".claude.json"]


def test_unregister_without_entry_writes_nothing(home: Path) -> None:
    config_path = home / ".claude.json"
    original = json.dumps({"mcpServers": {"other": {"command": "other"}}}, indent=2) + "\n"
    config_path.write_text(original, encoding="utf-8")

    report = McpConfigRegistrar().unregister(McpUnregistrationRequest(agent="claude", config_path=config_path))

    assert report.changed is False
    assert report.backup_path is None
    assert config_path.read_text(encoding="utf-8") == original
    assert sorted(path.name for path in home.iterdir()) == [".claude.json"]


def test_unregister_missing_config_file_writes_nothing(home: Path) -> None:
    config_path = home / ".claude.json"

    report = McpConfigRegistrar().unregister(McpUnregistrationRequest(agent="claude", config_path=config_path))

    assert report.changed is False
    assert not config_path.exists()


def test_unregister_refuses_invalid_json_without_writing(home: Path) -> None:
    config_path = home / ".claude.json"
    config_path.write_text("{not json", encoding="utf-8")

    with pytest.raises(McpConfigError, match="mcp_config_invalid_json"):
        McpConfigRegistrar().unregister(McpUnregistrationRequest(agent="claude", config_path=config_path))

    assert config_path.read_text(encoding="utf-8") == "{not json"
    assert sorted(path.name for path in home.iterdir()) == [".claude.json"]


def test_unregister_rejects_non_claude_agent(home: Path) -> None:
    with pytest.raises(McpConfigError, match="unsupported_mcp_agent"):
        McpConfigRegistrar().unregister(McpUnregistrationRequest(agent="codex", config_path=home / "config.toml"))


def test_cli_unregister_default_path_follows_claude_config_dir(
    home: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config_dir = tmp_path / "claude-config"
    config_dir.mkdir()
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(config_dir))
    config_path = config_dir / ".claude.json"
    _claude_config(config_path)

    result = runner.invoke(app, ["mcp", "unregister", "--agent", "claude"])

    assert result.exit_code == 0, result.stdout
    assert f"config_path: {config_path}" in result.stdout
    assert "changed: True" in result.stdout
    assert "backup_path: " in result.stdout
    assert "vault-graph" not in json.loads(config_path.read_text(encoding="utf-8"))["mcpServers"]
    assert not (home / ".claude.json").exists()


def test_cli_unregister_default_path_is_home_claude_json(home: Path) -> None:
    config_path = home / ".claude.json"
    _claude_config(config_path)

    result = runner.invoke(app, ["mcp", "unregister", "--agent", "claude", "--dry-run"])

    assert result.exit_code == 0, result.stdout
    assert f"config_path: {config_path}" in result.stdout
    assert "changed: True" in result.stdout
    assert "dry_run: True" in result.stdout
    assert "vault-graph" in json.loads(config_path.read_text(encoding="utf-8"))["mcpServers"]


def test_cli_unregister_without_entry_exits_zero_unchanged(home: Path, tmp_path: Path) -> None:
    config_path = tmp_path / "explicit.json"
    original = json.dumps({"theme": "dark"}) + "\n"
    config_path.write_text(original, encoding="utf-8")

    result = runner.invoke(app, ["mcp", "unregister", "--agent", "claude", "--config-path", str(config_path)])

    assert result.exit_code == 0, result.stdout
    assert "changed: False" in result.stdout
    assert "backup_path" not in result.stdout
    assert config_path.read_text(encoding="utf-8") == original
