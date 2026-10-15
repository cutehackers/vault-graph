"""Compatibility import for :mod:`vault_graph.interface.composition.local_index_service_factory`."""

import shutil as shutil
import sys
from collections.abc import Callable as Callable
from dataclasses import asdict as asdict
from dataclasses import dataclass as dataclass
from pathlib import Path as Path

from vault_graph.errors import GraphStoreError as GraphStoreError
from vault_graph.indexing.index_service import IndexRunReport as IndexRunReport
from vault_graph.indexing.index_service import IndexService as IndexService
from vault_graph.indexing.ingestion.document_chunking import CHUNKER_VERSION as CHUNKER_VERSION
from vault_graph.indexing.publication.projection_generation import (
    ProjectionBundlePublisher as ProjectionBundlePublisher,
)
from vault_graph.indexing.publication.projection_generation import (
    ProjectionGenerationError as ProjectionGenerationError,
)
from vault_graph.indexing.publication.projection_generation import (
    ProjectionGenerationManager as ProjectionGenerationManager,
)
from vault_graph.indexing.publication.projection_generation import ProjectionLayout as ProjectionLayout
from vault_graph.interface.composition import local_index_service_factory as _implementation
from vault_graph.interface.composition.adapters.text_embeddings import (
    FastEmbedTextEmbeddings as FastEmbedTextEmbeddings,
)
from vault_graph.interface.composition.adapters.text_embeddings import (
    FastEmbedTextEmbeddingsConfig as FastEmbedTextEmbeddingsConfig,
)
from vault_graph.interface.composition.graph_store_factory import GraphBackend as GraphBackend
from vault_graph.interface.composition.graph_store_factory import document_store_path as document_store_path
from vault_graph.interface.composition.graph_store_factory import open_graph_store as open_graph_store
from vault_graph.interface.composition.graph_store_factory import selected_graph_backend as selected_graph_backend
from vault_graph.interface.composition.graph_store_factory import (
    write_graph_backend_selection as write_graph_backend_selection,
)
from vault_graph.interface.composition.local_index_service_factory import (
    LocalIndexServiceBundle as LocalIndexServiceBundle,
)
from vault_graph.interface.composition.local_index_service_factory import (
    LocalIndexServiceFactory as LocalIndexServiceFactory,
)
from vault_graph.interface.composition.local_index_service_factory import TextEmbeddingsFactory as TextEmbeddingsFactory
from vault_graph.interface.composition.local_index_service_factory import (
    _bootstrap_document_graph as _bootstrap_document_graph,
)
from vault_graph.interface.composition.local_index_service_factory import (
    _default_text_embeddings as _default_text_embeddings,
)
from vault_graph.interface.composition.local_index_service_factory import (
    _discard_staged_document_cache as _discard_staged_document_cache,
)
from vault_graph.interface.composition.local_index_service_factory import (
    _open_index_graph_store as _open_index_graph_store,
)
from vault_graph.interface.composition.local_index_service_factory import _select_graph_backend as _select_graph_backend
from vault_graph.interface.composition.local_index_service_factory import _use_projection_root as _use_projection_root
from vault_graph.interface.composition.local_index_service_factory import (
    _write_projection_component_manifests as _write_projection_component_manifests,
)
from vault_graph.operation.diagnostics.projection_hygiene_service import (
    ProjectionHygieneService as ProjectionHygieneService,
)
from vault_graph.operation.readiness.graph_readiness_service import ReadOnlyGraphReadiness as ReadOnlyGraphReadiness
from vault_graph.operation.scope.catalog_service import CatalogService as CatalogService
from vault_graph.operation.scope.vault_catalog import QueryScope as QueryScope
from vault_graph.operation.scope.vault_catalog import VaultCatalog as VaultCatalog
from vault_graph.retrieval.graph.graph_contracts import current_graph_extraction_spec as current_graph_extraction_spec
from vault_graph.storage.interfaces.graph_store import GraphStore as GraphStore
from vault_graph.storage.local.chroma_vector_store import ChromaVectorStore as ChromaVectorStore
from vault_graph.storage.local.graph_status_store import LocalGraphStatusStore as LocalGraphStatusStore
from vault_graph.storage.local.sqlite_graph_store import SQLiteGraphStore as SQLiteGraphStore
from vault_graph.storage.local.sqlite_metadata_store import SQLiteMetadataStore as SQLiteMetadataStore
from vault_graph.storage.local.vector_status_store import LocalVectorStatusStore as LocalVectorStatusStore

sys.modules[__name__] = _implementation
