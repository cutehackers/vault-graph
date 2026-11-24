"""The scheduled dream run: every registered project, one at a time (spec 2026-11-24-dream-schedule-time D3, D8).

launchd starts one `vg dream scheduled` at the set time of day. That one process walks the `vault-map.json`
projects in id order and runs one dream per project with `trigger="schedule"`, so projects never wait on each
other inside it.

For each project:

- A project whose `root` is empty or not a folder is skipped with one line and no `run` line (F1).
- The worker lock `logs/dream-worker.lock` is polled without blocking for up to `LOCK_WAIT_SECONDS`. A hook run
  that is still going at the set time holds it. Past the wait, the project gets a `locked` `run` line, which does
  not start the hook interval, and the next project gets its own wait (D8, F3).
- `run_dream_locked` runs with the root as its `cwd`, and the judge runs `claude -p` in the root too (D10).
- Skipped and failed runs are reported and the walk goes on (F2, F11). A `VaultGraphError` or `OSError`, or ports
  that cannot be opened, is reported with the project id and the whole run ends with 1 (F12).

Dreaming off, or a broken settings file, prints "dream: skipped off" and judges nothing (F4, F8).
"""

from __future__ import annotations

import fcntl
import os
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from vault_graph.errors import VaultGraphError
from vault_graph.interface.composition.adapters.dream_worker import (
    DREAM_WORKER_LOCK,
    DreamRun,
    log_locked_run,
    run_dream_locked,
)
from vault_graph.operation.integration.vault_map import VaultMap
from vault_graph.operation.scope.dream_settings import dream_settings_path, read_dream_settings

LOCK_WAIT_SECONDS = 30 * 60
"""How long the scheduled run waits for the worker lock before it skips a project (D8)."""
LOCK_POLL_SECONDS = 5.0


def run_scheduled_dreams(
    graph_home: Path,
    *,
    vault_map: VaultMap | None,
    open_ports: Callable[[Path], Any],
    run_locked: Callable[..., DreamRun | None] = run_dream_locked,
    echo: Callable[[str], None] = print,
    lock_wait_seconds: float = LOCK_WAIT_SECONDS,
    poll_seconds: float = LOCK_POLL_SECONDS,
    sleep: Callable[[float], None] = time.sleep,
    monotonic: Callable[[], float] = time.monotonic,
    no_vault_map_reason: str = "no usable vault-map.json",
) -> int:
    """Run one scheduled dream for every registered project. Returns the exit code.

    ``open_ports(root)`` builds the dream ports for one project, with the judge running in ``root``, or returns the
    reason it cannot. ``vault_map`` None means no usable `vault-map.json`.
    """
    settings = read_dream_settings(dream_settings_path(graph_home)).settings
    if not settings.enabled:
        echo("dream: skipped off")
        return 0
    if vault_map is None:
        echo(f"dream: skipped no_vault_map: {no_vault_map_reason}")
        return 1

    errors = 0
    for project in vault_map.projects:
        project_id = project.project_id
        root = Path(project.root).expanduser() if project.root else None
        if root is None or not root.is_dir():
            echo(f"skipped {project_id}: root missing {project.root}")
            continue
        try:
            ports = open_ports(root)
            if isinstance(ports, str):
                echo(f"error {project_id}: {ports}")
                errors += 1
                continue
            lock_fd = _wait_for_lock(graph_home, lock_wait_seconds, poll_seconds, sleep, monotonic)
            if lock_fd is None:
                log_locked_run(graph_home, project_id, root)
                echo(f"skipped {project_id}: locked")
                continue
            result = run_locked(graph_home, root, settings, ports, lock_fd=lock_fd, trigger="schedule")
        except (VaultGraphError, OSError) as exc:
            echo(f"error {project_id}: {exc}")
            errors += 1
            continue
        if result is None:
            # Only when the lock was taken again between the wait and the run, which the held descriptor prevents.
            echo(f"skipped {project_id}: locked")
            continue
        echo(_describe(project_id, result))
    return 1 if errors else 0


def _wait_for_lock(
    graph_home: Path,
    wait_seconds: float,
    poll_seconds: float,
    sleep: Callable[[float], None],
    monotonic: Callable[[], float],
) -> int | None:
    """A descriptor of the worker lock, already locked, or None when it stayed taken for ``wait_seconds``."""
    (graph_home / DREAM_WORKER_LOCK.parent).mkdir(parents=True, exist_ok=True)
    descriptor = os.open(graph_home / DREAM_WORKER_LOCK, os.O_RDWR | os.O_CREAT, 0o644)
    deadline = monotonic() + wait_seconds
    try:
        while True:
            try:
                fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
                return descriptor
            except BlockingIOError:
                if monotonic() >= deadline:
                    break
                sleep(poll_seconds)
    except BaseException:
        os.close(descriptor)
        raise
    os.close(descriptor)
    return None


def _describe(project_id: str, result: DreamRun) -> str:
    line = f"{project_id}: {result.status}"
    if result.reason is not None:
        line += f" {result.reason}"
    if result.status != "skipped":
        line += f" judged={result.judged} proposals={len(result.proposals)}"
    if result.message:
        line += f" ({result.message})"
    return line


__all__ = ["LOCK_POLL_SECONDS", "LOCK_WAIT_SECONDS", "run_scheduled_dreams"]
