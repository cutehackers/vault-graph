from __future__ import annotations

import hashlib
import json
from dataclasses import fields, is_dataclass
from urllib.parse import quote

from vault_graph.answer.answer_response import AnswerEvidence, AnswerResponse, AnswerSignal, AnswerWarning
from vault_graph.context.context_pack import ContextEvidence, ContextPack, ContextPackSignal, ContextPackWarning
from vault_graph.graph.graph_contracts import RelationshipRecord
from vault_graph.memory.result_explanation import (
    ExplanationEvidenceRef,
    ExplanationRecord,
    ExplanationSignal,
    ExplanationWarning,
)
from vault_graph.retrieval.graph_retrieval import (
    DecisionTraceResponse,
    DecisionTraceStep,
    GraphRetrievalWarning,
    RelatedItem,
    RelatedResponse,
)
from vault_graph.retrieval.retrieval_result import RetrievalResult, RetrievalSignal, RetrievalWarning, StoreRevision
from vault_graph.retrieval.search_response import SearchResponse, SearchStoreRevision, SearchWarning
from vault_graph.storage.interfaces.metadata_store import EvidenceReference


def explanation_records_for_search(response: SearchResponse) -> tuple[ExplanationRecord, ...]:
    return tuple(
        ExplanationRecord(
            result_id=result.result_id,
            source_kind="search_result",
            title=result.title,
            summary=result.summary,
            vault_id=result.vault_id,
            evidence=tuple(_evidence_ref_from_metadata(evidence) for evidence in result.evidence),
            signals=tuple(_signal_from_retrieval(signal) for signal in result.signals),
            relationship_status=result.relationship_status,
            store_revisions=_store_revision_dicts_for_search(response, result),
            warnings=(
                tuple(_warning_from_retrieval(warning, vault_id=result.vault_id) for warning in result.warnings)
                + tuple(
                    _warning_from_search(warning)
                    for warning in response.warnings
                    if _search_warning_matches_result(warning, result)
                )
            ),
            resource_links=_links_to_dicts(
                tuple(link for evidence in result.evidence for link in _links_for_evidence(evidence))
            ),
            generated_at=response.generated_at,
        )
        for result in response.results
    )


def explanation_records_for_context_pack(pack: ContextPack) -> tuple[ExplanationRecord, ...]:
    evidence_by_ref = {
        (evidence.ref.vault_id, evidence.ref.document_id, evidence.ref.chunk_id): evidence for evidence in pack.evidence
    }
    records: list[ExplanationRecord] = []
    for item in (
        *pack.current_state,
        *pack.relevant_pages,
        *pack.relevant_sources,
        *pack.decisions,
        *pack.constraints,
        *pack.open_questions,
    ):
        evidence = tuple(
            evidence_by_ref[(ref.vault_id, ref.document_id, ref.chunk_id)]
            for ref in item.evidence_refs
            if (ref.vault_id, ref.document_id, ref.chunk_id) in evidence_by_ref
        )
        if not evidence:
            continue
        records.append(
            ExplanationRecord(
                result_id=item.item_id,
                source_kind="context_pack_item",
                title=item.title,
                summary=item.summary,
                vault_id=evidence[0].ref.vault_id,
                evidence=tuple(_evidence_ref_from_context(value) for value in evidence),
                signals=tuple(_signal_from_context(signal) for signal in item.retrieval_signals),
                relationship_status=item.relationship_status,
                store_revisions=tuple(_json_object(_json_safe(revision)) for revision in pack.store_revisions),
                warnings=(
                    tuple(_warning_from_context(warning) for warning in item.warnings)
                    + tuple(
                        _warning_from_context(warning)
                        for warning in pack.warnings
                        if _context_warning_matches_item(warning, evidence=evidence)
                    )
                    + tuple(
                        _warning_from_context(warning)
                        for context_evidence in evidence
                        for warning in context_evidence.warnings
                    )
                ),
                resource_links=_links_to_dicts(
                    tuple(
                        link
                        for context_evidence in evidence
                        for link in _links_for_context_evidence(context_evidence)
                    )
                ),
                generated_at=pack.generated_at,
            )
        )
    return tuple(records)


