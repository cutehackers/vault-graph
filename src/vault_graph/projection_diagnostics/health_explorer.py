"""Compatibility import for :mod:`vault_graph.operation.diagnostics.health_explorer`."""

import sys
from collections.abc import Callable as Callable
from dataclasses import dataclass as dataclass
from datetime import UTC as UTC
from datetime import datetime as datetime
from typing import TYPE_CHECKING as TYPE_CHECKING
from typing import Literal as Literal

from vault_graph.context.memory.memory_models import MemoryWarning as MemoryWarning
from vault_graph.context.memory.memory_models import MemoryWarningSeverity as MemoryWarningSeverity
from vault_graph.context.memory.memory_request_context import MemoryStatusService as MemoryStatusService
from vault_graph.operation.diagnostics import health_explorer as _implementation
from vault_graph.operation.diagnostics.health_explorer import BackendReadinessRecord as BackendReadinessRecord
from vault_graph.operation.diagnostics.health_explorer import HealthBackendKind as HealthBackendKind
from vault_graph.operation.diagnostics.health_explorer import HealthExplorerReport as HealthExplorerReport
from vault_graph.operation.diagnostics.health_explorer import HealthExplorerService as HealthExplorerService
from vault_graph.operation.diagnostics.health_explorer import McpRuntimeCacheRecord as McpRuntimeCacheRecord
from vault_graph.operation.diagnostics.health_explorer import ReadinessStatus as ReadinessStatus
from vault_graph.operation.diagnostics.health_explorer import ScaleUpAdapterReadiness as ScaleUpAdapterReadiness
from vault_graph.operation.diagnostics.health_explorer import _adapter_record as _adapter_record
from vault_graph.operation.diagnostics.health_explorer import _backend_records as _backend_records
from vault_graph.operation.diagnostics.health_explorer import _scale_up_records as _scale_up_records
from vault_graph.operation.diagnostics.health_explorer import _scope_key as _scope_key
from vault_graph.operation.diagnostics.health_explorer import _utc_now as _utc_now
from vault_graph.operation.diagnostics.health_explorer import _warning as _warning
from vault_graph.operation.scope.catalog_query_scopes import actual_query_scopes as actual_query_scopes
from vault_graph.operation.scope.vault_catalog import QueryScope as QueryScope
from vault_graph.operation.scope.vault_catalog import VaultCatalog as VaultCatalog

sys.modules[__name__] = _implementation
