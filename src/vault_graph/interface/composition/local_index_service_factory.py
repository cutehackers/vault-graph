from __future__ import annotations

import shutil
import sys
from collections.abc import Callable
from dataclasses import asdict, dataclass
from pathlib import Path

from vector_index.indexing import DEFAULT_TOKEN_BUDGET

from vault_graph.errors import GraphStoreError, VectorStoreError
from vault_graph.indexing.index_service import IndexRunReport, IndexService
from vault_graph.indexing.ingestion.document_chunking import CHUNKER_VERSION
from vault_graph.indexing.publication.projection_generation import (
    ProjectionBundlePublisher,
    ProjectionGenerationError,
    ProjectionGenerationManager,
    ProjectionLayout,
)
from vault_graph.indexing.vector_index_adapter import VectorApplyResult, embedding_key_for_text
from vault_graph.interface.composition.adapters.text_embeddings import (
    FastEmbedTextEmbeddings,
    text_embeddings_for,
)
from vault_graph.interface.composition.graph_store_factory import (
    GraphBackend,
    document_store_path,
    open_graph_store,
    selected_graph_backend,
    write_graph_backend_selection,
)
from vault_graph.operation.diagnostics.index_status_reader import IndexStatusReader
from vault_graph.operation.diagnostics.projection_hygiene_service import ProjectionHygieneService
from vault_graph.operation.readiness.graph_readiness_service import ReadOnlyGraphReadiness
from vault_graph.operation.scope.catalog_service import CatalogService
from vault_graph.operation.scope.embedding_selection import load_embedding_selection
from vault_graph.operation.scope.vault_catalog import QueryScope, VaultCatalog
from vault_graph.retrieval.graph.graph_contracts import current_graph_extraction_spec
from vault_graph.storage.interfaces.graph_store import GraphStore
from vault_graph.storage.interfaces.text_embeddings import EmbeddingModelSpec, TextEmbeddings
from vault_graph.storage.interfaces.vector_store import VectorStore
from vault_graph.storage.local.chroma_vector_store import CHROMA_BACKEND, COLLECTION_PREFIX, ChromaVectorStore
from vault_graph.storage.local.embedding_cache import (
    CachedTextEmbeddings,
    SQLiteEmbeddingCache,
    embedding_cache_path,
)
from vault_graph.storage.local.graph_status_store import LocalGraphStatusStore
from vault_graph.storage.local.sqlite_graph_store import SQLiteGraphStore
from vault_graph.storage.local.sqlite_metadata_store import SQLiteMetadataStore
from vault_graph.storage.local.sqlite_vector_manifest_store import (
    ChromaSQLiteListing,
    ManifestTrackedVectorStore,
    SQLiteVectorManifestStore,
    manifest_path_for_vector_path,
)
from vault_graph.storage.local.vector_status_store import LocalVectorStatusStore


@dataclass(frozen=True)
class ProjectionCommitResult:
    """What publishing removed from the new generation. Only `vg index` prints it (spec 4.7)."""

    removed_vector_collections: tuple[str, ...] = ()
    vector_cleanup_error: str | None = None


