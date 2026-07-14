from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from vault_graph.cli.main import app
from vault_graph.errors import CatalogError
from vault_graph.mcp.mcp_prompts import PHASE_5C_PROMPT_NAMES
from vault_graph.mcp.mcp_server import McpServerConfig, create_mcp_server

runner = CliRunner()


def test_mcp_server_config_accepts_stdio_only(tmp_path: Path) -> None:
    config = McpServerConfig(state_path=tmp_path / "state")

    assert config.transport == "stdio"
    assert config.server_name == "vault-graph"


def test_mcp_server_config_rejects_non_stdio_transport(tmp_path: Path) -> None:
    with pytest.raises(CatalogError, match="unsupported MCP transport"):
        McpServerConfig(state_path=tmp_path / "state", transport="streamable-http")  # type: ignore[arg-type]


def test_create_mcp_server_loads_services_before_stdio_run(tmp_path: Path) -> None:
    vault_root = tmp_path / "vault"
    vault_root.mkdir()
    state_path = tmp_path / "state"
    assert runner.invoke(app, ["init", "--vault", str(vault_root), "--state", str(state_path)]).exit_code == 0

    registered = create_mcp_server(McpServerConfig(state_path=state_path))

    assert registered.server.name == "vault-graph"
    assert registered.services.catalog.active_vault_id == "default"
    assert registered.server_version == "0.1.3"


def test_create_mcp_server_registers_resources_tools_prompts_and_explanation_cache(tmp_path: Path) -> None:
    vault_root = tmp_path / "vault"
    vault_root.mkdir()
    state_path = tmp_path / "state"
    assert runner.invoke(app, ["init", "--vault", str(vault_root), "--state", str(state_path)]).exit_code == 0

    registered = create_mcp_server(McpServerConfig(state_path=state_path))

    assert registered.resource_registry is not None
    assert registered.result_explanation_cache.max_entries == 256
    assert registered.tool_registry.tool_names == (
        "ask_vault",
        "search_vault",
        "build_context_pack",
        "find_related",
        "get_decision_trace",
        "check_index_status",
        "explain_result",
        "summarize_project_memory",
        "get_open_questions",
        "get_recent_changes",
    )
    assert registered.prompt_registry.prompt_names == PHASE_5C_PROMPT_NAMES


def test_create_mcp_server_missing_catalog_fails_before_server_object(tmp_path: Path) -> None:
    with pytest.raises(CatalogError):
        create_mcp_server(McpServerConfig(state_path=tmp_path / "missing-state"))
