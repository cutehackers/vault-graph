"""Cleanup backlog line of recall block D (spec 2026-11-05 §4.4.6, §4.4.4, A-26).

Session start shows how much cleanup waits, in one line, and never cleans up itself: cleanup is
``curate_memory``, started by the user. The counts come through a ``BacklogCounter`` port that
counts the way ``list_memory_candidates`` does (L1 notes and session exchanges only). The count
runs on a worker thread with a time limit. Over the limit, or on any error, the line is left out
and recall gets one warning line. The thread is a daemon, so a slow count never holds the hook.

The brief line (§4.4.7, A-35) comes from ``brief.project_brief_staleness`` over the documents recall
already read, so it needs no port and no time limit. vg only says the brief needs an update.

The backlog line also gives the median age of the waiting session exchanges (spec 2026-11-11 §4.3.3,
A-11). Over ``BACKLOG_ALERT_MEDIAN_DAYS`` the line says cleanup is needed now and recall prints it
first instead of in block D. It stays a notice: nothing here starts cleanup.
"""

from __future__ import annotations

import statistics
import threading
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from vault_graph.context.memory.brief import BriefStaleness

BACKLOG_BUDGET_S = 1.5
# Goal 7 of spec 2026-11-11 §2.1: the median age of waiting session exchanges stays at or under 7 days.
BACKLOG_ALERT_MEDIAN_DAYS = 7.0


@dataclass(frozen=True)
class MemoryBacklog:
    """Cleanup candidates of the ``cwd`` project. ``warnings`` are one line each.

    ``l1_notes`` is None when the L1 folder is missing or unreadable: the line then leaves the L1 part out.
    ``session_median_age_days`` is the median age of the waiting session exchanges, None when unknown.
    """

    l1_notes: int | None
    session_exchanges: int
    warnings: tuple[str, ...] = ()
    session_median_age_days: float | None = None


class BacklogCounter(Protocol):
    def count(self, cwd: Path) -> MemoryBacklog: ...


def median_age_days(started: Iterable[datetime], *, now: datetime) -> float | None:
    """Median age in days, one decimal, of exchanges started at ``started``. None when there are none."""
    ages = [(now - at).total_seconds() / 86400 for at in started]
    return round(statistics.median(ages), 1) if ages else None


def backlog_is_overdue(backlog: MemoryBacklog) -> bool:
    """True when session exchanges wait and their median age is over goal 7."""
    age = backlog.session_median_age_days
    return bool(backlog.session_exchanges) and age is not None and age > BACKLOG_ALERT_MEDIAN_DAYS


def backlog_line(backlog: MemoryBacklog) -> str | None:
    """The backlog line, or None when nothing waits. An overdue backlog says cleanup is needed now."""
    if not backlog.l1_notes and not backlog.session_exchanges:
        return None
    sessions = f"근거로 쓰이지 않은 세션 교환 {backlog.session_exchanges}개"
    age = backlog.session_median_age_days
    if backlog.session_exchanges and age is not None:
        sessions += f"(나이 중앙값 {age:g}일)"
    counts = sessions if backlog.l1_notes is None else f"L1 노트 {backlog.l1_notes}개, {sessions}"
    if backlog_is_overdue(backlog):
        return (
            f"- 정리 대기: {counts}. 나이 중앙값이 기준 {BACKLOG_ALERT_MEDIAN_DAYS:g}일을 넘었습니다. "
            '지금 정리가 필요합니다. "기억 정리해"라고 말하세요.'
        )
    return f'- 정리 대기: {counts}. 정리하려면 "기억 정리해"라고 말하세요.'


def brief_staleness_line(staleness: BriefStaleness) -> str | None:
    """The block D brief line, or None when the brief does not need an update."""
    if not staleness.stale:
        return None
    return f'- brief 갱신 필요: brief 이후 새 결정 {staleness.count}개. "기억 정리해"로 갱신하세요.'


def backlog_lines(
    counter: BacklogCounter | None, cwd: Path, warnings: list[str], *, budget_s: float
) -> tuple[list[str], list[str]]:
    """The backlog line as ``(top lines, block D lines)``: zero or one line in all.

    An overdue backlog puts the line in the top lines, which recall prints first. A count over
    ``budget_s`` or a failed count adds one warning instead.
    """
    if counter is None:
        return [], []
    outcome: list[MemoryBacklog | BaseException] = []

    def work() -> None:
        try:
            outcome.append(counter.count(cwd))
        except BaseException as exc:  # reported on the recall thread below
            outcome.append(exc)

    worker = threading.Thread(target=work, name="recall-backlog", daemon=True)
    worker.start()
    worker.join(budget_s)
    if not outcome:
        warnings.append(f"Cleanup backlog line was left out: the count passed its {budget_s:g} s time limit.")
        return [], []
    result = outcome[0]
    if isinstance(result, BaseException):
        warnings.append(_one_line(f"Cleanup backlog line was left out: {result}"))
        return [], []
    warnings.extend(_one_line(f"Cleanup backlog: {warning}") for warning in result.warnings)
    line = backlog_line(result)
    if line is None:
        return [], []
    return ([line], []) if backlog_is_overdue(result) else ([], [line])


def _one_line(text: str) -> str:
    return " ".join(text.split())


__all__ = [
    "BACKLOG_ALERT_MEDIAN_DAYS",
    "BACKLOG_BUDGET_S",
    "BacklogCounter",
    "MemoryBacklog",
    "backlog_is_overdue",
    "backlog_line",
    "backlog_lines",
    "brief_staleness_line",
    "median_age_days",
]
