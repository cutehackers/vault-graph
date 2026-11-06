"""Cleanup backlog line of recall block D (spec 2026-11-05 §4.4.6, §4.4.4, A-26).

Session start shows how much cleanup waits, in one line, and never cleans up itself: cleanup is
``curate_memory``, started by the user. The counts come through a ``BacklogCounter`` port that
counts the way ``list_memory_candidates`` does (L1 notes and session exchanges only). The count
runs on a worker thread with a time limit. Over the limit, or on any error, the line is left out
and recall gets one warning line. The thread is a daemon, so a slow count never holds the hook.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

BACKLOG_BUDGET_S = 1.5


@dataclass(frozen=True)
class MemoryBacklog:
    """Cleanup candidates of the ``cwd`` project. ``warnings`` are one line each.

    ``l1_notes`` is None when the L1 folder is missing or unreadable: the line then leaves the L1 part out.
    """

    l1_notes: int | None
    session_exchanges: int
    warnings: tuple[str, ...] = ()


class BacklogCounter(Protocol):
    def count(self, cwd: Path) -> MemoryBacklog: ...


def backlog_line(backlog: MemoryBacklog) -> str | None:
    """The block D line, or None when nothing waits."""
    if not backlog.l1_notes and not backlog.session_exchanges:
        return None
    sessions = f"근거로 쓰이지 않은 세션 교환 {backlog.session_exchanges}개"
    counts = sessions if backlog.l1_notes is None else f"L1 노트 {backlog.l1_notes}개, {sessions}"
    return f'- 정리 대기: {counts}. 정리하려면 "기억 정리해"라고 말하세요.'


def backlog_lines(counter: BacklogCounter | None, cwd: Path, warnings: list[str], *, budget_s: float) -> list[str]:
    """Zero or one block D line. A count over ``budget_s`` or a failed count adds one warning instead."""
    if counter is None:
        return []
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
        return []
    result = outcome[0]
    if isinstance(result, BaseException):
        warnings.append(_one_line(f"Cleanup backlog line was left out: {result}"))
        return []
    warnings.extend(_one_line(f"Cleanup backlog: {warning}") for warning in result.warnings)
    line = backlog_line(result)
    return [line] if line is not None else []


def _one_line(text: str) -> str:
    return " ".join(text.split())


__all__ = ["BACKLOG_BUDGET_S", "BacklogCounter", "MemoryBacklog", "backlog_line", "backlog_lines"]
