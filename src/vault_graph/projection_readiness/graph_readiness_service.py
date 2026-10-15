"""Compatibility import for :mod:`vault_graph.operation.readiness.graph_readiness_service`."""

import sys

from vault_graph.errors import GraphStoreError as GraphStoreError
from vault_graph.errors import GraphStoreUnavailable as GraphStoreUnavailable
from vault_graph.operation.readiness import graph_readiness_service as _implementation
from vault_graph.operation.readiness.graph_readiness_service import ReadOnlyGraphReadiness as ReadOnlyGraphReadiness
from vault_graph.operation.readiness.graph_readiness_service import _aggregate_freshness as _aggregate_freshness
from vault_graph.operation.readiness.graph_readiness_service import _evidence_warning as _evidence_warning
from vault_graph.operation.readiness.graph_readiness_service import (
    _evidence_warnings_by_scope as _evidence_warnings_by_scope,
)
from vault_graph.operation.readiness.graph_readiness_service import _graph_lookup_scopes as _graph_lookup_scopes
from vault_graph.operation.readiness.graph_readiness_service import _graph_spec_compatible as _graph_spec_compatible
from vault_graph.operation.readiness.graph_readiness_service import _last_revision as _last_revision
from vault_graph.operation.readiness.graph_readiness_service import _path_in_content_scope as _path_in_content_scope
from vault_graph.operation.readiness.graph_readiness_service import _recovery_hint as _recovery_hint
from vault_graph.operation.readiness.graph_readiness_service import _revision_for_scope as _revision_for_scope
from vault_graph.operation.readiness.graph_readiness_service import _revision_from_values as _revision_from_values
from vault_graph.operation.readiness.graph_readiness_service import (
    _tombstone_count_for_scope as _tombstone_count_for_scope,
)
from vault_graph.operation.readiness.graph_readiness_service import (
    _tombstone_counts_by_scope as _tombstone_counts_by_scope,
)
from vault_graph.operation.scope.vault_catalog import QueryScope as QueryScope
from vault_graph.retrieval.graph.graph_contracts import GraphExtractionSpec as GraphExtractionSpec
from vault_graph.retrieval.graph.graph_contracts import GraphManifest as GraphManifest
from vault_graph.retrieval.graph.graph_contracts import GraphManifestEvidence as GraphManifestEvidence
from vault_graph.retrieval.graph.graph_contracts import GraphRevision as GraphRevision
from vault_graph.retrieval.graph.graph_identity import graph_scope_key as graph_scope_key
from vault_graph.retrieval.graph.graph_readiness import GraphLineageScope as GraphLineageScope
from vault_graph.retrieval.graph.graph_readiness import GraphReadiness as GraphReadiness
from vault_graph.retrieval.graph.graph_readiness import GraphScopeReadiness as GraphScopeReadiness
from vault_graph.storage.interfaces.graph_store import GraphStore as GraphStore
from vault_graph.storage.interfaces.metadata_store import BatchEvidenceHashResolver as BatchEvidenceHashResolver
from vault_graph.storage.interfaces.metadata_store import EvidenceLookupKey as EvidenceLookupKey
from vault_graph.storage.interfaces.metadata_store import MetadataStore as MetadataStore
from vault_graph.storage.interfaces.store_health import StoreHealth as StoreHealth

sys.modules[__name__] = _implementation
