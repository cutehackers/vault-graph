"""Compatibility import for :mod:`vault_graph.retrieval.graph.graph_contracts`."""

import hashlib as hashlib
import json as json
import sys
from dataclasses import dataclass as dataclass

from vault_graph.errors import GraphRecordInvalid as GraphRecordInvalid
from vault_graph.operation.scope.vault_catalog import QueryScope as QueryScope
from vault_graph.retrieval.graph import graph_contracts as _implementation
from vault_graph.retrieval.graph.graph_contracts import ENTITY_STATUSES as ENTITY_STATUSES
from vault_graph.retrieval.graph.graph_contracts import OWNER_KINDS as OWNER_KINDS
from vault_graph.retrieval.graph.graph_contracts import RELATIONSHIP_STATUSES as RELATIONSHIP_STATUSES
from vault_graph.retrieval.graph.graph_contracts import TOMBSTONE_RECORD_KINDS as TOMBSTONE_RECORD_KINDS
from vault_graph.retrieval.graph.graph_contracts import EntityRecord as EntityRecord
from vault_graph.retrieval.graph.graph_contracts import GraphApplyResult as GraphApplyResult
from vault_graph.retrieval.graph.graph_contracts import GraphEvidenceRef as GraphEvidenceRef
from vault_graph.retrieval.graph.graph_contracts import GraphExtractionSpec as GraphExtractionSpec
from vault_graph.retrieval.graph.graph_contracts import GraphManifest as GraphManifest
from vault_graph.retrieval.graph.graph_contracts import GraphManifestEntity as GraphManifestEntity
from vault_graph.retrieval.graph.graph_contracts import GraphManifestEvidence as GraphManifestEvidence
from vault_graph.retrieval.graph.graph_contracts import GraphManifestRelationship as GraphManifestRelationship
from vault_graph.retrieval.graph.graph_contracts import GraphReconcilePlan as GraphReconcilePlan
from vault_graph.retrieval.graph.graph_contracts import GraphRecordScope as GraphRecordScope
from vault_graph.retrieval.graph.graph_contracts import GraphRevision as GraphRevision
from vault_graph.retrieval.graph.graph_contracts import GraphTombstone as GraphTombstone
from vault_graph.retrieval.graph.graph_contracts import RelationshipRecord as RelationshipRecord
from vault_graph.retrieval.graph.graph_contracts import _as_tuple as _as_tuple
from vault_graph.retrieval.graph.graph_contracts import _require_actual_scopes as _require_actual_scopes
from vault_graph.retrieval.graph.graph_contracts import _require_digest as _require_digest
from vault_graph.retrieval.graph.graph_contracts import _require_non_empty as _require_non_empty
from vault_graph.retrieval.graph.graph_contracts import current_graph_extraction_spec as current_graph_extraction_spec
from vault_graph.retrieval.graph.graph_identity import graph_scope_key as graph_scope_key

sys.modules[__name__] = _implementation
