"""Compatibility import for :mod:`vault_graph.retrieval.search.retrieval_result`."""

import sys
from dataclasses import dataclass as dataclass
from typing import Literal as Literal

from vault_graph.errors import RetrievalContractError as RetrievalContractError
from vault_graph.retrieval.search import retrieval_result as _implementation
from vault_graph.retrieval.search.retrieval_result import RelationshipStatus as RelationshipStatus
from vault_graph.retrieval.search.retrieval_result import RetrievalResult as RetrievalResult
from vault_graph.retrieval.search.retrieval_result import RetrievalSeverity as RetrievalSeverity
from vault_graph.retrieval.search.retrieval_result import RetrievalSignal as RetrievalSignal
from vault_graph.retrieval.search.retrieval_result import RetrievalSignalKind as RetrievalSignalKind
from vault_graph.retrieval.search.retrieval_result import RetrievalWarning as RetrievalWarning
from vault_graph.retrieval.search.retrieval_result import StoreRevision as StoreRevision
from vault_graph.retrieval.search.retrieval_result import _require_non_empty as _require_non_empty
from vault_graph.retrieval.search.retrieval_result import (
    require_vector_hit_evidence_match as require_vector_hit_evidence_match,
)
from vault_graph.retrieval.search.retrieval_result import (
    warning_for_missing_vector_evidence as warning_for_missing_vector_evidence,
)
from vault_graph.retrieval.search.retrieval_result import warning_for_stale_vector as warning_for_stale_vector
from vault_graph.storage.interfaces.metadata_store import EvidenceReference as EvidenceReference
from vault_graph.storage.interfaces.vector_store import VectorHit as VectorHit

sys.modules[__name__] = _implementation
