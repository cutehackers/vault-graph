# Phase 6C Timeline, Health, And Explorer Views SPEC

Status: Draft for implementation planning

Date: 2026-06-18

Scope: Phase 6C

## 1. Purpose

Phase 6C completes the memory and explorer layer by exposing recent changes,
projection freshness, backend health, and scale-up adapter readiness.

Users and agents should be able to inspect what changed recently and whether
Vault Graph's projections are trustworthy before relying on memory, context, or
graph output.

## 2. Success Criteria

Phase 6C is complete when:

- `TimelineMemoryService.recent_changes(...)` returns recent durable
  Vault-derived changes and derived projection changes with origin labels.
- MCP registers `get_recent_changes` only after the backing service exists.
- `vault://{vault_id}/timeline/recent` returns a structured timeline projection
  instead of a Phase 5B availability error.
- `HealthExplorerService.inspect(...)` reports metadata, vector, graph,
  projection, MCP cache, and adapter readiness in one evidence-linked payload.
- scale-up readiness checks report logical contract readiness without migrating
  data or requiring hosted services.
- stale or unavailable projections remain visible as structured warnings.
- no timeline or health view mutates Vault or derived indexes.

## 3. In Scope

- timeline DTOs and service.
- recent changes MCP tool.
- `timeline/recent` MCP resource upgrade.
- health/freshness explorer DTOs and service.
- scale-up adapter readiness records for configured or known backend contracts.
- tests for origin labeling, freshness, multi-Vault scoping, serialization, and
  read-only behavior.

## 4. Out Of Scope

- hosted monitoring
- data migration to Postgres, Qdrant, or Neo4j
- background watchers or resource subscriptions
- UI dashboards
- alert delivery
- answer synthesis
- raw session transcript or episode log storage
- external persistent memory server integration
- automatic Vault repair or publication

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
src/vault_graph/mcp/mcp_service_factory.py
src/vault_graph/mcp/mcp_resources.py
src/vault_graph/mcp/mcp_tools.py
src/vault_graph/mcp/mcp_tool_serialization.py
src/vault_graph/mcp/__init__.py
tests/test_mcp_resources.py
tests/test_mcp_tools.py
tests/test_mcp_stdio_smoke.py
```

## 6. Timeline Data Model

`src/vault_graph/memory/timeline_memory.py` owns timeline DTOs.

```python
from dataclasses import dataclass
from typing import Literal

TimelineOrigin = Literal[
    "vault_change",
    "index_change",
    "projection_change",
    "warning",
]

@dataclass(frozen=True)
class TimelineEvidenceRef:
    vault_id: str
    document_id: str | None
    chunk_id: str | None
    path: str | None
    content_hash: str | None
    metadata_index_revision: str | None
    vault_revision: str | None

@dataclass(frozen=True)
class TimelineWarning:
    code: str
    message: str
    severity: str
    affected_vault_ids: tuple[str, ...]
    recovery_hint: str | None = None

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
    warnings: tuple[TimelineWarning, ...]

@dataclass(frozen=True)
class RecentChangesProjection:
    requested_scope: QueryScope
    actual_scopes: tuple[QueryScope, ...]
    since: str | None
    limit: int
    items: tuple[TimelineItem, ...]
    warnings: tuple[TimelineWarning, ...]
    store_revisions: tuple[dict[str, object], ...]
    generated_at: str
