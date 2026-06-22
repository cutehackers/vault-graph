from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from datetime import datetime
from typing import Protocol

from vault_graph.errors import MemoryProjectionError
from vault_graph.ingestion.document_normalizer import DocumentSnapshot
from vault_graph.ingestion.vault_catalog import QueryScope, VaultCatalog
from vault_graph.memory.memory_models import (
    DecisionMemoryProjection,
    DecisionMemoryVault,
    MemoryBackendRevision,
    MemoryClaimStatus,
    MemoryFreshness,
    MemoryItem,
    MemoryWarning,
    stable_memory_item_id,
)
from vault_graph.memory.memory_request_context import (
    MemoryRequestContext,
    MemoryStatusService,
    build_memory_request_context,
)
from vault_graph.memory.memory_source_reader import (
    MemoryDocumentRead,
    MemorySourceReader,
    document_resource_kinds_for_document,
)
from vault_graph.retrieval.graph_retrieval import DecisionTraceResponse, GraphOutputFormat

DECISION_HEADING_TERMS = ("decision", "alternatives", "tradeoff", "trade-off", "revisit")


class DecisionTraceProvider(Protocol):
    def decision_trace(
        self,
        *,
        topic: str,
        requested_scope: QueryScope,
        depth: int = 2,
        include_cross_vault: bool = False,
        limit: int = 10,
        output_format: GraphOutputFormat = "text",
    ) -> DecisionTraceResponse: ...


