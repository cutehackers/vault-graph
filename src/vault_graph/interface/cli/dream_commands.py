"""Thin Typer adapter for dreaming: `vg dream on|off|status` (spec 2026-11-19 §3, OD2).

Dreaming is off when `configs/dream.json` does not exist. `on` and `off` keep the saved model and limits and
replace a broken file with the defaults. `status` shows the settings in use and the reason a broken file was
rejected.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

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

dream_app = typer.Typer(no_args_is_help=True)

# Module-level option values keep ruff B008 satisfied without a per-file ignore.
_GRAPH_HOME_OPTION = typer.Option(Path.home() / ".vault-graph", "--graph-home", help="Vault Graph Data Home path.")

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
