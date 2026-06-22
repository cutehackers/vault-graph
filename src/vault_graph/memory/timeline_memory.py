from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Literal

from vault_graph.errors import MemoryProjectionError, MetadataStoreError
from vault_graph.ingestion.document_normalizer import DocumentSnapshot
from vault_graph.ingestion.query_scope_resolution import actual_query_scopes
from vault_graph.ingestion.vault_catalog import QueryScope, VaultCatalog
from vault_graph.memory.memory_models import MemoryBackendRevision, MemoryWarning, MemoryWarningSeverity
from vault_graph.memory.memory_request_context import MemoryStatusService
from vault_graph.storage.interfaces.metadata_store import MetadataStore

if TYPE_CHECKING:
    from vault_graph.app.index_service import StatusReport

TimelineOrigin = Literal["document_snapshot_change", "index_change", "projection_change", "warning"]
TimelineSourceKind = Literal["document", "metadata_status", "vector_status", "graph_status"]
TimelineFreshness = Literal["fresh", "stale", "degraded", "unavailable", "unknown"]

TIMELINE_ORIGINS = ("document_snapshot_change", "index_change", "projection_change", "warning")
TIMELINE_SOURCE_KINDS = ("document", "metadata_status", "vector_status", "graph_status")
TIMELINE_FRESHNESS = ("fresh", "stale", "degraded", "unavailable", "unknown")


@dataclass(frozen=True)
class TimelineEvidenceRef:
    source_kind: TimelineSourceKind
    vault_id: str
    document_id: str | None = None
    chunk_id: str | None = None
    path: str | None = None
    content_hash: str | None = None
    raw_sha256: str | None = None
    metadata_index_revision: str | None = None
    vault_revision: str | None = None
    backend_kind: str | None = None
    backend_revision: str | None = None
    scope_key: str | None = None

    def __post_init__(self) -> None:
        _require_one_of(self.source_kind, "source_kind", TIMELINE_SOURCE_KINDS)
        _require_non_empty_string(self.vault_id, "vault_id")
        if self.source_kind == "document":
            for field_name in ("document_id", "path", "content_hash"):
                _require_non_empty_string(getattr(self, field_name), field_name)
            return
        for field_name in ("backend_kind", "scope_key"):
            _require_non_empty_string(getattr(self, field_name), field_name)


@dataclass(frozen=True)
class TimelineItem:
    item_id: str
    origin: TimelineOrigin
    title: str
    summary: str
    vault_id: str
    occurred_at: str | None
    sort_key: str
    evidence: tuple[TimelineEvidenceRef, ...]
    store_revisions: tuple[MemoryBackendRevision, ...]
    warnings: tuple[MemoryWarning, ...]

    def __post_init__(self) -> None:
        for field_name in ("item_id", "title", "summary", "vault_id", "sort_key"):
            _require_non_empty_string(getattr(self, field_name), field_name)
        _require_one_of(self.origin, "origin", TIMELINE_ORIGINS)
        _require_tuple(self.evidence, "evidence")
        _require_tuple(self.store_revisions, "store_revisions")
        _require_tuple(self.warnings, "warnings")
        if self.origin != "warning" and not self.evidence:
            raise MemoryProjectionError("TimelineItem.evidence must contain at least one evidence ref")
        if self.origin == "warning" and not self.warnings:
            raise MemoryProjectionError("warning timeline items must contain at least one warning")
        for evidence in self.evidence:
            if not isinstance(evidence, TimelineEvidenceRef):
                raise MemoryProjectionError("evidence must contain TimelineEvidenceRef values")
        for revision in self.store_revisions:
            if not isinstance(revision, MemoryBackendRevision):
                raise MemoryProjectionError("store_revisions must contain MemoryBackendRevision values")
        for warning in self.warnings:
            if not isinstance(warning, MemoryWarning):
                raise MemoryProjectionError("warnings must contain MemoryWarning values")
        if not self.item_id.startswith(f"timeline:{self.origin}:") or len(self.item_id.rsplit(":", 1)[-1]) != 24:
            raise MemoryProjectionError("item_id must use timeline:<origin>:<24 hex chars>")


