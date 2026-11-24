"""Dreaming settings and `vg dream on|off|status` (spec 2026-11-19 OD2, OD3, OD4)."""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest
from typer.testing import CliRunner

from vault_graph.errors import CatalogError
from vault_graph.interface.cli.main import app
from vault_graph.operation.scope.dream_settings import (
    DREAM_MODEL,
    DreamSettings,
    dream_judged_path,
    dream_runs_path,
    dream_settings_path,
    read_dream_settings,
    save_dream_settings,
)

runner = CliRunner()

VALID = {
    "version": 1,
    "enabled": True,
    "model": "claude-sonnet-5-5",
    "pending_cap": 10,
    "proposals_per_run": 10,
    "interval_hours": 24,
    "bundle_limit": 40,
    "due_exchanges": 20,
}


def _init_graph_home(tmp_path: Path) -> Path:
    vault = tmp_path / "vault"
    (vault / "wiki").mkdir(parents=True)
    (vault / "wiki" / "page.md").write_text("# Page\nBody\n", encoding="utf-8")
    graph_home = tmp_path / "graph-home"
    result = runner.invoke(app, ["init", "--vault", str(vault), "--graph-home", str(graph_home)])
    assert result.exit_code == 0, result.output
    return graph_home


def _write(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(payload if isinstance(payload, str) else json.dumps(payload), encoding="utf-8")


def test_paths_live_in_graph_home(tmp_path: Path) -> None:
    assert dream_settings_path(tmp_path) == tmp_path / "configs" / "dream.json"
    assert dream_judged_path(tmp_path) == tmp_path / "dream" / "judged.jsonl"
    assert dream_runs_path(tmp_path) == tmp_path / "logs" / "dream-runs.jsonl"


def test_missing_file_means_off_with_the_approved_limits(tmp_path: Path) -> None:
    reading = read_dream_settings(dream_settings_path(tmp_path))

    assert reading.source == "default"
    assert reading.problem is None
    assert reading.settings == DreamSettings(
        enabled=False,
        model=DREAM_MODEL,
        pending_cap=10,
        proposals_per_run=10,
        interval_hours=24,
        bundle_limit=40,
        due_exchanges=20,
    )
    assert DREAM_MODEL == "claude-sonnet-5-5"
    assert not dream_settings_path(tmp_path).exists()


def test_save_then_read_round_trips(tmp_path: Path) -> None:
    path = dream_settings_path(tmp_path)
    settings = DreamSettings(enabled=True, model="claude-opus-5-5", pending_cap=4, due_exchanges=7)

    save_dream_settings(path, settings)

    assert read_dream_settings(path) == type(read_dream_settings(path))(settings=settings, source="file")
    assert json.loads(path.read_text(encoding="utf-8"))["version"] == 1


@pytest.mark.parametrize(
    ("payload", "words"),
    [
        ("{not json", "not valid JSON"),
        ([1], "JSON object"),
        ({**VALID, "extra": 1}, "unknown keys"),
        ({key: value for key, value in VALID.items() if key != "model"}, "missing keys"),
        ({**VALID, "version": 2}, "version must be 1"),
        ({**VALID, "enabled": "yes"}, "enabled must be true or false"),
        ({**VALID, "model": ""}, "model must be a non-empty string"),
        ({**VALID, "pending_cap": 0}, "pending_cap must be a whole number of at least 1"),
        ({**VALID, "interval_hours": 1.5}, "interval_hours must be a whole number"),
        ({**VALID, "bundle_limit": True}, "bundle_limit must be a whole number"),
    ],
)
def test_a_broken_file_reads_as_off_with_the_reason(tmp_path: Path, payload: object, words: str) -> None:
    path = dream_settings_path(tmp_path)
    _write(path, payload)

    reading = read_dream_settings(path)

    assert reading.source == "broken"
    assert reading.settings == DreamSettings()
    assert reading.problem is not None and words in reading.problem


def test_missing_file_runs_at_one_in_the_morning(tmp_path: Path) -> None:
    reading = read_dream_settings(dream_settings_path(tmp_path))

    assert DreamSettings().run_at == "01:00"
    assert reading.settings.run_at == "01:00"


def test_a_version_1_file_without_run_at_still_reads_from_the_file(tmp_path: Path) -> None:
    path = dream_settings_path(tmp_path)
    _write(path, {**VALID, "enabled": True, "pending_cap": 3, "due_exchanges": 7})

    reading = read_dream_settings(path)

    assert reading.source == "file"
    assert reading.problem is None
    assert reading.settings == replace(DreamSettings(), enabled=True, pending_cap=3, due_exchanges=7, run_at="01:00")


@pytest.mark.parametrize("run_at", ["00:00", "23:59", "13:05"])
def test_a_valid_run_at_is_read_from_the_file(tmp_path: Path, run_at: str) -> None:
    path = dream_settings_path(tmp_path)
    _write(path, {**VALID, "run_at": run_at})

    reading = read_dream_settings(path)

    assert reading.source == "file"
    assert reading.settings.run_at == run_at


@pytest.mark.parametrize(
    "run_at", ["1:00", "24:00", "01:60", 1, "", "01:00:00", "0100", " 01:00", "01:0", "１２:００", None]
)
def test_a_bad_run_at_breaks_the_whole_file(tmp_path: Path, run_at: object) -> None:
    path = dream_settings_path(tmp_path)
    _write(path, {**VALID, "run_at": run_at})

    reading = read_dream_settings(path)

    assert reading.source == "broken"
    assert reading.settings == DreamSettings()
    assert reading.problem is not None and "run_at must be HH:MM" in reading.problem


def test_saving_always_writes_run_at_with_version_1(tmp_path: Path) -> None:
    path = dream_settings_path(tmp_path)
    _write(path, {**VALID, "enabled": False})

    save_dream_settings(path, replace(read_dream_settings(path).settings, enabled=True))
    first = json.loads(path.read_text(encoding="utf-8"))
    assert first["run_at"] == "01:00"
    assert first["version"] == 1

    save_dream_settings(path, replace(DreamSettings(), run_at="23:59"))
    second = json.loads(path.read_text(encoding="utf-8"))
    assert second["run_at"] == "23:59"
    assert second["version"] == 1
    assert read_dream_settings(path).settings.run_at == "23:59"


@pytest.mark.parametrize("run_at", ["24:00", "1:00", ""])
def test_saving_a_bad_run_at_raises_and_keeps_the_file(tmp_path: Path, run_at: str) -> None:
    path = dream_settings_path(tmp_path)
    save_dream_settings(path, DreamSettings())
    before = path.read_bytes()

    with pytest.raises(CatalogError):
        save_dream_settings(path, replace(DreamSettings(), run_at=run_at))

    assert path.read_bytes() == before


def test_saving_invalid_settings_raises_and_writes_nothing(tmp_path: Path) -> None:
    path = dream_settings_path(tmp_path)

    with pytest.raises(CatalogError):
        save_dream_settings(path, replace(DreamSettings(), proposals_per_run=0))

    assert not path.exists()


def test_cli_status_is_off_before_anything_is_saved(tmp_path: Path) -> None:
    graph_home = _init_graph_home(tmp_path)

    result = runner.invoke(app, ["dream", "status", "--graph-home", str(graph_home)])

    assert result.exit_code == 0, result.output
    assert "dream: off" in result.output
    assert "model: claude-sonnet-5-5" in result.output
    assert "pending_cap=10 proposals_per_run=10 interval_hours=24 bundle_limit=40 due_exchanges=20" in result.output
    assert "settings: default (no file)" in result.output


def test_cli_on_and_off_keep_saved_limits(tmp_path: Path) -> None:
    graph_home = _init_graph_home(tmp_path)
    path = dream_settings_path(graph_home)
    _write(path, {**VALID, "enabled": False, "pending_cap": 3})

    on = runner.invoke(app, ["dream", "on", "--graph-home", str(graph_home)])
    assert on.exit_code == 0, on.output
    assert "dream: on" in on.output
    assert read_dream_settings(path).settings == replace(DreamSettings(), enabled=True, pending_cap=3)

    off = runner.invoke(app, ["dream", "off", "--graph-home", str(graph_home)])
    assert off.exit_code == 0, off.output
    assert "dream: off" in off.output
    assert read_dream_settings(path).settings == replace(DreamSettings(), enabled=False, pending_cap=3)


def test_cli_on_replaces_a_broken_file_and_status_shows_the_problem(tmp_path: Path) -> None:
    graph_home = _init_graph_home(tmp_path)
    path = dream_settings_path(graph_home)
    _write(path, "{broken")

    status = runner.invoke(app, ["dream", "status", "--graph-home", str(graph_home)])
    assert "dream: off" in status.output
    assert "settings: broken" in status.output
    assert "problem: dream settings file is not valid JSON" in status.output

    on = runner.invoke(app, ["dream", "on", "--graph-home", str(graph_home)])
    assert on.exit_code == 0, on.output
    assert read_dream_settings(path).settings == replace(DreamSettings(), enabled=True)


def test_cli_needs_an_initialized_graph_home(tmp_path: Path) -> None:
    result = runner.invoke(app, ["dream", "on", "--graph-home", str(tmp_path / "none")])

    assert result.exit_code == 1
    assert "graph_home_not_initialized" in result.output
