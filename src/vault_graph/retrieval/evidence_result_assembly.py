"""Compatibility import for :mod:`vault_graph.retrieval.search.evidence_result_assembly`."""

import re as re
import sys

from vault_graph.indexing.ingestion.document_authority import DocumentRole as DocumentRole
from vault_graph.retrieval.evidence.evidence_linking import EvidenceLinker as EvidenceLinker
from vault_graph.retrieval.search import evidence_result_assembly as _implementation
from vault_graph.retrieval.search.candidate_ranking import FusedCandidate as FusedCandidate
from vault_graph.retrieval.search.candidate_ranking import rank_resolved_candidates as rank_resolved_candidates
from vault_graph.retrieval.search.evidence_result_assembly import EvidenceResultAssembly as EvidenceResultAssembly
from vault_graph.retrieval.search.evidence_result_assembly import _excerpt as _excerpt
from vault_graph.retrieval.search.evidence_result_assembly import (
    _one_reference_per_document as _one_reference_per_document,
)
from vault_graph.retrieval.search.evidence_result_assembly import _result_store_revisions as _result_store_revisions
from vault_graph.retrieval.search.evidence_result_assembly import _title_for_evidence as _title_for_evidence
from vault_graph.retrieval.search.retrieval_result import RetrievalResult as RetrievalResult
from vault_graph.retrieval.search.retrieval_result import StoreRevision as StoreRevision
from vault_graph.retrieval.search.search_response import SearchMode as SearchMode
from vault_graph.retrieval.search.search_response import SearchWarning as SearchWarning
from vault_graph.storage.interfaces.metadata_store import EvidenceReference as EvidenceReference
from vault_graph.storage.interfaces.metadata_store import MetadataStore as MetadataStore

sys.modules[__name__] = _implementation
