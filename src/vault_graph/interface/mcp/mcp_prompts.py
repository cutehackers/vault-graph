from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol

from vault_graph.interface.mcp.mcp_errors import McpErrorPayload, McpProtocolError
from vault_graph.operation.integration.harness.harness_guidance import (
    HARNESS_GUIDANCE_END_MARKER as HARNESS_GUIDANCE_END_MARKER,
)
from vault_graph.operation.integration.harness.harness_guidance import (
    HARNESS_GUIDANCE_START_MARKER as HARNESS_GUIDANCE_START_MARKER,
)


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
# Spec 2026-11-05 §4.4.4: the memory cleanup prompt the agent runs when the user says "기억 정리해".
MCP_PROMPT_NAMES = (*PHASE_5C_PROMPT_NAMES, "curate_memory")

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
    prompt_names: tuple[str, ...] = MCP_PROMPT_NAMES

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
        if name == "curate_memory":
            return _curate_memory(_optional_argument(arguments, "cwd"))
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

    @server.prompt("curate_memory")
    def curate_memory(cwd: str | None = None) -> str:
        """Clean up project memory: candidates, one decision each, evidence and basis rules (기억 정리)."""
        return registry.render("curate_memory", {"cwd": cwd})

    return registry


def _generate_codex_brief(goal: str, scope: str | None) -> str:
    return _join_prompt_lines(
        *_prompt_header("Codex Brief", scope),
        f"Goal: {goal}",
        "Call summarize_project_memory, ask_vault, then build_context_pack for cited working context.",
        "Use search_vault only when the context pack leaves a specific gap.",
        *_SHARED_LINES,
    )


def _prepare_implementation_context(task: str, scope: str | None) -> str:
    return _join_prompt_lines(
        *_prompt_header("Implementation Context", scope),
        f"Task: {task}",
        "Call explore_project first for bounded code and Vault evidence for the registered project.",
        (
            "If project scope is unavailable, use check_index_status, get_recent_changes, "
            "summarize_project_memory, then build_context_pack."
        ),
        "Use ask_vault for direct evidence-first questions that need a cited answer before implementation.",
        "Use find_related only when graph context is needed for named entities or relationships.",
        *_SHARED_LINES,
    )


def _review_architecture_decision(decision_or_topic: str, scope: str | None) -> str:
    return _join_prompt_lines(
        *_prompt_header("Architecture Decision Review", scope),
        f"Decision or topic: {decision_or_topic}",
        "Call get_decision_trace first, then build_context_pack for supporting evidence.",
        "Use ask_vault for a concise cited summary when the decision history spans multiple evidence chunks.",
        "Use search_vault for missing citations or alternative decision pages.",
        *_SHARED_LINES,
    )


def _summarize_feature_history(feature: str, scope: str | None) -> str:
    return _join_prompt_lines(
        *_prompt_header("Feature History", scope),
        f"Feature: {feature}",
        "Call get_recent_changes, then build_context_pack with the feature as the goal.",
        "Use ask_vault to answer the user's feature-history question from cited Vault evidence.",
        "Use find_related for graph-backed dependencies and get_decision_trace for durable decisions.",
        *_SHARED_LINES,
    )


def _analyze_project_risk(goal: str, scope: str | None) -> str:
    return _join_prompt_lines(
        *_prompt_header("Project Risk", scope),
        f"Goal: {goal}",
        (
            "Call check_index_status, get_open_questions, get_recent_changes, build_context_pack, "
            "inspect warnings, then use search_vault for unresolved risk evidence."
        ),
        "Use ask_vault only after inspecting warnings, and preserve partial or insufficient-evidence status.",
        "Use check_index_status when stale or missing indexes could affect confidence.",
        *_SHARED_LINES,
    )


def _prepare_wiki_update_context(topic: str, scope: str | None) -> str:
    return _join_prompt_lines(
        *_prompt_header("Wiki Update Context", scope),
        f"Topic: {topic}",
        "Call get_open_questions, then build_context_pack for read-only source context.",
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


def _curate_memory(cwd: str | None) -> str:
    """The six cleanup steps of spec 2026-11-05 §4.4.4, in Korean for the agent."""
    cwd_argument = f'cwd="{cwd}"' if cwd is not None else "cwd=<지금 작업하는 프로젝트 폴더>"
    return _join_prompt_lines(
        "기억 정리 흐름",
        f"프로젝트 폴더: 모든 도구 호출에 {cwd_argument}를 넘긴다.",
        (
            "vault-graph는 판단 재료만 만든다. 무엇을 기억하고 고치고 폐기할지는 당신이 정하고, "
            "모든 쓰기는 Vault 도구의 검증을 거친다. 아래 순서를 지킨다."
        ),
        (
            f"1. list_memory_candidates({cwd_argument})를 부른다. 이 호출이 새 정리를 시작한다. "
            "후보마다 후보 키(key), 근거 위치(location), 비교 재료(comparison)가 있다. "
            '비교 재료에 "폐기됨: <이유>" 표시가 있으면 폐기된 페이지다.'
        ),
        "2. 후보마다 하나를 고른다.",
        "   - 새 사실이면 remember.",
        "   - 기존 페이지의 claim 하나가 새 사실로 바뀌었으면 supersede_claim.",
        "   - 기존 페이지를 보강하면 update_memory.",
        "   - 페이지 전체가 바뀌었으면 retire_memory(replaced_by=...).",
        "   - 폐기된 기억이 다시 맞게 되었으면 restore_memory. 같은 내용을 새로 쓰지 않는다.",
        "   - 가치가 없으면 건너뛰고, 건너뛴 후보의 키를 모아 mark_candidates_reviewed(keys=[...])로 기록한다.",
        (
            "   - 모든 쓰기 도구 호출에 그 후보의 키를 candidate_key로 함께 넘긴다. 결과가 published나 proposed면 "
            "처리 기록이 남고, rejected나 error면 남지 않아 후보가 다음 정리에 다시 나온다."
        ),
        "3. 근거를 이렇게 적는다.",
        (
            "   - L1 노트(kind l1_note)를 근거로 쓸 때는 먼저 "
            "import_auto_memory(note=<location>, candidate_key=<key>)로 "
            "Vault에 사본을 남기고, 돌려받은 raw/imports/... 경로(raw_path)를 근거로 쓴다."
        ),
        (
            "   - 세션 교환(kind session_exchange)을 근거로 쓸 때는 후보 결과의 교환 위치 <path> L<a>-L<b>를 "
            "그대로 적는다. 파일 경로만 적으면 그 교환을 근거로 쓴 것으로 보지 않는다."
        ),
        (
            '   - 세션 내용을 더 찾아야 하면 search_vault(mode="evidence")로 찾는다. 세션 파일은 원본 근거라 '
            "기본 knowledge 모드 검색에는 나오지 않는다."
        ),
        (
            "4. 근거 원문에 사용자 자신의 말이 있고 그 문장을 인용할 때만 basis: stated로 쓴다. "
            "그 밖은 basis: inferred다. 경계 사례도 inferred다."
        ),
        (
            "5. 한 번의 정리에서 inferred 제안은 10개까지다. 11번째부터는 rejected로 돌아온다. "
            "남은 후보는 다음 정리에서 다룬다."
        ),
        (
            "6. brief 갱신 후보(키가 brief:로 시작)가 있으면 정리 마지막에 brief를 고친다. "
            'brief가 없으면 remember(kind="project"), 있으면 update_memory로 쓴다.'
        ),
        ("정리가 끝나면 사용자에게 stated로 쓴 수, inferred로 제안한 수와 review_path, 건너뛴 후보 수를 짧게 알린다."),
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
