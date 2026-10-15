from __future__ import annotations

from dataclasses import dataclass

from vault_graph.indexing.vector_indexer import VectorIndexer
from vault_graph.operation.readiness.graph_readiness_service import ReadOnlyGraphReadiness
from vault_graph.operation.scope.catalog_query_scopes import actual_query_scopes
from vault_graph.operation.scope.vault_catalog import QueryScope, VaultCatalog
from vault_graph.retrieval.graph.graph_contracts import GraphExtractionSpec, current_graph_extraction_spec
from vault_graph.retrieval.graph.graph_identity import graph_scope_key
from vault_graph.retrieval.graph.graph_readiness import GraphReadiness, GraphScopeReadiness
from vault_graph.storage.interfaces.metadata_store import MetadataStore
from vault_graph.storage.interfaces.text_embeddings import TextEmbeddings
from vault_graph.storage.interfaces.vector_store import VectorStore
from vault_graph.storage.local.graph_status_store import (
    GraphRunStatus,
    LocalGraphStatusStore,
    graph_scope_status_key,
    graph_spec_key,
)
from vault_graph.storage.local.vector_status_store import (
    LocalVectorStatusStore,
    embedding_spec_key,
    scope_key_for_status,
)


@dataclass(frozen=True)
class StatusReport:
    active_vault_id: str
    vaults: tuple[tuple[str, str], ...]
    metadata_ok: bool
    metadata_schema_compatible: bool
    metadata_message: str
    vector_ok: bool
    vector_backend: str
    vector_schema_compatible: bool
    vector_message: str
    embedding_model: str
    embedding_model_version: str
    embedding_dimensions: int
    embedding_spec_version: str
    embedding_batch_size: int
    embedding_parallelism: int | None
    embedding_lazy_load: bool
    vector_revision: str | None
    vector_last_success_at: str | None
    vector_last_error_at: str | None
    vector_stale_count: int
    vector_last_error: str | None
    vector_status_scope: str
    graph_readiness: GraphReadiness
    graph_status_scope: str
    graph_last_success_revision: str | None
    graph_last_success_at: str | None
    graph_last_error_at: str | None
    graph_last_error: str | None


