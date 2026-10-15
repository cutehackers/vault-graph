"""Compatibility import for :mod:`vault_graph.operation.readiness.search_readiness`."""

import sys
from dataclasses import dataclass as dataclass
from typing import Protocol as Protocol

from vault_graph.errors import SearchError as SearchError
from vault_graph.operation.readiness import search_readiness as _implementation
from vault_graph.operation.readiness.search_readiness import SearchReadiness as SearchReadiness
from vault_graph.operation.readiness.search_readiness import SearchReadinessReport as SearchReadinessReport
from vault_graph.operation.readiness.search_readiness import SearchScopeReadiness as SearchScopeReadiness
from vault_graph.operation.readiness.search_readiness import SearchStoreRevision as SearchStoreRevision
from vault_graph.operation.readiness.search_readiness import _require_revision_value as _require_revision_value
from vault_graph.operation.scope.vault_catalog import QueryScope as QueryScope
from vault_graph.storage.interfaces.store_health import StoreHealth as StoreHealth

sys.modules[__name__] = _implementation
