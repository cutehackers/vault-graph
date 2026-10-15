"""Compatibility import for :mod:`vault_graph.retrieval.search.search_response`."""

import sys
from dataclasses import dataclass as dataclass
from typing import Literal as Literal

from vault_graph.errors import SearchError as SearchError
from vault_graph.operation.readiness.search_readiness import SearchStoreRevision as SearchStoreRevision
from vault_graph.operation.scope.vault_catalog import QueryScope as QueryScope
from vault_graph.retrieval.search import search_response as _implementation
from vault_graph.retrieval.search.retrieval_result import RetrievalResult as RetrievalResult
from vault_graph.retrieval.search.retrieval_result import RetrievalSeverity as RetrievalSeverity
from vault_graph.retrieval.search.search_response import SearchMode as SearchMode
from vault_graph.retrieval.search.search_response import SearchOutputFormat as SearchOutputFormat
from vault_graph.retrieval.search.search_response import SearchRequest as SearchRequest
from vault_graph.retrieval.search.search_response import SearchResponse as SearchResponse
from vault_graph.retrieval.search.search_response import SearchWarning as SearchWarning
from vault_graph.retrieval.search.search_response import _require_non_empty as _require_non_empty

sys.modules[__name__] = _implementation
