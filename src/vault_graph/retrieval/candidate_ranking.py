"""Compatibility import for :mod:`vault_graph.retrieval.search.candidate_ranking`."""

import sys
from dataclasses import dataclass as dataclass

from vault_graph.retrieval.search import candidate_ranking as _implementation
from vault_graph.retrieval.search.candidate_ranking import RANK_CONSTANT as RANK_CONSTANT
from vault_graph.retrieval.search.candidate_ranking import SIGNAL_WEIGHTS as SIGNAL_WEIGHTS
from vault_graph.retrieval.search.candidate_ranking import FusedCandidate as FusedCandidate
from vault_graph.retrieval.search.candidate_ranking import _signal_kind_order as _signal_kind_order
from vault_graph.retrieval.search.candidate_ranking import _take_family_once as _take_family_once
from vault_graph.retrieval.search.candidate_ranking import candidate_from_keyword_hit as candidate_from_keyword_hit
from vault_graph.retrieval.search.candidate_ranking import candidate_from_vector_hit as candidate_from_vector_hit
from vault_graph.retrieval.search.candidate_ranking import family_duplication as family_duplication
from vault_graph.retrieval.search.candidate_ranking import fuse_candidates as fuse_candidates
from vault_graph.retrieval.search.candidate_ranking import rank_resolved_candidates as rank_resolved_candidates
from vault_graph.retrieval.search.retrieval_candidate import RetrievalCandidate as RetrievalCandidate
from vault_graph.retrieval.search.retrieval_result import RetrievalResult as RetrievalResult
from vault_graph.retrieval.search.retrieval_result import RetrievalSignal as RetrievalSignal
from vault_graph.retrieval.search.retrieval_result import RetrievalSignalKind as RetrievalSignalKind
from vault_graph.retrieval.search.search_response import SearchMode as SearchMode
from vault_graph.storage.interfaces.keyword_index import KeywordHit as KeywordHit
from vault_graph.storage.interfaces.metadata_store import EvidenceReference as EvidenceReference
from vault_graph.storage.interfaces.vector_store import VectorHit as VectorHit

sys.modules[__name__] = _implementation
