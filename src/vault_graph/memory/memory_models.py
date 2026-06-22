from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Literal

from vault_graph.errors import MemoryProjectionError
from vault_graph.ingestion.vault_catalog import QueryScope

MemoryItemKind = Literal[
    "current_state",
    "decision",
    "open_question",
    "constraint",
    "next_priority",
    "stale_area",
]
MemoryClaimStatus = Literal["stated", "metadata_derived", "heading_candidate"]
MemoryWarningSeverity = Literal["info", "warning", "error"]
MemoryFreshness = Literal["fresh", "stale", "unavailable", "unknown"]
MemoryDocumentResourceKind = Literal["document", "page", "source", "decision", "issue"]
MEMORY_DOCUMENT_RESOURCE_KINDS = ("document", "page", "source", "decision", "issue")


@dataclass(frozen=True)
class MemoryEvidenceRef:
    vault_id: str
    document_id: str
    chunk_id: str
    path: str
    section: str | None
    anchor: str | None
    content_hash: str
    raw_sha256: str | None
    metadata_index_revision: str | None
    vault_revision: str | None

    def __post_init__(self) -> None:
        for field_name in ("vault_id", "document_id", "chunk_id", "path", "content_hash"):
            _require_non_empty_string(getattr(self, field_name), field_name)


@dataclass(frozen=True)
class MemoryWarning:
    code: str
    message: str
    severity: MemoryWarningSeverity
    affected_vault_ids: tuple[str, ...]
    recovery_hint: str | None = None

    def __post_init__(self) -> None:
        _require_non_empty_string(self.code, "code")
        _require_non_empty_string(self.message, "message")
        _require_one_of(self.severity, "severity", ("info", "warning", "error"))
        _require_tuple(self.affected_vault_ids, "affected_vault_ids")
        if not self.affected_vault_ids:
            raise MemoryProjectionError("affected_vault_ids must contain at least one vault_id")
        for vault_id in self.affected_vault_ids:
            _require_non_empty_string(vault_id, "affected_vault_ids")


@dataclass(frozen=True)
class MemoryBackendRevision:
    kind: str
    revision: str | None
    vault_id: str | None
    scope_key: str

    def __post_init__(self) -> None:
        _require_non_empty_string(self.kind, "kind")
        _require_non_empty_string(self.scope_key, "scope_key")


@dataclass(frozen=True)
class MemoryItem:
    item_id: str
    kind: MemoryItemKind
    claim_status: MemoryClaimStatus
    matched_signals: tuple[str, ...]
    document_resource_kinds: tuple[MemoryDocumentResourceKind, ...]
    title: str
    summary: str
    vault_id: str
    path: str
    status: str | None
    rank: int
    evidence: tuple[MemoryEvidenceRef, ...]
    warnings: tuple[MemoryWarning, ...]

    def __post_init__(self) -> None:
        for field_name in ("item_id", "title", "summary", "vault_id", "path"):
            _require_non_empty_string(getattr(self, field_name), field_name)
        _require_one_of(
            self.kind,
            "kind",
            ("current_state", "decision", "open_question", "constraint", "next_priority", "stale_area"),
        )
        _require_one_of(self.claim_status, "claim_status", ("stated", "metadata_derived", "heading_candidate"))
        _require_tuple(self.matched_signals, "matched_signals")
        for signal in self.matched_signals:
            _require_non_empty_string(signal, "matched_signals")
        _require_tuple(self.document_resource_kinds, "document_resource_kinds")
        if not self.document_resource_kinds:
            raise MemoryProjectionError("document_resource_kinds must contain at least document")
        for resource_kind in self.document_resource_kinds:
            _require_one_of(resource_kind, "document_resource_kinds", MEMORY_DOCUMENT_RESOURCE_KINDS)
        if "document" not in self.document_resource_kinds:
            raise MemoryProjectionError("document_resource_kinds must include document")
        _require_tuple(self.evidence, "evidence")
        if not self.evidence:
            raise MemoryProjectionError("MemoryItem.evidence must contain at least one evidence ref")
        for evidence in self.evidence:
            if not isinstance(evidence, MemoryEvidenceRef):
                raise MemoryProjectionError("evidence must contain MemoryEvidenceRef values")
        _require_tuple(self.warnings, "warnings")
        for warning in self.warnings:
            if not isinstance(warning, MemoryWarning):
                raise MemoryProjectionError("warnings must contain MemoryWarning values")
        if self.rank < 1:
            raise MemoryProjectionError("MemoryItem.rank must be positive")
        first = self.evidence[0]
        if self.vault_id != first.vault_id:
            raise MemoryProjectionError("MemoryItem.vault_id must match first evidence ref")
        if self.path != first.path:
            raise MemoryProjectionError("MemoryItem.path must match first evidence ref")