@dataclass(frozen=True)
class TimelineVault:
    vault_id: str
    display_name: str
    items: tuple[TimelineItem, ...]
    warnings: tuple[MemoryWarning, ...]
    store_revisions: tuple[MemoryBackendRevision, ...]
    freshness: TimelineFreshness

    def __post_init__(self) -> None:
        _require_non_empty_string(self.vault_id, "vault_id")
        _require_non_empty_string(self.display_name, "display_name")
        _require_tuple(self.items, "items")
        _require_tuple(self.warnings, "warnings")
        _require_tuple(self.store_revisions, "store_revisions")
        _require_one_of(self.freshness, "freshness", TIMELINE_FRESHNESS)


@dataclass(frozen=True)
class RecentChangesProjection:
    requested_scope: QueryScope
    actual_scopes: tuple[QueryScope, ...]
    since: str | None
    limit: int
    vaults: tuple[TimelineVault, ...]
    warnings: tuple[MemoryWarning, ...]
    generated_at: str

    def __post_init__(self) -> None:
        _require_tuple(self.actual_scopes, "actual_scopes")
        _require_tuple(self.vaults, "vaults")
        _require_tuple(self.warnings, "warnings")
        _require_non_empty_string(self.generated_at, "generated_at")
        if self.limit < 1 or self.limit > 50:
            raise MemoryProjectionError("invalid_memory_limit: limit must be between 1 and 50")


