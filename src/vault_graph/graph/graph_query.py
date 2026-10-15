"""Compatibility import for :mod:`vault_graph.retrieval.graph.graph_query`."""

import sys
from dataclasses import dataclass as dataclass
from typing import Literal as Literal

from vault_graph.errors import GraphStoreError as GraphStoreError
from vault_graph.operation.scope.vault_catalog import QueryScope as QueryScope
from vault_graph.retrieval.graph import graph_query as _implementation
from vault_graph.retrieval.graph.graph_contracts import EntityRecord as EntityRecord
from vault_graph.retrieval.graph.graph_contracts import RelationshipRecord as RelationshipRecord
from vault_graph.retrieval.graph.graph_query import DEFAULT_GRAPH_ENTITY_SCAN_LIMIT as DEFAULT_GRAPH_ENTITY_SCAN_LIMIT
from vault_graph.retrieval.graph.graph_query import (
    DEFAULT_GRAPH_RELATIONSHIP_READ_LIMIT as DEFAULT_GRAPH_RELATIONSHIP_READ_LIMIT,
)
from vault_graph.retrieval.graph.graph_query import MAX_GRAPH_ENTITY_SCAN_LIMIT as MAX_GRAPH_ENTITY_SCAN_LIMIT
from vault_graph.retrieval.graph.graph_query import (
    MAX_GRAPH_RELATIONSHIP_READ_LIMIT as MAX_GRAPH_RELATIONSHIP_READ_LIMIT,
)
from vault_graph.retrieval.graph.graph_query import MAX_GRAPH_TARGET_CANDIDATE_LIMIT as MAX_GRAPH_TARGET_CANDIDATE_LIMIT
from vault_graph.retrieval.graph.graph_query import GraphEntityIdentity as GraphEntityIdentity
from vault_graph.retrieval.graph.graph_query import GraphEntityMatch as GraphEntityMatch
from vault_graph.retrieval.graph.graph_query import GraphEntityMatchKind as GraphEntityMatchKind
from vault_graph.retrieval.graph.graph_query import GraphEntityQuery as GraphEntityQuery
from vault_graph.retrieval.graph.graph_query import GraphEntityQueryResult as GraphEntityQueryResult
from vault_graph.retrieval.graph.graph_query import GraphRelationshipDirection as GraphRelationshipDirection
from vault_graph.retrieval.graph.graph_query import GraphRelationshipIdentity as GraphRelationshipIdentity
from vault_graph.retrieval.graph.graph_query import GraphRelationshipQuery as GraphRelationshipQuery
from vault_graph.retrieval.graph.graph_query import GraphRelationshipQueryResult as GraphRelationshipQueryResult
from vault_graph.retrieval.graph.graph_query import _require_actual_scopes as _require_actual_scopes

sys.modules[__name__] = _implementation
