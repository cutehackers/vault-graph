from __future__ import annotations

import hashlib
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import PurePosixPath
from typing import Protocol, cast

from vault_graph.context.context_pack import (
    CONTEXT_PACK_SCHEMA_VERSION,
    DEFAULT_CONTEXT_RETRIEVAL_LIMIT,
    DEFAULT_RETRIEVAL_POLICY_VERSION,
    ContextEvidence,
    ContextEvidenceRef,
    ContextPack,
    ContextPackActualScope,
    ContextPackBackend,
    ContextPackBackendUse,
    ContextPackItem,
    ContextPackItemType,
    ContextPackRequest,
    ContextPackSignal,
    ContextPackStoreRevision,
    ContextPackStoreRevisionKind,
    ContextPackVault,
    ContextPackVaultRevision,
    ContextPackWarning,
    context_scope_from_query_scopes,
)
from vault_graph.context.context_pack_serialization import with_computed_pack_id
from vault_graph.context.context_pack_warnings import (
    budget_warning,
    builder_warning,
    context_warning_from_retrieval,
    context_warning_from_search,
    evidence_ref_from_metadata,
)
from vault_graph.errors import ContextPackError
from vault_graph.ingestion.vault_catalog import QueryScope, VaultCatalog
from vault_graph.retrieval.retrieval_result import RetrievalResult
from vault_graph.retrieval.search_response import SearchOutputFormat, SearchResponse
from vault_graph.storage.interfaces.metadata_store import MetadataStore


class ContextPackBuilder(Protocol):
    def build(self, request: ContextPackRequest) -> ContextPack: ...


class ContextRetrievalService(Protocol):
    def search(
        self,
        *,
        query_text: str,
        requested_scope: QueryScope,
        limit: int = 10,
        output_format: SearchOutputFormat = "text",
        include_graph: bool = False,
        include_cross_vault: bool = False,
    ) -> SearchResponse: ...


class ContextEvidenceResolver(Protocol):
    def resolve(self, ref: ContextEvidenceRef) -> ResolvedContextEvidence | None: ...


@dataclass(frozen=True)
class ResolvedContextEvidence:
    ref: ContextEvidenceRef
    path: str
    section: str | None
    anchor: str | None
    content_hash: str
    raw_sha256: str | None
    metadata_index_revision: str
    vault_revision: str | None
    text: str
    token_count: int


class MetadataContextEvidenceResolver:
    def __init__(self, *, metadata_store: MetadataStore) -> None:
        self._metadata_store = metadata_store

    def resolve(self, ref: ContextEvidenceRef) -> ResolvedContextEvidence | None:
        chunk = self._metadata_store.resolve_chunk(vault_id=ref.vault_id, chunk_id=ref.chunk_id)
        evidence = self._metadata_store.resolve_chunk_evidence(
            vault_id=ref.vault_id,
            document_id=ref.document_id,
            chunk_id=ref.chunk_id,
        )
        if chunk is None or evidence is None:
            return None
        if (
            chunk.vault_id != evidence.vault_id
            or chunk.document_id != evidence.document_id
            or chunk.chunk_id != evidence.chunk_id
            or chunk.path != evidence.path
            or chunk.content_hash != evidence.content_hash
        ):
            return None
        metadata_revision = evidence.metadata_index_revision or chunk.index_revision or "unknown"
        return ResolvedContextEvidence(
            ref=ref,
            path=evidence.path,
            section=evidence.section,
            anchor=evidence.anchor,
            content_hash=evidence.content_hash,
            raw_sha256=evidence.raw_sha256,
            metadata_index_revision=metadata_revision,
            vault_revision=evidence.vault_revision,
            text=chunk.text,
            token_count=chunk.token_count,
        )


@dataclass(frozen=True)
class _PlannedItem:
    result: RetrievalResult
    item_type: ContextPackItemType
    evidence_refs: tuple[ContextEvidenceRef, ...]
    warnings: tuple[ContextPackWarning, ...]


