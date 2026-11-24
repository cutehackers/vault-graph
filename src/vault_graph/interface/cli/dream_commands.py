"""Thin Typer adapter for dreaming: `vg dream on|off|at|status|run|worker|scheduled` (spec 2026-11-19 §3, OD2).

Dreaming is off when `configs/dream.json` does not exist. `on` and `off` keep the saved model and limits and
replace a broken file with the defaults. `status` shows the settings in use, the reason a broken file was
rejected, the last run of each project, how many dream proposals were accepted, rejected or still wait, and
whether a write Vault is at the pending cap. An accept counts only when the Vault published it; an item whose
`status` was set to `accepted` by hand is counted as unpublished and listed with how to fix it (spec 2026-11-20 D7).

`run` does one dream run for a project folder by hand. It does not look at on or off, at the time since the last
run, or at whether a run is due; the pending cap still holds. `--dry-run` judges and prints what it would
propose, and writes nothing to a Vault or to the dream records. `worker` is the run the capture hook starts
detached (`interface/composition/adapters/dream_worker.py`); it follows every rule.

The scheduled run (spec 2026-11-24-dream-schedule-time): `on` saves the settings and installs one launchd job that
runs `vg dream scheduled` at `run_at` local time, and `off` removes it. `at HH:MM` saves `run_at` and, while
dreaming is on, installs the job again for the new time. A failed install or removal keeps the saved settings,
says why and ends with 1; the hook runs keep working (D13). Off macOS nothing is installed and the commands end
with 0 (F5). `scheduled` is the hidden command the job runs: every registered project in turn
(`interface/composition/adapters/dream_scheduled_run.py`).
"""

from __future__ import annotations

import os
from collections.abc import Callable, Mapping
from dataclasses import replace
from pathlib import Path
from typing import TYPE_CHECKING, Any

import typer

from vault_graph.errors import DataHomeNotInitializedError, VaultGraphError
from vault_graph.operation.scope.catalog_service import CatalogService
from vault_graph.operation.scope.dream_settings import (
    DreamSettings,
    dream_settings_path,
    is_valid_run_at,
    read_dream_settings,
    save_dream_settings,
)
from vault_graph.operation.scope.graph_home import GraphHomeResolver

if TYPE_CHECKING:
    from vault_graph.interface.composition.adapters.dream_schedule import DreamSchedule
    from vault_graph.interface.composition.adapters.dream_worker import DreamRun, Trigger

dream_app = typer.Typer(no_args_is_help=True)

# Module-level option values keep ruff B008 satisfied without a per-file ignore.
_GRAPH_HOME_OPTION = typer.Option(Path.home() / ".vault-graph", "--graph-home", help="Vault Graph Data Home path.")

_CWD_OPTION = typer.Option(None, "--cwd", help="Project folder to dream for. Default: the current folder.")
_WORKER_CWD_OPTION = typer.Option(..., "--cwd", help="Project folder of the captured session.")
_VAULT_MAP_OPTION = typer.Option(None, "--vault-map", help="vault-map.json path. Default: the usual lookup.")
_DRY_RUN_OPTION = typer.Option(
    False, "--dry-run", help="Judge and print what would be proposed. Writes nothing to a Vault or the dream records."
)
_LOCK_FD_OPTION = typer.Option(
    None, "--lock-fd", hidden=True, help="Descriptor of logs/dream-worker.lock, already locked by the starter."
)

_RUN_AT_ARGUMENT = typer.Argument(..., help="Local time of the daily scheduled run, HH:MM (00:00-23:59).")

_NOT_INITIALIZED = "graph_home_not_initialized: run `vg init --vault PATH --graph-home PATH` first"
_SOURCE_LABELS = {"default": "default (no file)", "file": "file", "broken": "broken"}


@dream_app.command("on")
def turn_on(state: Path = _GRAPH_HOME_OPTION) -> None:
    """Turn dreaming on: after a captured session and daily at `run_at`, propose memories for review."""
    settings_path, settings = _save(state, lambda saved: replace(saved, enabled=True))
    typer.echo("dream: on")
    typer.echo(f"dream_settings: {settings_path}")
    _install(settings_path.parent.parent, settings.run_at)


