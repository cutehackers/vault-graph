from __future__ import annotations

from dataclasses import replace

from tests.test_answer_response_contract import make_evidence
from vault_graph.answer.answer_composer import ExtractiveAnswerComposer
from vault_graph.answer.answer_plan import AnswerPlan, AnswerRequest, EvidencePlanStep, PlannedEvidence
from vault_graph.answer.answer_response import AnswerWarning
from vault_graph.ingestion.vault_catalog import QueryScope


def make_planned_evidence(
    *,
    evidence_count: int = 1,
    warnings: tuple[AnswerWarning, ...] = (),
) -> PlannedEvidence:
    request = AnswerRequest(
        question="Why GraphRAG?",
        requested_scope=QueryScope(vault_ids=("main",), content_scopes=("wiki",)),
    )
    plan = AnswerPlan(
        request=request,
        steps=(
            EvidencePlanStep(
                step_id="search:1",
                kind="search",
                query="Why GraphRAG?",
                required=True,
            ),
        ),
    )
    evidence = tuple(
        replace(
            make_evidence(f"ev_{index}_abcd"),
            excerpt=f"Evidence excerpt {index}",
            relationship_status="contested" if index == 1 and evidence_count > 1 else "not_applicable",
        )
        for index in range(1, evidence_count + 1)
    )
    return PlannedEvidence(
        plan=plan,
        actual_scopes=(QueryScope(vault_ids=("main",), content_scopes=("wiki",)),),
        evidence=evidence,
        reasoning_trace=(),
        warnings=warnings,
    )


def test_composer_returns_supported_answer_from_search_evidence() -> None:
    request = make_planned_evidence().plan.request

    draft = ExtractiveAnswerComposer().compose(request, make_planned_evidence())

    assert draft.answer_status == "supported"
    assert draft.claims[0].status == "supported"
    assert draft.claims[0].evidence_ids == ("ev_1_abcd",)
    assert "Evidence excerpt 1" in draft.claims[0].text


def test_composer_returns_partial_answer_when_warnings_exist() -> None:
    warning = AnswerWarning(
        code="vector_unavailable",
        message="Vector unavailable.",
        severity="warning",
        affected_vault_ids=("main",),
    )
    planned = make_planned_evidence(warnings=(warning,))

    draft = ExtractiveAnswerComposer().compose(planned.plan.request, planned)

    assert draft.answer_status == "partial"
    assert draft.warnings == (warning,)


def test_composer_returns_insufficient_evidence_without_evidence() -> None:
    planned = make_planned_evidence(evidence_count=0)

    draft = ExtractiveAnswerComposer().compose(planned.plan.request, planned)

    assert draft.answer_status == "insufficient_evidence"
    assert draft.claims[0].status == "missing"
    assert draft.suggested_follow_up == "Run vg index for the selected Vault, then retry the question."


def test_composer_never_creates_claim_without_evidence_except_missing_or_unsupported() -> None:
    planned = make_planned_evidence(evidence_count=3)

    draft = ExtractiveAnswerComposer().compose(planned.plan.request, planned)

    assert all(claim.evidence_ids or claim.status in {"missing", "unsupported"} for claim in draft.claims)


def test_composer_marks_contested_relationships_visibly() -> None:
    planned = make_planned_evidence(evidence_count=2)

    draft = ExtractiveAnswerComposer().compose(planned.plan.request, planned)

    assert draft.claims[0].status == "contested"


def test_composer_limits_claim_count() -> None:
    planned = make_planned_evidence(evidence_count=8)

    draft = ExtractiveAnswerComposer().compose(planned.plan.request, planned)

    assert len(draft.claims) == 5
