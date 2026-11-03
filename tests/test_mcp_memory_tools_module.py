"""The three memory write tools live in their own module, not in ``mcp_tools.py`` (정리 발견1)."""

from __future__ import annotations

import ast
from pathlib import Path

from tests.test_mcp_tools import RecordingToolServer, fake_factory, fake_services
from vault_graph.interface.mcp import mcp_memory_tools, mcp_tools
from vault_graph.interface.mcp.context_pack_resource_cache import ContextPackResourceCache
from vault_graph.interface.mcp.result_explanation_cache import ResultExplanationCache

MCP = Path(__file__).resolve().parents[1] / "src" / "vault_graph" / "interface" / "mcp"
MEMORY_NAMES = {
    "RememberInput",
    "UpdateMemoryInput",
    "RetireMemoryInput",
    "parse_remember_input",
    "parse_update_memory_input",
    "parse_retire_memory_input",
    "background_index_message",
}


def _defined(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return {node.name for node in tree.body if isinstance(node, ast.FunctionDef | ast.ClassDef)}


def test_memory_tool_code_is_defined_only_in_the_memory_module() -> None:
    assert MEMORY_NAMES <= _defined(MCP / "mcp_memory_tools.py")
    assert not MEMORY_NAMES & _defined(MCP / "mcp_tools.py")


def test_old_import_names_still_work() -> None:
    assert mcp_tools.RememberInput is mcp_memory_tools.RememberInput
    assert mcp_tools.parse_retire_memory_input is mcp_memory_tools.parse_retire_memory_input


def test_register_mcp_tools_still_registers_the_three_memory_tools(tmp_path: Path) -> None:
    from typing import Any, cast

    server = RecordingToolServer()
    mcp_tools.register_mcp_tools(
        server,
        services=fake_services(tmp_path),
        service_factory=cast(Any, fake_factory()),
        context_pack_cache=ContextPackResourceCache(),
        result_explanation_cache=ResultExplanationCache(),
    )

    assert {"remember", "update_memory", "retire_memory"} <= set(server.tools)
