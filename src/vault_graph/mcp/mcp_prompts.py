from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol

from vault_graph.mcp.mcp_errors import McpErrorPayload, McpProtocolError


class McpPromptServer(Protocol):
    def prompt(
        self,
        name: str | None = None,
        title: str | None = None,
        description: str | None = None,
        icons: list[Any] | None = None,
    ) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        raise NotImplementedError


PHASE_5C_PROMPT_NAMES = (
    "generate_codex_brief",
    "prepare_implementation_context",
    "review_architecture_decision",
    "summarize_feature_history",
    "analyze_project_risk",
    "prepare_wiki_update_context",
    "trace_decision_history",
)

_SHARED_LINES = (
    "Use Vault Graph as read-only working context.",
    "Do not read the whole Vault when a scoped context pack is enough.",
    "Inspect warnings before relying on evidence.",
    "Preserve vault_id, document IDs, chunk IDs, and resource links.",
    "Use explain_result for result_id or context item_id values you plan to rely on.",
    (
        "If durable knowledge should change, propose the Vault source capture, validation, release gate, "
        "and Git workflow. Do not publish through Vault Graph."
    ),
)


@dataclass(frozen=True)
class McpPromptRegistry:
    prompt_names: tuple[str, ...] = PHASE_5C_PROMPT_NAMES

    def render(self, name: str, arguments: dict[str, object]) -> str:
        if name == "generate_codex_brief":
            return _generate_codex_brief(_required_argument(arguments, "goal"), _optional_argument(arguments, "scope"))
        if name == "prepare_implementation_context":
            return _prepare_implementation_context(
                _required_argument(arguments, "task"),
                _optional_argument(arguments, "scope"),
            )
        if name == "review_architecture_decision":
            return _review_architecture_decision(
                _required_argument(arguments, "decision_or_topic"),
                _optional_argument(arguments, "scope"),
            )
        if name == "summarize_feature_history":
            return _summarize_feature_history(
                _required_argument(arguments, "feature"),
                _optional_argument(arguments, "scope"),
            )
        if name == "analyze_project_risk":
            return _analyze_project_risk(_required_argument(arguments, "goal"), _optional_argument(arguments, "scope"))
        if name == "prepare_wiki_update_context":
            return _prepare_wiki_update_context(
                _required_argument(arguments, "topic"),
                _optional_argument(arguments, "scope"),
            )
        if name == "trace_decision_history":
            return _trace_decision_history(
                _required_argument(arguments, "decision_or_topic"),
                _optional_argument(arguments, "scope"),
            )
        raise _invalid_prompt(f"unknown MCP prompt: {name}")


def register_mcp_prompts(server: McpPromptServer) -> McpPromptRegistry:
    registry = McpPromptRegistry()

    @server.prompt("generate_codex_brief")
    def generate_codex_brief(goal: str, scope: str | None = None) -> str:
        return registry.render("generate_codex_brief", {"goal": goal, "scope": scope})

    @server.prompt("prepare_implementation_context")
    def prepare_implementation_context(task: str, scope: str | None = None) -> str:
        return registry.render("prepare_implementation_context", {"task": task, "scope": scope})

    @server.prompt("review_architecture_decision")
    def review_architecture_decision(decision_or_topic: str, scope: str | None = None) -> str:
        return registry.render(
            "review_architecture_decision",
            {"decision_or_topic": decision_or_topic, "scope": scope},
        )

    @server.prompt("summarize_feature_history")
    def summarize_feature_history(feature: str, scope: str | None = None) -> str:
        return registry.render("summarize_feature_history", {"feature": feature, "scope": scope})

    @server.prompt("analyze_project_risk")
    def analyze_project_risk(goal: str, scope: str | None = None) -> str:
        return registry.render("analyze_project_risk", {"goal": goal, "scope": scope})

    @server.prompt("prepare_wiki_update_context")
    def prepare_wiki_update_context(topic: str, scope: str | None = None) -> str:
        return registry.render("prepare_wiki_update_context", {"topic": topic, "scope": scope})

    @server.prompt("trace_decision_history")
    def trace_decision_history(decision_or_topic: str, scope: str | None = None) -> str:
        return registry.render("trace_decision_history", {"decision_or_topic": decision_or_topic, "scope": scope})

    return registry