class SearchContextPackBuilder:
    def __init__(
        self,
        *,
        catalog: VaultCatalog,
        retrieval_service: ContextRetrievalService,
        evidence_resolver: ContextEvidenceResolver,
        clock: Callable[[], datetime] | None = None,
        retrieval_policy_version: str = DEFAULT_RETRIEVAL_POLICY_VERSION,
    ) -> None:
        self._catalog = catalog
        self._retrieval_service = retrieval_service
        self._evidence_resolver = evidence_resolver
        self._clock = clock or (lambda: datetime.now(UTC))
        self._retrieval_policy_version = retrieval_policy_version

    def build(self, request: ContextPackRequest) -> ContextPack:
        response = self._retrieval_service.search(
            query_text=request.goal,
            requested_scope=request.requested_scope,
            limit=_retrieval_limit(request),
            output_format="json",
            include_graph=request.include_graph,
            include_cross_vault=request.include_cross_vault,
        )
        _validate_response(request=request, response=response)
        scope = context_scope_from_query_scopes(
            requested_scope=response.requested_scope,
            actual_scopes=response.actual_scopes,
        )
        pack_warnings = [context_warning_from_search(warning) for warning in response.warnings]
        planned_items = tuple(
            sorted(
                (_planned_item(result) for result in response.results),
                key=_planned_item_sort_key,
            )
        )
        evidence_by_ref: dict[ContextEvidenceRef, ContextEvidence] = {}
        resolved_cache: dict[ContextEvidenceRef, ResolvedContextEvidence | None] = {}
        kept_items: list[ContextPackItem] = []
        omitted_for_evidence_limit = 0
        omitted_for_token_limit = 0
        omitted_missing = 0
        used_tokens = 0

        for planned in planned_items:
            kept_refs: list[ContextEvidenceRef] = []
            item_warnings = list(planned.warnings)
            pending_evidence: dict[ContextEvidenceRef, ContextEvidence] = {}
            item_token_cost = 0
            omitted_by_budget = False
            for ref in planned.evidence_refs:
                if ref in evidence_by_ref:
                    kept_refs.append(ref)
                    continue
                if ref in pending_evidence:
                    kept_refs.append(ref)
                    continue
                if len(evidence_by_ref) + len(pending_evidence) >= request.budget.max_evidence_items:
                    omitted_for_evidence_limit += 1
                    omitted_by_budget = True
                    break
                resolved = _resolve_once(self._evidence_resolver, resolved_cache, ref)
                if resolved is None:
                    item_warnings.append(
                        builder_warning(
                            code="missing_evidence",
                            message=f"Metadata evidence could not be resolved: {ref.chunk_id}",
                            affected_vault_ids=(ref.vault_id,),
                            evidence_refs=(ref,),
                            recovery_hint="Run `vg index`.",
                        )
                    )
                    continue
                if not _is_valid_evidence_path(
                    path=resolved.path,
                    vault_id=ref.vault_id,
                    actual_scopes=response.actual_scopes,
                ):
                    pack_warnings.append(
                        builder_warning(
                            code="invalid_evidence_path",
                            message=(
                                "Evidence path must be Vault-relative and inside the actual scope: "
                                f"{resolved.path}"
                            ),
                            affected_vault_ids=(ref.vault_id,),
                            evidence_refs=(ref,),
                        )
                    )
                    continue
                context_evidence = _context_evidence_from_resolved(
                    resolved=resolved,
                    retrieval_reasons=_retrieval_reasons(planned.result),
                    max_excerpt_tokens=request.budget.max_excerpt_tokens,
                )
                if used_tokens + item_token_cost + context_evidence.excerpt_token_count > request.budget.max_tokens:
                    omitted_for_token_limit += 1
                    omitted_by_budget = True
                    break
                if context_evidence.truncated:
                    pack_warnings.extend(context_evidence.warnings)
                pending_evidence[ref] = context_evidence
                kept_refs.append(ref)
                item_token_cost += context_evidence.excerpt_token_count
            if omitted_by_budget:
                pack_warnings.extend(planned.warnings)
                continue
            if not kept_refs:
                omitted_missing += 1
                pack_warnings.extend(item_warnings)
                continue
            used_tokens += item_token_cost
            evidence_by_ref.update(pending_evidence)
            kept_items.append(
                _context_item_from_planned(
                    planned=planned,
                    evidence_refs=tuple(kept_refs),
                    warnings=tuple(item_warnings),
                )
            )

        pack_warnings.extend(
            _budget_warnings(
                omitted_for_evidence_limit=omitted_for_evidence_limit,
                omitted_for_token_limit=omitted_for_token_limit,
                affected_vault_ids=_affected_vault_ids(response.actual_scopes),
            )
        )
        budget = replace(
            request.budget,
            used_tokens=used_tokens,
            omitted_items=omitted_for_evidence_limit + omitted_for_token_limit + omitted_missing,
        )
        items_by_type = _items_by_type(tuple(kept_items))
        actual_scope_records = scope.actual_scopes
        generated_at = self._clock().isoformat()
        pack = ContextPack(
            context_pack_schema_version=CONTEXT_PACK_SCHEMA_VERSION,
            pack_id="",
            goal=request.goal.strip(),
            scope=scope,
            vaults=_vaults(catalog=self._catalog, actual_scopes=actual_scope_records),
            vault_revisions=_vault_revisions(
                catalog=self._catalog,
                actual_scopes=actual_scope_records,
                evidence=tuple(evidence_by_ref.values()),
            ),
            backend=_backend(response=response, include_graph=request.include_graph),
            store_revisions=_store_revisions(response=response, include_graph=request.include_graph),
            retrieval_policy_version=self._retrieval_policy_version,
            budget=budget,
            generated_at=generated_at,
            current_state=(),
            relevant_pages=items_by_type["page"],
            relevant_sources=items_by_type["source"],
            decisions=items_by_type["decision"],
            constraints=items_by_type["constraint"],
            open_questions=items_by_type["open_question"],
            warnings=tuple(_dedupe_warnings(pack_warnings)),
            evidence=tuple(evidence_by_ref.values()),
        )
        return with_computed_pack_id(pack)


