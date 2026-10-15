"""Compatibility import for :mod:`vault_graph.operation.integration.mcp.mcp_config_registration`."""

import json as json
import os as os
import sys
import tomllib as tomllib
from collections.abc import Callable as Callable
from dataclasses import dataclass as dataclass
from pathlib import Path as Path
from typing import Literal as Literal

from vault_graph.errors import McpConfigError as McpConfigError
from vault_graph.operation.integration.mcp import mcp_config_registration as _implementation
from vault_graph.operation.integration.mcp.mcp_config_registration import McpAgent as McpAgent
from vault_graph.operation.integration.mcp.mcp_config_registration import McpConfigRegistrar as McpConfigRegistrar
from vault_graph.operation.integration.mcp.mcp_config_registration import McpConfigRenderer as McpConfigRenderer
from vault_graph.operation.integration.mcp.mcp_config_registration import McpConfigRequest as McpConfigRequest
from vault_graph.operation.integration.mcp.mcp_config_registration import McpRegistrationReport as McpRegistrationReport
from vault_graph.operation.integration.mcp.mcp_config_registration import (
    McpRegistrationRequest as McpRegistrationRequest,
)
from vault_graph.operation.integration.mcp.mcp_config_registration import (
    _codex_toml_server_block as _codex_toml_server_block,
)
from vault_graph.operation.integration.mcp.mcp_config_registration import _loads_object as _loads_object
from vault_graph.operation.integration.mcp.mcp_config_registration import _mcp_servers as _mcp_servers
from vault_graph.operation.integration.mcp.mcp_config_registration import _upsert_toml_section as _upsert_toml_section
from vault_graph.operation.integration.mcp.mcp_config_registration import _validate_agent as _validate_agent
from vault_graph.operation.integration.mcp.mcp_config_registration import _validate_server_name as _validate_server_name
from vault_graph.operation.integration.mcp.mcp_config_registration import _validate_toml_config as _validate_toml_config

sys.modules[__name__] = _implementation
