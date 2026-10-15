"""Resolve Vault evidence and explicitly find its graph owners without running search."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace
from pathlib import PurePosixPath
from typing import Literal

from vault_graph.errors import RetrievalContractError
from vault_graph.graph.graph_contracts import GraphEvidenceRef
from vault_graph.graph.graph_identity import graph_scope_key
from vault_graph.graph.graph_readiness import GraphReadiness
from vault_graph.ingestion.vault_catalog import QueryScope
from vault_graph.storage.interfaces.evidence_owner_lookup import EvidenceOwnerLookup, EvidenceOwnerRecord
from vault_graph.storage.interfaces.metadata_store import EvidenceReference, MetadataStore

EvidenceKey = tuple[str, str, str]
GraphOwnerKey = tuple[str, str, str]
LinkStatus = Literal["linked", "no_links", "missing_evidence", "not_ready", "not_processed"]
StopReason = Literal["completed", "result_limit", "not_ready", "revision_changed", "lookup_unavailable"]


@dataclass(frozen=True)
class EvidenceResolution:
    key: EvidenceKey
    evidence: EvidenceReference | None


@dataclass(frozen=True)
class EvidenceSourceRevision:
    kind: str
    revision: str
    scope: str = ""


@dataclass(frozen=True)
class GraphLinksRequest:
    keys: tuple[EvidenceKey, ...]
    actual_scopes: tuple[QueryScope, ...]
    include_cross_vault: bool
    max_keys: int
    limit: int


@dataclass(frozen=True)
class EvidenceGraphLink:
    owner: GraphOwnerKey
    key: EvidenceKey
    evidence_ref_id: str
    evidence: EvidenceReference
    graph_revision: str


@dataclass(frozen=True)
class GraphLinkOutcome:
    key: EvidenceKey
    status: LinkStatus
    key_complete: bool


@dataclass(frozen=True)
class GraphLinksResult:
    links: tuple[EvidenceGraphLink, ...]
    outcomes: tuple[GraphLinkOutcome, ...]
    coverage: Literal["complete", "partial"]
    stop_reason: StopReason
    source_revisions: tuple[EvidenceSourceRevision, ...]


class EvidenceLinker:
    def __init__(
        self,
        *,
        metadata_store: MetadataStore,
        owner_lookup: EvidenceOwnerLookup | None = None,
        readiness: Callable[[tuple[QueryScope, ...]], GraphReadiness] | None = None,
        revision_reader: Callable[[tuple[QueryScope, ...]], tuple[EvidenceSourceRevision, ...]] | None = None,
    ) -> None:
        self._metadata = metadata_store
        self._lookup = owner_lookup
        self._readiness = readiness
        self._revisions = revision_reader

    def resolve_evidence(self, keys: tuple[EvidenceKey, ...]) -> tuple[EvidenceResolution, ...]:
        """Preserve input positions. Consumer-specific filtering and warnings stay outside."""
        resolved: dict[EvidenceKey, EvidenceResolution] = {}
        for key in keys:
            _validate_key(key)
            if key not in resolved:
                evidence = self._metadata.resolve_chunk_evidence(vault_id=key[0], document_id=key[1], chunk_id=key[2])
                if evidence is not None and (
                    not isinstance(evidence, EvidenceReference)
                    or (evidence.vault_id, evidence.document_id, evidence.chunk_id) != key
                ):
                    raise RetrievalContractError("invalid_evidence_result")
                resolved[key] = EvidenceResolution(key, evidence)
        return tuple(resolved[key] for key in keys)

    def find_graph_links(self, request: GraphLinksRequest) -> GraphLinksResult:
        _validate_request(request)
        if not request.keys:
            return GraphLinksResult((), (), "complete", "completed", ())
        if self._lookup is None:
            return _unavailable(request, "lookup_unavailable", "not_processed")
        if self._readiness is None or self._revisions is None:
            return _unavailable(request, "not_ready", "not_ready")

        before = self._revisions(request.actual_scopes)
        if not before:
            return _unavailable(request, "not_ready", "not_ready")
        keys = tuple(dict.fromkeys(request.keys))
        evidence = {item.key: item.evidence for item in self.resolve_evidence(keys)}
        for item in evidence.values():
            if item is not None and not _path_allowed(item, request.actual_scopes):
                raise RetrievalContractError("evidence outside requested scope")
        readiness = self._readiness(request.actual_scopes)
        fresh = _fresh_scopes(readiness, request.actual_scopes)
        links: list[EvidenceGraphLink] = []
        outcomes: dict[EvidenceKey, GraphLinkOutcome] = {}
        stop: StopReason = "completed"
        rows_read = 0
        used_scopes: set[str] = set()
        for key in keys:
            if stop == "result_limit":
                outcomes[key] = GraphLinkOutcome(key, "not_processed", False)
                continue
            item = evidence[key]
            if item is None:
                outcomes[key] = GraphLinkOutcome(key, "missing_evidence", True)
                continue
            # Any unavailable owner scope can hide additional cross-Vault matches.
            relevant = (
                request.actual_scopes
                if request.include_cross_vault
                else tuple(scope for scope in request.actual_scopes if key[0] in scope.vault_ids)
            )
            if any(scope not in fresh for scope in relevant):
                outcomes[key] = GraphLinkOutcome(key, "not_ready", False)
                stop = "not_ready"
                continue
            budget = request.limit + 1 - rows_read
            if budget <= 0:
                outcomes[key] = GraphLinkOutcome(key, "not_processed", False)
                stop = "result_limit"
                continue
            rows = self._lookup.lookup_evidence_owners(
                vault_id=key[0],
                document_id=key[1],
                chunk_id=key[2],
                scopes=relevant,
                include_cross_vault=request.include_cross_vault,
                limit=budget,
            )
            _validate_rows(
                rows,
                key=key,
                evidence=item,
                scopes=relevant,
                request=request,
                budget=budget,
                readiness=readiness,
                source_revisions=before,
            )
            used_scopes.update(graph_scope_key(scope) for scope in relevant)
            used_scopes.update(graph_scope_key(replace(scope, include_cross_vault=False)) for scope in relevant)
            rows_read += len(rows)
            remaining = request.limit - len(links)
            selected = rows[:remaining]
            links.extend(
                EvidenceGraphLink(
                    (row.owner_kind, row.owner_vault_id, row.owner_id),
                    key,
                    row.evidence_ref.evidence_ref_id,
                    item,
                    row.graph_revision,
                )
                for row in selected
            )
            complete = len(rows) <= remaining
            outcomes[key] = GraphLinkOutcome(key, "linked" if selected else "no_links", complete)
            if not complete:
                # A lookahead-only match is not evidence of absence for this key.
                if not selected:
                    outcomes[key] = GraphLinkOutcome(key, "not_processed", False)
                stop = "result_limit"

        after = self._revisions(request.actual_scopes)
        if before != after or any(item.evidence != evidence[item.key] for item in self.resolve_evidence(keys)):
            return _unavailable(request, "revision_changed", "not_ready")
        result_outcomes = tuple(outcomes[key] for key in request.keys)
        coverage: Literal["complete", "partial"] = (
            "complete" if all(item.key_complete for item in result_outcomes) else "partial"
        )
        metadata_scopes = {
            graph_scope_key(scope) for scope in request.actual_scopes if any(key[0] in scope.vault_ids for key in keys)
        }
        provenance = tuple(
            row
            for row in before
            if (row.kind.startswith("metadata") and (not row.scope or row.scope in metadata_scopes))
            or (row.kind == "generation")
            or (row.kind.startswith("graph") and used_scopes and (not row.scope or row.scope in used_scopes))
        )
        return GraphLinksResult(tuple(links), result_outcomes, coverage, stop, provenance)


def _validate_key(key: EvidenceKey) -> None:
    if (
        not isinstance(key, tuple)
        or len(key) != 3
        or any(not isinstance(value, str) or not value.strip() for value in key)
    ):
        raise RetrievalContractError("evidence key requires vault, document and chunk IDs")


def _validate_request(request: GraphLinksRequest) -> None:
    if any(type(value) is not int or value <= 0 for value in (request.max_keys, request.limit)):
        raise RetrievalContractError("max_keys and limit must be positive integers")
    if not isinstance(request.keys, tuple) or len(request.keys) > request.max_keys:
        raise RetrievalContractError("evidence input exceeds max_keys")
    if not isinstance(request.actual_scopes, tuple) or not request.actual_scopes:
        raise RetrievalContractError("actual scopes are required")
    if type(request.include_cross_vault) is not bool:
        raise RetrievalContractError("include_cross_vault must be boolean")
    for scope in request.actual_scopes:
        if not isinstance(scope, QueryScope) or len(scope.vault_ids) != 1 or not scope.content_scopes:
            raise RetrievalContractError("actual scopes must be per-Vault scopes")
    allowed = {scope.vault_ids[0] for scope in request.actual_scopes}
    for key in request.keys:
        _validate_key(key)
        if key[0] not in allowed:
            raise RetrievalContractError("evidence outside requested scope")


def _path_allowed(evidence: EvidenceReference, scopes: tuple[QueryScope, ...]) -> bool:
    path = PurePosixPath(evidence.path)
    if path.is_absolute() or ".." in path.parts or "\\" in evidence.path:
        return False
    return any(
        evidence.vault_id in scope.vault_ids
        and any(
            path == PurePosixPath(prefix) or PurePosixPath(prefix) in path.parents for prefix in scope.content_scopes
        )
        for scope in scopes
    )


def _fresh_scopes(readiness: GraphReadiness, scopes: tuple[QueryScope, ...]) -> tuple[QueryScope, ...]:
    if not (readiness.backend_available and readiness.schema_compatible and readiness.graph_extraction_spec_compatible):
        return ()
    rows = {(row.vault_id, row.actual_scope): row for row in readiness.scope_readiness}
    return tuple(
        scope
        for scope in scopes
        if (row := rows.get((scope.vault_ids[0], graph_scope_key(scope)))) is not None
        and row.freshness in {"fresh", "empty"}
    )


def _validate_rows(
    rows: tuple[EvidenceOwnerRecord, ...],
    *,
    key: EvidenceKey,
    evidence: EvidenceReference,
    scopes: tuple[QueryScope, ...],
    request: GraphLinksRequest,
    budget: int,
    readiness: GraphReadiness,
    source_revisions: tuple[EvidenceSourceRevision, ...],
) -> None:
    invalid = RetrievalContractError("invalid_lookup_result")
    if not isinstance(rows, tuple) or len(rows) > budget:
        raise invalid
    identities: list[tuple[str, str, str, str]] = []
    allowed = {scope.vault_ids[0] for scope in scopes}
    scope_revisions = {(row.vault_id, row.actual_scope): row.last_graph_revision for row in readiness.scope_readiness}
    allowed_scope_keys = {
        (scope.vault_ids[0], graph_scope_key(candidate))
        for scope in scopes
        for candidate in (scope, replace(scope, include_cross_vault=False))
    }
    for row in rows:
        if not isinstance(row, EvidenceOwnerRecord) or not isinstance(row.evidence_ref, GraphEvidenceRef):
            raise invalid
        ref = row.evidence_ref
        if any(
            not isinstance(value, str) or not value.strip()
            for value in (
                row.owner_kind,
                row.owner_vault_id,
                row.owner_id,
                row.graph_revision,
                row.scope_key,
                row.scope_revision,
                ref.evidence_ref_id,
                ref.owner_kind,
                ref.owner_vault_id,
                ref.owner_id,
                ref.evidence_vault_id,
                ref.document_id,
                ref.chunk_id,
                ref.content_hash,
            )
        ):
            raise invalid
        owner = (row.owner_kind, row.owner_vault_id, row.owner_id)
        if (
            row.owner_kind not in {"entity", "relationship"}
            or row.owner_vault_id not in allowed
            or (row.owner_vault_id, row.scope_key) not in allowed_scope_keys
            or next(
                (item.revision for item in source_revisions if item.kind == "graph" and item.scope == row.scope_key),
                scope_revisions.get((row.owner_vault_id, row.scope_key)),
            )
            != row.scope_revision
            or (ref.owner_kind, ref.owner_vault_id, ref.owner_id) != owner
            or (ref.evidence_vault_id, ref.document_id, ref.chunk_id) != key
            or ref.content_hash != evidence.content_hash
            or (ref.path is not None and ref.path != evidence.path)
            or (not request.include_cross_vault and row.owner_vault_id != key[0])
        ):
            raise invalid
        if row.owner_kind == "relationship" and (
            not isinstance(row.source_vault_id, str)
            or not isinstance(row.target_vault_id, str)
            or row.source_vault_id != row.owner_vault_id
            or row.target_vault_id not in allowed
            or not isinstance(row.source_entity_id, str)
            or not row.source_entity_id.strip()
            or not isinstance(row.target_entity_id, str)
            or not row.target_entity_id.strip()
            or (not request.include_cross_vault and row.source_vault_id != row.target_vault_id)
        ):
            raise invalid
        identities.append((*owner, ref.evidence_ref_id))
    if identities != sorted(set(identities)):
        raise invalid


def _unavailable(request: GraphLinksRequest, reason: StopReason, status: LinkStatus) -> GraphLinksResult:
    return GraphLinksResult(
        (), tuple(GraphLinkOutcome(key, status, False) for key in request.keys), "partial", reason, ()
    )
