"""Compatibility import for :mod:`vault_graph.indexing.ingestion.vault_loader`."""

import hashlib as hashlib
import sys
from dataclasses import dataclass as dataclass
from pathlib import Path as Path

from vault_graph.errors import CatalogError as CatalogError
from vault_graph.indexing.ingestion import vault_loader as _implementation
from vault_graph.indexing.ingestion.document_models import ExtractedDocument as ExtractedDocument
from vault_graph.indexing.ingestion.document_models import SourceDocument as SourceDocument
from vault_graph.indexing.ingestion.document_readers import DocumentReaderRegistry as DocumentReaderRegistry
from vault_graph.indexing.ingestion.vault_frontmatter_reader import FrontmatterProjection as FrontmatterProjection
from vault_graph.indexing.ingestion.vault_loader import LoadedVaultDocument as LoadedVaultDocument
from vault_graph.indexing.ingestion.vault_loader import VaultLoader as VaultLoader
from vault_graph.indexing.ingestion.vault_loader import _actual_content_scopes as _actual_content_scopes
from vault_graph.indexing.ingestion.vault_loader import _is_same_or_child as _is_same_or_child
from vault_graph.operation.scope.vault_catalog import QueryScope as QueryScope
from vault_graph.operation.scope.vault_catalog import VaultCatalogEntry as VaultCatalogEntry

sys.modules[__name__] = _implementation
