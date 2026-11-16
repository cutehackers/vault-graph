"""Thin Typer adapter for session fact extraction: `vg facts on|off|status|worker`.

Spec 2026-11-16 D16, D18, D19, F13. Extraction is on with `claude` when `configs/facts.json` does not exist. `off`
writes `enabled: false`. `status` shows the settings in use, the reason a broken file was rejected, and the
job queue and failure log of the fact worker when they exist. `worker` drains the job queue once
(`interface/composition/adapters/fact_worker.py`); the capture hook starts it detached.
"""

from __future__ import annotations

import json
import os
from dataclasses import replace
from pathlib import Path

import typer

from vault_graph.errors import DataHomeNotInitializedError, VaultGraphError
from vault_graph.operation.scope.catalog_service import CatalogService
from vault_graph.operation.scope.facts_settings import (
    FACT_EXTRACTORS,
    FactsSettings,
    default_facts_settings,
    facts_failures_path,
    facts_queue_dir,
    facts_settings_path,
    read_facts_settings,
    save_facts_settings,
)
from vault_graph.operation.scope.graph_home import GraphHomeResolver

facts_app = typer.Typer(no_args_is_help=True)

# Module-level option values keep ruff B008 satisfied without a per-file ignore.
_GRAPH_HOME_OPTION = typer.Option(Path.home() / ".vault-graph", "--graph-home", help="Vault Graph Data Home path.")
_EXTRACTOR_OPTION = typer.Option(
    None,
    "--extractor",
    help=f"Fact extractor: {', '.join(FACT_EXTRACTORS)}. Default: keep the saved one, else claude.",
)
_CACHE_DIR_OPTION = typer.Option(
    None, "--cache-dir", help="Fact cache folder. Default: <graph-home>/facts/cache. LongMemEval shares one."
)
_LOCK_FD_OPTION = typer.Option(
    None, "--lock-fd", hidden=True, help="Descriptor of logs/facts-worker.lock, already locked by the starter."
)

_NOT_INITIALIZED = "graph_home_not_initialized: run `vg init --vault PATH --graph-home PATH` first"
_SOURCE_LABELS = {"default": "default (no file)", "file": "file", "broken": "broken"}


@facts_app.command("on")
def turn_on(extractor: str | None = _EXTRACTOR_OPTION, state: Path = _GRAPH_HOME_OPTION) -> None:
    """Turn session fact extraction on, optionally choosing the extractor."""
    if extractor is not None and extractor not in FACT_EXTRACTORS:
        typer.echo(f"unknown fact extractor {extractor!r}; available: {', '.join(FACT_EXTRACTORS)}")
        raise typer.Exit(1)
    try:
        catalog_service = _catalog_service(state)
        settings_path = facts_settings_path(catalog_service.graph_home_path)
        reading = read_facts_settings(settings_path)
        if reading.source == "file" and extractor in (None, reading.settings.extractor):
            settings = replace(reading.settings, enabled=True)
        else:
            settings = default_facts_settings(extractor or "claude")
        _save(catalog_service, settings_path, settings)
    except VaultGraphError as exc:
        typer.echo(str(exc))
        raise typer.Exit(1) from exc
    typer.echo(f"facts: on {settings.extractor}")
    typer.echo(f"facts_settings: {settings_path}")


@facts_app.command("off")
def turn_off(state: Path = _GRAPH_HOME_OPTION) -> None:
    """Turn session fact extraction off. Keeps the chosen extractor; a broken file is replaced."""
    try:
        catalog_service = _catalog_service(state)
        settings_path = facts_settings_path(catalog_service.graph_home_path)
        reading = read_facts_settings(settings_path)
        saved = reading.settings if reading.source == "file" else default_facts_settings("claude")
        settings = replace(saved, enabled=False)
        _save(catalog_service, settings_path, settings)
    except VaultGraphError as exc:
        typer.echo(str(exc))
        raise typer.Exit(1) from exc
    typer.echo("facts: off")
    typer.echo(f"facts_settings: {settings_path}")