def _retrieval_limit(request: ContextPackRequest) -> int:
    cap = max(request.budget.max_evidence_items * 4, DEFAULT_CONTEXT_RETRIEVAL_LIMIT)
    return min(request.retrieval_limit, cap)


def _planned_item(result: RetrievalResult) -> _PlannedItem:
    refs = tuple(evidence_ref_from_metadata(reference) for reference in result.evidence)
    item_warnings = tuple(
        context_warning_from_retrieval(warning, fallback_vault_id=result.vault_id, evidence_refs=refs)
        for warning in result.warnings
    )
    return _PlannedItem(result=result, item_type=_item_type(result), evidence_refs=refs, warnings=item_warnings)


def _planned_item_sort_key(item: _PlannedItem) -> tuple[int, int]:
    priority = {
        "decision": 0,
        "constraint": 1,
        "open_question": 2,
        "current_state": 3,
        "page": 4,
        "source": 5,
    }[item.item_type]
    return priority, item.result.rank


def _item_type(result: RetrievalResult) -> ContextPackItemType:
    if result.kind == "decision":
        return "decision"
    if result.kind == "constraint":
        return "constraint"
    if result.kind == "open_question":
        return "open_question"
    if result.evidence and result.evidence[0].path.startswith("raw/"):
        return "source"
    return "page"


def _context_item_from_planned(
    *,
    planned: _PlannedItem,
    evidence_refs: tuple[ContextEvidenceRef, ...],
    warnings: tuple[ContextPackWarning, ...],
) -> ContextPackItem:
    result = planned.result
    return ContextPackItem(
        item_id=_item_id(result, planned.item_type),
        item_type=planned.item_type,
        title=result.title,
        summary=result.summary,
        evidence_refs=evidence_refs,
        retrieval_signals=tuple(
            ContextPackSignal(
                kind=signal.kind,
                rank=signal.rank,
                score=signal.score,
                explanation=signal.explanation,
            )
            for signal in result.signals
        ),
        relationship_status=result.relationship_status,
        rank=result.rank,
        warnings=warnings,
    )


def _item_id(result: RetrievalResult, item_type: str) -> str:
    identity = "|".join(
        [item_type, result.result_id]
        + [f"{ref.vault_id}:{ref.document_id}:{ref.chunk_id}" for ref in result.evidence]
    )
    return hashlib.sha256(identity.encode("utf-8")).hexdigest()


