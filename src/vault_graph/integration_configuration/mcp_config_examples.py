"""Compatibility import for :mod:`vault_graph.operation.integration.mcp.mcp_config_examples`."""

import json as json
import sys
from typing import TypedDict as TypedDict

from vault_graph.operation.integration.mcp import mcp_config_examples as _implementation
from vault_graph.operation.integration.mcp.mcp_config_examples import (
    CODEX_STDIO_CONFIG_EXAMPLE as CODEX_STDIO_CONFIG_EXAMPLE,
)
from vault_graph.operation.integration.mcp.mcp_config_examples import CodexMcpConfig as CodexMcpConfig
from vault_graph.operation.integration.mcp.mcp_config_examples import CodexMcpServerConfig as CodexMcpServerConfig
from vault_graph.operation.integration.mcp.mcp_config_examples import codex_stdio_config_json as codex_stdio_config_json

sys.modules[__name__] = _implementation
