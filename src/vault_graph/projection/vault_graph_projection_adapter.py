"""Compatibility import for :mod:`vault_graph.retrieval.graph.projection.vault_graph_projection_adapter`."""

import sys
from dataclasses import dataclass as dataclass
from typing import Literal as Literal

from graph_search import Edge as Edge
from graph_search import GraphLimits as GraphLimits
from graph_search import GraphSearchError as GraphSearchError
from graph_search import GraphSnapshot as GraphSnapshot
from graph_search import PathOptions as PathOptions
from graph_search import search_paths as search_paths

from vault_graph.errors import GraphStoreError as GraphStoreError
from vault_graph.retrieval.graph.projection import vault_graph_projection_adapter as _implementation
from vault_graph.retrieval.graph.projection.graph_projection import GRAPH_PROJECTION_VERSION as GRAPH_PROJECTION_VERSION
from vault_graph.retrieval.graph.projection.graph_projection import GraphPath as GraphPath
from vault_graph.retrieval.graph.projection.graph_projection import GraphProjectionEdge as GraphProjectionEdge
from vault_graph.retrieval.graph.projection.graph_projection import GraphProjectionInput as GraphProjectionInput
from vault_graph.retrieval.graph.projection.graph_projection import GraphProjectionResult as GraphProjectionResult
from vault_graph.retrieval.graph.projection.rustworkx_projection import _dedupe_nodes as _dedupe_nodes
from vault_graph.retrieval.graph.projection.rustworkx_projection import _edge_allowed as _edge_allowed
from vault_graph.retrieval.graph.projection.rustworkx_projection import _edge_sort_key as _edge_sort_key
from vault_graph.retrieval.graph.projection.rustworkx_projection import _explain_path as _explain_path
from vault_graph.retrieval.graph.projection.rustworkx_projection import _node_sort_key as _node_sort_key
from vault_graph.retrieval.graph.projection.rustworkx_projection import _path_sort_key as _path_sort_key
from vault_graph.retrieval.graph.projection.rustworkx_projection import _projection_build_id as _projection_build_id
from vault_graph.retrieval.graph.projection.rustworkx_projection import _score_path as _score_path
from vault_graph.retrieval.graph.projection.vault_graph_projection_adapter import Identity as Identity
from vault_graph.retrieval.graph.projection.vault_graph_projection_adapter import LegacyPathKey as LegacyPathKey
from vault_graph.retrieval.graph.projection.vault_graph_projection_adapter import (
    ProjectionExecutionLimits as ProjectionExecutionLimits,
)
from vault_graph.retrieval.graph.projection.vault_graph_projection_adapter import (
    VaultGraphProjectionAdapter as VaultGraphProjectionAdapter,
)
from vault_graph.retrieval.graph.projection.vault_graph_projection_adapter import _admit_input as _admit_input
from vault_graph.retrieval.graph.projection.vault_graph_projection_adapter import _count_identifier as _count_identifier
from vault_graph.retrieval.graph.projection.vault_graph_projection_adapter import (
    _legacy_neighbor_ranks as _legacy_neighbor_ranks,
)

sys.modules[__name__] = _implementation
