"""Compatibility import for :mod:`vault_graph.retrieval.graph.graph_retrieval`."""

import sys
from dataclasses import dataclass as dataclass
from typing import Literal as Literal

from vault_graph.errors import SearchError as SearchError
from vault_graph.operation.scope.vault_catalog import QueryScope as QueryScope
from vault_graph.retrieval.graph import graph_retrieval as _implementation
from vault_graph.retrieval.graph.graph_contracts import EntityRecord as EntityRecord
from vault_graph.retrieval.graph.graph_contracts import RelationshipRecord as RelationshipRecord
from vault_graph.retrieval.graph.graph_retrieval import DecisionTraceResponse as DecisionTraceResponse
from vault_graph.retrieval.graph.graph_retrieval import DecisionTraceStep as DecisionTraceStep
from vault_graph.retrieval.graph.graph_retrieval import GraphOutputFormat as GraphOutputFormat
from vault_graph.retrieval.graph.graph_retrieval import GraphRetrievalRevision as GraphRetrievalRevision
from vault_graph.retrieval.graph.graph_retrieval import GraphRetrievalWarning as GraphRetrievalWarning
from vault_graph.retrieval.graph.graph_retrieval import GraphWarningSeverity as GraphWarningSeverity
from vault_graph.retrieval.graph.graph_retrieval import RelatedItem as RelatedItem
from vault_graph.retrieval.graph.graph_retrieval import RelatedRequest as RelatedRequest
from vault_graph.retrieval.graph.graph_retrieval import RelatedResponse as RelatedResponse
from vault_graph.retrieval.graph.graph_retrieval import _require_non_empty as _require_non_empty
from vault_graph.retrieval.graph.projection.graph_projection import GRAPH_PROJECTION_VERSION as GRAPH_PROJECTION_VERSION
from vault_graph.storage.interfaces.metadata_store import EvidenceReference as EvidenceReference

sys.modules[__name__] = _implementation
