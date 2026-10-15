"""Compatibility import for :mod:`vault_graph.interface.composition.read_only_service_factory`."""

import sys
from dataclasses import dataclass as dataclass
from pathlib import Path as Path
from typing import TYPE_CHECKING as TYPE_CHECKING

from vault_graph.interface.composition import read_only_service_factory as _implementation
from vault_graph.interface.composition.graph_store_factory import open_graph_store as open_graph_store
from vault_graph.interface.composition.read_only_service_factory import ReadOnlyServiceFactory as ReadOnlyServiceFactory
from vault_graph.interface.composition.read_only_service_factory import ReadOnlyServices as ReadOnlyServices
from vault_graph.interface.composition.read_only_service_factory import _RetrievalComponents as _RetrievalComponents
from vault_graph.operation.scope.catalog_service import CatalogService as CatalogService
from vault_graph.operation.scope.graph_home import GraphHomeResolver as GraphHomeResolver
from vault_graph.operation.scope.vault_catalog import VaultCatalog as VaultCatalog
from vault_graph.storage.interfaces.metadata_store import MetadataStore as MetadataStore

sys.modules[__name__] = _implementation
