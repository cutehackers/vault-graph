"""Thin CLI adapter for explicit repository-to-Vault bindings."""

from __future__ import annotations

import json
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any, cast

import typer

from vault_graph.app.catalog_service import CatalogService
from vault_graph.app.code_index_factory import CodeIndexFactory
from vault_graph.errors import VaultGraphError
from vault_graph.project_context.project_binding import ProjectBinding
from vault_graph.project_context.project_binding_catalog import ProjectBindingCatalogService

project_app = typer.Typer(no_args_is_help=True)


@project_app.command("bind")
def bind(
    repository_id: str,
    vault_id: list[str] = typer.Option(..., "--vault-id"),
    scope: list[str] = typer.Option([], "--scope"),
    state: Path = typer.Option(Path(".vault-graph"), "--state"),
    output_format: str = typer.Option("text", "--format"),
) -> None:
    """Persist an explicit, Graph-owned repository-to-Vault binding."""

    output_format = _validate_format(output_format)
    try:
        service = _binding_service(state)
        binding = ProjectBinding(repository_id=repository_id, vault_ids=tuple(vault_id), content_scopes=tuple(scope))
        result = service.bind(binding).resolve(repository_id)
    except (ValueError, VaultGraphError) as exc:
        typer.echo(str(exc))
        raise typer.Exit(1) from exc
    _render(result, output_format)


@project_app.command("bindings")
def bindings(
    state: Path = typer.Option(Path(".vault-graph"), "--state"),
    output_format: str = typer.Option("text", "--format"),
) -> None:
    """List explicit project bindings without choosing an active Vault."""

    output_format = _validate_format(output_format)
    try:
        result = _binding_service(state).load().entries()
    except (ValueError, VaultGraphError) as exc:
        typer.echo(str(exc))
        raise typer.Exit(1) from exc
    _render(result, output_format)


def _binding_service(state: Path) -> ProjectBindingCatalogService:
    catalog_service = CatalogService(state_path=state)
    return ProjectBindingCatalogService(
        catalog_service=catalog_service,
        repository_catalog=CodeIndexFactory(state_path=state).open().repository_catalog,
        vault_catalog=catalog_service.load_catalog(),
    )


def _validate_format(output_format: str) -> str:
    if output_format not in {"text", "json"}:
        typer.echo("unsupported_format")
        raise typer.Exit(1)
    return output_format


def _render(value: object, output_format: str) -> None:
    payload = _json_value(value)
    if output_format == "json":
        typer.echo(json.dumps(payload, sort_keys=True, indent=2))
    elif isinstance(payload, list):
        for item in payload:
            typer.echo(str(item))
    else:
        for key, item in cast(dict[str, object], payload).items():
            typer.echo(f"{key}: {item}")


def _json_value(value: object) -> Any:
    if isinstance(value, Path):
        return str(value)
    if is_dataclass(value):
        return _json_value(asdict(cast(Any, value)))
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, tuple | list):
        return [_json_value(item) for item in value]
    return value


__all__ = ["project_app"]
