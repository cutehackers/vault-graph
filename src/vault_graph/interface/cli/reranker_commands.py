"""Thin Typer adapter for turning reranking on and off (`vg reranker use` and `vg reranker off`).

`vg reranker use` is the only command that downloads a rerank model (spec 2026-11-13 D10).
"""

from __future__ import annotations

import os
from pathlib import Path

import typer

from vault_graph.errors import DataHomeNotInitializedError, VaultGraphError
from vault_graph.interface.composition.adapters.rerank_presets import (
    RERANK_PRESETS,
    download_rerank_model,
    rerank_model_downloaded,
)
from vault_graph.operation.scope.catalog_service import CatalogService
from vault_graph.operation.scope.embedding_selection import load_embedding_selection
from vault_graph.operation.scope.graph_home import GraphHomeResolver
from vault_graph.operation.scope.reranker_selection import (
    RerankerSelection,
    load_reranker_selection,
    reranker_config_path,
    save_reranker_selection,
)

reranker_app = typer.Typer(no_args_is_help=True)

# Module-level option values keep ruff B008 satisfied without a per-file ignore.
_GRAPH_HOME_OPTION = typer.Option(Path.home() / ".vault-graph", "--graph-home", help="Vault Graph Data Home path.")
_NAME_ARGUMENT = typer.Argument(..., help=f"Rerank model name: {', '.join(RERANK_PRESETS)}.")

_NOT_INITIALIZED = "graph_home_not_initialized: run `vg init --vault PATH --graph-home PATH` first"


@reranker_app.command("use")
def use_model(
    name: str = _NAME_ARGUMENT,
    state: Path = _GRAPH_HOME_OPTION,
) -> None:
    """Download the model into the embedding model folder if missing, then turn reranking on."""
    preset = RERANK_PRESETS.get(name)
    if preset is None:
        typer.echo(f"unknown reranker model {name!r}; available: {', '.join(RERANK_PRESETS)}")
        raise typer.Exit(1)
    try:
        catalog_service = _catalog_service(state)
        catalog = catalog_service.load_catalog()
        settings_path = reranker_config_path(catalog_service.graph_home_path)
        models_dir = _absolute(load_embedding_selection(catalog_service.embedding_config_path).models_dir)
        catalog_service.assert_cache_target_safe(target_path=models_dir, catalog=catalog)
        catalog_service.assert_graph_home_write_target_safe(target_path=settings_path, catalog=catalog)
        downloaded = rerank_model_downloaded(preset, models_dir)
        if not downloaded:
            download_rerank_model(preset, models_dir)
        save_reranker_selection(settings_path, RerankerSelection(enabled=True, model=preset.name))
    except VaultGraphError as exc:
        typer.echo(str(exc))
        raise typer.Exit(1) from exc
    typer.echo(f"reranker: on {preset.name}")
    typer.echo(f"models_dir: {models_dir}")
    typer.echo(f"download: {'already present' if downloaded else 'done'}")
    typer.echo(f"reranker_settings: {settings_path}")


@reranker_app.command("off")
def turn_off(state: Path = _GRAPH_HOME_OPTION) -> None:
    """Turn reranking off. Keeps the chosen model and its files."""
    try:
        catalog_service = _catalog_service(state)
        catalog = catalog_service.load_catalog()
        settings_path = reranker_config_path(catalog_service.graph_home_path)
        selection = load_reranker_selection(settings_path)
        if selection.enabled:
            catalog_service.assert_graph_home_write_target_safe(target_path=settings_path, catalog=catalog)
            save_reranker_selection(settings_path, RerankerSelection(enabled=False, model=selection.model))
    except VaultGraphError as exc:
        typer.echo(str(exc))
        raise typer.Exit(1) from exc
    typer.echo("reranker: off")
    typer.echo(f"reranker_settings: {settings_path}")


def _catalog_service(state: Path) -> CatalogService:
    try:
        descriptor = GraphHomeResolver().require_initialized(state)
    except DataHomeNotInitializedError as exc:
        raise DataHomeNotInitializedError(_NOT_INITIALIZED) from exc
    return CatalogService(graph_home_path=descriptor.root_path)


def _absolute(path: Path) -> Path:
    """Expand `~` and make the path absolute without following symlinks."""
    return Path(os.path.abspath(path.expanduser()))
