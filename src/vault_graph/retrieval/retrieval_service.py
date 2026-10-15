"""Compatibility import for :mod:`vault_graph.retrieval.search.retrieval_service`."""

import sys
from dataclasses import replace as replace
from datetime import UTC as UTC
from datetime import datetime as datetime

from vault_graph.errors import KeywordIndexError as KeywordIndexError
from vault_graph.errors import MetadataStoreError as MetadataStoreError
from vault_graph.errors import RetrievalContractError as RetrievalContractError
from vault_graph.errors import SearchError as SearchError
from vault_graph.errors import TextEmbeddingsError as TextEmbeddingsError
from vault_graph.errors import VectorStoreError as VectorStoreError
from vault_graph.indexing.ingestion.document_authority import DocumentRole as DocumentRole
from vault_graph.operation.readiness.search_readiness import SearchReadiness as SearchReadiness
from vault_graph.operation.readiness.search_readiness import SearchReadinessReport as SearchReadinessReport
from vault_graph.operation.scope.catalog_query_scopes import actual_query_scopes as actual_query_scopes
from vault_graph.operation.scope.vault_catalog import QueryScope as QueryScope
from vault_graph.operation.scope.vault_catalog import VaultCatalog as VaultCatalog
from vault_graph.retrieval.search import retrieval_service as _implementation
from vault_graph.retrieval.search.candidate_ranking import candidate_from_keyword_hit as candidate_from_keyword_hit
from vault_graph.retrieval.search.candidate_ranking import candidate_from_vector_hit as candidate_from_vector_hit
from vault_graph.retrieval.search.candidate_ranking import family_duplication as family_duplication
from vault_graph.retrieval.search.candidate_ranking import fuse_candidates as fuse_candidates
from vault_graph.retrieval.search.context_expansion import ContextExpander as ContextExpander
from vault_graph.retrieval.search.evidence_result_assembly import EvidenceResultAssembly as EvidenceResultAssembly
from vault_graph.retrieval.search.graph_candidates import GraphCandidateProvider as GraphCandidateProvider
from vault_graph.retrieval.search.graph_candidates import GraphCandidateResult as GraphCandidateResult
from vault_graph.retrieval.search.retrieval_candidate import RetrievalCandidate as RetrievalCandidate
from vault_graph.retrieval.search.retrieval_result import RetrievalResult as RetrievalResult
from vault_graph.retrieval.search.retrieval_service import (
    DEFAULT_CONTEXT_EXPANSION_MAX_TOKENS as DEFAULT_CONTEXT_EXPANSION_MAX_TOKENS,
)
from vault_graph.retrieval.search.retrieval_service import (
    DEFAULT_CONTEXT_NEIGHBOR_RADIUS as DEFAULT_CONTEXT_NEIGHBOR_RADIUS,
)
from vault_graph.retrieval.search.retrieval_service import SEARCH_MODE_ROLES as SEARCH_MODE_ROLES
from vault_graph.retrieval.search.retrieval_service import RetrievalService as RetrievalService
from vault_graph.retrieval.search.retrieval_service import _affected_vault_ids as _affected_vault_ids
from vault_graph.retrieval.search.retrieval_service import (
    _can_run_vector_search_globally as _can_run_vector_search_globally,
)
from vault_graph.retrieval.search.retrieval_service import _fatal_readiness_error as _fatal_readiness_error
from vault_graph.retrieval.search.retrieval_service import _requested_scope_for_search as _requested_scope_for_search
from vault_graph.retrieval.search.retrieval_service import (
    _vector_stale_count_for_scope as _vector_stale_count_for_scope,
)
from vault_graph.retrieval.search.retrieval_service import _vector_stale_warnings as _vector_stale_warnings
from vault_graph.retrieval.search.retrieval_service import _warnings_for_readiness as _warnings_for_readiness
from vault_graph.retrieval.search.search_response import SearchMode as SearchMode
from vault_graph.retrieval.search.search_response import SearchOutputFormat as SearchOutputFormat
from vault_graph.retrieval.search.search_response import SearchRequest as SearchRequest
from vault_graph.retrieval.search.search_response import SearchResponse as SearchResponse
from vault_graph.retrieval.search.search_response import SearchWarning as SearchWarning
from vault_graph.storage.interfaces.keyword_index import KeywordHit as KeywordHit
from vault_graph.storage.interfaces.keyword_index import KeywordIndex as KeywordIndex
from vault_graph.storage.interfaces.keyword_index import KeywordQuery as KeywordQuery
from vault_graph.storage.interfaces.metadata_store import MetadataStore as MetadataStore
from vault_graph.storage.interfaces.text_embeddings import EmbeddingInput as EmbeddingInput
from vault_graph.storage.interfaces.text_embeddings import TextEmbeddings as TextEmbeddings
from vault_graph.storage.interfaces.vector_store import VectorHit as VectorHit
from vault_graph.storage.interfaces.vector_store import VectorQuery as VectorQuery
from vault_graph.storage.interfaces.vector_store import VectorStore as VectorStore

sys.modules[__name__] = _implementation
