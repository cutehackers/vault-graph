"""Compatibility import for :mod:`vault_graph.interface.composition.query_scope_resolution`."""

import sys

from vault_graph.interface.composition import query_scope_resolution as _implementation
from vault_graph.operation.scope.query_scope_resolution import actual_query_scopes as actual_query_scopes

sys.modules[__name__] = _implementation
