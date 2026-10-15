"""Compatibility import for :mod:`vault_graph.retrieval.graph.projection.graph_projection`."""

import sys
from dataclasses import dataclass as dataclass
from typing import Literal as Literal
from typing import Protocol as Protocol

from vault_graph.errors import GraphStoreError as GraphStoreError
from vault_graph.retrieval.graph.projection import graph_projection as _implementation
from vault_graph.retrieval.graph.projection.graph_projection import (
    DEFAULT_GRAPH_PROJECTION_EDGE_LIMIT as DEFAULT_GRAPH_PROJECTION_EDGE_LIMIT,
)
from vault_graph.retrieval.graph.projection.graph_projection import (
    DEFAULT_GRAPH_RELATED_DEPTH as DEFAULT_GRAPH_RELATED_DEPTH,
)
from vault_graph.retrieval.graph.projection.graph_projection import (
    DEFAULT_GRAPH_RELATIONSHIP_READ_LIMIT as DEFAULT_GRAPH_RELATIONSHIP_READ_LIMIT,
)
from vault_graph.retrieval.graph.projection.graph_projection import (
    DEFAULT_GRAPH_RESULT_LIMIT as DEFAULT_GRAPH_RESULT_LIMIT,
)
from vault_graph.retrieval.graph.projection.graph_projection import (
    DEFAULT_GRAPH_TARGET_LIMIT as DEFAULT_GRAPH_TARGET_LIMIT,
)
from vault_graph.retrieval.graph.projection.graph_projection import GRAPH_PROJECTION_VERSION as GRAPH_PROJECTION_VERSION
from vault_graph.retrieval.graph.projection.graph_projection import (
    MAX_GRAPH_PROJECTION_DEPTH as MAX_GRAPH_PROJECTION_DEPTH,
)
from vault_graph.retrieval.graph.projection.graph_projection import (
    MAX_GRAPH_PROJECTION_EDGE_LIMIT as MAX_GRAPH_PROJECTION_EDGE_LIMIT,
)
from vault_graph.retrieval.graph.projection.graph_projection import MAX_GRAPH_RESULT_LIMIT as MAX_GRAPH_RESULT_LIMIT
from vault_graph.retrieval.graph.projection.graph_projection import GraphPath as GraphPath
from vault_graph.retrieval.graph.projection.graph_projection import GraphProjection as GraphProjection
from vault_graph.retrieval.graph.projection.graph_projection import GraphProjectionDirection as GraphProjectionDirection
from vault_graph.retrieval.graph.projection.graph_projection import GraphProjectionEdge as GraphProjectionEdge
from vault_graph.retrieval.graph.projection.graph_projection import GraphProjectionInput as GraphProjectionInput
from vault_graph.retrieval.graph.projection.graph_projection import GraphProjectionNode as GraphProjectionNode
from vault_graph.retrieval.graph.projection.graph_projection import GraphProjectionResult as GraphProjectionResult

sys.modules[__name__] = _implementation
