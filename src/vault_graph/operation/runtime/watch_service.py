from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from time import sleep as default_sleep
from typing import Any

from vault_graph.indexing.index_service import IndexRunReport
from vault_graph.operation.runtime.indexing import OperationsIndexFactory
from vault_graph.operation.scope.vault_catalog import QueryScope


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
        graph_home_path: Path,
        index_factory: OperationsIndexFactory | None = None,
        sleep: Callable[[float], None] = default_sleep,
        stop_requested: Callable[[], bool] | None = None,
    ) -> None:
        self._graph_home_path = graph_home_path
        if index_factory is None:
            from vault_graph.interface.composition.adapters.runtime_indexing import default_index_factory

            index_factory = default_index_factory()
        self._index_factory = index_factory
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
            bundle = self._index_factory.open(
                graph_home_path=self._graph_home_path,
                initialize_store=True,
                transactional=True,
                full=full,
            )
            try:
                report = bundle.index_service.run_apply(scope=scope, full=full)
                if report.exit_code == 0:
                    if full or _has_changes(report):
                        commit_projection = getattr(bundle, "commit_projection", None)
                        if commit_projection is not None:
                            commit_projection(report)
                    else:
                        _discard_staged_generation(bundle)
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


def _has_changes(report: IndexRunReport) -> bool:
    """True when the run changed metadata, vectors or graph rows, so a new generation is worth publishing."""
    metadata = report.metadata
    if metadata.changed_paths or metadata.deleted_paths:
        return True
    vector = report.vector
    if vector is not None and (vector.upsert_count or vector.tombstone_count):
        return True
    graph = report.graph
    if graph is None:
        return False
    if graph.stale_count:
        return True
    plan = graph.reconcile_plan
    # Evidence refs are re-upserted on every run even when no file changed, so they are not a change signal.
    return plan is not None and bool(
        plan.entity_upserts or plan.relationship_upserts or plan.entity_tombstones or plan.relationship_tombstones
    )


def _discard_staged_generation(bundle: Any) -> None:
    """Remove the unchanged staged copy so ``close`` neither keeps it nor records a failed publication."""
    staged = getattr(bundle, "staged_generation", None)
    publisher = getattr(bundle, "bundle_publisher", None) or getattr(bundle, "generation_manager", None)
    if staged is None or publisher is None:
        return
    publisher.discard(staged)
    bundle.staged_generation = None


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
