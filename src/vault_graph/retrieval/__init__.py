"""retrieval features and lazy legacy exports."""

from importlib import import_module
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from vault_graph.operation.readiness.search_readiness import SearchReadiness as SearchReadiness
    from vault_graph.operation.readiness.search_readiness import SearchReadinessReport as SearchReadinessReport
    from vault_graph.operation.readiness.search_readiness import SearchScopeReadiness as SearchScopeReadiness
    from vault_graph.retrieval.graph.graph_retrieval import DecisionTraceResponse as DecisionTraceResponse
    from vault_graph.retrieval.graph.graph_retrieval import DecisionTraceStep as DecisionTraceStep
    from vault_graph.retrieval.graph.graph_retrieval import GraphOutputFormat as GraphOutputFormat
    from vault_graph.retrieval.graph.graph_retrieval import GraphRetrievalRevision as GraphRetrievalRevision
    from vault_graph.retrieval.graph.graph_retrieval import GraphRetrievalWarning as GraphRetrievalWarning
    from vault_graph.retrieval.graph.graph_retrieval import GraphWarningSeverity as GraphWarningSeverity
    from vault_graph.retrieval.graph.graph_retrieval import RelatedItem as RelatedItem
    from vault_graph.retrieval.graph.graph_retrieval import RelatedRequest as RelatedRequest
    from vault_graph.retrieval.graph.graph_retrieval import RelatedResponse as RelatedResponse
    from vault_graph.retrieval.search.context_expansion import CONTEXT_POLICY_VERSION as CONTEXT_POLICY_VERSION
    from vault_graph.retrieval.search.context_expansion import ContextExpander as ContextExpander
    from vault_graph.retrieval.search.context_expansion import ContextExpansion as ContextExpansion
    from vault_graph.retrieval.search.graph_candidates import GraphCandidateProvider as GraphCandidateProvider
    from vault_graph.retrieval.search.graph_candidates import GraphCandidateResult as GraphCandidateResult
    from vault_graph.retrieval.search.graph_candidates import (
        GraphSearchCandidateProvider as GraphSearchCandidateProvider,
    )
    from vault_graph.retrieval.search.retrieval_candidate import RetrievalCandidate as RetrievalCandidate
    from vault_graph.retrieval.search.retrieval_result import RelationshipStatus as RelationshipStatus
    from vault_graph.retrieval.search.retrieval_result import RetrievalResult as RetrievalResult
    from vault_graph.retrieval.search.retrieval_result import RetrievalSeverity as RetrievalSeverity
    from vault_graph.retrieval.search.retrieval_result import RetrievalSignal as RetrievalSignal
    from vault_graph.retrieval.search.retrieval_result import RetrievalSignalKind as RetrievalSignalKind
    from vault_graph.retrieval.search.retrieval_result import RetrievalWarning as RetrievalWarning
    from vault_graph.retrieval.search.retrieval_result import StoreRevision as StoreRevision
    from vault_graph.retrieval.search.retrieval_result import (
        require_vector_hit_evidence_match as require_vector_hit_evidence_match,
    )
    from vault_graph.retrieval.search.retrieval_result import (
        warning_for_missing_vector_evidence as warning_for_missing_vector_evidence,
    )
    from vault_graph.retrieval.search.retrieval_result import warning_for_stale_vector as warning_for_stale_vector
    from vault_graph.retrieval.search.retrieval_service import RetrievalService as RetrievalService
    from vault_graph.retrieval.search.search_response import SearchOutputFormat as SearchOutputFormat
    from vault_graph.retrieval.search.search_response import SearchRequest as SearchRequest
    from vault_graph.retrieval.search.search_response import SearchResponse as SearchResponse
    from vault_graph.retrieval.search.search_response import SearchStoreRevision as SearchStoreRevision
    from vault_graph.retrieval.search.search_response import SearchWarning as SearchWarning

__all__ = [
    "CONTEXT_POLICY_VERSION",
    "ContextExpansion",
    "ContextExpander",
    "DecisionTraceResponse",
    "DecisionTraceStep",
    "GraphCandidateProvider",
    "GraphCandidateResult",
    "GraphSearchCandidateProvider",
    "GraphOutputFormat",
    "GraphRetrievalRevision",
    "GraphRetrievalWarning",
    "GraphWarningSeverity",
    "RelationshipStatus",
    "RelatedItem",
    "RelatedRequest",
    "RelatedResponse",
    "RetrievalCandidate",
    "RetrievalResult",
    "RetrievalSeverity",
    "RetrievalSignal",
    "RetrievalSignalKind",
    "RetrievalWarning",
    "RetrievalService",
    "SearchReadiness",
    "SearchReadinessReport",
    "SearchScopeReadiness",
    "SearchOutputFormat",
    "SearchRequest",
    "SearchResponse",
    "SearchStoreRevision",
    "SearchWarning",
    "StoreRevision",
    "require_vector_hit_evidence_match",
    "warning_for_missing_vector_evidence",
    "warning_for_stale_vector",
]

