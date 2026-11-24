"""`vg dream on|off|at|scheduled` and the launchd schedule (spec 2026-11-24-dream-schedule-time D6, D13, F5, F6, F9).

Every test runs against the `fake_dream_schedule` fixture from `conftest.py`, so no test writes a real LaunchAgent
or runs `launchctl`.
"""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from tests.conftest import FakeDreamSchedule
from vault_graph.interface.cli import dream_commands
from vault_graph.interface.cli.main import app
from vault_graph.operation.scope.dream_settings import (
    DreamSettings,
    dream_settings_path,
    read_dream_settings,
    save_dream_settings,
)

runner = CliRunner()


@pytest.fixture
def graph_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    vault = tmp_path / "vault"
    (vault / "wiki").mkdir(parents=True)
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    graph_home = home / ".vault-graph"
    init = runner.invoke(app, ["init", "--vault", str(vault), "--graph-home", str(graph_home)])
    assert init.exit_code == 0, init.output
    return graph_home


def dream(graph_home: Path, *args: str) -> Any:
    return runner.invoke(app, ["dream", *args, "--graph-home", str(graph_home)])


def test_on_saves_then_installs_the_schedule_at_run_at(
    graph_home: Path, fake_dream_schedule: FakeDreamSchedule
) -> None:
    save_dream_settings(dream_settings_path(graph_home), DreamSettings(run_at="02:30"))

    result = dream(graph_home, "on")

    assert result.exit_code == 0, result.output
    assert read_dream_settings(dream_settings_path(graph_home)).settings.enabled
    assert fake_dream_schedule.calls == [("install", "02:30")]
    assert f"schedule: installed at 02:30 {fake_dream_schedule.plist_path}" in result.output


def test_off_removes_the_schedule(graph_home: Path, fake_dream_schedule: FakeDreamSchedule) -> None:
    dream(graph_home, "on")

    result = dream(graph_home, "off")

    assert result.exit_code == 0, result.output
    assert fake_dream_schedule.calls[-1] == ("remove", None)
    assert "schedule: removed" in result.output
    assert not read_dream_settings(dream_settings_path(graph_home)).settings.enabled


def test_a_failed_install_keeps_the_settings_and_ends_with_1(
    graph_home: Path, fake_dream_schedule: FakeDreamSchedule
) -> None:
    fake_dream_schedule.fail = "launchctl exited 5: Input/output error"

    result = dream(graph_home, "on")

    assert result.exit_code == 1
    assert "schedule: not installed: launchctl exited 5: Input/output error" in result.output
    assert "hook runs still work" in result.output
    assert read_dream_settings(dream_settings_path(graph_home)).settings.enabled


def test_a_failed_remove_ends_with_1_and_dreaming_stays_off(
    graph_home: Path, fake_dream_schedule: FakeDreamSchedule
) -> None:
    dream(graph_home, "on")
    fake_dream_schedule.fail = "launchctl exited 5: Input/output error"

    result = dream(graph_home, "off")

    assert result.exit_code == 1
    assert "schedule: not removed: launchctl exited 5: Input/output error" in result.output
    assert not read_dream_settings(dream_settings_path(graph_home)).settings.enabled


def test_off_macos_on_saves_and_reports_unsupported_with_0(
    graph_home: Path, fake_dream_schedule: FakeDreamSchedule
) -> None:
    fake_dream_schedule.platform = "linux"

    result = dream(graph_home, "on")

    assert result.exit_code == 0, result.output
    assert "schedule: unsupported on linux" in result.output
    assert fake_dream_schedule.installed_at is None
    assert read_dream_settings(dream_settings_path(graph_home)).settings.enabled


def test_at_saves_the_time_and_reinstalls_when_dreaming_is_on(
    graph_home: Path, fake_dream_schedule: FakeDreamSchedule
) -> None:
    dream(graph_home, "on")

    result = runner.invoke(app, ["dream", "at", "03:15", "--graph-home", str(graph_home)])

    assert result.exit_code == 0, result.output
    assert read_dream_settings(dream_settings_path(graph_home)).settings.run_at == "03:15"
    assert fake_dream_schedule.calls == [("install", "01:00"), ("install", "03:15")]
    assert "run_at: 03:15" in result.output


def test_at_only_saves_while_dreaming_is_off(graph_home: Path, fake_dream_schedule: FakeDreamSchedule) -> None:
    result = runner.invoke(app, ["dream", "at", "23:59", "--graph-home", str(graph_home)])

    assert result.exit_code == 0, result.output
    settings = read_dream_settings(dream_settings_path(graph_home)).settings
    assert (settings.enabled, settings.run_at) == (False, "23:59")
    assert fake_dream_schedule.calls == []
    assert "schedule: not installed (dreaming is off)" in result.output


@pytest.mark.parametrize("value", ["1:00", "24:00", "01:60", "", "0100"])
def test_at_refuses_a_bad_time_and_leaves_the_file(
    graph_home: Path, fake_dream_schedule: FakeDreamSchedule, value: str
) -> None:
    path = dream_settings_path(graph_home)
    save_dream_settings(path, replace(DreamSettings(), enabled=True, pending_cap=3))
    before = path.read_bytes()

    result = runner.invoke(app, ["dream", "at", value, "--graph-home", str(graph_home)])

    assert result.exit_code == 1
    assert "run_at must be HH:MM from 00:00 to 23:59" in result.output
    assert path.read_bytes() == before
    assert fake_dream_schedule.calls == []


