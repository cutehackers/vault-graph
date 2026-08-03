"""Thin CLI adapter for explicit coding-harness instruction guidance."""

from __future__ import annotations

from pathlib import Path

import typer

from vault_graph.app.catalog_service import CatalogService
from vault_graph.app.setup_service import SetupService
from vault_graph.errors import VaultGraphError
from vault_graph.harness.harness_guidance import HarnessGuidanceRequest

harness_app = typer.Typer(no_args_is_help=True)
guidance_app = typer.Typer(no_args_is_help=True)
harness_app.add_typer(guidance_app, name="guidance")


@guidance_app.command("install")
def install(
    target: Path = typer.Option(..., "--target"),
    file_name: str = typer.Option(..., "--file-name"),
    backup: Path | None = typer.Option(None, "--backup"),
    preview: bool = typer.Option(False, "--preview"),
    state: Path = typer.Option(Path(".vault-graph"), "--state"),
) -> None:
    _run("install", target, file_name, backup, preview, state)


@guidance_app.command("remove")
def remove(
    target: Path = typer.Option(..., "--target"),
    file_name: str = typer.Option(..., "--file-name"),
    preview: bool = typer.Option(False, "--preview"),
    state: Path = typer.Option(Path(".vault-graph"), "--state"),
) -> None:
    _run("remove", target, file_name, None, preview, state)


@guidance_app.command("preview")
def preview(
    target: Path = typer.Option(..., "--target"),
    file_name: str = typer.Option(..., "--file-name"),
    state: Path = typer.Option(Path(".vault-graph"), "--state"),
) -> None:
    _run("preview", target, file_name, None, True, state)


def _run(
    action: str,
    target: Path,
    file_name: str,
    backup: Path | None,
    preview: bool,
    state: Path,
) -> None:
    try:
        report = SetupService().manage_harness_guidance(
            action=action,
            request=HarnessGuidanceRequest(
                target=target,
                file_name=file_name,  # type: ignore[arg-type]
                backup_path=backup,
                preview=preview,
            ),
            vault_roots=_vault_roots(state),
        )
    except (ValueError, VaultGraphError) as exc:
        typer.echo(str(exc))
        raise typer.Exit(1) from exc
    typer.echo(f"action: {report.action}")
    typer.echo(f"target_path: {report.target_path}")
    typer.echo(f"changed: {report.changed}")
    typer.echo(f"preview: {report.preview}")
    if report.backup_path is not None:
        typer.echo(f"backup_path: {report.backup_path}")
    if report.preview:
        typer.echo(report.content, nl=False)


def _vault_roots(state: Path) -> tuple[Path, ...]:
    catalog = CatalogService(state_path=state).load_catalog()
    return tuple(entry.root_path for entry in catalog.entries())


__all__ = ["harness_app"]
