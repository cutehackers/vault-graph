"""Compatibility import for :mod:`vault_graph.retrieval.graph.graph_identity`."""

import sys

from vault_graph.indexing.ingestion.document_normalizer import stable_id as stable_id
from vault_graph.operation.scope.vault_catalog import QueryScope as QueryScope
from vault_graph.retrieval.graph import graph_identity as _implementation
from vault_graph.retrieval.graph.graph_identity import graph_scope_key as graph_scope_key
from vault_graph.retrieval.graph.graph_identity import normalize_entity_name as normalize_entity_name
from vault_graph.retrieval.graph.graph_identity import require_actual_graph_scope as require_actual_graph_scope
from vault_graph.retrieval.graph.graph_identity import stable_entity_id as stable_entity_id
from vault_graph.retrieval.graph.graph_identity import stable_evidence_ref_id as stable_evidence_ref_id
from vault_graph.retrieval.graph.graph_identity import stable_graph_tombstone_id as stable_graph_tombstone_id
from vault_graph.retrieval.graph.graph_identity import stable_relationship_id as stable_relationship_id

sys.modules[__name__] = _implementation
