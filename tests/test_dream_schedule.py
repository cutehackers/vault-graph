"""The launchd schedule for dreaming (spec 2026-11-24-dream-schedule-time D4, D11, I6, A3).

Every test gives `LaunchdDreamSchedule` a temporary LaunchAgents folder and a `launchctl` function that only
records its arguments, so no test writes under `$HOME/Library/LaunchAgents` or runs the real `launchctl`.
"""

from __future__ import annotations

import hashlib
import plistlib
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import pytest

from vault_graph.interface.composition.adapters.dream_schedule import (
    DREAM_SCHEDULE_LOG,
    DreamSchedule,
    LaunchctlResult,
    LaunchdDreamSchedule,
    ScheduleResult,
    ScheduleState,
    dream_schedule_label,
    render_dream_plist,
)

WORKER_SCRIPT = "from vault_graph.interface.cli.main import app; app()"
UID = 501


class RecordingLaunchctl:
    """Records each `launchctl` call and answers from a queue of results (success when the queue is empty)."""

    def __init__(self, answers: Sequence[LaunchctlResult] = ()) -> None:
        self.calls: list[tuple[str, ...]] = []
        self._answers = list(answers)

    def __call__(self, arguments: Sequence[str]) -> LaunchctlResult:
        self.calls.append(tuple(arguments))
        if self._answers:
            return self._answers.pop(0)
        return LaunchctlResult(returncode=0, output="")


