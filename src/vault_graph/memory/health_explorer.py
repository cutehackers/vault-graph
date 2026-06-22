from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Literal

from vault_graph.ingestion.query_scope_resolution import actual_query_scopes
from vault_graph.ingestion.vault_catalog import QueryScope, VaultCatalog
from vault_graph.memory.memory_models import MemoryWarning, MemoryWarningSeverity
from vault_graph.memory.memory_request_context import MemoryStatusService

if TYPE_CHECKING:
    from vault_graph.app.index_service import StatusReport

ReadinessStatus = Literal["ready", "degraded", "unavailable", "not_configured"]
HealthBackendKind = Literal["metadata", "keyword", "vector", "graph", "mcp_runtime_cache"]


@dataclass(frozen=True)
class BackendReadinessRecord:
    backend_kind: HealthBackendKind
    backend_name: str
    vault_id: str | None
    scope_key: str
    status: ReadinessStatus
    schema_compatible: bool
    freshness: str
    revision: str | None
    last_success_at: str | None
    last_error_at: str | None
    message: str
    recovery_hint: str | None


@dataclass(frozen=True)
class McpRuntimeCacheRecord:
    cache_name: str
    current_entries: int
    max_entries: int
    status: ReadinessStatus
    oldest_cached_at: str | None = None
    newest_cached_at: str | None = None
    message: str = ""


@dataclass(frozen=True)
class ScaleUpAdapterReadiness:
    adapter_kind: str
    target_backend: str
    configured: bool
    contract_ready: bool
    migration_required: bool
    depends_on_backend_kind: str
    message: str
    recovery_hint: str | None = None


@dataclass(frozen=True)
class HealthExplorerReport:
    requested_scope: QueryScope
    actual_scopes: tuple[QueryScope, ...]
    backends: tuple[BackendReadinessRecord, ...]
    runtime_caches: tuple[McpRuntimeCacheRecord, ...]
    scale_up_adapters: tuple[ScaleUpAdapterReadiness, ...]
    warnings: tuple[MemoryWarning, ...]
    generated_at: str


