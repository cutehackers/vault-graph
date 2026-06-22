# Phase 6C Timeline, Health, And Explorer Views SPEC

Status: Draft for implementation planning

Date: 2026-06-18

Scope: Phase 6C

## 1. Purpose

Phase 6C completes the Phase 6 memory and explorer layer by exposing:

- recent indexed document snapshot changes;
- current index and projection revision state;
- backend health and freshness;
- MCP runtime-cache visibility;
- scale-up adapter contract readiness.

The user value is operational trust. Before a human or agent relies on project
memory, context packs, search, or graph output, Vault Graph should make it easy
to answer:

- What indexed document snapshots changed recently in this Vault scope?
- Which derived projections are stale, missing, incompatible, or degraded?
- Is the current local backend healthy enough for the requested task?
- Would a future scale-up backend have the logical identity fields it needs?

Phase 6C is still a read-only projection layer. It is not hosted monitoring, not
a UI dashboard, not a data migration system, and not a durable memory database.
All durable truth remains in Vault; all Phase 6C output is rebuildable working
context over Vault-derived indexes and runtime status.

## 2. Success Criteria

Phase 6C is complete when:

- `TimelineMemoryService.recent_changes(...)` returns a grouped
  `RecentChangesProjection` for the requested `QueryScope`.
- timeline items distinguish `document_snapshot_change`, `index_change`,
  `projection_change`, and `warning` origins.
- document-level recent changes are derived from `MetadataStore.list_documents`;
  no service reads Vault files directly.
- index/projection change timestamps come only from indexed document snapshots
  or explicit status fields. The service must not invent timestamps.
- `IndexService.status(...)` exposes the minimal timestamp fields needed for
  vector and graph timeline items without exposing local status-store internals.
- MCP registers `get_recent_changes(since=None, scope=None, limit=20)` only
  after the backing service exists.
- `vault://{vault_id}/timeline/recent` returns single-Vault structured JSON
  instead of the Phase 5B availability error.
- `HealthExplorerService.inspect(...)` returns backend readiness, runtime-cache
  readiness, and scale-up contract readiness in a structured report.
- `check_index_status` remains the stable MCP status tool and adds a compact
  health-explorer payload; Phase 6C does not add a separate health MCP tool.
- all outputs preserve Vault IDs, actual scopes, warnings, revisions,
  generated timestamps, and safe recovery hints.
- all-Vault tool output is grouped by `vault_id` and never merges records by
  path, title, backend name, or timestamp alone.
- no Phase 6C path mutates Vault, initializes missing read-only stores, writes
  memory files, creates episode logs, or imports external memory systems.

## 3. In Scope

- timeline DTOs, validation helpers, and deterministic item IDs;
- timeline service over `MetadataStore` and a status-service protocol;
- minimal `StatusReport` extension for vector/graph run timestamps;
- recent changes MCP tool and parser;
- `timeline/recent` MCP resource upgrade;
- health/freshness explorer DTOs and service;
- MCP runtime-cache snapshot records for context-pack and result-explanation
  caches;
- scale-up adapter readiness records for known logical backend contracts;
- MCP serialization, prompt wording, service-factory handoff, and import
  boundary tests;
- read-only, multi-Vault, stale-state, timestamp, serialization, and
  no-external-memory tests.

## 4. Out Of Scope

- hosted monitoring, alerts, dashboards, or subscriptions;
- Postgres, Qdrant, Neo4j, or remote backend migration;
- background file watchers;
- answer synthesis or `ask_vault`;
- automatic Vault repair, publication, validation, or wiki updates;
- durable result history beyond the Phase 6A in-process explanation cache;
- raw session transcripts, hidden episode logs, profile memory, preference
  memory, or procedural memory;
- Mem0, MemMachine, or MCP memory-server integration.

## 5. Files To Add Or Modify

Add:

