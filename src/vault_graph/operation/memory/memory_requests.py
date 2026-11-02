"""Request and result shapes for Vault memory writes, and the request field check (spec 4.2.4, V1)."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

RememberStatus = Literal["published", "rejected", "error"]

REMEMBER_KINDS: tuple[str, ...] = ("decision", "system")


@dataclass(frozen=True)
class RememberRequest:
    title: str
    kind: str
    body: str
    evidence: tuple[str, ...]
    cwd: str | None = None
    vault: str | None = None


@dataclass(frozen=True)
class MemoryWriteResult:
    status: RememberStatus
    vault: str | None
    written_paths: tuple[str, ...]
    messages: tuple[str, ...]


def validate_request(request: RememberRequest) -> tuple[str, ...]:
    problems: list[str] = []
    if not _non_empty(request.title):
        problems.append("title must be a non-empty string.")
    if not _non_empty(request.body):
        problems.append("body must be a non-empty string.")
    if request.kind not in REMEMBER_KINDS:
        problems.append(f"kind must be one of {', '.join(REMEMBER_KINDS)}.")
    if not _is_evidence(request.evidence):
        problems.append("evidence must list at least one non-empty string.")
    return tuple(problems)


def _non_empty(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _is_evidence(value: object) -> bool:
    if isinstance(value, str) or not isinstance(value, Sequence):
        return False
    return bool(value) and all(_non_empty(item) for item in value)


__all__ = [
    "REMEMBER_KINDS",
    "MemoryWriteResult",
    "RememberRequest",
    "RememberStatus",
    "validate_request",
]
