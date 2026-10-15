"""Compatibility import for :mod:`vault_graph.indexing.extraction.graph_source_store`."""

import sys
from pathlib import PurePosixPath as PurePosixPath
from typing import Protocol as Protocol

from vault_graph.indexing.extraction import graph_source_store as _implementation
from vault_graph.indexing.extraction.graph_source_store import GraphExtractionContext as GraphExtractionContext
from vault_graph.indexing.extraction.graph_source_store import GraphSourceStore as GraphSourceStore
from vault_graph.indexing.extraction.graph_source_store import MetadataGraphSourceStore as MetadataGraphSourceStore
from vault_graph.indexing.extraction.graph_source_store import PreviewGraphSourceStore as PreviewGraphSourceStore
from vault_graph.indexing.extraction.graph_source_store import _basename_index as _basename_index
from vault_graph.indexing.extraction.graph_source_store import _ensure_md_suffix as _ensure_md_suffix
from vault_graph.indexing.extraction.graph_source_store import _normalize_link_target as _normalize_link_target
from vault_graph.indexing.extraction.graph_source_store import (
    _normalize_vault_relative_path as _normalize_vault_relative_path,
)
from vault_graph.indexing.ingestion.document_normalizer import ChunkSnapshot as ChunkSnapshot
from vault_graph.indexing.ingestion.document_normalizer import DocumentSnapshot as DocumentSnapshot
from vault_graph.operation.scope.vault_catalog import ALLOWED_CONTENT_ROOTS as ALLOWED_CONTENT_ROOTS
from vault_graph.operation.scope.vault_catalog import QueryScope as QueryScope
from vault_graph.storage.interfaces.metadata_store import MetadataStore as MetadataStore

sys.modules[__name__] = _implementation
