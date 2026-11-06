"""Cleanup review records in the Graph Home ``memory/reviewed.jsonl`` (spec 2026-11-05 §4.4.4, A-22, A-38)."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from vault_graph.storage.local.reviewed_log import REVIEWED_LOG_PATH, JsonlReviewedLog


def _clock() -> datetime:
    return datetime(2026, 11, 6, 9, 30, 0, tzinfo=UTC)


@pytest.fixture
def graph_home(tmp_path: Path) -> Path:
    home = tmp_path / "graph-home"
    home.mkdir()
    return home


def test_append_writes_one_line_per_key_under_graph_home_memory(graph_home: Path) -> None:
    log = JsonlReviewedLog(graph_home, clock=_clock)

    log.append(["session:s1:u-1", "l1:abc"], outcome="skipped")

    assert REVIEWED_LOG_PATH == "memory/reviewed.jsonl"
    assert [path.name for path in graph_home.iterdir()] == ["memory"]
    lines = (graph_home / "memory" / "reviewed.jsonl").read_text(encoding="utf-8").splitlines()
    assert [json.loads(line) for line in lines] == [
        {"at": "2026-11-06T09:30:00Z", "candidate_key": "session:s1:u-1", "outcome": "skipped"},
        {"at": "2026-11-06T09:30:00Z", "candidate_key": "l1:abc", "outcome": "skipped"},
    ]
    assert log.reviewed_keys() == frozenset({"session:s1:u-1", "l1:abc"})


def test_later_appends_add_lines_and_keep_earlier_ones(graph_home: Path) -> None:
    log = JsonlReviewedLog(graph_home, clock=_clock)

    log.append(["l1:a"], outcome="skipped")
    log.append(["l1:b"], outcome="published")

    assert log.reviewed_keys() == frozenset({"l1:a", "l1:b"})
    assert len((graph_home / "memory" / "reviewed.jsonl").read_text(encoding="utf-8").splitlines()) == 2


def test_missing_file_means_nothing_reviewed(graph_home: Path) -> None:
    assert JsonlReviewedLog(graph_home).reviewed_keys() == frozenset()


def test_deleting_the_file_forgets_every_record(graph_home: Path) -> None:
    log = JsonlReviewedLog(graph_home, clock=_clock)
    log.append(["l1:a"], outcome="skipped")

    (graph_home / "memory" / "reviewed.jsonl").unlink()

    assert log.reviewed_keys() == frozenset()


def test_broken_and_foreign_lines_are_skipped(graph_home: Path) -> None:
    (graph_home / "memory").mkdir()
    (graph_home / "memory" / "reviewed.jsonl").write_text(
        'not json\n[1, 2]\n{"outcome": "skipped"}\n{"candidate_key": ""}\n{"candidate_key": "l1:ok"}\n',
        encoding="utf-8",
    )

    assert JsonlReviewedLog(graph_home).reviewed_keys() == frozenset({"l1:ok"})


def test_append_never_creates_a_missing_graph_home(tmp_path: Path) -> None:
    log = JsonlReviewedLog(tmp_path / "missing", clock=_clock)

    with pytest.raises(OSError):
        log.append(["l1:a"], outcome="skipped")

    assert not (tmp_path / "missing").exists()


def test_append_of_no_keys_writes_nothing(graph_home: Path) -> None:
    JsonlReviewedLog(graph_home, clock=_clock).append([], outcome="skipped")

    assert not (graph_home / "memory").exists()


@pytest.mark.parametrize("bad", ["", "  "])
def test_blank_keys_and_outcomes_are_rejected(graph_home: Path, bad: str) -> None:
    log = JsonlReviewedLog(graph_home, clock=_clock)

    with pytest.raises(ValueError):
        log.append([bad], outcome="skipped")
    with pytest.raises(ValueError):
        log.append(["l1:a"], outcome=bad)

    assert not (graph_home / "memory").exists()
