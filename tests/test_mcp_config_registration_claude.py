"""Claude Code user-scope MCP registration writes ``mcpServers.vault-graph`` into ``~/.claude.json``."""

from __future__ import annotations

import json
import os
import stat
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from vault_graph.errors import McpConfigError
from vault_graph.interface.cli.main import app
from vault_graph.operation.integration.mcp.mcp_config_registration import (
    McpConfigRegistrar,
    McpConfigRenderer,
    McpConfigRequest,
    McpRegistrationRequest,
)

runner = CliRunner()
VG = "/opt/tools/bin/vg"


def _renderer() -> McpConfigRenderer:
    return McpConfigRenderer(vg_command=lambda: VG)


def _registrar() -> McpConfigRegistrar:
    return McpConfigRegistrar(renderer=_renderer())


@pytest.fixture
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    monkeypatch.setenv("HOME", str(fake_home))
    monkeypatch.delenv("CLAUDE_CONFIG_DIR", raising=False)
    return fake_home


def test_claude_render_uses_absolute_vg_and_serve_mcp_for_default_graph_home(home: Path) -> None:
    rendered = _renderer().render(McpConfigRequest(agent="claude", graph_home_path=home / ".vault-graph"))

    assert json.loads(rendered) == {
        "mcpServers": {"vault-graph": {"type": "stdio", "command": VG, "args": ["serve", "--mcp"]}}
    }


def test_claude_render_keeps_a_non_default_graph_home(home: Path, tmp_path: Path) -> None:
    rendered = _renderer().render(McpConfigRequest(agent="claude", graph_home_path=tmp_path / "other-home"))

    server = json.loads(rendered)["mcpServers"]["vault-graph"]
    assert server["args"] == ["serve", "--mcp", "--graph-home", str((tmp_path / "other-home").resolve())]


def test_claude_render_fails_when_vg_cannot_be_found(home: Path) -> None:
    renderer = McpConfigRenderer(vg_command=lambda: None)

    with pytest.raises(McpConfigError, match="vg_command_not_found"):
        renderer.render(McpConfigRequest(agent="claude", graph_home_path=home / ".vault-graph"))


def test_claude_default_config_path_is_home_claude_json(home: Path) -> None:
    assert McpConfigRegistrar().default_config_path("claude") == home / ".claude.json"


@pytest.mark.parametrize("value", [None, ""])
def test_claude_default_config_path_ignores_unset_or_empty_config_dir(
    home: Path, monkeypatch: pytest.MonkeyPatch, value: str | None
) -> None:
    if value is not None:
        monkeypatch.setenv("CLAUDE_CONFIG_DIR", value)

    assert McpConfigRegistrar().default_config_path("claude") == home / ".claude.json"


def test_claude_default_config_path_follows_claude_config_dir(
    home: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Claude Code reads join(CLAUDE_CONFIG_DIR || homedir(), ".claude.json") (finding 발견6).
    config_dir = tmp_path / "claude-config"
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(config_dir))

    assert McpConfigRegistrar().default_config_path("claude") == config_dir / ".claude.json"


def test_cli_setup_claude_mcp_dry_run_targets_claude_config_dir(
    home: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config_dir = tmp_path / "claude-config"
    config_dir.mkdir()
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(config_dir))
    vault = tmp_path / "vault"
    vault.mkdir()

    result = runner.invoke(
        app,
        [
            "setup",
            "--vault",
            str(vault),
            "--graph-home",
            str(tmp_path / "state"),
            "--agent",
            "claude",
            "--mcp",
            "--dry-run",
        ],
    )

    assert result.exit_code == 0, result.output
    assert f"mcp_config_path: {config_dir / '.claude.json'}" in result.stdout
    assert not (home / ".claude.json").exists()


def test_claude_register_keeps_non_ascii_text_unescaped(home: Path) -> None:
    config_path = home / ".claude.json"
    original = {"projects": {"/저장소/프로젝트": {"note": "한글 메모 – café"}}}
    config_path.write_text(json.dumps(original, ensure_ascii=False, indent=2), encoding="utf-8")

    _registrar().register(
        McpRegistrationRequest(agent="claude", graph_home_path=home / ".vault-graph", config_path=config_path)
    )

    text = config_path.read_text(encoding="utf-8")
    assert "/저장소/프로젝트" in text and "한글 메모 – café" in text
    assert "\\u" not in text
    assert json.loads(text)["projects"] == original["projects"]


