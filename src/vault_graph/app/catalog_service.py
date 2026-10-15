"""Compatibility import for :mod:`vault_graph.vault_scope.catalog_service`."""

import sys

from vault_graph.vault_scope import catalog_service as _implementation
from vault_graph.vault_scope.catalog_service import CatalogService as CatalogService

# Preserve historical module patch targets as well as class identities.
sys.modules[__name__] = _implementation
