"""Block A of session start recall: pinned memory (spec 2026-11-02 V4, 결정14, 결정S11, 위험6).

A page is pinned only when its frontmatter ``pin`` is the YAML boolean ``true`` (Python ``True``).
The string ``"true"`` does not pin. A page whose ``memory_schema`` is not a known value is treated
as a regular page; the caller warns about it. Block A has its own token budget, so it never takes
room from block B. Usage history is never read here.

The second line of an item is the page ``summary``. ``remember`` writes the title there, so when
the summary is missing or equals the title, the line is the start of the body instead, cut to
``PIN_EXCERPT_MAX_TOKENS`` (F10).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

PIN_BLOCK_TITLE = "## 고정 기억"
PIN_BLOCK_MAX_TOKENS = 400
PIN_EXCERPT_MAX_TOKENS = 60
# The section that ``remember`` drafts end with. It holds evidence lines, not the memory itself.
_EVIDENCE_HEADING = "## evidence"
MEMORY_SCHEMA_V1 = "vault-memory/v1"
KNOWN_MEMORY_SCHEMAS = frozenset({MEMORY_SCHEMA_V1})


@dataclass(frozen=True)
class PinEntry:
    """One pinned page. ``kind`` is ``memory_kind`` or, without it, the page ``type``."""

    item_id: str
    kind: str
    title: str
    summary: str
    location: str
    day: str
    path: str


@dataclass(frozen=True)
class PinBlock:
    """``text`` is empty when there is nothing pinned. ``shown`` is in print order."""

    text: str
    shown: tuple[PinEntry, ...]
    omitted: int


def unknown_memory_schema(frontmatter: Mapping[str, object]) -> str | None:
    """Return the ``memory_schema`` value when it is present but not known, else None."""
    value = frontmatter.get("memory_schema")
    if value is None or value in KNOWN_MEMORY_SCHEMAS:
        return None
    return str(value)


def is_pinned(frontmatter: Mapping[str, object]) -> bool:
    return frontmatter.get("pin") is True and unknown_memory_schema(frontmatter) is None


def pin_line(*, title: str, summary: str | None, body: str) -> str:
    """The second line of a pinned item: a summary that says more than the title, else the body start."""
    if summary and summary != title:
        return summary
    return body_excerpt(body, max_tokens=PIN_EXCERPT_MAX_TOKENS) or title


def body_excerpt(body: str, *, max_tokens: int) -> str:
    """The body as one line without headings, stopping at the evidence section, cut to ``max_tokens``."""
    words: list[str] = []
    for line in body.splitlines():
        stripped = line.strip()
        if stripped.casefold() == _EVIDENCE_HEADING:
            break
        if not stripped.startswith("#"):
            words.extend(stripped.split())
    if len(words) <= max_tokens:
        return " ".join(words)
    return " ".join(words[:max_tokens]) + "…"


def pin_block(entries: Sequence[PinEntry], *, max_tokens: int) -> PinBlock:
    """Render block A newest ``updated`` first, ties by path, dropping items from the end to fit."""
    by_path = sorted(entries, key=lambda item: (item.path, item.location))
    ordered = tuple(sorted(by_path, key=lambda item: item.day, reverse=True))
    if not ordered:
        return PinBlock(text="", shown=(), omitted=0)
    item_lines = [_item_lines(item) for item in ordered]

    def render(count: int) -> str:
        omitted = len(ordered) - count
        lines = [line for pair in item_lines[:count] for line in pair]
        if omitted:
            lines.append(f"- {omitted}개 생략")
        return PIN_BLOCK_TITLE + "\n" + "".join(line + "\n" for line in lines)

    count = len(ordered)
    while count and _tokens(render(count)) > max_tokens:
        count -= 1
    return PinBlock(text=render(count), shown=ordered[:count], omitted=len(ordered) - count)


def _item_lines(item: PinEntry) -> tuple[str, str]:
    return (f"- [{item.item_id}] {item.kind} · {item.title} ({item.location})", f"  {item.summary}")


def _tokens(text: str) -> int:
    """Same whitespace estimate as ``recall.estimate_recall_tokens`` (kept here to avoid an import cycle)."""
    return len(text.split())


__all__ = [
    "KNOWN_MEMORY_SCHEMAS",
    "MEMORY_SCHEMA_V1",
    "PIN_BLOCK_MAX_TOKENS",
    "PIN_BLOCK_TITLE",
    "PIN_EXCERPT_MAX_TOKENS",
    "PinBlock",
    "PinEntry",
    "body_excerpt",
    "is_pinned",
    "pin_block",
    "pin_line",
    "unknown_memory_schema",
]
