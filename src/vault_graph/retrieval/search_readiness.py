"""Compatibility import for :mod:`vault_graph.operation.readiness.search_readiness`."""

import sys

from vault_graph.operation.readiness import search_readiness as _implementation
from vault_graph.operation.readiness.search_readiness import SearchReadiness as SearchReadiness
from vault_graph.operation.readiness.search_readiness import SearchReadinessReport as SearchReadinessReport
from vault_graph.operation.readiness.search_readiness import SearchScopeReadiness as SearchScopeReadiness

sys.modules[__name__] = _implementation
