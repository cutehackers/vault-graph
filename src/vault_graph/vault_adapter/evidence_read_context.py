"""Compatibility import for :mod:`vault_graph.retrieval.evidence.evidence_read_context`."""

import hashlib as hashlib
import sys
from dataclasses import replace as replace
from typing import Protocol as Protocol
from typing import cast as cast

from vault_graph.operation.scope.vault_catalog import QueryScope as QueryScope
from vault_graph.retrieval.evidence import evidence_read_context as _implementation
from vault_graph.retrieval.evidence.evidence_linking import EvidenceLinker as EvidenceLinker
from vault_graph.retrieval.evidence.evidence_linking import EvidenceSourceRevision as EvidenceSourceRevision
from vault_graph.retrieval.evidence.evidence_read_context import EvidenceReadiness as EvidenceReadiness
from vault_graph.retrieval.evidence.evidence_read_context import build_evidence_linker as build_evidence_linker
from vault_graph.retrieval.graph.graph_identity import graph_scope_key as graph_scope_key
from vault_graph.retrieval.graph.graph_readiness import GraphReadiness as GraphReadiness
from vault_graph.storage.interfaces.evidence_owner_lookup import EvidenceOwnerLookup as EvidenceOwnerLookup
from vault_graph.storage.interfaces.graph_store import GraphStore as GraphStore
from vault_graph.storage.interfaces.metadata_store import MetadataStore as MetadataStore

sys.modules[__name__] = _implementation
