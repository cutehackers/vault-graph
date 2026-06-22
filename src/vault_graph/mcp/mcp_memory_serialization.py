from __future__ import annotations

from typing import TYPE_CHECKING

from vault_graph.ingestion.vault_catalog import QueryScope
from vault_graph.mcp.mcp_errors import McpErrorPayload
from vault_graph.mcp.mcp_uri import encode_resource_segment
from vault_graph.memory.memory_models import (
    MemoryBackendRevision,
    MemoryEvidenceRef,
    MemoryItem,
    MemoryWarning,
    OpenQuestionsProjection,
    OpenQuestionsVault,
    ProjectMemoryProjection,
    ProjectMemoryVault,
)

if TYPE_CHECKING:
    from vault_graph.mcp.mcp_tools import McpResourceLink


def project_memory_projection_to_payload(projection: ProjectMemoryProjection) -> dict[str, object]:
    return {
        "requested_scope": query_scope_to_dict(projection.requested_scope),
        "actual_scopes": [query_scope_to_dict(scope) for scope in projection.actual_scopes],
        "vaults": [_project_vault_to_dict(vault) for vault in projection.vaults],
        "warnings": [memory_warning_to_dict(warning) for warning in projection.warnings],
        "generated_at": projection.generated_at,
    }


def open_questions_projection_to_payload(projection: OpenQuestionsProjection) -> dict[str, object]:
    return {
        "requested_scope": query_scope_to_dict(projection.requested_scope),
        "actual_scopes": [query_scope_to_dict(scope) for scope in projection.actual_scopes],
        "vaults": [_open_questions_vault_to_dict(vault) for vault in projection.vaults],
        "warnings": [memory_warning_to_dict(warning) for warning in projection.warnings],
        "generated_at": projection.generated_at,
    }


def memory_warning_to_mcp_error(warning: MemoryWarning) -> McpErrorPayload:
    return McpErrorPayload(
        code=warning.code,
        message=warning.message,
        severity=warning.severity,
        affected_vault_ids=warning.affected_vault_ids,
        recovery_hint=warning.recovery_hint,
    )


def resource_links_for_memory_projection(
    projection: ProjectMemoryProjection | OpenQuestionsProjection,
) -> tuple[McpResourceLink, ...]:
    from vault_graph.mcp.mcp_tools import McpResourceLink

    links: list[McpResourceLink] = []
    for item in _items_for_projection(projection):
        evidence = item.evidence[0]
        title = item.title
        if "document" in item.document_resource_kinds:
            links.append(
                McpResourceLink(
                    rel="document",
                    uri=f"vault://{evidence.vault_id}/documents/{encode_resource_segment(evidence.path)}",
                    title=title,
                    vault_id=evidence.vault_id,
                    document_id=evidence.document_id,
                    chunk_id=evidence.chunk_id,
                )
            )
        if "page" in item.document_resource_kinds:
            links.append(
                McpResourceLink(
                    rel="page",
                    uri=f"vault://{evidence.vault_id}/pages/{encode_resource_segment(evidence.path)}",
                    title=title,
                    vault_id=evidence.vault_id,
                    document_id=evidence.document_id,
                    chunk_id=evidence.chunk_id,
                )
            )
        if "source" in item.document_resource_kinds:
            links.append(
                McpResourceLink(
                    rel="source",
                    uri=f"vault://{evidence.vault_id}/sources/{encode_resource_segment(evidence.document_id)}",
                    title=title,
                    vault_id=evidence.vault_id,
                    document_id=evidence.document_id,
                    chunk_id=evidence.chunk_id,
                )
            )
        if item.kind == "decision" and "decision" in item.document_resource_kinds:
            links.append(
                McpResourceLink(
                    rel="decision",
                    uri=f"vault://{evidence.vault_id}/decisions/{encode_resource_segment(evidence.document_id)}",
                    title=title,
                    vault_id=evidence.vault_id,
                    document_id=evidence.document_id,
                    chunk_id=evidence.chunk_id,
                )
            )
        if item.kind == "open_question" and "issue" in item.document_resource_kinds:
            links.append(
                McpResourceLink(
                    rel="issue",
                    uri=f"vault://{evidence.vault_id}/issues/{encode_resource_segment(evidence.document_id)}",
                    title=title,
                    vault_id=evidence.vault_id,
                    document_id=evidence.document_id,
                    chunk_id=evidence.chunk_id,
                )
            )
    return _unique_links(links)