def test_at_keeps_the_other_saved_settings(graph_home: Path) -> None:
    path = dream_settings_path(graph_home)
    save_dream_settings(path, replace(DreamSettings(), enabled=False, pending_cap=3))

    runner.invoke(app, ["dream", "at", "04:00", "--graph-home", str(graph_home)])

    assert read_dream_settings(path).settings == replace(DreamSettings(), pending_cap=3, run_at="04:00")


def test_scheduled_runs_every_project_and_exits_with_its_code(
    graph_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[Path] = []

    def fake_run(home: Path, **kwargs: Any) -> int:
        calls.append(home)
        kwargs["echo"]("alpha: ran judged=1 proposals=0")
        return 1

    monkeypatch.setattr(dream_commands, "_run_scheduled", fake_run)

    result = dream(graph_home, "scheduled")

    assert result.exit_code == 1
    assert calls == [graph_home.resolve()] or calls == [graph_home]
    assert "alpha: ran judged=1 proposals=0" in result.output


def test_scheduled_with_dreaming_off_judges_nothing(graph_home: Path) -> None:
    result = dream(graph_home, "scheduled")

    assert result.exit_code == 0, result.output
    assert "dream: skipped off" in result.output


def test_scheduled_is_hidden_from_help(graph_home: Path) -> None:
    result = runner.invoke(app, ["dream", "--help"])

    assert " at " in result.output
    assert "│ scheduled " not in result.output


def test_the_default_schedule_is_launchd_with_the_worker_script(tmp_path: Path) -> None:
    from vault_graph.interface.composition.adapters.dream_schedule import LaunchdDreamSchedule
    from vault_graph.interface.composition.adapters.dream_worker import WORKER_SCRIPT

    schedule = dream_commands._default_schedule(tmp_path)

    assert isinstance(schedule, LaunchdDreamSchedule)
    assert schedule.worker_script == WORKER_SCRIPT
    assert json.dumps(str(schedule.graph_home))


def _write_runs(graph_home: Path, lines: list[dict[str, Any]]) -> None:
    logs = graph_home / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    (logs / "dream-runs.jsonl").write_text("".join(json.dumps(line) + "\n" for line in lines), encoding="utf-8")


def test_status_shows_run_at_and_an_installed_schedule(
    graph_home: Path, fake_dream_schedule: FakeDreamSchedule
) -> None:
    dream(graph_home, "on")

    result = dream(graph_home, "status")

    assert result.exit_code == 0, result.output
    assert "run_at: 01:00 (local)" in result.output
    assert f"schedule: installed {fake_dream_schedule.plist_path}" in result.output
    assert "last_scheduled_run: -" in result.output
    assert "run `vg dream on` to install it" not in result.output


def test_status_tells_an_upgraded_user_to_install_the_schedule(graph_home: Path) -> None:
    save_dream_settings(dream_settings_path(graph_home), DreamSettings(enabled=True))

    result = dream(graph_home, "status")

    assert "schedule: not_installed" in result.output
    assert "run `vg dream on` to install it" in result.output


def test_status_shows_a_stale_schedule_when_the_time_differs(
    graph_home: Path, fake_dream_schedule: FakeDreamSchedule
) -> None:
    dream(graph_home, "on")
    save_dream_settings(dream_settings_path(graph_home), DreamSettings(enabled=True, run_at="04:00"))

    result = dream(graph_home, "status")

    assert "schedule: stale plist runs at 01:00, run_at is 04:00" in result.output
    assert "run `vg dream on` to install it" in result.output


def test_status_gives_no_install_hint_while_dreaming_is_off(graph_home: Path) -> None:
    result = dream(graph_home, "status")

    assert "schedule: not_installed" in result.output
    assert "run `vg dream on` to install it" not in result.output


def test_status_shows_unsupported_off_macos(graph_home: Path, fake_dream_schedule: FakeDreamSchedule) -> None:
    fake_dream_schedule.platform = "linux"

    result = dream(graph_home, "status")

    assert "schedule: unsupported on linux" in result.output


def test_status_shows_the_last_scheduled_run_only(graph_home: Path) -> None:
    _write_runs(
        graph_home,
        [
            {"record": "run", "at": "2026-11-23T16:00:05Z", "project": "a", "status": "ran", "trigger": "schedule"},
            {"record": "run", "at": "2026-11-24T03:00:00Z", "project": "a", "status": "ran", "trigger": "hook"},
            {"record": "run", "at": "2026-11-24T05:00:00Z", "project": "b", "status": "ran"},
        ],
    )

    result = dream(graph_home, "status")

    assert "last_scheduled_run: 2026-11-23T16:00:05Z" in result.output


def test_status_keeps_its_earlier_lines(graph_home: Path) -> None:
    result = dream(graph_home, "status")

    assert result.output.splitlines()[:2] == ["dream: off", "model: claude-sonnet-5-5"]
    assert "settings: default (no file)" in result.output
