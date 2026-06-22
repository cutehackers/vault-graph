from __future__ import annotations

from collections.abc import Callable
from datetime import datetime

from vault_graph.errors import MemoryProjectionError
from vault_graph.ingestion.document_normalizer import DocumentSnapshot
from vault_graph.ingestion.vault_catalog import QueryScope, VaultCatalog
from vault_graph.memory.decision_memory import DecisionMemoryService
from vault_graph.memory.issue_memory import IssueMemoryService
from vault_graph.memory.memory_models import (
    MemoryBackendRevision,
    MemoryClaimStatus,
    MemoryFreshness,
    MemoryItem,
    MemoryItemKind,
    MemoryWarning,
    ProjectMemoryProjection,
    ProjectMemoryVault,
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

CURRENT_STATE_TYPES = ("project_status", "status", "roadmap", "plan", "overview")
CURRENT_STATE_PATH_TERMS = ("status", "roadmap", "plan", "overview")
CONSTRAINT_TERMS = ("constraint", "policy", "boundary", "invariant", "non-goal")
CONSTRAINT_PATH_TERMS = ("policy", "decision", "convention", "boundary")
PRIORITY_TERMS = ("next", "priorities", "roadmap", "implementation order", "todo")
PRIORITY_FRONTMATTER_TERMS = ("priority", "next", "roadmap", "phase")
STALE_STATUSES = ("stale", "deprecated", "superseded")
STALE_PATH_TERMS = ("deprecated", "superseded")


class ProjectMemoryService:
    def __init__(
        self,
        *,
        catalog: VaultCatalog,
        source_reader: MemorySourceReader,
        decision_service: DecisionMemoryService,
        issue_service: IssueMemoryService,
        status_service: MemoryStatusService,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._catalog = catalog
        self._source_reader = source_reader
        self._decision_service = decision_service
        self._issue_service = issue_service
        self._status_service = status_service
        self._clock = clock

    def summarize(
        self,
        *,
        requested_scope: QueryScope,
        limit: int = 10,
    ) -> ProjectMemoryProjection:
        _validate_limit(limit)
        context = build_memory_request_context(
            catalog=self._catalog,
            source_reader=self._source_reader,
            status_service=self._status_service,
            requested_scope=requested_scope,
            clock=self._clock,
        )
        decisions = self._decision_service._list_decisions_from_context(
            context=context,
            include_graph=False,
            limit=limit,
        )
        questions = self._issue_service._open_questions_from_context(context=context, limit=limit)
        decisions_by_vault = {vault.vault_id: vault for vault in decisions.vaults}
        questions_by_vault = {vault.vault_id: vault for vault in questions.vaults}
        vaults: list[ProjectMemoryVault] = []
        for group in context.documents_by_vault:
            project_groups, project_warnings = self._project_groups_for_vault(
                vault_id=group.vault_id,
                documents=group.documents,
                limit=limit,
            )
            decision_vault = decisions_by_vault.get(group.vault_id)
            question_vault = questions_by_vault.get(group.vault_id)
            warnings = [
                *project_warnings,
                *(decision_vault.warnings if decision_vault is not None else ()),
                *(question_vault.warnings if question_vault is not None else ()),
            ]
            if not any(
                (
                    project_groups["current_state"],
                    decision_vault.decisions if decision_vault is not None else (),
                    question_vault.questions if question_vault is not None else (),
                    project_groups["constraints"],
                    project_groups["next_priorities"],
                    project_groups["stale_areas"],
                )
            ):
                warnings.append(
                    _warning(
                        code="no_memory_items_found",
                        message="no project memory items found for selected scope",
                        affected_vault_ids=(group.vault_id,),
                    )
                )
            vaults.append(
                ProjectMemoryVault(
                    vault_id=group.vault_id,
                    display_name=self._catalog.resolve(group.vault_id).display_name,
                    current_state=project_groups["current_state"],
                    decisions=decision_vault.decisions if decision_vault is not None else (),
                    open_questions=question_vault.questions if question_vault is not None else (),
                    constraints=project_groups["constraints"],
                    next_priorities=project_groups["next_priorities"],
                    stale_areas=project_groups["stale_areas"],
                    warnings=tuple(warnings),
                    store_revisions=_store_revisions_from_documents(
                        documents=group.documents,
                        vault_id=group.vault_id,
                        scope_key=_scope_key(group.scope),
                    ),
                    freshness=_freshness_from_status(context),
                )
            )
        return ProjectMemoryProjection(
            requested_scope=context.requested_scope,
            actual_scopes=context.actual_scopes,
            vaults=tuple(vaults),
            warnings=(*decisions.warnings, *questions.warnings),
            generated_at=context.generated_at,
        )

    def _project_groups_for_vault(
        self,
        *,
        vault_id: str,
        documents: tuple[DocumentSnapshot, ...],
        limit: int,
    ) -> tuple[dict[str, tuple[MemoryItem, ...]], tuple[MemoryWarning, ...]]:
        groups: dict[str, list[MemoryItem]] = {
            "current_state": [],
            "constraints": [],
            "next_priorities": [],
            "stale_areas": [],
        }
        warnings: list[MemoryWarning] = []
        candidates: list[tuple[DocumentSnapshot, dict[MemoryItemKind, MemoryClaimStatus]]] = []
        for document in documents:
            if _is_root_readme(document):
                continue
            matches = _project_matches(document)
            if not matches:
                continue
            candidates.append((document, matches))
        candidate_cap = _candidate_read_limit(limit)
        if len(candidates) > candidate_cap:
            warnings.append(
                _warning(
                    code="candidate_scan_truncated",
                    message=f"project memory candidate scan truncated to {candidate_cap} documents",
                    affected_vault_ids=(vault_id,),
                )
            )
        for document, matches in candidates[:candidate_cap]:
            active_matches = {
                kind: claim_status
                for kind, claim_status in matches.items()
                if len(groups[_group_name_for_kind(kind)]) < limit
            }
            if not active_matches:
                continue
            read = self._read_with_preferred_heading(document=document, matches=active_matches)
            if not read.evidence:
                continue
            for group_name, kind in (
                ("current_state", "current_state"),
                ("constraints", "constraint"),
                ("next_priorities", "next_priority"),
                ("stale_areas", "stale_area"),
            ):
                if kind not in matches or len(groups[group_name]) >= limit:
                    continue
                groups[group_name].append(
                    _memory_item_for_project_document(
                        document=document,
                        read=read,
                        kind=kind,
                        rank=len(groups[group_name]) + 1,
                        claim_status=matches[kind],
                        ambiguous=len(matches) > 1,
                    )
                )
        return {key: tuple(value) for key, value in groups.items()}, tuple(warnings)

    def _read_with_preferred_heading(
        self,
        *,
        document: DocumentSnapshot,
        matches: dict[MemoryItemKind, MemoryClaimStatus],
    ) -> MemoryDocumentRead:
        initial = self._source_reader.read_document(document=document, max_evidence_chunks=3)
        terms: list[str] = []
        if "constraint" in matches:
            terms.extend(CONSTRAINT_TERMS)
        if "next_priority" in matches:
            terms.extend(PRIORITY_TERMS)
        if "stale_area" in matches:
            terms.extend(STALE_PATH_TERMS)
        matched_chunk_ids = _matching_heading_chunk_ids(initial, tuple(terms))
        if matched_chunk_ids and (not initial.evidence or initial.evidence[0].chunk_id != matched_chunk_ids[0]):
            return self._source_reader.read_document(
                document=document,
                max_evidence_chunks=3,
                preferred_chunk_ids=matched_chunk_ids,
            )
        return initial


def _project_matches(document: DocumentSnapshot) -> dict[MemoryItemKind, MemoryClaimStatus]:
    matches: dict[MemoryItemKind, MemoryClaimStatus] = {}
    doc_type = _frontmatter_value(document, "type")
    status = _status(document)
    path = document.path.casefold()
    frontmatter_text = _frontmatter_text(document).casefold()
    if doc_type in CURRENT_STATE_TYPES or any(term in path for term in CURRENT_STATE_PATH_TERMS):
        matches["current_state"] = "metadata_derived"
    if (
        any(term in document.frontmatter for term in ("constraint", "policy", "boundary", "invariant"))
        or any(term in path for term in CONSTRAINT_PATH_TERMS)
        or any(term in frontmatter_text for term in CONSTRAINT_TERMS)
    ):
        matches["constraint"] = "metadata_derived"
    if (
        any(term in document.frontmatter for term in PRIORITY_FRONTMATTER_TERMS)
        or any(term in path for term in ("roadmap", "todo"))
        or any(term in frontmatter_text for term in PRIORITY_FRONTMATTER_TERMS)
    ):
        matches["next_priority"] = "metadata_derived"
    if status in STALE_STATUSES or any(term in path for term in STALE_PATH_TERMS):
        matches["stale_area"] = "metadata_derived"
    return matches


def _group_name_for_kind(kind: MemoryItemKind) -> str:
    if kind == "current_state":
        return "current_state"
    if kind == "constraint":
        return "constraints"
    if kind == "next_priority":
        return "next_priorities"
    if kind == "stale_area":
        return "stale_areas"
    raise MemoryProjectionError(f"unsupported_project_memory_kind: {kind}")


def _candidate_read_limit(limit: int) -> int:
    return min(max(limit * 10, 50), 250)


def _memory_item_for_project_document(
    *,
    document: DocumentSnapshot,
    read: MemoryDocumentRead,
    kind: MemoryItemKind,
    rank: int,
    claim_status: MemoryClaimStatus,
    ambiguous: bool,
) -> MemoryItem:
    title = _title(document)
    warnings = read.warnings
    if ambiguous:
        warnings = (
            _warning(
                code="ambiguous_classification",
                message=f"document matched multiple project memory groups: {document.path}",
                affected_vault_ids=(document.vault_id,),
            ),
            *warnings,
        )
    return MemoryItem(
        item_id=stable_memory_item_id(
            kind=kind,
            vault_id=document.vault_id,
            document_id=document.document_id,
            chunk_id=read.evidence[0].chunk_id,
            title=title,
            status=_status(document),
            claim_status=claim_status,
        ),
        kind=kind,
        claim_status=claim_status,
        matched_signals=_project_signals(document=document, kind=kind),
        document_resource_kinds=document_resource_kinds_for_document(document),
        title=title,
        summary=read.body_excerpt or title,
        vault_id=document.vault_id,
        path=document.path,
        status=_status(document),
        rank=rank,
        evidence=read.evidence,
        warnings=warnings,
    )


def _project_signals(*, document: DocumentSnapshot, kind: MemoryItemKind) -> tuple[str, ...]:
    signals = [f"project:{kind}"]
    doc_type = _frontmatter_value(document, "type")
    if doc_type:
        signals.append(f"frontmatter:type={doc_type}")
    status = _status(document)
    if status:
        signals.append(f"frontmatter:status={status}")
    return tuple(signals)


def _matching_heading_chunk_ids(read: MemoryDocumentRead, heading_terms: tuple[str, ...]) -> tuple[str, ...]:
    if not heading_terms:
        return ()
    matches = []
    for heading in read.headings:
        section = heading.section.casefold()
        if any(term in section for term in heading_terms):
            matches.append(heading.chunk_id)
    return tuple(matches)


def _is_root_readme(document: DocumentSnapshot) -> bool:
    return document.path.casefold() == "readme.md"


def _frontmatter_value(document: DocumentSnapshot, key: str) -> str:
    value = document.frontmatter.get(key)
    return str(value).strip().casefold() if value is not None else ""


def _frontmatter_text(document: DocumentSnapshot) -> str:
    return " ".join(f"{key} {value}" for key, value in document.frontmatter.items())


def _status(document: DocumentSnapshot) -> str | None:
    status = _frontmatter_value(document, "status")
    return status or None


def _title(document: DocumentSnapshot) -> str:
    for key in ("title", "name"):
        value = document.frontmatter.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return document.path.rsplit("/", 1)[-1].removesuffix(".md")


def _validate_limit(limit: int) -> None:
    if not isinstance(limit, int) or isinstance(limit, bool) or limit < 1 or limit > 50:
        raise MemoryProjectionError("invalid_memory_limit: limit must be between 1 and 50")


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