```text
src/vault_graph/memory/timeline_memory.py
src/vault_graph/memory/health_explorer.py
tests/test_timeline_memory_service.py
tests/test_health_explorer_service.py
tests/test_mcp_recent_changes_tool.py
tests/test_mcp_timeline_resource.py
```

Modify:

```text
src/vault_graph/app/index_service.py
src/vault_graph/memory/__init__.py
src/vault_graph/mcp/__init__.py
src/vault_graph/mcp/mcp_resources.py
src/vault_graph/mcp/mcp_service_factory.py
src/vault_graph/mcp/mcp_memory_serialization.py
src/vault_graph/mcp/mcp_tool_serialization.py
src/vault_graph/mcp/mcp_tools.py
tests/test_mcp_errors.py
tests/test_mcp_import_boundaries.py
tests/test_mcp_resource_read_only_boundary.py
tests/test_mcp_resources.py
tests/test_mcp_server.py
tests/test_mcp_service_factory.py
tests/test_mcp_stdio_smoke.py
tests/test_mcp_tool_read_only_boundary.py
tests/test_mcp_tool_serialization.py
tests/test_mcp_tools.py
```

Do not add `data/memory/`, timeline databases, status history stores, or
external memory dependencies in Phase 6C.

## 6. Existing Dependencies

Phase 6C builds on these current contracts:

- `QueryScope`, `VaultCatalog`, and `actual_query_scopes(...)`;
- `MetadataStore.list_documents(scope)` from Phase 6B;
- `DocumentSnapshot.last_seen_at`, `last_indexed_at`, `content_hash`,
  `raw_sha256`, `vault_revision`, and `index_revision`;
- `StatusReport` from `vault_graph.app.index_service`;
- Phase 6A `ResultExplanationCache`;
- Phase 4/5 `ContextPackResourceCache`;
- existing MCP scope parsing, resource URI parsing, and tool envelope shapes;
- Phase 6B `MemoryWarning`, `MemoryBackendRevision`, warning-to-MCP
  serialization style, and `MemoryProjectionError` from `vault_graph.errors`.

MCP layers must depend on the Phase 6C application services. They must not query
SQLite, Chroma, graph stores, status JSON files, or Vault files directly.

## 7. Status Report Extension

Phase 6C needs vector and graph run timestamps for timeline and health views.
Add optional fields to `StatusReport` and fill them from the existing vector and
graph status stores already read by `IndexService.status(...)`:

```python
@dataclass(frozen=True)
class StatusReport:
    ...
    vector_revision: str | None
    vector_last_success_at: str | None
    vector_last_error_at: str | None
    vector_last_error: str | None
    ...
    graph_last_success_revision: str | None
    graph_last_success_at: str | None
    graph_last_error_at: str | None
    graph_last_error: str | None
```

Rules:

- keep existing fields and payload keys backward-compatible;
- do not expose status-store file paths or raw JSON payloads;
- use `None` when a run timestamp is unavailable;
- do not create status-store files while checking status;
- update MCP status serialization to include the new timestamp fields under
  existing `vector` and `graph` objects;
- tests must cover the absence of status files and the presence of successful
  vector/graph run timestamps.

## 8. Timeline Data Model

`src/vault_graph/memory/timeline_memory.py` owns timeline DTOs. It may reuse
`MemoryWarning` and `MemoryBackendRevision` from `memory_models.py` to avoid a
second warning/revision vocabulary.

