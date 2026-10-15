"""Compatibility import for :mod:`vault_graph.interface.mcp.mcp_prompts`."""

import sys
from collections.abc import Callable as Callable
from dataclasses import dataclass as dataclass
from typing import Any as Any
from typing import Protocol as Protocol

from vault_graph.interface.mcp import mcp_prompts as _implementation
from vault_graph.interface.mcp.mcp_errors import McpErrorPayload as McpErrorPayload
from vault_graph.interface.mcp.mcp_errors import McpProtocolError as McpProtocolError
from vault_graph.interface.mcp.mcp_prompts import PHASE_5C_PROMPT_NAMES as PHASE_5C_PROMPT_NAMES
from vault_graph.interface.mcp.mcp_prompts import McpPromptRegistry as McpPromptRegistry
from vault_graph.interface.mcp.mcp_prompts import McpPromptServer as McpPromptServer
from vault_graph.interface.mcp.mcp_prompts import _analyze_project_risk as _analyze_project_risk
from vault_graph.interface.mcp.mcp_prompts import _generate_codex_brief as _generate_codex_brief
from vault_graph.interface.mcp.mcp_prompts import _invalid_prompt as _invalid_prompt
from vault_graph.interface.mcp.mcp_prompts import _join_prompt_lines as _join_prompt_lines
from vault_graph.interface.mcp.mcp_prompts import _optional_argument as _optional_argument
from vault_graph.interface.mcp.mcp_prompts import _prepare_implementation_context as _prepare_implementation_context
from vault_graph.interface.mcp.mcp_prompts import _prepare_wiki_update_context as _prepare_wiki_update_context
from vault_graph.interface.mcp.mcp_prompts import _prompt_header as _prompt_header
from vault_graph.interface.mcp.mcp_prompts import _required_argument as _required_argument
from vault_graph.interface.mcp.mcp_prompts import _review_architecture_decision as _review_architecture_decision
from vault_graph.interface.mcp.mcp_prompts import _scope_line as _scope_line
from vault_graph.interface.mcp.mcp_prompts import _summarize_feature_history as _summarize_feature_history
from vault_graph.interface.mcp.mcp_prompts import _trace_decision_history as _trace_decision_history
from vault_graph.interface.mcp.mcp_prompts import register_mcp_prompts as register_mcp_prompts
from vault_graph.operation.integration.harness.harness_guidance import (
    HARNESS_GUIDANCE_END_MARKER as HARNESS_GUIDANCE_END_MARKER,
)
from vault_graph.operation.integration.harness.harness_guidance import (
    HARNESS_GUIDANCE_START_MARKER as HARNESS_GUIDANCE_START_MARKER,
)

sys.modules[__name__] = _implementation
