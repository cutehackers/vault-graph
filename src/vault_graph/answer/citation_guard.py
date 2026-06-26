from __future__ import annotations

from dataclasses import replace

from vault_graph.answer.answer_response import AnswerResponse
from vault_graph.errors import AnswerError

_USABLE_STATUSES = {"supported", "inferred", "partial", "contested", "stale", "deprecated"}


class CitationGuard:
    def validate(self, response: AnswerResponse) -> AnswerResponse:
        evidence_ids = _unique(tuple(evidence.evidence_id for evidence in response.evidence), "evidence_id")
        _unique(tuple(claim.claim_id for claim in response.claims), "claim_id")
        for claim in response.claims:
            if claim.status in _USABLE_STATUSES and not claim.evidence_ids:
                raise AnswerError("claim evidence is required for cited claim statuses")
            for evidence_id in claim.evidence_ids:
                if evidence_id not in evidence_ids:
                    raise AnswerError(f"unknown evidence_id for claim: {evidence_id}")

        usable_claims = tuple(claim for claim in response.claims if claim.status in _USABLE_STATUSES)
        if not usable_claims:
            return replace(response, answer_status="insufficient_evidence")
        if response.answer_status == "supported" and any(warning.severity == "error" for warning in response.warnings):
            return replace(response, answer_status="partial")
        return response


def _unique(values: tuple[str, ...], field_name: str) -> set[str]:
    seen: set[str] = set()
    for value in values:
        if value in seen:
            raise AnswerError(f"duplicate {field_name}: {value}")
        seen.add(value)
    return seen
