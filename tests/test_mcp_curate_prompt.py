"""MCP prompt ``curate_memory`` (spec 2026-11-05 §4.4.4, A-23): the six cleanup steps in Korean."""

from __future__ import annotations

import asyncio
import re

from tests.test_mcp_prompts import RecordingPromptServer
from vault_graph.interface.mcp.mcp_prompts import (
    MCP_PROMPT_NAMES,
    PHASE_5C_PROMPT_NAMES,
    McpPromptRegistry,
    register_mcp_prompts,
)


def _text(cwd: str | None = None) -> str:
    return McpPromptRegistry().render("curate_memory", {"cwd": cwd})


def test_curate_memory_is_registered_after_the_phase_5c_prompts() -> None:
    server = RecordingPromptServer()

    registry = register_mcp_prompts(server)

    assert MCP_PROMPT_NAMES == (*PHASE_5C_PROMPT_NAMES, "curate_memory")
    assert registry.prompt_names == MCP_PROMPT_NAMES
    assert tuple(server.prompts) == MCP_PROMPT_NAMES


def test_curate_memory_is_listed_by_the_mcp_server() -> None:
    from mcp.server.fastmcp import FastMCP

    server = FastMCP("prompt-check")
    register_mcp_prompts(server)

    prompts = {prompt.name: prompt for prompt in asyncio.run(server.list_prompts())}
    assert "curate_memory" in prompts
    arguments = prompts["curate_memory"].arguments or []
    assert [(argument.name, argument.required) for argument in arguments] == [("cwd", False)]


def test_curate_memory_has_six_numbered_steps_in_order() -> None:
    text = _text()

    steps = [int(match.group(1)) for match in re.finditer(r"^(\d)\. ", text, flags=re.MULTILINE)]
    assert steps == [1, 2, 3, 4, 5, 6]


def test_step_1_lists_candidates_and_starts_a_cleanup() -> None:
    step = _step(_text(), 1)

    assert "list_memory_candidates" in step


def test_step_2_names_every_choice_and_candidate_key() -> None:
    step = _step(_text(), 2)

    for tool in ("remember", "supersede_claim", "update_memory", "retire_memory(replaced_by=...)", "restore_memory"):
        assert tool in step
    assert "mark_candidates_reviewed" in step
    assert "candidate_key" in step
    assert "모든 쓰기 도구 호출" in step


def test_step_3_says_how_to_cite_l1_notes_and_session_exchanges() -> None:
    step = _step(_text(), 3)

    assert "import_auto_memory" in step
    assert "raw/imports/" in step
    assert "<path> L<a>-L<b>" in step
    assert 'search_vault(mode="evidence")' in step
    assert "knowledge" in step


def test_step_4_is_the_basis_rule() -> None:
    step = _step(_text(), 4)

    assert "basis: stated" in step
    assert "basis: inferred" in step
    assert "사용자 자신의 말" in step
    assert "인용" in step


def test_step_5_is_the_inferred_limit() -> None:
    step = _step(_text(), 5)

    assert "inferred" in step
    assert "10개" in step


def test_step_6_updates_the_brief_last() -> None:
    step = _step(_text(), 6)

    assert "brief" in step
    assert 'remember(kind="project")' in step
    assert "update_memory" in step


def test_curate_memory_passes_cwd_to_the_tools() -> None:
    assert "/work/repo" in _text("/work/repo")
    assert "cwd" in _text()


def _step(text: str, number: int) -> str:
    match = re.search(rf"^{number}\. .*?(?=^\d\. |\Z)", text, flags=re.MULTILINE | re.DOTALL)
    assert match is not None, text
    return match.group(0)
