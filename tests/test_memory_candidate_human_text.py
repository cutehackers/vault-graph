"""Session candidate signals read only what a person typed (spec 2026-11-05 §4.4.4, §4.2.2 사람 턴).

A real "기억 정리해" run (A-23, 2026-11-07) got 17 `correction` candidates and none was a person's
correction: they were prompts to subagents, context summaries after compaction and tagged command text.
"""

from __future__ import annotations

from types import SimpleNamespace

from vault_graph.indexing.ingestion.session_exchange_v1_chunker import SESSION_EXCHANGE_V1_VERSION
from vault_graph.indexing.ingestion.session_exchange_v2_chunker import SESSION_EXCHANGE_V2_VERSION
from vault_graph.interface.composition.memory_candidate_sources import _exchange

PATH = "raw/sessions/claude-code/2026-11-06-sess-part1.md"


def _human(lines: list[str], version: str) -> str:
    document = SimpleNamespace(path=PATH, frontmatter={"session_id": "sess"})
    locator = SimpleNamespace(coordinates=(("line", 1), ("line_end", len(lines))))
    chunk = SimpleNamespace(parent_locators=(locator,), chunker_version=version)
    exchange = _exchange(document, chunk, "key", lines)  # type: ignore[arg-type]
    assert exchange is not None
    return exchange.human_text


def test_v1_person_turn_is_human_text() -> None:
    lines = ["## 2026-11-06T10:00:00.000Z user", "", "아니야, 그건 틀렸어", "", "## 2026-11-06T10:00:01.000Z assistant"]

    assert _human(lines, SESSION_EXCHANGE_V1_VERSION) == "아니야, 그건 틀렸어"


def test_v1_prompt_to_a_subagent_is_not_human_text() -> None:
    lines = ["## 2026-11-06T10:00:00.000Z subagent a4c8 user", "", "Fix the bug. Do not touch other files."]

    assert _human(lines, SESSION_EXCHANGE_V1_VERSION) == ""


def test_v1_summary_after_compaction_is_not_human_text() -> None:
    lines = [
        "## 2026-11-07T01:57:49.039Z user",
        "",
        "This session is being continued from a previous conversation that ran out of context. The summary below",
        "- fix the push gate. Do not add Co-Authored-By.",
    ]

    assert _human(lines, SESSION_EXCHANGE_V1_VERSION) == ""


def test_v1_turn_that_starts_with_a_tag_is_not_human_text() -> None:
    lines = ["## 2026-11-03T10:40:17.669Z user", "", "<command-message>bake:bake</command-message>", "fix it"]

    assert _human(lines, SESSION_EXCHANGE_V1_VERSION) == ""


def test_v1_keeps_later_person_turns_in_the_same_exchange() -> None:
    lines = [
        "## 2026-11-06T10:00:00.000Z subagent a4c8 user",
        "Fix the bug.",
        "## 2026-11-06T10:00:01.000Z user",
        "그 방법 말고 다른 방법으로 해",
    ]

    assert _human(lines, SESSION_EXCHANGE_V1_VERSION) == "그 방법 말고 다른 방법으로 해"


def test_v2_subagent_exchange_has_no_human_text() -> None:
    lines = [
        "## Subagent a7f3 · code-reviewer · 2026-11-03T14:00:02.000Z · s-301",
        "<!-- vg:exchange id=s-301 scope=subagent:a7f3 started=2026-11-03T14:00:02.000Z outcome=answered -->",
        "",
        "### user · 2026-11-03T14:00:02.000Z · s-301",
        "",
        "Review src/app.py for bugs. Do not change files.",
    ]

    assert _human(lines, SESSION_EXCHANGE_V2_VERSION) == ""


def test_v2_main_exchange_keeps_the_person_turn() -> None:
    lines = [
        "## Review it. 2026-11-03T14:00:00.000Z · u-201",
        "<!-- vg:exchange id=u-201 scope=main started=2026-11-03T14:00:00.000Z outcome=answered -->",
        "",
        "### user · 2026-11-03T14:00:00.000Z · u-201",
        "",
        "아니야, 리뷰어를 써",
    ]

    assert _human(lines, SESSION_EXCHANGE_V2_VERSION) == "아니야, 리뷰어를 써"
