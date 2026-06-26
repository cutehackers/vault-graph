from __future__ import annotations

import pytest

from vault_graph.answer.answer_plan import AnswerRequest, answer_id_for
from vault_graph.errors import AnswerError
from vault_graph.ingestion.vault_catalog import QueryScope


def scope(*, vault_ids: tuple[str, ...] = ("main",), include_cross_vault: bool = False) -> QueryScope:
    return QueryScope(vault_ids=vault_ids, content_scopes=("wiki",), include_cross_vault=include_cross_vault)


def test_answer_request_rejects_empty_question() -> None:
    with pytest.raises(AnswerError, match="question is required"):
        AnswerRequest(question="   ", requested_scope=scope())


def test_answer_request_rejects_unsupported_mode() -> None:
    with pytest.raises(AnswerError, match="unsupported answer mode"):
        AnswerRequest(question="Why?", requested_scope=scope(), mode="creative")  # type: ignore[arg-type]


def test_answer_request_caps_retrieval_limit() -> None:
    with pytest.raises(AnswerError, match="retrieval_limit"):
        AnswerRequest(question="Why?", requested_scope=scope(), retrieval_limit=51)


def test_answer_request_caps_evidence_budget() -> None:
    with pytest.raises(AnswerError, match="max_evidence_tokens"):
        AnswerRequest(question="Why?", requested_scope=scope(), max_evidence_tokens=999)


def test_cross_vault_requires_graph_and_multi_vault_scope() -> None:
    with pytest.raises(AnswerError, match="include_cross_vault requires include_graph"):
        AnswerRequest(
            question="Why?",
            requested_scope=scope(vault_ids=("main", "work"), include_cross_vault=True),
            include_cross_vault=True,
        )

    with pytest.raises(AnswerError, match="include_cross_vault requires more than one vault_id"):
        AnswerRequest(
            question="Why?",
            requested_scope=scope(include_cross_vault=True),
            include_graph=True,
            include_cross_vault=True,
        )

    with pytest.raises(AnswerError, match="requested_scope.include_cross_vault must match"):
        AnswerRequest(
            question="Why?",
            requested_scope=scope(vault_ids=("main", "work")),
            include_graph=True,
            include_cross_vault=True,
        )


def test_answer_id_is_runtime_scoped_and_stable_for_same_inputs() -> None:
    first = answer_id_for(
        question="Why GraphRAG?",
        mode="evidence-first",
        requested_scope=scope(),
        evidence_ids=("ev-1",),
        generated_at="2026-06-26T00:00:00+00:00",
    )
    second = answer_id_for(
        question=" Why   GraphRAG? ",
        mode="evidence-first",
        requested_scope=scope(),
        evidence_ids=("ev-1",),
        generated_at="2026-06-26T00:00:00+00:00",
    )

    assert first == second
    assert first.startswith("answer:")
    assert len(first.removeprefix("answer:")) == 24
