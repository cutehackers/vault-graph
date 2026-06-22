from __future__ import annotations

from collections.abc import Callable
from datetime import datetime

from vault_graph.errors import MemoryProjectionError
from vault_graph.ingestion.document_normalizer import DocumentSnapshot
from vault_graph.ingestion.vault_catalog import QueryScope, VaultCatalog
from vault_graph.memory.memory_models import (
    MemoryBackendRevision,
    MemoryClaimStatus,
    MemoryFreshness,
    MemoryItem,
    MemoryWarning,
    OpenQuestionsProjection,
    OpenQuestionsVault,
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

OPEN_HEADING_TERMS = ("open questions", "question", "follow-up", "follow up", "todo", "blocker", "revisit")
ACTIVE_STATUSES = ("open", "unresolved", "todo", "blocked", "revisit")
EXCLUDED_STATUSES = ("closed", "resolved", "done", "accepted", "superseded", "deprecated", "cancelled")
ISSUE_TYPES = ("issue", "question", "follow_up")


class IssueMemoryService:
    def __init__(
        self,
        *,
        catalog: VaultCatalog,
        source_reader: MemorySourceReader,
        status_service: MemoryStatusService,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._catalog = catalog
        self._source_reader = source_reader
        self._status_service = status_service
        self._clock = clock

    def open_questions(
        self,
        *,
        requested_scope: QueryScope,
        limit: int = 20,
    ) -> OpenQuestionsProjection:
        context = build_memory_request_context(
            catalog=self._catalog,
            source_reader=self._source_reader,
            status_service=self._status_service,
            requested_scope=requested_scope,
            clock=self._clock,
        )
        return self._open_questions_from_context(context=context, limit=limit)

    def _open_questions_from_context(
        self,
        *,
        context: MemoryRequestContext,
        limit: int = 20,
    ) -> OpenQuestionsProjection:
        _validate_limit(limit)
        vaults: list[OpenQuestionsVault] = []
        for group in context.documents_by_vault:
            warnings: list[MemoryWarning] = []
            items: list[MemoryItem] = []
            candidates = tuple(document for document in group.documents if _is_issue_candidate_document(document))
            candidate_cap = _candidate_read_limit(limit)
            if len(candidates) > candidate_cap:
                warnings.append(
                    _warning(
                        code="candidate_scan_truncated",
                        message=f"open-question candidate scan truncated to {candidate_cap} documents",
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
                OpenQuestionsVault(
                    vault_id=group.vault_id,
                    display_name=self._catalog.resolve(group.vault_id).display_name,
                    questions=tuple(items),
                    warnings=tuple(warnings),
                    store_revisions=_store_revisions_from_documents(
                        documents=group.documents,
                        vault_id=group.vault_id,
                        scope_key=_scope_key(group.scope),
                    ),
                    freshness=_freshness_from_status(context),
                )
            )
        return OpenQuestionsProjection(
            requested_scope=context.requested_scope,
            actual_scopes=context.actual_scopes,
            vaults=tuple(vaults),
            warnings=(),
            generated_at=context.generated_at,
        )

    def _item_for_document(self, *, document: DocumentSnapshot, rank: int) -> MemoryItem | None:
        status = _status(document)
        if status in EXCLUDED_STATUSES:
            return None
        read = self._read_with_preferred_heading(document=document)
        heading_matches = _matching_heading_chunk_ids(read)
        if _is_canonical_issue_document(document) and status in ACTIVE_STATUSES:
            claim_status: MemoryClaimStatus = "stated"
            warnings: tuple[MemoryWarning, ...] = ()
            signals = _document_issue_signals(document)
        elif status is None and heading_matches:
            claim_status = "heading_candidate"
            warnings = (
                _warning(
                    code="missing_issue_status",
                    message=f"open-question candidate has no explicit status: {document.path}",
                    affected_vault_ids=(document.vault_id,),
                ),
            )
            signals = (*_document_issue_signals(document), "heading:open_question")
        elif heading_matches and (status in ACTIVE_STATUSES or status is None):
            claim_status = "heading_candidate"
            warnings = (
                _warning(
                    code="candidate_open_question",
                    message=f"open-question candidate inferred from heading in {document.path}",
                    affected_vault_ids=(document.vault_id,),
                ),
            )
            signals = (*_document_issue_signals(document), "heading:open_question")
        else:
            return None
        if not read.evidence:
            return None
        title = _title(document)
        return MemoryItem(
            item_id=stable_memory_item_id(
                kind="open_question",
                vault_id=document.vault_id,
                document_id=document.document_id,
                chunk_id=read.evidence[0].chunk_id,
                title=title,
                status=status,
                claim_status=claim_status,
            ),
            kind="open_question",
            claim_status=claim_status,
            matched_signals=tuple(dict.fromkeys(signals)),
            document_resource_kinds=document_resource_kinds_for_document(document),
            title=title,
            summary=read.body_excerpt or title,
            vault_id=document.vault_id,
            path=document.path,
            status=status,
            rank=rank,
            evidence=read.evidence,
            warnings=warnings + read.warnings,
        )

    def _read_with_preferred_heading(self, *, document: DocumentSnapshot) -> MemoryDocumentRead:
        initial = self._source_reader.read_document(document=document, max_evidence_chunks=3)
        matched_chunk_ids = _matching_heading_chunk_ids(initial)
        if matched_chunk_ids and (not initial.evidence or initial.evidence[0].chunk_id != matched_chunk_ids[0]):
            return self._source_reader.read_document(
                document=document,
                max_evidence_chunks=3,
                preferred_chunk_ids=matched_chunk_ids,
            )
        return initial


def _is_issue_candidate_document(document: DocumentSnapshot) -> bool:
    if _status(document) in EXCLUDED_STATUSES:
        return False
    if _is_canonical_issue_document(document):
        return True
    text = f"{document.path} {_frontmatter_text(document)}".casefold()
    return any(term in text for term in OPEN_HEADING_TERMS)


def _is_canonical_issue_document(document: DocumentSnapshot) -> bool:
    return document.path.startswith("wiki/issues/") or _frontmatter_value(document, "type") in ISSUE_TYPES


def _document_issue_signals(document: DocumentSnapshot) -> tuple[str, ...]:
    signals: list[str] = []
    if document.path.startswith("wiki/issues/"):
        signals.append("path:wiki/issues")
    doc_type = _frontmatter_value(document, "type")
    if doc_type in ISSUE_TYPES:
        signals.append(f"frontmatter:type={doc_type}")
    status = _status(document)
    if status:
        signals.append(f"frontmatter:status={status}")
    text = document.path.casefold()
    for term in OPEN_HEADING_TERMS:
        if term in text:
            signals.append(f"path:{term}")
    return tuple(dict.fromkeys(signals or ("metadata:open_question_candidate",)))


def _matching_heading_chunk_ids(read: MemoryDocumentRead) -> tuple[str, ...]:
    matches = []
    for heading in read.headings:
        section = heading.section.casefold()
        if any(term in section for term in OPEN_HEADING_TERMS):
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
    for key in ("title", "name", "question"):
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