@pytest.fixture(autouse=True)
def fake_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point HOME at a temporary folder so a stray default would land there, not in the real LaunchAgents."""
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    return home


def make_schedule(
    tmp_path: Path,
    launchctl: RecordingLaunchctl,
    *,
    platform: str = "darwin",
    python: str = sys.executable,
    environ: dict[str, str] | None = None,
) -> LaunchdDreamSchedule:
    return LaunchdDreamSchedule(
        tmp_path / "graph-home",
        worker_script=WORKER_SCRIPT,
        launch_agents=tmp_path / "LaunchAgents",
        launchctl=launchctl,
        platform=platform,
        python=python,
        environ=environ if environ is not None else {"PATH": "/usr/bin:/bin", "HOME": "/Users/someone"},
        uid=UID,
    )


def read_plist(path: Path) -> dict[str, Any]:
    with path.open("rb") as handle:
        loaded: dict[str, Any] = plistlib.load(handle)
    return loaded


def test_label_carries_the_graph_home_hash(tmp_path: Path) -> None:
    graph_home = tmp_path / "graph-home"
    digest = hashlib.sha256(str(graph_home.resolve()).encode("utf-8")).hexdigest()[:8]

    assert dream_schedule_label(graph_home) == f"io.vault-graph.dream.{digest}"


def test_render_dream_plist_is_pure_and_holds_run_at(tmp_path: Path) -> None:
    graph_home = tmp_path / "graph-home"
    arguments: dict[str, Any] = {
        "label": "io.vault-graph.dream.abcd1234",
        "python": "/opt/python3",
        "worker_script": WORKER_SCRIPT,
        "graph_home": graph_home,
        "run_at": "02:30",
        "environment": {"PATH": "/usr/bin", "HOME": "/Users/someone"},
    }

    first = render_dream_plist(**arguments)
    second = render_dream_plist(**arguments)
    loaded = plistlib.loads(first)

    assert first == second
    assert not graph_home.exists()
    assert loaded["StartCalendarInterval"] == {"Hour": 2, "Minute": 30}
    assert loaded["ProgramArguments"] == [
        "/opt/python3",
        "-c",
        WORKER_SCRIPT,
        "dream",
        "scheduled",
        "--graph-home",
        str(graph_home),
    ]


@pytest.mark.parametrize("run_at", ["1:00", "24:00", "01:60", ""])
def test_render_dream_plist_rejects_a_bad_time(tmp_path: Path, run_at: str) -> None:
    with pytest.raises(ValueError):
        render_dream_plist(
            label="io.vault-graph.dream.abcd1234",
            python="/opt/python3",
            worker_script=WORKER_SCRIPT,
            graph_home=tmp_path,
            run_at=run_at,
            environment={},
        )


def test_install_writes_the_plist_then_bootstraps(tmp_path: Path) -> None:
    launchctl = RecordingLaunchctl()
    schedule = make_schedule(
        tmp_path,
        launchctl,
        environ={
            "PATH": "/usr/bin:/bin",
            "HOME": "/Users/someone",
            "VAULT_GRAPH_VAULT_MAP": "/Users/someone/vault-map.json",
            "CLAUDE_CONFIG_DIR": "/Users/someone/.claude-alt",
            "ANTHROPIC_API_KEY": "secret",
        },
    )
    graph_home = tmp_path / "graph-home"
    label = dream_schedule_label(graph_home)
    plist_path = tmp_path / "LaunchAgents" / f"{label}.plist"

    result = schedule.install("01:15")

    assert result == ScheduleResult(ok=True, status="installed", plist_path=plist_path, reason="")
    loaded = read_plist(plist_path)
    assert loaded["Label"] == label
    assert loaded["StartCalendarInterval"] == {"Hour": 1, "Minute": 15}
    assert loaded["ProgramArguments"] == [
        sys.executable,
        "-c",
        WORKER_SCRIPT,
        "dream",
        "scheduled",
        "--graph-home",
        str(graph_home),
    ]
    assert loaded["EnvironmentVariables"] == {
        "PATH": "/usr/bin:/bin",
        "HOME": "/Users/someone",
        "VAULT_GRAPH_VAULT_MAP": "/Users/someone/vault-map.json",
        "CLAUDE_CONFIG_DIR": "/Users/someone/.claude-alt",
    }
    log_path = str(graph_home / DREAM_SCHEDULE_LOG)
    assert DREAM_SCHEDULE_LOG == Path("logs/dream-schedule.log")
    assert loaded["StandardOutPath"] == log_path
    assert loaded["StandardErrorPath"] == log_path
    assert (graph_home / "logs").is_dir()
    assert launchctl.calls[-1] == ("bootstrap", f"gui/{UID}", str(plist_path))
    assert ("bootstrap", f"gui/{UID}", str(plist_path)) not in launchctl.calls[:-1]


def test_environment_leaves_out_optional_keys_that_are_not_set(tmp_path: Path) -> None:
    schedule = make_schedule(tmp_path, RecordingLaunchctl(), environ={"PATH": "/usr/bin", "HOME": "/Users/x"})

    result = schedule.install("01:00")

    assert result.plist_path is not None
    assert read_plist(result.plist_path)["EnvironmentVariables"] == {"PATH": "/usr/bin", "HOME": "/Users/x"}


def test_install_again_boots_out_first(tmp_path: Path) -> None:
    launchctl = RecordingLaunchctl()
    schedule = make_schedule(tmp_path, launchctl)
    label = dream_schedule_label(tmp_path / "graph-home")
    schedule.install("01:00")
    launchctl.calls.clear()

    result = schedule.install("03:45")

    assert result.ok
    assert result.plist_path is not None
    assert [call[0] for call in launchctl.calls] == ["bootout", "bootstrap"]
    assert launchctl.calls[0] == ("bootout", f"gui/{UID}/{label}")
    assert read_plist(result.plist_path)["StartCalendarInterval"] == {"Hour": 3, "Minute": 45}


def test_install_failure_reports_the_reason_and_leaves_no_plist(tmp_path: Path) -> None:
    launchctl = RecordingLaunchctl(
        [
            LaunchctlResult(returncode=3, output="Boot-out failed: 3: No such process"),
            LaunchctlResult(returncode=5, output="Bootstrap failed: 5: Input/output error"),
        ]
    )
    schedule = make_schedule(tmp_path, launchctl)

    result = schedule.install("01:00")

    assert not result.ok
    assert result.status == "not_installed"
    assert "Bootstrap failed" in result.reason
    assert list((tmp_path / "LaunchAgents").glob("*.plist")) == []


def test_install_rejects_a_bad_time_without_calling_launchctl(tmp_path: Path) -> None:
    launchctl = RecordingLaunchctl()
    schedule = make_schedule(tmp_path, launchctl)

    with pytest.raises(ValueError):
        schedule.install("25:00")

    assert launchctl.calls == []
    assert not (tmp_path / "LaunchAgents").exists()


def test_remove_boots_out_then_deletes_the_plist(tmp_path: Path) -> None:
    launchctl = RecordingLaunchctl()
    schedule = make_schedule(tmp_path, launchctl)
    label = dream_schedule_label(tmp_path / "graph-home")
    installed = schedule.install("01:00")
    launchctl.calls.clear()

    result = schedule.remove()

    assert result.ok
    assert result.status == "not_installed"
    assert launchctl.calls == [("bootout", f"gui/{UID}/{label}")]
    assert installed.plist_path is not None
    assert not installed.plist_path.exists()


@pytest.mark.parametrize(
    "answer",
    [
        LaunchctlResult(returncode=3, output="Boot-out failed: 3: No such process"),
        LaunchctlResult(returncode=113, output="Could not find specified service"),
    ],
)
def test_remove_counts_not_loaded_as_success(tmp_path: Path, answer: LaunchctlResult) -> None:
    schedule = make_schedule(tmp_path, RecordingLaunchctl([answer]))

    result = schedule.remove()

    assert result.ok
    assert result.status == "not_installed"


def test_remove_reports_another_bootout_failure_and_keeps_the_plist(tmp_path: Path) -> None:
    launchctl = RecordingLaunchctl()
    schedule = make_schedule(tmp_path, launchctl)
    installed = schedule.install("01:00")
    launchctl._answers.append(LaunchctlResult(returncode=1, output="Operation not permitted"))

    result = schedule.remove()

    assert not result.ok
    assert result.status == "installed"
    assert "Operation not permitted" in result.reason
    assert installed.plist_path is not None
    assert installed.plist_path.exists()


def test_state_reads_the_plist(tmp_path: Path) -> None:
    launchctl = RecordingLaunchctl()
    schedule = make_schedule(tmp_path, launchctl)

    assert schedule.state().status == "not_installed"
    installed = schedule.install("01:00")
    calls_after_install = list(launchctl.calls)

    assert schedule.state() == ScheduleState(status="installed", plist_path=installed.plist_path, reason="")
    assert schedule.state("01:00").status == "installed"
    assert launchctl.calls == calls_after_install


def test_state_is_stale_when_the_time_differs(tmp_path: Path) -> None:
    schedule = make_schedule(tmp_path, RecordingLaunchctl())
    schedule.install("01:00")

    state = schedule.state("02:00")

    assert state.status == "stale"
    assert "01:00" in state.reason
    assert "02:00" in state.reason


def test_state_is_stale_when_the_python_is_gone(tmp_path: Path) -> None:
    missing_python = str(tmp_path / "gone" / "python3")
    schedule = make_schedule(tmp_path, RecordingLaunchctl(), python=missing_python)
    schedule.install("01:00")

    state = schedule.state("01:00")

    assert state.status == "stale"
    assert missing_python in state.reason


def test_state_is_stale_when_the_plist_is_unreadable(tmp_path: Path) -> None:
    schedule = make_schedule(tmp_path, RecordingLaunchctl())
    installed = schedule.install("01:00")
    assert installed.plist_path is not None
    installed.plist_path.write_text("not a plist", encoding="utf-8")

    assert schedule.state().status == "stale"


def test_other_platforms_are_unsupported_and_touch_nothing(tmp_path: Path) -> None:
    launchctl = RecordingLaunchctl()
    schedule = make_schedule(tmp_path, launchctl, platform="linux")

    installed = schedule.install("01:00")
    removed = schedule.remove()
    state = schedule.state("01:00")

    assert installed == ScheduleResult(ok=True, status="unsupported", plist_path=None, reason="unsupported on linux")
    assert removed.status == "unsupported"
    assert removed.ok
    assert state == ScheduleState(status="unsupported", plist_path=None, reason="unsupported on linux")
    assert launchctl.calls == []
    assert not (tmp_path / "LaunchAgents").exists()
    assert not (tmp_path / "graph-home").exists()


def test_launchd_schedule_meets_the_protocol(tmp_path: Path) -> None:
    schedule: DreamSchedule = make_schedule(tmp_path, RecordingLaunchctl())

    assert schedule.state().status == "not_installed"


def test_default_folder_is_the_user_launch_agents_and_tests_never_touch_it(tmp_path: Path, fake_home: Path) -> None:
    launchctl = RecordingLaunchctl()
    default = LaunchdDreamSchedule(tmp_path / "graph-home", worker_script=WORKER_SCRIPT, launchctl=launchctl)
    schedule = make_schedule(tmp_path, launchctl)

    schedule.install("01:00")
    schedule.state("01:00")
    schedule.remove()

    assert default.launch_agents == fake_home / "Library" / "LaunchAgents"
    assert not (fake_home / "Library").exists()