```python
from dataclasses import dataclass
from typing import Literal

TimelineOrigin = Literal[
    "document_snapshot_change",
    "index_change",
    "projection_change",
    "warning",
]
TimelineSourceKind = Literal[
    "document",
    "metadata_status",
    "vector_status",
    "graph_status",
]

@dataclass(frozen=True)
class TimelineEvidenceRef:
    source_kind: TimelineSourceKind
    vault_id: str
    document_id: str | None = None
    chunk_id: str | None = None
    path: str | None = None
    content_hash: str | None = None
    raw_sha256: str | None = None
    metadata_index_revision: str | None = None
    vault_revision: str | None = None
    backend_kind: str | None = None
    backend_revision: str | None = None
    scope_key: str | None = None

@dataclass(frozen=True)
class TimelineItem:
    item_id: str
    origin: TimelineOrigin
    title: str
    summary: str
    vault_id: str
    occurred_at: str | None
    sort_key: str
    evidence: tuple[TimelineEvidenceRef, ...]
    store_revisions: tuple[MemoryBackendRevision, ...]
    warnings: tuple[MemoryWarning, ...]

@dataclass(frozen=True)
class TimelineVault:
    vault_id: str
    display_name: str
    items: tuple[TimelineItem, ...]
    warnings: tuple[MemoryWarning, ...]
    store_revisions: tuple[MemoryBackendRevision, ...]
    freshness: str

@dataclass(frozen=True)
class RecentChangesProjection:
    requested_scope: QueryScope
    actual_scopes: tuple[QueryScope, ...]
    since: str | None
    limit: int
    vaults: tuple[TimelineVault, ...]
    warnings: tuple[MemoryWarning, ...]
    generated_at: str
```

Model rules:

- constructors validate required strings, tuple immutability, allowed literal
  values, and warning types like the Phase 6B memory DTOs;
- `TimelineEvidenceRef.vault_id` is required for every source kind;
- `source_kind="document"` requires `document_id`, `path`, and `content_hash`;
- `source_kind` values ending in `_status` require `backend_kind` and
  `scope_key`;
- `TimelineItem.evidence` must be non-empty unless `origin="warning"`;
- `warning` items must contain at least one warning with affected Vault IDs;
- `item_id` is `timeline:<origin>:<24 hex chars>`;
- item ID hash input includes origin, Vault ID, source kind, document ID or
  backend kind, path or scope key, revision, and occurred timestamp;
- `sort_key` is a deterministic string derived from occurred timestamp when
  available, otherwise `no-time:<vault_id>:<path-or-backend>:<item_id>`;
- `freshness` values should be `fresh`, `stale`, `degraded`, `unavailable`, or
  `unknown`;
- text mirrors must preserve `origin`, `occurred_at`, warnings, and evidence
  source kinds so status records do not look like durable Vault facts.

## 9. Timeline Origin Rules

`document_snapshot_change` items:

- are derived from `DocumentSnapshot` records returned by
  `MetadataStore.list_documents(scope)`;
- use `occurred_at = last_indexed_at or last_seen_at` and label it as an index
  observation timestamp, not a durable business-event timestamp;
- use title `Indexed document: <path>`;
- summarize only indexed document state such as path, document kind, content
  hash, raw SHA-256, metadata index revision, and Vault revision;
- never infer a business event such as "the project decided X" unless the Vault
  document itself is returned as evidence elsewhere.

`index_change` items:

- cover metadata and vector status derived from `StatusReport`;
- use vector `last_success_at` or `last_error_at` when available;
- use `occurred_at=None` when the status report lacks an explicit timestamp;
- represent keyword state as part of metadata unless a later phase gives keyword
  indexing an independent status contract.

`projection_change` items:

- cover graph readiness/status;
- use graph `last_success_at` or `last_error_at` when available;
- do not include MCP runtime caches. Runtime caches are health explorer records,
  not recent-change timeline items.

`warning` items:

- represent missing metadata, incompatible schema, stale vector or graph state,
  timestamp gaps, unsupported scope, or other degraded projection state;
- include safe recovery hints such as `Run vg index` or `Run vg status`;
- must not be hidden only in top-level warnings when they affect user trust in
  the timeline.

## 10. Timestamp And Since Policy

`since` is an ISO-8601 timestamp string. Both service and MCP parser must accept
timezone-aware values and treat timezone-naive values as UTC only if the parser
normalizes them explicitly.

Rules:

- invalid `since` is a validation error with ISO-8601 guidance;
- `since` filtering applies to `occurred_at`;
- when `since` is provided, items with `occurred_at=None` are excluded and a
  top-level `timeline_items_without_timestamps_excluded` warning is emitted;