@dataclass
class LocalIndexServiceBundle:
    catalog_service: CatalogService
    catalog: VaultCatalog
    index_service: IndexService
    generation_manager: ProjectionGenerationManager | None = None
    bundle_publisher: ProjectionBundlePublisher | None = None
    staged_generation: ProjectionLayout | None = None
    projection_committed: bool = False
    # Present for writable runs. Pruned to the published generation's vectors (spec 4.3.5).
    embedding_cache: CachedTextEmbeddings | None = None

    def commit_projection(self, report: IndexRunReport | None = None) -> ProjectionCommitResult:
        result = ProjectionCommitResult()
        if self.staged_generation is None:
            return result
        if self.bundle_publisher is None:
            if self.generation_manager is None:
                return result
            self.generation_manager.activate(self.staged_generation)
        else:
            if report is None:
                raise RuntimeError("projection report is required before bundle publication")
            if (self.catalog_service.graph_path.parent / "backend.json").exists():
                metadata = SQLiteMetadataStore(self.catalog_service.metadata_path, initialize=False)
                graph_store = open_graph_store(self.catalog_service, metadata_store=metadata)
                scope = self.catalog.scope_for_vault_ids(report.metadata.vault_ids)
                actual_scopes = tuple(
                    QueryScope((vault_id,), self.catalog.resolve(vault_id).content_scopes)
                    for vault_id in scope.vault_ids
                )
                try:
                    readiness = ReadOnlyGraphReadiness(
                        metadata_store=metadata,
                        graph_store=graph_store,
                        expected_spec=current_graph_extraction_spec(),
                    ).check(requested_scope=scope, actual_scopes=actual_scopes)
                    if readiness.freshness not in ("fresh", "empty"):
                        raise ProjectionGenerationError(
                            f"graph backend publication requires current evidence: {readiness.freshness}"
                        )
                finally:
                    close = getattr(graph_store, "close", None)
                    if callable(close):
                        close()
            if isinstance(report.vector, VectorApplyResult) and not report.vector.failed:
                result = _remove_empty_vector_collections(self.catalog_service, keep=report.vector.embedding_spec)
            enabled_components = _write_projection_component_manifests(
                publisher=self.bundle_publisher,
                staged=self.staged_generation,
                report=report,
                catalog_service=self.catalog_service,
                catalog=self.catalog,
            )
            self.bundle_publisher.activate(
                self.staged_generation,
                enabled_components=enabled_components,
                run_id=f"projection-run-{self.staged_generation.generation_id}",
            )
            if isinstance(report.vector, VectorApplyResult) and not report.vector.failed:
                self._prune_embedding_cache()
        self.projection_committed = True
        return result

    def _prune_embedding_cache(self) -> None:
        """Keep only keys of vectors in the published generation. A failure here never undoes the publish."""
        cached = self.embedding_cache
        if cached is None:
            return
        try:
            if cached.cache_failed:
                # The next run builds a new cache in place of the unusable file.
                cached.cache.remove_files()
                return
            manifest = SQLiteVectorManifestStore(manifest_path_for_vector_path(self.catalog_service.vector_path))
            if not manifest.exists():
                return
            vault_ids = tuple(entry.vault_id for entry in self.catalog.entries())
            cached.cache.retain({row.embedding_key for row in manifest.rows(vault_ids) if row.embedding_key})
        except (OSError, VectorStoreError) as exc:
            print(f"vault-graph: warning: embedding cache was not pruned: {exc}", file=sys.stderr)

    def close(self) -> None:
        self.index_service.close()
        if self.staged_generation is not None and not self.projection_committed:
            if self.bundle_publisher is not None:
                try:
                    self.bundle_publisher.write_run_diagnostic(
                        run_id=f"projection-run-{self.staged_generation.generation_id}",
                        status="failed",
                        staged=self.staged_generation,
                        error="projection bundle was not published",
                    )
                except Exception:
                    pass
                self.bundle_publisher.discard(self.staged_generation)
            elif self.generation_manager is not None:
                self.generation_manager.discard(self.staged_generation)


TextEmbeddingsFactory = Callable[[CatalogService], FastEmbedTextEmbeddings]


