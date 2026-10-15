"""Compatibility import for :mod:`vault_graph.operation.scope.catalog_service`."""

import sys
from pathlib import Path as Path

from vault_graph.indexing.publication.projection_generation import (
    ProjectionGenerationManager as ProjectionGenerationManager,
)
from vault_graph.operation.scope import catalog_service as _implementation
from vault_graph.operation.scope.catalog_service import CatalogService as CatalogService
from vault_graph.operation.scope.graph_home import GraphHomeResolver as GraphHomeResolver
from vault_graph.operation.scope.path_guard import assert_graph_home_outside_vaults as assert_graph_home_outside_vaults
from vault_graph.operation.scope.path_guard import (
    assert_graph_home_write_target_allowed as assert_graph_home_write_target_allowed,
)
from vault_graph.operation.scope.path_guard import assert_target_outside_vaults as assert_target_outside_vaults
from vault_graph.operation.scope.vault_catalog import VaultCatalog as VaultCatalog
from vault_graph.operation.scope.vault_catalog import VaultCatalogEntry as VaultCatalogEntry

sys.modules[__name__] = _implementation