@facts_app.command("status")
def status(state: Path = _GRAPH_HOME_OPTION) -> None:
    """Show whether fact extraction is on, the extractor, the job queue and recorded failures."""
    try:
        catalog_service = _catalog_service(state)
    except VaultGraphError as exc:
        typer.echo(str(exc))
        raise typer.Exit(1) from exc
    graph_home = catalog_service.graph_home_path
    settings_path = facts_settings_path(graph_home)
    reading = read_facts_settings(settings_path)
    settings = reading.settings
    typer.echo(f"facts: {'on' if settings.enabled else 'off'}")
    typer.echo(f"extractor: {settings.extractor}")
    typer.echo(f"model: {settings.model}")
    if settings.endpoint is not None:
        typer.echo(f"endpoint: {settings.endpoint}")
    typer.echo(f"settings: {_SOURCE_LABELS[reading.source]} {settings_path}")
    if reading.problem is not None:
        typer.echo(f"problem: {reading.problem}")
    typer.echo(f"queue: {_count_queue(facts_queue_dir(graph_home))} {facts_queue_dir(graph_home)}")
    typer.echo(f"failures: {_count_failures(facts_failures_path(graph_home))} {facts_failures_path(graph_home)}")


@facts_app.command("worker")
def worker(
    state: Path = _GRAPH_HOME_OPTION, cache_dir: Path | None = _CACHE_DIR_OPTION, lock_fd: int | None = _LOCK_FD_OPTION
) -> None:
    """Process the fact job queue until it is empty. Only one worker runs at a time."""
    try:
        catalog_service = _catalog_service(state)
    except VaultGraphError as exc:
        if lock_fd is not None:
            os.close(lock_fd)
        typer.echo(str(exc))
        raise typer.Exit(1) from exc
    graph_home = catalog_service.graph_home_path
    reading = read_facts_settings(facts_settings_path(graph_home))
    if not reading.settings.enabled:
        if lock_fd is not None:
            os.close(lock_fd)
        typer.echo("facts worker: fact extraction is off; the queue is kept")
        return
    # Imported here so `vg search` and the other commands never load the extractor port (spec 2026-11-16 I2).
    from vault_graph.interface.composition.adapters.fact_worker import run_fact_worker

    run = run_fact_worker(graph_home, reading.settings, cache_dir=cache_dir, lock_fd=lock_fd)
    if run is None:
        typer.echo("facts worker: another worker holds logs/facts-worker.lock")
        return
    for result in run.results:
        detail = f" {result.reason}: {result.message}" if result.reason else ""
        typer.echo(f"facts worker: {result.job} {result.status}{detail}")
    for name in run.held_back:
        typer.echo(f"facts worker: {name} waiting for its retry time")


def _save(catalog_service: CatalogService, settings_path: Path, settings: FactsSettings) -> None:
    catalog = catalog_service.load_catalog()
    catalog_service.assert_graph_home_write_target_safe(target_path=settings_path, catalog=catalog)
    save_facts_settings(settings_path, settings)


def _count_queue(queue_dir: Path) -> str:
    """Number of job files. Names starting with `.` are files still being written."""
    if not queue_dir.is_dir():
        return "0"
    try:
        return str(sum(1 for entry in queue_dir.iterdir() if entry.is_file() and not entry.name.startswith(".")))
    except OSError as exc:
        return f"unreadable ({exc.strerror})"


def _count_failures(failures_path: Path) -> str:
    """Number of entries of the failure log, a JSON list (format in `fact_worker.py`)."""
    try:
        payload = json.loads(failures_path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return "0"
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return "unreadable"
    if isinstance(payload, list):
        return str(len(payload))
    return "unreadable"


def _catalog_service(state: Path) -> CatalogService:
    try:
        descriptor = GraphHomeResolver().require_initialized(state)
    except DataHomeNotInitializedError as exc:
        raise DataHomeNotInitializedError(_NOT_INITIALIZED) from exc
    return CatalogService(graph_home_path=descriptor.root_path)
