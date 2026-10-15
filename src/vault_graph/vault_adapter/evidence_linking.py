"""Compatibility import for :mod:`vault_graph.retrieval.evidence.evidence_linking`."""

import sys
from collections.abc import Callable as Callable
from dataclasses import dataclass as dataclass
from dataclasses import replace as replace
from pathlib import PurePosixPath as PurePosixPath
from typing import Literal as Literal

from vault_graph.errors import RetrievalContractError as RetrievalContractError
from vault_graph.operation.scope.vault_catalog import QueryScope as QueryScope
from vault_graph.retrieval.evidence import evidence_linking as _implementation
from vault_graph.retrieval.evidence.evidence_linking import EvidenceGraphLink as EvidenceGraphLink
from vault_graph.retrieval.evidence.evidence_linking import EvidenceKey as EvidenceKey
from vault_graph.retrieval.evidence.evidence_linking import EvidenceLinker as EvidenceLinker
from vault_graph.retrieval.evidence.evidence_linking import EvidenceResolution as EvidenceResolution
from vault_graph.retrieval.evidence.evidence_linking import EvidenceSourceRevision as EvidenceSourceRevision
from vault_graph.retrieval.evidence.evidence_linking import GraphLinkOutcome as GraphLinkOutcome
from vault_graph.retrieval.evidence.evidence_linking import GraphLinksRequest as GraphLinksRequest
from vault_graph.retrieval.evidence.evidence_linking import GraphLinksResult as GraphLinksResult
from vault_graph.retrieval.evidence.evidence_linking import GraphOwnerKey as GraphOwnerKey
from vault_graph.retrieval.evidence.evidence_linking import LinkStatus as LinkStatus
from vault_graph.retrieval.evidence.evidence_linking import StopReason as StopReason
from vault_graph.retrieval.evidence.evidence_linking import _fresh_scopes as _fresh_scopes
from vault_graph.retrieval.evidence.evidence_linking import _path_allowed as _path_allowed
from vault_graph.retrieval.evidence.evidence_linking import _unavailable as _unavailable
from vault_graph.retrieval.evidence.evidence_linking import _validate_key as _validate_key
from vault_graph.retrieval.evidence.evidence_linking import _validate_request as _validate_request
from vault_graph.retrieval.evidence.evidence_linking import _validate_rows as _validate_rows
from vault_graph.retrieval.graph.graph_contracts import GraphEvidenceRef as GraphEvidenceRef
from vault_graph.retrieval.graph.graph_identity import graph_scope_key as graph_scope_key
from vault_graph.retrieval.graph.graph_readiness import GraphReadiness as GraphReadiness
from vault_graph.storage.interfaces.evidence_owner_lookup import EvidenceOwnerLookup as EvidenceOwnerLookup
from vault_graph.storage.interfaces.evidence_owner_lookup import EvidenceOwnerRecord as EvidenceOwnerRecord
from vault_graph.storage.interfaces.metadata_store import EvidenceReference as EvidenceReference
from vault_graph.storage.interfaces.metadata_store import MetadataStore as MetadataStore

sys.modules[__name__] = _implementation
