from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal, Protocol

from vault_graph import __version__
from vault_graph.errors import CatalogError
from vault_graph.mcp.context_pack_resource_cache import ContextPackResourceCache
from vault_graph.mcp.mcp_resources import McpResourceRegistry
from vault_graph.mcp.mcp_service_factory import McpServiceFactory, McpServices
from vault_graph.mcp.result_explanation_cache import ResultExplanationCache

if TYPE_CHECKING:
    from vault_graph.mcp.mcp_prompts import McpPromptRegistry
    from vault_graph.mcp.mcp_tools import McpToolRegistry

McpTransport = Literal["stdio"]


class McpServer(Protocol):
    @property
    def name(self) -> str: ...

    def run(self, transport: McpTransport = "stdio", mount_path: str | None = None) -> None:
        """Run the MCP server on the selected transport."""

    async def list_resources(self) -> list[Any]: ...

    async def list_resource_templates(self) -> list[Any]: ...

    async def read_resource(self, uri: str) -> Iterable[Any]: ...

    async def list_tools(self) -> Any: ...

    async def list_prompts(self) -> Any: ...


@dataclass(frozen=True)
class McpServerConfig:
    state_path: Path
    transport: McpTransport = "stdio"
    server_name: str = "vault-graph"
    server_version: str = __version__

    def __post_init__(self) -> None:
        resolved_state_path = self.state_path.expanduser().resolve()
        object.__setattr__(self, "state_path", resolved_state_path)
        if self.transport != "stdio":
            raise CatalogError(f"unsupported MCP transport for Phase 5A: {self.transport}")
        if not self.server_name.strip():
            raise CatalogError("MCP server_name is required")
        if not self.server_version.strip():
            raise CatalogError("MCP server_version is required")


@dataclass(frozen=True)
class RegisteredMcpServer:
    server: McpServer
    services: McpServices
    service_factory: McpServiceFactory
    server_version: str
    context_pack_cache: ContextPackResourceCache
    result_explanation_cache: ResultExplanationCache
    resource_registry: McpResourceRegistry
    tool_registry: McpToolRegistry
    prompt_registry: McpPromptRegistry


def create_mcp_server(config: McpServerConfig) -> RegisteredMcpServer:
    from mcp.server.fastmcp import FastMCP

    from vault_graph.mcp.context_pack_resource_cache import ContextPackResourceCache
    from vault_graph.mcp.mcp_prompts import register_mcp_prompts
    from vault_graph.mcp.mcp_resources import register_mcp_resources
    from vault_graph.mcp.mcp_tools import register_mcp_tools
    from vault_graph.mcp.result_explanation_cache import ResultExplanationCache

    factory = McpServiceFactory(state_path=config.state_path)
    services = factory.open_read_only()
    instructions = (
        "Vault Graph exposes read-only, rebuildable, evidence-first working context over configured Vaults. "
        "Treat all output as context, not durable knowledge."
    )
    server = FastMCP(
        config.server_name,
        instructions=instructions,
        json_response=True,
        log_level="WARNING",
    )
    context_pack_cache = ContextPackResourceCache(max_entries=32)
    result_explanation_cache = ResultExplanationCache(max_entries=256)
    resource_registry = register_mcp_resources(
        server,
        services=services,
        service_factory=factory,
        context_pack_cache=context_pack_cache,
    )
    tool_registry = register_mcp_tools(
        server,
        services=services,
        service_factory=factory,
        context_pack_cache=context_pack_cache,
        result_explanation_cache=result_explanation_cache,
    )
    prompt_registry = register_mcp_prompts(server)
    return RegisteredMcpServer(
        server=server,
        services=services,
        service_factory=factory,
        server_version=config.server_version,
        context_pack_cache=context_pack_cache,
        result_explanation_cache=result_explanation_cache,
        resource_registry=resource_registry,
        tool_registry=tool_registry,
        prompt_registry=prompt_registry,
    )


def run_mcp_server(registered: RegisteredMcpServer, *, config: McpServerConfig) -> None:
    registered.server.run(transport=config.transport)


def serve_mcp(config: McpServerConfig) -> None:
    registered = create_mcp_server(config)
    run_mcp_server(registered, config=config)