def explanation_records_for_related(response: RelatedResponse) -> tuple[ExplanationRecord, ...]:
    return tuple(
        ExplanationRecord(
            result_id=_related_result_id(response, item),
            source_kind="related_item",
            title=item.entity.name,
            summary=item.explanation,
            vault_id=item.entity.vault_id,
            evidence=tuple(_evidence_ref_from_metadata(evidence) for evidence in item.evidence),
            signals=(
                ExplanationSignal(
                    kind="graph",
                    source_id=item.entity.entity_id,
                    rank=item.rank,
                    score=item.score,
                    backend="graph_projection",
                    index_revision=response.projection_build_id or response.graph_projection_version,
                    explanation=item.explanation,
                ),
            ),
            relationship_status=_relationship_status_for_path(item.relationship_path),
            store_revisions=tuple(_json_object(_json_safe(revision)) for revision in response.store_revisions),
            warnings=tuple(
                _warning_from_graph(warning)
                for warning in response.warnings
                if _graph_warning_matches_item(
                    warning, vault_id=item.entity.vault_id, entity_id=item.entity.entity_id, path=item.relationship_path
                )
            ),
            resource_links=_links_to_dicts(
                tuple(
                    link
                    for link_group in (
                        _links_for_graph_entity(item.entity),
                        *(_links_for_evidence(evidence) for evidence in item.evidence),
                    )
                    for link in link_group
                )
            ),
            generated_at=response.generated_at,
        )
        for item in response.items
    )


def explanation_records_for_decision_trace(response: DecisionTraceResponse) -> tuple[ExplanationRecord, ...]:
    return tuple(
        ExplanationRecord(
            result_id=_decision_trace_result_id(response, step),
            source_kind="decision_trace_step",
            title=f"{step.role}: {step.entity.name}",
            summary=step.explanation,
            vault_id=step.entity.vault_id,
            evidence=tuple(_evidence_ref_from_metadata(evidence) for evidence in step.evidence),
            signals=(
                ExplanationSignal(
                    kind="graph",
                    source_id=step.entity.entity_id,
                    rank=step.rank,
                    score=None,
                    backend="graph_projection",
                    index_revision=response.projection_build_id or response.graph_projection_version,
                    explanation=step.explanation,
                ),
            ),
            relationship_status=step.relationship_status,
            store_revisions=tuple(_json_object(_json_safe(revision)) for revision in response.store_revisions),
            warnings=tuple(
                _warning_from_graph(warning)
                for warning in response.warnings
                if _graph_warning_matches_item(
                    warning, vault_id=step.entity.vault_id, entity_id=step.entity.entity_id, path=step.relationship_path
                )
            ),
            resource_links=_links_to_dicts(
                tuple(
                    link
                    for link_group in (
                        _links_for_graph_entity(step.entity),
                        *(_links_for_evidence(evidence) for evidence in step.evidence),
                    )
                    for link in link_group
                )
            ),
            generated_at=response.generated_at,
        )
        for step in response.steps
    )


def explanation_records_for_answer(response: AnswerResponse) -> tuple[ExplanationRecord, ...]:
    warnings = tuple(_warning_from_answer(warning) for warning in response.warnings)
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
            store_revisions=tuple(_json_safe(revision) for revision in evidence.store_revisions),
            warnings=warnings,
            resource_links=_links_to_dicts(_links_for_answer_evidence(evidence)),
            generated_at=response.generated_at,
        )
        for evidence in response.evidence
    )


def _evidence_ref_from_metadata(evidence: EvidenceReference) -> ExplanationEvidenceRef:
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