class LocalIndexServiceFactory:
    def __init__(self, *, text_embeddings_factory: TextEmbeddingsFactory | None = None) -> None:
        self._text_embeddings_factory = text_embeddings_factory or _default_text_embeddings

    def open(
        self,
        *,
        graph_home_path: Path,
        initialize_store: bool,
        transactional: bool = False,
        full: bool = False,
        graph_backend: GraphBackend | None = None,
        requested_scope: QueryScope | None = None,
    ) -> LocalIndexServiceBundle:
        catalog_service = CatalogService(graph_home_path=graph_home_path)
        catalog = catalog_service.load_catalog()
        generation_manager = (
            ProjectionGenerationManager(catalog_service.graph_home_path) if initialize_store and transactional else None
        )
        bundle_publisher = (
            ProjectionBundlePublisher(catalog_service.graph_home_path, generation_manager)
            if generation_manager is not None
            else None
        )
        staged_generation = bundle_publisher.stage_from_active(full=full) if bundle_publisher is not None else None
        if staged_generation is not None:
            _use_projection_root(catalog_service, staged_generation.root_path)
        graph_store: GraphStore | None = None
        try:
            if initialize_store:
                self._assert_write_targets_safe(catalog_service=catalog_service, catalog=catalog)
            previous_backend, selected_backend = _select_graph_backend(
                catalog_service,
                initialize_store=initialize_store,
                transactional=transactional,
                requested_backend=graph_backend,
            )
            metadata_store = SQLiteMetadataStore(catalog_service.metadata_path, initialize=initialize_store)
            text_embeddings = self._text_embeddings_factory(catalog_service)
            # Only writable runs read and fill the cache. Read-only bundles create no files.
            embedding_cache = (
                CachedTextEmbeddings(
                    text_embeddings,
                    SQLiteEmbeddingCache(embedding_cache_path(catalog_service.graph_home_path)),
                    key_for=embedding_key_for_text,
                    run_id=staged_generation.generation_id if staged_generation is not None else "unstaged",
                )
                if initialize_store
                else None
            )
            indexing_embeddings: TextEmbeddings = embedding_cache or text_embeddings
            graph_store = _open_index_graph_store(
                catalog_service,
                catalog,
                metadata_store,
                initialize_store=initialize_store,
                previous_backend=previous_backend,
                selected_backend=selected_backend,
                full=full,
                requested_scope=requested_scope,
            )
            if initialize_store and selected_backend == "document" and previous_backend == "legacy" and not full:
                _bootstrap_document_graph(graph_store, catalog_service, catalog)
            if initialize_store and (selected_backend == "document" or graph_backend is not None):
                write_graph_backend_selection(catalog_service, selected_backend)
            chroma_store = ChromaVectorStore(
                catalog_service.vector_path,
                initialize=initialize_store,
                read_only=not initialize_store,
            )
            # Writable runs keep `vector/manifest.sqlite3` in step, so the plan never lists Chroma.
            vector_store: VectorStore = (
                manifest_tracked(chroma_store, catalog_service.vector_path) if initialize_store else chroma_store
            )
            vector_status_store = LocalVectorStatusStore(catalog_service.vector_status_path)
            graph_status_store = LocalGraphStatusStore(catalog_service.graph_status_path)
            return LocalIndexServiceBundle(
                catalog_service=catalog_service,
                catalog=catalog,
                index_service=IndexService(
                    catalog=catalog,
                    metadata_store=metadata_store,
                    vector_store=vector_store,
                    text_embeddings=indexing_embeddings,
                    vector_status_store=vector_status_store,
                    embedding_batch_size=text_embeddings.config.embedding_batch_size,
                    embedding_parallelism=text_embeddings.config.embedding_parallelism,
                    embedding_lazy_load=text_embeddings.config.embedding_lazy_load,
                    embedding_token_budget=getattr(
                        text_embeddings.config, "embedding_token_budget", DEFAULT_TOKEN_BUDGET
                    ),
                    graph_store=graph_store,
                    graph_extraction_spec=current_graph_extraction_spec(),
                    graph_status_store=graph_status_store,
                    status_reader=IndexStatusReader(
                        catalog=catalog,
                        metadata_store=metadata_store,
                        vector_store=vector_store,
                        text_embeddings=text_embeddings,
                        vector_status_store=vector_status_store,
                        embedding_batch_size=text_embeddings.config.embedding_batch_size,
                        embedding_parallelism=text_embeddings.config.embedding_parallelism,
                        embedding_lazy_load=text_embeddings.config.embedding_lazy_load,
                        graph_readiness=ReadOnlyGraphReadiness(
                            metadata_store=metadata_store,
                            graph_store=graph_store,
                            expected_spec=current_graph_extraction_spec(),
                        ),
                        graph_extraction_spec=current_graph_extraction_spec(),
                        graph_status_store=graph_status_store,
                    ),
                ),
                generation_manager=generation_manager,
                bundle_publisher=bundle_publisher,
                staged_generation=staged_generation,
                embedding_cache=embedding_cache,
            )
        except Exception:
            close = getattr(graph_store, "close", None)
            if callable(close):
                close()
            if staged_generation is not None and bundle_publisher is not None:
                bundle_publisher.discard(staged_generation)
            raise

    def _assert_write_targets_safe(self, *, catalog_service: CatalogService, catalog: VaultCatalog) -> None:
        catalog_service.assert_graph_home_write_target_safe(target_path=catalog_service.metadata_path, catalog=catalog)
        catalog_service.assert_graph_home_write_target_safe(target_path=catalog_service.vector_path, catalog=catalog)
        catalog_service.assert_graph_home_write_target_safe(
            target_path=catalog_service.vector_status_path, catalog=catalog
        )
        catalog_service.assert_graph_home_write_target_safe(target_path=catalog_service.graph_path, catalog=catalog)
        catalog_service.assert_graph_home_write_target_safe(
            target_path=document_store_path(catalog_service), catalog=catalog
        )
        catalog_service.assert_graph_home_write_target_safe(
            target_path=catalog_service.graph_status_path, catalog=catalog
        )
        catalog_service.assert_graph_home_write_target_safe(
            target_path=embedding_cache_path(catalog_service.graph_home_path), catalog=catalog
        )
        models_dir = load_embedding_selection(catalog_service.embedding_config_path).models_dir.expanduser()
        catalog_service.assert_cache_target_safe(target_path=models_dir, catalog=catalog)


