from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import typer

from vault_graph.app.catalog_service import CatalogService
from vault_graph.app.index_service import IndexService
from vault_graph.errors import CatalogError, ReadOnlyBoundaryError
from vault_graph.ingestion.vault_catalog import VaultCatalog, VaultCatalogEntry
from vault_graph.storage.local.sqlite_metadata_store import SQLiteMetadataStore

app = typer.Typer(no_args_is_help=True)
vault_app = typer.Typer(no_args_is_help=True)
app.add_typer(vault_app, name="vault")


def _catalog(state: Path) -> tuple[CatalogService, VaultCatalog]:
    config = CatalogService(state_path=state)
    catalog = config.load_catalog()
    return config, catalog


def _service(state: Path, *, initialize_store: bool) -> tuple[CatalogService, VaultCatalog, IndexService]:
    config, catalog = _catalog(state)
    if initialize_store:
        config.assert_write_target_safe(target_path=config.metadata_path, catalog=catalog)
    metadata_store = SQLiteMetadataStore(config.metadata_path, initialize=initialize_store)
    return config, catalog, IndexService(catalog=catalog, metadata_store=metadata_store)


@app.command()
def init(
    vault: Path = typer.Option(..., "--vault", help="Vault repository root."),
    state: Path = typer.Option(Path(".vault-graph"), "--state", help="Vault Graph state path."),
    vault_id: str = typer.Option("default", "--vault-id", help="Registered Vault ID."),
) -> None:
    config = CatalogService(state_path=state)
    catalog = _exit_on_domain_error(lambda: config.create_default_catalog(vault_root=vault, vault_id=vault_id))
    typer.echo(f"initialized vault_id: {catalog.active_vault_id}")
    typer.echo(f"state: {config.state_path}")


@vault_app.command("add")
def vault_add(
    vault_id: str,
    path: Path = typer.Option(..., "--path", help="Vault repository root."),
    state: Path = typer.Option(Path(".vault-graph"), "--state", help="Vault Graph state path."),
) -> None:
    config, catalog = _exit_on_domain_error(lambda: _catalog(state))
    entries = list(catalog.entries())
    entries.append(_exit_on_domain_error(lambda: VaultCatalogEntry.from_root(vault_id=vault_id, root_path=path)))
    updated = _exit_on_domain_error(
        lambda: VaultCatalog.from_entries(entries=entries, active_vault_id=catalog.active_vault_id)
    )
    _exit_on_domain_error(lambda: config.save_catalog(updated))
    typer.echo(f"added vault_id: {vault_id}")


@vault_app.command("list")
def vault_list(state: Path = typer.Option(Path(".vault-graph"), "--state", help="Vault Graph state path.")) -> None:
    _, catalog = _exit_on_domain_error(lambda: _catalog(state))
    for entry in catalog.entries():
        active = " active" if entry.vault_id == catalog.active_vault_id else ""
        typer.echo(f"{entry.vault_id}{active} {entry.root_path}")


@app.command()
def index(
    state: Path = typer.Option(Path(".vault-graph"), "--state", help="Vault Graph state path."),
    vault_id: str | None = typer.Option(None, "--vault-id", help="Index one registered Vault ID."),
    all_vaults: bool = typer.Option(False, "--all-vaults", help="Index all enabled registered Vaults."),
    full: bool = typer.Option(False, "--full", help="Rebuild selected metadata projection."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Plan changes without mutating Vault Graph state."),
) -> None:
    if all_vaults and vault_id:
        typer.echo("Use either --vault-id or --all-vaults, not both.")
        raise typer.Exit(1)
    config, catalog = _exit_on_domain_error(lambda: _catalog(state))
    if all_vaults:
        scope = _exit_on_domain_error(catalog.scope_for_all_enabled)
    elif vault_id:
        scope = _exit_on_domain_error(lambda: catalog.scope_for_vault_ids([vault_id]))
    else:
        scope = _exit_on_domain_error(catalog.default_scope)
    if not dry_run:
        _exit_on_domain_error(
            lambda: config.assert_write_target_safe(target_path=config.metadata_path, catalog=catalog)
        )
    metadata_store = SQLiteMetadataStore(config.metadata_path, initialize=not dry_run)
    service = IndexService(catalog=catalog, metadata_store=metadata_store)
    plan = service.plan(scope=scope, full=full) if dry_run else service.apply(scope=scope, full=full)
    typer.echo(f"mode: {plan.mode}")
    typer.echo(f"vault_ids: {', '.join(plan.vault_ids)}")
    typer.echo(f"index_revision: {plan.index_revision}")
    typer.echo(f"changed: {len(plan.changed_paths)}")
    typer.echo(f"unchanged: {len(plan.unchanged_paths)}")
    typer.echo(f"deleted: {len(plan.deleted_paths)}")


@app.command()
def status(state: Path = typer.Option(Path(".vault-graph"), "--state", help="Vault Graph state path.")) -> None:
    config, _, service = _exit_on_domain_error(lambda: _service(state, initialize_store=False))
    report = service.status()
    typer.echo(f"state: {config.state_path}")
    typer.echo(f"active_vault_id: {report.active_vault_id}")
    for vault_id, root_path in report.vaults:
        typer.echo(f"{vault_id} {root_path}")
    typer.echo(f"metadata_ok: {report.metadata_ok}")
    typer.echo(f"metadata_schema_compatible: {report.metadata_schema_compatible}")
    typer.echo(f"metadata: {report.metadata_message}")


def _exit_on_domain_error[T](operation: Callable[[], T]) -> T:
    try:
        return operation()
    except (CatalogError, ReadOnlyBoundaryError) as exc:
        typer.echo(str(exc))
        raise typer.Exit(1) from exc
