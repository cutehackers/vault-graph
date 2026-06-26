from __future__ import annotations

from datetime import UTC, datetime

from tests.test_answer_composer import make_planned_evidence
from vault_graph.answer.answer_composer import ExtractiveAnswerComposer
from vault_graph.answer.answer_plan import AnswerPlan, AnswerRequest, PlannedEvidence
from vault_graph.answer.answer_response import AnswerDraft, AnswerResponse
from vault_graph.answer.citation_guard import CitationGuard
from vault_graph.app.answer_service import AnswerService
from vault_graph.ingestion.vault_catalog import QueryScope


class RecordingPlanner:
    def __init__(self, planned: PlannedEvidence) -> None:
        self.planned = planned
        self.plan_calls: list[AnswerRequest] = []
        self.gather_calls: list[AnswerPlan] = []

    def plan(self, request: AnswerRequest) -> AnswerPlan:
        self.plan_calls.append(request)
        return self.planned.plan

    def gather(self, plan: AnswerPlan) -> PlannedEvidence:
        self.gather_calls.append(plan)
        return self.planned


class RecordingComposer:
    def __init__(self, draft: AnswerDraft) -> None:
        self.draft = draft
        self.calls: list[tuple[AnswerRequest, PlannedEvidence]] = []

    def compose(self, request: AnswerRequest, evidence: PlannedEvidence) -> AnswerDraft:
        self.calls.append((request, evidence))
        return self.draft


class RecordingGuard(CitationGuard):
    def __init__(self) -> None:
        self.calls: list[AnswerResponse] = []

    def validate(self, response: AnswerResponse) -> AnswerResponse:
        self.calls.append(response)
        return super().validate(response)


def request() -> AnswerRequest:
    return AnswerRequest(
        question="Why GraphRAG?",
        requested_scope=QueryScope(vault_ids=("main",), content_scopes=("wiki",)),
    )


def fixed_clock() -> datetime:
    return datetime(2026, 6, 26, tzinfo=UTC)


def test_answer_service_calls_planner_composer_and_guard() -> None:
    planned = make_planned_evidence()
    draft = ExtractiveAnswerComposer().compose(planned.plan.request, planned)
    planner = RecordingPlanner(planned)
    composer = RecordingComposer(draft)
    guard = RecordingGuard()

    response = AnswerService(planner=planner, composer=composer, citation_guard=guard, clock=fixed_clock).ask(request())

    assert planner.plan_calls
    assert planner.gather_calls
    assert composer.calls
    assert guard.calls
    assert response.answer_status == "supported"


def test_answer_service_attaches_answer_id_and_generated_at() -> None:
    planned = make_planned_evidence()
    service = AnswerService(
        planner=RecordingPlanner(planned),
        composer=ExtractiveAnswerComposer(),
        citation_guard=CitationGuard(),
        clock=fixed_clock,
    )

    response = service.ask(request())

    assert response.answer_id.startswith("answer:")
    assert response.generated_at == "2026-06-26T00:00:00+00:00"


def test_answer_service_preserves_planned_evidence_and_trace() -> None:
    planned = make_planned_evidence()
    service = AnswerService(
        planner=RecordingPlanner(planned),
        composer=ExtractiveAnswerComposer(),
        citation_guard=CitationGuard(),
        clock=fixed_clock,
    )

    response = service.ask(request())

    assert response.evidence == planned.evidence
    assert response.actual_scopes == planned.actual_scopes


def test_answer_service_returns_insufficient_evidence_response() -> None:
    planned = make_planned_evidence(evidence_count=0)
    service = AnswerService(
        planner=RecordingPlanner(planned),
        composer=ExtractiveAnswerComposer(),
        citation_guard=CitationGuard(),
        clock=fixed_clock,
    )

    response = service.ask(request())

    assert response.answer_status == "insufficient_evidence"
    assert response.claims[0].status == "missing"
