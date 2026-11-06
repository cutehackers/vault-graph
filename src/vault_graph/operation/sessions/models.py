"""Shapes of the normalized session format ``vg-session-jsonl/1`` (spec 2026-11-05 §4.2.2).

A normalized file holds one session: a ``session`` line, then each ``exchange`` line followed by its
``turn`` lines. Field order in these dataclasses is the key order on each JSON line, after ``schema``
and ``kind``. Adding a field keeps ``/1``; changing a field's meaning moves to ``/2``.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator, Mapping
from dataclasses import dataclass, field
from typing import ClassVar, Literal, Protocol

NORMALIZED_SESSION_SCHEMA = "vg-session-jsonl/1"

TurnKind = Literal["human", "assistant_text", "tool_only", "notification", "meta", "compact_summary"]
Outcome = Literal["answered", "tool_error_unresolved", "interrupted", "open"]


@dataclass(frozen=True)
class SourceRecord:
    """One raw input unit, read by composition and passed in as text.

    ``source_path`` is the posix path relative to the folder the caller copied or read the session
    from, for example ``<session_id>.jsonl`` or ``<session_id>/subagents/agent-<id>.jsonl``.
    For ``.jsonl`` files ``text`` is one line and ``line_no`` counts from 1. For a subagent
    ``.meta.json`` file ``text`` is the whole file and ``line_no`` is 1.
    """

    source_path: str
    line_no: int
    text: str


@dataclass(frozen=True)
class SessionTitle:
    """A title the agent generated, not one a person wrote. ``source`` names the raw record kind."""

    text: str
    source: str


@dataclass(frozen=True)
class Action:
    tool: str
    call_id: str
    target: str | None
    ok: bool | None  # None while the tool result is not in the source yet
    error_head: str | None


@dataclass(frozen=True)
class SessionLine:
    kind: ClassVar[str] = "session"

    session_id: str
    agent: str
    agent_version: str | None
    adapter: str
    project: str | None
    cwd: str | None
    git_branch: str | None
    git_commit: str | None
    parent_session_id: str | None
    title: SessionTitle | None
    started_at: str | None
    ended_at: str | None
    source_paths: tuple[str, ...]
    source_sha256: str


@dataclass(frozen=True)
class ExchangeLine:
    kind: ClassVar[str] = "exchange"

    exchange_id: str
    seq: int
    agent_scope: str
    subagent_type: str | None
    parent_tool_use_id: str | None
    started_at: str | None
    ended_at: str | None
    closed: bool
    prompt_source: str | None
    tools: Mapping[str, int]
    files_touched: tuple[str, ...]
    commands: tuple[str, ...]
    errors: int
    outcome: Outcome


@dataclass(frozen=True)
class TurnLine:
    kind: ClassVar[str] = "turn"

    turn_id: str
    parent_id: str | None
    exchange_id: str
    role: Literal["user", "assistant"]
    turn_kind: TurnKind
    at: str | None
    agent_id: str | None
    sidechain: bool
    text: str
    actions: tuple[Action, ...]


NormalizedLine = SessionLine | ExchangeLine | TurnLine


@dataclass(frozen=True)
class NormalizedSession:
    """Normalized lines plus what the adapter skipped, for the export report (spec §6)."""

    lines: tuple[NormalizedLine, ...]
    invalid_lines: int = 0
    unknown_record_types: Mapping[str, int] = field(default_factory=dict)


class SessionAdapter(Protocol):
    agent: str
    version: str

    def normalize(self, records: Iterable[SourceRecord]) -> Iterator[NormalizedLine]: ...
