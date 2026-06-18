from __future__ import annotations

import dataclasses
import json
from pathlib import Path
from typing import Any

from vault_graph.app.index_service import StatusReport
from vault_graph.context.context_pack import ContextEvidence, ContextPack, ContextPackWarning
from vault_graph.context.context_pack_serialization import context_pack_to_dict
from vault_graph.ingestion.vault_catalog import QueryScope
from vault_graph.mcp.mcp_errors import McpErrorPayload
from vault_graph.mcp.mcp_tools import McpResourceLink
from vault_graph.mcp.mcp_uri import encode_resource_segment
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


def query_scope_to_dict(scope: QueryScope) -> dict[str, object]:
    return {
        "vault_ids": list(scope.vault_ids),
        "content_scopes": list(scope.content_scopes),
        "include_cross_vault": scope.include_cross_vault,
    }


def search_response_to_payload(response: SearchResponse) -> dict[str, object]:
    return {
        "query_text": response.query_text,
        "requested_scope": query_scope_to_dict(response.requested_scope),
        "actual_scopes": [query_scope_to_dict(scope) for scope in response.actual_scopes],
        "limit": response.limit,
        "result_count": response.result_count,
        "candidate_count": response.candidate_count,
        "dropped_candidate_count": response.dropped_candidate_count,
        "results": [_retrieval_result_to_dict(result) for result in response.results],
        "warnings": [search_warning_to_dict(warning) for warning in response.warnings],
        "degraded": response.degraded,
        "store_revisions": [_search_store_revision_to_dict(revision) for revision in response.store_revisions],
        "generated_at": response.generated_at,
    }


def context_pack_to_payload(pack: ContextPack) -> dict[str, object]:
    return context_pack_to_dict(pack)


def related_response_to_payload(response: RelatedResponse) -> dict[str, object]:
    return {
        "target": response.target,
        "resolved_target": _json_value(response.resolved_target),
        "target_candidates": [_json_value(candidate) for candidate in response.target_candidates],
        "requested_scope": query_scope_to_dict(response.requested_scope),
        "actual_scopes": [query_scope_to_dict(scope) for scope in response.actual_scopes],
        "projection_build_id": response.projection_build_id,
        "graph_projection_version": response.graph_projection_version,
        "result_count": response.result_count,
        "items": [_related_item_to_dict(item) for item in response.items],
        "warnings": [graph_warning_to_dict(warning) for warning in response.warnings],
        "store_revisions": [_json_value(revision) for revision in response.store_revisions],
        "generated_at": response.generated_at,
    }


def decision_trace_response_to_payload(response: DecisionTraceResponse) -> dict[str, object]:
    return {
        "topic": response.topic,
        "trace_kind": response.trace_kind,
        "resolved_target": _json_value(response.resolved_target),
        "target_candidates": [_json_value(candidate) for candidate in response.target_candidates],
        "requested_scope": query_scope_to_dict(response.requested_scope),
        "actual_scopes": [query_scope_to_dict(scope) for scope in response.actual_scopes],
        "projection_build_id": response.projection_build_id,
        "graph_projection_version": response.graph_projection_version,
        "steps": [_decision_trace_step_to_dict(step) for step in response.steps],
        "warnings": [graph_warning_to_dict(warning) for warning in response.warnings],
        "store_revisions": [_json_value(revision) for revision in response.store_revisions],
        "generated_at": response.generated_at,
    }


def status_report_to_payload(report: StatusReport, *, selected_scope: QueryScope) -> dict[str, object]:
    return {
        "selected_scope": query_scope_to_dict(selected_scope),
        "active_vault_id": report.active_vault_id,
        "vaults": [{"vault_id": vault_id, "root_path": root_path} for vault_id, root_path in report.vaults],
        "metadata": {
            "ok": report.metadata_ok,
            "schema_compatible": report.metadata_schema_compatible,
            "message": report.metadata_message,
        },
        "vector": {
            "ok": report.vector_ok,
            "backend": report.vector_backend,
            "schema_compatible": report.vector_schema_compatible,
            "message": report.vector_message,
            "revision": report.vector_revision,
            "stale_count": report.vector_stale_count,
            "last_error": report.vector_last_error,
            "status_scope": report.vector_status_scope,
        },
        "embedding": {
            "model": report.embedding_model,
            "model_version": report.embedding_model_version,
            "dimensions": report.embedding_dimensions,
            "spec_version": report.embedding_spec_version,
            "embedding_batch_size": report.embedding_batch_size,
            "embedding_parallelism": report.embedding_parallelism,
            "embedding_lazy_load": report.embedding_lazy_load,
        },
        "graph": {
            "readiness": _json_value(report.graph_readiness),
            "status_scope": report.graph_status_scope,
            "last_error": report.graph_last_error,
        },
    }


