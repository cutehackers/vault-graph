from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

from vault_graph.answer.answer_response import (
    AnswerEvidence,
    AnswerMode,
    AnswerReasoningStep,
    AnswerWarning,
)
from vault_graph.errors import AnswerError
from vault_graph.ingestion.vault_catalog import QueryScope


@dataclass(frozen=True)
class AnswerRequest:
    question: str
    requested_scope: QueryScope
    mode: AnswerMode = "evidence-first"
    include_graph: bool = False
    include_cross_vault: bool = False
    retrieval_limit: int = 10
    max_evidence_tokens: int = 8000

    def __post_init__(self) -> None:
        if not self.question.strip():
            raise AnswerError("question is required")
        if self.mode != "evidence-first":
            raise AnswerError(f"unsupported answer mode: {self.mode}")
        if not 1 <= self.retrieval_limit <= 50:
            raise AnswerError("retrieval_limit must be between 1 and 50")
        if not 1000 <= self.max_evidence_tokens <= 24000:
            raise AnswerError("max_evidence_tokens must be between 1000 and 24000")
        if self.include_cross_vault and not self.include_graph:
            raise AnswerError("include_cross_vault requires include_graph")
        if self.include_cross_vault and len(self.requested_scope.vault_ids) <= 1:
            raise AnswerError("include_cross_vault requires more than one vault_id")
        if self.include_cross_vault != self.requested_scope.include_cross_vault:
            raise AnswerError("requested_scope.include_cross_vault must match include_cross_vault")


@dataclass(frozen=True)
class EvidencePlanStep:
    step_id: str
    kind: str
    query: str
    required: bool
    include_graph: bool = False
    include_cross_vault: bool = False
    limit: int = 10

    def __post_init__(self) -> None:
        for field_name in ("step_id", "kind", "query"):
            if not str(getattr(self, field_name)).strip():
                raise AnswerError(f"{field_name} is required")
        if self.limit <= 0:
            raise AnswerError("plan step limit must be positive")


@dataclass(frozen=True)
class AnswerPlan:
    request: AnswerRequest
    steps: tuple[EvidencePlanStep, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.steps, tuple):
            raise AnswerError("steps must be an immutable tuple")
        if not self.steps:
            raise AnswerError("answer plan requires at least one step")


@dataclass(frozen=True)
class PlannedEvidence:
    plan: AnswerPlan
    actual_scopes: tuple[QueryScope, ...]
    evidence: tuple[AnswerEvidence, ...]
    reasoning_trace: tuple[AnswerReasoningStep, ...]
    warnings: tuple[AnswerWarning, ...]
    dropped_evidence_count: int = 0

    def __post_init__(self) -> None:
        for field_name in ("actual_scopes", "evidence", "reasoning_trace", "warnings"):
            if not isinstance(getattr(self, field_name), tuple):
                raise AnswerError(f"{field_name} must be an immutable tuple")
        if not self.actual_scopes:
            raise AnswerError("actual_scopes is required")
        if self.dropped_evidence_count < 0:
            raise AnswerError("dropped_evidence_count must not be negative")


def answer_id_for(
    *,
    question: str,
    mode: AnswerMode,
    requested_scope: QueryScope,
    evidence_ids: tuple[str, ...],
    generated_at: str,
) -> str:
    payload = {
        "question": " ".join(question.casefold().split()),
        "mode": mode,
        "requested_scope": {
            "vault_ids": list(requested_scope.vault_ids),
            "content_scopes": list(requested_scope.content_scopes),
            "include_cross_vault": requested_scope.include_cross_vault,
        },
        "evidence_ids": list(evidence_ids),
        "generated_at": generated_at,
    }
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
    return f"answer:{digest[:24]}"