def _resolve_once(
    resolver: ContextEvidenceResolver,
    cache: dict[ContextEvidenceRef, ResolvedContextEvidence | None],
    ref: ContextEvidenceRef,
) -> ResolvedContextEvidence | None:
    if ref not in cache:
        cache[ref] = resolver.resolve(ref)
    return cache[ref]


def _truncate_excerpt(*, text: str, max_tokens: int) -> tuple[str, int, bool]:
    tokens = text.split()
    if len(tokens) <= max_tokens:
        return text, len(tokens), False
    return " ".join(tokens[:max_tokens]), max_tokens, True


def _context_evidence_from_resolved(
    *,
    resolved: ResolvedContextEvidence,
    retrieval_reasons: tuple[str, ...],
    max_excerpt_tokens: int,
) -> ContextEvidence:
    excerpt, token_count, truncated = _truncate_excerpt(text=resolved.text, max_tokens=max_excerpt_tokens)
    warnings = (
        (
            budget_warning(
                code="excerpt_truncated",
                message=f"Evidence excerpt truncated to {max_excerpt_tokens} tokens.",
                affected_vault_ids=(resolved.ref.vault_id,),
                evidence_refs=(resolved.ref,),
            ),
        )
        if truncated
        else ()
    )
    return ContextEvidence(
        ref=resolved.ref,
        path=resolved.path,
        section=resolved.section,
        anchor=resolved.anchor,
        content_hash=resolved.content_hash,
        raw_sha256=resolved.raw_sha256,
        metadata_index_revision=resolved.metadata_index_revision,
        vault_revision=resolved.vault_revision,
        excerpt=excerpt,
        excerpt_token_count=token_count,
        truncated=truncated,
        retrieval_reasons=retrieval_reasons,
        warnings=warnings,
    )


def _retrieval_reasons(result: RetrievalResult) -> tuple[str, ...]:
    return tuple(signal.explanation for signal in result.signals)


def _budget_warnings(
    *,
    omitted_for_evidence_limit: int,
    omitted_for_token_limit: int,
    affected_vault_ids: tuple[str, ...],
) -> tuple[ContextPackWarning, ...]:
    warnings = []
    if omitted_for_evidence_limit:
        warnings.append(
            budget_warning(
                code="budget_omitted",
                message=f"{omitted_for_evidence_limit} result(s) omitted by evidence item budget.",
                affected_vault_ids=affected_vault_ids,
            )
        )
    if omitted_for_token_limit:
        warnings.append(
            budget_warning(
                code="budget_omitted",
                message=f"{omitted_for_token_limit} result(s) omitted by token budget.",
                affected_vault_ids=affected_vault_ids,
            )
        )
    return tuple(warnings)


def _items_by_type(items: tuple[ContextPackItem, ...]) -> dict[str, tuple[ContextPackItem, ...]]:
    return {
        "page": tuple(item for item in items if item.item_type == "page"),
        "source": tuple(item for item in items if item.item_type == "source"),
        "decision": tuple(item for item in items if item.item_type == "decision"),
        "constraint": tuple(item for item in items if item.item_type == "constraint"),
        "open_question": tuple(item for item in items if item.item_type == "open_question"),
    }


def _vaults(
    *,
    catalog: VaultCatalog,
    actual_scopes: tuple[ContextPackActualScope, ...],
) -> tuple[ContextPackVault, ...]:
    vault_ids = tuple(dict.fromkeys(vault_id for scope in actual_scopes for vault_id in scope.vault_ids))
    return tuple(
        ContextPackVault(
            vault_id=vault_id,
            display_name=catalog.resolve(vault_id).display_name,
        )
        for vault_id in vault_ids
    )


def _vault_revisions(
    *,
    catalog: VaultCatalog,
    actual_scopes: tuple[ContextPackActualScope, ...],
    evidence: tuple[ContextEvidence, ...],
) -> tuple[ContextPackVaultRevision, ...]:
    revisions_by_vault: dict[str, str] = {}
    for item in evidence:
        if item.vault_revision:
            revisions_by_vault.setdefault(item.ref.vault_id, item.vault_revision)
    vault_ids = tuple(dict.fromkeys(vault_id for scope in actual_scopes for vault_id in scope.vault_ids))
    return tuple(
        ContextPackVaultRevision(
            vault_id=vault_id,
            revision=revisions_by_vault.get(vault_id),
            revision_kind="git"
            if revisions_by_vault.get(vault_id) and catalog.resolve(vault_id).git_revision_policy == "head"
            else "unknown",
        )
        for vault_id in vault_ids
    )


