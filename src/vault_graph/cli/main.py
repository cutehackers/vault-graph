from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import cast

import typer

from vault_graph.app.catalog_service import CatalogService
from vault_graph.app.graph_readiness_service import ReadOnlyGraphReadiness
from vault_graph.app.graph_retrieval_service import GraphRetrievalService
from vault_graph.app.index_service import IndexService, StatusReport
from vault_graph.app.search_readiness_service import ReadOnlySearchReadiness
from vault_graph.embeddings.fastembed_text_embeddings import FastEmbedTextEmbeddings, FastEmbedTextEmbeddingsConfig
from vault_graph.errors import (
    CatalogError,
    GraphIndexingError,
    GraphStoreError,
    KeywordIndexError,
    ReadOnlyBoundaryError,
    SearchError,
    TextEmbeddingsError,
    VectorStoreError,
)
from vault_graph.graph.graph_contracts import (
    EntityRecord,
    GraphEvidenceRef,
    RelationshipRecord,
    current_graph_extraction_spec,
)
from vault_graph.graph.graph_identity import graph_scope_key
from vault_graph.ingestion.vault_catalog import QueryScope, VaultCatalog, VaultCatalogEntry
from vault_graph.projection.rustworkx_projection import RustworkxGraphProjection
from vault_graph.retrieval import (
    GraphOutputFormat,
    GraphRetrievalRevision,
    GraphRetrievalWarning,
    RelatedResponse,
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
from vault_graph.storage.local.graph_status_store import LocalGraphStatusStore
from vault_graph.storage.local.sqlite_graph_store import SQLiteGraphStore
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
        config.assert_write_target_safe(target_path=config.graph_path, catalog=catalog)
        config.assert_write_target_safe(target_path=config.graph_status_path, catalog=catalog)
        config.assert_cache_target_safe(target_path=config.embedding_cache_path, catalog=catalog)
    metadata_store = SQLiteMetadataStore(config.metadata_path, initialize=initialize_store)
    text_embeddings = _text_embeddings(config)
    graph_store = (
        SQLiteGraphStore.open_writable(config.graph_path)
        if initialize_store
        else SQLiteGraphStore.open_read_only(config.graph_path)
    )
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
            graph_store=graph_store,
            graph_extraction_spec=current_graph_extraction_spec(),
            graph_status_store=LocalGraphStatusStore(config.graph_status_path),
            graph_readiness=ReadOnlyGraphReadiness(
                metadata_store=metadata_store,
                graph_store=graph_store,
                expected_spec=current_graph_extraction_spec(),
            ),
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


def _graph_retrieval_service(state: Path) -> tuple[CatalogService, VaultCatalog, GraphRetrievalService]:
    config, catalog = _catalog(state)
    metadata_store = SQLiteMetadataStore(config.metadata_path, initialize=False)
    graph_store = SQLiteGraphStore.open_read_only(config.graph_path)
    readiness = ReadOnlyGraphReadiness(
        metadata_store=metadata_store,
        graph_store=graph_store,
        expected_spec=current_graph_extraction_spec(),
    )
    return (
        config,
        catalog,
        GraphRetrievalService(
            catalog=catalog,
            metadata_store=metadata_store,
            graph_store=graph_store,
            graph_readiness=readiness,
            projection=RustworkxGraphProjection(),
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
    if report.graph is not None:
        graph = report.graph
        plan = graph.reconcile_plan
        typer.echo(f"graph_mode: {graph.mode}")
        typer.echo(f"graph_run_id: {plan.graph_run_id if plan is not None else None}")
        typer.echo(f"graph_revision: {_graph_revision_text(graph)}")
        typer.echo(f"graph_entities_upserted: {len(plan.entity_upserts) if plan is not None else 0}")
        typer.echo(f"graph_relationships_upserted: {len(plan.relationship_upserts) if plan is not None else 0}")
        typer.echo(f"graph_evidence_refs_upserted: {len(plan.evidence_ref_upserts) if plan is not None else 0}")
        typer.echo(f"graph_tombstones: {_graph_tombstone_count(plan)}")
        typer.echo(f"graph_stale: {graph.stale_count}")
        spec = current_graph_extraction_spec()
        typer.echo(f"graph_extraction_spec_version: {spec.spec_version}")
        typer.echo(f"graph_extraction_spec_digest: {spec.spec_digest}")
        typer.echo(f"graph_failed: {getattr(graph, 'failed', False)}")
        typer.echo(f"graph_last_error: {getattr(graph, 'error', None)}")
        for warning in graph.warnings:
            typer.echo(f"graph_warning: {warning}")
    if report.exit_code:
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
def related(
    target: str = typer.Argument(..., help="Graph target entity, path, alias, or entity ID."),
    state: Path = typer.Option(Path(".vault-graph"), "--state", help="Vault Graph state path."),
    vault_id: str | None = typer.Option(None, "--vault-id", help="Search one registered Vault ID."),
    all_vaults: bool = typer.Option(False, "--all-vaults", help="Search all enabled registered Vaults."),
    include_cross_vault: bool = typer.Option(
        False,
        "--include-cross-vault",
        help="Include explicit cross-Vault graph relationships.",
    ),
    depth: int = typer.Option(1, "--depth", help="Graph traversal depth, max 2."),
    relationship_type: list[str] | None = typer.Option(
        None,
        "--relationship-type",
        help="Relationship type filter.",
    ),
    limit: int = typer.Option(10, "--limit", help="Maximum related items."),
    output_format: str = typer.Option("text", "--format", help="Output format: text or json."),
) -> None:
    if all_vaults and vault_id:
        typer.echo("Use either --vault-id or --all-vaults, not both.")
        raise typer.Exit(1)
    if include_cross_vault and not all_vaults:
        typer.echo("include_cross_vault_requires_multi_vault_graph_scope")
        raise typer.Exit(1)
    if output_format not in {"text", "json"}:
        typer.echo("unsupported_format")
        raise typer.Exit(1)
    _, catalog, service = _exit_on_domain_error(lambda: _graph_retrieval_service(state))
    if all_vaults:
        scope = _exit_on_domain_error(catalog.scope_for_all_enabled)
    elif vault_id is not None:
        selected_vault_id = vault_id
        scope = _exit_on_domain_error(lambda: catalog.scope_for_vault_ids([selected_vault_id]))
    else:
        scope = _exit_on_domain_error(catalog.default_scope)
    response = _exit_on_domain_error(
        lambda: service.related(
            target=target,
            requested_scope=scope,
            depth=depth,
            relationship_types=tuple(relationship_type or ()),
            include_cross_vault=include_cross_vault,
            limit=limit,
            output_format=cast(GraphOutputFormat, output_format),
        )
    )
    if output_format == "json":
        typer.echo(json.dumps(_related_response_json(response), sort_keys=True, indent=2))
    else:
        _render_related_response(response)


@app.command()
def status(
    state: Path = typer.Option(Path(".vault-graph"), "--state", help="Vault Graph state path."),
    vault_id: str | None = typer.Option(None, "--vault-id", help="Report one registered Vault ID."),
    all_vaults: bool = typer.Option(False, "--all-vaults", help="Report all enabled registered Vaults."),
    output_format: str = typer.Option("text", "--format", help="Output format: text or json."),
) -> None:
    if all_vaults and vault_id:
        typer.echo("Use either --vault-id or --all-vaults, not both.")
        raise typer.Exit(1)
    if output_format not in {"text", "json"}:
        typer.echo("unsupported_format")
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
    if output_format == "json":
        payload = _status_report_json(report, config=config, selected_scope=scope)
        typer.echo(json.dumps(payload, sort_keys=True, indent=2))
        return
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
    graph = report.graph_readiness
    typer.echo(f"graph_backend: {graph.backend_name}")
    typer.echo(f"graph_backend_available: {graph.backend_available}")
    typer.echo(f"graph_schema_version: {graph.schema_version}")
    typer.echo(f"graph_schema_compatible: {graph.schema_compatible}")
    typer.echo(f"graph_extraction_spec_version: {graph.graph_extraction_spec_version}")
    typer.echo(f"graph_extraction_spec_digest: {graph.graph_extraction_spec_digest}")
    typer.echo(f"graph_extraction_spec_compatible: {graph.graph_extraction_spec_compatible}")
    typer.echo(f"graph_freshness: {graph.freshness}")
    typer.echo(f"graph_stale_count: {graph.stale_count}")
    typer.echo(f"graph_tombstone_count: {graph.tombstone_count}")
    typer.echo(f"graph_last_revision: {graph.last_graph_revision}")
    typer.echo(f"graph_status_scope: {report.graph_status_scope}")
    typer.echo(f"graph_last_error: {report.graph_last_error}")
    for row in graph.scope_readiness:
        typer.echo(f"graph_scope: {row.actual_scope} {row.freshness} {row.last_graph_revision}")
    typer.echo(f"graph_recovery_hint: {graph.recovery_hint}")


def _render_search_response(response: SearchResponse) -> None:
    if response.warnings:
        for warning in response.warnings:
            scope = ",".join(warning.affected_vault_ids)
            scope_key = f" {warning.scope_key}" if warning.scope_key else ""
            typer.echo(f"warning: {warning.code} [{scope}]{scope_key} {warning.message}")
    typer.echo(f"query: {response.query_text}")
    typer.echo(f"vault_ids: {','.join(response.requested_scope.vault_ids)}")
    typer.echo(f"actual_scopes: {','.join(_scope_text(scope) for scope in response.actual_scopes)}")
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


def _render_related_response(response: RelatedResponse) -> None:
    if response.warnings:
        for warning in response.warnings:
            scope = ",".join(warning.affected_vault_ids)
            scope_key = f" {warning.scope_key}" if warning.scope_key else ""
            typer.echo(f"warning: {warning.code} [{scope}]{scope_key} {warning.message}")
    typer.echo(f"target: {response.target}")
    if response.resolved_target is not None:
        typer.echo(f"resolved: {_entity_text(response.resolved_target)}")
    for candidate in response.target_candidates:
        if response.resolved_target is not None and (
            candidate.vault_id,
            candidate.entity_id,
        ) == (
            response.resolved_target.vault_id,
            response.resolved_target.entity_id,
        ):
            continue
        typer.echo(f"candidate: {_entity_text(candidate)}")
    typer.echo(f"actual_scopes: {','.join(graph_scope_key(scope) for scope in response.actual_scopes)}")
    build_id = response.projection_build_id or "none"
    typer.echo(f"projection: {response.graph_projection_version} {build_id}")
    typer.echo(f"results: {response.result_count}")
    for item in response.items:
        typer.echo(f"{item.rank}. {_entity_text(item.entity)}")
        typer.echo(f"   score: {item.score:.4f}")
        typer.echo(f"   depth: {len(item.relationship_path)}")
        typer.echo(f"   relationship: {_relationship_path_text(item.relationship_path)}")
        for evidence in item.evidence:
            typer.echo(f"   evidence: {_evidence_ref_text(evidence)}")
        typer.echo(f"   explanation: {item.explanation}")
        typer.echo("   signals: graph")


def _related_response_json(response: RelatedResponse) -> dict[str, object]:
    return {
        "target": response.target,
        "resolved_target": _entity_json(response.resolved_target),
        "target_candidates": [_entity_json(candidate) for candidate in response.target_candidates],
        "requested_scope": _scope_json(response.requested_scope),
        "actual_scopes": [_scope_json(scope) for scope in response.actual_scopes],
        "projection_build_id": response.projection_build_id,
        "graph_projection_version": response.graph_projection_version,
        "result_count": response.result_count,
        "items": [
            {
                "rank": item.rank,
                "entity": _entity_json(item.entity),
                "relationship_path": [_relationship_json(relationship) for relationship in item.relationship_path],
                "evidence": [_evidence_json(evidence) for evidence in item.evidence],
                "score": item.score,
                "explanation": item.explanation,
            }
            for item in response.items
        ],
        "warnings": [_graph_warning_json(warning) for warning in response.warnings],
        "store_revisions": [_graph_revision_json(revision) for revision in response.store_revisions],
        "generated_at": response.generated_at,
    }


def _search_response_json(response: SearchResponse) -> dict[str, object]:
    return {
        "query_text": response.query_text,
        "requested_scope": _scope_json(response.requested_scope),
        "actual_scopes": [_scope_json(scope) for scope in response.actual_scopes],
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


def _status_report_json(
    report: StatusReport,
    *,
    config: CatalogService,
    selected_scope: QueryScope,
) -> dict[str, object]:
    graph = report.graph_readiness
    return {
        "state": str(config.state_path),
        "active_vault_id": report.active_vault_id,
        "vaults": [{"vault_id": vault_id, "root_path": root_path} for vault_id, root_path in report.vaults],
        "selected_scope": _scope_json(selected_scope),
        "metadata": {
            "ok": report.metadata_ok,
            "schema_compatible": report.metadata_schema_compatible,
            "message": report.metadata_message,
        },
        "vector": {
            "ok": report.vector_ok,
            "backend": report.vector_backend,
            "schema_compatible": report.vector_schema_compatible,
            "message": report.vector_message,
            "embedding_model": report.embedding_model,
            "embedding_model_version": report.embedding_model_version,
            "embedding_dimensions": report.embedding_dimensions,
            "embedding_spec_version": report.embedding_spec_version,
            "embedding_batch_size": report.embedding_batch_size,
            "embedding_parallelism": report.embedding_parallelism,
            "embedding_lazy_load": report.embedding_lazy_load,
            "revision": report.vector_revision,
            "stale_count": report.vector_stale_count,
            "last_error": report.vector_last_error,
            "status_scope": report.vector_status_scope,
        },
        "graph": {
            "backend_name": graph.backend_name,
            "backend_available": graph.backend_available,
            "schema_version": graph.schema_version,
            "schema_compatible": graph.schema_compatible,
            "graph_extraction_spec_version": graph.graph_extraction_spec_version,
            "graph_extraction_spec_digest": graph.graph_extraction_spec_digest,
            "graph_extraction_spec_compatible": graph.graph_extraction_spec_compatible,
            "freshness": graph.freshness,
            "stale_count": graph.stale_count,
            "tombstone_count": graph.tombstone_count,
            "last_graph_revision": graph.last_graph_revision,
            "status_scope": report.graph_status_scope,
            "last_error": report.graph_last_error,
            "affected_vault_ids": list(graph.affected_vault_ids),
            "scope_readiness": [
                {
                    "vault_id": row.vault_id,
                    "actual_scope": row.actual_scope,
                    "freshness": row.freshness,
                    "stale_count": row.stale_count,
                    "tombstone_count": row.tombstone_count,
                    "last_graph_revision": row.last_graph_revision,
                    "warnings": list(row.warnings),
                }
                for row in graph.scope_readiness
            ],
            "warnings": list(graph.warnings),
            "recovery_hint": graph.recovery_hint,
        },
    }


def _scope_text(scope: QueryScope) -> str:
    return f"{','.join(scope.vault_ids)}:{','.join(scope.content_scopes)}"


def _entity_text(entity: EntityRecord) -> str:
    return f"[{entity.vault_id}] {entity.name} ({entity.type})"


def _relationship_path_text(relationships: tuple[RelationshipRecord, ...]) -> str:
    return " -> ".join(f"{relationship.type} {relationship.status}" for relationship in relationships)


def _evidence_ref_text(evidence: EvidenceReference) -> str:
    if evidence.anchor:
        return f"{evidence.path}#{evidence.anchor}"
    if evidence.section:
        return f"{evidence.path}#{evidence.section}"
    return evidence.path


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


def _entity_json(entity: EntityRecord | None) -> dict[str, object] | None:
    if entity is None:
        return None
    return {
        "vault_id": entity.vault_id,
        "entity_id": entity.entity_id,
        "type": entity.type,
        "name": entity.name,
        "normalized_name": entity.normalized_name,
        "aliases": list(entity.aliases),
        "canonical_path": entity.canonical_path,
        "evidence_refs": [_graph_evidence_ref_json(ref) for ref in entity.evidence_refs],
        "confidence": entity.confidence,
        "extraction_method": entity.extraction_method,
        "graph_extraction_spec_version": entity.graph_extraction_spec_version,
        "graph_extraction_spec_digest": entity.graph_extraction_spec_digest,
        "status": entity.status,
        "created_at": entity.created_at,
        "updated_at": entity.updated_at,
        "graph_index_revision": entity.graph_index_revision,
    }


def _relationship_json(relationship: RelationshipRecord) -> dict[str, object]:
    return {
        "relationship_id": relationship.relationship_id,
        "type": relationship.type,
        "source_vault_id": relationship.source_vault_id,
        "source_entity_id": relationship.source_entity_id,
        "target_vault_id": relationship.target_vault_id,
        "target_entity_id": relationship.target_entity_id,
        "evidence_refs": [_graph_evidence_ref_json(ref) for ref in relationship.evidence_refs],
        "status": relationship.status,
        "confidence": relationship.confidence,
        "extraction_method": relationship.extraction_method,
        "graph_extraction_spec_version": relationship.graph_extraction_spec_version,
        "graph_extraction_spec_digest": relationship.graph_extraction_spec_digest,
        "created_at": relationship.created_at,
        "updated_at": relationship.updated_at,
        "graph_index_revision": relationship.graph_index_revision,
    }


def _graph_evidence_ref_json(ref: GraphEvidenceRef) -> dict[str, object]:
    return {
        "evidence_ref_id": ref.evidence_ref_id,
        "owner_kind": ref.owner_kind,
        "owner_vault_id": ref.owner_vault_id,
        "owner_id": ref.owner_id,
        "evidence_vault_id": ref.evidence_vault_id,
        "document_id": ref.document_id,
        "chunk_id": ref.chunk_id,
        "content_hash": ref.content_hash,
        "section": ref.section,
        "anchor": ref.anchor,
        "path": ref.path,
        "excerpt": ref.excerpt,
    }


def _graph_warning_json(warning: GraphRetrievalWarning) -> dict[str, object]:
    return {
        "code": warning.code,
        "message": warning.message,
        "severity": warning.severity,
        "affected_vault_ids": list(warning.affected_vault_ids),
        "scope_key": warning.scope_key,
        "entity_id": warning.entity_id,
        "relationship_id": warning.relationship_id,
        "evidence_ref_id": warning.evidence_ref_id,
    }


def _graph_revision_json(revision: GraphRetrievalRevision) -> dict[str, object]:
    return {
        "kind": revision.kind,
        "revision": revision.revision,
        "scope_key": revision.scope_key,
        "vault_id": revision.vault_id,
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


def _graph_revision_text(graph: object) -> str | None:
    apply_result = getattr(graph, "apply_result", None)
    if apply_result is not None:
        revisions = tuple(revision.graph_index_revision for revision in apply_result.graph_revision_rows)
        return ",".join(sorted(set(revisions))) if revisions else None
    plan = getattr(graph, "reconcile_plan", None)
    if plan is None:
        return None
    revisions = tuple(revision.graph_index_revision for revision in plan.graph_revision_rows)
    return ",".join(sorted(set(revisions))) if revisions else None


def _graph_tombstone_count(plan: object | None) -> int:
    if plan is None:
        return 0
    return len(plan.entity_tombstones) + len(plan.relationship_tombstones)  # type: ignore[attr-defined]


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
        GraphIndexingError,
        GraphStoreError,
        KeywordIndexError,
        ReadOnlyBoundaryError,
        SearchError,
        TextEmbeddingsError,
        VectorStoreError,
    ) as exc:
        typer.echo(str(exc))
        raise typer.Exit(1) from exc