- when `since` is not provided, items with `occurred_at=None` are included after
  timestamped items and carry item-level `missing_timeline_timestamp` warnings;
- timestamps are not synthesized from file names, titles, or rank;
- ordering is descending `occurred_at`, then `vault_id`, then normalized path or
  backend kind, then `item_id`;
- the default limit is `20`, the allowed range is `1..50`, and the limit applies
  per Vault group.

## 11. Timeline Service

Use a protocol rather than importing `IndexService` in the memory module:

```python
class TimelineStatusService(Protocol):
    def status(self, *, scope: QueryScope | None = None) -> StatusReport: ...

class TimelineMemoryService:
    def __init__(
        self,
        *,
        catalog: VaultCatalog,
        metadata_store: MetadataStore,
        status_service: TimelineStatusService,
        clock: Callable[[], datetime] | None = None,
    ) -> None: ...

    def recent_changes(
        self,
        *,
        requested_scope: QueryScope,
        since: str | None = None,
        limit: int = 20,
    ) -> RecentChangesProjection: ...
```

Service flow:

1. validate `limit` and parse `since`;
2. resolve actual scopes with `actual_query_scopes(...)`;
3. call `status_service.status(scope=actual_scope)` once per actual Vault
   scope;
4. fail with `MemoryProjectionError("metadata_unavailable: ...")` if metadata
   health is unavailable or schema-incompatible;
5. call `MetadataStore.list_recent_documents(actual_scope, since, limit)` once
   per actual Vault scope;
6. build document, index, projection, and warning items;
7. apply `since` and per-Vault limits;
8. return grouped output with top-level, Vault-level, and item-level warnings.

Service rules:

- `TimelineMemoryService` does not read chunk evidence or Vault files directly
  in Phase 6C. The existing status service may inspect derived chunk metadata
  internally when computing projection freshness;
- it does not call `VaultLoader`, `IndexService.run_apply(...)`, graph
  traversal, vector search, or context-pack builders;
- it does not create stores, run migrations, or repair stale indexes;
- metadata-unavailable is fatal because indexed document snapshots cannot be
  listed;
- vector or graph unavailable is a warning item and health warning, not fatal;
- document snapshots always use observed metadata timestamps; status or
  projection-only items may omit timestamps, and that gap remains visible.

## 12. Health Explorer Data Model

`src/vault_graph/memory/health_explorer.py` owns operations-facing DTOs. It is
MCP-free and has no direct dependency on MCP cache implementations.

```python
from dataclasses import dataclass
from typing import Literal

ReadinessStatus = Literal["ready", "degraded", "unavailable", "not_configured"]
HealthBackendKind = Literal["metadata", "keyword", "vector", "graph", "mcp_runtime_cache"]

@dataclass(frozen=True)
class BackendReadinessRecord:
    backend_kind: HealthBackendKind
    backend_name: str
    vault_id: str | None
    scope_key: str
    status: ReadinessStatus
    schema_compatible: bool
    freshness: str
    revision: str | None
    last_success_at: str | None
    last_error_at: str | None
    message: str
    recovery_hint: str | None

@dataclass(frozen=True)
class McpRuntimeCacheRecord:
    cache_name: str
    current_entries: int
    max_entries: int
    status: ReadinessStatus
    oldest_cached_at: str | None = None
    newest_cached_at: str | None = None
    message: str = ""

@dataclass(frozen=True)
class ScaleUpAdapterReadiness:
    adapter_kind: str
    target_backend: str
    configured: bool
    contract_ready: bool
    migration_required: bool
    depends_on_backend_kind: str
    message: str
    recovery_hint: str | None = None

@dataclass(frozen=True)
class HealthExplorerReport:
    requested_scope: QueryScope
    actual_scopes: tuple[QueryScope, ...]
    backends: tuple[BackendReadinessRecord, ...]
    runtime_caches: tuple[McpRuntimeCacheRecord, ...]
    scale_up_adapters: tuple[ScaleUpAdapterReadiness, ...]
    warnings: tuple[MemoryWarning, ...]
    generated_at: str
```

