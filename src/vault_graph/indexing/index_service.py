from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from typing import Protocol

from vector_index.indexing import DEFAULT_TOKEN_BUDGET

from vault_graph.errors import UnsupportedGraphScopeWidthError
from vault_graph.indexing.extraction.entity_extractor import DeterministicEntityExtractor
from vault_graph.indexing.extraction.graph_source_store import MetadataGraphSourceStore, PreviewGraphSourceStore
from vault_graph.indexing.extraction.relationship_extractor import DeterministicRelationshipExtractor
from vault_graph.indexing.graph_indexer import (
    GraphDocumentChanges,
    GraphIndexApplyResult,
    GraphIndexer,
    GraphIndexPlanReport,
)
from vault_graph.indexing.ingestion.document_normalizer import ChunkSnapshot
from vault_graph.indexing.metadata_indexer import MetadataIndexer
from vault_graph.indexing.revision_planner import MetadataRevisionPlan
from vault_graph.indexing.vector_index_adapter import (
    VectorApplyResult,
    VectorIndexer,
    VectorRevisionPlan,
    stable_vector_id,
)
from vault_graph.operation.scope.catalog_query_scopes import actual_query_scopes
from vault_graph.operation.scope.vault_catalog import QueryScope, VaultCatalog
from vault_graph.retrieval.graph.graph_contracts import GraphExtractionSpec, current_graph_extraction_spec
from vault_graph.retrieval.graph.graph_readiness import GraphReadiness
from vault_graph.storage.interfaces.graph_status_store import GraphStatusStore, graph_scope_status_key, graph_spec_key
from vault_graph.storage.interfaces.graph_store import GraphStore
from vault_graph.storage.interfaces.metadata_store import MetadataStore
from vault_graph.storage.interfaces.text_embeddings import TextEmbeddings
from vault_graph.storage.interfaces.vector_status_store import (
    VectorStatusStore,
    embedding_spec_key,
    scope_key_for_status,
)
from vault_graph.storage.interfaces.vector_store import VectorStore, VectorTombstone


@dataclass(frozen=True)
class IndexRunReport:
    metadata: MetadataRevisionPlan
    vector: VectorRevisionPlan | VectorApplyResult | None
    graph: GraphIndexPlanReport | GraphIndexApplyResult | None

    @property
    def exit_code(self) -> int:
        return 1 if getattr(self.vector, "failed", False) or getattr(self.graph, "failed", False) else 0

    @property
    def publishable(self) -> bool:
        """True when the staged generation may be published.

        A vector plan failure wrote nothing to the staged vector store, so metadata and graph are
        published and the vectors stay as they were (spec 2026-11-05 §4.3.1). Any other failure is not.
        """
        if getattr(self.graph, "failed", False):
            return False
        if getattr(self.vector, "failed", False):
            return getattr(self.vector, "failed_stage", None) == "plan"
        return True


class IndexStatusReport(Protocol):
    """Status report fields. M15 StatusReport satisfies this; M03 cannot import it (보완3, 보완4)."""

    @property
    def active_vault_id(self) -> str: ...

    @property
    def vaults(self) -> tuple[tuple[str, str], ...]: ...

    @property
    def metadata_ok(self) -> bool: ...

    @property
    def metadata_schema_compatible(self) -> bool: ...

    @property
    def metadata_message(self) -> str: ...

    @property
    def vector_ok(self) -> bool: ...

    @property
    def vector_backend(self) -> str: ...

    @property
    def vector_schema_compatible(self) -> bool: ...

    @property
    def vector_message(self) -> str: ...

    @property
    def embedding_model(self) -> str: ...

    @property
    def embedding_model_version(self) -> str: ...

    @property
    def embedding_dimensions(self) -> int: ...

    @property
    def embedding_spec_version(self) -> str: ...

    @property
    def embedding_batch_size(self) -> int: ...

    @property
    def embedding_parallelism(self) -> int | None: ...

    @property
    def embedding_lazy_load(self) -> bool: ...

    @property
    def vector_revision(self) -> str | None: ...

    @property
    def vector_last_success_at(self) -> str | None: ...

    @property
    def vector_last_error_at(self) -> str | None: ...

    @property
    def vector_stale_count(self) -> int: ...

    @property
    def vector_last_error(self) -> str | None: ...

    @property
    def vector_status_scope(self) -> str: ...

    @property
    def graph_readiness(self) -> GraphReadiness: ...

    @property
    def graph_status_scope(self) -> str: ...

    @property
    def graph_last_success_revision(self) -> str | None: ...

    @property
    def graph_last_success_at(self) -> str | None: ...

    @property
    def graph_last_error_at(self) -> str | None: ...

    @property
    def graph_last_error(self) -> str | None: ...


