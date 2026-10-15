"""Compatibility import for :mod:`vault_graph.interface.mcp.mcp_tools`."""

import json as json
import sys
from collections.abc import Callable as Callable
from dataclasses import dataclass as dataclass
from typing import Any as Any
from typing import Literal as Literal
from typing import Protocol as Protocol
from typing import cast as cast

from vault_graph.context.memory.memory_models import MemoryWarning as MemoryWarning
from vault_graph.context.memory.memory_models import OpenQuestionsProjection as OpenQuestionsProjection
from vault_graph.context.memory.memory_models import ProjectMemoryProjection as ProjectMemoryProjection
from vault_graph.context.pack.context_pack import DEFAULT_CONTEXT_MAX_TOKENS as DEFAULT_CONTEXT_MAX_TOKENS
from vault_graph.context.pack.context_pack import DEFAULT_CONTEXT_RETRIEVAL_LIMIT as DEFAULT_CONTEXT_RETRIEVAL_LIMIT
from vault_graph.context.pack.context_pack import ContextPackBudget as ContextPackBudget
from vault_graph.context.pack.context_pack import ContextPackRequest as ContextPackRequest
from vault_graph.errors import MemoryProjectionError as MemoryProjectionError
from vault_graph.interface.mcp import mcp_tools as _implementation
from vault_graph.interface.mcp.context_pack_resource_cache import ContextPackResourceCache as ContextPackResourceCache
from vault_graph.interface.mcp.mcp_errors import McpErrorPayload as McpErrorPayload
from vault_graph.interface.mcp.mcp_errors import McpProtocolError as McpProtocolError
from vault_graph.interface.mcp.mcp_errors import map_exception_to_mcp_error as map_exception_to_mcp_error
from vault_graph.interface.mcp.mcp_scope import McpScopeInput as McpScopeInput
from vault_graph.interface.mcp.mcp_scope import scope_from_mcp_input as scope_from_mcp_input
from vault_graph.interface.mcp.mcp_service_factory import McpServiceFactory as McpServiceFactory
from vault_graph.interface.mcp.mcp_service_factory import McpServices as McpServices
from vault_graph.interface.mcp.mcp_tools import MAX_MCP_PROJECT_TASK_CHARS as MAX_MCP_PROJECT_TASK_CHARS
from vault_graph.interface.mcp.mcp_tools import MAX_MCP_TOOL_LIMIT as MAX_MCP_TOOL_LIMIT
from vault_graph.interface.mcp.mcp_tools import AskVaultInput as AskVaultInput
from vault_graph.interface.mcp.mcp_tools import BuildContextPackInput as BuildContextPackInput
from vault_graph.interface.mcp.mcp_tools import CheckIndexStatusInput as CheckIndexStatusInput
from vault_graph.interface.mcp.mcp_tools import DecisionTraceInput as DecisionTraceInput
from vault_graph.interface.mcp.mcp_tools import ExplainResultInput as ExplainResultInput
from vault_graph.interface.mcp.mcp_tools import ExploreProjectInput as ExploreProjectInput
from vault_graph.interface.mcp.mcp_tools import FindRelatedInput as FindRelatedInput
from vault_graph.interface.mcp.mcp_tools import GetOpenQuestionsInput as GetOpenQuestionsInput
from vault_graph.interface.mcp.mcp_tools import GetRecentChangesInput as GetRecentChangesInput
from vault_graph.interface.mcp.mcp_tools import McpResourceLink as McpResourceLink
from vault_graph.interface.mcp.mcp_tools import McpToolBody as McpToolBody
from vault_graph.interface.mcp.mcp_tools import McpToolName as McpToolName
from vault_graph.interface.mcp.mcp_tools import McpToolRegistry as McpToolRegistry
from vault_graph.interface.mcp.mcp_tools import McpToolServer as McpToolServer
from vault_graph.interface.mcp.mcp_tools import SearchVaultInput as SearchVaultInput
from vault_graph.interface.mcp.mcp_tools import SummarizeProjectMemoryInput as SummarizeProjectMemoryInput
from vault_graph.interface.mcp.mcp_tools import _bounded_project_context_body as _bounded_project_context_body
from vault_graph.interface.mcp.mcp_tools import _drop_last_mapping_item as _drop_last_mapping_item
from vault_graph.interface.mcp.mcp_tools import _drop_last_payload_item as _drop_last_payload_item
from vault_graph.interface.mcp.mcp_tools import _estimate_mcp_body_tokens as _estimate_mcp_body_tokens
from vault_graph.interface.mcp.mcp_tools import _evidence_token_budget as _evidence_token_budget
from vault_graph.interface.mcp.mcp_tools import _graph_depth as _graph_depth
from vault_graph.interface.mcp.mcp_tools import _invalid_arguments as _invalid_arguments
from vault_graph.interface.mcp.mcp_tools import _is_project_scope_error as _is_project_scope_error
from vault_graph.interface.mcp.mcp_tools import _limit as _limit
from vault_graph.interface.mcp.mcp_tools import _map_tool_exception as _map_tool_exception
from vault_graph.interface.mcp.mcp_tools import (
    _memory_projection_error_to_mcp_error as _memory_projection_error_to_mcp_error,
)
from vault_graph.interface.mcp.mcp_tools import _open_questions_warnings as _open_questions_warnings
from vault_graph.interface.mcp.mcp_tools import _optional_bool as _optional_bool
from vault_graph.interface.mcp.mcp_tools import _optional_positive_int as _optional_positive_int
from vault_graph.interface.mcp.mcp_tools import _optional_project_scope as _optional_project_scope
from vault_graph.interface.mcp.mcp_tools import _optional_string_tuple as _optional_string_tuple
from vault_graph.interface.mcp.mcp_tools import _project_context_body as _project_context_body
from vault_graph.interface.mcp.mcp_tools import _project_depth as _project_depth
from vault_graph.interface.mcp.mcp_tools import _project_limit as _project_limit
from vault_graph.interface.mcp.mcp_tools import _project_memory_warnings as _project_memory_warnings
from vault_graph.interface.mcp.mcp_tools import _project_scope_error as _project_scope_error
from vault_graph.interface.mcp.mcp_tools import _project_task as _project_task
from vault_graph.interface.mcp.mcp_tools import _project_token_budget as _project_token_budget
from vault_graph.interface.mcp.mcp_tools import _reject_cross_vault_without_graph as _reject_cross_vault_without_graph
from vault_graph.interface.mcp.mcp_tools import _required_bool as _required_bool
from vault_graph.interface.mcp.mcp_tools import _required_string as _required_string
from vault_graph.interface.mcp.mcp_tools import _scope_for_tool as _scope_for_tool
from vault_graph.interface.mcp.mcp_tools import _string_tuple as _string_tuple
from vault_graph.interface.mcp.mcp_tools import _tool_body as _tool_body
from vault_graph.interface.mcp.mcp_tools import _trim_project_context_payload as _trim_project_context_payload
from vault_graph.interface.mcp.mcp_tools import _validate_ask_vault_request as _validate_ask_vault_request
from vault_graph.interface.mcp.mcp_tools import (
    _validate_build_context_pack_request as _validate_build_context_pack_request,
)
from vault_graph.interface.mcp.mcp_tools import _validate_decision_trace_request as _validate_decision_trace_request
from vault_graph.interface.mcp.mcp_tools import _validate_explain_result_request as _validate_explain_result_request
from vault_graph.interface.mcp.mcp_tools import _validate_explore_project_request as _validate_explore_project_request
from vault_graph.interface.mcp.mcp_tools import _validate_find_related_request as _validate_find_related_request
from vault_graph.interface.mcp.mcp_tools import (
    _validate_get_open_questions_request as _validate_get_open_questions_request,
)
from vault_graph.interface.mcp.mcp_tools import (
    _validate_get_recent_changes_request as _validate_get_recent_changes_request,
)
from vault_graph.interface.mcp.mcp_tools import (
    _validate_graph_cross_vault_request as _validate_graph_cross_vault_request,
)
from vault_graph.interface.mcp.mcp_tools import _validate_search_vault_request as _validate_search_vault_request
from vault_graph.interface.mcp.mcp_tools import (
    _validate_summarize_project_memory_request as _validate_summarize_project_memory_request,
)
from vault_graph.interface.mcp.mcp_tools import _warning_to_dict as _warning_to_dict
from vault_graph.interface.mcp.mcp_tools import mcp_scope_input_from_raw as mcp_scope_input_from_raw
from vault_graph.interface.mcp.mcp_tools import parse_ask_vault_input as parse_ask_vault_input
from vault_graph.interface.mcp.mcp_tools import parse_build_context_pack_input as parse_build_context_pack_input
from vault_graph.interface.mcp.mcp_tools import parse_check_index_status_input as parse_check_index_status_input
from vault_graph.interface.mcp.mcp_tools import parse_decision_trace_input as parse_decision_trace_input
from vault_graph.interface.mcp.mcp_tools import parse_explain_result_input as parse_explain_result_input
from vault_graph.interface.mcp.mcp_tools import parse_explore_project_input as parse_explore_project_input
from vault_graph.interface.mcp.mcp_tools import parse_find_related_input as parse_find_related_input
from vault_graph.interface.mcp.mcp_tools import parse_get_open_questions_input as parse_get_open_questions_input
from vault_graph.interface.mcp.mcp_tools import parse_get_recent_changes_input as parse_get_recent_changes_input
from vault_graph.interface.mcp.mcp_tools import parse_search_vault_input as parse_search_vault_input
from vault_graph.interface.mcp.mcp_tools import (
    parse_summarize_project_memory_input as parse_summarize_project_memory_input,
)
from vault_graph.interface.mcp.mcp_tools import register_mcp_tools as register_mcp_tools
from vault_graph.interface.mcp.mcp_uri import encode_resource_segment as encode_resource_segment
from vault_graph.interface.mcp.result_explanation_cache import ResultExplanationCache as ResultExplanationCache
from vault_graph.operation.scope.vault_catalog import QueryScope as QueryScope
from vault_graph.operation.scope.vault_catalog import VaultCatalog as VaultCatalog
from vault_graph.project_context import DEFAULT_PROJECT_CONTEXT_DEPTH as DEFAULT_PROJECT_CONTEXT_DEPTH
from vault_graph.project_context import DEFAULT_PROJECT_CONTEXT_LIMIT as DEFAULT_PROJECT_CONTEXT_LIMIT
from vault_graph.project_context import DEFAULT_PROJECT_CONTEXT_TOKENS as DEFAULT_PROJECT_CONTEXT_TOKENS
from vault_graph.project_context import MAX_PROJECT_CONTEXT_DEPTH as MAX_PROJECT_CONTEXT_DEPTH
from vault_graph.project_context import MAX_PROJECT_CONTEXT_LIMIT as MAX_PROJECT_CONTEXT_LIMIT
from vault_graph.project_context import MAX_PROJECT_CONTEXT_TOKENS as MAX_PROJECT_CONTEXT_TOKENS
from vault_graph.project_context import MIN_PROJECT_CONTEXT_TOKENS as MIN_PROJECT_CONTEXT_TOKENS
from vault_graph.project_context import ProjectContextRequest as ProjectContextRequest
from vault_graph.retrieval.explanation.result_explanation import ExplainResultService as ExplainResultService
from vault_graph.retrieval.graph.projection.graph_projection import (
    DEFAULT_GRAPH_RELATED_DEPTH as DEFAULT_GRAPH_RELATED_DEPTH,
)
from vault_graph.retrieval.graph.projection.graph_projection import (
    DEFAULT_GRAPH_RESULT_LIMIT as DEFAULT_GRAPH_RESULT_LIMIT,
)
from vault_graph.retrieval.graph.projection.graph_projection import (
    MAX_GRAPH_PROJECTION_DEPTH as MAX_GRAPH_PROJECTION_DEPTH,
)
from vault_graph.retrieval.search.search_response import SearchMode as SearchMode

sys.modules[__name__] = _implementation
