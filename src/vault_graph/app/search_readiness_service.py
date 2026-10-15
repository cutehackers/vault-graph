"""Compatibility import for :mod:`vault_graph.operation.readiness.search_readiness_service`."""

import sys

from vault_graph.operation.readiness import search_readiness_service as _implementation
from vault_graph.operation.readiness.search_readiness_service import ReadOnlySearchReadiness as ReadOnlySearchReadiness

sys.modules[__name__] = _implementation
