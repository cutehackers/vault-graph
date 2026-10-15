"""Compatibility import for :mod:`vault_graph.operation.scope.catalog_query_scopes`."""

import sys

from vault_graph.operation.scope import catalog_query_scopes as _implementation
from vault_graph.operation.scope.catalog_query_scopes import _is_same_or_child as _is_same_or_child
from vault_graph.operation.scope.catalog_query_scopes import actual_query_scopes as actual_query_scopes
from vault_graph.operation.scope.vault_catalog import QueryScope as QueryScope
from vault_graph.operation.scope.vault_catalog import VaultCatalog as VaultCatalog

sys.modules[__name__] = _implementation
