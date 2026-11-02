"""Request and result shapes for Vault memory writes, and the request field checks (spec 2026-11-02 V1, V3).

The checks look only at the fields. Which Vault and whether the page exists are decided later.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Literal

Basis = Literal["stated", "inferred"]
MemoryWriteStatus = Literal["published", "proposed", "rejected", "vault_required", "error"]

BASES: tuple[str, ...] = ("stated", "inferred")
REMEMBER_KINDS: tuple[str, ...] = ("decision", "system")
# Vault 계약2 tools/wiki/lib/memory_fields.py ALLOWED_MEMORY_KINDS.
MEMORY_KINDS: tuple[str, ...] = ("rule", "correction", "decision", "preference")

_PATH_SEGMENT = re.compile(r"^[^/\\]+$")


@dataclass(frozen=True)
class RememberRequest:
    title: str
    kind: str
    body: str
    evidence: tuple[str, ...]
    basis: Basis
    cwd: str | None = None
    vault: str | None = None
    pin: bool = False
    memory_kind: str | None = None


@dataclass(frozen=True)
class UpdateRequest:
    """Replace the body of an existing page. ``None`` fields keep the page's current value."""

    path: str
    body: str
    evidence: tuple[str, ...]
    basis: Basis
    vault: str | None = None
    cwd: str | None = None
    title: str | None = None
    pin: bool | None = None
    memory_kind: str | None = None


@dataclass(frozen=True)
class RetireRequest:
    path: str
    reason: str
    basis: Basis
    vault: str | None = None
    cwd: str | None = None
    replaced_by: str | None = None


@dataclass(frozen=True)
class VaultCandidate:
    name: str
    role: str


@dataclass(frozen=True)
class MemoryWriteResult:
    status: MemoryWriteStatus
    vault: str | None
    written_paths: tuple[str, ...]
    messages: tuple[str, ...]
    vault_role: str | None = None
    review_path: str | None = None
    candidates: tuple[VaultCandidate, ...] = ()


def validate_remember(request: RememberRequest) -> tuple[str, ...]:
    problems: list[str] = []
    if not _non_empty(request.title):
        problems.append("title must be a non-empty string.")
    if not _non_empty(request.body):
        problems.append("body must be a non-empty string.")
    if request.kind not in REMEMBER_KINDS:
        problems.append(f"kind must be one of {', '.join(REMEMBER_KINDS)}.")
    if not _is_evidence(request.evidence):
        problems.append("evidence must list at least one non-empty string.")
    problems.extend(_basis_problems(request.basis))
    if not isinstance(request.pin, bool):
        problems.append("pin must be true or false.")
    problems.extend(_memory_kind_problems(request.memory_kind))
    return tuple(problems)


def validate_update(request: UpdateRequest) -> tuple[str, ...]:
    problems: list[str] = list(_page_path_problems(request.path, "path"))
    if not _non_empty(request.body):
        problems.append("body must be a non-empty string.")
    if not _is_evidence(request.evidence):
        problems.append("evidence must list at least one non-empty string.")
    problems.extend(_basis_problems(request.basis))
    if request.title is not None and not _non_empty(request.title):
        problems.append("title must be a non-empty string when given.")
    if request.pin is not None and not isinstance(request.pin, bool):
        problems.append("pin must be true or false when given.")
    problems.extend(_memory_kind_problems(request.memory_kind))
    return tuple(problems)


def validate_retire(request: RetireRequest) -> tuple[str, ...]:
    problems: list[str] = list(_page_path_problems(request.path, "path"))
    if not _non_empty(request.reason) or "\n" in request.reason or "\r" in request.reason:
        problems.append("reason must be a non-empty single-line string.")
    problems.extend(_basis_problems(request.basis))
    if request.replaced_by is not None:
        problems.extend(_page_path_problems(request.replaced_by, "replaced_by"))
        if request.replaced_by == request.path:
            problems.append("replaced_by must name a different page than path.")
    return tuple(problems)


def _basis_problems(basis: object) -> tuple[str, ...]:
    if basis in BASES:
        return ()
    return (f"basis must be one of {', '.join(BASES)}.",)


def _memory_kind_problems(memory_kind: object) -> tuple[str, ...]:
    if memory_kind is None or memory_kind in MEMORY_KINDS:
        return ()
    return (f"memory_kind must be one of {', '.join(MEMORY_KINDS)} when given.",)


def _page_path_problems(path: object, field: str) -> tuple[str, ...]:
    """A Vault-relative page path such as ``wiki/decisions/a.md``: no absolute path, no ``..``."""
    message = f"{field} must be a Vault-relative page path such as wiki/decisions/example.md."
    if not isinstance(path, str):
        return (message,)
    parts = path.split("/")
    if (
        len(parts) < 2
        or parts[0] != "wiki"
        or not all(_PATH_SEGMENT.match(part) and part not in {".", ".."} for part in parts)
        or PurePosixPath(path).suffix != ".md"
    ):
        return (message,)
    return ()


def _non_empty(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _is_evidence(value: object) -> bool:
    if isinstance(value, str) or not isinstance(value, Sequence):
        return False
    return bool(value) and all(_non_empty(item) for item in value)


__all__ = [
    "BASES",
    "MEMORY_KINDS",
    "REMEMBER_KINDS",
    "Basis",
    "MemoryWriteResult",
    "MemoryWriteStatus",
    "RememberRequest",
    "RetireRequest",
    "UpdateRequest",
    "VaultCandidate",
    "validate_remember",
    "validate_retire",
    "validate_update",
]
