"""Compatibility import for :mod:`vault_graph.storage.local.vector_store_adapter`."""

import hashlib as hashlib
import sys
from collections.abc import Mapping as Mapping
from pathlib import Path as Path
from typing import Any as Any
from typing import cast as cast

from vector_search import CollectionSpec as CollectionSpec
from vector_search import StoredVector as StoredVector
from vector_search import VectorDeletion as VectorDeletion
from vector_search import VectorSearchError as VectorSearchError

from vault_graph.errors import VectorStoreError as VectorStoreError
from vault_graph.indexing.ingestion.document_authority import DocumentRole as DocumentRole
from vault_graph.operation.scope.vault_catalog import QueryScope as QueryScope
from vault_graph.storage.interfaces.store_health import StoreHealth as StoreHealth
from vault_graph.storage.interfaces.text_embeddings import EmbeddingModelSpec as EmbeddingModelSpec
from vault_graph.storage.interfaces.vector_store import VectorEmbeddingRecord as VectorEmbeddingRecord
from vault_graph.storage.interfaces.vector_store import VectorHit as VectorHit
from vault_graph.storage.interfaces.vector_store import VectorManifestRecord as VectorManifestRecord
from vault_graph.storage.interfaces.vector_store import VectorQuery as VectorQuery
from vault_graph.storage.interfaces.vector_store import VectorStore as VectorStore
from vault_graph.storage.interfaces.vector_store import VectorTombstone as VectorTombstone
from vault_graph.storage.local import vector_store_adapter as _implementation
from vault_graph.storage.local.vector_store_adapter import CHROMA_BACKEND as CHROMA_BACKEND
from vault_graph.storage.local.vector_store_adapter import CHROMA_VECTOR_SCHEMA_VERSION as CHROMA_VECTOR_SCHEMA_VERSION
from vault_graph.storage.local.vector_store_adapter import COLLECTION_PREFIX as COLLECTION_PREFIX
from vault_graph.storage.local.vector_store_adapter import SQLITE_VECTOR_ID_BATCH_SIZE as SQLITE_VECTOR_ID_BATCH_SIZE
from vault_graph.storage.local.vector_store_adapter import ChromaVectorStore as ChromaVectorStore
from vault_graph.storage.local.vector_store_adapter import _collection_spec as _collection_spec
from vault_graph.storage.local.vector_store_adapter import (
    _manifest_record_from_metadata as _manifest_record_from_metadata,
)
from vault_graph.storage.local.vector_store_adapter import _metadata_for_record as _metadata_for_record
from vault_graph.storage.local.vector_store_adapter import _metadata_in_scope as _metadata_in_scope

sys.modules[__name__] = _implementation