_EXPORTS = {
    "SearchReadiness": ("vault_graph.operation.readiness.search_readiness", "SearchReadiness"),
    "SearchReadinessReport": ("vault_graph.operation.readiness.search_readiness", "SearchReadinessReport"),
    "SearchScopeReadiness": ("vault_graph.operation.readiness.search_readiness", "SearchScopeReadiness"),
    "CONTEXT_POLICY_VERSION": ("vault_graph.retrieval.search.context_expansion", "CONTEXT_POLICY_VERSION"),
    "ContextExpander": ("vault_graph.retrieval.search.context_expansion", "ContextExpander"),
    "ContextExpansion": ("vault_graph.retrieval.search.context_expansion", "ContextExpansion"),
    "GraphCandidateProvider": ("vault_graph.retrieval.search.graph_candidates", "GraphCandidateProvider"),
    "GraphCandidateResult": ("vault_graph.retrieval.search.graph_candidates", "GraphCandidateResult"),
    "GraphSearchCandidateProvider": ("vault_graph.retrieval.search.graph_candidates", "GraphSearchCandidateProvider"),
    "DecisionTraceResponse": ("vault_graph.retrieval.graph.graph_retrieval", "DecisionTraceResponse"),
    "DecisionTraceStep": ("vault_graph.retrieval.graph.graph_retrieval", "DecisionTraceStep"),
    "GraphOutputFormat": ("vault_graph.retrieval.graph.graph_retrieval", "GraphOutputFormat"),
    "GraphRetrievalRevision": ("vault_graph.retrieval.graph.graph_retrieval", "GraphRetrievalRevision"),
    "GraphRetrievalWarning": ("vault_graph.retrieval.graph.graph_retrieval", "GraphRetrievalWarning"),
    "GraphWarningSeverity": ("vault_graph.retrieval.graph.graph_retrieval", "GraphWarningSeverity"),
    "RelatedItem": ("vault_graph.retrieval.graph.graph_retrieval", "RelatedItem"),
    "RelatedRequest": ("vault_graph.retrieval.graph.graph_retrieval", "RelatedRequest"),
    "RelatedResponse": ("vault_graph.retrieval.graph.graph_retrieval", "RelatedResponse"),
    "RetrievalCandidate": ("vault_graph.retrieval.search.retrieval_candidate", "RetrievalCandidate"),
    "RelationshipStatus": ("vault_graph.retrieval.search.retrieval_result", "RelationshipStatus"),
    "RetrievalResult": ("vault_graph.retrieval.search.retrieval_result", "RetrievalResult"),
    "RetrievalSeverity": ("vault_graph.retrieval.search.retrieval_result", "RetrievalSeverity"),
    "RetrievalSignal": ("vault_graph.retrieval.search.retrieval_result", "RetrievalSignal"),
    "RetrievalSignalKind": ("vault_graph.retrieval.search.retrieval_result", "RetrievalSignalKind"),
    "RetrievalWarning": ("vault_graph.retrieval.search.retrieval_result", "RetrievalWarning"),
    "StoreRevision": ("vault_graph.retrieval.search.retrieval_result", "StoreRevision"),
    "require_vector_hit_evidence_match": (
        "vault_graph.retrieval.search.retrieval_result",
        "require_vector_hit_evidence_match",
    ),
    "warning_for_missing_vector_evidence": (
        "vault_graph.retrieval.search.retrieval_result",
        "warning_for_missing_vector_evidence",
    ),
    "warning_for_stale_vector": ("vault_graph.retrieval.search.retrieval_result", "warning_for_stale_vector"),
    "RetrievalService": ("vault_graph.retrieval.search.retrieval_service", "RetrievalService"),
    "SearchOutputFormat": ("vault_graph.retrieval.search.search_response", "SearchOutputFormat"),
    "SearchRequest": ("vault_graph.retrieval.search.search_response", "SearchRequest"),
    "SearchResponse": ("vault_graph.retrieval.search.search_response", "SearchResponse"),
    "SearchStoreRevision": ("vault_graph.retrieval.search.search_response", "SearchStoreRevision"),
    "SearchWarning": ("vault_graph.retrieval.search.search_response", "SearchWarning"),
}


def __getattr__(name: str) -> Any:
    if name not in _EXPORTS:
        raise AttributeError(name)
    module, symbol = _EXPORTS[name]
    return getattr(import_module(module), symbol)


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(__all__))