DTO rules:

- backend records must include a `scope_key` and either `vault_id` or an
  explicit all-scope marker in the message;
- runtime-cache records expose counts and capacity only, not cached payloads;
- scale-up records are readiness statements, not migrations or configuration
  writes;
- every degraded/unavailable backend should either have a recovery hint or a
  message explaining why no local recovery exists.

## 13. Health Explorer Service

```python
class HealthExplorerService:
    def __init__(
        self,
        *,
        catalog: VaultCatalog,
        status_service: TimelineStatusService,
        clock: Callable[[], datetime] | None = None,
    ) -> None: ...

    def inspect(
        self,
        *,
        requested_scope: QueryScope,
        runtime_caches: tuple[McpRuntimeCacheRecord, ...] = (),
        status_report: StatusReport | None = None,
    ) -> HealthExplorerReport: ...
```

Service flow:

1. resolve actual scopes;
2. use `status_report` when supplied, otherwise request one aggregate status
   report for the requested scope;
3. convert metadata, keyword, vector, and graph status into backend readiness
   records;
4. append runtime-cache records supplied by the MCP layer;
5. append static scale-up readiness records for known backend contracts;
6. return structured warnings for stale, unavailable, incompatible, or unknown
   state.

Backend mapping:

- metadata is `ready` when `metadata_ok` and `metadata_schema_compatible` are
  true;
- keyword is reported as `ready` only as a metadata-coupled projection in Phase
  6C. If future keyword health becomes independent, it can split without
  changing the health report shape;
- vector is `ready` when vector health is OK, schema-compatible, and
  `vector_stale_count == 0`; it is `degraded` when stale or when a last error is
  present but a last success revision exists;
- graph uses `StatusReport.graph_readiness.freshness`,
  `graph_last_success_revision`, and `graph_last_error`;
- MCP runtime caches are `ready` when configured and below capacity,
  `degraded` when at capacity, and `not_configured` only when omitted.

The service does not inspect local files, open stores, or instantiate backends.
`McpServiceFactory` is responsible for constructing it with the existing
read-only status service.

## 14. Scale-Up Readiness Policy

Phase 6C readiness checks are status/schema-derived contract checks, not
migrations and not record-level migration audits. They answer whether the local
logical contract appears ready enough to support a future adapter, based on the
current status report and known store DTO contracts.

Initial records:

| Adapter Kind | Target Backend | Depends On | Contract Ready When |
| --- | --- | --- | --- |
| `metadata` | `postgres` | metadata | metadata status is healthy/schema-compatible and current metadata DTO contracts define documents, chunks, evidence refs, tombstones, revisions, and health fields |
| `vector` | `qdrant` | vector | vector status is available/schema-compatible and current vector DTO contracts define vector IDs, embedding model specs, metadata revisions, and tombstones |
| `graph` | `neo4j` | graph | graph readiness is available/schema-compatible and current graph DTO contracts define entity IDs, relationship IDs, graph revisions, evidence memberships, and scope keys |

Rules:

- if no scale-up backend config exists, return `configured=False` and
  `contract_ready` based only on status/schema health and known local logical
  contracts;
- `migration_required=True` means data movement would be needed before using
  the target backend. It must not run a migration;
- missing local metadata makes all adapter readiness degraded because the
  status/schema basis for local identity contracts cannot be proven;
- stale vector or graph state should mark the corresponding adapter readiness
  degraded, not unavailable, when the logical fields are still present;
- readiness output must state that no record-level migration audit was
  performed and must never suggest that a remote backend is required for Phase
  6C.

## 15. MCP Tool Contract

Add tool:

```text
get_recent_changes(since=None, scope=None, limit=20)
```

Input DTO:

```python
@dataclass(frozen=True)
class GetRecentChangesInput:
    since: str | None = None
    scope: McpScopeInput | None = None
    limit: int = 20
```

