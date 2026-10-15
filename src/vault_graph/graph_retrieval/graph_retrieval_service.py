"""Compatibility import for :mod:`vault_graph.retrieval.graph.graph_retrieval_service`."""

import sys
from collections.abc import Iterable as Iterable
from dataclasses import dataclass as dataclass
from dataclasses import replace as replace
from datetime import UTC as UTC
from datetime import datetime as datetime
from typing import Literal as Literal
from typing import Protocol as Protocol
from typing import cast as cast

from vault_graph.errors import GraphStoreError as GraphStoreError
from vault_graph.errors import SearchError as SearchError
from vault_graph.operation.scope.catalog_query_scopes import actual_query_scopes as actual_query_scopes
from vault_graph.operation.scope.vault_catalog import QueryScope as QueryScope
from vault_graph.operation.scope.vault_catalog import VaultCatalog as VaultCatalog
from vault_graph.retrieval.evidence.evidence_linking import EvidenceLinker as EvidenceLinker
from vault_graph.retrieval.graph import graph_retrieval_service as _implementation
from vault_graph.retrieval.graph.graph_contracts import EntityRecord as EntityRecord
from vault_graph.retrieval.graph.graph_contracts import GraphEvidenceRef as GraphEvidenceRef
from vault_graph.retrieval.graph.graph_contracts import RelationshipRecord as RelationshipRecord
from vault_graph.retrieval.graph.graph_identity import graph_scope_key as graph_scope_key
from vault_graph.retrieval.graph.graph_query import GraphEntityIdentity as GraphEntityIdentity
from vault_graph.retrieval.graph.graph_query import GraphEntityMatch as GraphEntityMatch
from vault_graph.retrieval.graph.graph_query import GraphEntityQuery as GraphEntityQuery
from vault_graph.retrieval.graph.graph_query import GraphRelationshipQuery as GraphRelationshipQuery
from vault_graph.retrieval.graph.graph_readiness import GraphReadiness as GraphReadiness
from vault_graph.retrieval.graph.graph_retrieval import DecisionTraceResponse as DecisionTraceResponse
from vault_graph.retrieval.graph.graph_retrieval import DecisionTraceStep as DecisionTraceStep
from vault_graph.retrieval.graph.graph_retrieval import GraphOutputFormat as GraphOutputFormat
from vault_graph.retrieval.graph.graph_retrieval import GraphRetrievalRevision as GraphRetrievalRevision
from vault_graph.retrieval.graph.graph_retrieval import GraphRetrievalWarning as GraphRetrievalWarning
from vault_graph.retrieval.graph.graph_retrieval import RelatedItem as RelatedItem
from vault_graph.retrieval.graph.graph_retrieval import RelatedResponse as RelatedResponse
from vault_graph.retrieval.graph.graph_retrieval_service import (
    GRAPH_RELATIONSHIP_READ_LIMIT as GRAPH_RELATIONSHIP_READ_LIMIT,
)
from vault_graph.retrieval.graph.graph_retrieval_service import GRAPH_TARGET_LIMIT as GRAPH_TARGET_LIMIT
from vault_graph.retrieval.graph.graph_retrieval_service import GraphReadinessChecker as GraphReadinessChecker
from vault_graph.retrieval.graph.graph_retrieval_service import GraphRetrievalService as GraphRetrievalService
from vault_graph.retrieval.graph.graph_retrieval_service import _actual_scopes as _actual_scopes
from vault_graph.retrieval.graph.graph_retrieval_service import _affected_vault_ids as _affected_vault_ids
from vault_graph.retrieval.graph.graph_retrieval_service import (
    _affected_vault_ids_for_request as _affected_vault_ids_for_request,
)
from vault_graph.retrieval.graph.graph_retrieval_service import _candidate_vault_ids as _candidate_vault_ids
from vault_graph.retrieval.graph.graph_retrieval_service import (
    _decision_trace_step_from_path as _decision_trace_step_from_path,
)
from vault_graph.retrieval.graph.graph_retrieval_service import _dedupe_evidence as _dedupe_evidence
from vault_graph.retrieval.graph.graph_retrieval_service import (
    _empty_decision_trace_response as _empty_decision_trace_response,
)
from vault_graph.retrieval.graph.graph_retrieval_service import _empty_related_response as _empty_related_response
from vault_graph.retrieval.graph.graph_retrieval_service import _entity_type_priority as _entity_type_priority
from vault_graph.retrieval.graph.graph_retrieval_service import (
    _fresh_scopes_with_warnings as _fresh_scopes_with_warnings,
)
from vault_graph.retrieval.graph.graph_retrieval_service import (
    _initial_decision_trace_step as _initial_decision_trace_step,
)
from vault_graph.retrieval.graph.graph_retrieval_service import _is_decision_entity as _is_decision_entity
from vault_graph.retrieval.graph.graph_retrieval_service import _path_relationship_status as _path_relationship_status
from vault_graph.retrieval.graph.graph_retrieval_service import _path_role as _path_role
from vault_graph.retrieval.graph.graph_retrieval_service import _projection_direction as _projection_direction
from vault_graph.retrieval.graph.graph_retrieval_service import _projection_edge as _projection_edge
from vault_graph.retrieval.graph.graph_retrieval_service import _projection_node as _projection_node
from vault_graph.retrieval.graph.graph_retrieval_service import _raise_fatal_readiness as _raise_fatal_readiness
from vault_graph.retrieval.graph.graph_retrieval_service import _relationship_endpoints as _relationship_endpoints
from vault_graph.retrieval.graph.graph_retrieval_service import (
    _relationship_role_priority as _relationship_role_priority,
)
from vault_graph.retrieval.graph.graph_retrieval_service import (
    _relationship_status_weight as _relationship_status_weight,
)
from vault_graph.retrieval.graph.graph_retrieval_service import _resolve_decision_target as _resolve_decision_target
from vault_graph.retrieval.graph.graph_retrieval_service import _resolve_graph_evidence as _resolve_graph_evidence
from vault_graph.retrieval.graph.graph_retrieval_service import _resolve_target as _resolve_target
from vault_graph.retrieval.graph.graph_retrieval_service import (
    _search_candidates_from_related as _search_candidates_from_related,
)
from vault_graph.retrieval.graph.graph_retrieval_service import (
    _search_revision_from_graph_revision as _search_revision_from_graph_revision,
)
from vault_graph.retrieval.graph.graph_retrieval_service import _search_warning_code as _search_warning_code
from vault_graph.retrieval.graph.graph_retrieval_service import (
    _search_warning_from_graph_warning as _search_warning_from_graph_warning,
)
from vault_graph.retrieval.graph.graph_retrieval_service import _store_revisions as _store_revisions
from vault_graph.retrieval.graph.graph_retrieval_service import _TargetResolution as _TargetResolution
from vault_graph.retrieval.graph.graph_retrieval_service import _TraversalResult as _TraversalResult
from vault_graph.retrieval.graph.projection.graph_projection import (
    DEFAULT_GRAPH_PROJECTION_EDGE_LIMIT as DEFAULT_GRAPH_PROJECTION_EDGE_LIMIT,
)
from vault_graph.retrieval.graph.projection.graph_projection import GRAPH_PROJECTION_VERSION as GRAPH_PROJECTION_VERSION
from vault_graph.retrieval.graph.projection.graph_projection import (
    MAX_GRAPH_PROJECTION_DEPTH as MAX_GRAPH_PROJECTION_DEPTH,
)
from vault_graph.retrieval.graph.projection.graph_projection import GraphPath as GraphPath
from vault_graph.retrieval.graph.projection.graph_projection import GraphProjection as GraphProjection
from vault_graph.retrieval.graph.projection.graph_projection import GraphProjectionEdge as GraphProjectionEdge
from vault_graph.retrieval.graph.projection.graph_projection import GraphProjectionInput as GraphProjectionInput
from vault_graph.retrieval.graph.projection.graph_projection import GraphProjectionNode as GraphProjectionNode
from vault_graph.retrieval.search.graph_candidates import GraphCandidateResult as GraphCandidateResult
from vault_graph.retrieval.search.retrieval_candidate import RetrievalCandidate as RetrievalCandidate
from vault_graph.retrieval.search.retrieval_result import RetrievalSignal as RetrievalSignal
from vault_graph.retrieval.search.search_response import SearchStoreRevision as SearchStoreRevision
from vault_graph.retrieval.search.search_response import SearchWarning as SearchWarning
from vault_graph.storage.interfaces.graph_store import GraphStore as GraphStore
from vault_graph.storage.interfaces.metadata_store import EvidenceReference as EvidenceReference
from vault_graph.storage.interfaces.metadata_store import MetadataStore as MetadataStore

sys.modules[__name__] = _implementation