def resource_links_for_search(response: SearchResponse) -> tuple[McpResourceLink, ...]:
    return _unique_links(
        link
        for result in response.results
        for evidence in result.evidence
        for link in _links_for_evidence(evidence)
    )


def resource_links_for_context_pack(pack: ContextPack) -> tuple[McpResourceLink, ...]:
    return _unique_links(link for evidence in pack.evidence for link in _links_for_context_evidence(evidence))


def resource_links_for_related(response: RelatedResponse) -> tuple[McpResourceLink, ...]:
    return _unique_links(
        (
            *_links_for_graph_entity(response.resolved_target),
            *(
                link
                for candidate in response.target_candidates
                for link in _links_for_graph_entity(candidate)
            ),
            *(
                link
                for item in response.items
                for link in (
                    *_links_for_graph_entity(item.entity),
                    *(evidence_link for evidence in item.evidence for evidence_link in _links_for_evidence(evidence)),
                )
            ),
        )
    )


def resource_links_for_decision_trace(response: DecisionTraceResponse) -> tuple[McpResourceLink, ...]:
    return _unique_links(
        (
            *_links_for_graph_entity(response.resolved_target),
            *(
                link
                for candidate in response.target_candidates
                for link in _links_for_graph_entity(candidate)
            ),
            *(
                link
                for step in response.steps
                for link in (
                    *_links_for_graph_entity(step.entity),
                    *(evidence_link for evidence in step.evidence for evidence_link in _links_for_evidence(evidence)),
                )
            ),
        )
    )


def tool_text_mirror(payload: dict[str, object]) -> str:
    return json.dumps(payload, sort_keys=True, ensure_ascii=False, allow_nan=False)


def evidence_to_dict(evidence: EvidenceReference) -> dict[str, object]:
    return {
        "vault_id": evidence.vault_id,
        "document_id": evidence.document_id,
        "chunk_id": evidence.chunk_id,
        "path": evidence.path,
        "section": evidence.section,
        "anchor": evidence.anchor,
        "content_hash": evidence.content_hash,
        "raw_sha256": evidence.raw_sha256,
        "metadata_index_revision": evidence.metadata_index_revision,
        "vault_revision": evidence.vault_revision,
    }


def retrieval_signal_to_dict(signal: RetrievalSignal) -> dict[str, object]:
    return {
        "kind": signal.kind,
        "source_id": signal.source_id,
        "rank": signal.rank,
        "score": signal.score,
        "backend": signal.backend,
        "index_revision": signal.index_revision,
        "explanation": signal.explanation,
    }


def retrieval_warning_to_dict(warning: RetrievalWarning) -> dict[str, object]:
    return {
        "code": warning.code,
        "message": warning.message,
        "severity": warning.severity,
    }


def search_warning_to_dict(warning: SearchWarning) -> dict[str, object]:
    return {
        "code": warning.code,
        "message": warning.message,
        "severity": warning.severity,
        "affected_vault_ids": list(warning.affected_vault_ids),
        "scope_key": warning.scope_key,
        "document_id": warning.document_id,
        "chunk_id": warning.chunk_id,
        "source_id": warning.source_id,
    }


def graph_warning_to_dict(warning: GraphRetrievalWarning) -> dict[str, object]:
    return {
        "code": warning.code,
        "message": warning.message,
        "severity": warning.severity,
        "affected_vault_ids": list(warning.affected_vault_ids),
        "scope_key": warning.scope_key,
        "entity_id": warning.entity_id,
        "relationship_id": warning.relationship_id,
        "evidence_ref_id": warning.evidence_ref_id,
    }


def mcp_warning_from_search(warning: SearchWarning) -> McpErrorPayload:
    return McpErrorPayload(
        code=warning.code,
        message=warning.message,
        severity=warning.severity,
        affected_vault_ids=warning.affected_vault_ids,
    )


def mcp_warning_from_graph(warning: GraphRetrievalWarning) -> McpErrorPayload:
    return McpErrorPayload(
        code=warning.code,
        message=warning.message,
        severity=warning.severity,
        affected_vault_ids=warning.affected_vault_ids,
    )


def mcp_warning_from_context(warning: ContextPackWarning) -> McpErrorPayload:
    return McpErrorPayload(
        code=warning.code,
        message=warning.message,
        severity=warning.severity,
        affected_vault_ids=warning.affected_vault_ids,
        recovery_hint=warning.recovery_hint,
    )


def _retrieval_result_to_dict(result: RetrievalResult) -> dict[str, object]:
    return {
        "result_id": result.result_id,
        "vault_id": result.vault_id,
        "kind": result.kind,
        "title": result.title,
        "summary": result.summary,
        "rank": result.rank,
        "evidence": [evidence_to_dict(evidence) for evidence in result.evidence],
        "signals": [retrieval_signal_to_dict(signal) for signal in result.signals],
        "relationship_status": result.relationship_status,
        "warnings": [retrieval_warning_to_dict(warning) for warning in result.warnings],
        "store_revisions": [_store_revision_to_dict(revision) for revision in result.store_revisions],
    }