Parser and registration rules:

- append `get_recent_changes` to `McpToolName` and
  `McpToolRegistry.tool_names`;
- update `tests/test_mcp_stdio_smoke.py` exact tool-list expectations;
- parse `scope` through `scope_from_mcp_input(...)`;
- support active-Vault default, explicit `vault_ids`, and `all_vaults`;
- reject `include_cross_vault`; timeline grouping is all-Vault selection, not
  cross-Vault graph traversal;
- validate `limit` with the existing `MAX_MCP_TOOL_LIMIT`;
- validate `since` before service invocation when called through MCP;
- return the existing MCP tool envelope:

```json
{
  "tool_name": "get_recent_changes",
  "payload": {
    "requested_scope": {},
    "actual_scopes": [],
    "since": null,
    "limit": 20,
    "vaults": [],
    "warnings": [],
    "generated_at": "..."
  },
  "resource_links": [],
  "warnings": [],
  "text": "{...}"
}
```

Resource-link rules:

- document-backed `document_snapshot_change` items link to
  `vault://{vault_id}/documents/{path}`;
- page/source/decision/issue links are not emitted from timeline items unless a
  later implementation intentionally reuses the Phase 6B document classifier;
- status-backed items do not get document links;
- no timeline-specific writable resource URI is introduced.

## 16. MCP Resource Contract

Upgrade:

```text
vault://{vault_id}/timeline/recent
```

Rules:

- resource returns `RecentChangesProjection` for exactly one Vault;
- resource scope is `catalog.scope_for_vault_ids((vault_id,))`;
- default limit is `20` and `since=None`;
- resource content type remains `application/json`;
- resource metadata mirrors the structured payload;
- all-Vault timeline remains tool-only because the URI is single-Vault;
- errors include affected Vault ID and safe recovery hints.

`CurrentContextResourceReader.read_recent_timeline(...)` may be kept as the
method name for a small patch, but the implementation should delegate to
`TimelineMemoryService`. If the implementation becomes harder to read, rename
the class to a neutral projection-resource reader in a separate mechanical
change.

## 17. MCP Status Health Exposure

Keep `check_index_status(scope=None)` as the stable tool. Extend its payload:

```json
{
  "metadata": {},
  "vector": {
    "last_success_at": null,
    "last_error_at": null
  },
  "graph": {
    "last_success_revision": null,
    "last_success_at": null,
    "last_error_at": null
  },
  "health_explorer": {
    "backends": [],
    "runtime_caches": [],
    "scale_up_adapters": [],
    "warnings": [],
    "generated_at": "..."
  }
}
```

Rules:

- `McpToolRegistry.check_index_status(...)` should call
  `HealthExplorerService.inspect(..., status_report=report)` after the existing
  `StatusReport` is available;
- `get_recent_changes` and `timeline/recent` may let timeline services read
  status internally because they do not already need a separate status payload;
- runtime cache snapshots are built in the MCP layer from
  `ContextPackResourceCache` and `ResultExplanationCache` using `len(...)` and
  `max_entries`;
- do not serialize cached context-pack bodies or explanation records in the
  status payload;
- prompt text may mention `check_index_status` for health/freshness, but must
  not imply autonomous repair.

## 18. Serialization Boundary

Add MCP adapter serializers near existing memory serialization:

```python
def recent_changes_projection_to_payload(
    projection: RecentChangesProjection,
) -> dict[str, object]: ...

def health_explorer_report_to_payload(
    report: HealthExplorerReport,
) -> dict[str, object]: ...

def resource_links_for_recent_changes(
    projection: RecentChangesProjection,
) -> tuple[McpResourceLink, ...]: ...
```

Rules:

- serializers preserve all warnings from projection, vault, and item levels;
- serializers use the same `query_scope_to_dict(...)` shape as existing MCP
  payloads;
- text mirrors are JSON mirrors like existing tool bodies and must not add
  facts absent from structured output;
