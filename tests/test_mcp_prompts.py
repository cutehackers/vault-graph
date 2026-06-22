from __future__ import annotations

from collections.abc import Callable

import pytest

from vault_graph.mcp.mcp_errors import McpProtocolError
from vault_graph.mcp.mcp_prompts import PHASE_5C_PROMPT_NAMES, McpPromptRegistry, register_mcp_prompts


class RecordingPromptServer:
    def __init__(self) -> None:
        self.prompts: dict[str, Callable[..., object]] = {}

    def prompt(
        self,
        name: str | None = None,
        title: str | None = None,
        description: str | None = None,
        icons: list[object] | None = None,
    ) -> Callable[[Callable[..., object]], Callable[..., object]]:
        del title, description, icons

        def decorator(func: Callable[..., object]) -> Callable[..., object]:
            assert name is not None
            self.prompts[name] = func
            return func

        return decorator


def test_register_mcp_prompts_registers_exact_phase_5c_prompts() -> None:
    server = RecordingPromptServer()

    registry = register_mcp_prompts(server)

    assert registry.prompt_names == PHASE_5C_PROMPT_NAMES
    assert tuple(server.prompts) == PHASE_5C_PROMPT_NAMES


def test_prompt_text_mentions_registered_phase_6c_memory_tools() -> None:
    registry = McpPromptRegistry()
    codex = registry.render("generate_codex_brief", {"goal": "Implement tools", "scope": "main"})
    implementation = registry.render("prepare_implementation_context", {"task": "Implement tools", "scope": "main"})
    feature = registry.render("summarize_feature_history", {"feature": "Search", "scope": "main"})
    risk = registry.render("analyze_project_risk", {"goal": "Implement tools", "scope": "main"})
    wiki = registry.render("prepare_wiki_update_context", {"topic": "MCP", "scope": "main"})

    for required in (
        "build_context_pack",
        "summarize_project_memory",
        "read-only working context",
        "Inspect warnings",
        "resource links",
        "explain_result",
    ):
        assert required in codex
    assert "summarize_project_memory" in implementation
    assert "get_recent_changes" in implementation
    assert "get_recent_changes" in feature
    assert "get_open_questions" in risk
    assert "get_recent_changes" in risk
    assert "get_open_questions" in wiki


def test_prompt_text_still_omits_unregistered_future_answer_tools() -> None:
    registry = McpPromptRegistry()
    text = "\n".join(
        registry.render(name, {"goal": "G", "task": "T", "topic": "P", "feature": "F", "decision_or_topic": "D"})
        for name in registry.prompt_names
    )

    assert "ask_vault" not in text


def test_unknown_prompt_name_raises_invalid_parameter() -> None:
    registry = McpPromptRegistry()

    with pytest.raises(McpProtocolError) as exc_info:
        registry.render("ask_vault", {})

    assert exc_info.value.kind == "invalid_parameter"
    assert exc_info.value.payload.code == "invalid_prompt"
