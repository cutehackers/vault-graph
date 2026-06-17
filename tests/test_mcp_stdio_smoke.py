from __future__ import annotations

import os
from pathlib import Path

import pytest
from typer.testing import CliRunner

from vault_graph.cli.main import app

runner = CliRunner()


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
                    prompts = await session.list_prompts()
                    assert tools.tools == []
                    assert resources.resources == []
                    assert prompts.prompts == []

    anyio.run(run_client)
