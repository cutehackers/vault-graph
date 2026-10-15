"""Compatibility import for :mod:`vault_graph.retrieval.graph.graph_resource_service`."""

import sys
from dataclasses import dataclass as dataclass
from typing import Literal as Literal

from vault_graph.errors import CatalogError as CatalogError
from vault_graph.errors import GraphStoreError as GraphStoreError
from vault_graph.operation.scope.catalog_query_scopes import actual_query_scopes as actual_query_scopes
from vault_graph.operation.scope.vault_catalog import QueryScope as QueryScope
from vault_graph.operation.scope.vault_catalog import VaultCatalog as VaultCatalog
from vault_graph.retrieval.evidence.evidence_linking import EvidenceLinker as EvidenceLinker
from vault_graph.retrieval.graph import graph_resource_service as _implementation
from vault_graph.retrieval.graph.graph_contracts import EntityRecord as EntityRecord
from vault_graph.retrieval.graph.graph_contracts import GraphEvidenceRef as GraphEvidenceRef
from vault_graph.retrieval.graph.graph_contracts import RelationshipRecord as RelationshipRecord
from vault_graph.retrieval.graph.graph_identity import graph_scope_key as graph_scope_key
from vault_graph.retrieval.graph.graph_query import GraphEntityIdentity as GraphEntityIdentity
from vault_graph.retrieval.graph.graph_query import GraphEntityQuery as GraphEntityQuery
from vault_graph.retrieval.graph.graph_query import GraphRelationshipQuery as GraphRelationshipQuery
from vault_graph.retrieval.graph.graph_readiness import GraphReadiness as GraphReadiness
from vault_graph.retrieval.graph.graph_resource_service import GraphEntityResource as GraphEntityResource
from vault_graph.retrieval.graph.graph_resource_service import GraphResourceService as GraphResourceService
from vault_graph.retrieval.graph.graph_resource_service import GraphResourceWarning as GraphResourceWarning
from vault_graph.retrieval.graph.graph_resource_service import (
    GraphResourceWarningSeverity as GraphResourceWarningSeverity,
)
from vault_graph.retrieval.graph.graph_resource_service import (
    _fresh_scopes_with_warnings as _fresh_scopes_with_warnings,
)
from vault_graph.retrieval.graph.graph_resource_service import _normalize_concept_name as _normalize_concept_name
from vault_graph.retrieval.graph.graph_resource_service import _store_revisions as _store_revisions
from vault_graph.retrieval.graph.graph_retrieval import GraphRetrievalRevision as GraphRetrievalRevision
from vault_graph.retrieval.graph.graph_retrieval_service import GraphReadinessChecker as GraphReadinessChecker
from vault_graph.storage.interfaces.graph_store import GraphStore as GraphStore
from vault_graph.storage.interfaces.metadata_store import EvidenceReference as EvidenceReference
from vault_graph.storage.interfaces.metadata_store import MetadataStore as MetadataStore

sys.modules[__name__] = _implementation
