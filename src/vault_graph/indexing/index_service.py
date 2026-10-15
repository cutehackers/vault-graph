from __future__ import annotations

from dataclasses import dataclass

from vault_graph.errors import UnsupportedGraphScopeWidthError
from vault_graph.indexing.extraction.entity_extractor import DeterministicEntityExtractor
from vault_graph.indexing.extraction.graph_source_store import MetadataGraphSourceStore, PreviewGraphSourceStore
from vault_graph.indexing.extraction.relationship_extractor import DeterministicRelationshipExtractor
from vault_graph.indexing.graph_indexer import GraphIndexApplyResult, GraphIndexer, GraphIndexPlanReport
from vault_graph.indexing.ingestion.document_normalizer import ChunkSnapshot
from vault_graph.indexing.metadata_indexer import MetadataIndexer
from vault_graph.indexing.revision_planner import MetadataRevisionPlan
from vault_graph.indexing.vector_indexer import VectorApplyResult, VectorIndexer, VectorRevisionPlan
from vault_graph.operation.diagnostics.index_status_reader import IndexStatusReader
from vault_graph.operation.diagnostics.index_status_reader import StatusReport as StatusReport
from vault_graph.operation.readiness.graph_readiness_service import ReadOnlyGraphReadiness
from vault_graph.operation.scope.catalog_query_scopes import actual_query_scopes
from vault_graph.operation.scope.vault_catalog import QueryScope, VaultCatalog
from vault_graph.retrieval.graph.graph_contracts import GraphExtractionSpec, current_graph_extraction_spec
from vault_graph.storage.interfaces.graph_store import GraphStore
from vault_graph.storage.interfaces.metadata_store import MetadataStore
from vault_graph.storage.interfaces.text_embeddings import TextEmbeddings
from vault_graph.storage.interfaces.vector_store import VectorStore
from vault_graph.storage.local.graph_status_store import LocalGraphStatusStore, graph_scope_status_key, graph_spec_key
from vault_graph.storage.local.vector_status_store import (
    LocalVectorStatusStore,
    embedding_spec_key,
    scope_key_for_status,
)


@dataclass(frozen=True)
class IndexRunReport:
    metadata: MetadataRevisionPlan
    vector: VectorRevisionPlan | VectorApplyResult | None
    graph: GraphIndexPlanReport | GraphIndexApplyResult | None

    @property
    def exit_code(self) -> int:
        return 1 if getattr(self.vector, "failed", False) or getattr(self.graph, "failed", False) else 0


