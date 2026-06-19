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


def test_prompt_text_mentions_only_registered_tools_after_phase_6a() -> None:
    registry = McpPromptRegistry()
    text = registry.render("generate_codex_brief", {"goal": "Implement tools", "scope": "main"})

    for required in (
        "build_context_pack",
        "read-only working context",
        "Inspect warnings",
        "resource links",
        "explain_result",
    ):
        assert required in text
    for forbidden in (
        "ask_vault",
        "summarize_project_memory",
        "get_open_questions",
        "get_recent_changes",
    ):
        assert forbidden not in text


def test_unknown_prompt_name_raises_invalid_parameter() -> None:
    registry = McpPromptRegistry()

    with pytest.raises(McpProtocolError) as exc_info:
        registry.render("ask_vault", {})

    assert exc_info.value.kind == "invalid_parameter"
    assert exc_info.value.payload.code == "invalid_prompt"
