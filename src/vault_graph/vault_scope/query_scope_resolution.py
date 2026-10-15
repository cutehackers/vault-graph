"""Compatibility import for :mod:`vault_graph.operation.scope.query_scope_resolution`."""

import sys

from vault_graph.operation.scope import query_scope_resolution as _implementation
from vault_graph.operation.scope.catalog_query_scopes import actual_query_scopes as actual_query_scopes

sys.modules[__name__] = _implementation
