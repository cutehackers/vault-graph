"""Block A of session start recall: pinned memory (spec 2026-11-02 V4, 결정14, 결정S11, 위험6)."""

from __future__ import annotations

import hashlib
import re

import pytest

from vault_graph.context.pack.recall_pins import (
    MEMORY_SCHEMA_V1,
    PIN_BLOCK_MAX_TOKENS,
    PIN_BLOCK_TITLE,
    PinEntry,
    is_pinned,
    pin_block,
    unknown_memory_schema,
)
from vault_graph.indexing.ingestion.vault_frontmatter_reader import read_frontmatter


def entry(path: str, *, day: str = "2026-10-01", title: str = "Rule", summary: str = "Short summary") -> PinEntry:
    return PinEntry(
        item_id="m:" + hashlib.sha256(path.encode()).hexdigest()[:8],
        kind="rule",
        title=title,
        summary=summary,
        location=path,
        day=day,
        path=path,
    )


def tokens(text: str) -> int:
    return len(text.split())


def test_yaml_boolean_true_is_python_true_and_quoted_true_is_a_string() -> None:
    """위험6: the frontmatter reader gives ``True`` for ``pin: true`` and ``"true"`` for ``pin: "true"``."""
    boolean = read_frontmatter(f"---\npin: true\nmemory_schema: {MEMORY_SCHEMA_V1}\n---\nbody\n").data
    quoted = read_frontmatter(f'---\npin: "true"\nmemory_schema: {MEMORY_SCHEMA_V1}\n---\nbody\n').data

    assert boolean["pin"] is True
    assert quoted["pin"] == "true"
    assert is_pinned(boolean) is True
    assert is_pinned(quoted) is False


@pytest.mark.parametrize("value", [False, "true", "yes", 1, None, ["true"]])
def test_only_boolean_true_pins(value: object) -> None:
    assert is_pinned({"pin": value, "memory_schema": MEMORY_SCHEMA_V1}) is False


def test_pin_without_memory_schema_still_pins() -> None:
    assert is_pinned({"pin": True}) is True


def test_unknown_memory_schema_does_not_pin_and_is_reported() -> None:
    frontmatter = {"pin": True, "memory_schema": "vault-memory/v2"}

    assert is_pinned(frontmatter) is False
    assert unknown_memory_schema(frontmatter) == "vault-memory/v2"
    assert unknown_memory_schema({"memory_schema": MEMORY_SCHEMA_V1}) is None
    assert unknown_memory_schema({}) is None


def test_empty_input_gives_an_empty_block() -> None:
    block = pin_block((), max_tokens=PIN_BLOCK_MAX_TOKENS)

    assert (block.text, block.shown, block.omitted) == ("", (), 0)


def test_each_item_is_a_title_line_and_a_summary_line() -> None:
    pinned = PinEntry(
        item_id="m:0123abcd",
        kind="correction",
        title="Use uv run",
        summary="Never call pip directly.",
        location="team:wiki/rules/uv.md",
        day="2026-10-01",
        path="wiki/rules/uv.md",
    )

    block = pin_block((pinned,), max_tokens=PIN_BLOCK_MAX_TOKENS)

    assert block.text == (
        f"{PIN_BLOCK_TITLE}\n"
        "- [m:0123abcd] correction · Use uv run (team:wiki/rules/uv.md)\n"
        "  Never call pip directly.\n"
    )
    assert PIN_BLOCK_TITLE == "## 고정 기억"


def test_order_is_newest_updated_first_then_path() -> None:
    entries = (
        entry("wiki/b.md", day="2026-10-01"),
        entry("wiki/a.md", day="2026-10-01"),
        entry("wiki/z.md", day="2026-10-05"),
    )

    block = pin_block(entries, max_tokens=PIN_BLOCK_MAX_TOKENS)

    assert [item.path for item in block.shown] == ["wiki/z.md", "wiki/a.md", "wiki/b.md"]
    locations = re.findall(r"\((wiki/\S+)\)$", block.text, flags=re.MULTILINE)
    assert locations == ["wiki/z.md", "wiki/a.md", "wiki/b.md"]


def test_over_budget_drops_from_the_end_and_counts_omitted_items() -> None:
    entries = tuple(
        entry(f"wiki/rules/r{index:02d}.md", day=f"2026-10-{index + 1:02d}", summary="word " * 30)
        for index in range(20)
    )

    block = pin_block(entries, max_tokens=PIN_BLOCK_MAX_TOKENS)

    assert tokens(block.text) <= PIN_BLOCK_MAX_TOKENS
    assert block.omitted > 0
    assert len(block.shown) + block.omitted == 20
    assert block.text.splitlines()[-1] == f"- {block.omitted}개 생략"
    # The newest items stay; the oldest are dropped.
    assert block.shown[0].path == "wiki/rules/r19.md"
    assert block.shown[-1].day > "2026-10-01"


def test_a_tiny_budget_keeps_only_the_heading_and_the_count() -> None:
    block = pin_block((entry("wiki/a.md", summary="word " * 50),), max_tokens=10)

    assert block.shown == ()
    assert block.text == f"{PIN_BLOCK_TITLE}\n- 1개 생략\n"