@dataclass(frozen=True)
class ProjectMemoryVault:
    vault_id: str
    display_name: str
    current_state: tuple[MemoryItem, ...]
    decisions: tuple[MemoryItem, ...]
    open_questions: tuple[MemoryItem, ...]
    constraints: tuple[MemoryItem, ...]
    next_priorities: tuple[MemoryItem, ...]
    stale_areas: tuple[MemoryItem, ...]
    warnings: tuple[MemoryWarning, ...]
    store_revisions: tuple[MemoryBackendRevision, ...]
    freshness: MemoryFreshness

    def __post_init__(self) -> None:
        _validate_memory_vault_groups(
            vault_id=self.vault_id,
            display_name=self.display_name,
            warnings=self.warnings,
            store_revisions=self.store_revisions,
            freshness=self.freshness,
            groups=(
                ("current_state", self.current_state),
                ("decisions", self.decisions),
                ("open_questions", self.open_questions),
                ("constraints", self.constraints),
                ("next_priorities", self.next_priorities),
                ("stale_areas", self.stale_areas),
            ),
        )


@dataclass(frozen=True)
class ProjectMemoryProjection:
    requested_scope: QueryScope
    actual_scopes: tuple[QueryScope, ...]
    vaults: tuple[ProjectMemoryVault, ...]
    warnings: tuple[MemoryWarning, ...]
    generated_at: str

    def __post_init__(self) -> None:
        _validate_projection(actual_scopes=self.actual_scopes, vaults=self.vaults, warnings=self.warnings)
        _require_non_empty_string(self.generated_at, "generated_at")


@dataclass(frozen=True)
class DecisionMemoryVault:
    vault_id: str
    display_name: str
    decisions: tuple[MemoryItem, ...]
    warnings: tuple[MemoryWarning, ...]
    store_revisions: tuple[MemoryBackendRevision, ...]
    freshness: MemoryFreshness

    def __post_init__(self) -> None:
        _validate_memory_vault_groups(
            vault_id=self.vault_id,
            display_name=self.display_name,
            warnings=self.warnings,
            store_revisions=self.store_revisions,
            freshness=self.freshness,
            groups=(("decisions", self.decisions),),
        )


@dataclass(frozen=True)
class DecisionMemoryProjection:
    requested_scope: QueryScope
    actual_scopes: tuple[QueryScope, ...]
    topic: str | None
    vaults: tuple[DecisionMemoryVault, ...]
    warnings: tuple[MemoryWarning, ...]
    generated_at: str

    def __post_init__(self) -> None:
        _validate_projection(actual_scopes=self.actual_scopes, vaults=self.vaults, warnings=self.warnings)
        _require_non_empty_string(self.generated_at, "generated_at")


@dataclass(frozen=True)
class OpenQuestionsVault:
    vault_id: str
    display_name: str
    questions: tuple[MemoryItem, ...]
    warnings: tuple[MemoryWarning, ...]
    store_revisions: tuple[MemoryBackendRevision, ...]
    freshness: MemoryFreshness

    def __post_init__(self) -> None:
        _validate_memory_vault_groups(
            vault_id=self.vault_id,
            display_name=self.display_name,
            warnings=self.warnings,
            store_revisions=self.store_revisions,
            freshness=self.freshness,
            groups=(("questions", self.questions),),
        )


@dataclass(frozen=True)
class OpenQuestionsProjection:
    requested_scope: QueryScope
    actual_scopes: tuple[QueryScope, ...]
    vaults: tuple[OpenQuestionsVault, ...]
    warnings: tuple[MemoryWarning, ...]
    generated_at: str

    def __post_init__(self) -> None:
        _validate_projection(actual_scopes=self.actual_scopes, vaults=self.vaults, warnings=self.warnings)
        _require_non_empty_string(self.generated_at, "generated_at")


def stable_memory_item_id(
    *,
    kind: MemoryItemKind,
    vault_id: str,
    document_id: str,
    chunk_id: str,
    title: str,
    status: str | None,
    claim_status: MemoryClaimStatus,
) -> str:
    payload = {
        "kind": kind,
        "vault_id": vault_id,
        "document_id": document_id,
        "chunk_id": chunk_id,
        "title": " ".join(title.casefold().split()),
        "status": " ".join((status or "").casefold().split()) or None,
        "claim_status": claim_status,
    }
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
    return f"memory:{kind}:{digest[:24]}"


def _validate_memory_vault_groups(
    *,
    vault_id: str,
    display_name: str,
    warnings: tuple[MemoryWarning, ...],
    store_revisions: tuple[MemoryBackendRevision, ...],
    freshness: MemoryFreshness,
    groups: tuple[tuple[str, tuple[MemoryItem, ...]], ...],
) -> None:
    _require_non_empty_string(vault_id, "vault_id")
    _require_non_empty_string(display_name, "display_name")
    for field_name, group in groups:
        _require_tuple(group, field_name)
    _require_tuple(warnings, "warnings")
    _require_tuple(store_revisions, "store_revisions")
    _require_one_of(freshness, "freshness", ("fresh", "stale", "unavailable", "unknown"))


def _validate_projection(*, actual_scopes: object, vaults: object, warnings: object) -> None:
    _require_tuple(actual_scopes, "actual_scopes")
    _require_tuple(vaults, "vaults")
    _require_tuple(warnings, "warnings")


def _require_non_empty_string(value: object, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise MemoryProjectionError(f"{field_name} must be a non-empty string")


def _require_tuple(value: object, field_name: str) -> None:
    if not isinstance(value, tuple):
        raise MemoryProjectionError(f"{field_name} must be a tuple")


def _require_one_of(value: str, field_name: str, allowed: tuple[str, ...]) -> None:
    if value not in allowed:
        raise MemoryProjectionError(f"{field_name} must be one of: {', '.join(allowed)}")
