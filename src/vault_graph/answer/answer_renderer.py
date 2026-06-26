from __future__ import annotations

import dataclasses
import json
import math
from pathlib import Path
from typing import Protocol

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
from vault_graph.errors import AnswerError
from vault_graph.ingestion.vault_catalog import QueryScope

_DTO_TYPES = {
    AnswerClaim,
    AnswerDraft,
    AnswerEvidence,
    AnswerReasoningStep,
    AnswerResponse,
    AnswerSignal,
    AnswerStoreRevision,
    AnswerWarning,
}


class AnswerRenderer(Protocol):
    def render_text(self, response: AnswerResponse) -> str: ...
    def render_json(self, response: AnswerResponse) -> str: ...


class DefaultAnswerRenderer:
    def render_text(self, response: AnswerResponse) -> str:
        lines = [
            f"status: {response.answer_status}",
            "answer:",
            response.answer,
            "claims:",
        ]
        for claim in response.claims:
            claim_evidence_ids = ",".join(claim.evidence_ids) if claim.evidence_ids else "none"
            lines.append(f"- {claim.claim_id} [{claim.status}] {claim.text} (evidence: {claim_evidence_ids})")
        lines.append("evidence:")
        for evidence in response.evidence:
            suffix = evidence.anchor or evidence.section
            path = f"{evidence.path}#{suffix}" if suffix else evidence.path
            lines.append(f"- {evidence.evidence_id} [{evidence.vault_id}] {path}")
        lines.append("warnings:")
        if response.warnings:
            for warning in response.warnings:
                lines.append(f"- {warning.code} [{warning.severity}] {warning.message}")
        else:
            lines.append("- none")
        lines.append("reasoning:")
        for step in response.reasoning_trace:
            kept_count = len(step.kept_evidence_ids)
            lines.append(f"- {step.step_id} {step.service} results={step.result_count} kept={kept_count}")
        if response.suggested_follow_up:
            lines.append("follow_up:")
            lines.append(response.suggested_follow_up)
        return "\n".join(lines) + "\n"

    def render_json(self, response: AnswerResponse) -> str:
        return (
            json.dumps(answer_response_to_dict(response), ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False)
            + "\n"
        )


def answer_response_to_dict(response: AnswerResponse) -> dict[str, object]:
    converted = _to_json_value(response)
    if not isinstance(converted, dict):
        raise AnswerError("answer response serialization produced a non-object")
    return converted


def _to_json_value(value: object) -> object:
    if isinstance(value, QueryScope):
        return {
            "vault_ids": list(value.vault_ids),
            "content_scopes": list(value.content_scopes),
            "include_cross_vault": value.include_cross_vault,
        }
    if dataclasses.is_dataclass(value):
        value_type = type(value)
        if value_type not in _DTO_TYPES:
            raise AnswerError(f"unsupported dataclass in answer serialization: {value_type.__name__}")
        return {field.name: _to_json_value(getattr(value, field.name)) for field in dataclasses.fields(value)}
    if isinstance(value, tuple):
        return [_to_json_value(item) for item in value]
    if isinstance(value, float):
        if not math.isfinite(value):
            raise AnswerError("non-finite float values are not supported in answer JSON")
        return value
    if isinstance(value, str | int | bool) or value is None:
        return value
    if isinstance(value, Path | bytes | bytearray | list | dict | set):
        raise AnswerError(f"unsupported value in answer serialization: {type(value).__name__}")
    raise AnswerError(f"unsupported value in answer serialization: {type(value).__name__}")
