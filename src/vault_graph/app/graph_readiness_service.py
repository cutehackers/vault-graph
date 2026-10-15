"""Compatibility import for :mod:`vault_graph.operation.readiness.graph_readiness_service`."""

import sys

from vault_graph.operation.readiness import graph_readiness_service as _implementation
from vault_graph.operation.readiness.graph_readiness_service import ReadOnlyGraphReadiness as ReadOnlyGraphReadiness

sys.modules[__name__] = _implementation