def _select_graph_backend(
    config: CatalogService,
    *,
    initialize_store: bool,
    transactional: bool,
    requested_backend: GraphBackend | None,
) -> tuple[GraphBackend, GraphBackend]:
    previous_backend = selected_graph_backend(config)
    # Planning uses the current immutable source. Opening a candidate store
    # would either write state or require a transition that has not happened.
    selected_backend = (requested_backend or previous_backend) if initialize_store else previous_backend
    if initialize_store and selected_backend == "document" and not transactional:
        raise ProjectionGenerationError("document graph writes require transactional generation publication")
    if (
        requested_backend is not None
        and requested_backend != previous_backend
        and initialize_store
        and not transactional
    ):
        raise ProjectionGenerationError("graph backend transitions require transactional generation publication")
    return previous_backend, selected_backend


def _open_index_graph_store(
    config: CatalogService,
    catalog: VaultCatalog,
    metadata_store: SQLiteMetadataStore,
    *,
    initialize_store: bool,
    previous_backend: GraphBackend,
    selected_backend: GraphBackend,
    full: bool,
    requested_scope: QueryScope | None,
) -> GraphStore:
    if initialize_store and previous_backend == "document" and selected_backend == "legacy":
        if not full:
            raise ProjectionGenerationError("legacy rollback requires a full reindex")
        # This is a private staging copy. Rebuild rather than revive stale
        # evidence rows retained in the previous legacy cache.
        for path in (
            config.graph_path,
            Path(f"{config.graph_path}-wal"),
            Path(f"{config.graph_path}-shm"),
        ):
            config.assert_graph_home_write_target_safe(target_path=path, catalog=catalog)
            path.unlink(missing_ok=True)
    if initialize_store and selected_backend == "document":
        from graph_document import GraphDocumentError

        from vault_graph.indexing.extraction.vault_graph_document_adapter import VaultDocumentMappingError

        if previous_backend == "legacy":
            _discard_staged_document_cache(config, catalog)
        try:
            graph_store = open_graph_store(
                config, metadata_store=metadata_store, writable=True, backend=selected_backend
            )
        except (GraphStoreError, GraphDocumentError, VaultDocumentMappingError):
            if not full:
                raise
            rebuild_scope = requested_scope or catalog.default_scope()
            enabled_vaults = {entry.vault_id for entry in catalog.entries() if entry.enabled}
            if set(rebuild_scope.vault_ids) != enabled_vaults:
                raise ProjectionGenerationError("document graph cache recovery requires --all-vaults") from None
            _discard_staged_document_cache(config, catalog)
            graph_store = open_graph_store(
                config, metadata_store=metadata_store, writable=True, backend=selected_backend
            )
    else:
        graph_store = open_graph_store(
            config, metadata_store=metadata_store, writable=initialize_store, backend=selected_backend
        )
    return graph_store


