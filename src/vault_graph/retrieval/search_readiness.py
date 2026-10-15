"""Compatibility import for :mod:`vault_graph.projection_readiness.search_readiness`."""

import sys

from vault_graph.projection_readiness import search_readiness as _implementation
from vault_graph.projection_readiness.search_readiness import SearchReadiness as SearchReadiness
from vault_graph.projection_readiness.search_readiness import SearchReadinessReport as SearchReadinessReport
from vault_graph.projection_readiness.search_readiness import SearchScopeReadiness as SearchScopeReadiness

# Preserve historical module patch targets as well as class identities.
sys.modules[__name__] = _implementation