class TimelineMemoryService:
    def __init__(
        self,
        *,
        catalog: VaultCatalog,
        metadata_store: MetadataStore,
        status_service: MemoryStatusService,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._catalog = catalog
        self._metadata_store = metadata_store
        self._status_service = status_service
        self._clock = clock or _utc_now

    def recent_changes(
        self,
        *,
        requested_scope: QueryScope,
        since: str | None = None,
        limit: int = 20,
    ) -> RecentChangesProjection:
        if limit < 1 or limit > 50:
            raise MemoryProjectionError("invalid_memory_limit: limit must be between 1 and 50")
        normalized_since = parse_timeline_since(since)
        actual_scopes = actual_query_scopes(catalog=self._catalog, scope=requested_scope)
        generated_at = self._clock().isoformat()
        vaults: list[TimelineVault] = []
        projection_warnings: list[MemoryWarning] = []
        excluded_untimestamped = False
        for actual_scope in actual_scopes:
            report = self._status_service.status(scope=actual_scope)
            if not report.metadata_ok or not report.metadata_schema_compatible:
                raise MemoryProjectionError(f"metadata_unavailable: {report.metadata_message}")
            try:
                documents = self._metadata_store.list_recent_documents(
                    actual_scope,
                    since=normalized_since,
                    limit=limit,
                )
            except (MetadataStoreError, OSError) as exc:
                raise MemoryProjectionError(f"metadata_unavailable: {exc}") from exc
            vault, skipped = self._timeline_vault(
                actual_scope=actual_scope,
                report=report,
                documents=documents,
                since=normalized_since,
                limit=limit,
            )
            vaults.append(vault)
            excluded_untimestamped = excluded_untimestamped or skipped
        if excluded_untimestamped:
            projection_warnings.append(
                _warning(
                    code="timeline_items_without_timestamps_excluded",
                    message="Timeline items without explicit timestamps were excluded by the since filter.",
                    severity="info",
                    affected_vault_ids=tuple(scope.vault_ids[0] for scope in actual_scopes),
                    recovery_hint="Re-index the selected scope to refresh indexed timestamps.",
                )
            )
        return RecentChangesProjection(
            requested_scope=requested_scope,
            actual_scopes=actual_scopes,
            since=normalized_since,
            limit=limit,
            vaults=tuple(vaults),
            warnings=tuple(projection_warnings),
            generated_at=generated_at,
        )

    def _timeline_vault(
        self,
        *,
        actual_scope: QueryScope,
        report: StatusReport,
        documents: tuple[DocumentSnapshot, ...],
        since: str | None,
        limit: int,
    ) -> tuple[TimelineVault, bool]:
        vault_id = actual_scope.vault_ids[0]
        entry = self._catalog.resolve(vault_id)
        items = [
            *(_document_item(document) for document in documents),
            _metadata_status_item(vault_id=vault_id, scope_key=_scope_key(actual_scope)),
            *_vector_items(report=report, vault_id=vault_id),
            *_graph_items(report=report, vault_id=vault_id),
        ]
        filtered, skipped_untimestamped = _filter_and_limit_items(items=tuple(items), since=since, limit=limit)
        warnings = tuple(warning for item in filtered for warning in item.warnings)
        return (
            TimelineVault(
                vault_id=vault_id,
                display_name=entry.display_name,
                items=filtered,
                warnings=warnings,
                store_revisions=_vault_revisions(filtered),
                freshness=_freshness_for_report(report),
            ),
            skipped_untimestamped,
        )


def parse_timeline_since(value: str | None) -> str | None:
    if value is None:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise MemoryProjectionError("invalid_timeline_since: use an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC).isoformat()


def stable_timeline_item_id(
    *,
    origin: TimelineOrigin,
    vault_id: str,
    source_kind: TimelineSourceKind,
    document_id: str | None,
    backend_kind: str | None,
    path_or_scope: str | None,
    revision: str | None,
    occurred_at: str | None,
) -> str:
    payload = {
        "origin": origin,
        "vault_id": vault_id,
        "source_kind": source_kind,
        "document_id": document_id,
        "backend_kind": backend_kind,
        "path_or_scope": path_or_scope,
        "revision": revision,
        "occurred_at": occurred_at,
    }
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
    return f"timeline:{origin}:{digest[:24]}"


def _document_item(document: DocumentSnapshot) -> TimelineItem:
    occurred_at = document.last_indexed_at or document.last_seen_at
    revision = MemoryBackendRevision(
        kind="metadata",
        revision=document.index_revision,
        vault_id=document.vault_id,
        scope_key=document.path.split("/", 1)[0],
    )
    return TimelineItem(
        item_id=stable_timeline_item_id(
            origin="document_snapshot_change",
            vault_id=document.vault_id,
            source_kind="document",
            document_id=document.document_id,
            backend_kind=None,
            path_or_scope=document.path,
            revision=document.index_revision,
            occurred_at=occurred_at,
        ),
        origin="document_snapshot_change",
        title=f"Indexed document: {document.path}",
        summary=(
            "Indexed document state changed: "
            f"kind={document.kind}, content_hash={document.content_hash}, raw_sha256={document.raw_sha256}, "
            f"metadata_index_revision={document.index_revision}, vault_revision={document.vault_revision}."
        ),
        vault_id=document.vault_id,
        occurred_at=occurred_at,
        sort_key=_sort_key(
            occurred_at=occurred_at,
            vault_id=document.vault_id,
            path_or_backend=document.path,
            item_id=stable_timeline_item_id(
                origin="document_snapshot_change",
                vault_id=document.vault_id,
                source_kind="document",
                document_id=document.document_id,
                backend_kind=None,
                path_or_scope=document.path,
                revision=document.index_revision,
                occurred_at=occurred_at,
            ),
        ),
        evidence=(
            TimelineEvidenceRef(
                source_kind="document",
                vault_id=document.vault_id,
                document_id=document.document_id,
                path=document.path,
                content_hash=document.content_hash,
                raw_sha256=document.raw_sha256,
                metadata_index_revision=document.index_revision,
                vault_revision=document.vault_revision,
            ),
        ),
        store_revisions=(revision,),
        warnings=(),
    )


def _metadata_status_item(*, vault_id: str, scope_key: str) -> TimelineItem:
    warning = _missing_timestamp_warning(vault_id=vault_id)
    item_id = stable_timeline_item_id(
        origin="index_change",
        vault_id=vault_id,
        source_kind="metadata_status",
        document_id=None,
        backend_kind="metadata",
        path_or_scope=scope_key,
        revision=None,
        occurred_at=None,
    )
    return TimelineItem(
        item_id=item_id,
        origin="index_change",
        title="Metadata index status",
        summary="Metadata index status is available for this scope.",
        vault_id=vault_id,
        occurred_at=None,
        sort_key=_sort_key(occurred_at=None, vault_id=vault_id, path_or_backend="metadata", item_id=item_id),
        evidence=(
            TimelineEvidenceRef(
                source_kind="metadata_status",
                vault_id=vault_id,
                backend_kind="metadata",
                scope_key=scope_key,
            ),
        ),
        store_revisions=(),
        warnings=(warning,),
    )


def _vector_items(*, report: StatusReport, vault_id: str) -> tuple[TimelineItem, ...]:
    if (
        report.vector_backend == "none"
        and report.vector_ok
        and report.vector_schema_compatible
        and not report.vector_revision
        and not report.vector_last_error
        and not report.vector_stale_count
        and report.vector_last_success_at is None
        and report.vector_last_error_at is None
    ):
        return ()
    warnings: list[MemoryWarning] = []
    if not report.vector_ok:
        warnings.append(
            _warning(
                code="vector_unavailable",
                message=report.vector_message,
                severity="warning",
                affected_vault_ids=(vault_id,),
                recovery_hint="Run vg status after indexing the selected scope.",
            )
        )
    if not report.vector_schema_compatible:
        warnings.append(
            _warning(
                code="vector_schema_incompatible",
                message=report.vector_message,
                severity="error",
                affected_vault_ids=(vault_id,),
                recovery_hint="Rebuild the vector index for the selected scope.",
            )
        )
    if report.vector_stale_count:
        warnings.append(
            _warning(
                code="vector_stale",
                message=f"{report.vector_stale_count} vector records are stale.",
                severity="warning",
                affected_vault_ids=(vault_id,),
                recovery_hint="Run vg index for the selected scope to refresh vector state.",
            )
        )
    if report.vector_last_error:
        warnings.append(
            _warning(
                code="vector_last_error",
                message=report.vector_last_error,
                severity="warning",
                affected_vault_ids=(vault_id,),
                recovery_hint="Run vg index, then vg status for the selected Vault.",
            )
        )
    occurred_at = report.vector_last_success_at or report.vector_last_error_at
    if occurred_at is None:
        warnings.append(_missing_timestamp_warning(vault_id=vault_id))
    return (
        _status_item(
            origin="index_change",
            source_kind="vector_status",
            backend_kind="vector",
            vault_id=vault_id,
            scope_key=report.vector_status_scope,
            revision=report.vector_revision,
            occurred_at=occurred_at,
            title="Vector index status",
            summary="Vector index status changed or is visible for this scope.",
            warnings=tuple(warnings),
        ),
    )


def _graph_items(*, report: StatusReport, vault_id: str) -> tuple[TimelineItem, ...]:
    graph = report.graph_readiness
    warnings: list[MemoryWarning] = []
    if not graph.backend_available:
        warnings.append(
            _warning(
                code="graph_unavailable",
                message=graph.recovery_hint or "graph backend is unavailable",
                severity="warning",
                affected_vault_ids=(vault_id,),
                recovery_hint="Run vg index for the selected scope, then vg status.",
            )
        )
    if not graph.schema_compatible or not graph.graph_extraction_spec_compatible:
        warnings.append(
            _warning(
                code="graph_schema_incompatible",
                message="graph schema or extraction spec is incompatible",
                severity="error",
                affected_vault_ids=(vault_id,),
                recovery_hint="Rebuild graph state for the selected scope.",
            )
        )
    if graph.freshness not in {"fresh", "empty"}:
        warnings.append(
            _warning(
                code="graph_stale",
                message=f"graph freshness is {graph.freshness}",
                severity="warning",
                affected_vault_ids=(vault_id,),
                recovery_hint="Run vg index for the selected scope, then vg status.",
            )
        )
    if report.graph_last_error:
        warnings.append(
            _warning(
                code="graph_last_error",
                message=report.graph_last_error,
                severity="warning",
                affected_vault_ids=(vault_id,),
                recovery_hint="Run vg index for the selected scope, then vg status.",
            )
        )
    occurred_at = report.graph_last_success_at or report.graph_last_error_at
    if occurred_at is None:
        warnings.append(_missing_timestamp_warning(vault_id=vault_id))
    return (
        _status_item(
            origin="projection_change",
            source_kind="graph_status",
            backend_kind="graph",
            vault_id=vault_id,
            scope_key=report.graph_status_scope,
            revision=report.graph_last_success_revision,
            occurred_at=occurred_at,
            title="Graph projection status",
            summary="Graph projection status changed or is visible for this scope.",
            warnings=tuple(warnings),
        ),
    )


def _status_item(
    *,
    origin: TimelineOrigin,
    source_kind: TimelineSourceKind,
    backend_kind: str,
    vault_id: str,
    scope_key: str,
    revision: str | None,
    occurred_at: str | None,
    title: str,
    summary: str,
    warnings: tuple[MemoryWarning, ...],
) -> TimelineItem:
    item_id = stable_timeline_item_id(
        origin=origin,
        vault_id=vault_id,
        source_kind=source_kind,
        document_id=None,
        backend_kind=backend_kind,
        path_or_scope=scope_key,
        revision=revision,
        occurred_at=occurred_at,
    )
    return TimelineItem(
        item_id=item_id,
        origin=origin,
        title=title,
        summary=summary,
        vault_id=vault_id,
        occurred_at=occurred_at,
        sort_key=_sort_key(occurred_at=occurred_at, vault_id=vault_id, path_or_backend=backend_kind, item_id=item_id),
        evidence=(
            TimelineEvidenceRef(
                source_kind=source_kind,
                vault_id=vault_id,
                backend_kind=backend_kind,
                backend_revision=revision,
                scope_key=scope_key,
            ),
        ),
        store_revisions=(
            MemoryBackendRevision(kind=backend_kind, revision=revision, vault_id=vault_id, scope_key=scope_key),
        ),
        warnings=warnings,
    )


def _filter_and_limit_items(
    *,
    items: tuple[TimelineItem, ...],
    since: str | None,
    limit: int,
) -> tuple[tuple[TimelineItem, ...], bool]:
    skipped_untimestamped = False
    filtered: list[TimelineItem] = []
    for item in items:
        if since is not None and item.occurred_at is None:
            skipped_untimestamped = True
            continue
        if since is not None and item.occurred_at is not None and item.occurred_at <= since:
            continue
        filtered.append(item)
    return tuple(sorted(filtered, key=_item_order)[:limit]), skipped_untimestamped


def _item_order(item: TimelineItem) -> tuple[int, str, str, str, str]:
    occurred = item.occurred_at or ""
    marker = 0 if item.occurred_at is not None else 1
    path_or_backend = item.evidence[0].path or item.evidence[0].backend_kind or ""
    return (marker, _reverse_time_key(occurred), item.vault_id, path_or_backend, item.item_id)


def _reverse_time_key(value: str) -> str:
    if not value:
        return ""
    return "".join(chr(255 - ord(char)) for char in value)


def _sort_key(*, occurred_at: str | None, vault_id: str, path_or_backend: str, item_id: str) -> str:
    return occurred_at or f"no-time:{vault_id}:{path_or_backend}:{item_id}"


def _vault_revisions(items: tuple[TimelineItem, ...]) -> tuple[MemoryBackendRevision, ...]:
    seen: set[tuple[str, str | None, str | None, str]] = set()
    revisions: list[MemoryBackendRevision] = []
    for item in items:
        for revision in item.store_revisions:
            key = (revision.kind, revision.revision, revision.vault_id, revision.scope_key)
            if key not in seen:
                seen.add(key)
                revisions.append(revision)
    return tuple(revisions)


def _freshness_for_report(report: StatusReport) -> TimelineFreshness:
    if not report.metadata_ok or not report.metadata_schema_compatible:
        return "unavailable"
    graph = report.graph_readiness
    if not report.vector_ok or not graph.backend_available:
        return "degraded"
    if report.vector_stale_count or graph.freshness == "stale":
        return "stale"
    return "fresh"


def _missing_timestamp_warning(*, vault_id: str) -> MemoryWarning:
    return _warning(
        code="missing_timeline_timestamp",
        message="This timeline item has no explicit status timestamp.",
        severity="info",
        affected_vault_ids=(vault_id,),
        recovery_hint="Re-index the selected scope to refresh indexed timestamps.",
    )


def _warning(
    *,
    code: str,
    message: str,
    severity: MemoryWarningSeverity,
    affected_vault_ids: tuple[str, ...],
    recovery_hint: str | None = None,
) -> MemoryWarning:
    return MemoryWarning(
        code=code,
        message=message,
        severity=severity,
        affected_vault_ids=affected_vault_ids,
        recovery_hint=recovery_hint,
    )


def _scope_key(scope: QueryScope) -> str:
    return f"{','.join(scope.vault_ids)}:{','.join(scope.content_scopes)}"


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _require_non_empty_string(value: object, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise MemoryProjectionError(f"{field_name} must be a non-empty string")


def _require_tuple(value: object, field_name: str) -> None:
    if not isinstance(value, tuple):
        raise MemoryProjectionError(f"{field_name} must be a tuple")


def _require_one_of(value: str, field_name: str, allowed: tuple[str, ...]) -> None:
    if value not in allowed:
        raise MemoryProjectionError(f"{field_name} must be one of: {', '.join(allowed)}")
