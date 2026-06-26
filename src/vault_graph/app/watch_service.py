from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from time import sleep as default_sleep

from vault_graph.app.index_service import IndexRunReport
from vault_graph.app.local_index_service_factory import LocalIndexServiceFactory
from vault_graph.ingestion.vault_catalog import QueryScope


@dataclass(frozen=True)
class WatchIterationReport:
    iteration: int
    exit_code: int
    index_revision: str
    changed: int
    unchanged: int
    deleted: int
    vector_failed: bool
    graph_failed: bool


@dataclass(frozen=True)
class WatchReport:
    iterations: tuple[WatchIterationReport, ...]
    interrupted: bool

    @property
    def exit_code(self) -> int:
        if not self.iterations:
            return 1
        return 1 if any(iteration.exit_code for iteration in self.iterations) else 0


class WatchService:
    def __init__(
        self,
        *,
        state_path: Path,
        index_factory: LocalIndexServiceFactory | None = None,
        sleep: Callable[[float], None] = default_sleep,
        stop_requested: Callable[[], bool] | None = None,
    ) -> None:
        self._state_path = state_path
        self._index_factory = index_factory or LocalIndexServiceFactory()
        self._sleep = sleep
        self._stop_requested = stop_requested or (lambda: False)

    def run(
        self,
        *,
        scope: QueryScope,
        interval_seconds: float,
        full: bool = False,
        max_iterations: int | None = None,
    ) -> WatchReport:
        if interval_seconds <= 0:
            raise ValueError("watch_interval_must_be_positive")
        iterations: list[WatchIterationReport] = []
        interrupted = False
        count = 0
        while not self._stop_requested():
            count += 1
            bundle = self._index_factory.open(state_path=self._state_path, initialize_store=True)
            try:
                report = bundle.index_service.run_apply(scope=scope, full=full)
            finally:
                bundle.close()
            iterations.append(_iteration_report(count, report))
            if max_iterations is not None and count >= max_iterations:
                break
            try:
                self._sleep(interval_seconds)
            except KeyboardInterrupt:
                interrupted = True
                break
        return WatchReport(iterations=tuple(iterations), interrupted=interrupted)


def _iteration_report(iteration: int, report: IndexRunReport) -> WatchIterationReport:
    return WatchIterationReport(
        iteration=iteration,
        exit_code=report.exit_code,
        index_revision=report.metadata.index_revision,
        changed=len(report.metadata.changed_paths),
        unchanged=len(report.metadata.unchanged_paths),
        deleted=len(report.metadata.deleted_paths),
        vector_failed=bool(getattr(report.vector, "failed", False)),
        graph_failed=bool(getattr(report.graph, "failed", False)),
    )