def _backend(*, response: SearchResponse, include_graph: bool) -> ContextPackBackend:
    keyword_name = _first_signal_backend(response=response, kind="keyword") or "keyword"
    vector_name = _first_signal_backend(response=response, kind="vector") or (
        "vector" if _has_revision(response, "vector") else None
    )
    vector_used = bool(_first_signal_backend(response=response, kind="vector") or _has_revision(response, "vector"))
    graph_available = bool(_first_signal_backend(response=response, kind="graph") or _has_revision(response, "graph"))
    graph_name = _first_signal_backend(response=response, kind="graph") or (
        "graph" if _has_revision(response, "graph") else None
    )
    return ContextPackBackend(
        metadata_store=ContextPackBackendUse(name="metadata", used=True),
        keyword_index=ContextPackBackendUse(name=keyword_name, used=True),
        vector_store=ContextPackBackendUse(
            name=vector_name,
            used=vector_used,
        ),
        graph_store=ContextPackBackendUse(
            name=graph_name,
            used=include_graph and graph_available,
        ),
        graph_projection=ContextPackBackendUse(
            name="projection" if _has_revision(response, "projection") else None,
            used=include_graph and _has_revision(response, "projection"),
        ),
    )


def _first_signal_backend(*, response: SearchResponse, kind: str) -> str | None:
    for result in response.results:
        for signal in result.signals:
            if signal.kind == kind:
                return signal.backend
    return None


def _has_revision(response: SearchResponse, kind: str) -> bool:
    return any(revision.kind == kind for revision in response.store_revisions)


def _store_revisions(*, response: SearchResponse, include_graph: bool) -> tuple[ContextPackStoreRevision, ...]:
    allowed_kinds = (
        {"metadata", "keyword", "vector", "graph", "projection"}
        if include_graph
        else {"metadata", "keyword", "vector"}
    )
    return tuple(
        ContextPackStoreRevision(
            kind=cast(ContextPackStoreRevisionKind, revision.kind),
            revision=revision.revision,
            vault_id=revision.vault_id,
            scope_key=revision.scope_key,
        )
        for revision in response.store_revisions
        if revision.kind in allowed_kinds
    )


def _validate_response(*, request: ContextPackRequest, response: SearchResponse) -> None:
    if response.requested_scope != request.requested_scope:
        raise ContextPackError("response requested_scope must match the context pack request")
    requested_vault_ids = set(request.requested_scope.vault_ids)
    actual_vault_ids = {vault_id for scope in response.actual_scopes for vault_id in scope.vault_ids}
    if not actual_vault_ids <= requested_vault_ids:
        raise ContextPackError("response actual scope contains vault_id outside requested scope")
    for result in response.results:
        if result.vault_id not in actual_vault_ids:
            raise ContextPackError("retrieval result vault_id is outside actual scope")
        for evidence in result.evidence:
            if evidence.vault_id not in actual_vault_ids:
                raise ContextPackError("retrieval result evidence vault_id is outside actual scope")


def _affected_vault_ids(actual_scopes: tuple[QueryScope, ...]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(vault_id for scope in actual_scopes for vault_id in scope.vault_ids)) or ("unknown",)


def _is_valid_evidence_path(*, path: str, vault_id: str, actual_scopes: tuple[QueryScope, ...]) -> bool:
    posix_path = PurePosixPath(path)
    if posix_path.is_absolute() or ".." in posix_path.parts or path == "":
        return False
    return any(
        vault_id in scope.vault_ids and _path_is_inside_content_scopes(path=path, content_scopes=scope.content_scopes)
        for scope in actual_scopes
    )


def _path_is_inside_content_scopes(*, path: str, content_scopes: tuple[str, ...]) -> bool:
    return any(path == content_scope or path.startswith(f"{content_scope}/") for content_scope in content_scopes)


def _dedupe_warnings(warnings: list[ContextPackWarning]) -> tuple[ContextPackWarning, ...]:
    return tuple(dict.fromkeys(warnings))
