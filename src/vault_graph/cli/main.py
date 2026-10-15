"""Compatibility import for :mod:`vault_graph.interface.cli.main`."""

import json as json
import sys
from collections.abc import Callable as Callable
from pathlib import Path as Path
from typing import TYPE_CHECKING as TYPE_CHECKING
from typing import cast as cast

import typer as typer

from vault_graph.context import DEFAULT_CONTEXT_MAX_TOKENS as DEFAULT_CONTEXT_MAX_TOKENS
from vault_graph.context import DEFAULT_CONTEXT_RETRIEVAL_LIMIT as DEFAULT_CONTEXT_RETRIEVAL_LIMIT
from vault_graph.context import ContextPackBudget as ContextPackBudget
from vault_graph.context import ContextPackRenderer as ContextPackRenderer
from vault_graph.context import ContextPackRequest as ContextPackRequest
from vault_graph.context import DefaultContextPackRenderer as DefaultContextPackRenderer
from vault_graph.context import MetadataContextEvidenceResolver as MetadataContextEvidenceResolver
from vault_graph.context import SearchContextPackBuilder as SearchContextPackBuilder
from vault_graph.errors import VaultGraphError as VaultGraphError
from vault_graph.indexing.index_service import IndexService as IndexService
from vault_graph.indexing.index_service import StatusReport as StatusReport
from vault_graph.indexing.publication.projection_generation import (
    ProjectionGenerationManager as ProjectionGenerationManager,
)
from vault_graph.interface.cli import main as _implementation
from vault_graph.interface.cli.code_commands import code_app as code_app
from vault_graph.interface.cli.harness_commands import harness_app as harness_app
from vault_graph.interface.cli.main import _answer_service as _answer_service
from vault_graph.interface.cli.main import _catalog as _catalog
from vault_graph.interface.cli.main import _context_builder_service as _context_builder_service
from vault_graph.interface.cli.main import _context_scope_for_flags as _context_scope_for_flags
from vault_graph.interface.cli.main import _decision_trace_response_json as _decision_trace_response_json
from vault_graph.interface.cli.main import _entity_json as _entity_json
from vault_graph.interface.cli.main import _entity_text as _entity_text
from vault_graph.interface.cli.main import _evidence_json as _evidence_json
from vault_graph.interface.cli.main import _evidence_ref_text as _evidence_ref_text
from vault_graph.interface.cli.main import _exit_on_domain_error as _exit_on_domain_error
from vault_graph.interface.cli.main import _exit_on_domain_error_stderr as _exit_on_domain_error_stderr
from vault_graph.interface.cli.main import _graph_evidence_ref_json as _graph_evidence_ref_json
from vault_graph.interface.cli.main import _graph_retrieval_service as _graph_retrieval_service
from vault_graph.interface.cli.main import _graph_revision_json as _graph_revision_json
from vault_graph.interface.cli.main import _graph_revision_text as _graph_revision_text
from vault_graph.interface.cli.main import _graph_tombstone_count as _graph_tombstone_count
from vault_graph.interface.cli.main import _graph_warning_json as _graph_warning_json
from vault_graph.interface.cli.main import _projection_bundle_status as _projection_bundle_status
from vault_graph.interface.cli.main import _read_only_search_components as _read_only_search_components
from vault_graph.interface.cli.main import _related_response_json as _related_response_json
from vault_graph.interface.cli.main import _relationship_json as _relationship_json
from vault_graph.interface.cli.main import _relationship_path_text as _relationship_path_text
from vault_graph.interface.cli.main import _render_decision_trace_response as _render_decision_trace_response
from vault_graph.interface.cli.main import _render_related_response as _render_related_response
from vault_graph.interface.cli.main import _render_search_response as _render_search_response
from vault_graph.interface.cli.main import _result_json as _result_json
from vault_graph.interface.cli.main import _result_warning_json as _result_warning_json
from vault_graph.interface.cli.main import _scope_json as _scope_json
from vault_graph.interface.cli.main import _scope_text as _scope_text
from vault_graph.interface.cli.main import _search_response_json as _search_response_json
from vault_graph.interface.cli.main import _search_service as _search_service
from vault_graph.interface.cli.main import _search_service_with_metadata as _search_service_with_metadata
from vault_graph.interface.cli.main import _search_text_embeddings as _search_text_embeddings
from vault_graph.interface.cli.main import _service as _service
from vault_graph.interface.cli.main import _signal_json as _signal_json
from vault_graph.interface.cli.main import _status_report_json as _status_report_json
from vault_graph.interface.cli.main import _store_revision_json as _store_revision_json
from vault_graph.interface.cli.main import _text_embeddings as _text_embeddings
from vault_graph.interface.cli.main import _warning_json as _warning_json
from vault_graph.interface.cli.main import app as app
from vault_graph.interface.cli.main import ask as ask
from vault_graph.interface.cli.main import context as context
from vault_graph.interface.cli.main import decision_trace as decision_trace
from vault_graph.interface.cli.main import index as index
from vault_graph.interface.cli.main import init as init
from vault_graph.interface.cli.main import mcp_app as mcp_app
from vault_graph.interface.cli.main import mcp_config as mcp_config
from vault_graph.interface.cli.main import mcp_register as mcp_register
from vault_graph.interface.cli.main import projection_audit as projection_audit
from vault_graph.interface.cli.main import related as related
from vault_graph.interface.cli.main import search as search
from vault_graph.interface.cli.main import serve as serve
from vault_graph.interface.cli.main import setup as setup
from vault_graph.interface.cli.main import status as status
from vault_graph.interface.cli.main import vault_add as vault_add
from vault_graph.interface.cli.main import vault_app as vault_app
from vault_graph.interface.cli.main import vault_list as vault_list
from vault_graph.interface.cli.main import watch as watch
from vault_graph.interface.cli.project_commands import project_app as project_app
from vault_graph.interface.composition.adapters.text_embeddings import (
    FastEmbedTextEmbeddings as FastEmbedTextEmbeddings,
)
from vault_graph.interface.composition.adapters.text_embeddings import (
    FastEmbedTextEmbeddingsConfig as FastEmbedTextEmbeddingsConfig,
)
from vault_graph.interface.composition.graph_store_factory import GraphBackend as GraphBackend
from vault_graph.interface.composition.graph_store_factory import open_graph_store as open_graph_store
from vault_graph.interface.composition.graph_store_factory import selected_graph_backend as selected_graph_backend
from vault_graph.interface.composition.local_index_service_factory import (
    LocalIndexServiceFactory as LocalIndexServiceFactory,
)
from vault_graph.operation.diagnostics.projection_hygiene_service import (
    ProjectionHygieneService as ProjectionHygieneService,
)
from vault_graph.operation.readiness.graph_readiness_service import ReadOnlyGraphReadiness as ReadOnlyGraphReadiness
from vault_graph.operation.readiness.search_readiness_service import ReadOnlySearchReadiness as ReadOnlySearchReadiness
from vault_graph.operation.scope.catalog_service import CatalogService as CatalogService
from vault_graph.operation.scope.graph_home import GraphHomeResolver as GraphHomeResolver
from vault_graph.operation.scope.vault_catalog import QueryScope as QueryScope
from vault_graph.operation.scope.vault_catalog import VaultCatalog as VaultCatalog
from vault_graph.operation.scope.vault_catalog import VaultCatalogEntry as VaultCatalogEntry
from vault_graph.retrieval import DecisionTraceResponse as DecisionTraceResponse
from vault_graph.retrieval import GraphOutputFormat as GraphOutputFormat
from vault_graph.retrieval import GraphRetrievalRevision as GraphRetrievalRevision
from vault_graph.retrieval import GraphRetrievalWarning as GraphRetrievalWarning
from vault_graph.retrieval import GraphSearchCandidateProvider as GraphSearchCandidateProvider
from vault_graph.retrieval import RelatedResponse as RelatedResponse
from vault_graph.retrieval import RetrievalResult as RetrievalResult
from vault_graph.retrieval import RetrievalService as RetrievalService
from vault_graph.retrieval import RetrievalSignal as RetrievalSignal
from vault_graph.retrieval import RetrievalWarning as RetrievalWarning
from vault_graph.retrieval import SearchResponse as SearchResponse
from vault_graph.retrieval import SearchStoreRevision as SearchStoreRevision
from vault_graph.retrieval import SearchWarning as SearchWarning
from vault_graph.retrieval import StoreRevision as StoreRevision
from vault_graph.retrieval.graph.graph_contracts import EntityRecord as EntityRecord
from vault_graph.retrieval.graph.graph_contracts import GraphEvidenceRef as GraphEvidenceRef
from vault_graph.retrieval.graph.graph_contracts import RelationshipRecord as RelationshipRecord
from vault_graph.retrieval.graph.graph_contracts import current_graph_extraction_spec as current_graph_extraction_spec
from vault_graph.retrieval.graph.graph_identity import graph_scope_key as graph_scope_key
from vault_graph.retrieval.graph.graph_retrieval_service import GraphRetrievalService as GraphRetrievalService
from vault_graph.retrieval.search.search_response import SearchMode as SearchMode
from vault_graph.storage.interfaces.metadata_store import EvidenceReference as EvidenceReference
from vault_graph.storage.local.chroma_vector_store import ChromaVectorStore as ChromaVectorStore
from vault_graph.storage.local.sqlite_graph_store import SQLiteGraphStore as SQLiteGraphStore
from vault_graph.storage.local.sqlite_keyword_index import SQLiteKeywordIndex as SQLiteKeywordIndex
from vault_graph.storage.local.sqlite_metadata_store import SQLiteMetadataStore as SQLiteMetadataStore

sys.modules[__name__] = _implementation
