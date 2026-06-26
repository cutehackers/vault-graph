from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from vault_graph.errors import AnswerError
from vault_graph.ingestion.vault_catalog import QueryScope

AnswerMode = Literal["evidence-first"]
AnswerStatus = Literal["supported", "partial", "insufficient_evidence"]
AnswerClaimStatus = Literal[
    "supported",
    "inferred",
    "partial",
    "unsupported",
    "missing",
    "contested",
    "stale",
    "deprecated",
]
AnswerWarningSeverity = Literal["info", "warning", "error"]
AnswerEvidenceSourceKind = Literal[
    "search_result",
    "graph_related",
    "decision_trace",
    "context_pack",
    "project_memory",
    "open_question",
    "recent_change",
]

_EVIDENCE_REQUIRED_CLAIM_STATUSES = {
    "supported",
    "inferred",
    "partial",
    "contested",
    "stale",
    "deprecated",
}
_USABLE_CLAIM_STATUSES = _EVIDENCE_REQUIRED_CLAIM_STATUSES


@dataclass(frozen=True)
class AnswerSignal:
    kind: str
    rank: int
    score: float
    backend: str
    index_revision: str
    explanation: str = ""

    def __post_init__(self) -> None:
        _require_non_empty(self.kind, "signal kind")
        _require_non_empty(self.backend, "signal backend")
        _require_non_empty(self.index_revision, "signal index_revision")
        if self.rank <= 0:
            raise AnswerError("signal rank must be positive")


@dataclass(frozen=True)
class AnswerStoreRevision:
    kind: str
    revision: str
    scope_key: str
    vault_id: str | None = None

    def __post_init__(self) -> None:
        _require_non_empty(self.kind, "store revision kind")
        _require_non_empty(self.revision, "store revision")
        _require_non_empty(self.scope_key, "store revision scope_key")


@dataclass(frozen=True)
class AnswerEvidence:
    evidence_id: str
    source_kind: AnswerEvidenceSourceKind
    result_id: str
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
    excerpt: str
    retrieval_reason: str
    relationship_status: str | None
    signals: tuple[AnswerSignal, ...]
    store_revisions: tuple[AnswerStoreRevision, ...]

    def __post_init__(self) -> None:
        for field_name in (
            "evidence_id",
            "result_id",
            "vault_id",
            "document_id",
            "chunk_id",
            "path",
            "content_hash",
            "retrieval_reason",
        ):
            _require_non_empty(getattr(self, field_name), field_name)
        _require_tuple(self.signals, "signals")
        _require_tuple(self.store_revisions, "store_revisions")


@dataclass(frozen=True)
class AnswerWarning:
    code: str
    message: str
    severity: AnswerWarningSeverity
    affected_vault_ids: tuple[str, ...]
    recovery_hint: str | None = None
    evidence_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _require_non_empty(self.code, "warning code")
        _require_non_empty(self.message, "warning message")
        _require_tuple(self.affected_vault_ids, "affected_vault_ids")
        if not self.affected_vault_ids:
            raise AnswerError("affected_vault_ids is required")
        _require_tuple(self.evidence_ids, "warning evidence_ids")


@dataclass(frozen=True)
class AnswerClaim:
    claim_id: str
    text: str
    status: AnswerClaimStatus
    evidence_ids: tuple[str, ...]
    warnings: tuple[AnswerWarning, ...]

    def __post_init__(self) -> None:
        _require_non_empty(self.claim_id, "claim_id")
        _require_non_empty(self.text, "claim text")
        _require_tuple(self.evidence_ids, "claim evidence_ids")
        _require_tuple(self.warnings, "claim warnings")
        if self.status in _EVIDENCE_REQUIRED_CLAIM_STATUSES and not self.evidence_ids:
            raise AnswerError("claim evidence is required for cited claim statuses")


@dataclass(frozen=True)
class AnswerReasoningStep:
    step_id: str
    kind: str
    service: str
    status: str
    query: str
    result_count: int
    kept_evidence_ids: tuple[str, ...]
    dropped_count: int
    warning_codes: tuple[str, ...]

    def __post_init__(self) -> None:
        for field_name in ("step_id", "kind", "service", "status", "query"):
            _require_non_empty(getattr(self, field_name), field_name)
        if self.result_count < 0:
            raise AnswerError("result_count must not be negative")
        if self.dropped_count < 0:
            raise AnswerError("dropped_count must not be negative")
        _require_tuple(self.kept_evidence_ids, "kept_evidence_ids")
        _require_tuple(self.warning_codes, "warning_codes")


@dataclass(frozen=True)
class AnswerDraft:
    answer: str
    answer_status: AnswerStatus
    claims: tuple[AnswerClaim, ...]
    warnings: tuple[AnswerWarning, ...]
    suggested_follow_up: str | None

    def __post_init__(self) -> None:
        _require_non_empty(self.answer, "answer")
        _require_tuple(self.claims, "claims")
        _require_tuple(self.warnings, "warnings")


@dataclass(frozen=True)
class AnswerResponse:
    answer_id: str
    question: str
    requested_scope: QueryScope
    actual_scopes: tuple[QueryScope, ...]
    answer: str
    answer_status: AnswerStatus
    claims: tuple[AnswerClaim, ...]
    evidence: tuple[AnswerEvidence, ...]
    reasoning_trace: tuple[AnswerReasoningStep, ...]
    warnings: tuple[AnswerWarning, ...]
    suggested_follow_up: str | None
    generated_at: str

    def __post_init__(self) -> None:
        _require_non_empty(self.answer_id, "answer_id")
        _require_non_empty(self.question, "question")
        _require_non_empty(self.answer, "answer")
        _require_non_empty(self.generated_at, "generated_at")
        _require_tuple(self.actual_scopes, "actual_scopes")
        if not self.actual_scopes:
            raise AnswerError("actual_scopes is required")
        _require_tuple(self.claims, "claims")
        _require_tuple(self.evidence, "evidence")
        _require_tuple(self.reasoning_trace, "reasoning_trace")
        _require_tuple(self.warnings, "warnings")
        evidence_ids = _unique_ids(tuple(item.evidence_id for item in self.evidence), "evidence_id")
        _unique_ids(tuple(claim.claim_id for claim in self.claims), "claim_id")
        for claim in self.claims:
            for evidence_id in claim.evidence_ids:
                if evidence_id not in evidence_ids:
                    raise AnswerError(f"unknown evidence_id for claim: {evidence_id}")
        if self.answer_status == "supported":
            if not any(claim.status == "supported" for claim in self.claims):
                raise AnswerError("supported answer requires at least one supported claim")


def _require_non_empty(value: str, field_name: str) -> None:
    if not value.strip():
        raise AnswerError(f"{field_name} is required")


def _require_tuple(value: object, field_name: str) -> None:
    if not isinstance(value, tuple):
        raise AnswerError(f"{field_name} must be an immutable tuple")


def _unique_ids(values: tuple[str, ...], field_name: str) -> set[str]:
    seen: set[str] = set()
    for value in values:
        _require_non_empty(value, field_name)
        if value in seen:
            raise AnswerError(f"duplicate {field_name}: {value}")
        seen.add(value)
    return seen
