"""Append-only usage records under the Graph Home ``usage/`` folder (spec 4.2.3, S11, A-10d, A-10i)."""

from __future__ import annotations

import json
import stat
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import pytest

from vault_graph.storage.local.usage_log import JsonlUsageLog


def _clock(text: str = "2026-10-30T09:00:00+00:00") -> datetime:
    return datetime.fromisoformat(text)


@pytest.fixture
def graph_home(tmp_path: Path) -> Path:
    home = tmp_path / "graph-home"
    home.mkdir()
    return home


def test_append_creates_only_the_usage_folder_and_reads_back(graph_home: Path) -> None:
    log = JsonlUsageLog(graph_home, clock=_clock)

    log.append_events([{"event": "injected", "item_id": "m:1"}, {"event": "fetched", "item_id": "m:1"}])
    log.append_events([{"event": "injected", "item_id": "m:2"}])

    assert [path.name for path in graph_home.iterdir()] == ["usage"]
    assert [path.name for path in (graph_home / "usage").iterdir()] == ["2026-10.jsonl"]
    assert [event["item_id"] for event in log.read_events()] == ["m:1", "m:1", "m:2"]


def test_append_never_creates_a_missing_graph_home(tmp_path: Path) -> None:
    log = JsonlUsageLog(tmp_path / "missing", clock=_clock)

    with pytest.raises(OSError):
        log.append_events([{"event": "injected"}])

    assert not (tmp_path / "missing").exists()


def test_append_of_nothing_writes_nothing(graph_home: Path) -> None:
    JsonlUsageLog(graph_home, clock=_clock).append_events([])

    assert not (graph_home / "usage").exists()


def test_reading_without_usage_folder_is_empty(graph_home: Path) -> None:
    assert JsonlUsageLog(graph_home, clock=_clock).read_events() == ()


def test_broken_lines_are_skipped(graph_home: Path) -> None:
    usage = graph_home / "usage"
    usage.mkdir()
    (usage / "2026-10.jsonl").write_text(
        '{"event": "injected", "item_id": "m:1"}\n{broken\n[1, 2]\n\n{"event": "fetched", "item_id": "m:1"}\n',
        encoding="utf-8",
    )

    events = JsonlUsageLog(graph_home, clock=_clock).read_events()

    assert [event["event"] for event in events] == ["injected", "fetched"]


def test_reads_only_the_newest_month_files_in_order(graph_home: Path) -> None:
    usage = graph_home / "usage"
    usage.mkdir()
    for month in ("2026-06", "2026-07", "2026-08", "2026-09"):
        (usage / f"{month}.jsonl").write_text(json.dumps({"month": month}) + "\n", encoding="utf-8")

    events = JsonlUsageLog(graph_home, clock=_clock, max_files=3).read_events()

    assert [event["month"] for event in events] == ["2026-07", "2026-08", "2026-09"]


def test_month_file_follows_the_clock(graph_home: Path) -> None:
    log = JsonlUsageLog(graph_home, clock=lambda: datetime(2026, 11, 1, tzinfo=UTC))

    log.append_events([{"event": "injected"}])

    assert (graph_home / "usage" / "2026-11.jsonl").is_file()


@pytest.fixture
def read_only_usage(graph_home: Path) -> Iterator[Path]:
    usage = graph_home / "usage"
    usage.mkdir()
    usage.chmod(stat.S_IRUSR | stat.S_IXUSR)
    yield usage
    usage.chmod(stat.S_IRWXU)


def test_append_to_read_only_usage_folder_raises_os_error(graph_home: Path, read_only_usage: Path) -> None:
    with pytest.raises(OSError):
        JsonlUsageLog(graph_home, clock=_clock).append_events([{"event": "injected"}])

    assert list(read_only_usage.iterdir()) == []