def _bootstrap_document_graph(graph_store: GraphStore, config: CatalogService, catalog: VaultCatalog) -> None:
    from vault_graph.storage.local.document_graph_store import DocumentGraphStore

    legacy = SQLiteGraphStore.open_read_only(config.graph_path)
    if legacy.health().ok:
        scopes = tuple(
            QueryScope((entry.vault_id,), entry.content_scopes)
            for entry in catalog.entries()
            if entry.enabled and legacy.latest_revisions((QueryScope((entry.vault_id,), entry.content_scopes),))
        )
        assert isinstance(graph_store, DocumentGraphStore)
        graph_store.bootstrap_from_legacy(legacy, scopes)


def _discard_staged_document_cache(config: CatalogService, catalog: VaultCatalog) -> None:
    path = document_store_path(config)
    config.assert_graph_home_write_target_safe(target_path=path, catalog=catalog)
    if path.is_dir():
        shutil.rmtree(path)
    else:
        path.unlink(missing_ok=True)


def _default_text_embeddings(catalog_service: CatalogService) -> FastEmbedTextEmbeddings:
    return text_embeddings_for(catalog_service, local_files_only=False)


_CLEANUP_FAILED_PREFIX = "vector collection cleanup failed: "


def _remove_empty_vector_collections(
    catalog_service: CatalogService, *, keep: EmbeddingModelSpec
) -> ProjectionCommitResult:
    """Drop old-model empty collections from the unpublished generation. A failure does not stop publishing."""

    vector_store: ChromaVectorStore | None = None
    try:
        vector_store = ChromaVectorStore(catalog_service.vector_path)
        return ProjectionCommitResult(removed_vector_collections=vector_store.remove_empty_collections(keep=keep))
    except VectorStoreError as exc:
        # The adapter already prefixes its message with the phrase `vg index` prints before it.
        return ProjectionCommitResult(vector_cleanup_error=str(exc).removeprefix(_CLEANUP_FAILED_PREFIX))
    finally:
        if vector_store is not None:
            vector_store.close()


def _use_projection_root(catalog_service: CatalogService, root_path: Path) -> None:
    catalog_service.metadata_path = root_path / "metadata" / "metadata.sqlite3"
    catalog_service.vector_path = root_path / "vector" / "chroma"
    catalog_service.graph_path = root_path / "graph" / "graph.sqlite3"


