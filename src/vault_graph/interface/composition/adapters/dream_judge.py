"""Port of the dream judge, its input and answer shapes, and the per-action answer check (spec 2026-11-19 D2, D3).

A dream run hands the judge a batch of ``DreamItem`` (one session exchange each, with what the user typed and
the pages it may be compared with) and the ``DreamPage`` texts those items name. The judge answers one
``DreamJudgment`` per item. The worker (`dream_worker.py`) checks every judgment in code before anything is sent
to a Vault, so an adapter only has to return what the model said.

Actions:

- ``none``: nothing to keep.
- ``remember``: a new page (`title`, `kind`, `summary`, `body`, optional `memory_kind`).
- ``update_memory``: text to add to a shown page (`path`, `addition`).
- ``supersede_claim``: replace one claim row of a shown page (`path`, `claim`, `new_claim`).
- ``retire_memory``: a shown page is no longer true (`path`, `reason`). Only `verify` items allow it (D3).

Every action except ``none`` carries `quote`, the user's own words. ``PROMPT_VERSION`` changes whenever the
prompt or these rules change in a way that could change an answer: the worker then judges earlier ``none``
answers again.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

from vault_graph.operation.memory.memory_requests import MEMORY_KINDS

PROMPT_VERSION = "dream-1"

DREAM_ACTIONS: tuple[str, ...] = ("none", "remember", "update_memory", "supersede_claim", "retire_memory")
EXCHANGE_ACTIONS: tuple[str, ...] = ("none", "remember", "update_memory", "supersede_claim")
VERIFY_ACTIONS: tuple[str, ...] = ("none", "supersede_claim", "retire_memory")
# A dream run never writes the project brief (kind `project`): it is injected into every session (C6).
DREAM_REMEMBER_KINDS: tuple[str, ...] = ("decision", "system")

_REQUIRED_FIELDS: dict[str, tuple[str, ...]] = {
    "remember": ("title", "kind", "summary", "body"),
    "update_memory": ("path", "addition"),
    "supersede_claim": ("path", "claim", "new_claim"),
    "retire_memory": ("path", "reason"),
}
_ONE_LINE_FIELDS = ("title", "summary", "path", "claim", "new_claim", "reason")


@dataclass(frozen=True)
class DreamPage:
    """One Vault page shown to the judge. ``changeable`` is False for a page a dream run may not change."""

    path: str
    title: str
    text: str
    status: str | None = None
    changeable: bool = True


@dataclass(frozen=True)
class DreamItem:
    """One thing to judge: a session exchange, what the user typed in it, and the pages to compare it with."""

    key: str
    date: str
    user_text: str
    exchange_text: str
    pages: tuple[str, ...] = ()
    actions: tuple[str, ...] = EXCHANGE_ACTIONS


@dataclass(frozen=True)
class DreamJudgment:
    key: str
    action: str
    quote: str = ""
    path: str = ""
    title: str = ""
    kind: str = ""
    memory_kind: str = ""
    summary: str = ""
    body: str = ""
    addition: str = ""
    claim: str = ""
    new_claim: str = ""
    reason: str = ""


@dataclass(frozen=True)
class DreamAnswer:
    judgments: tuple[DreamJudgment, ...]
    cost_usd: float | None = None
    """What the model run cost, when the adapter knows it."""


class DreamJudgeUnavailable(Exception):
    """The judge could not run: the command is missing, failed or ran out of time."""


class DreamOutputInvalid(Exception):
    """The judge answered, but not in the agreed shape."""


class DreamJudge(Protocol):
    model: str

    def judge(self, items: Sequence[DreamItem], pages: Sequence[DreamPage]) -> DreamAnswer:
        """One judgment per item at most. Judgments for keys not in ``items`` are left out."""
        ...


def judgment_problem(judgment: DreamJudgment, item: DreamItem) -> str | None:
    """Why a judgment that is not ``none`` cannot be used, or None. Looks only at the fields."""
    action = judgment.action
    if action not in item.actions:
        return f"action {action} is not allowed for this item"
    if action == "none":
        return None
    if not judgment.quote.strip():
        return "quote is empty"
    for field in _REQUIRED_FIELDS[action]:
        if not getattr(judgment, field).strip():
            return f"{field} is empty"
    for field in _ONE_LINE_FIELDS:
        value = getattr(judgment, field).strip()
        if "\n" in value or "\r" in value:
            return f"{field} has a line break"
    if action == "remember":
        if judgment.kind not in DREAM_REMEMBER_KINDS:
            return f"kind must be one of {', '.join(DREAM_REMEMBER_KINDS)}"
        if judgment.memory_kind and judgment.memory_kind not in MEMORY_KINDS:
            return f"memory_kind must be one of {', '.join(MEMORY_KINDS)}"
    elif judgment.path not in item.pages:
        return f"path {judgment.path} is not a page shown for this item"
    if action == "supersede_claim" and ("|" in judgment.claim or "|" in judgment.new_claim):
        return "claim and new_claim are table cells and cannot hold '|'"
    return None


__all__ = [
    "DREAM_ACTIONS",
    "DREAM_REMEMBER_KINDS",
    "EXCHANGE_ACTIONS",
    "PROMPT_VERSION",
    "VERIFY_ACTIONS",
    "DreamAnswer",
    "DreamItem",
    "DreamJudge",
    "DreamJudgeUnavailable",
    "DreamJudgment",
    "DreamOutputInvalid",
    "DreamPage",
    "judgment_problem",
]