def _evidence_ref_from_context(evidence: ContextEvidence) -> ExplanationEvidenceRef:
    return ExplanationEvidenceRef(
        vault_id=evidence.ref.vault_id,
        document_id=evidence.ref.document_id,
        chunk_id=evidence.ref.chunk_id,
        path=evidence.path,
        section=evidence.section,
        anchor=evidence.anchor,
        content_hash=evidence.content_hash,
        raw_sha256=evidence.raw_sha256,
        metadata_index_revision=evidence.metadata_index_revision,
        vault_revision=evidence.vault_revision,
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


def _signal_from_retrieval(signal: RetrievalSignal) -> ExplanationSignal:
    return ExplanationSignal(
        kind=signal.kind,
        source_id=signal.source_id,
        rank=signal.rank,
        score=signal.score,
        backend=signal.backend,
        index_revision=signal.index_revision,
        explanation=signal.explanation,
    )


def _signal_from_context(signal: ContextPackSignal) -> ExplanationSignal:
    return ExplanationSignal(
        kind=signal.kind,
        source_id=None,
        rank=signal.rank,
        score=signal.score,
        backend=None,
        index_revision=None,
        explanation=signal.explanation,
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


def _warning_from_retrieval(warning: RetrievalWarning, *, vault_id: str) -> ExplanationWarning:
    return ExplanationWarning(
        code=warning.code,
        message=warning.message,
        severity=warning.severity,
        affected_vault_ids=(vault_id,),
    )


def _warning_from_search(warning: SearchWarning) -> ExplanationWarning:
    return ExplanationWarning(
        code=warning.code,
        message=warning.message,
        severity=warning.severity,
        affected_vault_ids=warning.affected_vault_ids,
    )


def _warning_from_context(warning: ContextPackWarning) -> ExplanationWarning:
    return ExplanationWarning(
        code=warning.code,
        message=warning.message,
        severity=warning.severity,
        affected_vault_ids=warning.affected_vault_ids,
        recovery_hint=warning.recovery_hint,
    )


def _warning_from_graph(warning: GraphRetrievalWarning) -> ExplanationWarning:
    return ExplanationWarning(
        code=warning.code,
        message=warning.message,
        severity=warning.severity,
        affected_vault_ids=warning.affected_vault_ids,
    )


def _warning_from_answer(warning: AnswerWarning) -> ExplanationWarning:
    return ExplanationWarning(
        code=warning.code,
        message=warning.message,
        severity=warning.severity,
        affected_vault_ids=warning.affected_vault_ids,
        recovery_hint=warning.recovery_hint,
    )


def _store_revision_dicts_for_search(
    response: SearchResponse,
    result: RetrievalResult,
) -> tuple[dict[str, object], ...]:
    return _dedupe_dicts(
        tuple(_store_revision_to_dict(revision) for revision in result.store_revisions)
        + tuple(_search_store_revision_to_dict(revision) for revision in response.store_revisions)
    )


def _store_revision_to_dict(revision: StoreRevision) -> dict[str, object]:
    return {"kind": revision.kind, "revision": revision.revision}


def _search_store_revision_to_dict(revision: SearchStoreRevision) -> dict[str, object]:
    return {
        "kind": revision.kind,
        "revision": revision.revision,
        "scope_key": revision.scope_key,
        "vault_id": revision.vault_id,
    }


def _links_for_evidence(evidence: EvidenceReference) -> tuple[dict[str, object], ...]:
    return _links_for_path(
        vault_id=evidence.vault_id,
        document_id=evidence.document_id,
        chunk_id=evidence.chunk_id,
        path=evidence.path,
    )


def _links_for_context_evidence(evidence: ContextEvidence) -> tuple[dict[str, object], ...]:
    return _links_for_path(
        vault_id=evidence.ref.vault_id,
        document_id=evidence.ref.document_id,
        chunk_id=evidence.ref.chunk_id,
        path=evidence.path,
    )


def _links_for_answer_evidence(evidence: AnswerEvidence) -> tuple[dict[str, object], ...]:
    return _links_for_path(
        vault_id=evidence.vault_id,
        document_id=evidence.document_id,
        chunk_id=evidence.chunk_id,
        path=evidence.path,
    )


def _links_for_graph_entity(entity: object | None) -> tuple[dict[str, object], ...]:
    if entity is None:
        return ()
    vault_id = getattr(entity, "vault_id", None)
    entity_id = getattr(entity, "entity_id", None)
    name = getattr(entity, "name", None)
    if not isinstance(vault_id, str) or not isinstance(entity_id, str):
        return ()
    return (
        {
            "rel": "entity",
            "uri": f"vault://{vault_id}/entities/{_encode(entity_id)}",
            "title": name if isinstance(name, str) else entity_id,
            "vault_id": vault_id,
        },
    )


def _links_for_path(*, vault_id: str, document_id: str, chunk_id: str, path: str) -> tuple[dict[str, object], ...]:
    links: list[dict[str, object]] = [
        {
            "rel": "evidence",
            "uri": f"vault://{vault_id}/documents/{_encode(path)}",
            "title": path,
            "vault_id": vault_id,
            "document_id": document_id,
            "chunk_id": chunk_id,
        }
    ]
    if path.startswith("wiki/"):
        links.append(
            {
                "rel": "page",
                "uri": f"vault://{vault_id}/pages/{_encode(path)}",
                "title": path,
                "vault_id": vault_id,
                "document_id": document_id,
                "chunk_id": chunk_id,
            }
        )
    if path.startswith(("raw/", "docs/", "scratch/reports/")):
        links.append(
            {
                "rel": "source",
                "uri": f"vault://{vault_id}/sources/{_encode(document_id)}",
                "title": path,
                "vault_id": vault_id,
                "document_id": document_id,
                "chunk_id": chunk_id,
            }
        )
    if path.startswith("wiki/decisions/"):
        links.append(
            {
                "rel": "decision",
                "uri": f"vault://{vault_id}/decisions/{_encode(document_id)}",
                "title": path,
                "vault_id": vault_id,
                "document_id": document_id,
                "chunk_id": chunk_id,
            }
        )
    if path.startswith("wiki/issues/"):
        links.append(
            {
                "rel": "issue",
                "uri": f"vault://{vault_id}/issues/{_encode(document_id)}",
                "title": path,
                "vault_id": vault_id,
                "document_id": document_id,
                "chunk_id": chunk_id,
            }
        )
    return tuple(links)


def _links_to_dicts(links: tuple[dict[str, object], ...]) -> tuple[dict[str, object], ...]:
    seen: set[tuple[str, str]] = set()
    unique: list[dict[str, object]] = []
    for link in links:
        rel = str(link["rel"])
        uri = str(link["uri"])
        identity = (rel, uri)
        if identity in seen:
            continue
        seen.add(identity)
        unique.append(dict(link))
    return tuple(unique)


def _related_result_id(response: RelatedResponse, item: RelatedItem) -> str:
    return _runtime_result_id(
        "related",
        {
            "target": response.target,
            "vault_id": item.entity.vault_id,
            "entity_id": item.entity.entity_id,
            "rank": item.rank,
            "relationship_path": [relationship.relationship_id for relationship in item.relationship_path],
        },
    )


def _decision_trace_result_id(response: DecisionTraceResponse, step: DecisionTraceStep) -> str:
    return _runtime_result_id(
        "decision_trace",
        {
            "topic": response.topic,
            "role": step.role,
            "vault_id": step.entity.vault_id,
            "entity_id": step.entity.entity_id,
            "rank": step.rank,
            "relationship_path": [relationship.relationship_id for relationship in step.relationship_path],
        },
    )


def _runtime_result_id(prefix: str, identity: dict[str, object]) -> str:
    identity_json = json.dumps(identity, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    digest = hashlib.sha256(identity_json.encode("utf-8")).hexdigest()[:24]
    return f"{prefix}:{digest}"


def _relationship_status_for_path(path: tuple[RelationshipRecord, ...]) -> str | None:
    statuses = tuple(dict.fromkeys(relationship.status for relationship in path if relationship.status))
    if not statuses:
        return None
    if len(statuses) == 1:
        return statuses[0]
    return ",".join(statuses)


def _search_warning_matches_result(warning: SearchWarning, result: RetrievalResult) -> bool:
    if warning.source_id and not any(signal.source_id == warning.source_id for signal in result.signals):
        return False
    if warning.document_id and not any(evidence.document_id == warning.document_id for evidence in result.evidence):
        return False
    if warning.chunk_id and not any(evidence.chunk_id == warning.chunk_id for evidence in result.evidence):
        return False
    return result.vault_id in warning.affected_vault_ids


def _context_warning_matches_item(
    warning: ContextPackWarning,
    *,
    evidence: tuple[ContextEvidence, ...],
) -> bool:
    if not warning.evidence_refs:
        return False
    identities = {(value.ref.vault_id, value.ref.document_id, value.ref.chunk_id) for value in evidence}
    return any((ref.vault_id, ref.document_id, ref.chunk_id) in identities for ref in warning.evidence_refs)


def _graph_warning_matches_item(
    warning: GraphRetrievalWarning,
    *,
    vault_id: str,
    entity_id: str,
    path: tuple[RelationshipRecord, ...],
) -> bool:
    if vault_id not in warning.affected_vault_ids:
        return False
    if warning.entity_id and warning.entity_id != entity_id:
        return False
    if warning.relationship_id and not any(
        relationship.relationship_id == warning.relationship_id for relationship in path
    ):
        return False
    return True


def _json_safe(value: object) -> dict[str, object]:
    if is_dataclass(value) and not isinstance(value, type):
        return {field.name: _json_value(getattr(value, field.name)) for field in fields(value)}
    return _json_object(value)


def _json_value(value: object) -> object:
    if is_dataclass(value) and not isinstance(value, type):
        return _json_safe(value)
    if isinstance(value, tuple | list):
        return [_json_value(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, str | int | float | bool) or value is None:
        return value
    return str(value)


def _json_object(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        raise TypeError("expected JSON object")
    return {str(key): _json_value(item) for key, item in value.items()}


def _dedupe_dicts(values: tuple[dict[str, object], ...]) -> tuple[dict[str, object], ...]:
    seen: set[str] = set()
    unique: list[dict[str, object]] = []
    for value in values:
        identity = json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
        if identity in seen:
            continue
        seen.add(identity)
        unique.append(value)
    return tuple(unique)


def _encode(value: str) -> str:
    return quote(value, safe="")
