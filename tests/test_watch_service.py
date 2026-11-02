from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest

from tests.test_setup_service import RecordingIndexFactory
from vault_graph.indexing.index_service import IndexRunReport
from vault_graph.indexing.revision_planner import MetadataRevisionPlan
from vault_graph.operation.runtime.watch_service import WatchService
from vault_graph.operation.scope.vault_catalog import QueryScope


def test_watch_runs_incremental_index_until_max_iterations(tmp_path: Path) -> None:
    factory = RecordingIndexFactory()
    sleeps: list[float] = []

    report = WatchService(
        graph_home_path=tmp_path / "state",
        index_factory=cast(Any, factory),
        sleep=sleeps.append,
    ).run(
        scope=QueryScope(vault_ids=("main",), content_scopes=("wiki",)),
        interval_seconds=2.5,
        max_iterations=1,
    )

    assert report.exit_code == 0
    assert report.iterations[0].index_revision == "metadata-1"
    assert factory.index_service.calls[0]["full"] is False
    assert sleeps == []


def test_watch_sleeps_between_iterations(tmp_path: Path) -> None:
    factory = RecordingIndexFactory()
    sleeps: list[float] = []

    WatchService(
        graph_home_path=tmp_path / "state",
        index_factory=cast(Any, factory),
        sleep=sleeps.append,
    ).run(
        scope=QueryScope(vault_ids=("main",), content_scopes=("wiki",)),
        interval_seconds=2.5,
        max_iterations=2,
    )

    assert sleeps == [2.5]


class StagedBundle:
    """Bundle with a staged generation, like ``LocalIndexServiceBundle``."""

    def __init__(self, index_service: object, publisher: RecordingPublisher) -> None:
        self.index_service = index_service
        self.bundle_publisher = publisher
        self.staged_generation: object | None = object()
        self.committed: list[IndexRunReport | None] = []
        self.closed_with_staged: object | None = None
        self.closed = False

    def commit_projection(self, report: IndexRunReport | None = None) -> None:
        self.committed.append(report)

    def close(self) -> None:
        self.closed = True
        self.closed_with_staged = self.staged_generation


class RecordingPublisher:
    def __init__(self) -> None:
        self.discarded: list[object] = []

    def discard(self, staged: object) -> None:
        self.discarded.append(staged)


class StagedFactory:
    def __init__(self, reports: list[IndexRunReport]) -> None:
        self._reports = reports
        self.publisher = RecordingPublisher()
        self.bundles: list[StagedBundle] = []

    def run_apply(self, **kwargs: object) -> IndexRunReport:
        return self._reports.pop(0)

    def open(self, **kwargs: object) -> StagedBundle:
        bundle = StagedBundle(self, self.publisher)
        self.bundles.append(bundle)
        return bundle


def _report(
    *, changed: tuple[tuple[str, str], ...] = (), deleted: tuple[tuple[str, str], ...] = (), vector: object = None
) -> IndexRunReport:
    return IndexRunReport(
        metadata=MetadataRevisionPlan(
            index_revision="metadata-1",
            mode="incremental",
            vault_ids=("main",),
            changed_paths=changed,
            unchanged_paths=(("main", "wiki/a.md"),),
            deleted_paths=deleted,
            warnings=(),
        ),
        vector=cast(Any, vector),
        graph=None,
    )


def _run(factory: StagedFactory, tmp_path: Path, *, iterations: int, full: bool = False) -> None:
    WatchService(graph_home_path=tmp_path / "state", index_factory=cast(Any, factory), sleep=lambda _: None).run(
        scope=QueryScope(vault_ids=("main",), content_scopes=("wiki",)),
        interval_seconds=1,
        full=full,
        max_iterations=iterations,
    )


def test_watch_does_not_publish_when_nothing_changed(tmp_path: Path) -> None:
    factory = StagedFactory([_report(), _report()])

    _run(factory, tmp_path, iterations=2)

    assert [bundle.committed for bundle in factory.bundles] == [[], []]
    # The staged copy is removed quietly, so close() leaves no staged generation or failed run behind.
    assert len(factory.publisher.discarded) == 2
    assert all(bundle.closed and bundle.closed_with_staged is None for bundle in factory.bundles)