@dream_app.command("off")
def turn_off(state: Path = _GRAPH_HOME_OPTION) -> None:
    """Turn dreaming off and remove the daily schedule. Proposals already in a Vault review queue stay there."""
    settings_path, _ = _save(state, lambda saved: replace(saved, enabled=False))
    typer.echo("dream: off")
    typer.echo(f"dream_settings: {settings_path}")
    result = _schedule_for(settings_path.parent.parent).remove()
    if result.status == "unsupported":
        typer.echo(f"schedule: {result.reason}")
    elif not result.ok:
        typer.echo(f"schedule: not removed: {result.reason}")
        raise typer.Exit(1)
    else:
        typer.echo("schedule: removed")


@dream_app.command("at")
def set_run_at(run_at: str = _RUN_AT_ARGUMENT, state: Path = _GRAPH_HOME_OPTION) -> None:
    """Set the local time of the daily scheduled run, for example `vg dream at 01:00`."""
    if not is_valid_run_at(run_at):
        typer.echo(f"dream: run_at must be HH:MM from 00:00 to 23:59, got {run_at!r}")
        raise typer.Exit(1)
    settings_path, settings = _save(state, lambda saved: replace(saved, run_at=run_at))
    typer.echo(f"run_at: {run_at} (local)")
    typer.echo(f"dream_settings: {settings_path}")
    if not settings.enabled:
        typer.echo("schedule: not installed (dreaming is off)")
        return
    _install(settings_path.parent.parent, run_at)


@dream_app.command("scheduled", hidden=True)
def scheduled(state: Path = _GRAPH_HOME_OPTION) -> None:
    """The run the launchd job starts at `run_at`: every registered project, one at a time."""
    try:
        catalog_service = _catalog_service(state)
    except VaultGraphError as exc:
        typer.echo(str(exc))
        raise typer.Exit(1) from exc
    code = _run_scheduled(catalog_service.graph_home_path, echo=typer.echo)
    if code:
        raise typer.Exit(code)


@dream_app.command("status")
def status(state: Path = _GRAPH_HOME_OPTION) -> None:
    """Show whether dreaming is on, its model and its limits."""
    try:
        catalog_service = _catalog_service(state)
    except VaultGraphError as exc:
        typer.echo(str(exc))
        raise typer.Exit(1) from exc
    settings_path = dream_settings_path(catalog_service.graph_home_path)
    reading = read_dream_settings(settings_path)
    settings = reading.settings
    typer.echo(f"dream: {'on' if settings.enabled else 'off'}")
    typer.echo(f"model: {settings.model}")
    typer.echo(
        f"limits: pending_cap={settings.pending_cap} proposals_per_run={settings.proposals_per_run} "
        f"interval_hours={settings.interval_hours} bundle_limit={settings.bundle_limit} "
        f"due_exchanges={settings.due_exchanges}"
    )
    typer.echo(f"settings: {_SOURCE_LABELS[reading.source]} {settings_path}")
    if reading.problem is not None:
        typer.echo(f"problem: {reading.problem}")
    _echo_schedule(catalog_service.graph_home_path, settings)
    _echo_runs(catalog_service.graph_home_path, settings)


@dream_app.command("run")
def run(
    cwd: Path | None = _CWD_OPTION,
    dry_run: bool = _DRY_RUN_OPTION,
    state: Path = _GRAPH_HOME_OPTION,
    vault_map: Path | None = _VAULT_MAP_OPTION,
) -> None:
    """Do one dream run for a project folder now. It runs the logged-in Claude Code (`claude -p`)."""
    _run(state, cwd or Path.cwd(), vault_map, lock_fd=None, trigger="manual", dry_run=dry_run)


@dream_app.command("worker", hidden=True)
def worker(
    cwd: Path = _WORKER_CWD_OPTION,
    state: Path = _GRAPH_HOME_OPTION,
    vault_map: Path | None = _VAULT_MAP_OPTION,
    lock_fd: int | None = _LOCK_FD_OPTION,
) -> None:
    """The dream run the capture hook starts. It runs only when dreaming is on and a run is due."""
    _run(state, cwd, vault_map, lock_fd=lock_fd, trigger="hook", dry_run=False)


