from __future__ import annotations

from collections.abc import Callable
from dataclasses import asdict, dataclass
from pathlib import Path

from vault_graph.app.catalog_service import CatalogService
from vault_graph.app.graph_readiness_service import ReadOnlyGraphReadiness
from vault_graph.app.index_service import IndexRunReport, IndexService
from vault_graph.app.projection_generation import (
    ProjectionBundlePublisher,
    ProjectionGenerationError,
    ProjectionGenerationManager,
    ProjectionLayout,
)
from vault_graph.app.projection_hygiene_service import ProjectionHygieneService
from vault_graph.embeddings.fastembed_text_embeddings import FastEmbedTextEmbeddings, FastEmbedTextEmbeddingsConfig
from vault_graph.graph.graph_contracts import current_graph_extraction_spec
from vault_graph.ingestion.vault_catalog import VaultCatalog
from vault_graph.storage.local.chroma_vector_store import ChromaVectorStore
from vault_graph.storage.local.graph_status_store import LocalGraphStatusStore
from vault_graph.storage.local.sqlite_graph_store import SQLiteGraphStore
from vault_graph.storage.local.sqlite_metadata_store import SQLiteMetadataStore
from vault_graph.storage.local.vector_status_store import LocalVectorStatusStore


@dataclass
class LocalIndexServiceBundle:
    catalog_service: CatalogService
    catalog: VaultCatalog
    index_service: IndexService
    generation_manager: ProjectionGenerationManager | None = None
    bundle_publisher: ProjectionBundlePublisher | None = None
    staged_generation: ProjectionLayout | None = None
    projection_committed: bool = False

    def commit_projection(self, report: IndexRunReport | None = None) -> None:
        if self.staged_generation is None:
            return
        if self.bundle_publisher is None:
            if self.generation_manager is None:
                return
            self.generation_manager.activate(self.staged_generation)
        else:
            if report is None:
                raise RuntimeError("projection report is required before bundle publication")
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
        self.projection_committed = True

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
        if initialize_store:
            self._assert_write_targets_safe(catalog_service=catalog_service, catalog=catalog)
        metadata_store = SQLiteMetadataStore(catalog_service.metadata_path, initialize=initialize_store)
        text_embeddings = self._text_embeddings_factory(catalog_service)
        graph_store = (
            SQLiteGraphStore.open_writable(catalog_service.graph_path)
            if initialize_store
            else SQLiteGraphStore.open_read_only(catalog_service.graph_path)
        )
        return LocalIndexServiceBundle(
            catalog_service=catalog_service,
            catalog=catalog,
            index_service=IndexService(
                catalog=catalog,
                metadata_store=metadata_store,
                vector_store=ChromaVectorStore(
                    catalog_service.vector_path,
                    initialize=initialize_store,
                    read_only=not initialize_store,
                ),
                text_embeddings=text_embeddings,
                vector_status_store=LocalVectorStatusStore(catalog_service.vector_status_path),
                embedding_batch_size=text_embeddings.config.embedding_batch_size,
                embedding_parallelism=text_embeddings.config.embedding_parallelism,
                embedding_lazy_load=text_embeddings.config.embedding_lazy_load,
                graph_store=graph_store,
                graph_extraction_spec=current_graph_extraction_spec(),
                graph_status_store=LocalGraphStatusStore(catalog_service.graph_status_path),
                graph_readiness=ReadOnlyGraphReadiness(
                    metadata_store=metadata_store,
                    graph_store=graph_store,
                    expected_spec=current_graph_extraction_spec(),
                ),
            ),
            generation_manager=generation_manager,
            bundle_publisher=bundle_publisher,
            staged_generation=staged_generation,
        )

    def _assert_write_targets_safe(self, *, catalog_service: CatalogService, catalog: VaultCatalog) -> None:
        catalog_service.assert_graph_home_write_target_safe(target_path=catalog_service.metadata_path, catalog=catalog)
        catalog_service.assert_graph_home_write_target_safe(target_path=catalog_service.vector_path, catalog=catalog)
        catalog_service.assert_graph_home_write_target_safe(
            target_path=catalog_service.vector_status_path, catalog=catalog
        )
        catalog_service.assert_graph_home_write_target_safe(target_path=catalog_service.graph_path, catalog=catalog)
        catalog_service.assert_graph_home_write_target_safe(
            target_path=catalog_service.graph_status_path, catalog=catalog
        )
        catalog_service.assert_cache_target_safe(target_path=catalog_service.embedding_cache_path, catalog=catalog)


def _default_text_embeddings(catalog_service: CatalogService) -> FastEmbedTextEmbeddings:
    return FastEmbedTextEmbeddings(config=FastEmbedTextEmbeddingsConfig(cache_dir=catalog_service.embedding_cache_path))


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
            "chunker": "document-normalizer-v1",
        },
        schema_version=metadata_health.schema_version,
        revision=metadata_revision,
    )
    enabled_components = ["metadata"]
    if report.vector is not None:
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
        graph_schema = SQLiteGraphStore.open_read_only(catalog_service.graph_path).health().schema_version
        publisher.write_component_manifest(
            staged,
            "graph",
            source_snapshot=source_snapshot,
            contract={"extraction_spec": asdict(graph_spec)},
            schema_version=graph_schema,
            revision=graph_revision,
        )
        enabled_components.append("graph")
    hygiene = ProjectionHygieneService(
        metadata_path=catalog_service.metadata_path,
        vector_path=catalog_service.vector_path,
        graph_path=catalog_service.graph_path,
    ).audit(
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
