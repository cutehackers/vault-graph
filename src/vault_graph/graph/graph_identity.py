from __future__ import annotations

from vault_graph.ingestion.document_normalizer import stable_id
from vault_graph.ingestion.vault_catalog import QueryScope


def normalize_entity_name(name: str) -> str:
    return " ".join(name.casefold().strip().split())


def stable_entity_id(
    *,
    vault_id: str,
    entity_type: str,
    normalized_name: str,
    canonical_path: str | None,
) -> str:
    return stable_id("entity", vault_id, entity_type, normalized_name, canonical_path or "")


def stable_relationship_id(
    *,
    relationship_type: str,
    source_vault_id: str,
    source_entity_id: str,
    target_vault_id: str,
    target_entity_id: str,
) -> str:
    return stable_id(
        "relationship",
        relationship_type,
        source_vault_id,
        source_entity_id,
        target_vault_id,
        target_entity_id,
    )


def stable_evidence_ref_id(
    *,
    owner_kind: str,
    owner_vault_id: str,
    owner_id: str,
    evidence_vault_id: str,
    document_id: str,
    chunk_id: str,
    anchor: str | None,
) -> str:
    return stable_id(
        "graph-evidence",
        owner_kind,
        owner_vault_id,
        owner_id,
        evidence_vault_id,
        document_id,
        chunk_id,
        anchor or "",
    )


def stable_graph_tombstone_id(
    *,
    record_kind: str,
    record_vault_id: str,
    record_id: str,
    actual_scope: str,
) -> str:
    return stable_id("graph-tombstone", record_kind, record_vault_id, record_id, actual_scope)


def graph_scope_key(scope: QueryScope) -> str:
    cross_vault = "cross" if scope.include_cross_vault else "local"
    return f"{','.join(scope.vault_ids)}:{','.join(scope.content_scopes)}:{cross_vault}"


def require_actual_graph_scope(scope: QueryScope) -> None:
    if len(scope.vault_ids) != 1:
        raise ValueError("GraphStore operations require per-Vault actual scopes")
