"""Compatibility import for :mod:`vault_graph.operation.scope.catalog_service`."""

import sys

from vault_graph.operation.scope import catalog_service as _implementation
from vault_graph.operation.scope.catalog_service import CatalogService as CatalogService

sys.modules[__name__] = _implementation