- MCP error warnings reuse `memory_warning_to_mcp_error(...)`;
- serialization modules must not import local backend implementations.

## 19. Service Factory Handoff

`McpServiceFactory` adds lazy read-only construction methods:

```python
class McpServiceFactory:
    def open_timeline_memory_service(self) -> TimelineMemoryService: ...
    def open_health_explorer_service(self) -> HealthExplorerService: ...
```

Rules:

- open metadata stores with `initialize=False`;
- use `open_status_service()` for status access;
- do not add services to `McpServices` unless repeated construction becomes a
  measured problem;
- do not create timeline-specific storage directories;
- keep imports lazy so importing `vault_graph.mcp` does not import Chroma,
  graph stores, or embedding models.

## 20. Error And Degradation Policy

Validation errors:

- invalid `since`;
- non-integer, non-positive, or out-of-range `limit`;
- invalid scope object;
- unknown or disabled Vault ID.

Execution errors:

- missing or schema-incompatible metadata state;
- metadata store error that prevents document listing;
- malformed status report that prevents safe health conversion.

Degraded successful output:

- no recent changes;
- document timestamps missing;
- vector backend missing, stale, schema-incompatible, or last run failed;
- graph backend missing, stale, schema-incompatible, or last run failed;
- MCP runtime caches at capacity;
- scale-up backend not configured.

Recovery hints:

- metadata unavailable: `Run vg index, then vg status for the selected Vault.`
- stale vector: `Run vg index for the selected scope to refresh vector state.`
- stale graph: `Run vg index for the selected scope, then vg status.`
- missing timestamp: `Re-index the selected scope to refresh indexed timestamps.`

The exact CLI flags should match the implementation at the time of Phase 6C
coding. Do not invent unsupported commands in user-facing errors.

## 21. Multi-Vault Policy

- `scope=None` uses the active Vault.
- explicit `vault_ids` selects those Vaults.
- `all_vaults=True` expands to all enabled Vault entries before services run.
- `RecentChangesProjection.vaults` contains one `TimelineVault` per actual Vault
  scope.
- per-Vault `limit` avoids one noisy Vault hiding another.
- item IDs include `vault_id`.
- same path, same timestamp, or same revision in different Vaults never merge.
- resource URIs are single-Vault only.
- graph cross-Vault traversal remains out of scope for timeline and health
  explorer views.

## 22. Read-Only And Rebuildability

- Phase 6C writes no Vault files.
- Phase 6C writes no derived timeline or health files.
- Timeline output is regenerated from current metadata snapshots and status
  reports. Runtime-cache snapshots belong to health explorer output.
- Deleting runtime caches loses only cache visibility, not Vault Graph truth.
- Deleting derived indexes makes timeline/health output unavailable or degraded
  until `vg index` rebuilds them.
- External memory systems may later export Phase 6C projections, but they must
  not become sources for timeline or health facts.

Required boundary tests:

- no call path opens write-capable metadata, vector, or graph stores;
- no call path writes status files or creates status files during read-only
  timeline or health checks;
- no call path invokes `IndexService.run_apply(...)`;
- no call path reads registered Vault source files;
- no `MemoryStore`, `Memory.create/query/upsert/link/audit`, episode-log,
  profile-memory, preference-memory, procedural-memory, or external memory
  dependency is introduced.

## 23. Tests

Required tests:

- timeline DTOs reject blank IDs, invalid origins, mutable sequences, invalid
  evidence shapes, and warning items without warnings.
- document timeline items use `last_indexed_at` before `last_seen_at`.
- missing document timestamps create item warnings and deterministic fallback
  order.
- `since` filters timestamped items and excludes untimestamped items with a
  visible warning.
- recent changes classify `document_snapshot_change`, `index_change`,
  `projection_change`, and `warning` origins.
- per-Vault limits are enforced after grouping.
- multi-Vault timelines do not collide on identical paths, timestamps, or
  revisions.
- metadata-unavailable raises `MemoryProjectionError` with a safe recovery
  hint through MCP.
