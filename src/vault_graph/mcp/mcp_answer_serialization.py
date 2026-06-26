from __future__ import annotations

from vault_graph.answer.answer_renderer import answer_response_to_dict
from vault_graph.answer.answer_response import (
    AnswerEvidence,
    AnswerResponse,
    AnswerSignal,
    AnswerStoreRevision,
    AnswerWarning,
)
from vault_graph.mcp.mcp_errors import McpErrorPayload
from vault_graph.mcp.mcp_tools import McpResourceLink
from vault_graph.mcp.mcp_uri import encode_resource_segment
from vault_graph.memory.result_explanation import (
    ExplanationEvidenceRef,
    ExplanationRecord,
    ExplanationSignal,
    ExplanationWarning,
)


def answer_response_to_payload(response: AnswerResponse) -> dict[str, object]:
    return answer_response_to_dict(response)


def resource_links_for_answer(response: AnswerResponse) -> tuple[McpResourceLink, ...]:
    return _unique_links(tuple(link for evidence in response.evidence for link in _links_for_evidence(evidence)))


def mcp_warning_from_answer(warning: AnswerWarning) -> McpErrorPayload:
    return McpErrorPayload(
        code=warning.code,
        message=warning.message,
        severity=warning.severity,
        affected_vault_ids=warning.affected_vault_ids,
        recovery_hint=warning.recovery_hint,
    )


def explanation_records_for_answer(response: AnswerResponse) -> tuple[ExplanationRecord, ...]:
    answer_warnings = tuple(_warning_from_answer(warning) for warning in response.warnings)
    return tuple(
        ExplanationRecord(
            result_id=evidence.evidence_id,
            source_kind="search_result",
            title=evidence.path,
            summary=evidence.excerpt or evidence.retrieval_reason,
            vault_id=evidence.vault_id,
            evidence=(_evidence_ref_from_answer(evidence),),
            signals=tuple(_signal_from_answer(signal) for signal in evidence.signals),
            relationship_status=evidence.relationship_status,
            store_revisions=tuple(_store_revision_to_dict(revision) for revision in evidence.store_revisions),
            warnings=answer_warnings,
            resource_links=tuple(link.to_json_dict() for link in _links_for_evidence(evidence)),
            generated_at=response.generated_at,
        )
        for evidence in response.evidence
    )


def _evidence_ref_from_answer(evidence: AnswerEvidence) -> ExplanationEvidenceRef:
    return ExplanationEvidenceRef(
        vault_id=evidence.vault_id,
        document_id=evidence.document_id,
        chunk_id=evidence.chunk_id,
        path=evidence.path,
        section=evidence.section,
        anchor=evidence.anchor,
        content_hash=evidence.content_hash,
        raw_sha256=evidence.raw_sha256,
        metadata_index_revision=evidence.metadata_index_revision,
        vault_revision=evidence.vault_revision,
    )


def _signal_from_answer(signal: AnswerSignal) -> ExplanationSignal:
    return ExplanationSignal(
        kind=signal.kind,
        source_id=None,
        rank=signal.rank,
        score=signal.score,
        backend=signal.backend,
        index_revision=signal.index_revision,
        explanation=signal.explanation or "Used as answer evidence.",
    )


def _warning_from_answer(warning: AnswerWarning) -> ExplanationWarning:
    return ExplanationWarning(
        code=warning.code,
        message=warning.message,
        severity=warning.severity,
        affected_vault_ids=warning.affected_vault_ids,
        recovery_hint=warning.recovery_hint,
    )


def _store_revision_to_dict(revision: AnswerStoreRevision) -> dict[str, object]:
    return {
        "kind": revision.kind,
        "revision": revision.revision,
        "scope_key": revision.scope_key,
        "vault_id": revision.vault_id,
    }


def _links_for_evidence(evidence: AnswerEvidence) -> tuple[McpResourceLink, ...]:
    encoded_path = encode_resource_segment(evidence.path)
    links = [
        McpResourceLink(
            rel="evidence",
            uri=f"vault://{evidence.vault_id}/documents/{encoded_path}",
            title=evidence.path,
            vault_id=evidence.vault_id,
            document_id=evidence.document_id,
            chunk_id=evidence.chunk_id,
        )
    ]
    if evidence.path.startswith("wiki/"):
        links.append(
            McpResourceLink(
                rel="page",
                uri=f"vault://{evidence.vault_id}/pages/{encoded_path}",
                title=evidence.path,
                vault_id=evidence.vault_id,
                document_id=evidence.document_id,
                chunk_id=evidence.chunk_id,
            )
        )
    return tuple(links)


def _unique_links(links: tuple[McpResourceLink, ...]) -> tuple[McpResourceLink, ...]:
    seen: set[tuple[str, str]] = set()
    unique: list[McpResourceLink] = []
    for link in links:
        identity = (link.rel, link.uri)
        if identity in seen:
            continue
        seen.add(identity)
        unique.append(link)
    return tuple(unique)