def _store_revision_to_dict(revision: StoreRevision) -> dict[str, object]:
    return {
        "kind": revision.kind,
        "revision": revision.revision,
    }


def _search_store_revision_to_dict(revision: SearchStoreRevision) -> dict[str, object]:
    return {
        "kind": revision.kind,
        "revision": revision.revision,
        "scope_key": revision.scope_key,
        "vault_id": revision.vault_id,
    }


def _related_item_to_dict(item: RelatedItem) -> dict[str, object]:
    return {
        "rank": item.rank,
        "entity": _json_value(item.entity),
        "relationship_path": [_json_value(relationship) for relationship in item.relationship_path],
        "evidence": [evidence_to_dict(evidence) for evidence in item.evidence],
        "score": item.score,
        "explanation": item.explanation,
    }


def _decision_trace_step_to_dict(step: DecisionTraceStep) -> dict[str, object]:
    return {
        "rank": step.rank,
        "role": step.role,
        "entity": _json_value(step.entity),
        "relationship_path": [_json_value(relationship) for relationship in step.relationship_path],
        "evidence": [evidence_to_dict(evidence) for evidence in step.evidence],
        "relationship_status": step.relationship_status,
        "explanation": step.explanation,
    }


def _links_for_evidence(evidence: EvidenceReference) -> tuple[McpResourceLink, ...]:
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
    if evidence.path.startswith(("raw/", "docs/", "scratch/reports/")):
        links.append(
            McpResourceLink(
                rel="source",
                uri=f"vault://{evidence.vault_id}/sources/{encode_resource_segment(evidence.document_id)}",
                title=evidence.path,
                vault_id=evidence.vault_id,
                document_id=evidence.document_id,
                chunk_id=evidence.chunk_id,
            )
        )
    if evidence.path.startswith("wiki/decisions/"):
        links.append(
            McpResourceLink(
                rel="decision",
                uri=f"vault://{evidence.vault_id}/decisions/{encode_resource_segment(evidence.document_id)}",
                title=evidence.path,
                vault_id=evidence.vault_id,
                document_id=evidence.document_id,
                chunk_id=evidence.chunk_id,
            )
        )
    if evidence.path.startswith("wiki/issues/"):
        links.append(
            McpResourceLink(
                rel="issue",
                uri=f"vault://{evidence.vault_id}/issues/{encode_resource_segment(evidence.document_id)}",
                title=evidence.path,
                vault_id=evidence.vault_id,
                document_id=evidence.document_id,
                chunk_id=evidence.chunk_id,
            )
        )
    return tuple(links)


def _links_for_context_evidence(evidence: ContextEvidence) -> tuple[McpResourceLink, ...]:
    reference = EvidenceReference(
        vault_id=evidence.ref.vault_id,
        document_id=evidence.ref.document_id,
        chunk_id=evidence.ref.chunk_id,
        path=evidence.path,
        section=evidence.section,
        anchor=evidence.anchor,
        content_hash=evidence.content_hash,
        raw_sha256=evidence.raw_sha256 or "",
        metadata_index_revision=evidence.metadata_index_revision,
        vault_revision=evidence.vault_revision,
    )
    return _links_for_evidence(reference)


def _links_for_graph_entity(entity: Any) -> tuple[McpResourceLink, ...]:
    if entity is None:
        return ()
    vault_id = entity.vault_id
    entity_id = entity.entity_id
    return (
        McpResourceLink(
            rel="graph_entity",
            uri=f"vault://{vault_id}/graph/entities/{encode_resource_segment(entity_id)}",
            title=getattr(entity, "name", entity_id),
            vault_id=vault_id,
        ),
    )


def _unique_links(links: Any) -> tuple[McpResourceLink, ...]:
    seen: set[tuple[str, str]] = set()
    unique: list[McpResourceLink] = []
    for link in links:
        key = (link.rel, link.uri)
        if key in seen:
            continue
        seen.add(key)
        unique.append(link)
    return tuple(unique)


def _json_value(value: object) -> object:
    if dataclasses.is_dataclass(value):
        return {field.name: _json_value(getattr(value, field.name)) for field in dataclasses.fields(value)}
    if isinstance(value, tuple | list):
        return [_json_value(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, str | int | float | bool) or value is None:
        return value
    if isinstance(value, Path | bytes | bytearray | set):
        raise TypeError(f"unsupported value in MCP tool serialization: {type(value).__name__}")
    raise TypeError(f"unsupported value in MCP tool serialization: {type(value).__name__}")
