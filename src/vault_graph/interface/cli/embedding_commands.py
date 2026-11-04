"""Thin Typer adapter for choosing the embedding model (`vg embedding list` and `vg embedding use`)."""

from __future__ import annotations

import json
import os
from pathlib import Path

import typer

from vault_graph.errors import DataHomeNotInitializedError, VaultGraphError
from vault_graph.interface.composition.adapters.text_embeddings import (
    DEFAULT_EMBEDDING_PRESET,
    EMBEDDING_PRESETS,
    EmbeddingPreset,
    download_embedding_model,
    embedding_model_downloaded,
)
from vault_graph.operation.scope.catalog_service import CatalogService
from vault_graph.operation.scope.embedding_selection import EmbeddingSelection, load_embedding_selection
from vault_graph.operation.scope.graph_home import GraphHomeResolver

embedding_app = typer.Typer(no_args_is_help=True)

# Module-level option values keep ruff B008 satisfied without a per-file ignore.
_GRAPH_HOME_OPTION = typer.Option(Path.home() / ".vault-graph", "--graph-home", help="Vault Graph Data Home path.")
_FORMAT_OPTION = typer.Option("text", "--format", help="Output format: text or json.")
_NAME_ARGUMENT = typer.Argument(..., help="Model name from `vg embedding list`.")
_MODELS_DIR_OPTION = typer.Option(
    None, "--models-dir", help="Folder for model files. Defaults to the current folder in the settings file."
)

_NOT_INITIALIZED = "graph_home_not_initialized: run `vg init --vault PATH --graph-home PATH` first"
_NEXT_STEP = (
    "next: `vg embedding use` does not re-embed anything. The next `vg index`, or the background index at the "
    "next agent session start, re-embeds every chunk with the new model. Until then, search in each Vault "
    "returns keyword results only."
)


@embedding_app.command("list")
def list_models(
    state: Path = _GRAPH_HOME_OPTION,
    output_format: str = _FORMAT_OPTION,
) -> None:
    """Show the recommended model, the alternatives, and which one is selected. Never downloads."""
    if output_format not in {"text", "json"}:
        typer.echo("unsupported_format")
        raise typer.Exit(1)
    try:
        catalog_service = _catalog_service(state)
        selection = load_embedding_selection(catalog_service.embedding_config_path)
    except VaultGraphError as exc:
        typer.echo(str(exc))
        raise typer.Exit(1) from exc
    models_dir = _absolute(selection.models_dir)
    selected = selection.model or DEFAULT_EMBEDDING_PRESET
    models = [
        {
            "name": preset.name,
            "role": "recommended" if preset.name == DEFAULT_EMBEDDING_PRESET else "alternative",
            "selected": preset.name == selected,
            "downloaded": embedding_model_downloaded(preset, models_dir),
            "dimensions": preset.dimensions,
            "max_tokens": preset.max_tokens,
            "download_mb": preset.download_mb,
            "model_name": preset.model_name,
            "summary": preset.summary,
        }
        for preset in _presets_recommended_first()
    ]
    if output_format == "json":
        payload = {
            "settings_path": str(catalog_service.embedding_config_path),
            "models_dir": str(models_dir),
            "models": models,
        }
        typer.echo(json.dumps(payload, ensure_ascii=False, indent=2))
        return
    typer.echo(f"embedding_settings: {catalog_service.embedding_config_path}")
    typer.echo(f"models_dir: {models_dir}")
    for model in models:
        typer.echo(
            f"model: {model['name']} {model['role']} selected={_yes_no(model['selected'])} "
            f"downloaded={_yes_no(model['downloaded'])} dimensions={model['dimensions']} "
            f"max_tokens={model['max_tokens']} download_mb={model['download_mb']} summary={model['summary']}"
        )


@embedding_app.command("use")
def use_model(
    name: str = _NAME_ARGUMENT,
    models_dir: Path | None = _MODELS_DIR_OPTION,
    state: Path = _GRAPH_HOME_OPTION,
) -> None:
    """Download the model if the folder does not have it, then save it as the selected model."""
    preset = EMBEDDING_PRESETS.get(name)
    if preset is None:
        typer.echo(f"unknown embedding model {name!r}; available: {', '.join(_preset_names())}")
        raise typer.Exit(1)
    try:
        catalog_service = _catalog_service(state)
        if models_dir is None:
            models_dir = load_embedding_selection(catalog_service.embedding_config_path).models_dir
        target_dir = _absolute(models_dir)
        catalog_service.assert_cache_target_safe(target_path=target_dir, catalog=catalog_service.load_catalog())
        downloaded = embedding_model_downloaded(preset, target_dir)
        if not downloaded:
            download_embedding_model(preset, target_dir)
        catalog_service.save_embedding_selection(EmbeddingSelection(model=preset.name, models_dir=target_dir))
    except VaultGraphError as exc:
        typer.echo(str(exc))
        raise typer.Exit(1) from exc
    typer.echo(f"selected: {preset.name}")
    typer.echo(f"models_dir: {target_dir}")
    typer.echo(f"download: {'already present' if downloaded else 'done'}")
    typer.echo(f"embedding_settings: {catalog_service.embedding_config_path}")
    typer.echo(_NEXT_STEP)


def _catalog_service(state: Path) -> CatalogService:
    try:
        descriptor = GraphHomeResolver().require_initialized(state)
    except DataHomeNotInitializedError as exc:
        raise DataHomeNotInitializedError(_NOT_INITIALIZED) from exc
    return CatalogService(graph_home_path=descriptor.root_path)


def _presets_recommended_first() -> list[EmbeddingPreset]:
    return [EMBEDDING_PRESETS[name] for name in _preset_names()]


def _preset_names() -> list[str]:
    return [DEFAULT_EMBEDDING_PRESET, *(name for name in EMBEDDING_PRESETS if name != DEFAULT_EMBEDDING_PRESET)]


def _absolute(path: Path) -> Path:
    """Expand `~` and make the path absolute without following symlinks."""
    return Path(os.path.abspath(path.expanduser()))


def _yes_no(value: object) -> str:
    return "yes" if value else "no"