def _run(
    state: Path, cwd: Path, vault_map: Path | None, *, lock_fd: int | None, trigger: Trigger, dry_run: bool
) -> None:
    try:
        catalog_service = _catalog_service(state)
    except VaultGraphError as exc:
        if lock_fd is not None:
            os.close(lock_fd)
        typer.echo(str(exc))
        raise typer.Exit(1) from exc
    graph_home = catalog_service.graph_home_path
    settings = read_dream_settings(dream_settings_path(graph_home)).settings
    if trigger != "manual" and not settings.enabled:
        if lock_fd is not None:
            os.close(lock_fd)
        typer.echo("dream: skipped off")
        return
    # Imported here so the other commands never load the judge and the memory write service.
    from vault_graph.interface.composition.adapters.dream_worker import open_dream_ports, run_dream_locked

    ports = open_dream_ports(graph_home, cwd, settings, vault_map_file=vault_map)
    if isinstance(ports, str):
        if lock_fd is not None:
            os.close(lock_fd)
        typer.echo(f"dream: skipped no_vault_map: {ports}")
        raise typer.Exit(1)
    result = run_dream_locked(graph_home, cwd, settings, ports, lock_fd=lock_fd, trigger=trigger, dry_run=dry_run)
    if result is None:
        typer.echo("dream: another dream run holds logs/dream-worker.lock")
        return
    _echo_run(result)
    if result.status == "failed":
        raise typer.Exit(1)


def _echo_run(result: DreamRun) -> None:
    head = f"dream: {result.status}"
    if result.reason is not None:
        head += f" {result.reason}"
    if result.dry_run:
        head += " (dry run)"
    typer.echo(head)
    if result.message:
        typer.echo(f"message: {result.message}")
    if result.project_id is not None:
        typer.echo(f"project: {result.project_id} vault: {result.vault or '-'}")
    if result.status == "skipped":
        return
    outcomes = " ".join(f"{name}={count}" for name, count in sorted(result.outcomes.items())) or "-"
    typer.echo(f"judged: {result.judged} outcomes: {outcomes}")
    if result.cost_usd is not None:
        typer.echo(f"cost_usd: {result.cost_usd:.2f}")
    for proposal in result.proposals:
        where = proposal.review_path or "not sent"
        typer.echo(f"proposal: {proposal.action} {proposal.target} <- {proposal.candidate_key} [{where}]")


def _echo_schedule(graph_home: Path, settings: DreamSettings) -> None:
    """The run time, whether the launchd job matches it, and the last scheduled run (spec 2026-11-24 D9)."""
    from vault_graph.interface.composition.adapters.dream_worker import RUN_RECORD, read_dream_runs

    typer.echo(f"run_at: {settings.run_at} (local)")
    state = _schedule_for(graph_home).state(settings.run_at)
    if state.status == "unsupported":
        typer.echo(f"schedule: {state.reason}")
    else:
        detail = str(state.plist_path) if state.plist_path is not None and not state.reason else state.reason
        typer.echo(f"schedule: {state.status}" + (f" {detail}" if detail else ""))
    if settings.enabled and state.status in ("not_installed", "stale"):
        typer.echo("run `vg dream on` to install it")
    last = "-"
    for record in read_dream_runs(graph_home):
        if record.get("record") == RUN_RECORD and record.get("trigger") == "schedule":
            last = str(record.get("at") or "-")
    typer.echo(f"last_scheduled_run: {last}")


def _echo_runs(graph_home: Path, settings: DreamSettings) -> None:
    """The last run of each project, the review state of every dream proposal, and Vaults at the pending cap."""
    from vault_graph.interface.composition.adapters.dream_worker import PROPOSAL_RECORD, RUN_RECORD, read_dream_runs
    from vault_graph.interface.composition.adapters.vault_review_queue import (
        UNPUBLISHED_FIX,
        pending_proposals,
        review_item_state,
    )

    records = read_dream_runs(graph_home)
    last: dict[str, Mapping[str, Any]] = {}
    states: dict[str, int] = {}
    vault_roots: dict[str, str] = {}
    # Accepts the Vault never published, keyed by item file so a repeated record gives one line.
    unpublished_items: dict[Path, str] = {}
    run_count = 0
    for record in records:
        vault, root = record.get("vault"), record.get("vault_root")
        if isinstance(vault, str) and isinstance(root, str):
            vault_roots[vault] = root
        if record.get("record") == RUN_RECORD:
            run_count += 1
            if isinstance(record.get("project"), str):
                last[record["project"]] = record
        elif record.get("record") == PROPOSAL_RECORD:
            review_path = record.get("review_path")
            if isinstance(root, str) and isinstance(review_path, str):
                state = review_item_state(Path(root), review_path)
                states[state] = states.get(state, 0) + 1
                if state == "unpublished":
                    unpublished_items[Path(root) / review_path] = vault if isinstance(vault, str) else "-"
    typer.echo(f"runs: {run_count}")
    for project, record in sorted(last.items()):
        reason = f" {record['reason']}" if record.get("reason") else ""
        typer.echo(
            f"last_run: {project} {record.get('at')} {record.get('status')}{reason} "
            f"judged={record.get('judged')} proposals={record.get('proposals')}"
        )
    sent_total = sum(states.values())
    accepted, rejected, pending = states.get("accepted", 0), states.get("rejected", 0), states.get("pending", 0)
    unpublished = states.get("unpublished", 0)
    typer.echo(
        f"proposals: sent={sent_total} accepted={accepted} rejected={rejected} pending={pending} "
        f"unpublished={unpublished} other={sent_total - accepted - rejected - pending - unpublished}"
    )
    # An unpublished accept is in neither side of the rate: nothing was published and nothing was rejected (I3).
    if accepted + rejected:
        typer.echo(f"acceptance_rate: {accepted / (accepted + rejected):.2f} of {accepted + rejected} resolved")
    for item_path, vault_name in unpublished_items.items():
        typer.echo(
            f"unpublished: {vault_name} {item_path} is marked accepted but nothing was published. "
            f"To fix: {UNPUBLISHED_FIX}."
        )
    # Every Vault a run looked at is checked now, so the stop shows even before any dream proposal exists.
    for vault, root in sorted(vault_roots.items()):
        waiting = pending_proposals(Path(root))
        if waiting >= settings.pending_cap:
            typer.echo(
                f"stopped: pending cap reached in {vault} ({waiting} waiting, cap {settings.pending_cap}). "
                "Accept or reject them with `vg review`."
            )


