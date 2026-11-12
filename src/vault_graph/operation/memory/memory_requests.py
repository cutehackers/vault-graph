"""Request and result shapes for Vault memory writes, and the request field checks (spec 2026-11-02 V1, V3).

The checks look only at the fields. Which Vault and whether the page exists are decided later.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import PurePath, PurePosixPath
from typing import Literal

Basis = Literal["stated", "inferred"]
MemoryWriteStatus = Literal["published", "proposed", "rejected", "vault_required", "error"]

BASES: tuple[str, ...] = ("stated", "inferred")
# ``project`` is the one brief of a project (spec 2026-11-05 §4.4.7). New values go at the end (docs/SPEC.md §5).
REMEMBER_KINDS: tuple[str, ...] = ("decision", "system", "project")
PROJECT_KIND = "project"
# A brief path is wiki/projects/<project id>.md. Same pattern as Vault tools/wiki/lib/schema.py _PROJECT_ID.
_PROJECT_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
BRIEF_NEEDS_PROJECT_MESSAGE = (
    "kind project writes the project brief, so it must be called from a project folder: "
    "cwd is not inside one project of vault-map.json."
)
# Vault 계약2 tools/wiki/lib/memory_fields.py ALLOWED_MEMORY_KINDS.
MEMORY_KINDS: tuple[str, ...] = ("rule", "correction", "decision", "preference")
# The memory kinds the Vault project summary lists as corrections when ``tags`` holds them
# (vault-builder tools/wiki/lib/maps.py PROJECT_CORRECTION_TAGS).
TAGGED_MEMORY_KINDS: tuple[str, ...] = ("correction", "rule")

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
    # The ``cwd`` project id the MCP write tool found, or None outside a project (spec 2026-11-05 §4.4.3).
    project_id: str | None = None
    # The cleanup candidate this write handles, recorded when the write is published or proposed (§4.4.4).
    candidate_key: str | None = None
    # Written by the calling agent, never made by vault-graph (spec 2026-11-11 §4.3.1). Without a summary
    # the page gets its title as the frontmatter ``summary`` the Vault requires.
    summary: str | None = None
    aliases: tuple[str, ...] = ()


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
    candidate_key: str | None = None
    summary: str | None = None
    # None keeps the page's aliases. A list replaces them, and an empty list removes them.
    aliases: tuple[str, ...] | None = None


@dataclass(frozen=True)
class RetireRequest:
    path: str
    reason: str
    basis: Basis
    vault: str | None = None
    cwd: str | None = None
    replaced_by: str | None = None
    candidate_key: str | None = None


@dataclass(frozen=True)
class SupersedeClaimRequest:
    """Replace one claim row of a claim page (spec 2026-11-05 §4.4.4, 결정43).

    ``claim`` is the current row text, ``new_claim`` and ``evidence`` are the cells of the new row.
    """

    path: str
    claim: str
    new_claim: str
    evidence: str
    basis: Basis
    vault: str | None = None
    cwd: str | None = None
    candidate_key: str | None = None


@dataclass(frozen=True)
class RestoreRequest:
    """Bring a retired, deprecated or superseded page back to ``status: active`` (spec 2026-11-05 §4.4.13-3)."""

    path: str
    reason: str
    basis: Basis
    vault: str | None = None
    cwd: str | None = None
    candidate_key: str | None = None


@dataclass(frozen=True)
class ImportRequest:
    """Keep a copy of one Claude Code auto-memory note with Vault ``import-source`` (spec 2026-11-05 §4.4.5).

    ``note`` is the absolute path of the note file. vault-graph only passes it to the Vault command.
    """

    note: str
    cwd: str | None = None
    vault: str | None = None
    candidate_key: str | None = None


@dataclass(frozen=True)
class VaultCandidate:
    name: str
    role: str


@dataclass(frozen=True)
class SimilarMemoryPage:
    """An existing page that looks like the one ``remember`` was asked to add (backlog MEMORY-01).

    ``status`` is the page frontmatter status, so a retired or deprecated page is shown as such.
    """

    vault_id: str
    path: str
    title: str
    status: str | None = None
    superseded_by: str | None = None
    retired_reason: str | None = None


@dataclass(frozen=True)
class MemoryWriteResult:
    status: MemoryWriteStatus
    vault: str | None
    written_paths: tuple[str, ...]
    messages: tuple[str, ...]
    vault_role: str | None = None
    review_path: str | None = None
    candidates: tuple[VaultCandidate, ...] = ()
    # Set by import_auto_memory: the Vault copy under raw/imports/ and its source page.
    raw_path: str | None = None
    source_page: str | None = None
    # Advice that does not change the status, such as a stated memory without a summary.
    warnings: tuple[str, ...] = ()
    # Set by remember: at most ``SIMILAR_PAGE_LIMIT`` existing pages like the new one. Never blocks the write.
    similar_pages: tuple[SimilarMemoryPage, ...] = ()


def validate_remember(request: RememberRequest) -> tuple[str, ...]:
    problems: list[str] = []
    if not _non_empty(request.title):
        problems.append("title must be a non-empty string.")
    if not _non_empty(request.body):
        problems.append("body must be a non-empty string.")
    if request.kind not in REMEMBER_KINDS:
        problems.append(f"kind must be one of {', '.join(REMEMBER_KINDS)}.")
    if request.kind == PROJECT_KIND:
        problems.extend(_brief_project_problems(request.project_id))
    if not _is_evidence(request.evidence):
        problems.append("evidence must list at least one non-empty string.")
    problems.extend(_basis_problems(request.basis))
    if not isinstance(request.pin, bool):
        problems.append("pin must be true or false.")
    problems.extend(_memory_kind_problems(request.memory_kind))
    problems.extend(_candidate_key_problems(request.candidate_key))
    problems.extend(_summary_problems(request.summary))
    problems.extend(_aliases_problems(request.aliases))
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
    problems.extend(_candidate_key_problems(request.candidate_key))
    problems.extend(_summary_problems(request.summary))
    if request.aliases is not None:
        problems.extend(_aliases_problems(request.aliases))
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
    problems.extend(_candidate_key_problems(request.candidate_key))
    return tuple(problems)


def validate_supersede_claim(request: SupersedeClaimRequest) -> tuple[str, ...]:
    """Each text becomes one cell of the Vault claim table, so none may hold ``|`` or a line break."""
    problems: list[str] = list(_page_path_problems(request.path, "path"))
    for field, value in (("claim", request.claim), ("new_claim", request.new_claim), ("evidence", request.evidence)):
        if not _is_cell(value):
            problems.append(f"{field} must be a non-empty single-line string without '|'.")
    if _is_cell(request.claim) and _is_cell(request.new_claim) and request.claim.strip() == request.new_claim.strip():
        problems.append("new_claim must differ from claim.")
    problems.extend(_basis_problems(request.basis))
    problems.extend(_candidate_key_problems(request.candidate_key))
    return tuple(problems)


def validate_restore(request: RestoreRequest) -> tuple[str, ...]:
    problems: list[str] = list(_page_path_problems(request.path, "path"))
    if not _is_single_line(request.reason):
        problems.append("reason must be a non-empty single-line string.")
    problems.extend(_basis_problems(request.basis))
    problems.extend(_candidate_key_problems(request.candidate_key))
    return tuple(problems)


def validate_import(request: ImportRequest) -> tuple[str, ...]:
    """The Vault command runs in the Vault folder, so a relative note path would point into the Vault."""
    problems: list[str] = []
    if not _is_single_line(request.note) or not PurePath(request.note.strip()).is_absolute():
        problems.append("note must be the absolute path of an auto-memory note file.")
    problems.extend(_candidate_key_problems(request.candidate_key))
    return tuple(problems)


def _brief_project_problems(project_id: str | None) -> tuple[str, ...]:
    """The brief path is built from the project id, so it must be one Vault project id (spec §4.4.7)."""
    if project_id is None:
        return (BRIEF_NEEDS_PROJECT_MESSAGE,)
    if not _PROJECT_ID.match(project_id):
        return (f"project id {project_id!r} cannot name a brief page: it must match {_PROJECT_ID.pattern}.",)
    return ()


def _candidate_key_problems(candidate_key: object) -> tuple[str, ...]:
    if candidate_key is None or _is_single_line(candidate_key):
        return ()
    return ("candidate_key must be a non-empty single-line string when given.",)


def _summary_problems(summary: object) -> tuple[str, ...]:
    """A frontmatter value is one line: the Vault renders it without escaping line breaks."""
    if summary is None or _is_single_line(summary):
        return ()
    return ("summary must be a non-empty single-line string when given.",)


def _aliases_problems(aliases: object) -> tuple[str, ...]:
    if (
        not isinstance(aliases, str)
        and isinstance(aliases, Sequence)
        and all(_is_single_line(alias) for alias in aliases)
    ):
        return ()
    return ("aliases must be a list of non-empty single-line strings.",)


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


def _is_single_line(value: object) -> bool:
    return _non_empty(value) and "\n" not in str(value) and "\r" not in str(value)


def _is_cell(value: object) -> bool:
    return _is_single_line(value) and "|" not in str(value)


def _is_evidence(value: object) -> bool:
    if isinstance(value, str) or not isinstance(value, Sequence):
        return False
    return bool(value) and all(_non_empty(item) for item in value)


__all__ = [
    "BASES",
    "BRIEF_NEEDS_PROJECT_MESSAGE",
    "MEMORY_KINDS",
    "PROJECT_KIND",
    "REMEMBER_KINDS",
    "TAGGED_MEMORY_KINDS",
    "Basis",
    "ImportRequest",
    "MemoryWriteResult",
    "MemoryWriteStatus",
    "RememberRequest",
    "RestoreRequest",
    "RetireRequest",
    "SimilarMemoryPage",
    "SupersedeClaimRequest",
    "UpdateRequest",
    "VaultCandidate",
    "validate_import",
    "validate_remember",
    "validate_restore",
    "validate_retire",
    "validate_supersede_claim",
    "validate_update",
]
