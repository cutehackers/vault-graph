"""Compatibility import for :mod:`vault_graph.operation.diagnostics.index_status_reader`."""

import sys
from dataclasses import dataclass as dataclass

from vault_graph.indexing.vector_indexer import VectorIndexer as VectorIndexer
from vault_graph.operation.diagnostics import index_status_reader as _implementation
from vault_graph.operation.diagnostics.index_status_reader import IndexStatusReader as IndexStatusReader
from vault_graph.operation.diagnostics.index_status_reader import StatusReport as StatusReport
from vault_graph.operation.diagnostics.index_status_reader import _embedding_config_value as _embedding_config_value
from vault_graph.operation.diagnostics.index_status_reader import (
    _graph_not_configured_readiness as _graph_not_configured_readiness,
)
from vault_graph.operation.readiness.graph_readiness_service import ReadOnlyGraphReadiness as ReadOnlyGraphReadiness
from vault_graph.operation.scope.catalog_query_scopes import actual_query_scopes as actual_query_scopes
from vault_graph.operation.scope.vault_catalog import QueryScope as QueryScope
from vault_graph.operation.scope.vault_catalog import VaultCatalog as VaultCatalog
from vault_graph.retrieval.graph.graph_contracts import GraphExtractionSpec as GraphExtractionSpec
from vault_graph.retrieval.graph.graph_contracts import current_graph_extraction_spec as current_graph_extraction_spec
from vault_graph.retrieval.graph.graph_identity import graph_scope_key as graph_scope_key
from vault_graph.retrieval.graph.graph_readiness import GraphReadiness as GraphReadiness
from vault_graph.retrieval.graph.graph_readiness import GraphScopeReadiness as GraphScopeReadiness
from vault_graph.storage.interfaces.metadata_store import MetadataStore as MetadataStore
from vault_graph.storage.interfaces.text_embeddings import TextEmbeddings as TextEmbeddings
from vault_graph.storage.interfaces.vector_store import VectorStore as VectorStore
from vault_graph.storage.local.graph_status_store import GraphRunStatus as GraphRunStatus
from vault_graph.storage.local.graph_status_store import LocalGraphStatusStore as LocalGraphStatusStore
from vault_graph.storage.local.graph_status_store import graph_scope_status_key as graph_scope_status_key
from vault_graph.storage.local.graph_status_store import graph_spec_key as graph_spec_key
from vault_graph.storage.local.vector_status_store import LocalVectorStatusStore as LocalVectorStatusStore
from vault_graph.storage.local.vector_status_store import embedding_spec_key as embedding_spec_key
from vault_graph.storage.local.vector_status_store import scope_key_for_status as scope_key_for_status

sys.modules[__name__] = _implementation