class HealthExplorerService:
    def __init__(
        self,
        *,
        catalog: VaultCatalog,
        status_service: MemoryStatusService,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._catalog = catalog
        self._status_service = status_service
        self._clock = clock or _utc_now

    def inspect(
        self,
        *,
        requested_scope: QueryScope,
        runtime_caches: tuple[McpRuntimeCacheRecord, ...] = (),
        status_report: StatusReport | None = None,
    ) -> HealthExplorerReport:
        actual_scopes = actual_query_scopes(catalog=self._catalog, scope=requested_scope)
        reports = (
            (status_report,)
            if status_report is not None
            else tuple(self._status_service.status(scope=scope) for scope in actual_scopes)
        )
        backends: list[BackendReadinessRecord] = []
        warnings: list[MemoryWarning] = []
        single_vault_id = actual_scopes[0].vault_ids[0] if len(actual_scopes) == 1 else None
        for index, report in enumerate(reports):
            actual_scope = actual_scopes[index] if status_report is None and index < len(actual_scopes) else None
            vault_id = actual_scope.vault_ids[0] if actual_scope is not None else single_vault_id
            scope_key = _scope_key(actual_scope or requested_scope)
            records, record_warnings = _backend_records(
                report=report,
                vault_id=vault_id,
                scope_key=scope_key,
                affected_vault_ids=(vault_id,) if vault_id is not None else requested_scope.vault_ids,
            )
            backends.extend(records)
            warnings.extend(record_warnings)
        scale_up = _scale_up_records(backends)
        return HealthExplorerReport(
            requested_scope=requested_scope,
            actual_scopes=actual_scopes,
            backends=tuple(backends),
            runtime_caches=runtime_caches,
            scale_up_adapters=scale_up,
            warnings=tuple(warnings),
            generated_at=self._clock().isoformat(),
        )


def _backend_records(
    *,
    report: StatusReport,
    vault_id: str | None,
    scope_key: str,
    affected_vault_ids: tuple[str, ...],
) -> tuple[tuple[BackendReadinessRecord, ...], tuple[MemoryWarning, ...]]:
    warnings: list[MemoryWarning] = []
    metadata_status: ReadinessStatus = (
        "ready" if report.metadata_ok and report.metadata_schema_compatible else "unavailable"
    )
    metadata = BackendReadinessRecord(
        backend_kind="metadata",
        backend_name="sqlite",
        vault_id=vault_id,
        scope_key=scope_key,
        status=metadata_status,
        schema_compatible=report.metadata_schema_compatible,
        freshness="fresh" if metadata_status == "ready" else "unavailable",
        revision=None,
        last_success_at=None,
        last_error_at=None,
        message=report.metadata_message,
        recovery_hint=None if metadata_status == "ready" else "Run vg index, then vg status for the selected Vault.",
    )
    keyword = BackendReadinessRecord(
        backend_kind="keyword",
        backend_name="sqlite_fts",
        vault_id=vault_id,
        scope_key=scope_key,
        status=metadata_status,
        schema_compatible=report.metadata_schema_compatible,
        freshness=metadata.freshness,
        revision=None,
        last_success_at=None,
        last_error_at=None,
        message="keyword index is metadata-coupled in Phase 6C",
        recovery_hint=metadata.recovery_hint,
    )
    vector_status: ReadinessStatus = "ready"
    vector_freshness = "fresh"
    vector_hint = None
    if not report.vector_ok:
        vector_status = "unavailable"
        vector_freshness = "unavailable"
        vector_hint = "Run vg index for the selected scope to refresh vector state."
        warnings.append(_warning("vector_unavailable", report.vector_message, affected_vault_ids))
    elif not report.vector_schema_compatible:
        vector_status = "unavailable"
        vector_freshness = "unavailable"
        vector_hint = "Rebuild the vector index for the selected scope."
        warnings.append(
            _warning("vector_schema_incompatible", report.vector_message, affected_vault_ids, severity="error")
        )
    elif report.vector_stale_count:
        vector_status = "degraded"
        vector_freshness = "stale"
        vector_hint = "Run vg index for the selected scope to refresh vector state."
        warnings.append(
            _warning("vector_stale", f"{report.vector_stale_count} vector records are stale.", affected_vault_ids)
        )
    elif report.vector_last_error:
        vector_status = "degraded"
        vector_freshness = "degraded"
        vector_hint = "Run vg index, then vg status for the selected Vault."
        warnings.append(_warning("vector_last_error", report.vector_last_error, affected_vault_ids))
    vector = BackendReadinessRecord(
        backend_kind="vector",
        backend_name=report.vector_backend,
        vault_id=vault_id,
        scope_key=report.vector_status_scope,
        status=vector_status,
        schema_compatible=report.vector_schema_compatible,
        freshness=vector_freshness,
        revision=report.vector_revision,
        last_success_at=report.vector_last_success_at,
        last_error_at=report.vector_last_error_at,
        message=report.vector_message,
        recovery_hint=vector_hint,
    )
    graph = report.graph_readiness
    graph_status: ReadinessStatus = "ready"
    graph_hint = None
    if not graph.backend_available:
        graph_status = "unavailable"
        graph_hint = "Run vg index for the selected scope, then vg status."
        warnings.append(_warning("graph_unavailable", graph.recovery_hint or "graph unavailable", affected_vault_ids))
    elif not graph.schema_compatible or not graph.graph_extraction_spec_compatible:
        graph_status = "unavailable"
        graph_hint = "Rebuild graph state for the selected scope."
        warnings.append(
            _warning("graph_schema_incompatible", "graph schema is incompatible", affected_vault_ids, severity="error")
        )
    elif graph.freshness not in {"fresh", "empty"} or report.graph_last_error:
        graph_status = "degraded"
        graph_hint = "Run vg index for the selected scope, then vg status."
        warnings.append(_warning("graph_stale", f"graph freshness is {graph.freshness}", affected_vault_ids))
    graph_record = BackendReadinessRecord(
        backend_kind="graph",
        backend_name=graph.backend_name,
        vault_id=vault_id,
        scope_key=report.graph_status_scope,
        status=graph_status,
        schema_compatible=graph.schema_compatible and graph.graph_extraction_spec_compatible,
        freshness=graph.freshness,
        revision=report.graph_last_success_revision or graph.last_graph_revision,
        last_success_at=report.graph_last_success_at,
        last_error_at=report.graph_last_error_at,
        message=graph.recovery_hint or "graph readiness available",
        recovery_hint=graph_hint,
    )
    return (metadata, keyword, vector, graph_record), tuple(warnings)


def _scale_up_records(backends: list[BackendReadinessRecord]) -> tuple[ScaleUpAdapterReadiness, ...]:
    by_kind: dict[str, list[BackendReadinessRecord]] = {}
    for backend in backends:
        by_kind.setdefault(backend.backend_kind, []).append(backend)
    return (
        _adapter_record("metadata", "postgres", by_kind.get("metadata")),
        _adapter_record("vector", "qdrant", by_kind.get("vector")),
        _adapter_record("graph", "neo4j", by_kind.get("graph")),
    )


def _adapter_record(
    adapter_kind: str,
    target_backend: str,
    backends: list[BackendReadinessRecord] | None,
) -> ScaleUpAdapterReadiness:
    records = backends or []
    ready = bool(records) and all(backend.status == "ready" and backend.schema_compatible for backend in records)
    first_backend = records[0] if records else None
    return ScaleUpAdapterReadiness(
        adapter_kind=adapter_kind,
        target_backend=target_backend,
        configured=False,
        contract_ready=ready,
        migration_required=True,
        depends_on_backend_kind=adapter_kind,
        message=(
            f"{adapter_kind} contract ready; no record-level migration audit was performed"
            if ready
            else f"{adapter_kind} contract is not ready for {target_backend}; no migration was performed"
        ),
        recovery_hint=None if ready else first_backend.recovery_hint if first_backend is not None else "Run vg status.",
    )


def _warning(
    code: str,
    message: str,
    affected_vault_ids: tuple[str, ...],
    *,
    severity: MemoryWarningSeverity = "warning",
) -> MemoryWarning:
    return MemoryWarning(
        code=code,
        message=message,
        severity=severity,
        affected_vault_ids=affected_vault_ids,
        recovery_hint="Run vg status for the selected Vault.",
    )


def _scope_key(scope: QueryScope) -> str:
    return f"{','.join(scope.vault_ids)}:{','.join(scope.content_scopes)}"


def _utc_now() -> datetime:
    return datetime.now(UTC)
