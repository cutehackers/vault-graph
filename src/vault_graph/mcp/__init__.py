from __future__ import annotations

from typing import Any

__all__ = [
    "McpErrorPayload",
    "McpProtocolError",
    "McpScopeInput",
    "McpServerConfig",
    "McpServiceFactory",
    "McpServices",
    "RegisteredMcpServer",
    "codex_stdio_config_json",
    "create_mcp_server",
    "map_exception_to_mcp_error",
    "run_mcp_server",
    "scope_from_mcp_input",
    "serve_mcp",
]


def __getattr__(name: str) -> Any:
    if name in {"McpServerConfig", "RegisteredMcpServer", "create_mcp_server", "run_mcp_server", "serve_mcp"}:
        from vault_graph.mcp.mcp_server import (
            McpServerConfig,
            RegisteredMcpServer,
            create_mcp_server,
            run_mcp_server,
            serve_mcp,
        )

        return {
            "McpServerConfig": McpServerConfig,
            "RegisteredMcpServer": RegisteredMcpServer,
            "create_mcp_server": create_mcp_server,
            "run_mcp_server": run_mcp_server,
            "serve_mcp": serve_mcp,
        }[name]
    if name in {"McpServiceFactory", "McpServices"}:
        from vault_graph.mcp.mcp_service_factory import McpServiceFactory, McpServices

        return {"McpServiceFactory": McpServiceFactory, "McpServices": McpServices}[name]
    if name in {"McpScopeInput", "scope_from_mcp_input"}:
        from vault_graph.mcp.mcp_scope import McpScopeInput, scope_from_mcp_input

        return {"McpScopeInput": McpScopeInput, "scope_from_mcp_input": scope_from_mcp_input}[name]
    if name in {"McpErrorPayload", "McpProtocolError", "map_exception_to_mcp_error"}:
        from vault_graph.mcp.mcp_errors import McpErrorPayload, McpProtocolError, map_exception_to_mcp_error

        return {
            "McpErrorPayload": McpErrorPayload,
            "McpProtocolError": McpProtocolError,
            "map_exception_to_mcp_error": map_exception_to_mcp_error,
        }[name]
    if name == "codex_stdio_config_json":
        from vault_graph.mcp.mcp_config_examples import codex_stdio_config_json

        return codex_stdio_config_json
    raise AttributeError(name)


def __dir__() -> list[str]:
    return sorted(__all__)