def query_scope_to_dict(scope: QueryScope) -> dict[str, object]:
    return {
        "vault_ids": list(scope.vault_ids),
        "content_scopes": list(scope.content_scopes),
        "include_cross_vault": scope.include_cross_vault,
    }


def memory_warning_to_dict(warning: MemoryWarning) -> dict[str, object]:
    return {
        "code": warning.code,
        "message": warning.message,
        "severity": warning.severity,
        "affected_vault_ids": list(warning.affected_vault_ids),
        "recovery_hint": warning.recovery_hint,
    }


def _project_vault_to_dict(vault: ProjectMemoryVault) -> dict[str, object]:
    return {
        "vault_id": vault.vault_id,
        "display_name": vault.display_name,
        "current_state": [_memory_item_to_dict(item) for item in vault.current_state],
        "decisions": [_memory_item_to_dict(item) for item in vault.decisions],
        "open_questions": [_memory_item_to_dict(item) for item in vault.open_questions],
        "constraints": [_memory_item_to_dict(item) for item in vault.constraints],
        "next_priorities": [_memory_item_to_dict(item) for item in vault.next_priorities],
        "stale_areas": [_memory_item_to_dict(item) for item in vault.stale_areas],
        "warnings": [memory_warning_to_dict(warning) for warning in vault.warnings],
        "store_revisions": [_backend_revision_to_dict(revision) for revision in vault.store_revisions],
        "freshness": vault.freshness,
    }


def _open_questions_vault_to_dict(vault: OpenQuestionsVault) -> dict[str, object]:
    return {
        "vault_id": vault.vault_id,
        "display_name": vault.display_name,
        "questions": [_memory_item_to_dict(item) for item in vault.questions],
        "warnings": [memory_warning_to_dict(warning) for warning in vault.warnings],
        "store_revisions": [_backend_revision_to_dict(revision) for revision in vault.store_revisions],
        "freshness": vault.freshness,
    }


def _memory_item_to_dict(item: MemoryItem) -> dict[str, object]:
    return {
        "item_id": item.item_id,
        "kind": item.kind,
        "claim_status": item.claim_status,
        "matched_signals": list(item.matched_signals),
        "document_resource_kinds": list(item.document_resource_kinds),
        "title": item.title,
        "summary": item.summary,
        "vault_id": item.vault_id,
        "path": item.path,
        "status": item.status,
        "rank": item.rank,
        "evidence": [_evidence_to_dict(evidence) for evidence in item.evidence],
        "warnings": [memory_warning_to_dict(warning) for warning in item.warnings],
    }


def _evidence_to_dict(evidence: MemoryEvidenceRef) -> dict[str, object]:
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


def _backend_revision_to_dict(revision: MemoryBackendRevision) -> dict[str, object]:
    return {
        "kind": revision.kind,
        "revision": revision.revision,
        "vault_id": revision.vault_id,
        "scope_key": revision.scope_key,
    }


def _items_for_projection(projection: ProjectMemoryProjection | OpenQuestionsProjection) -> tuple[MemoryItem, ...]:
    items: list[MemoryItem] = []
    for vault in projection.vaults:
        if isinstance(vault, ProjectMemoryVault):
            items.extend(
                (
                    *vault.current_state,
                    *vault.decisions,
                    *vault.open_questions,
                    *vault.constraints,
                    *vault.next_priorities,
                    *vault.stale_areas,
                )
            )
        else:
            items.extend(vault.questions)
    return tuple(items)


def _unique_links(links: list[McpResourceLink]) -> tuple[McpResourceLink, ...]:
    seen: set[tuple[str, str, str | None, str | None]] = set()
    unique: list[McpResourceLink] = []
    for link in links:
        key = (link.rel, link.uri, link.document_id, link.chunk_id)
        if key in seen:
            continue
        seen.add(key)
        unique.append(link)
    return tuple(unique)