def _save(state: Path, change: Callable[[DreamSettings], DreamSettings]) -> tuple[Path, DreamSettings]:
    """Apply ``change`` to the saved settings (the defaults when the file is missing or broken) and save them."""
    try:
        catalog_service = _catalog_service(state)
        settings_path = dream_settings_path(catalog_service.graph_home_path)
        reading = read_dream_settings(settings_path)
        saved = reading.settings if reading.source == "file" else DreamSettings()
        catalog = catalog_service.load_catalog()
        catalog_service.assert_graph_home_write_target_safe(target_path=settings_path, catalog=catalog)
        settings = change(saved)
        save_dream_settings(settings_path, settings)
    except VaultGraphError as exc:
        typer.echo(str(exc))
        raise typer.Exit(1) from exc
    return settings_path, settings


def _install(graph_home: Path, run_at: str) -> None:
    """Install the daily job for ``run_at``. A failure ends the command with 1; the saved settings stay (D13)."""
    result = _schedule_for(graph_home).install(run_at)
    if result.status == "unsupported":
        typer.echo(f"schedule: {result.reason}")
        return
    if not result.ok:
        typer.echo(f"schedule: not installed: {result.reason}")
        typer.echo("hook runs still work")
        raise typer.Exit(1)
    typer.echo(f"schedule: installed at {run_at} {result.plist_path}")


def _default_schedule(graph_home: Path) -> DreamSchedule:
    from vault_graph.interface.composition.adapters.dream_schedule import LaunchdDreamSchedule
    from vault_graph.interface.composition.adapters.dream_worker import WORKER_SCRIPT

    return LaunchdDreamSchedule(graph_home, worker_script=WORKER_SCRIPT)


# Tests replace this, so no test writes a real LaunchAgent or runs `launchctl`.
_schedule_for: Callable[[Path], DreamSchedule] = _default_schedule


def _run_scheduled(graph_home: Path, *, echo: Callable[[str], None]) -> int:
    # Imported here so the other commands never load the judge and the memory write service.
    from vault_graph.interface.composition.adapters.dream_scheduled_run import run_scheduled_dreams
    from vault_graph.interface.composition.adapters.dream_worker import open_dream_ports
    from vault_graph.operation.integration.vault_map import open_vault_map, vault_map_path

    settings = read_dream_settings(dream_settings_path(graph_home)).settings
    opening = open_vault_map(vault_map_path(None))

    def open_ports(root: Path) -> Any:
        return open_dream_ports(graph_home, root, settings, judge_cwd=root)

    return run_scheduled_dreams(
        graph_home,
        vault_map=opening.vault_map,
        open_ports=open_ports,
        echo=echo,
        no_vault_map_reason=opening.warning or f"no vault-map.json at {opening.path}",
    )


def _catalog_service(state: Path) -> CatalogService:
    try:
        descriptor = GraphHomeResolver().require_initialized(state)
    except DataHomeNotInitializedError as exc:
        raise DataHomeNotInitializedError(_NOT_INITIALIZED) from exc
    return CatalogService(graph_home_path=descriptor.root_path)
