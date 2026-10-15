"""Compatibility import for :mod:`vault_graph.interface.http.http_explanation_serialization`."""

import hashlib as hashlib
import json as json
import sys
from dataclasses import fields as fields
from dataclasses import is_dataclass as is_dataclass
from urllib.parse import quote as quote

from vault_graph.context.answer.answer_response import AnswerEvidence as AnswerEvidence
from vault_graph.context.answer.answer_response import AnswerResponse as AnswerResponse
from vault_graph.context.answer.answer_response import AnswerSignal as AnswerSignal
from vault_graph.context.answer.answer_response import AnswerWarning as AnswerWarning
from vault_graph.context.pack.context_pack import ContextEvidence as ContextEvidence
from vault_graph.context.pack.context_pack import ContextPack as ContextPack
from vault_graph.context.pack.context_pack import ContextPackSignal as ContextPackSignal
from vault_graph.context.pack.context_pack import ContextPackWarning as ContextPackWarning
from vault_graph.interface.http import http_explanation_serialization as _implementation
from vault_graph.interface.http.http_explanation_serialization import (
    _context_warning_matches_item as _context_warning_matches_item,
)
from vault_graph.interface.http.http_explanation_serialization import (
    _decision_trace_result_id as _decision_trace_result_id,
)
from vault_graph.interface.http.http_explanation_serialization import _dedupe_dicts as _dedupe_dicts
from vault_graph.interface.http.http_explanation_serialization import _encode as _encode
from vault_graph.interface.http.http_explanation_serialization import (
    _evidence_ref_from_answer as _evidence_ref_from_answer,
)
from vault_graph.interface.http.http_explanation_serialization import (
    _evidence_ref_from_context as _evidence_ref_from_context,
)
from vault_graph.interface.http.http_explanation_serialization import (
    _evidence_ref_from_metadata as _evidence_ref_from_metadata,
)
from vault_graph.interface.http.http_explanation_serialization import (
    _graph_warning_matches_item as _graph_warning_matches_item,
)
from vault_graph.interface.http.http_explanation_serialization import _json_object as _json_object
from vault_graph.interface.http.http_explanation_serialization import _json_safe as _json_safe
from vault_graph.interface.http.http_explanation_serialization import _json_value as _json_value
from vault_graph.interface.http.http_explanation_serialization import (
    _links_for_answer_evidence as _links_for_answer_evidence,
)
from vault_graph.interface.http.http_explanation_serialization import (
    _links_for_context_evidence as _links_for_context_evidence,
)
from vault_graph.interface.http.http_explanation_serialization import _links_for_evidence as _links_for_evidence
from vault_graph.interface.http.http_explanation_serialization import _links_for_graph_entity as _links_for_graph_entity
from vault_graph.interface.http.http_explanation_serialization import _links_for_path as _links_for_path
from vault_graph.interface.http.http_explanation_serialization import _links_to_dicts as _links_to_dicts
from vault_graph.interface.http.http_explanation_serialization import _related_result_id as _related_result_id
from vault_graph.interface.http.http_explanation_serialization import (
    _relationship_status_for_path as _relationship_status_for_path,
)
from vault_graph.interface.http.http_explanation_serialization import _runtime_result_id as _runtime_result_id
from vault_graph.interface.http.http_explanation_serialization import (
    _search_store_revision_to_dict as _search_store_revision_to_dict,
)
from vault_graph.interface.http.http_explanation_serialization import (
    _search_warning_matches_result as _search_warning_matches_result,
)
from vault_graph.interface.http.http_explanation_serialization import _signal_from_answer as _signal_from_answer
from vault_graph.interface.http.http_explanation_serialization import _signal_from_context as _signal_from_context
from vault_graph.interface.http.http_explanation_serialization import _signal_from_retrieval as _signal_from_retrieval
from vault_graph.interface.http.http_explanation_serialization import (
    _store_revision_dicts_for_search as _store_revision_dicts_for_search,
)
from vault_graph.interface.http.http_explanation_serialization import _store_revision_to_dict as _store_revision_to_dict
from vault_graph.interface.http.http_explanation_serialization import _warning_from_answer as _warning_from_answer
from vault_graph.interface.http.http_explanation_serialization import _warning_from_context as _warning_from_context
from vault_graph.interface.http.http_explanation_serialization import _warning_from_graph as _warning_from_graph
from vault_graph.interface.http.http_explanation_serialization import _warning_from_retrieval as _warning_from_retrieval
from vault_graph.interface.http.http_explanation_serialization import _warning_from_search as _warning_from_search
from vault_graph.interface.http.http_explanation_serialization import (
    explanation_records_for_answer as explanation_records_for_answer,
)
from vault_graph.interface.http.http_explanation_serialization import (
    explanation_records_for_context_pack as explanation_records_for_context_pack,
)
from vault_graph.interface.http.http_explanation_serialization import (
    explanation_records_for_decision_trace as explanation_records_for_decision_trace,
)
from vault_graph.interface.http.http_explanation_serialization import (
    explanation_records_for_related as explanation_records_for_related,
)
from vault_graph.interface.http.http_explanation_serialization import (
    explanation_records_for_search as explanation_records_for_search,
)
from vault_graph.retrieval.explanation.result_explanation import ExplanationEvidenceRef as ExplanationEvidenceRef
from vault_graph.retrieval.explanation.result_explanation import ExplanationRecord as ExplanationRecord
from vault_graph.retrieval.explanation.result_explanation import ExplanationSignal as ExplanationSignal
from vault_graph.retrieval.explanation.result_explanation import ExplanationWarning as ExplanationWarning
from vault_graph.retrieval.graph.graph_contracts import RelationshipRecord as RelationshipRecord
from vault_graph.retrieval.graph.graph_retrieval import DecisionTraceResponse as DecisionTraceResponse
from vault_graph.retrieval.graph.graph_retrieval import DecisionTraceStep as DecisionTraceStep
from vault_graph.retrieval.graph.graph_retrieval import GraphRetrievalWarning as GraphRetrievalWarning
from vault_graph.retrieval.graph.graph_retrieval import RelatedItem as RelatedItem
from vault_graph.retrieval.graph.graph_retrieval import RelatedResponse as RelatedResponse
from vault_graph.retrieval.search.retrieval_result import RetrievalResult as RetrievalResult
from vault_graph.retrieval.search.retrieval_result import RetrievalSignal as RetrievalSignal
from vault_graph.retrieval.search.retrieval_result import RetrievalWarning as RetrievalWarning
from vault_graph.retrieval.search.retrieval_result import StoreRevision as StoreRevision
from vault_graph.retrieval.search.search_response import SearchResponse as SearchResponse
from vault_graph.retrieval.search.search_response import SearchStoreRevision as SearchStoreRevision
from vault_graph.retrieval.search.search_response import SearchWarning as SearchWarning
from vault_graph.storage.interfaces.metadata_store import EvidenceReference as EvidenceReference

sys.modules[__name__] = _implementation
