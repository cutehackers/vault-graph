from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import typer

from vault_graph.app.catalog_service import CatalogService
from vault_graph.app.index_service import IndexService
from vault_graph.embeddings.fastembed_text_embeddings import FastEmbedTextEmbeddings, FastEmbedTextEmbeddingsConfig
from vault_graph.errors import CatalogError, ReadOnlyBoundaryError
from vault_graph.ingestion.vault_catalog import VaultCatalog, VaultCatalogEntry
from vault_graph.storage.local.chroma_vector_store import ChromaVectorStore
from vault_graph.storage.local.sqlite_metadata_store import SQLiteMetadataStore
from vault_graph.storage.local.vector_status_store import LocalVectorStatusStore

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
        config.assert_write_target_safe(target_path=config.vector_path, catalog=catalog)
        config.assert_write_target_safe(target_path=config.vector_status_path, catalog=catalog)
        config.assert_cache_target_safe(target_path=config.embedding_cache_path, catalog=catalog)
    metadata_store = SQLiteMetadataStore(config.metadata_path, initialize=initialize_store)
    text_embeddings = _text_embeddings(config)
    return config, catalog, IndexService(
        catalog=catalog,
        metadata_store=metadata_store,
        vector_store=ChromaVectorStore(config.vector_path, initialize=initialize_store, read_only=not initialize_store),
        text_embeddings=text_embeddings,
        vector_status_store=LocalVectorStatusStore(config.vector_status_path),
        embedding_batch_size=text_embeddings.config.embedding_batch_size,
        embedding_parallelism=text_embeddings.config.embedding_parallelism,
        embedding_lazy_load=text_embeddings.config.embedding_lazy_load,
    )


def _text_embeddings(config: CatalogService) -> FastEmbedTextEmbeddings:
    return FastEmbedTextEmbeddings(config=FastEmbedTextEmbeddingsConfig(cache_dir=config.embedding_cache_path))


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
    elif vault_id is not None:
        selected_vault_id = vault_id
        scope = _exit_on_domain_error(lambda: catalog.scope_for_vault_ids([selected_vault_id]))
    else:
        scope = _exit_on_domain_error(catalog.default_scope)
    config, catalog, service = _exit_on_domain_error(lambda: _service(state, initialize_store=not dry_run))
    report = service.run_plan(scope=scope, full=full) if dry_run else service.run_apply(scope=scope, full=full)
    metadata = report.metadata
    typer.echo(f"mode: {metadata.mode}")
    typer.echo(f"vault_ids: {', '.join(metadata.vault_ids)}")
    typer.echo(f"index_revision: {metadata.index_revision}")
    typer.echo(f"changed: {len(metadata.changed_paths)}")
    typer.echo(f"unchanged: {len(metadata.unchanged_paths)}")
    typer.echo(f"deleted: {len(metadata.deleted_paths)}")
    if report.vector is not None:
        vector = report.vector
        typer.echo(f"vector_mode: {vector.mode}")
        typer.echo(f"vector_revision: {vector.vector_index_revision}")
        typer.echo(f"vector_upserts: {vector.upsert_count}")
        typer.echo(f"vector_tombstones: {vector.tombstone_count}")
        typer.echo(f"vector_unchanged: {vector.unchanged_count}")
        typer.echo(f"vector_stale: {vector.upsert_count + vector.tombstone_count}")
        typer.echo(f"embedding_model: {vector.embedding_spec.model_name}")
        typer.echo(f"embedding_model_version: {vector.embedding_spec.model_version}")
        typer.echo(f"embedding_dimensions: {vector.embedding_spec.dimensions}")
        typer.echo(f"embedding_spec_version: {vector.embedding_spec.spec_version}")
        typer.echo(f"embedding_batch_size: {vector.embedding_batch_size}")
        typer.echo(f"embedding_parallelism: {vector.embedding_parallelism}")
        typer.echo(f"embedding_lazy_load: {vector.embedding_lazy_load}")
        if getattr(vector, "failed", False):
            typer.echo("vector_failed: True")
            typer.echo(f"vector_last_error: {getattr(vector, 'error', None)}")
            raise typer.Exit(report.exit_code)


@app.command()
def status(
    state: Path = typer.Option(Path(".vault-graph"), "--state", help="Vault Graph state path."),
    vault_id: str | None = typer.Option(None, "--vault-id", help="Report one registered Vault ID."),
    all_vaults: bool = typer.Option(False, "--all-vaults", help="Report all enabled registered Vaults."),
) -> None:
    if all_vaults and vault_id:
        typer.echo("Use either --vault-id or --all-vaults, not both.")
        raise typer.Exit(1)
    config, _, service = _exit_on_domain_error(lambda: _service(state, initialize_store=False))
    _, catalog = _exit_on_domain_error(lambda: _catalog(state))
    if all_vaults:
        scope = _exit_on_domain_error(catalog.scope_for_all_enabled)
    elif vault_id is not None:
        selected_vault_id = vault_id
        scope = _exit_on_domain_error(lambda: catalog.scope_for_vault_ids([selected_vault_id]))
    else:
        scope = _exit_on_domain_error(catalog.default_scope)
    report = service.status(scope=scope)
    typer.echo(f"state: {config.state_path}")
    typer.echo(f"active_vault_id: {report.active_vault_id}")
    for report_vault_id, root_path in report.vaults:
        typer.echo(f"{report_vault_id} {root_path}")
    typer.echo(f"metadata_ok: {report.metadata_ok}")
    typer.echo(f"metadata_schema_compatible: {report.metadata_schema_compatible}")
    typer.echo(f"metadata: {report.metadata_message}")
    typer.echo(f"vector_ok: {report.vector_ok}")
    typer.echo(f"vector_backend: {report.vector_backend}")
    typer.echo(f"vector_schema_compatible: {report.vector_schema_compatible}")
    typer.echo(f"vector_message: {report.vector_message}")
    typer.echo(f"embedding_model: {report.embedding_model}")
    typer.echo(f"embedding_model_version: {report.embedding_model_version}")
    typer.echo(f"embedding_dimensions: {report.embedding_dimensions}")
    typer.echo(f"embedding_spec_version: {report.embedding_spec_version}")
    typer.echo(f"embedding_batch_size: {report.embedding_batch_size}")
    typer.echo(f"embedding_parallelism: {report.embedding_parallelism}")
    typer.echo(f"embedding_lazy_load: {report.embedding_lazy_load}")
    typer.echo(f"vector_revision: {report.vector_revision}")
    typer.echo(f"vector_stale_count: {report.vector_stale_count}")
    typer.echo(f"vector_last_error: {report.vector_last_error}")
    typer.echo(f"vector_status_scope: {report.vector_status_scope}")


def _exit_on_domain_error[T](operation: Callable[[], T]) -> T:
    try:
        return operation()
    except (CatalogError, ReadOnlyBoundaryError) as exc:
        typer.echo(str(exc))
        raise typer.Exit(1) from exc
