"""Compatibility import for :mod:`vault_graph.operation.readiness.search_readiness_service`."""

import sys

from vault_graph.indexing.vector_indexer import VectorIndexer as VectorIndexer
from vault_graph.operation.readiness import search_readiness_service as _implementation
from vault_graph.operation.readiness.search_readiness import SearchReadinessReport as SearchReadinessReport
from vault_graph.operation.readiness.search_readiness import SearchScopeReadiness as SearchScopeReadiness
from vault_graph.operation.readiness.search_readiness import SearchStoreRevision as SearchStoreRevision
from vault_graph.operation.readiness.search_readiness_service import ReadOnlySearchReadiness as ReadOnlySearchReadiness
from vault_graph.operation.readiness.search_readiness_service import _revision_from_values as _revision_from_values
from vault_graph.operation.readiness.search_readiness_service import _scope_key as _scope_key
from vault_graph.operation.scope.vault_catalog import QueryScope as QueryScope
from vault_graph.storage.interfaces.keyword_index import KeywordIndex as KeywordIndex
from vault_graph.storage.interfaces.metadata_store import MetadataStore as MetadataStore
from vault_graph.storage.interfaces.store_health import StoreHealth as StoreHealth
from vault_graph.storage.interfaces.text_embeddings import TextEmbeddings as TextEmbeddings
from vault_graph.storage.interfaces.vector_store import VectorStore as VectorStore

sys.modules[__name__] = _implementation