```

Origin rules:

- `vault_change`: document-level changes derived from metadata snapshots,
  hashes, `last_seen_at`, `last_indexed_at`, and optional Vault Git revision.
- `index_change`: metadata, keyword, or vector revision state.
- `projection_change`: graph or context projection revision state.
- `warning`: stale, unavailable, incompatible, or missing projection state.

Timeline records are projection records. They do not assert a durable business
event unless backed by Vault evidence.

External memory-layer systems often model episodic memory as persistent event
history. Phase 6C uses only the projection form of that idea. Raw conversation
transcripts, agent session logs, user profiles, and hidden episode stores remain
outside Vault Graph core. If a conversation or event should become durable, it
must be captured in Vault first and then appear in the timeline through normal
indexing.

## 7. Timeline Service

```python
class TimelineMemoryService:
    def __init__(
        self,
        *,
        catalog: VaultCatalog,
        metadata_store: MetadataStore,
        status_service: IndexService,
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

Rules:

- expand requested scopes through `actual_query_scopes(...)`;
- read metadata document snapshots through `MetadataStore.list_documents(...)`;
- read projection freshness through `IndexService.status(...)`;
- parse `since` as ISO-8601 timestamp when provided;
- reject non-positive limits and limits above the MCP tool limit;
- return deterministic ordering by descending timestamp, then Vault ID, then
  path, then item ID;
- include warnings when timestamps are unavailable and fallback sorting is used.

## 8. Health Explorer Data Model

`src/vault_graph/memory/health_explorer.py` owns operations-facing DTOs.

```python
from dataclasses import dataclass
from typing import Literal

ReadinessStatus = Literal["ready", "degraded", "unavailable", "not_configured"]

@dataclass(frozen=True)
class BackendReadinessRecord:
    backend_kind: str
    backend_name: str
    status: ReadinessStatus
    schema_compatible: bool
    freshness: str | None
    revision: str | None
    message: str
    recovery_hint: str | None

@dataclass(frozen=True)
class ScaleUpAdapterReadiness:
    adapter_kind: str
    target_backend: str
    configured: bool
    contract_ready: bool
    migration_required: bool
    message: str

@dataclass(frozen=True)
class HealthExplorerReport:
    requested_scope: QueryScope
    actual_scopes: tuple[QueryScope, ...]
    backends: tuple[BackendReadinessRecord, ...]
    scale_up_adapters: tuple[ScaleUpAdapterReadiness, ...]
    warnings: tuple[TimelineWarning, ...]
    generated_at: str
```

The health explorer is an operations projection over existing status and
configuration. It does not create or repair stores.

## 9. Scale-Up Readiness Policy

Phase 6C readiness checks are contract checks, not migrations.

Records should answer:

- Is a scale-up backend configured?
- Does the repository have an adapter contract for this backend kind?
- Can current local logical identity fields map to the backend?
- Would migration be required before use?
- Which current projection is stale or incompatible?

Initial backend kinds:

- metadata: local SQLite now, future Postgres contract
- vector: local Chroma now, future Qdrant contract
- graph: local SQLite/rustworkx now, future Neo4j contract

If no scale-up backend config exists, return `configured=False` and
`contract_ready=False` with a neutral message. Do not fail the health report.

## 10. MCP Tools And Resources

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

Resource upgrade:

```text
vault://{vault_id}/timeline/recent
```

This resource returns `RecentChangesProjection` for one Vault with default limit
20 and no `since` filter.

Health explorer exposure:

- keep `check_index_status` as the stable MCP status tool;
- add health explorer fields to the status payload after the service exists;
- do not add a separate MCP health tool unless the implementation plan proves
  the existing status payload becomes too broad.

## 11. Error And Degradation Policy

- invalid `since`: validation error with ISO-8601 guidance
- unknown Vault ID: validation error
- missing metadata: execution error for timeline, because document changes
  cannot be listed
- missing vector or graph state: warning records
- incompatible backend schema: warning or error based on whether timeline can
  still list metadata-backed changes
- no recent changes: successful empty projection

## 12. Multi-Vault Policy

- tools default to active Vault.
- resource URIs are single-Vault.
- explicit all-Vault tool scope groups items by Vault ID and never merges by
  path alone.
- identical timestamps sort by Vault ID and path for deterministic output.
- scale-up readiness records report the scope they evaluated.

## 13. Tests

Required tests:

- recent changes classify origins as `vault_change`, `index_change`,
  `projection_change`, and `warning`.
- `since` filters ISO timestamps correctly.
- timeline output remains deterministic with missing timestamps.
- `timeline/recent` resource returns structured JSON for one Vault.
- `get_recent_changes` serializes tool output and warnings.
- health explorer reports metadata, vector, graph, and scale-up readiness
  without mutating stores.
- multi-Vault timelines do not collide on identical paths.
- read-only boundary tests assert no Vault file mutation and no store
  initialization.
- boundary tests assert no raw episode log, session transcript, or external
  memory-server persistence is created.

Verification commands:

```bash
uv run --python 3.12 pytest tests/test_timeline_memory_service.py tests/test_health_explorer_service.py -q
uv run --python 3.12 pytest tests/test_mcp_recent_changes_tool.py tests/test_mcp_timeline_resource.py tests/test_mcp_resources.py tests/test_mcp_tools.py -q
VG_RUN_MCP_STDIO_SMOKE=1 uv run --python 3.12 pytest tests/test_mcp_stdio_smoke.py -q
uv run --python 3.12 ruff check src tests
uv run --python 3.12 mypy src tests
```

## 14. Risks And Mitigations

- **Risk:** timeline users may treat projection timestamps as durable business
  events.
  **Mitigation:** every item carries `origin` and evidence; projection changes
  are labeled separately.
- **Risk:** scale-up readiness becomes a speculative config system.
  **Mitigation:** report only known backend kinds and contract readiness; do not
  add migration behavior.
- **Risk:** status payload grows too broad.
  **Mitigation:** keep `HealthExplorerService` separate from MCP serialization
  and expose only compact summary fields in `check_index_status`.
- **Risk:** episodic-memory terminology creates pressure to store raw sessions.
  **Mitigation:** timeline items are projections over Vault-derived metadata and
  projection status only; durable events must enter through Vault first.

## 15. Open Decisions

None for Phase 6C. Hosted monitoring and remote backend migration remain future
work.
