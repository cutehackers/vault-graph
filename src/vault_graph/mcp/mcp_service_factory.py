from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from vault_graph.app.catalog_service import CatalogService
from vault_graph.ingestion.vault_catalog import VaultCatalog
from vault_graph.storage.interfaces.metadata_store import MetadataStore

if TYPE_CHECKING:
    from vault_graph.app.graph_resource_service import GraphResourceService
    from vault_graph.app.graph_retrieval_service import GraphRetrievalService
    from vault_graph.app.index_service import IndexService
    from vault_graph.context.context_pack_builder import ContextPackBuilder
    from vault_graph.context.context_pack_renderer import ContextPackRenderer
    from vault_graph.embeddings.fastembed_text_embeddings import FastEmbedTextEmbeddings
    from vault_graph.retrieval.graph_candidates import GraphSearchCandidateProvider
    from vault_graph.retrieval.retrieval_service import RetrievalService


@dataclass(frozen=True)
class McpServices:
    catalog_service: CatalogService
    catalog: VaultCatalog
    metadata_store: MetadataStore
    retrieval_service: RetrievalService
    context_pack_builder: ContextPackBuilder
    context_pack_renderer: ContextPackRenderer


class McpServiceFactory:
    def __init__(self, *, state_path: Path) -> None:
        self._state_path = state_path

    def open_read_only(self) -> McpServices:
        from vault_graph.app.search_readiness_service import ReadOnlySearchReadiness
        from vault_graph.context.context_pack_builder import MetadataContextEvidenceResolver, SearchContextPackBuilder
        from vault_graph.context.context_pack_renderer import DefaultContextPackRenderer
        from vault_graph.retrieval.retrieval_service import RetrievalService
        from vault_graph.storage.local.chroma_vector_store import ChromaVectorStore
        from vault_graph.storage.local.sqlite_keyword_index import SQLiteKeywordIndex
        from vault_graph.storage.local.sqlite_metadata_store import SQLiteMetadataStore

        catalog_service, catalog = self._catalog()
        metadata_store = SQLiteMetadataStore(catalog_service.metadata_path, initialize=False)
        keyword_index = SQLiteKeywordIndex(catalog_service.metadata_path)
        vector_store = ChromaVectorStore(catalog_service.vector_path, initialize=False, read_only=True)
        text_embeddings = self._search_text_embeddings(catalog_service)
        retrieval_service = RetrievalService(
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
        )
        return McpServices(
            catalog_service=catalog_service,
            catalog=catalog,
            metadata_store=metadata_store,
            retrieval_service=retrieval_service,
            context_pack_builder=SearchContextPackBuilder(
                catalog=catalog,
                retrieval_service=retrieval_service,
                evidence_resolver=MetadataContextEvidenceResolver(metadata_store=metadata_store),
            ),
            context_pack_renderer=DefaultContextPackRenderer(),
        )

    def open_status_service(self) -> IndexService:
        from vault_graph.app.graph_readiness_service import ReadOnlyGraphReadiness
        from vault_graph.app.index_service import IndexService
        from vault_graph.graph.graph_contracts import current_graph_extraction_spec
        from vault_graph.storage.local.chroma_vector_store import ChromaVectorStore
        from vault_graph.storage.local.graph_status_store import LocalGraphStatusStore
        from vault_graph.storage.local.sqlite_graph_store import SQLiteGraphStore
        from vault_graph.storage.local.sqlite_metadata_store import SQLiteMetadataStore
        from vault_graph.storage.local.vector_status_store import LocalVectorStatusStore

        catalog_service, catalog = self._catalog()
        metadata_store = SQLiteMetadataStore(catalog_service.metadata_path, initialize=False)
        graph_store = SQLiteGraphStore.open_read_only(catalog_service.graph_path)
        text_embeddings = self._search_text_embeddings(catalog_service)
        return IndexService(
            catalog=catalog,
            metadata_store=metadata_store,
            vector_store=ChromaVectorStore(catalog_service.vector_path, initialize=False, read_only=True),
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
        )

    def open_graph_retrieval_service(self) -> GraphRetrievalService:
        from vault_graph.app.graph_readiness_service import ReadOnlyGraphReadiness
        from vault_graph.app.graph_retrieval_service import GraphRetrievalService
        from vault_graph.graph.graph_contracts import current_graph_extraction_spec
        from vault_graph.projection.rustworkx_projection import RustworkxGraphProjection
        from vault_graph.storage.local.sqlite_graph_store import SQLiteGraphStore
        from vault_graph.storage.local.sqlite_metadata_store import SQLiteMetadataStore

        catalog_service, catalog = self._catalog()
        metadata_store = SQLiteMetadataStore(catalog_service.metadata_path, initialize=False)
        graph_store = SQLiteGraphStore.open_read_only(catalog_service.graph_path)
        readiness = ReadOnlyGraphReadiness(
            metadata_store=metadata_store,
            graph_store=graph_store,
            expected_spec=current_graph_extraction_spec(),
        )
        return GraphRetrievalService(
            catalog=catalog,
            metadata_store=metadata_store,
            graph_store=graph_store,
            graph_readiness=readiness,
            projection=RustworkxGraphProjection(),
        )

    def open_graph_resource_service(self) -> GraphResourceService:
        from vault_graph.app.graph_readiness_service import ReadOnlyGraphReadiness
        from vault_graph.app.graph_resource_service import GraphResourceService
        from vault_graph.graph.graph_contracts import current_graph_extraction_spec
        from vault_graph.storage.local.sqlite_graph_store import SQLiteGraphStore
        from vault_graph.storage.local.sqlite_metadata_store import SQLiteMetadataStore

        catalog_service, catalog = self._catalog()
        metadata_store = SQLiteMetadataStore(catalog_service.metadata_path, initialize=False)
        graph_store = SQLiteGraphStore.open_read_only(catalog_service.graph_path)
        readiness = ReadOnlyGraphReadiness(
            metadata_store=metadata_store,
            graph_store=graph_store,
            expected_spec=current_graph_extraction_spec(),
        )
        return GraphResourceService(
            catalog=catalog,
            metadata_store=metadata_store,
            graph_store=graph_store,
            graph_readiness=readiness,
        )

    def open_graph_search_candidate_provider(self) -> GraphSearchCandidateProvider:
        from vault_graph.retrieval.graph_candidates import GraphSearchCandidateProvider

        return GraphSearchCandidateProvider(graph_retrieval_service=self.open_graph_retrieval_service())

    def _catalog(self) -> tuple[CatalogService, VaultCatalog]:
        catalog_service = CatalogService(state_path=self._state_path)
        catalog = catalog_service.load_catalog()
        return catalog_service, catalog

    def _search_text_embeddings(self, catalog_service: CatalogService) -> FastEmbedTextEmbeddings:
        from vault_graph.embeddings.fastembed_text_embeddings import (
            FastEmbedTextEmbeddings,
            FastEmbedTextEmbeddingsConfig,
        )

        return FastEmbedTextEmbeddings(
            config=FastEmbedTextEmbeddingsConfig(
                cache_dir=catalog_service.embedding_cache_path,
                local_files_only=True,
            )
        )
