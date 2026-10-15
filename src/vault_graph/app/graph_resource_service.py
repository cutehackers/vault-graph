"""Compatibility import for :mod:`vault_graph.graph_retrieval.graph_resource_service`."""

import sys

from vault_graph.graph_retrieval import graph_resource_service as _implementation
from vault_graph.graph_retrieval.graph_resource_service import GraphEntityResource as GraphEntityResource
from vault_graph.graph_retrieval.graph_resource_service import GraphResourceService as GraphResourceService
from vault_graph.graph_retrieval.graph_resource_service import GraphResourceWarning as GraphResourceWarning

sys.modules[__name__] = _implementation