class DecisionMemoryService:
    def __init__(
        self,
        *,
        catalog: VaultCatalog,
        source_reader: MemorySourceReader,
        status_service: MemoryStatusService,
        decision_trace_provider_factory: Callable[[], DecisionTraceProvider] | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._catalog = catalog
        self._source_reader = source_reader
        self._status_service = status_service
        self._decision_trace_provider_factory = decision_trace_provider_factory
        self._clock = clock

    def list_decisions(
        self,
        *,
        requested_scope: QueryScope,
        topic: str | None = None,
        limit: int = 20,
        include_graph: bool = False,
    ) -> DecisionMemoryProjection:
        context = build_memory_request_context(
            catalog=self._catalog,
            source_reader=self._source_reader,
            status_service=self._status_service,
            requested_scope=requested_scope,
            clock=self._clock,
        )
        return self._list_decisions_from_context(
            context=context,
            topic=topic,
            limit=limit,
            include_graph=include_graph,
        )

    def _list_decisions_from_context(
        self,
        *,
        context: MemoryRequestContext,
        topic: str | None = None,
        limit: int = 20,
        include_graph: bool = False,
    ) -> DecisionMemoryProjection:
        _validate_limit(limit)
        vaults: list[DecisionMemoryVault] = []
        projection_warnings: list[MemoryWarning] = []
        for group in context.documents_by_vault:
            items: list[MemoryItem] = []
            warnings: list[MemoryWarning] = []
            candidates = tuple(document for document in group.documents if _is_decision_candidate_document(document))
            candidate_cap = _candidate_read_limit(limit)
            if len(candidates) > candidate_cap:
                warnings.append(
                    _warning(
                        code="candidate_scan_truncated",
                        message=f"decision candidate scan truncated to {candidate_cap} documents",
                        affected_vault_ids=(group.vault_id,),
                    )
                )
            for document in candidates[:candidate_cap]:
                item = self._item_for_document(document=document, rank=len(items) + 1)
                if item is not None:
                    items.append(item)
                if len(items) >= limit:
                    break
            vaults.append(
                DecisionMemoryVault(
                    vault_id=group.vault_id,
                    display_name=self._catalog.resolve(group.vault_id).display_name,
                    decisions=tuple(items),
                    warnings=tuple(warnings),
                    store_revisions=_store_revisions_from_documents(
                        documents=group.documents,
                        vault_id=group.vault_id,
                        scope_key=_scope_key(group.scope),
                    ),
                    freshness=_freshness_from_status(context),
                )
            )
        projection = DecisionMemoryProjection(
            requested_scope=context.requested_scope,
            actual_scopes=context.actual_scopes,
            topic=topic,
            vaults=tuple(vaults),
            warnings=tuple(projection_warnings),
            generated_at=context.generated_at,
        )
        if topic is not None and include_graph:
            return self._with_graph_enrichment(projection=projection, topic=topic, limit=limit)
        return projection

    def _item_for_document(self, *, document: DocumentSnapshot, rank: int) -> MemoryItem | None:
        claim_status: MemoryClaimStatus
        matched_signals: tuple[str, ...]
        item_warnings: tuple[MemoryWarning, ...] = ()
        canonical = _is_canonical_decision_document(document)
        if canonical:
            claim_status = "stated"
            matched_signals = _document_decision_signals(document)
        else:
            claim_status = "metadata_derived"
            matched_signals = _document_decision_signals(document)
        read = self._read_with_preferred_heading(document=document, heading_terms=DECISION_HEADING_TERMS)
        heading_matches = _matching_heading_chunk_ids(read, DECISION_HEADING_TERMS)
        if not canonical and heading_matches:
            claim_status = "heading_candidate"
            matched_signals = (*matched_signals, "heading:decision")
            item_warnings = (
                _warning(
                    code="candidate_decision",
                    message=f"decision candidate inferred from heading in {document.path}",
                    affected_vault_ids=(document.vault_id,),
                ),
            )
        if not read.evidence:
            return None
        evidence = read.evidence
        title = _title(document)
        return MemoryItem(
            item_id=stable_memory_item_id(
                kind="decision",
                vault_id=document.vault_id,
                document_id=document.document_id,
                chunk_id=evidence[0].chunk_id,
                title=title,
                status=_status(document),
                claim_status=claim_status,
            ),
            kind="decision",
            claim_status=claim_status,
            matched_signals=matched_signals,
            document_resource_kinds=document_resource_kinds_for_document(document),
            title=title,
            summary=read.body_excerpt or title,
            vault_id=document.vault_id,
            path=document.path,
            status=_status(document),
            rank=rank,
            evidence=evidence,
            warnings=item_warnings + read.warnings,
        )

    def _read_with_preferred_heading(
        self,
        *,
        document: DocumentSnapshot,
        heading_terms: tuple[str, ...],
    ) -> MemoryDocumentRead:
        initial = self._source_reader.read_document(document=document, max_evidence_chunks=3)
        matched_chunk_ids = _matching_heading_chunk_ids(initial, heading_terms)
        if matched_chunk_ids and (not initial.evidence or initial.evidence[0].chunk_id != matched_chunk_ids[0]):
            return self._source_reader.read_document(
                document=document,
                max_evidence_chunks=3,
                preferred_chunk_ids=matched_chunk_ids,
            )
        return initial

    def _with_graph_enrichment(
        self,
        *,
        projection: DecisionMemoryProjection,
        topic: str,
        limit: int,
    ) -> DecisionMemoryProjection:
        if self._decision_trace_provider_factory is None:
            return replace(
                projection,
                warnings=(
                    *projection.warnings,
                    _warning(
                        code="graph_decision_trace_unavailable",
                        message="decision graph enrichment is not configured",
                        affected_vault_ids=projection.requested_scope.vault_ids,
                    ),
                ),
            )
        try:
            trace = self._decision_trace_provider_factory().decision_trace(
                topic=topic,
                requested_scope=projection.requested_scope,
                depth=2,
                include_cross_vault=False,
                limit=limit,
                output_format="json",
            )
        except Exception as exc:
            return replace(
                projection,
                warnings=(
                    *projection.warnings,
                    _warning(
                        code="graph_decision_trace_unavailable",
                        message=str(exc),
                        affected_vault_ids=projection.requested_scope.vault_ids,
                    ),
                ),
            )
        graph_evidence_docs = {
            (evidence.vault_id, evidence.document_id) for step in trace.steps for evidence in step.evidence
        }
        enriched_vaults: list[DecisionMemoryVault] = []
        matched = False
        for vault in projection.vaults:
            decisions: list[MemoryItem] = []
            for item in vault.decisions:
                if any((evidence.vault_id, evidence.document_id) in graph_evidence_docs for evidence in item.evidence):
                    matched = True
                    decisions.append(
                        replace(
                            item,
                            matched_signals=tuple(
                                dict.fromkeys((*item.matched_signals, "graph_decision_trace"))
                            ),
                        )
                    )
                else:
                    decisions.append(item)
            enriched_vaults.append(replace(vault, decisions=tuple(decisions)))
        if not matched:
            return replace(
                projection,
                vaults=tuple(enriched_vaults),
                warnings=(
                    *projection.warnings,
                    _warning(
                        code="graph_decision_trace_unmatched",
                        message="decision trace did not match metadata-backed decision items",
                        affected_vault_ids=projection.requested_scope.vault_ids,
                    ),
                ),
            )
        return replace(projection, vaults=tuple(enriched_vaults))


def _is_decision_candidate_document(document: DocumentSnapshot) -> bool:
    if _is_canonical_decision_document(document):
        return True
    text = f"{document.path} {_frontmatter_text(document)}".casefold()
    return any(term in text for term in DECISION_HEADING_TERMS)


def _is_canonical_decision_document(document: DocumentSnapshot) -> bool:
    return (
        document.path.startswith("wiki/decisions/")
        or _frontmatter_value(document, "type") == "decision"
        or "decision" in document.frontmatter
    )


def _document_decision_signals(document: DocumentSnapshot) -> tuple[str, ...]:
    signals: list[str] = []
    if document.path.startswith("wiki/decisions/"):
        signals.append("path:wiki/decisions")
    if _frontmatter_value(document, "type") == "decision":
        signals.append("frontmatter:type=decision")
    if "decision" in document.frontmatter:
        signals.append("frontmatter:decision")
    text = document.path.casefold()
    for term in DECISION_HEADING_TERMS:
        if term in text:
            signals.append(f"path:{term}")
    return tuple(dict.fromkeys(signals or ("metadata:decision_candidate",)))


def _matching_heading_chunk_ids(read: MemoryDocumentRead, heading_terms: tuple[str, ...]) -> tuple[str, ...]:
    matches = []
    for heading in read.headings:
        section = heading.section.casefold()
        if any(term in section for term in heading_terms):
            matches.append(heading.chunk_id)
    return tuple(matches)


def _frontmatter_value(document: DocumentSnapshot, key: str) -> str:
    value = document.frontmatter.get(key)
    return str(value).strip().casefold() if value is not None else ""


def _frontmatter_text(document: DocumentSnapshot) -> str:
    return " ".join(f"{key} {value}" for key, value in document.frontmatter.items())


def _status(document: DocumentSnapshot) -> str | None:
    status = _frontmatter_value(document, "status")
    return status or None


def _title(document: DocumentSnapshot) -> str:
    for key in ("title", "name", "decision"):
        value = document.frontmatter.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return document.path.rsplit("/", 1)[-1].removesuffix(".md")


def _validate_limit(limit: int) -> None:
    if not isinstance(limit, int) or isinstance(limit, bool) or limit < 1 or limit > 50:
        raise MemoryProjectionError("invalid_memory_limit: limit must be between 1 and 50")


def _candidate_read_limit(limit: int) -> int:
    return min(max(limit * 10, 50), 250)


def _freshness_from_status(context: MemoryRequestContext) -> MemoryFreshness:
    if not context.status_report.metadata_ok or not context.status_report.metadata_schema_compatible:
        return "unavailable"
    return "fresh"


def _store_revisions_from_documents(
    *,
    documents: tuple[DocumentSnapshot, ...],
    vault_id: str,
    scope_key: str,
) -> tuple[MemoryBackendRevision, ...]:
    revisions = tuple(dict.fromkeys(document.index_revision for document in documents if document.index_revision))
    if not revisions:
        return (MemoryBackendRevision(kind="metadata", revision=None, vault_id=vault_id, scope_key=scope_key),)
    return tuple(
        MemoryBackendRevision(kind="metadata", revision=revision, vault_id=vault_id, scope_key=scope_key)
        for revision in revisions
    )


def _scope_key(scope: QueryScope) -> str:
    return f"{','.join(scope.vault_ids)}:{','.join(scope.content_scopes)}:cross={scope.include_cross_vault}"


def _warning(
    *,
    code: str,
    message: str,
    affected_vault_ids: tuple[str, ...],
    recovery_hint: str | None = None,
) -> MemoryWarning:
    return MemoryWarning(
        code=code,
        message=message,
        severity="warning",
        affected_vault_ids=affected_vault_ids,
        recovery_hint=recovery_hint,
    )
