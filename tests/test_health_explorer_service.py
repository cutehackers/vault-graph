from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

from tests.test_mcp_tools import make_status_report
from vault_graph.app.index_service import StatusReport
from vault_graph.ingestion.vault_catalog import QueryScope, VaultCatalog, VaultCatalogEntry
from vault_graph.memory.health_explorer import (
    HealthExplorerService,
    McpRuntimeCacheRecord,
)


class RecordingStatusService:
    def __init__(self, reports: tuple[StatusReport, ...] | None = None) -> None:
        self.calls: list[QueryScope | None] = []
        self._reports = reports or (make_status_report(),)

    def status(self, *, scope: QueryScope | None = None) -> StatusReport:
        self.calls.append(scope)
        index = min(len(self.calls) - 1, len(self._reports) - 1)
        return self._reports[index]


def test_health_explorer_uses_supplied_status_report_and_runtime_cache_records(tmp_path: Path) -> None:
    catalog = make_catalog(tmp_path, ("main",))
    status = RecordingStatusService()
    runtime_cache = McpRuntimeCacheRecord(
        cache_name="context_pack",
        current_entries=2,
        max_entries=2,
        status="degraded",
        message="cache at capacity",
    )
    report = HealthExplorerService(
        catalog=catalog,
        status_service=status,
        clock=lambda: datetime(2026, 6, 18, tzinfo=UTC),
    ).inspect(
        requested_scope=QueryScope(vault_ids=("main",), content_scopes=("wiki",)),
        runtime_caches=(runtime_cache,),
        status_report=make_status_report(),
    )

    assert status.calls == []
    assert {backend.backend_kind for backend in report.backends} == {"metadata", "keyword", "vector", "graph"}
    assert report.runtime_caches == (runtime_cache,)
    assert {adapter.target_backend for adapter in report.scale_up_adapters} == {"postgres", "qdrant", "neo4j"}
    assert report.generated_at == "2026-06-18T00:00:00+00:00"


def test_health_explorer_splits_status_calls_per_actual_vault_when_no_report_is_supplied(tmp_path: Path) -> None:
    catalog = make_catalog(tmp_path, ("main", "work"))
    status = RecordingStatusService()

    report = HealthExplorerService(catalog=catalog, status_service=status).inspect(
        requested_scope=QueryScope(vault_ids=("main", "work"), content_scopes=("wiki",)),
    )

    assert [scope.vault_ids for scope in status.calls if scope is not None] == [("main",), ("work",)]
    assert [scope.vault_ids for scope in report.actual_scopes] == [("main",), ("work",)]


def test_health_explorer_marks_degraded_backend_and_adapter_when_vector_is_stale(tmp_path: Path) -> None:
    catalog = make_catalog(tmp_path, ("main",))
    status = RecordingStatusService()
    stale_report = replace(make_status_report(), vector_stale_count=3)

    report = HealthExplorerService(catalog=catalog, status_service=status).inspect(
        requested_scope=QueryScope(vault_ids=("main",), content_scopes=("wiki",)),
        status_report=stale_report,
    )

    vector_backend = next(backend for backend in report.backends if backend.backend_kind == "vector")
    qdrant = next(adapter for adapter in report.scale_up_adapters if adapter.target_backend == "qdrant")

    assert vector_backend.status == "degraded"
    assert qdrant.contract_ready is False
    assert any(warning.code == "vector_stale" for warning in report.warnings)


def test_health_explorer_scale_up_readiness_uses_all_actual_vault_statuses(tmp_path: Path) -> None:
    catalog = make_catalog(tmp_path, ("main", "work"))
    status = RecordingStatusService(
        reports=(
            replace(make_status_report(), vector_stale_count=2),
            make_status_report(),
        )
    )

    report = HealthExplorerService(catalog=catalog, status_service=status).inspect(
        requested_scope=QueryScope(vault_ids=("main", "work"), content_scopes=("wiki",)),
    )

    qdrant = next(adapter for adapter in report.scale_up_adapters if adapter.target_backend == "qdrant")

    assert qdrant.contract_ready is False
    assert any(
        warning.code == "vector_stale" and warning.affected_vault_ids == ("main",) for warning in report.warnings
    )


def make_catalog(tmp_path: Path, vault_ids: tuple[str, ...]) -> VaultCatalog:
    entries = []
    for vault_id in vault_ids:
        root = tmp_path / vault_id
        (root / "wiki").mkdir(parents=True)
        entries.append(VaultCatalogEntry.from_root(vault_id=vault_id, root_path=root, display_name=vault_id.title()))
    return VaultCatalog.from_entries(entries=tuple(entries), active_vault_id=vault_ids[0])