def test_watch_publishes_when_files_change_or_are_deleted(tmp_path: Path) -> None:
    factory = StagedFactory(
        [_report(changed=(("main", "wiki/b.md"),)), _report(), _report(deleted=(("main", "wiki/a.md"),))]
    )

    _run(factory, tmp_path, iterations=3)

    assert [len(bundle.committed) for bundle in factory.bundles] == [1, 0, 1]
    assert len(factory.publisher.discarded) == 1


def test_watch_publishes_when_only_vectors_catch_up(tmp_path: Path) -> None:
    vector = SimpleNamespace(upsert_count=3, tombstone_count=0, failed=False)
    factory = StagedFactory([_report(vector=vector)])

    _run(factory, tmp_path, iterations=1)

    assert len(factory.bundles[0].committed) == 1


def test_watch_publishes_graph_changes_but_not_repeated_evidence_refs(tmp_path: Path) -> None:
    def graph(**counts: int) -> SimpleNamespace:
        fields = ("entity_upserts", "relationship_upserts", "evidence_ref_upserts", "entity_tombstones")
        plan = {name: (object(),) * counts.get(name, 0) for name in fields}
        reconcile_plan = SimpleNamespace(relationship_tombstones=(), **plan)
        return SimpleNamespace(stale_count=0, failed=False, reconcile_plan=reconcile_plan)

    reports = [_report(), _report()]
    reports = [
        replace(reports[0], graph=cast(Any, graph(evidence_ref_upserts=3))),
        replace(reports[1], graph=cast(Any, graph(entity_upserts=1))),
    ]
    factory = StagedFactory(reports)

    _run(factory, tmp_path, iterations=2)

    assert [len(bundle.committed) for bundle in factory.bundles] == [0, 1]


def test_watch_full_run_always_publishes(tmp_path: Path) -> None:
    factory = StagedFactory([_report()])

    _run(factory, tmp_path, iterations=1, full=True)

    assert len(factory.bundles[0].committed) == 1
    assert factory.publisher.discarded == []


def test_watch_with_real_index_keeps_active_generation_when_vault_is_unchanged(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import json

    from typer.testing import CliRunner

    from tests.test_read_only_boundary import _fake_text_embeddings
    from vault_graph.interface.cli.main import app

    monkeypatch.setattr(
        "vault_graph.interface.composition.local_index_service_factory._default_text_embeddings",
        _fake_text_embeddings,
    )
    vault_root = tmp_path / "vault"
    (vault_root / "wiki").mkdir(parents=True)
    page = vault_root / "wiki" / "page.md"
    page.write_text("# Page\nBody\n", encoding="utf-8")
    graph_home = tmp_path / "state"
    assert CliRunner().invoke(app, ["init", "--vault", str(vault_root), "--graph-home", str(graph_home)]).exit_code == 0
    service = WatchService(graph_home_path=graph_home, sleep=lambda _: None)
    scope = QueryScope(vault_ids=("default",), content_scopes=("raw", "wiki", "docs", "scratch/reports"))
    active = graph_home / "projections" / "active.json"

    def state() -> tuple[str, list[str], list[str]]:
        generation = json.loads(active.read_text(encoding="utf-8"))["generation_id"]
        runs = sorted(path.name for path in (graph_home / "runs").glob("*.json"))
        generations = sorted(path.name for path in (graph_home / "projections" / "generations").iterdir())
        return generation, runs, generations

    service.run(scope=scope, interval_seconds=1, max_iterations=1)
    first = state()

    report = service.run(scope=scope, interval_seconds=1, max_iterations=2)

    assert report.exit_code == 0
    assert state() == first
    page.write_text("# Page\nChanged body\n", encoding="utf-8")
    service.run(scope=scope, interval_seconds=1, max_iterations=1)
    assert state()[0] != first[0]