def _generate_codex_brief(goal: str, scope: str | None) -> str:
    return _join_prompt_lines(
        *_prompt_header("Codex Brief", scope),
        f"Goal: {goal}",
        "Call build_context_pack first. Use returned resource links for follow-up evidence.",
        "Use search_vault only when the context pack leaves a specific gap.",
        *_SHARED_LINES,
    )


def _prepare_implementation_context(task: str, scope: str | None) -> str:
    return _join_prompt_lines(
        *_prompt_header("Implementation Context", scope),
        f"Task: {task}",
        "Call check_index_status, then build_context_pack for the bounded implementation scope.",
        "Use find_related only when graph context is needed for named entities or relationships.",
        *_SHARED_LINES,
    )


def _review_architecture_decision(decision_or_topic: str, scope: str | None) -> str:
    return _join_prompt_lines(
        *_prompt_header("Architecture Decision Review", scope),
        f"Decision or topic: {decision_or_topic}",
        "Call get_decision_trace first, then build_context_pack for supporting evidence.",
        "Use search_vault for missing citations or alternative decision pages.",
        *_SHARED_LINES,
    )


def _summarize_feature_history(feature: str, scope: str | None) -> str:
    return _join_prompt_lines(
        *_prompt_header("Feature History", scope),
        f"Feature: {feature}",
        "Call build_context_pack with the feature as the goal.",
        "Use find_related for graph-backed dependencies and get_decision_trace for durable decisions.",
        *_SHARED_LINES,
    )


def _analyze_project_risk(goal: str, scope: str | None) -> str:
    return _join_prompt_lines(
        *_prompt_header("Project Risk", scope),
        f"Goal: {goal}",
        "Call build_context_pack, inspect warnings, then use search_vault for unresolved risk evidence.",
        "Use check_index_status when stale or missing indexes could affect confidence.",
        *_SHARED_LINES,
    )


def _prepare_wiki_update_context(topic: str, scope: str | None) -> str:
    return _join_prompt_lines(
        *_prompt_header("Wiki Update Context", scope),
        f"Topic: {topic}",
        "Call build_context_pack for read-only source context.",
        "Use get_decision_trace when the update depends on prior decisions.",
        "Propose the external Vault validation workflow for durable edits.",
        *_SHARED_LINES,
    )


def _trace_decision_history(decision_or_topic: str, scope: str | None) -> str:
    return _join_prompt_lines(
        *_prompt_header("Decision History", scope),
        f"Decision or topic: {decision_or_topic}",
        "Call get_decision_trace first.",
        "Use build_context_pack to collect supporting pages and resource links.",
        *_SHARED_LINES,
    )


def _prompt_header(title: str, scope: str | None) -> tuple[str, ...]:
    return (f"{title} Workflow", _scope_line(scope))


def _scope_line(scope: str | None) -> str:
    if scope is None or not scope.strip():
        return "Scope: use the active Vault unless the user provides a narrower scope."
    return f"Scope: {scope.strip()}"


def _join_prompt_lines(*lines: str) -> str:
    return "\n".join(line for line in lines if line.strip())


def _required_argument(arguments: dict[str, object], name: str) -> str:
    value = arguments.get(name)
    if not isinstance(value, str) or not value.strip():
        raise _invalid_prompt(f"{name} is required")
    return value.strip()


def _optional_argument(arguments: dict[str, object], name: str) -> str | None:
    value = arguments.get(name)
    if value is None:
        return None
    if not isinstance(value, str):
        raise _invalid_prompt(f"{name} must be a string")
    return value.strip() or None


def _invalid_prompt(message: str) -> McpProtocolError:
    return McpProtocolError(
        kind="invalid_parameter",
        payload=McpErrorPayload(
            code="invalid_prompt",
            message=message,
            severity="error",
            affected_vault_ids=(),
            recovery_hint="Use one of the registered Phase 5C MCP prompts with its required arguments.",
        ),
    )
