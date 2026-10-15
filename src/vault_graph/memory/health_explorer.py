"""Compatibility import for :mod:`vault_graph.operation.diagnostics.health_explorer`."""

import sys

from vault_graph.operation.diagnostics import health_explorer as _implementation
from vault_graph.operation.diagnostics.health_explorer import BackendReadinessRecord as BackendReadinessRecord
from vault_graph.operation.diagnostics.health_explorer import HealthBackendKind as HealthBackendKind
from vault_graph.operation.diagnostics.health_explorer import HealthExplorerReport as HealthExplorerReport
from vault_graph.operation.diagnostics.health_explorer import HealthExplorerService as HealthExplorerService
from vault_graph.operation.diagnostics.health_explorer import McpRuntimeCacheRecord as McpRuntimeCacheRecord
from vault_graph.operation.diagnostics.health_explorer import ReadinessStatus as ReadinessStatus
from vault_graph.operation.diagnostics.health_explorer import ScaleUpAdapterReadiness as ScaleUpAdapterReadiness

sys.modules[__name__] = _implementation
