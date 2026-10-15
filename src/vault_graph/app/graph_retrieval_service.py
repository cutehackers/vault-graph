"""Compatibility import for :mod:`vault_graph.retrieval.graph.graph_retrieval_service`."""

import sys

from vault_graph.retrieval.graph import graph_retrieval_service as _implementation
from vault_graph.retrieval.graph.graph_retrieval_service import GraphReadinessChecker as GraphReadinessChecker
from vault_graph.retrieval.graph.graph_retrieval_service import GraphRetrievalService as GraphRetrievalService

sys.modules[__name__] = _implementation
