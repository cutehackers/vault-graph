from __future__ import annotations

from typing import Any

__all__ = [
    "AnswerClaim",
    "AnswerDraft",
    "AnswerEvidence",
    "AnswerPlan",
    "AnswerReasoningStep",
    "AnswerRequest",
    "AnswerResponse",
    "AnswerSignal",
    "AnswerStoreRevision",
    "AnswerWarning",
    "CitationGuard",
    "DefaultAnswerRenderer",
    "EvidencePlanner",
    "EvidencePlanStep",
    "ExtractiveAnswerComposer",
    "PlannedEvidence",
    "answer_id_for",
]


def __getattr__(name: str) -> Any:
    if name in {
        "AnswerClaim",
        "AnswerDraft",
        "AnswerEvidence",
        "AnswerReasoningStep",
        "AnswerResponse",
        "AnswerSignal",
        "AnswerStoreRevision",
        "AnswerWarning",
    }:
        from vault_graph.answer.answer_response import (
            AnswerClaim,
            AnswerDraft,
            AnswerEvidence,
            AnswerReasoningStep,
            AnswerResponse,
            AnswerSignal,
            AnswerStoreRevision,
            AnswerWarning,
        )

        return {
            "AnswerClaim": AnswerClaim,
            "AnswerDraft": AnswerDraft,
            "AnswerEvidence": AnswerEvidence,
            "AnswerReasoningStep": AnswerReasoningStep,
            "AnswerResponse": AnswerResponse,
            "AnswerSignal": AnswerSignal,
            "AnswerStoreRevision": AnswerStoreRevision,
            "AnswerWarning": AnswerWarning,
        }[name]
    if name in {"AnswerPlan", "AnswerRequest", "EvidencePlanStep", "PlannedEvidence", "answer_id_for"}:
        from vault_graph.answer.answer_plan import (
            AnswerPlan,
            AnswerRequest,
            EvidencePlanStep,
            PlannedEvidence,
            answer_id_for,
        )

        return {
            "AnswerPlan": AnswerPlan,
            "AnswerRequest": AnswerRequest,
            "EvidencePlanStep": EvidencePlanStep,
            "PlannedEvidence": PlannedEvidence,
            "answer_id_for": answer_id_for,
        }[name]
    if name == "CitationGuard":
        from vault_graph.answer.citation_guard import CitationGuard

        return CitationGuard
    if name == "DefaultAnswerRenderer":
        from vault_graph.answer.answer_renderer import DefaultAnswerRenderer

        return DefaultAnswerRenderer
    if name == "EvidencePlanner":
        from vault_graph.answer.evidence_planner import EvidencePlanner

        return EvidencePlanner
    if name == "ExtractiveAnswerComposer":
        from vault_graph.answer.answer_composer import ExtractiveAnswerComposer

        return ExtractiveAnswerComposer
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
