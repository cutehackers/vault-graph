from __future__ import annotations

from typing import Protocol

from vault_graph.answer.answer_plan import AnswerRequest, PlannedEvidence
from vault_graph.answer.answer_response import AnswerClaim, AnswerClaimStatus, AnswerDraft, AnswerStatus


class AnswerComposer(Protocol):
    def compose(self, request: AnswerRequest, evidence: PlannedEvidence) -> AnswerDraft: ...


class ExtractiveAnswerComposer:
    def compose(self, request: AnswerRequest, evidence: PlannedEvidence) -> AnswerDraft:
        if not evidence.evidence:
            return AnswerDraft(
                answer="Vault Graph does not have enough indexed evidence to answer this question.",
                answer_status="insufficient_evidence",
                claims=(
                    AnswerClaim(
                        claim_id="claim-1",
                        text=f"No indexed evidence directly answers: {request.question.strip()}",
                        status="missing",
                        evidence_ids=(),
                        warnings=(),
                    ),
                ),
                warnings=evidence.warnings,
                suggested_follow_up="Run vg index for the selected Vault, then retry the question.",
            )

        claims: list[AnswerClaim] = []
        for index, item in enumerate(evidence.evidence[:5], start=1):
            status = _claim_status_for_evidence(item.relationship_status)
            prefix = "Evidence" if status == "supported" else "Vault Graph found partial evidence"
            claims.append(
                AnswerClaim(
                    claim_id=f"claim-{index}",
                    text=f"{prefix} from {item.path} indicates: {item.excerpt}",
                    status=status,
                    evidence_ids=(item.evidence_id,),
                    warnings=(),
                )
            )

        if any(warning.severity in {"warning", "error"} for warning in evidence.warnings):
            answer_status: AnswerStatus = "partial"
            answer = "Vault Graph found partial evidence; review the labeled claims and warnings."
        elif any(claim.status == "supported" for claim in claims):
            answer_status = "supported"
            answer = "Vault Graph found indexed evidence that answers the question."
        else:
            answer_status = "partial"
            answer = "Vault Graph found partial evidence; review the labeled claims and warnings."

        return AnswerDraft(
            answer=answer,
            answer_status=answer_status,
            claims=tuple(claims),
            warnings=evidence.warnings,
            suggested_follow_up=(
                "Review the cited Vault evidence and update durable knowledge through the Vault workflow if needed."
                if answer_status == "partial"
                else None
            ),
        )


def _claim_status_for_evidence(relationship_status: str | None) -> AnswerClaimStatus:
    if relationship_status == "contested":
        return "contested"
    if relationship_status == "deprecated":
        return "deprecated"
    if relationship_status == "inferred":
        return "inferred"
    return "supported"
