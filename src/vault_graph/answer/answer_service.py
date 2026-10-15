from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Protocol

from vault_graph.answer.answer_composer import AnswerComposer
from vault_graph.answer.answer_plan import AnswerPlan, AnswerRequest, PlannedEvidence, answer_id_for
from vault_graph.answer.answer_response import AnswerResponse
from vault_graph.answer.citation_guard import CitationGuard


class AnswerEvidencePlanner(Protocol):
    def plan(self, request: AnswerRequest) -> AnswerPlan: ...
    def gather(self, plan: AnswerPlan) -> PlannedEvidence: ...


class AnswerService:
    def __init__(
        self,
        *,
        planner: AnswerEvidencePlanner,
        composer: AnswerComposer,
        citation_guard: CitationGuard,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._planner = planner
        self._composer = composer
        self._citation_guard = citation_guard
        self._clock = clock or (lambda: datetime.now(tz=UTC))

    def ask(self, request: AnswerRequest) -> AnswerResponse:
        plan = self._planner.plan(request)
        planned_evidence = self._planner.gather(plan)
        draft = self._composer.compose(request, planned_evidence)
        generated_at = _utc_isoformat(self._clock())
        response = AnswerResponse(
            answer_id=answer_id_for(
                question=request.question,
                mode=request.mode,
                requested_scope=request.requested_scope,
                evidence_ids=tuple(evidence.evidence_id for evidence in planned_evidence.evidence),
                generated_at=generated_at,
            ),
            question=request.question.strip(),
            requested_scope=request.requested_scope,
            actual_scopes=planned_evidence.actual_scopes,
            answer=draft.answer,
            answer_status=draft.answer_status,
            claims=draft.claims,
            evidence=planned_evidence.evidence,
            reasoning_trace=planned_evidence.reasoning_trace,
            warnings=(*planned_evidence.warnings, *draft.warnings),
            suggested_follow_up=draft.suggested_follow_up,
            generated_at=generated_at,
        )
        return self._citation_guard.validate(response)


def _utc_isoformat(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).isoformat()
