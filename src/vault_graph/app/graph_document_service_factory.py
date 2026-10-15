"""Compatibility import for :mod:`vault_graph.interface.composition.graph_document_service_factory`."""

import sys
from pathlib import Path as Path

from graph_document import GraphLimits as GraphLimits
from graph_document import ReadLimits as ReadLimits

from vault_graph.indexing.extraction.vault_graph_document_adapter import (
    VaultGraphDocumentAdapter as VaultGraphDocumentAdapter,
)
from vault_graph.interface.composition import graph_document_service_factory as _implementation
from vault_graph.interface.composition.graph_document_service_factory import (
    GraphDocumentServiceFactory as GraphDocumentServiceFactory,
)
from vault_graph.operation.scope.catalog_service import CatalogService as CatalogService
from vault_graph.operation.scope.graph_home import GraphHomeResolver as GraphHomeResolver
from vault_graph.storage.local.sqlite_metadata_store import SQLiteMetadataStore as SQLiteMetadataStore

sys.modules[__name__] = _implementation
