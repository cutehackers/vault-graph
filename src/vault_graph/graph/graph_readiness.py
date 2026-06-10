from __future__ import annotations

from dataclasses import dataclass

from vault_graph.ingestion.vault_catalog import QueryScope

GRAPH_FRESHNESS_VALUES = ("missing", "empty", "fresh", "stale", "incompatible", "unavailable")


@dataclass(frozen=True)
class GraphLineageScope:
    vault_id: str
    effective_scope: str
    metadata_index_revision: str
    parser_version: str
    chunker_version: str


@dataclass(frozen=True)
class GraphLineageSnapshot:
    requested_scope: QueryScope
    effective_scopes: tuple[QueryScope, ...]
    metadata_lineage: tuple[GraphLineageScope, ...]
    graph_store_schema_version: str
    expected_graph_extraction_spec_version: str
    expected_graph_extraction_spec_digest: str


@dataclass(frozen=True)
class GraphScopeReadiness:
    vault_id: str
    effective_scope: str
    freshness: str
    stale_count: int
    tombstone_count: int
    last_graph_revision: str | None
    warnings: tuple[str, ...]


@dataclass(frozen=True)
class GraphReadiness:
    backend_name: str
    backend_available: bool
    schema_version: str
    schema_compatible: bool
    graph_extraction_spec_version: str
    graph_extraction_spec_digest: str
    graph_extraction_spec_compatible: bool
    freshness: str
    stale_count: int
    tombstone_count: int
    last_graph_revision: str | None
    affected_vault_ids: tuple[str, ...]
    scope_readiness: tuple[GraphScopeReadiness, ...]
    warnings: tuple[str, ...]
    recovery_hint: str
