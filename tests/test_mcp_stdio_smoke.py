from __future__ import annotations

import os
from pathlib import Path

import pytest
from typer.testing import CliRunner

from vault_graph.cli.main import app
from vault_graph.mcp.mcp_prompts import PHASE_5C_PROMPT_NAMES

runner = CliRunner()

EXPECTED_PHASE_6C_TOOLS = {
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
}


@pytest.mark.skipif(os.environ.get("VG_RUN_MCP_STDIO_SMOKE") != "1", reason="set VG_RUN_MCP_STDIO_SMOKE=1")
def test_mcp_stdio_initializes_with_official_client(tmp_path: Path) -> None:
    import anyio
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    vault_root = tmp_path / "vault"
    vault_root.mkdir()
    state_path = tmp_path / "state"
    assert runner.invoke(app, ["init", "--vault", str(vault_root), "--state", str(state_path)]).exit_code == 0

    async def run_client() -> None:
        params = StdioServerParameters(
            command="uv",
            args=[
                "run",
                "--python",
                "3.12",
                "vg",
                "serve",
                "--mcp",
                "--state",
                str(state_path),
            ],
        )
        with anyio.fail_after(15):
            async with stdio_client(params) as (read_stream, write_stream):
                async with ClientSession(read_stream, write_stream) as session:
                    await session.initialize()
                    tools = await session.list_tools()
                    resources = await session.list_resources()
                    resource_templates = await session.list_resource_templates()
                    prompts = await session.list_prompts()
                    tool_names = {tool.name for tool in tools.tools}
                    prompt_names = {prompt.name for prompt in prompts.prompts}
                    template_uris = {str(template.uriTemplate) for template in resource_templates.resourceTemplates}
                    assert tool_names == EXPECTED_PHASE_6C_TOOLS
                    assert resources.resources == []
                    assert "vault://{vault_id}/documents/{path}" in template_uris
                    assert "vault://context/packs/{pack_id}" in template_uris
                    assert prompt_names == set(PHASE_5C_PROMPT_NAMES)

    anyio.run(run_client)
