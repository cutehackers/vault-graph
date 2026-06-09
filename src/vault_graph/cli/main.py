from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

import typer

from vault_graph.app.catalog_service import CatalogService
from vault_graph.app.index_service import IndexService
from vault_graph.app.search_readiness_service import ReadOnlySearchReadiness
from vault_graph.embeddings.fastembed_text_embeddings import FastEmbedTextEmbeddings, FastEmbedTextEmbeddingsConfig
from vault_graph.errors import (
    CatalogError,
    KeywordIndexError,
    ReadOnlyBoundaryError,
    SearchError,
    TextEmbeddingsError,
    VectorStoreError,
)
from vault_graph.ingestion.vault_catalog import QueryScope, VaultCatalog, VaultCatalogEntry
from vault_graph.retrieval import (
    RetrievalResult,
    RetrievalService,
    RetrievalSignal,
    RetrievalWarning,
    SearchResponse,
    SearchStoreRevision,
    SearchWarning,
    StoreRevision,
)
from vault_graph.storage.interfaces.metadata_store import EvidenceReference
from vault_graph.storage.local.chroma_vector_store import ChromaVectorStore
from vault_graph.storage.local.sqlite_keyword_index import SQLiteKeywordIndex
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
    return (
        config,
        catalog,
        IndexService(
            catalog=catalog,
            metadata_store=metadata_store,
            vector_store=ChromaVectorStore(
                config.vector_path, initialize=initialize_store, read_only=not initialize_store
            ),
            text_embeddings=text_embeddings,
            vector_status_store=LocalVectorStatusStore(config.vector_status_path),
            embedding_batch_size=text_embeddings.config.embedding_batch_size,
            embedding_parallelism=text_embeddings.config.embedding_parallelism,
            embedding_lazy_load=text_embeddings.config.embedding_lazy_load,
        ),
    )


def _search_service(state: Path) -> tuple[CatalogService, VaultCatalog, RetrievalService]:
    config, catalog = _catalog(state)
    metadata_store = SQLiteMetadataStore(config.metadata_path, initialize=False)
    keyword_index = SQLiteKeywordIndex(config.metadata_path)
    vector_store = ChromaVectorStore(config.vector_path, initialize=False, read_only=True)
    text_embeddings = _search_text_embeddings(config)
    return (
        config,
        catalog,
        RetrievalService(
            catalog=catalog,
            metadata_store=metadata_store,
            keyword_index=keyword_index,
            vector_store=vector_store,
            text_embeddings=text_embeddings,
            readiness=ReadOnlySearchReadiness(
                metadata_store=metadata_store,
                keyword_index=keyword_index,
                vector_store=vector_store,
                text_embeddings=text_embeddings,
            ),
        ),
    )


def _text_embeddings(config: CatalogService) -> FastEmbedTextEmbeddings:
    return FastEmbedTextEmbeddings(config=FastEmbedTextEmbeddingsConfig(cache_dir=config.embedding_cache_path))


def _search_text_embeddings(config: CatalogService) -> FastEmbedTextEmbeddings:
    return FastEmbedTextEmbeddings(
        config=FastEmbedTextEmbeddingsConfig(
            cache_dir=config.embedding_cache_path,
            local_files_only=True,
        )
    )


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
def search(
    query: str = typer.Argument(..., help="Search query text."),
    state: Path = typer.Option(Path(".vault-graph"), "--state", help="Vault Graph state path."),
    vault_id: str | None = typer.Option(None, "--vault-id", help="Search one registered Vault ID."),
    all_vaults: bool = typer.Option(False, "--all-vaults", help="Search all enabled registered Vaults."),
    limit: int = typer.Option(10, "--limit", help="Maximum number of final results."),
    output_format: str = typer.Option("text", "--format", help="Output format: text or json."),
) -> None:
    if all_vaults and vault_id:
        typer.echo("Use either --vault-id or --all-vaults, not both.")
        raise typer.Exit(1)
    if output_format not in {"text", "json"}:
        typer.echo("unsupported_format")
        raise typer.Exit(1)
    _, catalog, service = _exit_on_domain_error(lambda: _search_service(state))
    if all_vaults:
        scope = _exit_on_domain_error(catalog.scope_for_all_enabled)
    elif vault_id is not None:
        selected_vault_id = vault_id
        scope = _exit_on_domain_error(lambda: catalog.scope_for_vault_ids([selected_vault_id]))
    else:
        scope = _exit_on_domain_error(catalog.default_scope)
    response = _exit_on_domain_error(
        lambda: service.search(
            query_text=query,
            requested_scope=scope,
            limit=limit,
            output_format=output_format,  # type: ignore[arg-type]
        )
    )
    if output_format == "json":
        typer.echo(json.dumps(_search_response_json(response), sort_keys=True, indent=2))
    else:
        _render_search_response(response)


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


