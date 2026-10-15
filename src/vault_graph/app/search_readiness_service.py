"""Compatibility import for :mod:`vault_graph.projection_readiness.search_readiness_service`."""

import sys

from vault_graph.projection_readiness import search_readiness_service as _implementation
from vault_graph.projection_readiness.search_readiness_service import ReadOnlySearchReadiness as ReadOnlySearchReadiness

# Preserve historical module patch targets as well as class identities.
sys.modules[__name__] = _implementation
