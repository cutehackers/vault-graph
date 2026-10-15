"""Compatibility import for :mod:`vault_graph.retrieval.graph.graph_readiness`."""

import sys
from dataclasses import dataclass as dataclass

from vault_graph.operation.scope.vault_catalog import QueryScope as QueryScope
from vault_graph.retrieval.graph import graph_readiness as _implementation
from vault_graph.retrieval.graph.graph_readiness import GRAPH_FRESHNESS_VALUES as GRAPH_FRESHNESS_VALUES
from vault_graph.retrieval.graph.graph_readiness import GraphLineageScope as GraphLineageScope
from vault_graph.retrieval.graph.graph_readiness import GraphLineageSnapshot as GraphLineageSnapshot
from vault_graph.retrieval.graph.graph_readiness import GraphReadiness as GraphReadiness
from vault_graph.retrieval.graph.graph_readiness import GraphScopeReadiness as GraphScopeReadiness

sys.modules[__name__] = _implementation
