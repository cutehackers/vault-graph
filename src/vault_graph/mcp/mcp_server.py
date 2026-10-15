"""Compatibility import for :mod:`vault_graph.interface.mcp.mcp_server`."""

import sys
from collections.abc import Iterable as Iterable
from dataclasses import dataclass as dataclass
from pathlib import Path as Path
from typing import TYPE_CHECKING as TYPE_CHECKING
from typing import Any as Any
from typing import Literal as Literal
from typing import Protocol as Protocol

from vault_graph.errors import CatalogError as CatalogError
from vault_graph.interface.mcp import mcp_server as _implementation
from vault_graph.interface.mcp.context_pack_resource_cache import ContextPackResourceCache as ContextPackResourceCache
from vault_graph.interface.mcp.mcp_resources import McpResourceRegistry as McpResourceRegistry
from vault_graph.interface.mcp.mcp_server import McpServer as McpServer
from vault_graph.interface.mcp.mcp_server import McpServerConfig as McpServerConfig
from vault_graph.interface.mcp.mcp_server import McpTransport as McpTransport
from vault_graph.interface.mcp.mcp_server import RegisteredMcpServer as RegisteredMcpServer
from vault_graph.interface.mcp.mcp_server import create_mcp_server as create_mcp_server
from vault_graph.interface.mcp.mcp_server import run_mcp_server as run_mcp_server
from vault_graph.interface.mcp.mcp_server import serve_mcp as serve_mcp
from vault_graph.interface.mcp.mcp_service_factory import McpServiceFactory as McpServiceFactory
from vault_graph.interface.mcp.mcp_service_factory import McpServices as McpServices
from vault_graph.interface.mcp.result_explanation_cache import ResultExplanationCache as ResultExplanationCache

sys.modules[__name__] = _implementation
