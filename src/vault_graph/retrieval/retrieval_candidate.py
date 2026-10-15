"""Compatibility import for :mod:`vault_graph.retrieval.search.retrieval_candidate`."""

import sys
from dataclasses import dataclass as dataclass

from vault_graph.errors import RetrievalContractError as RetrievalContractError
from vault_graph.retrieval.search import retrieval_candidate as _implementation
from vault_graph.retrieval.search.retrieval_candidate import RetrievalCandidate as RetrievalCandidate
from vault_graph.retrieval.search.retrieval_result import RetrievalSignal as RetrievalSignal

sys.modules[__name__] = _implementation
