"""Compatibility import for :mod:`vault_graph.retrieval.search.context_expansion`."""

import sys
from dataclasses import dataclass as dataclass

from vault_graph.errors import RetrievalContractError as RetrievalContractError
from vault_graph.indexing.ingestion.document_normalizer import ChunkSnapshot as ChunkSnapshot
from vault_graph.operation.scope.vault_catalog import QueryScope as QueryScope
from vault_graph.retrieval.search import context_expansion as _implementation
from vault_graph.retrieval.search.context_expansion import CONTEXT_POLICY_VERSION as CONTEXT_POLICY_VERSION
from vault_graph.retrieval.search.context_expansion import ContextExpander as ContextExpander
from vault_graph.retrieval.search.context_expansion import ContextExpansion as ContextExpansion
from vault_graph.retrieval.search.context_expansion import _chunk_in_scope as _chunk_in_scope
from vault_graph.retrieval.search.context_expansion import _common_prefix as _common_prefix
from vault_graph.retrieval.search.context_expansion import _find_chunk_index as _find_chunk_index
from vault_graph.retrieval.search.context_expansion import _longest_parent_prefix as _longest_parent_prefix
from vault_graph.retrieval.search.context_expansion import _neighbor_candidates as _neighbor_candidates
from vault_graph.retrieval.search.context_expansion import _validate_arguments as _validate_arguments
from vault_graph.retrieval.search.context_expansion import _warning as _warning
from vault_graph.retrieval.search.retrieval_result import RetrievalWarning as RetrievalWarning
from vault_graph.storage.interfaces.metadata_store import MetadataStore as MetadataStore

sys.modules[__name__] = _implementation
