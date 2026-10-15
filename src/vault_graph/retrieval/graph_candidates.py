"""Compatibility import for :mod:`vault_graph.retrieval.search.graph_candidates`."""

import sys
from dataclasses import dataclass as dataclass
from typing import Protocol as Protocol

from vault_graph.errors import GraphStoreError as GraphStoreError
from vault_graph.errors import SearchError as SearchError
from vault_graph.operation.scope.vault_catalog import QueryScope as QueryScope
from vault_graph.retrieval.search import graph_candidates as _implementation
from vault_graph.retrieval.search.graph_candidates import GraphCandidateProvider as GraphCandidateProvider
from vault_graph.retrieval.search.graph_candidates import GraphCandidateResult as GraphCandidateResult
from vault_graph.retrieval.search.graph_candidates import GraphSearchCandidateProvider as GraphSearchCandidateProvider
from vault_graph.retrieval.search.graph_candidates import GraphSearchSource as GraphSearchSource
from vault_graph.retrieval.search.graph_candidates import _affected_vault_ids as _affected_vault_ids
from vault_graph.retrieval.search.graph_candidates import _failed_result as _failed_result
from vault_graph.retrieval.search.retrieval_candidate import RetrievalCandidate as RetrievalCandidate
from vault_graph.retrieval.search.search_response import SearchStoreRevision as SearchStoreRevision
from vault_graph.retrieval.search.search_response import SearchWarning as SearchWarning

sys.modules[__name__] = _implementation
