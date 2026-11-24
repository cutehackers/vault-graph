"""Port of the dream schedule and its launchd implementation (spec 2026-11-24-dream-schedule-time D4, D11, I6).

A schedule runs `vg dream scheduled --graph-home <Graph Home>` once a day at the local time ``run_at`` ("HH:MM").
``DreamSchedule`` is the port the CLI uses: ``install(run_at)``, ``remove()``, ``state()``.

``LaunchdDreamSchedule`` writes one LaunchAgent plist per Graph Home and loads it with `launchctl bootstrap
gui/<uid>`. The label is `io.vault-graph.dream.<first 8 hex of sha256(Graph Home absolute path)>`. The plist
records the Python that installed it, the worker script the caller passes, and that process's `PATH`, `HOME`, and
(when set) `VAULT_GRAPH_VAULT_MAP` and `CLAUDE_CONFIG_DIR`, because the judge finds `claude` on `PATH`. Output goes
to `logs/dream-schedule.log` under the Graph Home.

The LaunchAgents folder and the `launchctl` function are injected, so tests never write under
`$HOME/Library/LaunchAgents` or run the real `launchctl` (I6). Off macOS every call answers ``unsupported`` and
touches no file and runs no command.
"""

from __future__ import annotations

import hashlib
import os
import plistlib
import re
import subprocess
import sys
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Protocol

DREAM_SCHEDULE_LOG = Path("logs") / "dream-schedule.log"
LABEL_PREFIX = "io.vault-graph.dream."
LAUNCHD_PLATFORM = "darwin"
OPTIONAL_ENVIRONMENT_KEYS: tuple[str, ...] = ("VAULT_GRAPH_VAULT_MAP", "CLAUDE_CONFIG_DIR")

# `launchctl bootout` answers these when the job is not loaded: 3 is ESRCH ("No such process"), 113 is
# "Could not find specified service". Removing a job that is not loaded counts as done.
_NOT_LOADED_CODES = frozenset({3, 113})
_NOT_LOADED_TEXTS = ("No such process", "Could not find specified service")
_LAUNCHCTL_TIMEOUT_SECONDS = 30
_RUN_AT = re.compile(r"([01]\d|2[0-3]):([0-5]\d)")

ScheduleStatus = Literal["installed", "not_installed", "stale", "unsupported"]


@dataclass(frozen=True)
class ScheduleState:
    """What the schedule looks like now. ``plist_path`` is set when a plist file exists; ``reason`` explains
    ``stale`` and ``unsupported``."""

    status: ScheduleStatus
    plist_path: Path | None
    reason: str


@dataclass(frozen=True)
class ScheduleResult:
    """The outcome of ``install`` or ``remove``. ``status`` is the state after the call; ``reason`` says why it
    failed or, for ``unsupported``, which platform."""

    ok: bool
    status: ScheduleStatus
    plist_path: Path | None
    reason: str


@dataclass(frozen=True)
class LaunchctlResult:
    """Exit code and combined stdout and stderr of one `launchctl` call."""

    returncode: int
    output: str


LaunchctlRunner = Callable[[Sequence[str]], LaunchctlResult]


class DreamSchedule(Protocol):
    """Installs, removes, and reports the OS job that runs dreaming at ``run_at`` each day."""

    def install(self, run_at: str) -> ScheduleResult: ...

    def remove(self) -> ScheduleResult: ...

    def state(self, run_at: str | None = None) -> ScheduleState: ...


