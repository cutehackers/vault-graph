"""Thin Typer adapter for dreaming: `vg dream on|off|status|run|worker` (spec 2026-11-19 §3, OD2).

Dreaming is off when `configs/dream.json` does not exist. `on` and `off` keep the saved model and limits and
replace a broken file with the defaults. `status` shows the settings in use, the reason a broken file was
rejected, the last run of each project, how many dream proposals were accepted, rejected or still wait, and
whether a write Vault is at the pending cap.

`run` does one dream run for a project folder by hand. It does not look at on or off, at the time since the last
run, or at whether a run is due; the pending cap still holds. `--dry-run` judges and prints what it would
propose, and writes nothing to a Vault or to the dream records. `worker` is the run the capture hook starts
detached (`interface/composition/adapters/dream_worker.py`); it follows every rule.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import replace
from pathlib import Path
from typing import TYPE_CHECKING, Any

import typer

from vault_graph.errors import DataHomeNotInitializedError, VaultGraphError
from vault_graph.operation.scope.catalog_service import CatalogService
from vault_graph.operation.scope.dream_settings import (
    DreamSettings,
    dream_settings_path,
    read_dream_settings,
    save_dream_settings,
)
from vault_graph.operation.scope.graph_home import GraphHomeResolver

if TYPE_CHECKING:
    from vault_graph.interface.composition.adapters.dream_worker import DreamRun

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

_NOT_INITIALIZED = "graph_home_not_initialized: run `vg init --vault PATH --graph-home PATH` first"
_SOURCE_LABELS = {"default": "default (no file)", "file": "file", "broken": "broken"}


@dream_app.command("on")
def turn_on(state: Path = _GRAPH_HOME_OPTION) -> None:
    """Turn dreaming on: after a captured session, propose memories for review in the background."""
    settings_path = _set_enabled(state, True)
    typer.echo("dream: on")
    typer.echo(f"dream_settings: {settings_path}")


@dream_app.command("off")
def turn_off(state: Path = _GRAPH_HOME_OPTION) -> None:
    """Turn dreaming off. Proposals already in a Vault review queue stay there."""
    settings_path = _set_enabled(state, False)
    typer.echo("dream: off")
    typer.echo(f"dream_settings: {settings_path}")


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
    _echo_runs(catalog_service.graph_home_path, settings)


@dream_app.command("run")
def run(
    cwd: Path | None = _CWD_OPTION,
    dry_run: bool = _DRY_RUN_OPTION,
    state: Path = _GRAPH_HOME_OPTION,
    vault_map: Path | None = _VAULT_MAP_OPTION,
) -> None:
    """Do one dream run for a project folder now. It runs the logged-in Claude Code (`claude -p`)."""
    _run(state, cwd or Path.cwd(), vault_map, lock_fd=None, manual=True, dry_run=dry_run)


@dream_app.command("worker", hidden=True)
def worker(
    cwd: Path = _WORKER_CWD_OPTION,
    state: Path = _GRAPH_HOME_OPTION,
    vault_map: Path | None = _VAULT_MAP_OPTION,
    lock_fd: int | None = _LOCK_FD_OPTION,
) -> None:
    """The dream run the capture hook starts. It runs only when dreaming is on and a run is due."""
    _run(state, cwd, vault_map, lock_fd=lock_fd, manual=False, dry_run=False)


def _run(state: Path, cwd: Path, vault_map: Path | None, *, lock_fd: int | None, manual: bool, dry_run: bool) -> None:
    try:
        catalog_service = _catalog_service(state)
    except VaultGraphError as exc:
        if lock_fd is not None:
            os.close(lock_fd)
        typer.echo(str(exc))
        raise typer.Exit(1) from exc
    graph_home = catalog_service.graph_home_path
    settings = read_dream_settings(dream_settings_path(graph_home)).settings
    if not manual and not settings.enabled:
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
    result = run_dream_locked(graph_home, cwd, settings, ports, lock_fd=lock_fd, manual=manual, dry_run=dry_run)
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


def _echo_runs(graph_home: Path, settings: DreamSettings) -> None:
    """The last run of each project, the review state of every dream proposal, and Vaults at the pending cap."""
    from vault_graph.interface.composition.adapters.dream_worker import read_dream_runs
    from vault_graph.interface.composition.adapters.vault_review_queue import pending_proposals, review_item_status

    runs = read_dream_runs(graph_home)
    last: dict[str, Mapping[str, Any]] = {}
    states: dict[str, int] = {}
    vault_roots: dict[str, str] = {}
    for record in runs:
        if isinstance(record.get("project"), str):
            last[record["project"]] = record
        proposals = record.get("proposals")
        for proposal in proposals if isinstance(proposals, list) else []:
            if not isinstance(proposal, dict):
                continue
            root, review_path, vault = proposal.get("vault_root"), proposal.get("review_path"), proposal.get("vault")
            if not isinstance(root, str) or not isinstance(review_path, str):
                continue
            if isinstance(vault, str):
                vault_roots[vault] = root
            state = review_item_status(Path(root), review_path) or "missing"
            states[state] = states.get(state, 0) + 1
    typer.echo(f"runs: {len(runs)}")
    for project, record in sorted(last.items()):
        proposals = record.get("proposals")
        sent = len(proposals) if isinstance(proposals, list) else 0
        reason = f" {record['reason']}" if record.get("reason") else ""
        typer.echo(
            f"last_run: {project} {record.get('at')} {record.get('status')}{reason} "
            f"judged={record.get('judged')} proposals={sent}"
        )
    sent_total = sum(states.values())
    accepted, rejected, pending = states.get("accepted", 0), states.get("rejected", 0), states.get("pending", 0)
    typer.echo(
        f"proposals: sent={sent_total} accepted={accepted} rejected={rejected} pending={pending} "
        f"other={sent_total - accepted - rejected - pending}"
    )
    if accepted + rejected:
        typer.echo(f"acceptance_rate: {accepted / (accepted + rejected):.2f} of {accepted + rejected} resolved")
    for vault, root in sorted(vault_roots.items()):
        waiting = pending_proposals(Path(root))
        if waiting >= settings.pending_cap:
            typer.echo(
                f"stopped: pending cap reached in {vault} ({waiting} waiting, cap {settings.pending_cap}). "
                "Resolve them with the Vault's `review resolve`."
            )


def _set_enabled(state: Path, enabled: bool) -> Path:
    try:
        catalog_service = _catalog_service(state)
        settings_path = dream_settings_path(catalog_service.graph_home_path)
        reading = read_dream_settings(settings_path)
        saved = reading.settings if reading.source == "file" else DreamSettings()
        catalog = catalog_service.load_catalog()
        catalog_service.assert_graph_home_write_target_safe(target_path=settings_path, catalog=catalog)
        save_dream_settings(settings_path, replace(saved, enabled=enabled))
    except VaultGraphError as exc:
        typer.echo(str(exc))
        raise typer.Exit(1) from exc
    return settings_path


def _catalog_service(state: Path) -> CatalogService:
    try:
        descriptor = GraphHomeResolver().require_initialized(state)
    except DataHomeNotInitializedError as exc:
        raise DataHomeNotInitializedError(_NOT_INITIALIZED) from exc
    return CatalogService(graph_home_path=descriptor.root_path)
