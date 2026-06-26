from __future__ import annotations

import pytest

from tests.test_answer_response_contract import make_evidence, make_response
from vault_graph.answer.answer_response import AnswerClaim, AnswerWarning
from vault_graph.answer.citation_guard import CitationGuard
from vault_graph.errors import AnswerError


def test_guard_rejects_unknown_evidence_id() -> None:
    with pytest.raises(AnswerError, match="unknown evidence_id"):
        CitationGuard().validate(
            make_response(
                claims=(
                    AnswerClaim(
                        claim_id="claim-1",
                        text="Unknown evidence",
                        status="supported",
                        evidence_ids=("missing",),
                        warnings=(),
                    ),
                )
            )
        )


def test_guard_rejects_supported_claim_without_evidence() -> None:
    with pytest.raises(AnswerError, match="claim evidence is required"):
        CitationGuard().validate(
            make_response(
                claims=(
                    AnswerClaim(
                        claim_id="claim-1",
                        text="No evidence",
                        status="supported",
                        evidence_ids=(),
                        warnings=(),
                    ),
                )
            )
        )


def test_guard_downgrades_supported_response_with_error_warning_to_partial() -> None:
    response = make_response(
        warnings=(
            AnswerWarning(
                code="graph_unavailable",
                message="Graph projection is unavailable.",
                severity="error",
                affected_vault_ids=("main",),
                recovery_hint=None,
            ),
        )
    )

    guarded = CitationGuard().validate(response)

    assert guarded.answer_status == "partial"


def test_guard_downgrades_no_usable_evidence_to_insufficient_evidence() -> None:
    response = make_response(
        answer_status="partial",
        evidence=(make_evidence(),),
        claims=(
            AnswerClaim(
                claim_id="claim-1",
                text="Missing",
                status="missing",
                evidence_ids=(),
                warnings=(),
            ),
        ),
    )

    guarded = CitationGuard().validate(response)

    assert guarded.answer_status == "insufficient_evidence"


def test_guard_preserves_missing_claim_as_labeled_output() -> None:
    response = make_response(
        answer_status="insufficient_evidence",
        evidence=(),
        claims=(
            AnswerClaim(
                claim_id="claim-1",
                text="Missing",
                status="missing",
                evidence_ids=(),
                warnings=(),
            ),
        ),
    )

    guarded = CitationGuard().validate(response)

    assert guarded.claims[0].status == "missing"
