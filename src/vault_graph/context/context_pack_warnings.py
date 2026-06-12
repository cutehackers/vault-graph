from __future__ import annotations

from typing import TYPE_CHECKING, cast

from vault_graph.context.context_pack import ContextEvidenceRef, ContextPackWarning, ContextPackWarningSeverity

if TYPE_CHECKING:
    from vault_graph.retrieval.graph_retrieval import GraphRetrievalWarning
    from vault_graph.retrieval.retrieval_result import RetrievalWarning
    from vault_graph.retrieval.search_response import SearchWarning
    from vault_graph.storage.interfaces.metadata_store import EvidenceReference

SEARCH_WARNING_CODE_MAP = {
    "vector_query_failed": "search_degraded",
    "vector_stale": "stale_projection",
    "stale_vector": "stale_projection",
    "keyword_index_unavailable": "search_degraded",
    "vector_unavailable": "search_degraded",
    "embedding_model_unavailable": "search_degraded",
    "degraded_keyword_only": "search_degraded",
    "missing_evidence": "missing_evidence",
    "graph_stale": "graph_stale",
    "graph_unavailable": "graph_unavailable",
    "graph_query_failed": "graph_unavailable",
}

GRAPH_WARNING_CODE_MAP = {
    "graph_query_failed": "graph_unavailable",
    "graph_missing": "graph_unavailable",
    "graph_unavailable": "graph_unavailable",
    "graph_stale": "graph_stale",
    "target_not_found": "target_not_found",
    "graph_target_not_found": "target_not_found",
    "ambiguous_graph_target": "ambiguous_graph_target",
    "topic_not_durable_decision": "topic_not_durable_decision",
    "graph_empty": "graph_empty",
    "graph_target_scan_truncated": "graph_target_scan_truncated",
    "graph_relationship_read_truncated": "graph_relationship_read_truncated",
    "graph_projection_truncated": "graph_projection_truncated",
    "cross_vault_relationship_omitted": "cross_vault_relationship_omitted",
    "graph_evidence_missing": "graph_evidence_missing",
    "deprecated_relationship_omitted": "deprecated_relationship_omitted",
}


def evidence_ref_from_metadata(reference: EvidenceReference) -> ContextEvidenceRef:
    return ContextEvidenceRef(
        vault_id=reference.vault_id,
        document_id=reference.document_id,
        chunk_id=reference.chunk_id,
    )


def context_warning_from_search(warning: SearchWarning) -> ContextPackWarning:
    evidence_refs: tuple[ContextEvidenceRef, ...] = ()
    if (
        warning.document_id is not None
        and warning.chunk_id is not None
        and len(warning.affected_vault_ids) == 1
    ):
        evidence_refs = (
            ContextEvidenceRef(
                vault_id=warning.affected_vault_ids[0],
                document_id=warning.document_id,
                chunk_id=warning.chunk_id,
            ),
        )
    return ContextPackWarning(
        code=SEARCH_WARNING_CODE_MAP.get(warning.code, warning.code),
        severity=_severity(warning.severity),
        message=warning.message,
        affected_vault_ids=warning.affected_vault_ids,
        evidence_refs=evidence_refs,
        scope_key=warning.scope_key,
        source_code=warning.code,
        source_kind="retrieval",
    )


def context_warning_from_retrieval(
    warning: RetrievalWarning,
    *,
    fallback_vault_id: str,
    evidence_refs: tuple[ContextEvidenceRef, ...] = (),
) -> ContextPackWarning:
    return ContextPackWarning(
        code=SEARCH_WARNING_CODE_MAP.get(warning.code, warning.code),
        severity=_severity(warning.severity),
        message=warning.message,
        affected_vault_ids=(fallback_vault_id,),
        evidence_refs=evidence_refs,
        source_code=warning.code,
        source_kind="retrieval",
    )


def context_warning_from_graph(warning: GraphRetrievalWarning) -> ContextPackWarning:
    return ContextPackWarning(
        code=GRAPH_WARNING_CODE_MAP.get(warning.code, warning.code),
        severity=_severity(warning.severity),
        message=warning.message,
        affected_vault_ids=warning.affected_vault_ids,
        scope_key=warning.scope_key,
        source_code=warning.code,
        source_kind="graph",
        entity_id=warning.entity_id,
        relationship_id=warning.relationship_id,
        evidence_ref_id=warning.evidence_ref_id,
    )


def budget_warning(
    *,
    code: str,
    message: str,
    affected_vault_ids: tuple[str, ...],
    evidence_refs: tuple[ContextEvidenceRef, ...] = (),
    scope_key: str | None = None,
) -> ContextPackWarning:
    return ContextPackWarning(
        code=code,
        severity="warning",
        message=message,
        affected_vault_ids=affected_vault_ids,
        evidence_refs=evidence_refs,
        scope_key=scope_key,
        source_code=code,
        source_kind="budget",
    )


def builder_warning(
    *,
    code: str,
    message: str,
    affected_vault_ids: tuple[str, ...],
    evidence_refs: tuple[ContextEvidenceRef, ...] = (),
    scope_key: str | None = None,
    recovery_hint: str | None = None,
) -> ContextPackWarning:
    return ContextPackWarning(
        code=code,
        severity="warning",
        message=message,
        affected_vault_ids=affected_vault_ids,
        evidence_refs=evidence_refs,
        scope_key=scope_key,
        source_code=code,
        source_kind="builder",
        recovery_hint=recovery_hint,
    )


def _severity(value: str) -> ContextPackWarningSeverity:
    if value not in {"info", "warning", "error"}:
        return "warning"
    return cast(ContextPackWarningSeverity, value)