class IndexStatusReader:
    def __init__(
        self,
        *,
        catalog: VaultCatalog,
        metadata_store: MetadataStore,
        vector_store: VectorStore | None = None,
        text_embeddings: TextEmbeddings | None = None,
        vector_status_store: LocalVectorStatusStore | None = None,
        embedding_batch_size: int = 256,
        embedding_parallelism: int | None = None,
        embedding_lazy_load: bool = True,
        graph_readiness: ReadOnlyGraphReadiness | None = None,
        graph_extraction_spec: GraphExtractionSpec | None = None,
        graph_status_store: LocalGraphStatusStore | None = None,
    ) -> None:
        self._catalog = catalog
        self._metadata_store = metadata_store
        self._vector_store = vector_store
        self._text_embeddings = text_embeddings
        self._vector_status_store = vector_status_store
        self._embedding_batch_size = embedding_batch_size
        self._embedding_parallelism = embedding_parallelism
        self._embedding_lazy_load = embedding_lazy_load
        self._graph_readiness = graph_readiness
        self._graph_extraction_spec = graph_extraction_spec or current_graph_extraction_spec()
        self._graph_status_store = graph_status_store

    def read(self, *, scope: QueryScope | None = None) -> StatusReport:
        resolved_scope = scope or self._catalog.default_scope()
        actual_scopes = actual_query_scopes(catalog=self._catalog, scope=resolved_scope)
        health = self._metadata_store.health()
        vector_health = self._vector_store.health() if self._vector_store is not None else None
        vector_status_scope = scope_key_for_status(resolved_scope)
        spec = self._text_embeddings.model_spec() if self._text_embeddings is not None else None
        run_status = (
            self._vector_status_store.read(
                scope_key=vector_status_scope,
                embedding_spec_key=embedding_spec_key(spec),
            )
            if self._vector_status_store is not None and spec is not None
            else None
        )
        graph_run_status = self._graph_status(scope=resolved_scope)
        vector_stale_count = 0
        if (
            self._vector_store is not None
            and self._text_embeddings is not None
            and vector_health is not None
            and vector_health.ok
            and vector_health.schema_compatible
        ):
            vector_plan = VectorIndexer(
                chunk_store=self._metadata_store,
                vector_store=self._vector_store,
                text_embeddings=self._text_embeddings,
                embedding_batch_size=self._embedding_batch_size,
                embedding_parallelism=self._embedding_parallelism,
                embedding_lazy_load=self._embedding_lazy_load,
            ).plan(scopes=actual_scopes, full=False)
            vector_stale_count = vector_plan.upsert_count + vector_plan.tombstone_count
        graph_readiness = (
            self._graph_readiness.check(requested_scope=resolved_scope, actual_scopes=actual_scopes)
            if self._graph_readiness is not None
            else _graph_not_configured_readiness(resolved_scope, actual_scopes)
        )
        return StatusReport(
            active_vault_id=self._catalog.active_vault_id,
            vaults=tuple((entry.vault_id, str(entry.root_path)) for entry in self._catalog.entries()),
            metadata_ok=health.ok,
            metadata_schema_compatible=health.schema_compatible,
            metadata_message=health.message,
            vector_ok=vector_health.ok if vector_health is not None else False,
            vector_backend=vector_health.backend if vector_health is not None else "none",
            vector_schema_compatible=vector_health.schema_compatible if vector_health is not None else False,
            vector_message=vector_health.message if vector_health is not None else "not configured",
            embedding_model=spec.model_name if spec is not None else "none",
            embedding_model_version=spec.model_version if spec is not None else "none",
            embedding_dimensions=spec.dimensions if spec is not None else 0,
            embedding_spec_version=spec.spec_version if spec is not None else "none",
            embedding_batch_size=_embedding_config_value(
                self._text_embeddings,
                "embedding_batch_size",
                self._embedding_batch_size,
            ),
            embedding_parallelism=_embedding_config_value(
                self._text_embeddings,
                "embedding_parallelism",
                self._embedding_parallelism,
            ),
            embedding_lazy_load=_embedding_config_value(
                self._text_embeddings,
                "embedding_lazy_load",
                self._embedding_lazy_load,
            ),
            vector_revision=run_status.last_success_revision if run_status is not None else None,
            vector_last_success_at=run_status.last_success_at if run_status is not None else None,
            vector_last_error_at=run_status.last_error_at if run_status is not None else None,
            vector_stale_count=vector_stale_count,
            vector_last_error=run_status.last_error if run_status is not None else None,
            vector_status_scope=vector_status_scope,
            graph_readiness=graph_readiness,
            graph_status_scope=graph_scope_status_key(resolved_scope),
            graph_last_success_revision=graph_run_status.last_success_revision
            if graph_run_status is not None
            else None,
            graph_last_success_at=graph_run_status.last_success_at if graph_run_status is not None else None,
            graph_last_error_at=graph_run_status.last_error_at if graph_run_status is not None else None,
            graph_last_error=graph_run_status.last_error if graph_run_status is not None else None,
        )

    def _graph_status(self, *, scope: QueryScope) -> GraphRunStatus | None:
        if self._graph_status_store is None:
            return None
        return self._graph_status_store.read(
            scope_key=graph_scope_status_key(scope),
            graph_spec_key=graph_spec_key(self._graph_extraction_spec),
        )


def _embedding_config_value[T](text_embeddings: TextEmbeddings | None, field_name: str, fallback: T) -> T:
    config = getattr(text_embeddings, "config", None)
    value = getattr(config, field_name, fallback)
    return value if isinstance(value, type(fallback)) or fallback is None else fallback


def _graph_not_configured_readiness(
    requested_scope: QueryScope,
    actual_scopes: tuple[QueryScope, ...],
) -> GraphReadiness:
    spec = current_graph_extraction_spec()
    return GraphReadiness(
        backend_name="none",
        backend_available=False,
        schema_version="none",
        schema_compatible=False,
        graph_extraction_spec_version=spec.spec_version,
        graph_extraction_spec_digest=spec.spec_digest,
        graph_extraction_spec_compatible=False,
        freshness="missing",
        stale_count=0,
        tombstone_count=0,
        last_graph_revision=None,
        affected_vault_ids=requested_scope.vault_ids,
        scope_readiness=tuple(
            GraphScopeReadiness(
                vault_id=scope.vault_ids[0],
                actual_scope=graph_scope_key(scope),
                freshness="missing",
                stale_count=0,
                tombstone_count=0,
                last_graph_revision=None,
                warnings=(),
            )
            for scope in actual_scopes
        ),
        warnings=(),
        recovery_hint="graph readiness is not configured",
    )
