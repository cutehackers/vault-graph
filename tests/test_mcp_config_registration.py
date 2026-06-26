from __future__ import annotations

import json
from pathlib import Path

import pytest

from vault_graph.errors import McpConfigError
from vault_graph.mcp.mcp_config_registration import (
    McpConfigRegistrar,
    McpConfigRenderer,
    McpConfigRequest,
    McpRegistrationRequest,
)


def test_mcp_config_renderer_outputs_installed_vg_command(tmp_path: Path) -> None:
    rendered = McpConfigRenderer().render(McpConfigRequest(agent="codex", state_path=tmp_path / "state"))
    payload = json.loads(rendered)

    server = payload["mcpServers"]["vault-graph"]
    assert server["command"] == "vg"
    assert server["args"][:3] == ["serve", "--mcp", "--state"]
    assert server["args"][3] == str((tmp_path / "state").resolve())


def test_mcp_config_register_preserves_unrelated_servers(tmp_path: Path) -> None:
    config_path = tmp_path / "codex.json"
    config_path.write_text(
        json.dumps({"mcpServers": {"other": {"command": "other", "args": []}}}),
        encoding="utf-8",
    )

    report = McpConfigRegistrar(backup_suffix_factory=lambda: "bak").register(
        McpRegistrationRequest(agent="codex", state_path=tmp_path / "state", config_path=config_path)
    )

    payload = json.loads(config_path.read_text(encoding="utf-8"))
    assert report.changed is True
    assert report.backup_path == config_path.with_name("codex.json.bak")
    assert "other" in payload["mcpServers"]
    assert "vault-graph" in payload["mcpServers"]


def test_mcp_config_register_dry_run_writes_nothing(tmp_path: Path) -> None:
    config_path = tmp_path / "codex.json"

    report = McpConfigRegistrar().register(
        McpRegistrationRequest(
            agent="codex",
            state_path=tmp_path / "state",
            config_path=config_path,
            dry_run=True,
        )
    )

    assert report.changed is True
    assert not config_path.exists()


def test_mcp_config_register_rejects_missing_parent(tmp_path: Path) -> None:
    with pytest.raises(McpConfigError, match="mcp_config_parent_missing"):
        McpConfigRegistrar().register(
            McpRegistrationRequest(
                agent="codex",
                state_path=tmp_path / "state",
                config_path=tmp_path / "missing" / "codex.json",
            )
        )
