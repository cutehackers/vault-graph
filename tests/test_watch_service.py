from __future__ import annotations

from pathlib import Path
from typing import Any, cast

from tests.test_setup_service import RecordingIndexFactory
from vault_graph.app.watch_service import WatchService
from vault_graph.ingestion.vault_catalog import QueryScope


def test_watch_runs_incremental_index_until_max_iterations(tmp_path: Path) -> None:
    factory = RecordingIndexFactory()
    sleeps: list[float] = []

    report = WatchService(
        state_path=tmp_path / "state",
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
        state_path=tmp_path / "state",
        index_factory=cast(Any, factory),
        sleep=sleeps.append,
    ).run(
        scope=QueryScope(vault_ids=("main",), content_scopes=("wiki",)),
        interval_seconds=2.5,
        max_iterations=2,
    )

    assert sleeps == [2.5]
