from __future__ import annotations

from typing import Any

__all__ = [
    "McpErrorPayload",
    "McpProtocolError",
    "McpPromptRegistry",
    "McpResourceBody",
    "McpResourceLink",
    "McpResourceRegistry",
    "McpResourceRequest",
    "McpResourceUri",
    "McpScopeInput",
    "McpServerConfig",
    "McpServiceFactory",
    "McpServices",
    "McpToolBody",
    "McpToolRegistry",
    "PHASE_5C_PROMPT_NAMES",
    "RegisteredMcpServer",
    "CachedContextPack",
    "CachedExplanation",
    "ContextPackResourceCache",
    "ExplainResultInput",
    "GetOpenQuestionsInput",
    "GetRecentChangesInput",
    "ResultExplanationCache",
    "SummarizeProjectMemoryInput",
    "codex_stdio_config_json",
    "create_mcp_server",
    "decode_resource_segment",
    "encode_resource_segment",
    "map_exception_to_mcp_error",
    "parse_mcp_resource_uri",
    "parse_explain_result_input",
    "parse_get_open_questions_input",
    "parse_get_recent_changes_input",
    "parse_summarize_project_memory_input",
    "register_mcp_prompts",
    "register_mcp_tools",
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
    if name in {"McpResourceUri", "parse_mcp_resource_uri", "encode_resource_segment", "decode_resource_segment"}:
        from vault_graph.mcp.mcp_uri import (
            McpResourceUri,
            decode_resource_segment,
            encode_resource_segment,
            parse_mcp_resource_uri,
        )

        return {
            "McpResourceUri": McpResourceUri,
            "parse_mcp_resource_uri": parse_mcp_resource_uri,
            "encode_resource_segment": encode_resource_segment,
            "decode_resource_segment": decode_resource_segment,
        }[name]
    if name in {"McpResourceRequest", "McpResourceBody", "McpResourceRegistry"}:
        from vault_graph.mcp.mcp_resources import McpResourceBody, McpResourceRegistry, McpResourceRequest

        return {
            "McpResourceRequest": McpResourceRequest,
            "McpResourceBody": McpResourceBody,
            "McpResourceRegistry": McpResourceRegistry,
        }[name]
    if name in {"McpPromptRegistry", "PHASE_5C_PROMPT_NAMES", "register_mcp_prompts"}:
        from vault_graph.mcp.mcp_prompts import PHASE_5C_PROMPT_NAMES, McpPromptRegistry, register_mcp_prompts

        return {
            "McpPromptRegistry": McpPromptRegistry,
            "PHASE_5C_PROMPT_NAMES": PHASE_5C_PROMPT_NAMES,
            "register_mcp_prompts": register_mcp_prompts,
        }[name]
    if name in {
        "ExplainResultInput",
        "GetOpenQuestionsInput",
        "GetRecentChangesInput",
        "McpResourceLink",
        "McpToolBody",
        "McpToolRegistry",
        "SummarizeProjectMemoryInput",
        "parse_explain_result_input",
        "parse_get_open_questions_input",
        "parse_get_recent_changes_input",
        "parse_summarize_project_memory_input",
        "register_mcp_tools",
    }:
        from vault_graph.mcp.mcp_tools import (
            ExplainResultInput,
            GetOpenQuestionsInput,
            GetRecentChangesInput,
            McpResourceLink,
            McpToolBody,
            McpToolRegistry,
            SummarizeProjectMemoryInput,
            parse_explain_result_input,
            parse_get_open_questions_input,
            parse_get_recent_changes_input,
            parse_summarize_project_memory_input,
            register_mcp_tools,
        )

        return {
            "ExplainResultInput": ExplainResultInput,
            "GetOpenQuestionsInput": GetOpenQuestionsInput,
            "GetRecentChangesInput": GetRecentChangesInput,
            "McpResourceLink": McpResourceLink,
            "McpToolBody": McpToolBody,
            "McpToolRegistry": McpToolRegistry,
            "SummarizeProjectMemoryInput": SummarizeProjectMemoryInput,
            "parse_explain_result_input": parse_explain_result_input,
            "parse_get_open_questions_input": parse_get_open_questions_input,
            "parse_get_recent_changes_input": parse_get_recent_changes_input,
            "parse_summarize_project_memory_input": parse_summarize_project_memory_input,
            "register_mcp_tools": register_mcp_tools,
        }[name]
    if name in {"ContextPackResourceCache", "CachedContextPack"}:
        from vault_graph.mcp.context_pack_resource_cache import CachedContextPack, ContextPackResourceCache

        return {"ContextPackResourceCache": ContextPackResourceCache, "CachedContextPack": CachedContextPack}[name]
    if name in {"CachedExplanation", "ResultExplanationCache"}:
        from vault_graph.mcp.result_explanation_cache import CachedExplanation, ResultExplanationCache

        return {
            "CachedExplanation": CachedExplanation,
            "ResultExplanationCache": ResultExplanationCache,
        }[name]
    if name == "codex_stdio_config_json":
        from vault_graph.mcp.mcp_config_examples import codex_stdio_config_json

        return codex_stdio_config_json
    raise AttributeError(name)


def __dir__() -> list[str]:
    return sorted(__all__)
