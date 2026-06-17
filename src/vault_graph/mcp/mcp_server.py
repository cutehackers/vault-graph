from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Protocol

from vault_graph import __version__
from vault_graph.errors import CatalogError
from vault_graph.mcp.mcp_service_factory import McpServiceFactory, McpServices

McpTransport = Literal["stdio"]


class McpServer(Protocol):
    @property
    def name(self) -> str: ...

    def run(self, transport: McpTransport = "stdio", mount_path: str | None = None) -> None:
        """Run the MCP server on the selected transport."""


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


def create_mcp_server(config: McpServerConfig) -> RegisteredMcpServer:
    from mcp.server.fastmcp import FastMCP

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
    return RegisteredMcpServer(
        server=server,
        services=services,
        service_factory=factory,
        server_version=config.server_version,
    )


def run_mcp_server(registered: RegisteredMcpServer, *, config: McpServerConfig) -> None:
    registered.server.run(transport=config.transport)


def serve_mcp(config: McpServerConfig) -> None:
    registered = create_mcp_server(config)
    run_mcp_server(registered, config=config)
