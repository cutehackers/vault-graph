"""Immutable public contracts for bounded combined project evidence."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from hashlib import sha256
from typing import Literal

from vault_graph.project_context.project_binding import ProjectBinding

PROJECT_CONTEXT_SCHEMA_VERSION = "project-context-v1"
DEFAULT_PROJECT_CONTEXT_DEPTH = 2
DEFAULT_PROJECT_CONTEXT_LIMIT = 20
DEFAULT_PROJECT_CONTEXT_TOKENS = 4000
MIN_PROJECT_CONTEXT_TOKENS = 512
MAX_PROJECT_CONTEXT_DEPTH = 8
MAX_PROJECT_CONTEXT_LIMIT = 100
MAX_PROJECT_CONTEXT_TOKENS = 16000
MAX_COMPACT_CONTEXT_STRING_CHARS = 96

ProjectFreshness = Literal["fresh", "stale", "syncing", "partial", "unavailable", "unknown"]
ProjectAuthorityKind = Literal["code", "vault"]
ProjectRelationStatus = Literal[
    "stated",
    "inferred",
    "ambiguous",
    "unresolved",
    "not_applicable",
    "contested",
    "deprecated",
]


@dataclass(frozen=True)
class ProjectContextRequest:
    task: str
    project_path: str | None = None
    repository_id: str | None = None
    max_tokens: int = DEFAULT_PROJECT_CONTEXT_TOKENS
    depth: int = DEFAULT_PROJECT_CONTEXT_DEPTH
    limit: int = DEFAULT_PROJECT_CONTEXT_LIMIT

    def __post_init__(self) -> None:
        _require_non_empty(self.task, "task")
        if self.project_path is not None:
            _require_non_empty(self.project_path, "project_path")
        if self.repository_id is not None:
            _require_non_empty(self.repository_id, "repository_id")
        _require_bounded(self.max_tokens, "max_tokens", MIN_PROJECT_CONTEXT_TOKENS, MAX_PROJECT_CONTEXT_TOKENS)
        _require_bounded(self.depth, "depth", 0, MAX_PROJECT_CONTEXT_DEPTH)
        _require_bounded(self.limit, "limit", 1, MAX_PROJECT_CONTEXT_LIMIT)


@dataclass(frozen=True)
class ProjectEvidence:
    """A compact evidence reference; it deliberately contains no source body."""

    evidence_id: str
    authority: ProjectAuthorityKind
    title: str
    summary: str
    relationship_status: ProjectRelationStatus
    revision: str | None
    freshness: ProjectFreshness
    source_uri: str | None = None
    repository_id: str | None = None
    vault_id: str | None = None
    relative_path: str | None = None
    start_line: int | None = None
    end_line: int | None = None
    reasons: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _require_non_empty(self.evidence_id, "evidence_id")
        _require_non_empty(self.title, "title")
        if self.authority not in {"code", "vault"}:
            raise ValueError("unsupported evidence authority")
        if self.relationship_status not in {
            "stated",
            "inferred",
            "ambiguous",
            "unresolved",
            "not_applicable",
            "contested",
            "deprecated",
        }:
            raise ValueError("unsupported relationship_status")
        _require_freshness(self.freshness)
        if self.authority == "code" and not self.repository_id:
            raise ValueError("code evidence requires repository_id")
        if self.authority == "vault" and not self.vault_id:
            raise ValueError("vault evidence requires vault_id")
        if not isinstance(self.reasons, tuple):
            raise ValueError("reasons must be an immutable tuple")
        if self.start_line is not None and self.start_line <= 0:
            raise ValueError("start_line must be positive")
        if self.end_line is not None and self.end_line <= 0:
            raise ValueError("end_line must be positive")
        if self.start_line is not None and self.end_line is not None and self.end_line < self.start_line:
            raise ValueError("line range is invalid")


@dataclass(frozen=True)
class ProjectAuthorityFreshness:
    authority: ProjectAuthorityKind
    authority_id: str
    state: ProjectFreshness
    revision: str | None = None
    warnings: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _require_non_empty(self.authority_id, "authority_id")
        _require_freshness(self.state)
        if not isinstance(self.warnings, tuple):
            raise ValueError("warnings must be an immutable tuple")


@dataclass(frozen=True)
class ProjectEvidenceRelation:
    """An explicit, inspectable link between separate authority records."""

    code_evidence_id: str
    vault_evidence_id: str
    status: ProjectRelationStatus
    reason: str

    def __post_init__(self) -> None:
        _require_non_empty(self.code_evidence_id, "code_evidence_id")
        _require_non_empty(self.vault_evidence_id, "vault_evidence_id")
        _require_non_empty(self.reason, "reason")
        if self.status not in {
            "stated",
            "inferred",
            "ambiguous",
            "unresolved",
            "not_applicable",
            "contested",
            "deprecated",
        }:
            raise ValueError("unsupported relationship_status")


@dataclass(frozen=True)
class ProjectContextWarning:
    code: str
    message: str
    freshness: ProjectFreshness = "unknown"
    authority_id: str | None = None
    recovery_hint: str | None = None

    def __post_init__(self) -> None:
        _require_non_empty(self.code, "code")
        _require_non_empty(self.message, "message")
        _require_freshness(self.freshness)


@dataclass(frozen=True)
class ProjectContextBudget:
    max_tokens: int
    used_tokens: int = 0
    omitted_evidence: int = 0

    def __post_init__(self) -> None:
        _require_bounded(self.max_tokens, "max_tokens", 1, MAX_PROJECT_CONTEXT_TOKENS)
        if self.used_tokens < 0 or self.used_tokens > self.max_tokens:
            raise ValueError("used_tokens must stay within max_tokens")
        if self.omitted_evidence < 0:
            raise ValueError("omitted_evidence must not be negative")


@dataclass(frozen=True)
class ProjectContext:
    task: str
    repository_id: str
    binding: ProjectBinding
    freshness: ProjectFreshness
    code_evidence: tuple[ProjectEvidence, ...]
    vault_evidence: tuple[ProjectEvidence, ...]
    relations: tuple[ProjectEvidenceRelation, ...]
    authority_freshness: tuple[ProjectAuthorityFreshness, ...]
    warnings: tuple[ProjectContextWarning, ...]
    budget: ProjectContextBudget
    impact_evidence: tuple[ProjectEvidence, ...] = ()
    test_evidence: tuple[ProjectEvidence, ...] = ()
    schema_version: str = PROJECT_CONTEXT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        _require_non_empty(self.task, "task")
        _require_non_empty(self.repository_id, "repository_id")
        if self.binding.repository_id != self.repository_id:
            raise ValueError("binding repository_id must match context repository_id")
        _require_freshness(self.freshness)
        for field_name in (
            "code_evidence",
            "impact_evidence",
            "test_evidence",
            "vault_evidence",
            "relations",
            "authority_freshness",
            "warnings",
        ):
            if not isinstance(getattr(self, field_name), tuple):
                raise ValueError(f"{field_name} must be an immutable tuple")
        if self.schema_version != PROJECT_CONTEXT_SCHEMA_VERSION:
            raise ValueError("schema_version must match current schema")


def combine_freshness(states: tuple[ProjectFreshness, ...]) -> ProjectFreshness:
    """Return the most severe authority freshness in a deterministic order."""

    if not states:
        return "unknown"
    for state in ("unavailable", "partial", "syncing", "unknown", "stale", "fresh"):
        if state in states:
            return state
    raise ValueError("unsupported freshness state")


def estimate_project_context_tokens(context: ProjectContext) -> int:
    """Estimate compact JSON output tokens from every field emitted by the DTO.

    Project bindings and authority revisions are user-controlled identifiers and
    may be arbitrarily long. The wire contract uses a deterministic abbreviated
    representation for oversized strings, retaining a prefix and digest so the
    estimate cannot fail merely because metadata is verbose. Every DTO field is
    still traversed; only oversized scalar values are compacted.
    """

    serialized = json.dumps(
        _compact_for_output(asdict(context)), sort_keys=True, separators=(",", ":"), ensure_ascii=True
    )
    return max(1, (len(serialized) + 3) // 4)


def _compact_for_output(value: object) -> object:
    if isinstance(value, str):
        if len(value) <= MAX_COMPACT_CONTEXT_STRING_CHARS:
            return value
        digest = sha256(value.encode("utf-8")).hexdigest()[:16]
        prefix_length = MAX_COMPACT_CONTEXT_STRING_CHARS - len(digest) - 1
        return f"{value[:prefix_length]}~{digest}"
    if isinstance(value, dict):
        return {key: _compact_for_output(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return tuple(_compact_for_output(item) for item in value)
    if isinstance(value, list):
        return [_compact_for_output(item) for item in value]
    return value


def _require_non_empty(value: str, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} is required")


def _require_bounded(value: int, field_name: str, minimum: int, maximum: int) -> None:
    if not isinstance(value, int) or value < minimum or value > maximum:
        raise ValueError(f"{field_name} must be between {minimum} and {maximum}")


def _require_freshness(value: str) -> None:
    if value not in {"fresh", "stale", "syncing", "partial", "unavailable", "unknown"}:
        raise ValueError("unsupported freshness")


__all__ = [
    "DEFAULT_PROJECT_CONTEXT_DEPTH",
    "DEFAULT_PROJECT_CONTEXT_LIMIT",
    "DEFAULT_PROJECT_CONTEXT_TOKENS",
    "MAX_PROJECT_CONTEXT_DEPTH",
    "MAX_PROJECT_CONTEXT_LIMIT",
    "MAX_PROJECT_CONTEXT_TOKENS",
    "MIN_PROJECT_CONTEXT_TOKENS",
    "PROJECT_CONTEXT_SCHEMA_VERSION",
    "ProjectAuthorityFreshness",
    "ProjectContext",
    "ProjectContextBudget",
    "ProjectContextRequest",
    "ProjectContextWarning",
    "ProjectEvidenceRelation",
    "ProjectEvidence",
    "ProjectFreshness",
    "ProjectRelationStatus",
    "combine_freshness",
    "estimate_project_context_tokens",
]
