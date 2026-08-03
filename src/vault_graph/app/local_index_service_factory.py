from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from vault_graph.app.catalog_service import CatalogService
from vault_graph.app.graph_readiness_service import ReadOnlyGraphReadiness
from vault_graph.app.index_service import IndexService
from vault_graph.app.projection_generation import ProjectionGenerationManager, ProjectionLayout
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
    staged_generation: ProjectionLayout | None = None
    projection_committed: bool = False

    def commit_projection(self) -> None:
        if self.generation_manager is None or self.staged_generation is None:
            return
        self.generation_manager.activate(self.staged_generation)
        self.projection_committed = True

    def close(self) -> None:
        self.index_service.close()
        if self.generation_manager is not None and self.staged_generation is not None and not self.projection_committed:
            self.generation_manager.discard(self.staged_generation)


TextEmbeddingsFactory = Callable[[CatalogService], FastEmbedTextEmbeddings]


class LocalIndexServiceFactory:
    def __init__(self, *, text_embeddings_factory: TextEmbeddingsFactory | None = None) -> None:
        self._text_embeddings_factory = text_embeddings_factory or _default_text_embeddings

    def open(
        self,
        *,
        state_path: Path,
        initialize_store: bool,
        transactional_full: bool = False,
    ) -> LocalIndexServiceBundle:
        catalog_service = CatalogService(state_path=state_path)
        catalog = catalog_service.load_catalog()
        generation_manager = ProjectionGenerationManager(catalog_service.state_path) if transactional_full else None
        staged_generation = generation_manager.stage() if generation_manager is not None else None
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
            staged_generation=staged_generation,
        )

    def _assert_write_targets_safe(self, *, catalog_service: CatalogService, catalog: VaultCatalog) -> None:
        catalog_service.assert_write_target_safe(target_path=catalog_service.metadata_path, catalog=catalog)
        catalog_service.assert_write_target_safe(target_path=catalog_service.vector_path, catalog=catalog)
        catalog_service.assert_write_target_safe(target_path=catalog_service.vector_status_path, catalog=catalog)
        catalog_service.assert_write_target_safe(target_path=catalog_service.graph_path, catalog=catalog)
        catalog_service.assert_write_target_safe(target_path=catalog_service.graph_status_path, catalog=catalog)
        catalog_service.assert_cache_target_safe(target_path=catalog_service.embedding_cache_path, catalog=catalog)


def _default_text_embeddings(catalog_service: CatalogService) -> FastEmbedTextEmbeddings:
    return FastEmbedTextEmbeddings(config=FastEmbedTextEmbeddingsConfig(cache_dir=catalog_service.embedding_cache_path))


def _use_projection_root(catalog_service: CatalogService, root_path: Path) -> None:
    catalog_service.metadata_path = root_path / "metadata" / "metadata.sqlite3"
    catalog_service.vector_path = root_path / "vector" / "chroma"
    catalog_service.vector_status_path = root_path / "vector" / "status.json"
    catalog_service.graph_path = root_path / "graph" / "graph.sqlite3"
    catalog_service.graph_status_path = root_path / "graph" / "status.json"
