"""Which `vault-session/v1` parts a v2 part covers, and exchange counts of normalized lines.

Spec 2026-11-25-v1-session-recapture D2, I2, F9. A v1 part is covered when one v2 part of the same Vault,
`agent` and `session_id` has an exchange time range (earliest `started` to latest `ended` of its
`<!-- vg:exchange ... -->` meta lines) that contains the v1 frontmatter range `first_turn_at` to
`last_turn_at`. The v2 frontmatter `last_turn_at` is the last turn in file order, not the latest time, so it
is not used. Two v2 parts are never joined to cover one v1 part. Times compare as instants, so `...00.000Z`
and `...00+00:00` are equal. A time without an offset is read as UTC.

Pure code: callers read the files and pass part heads, body lines or normalized lines in.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from urllib.parse import unquote

from vault_graph.operation.sessions.models import ExchangeLine, NormalizedLine, TurnLine

V1_SCHEMA = "vault-session/v1"
V2_SCHEMA = "vault-session/v2"

_META_RE = re.compile(r"^<!-- vg:exchange (?P<body>.*) -->$")


@dataclass(frozen=True)
class PartHead:
    """Frontmatter of one session part, plus the exchange meta time range for a v2 part.

    `path` is whatever the caller uses to name the file in reports. `exchange_started` and
    `exchange_ended` come from `exchange_time_range` over the v2 body and stay None for v1.
    """

    vault: str
    path: str
    schema: str
    agent: str | None
    session_id: str | None
    part: int | None
    first_turn_at: str | None
    last_turn_at: str | None
    first_exchange_id: str | None = None
    last_exchange_id: str | None = None
    exchange_started: str | None = None
    exchange_ended: str | None = None


@dataclass(frozen=True)
class V1Coverage:
    """v1 parts split three ways, each in input order.

    `unreadable` holds v1 parts without `session_id` or with a `first_turn_at` or `last_turn_at` that is
    missing or not a time (F9). Their coverage is unknown.
    """

    covered: tuple[PartHead, ...]
    uncovered: tuple[PartHead, ...]
    unreadable: tuple[PartHead, ...]


@dataclass(frozen=True)
class ExchangeSummary:
    """Exchanges with at least one turn line, and the first and last of them in exchange line order."""

    count: int
    first_exchange_id: str | None
    last_exchange_id: str | None


type _Key = tuple[str, str | None, str]
type _Range = tuple[datetime, datetime]


def uncovered_v1_parts(parts: Iterable[PartHead]) -> V1Coverage:
    """Split the v1 parts in `parts` into covered, uncovered and unreadable. Other schemas only cover."""
    heads = tuple(parts)
    v2_ranges: dict[_Key, list[_Range]] = {}
    for head in heads:
        if head.schema != V2_SCHEMA or not head.session_id:
            continue
        span = _range(head.exchange_started, head.exchange_ended)
        if span is not None:
            v2_ranges.setdefault((head.vault, head.agent, head.session_id), []).append(span)

    covered: list[PartHead] = []
    uncovered: list[PartHead] = []
    unreadable: list[PartHead] = []
    for head in heads:
        if head.schema != V1_SCHEMA:
            continue
        span = _range(head.first_turn_at, head.last_turn_at)
        if not head.session_id or span is None:
            unreadable.append(head)
            continue
        candidates = v2_ranges.get((head.vault, head.agent, head.session_id), [])
        if any(start <= span[0] and span[1] <= end for start, end in candidates):
            covered.append(head)
        else:
            uncovered.append(head)
    return V1Coverage(covered=tuple(covered), uncovered=tuple(uncovered), unreadable=tuple(unreadable))


def exchange_time_range(body_lines: Iterable[str]) -> tuple[str, str] | None:
    """Earliest `started` and latest `ended` over the `vg:exchange` meta lines of a v2 body, as written.

    The two may come from different meta lines. Values that are not times are skipped. None when no meta
    line has a readable `started` or none has a readable `ended`.
    """
    earliest: tuple[datetime, str] | None = None
    latest: tuple[datetime, str] | None = None
    for line in body_lines:
        match = _META_RE.match(line.rstrip("\r\n"))
        if match is None:
            continue
        fields = _meta_fields(match.group("body"))
        started = fields.get("started")
        ended = fields.get("ended")
        started_at = _instant(started)
        ended_at = _instant(ended)
        if started is not None and started_at is not None and (earliest is None or started_at < earliest[0]):
            earliest = (started_at, started)
        if ended is not None and ended_at is not None and (latest is None or ended_at > latest[0]):
            latest = (ended_at, ended)
    if earliest is None or latest is None:
        return None
    return earliest[1], latest[1]


def exchange_summary(lines: Iterable[NormalizedLine]) -> ExchangeSummary:
    """Count `vg-session-jsonl/1` exchanges that have a turn line, as the Vault tool's `exchange_count` does.

    The Vault tool skips exchanges without turns (spec X9), so they are not counted and are never first or last.
    """
    order: list[str] = []
    with_turns: set[str] = set()
    for line in lines:
        if isinstance(line, ExchangeLine):
            order.append(line.exchange_id)
        elif isinstance(line, TurnLine):
            with_turns.add(line.exchange_id)
    counted = [exchange_id for exchange_id in order if exchange_id in with_turns]
    if not counted:
        return ExchangeSummary(count=0, first_exchange_id=None, last_exchange_id=None)
    return ExchangeSummary(count=len(counted), first_exchange_id=counted[0], last_exchange_id=counted[-1])


def _meta_fields(body: str) -> dict[str, str]:
    fields: dict[str, str] = {}
    for token in body.split(" "):
        key, separator, value = token.partition("=")
        if separator and key and key not in fields:
            fields[key] = unquote(value)
    return fields


def _range(start: str | None, end: str | None) -> _Range | None:
    start_at = _instant(start)
    end_at = _instant(end)
    if start_at is None or end_at is None:
        return None
    return start_at, end_at


def _instant(value: str | None) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)