- vector/graph unavailable states return warning items instead of failing the
  timeline.
- `StatusReport` timestamp fields serialize through `check_index_status`.
- health explorer maps metadata, keyword, vector, graph, runtime-cache, and
  scale-up readiness states deterministically.
- runtime-cache records expose counts/capacity but not cached payloads.
- `get_recent_changes` validates input, serializes payloads, resource links,
  warnings, and text mirrors.
- `timeline/recent` resource returns structured JSON for one Vault.
- `check_index_status` includes compact `health_explorer` output.
- prompt tests mention `get_recent_changes` only after the tool is registered.
- import-boundary tests keep Phase 6C modules free of local backend imports at
  package import time.
- read-only boundary tests assert no Vault mutation and no store
  initialization.
- boundary tests assert no raw episode log, session transcript, profile memory,
  preference memory, procedural memory, or external memory-server persistence is
  created.

Verification commands:

```bash
uv run --python 3.12 pytest tests/test_timeline_memory_service.py tests/test_health_explorer_service.py -q
uv run --python 3.12 pytest tests/test_mcp_recent_changes_tool.py tests/test_mcp_timeline_resource.py tests/test_mcp_resources.py tests/test_mcp_tools.py -q
uv run --python 3.12 pytest tests/test_mcp_tool_serialization.py tests/test_mcp_service_factory.py tests/test_mcp_import_boundaries.py -q
VG_RUN_MCP_STDIO_SMOKE=1 uv run --python 3.12 pytest tests/test_mcp_stdio_smoke.py -q
uv run --python 3.12 ruff check src tests
uv run --python 3.12 mypy src tests
```

## 24. Implementation Handoff

Implement Phase 6C in this order:

1. Extend `StatusReport` with vector/graph timestamp fields and update status
   serialization tests.
2. Add timeline DTOs, stable timeline item IDs, timestamp parsing, and model
   tests.
3. Add `TimelineMemoryService` over `MetadataStore.list_documents(...)` and the
   status-service protocol.
4. Add health explorer DTOs and `HealthExplorerService`.
5. Add MCP serializers for recent changes and health explorer reports.
6. Add `McpServiceFactory.open_timeline_memory_service()` and
   `open_health_explorer_service()`.
7. Add `GetRecentChangesInput`, parser, registry method, MCP tool, and tool
   tests.
8. Upgrade `vault://{vault_id}/timeline/recent`.
9. Extend `check_index_status` with compact health-explorer output.
10. Update prompts and stdio smoke expectations.
11. Run read-only/import-boundary tests, focused Phase 6C tests, and full static
    checks.

## 25. Risks And Mitigations

- **Risk:** users treat timeline timestamps as durable business events.
  **Mitigation:** title and summary must say indexed/projection state changed;
  every item carries `origin` and evidence source kind.
- **Risk:** health explorer becomes a speculative migration/config system.
  **Mitigation:** report contract readiness only; do not create remote configs,
  migrate data, or require hosted services.
- **Risk:** status payload becomes too broad.
  **Mitigation:** keep `HealthExplorerService` separate and serialize a compact
  structured section under `check_index_status`.
- **Risk:** timeline output becomes an unbounded whole-Vault scan.
  **Mitigation:** use metadata snapshots only, apply per-Vault limits, and do
  not read chunk evidence or Vault source files directly. Existing
  status/freshness services may inspect derived chunk metadata.
- **Risk:** memory terminology creates pressure for raw episode storage.
  **Mitigation:** Phase 6C exposes only Vault-derived timeline projections and
  runtime cache readiness. Durable events enter through Vault first.
- **Risk:** all-Vault recent changes hide source ownership.
  **Mitigation:** group by Vault ID and include Vault IDs in item IDs, evidence,
  warnings, revisions, and resource links.

## 26. Open Decisions

None for Phase 6C.

Hosted monitoring, remote backend migration, independent keyword status, and
external memory adapters remain future work.
