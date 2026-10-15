"""Compatibility import for :mod:`vault_graph.interface.mcp.mcp_tool_serialization`."""

import dataclasses as dataclasses
import hashlib as hashlib
import json as json
import re as re
import sys
from pathlib import Path as Path
from pathlib import PurePosixPath as PurePosixPath
from typing import Any as Any
from urllib.parse import quote as quote
from urllib.parse import unquote as unquote
from urllib.parse import urlsplit as urlsplit

from vault_graph.context.pack.context_pack import ContextEvidence as ContextEvidence
from vault_graph.context.pack.context_pack import ContextPack as ContextPack
from vault_graph.context.pack.context_pack import ContextPackSignal as ContextPackSignal
from vault_graph.context.pack.context_pack import ContextPackWarning as ContextPackWarning
from vault_graph.context.pack.context_pack_serialization import context_pack_to_dict as context_pack_to_dict
from vault_graph.interface.mcp import mcp_tool_serialization as _implementation
from vault_graph.interface.mcp.mcp_errors import McpErrorPayload as McpErrorPayload
from vault_graph.interface.mcp.mcp_tool_serialization import (
    _context_warning_matches_item as _context_warning_matches_item,
)
from vault_graph.interface.mcp.mcp_tool_serialization import _decision_trace_result_id as _decision_trace_result_id
from vault_graph.interface.mcp.mcp_tool_serialization import (
    _decision_trace_step_to_dict as _decision_trace_step_to_dict,
)
from vault_graph.interface.mcp.mcp_tool_serialization import _dedupe_dicts as _dedupe_dicts
from vault_graph.interface.mcp.mcp_tool_serialization import _evidence_ref_from_context as _evidence_ref_from_context
from vault_graph.interface.mcp.mcp_tool_serialization import _evidence_ref_from_metadata as _evidence_ref_from_metadata
from vault_graph.interface.mcp.mcp_tool_serialization import _expect_dict as _expect_dict
from vault_graph.interface.mcp.mcp_tool_serialization import _graph_warning_matches_item as _graph_warning_matches_item
from vault_graph.interface.mcp.mcp_tool_serialization import _is_safe_relative_path as _is_safe_relative_path
from vault_graph.interface.mcp.mcp_tool_serialization import (
    _is_safe_repository_evidence_uri as _is_safe_repository_evidence_uri,
)
from vault_graph.interface.mcp.mcp_tool_serialization import _is_safe_vault_evidence_uri as _is_safe_vault_evidence_uri
from vault_graph.interface.mcp.mcp_tool_serialization import _json_value as _json_value
from vault_graph.interface.mcp.mcp_tool_serialization import _links_for_context_evidence as _links_for_context_evidence
from vault_graph.interface.mcp.mcp_tool_serialization import _links_for_evidence as _links_for_evidence
from vault_graph.interface.mcp.mcp_tool_serialization import _links_for_graph_entity as _links_for_graph_entity
from vault_graph.interface.mcp.mcp_tool_serialization import _links_from_dicts as _links_from_dicts
from vault_graph.interface.mcp.mcp_tool_serialization import _links_to_dicts as _links_to_dicts
from vault_graph.interface.mcp.mcp_tool_serialization import _optional_positive_int as _optional_positive_int
from vault_graph.interface.mcp.mcp_tool_serialization import _optional_string as _optional_string
from vault_graph.interface.mcp.mcp_tool_serialization import (
    _redact_unsafe_project_context_paths as _redact_unsafe_project_context_paths,
)
from vault_graph.interface.mcp.mcp_tool_serialization import _related_item_to_dict as _related_item_to_dict
from vault_graph.interface.mcp.mcp_tool_serialization import _related_result_id as _related_result_id
from vault_graph.interface.mcp.mcp_tool_serialization import (
    _relationship_status_for_path as _relationship_status_for_path,
)
from vault_graph.interface.mcp.mcp_tool_serialization import _retrieval_result_to_dict as _retrieval_result_to_dict
from vault_graph.interface.mcp.mcp_tool_serialization import _runtime_result_id as _runtime_result_id
from vault_graph.interface.mcp.mcp_tool_serialization import (
    _search_store_revision_to_dict as _search_store_revision_to_dict,
)
from vault_graph.interface.mcp.mcp_tool_serialization import (
    _search_warning_matches_result as _search_warning_matches_result,
)
from vault_graph.interface.mcp.mcp_tool_serialization import _signal_from_context as _signal_from_context
from vault_graph.interface.mcp.mcp_tool_serialization import _signal_from_retrieval as _signal_from_retrieval
from vault_graph.interface.mcp.mcp_tool_serialization import (
    _store_revision_dicts_for_context as _store_revision_dicts_for_context,
)
from vault_graph.interface.mcp.mcp_tool_serialization import (
    _store_revision_dicts_for_graph as _store_revision_dicts_for_graph,
)
from vault_graph.interface.mcp.mcp_tool_serialization import (
    _store_revision_dicts_for_search as _store_revision_dicts_for_search,
)
from vault_graph.interface.mcp.mcp_tool_serialization import _store_revision_to_dict as _store_revision_to_dict
from vault_graph.interface.mcp.mcp_tool_serialization import _unique_links as _unique_links
from vault_graph.interface.mcp.mcp_tool_serialization import _warning_from_context as _warning_from_context
from vault_graph.interface.mcp.mcp_tool_serialization import _warning_from_graph as _warning_from_graph
from vault_graph.interface.mcp.mcp_tool_serialization import _warning_from_retrieval as _warning_from_retrieval
from vault_graph.interface.mcp.mcp_tool_serialization import _warning_from_search as _warning_from_search
from vault_graph.interface.mcp.mcp_tool_serialization import context_pack_to_payload as context_pack_to_payload
from vault_graph.interface.mcp.mcp_tool_serialization import (
    decision_trace_response_to_payload as decision_trace_response_to_payload,
)
from vault_graph.interface.mcp.mcp_tool_serialization import evidence_to_dict as evidence_to_dict
from vault_graph.interface.mcp.mcp_tool_serialization import (
    explanation_payload_to_resource_links as explanation_payload_to_resource_links,
)
from vault_graph.interface.mcp.mcp_tool_serialization import (
    explanation_records_for_context_pack as explanation_records_for_context_pack,
)
from vault_graph.interface.mcp.mcp_tool_serialization import (
    explanation_records_for_decision_trace as explanation_records_for_decision_trace,
)
from vault_graph.interface.mcp.mcp_tool_serialization import (
    explanation_records_for_related as explanation_records_for_related,
)
from vault_graph.interface.mcp.mcp_tool_serialization import (
    explanation_records_for_search as explanation_records_for_search,
)
from vault_graph.interface.mcp.mcp_tool_serialization import graph_warning_to_dict as graph_warning_to_dict
from vault_graph.interface.mcp.mcp_tool_serialization import mcp_warning_from_context as mcp_warning_from_context
from vault_graph.interface.mcp.mcp_tool_serialization import mcp_warning_from_graph as mcp_warning_from_graph
from vault_graph.interface.mcp.mcp_tool_serialization import mcp_warning_from_search as mcp_warning_from_search
from vault_graph.interface.mcp.mcp_tool_serialization import (
    mcp_warnings_for_project_context as mcp_warnings_for_project_context,
)
from vault_graph.interface.mcp.mcp_tool_serialization import project_context_text_mirror as project_context_text_mirror
from vault_graph.interface.mcp.mcp_tool_serialization import project_context_to_payload as project_context_to_payload
from vault_graph.interface.mcp.mcp_tool_serialization import query_scope_to_dict as query_scope_to_dict
from vault_graph.interface.mcp.mcp_tool_serialization import related_response_to_payload as related_response_to_payload
from vault_graph.interface.mcp.mcp_tool_serialization import (
    resource_links_for_context_pack as resource_links_for_context_pack,
)
from vault_graph.interface.mcp.mcp_tool_serialization import (
    resource_links_for_decision_trace as resource_links_for_decision_trace,
)
from vault_graph.interface.mcp.mcp_tool_serialization import (
    resource_links_for_project_context as resource_links_for_project_context,
)
from vault_graph.interface.mcp.mcp_tool_serialization import resource_links_for_related as resource_links_for_related
from vault_graph.interface.mcp.mcp_tool_serialization import resource_links_for_search as resource_links_for_search
from vault_graph.interface.mcp.mcp_tool_serialization import retrieval_signal_to_dict as retrieval_signal_to_dict
from vault_graph.interface.mcp.mcp_tool_serialization import retrieval_warning_to_dict as retrieval_warning_to_dict
from vault_graph.interface.mcp.mcp_tool_serialization import search_response_to_payload as search_response_to_payload
from vault_graph.interface.mcp.mcp_tool_serialization import search_warning_to_dict as search_warning_to_dict
from vault_graph.interface.mcp.mcp_tool_serialization import status_report_to_payload as status_report_to_payload
from vault_graph.interface.mcp.mcp_tool_serialization import tool_text_mirror as tool_text_mirror
from vault_graph.interface.mcp.mcp_tools import McpResourceLink as McpResourceLink
from vault_graph.interface.mcp.mcp_uri import encode_resource_segment as encode_resource_segment
from vault_graph.operation.diagnostics.index_status_reader import StatusReport as StatusReport
from vault_graph.operation.scope.vault_catalog import QueryScope as QueryScope
from vault_graph.project_context import ProjectContext as ProjectContext
from vault_graph.project_context import compact_project_context_value as compact_project_context_value
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
