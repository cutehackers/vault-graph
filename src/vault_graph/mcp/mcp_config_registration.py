"""Compatibility import for :mod:`vault_graph.operation.integration.mcp.mcp_config_registration`."""

import sys

from vault_graph.operation.integration.mcp import mcp_config_registration as _implementation
from vault_graph.operation.integration.mcp.mcp_config_registration import McpAgent as McpAgent
from vault_graph.operation.integration.mcp.mcp_config_registration import McpConfigRegistrar as McpConfigRegistrar
from vault_graph.operation.integration.mcp.mcp_config_registration import McpConfigRenderer as McpConfigRenderer
from vault_graph.operation.integration.mcp.mcp_config_registration import McpConfigRequest as McpConfigRequest
from vault_graph.operation.integration.mcp.mcp_config_registration import McpRegistrationReport as McpRegistrationReport
from vault_graph.operation.integration.mcp.mcp_config_registration import (
    McpRegistrationRequest as McpRegistrationRequest,
)

sys.modules[__name__] = _implementation