def test_claude_register_preserves_other_keys_servers_order_and_mode(home: Path) -> None:
    config_path = home / ".claude.json"
    original: dict[str, Any] = {
        "numStartups": 12,
        "projects": {"/repo": {"allowedTools": ["Bash"], "mcpServers": {"local": {"command": "x"}}}},
        "mcpServers": {"other": {"type": "stdio", "command": "other", "args": []}},
        "zzz": True,
    }
    config_path.write_text(json.dumps(original, indent=2), encoding="utf-8")
    config_path.chmod(0o600)

    report = _registrar().register(
        McpRegistrationRequest(agent="claude", graph_home_path=home / ".vault-graph", config_path=config_path)
    )

    payload = json.loads(config_path.read_text(encoding="utf-8"))
    assert report.changed is True
    assert list(payload) == ["numStartups", "projects", "mcpServers", "zzz"]
    assert payload["projects"] == original["projects"]
    assert payload["mcpServers"]["other"] == original["mcpServers"]["other"]
    assert payload["mcpServers"]["vault-graph"] == {"type": "stdio", "command": VG, "args": ["serve", "--mcp"]}
    assert stat.S_IMODE(config_path.stat().st_mode) == 0o600
    assert report.backup_path is not None
    assert json.loads(report.backup_path.read_text(encoding="utf-8")) == original
    assert stat.S_IMODE(report.backup_path.stat().st_mode) == 0o600
    assert sorted(path.name for path in home.iterdir()) == [".claude.json", report.backup_path.name]


def test_claude_register_is_idempotent(home: Path) -> None:
    config_path = home / ".claude.json"
    request = McpRegistrationRequest(agent="claude", graph_home_path=home / ".vault-graph", config_path=config_path)
    _registrar().register(request)
    first = config_path.read_bytes()

    report = _registrar().register(request)

    assert report.changed is False
    assert config_path.read_bytes() == first


def test_claude_register_refuses_invalid_json_without_writing(home: Path) -> None:
    config_path = home / ".claude.json"
    config_path.write_text("{not json", encoding="utf-8")

    with pytest.raises(McpConfigError, match="mcp_config_invalid_json"):
        _registrar().register(
            McpRegistrationRequest(agent="claude", graph_home_path=home / ".vault-graph", config_path=config_path)
        )

    assert config_path.read_text(encoding="utf-8") == "{not json"
    assert [path.name for path in home.iterdir()] == [".claude.json"]


def test_claude_register_uses_rename_not_in_place_write(home: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    config_path = home / ".claude.json"
    config_path.write_text("{}", encoding="utf-8")
    replaced: list[tuple[str, str]] = []
    real_replace = os.replace

    def spy_replace(source: str | os.PathLike[str], target: str | os.PathLike[str]) -> None:
        replaced.append((str(source), str(target)))
        real_replace(source, target)

    monkeypatch.setattr(os, "replace", spy_replace)

    _registrar().register(
        McpRegistrationRequest(agent="claude", graph_home_path=home / ".vault-graph", config_path=config_path)
    )

    assert [target for _, target in replaced] == [str(config_path)]
    assert Path(replaced[0][0]).parent == home


def test_cli_setup_claude_mcp_dry_run_targets_home_claude_json(home: Path, tmp_path: Path) -> None:
    vault_root = tmp_path / "vault"
    vault_root.mkdir()
    (home / ".claude.json").write_text(json.dumps({"keep": 1}), encoding="utf-8")

    dry = runner.invoke(
        app,
        [
            "setup",
            "--vault",
            str(vault_root),
            "--graph-home",
            str(home / ".vault-graph"),
            "--agent",
            "claude",
            "--mcp",
            "--dry-run",
        ],
    )

    assert dry.exit_code == 0, dry.output
    assert f"mcp_config_path: {home / '.claude.json'}" in dry.stdout
    assert "mcp_changed: True" in dry.stdout
    assert json.loads((home / ".claude.json").read_text(encoding="utf-8")) == {"keep": 1}


def test_cli_setup_claude_print_mcp_config(home: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    vault_root = tmp_path / "vault"
    vault_root.mkdir()
    # setup --agent claude reads <config dir>/vault-builder/vault-hooks.json. Keep it off the real ~/.claude.
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / "claude-config"))

    result = runner.invoke(
        app,
        [
            "setup",
            "--vault",
            str(vault_root),
            "--graph-home",
            str(home / ".vault-graph"),
            "--agent",
            "claude",
            "--print-mcp-config",
            "--dry-run",
        ],
    )

    assert result.exit_code == 0, result.output
    rendered = result.stdout.split("mcp_config:\n", 1)[1]
    server = json.loads(rendered)["mcpServers"]["vault-graph"]
    assert Path(server["command"]).is_absolute()
    assert Path(server["command"]).name == "vg"
    assert server["args"] == ["serve", "--mcp"]
    assert not (home / ".claude.json").exists()


def test_cli_mcp_register_claude_with_explicit_path(home: Path, tmp_path: Path) -> None:
    config_path = tmp_path / "claude.json"
    config_path.write_text(json.dumps({"mcpServers": {"other": {"command": "o"}}}), encoding="utf-8")

    result = runner.invoke(
        app,
        [
            "mcp",
            "register",
            "--agent",
            "claude",
            "--graph-home",
            str(home / ".vault-graph"),
            "--config-path",
            str(config_path),
        ],
    )

    assert result.exit_code == 0, result.output
    servers = json.loads(config_path.read_text(encoding="utf-8"))["mcpServers"]
    assert set(servers) == {"other", "vault-graph"}
    assert not (home / ".claude.json").exists()