def _write_projection_component_manifests(
    *,
    publisher: ProjectionBundlePublisher,
    staged: ProjectionLayout,
    report: IndexRunReport,
    catalog_service: CatalogService,
    catalog: VaultCatalog,
) -> tuple[str, ...]:
    metadata_revision = report.metadata.index_revision
    source_snapshot = {
        "vault_ids": list(report.metadata.vault_ids),
        "metadata_index_revision": metadata_revision,
    }
    metadata_health = SQLiteMetadataStore(catalog_service.metadata_path, initialize=False).health()
    publisher.write_component_manifest(
        staged,
        "metadata",
        source_snapshot=source_snapshot,
        contract={
            "loader": "VaultLoader",
            "normalizer": "DocumentNormalizer",
            "chunker": CHUNKER_VERSION,
        },
        schema_version=metadata_health.schema_version,
        revision=metadata_revision,
    )
    enabled_components = ["metadata"]
    # A failed vector run publishes no vector component, like a metadata-only refresh.
    if report.vector is not None and not getattr(report.vector, "failed", False):
        vector = report.vector
        embedding_spec = getattr(vector, "embedding_spec", None)
        vector_revision = str(getattr(vector, "vector_index_revision", f"vector-{metadata_revision}"))
        vector_schema = ChromaVectorStore(catalog_service.vector_path, read_only=True).health().schema_version
        publisher.write_component_manifest(
            staged,
            "vector",
            source_snapshot=source_snapshot,
            contract={
                "embedding_model": getattr(embedding_spec, "model_name", "unknown"),
                "embedding_model_version": getattr(embedding_spec, "model_version", "unknown"),
                "embedding_dimensions": getattr(embedding_spec, "dimensions", 0),
                "embedding_spec_version": getattr(embedding_spec, "spec_version", "unknown"),
            },
            schema_version=vector_schema,
            revision=vector_revision,
        )
        enabled_components.append("vector")
    if report.graph is not None:
        graph = report.graph
        apply_result = getattr(graph, "apply_result", None)
        revisions = tuple(
            getattr(row, "graph_index_revision", "") for row in getattr(apply_result, "graph_revision_rows", ())
        )
        graph_revision = (
            sorted(revision for revision in revisions if revision)[0] if revisions else f"graph-{metadata_revision}"
        )
        graph_spec = current_graph_extraction_spec()
        graph_schema = (
            open_graph_store(
                catalog_service,
                metadata_store=SQLiteMetadataStore(catalog_service.metadata_path, initialize=False),
            )
            .health()
            .schema_version
        )
        publisher.write_component_manifest(
            staged,
            "graph",
            source_snapshot=source_snapshot,
            contract={"extraction_spec": asdict(graph_spec), "backend": selected_graph_backend(catalog_service)},
            schema_version=graph_schema,
            revision=graph_revision,
        )
        enabled_components.append("graph")
    hygiene = open_projection_hygiene_service(catalog_service).audit(
        scope=catalog.scope_for_vault_ids(report.metadata.vault_ids),
        active_generation_id=staged.generation_id,
    )
    dangling = {
        "keyword": hygiene.dangling_keyword_refs,
        "vector": hygiene.dangling_vector_refs,
        "graph": hygiene.dangling_graph_refs,
    }
    if any(count for count in dangling.values()):
        raise ProjectionGenerationError(f"projection bundle hygiene failed: dangling references {dangling}")
    return tuple(enabled_components)


def open_projection_hygiene_service(catalog_service: CatalogService) -> ProjectionHygieneService:
    """Build the read-only projection audit with local stores (보완4)."""
    from vault_graph.storage.local.document_graph_store import DocumentGraphStore

    metadata_store = SQLiteMetadataStore(catalog_service.metadata_path, initialize=False)
    graph_store = (
        open_graph_store(catalog_service, metadata_store=metadata_store)
        if selected_graph_backend(catalog_service) == "document"
        else None
    )
    return ProjectionHygieneService(
        metadata_path=catalog_service.metadata_path,
        metadata_store=metadata_store,
        open_vector_store=lambda: ChromaVectorStore(catalog_service.vector_path, read_only=True),
        graph_path=catalog_service.graph_path,
        graph_store=graph_store,
        document_evidence_refs=graph_store if isinstance(graph_store, DocumentGraphStore) else None,
    )


def manifest_tracked(chroma_store: VectorStore, vector_path: Path) -> VectorStore:
    """Wrap a writable Chroma store so `vector/manifest.sqlite3` follows each successful write."""

    return ManifestTrackedVectorStore(
        chroma_store,
        manifest=SQLiteVectorManifestStore(manifest_path_for_vector_path(vector_path)),
        listing=ChromaSQLiteListing(vector_path, collection_prefix=COLLECTION_PREFIX, backend=CHROMA_BACKEND),
        backend=CHROMA_BACKEND,
    )
