from __future__ import annotations

import pytest

from vault_graph.answer.answer_response import (
    AnswerClaim,
    AnswerEvidence,
    AnswerReasoningStep,
    AnswerResponse,
    AnswerSignal,
    AnswerStoreRevision,
    AnswerWarning,
)
from vault_graph.errors import AnswerError
from vault_graph.ingestion.vault_catalog import QueryScope


def make_evidence(evidence_id: str = "ev_1_abcd") -> AnswerEvidence:
    return AnswerEvidence(
        evidence_id=evidence_id,
        source_kind="search_result",
        result_id="result-1",
        vault_id="main",
        document_id="doc-1",
        chunk_id="chunk-1",
        path="wiki/page.md",
        section="Section",
        anchor="section",
        content_hash="chunk-hash",
        raw_sha256="raw-hash",
        metadata_index_revision="metadata-1",
        vault_revision="vault-1",
        excerpt="GraphRAG evidence",
        retrieval_reason="keyword",
        relationship_status="not_applicable",
        signals=(AnswerSignal(kind="keyword", rank=1, score=0.9, backend="sqlite", index_revision="keyword-1"),),
        store_revisions=(AnswerStoreRevision(kind="metadata", revision="metadata-1", scope_key="main:wiki"),),
    )


def make_response(
    *,
    claims: tuple[AnswerClaim, ...] | None = None,
    evidence: tuple[AnswerEvidence, ...] | None = None,
    warnings: tuple[AnswerWarning, ...] = (),
    answer_status: str = "supported",
) -> AnswerResponse:
    evidence_items = (make_evidence(),) if evidence is None else evidence
    claim_items = (
        AnswerClaim(
            claim_id="claim-1",
            text="GraphRAG evidence",
            status="supported",
            evidence_ids=("ev_1_abcd",),
            warnings=(),
        ),
    ) if claims is None else claims
    return AnswerResponse(
        answer_id="answer:123",
        question="Why GraphRAG?",
        requested_scope=QueryScope(vault_ids=("main",), content_scopes=("wiki",)),
        actual_scopes=(QueryScope(vault_ids=("main",), content_scopes=("wiki",)),),
        answer="Vault Graph found indexed evidence that answers the question.",
        answer_status=answer_status,  # type: ignore[arg-type]
        claims=claim_items,
        evidence=evidence_items,
        reasoning_trace=(
            AnswerReasoningStep(
                step_id="search:1",
                kind="search",
                service="RetrievalService.search",
                status="ok",
                query="Why GraphRAG?",
                result_count=1,
                kept_evidence_ids=("ev_1_abcd",),
                dropped_count=0,
                warning_codes=(),
            ),
        ),
        warnings=warnings,
        suggested_follow_up=None,
        generated_at="2026-06-26T00:00:00+00:00",
    )


def test_answer_response_rejects_supported_claim_without_evidence() -> None:
    with pytest.raises(AnswerError, match="claim evidence is required"):
        make_response(
            claims=(
                AnswerClaim(
                    claim_id="claim-1",
                    text="Unsupported supported claim",
                    status="supported",
                    evidence_ids=(),
                    warnings=(),
                ),
            )
        )


def test_answer_response_rejects_unknown_claim_evidence_id() -> None:
    with pytest.raises(AnswerError, match="unknown evidence_id"):
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


def test_answer_response_requires_non_empty_actual_scopes() -> None:
    with pytest.raises(AnswerError, match="actual_scopes is required"):
        AnswerResponse(
            answer_id="answer:123",
            question="Why GraphRAG?",
            requested_scope=QueryScope(vault_ids=("main",), content_scopes=("wiki",)),
            actual_scopes=(),
            answer="answer",
            answer_status="insufficient_evidence",
            claims=(),
            evidence=(),
            reasoning_trace=(),
            warnings=(),
            suggested_follow_up=None,
            generated_at="2026-06-26T00:00:00+00:00",
        )


def test_supported_answer_requires_supported_claim() -> None:
    with pytest.raises(AnswerError, match="supported answer requires"):
        make_response(
            answer_status="supported",
            claims=(
                AnswerClaim(
                    claim_id="claim-1",
                    text="Partial claim",
                    status="partial",
                    evidence_ids=("ev_1_abcd",),
                    warnings=(),
                ),
            ),
        )


def test_insufficient_evidence_allows_empty_evidence() -> None:
    response = make_response(
        answer_status="insufficient_evidence",
        evidence=(),
        claims=(
            AnswerClaim(
                claim_id="claim-1",
                text="No indexed evidence directly answers: Why GraphRAG?",
                status="missing",
                evidence_ids=(),
                warnings=(),
            ),
        ),
        warnings=(
            AnswerWarning(
                code="insufficient_evidence",
                message="No indexed evidence matched the question.",
                severity="warning",
                affected_vault_ids=("main",),
                recovery_hint="Run vg index for the selected Vault, then retry the question.",
            ),
        ),
    )

    assert response.answer_status == "insufficient_evidence"
    assert response.evidence == ()