def run_launchctl(arguments: Sequence[str]) -> LaunchctlResult:
    """Run the real `launchctl` with ``arguments``. Only the default of ``LaunchdDreamSchedule`` uses this."""
    try:
        completed = subprocess.run(
            ["launchctl", *arguments],
            capture_output=True,
            text=True,
            check=False,
            timeout=_LAUNCHCTL_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        return LaunchctlResult(returncode=-1, output=str(error))
    return LaunchctlResult(returncode=completed.returncode, output=(completed.stdout + completed.stderr).strip())


def dream_schedule_label(graph_home: Path) -> str:
    """The launchd label for ``graph_home``: one job per Graph Home."""
    digest = hashlib.sha256(str(graph_home.resolve()).encode("utf-8")).hexdigest()[:8]
    return f"{LABEL_PREFIX}{digest}"


def parse_run_at(run_at: str) -> tuple[int, int]:
    """``(hour, minute)`` from "HH:MM" (00:00 to 23:59). Raises ``ValueError`` for any other text."""
    match = _RUN_AT.fullmatch(run_at)
    if match is None:
        raise ValueError(f"run_at must be HH:MM between 00:00 and 23:59, got {run_at!r}")
    return int(match.group(1)), int(match.group(2))


def render_dream_plist(
    *,
    label: str,
    python: str,
    worker_script: str,
    graph_home: Path,
    run_at: str,
    environment: Mapping[str, str],
) -> bytes:
    """The LaunchAgent plist text for one Graph Home. Pure: it reads and writes nothing."""
    hour, minute = parse_run_at(run_at)
    log_path = str(graph_home / DREAM_SCHEDULE_LOG)
    document = {
        "Label": label,
        "ProgramArguments": [python, "-c", worker_script, "dream", "scheduled", "--graph-home", str(graph_home)],
        "EnvironmentVariables": dict(environment),
        "StartCalendarInterval": {"Hour": hour, "Minute": minute},
        "StandardOutPath": log_path,
        "StandardErrorPath": log_path,
        "ProcessType": "Background",
    }
    return plistlib.dumps(document)


class LaunchdDreamSchedule:
    """``DreamSchedule`` over a macOS LaunchAgent. ``launch_agents`` and ``launchctl`` default to the real ones."""

    def __init__(
        self,
        graph_home: Path,
        *,
        worker_script: str,
        launch_agents: Path | None = None,
        launchctl: LaunchctlRunner = run_launchctl,
        platform: str = sys.platform,
        python: str = sys.executable,
        environ: Mapping[str, str] | None = None,
        uid: int | None = None,
    ) -> None:
        self.graph_home = graph_home
        self.worker_script = worker_script
        self.launch_agents = launch_agents if launch_agents is not None else Path.home() / "Library" / "LaunchAgents"
        self.platform = platform
        self.python = python
        self.label = dream_schedule_label(graph_home)
        self.plist_path = self.launch_agents / f"{self.label}.plist"
        self._launchctl = launchctl
        self._environ = environ if environ is not None else os.environ
        self._uid = uid if uid is not None else os.getuid()

    @property
    def _supported(self) -> bool:
        return self.platform == LAUNCHD_PLATFORM

    @property
    def _unsupported_reason(self) -> str:
        return f"unsupported on {self.platform}"

    def install(self, run_at: str) -> ScheduleResult:
        """Write the plist for ``run_at`` and load it, booting out a loaded copy first."""
        text = render_dream_plist(
            label=self.label,
            python=self.python,
            worker_script=self.worker_script,
            graph_home=self.graph_home,
            run_at=run_at,
            environment=self._environment(),
        )
        if not self._supported:
            return ScheduleResult(ok=True, status="unsupported", plist_path=None, reason=self._unsupported_reason)
        booted_out = self._bootout()
        if booted_out is not None:
            return ScheduleResult(ok=False, status="not_installed", plist_path=None, reason=booted_out)
        (self.graph_home / DREAM_SCHEDULE_LOG.parent).mkdir(parents=True, exist_ok=True)
        self.launch_agents.mkdir(parents=True, exist_ok=True)
        temporary = self.plist_path.with_name(f".{self.plist_path.name}.tmp")
        temporary.write_bytes(text)
        os.replace(temporary, self.plist_path)
        loaded = self._launchctl(["bootstrap", self._domain, str(self.plist_path)])
        if loaded.returncode != 0:
            # An unloaded plist would read as installed, so it goes too.
            self.plist_path.unlink(missing_ok=True)
            return ScheduleResult(ok=False, status="not_installed", plist_path=None, reason=_failure(loaded))
        return ScheduleResult(ok=True, status="installed", plist_path=self.plist_path, reason="")

    def remove(self) -> ScheduleResult:
        """Boot the job out, then delete the plist. A job that is not loaded counts as removed."""
        if not self._supported:
            return ScheduleResult(ok=True, status="unsupported", plist_path=None, reason=self._unsupported_reason)
        booted_out = self._bootout()
        if booted_out is not None:
            status: ScheduleStatus = "installed" if self.plist_path.exists() else "not_installed"
            plist_path = self.plist_path if status == "installed" else None
            return ScheduleResult(ok=False, status=status, plist_path=plist_path, reason=booted_out)
        self.plist_path.unlink(missing_ok=True)
        return ScheduleResult(ok=True, status="not_installed", plist_path=None, reason="")

    def state(self, run_at: str | None = None) -> ScheduleState:
        """Read the plist without running `launchctl`. ``stale`` when its Python is gone or, given ``run_at``,
        its time differs."""
        if not self._supported:
            return ScheduleState(status="unsupported", plist_path=None, reason=self._unsupported_reason)
        if not self.plist_path.exists():
            return ScheduleState(status="not_installed", plist_path=None, reason="")
        try:
            with self.plist_path.open("rb") as handle:
                document = plistlib.load(handle)
            python = str(document["ProgramArguments"][0])
            interval = document["StartCalendarInterval"]
            installed_at = f"{int(interval['Hour']):02d}:{int(interval['Minute']):02d}"
        except (OSError, plistlib.InvalidFileException, KeyError, IndexError, TypeError, ValueError) as error:
            return ScheduleState(status="stale", plist_path=self.plist_path, reason=f"unreadable plist: {error}")
        if not Path(python).exists():
            return ScheduleState(status="stale", plist_path=self.plist_path, reason=f"python not found: {python}")
        if run_at is not None and installed_at != run_at:
            reason = f"plist runs at {installed_at}, run_at is {run_at}"
            return ScheduleState(status="stale", plist_path=self.plist_path, reason=reason)
        return ScheduleState(status="installed", plist_path=self.plist_path, reason="")

    @property
    def _domain(self) -> str:
        return f"gui/{self._uid}"

    def _bootout(self) -> str | None:
        """Unload the job. None when it is gone afterwards (including when it was never loaded), else the reason."""
        result = self._launchctl(["bootout", f"{self._domain}/{self.label}"])
        if result.returncode == 0 or _not_loaded(result):
            return None
        return _failure(result)

    def _environment(self) -> dict[str, str]:
        environment = {
            "PATH": self._environ.get("PATH", os.defpath),
            "HOME": self._environ.get("HOME", str(Path.home())),
        }
        for key in OPTIONAL_ENVIRONMENT_KEYS:
            value = self._environ.get(key)
            if value:
                environment[key] = value
        return environment


def _not_loaded(result: LaunchctlResult) -> bool:
    return result.returncode in _NOT_LOADED_CODES or any(text in result.output for text in _NOT_LOADED_TEXTS)


def _failure(result: LaunchctlResult) -> str:
    return f"launchctl exited {result.returncode}: {result.output}".rstrip(": ")