class IndexService:
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
        graph_store: GraphStore | None = None,
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
        self._graph_store = graph_store
        self._graph_extraction_spec = graph_extraction_spec or current_graph_extraction_spec()
        self._graph_status_store = graph_status_store

    def plan(self, *, scope: QueryScope, full: bool = False) -> MetadataRevisionPlan:
        return MetadataIndexer(catalog=self._catalog, metadata_store=self._metadata_store).plan(scope=scope, full=full)

    def apply(self, *, scope: QueryScope, full: bool = False) -> MetadataRevisionPlan:
        return MetadataIndexer(catalog=self._catalog, metadata_store=self._metadata_store).apply(scope=scope, full=full)

    def run_plan(self, *, scope: QueryScope, full: bool = False) -> IndexRunReport:
        preview = MetadataIndexer(catalog=self._catalog, metadata_store=self._metadata_store).preview(
            scope=scope,
            full=full,
        )
        vector_plan = self._vector_plan(
            chunk_store=_PreviewChunkStore(preview.chunks_after_apply),
            scope=scope,
            full=full,
        )
        graph_plan = self._graph_plan(
            source_store=PreviewGraphSourceStore(
                chunks=preview.chunks_after_apply,
                documents=preview.documents_after_apply,
            ),
            scope=scope,
            full=full,
        )
        return IndexRunReport(metadata=preview.plan, vector=vector_plan, graph=graph_plan)

    def run_apply(self, *, scope: QueryScope, full: bool = False) -> IndexRunReport:
        metadata_plan = MetadataIndexer(catalog=self._catalog, metadata_store=self._metadata_store).apply(
            scope=scope,
            full=full,
        )
        vector_result = None
        if self._vector_store is None or self._text_embeddings is None:
            vector_result = None
        else:
            vector_result = self._vector_indexer(chunk_store=self._metadata_store).apply(
                scopes=actual_query_scopes(catalog=self._catalog, scope=scope),
                full=full,
            )
            self._record_vector_status(scope=scope, result=vector_result)
        graph_result = self._graph_apply(
            source_store=MetadataGraphSourceStore(self._metadata_store),
            scope=scope,
            full=full,
        )
        return IndexRunReport(metadata=metadata_plan, vector=vector_result, graph=graph_result)

    def status(self, *, scope: QueryScope | None = None) -> StatusReport:
        return IndexStatusReader(
            catalog=self._catalog,
            metadata_store=self._metadata_store,
            vector_store=self._vector_store,
            text_embeddings=self._text_embeddings,
            vector_status_store=self._vector_status_store,
            embedding_batch_size=self._embedding_batch_size,
            embedding_parallelism=self._embedding_parallelism,
            embedding_lazy_load=self._embedding_lazy_load,
            graph_readiness=self._graph_readiness,
            graph_extraction_spec=self._graph_extraction_spec,
            graph_status_store=self._graph_status_store,
        ).read(scope=scope)

    def close(self) -> None:
        close = getattr(self._vector_store, "close", None)
        if callable(close):
            close()
        close_graph = getattr(self._graph_store, "close", None)
        if callable(close_graph):
            close_graph()

    def _vector_plan(self, *, chunk_store: object, scope: QueryScope, full: bool) -> VectorRevisionPlan | None:
        if self._vector_store is None or self._text_embeddings is None:
            return None
        return self._vector_indexer(chunk_store=chunk_store).plan(
            scopes=actual_query_scopes(catalog=self._catalog, scope=scope),
            full=full,
        )

    def _vector_indexer(self, *, chunk_store: object) -> VectorIndexer:
        if self._vector_store is None or self._text_embeddings is None:
            raise RuntimeError("vector dependencies are not configured")
        return VectorIndexer(
            chunk_store=chunk_store,  # type: ignore[arg-type]
            vector_store=self._vector_store,
            text_embeddings=self._text_embeddings,
            embedding_batch_size=self._embedding_batch_size,
            embedding_parallelism=self._embedding_parallelism,
            embedding_lazy_load=self._embedding_lazy_load,
        )

    def _record_vector_status(self, *, scope: QueryScope, result: VectorApplyResult) -> None:
        if self._vector_status_store is None or self._text_embeddings is None:
            return
        scope_key = scope_key_for_status(scope)
        spec_key = embedding_spec_key(self._text_embeddings.model_spec())
        if result.failed:
            self._vector_status_store.record_failure(
                scope_key=scope_key,
                embedding_spec_key=spec_key,
                error=result.error or "",
            )
        else:
            self._vector_status_store.record_success(
                scope_key=scope_key,
                embedding_spec_key=spec_key,
                vector_index_revision=result.vector_index_revision,
            )

    def _graph_plan(
        self,
        *,
        source_store: object,
        scope: QueryScope,
        full: bool,
    ) -> GraphIndexPlanReport | GraphIndexApplyResult | None:
        if self._graph_store is None:
            return None
        try:
            actual_scopes = _graph_actual_scopes(catalog=self._catalog, requested_scope=scope)
            _validate_supported_graph_scopes(actual_scopes=actual_scopes)
        except UnsupportedGraphScopeWidthError as exc:
            return _failed_graph_result(mode="full" if full else "incremental", error=str(exc))
        health = self._graph_store.health()
        if (not health.ok or not health.schema_compatible) and "not initialized" not in health.message:
            return _failed_graph_result(mode="full" if full else "incremental", error=health.message)
        return self._graph_indexer(source_store=source_store).plan(
            requested_scope=scope,
            actual_scopes=actual_scopes,
            full=full,
        )

    def _graph_apply(
        self,
        *,
        source_store: object,
        scope: QueryScope,
        full: bool,
    ) -> GraphIndexApplyResult | None:
        if self._graph_store is None:
            return None
        try:
            actual_scopes = _graph_actual_scopes(catalog=self._catalog, requested_scope=scope)
            _validate_supported_graph_scopes(actual_scopes=actual_scopes)
        except UnsupportedGraphScopeWidthError as exc:
            result = _failed_graph_result(mode="full" if full else "incremental", error=str(exc))
            self._record_graph_status(scope=scope, result=result)
            return result
        health = self._graph_store.health()
        if not health.ok or not health.schema_compatible:
            result = _failed_graph_result(mode="full" if full else "incremental", error=health.message)
            self._record_graph_status(scope=scope, result=result)
            return result
        result = self._graph_indexer(source_store=source_store).apply(
            requested_scope=scope,
            actual_scopes=actual_scopes,
            full=full,
        )
        self._record_graph_status(scope=scope, result=result)
        return result

    def _graph_indexer(self, *, source_store: object) -> GraphIndexer:
        if self._graph_store is None:
            raise RuntimeError("graph dependencies are not configured")
        return GraphIndexer(
            source_store=source_store,  # type: ignore[arg-type]
            graph_store=self._graph_store,
            entity_extractor=DeterministicEntityExtractor(),
            relationship_extractor=DeterministicRelationshipExtractor(),
            graph_extraction_spec=self._graph_extraction_spec,
            metadata_schema_version=self._metadata_store.health().schema_version,
        )

    def _record_graph_status(self, *, scope: QueryScope, result: GraphIndexApplyResult) -> None:
        if self._graph_status_store is None:
            return
        scope_key = graph_scope_status_key(scope)
        spec_key = graph_spec_key(self._graph_extraction_spec)
        if result.failed:
            self._graph_status_store.record_failure(
                scope_key=scope_key,
                graph_spec_key=spec_key,
                error=result.error or "",
            )
            return
        if result.apply_result is None:
            return
        graph_revision = _revision_from_values(
            tuple(revision.graph_index_revision for revision in result.apply_result.graph_revision_rows),
            fallback="unknown",
        )
        self._graph_status_store.record_success(
            scope_key=scope_key,
            graph_spec_key=spec_key,
            graph_index_revision=graph_revision,
        )


