"""Compatibility import for :mod:`vault_graph.interface.mcp.mcp_service_factory`."""

import sys
from dataclasses import dataclass as dataclass
from pathlib import Path as Path
from typing import TYPE_CHECKING as TYPE_CHECKING

from vault_graph.interface.composition.read_only_service_factory import ReadOnlyServiceFactory as ReadOnlyServiceFactory
from vault_graph.interface.mcp import mcp_service_factory as _implementation
from vault_graph.interface.mcp.mcp_service_factory import McpServiceFactory as McpServiceFactory
from vault_graph.interface.mcp.mcp_service_factory import McpServices as McpServices
from vault_graph.operation.scope.catalog_service import CatalogService as CatalogService
from vault_graph.operation.scope.vault_catalog import VaultCatalog as VaultCatalog
from vault_graph.storage.interfaces.metadata_store import MetadataStore as MetadataStore

sys.modules[__name__] = _implementation
