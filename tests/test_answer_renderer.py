from __future__ import annotations

import json
from dataclasses import replace

import pytest

from tests.test_answer_response_contract import make_response
from vault_graph.answer.answer_renderer import DefaultAnswerRenderer, answer_response_to_dict
from vault_graph.errors import AnswerError


def test_render_json_round_trips_answer_response_shape() -> None:
    rendered = DefaultAnswerRenderer().render_json(make_response())

    payload = json.loads(rendered)

    assert payload["answer_status"] == "supported"
    assert payload["claims"][0]["claim_id"] == "claim-1"
    assert payload["evidence"][0]["vault_id"] == "main"


def test_render_text_includes_status_claims_evidence_warnings_and_reasoning() -> None:
    rendered = DefaultAnswerRenderer().render_text(make_response())

    assert "status: supported" in rendered
    assert "claims:" in rendered
    assert "evidence:" in rendered
    assert "warnings:" in rendered
    assert "reasoning:" in rendered


def test_render_text_labels_missing_claims() -> None:
    response = make_response(answer_status="insufficient_evidence", evidence=(), claims=())

    rendered = DefaultAnswerRenderer().render_text(response)

    assert "status: insufficient_evidence" in rendered


def test_render_text_does_not_include_absolute_vault_paths() -> None:
    rendered = DefaultAnswerRenderer().render_text(make_response())

    assert "/Users/" not in rendered


def test_render_json_rejects_non_finite_float_scores() -> None:
    evidence = make_response().evidence[0]
    response = replace(
        make_response(),
        evidence=(replace(evidence, signals=(replace(evidence.signals[0], score=float("nan")),)),),
    )

    with pytest.raises(AnswerError, match="non-finite"):
        answer_response_to_dict(response)