class _PreviewChunkStore:
    def __init__(self, chunks: tuple[ChunkSnapshot, ...]) -> None:
        self._chunks = chunks

    def list_chunks(self, scope: QueryScope) -> tuple[ChunkSnapshot, ...]:
        return tuple(
            chunk
            for chunk in self._chunks
            if chunk.vault_id in scope.vault_ids
            and any(
                chunk.path == content_scope or chunk.path.startswith(f"{content_scope}/")
                for content_scope in scope.content_scopes
            )
        )


def _graph_actual_scopes(*, catalog: VaultCatalog, requested_scope: QueryScope) -> tuple[QueryScope, ...]:
    actual_scopes = actual_query_scopes(catalog=catalog, scope=requested_scope)
    normalized: list[QueryScope] = []
    for actual_scope in actual_scopes:
        entry = catalog.resolve(actual_scope.vault_ids[0])
        if set(actual_scope.content_scopes) != set(entry.content_scopes):
            raise UnsupportedGraphScopeWidthError(
                "unsupported_graph_scope_width: graph indexing supports only whole selected Vault scopes"
            )
        normalized.append(
            QueryScope(
                vault_ids=(entry.vault_id,),
                content_scopes=entry.content_scopes,
                include_cross_vault=requested_scope.include_cross_vault,
            )
        )
    return tuple(normalized)


def _validate_supported_graph_scopes(*, actual_scopes: tuple[QueryScope, ...]) -> None:
    for actual_scope in actual_scopes:
        if len(actual_scope.vault_ids) != 1:
            raise UnsupportedGraphScopeWidthError(
                "unsupported_graph_scope_width: graph indexing requires per-Vault actual scopes"
            )


def _failed_graph_result(*, mode: str, error: str) -> GraphIndexApplyResult:
    return GraphIndexApplyResult(
        reconcile_plan=None,
        apply_result=None,
        mode=mode,
        stale_count=0,
        warnings=(error,),
        failed=True,
        error=error,
    )


def _revision_from_values(values: tuple[str | None, ...], *, fallback: str) -> str:
    revisions = tuple(sorted({value for value in values if value}))
    return ",".join(revisions) if revisions else fallback
