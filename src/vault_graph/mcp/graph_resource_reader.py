from __future__ import annotations

import json

from vault_graph.app.graph_resource_service import GraphEntityResource, GraphResourceService, GraphResourceWarning
from vault_graph.graph.graph_contracts import EntityRecord, GraphEvidenceRef, RelationshipRecord
from vault_graph.mcp.mcp_errors import McpErrorPayload
from vault_graph.mcp.mcp_resources import McpResourceBody
from vault_graph.mcp.mcp_uri import McpResourceUri
from vault_graph.retrieval.graph_retrieval import GraphRetrievalRevision
from vault_graph.storage.interfaces.metadata_store import EvidenceReference


class GraphResourceReader:
    def __init__(self, *, graph_resource_service: GraphResourceService) -> None:
        self._graph_resource_service = graph_resource_service

    def read_entity(self, uri: McpResourceUri) -> McpResourceBody:
        resource = self._graph_resource_service.get_entity(
            vault_id=_required_value(uri.vault_id),
            entity_id=_required_value(uri.value),
        )
        return _resource_body(uri=uri, resource=resource, resource_kind="graph_entity")

    def read_concept(self, uri: McpResourceUri) -> McpResourceBody:
        resource = self._graph_resource_service.find_concept(
            vault_id=_required_value(uri.vault_id),
            name=_required_value(uri.value),
        )
        return _resource_body(uri=uri, resource=resource, resource_kind="concept")


def _resource_body(*, uri: McpResourceUri, resource: GraphEntityResource, resource_kind: str) -> McpResourceBody:
    payload: dict[str, object] = {
        "entity": _entity_to_dict(resource.entity),
        "evidence": [_evidence_to_dict(item) for item in resource.evidence],
        "relationships_by_status": _relationships_by_status(resource.related_relationships),
        "store_revisions": [_revision_to_dict(item) for item in resource.store_revisions],
        "warnings": [_warning_to_dict(item) for item in resource.warnings],
    }
    return McpResourceBody(
        uri=uri.normalized_uri,
        content_mime_type="application/json",
        text=json.dumps(payload, sort_keys=True, ensure_ascii=False, indent=2) + "\n",
        metadata={
            "vault_id": resource.entity.vault_id,
            "entity_id": resource.entity.entity_id,
            "resource_kind": resource_kind,
            "graph_extraction_spec_version": resource.entity.graph_extraction_spec_version,
            "graph_extraction_spec_digest": resource.entity.graph_extraction_spec_digest,
            "graph_index_revision": resource.entity.graph_index_revision,
            "relationship_count": len(resource.related_relationships),
            "evidence_count": len(resource.evidence),
        },
        warnings=tuple(_warning_to_mcp(item) for item in resource.warnings),
    )


def _entity_to_dict(entity: EntityRecord) -> dict[str, object]:
    return {
        "vault_id": entity.vault_id,
        "entity_id": entity.entity_id,
        "type": entity.type,
        "name": entity.name,
        "normalized_name": entity.normalized_name,
        "aliases": list(entity.aliases),
        "canonical_path": entity.canonical_path,
        "evidence_refs": [_graph_evidence_ref_to_dict(ref) for ref in entity.evidence_refs],
        "confidence": entity.confidence,
        "extraction_method": entity.extraction_method,
        "graph_extraction_spec_version": entity.graph_extraction_spec_version,
        "graph_extraction_spec_digest": entity.graph_extraction_spec_digest,
        "status": entity.status,
        "created_at": entity.created_at,
        "updated_at": entity.updated_at,
        "graph_index_revision": entity.graph_index_revision,
    }


def _relationship_to_dict(relationship: RelationshipRecord) -> dict[str, object]:
    return {
        "relationship_id": relationship.relationship_id,
        "type": relationship.type,
        "source_vault_id": relationship.source_vault_id,
        "source_entity_id": relationship.source_entity_id,
        "target_vault_id": relationship.target_vault_id,
        "target_entity_id": relationship.target_entity_id,
        "evidence_refs": [_graph_evidence_ref_to_dict(ref) for ref in relationship.evidence_refs],
        "status": relationship.status,
        "confidence": relationship.confidence,
        "extraction_method": relationship.extraction_method,
        "graph_extraction_spec_version": relationship.graph_extraction_spec_version,
        "graph_extraction_spec_digest": relationship.graph_extraction_spec_digest,
        "created_at": relationship.created_at,
        "updated_at": relationship.updated_at,
        "graph_index_revision": relationship.graph_index_revision,
    }


def _relationships_by_status(relationships: tuple[RelationshipRecord, ...]) -> dict[str, list[dict[str, object]]]:
    grouped: dict[str, list[dict[str, object]]] = {
        "stated": [],
        "inferred": [],
        "contested": [],
        "deprecated": [],
    }
    for relationship in relationships:
        grouped.setdefault(relationship.status, []).append(_relationship_to_dict(relationship))
    return grouped


def _graph_evidence_ref_to_dict(ref: GraphEvidenceRef) -> dict[str, object]:
    return {
        "evidence_ref_id": ref.evidence_ref_id,
        "owner_kind": ref.owner_kind,
        "owner_vault_id": ref.owner_vault_id,
        "owner_id": ref.owner_id,
        "evidence_vault_id": ref.evidence_vault_id,
        "document_id": ref.document_id,
        "chunk_id": ref.chunk_id,
        "content_hash": ref.content_hash,
        "section": ref.section,
        "anchor": ref.anchor,
        "path": ref.path,
        "excerpt": ref.excerpt,
    }


def _evidence_to_dict(evidence: EvidenceReference) -> dict[str, object]:
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


def _revision_to_dict(revision: GraphRetrievalRevision) -> dict[str, object]:
    return {
        "kind": revision.kind,
        "revision": revision.revision,
        "scope_key": revision.scope_key,
        "vault_id": revision.vault_id,
    }


def _warning_to_mcp(warning: GraphResourceWarning) -> McpErrorPayload:
    return McpErrorPayload(
        code=warning.code,
        message=warning.message,
        severity=warning.severity,
        affected_vault_ids=warning.affected_vault_ids,
        recovery_hint=warning.recovery_hint,
    )


def _warning_to_dict(warning: GraphResourceWarning) -> dict[str, object]:
    return {
        "code": warning.code,
        "message": warning.message,
        "severity": warning.severity,
        "affected_vault_ids": list(warning.affected_vault_ids),
        "recovery_hint": warning.recovery_hint,
    }


def _required_value(value: str | None) -> str:
    if value is None:
        raise AssertionError("resource value is required")
    return value
