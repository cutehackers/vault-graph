"""Shared parts of the MCP tool layer: tool names, the server port, the tool body and argument errors.

``mcp_tools`` (read tools and registration) and ``mcp_memory_tools`` (the three Vault write tools)
both build on these, so neither imports the other's internals (정리 발견1).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Literal, Protocol

from vault_graph.interface.mcp.mcp_errors import McpErrorPayload, McpProtocolError, map_exception_to_mcp_error
from vault_graph.interface.mcp.mcp_resource_models import McpResourceLink
from vault_graph.interface.mcp.mcp_service_factory import McpServiceFactory

McpToolName = Literal[
    "ask_vault",
    "search_vault",
    "build_context_pack",
    "find_related",
    "get_decision_trace",
    "check_index_status",
    "explain_result",
    "summarize_project_memory",
    "get_open_questions",
    "get_recent_changes",
    "explore_project",
    "remember",
    "update_memory",
    "retire_memory",
]


class McpToolServer(Protocol):
    def tool(
        self,
        name: str | None = None,
        title: str | None = None,
        description: str | None = None,
        annotations: Any | None = None,
        icons: list[Any] | None = None,
        meta: dict[str, Any] | None = None,
        structured_output: bool | None = None,
    ) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        raise NotImplementedError


@dataclass(frozen=True)
class McpToolBody:
    tool_name: McpToolName
    payload: dict[str, object]
    resource_links: tuple[McpResourceLink, ...]
    warnings: tuple[McpErrorPayload, ...]
    text: str

    def to_json_dict(self) -> dict[str, object]:
        return {
            "tool_name": self.tool_name,
            "payload": self.payload,
            "resource_links": [link.to_json_dict() for link in self.resource_links],
            "warnings": [_warning_to_dict(warning) for warning in self.warnings],
            "text": self.text,
        }


def _warning_to_dict(warning: McpErrorPayload) -> dict[str, object]:
    return {
        "code": warning.code,
        "message": warning.message,
        "severity": warning.severity,
        "affected_vault_ids": list(warning.affected_vault_ids),
        "recovery_hint": warning.recovery_hint,
    }


def tool_body(
    *,
    tool_name: McpToolName,
    payload: dict[str, object],
    resource_links: tuple[McpResourceLink, ...],
    warnings: tuple[McpErrorPayload, ...],
    text: str | None = None,
) -> McpToolBody:
    from vault_graph.interface.mcp.mcp_tool_serialization import tool_text_mirror

    return McpToolBody(
        tool_name=tool_name,
        payload=payload,
        resource_links=resource_links,
        warnings=warnings,
        text=text if text is not None else tool_text_mirror(payload),
    )


def map_tool_exception(exc: Exception, *, service_factory: McpServiceFactory) -> McpProtocolError:
    if isinstance(exc, McpProtocolError):
        return exc
    graph_home_path = getattr(service_factory, "_graph_home_path", None)
    return map_exception_to_mcp_error(exc, user_graph_home_path=graph_home_path)


def invalid_arguments(message: str) -> McpProtocolError:
    return McpProtocolError(
        kind="invalid_parameter",
        payload=McpErrorPayload(
            code="invalid_tool_arguments",
            message=message,
            severity="error",
            affected_vault_ids=(),
            recovery_hint="Check the tool argument schema and retry with bounded scope.",
        ),
    )


__all__ = [
    "McpToolBody",
    "McpToolName",
    "McpToolServer",
    "invalid_arguments",
    "map_tool_exception",
    "tool_body",
]
