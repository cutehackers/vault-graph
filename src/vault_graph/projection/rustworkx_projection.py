"""Compatibility import for :mod:`vault_graph.retrieval.graph.projection.rustworkx_projection`."""

import hashlib as hashlib
import json as json
import sys
from collections.abc import Iterable as Iterable

from vault_graph.retrieval.graph.projection import rustworkx_projection as _implementation
from vault_graph.retrieval.graph.projection.graph_projection import GRAPH_PROJECTION_VERSION as GRAPH_PROJECTION_VERSION
from vault_graph.retrieval.graph.projection.graph_projection import GraphPath as GraphPath
from vault_graph.retrieval.graph.projection.graph_projection import GraphProjectionEdge as GraphProjectionEdge
from vault_graph.retrieval.graph.projection.graph_projection import GraphProjectionInput as GraphProjectionInput
from vault_graph.retrieval.graph.projection.graph_projection import GraphProjectionNode as GraphProjectionNode
from vault_graph.retrieval.graph.projection.graph_projection import GraphProjectionResult as GraphProjectionResult
from vault_graph.retrieval.graph.projection.rustworkx_projection import DEPTH_WEIGHTS as DEPTH_WEIGHTS
from vault_graph.retrieval.graph.projection.rustworkx_projection import (
    RELATIONSHIP_TYPE_PRIORITY as RELATIONSHIP_TYPE_PRIORITY,
)
from vault_graph.retrieval.graph.projection.rustworkx_projection import STATUS_WEIGHTS as STATUS_WEIGHTS
from vault_graph.retrieval.graph.projection.rustworkx_projection import (
    RustworkxGraphProjection as RustworkxGraphProjection,
)
from vault_graph.retrieval.graph.projection.rustworkx_projection import _adjacent_edges as _adjacent_edges
from vault_graph.retrieval.graph.projection.rustworkx_projection import _dedupe_nodes as _dedupe_nodes
from vault_graph.retrieval.graph.projection.rustworkx_projection import _edge_allowed as _edge_allowed
from vault_graph.retrieval.graph.projection.rustworkx_projection import _edge_sort_key as _edge_sort_key
from vault_graph.retrieval.graph.projection.rustworkx_projection import _enumerate_paths as _enumerate_paths
from vault_graph.retrieval.graph.projection.rustworkx_projection import _explain_path as _explain_path
from vault_graph.retrieval.graph.projection.rustworkx_projection import _node_sort_key as _node_sort_key
from vault_graph.retrieval.graph.projection.rustworkx_projection import _path_sort_key as _path_sort_key
from vault_graph.retrieval.graph.projection.rustworkx_projection import _projection_build_id as _projection_build_id
from vault_graph.retrieval.graph.projection.rustworkx_projection import (
    _relationship_type_rank as _relationship_type_rank,
)
from vault_graph.retrieval.graph.projection.rustworkx_projection import _score_path as _score_path
from vault_graph.retrieval.graph.projection.rustworkx_projection import _walk_paths as _walk_paths

sys.modules[__name__] = _implementation