def _render_search_response(response: SearchResponse) -> None:
    if response.warnings:
        for warning in response.warnings:
            scope = ",".join(warning.affected_vault_ids)
            scope_key = f" {warning.scope_key}" if warning.scope_key else ""
            typer.echo(f"warning: {warning.code} [{scope}]{scope_key} {warning.message}")
    typer.echo(f"query: {response.query_text}")
    typer.echo(f"vault_ids: {','.join(response.requested_scope.vault_ids)}")
    typer.echo(f"effective_scopes: {','.join(_scope_text(scope) for scope in response.effective_scopes)}")
    typer.echo(f"results: {response.result_count}")
    for result in response.results:
        evidence = result.evidence[0]
        typer.echo(f"{result.rank}. [{result.vault_id}] {result.title}")
        typer.echo(f"   path: {evidence.path}")
        if evidence.section:
            typer.echo(f"   section: {evidence.section}")
        typer.echo(f"   summary: {result.summary}")
        signal_text = ", ".join(f"{signal.kind}:{signal.rank}" for signal in result.signals)
        typer.echo(f"   signals: {signal_text}")


def _search_response_json(response: SearchResponse) -> dict[str, object]:
    return {
        "query_text": response.query_text,
        "requested_scope": _scope_json(response.requested_scope),
        "effective_scopes": [_scope_json(scope) for scope in response.effective_scopes],
        "limit": response.limit,
        "result_count": response.result_count,
        "candidate_count": response.candidate_count,
        "dropped_candidate_count": response.dropped_candidate_count,
        "results": [_result_json(result) for result in response.results],
        "warnings": [_warning_json(warning) for warning in response.warnings],
        "degraded": response.degraded,
        "store_revisions": [_store_revision_json(revision) for revision in response.store_revisions],
        "generated_at": response.generated_at,
    }


def _scope_json(scope: QueryScope) -> dict[str, object]:
    return {
        "vault_ids": list(scope.vault_ids),
        "content_scopes": list(scope.content_scopes),
        "include_cross_vault": scope.include_cross_vault,
    }


def _scope_text(scope: QueryScope) -> str:
    return f"{','.join(scope.vault_ids)}:{','.join(scope.content_scopes)}"


def _result_json(result: RetrievalResult) -> dict[str, object]:
    return {
        "result_id": result.result_id,
        "vault_id": result.vault_id,
        "kind": result.kind,
        "title": result.title,
        "summary": result.summary,
        "rank": result.rank,
        "evidence": [_evidence_json(evidence) for evidence in result.evidence],
        "signals": [_signal_json(signal) for signal in result.signals],
        "relationship_status": result.relationship_status,
        "warnings": [_result_warning_json(warning) for warning in result.warnings],
        "store_revisions": [_store_revision_json(revision) for revision in result.store_revisions],
    }


def _evidence_json(evidence: EvidenceReference) -> dict[str, object]:
    return {
        "vault_id": evidence.vault_id,
        "document_id": evidence.document_id,
        "chunk_id": evidence.chunk_id,
        "path": evidence.path,
        "section": evidence.section,
        "anchor": evidence.anchor,
        "content_hash": evidence.content_hash,
        "raw_sha256": evidence.raw_sha256,
        "metadata_index_revision": evidence.metadata_index_revision,
        "vault_revision": evidence.vault_revision,
    }


def _signal_json(signal: RetrievalSignal) -> dict[str, object]:
    return {
        "kind": signal.kind,
        "source_id": signal.source_id,
        "rank": signal.rank,
        "score": signal.score,
        "backend": signal.backend,
        "index_revision": signal.index_revision,
        "explanation": signal.explanation,
    }


def _result_warning_json(warning: RetrievalWarning) -> dict[str, object]:
    return {
        "code": warning.code,
        "message": warning.message,
        "severity": warning.severity,
    }


def _store_revision_json(revision: StoreRevision | SearchStoreRevision) -> dict[str, object]:
    payload: dict[str, object] = {
        "kind": revision.kind,
        "revision": revision.revision,
    }
    scope_key = getattr(revision, "scope_key", None)
    vault_id = getattr(revision, "vault_id", None)
    if scope_key is not None:
        payload["scope_key"] = scope_key
    if vault_id is not None:
        payload["vault_id"] = vault_id
    return payload


def _warning_json(warning: SearchWarning) -> dict[str, object]:
    return {
        "code": warning.code,
        "message": warning.message,
        "severity": warning.severity,
        "affected_vault_ids": list(warning.affected_vault_ids),
        "scope_key": warning.scope_key,
        "document_id": warning.document_id,
        "chunk_id": warning.chunk_id,
        "source_id": warning.source_id,
    }


def _exit_on_domain_error[T](operation: Callable[[], T]) -> T:
    try:
        return operation()
    except (
        CatalogError,
        KeywordIndexError,
        ReadOnlyBoundaryError,
        SearchError,
        TextEmbeddingsError,
        VectorStoreError,
    ) as exc:
        typer.echo(str(exc))
        raise typer.Exit(1) from exc
