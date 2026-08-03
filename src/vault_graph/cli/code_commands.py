"""Thin Typer adapter for registered repository code projections."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any, cast

import typer

from vault_graph.app.code_index_factory import CodeIndexFactory, CodeIndexServices
from vault_graph.code_index.code_models import (
    CodeFileOutlineRequest,
    CodeFreshnessRequest,
    CodeImpactRequest,
    CodeIndexRequest,
    CodeOutputFormat,
    CodeRepositoryEntry,
    CodeSymbolRequest,
    CodeSymbolSearchRequest,
    CodeTraversalRequest,
)
from vault_graph.code_index.code_query_service import CodeQueryService
from vault_graph.errors import VaultGraphError

code_app = typer.Typer(no_args_is_help=True)
repository_app = typer.Typer(no_args_is_help=True)
code_app.add_typer(repository_app, name="repository")


@repository_app.command("add")
def repository_add(
    repository_id: str,
    path: Path = typer.Option(..., "--path"),
    language: list[str] = typer.Option([], "--language"),
    state: Path = typer.Option(Path(".vault-graph"), "--state"),
    output_format: str = typer.Option("text", "--format"),
) -> None:
    output_format = _validate_format(output_format)
    _render(_code_operation(lambda: _add_repository(state, repository_id, path, tuple(language))), output_format)


@repository_app.command("list")
def repository_list(
    state: Path = typer.Option(Path(".vault-graph"), "--state"),
    output_format: str = typer.Option("text", "--format"),
) -> None:
    output_format = _validate_format(output_format)
    _render(_services(state).repository_catalog.entries(), output_format)


@repository_app.command("remove")
def repository_remove(
    repository_id: str,
    state: Path = typer.Option(Path(".vault-graph"), "--state"),
    output_format: str = typer.Option("text", "--format"),
) -> None:
    output_format = _validate_format(output_format)
    _services(state).repository_catalog_service.remove(repository_id)
    _render({"repository_id": repository_id, "changed": True}, output_format)


@code_app.command("index")
def index(
    repository_id: str | None = typer.Option(None, "--repository-id"),
    full: bool = typer.Option(False, "--full"),
    dry_run: bool = typer.Option(False, "--dry-run"),
    state: Path = typer.Option(Path(".vault-graph"), "--state"),
    output_format: str = typer.Option("text", "--format"),
) -> None:
    output_format = _validate_format(output_format)
    report = _services(state).projection_service.apply(
        CodeIndexRequest(repository_ids=(repository_id,) if repository_id else (), full=full, dry_run=dry_run)
    )
    _render(report, output_format)
    if report.status in {"partial", "unavailable"}:
        raise typer.Exit(1)


@code_app.command("status")
def status(
    repository_id: str | None = typer.Option(None, "--repository-id"),
    verify: bool = typer.Option(False, "--verify"),
    state: Path = typer.Option(Path(".vault-graph"), "--state"),
    output_format: str = typer.Option("text", "--format"),
) -> None:
    output_format = _validate_format(output_format)
    services = _services(state)
    report = services.freshness_service.compare(
        CodeFreshnessRequest(repository_ids=(repository_id,) if repository_id else (), verify=verify)
    )
    _render(report, output_format)
    if report.state in {"partial", "unavailable", "unknown"}:
        raise typer.Exit(1)


@code_app.command("search")
def search(
    query: str,
    repository_id: str | None = typer.Option(None, "--repository-id"),
    kind: list[str] = typer.Option([], "--kind"),
    limit: int = typer.Option(20, "--limit"),
    state: Path = typer.Option(Path(".vault-graph"), "--state"),
    output_format: str = typer.Option("text", "--format"),
) -> None:
    output_format = _validate_format(output_format)
    response = _query(state, repository_id).search_symbols(
        CodeSymbolSearchRequest(
            query, (repository_id,) if repository_id else (), tuple(kind), limit=limit, output_format=output_format
        )
    )
    _render(response, output_format)


@code_app.command("symbol")
def symbol(
    symbol_or_id: str,
    repository_id: str | None = typer.Option(None, "--repository-id"),
    path: str | None = typer.Option(None, "--path"),
    source: bool = typer.Option(False, "--source"),
    state: Path = typer.Option(Path(".vault-graph"), "--state"),
    output_format: str = typer.Option("text", "--format"),
) -> None:
    output_format = _validate_format(output_format)
    response = _query(state, repository_id).get_symbol(
        CodeSymbolRequest(symbol_or_id, repository_id, path, source, output_format=output_format)
    )
    _render(response, output_format)
    if response.symbol is None:
        raise typer.Exit(1)


@code_app.command("outline")
def outline(
    path: str,
    repository_id: str | None = typer.Option(None, "--repository-id"),
    state: Path = typer.Option(Path(".vault-graph"), "--state"),
    output_format: str = typer.Option("text", "--format"),
) -> None:
    output_format = _validate_format(output_format)
    if repository_id is None:
        typer.echo("repository_id_required")
        raise typer.Exit(1)
    _render(
        _query(state, repository_id).get_file_outline(CodeFileOutlineRequest(repository_id, path, output_format)),
        output_format,
    )


def _traversal_command(
    action: str,
    symbol_or_id: str,
    repository_id: str | None,
    path: str | None,
    depth: int,
    state: Path,
    output_format: str,
) -> None:
    output_format = _validate_format(output_format)
    query_service = _query(state, repository_id)
    request = CodeTraversalRequest(symbol_or_id, repository_id, path, depth=depth, output_format=output_format)
    response = (
        query_service.get_callers(request)
        if action == "callers"
        else query_service.get_callees(request)
        if action == "callees"
        else query_service.get_impact(
            CodeImpactRequest(symbol_or_id, repository_id, path, depth=depth, output_format=output_format)
        )
    )
    _render(response, output_format)


@code_app.command("callers")
def callers(
    symbol_or_id: str,
    repository_id: str | None = typer.Option(None, "--repository-id"),
    path: str | None = typer.Option(None, "--path"),
    depth: int = typer.Option(1, "--depth"),
    state: Path = typer.Option(Path(".vault-graph"), "--state"),
    output_format: str = typer.Option("text", "--format"),
) -> None:
    _traversal_command("callers", symbol_or_id, repository_id, path, depth, state, output_format)


@code_app.command("callees")
def callees(
    symbol_or_id: str,
    repository_id: str | None = typer.Option(None, "--repository-id"),
    path: str | None = typer.Option(None, "--path"),
    depth: int = typer.Option(1, "--depth"),
    state: Path = typer.Option(Path(".vault-graph"), "--state"),
    output_format: str = typer.Option("text", "--format"),
) -> None:
    _traversal_command("callees", symbol_or_id, repository_id, path, depth, state, output_format)


@code_app.command("impact")
def impact(
    symbol_or_id: str,
    repository_id: str | None = typer.Option(None, "--repository-id"),
    path: str | None = typer.Option(None, "--path"),
    depth: int = typer.Option(3, "--depth"),
    state: Path = typer.Option(Path(".vault-graph"), "--state"),
    output_format: str = typer.Option("text", "--format"),
) -> None:
    _traversal_command("impact", symbol_or_id, repository_id, path, depth, state, output_format)


def _services(state: Path) -> CodeIndexServices:
    try:
        return CodeIndexFactory(state_path=state).open()
    except (ValueError, VaultGraphError) as exc:
        typer.echo(str(exc))
        raise typer.Exit(1) from exc


def _add_repository(
    state: Path, repository_id: str, path: Path, requested_languages: tuple[str, ...]
) -> CodeRepositoryEntry:
    languages = requested_languages or ("python", "dart")
    entry = CodeRepositoryEntry(
        repository_id=repository_id,
        root_path=path,
        display_name=repository_id,
        enabled=True,
        include_globs=tuple(f"**/*.{'py' if item == 'python' else 'dart'}" for item in languages),
        exclude_globs=(),
        languages=languages,
        state_namespace=f"code/{repository_id}",
        git_revision_policy="head-and-working-tree",
        watch=False,
    )
    return _services(state).repository_catalog_service.add(entry).resolve(repository_id)


def _code_operation[T](operation: Callable[[], T]) -> T:
    try:
        return operation()
    except (ValueError, VaultGraphError) as exc:
        typer.echo(str(exc))
        raise typer.Exit(1) from exc


def _query(state: Path, repository_id: str | None) -> CodeQueryService:
    try:
        return CodeIndexFactory(state_path=state).open_query_service(repository_id)
    except (ValueError, VaultGraphError) as exc:
        typer.echo(str(exc))
        raise typer.Exit(1) from exc


def _validate_format(output_format: str) -> CodeOutputFormat:
    if output_format not in {"text", "json"}:
        typer.echo("unsupported_format")
        raise typer.Exit(1)
    return cast(CodeOutputFormat, output_format)


def _render(value: object, output_format: str) -> None:
    payload = _json_value(value)
    if output_format == "json":
        typer.echo(json.dumps(payload, sort_keys=True, indent=2))
        return
    if isinstance(payload, dict):
        for key, item in payload.items():
            typer.echo(f"{key}: {item}")
    else:
        for item in payload:
            typer.echo(str(item))


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


__all__ = ["code_app"]