class IndexStatusReading(Protocol):
    """Status read port. Composition injects the M15 IndexStatusReader (보완3)."""

    def read(self, *, scope: QueryScope | None = None) -> IndexStatusReport: ...


class IndexService:
    def __init__(
        self,
        *,
        catalog: VaultCatalog,
        metadata_store: MetadataStore,
        vector_store: VectorStore | None = None,
        text_embeddings: TextEmbeddings | None = None,
        vector_status_store: VectorStatusStore | None = None,
        embedding_batch_size: int = 256,
        embedding_parallelism: int | None = None,
        embedding_lazy_load: bool = True,
        embedding_token_budget: int = DEFAULT_TOKEN_BUDGET,
        graph_store: GraphStore | None = None,
        graph_extraction_spec: GraphExtractionSpec | None = None,
        graph_status_store: GraphStatusStore | None = None,
        status_reader: IndexStatusReading | None = None,
    ) -> None:
        self._catalog = catalog
        self._metadata_store = metadata_store
        self._vector_store = vector_store
        self._text_embeddings = text_embeddings
        self._vector_status_store = vector_status_store
        self._embedding_batch_size = embedding_batch_size
        self._embedding_parallelism = embedding_parallelism
        self._embedding_lazy_load = embedding_lazy_load
        self._embedding_token_budget = embedding_token_budget
        self._graph_store = graph_store
        self._graph_extraction_spec = graph_extraction_spec or current_graph_extraction_spec()
        self._graph_status_store = graph_status_store
        self._status_reader = status_reader

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
            changes=_graph_changes(preview.plan),
        )
        return IndexRunReport(metadata=preview.plan, vector=vector_plan, graph=graph_plan)

    def run_apply(self, *, scope: QueryScope, full: bool = False, skip_vector: bool = False) -> IndexRunReport:
        """Metadata, then vectors, then the graph.

        ``skip_vector`` runs metadata and graph only, as the background catch-up does while a Vault
        waits out its vector retry interval (spec 2026-11-05 §4.3.1). The vectors that point at
        chunks this run removed are dropped, as after a vector plan failure, so the generation
        passes the publication hygiene check.
        """
        with_vectors = self._vector_store is not None and self._text_embeddings is not None
        vector_scopes = actual_query_scopes(catalog=self._catalog, scope=scope) if with_vectors else ()
        chunks_before = self._scope_chunk_keys(vector_scopes)
        metadata_plan = MetadataIndexer(catalog=self._catalog, metadata_store=self._metadata_store).apply(
            scope=scope,
            full=full,
        )
        vector_result = None
        if with_vectors and skip_vector:
            try:
                self._drop_removed_chunk_vectors(chunks_before - self._scope_chunk_keys(vector_scopes))
            except Exception as exc:  # noqa: BLE001 - reported as a vector failure, nothing is published
                vector_result = replace(
                    self._vector_indexer(chunk_store=self._metadata_store).plan_failure(
                        scopes=vector_scopes, full=full, error=f"dropping vectors of removed chunks failed: {exc}"
                    ),
                    failed_stage="apply",
                )
        elif with_vectors:
            vector_result = self._vector_indexer(chunk_store=self._metadata_store).apply(
                scopes=vector_scopes, full=full
            )
            if vector_result.failed and vector_result.failed_stage == "plan":
                vector_result = self._after_plan_failure(
                    vector_result, removed=chunks_before - self._scope_chunk_keys(vector_scopes)
                )
            self._record_vector_status(scope=scope, result=vector_result)
        graph_result = self._graph_apply(
            source_store=MetadataGraphSourceStore(self._metadata_store),
            scope=scope,
            full=full,
            changes=_graph_changes(metadata_plan),
        )
        return IndexRunReport(metadata=metadata_plan, vector=vector_result, graph=graph_result)

    def run_apply_paths(
        self,
        *,
        scope: QueryScope,
        changed_paths: tuple[tuple[str, str], ...],
        deleted_paths: tuple[tuple[str, str], ...],
        open_vector_store: Callable[[], VectorStore | None] | None = None,
    ) -> IndexRunReport:
        """Metadata for the listed files only (``MetadataIndexer.apply_paths``), then the graph. No embeddings.

        The graph re-extracts the documents the metadata run changed or removed and those linked with
        them (spec 2026-11-05 §4.3.3). A graph that did not follow the metadata is reconciled whole.

        Vectors of chunks the listed files no longer have are dropped, so the generation passes the
        same hygiene check as a full run without an embedding model. ``open_vector_store`` is called
        only when a chunk was removed (a new file removes none), and the store it returns is closed
        here. It may return None when there is no vector store yet.
        """
        listed = changed_paths + deleted_paths
        chunks_before = self._chunk_keys(listed)
        metadata_plan = MetadataIndexer(catalog=self._catalog, metadata_store=self._metadata_store).apply_paths(
            scope=scope,
            changed_paths=changed_paths,
            deleted_paths=deleted_paths,
        )
        graph_result = self._graph_apply(
            source_store=MetadataGraphSourceStore(self._metadata_store),
            scope=scope,
            full=False,
            changes=_graph_changes(metadata_plan),
        )
        report = IndexRunReport(metadata=metadata_plan, vector=None, graph=graph_result)
        removed = chunks_before - self._chunk_keys(listed)
        if removed and report.exit_code == 0 and open_vector_store is not None:
            _drop_vectors(open_vector_store, scope, removed)
        return report

    def status(self, *, scope: QueryScope | None = None) -> IndexStatusReport:
        if self._status_reader is None:
            raise RuntimeError("index status reader is not configured")
        return self._status_reader.read(scope=scope)

    def close(self) -> None:
        close = getattr(self._vector_store, "close", None)
        if callable(close):
            close()
        close_graph = getattr(self._graph_store, "close", None)
        if callable(close_graph):
            close_graph()

    def _scope_chunk_keys(self, scopes: tuple[QueryScope, ...]) -> set[tuple[str, str]]:
        return {
            (chunk.vault_id, chunk.chunk_id) for scope in scopes for chunk in self._metadata_store.list_chunks(scope)
        }

    def _after_plan_failure(self, result: VectorApplyResult, *, removed: set[tuple[str, str]]) -> VectorApplyResult:
        """Drop vectors of removed chunks so metadata and graph can be published without new vectors.

        When that fails too, the result becomes an apply failure and nothing is published.
        """
        try:
            self._drop_removed_chunk_vectors(removed)
        except Exception as exc:  # noqa: BLE001 - reported as part of the vector failure
            return replace(
                result,
                failed_stage="apply",
                error=f"{result.error}; dropping vectors of removed chunks failed: {exc}",
            )
        return result

    def _drop_removed_chunk_vectors(self, removed: set[tuple[str, str]]) -> None:
        """Delete by computed vector id, without listing the store (listing may be what failed)."""
        if not removed or self._vector_store is None or self._text_embeddings is None:
            return
        spec = self._text_embeddings.model_spec()
        tombstones = tuple(
            VectorTombstone(
                vector_id=stable_vector_id(vault_id=vault_id, chunk_id=chunk_id, embedding_spec=spec),
                vault_id=vault_id,
                chunk_id=chunk_id,
                embedding_spec=spec,
            )
            for vault_id, chunk_id in sorted(removed)
        )
        self._vector_store.apply_vector_revision(
            vector_index_revision=f"vector-{datetime.now(UTC).strftime('%Y%m%d%H%M%S%f')}",
            records=(),
            tombstones=tombstones,
        )

    def _chunk_keys(self, paths: tuple[tuple[str, str], ...]) -> set[tuple[str, str]]:
        """(vault_id, chunk_id) of the listed files' current chunks."""
        keys: set[tuple[str, str]] = set()
        for vault_id, path in paths:
            state = self._metadata_store.document_state(vault_id, path)
            if state.document_id is None or state.is_tombstoned:
                continue
            chunks = self._metadata_store.list_document_chunks(vault_id=vault_id, document_id=state.document_id)
            keys.update((chunk.vault_id, chunk.chunk_id) for chunk in chunks)
        return keys

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
            embedding_token_budget=self._embedding_token_budget,
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
        changes: GraphDocumentChanges,
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
            changes=changes,
        )

    def _graph_apply(
        self,
        *,
        source_store: object,
        scope: QueryScope,
        full: bool,
        changes: GraphDocumentChanges,
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
            changes=changes,
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


def _graph_changes(plan: MetadataRevisionPlan) -> GraphDocumentChanges:
    """The files a metadata run wrote or removed, for the graph's document-level run."""
    return GraphDocumentChanges(
        index_revision=plan.index_revision,
        changed_paths=plan.changed_paths,
        deleted_paths=plan.deleted_paths,
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


def _drop_vectors(
    open_vector_store: Callable[[], VectorStore | None], scope: QueryScope, removed: set[tuple[str, str]]
) -> None:
    vector_store = open_vector_store()
    if vector_store is None:
        return
    try:
        tombstones = tuple(
            VectorTombstone(
                vector_id=row.vector_id,
                vault_id=row.vault_id,
                chunk_id=row.chunk_id,
                embedding_spec=row.embedding_spec,
            )
            for row in vector_store.export_manifest(scope)
            if (row.vault_id, row.chunk_id) in removed
        )
        if tombstones:
            vector_store.apply_vector_revision(
                vector_index_revision=f"vector-{datetime.now(UTC).strftime('%Y%m%d%H%M%S%f')}",
                records=(),
                tombstones=tombstones,
            )
    finally:
        close = getattr(vector_store, "close", None)
        if callable(close):
            close()
