"""Compatibility import for :mod:`vault_graph.context.answer.evidence_planner`."""

import hashlib as hashlib
import sys
from typing import Protocol as Protocol

from vault_graph.context.answer import evidence_planner as _implementation
from vault_graph.context.answer.answer_plan import AnswerPlan as AnswerPlan
from vault_graph.context.answer.answer_plan import AnswerRequest as AnswerRequest
from vault_graph.context.answer.answer_plan import EvidencePlanStep as EvidencePlanStep
from vault_graph.context.answer.answer_plan import PlannedEvidence as PlannedEvidence
from vault_graph.context.answer.answer_response import AnswerEvidence as AnswerEvidence
from vault_graph.context.answer.answer_response import AnswerReasoningStep as AnswerReasoningStep
from vault_graph.context.answer.answer_response import AnswerSignal as AnswerSignal
from vault_graph.context.answer.answer_response import AnswerStoreRevision as AnswerStoreRevision
from vault_graph.context.answer.answer_response import AnswerWarning as AnswerWarning
from vault_graph.context.answer.evidence_planner import AnswerGraphService as AnswerGraphService
from vault_graph.context.answer.evidence_planner import AnswerOpenQuestionsService as AnswerOpenQuestionsService
from vault_graph.context.answer.evidence_planner import AnswerProjectMemoryService as AnswerProjectMemoryService
from vault_graph.context.answer.evidence_planner import AnswerRetrievalService as AnswerRetrievalService
from vault_graph.context.answer.evidence_planner import EvidencePlanner as EvidencePlanner
from vault_graph.context.answer.evidence_planner import _dedupe_evidence as _dedupe_evidence
from vault_graph.context.answer.evidence_planner import _enforce_budget as _enforce_budget
from vault_graph.context.answer.evidence_planner import (
    _evidence_from_decision_trace_response as _evidence_from_decision_trace_response,
)
from vault_graph.context.answer.evidence_planner import _evidence_from_search_response as _evidence_from_search_response
from vault_graph.context.answer.evidence_planner import _evidence_id as _evidence_id
from vault_graph.context.answer.evidence_planner import (
    _filter_reasoning_step_evidence_ids as _filter_reasoning_step_evidence_ids,
)
from vault_graph.context.answer.evidence_planner import _is_decision_oriented as _is_decision_oriented
from vault_graph.context.answer.evidence_planner import _projection_result_count as _projection_result_count
from vault_graph.context.answer.evidence_planner import _store_revision_from_any as _store_revision_from_any
from vault_graph.context.answer.evidence_planner import _string_attr as _string_attr
from vault_graph.errors import AnswerError as AnswerError
from vault_graph.operation.scope.vault_catalog import QueryScope as QueryScope
from vault_graph.retrieval.graph.graph_retrieval import DecisionTraceResponse as DecisionTraceResponse
from vault_graph.retrieval.graph.graph_retrieval import GraphOutputFormat as GraphOutputFormat
from vault_graph.retrieval.search.search_response import SearchOutputFormat as SearchOutputFormat
from vault_graph.retrieval.search.search_response import SearchResponse as SearchResponse

sys.modules[__name__] = _implementation
