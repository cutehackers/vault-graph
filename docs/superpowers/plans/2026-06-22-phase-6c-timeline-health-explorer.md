# Phase 6C Timeline Health Explorer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add read-only recent-change timeline, projection health, runtime-cache visibility, and scale-up readiness explorer views for Phase 6C.

**Architecture:** Keep Phase 6C as a projection layer over existing Vault-derived metadata and status reports. `vault_graph.memory` owns MCP-free timeline and health DTOs/services, while `vault_graph.mcp` owns argument parsing, resource/tool registration, JSON serialization, runtime-cache snapshots, and MCP error mapping.

**Tech Stack:** Python 3.12, frozen dataclasses, existing `QueryScope`/`VaultCatalog`, bounded `MetadataStore.list_recent_documents(...)`, `IndexService.status(...)`, FastMCP tool/resource registration, pytest, ruff, mypy.

---

## Source Documents

Read these before implementation:

- `AGENTS.md`
- `docs/SPEC.md`
- `docs/FEATURES.md`
- `docs/DESIGN.md`
- `docs/DECISIONS.md`
- `docs/PATCH_LOG.md`
- `docs/CONVENTIONS.md`
- `docs/superpowers/specs/phase-6/README.md`
- `docs/superpowers/specs/phase-6/2026-06-18-phase-6-memory-and-explorer-views-overview-design.md`
- `docs/superpowers/specs/phase-6/2026-06-18-phase-6a-result-explanation-contract-design.md`
- `docs/superpowers/specs/phase-6/2026-06-18-phase-6b-project-decision-issue-memory-design.md`
- `docs/superpowers/specs/phase-6/2026-06-18-phase-6c-timeline-health-explorer-design.md`
- `docs/superpowers/plans/2026-06-19-phase-6a-result-explanation-contract.md`
- `docs/superpowers/plans/2026-06-19-phase-6b-project-decision-issue-memory.md`

Current repo facts to preserve:

- `src/vault_graph/memory/memory_models.py` already owns `MemoryWarning` and `MemoryBackendRevision`; Phase 6C should reuse them instead of creating a second warning vocabulary.
- `src/vault_graph/memory/memory_request_context.py` already uses a protocol to avoid importing `IndexService` at memory-module import time; Phase 6C timeline service should follow the same pattern.
- `src/vault_graph/storage/interfaces/metadata_store.py` already exposes `list_documents(scope)`. Phase 6C adds a bounded recent-document listing method over the same metadata snapshots so timeline output does not require materializing every document in a large Vault.
- `src/vault_graph/storage/local/vector_status_store.py` and `src/vault_graph/storage/local/graph_status_store.py` already persist `last_success_at` and `last_error_at`, but `StatusReport` does not expose them yet.
- `src/vault_graph/mcp/mcp_tools.py` currently registers Phase 6B tools only and intentionally excludes `get_recent_changes`.
- `src/vault_graph/mcp/mcp_resources.py` currently returns an availability error for `vault://{vault_id}/timeline/recent`.
- `src/vault_graph/mcp/mcp_service_factory.py` opens stores lazily and read-only; new services must preserve `initialize=False`, lazy graph imports, and no external-memory imports.
- Phase 6 memory is projection terminology only. Do not add writable memory APIs, episode logs, profile/preference/procedural memory, or external memory dependencies.

## Scope

Implement Phase 6C:

- Extend `StatusReport` with vector and graph run timestamp fields.
- Add bounded recent-document listing to `MetadataStore` and the SQLite metadata store.
- Add timeline DTOs, timestamp parsing, stable IDs, and `TimelineMemoryService`.
- Add health explorer DTOs and `HealthExplorerService`.
- Add MCP serialization for recent changes, health reports, resource links, and runtime-cache records.
- Add `McpServiceFactory.open_timeline_memory_service()` and `open_health_explorer_service()`.
- Register `get_recent_changes(since=None, scope=None, limit=20)`.
- Upgrade `vault://{vault_id}/timeline/recent` to return one-Vault JSON timeline output.
- Extend `check_index_status(scope=None)` with a compact `health_explorer` payload.
- Update prompts and MCP smoke expectations now that Phase 6C services exist.
- Add read-only, import-boundary, multi-Vault, timestamp, serialization, resource, tool, and health tests.

## Non-Goals

Do not implement:

- hosted monitoring, alerts, dashboards, subscriptions, or UI pages
- Postgres, Qdrant, Neo4j, or remote backend migration
- background file watchers
- answer synthesis or `ask_vault`
- automatic Vault edits, source capture, validation, wiki publication, or repair
- durable timeline databases, status history tables, or memory files
- raw session transcripts, hidden episode logs, profile memory, preference memory, or procedural memory
- Mem0, MemMachine, MCP memory-server, or any external-memory dependency
- new CLI or HTTP surfaces
- record-level migration audits for scale-up backends

## Directory And File Structure

Create:

- `src/vault_graph/memory/timeline_memory.py`: MCP-free timeline DTOs, timestamp parsing, stable item IDs, and `TimelineMemoryService`.
- `src/vault_graph/memory/health_explorer.py`: MCP-free backend readiness, runtime-cache readiness, scale-up readiness DTOs, and `HealthExplorerService`.
- `tests/test_timeline_memory_service.py`: timeline DTO, timestamp, grouping, warning, multi-Vault, and service behavior tests.
- `tests/test_health_explorer_service.py`: health DTO and `HealthExplorerService.inspect(...)` mapping tests.
- `tests/test_mcp_recent_changes_tool.py`: MCP parser, registry, tool payload, warnings, errors, and scope tests.
- `tests/test_mcp_timeline_resource.py`: `vault://{vault_id}/timeline/recent` one-Vault resource tests.

Modify:

- `src/vault_graph/app/index_service.py`: add timestamp fields to `StatusReport` and populate them from vector/graph run status stores.
- `src/vault_graph/memory/__init__.py`: add lazy exports for Phase 6C DTOs and services.
- `src/vault_graph/storage/interfaces/metadata_store.py`: add `list_recent_documents(scope, since, limit)`.
- `src/vault_graph/storage/local/sqlite_metadata_store.py`: implement bounded recent-document listing over indexed document snapshots.
- `src/vault_graph/mcp/__init__.py`: add lazy exports for `GetRecentChangesInput` and `parse_get_recent_changes_input` if public MCP imports require them.
- `src/vault_graph/mcp/mcp_errors.py`: recognize Phase 6C domain error codes that may cross MCP boundaries.
- `src/vault_graph/mcp/mcp_memory_serialization.py`: add timeline/health payload serializers, timeline resource links, warning collection, and runtime-cache snapshot helpers.
- `src/vault_graph/mcp/mcp_resources.py`: implement `CurrentContextResourceReader.read_recent_timeline(...)`.
- `src/vault_graph/mcp/mcp_service_factory.py`: add lazy read-only timeline and health service constructors.
- `src/vault_graph/mcp/mcp_tool_serialization.py`: include status timestamps and accept optional health-explorer payload for `check_index_status`.
- `src/vault_graph/mcp/mcp_tools.py`: add input DTO, parser, registry method, FastMCP handler, and status health handoff.
- `src/vault_graph/mcp/mcp_prompts.py`: mention `get_recent_changes` in workflows that benefit from recency checks.
- `tests/test_mcp_errors.py`
- `tests/test_sqlite_metadata_store.py`
- `tests/test_mcp_import_boundaries.py`
- `tests/test_mcp_resource_read_only_boundary.py`
- `tests/test_mcp_resources.py`
- `tests/test_mcp_server.py`
- `tests/test_mcp_service_factory.py`
- `tests/test_mcp_stdio_smoke.py`
- `tests/test_mcp_tool_read_only_boundary.py`
- `tests/test_mcp_tool_serialization.py`
- `tests/test_mcp_tools.py`
- `tests/test_naming_conventions.py` only if a new naming guard is needed by review.

Do not create:

- `src/vault_graph/memory/memory_store.py`
- `src/vault_graph/memory/episode_log.py`
- `src/vault_graph/memory/profile_memory.py`
- `src/vault_graph/memory/preference_memory.py`
- `src/vault_graph/memory/procedural_memory.py`
- `src/vault_graph/memory/external_memory.py`
- `data/memory/`
- a timeline SQLite table
- a status-history store
- a timeline Chroma collection
- external-memory adapter code

## Component And Interface Spec

### `src/vault_graph/app/index_service.py`

Extend `StatusReport` without removing existing fields:

```python
@dataclass(frozen=True)
class StatusReport:
    ...
    vector_revision: str | None
    vector_last_success_at: str | None
    vector_last_error_at: str | None
    vector_stale_count: int
    vector_last_error: str | None
    vector_status_scope: str
    graph_readiness: GraphReadiness
    graph_status_scope: str
    graph_last_success_revision: str | None
    graph_last_success_at: str | None
    graph_last_error_at: str | None
    graph_last_error: str | None
```

Populate values in `IndexService.status(...)`:

```python
vector_revision=run_status.last_success_revision if run_status is not None else None,
vector_last_success_at=run_status.last_success_at if run_status is not None else None,
vector_last_error_at=run_status.last_error_at if run_status is not None else None,
vector_stale_count=vector_stale_count,
vector_last_error=run_status.last_error if run_status is not None else None,
...
graph_last_success_revision=graph_run_status.last_success_revision if graph_run_status is not None else None,
graph_last_success_at=graph_run_status.last_success_at if graph_run_status is not None else None,
graph_last_error_at=graph_run_status.last_error_at if graph_run_status is not None else None,
graph_last_error=graph_run_status.last_error if graph_run_status is not None else None,
```

Rules:

- Do not create status files from `status(...)`.
- Do not expose status-store paths or raw JSON payloads.
- Use `None` when status stores or timestamps are unavailable.
- Keep existing MCP status keys backward-compatible.

### `src/vault_graph/storage/interfaces/metadata_store.py`

Add to `MetadataStore`:

```python
def list_recent_documents(
    self,
    scope: QueryScope,
    *,
    since: str | None = None,
    limit: int = 20,
) -> tuple[DocumentSnapshot, ...]: ...
```

Contract:

- returns current non-tombstoned documents only;
- returns `()` when the database is missing and must not create files;
- filters by `scope.vault_ids` and `scope.content_scopes`;
- uses `last_indexed_at or last_seen_at` as the observed timestamp;
- when `since` is provided, returns only documents with observed timestamp at
  or after `since`;
- `DocumentSnapshot.last_seen_at` is required by the current model, so document
  snapshot changes always have an observed timestamp in Phase 6C;
- orders by observed timestamp descending, then `vault_id`, `path`, and
  `document_id`;
- applies `limit` before returning rows for each actual one-Vault scope;
- preserves all `DocumentSnapshot` fields exactly;
- does not run schema creation, migrations, tombstone writes, keyword updates,
  vector calls, graph calls, or status writes.

SQLite implementation guidance:

```python
def list_recent_documents(
    self,
    scope: QueryScope,
    *,
    since: str | None = None,
    limit: int = 20,
) -> tuple[DocumentSnapshot, ...]:
    if limit < 1:
        raise MetadataStoreError("invalid_metadata_limit: limit must be positive")
    if not scope.vault_ids or not self._database_path.exists():
        return ()
    # Build a bounded SELECT over documents with path predicates for each
    # content scope. Use COALESCE(last_indexed_at, last_seen_at) as observed_at.
```

The implementation should push content-scope filtering into SQL rather than
fetching all rows and filtering in Python. Reuse the same-or-child content-scope
rule used by `list_documents(...)`.

### `src/vault_graph/memory/timeline_memory.py`

Public API:

```python
from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal, Protocol, TYPE_CHECKING

from vault_graph.errors import MemoryProjectionError
from vault_graph.ingestion.query_scope_resolution import actual_query_scopes
from vault_graph.ingestion.vault_catalog import QueryScope, VaultCatalog
from vault_graph.memory.memory_models import MemoryBackendRevision, MemoryWarning
from vault_graph.storage.interfaces.metadata_store import MetadataStore

if TYPE_CHECKING:
    from vault_graph.app.index_service import StatusReport

TimelineOrigin = Literal["document_snapshot_change", "index_change", "projection_change", "warning"]
TimelineSourceKind = Literal["document", "metadata_status", "vector_status", "graph_status"]
TimelineFreshness = Literal["fresh", "stale", "degraded", "unavailable", "unknown"]


class TimelineStatusService(Protocol):
    def status(self, *, scope: QueryScope | None = None) -> StatusReport: ...


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
    freshness: TimelineFreshness


@dataclass(frozen=True)
class RecentChangesProjection:
    requested_scope: QueryScope
    actual_scopes: tuple[QueryScope, ...]
    since: str | None
    limit: int
    vaults: tuple[TimelineVault, ...]
    warnings: tuple[MemoryWarning, ...]
    generated_at: str


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


def parse_timeline_since(value: str | None) -> str | None: ...


def stable_timeline_item_id(
    *,
    origin: TimelineOrigin,
    vault_id: str,
    source_kind: TimelineSourceKind,
    document_id: str | None,
    backend_kind: str | None,
    path: str | None,
    scope_key: str | None,
    revision: str | None,
    occurred_at: str | None,
) -> str: ...
```

Validation rules:

- Required string fields are non-empty after `strip()`.
- Sequence fields are tuples.
- Literal fields are validated explicitly.
- `TimelineEvidenceRef.vault_id` is always required.
- `source_kind="document"` requires `document_id`, `path`, and `content_hash`.
- `source_kind` values ending in `_status` require `backend_kind` and `scope_key`.
- `TimelineItem.evidence` is non-empty unless `origin == "warning"`.
- `origin == "warning"` requires at least one `MemoryWarning`.
- `MemoryWarning.affected_vault_ids` must remain non-empty through the reused Phase 6B validator.
- `item_id` starts with `timeline:<origin>:` and ends with 24 hex characters.
- `sort_key` uses `occurred_at` when present and `no-time:<vault_id>:<path-or-backend>:<item_id>` otherwise.

Service rules:

- Validate `limit` as `1..50`; raise `MemoryProjectionError("invalid_memory_limit: ...")` for invalid service calls.
- Parse `since` with `parse_timeline_since(...)`; raise `MemoryProjectionError("invalid_timeline_since: ...")` for invalid service calls.
- Treat timezone-naive `since` values as UTC by explicitly attaching `UTC`.
- Normalize accepted `since` values to UTC ISO-8601 strings.
- Call `status_service.status(scope=actual_scope)` once per actual Vault scope
  so vector/graph status items do not smear one Vault's state across another
  Vault group.
- Raise `MemoryProjectionError("metadata_unavailable: ...")` when any selected
  actual-scope metadata status is unavailable or schema-incompatible.
- Call `metadata_store.list_recent_documents(actual_scope, since=normalized_since, limit=limit)`
  once per actual Vault scope.
- Do not call `metadata_store.list_documents(...)` from `TimelineMemoryService`
  in Phase 6C.
- Do not read chunk evidence or Vault source files directly.
- Do not call `VaultLoader`, `IndexService.run_apply(...)`, retrieval, graph traversal, vector search, or context-pack builders.
- Do not create stores, run migrations, repair stale indexes, or write status files.

Timeline item rules:

- `document_snapshot_change` items are built from `DocumentSnapshot` and use `last_indexed_at or last_seen_at`.
- Document summaries describe indexed state only: path, kind, content hash, raw SHA-256, metadata index revision, and Vault revision.
- `index_change` items cover metadata and vector status. Metadata has `occurred_at=None` until a status timestamp exists.
- `projection_change` items cover graph status. MCP runtime caches are not timeline items.
- `warning` items cover stale/missing/unavailable projection state and safe recovery hints.
- Since filtering applies only to `occurred_at`.
- With `since` set, status/projection items whose `occurred_at` is `None` are
  excluded and a top-level `timeline_items_without_timestamps_excluded` warning
  is emitted.
- With `since` unset, status/projection items whose `occurred_at` is `None` are
  included after timestamped items and carry item-level
  `missing_timeline_timestamp` warnings.
- Per-Vault limit is applied after grouping and ordering.
- Ordering is descending `occurred_at`, then `vault_id`, then normalized path/backend kind, then `item_id`.

### `src/vault_graph/memory/health_explorer.py`

Public API:

```python
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal, TYPE_CHECKING

from vault_graph.errors import MemoryProjectionError
from vault_graph.ingestion.query_scope_resolution import actual_query_scopes
from vault_graph.ingestion.vault_catalog import QueryScope, VaultCatalog
from vault_graph.memory.memory_models import MemoryWarning
from vault_graph.memory.timeline_memory import TimelineStatusService

if TYPE_CHECKING:
    from vault_graph.app.index_service import StatusReport

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

Service rules:

- Use `status_report` when supplied; otherwise request one aggregate status report for the requested scope.
- Convert metadata, keyword, vector, and graph fields from `StatusReport` into `BackendReadinessRecord` values.
- Treat keyword as metadata-coupled in Phase 6C and state that in `message`.
- Append runtime-cache records supplied by the MCP layer; do not import MCP cache classes.
- Append static scale-up readiness records for metadata/Postgres, vector/Qdrant, and graph/Neo4j.
- Scale-up readiness is a status/schema-derived contract check only.
- `migration_required=True` means data movement would be required before using the target backend; it must not run any migration.
- Missing metadata degrades all scale-up readiness because identity-contract health cannot be proven.
- Stale vector or graph state degrades its readiness when logical fields still exist.
- Runtime-cache records expose counts and capacity only, never cached context packs or explanation records.

## Implementation Tasks

### Task 1: Expose Vector And Graph Status Timestamps

**Files:**

- Modify: `src/vault_graph/app/index_service.py`
- Modify: `src/vault_graph/mcp/mcp_tool_serialization.py`
- Modify: `tests/test_mcp_tools.py`
- Modify: `tests/test_mcp_tool_serialization.py`
- Modify: `tests/test_index_service_vector_reconcile.py`
- Modify: `tests/test_index_service_graph_reconcile.py`

- [ ] **Step 1: Write failing status serialization test**

Add to `tests/test_mcp_tool_serialization.py`:

```python
from vault_graph.app.index_service import StatusReport
from vault_graph.graph.graph_readiness import GraphReadiness
from vault_graph.ingestion.vault_catalog import QueryScope
from vault_graph.mcp.mcp_tool_serialization import status_report_to_payload


def make_status_report_for_serialization() -> StatusReport:
    return StatusReport(
        active_vault_id="main",
        vaults=(("main", "/vault"),),
        metadata_ok=True,
        metadata_schema_compatible=True,
        metadata_message="ok",
        vector_ok=True,
        vector_backend="chroma",
        vector_schema_compatible=True,
        vector_message="ok",
        embedding_model="deterministic",
        embedding_model_version="test",
        embedding_dimensions=4,
        embedding_spec_version="embedding-spec-v1",
        embedding_batch_size=8,
        embedding_parallelism=None,
        embedding_lazy_load=True,
        vector_revision="vector-1",
        vector_last_success_at="2026-06-18T01:00:00+00:00",
        vector_last_error_at=None,
        vector_stale_count=0,
        vector_last_error=None,
        vector_status_scope="main:wiki",
        graph_readiness=GraphReadiness(
            backend_name="sqlite",
            backend_available=True,
            schema_version="graph-store-v1",
            schema_compatible=True,
            graph_extraction_spec_version="graph-extraction-spec-v2",
            graph_extraction_spec_digest="0" * 64,
            graph_extraction_spec_compatible=True,
            freshness="fresh",
            stale_count=0,
            tombstone_count=0,
            last_graph_revision="graph-1",
            affected_vault_ids=("main",),
            scope_readiness=(),
            warnings=(),
            recovery_hint="",
        ),
        graph_status_scope="main:wiki",
        graph_last_success_revision="graph-status-1",
        graph_last_success_at="2026-06-18T02:00:00+00:00",
        graph_last_error_at=None,
        graph_last_error=None,
    )


def test_status_report_payload_includes_vector_and_graph_run_timestamps() -> None:
    report = make_status_report_for_serialization()

    payload = status_report_to_payload(
        report,
        selected_scope=QueryScope(vault_ids=("main",), content_scopes=("wiki",)),
    )

    vector = payload["vector"]
    graph = payload["graph"]
    assert isinstance(vector, dict)
    assert isinstance(graph, dict)
    assert vector["last_success_at"] == "2026-06-18T01:00:00+00:00"
    assert vector["last_error_at"] is None
    assert graph["last_success_revision"] == "graph-status-1"
    assert graph["last_success_at"] == "2026-06-18T02:00:00+00:00"
    assert graph["last_error_at"] is None
```

- [ ] **Step 2: Run the focused failing test**

Run:

```bash
uv run --python 3.12 pytest tests/test_mcp_tool_serialization.py::test_status_report_payload_includes_vector_and_graph_run_timestamps -q
```

Expected: FAIL because `StatusReport` and `status_report_to_payload(...)` do not expose the new timestamp fields.

- [ ] **Step 3: Extend `StatusReport` and test fixture**

In `src/vault_graph/app/index_service.py`, add fields in the positions defined in the component spec. In `tests/test_mcp_tools.py::make_status_report`, keep the existing `graph_readiness=GraphReadiness(...)` fixture body unchanged and insert these new values around the existing vector and graph status fields:

```python
        vector_revision="vector-1",
        vector_last_success_at="2026-06-18T01:00:00+00:00",
        vector_last_error_at=None,
        vector_stale_count=0,
        vector_last_error=None,
        vector_status_scope="main:wiki",
        graph_status_scope="main:wiki",
        graph_last_success_revision="graph-status-1",
        graph_last_success_at="2026-06-18T02:00:00+00:00",
        graph_last_error_at=None,
        graph_last_error=None,
```

Update every direct `StatusReport(...)` construction by using the same field order.

- [ ] **Step 4: Populate fields in `IndexService.status(...)`**

Use the vector and graph run status already read by the service:

```python
vector_last_success_at=run_status.last_success_at if run_status is not None else None,
vector_last_error_at=run_status.last_error_at if run_status is not None else None,
graph_last_success_revision=graph_run_status.last_success_revision if graph_run_status is not None else None,
graph_last_success_at=graph_run_status.last_success_at if graph_run_status is not None else None,
graph_last_error_at=graph_run_status.last_error_at if graph_run_status is not None else None,
```

- [ ] **Step 5: Serialize new fields through MCP status payload**

In `src/vault_graph/mcp/mcp_tool_serialization.py::status_report_to_payload`, add:

```python
"vector": {
    ...
    "last_success_at": report.vector_last_success_at,
    "last_error_at": report.vector_last_error_at,
    ...
},
"graph": {
    ...
    "last_success_revision": report.graph_last_success_revision,
    "last_success_at": report.graph_last_success_at,
    "last_error_at": report.graph_last_error_at,
},
```

- [ ] **Step 6: Add status-store timestamp regression tests**

Add assertions in existing vector and graph reconcile tests after reading status:

```python
assert status.last_success_at is not None
assert status.last_error_at is None
```

For failure tests:

```python
assert status.last_error_at is not None
```

- [ ] **Step 7: Run verification**

Run:

```bash
uv run --python 3.12 pytest tests/test_mcp_tool_serialization.py tests/test_mcp_tools.py tests/test_index_service_vector_reconcile.py tests/test_index_service_graph_reconcile.py -q
```

Expected: PASS.

### Task 2: Add Timeline DTOs, Timestamp Parsing, And Stable IDs

**Files:**

- Create: `src/vault_graph/memory/timeline_memory.py`
- Modify: `src/vault_graph/memory/__init__.py`
- Create: `tests/test_timeline_memory_service.py`
- Modify: `tests/test_mcp_import_boundaries.py`

- [ ] **Step 1: Write failing DTO tests**

Create `tests/test_timeline_memory_service.py` with:

```python
from __future__ import annotations

from datetime import UTC, datetime

import pytest

from vault_graph.errors import MemoryProjectionError
from vault_graph.ingestion.vault_catalog import QueryScope
from vault_graph.memory.memory_models import MemoryBackendRevision, MemoryWarning
from vault_graph.memory.timeline_memory import (
    RecentChangesProjection,
    TimelineEvidenceRef,
    TimelineItem,
    TimelineVault,
    parse_timeline_since,
    stable_timeline_item_id,
)


def warning(code: str = "missing_timeline_timestamp") -> MemoryWarning:
    return MemoryWarning(
        code=code,
        message="timeline timestamp is missing",
        severity="warning",
        affected_vault_ids=("main",),
        recovery_hint="Re-index the selected scope to refresh indexed timestamps.",
    )


def document_evidence() -> TimelineEvidenceRef:
    return TimelineEvidenceRef(
        source_kind="document",
        vault_id="main",
        document_id="doc-1",
        path="wiki/page.md",
        content_hash="hash",
        raw_sha256="raw",
        metadata_index_revision="metadata-1",
        vault_revision="vault-1",
    )


def status_evidence() -> TimelineEvidenceRef:
    return TimelineEvidenceRef(
        source_kind="vector_status",
        vault_id="main",
        backend_kind="vector",
        backend_revision="vector-1",
        scope_key="main:wiki",
    )


def item(**overrides: object) -> TimelineItem:
    values: dict[str, object] = {
        "item_id": "timeline:document_snapshot_change:0123456789abcdef01234567",
        "origin": "document_snapshot_change",
        "title": "Indexed document: wiki/page.md",
        "summary": "Indexed document state changed.",
        "vault_id": "main",
        "occurred_at": "2026-06-18T00:00:00+00:00",
        "sort_key": "2026-06-18T00:00:00+00:00",
        "evidence": (document_evidence(),),
        "store_revisions": (MemoryBackendRevision(kind="metadata", revision="metadata-1", vault_id="main", scope_key="main:wiki"),),
        "warnings": (),
    }
    values.update(overrides)
    return TimelineItem(**values)  # type: ignore[arg-type]


def test_timeline_item_requires_evidence_unless_warning_origin() -> None:
    with pytest.raises(MemoryProjectionError, match="evidence"):
        item(evidence=())

    warning_item = item(
        item_id="timeline:warning:0123456789abcdef01234567",
        origin="warning",
        evidence=(),
        warnings=(warning("vector_unavailable"),),
    )
    assert warning_item.origin == "warning"


def test_timeline_evidence_validates_document_and_status_shapes() -> None:
    with pytest.raises(MemoryProjectionError, match="document_id"):
        TimelineEvidenceRef(source_kind="document", vault_id="main", path="wiki/page.md", content_hash="hash")

    assert status_evidence().backend_kind == "vector"

    with pytest.raises(MemoryProjectionError, match="scope_key"):
        TimelineEvidenceRef(source_kind="graph_status", vault_id="main", backend_kind="graph")


def test_warning_item_requires_warning() -> None:
    with pytest.raises(MemoryProjectionError, match="warning"):
        item(item_id="timeline:warning:0123456789abcdef01234567", origin="warning", evidence=(), warnings=())


def test_recent_changes_projection_requires_tuple_fields() -> None:
    vault = TimelineVault(
        vault_id="main",
        display_name="Main",
        items=(item(),),
        warnings=(),
        store_revisions=(),
        freshness="fresh",
    )
    with pytest.raises(MemoryProjectionError, match="actual_scopes"):
        RecentChangesProjection(
            requested_scope=QueryScope(vault_ids=("main",), content_scopes=("wiki",)),
            actual_scopes=[QueryScope(vault_ids=("main",), content_scopes=("wiki",))],  # type: ignore[arg-type]
            since=None,
            limit=20,
            vaults=(vault,),
            warnings=(),
            generated_at="2026-06-18T00:00:00+00:00",
        )


def test_parse_timeline_since_normalizes_timezone_naive_values_to_utc() -> None:
    assert parse_timeline_since("2026-06-18T00:00:00") == "2026-06-18T00:00:00+00:00"
    assert parse_timeline_since("2026-06-18T09:00:00+09:00") == "2026-06-18T00:00:00+00:00"
    assert parse_timeline_since(None) is None

    with pytest.raises(MemoryProjectionError, match="invalid_timeline_since"):
        parse_timeline_since("not-a-date")


def test_stable_timeline_item_id_includes_vault_revision_and_timestamp() -> None:
    base = stable_timeline_item_id(
        origin="document_snapshot_change",
        vault_id="main",
        source_kind="document",
        document_id="doc-1",
        backend_kind=None,
        path="wiki/page.md",
        scope_key=None,
        revision="metadata-1",
        occurred_at="2026-06-18T00:00:00+00:00",
    )

    changed_time = stable_timeline_item_id(
        origin="document_snapshot_change",
        vault_id="main",
        source_kind="document",
        document_id="doc-1",
        backend_kind=None,
        path="wiki/page.md",
        scope_key=None,
        revision="metadata-1",
        occurred_at="2026-06-19T00:00:00+00:00",
    )

    assert base.startswith("timeline:document_snapshot_change:")
    assert len(base) == len("timeline:document_snapshot_change:") + 24
    assert base != changed_time
```

- [ ] **Step 2: Run the failing DTO tests**

Run:

```bash
uv run --python 3.12 pytest tests/test_timeline_memory_service.py -q
```

Expected: FAIL because `timeline_memory.py` does not exist.

- [ ] **Step 3: Implement DTOs and helpers**

Create `src/vault_graph/memory/timeline_memory.py` with the public API from the component spec. Implement helper validators locally:

```python
def _require_non_empty_string(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise MemoryProjectionError(f"{field_name} is required")
    return value.strip()


def _require_tuple(value: object, field_name: str) -> None:
    if not isinstance(value, tuple):
        raise MemoryProjectionError(f"{field_name} must be a tuple")


def _require_one_of(value: object, field_name: str, allowed: tuple[str, ...]) -> None:
    if value not in allowed:
        raise MemoryProjectionError(f"{field_name} must be one of: {', '.join(allowed)}")
```

Implement stable ID:

```python
def stable_timeline_item_id(...) -> str:
    payload = {
        "origin": origin,
        "vault_id": vault_id,
        "source_kind": source_kind,
        "document_id": document_id,
        "backend_kind": backend_kind,
        "path": " ".join((path or "").casefold().split()) or None,
        "scope_key": scope_key,
        "revision": revision,
        "occurred_at": occurred_at,
    }
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
    return f"timeline:{origin}:{digest[:24]}"
```

Implement `parse_timeline_since(...)`:

```python
def parse_timeline_since(value: str | None) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise MemoryProjectionError("invalid_timeline_since: since must be an ISO-8601 timestamp")
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError as exc:
        raise MemoryProjectionError("invalid_timeline_since: since must be an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC).isoformat()
```

- [ ] **Step 4: Add timeline lazy exports**

Add timeline names to `src/vault_graph/memory/__init__.py`:

```python
"TimelineMemoryService",
"RecentChangesProjection",
"TimelineEvidenceRef",
"TimelineItem",
"TimelineVault",
"parse_timeline_since",
"stable_timeline_item_id",
```

Route these names to `vault_graph.memory.timeline_memory`. Add health exports in Task 4 after `health_explorer.py` exists.

- [ ] **Step 5: Add import-boundary test**

Add to `tests/test_mcp_import_boundaries.py`:

```python
def test_timeline_memory_import_is_backend_mcp_and_external_memory_free() -> None:
    code = """
import sys
import vault_graph.memory.timeline_memory
for name in (
    'mcp',
    'mcp.server.fastmcp',
    'chromadb',
    'fastembed',
    'rustworkx',
    'vault_graph.mcp.mcp_tools',
    'vault_graph.storage.local.chroma_vector_store',
    'vault_graph.projection.rustworkx_projection',
    'mem0',
    'memmachine',
):
    if name in sys.modules:
        raise SystemExit(name)
"""
    completed = subprocess.run([sys.executable, "-c", code], check=False, capture_output=True, text=True)
    assert completed.returncode == 0, completed.stderr or completed.stdout
```

- [ ] **Step 6: Run verification**

Run:

```bash
uv run --python 3.12 pytest tests/test_timeline_memory_service.py tests/test_mcp_import_boundaries.py -q
```

Expected: PASS.

### Task 3: Implement `TimelineMemoryService.recent_changes(...)`

**Files:**

- Modify: `src/vault_graph/storage/interfaces/metadata_store.py`
- Modify: `src/vault_graph/storage/local/sqlite_metadata_store.py`
- Modify: `src/vault_graph/memory/timeline_memory.py`
- Modify: `tests/test_sqlite_metadata_store.py`
- Modify: `tests/test_timeline_memory_service.py`

- [ ] **Step 1: Add service fakes and tests**

Append to `tests/test_timeline_memory_service.py`:

```python
from dataclasses import replace
from pathlib import Path
from typing import Any, cast

from vault_graph.app.index_service import StatusReport
from vault_graph.ingestion.document_normalizer import DocumentSnapshot
from tests.test_mcp_tools import make_status_report
from tests.test_sqlite_metadata_store import make_document
from vault_graph.ingestion.vault_catalog import VaultCatalog, VaultCatalogEntry
from vault_graph.memory.timeline_memory import TimelineMemoryService


class FakeMetadataStore:
    def __init__(self, documents_by_vault: dict[str, tuple[object, ...]]) -> None:
        self.documents_by_vault = documents_by_vault
        self.calls: list[QueryScope] = []

    def list_documents(self, scope: QueryScope) -> tuple[object, ...]:
        del scope
        raise AssertionError("TimelineMemoryService must use list_recent_documents")

    def list_recent_documents(
        self,
        scope: QueryScope,
        *,
        since: str | None = None,
        limit: int = 20,
    ) -> tuple[object, ...]:
        del since
        self.calls.append(scope)
        return self.documents_by_vault.get(scope.vault_ids[0], ())[:limit]


class FakeStatusService:
    def __init__(self, report: object) -> None:
        self.report = report
        self.calls: list[QueryScope | None] = []

    def status(self, *, scope: QueryScope | None = None) -> object:
        self.calls.append(scope)
        return self.report


class PerVaultStatusService:
    def __init__(self, reports_by_vault: dict[str, object]) -> None:
        self.reports_by_vault = reports_by_vault
        self.calls: list[QueryScope | None] = []

    def status(self, *, scope: QueryScope | None = None) -> object:
        self.calls.append(scope)
        assert scope is not None
        return self.reports_by_vault[scope.vault_ids[0]]


def catalog(tmp_path: Path) -> VaultCatalog:
    main_root = tmp_path / "main"
    work_root = tmp_path / "work"
    main_root.mkdir()
    work_root.mkdir()
    return VaultCatalog.from_entries(
        entries=(
            VaultCatalogEntry.from_root(vault_id="main", root_path=main_root, display_name="Main"),
            VaultCatalogEntry.from_root(vault_id="work", root_path=work_root, display_name="Work"),
        ),
        active_vault_id="main",
    )


def document(
    vault_id: str,
    path: str,
    content_hash: str,
    *,
    last_seen_at: str,
    last_indexed_at: str | None,
) -> DocumentSnapshot:
    return replace(
        make_document(vault_id, path, content_hash),
        last_seen_at=last_seen_at,
        last_indexed_at=last_indexed_at,
        index_revision=f"metadata-{vault_id}",
        vault_revision=f"vault-{vault_id}",
    )


def status_report_without_timeline_timestamps() -> StatusReport:
    return replace(
        make_status_report(),
        vector_last_success_at=None,
        vector_last_error_at=None,
        graph_last_success_revision=None,
        graph_last_success_at=None,
        graph_last_error_at=None,
    )


def test_recent_changes_prefers_last_indexed_at_and_groups_per_vault(tmp_path: Path) -> None:
    docs = {
        "main": (document("main", "wiki/page.md", "hash-1", last_seen_at="2026-06-18T00:00:00+00:00", last_indexed_at="2026-06-18T01:00:00+00:00"),),
        "work": (document("work", "wiki/page.md", "hash-2", last_seen_at="2026-06-18T02:00:00+00:00", last_indexed_at=None),),
    }
    service = TimelineMemoryService(
        catalog=catalog(tmp_path),
        metadata_store=cast(Any, FakeMetadataStore(docs)),
        status_service=cast(Any, FakeStatusService(status_report_without_timeline_timestamps())),
        clock=lambda: datetime(2026, 6, 18, 3, tzinfo=UTC),
    )

    projection = service.recent_changes(
        requested_scope=QueryScope(vault_ids=("main", "work"), content_scopes=("wiki",)),
        limit=20,
    )

    assert [vault.vault_id for vault in projection.vaults] == ["main", "work"]
    main_item = projection.vaults[0].items[0]
    work_item = projection.vaults[1].items[0]
    assert main_item.origin == "document_snapshot_change"
    assert main_item.occurred_at == "2026-06-18T01:00:00+00:00"
    assert work_item.vault_id == "work"
    assert main_item.item_id != work_item.item_id


def test_recent_changes_since_filters_timestamped_items_and_warns_for_excluded_untimestamped_items(
    tmp_path: Path,
) -> None:
    docs = {
        "main": (
            document("main", "wiki/old.md", "old", last_seen_at="2026-06-17T00:00:00+00:00", last_indexed_at=None),
            document("main", "wiki/new.md", "new", last_seen_at="2026-06-19T00:00:00+00:00", last_indexed_at=None),
        ),
    }
    service = TimelineMemoryService(
        catalog=catalog(tmp_path),
        metadata_store=cast(Any, FakeMetadataStore(docs)),
        status_service=cast(Any, FakeStatusService(status_report_without_timeline_timestamps())),
    )

    projection = service.recent_changes(
        requested_scope=QueryScope(vault_ids=("main",), content_scopes=("wiki",)),
        since="2026-06-18T00:00:00+00:00",
        limit=20,
    )

    titles = [item.title for item in projection.vaults[0].items]
    assert titles == ["Indexed document: wiki/new.md"]
    assert any(warning.code == "timeline_items_without_timestamps_excluded" for warning in projection.warnings)


def test_recent_changes_applies_limit_per_vault_after_grouping(tmp_path: Path) -> None:
    docs = {
        "main": (
            document("main", "wiki/a.md", "a", last_seen_at="2026-06-18T00:00:00+00:00", last_indexed_at=None),
            document("main", "wiki/b.md", "b", last_seen_at="2026-06-19T00:00:00+00:00", last_indexed_at=None),
        ),
        "work": (
            document("work", "wiki/a.md", "a", last_seen_at="2026-06-18T00:00:00+00:00", last_indexed_at=None),
            document("work", "wiki/b.md", "b", last_seen_at="2026-06-19T00:00:00+00:00", last_indexed_at=None),
        ),
    }
    service = TimelineMemoryService(
        catalog=catalog(tmp_path),
        metadata_store=cast(Any, FakeMetadataStore(docs)),
        status_service=cast(Any, FakeStatusService(status_report_without_timeline_timestamps())),
    )

    projection = service.recent_changes(
        requested_scope=QueryScope(vault_ids=("main", "work"), content_scopes=("wiki",)),
        limit=1,
    )

    assert [len(vault.items) for vault in projection.vaults] == [1, 1]
    assert [vault.items[0].title for vault in projection.vaults] == [
        "Indexed document: wiki/b.md",
        "Indexed document: wiki/b.md",
    ]


def test_recent_changes_uses_bounded_recent_document_listing_per_actual_scope(tmp_path: Path) -> None:
    metadata = FakeMetadataStore(
        {
            "main": tuple(
                document(
                    "main",
                    f"wiki/{index}.md",
                    f"hash-{index}",
                    last_seen_at=f"2026-06-{index + 1:02d}T00:00:00+00:00",
                    last_indexed_at=None,
                )
                for index in range(30)
            )
        }
    )
    service = TimelineMemoryService(
        catalog=catalog(tmp_path),
        metadata_store=cast(Any, metadata),
        status_service=cast(Any, FakeStatusService(status_report_without_timeline_timestamps())),
    )

    projection = service.recent_changes(
        requested_scope=QueryScope(vault_ids=("main",), content_scopes=("wiki",)),
        limit=20,
    )

    assert len(metadata.calls) == 1
    assert len(projection.vaults[0].items) == 20


def test_recent_changes_reads_status_per_actual_vault_scope(tmp_path: Path) -> None:
    docs = {
        "main": (document("main", "wiki/main.md", "main", last_seen_at="2026-06-18T00:00:00+00:00", last_indexed_at=None),),
        "work": (document("work", "wiki/work.md", "work", last_seen_at="2026-06-18T00:00:00+00:00", last_indexed_at=None),),
    }
    status_service = PerVaultStatusService(
        {
            "main": status_report_without_timeline_timestamps(),
            "work": replace(
                status_report_without_timeline_timestamps(),
                vector_ok=False,
                vector_backend="none",
                vector_schema_compatible=False,
                vector_message="not configured",
            ),
        }
    )
    service = TimelineMemoryService(
        catalog=catalog(tmp_path),
        metadata_store=cast(Any, FakeMetadataStore(docs)),
        status_service=cast(Any, status_service),
    )

    projection = service.recent_changes(
        requested_scope=QueryScope(vault_ids=("main", "work"), content_scopes=("wiki",)),
        limit=20,
    )

    assert [call.vault_ids for call in status_service.calls if call is not None] == [("main",), ("work",)]
    main_warning_codes = [warning.code for item in projection.vaults[0].items for warning in item.warnings]
    work_warning_codes = [warning.code for item in projection.vaults[1].items for warning in item.warnings]
    assert "vector_unavailable" not in main_warning_codes
    assert "vector_unavailable" in work_warning_codes


def test_recent_changes_metadata_unavailable_is_fatal(tmp_path: Path) -> None:
    report = replace(make_status_report(), metadata_ok=False, metadata_message="not initialized")
    service = TimelineMemoryService(
        catalog=catalog(tmp_path),
        metadata_store=cast(Any, FakeMetadataStore({})),
        status_service=cast(Any, FakeStatusService(report)),
    )

    with pytest.raises(MemoryProjectionError, match="metadata_unavailable"):
        service.recent_changes(requested_scope=QueryScope(vault_ids=("main",), content_scopes=("wiki",)))
```

- [ ] **Step 2: Run failing service tests**

Run:

```bash
uv run --python 3.12 pytest tests/test_timeline_memory_service.py -q
```

Expected: FAIL because `TimelineMemoryService.recent_changes(...)` has no implementation.

- [ ] **Step 3: Add bounded metadata-store recent document listing**

In `src/vault_graph/storage/interfaces/metadata_store.py`, add `list_recent_documents(...)` from the component spec.

In `src/vault_graph/storage/local/sqlite_metadata_store.py`, implement a bounded SQL query:

```python
from vault_graph.errors import MetadataStoreError


def list_recent_documents(
    self,
    scope: QueryScope,
    *,
    since: str | None = None,
    limit: int = 20,
) -> tuple[DocumentSnapshot, ...]:
    if limit < 1:
        raise MetadataStoreError("invalid_metadata_limit: limit must be positive")
    if not scope.vault_ids or not self._database_path.exists():
        return ()
    observed_at = "COALESCE(last_indexed_at, last_seen_at)"
    path_clause, path_params = _content_scope_sql_clause(scope.content_scopes)
    since_clause = f"AND {observed_at} >= ?" if since is not None else ""
    params = (*scope.vault_ids, *path_params, *((since,) if since is not None else ()), limit)
    vault_placeholders = ", ".join("?" for _ in scope.vault_ids)
    with self._connect() as connection:
        rows = connection.execute(
            f"""
            SELECT vault_id, document_id, path, kind, frontmatter_json, frontmatter_hash,
                   content_hash, raw_sha256, parser_version, last_seen_at, last_indexed_at,
                   vault_revision, index_revision, {observed_at} AS observed_at
            FROM documents
            WHERE vault_id IN ({vault_placeholders})
              AND is_tombstoned = 0
              AND {path_clause}
              {since_clause}
            ORDER BY observed_at DESC, vault_id, path, document_id
            LIMIT ?
            """,
            params,
        ).fetchall()
    return tuple(_document_snapshot_from_row(row) for row in rows)
```

Add a small private `_content_scope_sql_clause(content_scopes)` helper that returns:

```sql
(path = ? OR path LIKE ? OR ...)
```

with parameters such as `("wiki", "wiki/%")`. Keep `_path_in_content_scope(...)`
for existing callers.

Add tests to `tests/test_sqlite_metadata_store.py`:

```python
def test_list_recent_documents_filters_orders_and_limits_in_sqlite(tmp_path: Path) -> None:
    store = SQLiteMetadataStore(tmp_path / "metadata.sqlite3", initialize=True)
    docs = [
        replace(make_document("main", "wiki/old.md", "old"), last_seen_at="2026-06-17T00:00:00+00:00"),
        replace(make_document("main", "wiki/new.md", "new"), last_seen_at="2026-06-19T00:00:00+00:00"),
        replace(make_document("main", "docs/out.md", "out"), last_seen_at="2026-06-20T00:00:00+00:00"),
    ]
    store.apply_metadata_revision(index_revision="metadata-1", documents=docs, chunks=[], tombstones=[])

    recent = store.list_recent_documents(
        QueryScope(vault_ids=("main",), content_scopes=("wiki",)),
        since="2026-06-18T00:00:00+00:00",
        limit=1,
    )

    assert [document.path for document in recent] == ["wiki/new.md"]
```

- [ ] **Step 4: Implement service flow**

In `TimelineMemoryService.recent_changes(...)`:

```python
normalized_since = parse_timeline_since(since)
_validate_limit(limit)
actual_scopes = actual_query_scopes(catalog=self._catalog, scope=requested_scope)
status_reports = tuple(self._status_service.status(scope=actual_scope) for actual_scope in actual_scopes)
for status_report in status_reports:
    if not status_report.metadata_ok or not status_report.metadata_schema_compatible:
        raise MemoryProjectionError(f"metadata_unavailable: {status_report.metadata_message}")
generated_at = (self._clock or _utc_now)().astimezone(UTC).isoformat()
```

For each actual scope:

```python
status_report = status_reports[index]
documents = self._metadata_store.list_recent_documents(
    actual_scope,
    since=normalized_since,
    limit=limit,
)
items = [
    _document_timeline_item(document=document, scope_key=_scope_key(actual_scope))
    for document in documents
]
items.extend(_status_timeline_items(report=status_report, actual_scope=actual_scope))
items = _filter_sort_and_limit(items, since=normalized_since, limit=limit, top_level_warnings=warnings)
```

- [ ] **Step 5: Implement document, status, and warning item builders**

Use exact origin names:

```python
origin="document_snapshot_change"
origin="index_change"
origin="projection_change"
origin="warning"
```

Document summary format:

```python
summary = (
    f"Indexed document snapshot for {document.path}; kind={document.kind}; "
    f"content_hash={document.content_hash}; raw_sha256={document.raw_sha256}; "
    f"metadata_revision={document.index_revision}; vault_revision={document.vault_revision}."
)
```

Recovery hints:

```python
METADATA_RECOVERY_HINT = "Run vg index, then vg status for the selected Vault."
VECTOR_RECOVERY_HINT = "Run vg index for the selected scope to refresh vector state."
GRAPH_RECOVERY_HINT = "Run vg index for the selected scope, then vg status."
TIMESTAMP_RECOVERY_HINT = "Re-index the selected scope to refresh indexed timestamps."
```

- [ ] **Step 6: Add vector/graph unavailable warning tests**

Add tests where `vector_ok=False` and graph readiness freshness is `"missing"`. Assert timeline returns warning items, not fatal errors:

```python
assert any(item.origin == "warning" and item.vault_id == "main" for item in projection.vaults[0].items)
```

- [ ] **Step 7: Run verification**

Run:

```bash
uv run --python 3.12 pytest tests/test_sqlite_metadata_store.py tests/test_timeline_memory_service.py -q
```

Expected: PASS.

### Task 4: Add Health Explorer DTOs And Service

**Files:**

- Create: `src/vault_graph/memory/health_explorer.py`
- Modify: `src/vault_graph/memory/__init__.py`
- Create: `tests/test_health_explorer_service.py`
- Modify: `tests/test_mcp_import_boundaries.py`

- [ ] **Step 1: Write failing health tests**

Create `tests/test_health_explorer_service.py`:

```python
from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

from tests.test_mcp_tools import make_status_report
from vault_graph.ingestion.vault_catalog import QueryScope, VaultCatalog, VaultCatalogEntry
from vault_graph.memory.health_explorer import HealthExplorerService, McpRuntimeCacheRecord


class FakeStatusService:
    def __init__(self, report: object) -> None:
        self.report = report
        self.calls: list[QueryScope | None] = []

    def status(self, *, scope: QueryScope | None = None) -> object:
        self.calls.append(scope)
        return self.report


def catalog(tmp_path: Path) -> VaultCatalog:
    vault_root = tmp_path / "main"
    vault_root.mkdir()
    return VaultCatalog.from_entries(
        entries=(VaultCatalogEntry.from_root(vault_id="main", root_path=vault_root, display_name="Main"),),
        active_vault_id="main",
    )


def test_health_explorer_maps_backend_readiness_and_scale_up_records(tmp_path: Path) -> None:
    service = HealthExplorerService(
        catalog=catalog(tmp_path),
        status_service=cast(Any, FakeStatusService(make_status_report())),
        clock=lambda: datetime(2026, 6, 18, 4, tzinfo=UTC),
    )

    report = service.inspect(requested_scope=QueryScope(vault_ids=("main",), content_scopes=("wiki",)))

    kinds = [record.backend_kind for record in report.backends]
    assert kinds == ["metadata", "keyword", "vector", "graph"]
    assert report.backends[0].status == "ready"
    assert report.scale_up_adapters[0].adapter_kind == "metadata"
    assert report.scale_up_adapters[0].target_backend == "postgres"
    assert report.scale_up_adapters[0].migration_required is True
    assert report.generated_at == "2026-06-18T04:00:00+00:00"


def test_health_explorer_uses_supplied_status_report_without_second_status_call(tmp_path: Path) -> None:
    fake_status = FakeStatusService(make_status_report())
    service = HealthExplorerService(catalog=catalog(tmp_path), status_service=cast(Any, fake_status))

    service.inspect(
        requested_scope=QueryScope(vault_ids=("main",), content_scopes=("wiki",)),
        status_report=make_status_report(),
    )

    assert fake_status.calls == []


def test_health_explorer_marks_runtime_cache_at_capacity_as_degraded(tmp_path: Path) -> None:
    service = HealthExplorerService(
        catalog=catalog(tmp_path),
        status_service=cast(Any, FakeStatusService(make_status_report())),
    )

    report = service.inspect(
        requested_scope=QueryScope(vault_ids=("main",), content_scopes=("wiki",)),
        runtime_caches=(
            McpRuntimeCacheRecord(
                cache_name="result_explanation",
                current_entries=256,
                max_entries=256,
                status="degraded",
                message="cache is at capacity",
            ),
        ),
    )

    assert report.runtime_caches[0].status == "degraded"
    assert report.runtime_caches[0].current_entries == 256


def test_health_explorer_degrades_scale_up_readiness_when_metadata_is_unavailable(tmp_path: Path) -> None:
    service = HealthExplorerService(
        catalog=catalog(tmp_path),
        status_service=cast(Any, FakeStatusService(make_status_report())),
    )
    report = service.inspect(
        requested_scope=QueryScope(vault_ids=("main",), content_scopes=("wiki",)),
        status_report=replace(make_status_report(), metadata_ok=False, metadata_schema_compatible=False),
    )

    assert all(adapter.contract_ready is False for adapter in report.scale_up_adapters)
    assert any(warning.code == "metadata_unavailable" for warning in report.warnings)
```

- [ ] **Step 2: Run failing health tests**

Run:

```bash
uv run --python 3.12 pytest tests/test_health_explorer_service.py -q
```

Expected: FAIL because `health_explorer.py` does not exist.

- [ ] **Step 3: Implement DTOs and validation**

Create `src/vault_graph/memory/health_explorer.py` with the public API from the component spec. Validate:

```python
if record.current_entries < 0:
    raise MemoryProjectionError("current_entries must be non-negative")
if record.max_entries <= 0:
    raise MemoryProjectionError("max_entries must be positive")
if record.current_entries > record.max_entries:
    raise MemoryProjectionError("current_entries cannot exceed max_entries")
```

- [ ] **Step 4: Add health lazy exports**

Add health names to `src/vault_graph/memory/__init__.py`:

```python
"BackendReadinessRecord",
"HealthExplorerReport",
"HealthExplorerService",
"McpRuntimeCacheRecord",
"ScaleUpAdapterReadiness",
```

Route these names to `vault_graph.memory.health_explorer`.

- [ ] **Step 5: Implement status-to-backend mapping**

Use this mapping:

```python
metadata_status = "ready" if report.metadata_ok and report.metadata_schema_compatible else "unavailable"
keyword_status = metadata_status
vector_status = (
    "ready"
    if report.vector_ok and report.vector_schema_compatible and report.vector_stale_count == 0 and not report.vector_last_error
    else "degraded"
    if report.vector_revision or report.vector_last_success_at
    else "unavailable"
)
graph_status = (
    "ready"
    if report.graph_readiness.backend_available
    and report.graph_readiness.schema_compatible
    and report.graph_readiness.freshness == "fresh"
    and not report.graph_last_error
    else "degraded"
    if report.graph_last_success_revision or report.graph_readiness.last_graph_revision
    else "unavailable"
)
```

- [ ] **Step 6: Implement static scale-up readiness records**

Return exactly three records:

```python
("metadata", "postgres", "metadata")
("vector", "qdrant", "vector")
("graph", "neo4j", "graph")
```

Messages must state that no record-level migration audit was performed. Example:

```python
message="metadata contract appears ready from local status/schema fields; no record-level migration audit was performed"
```

- [ ] **Step 7: Add import-boundary test**

Add to `tests/test_mcp_import_boundaries.py`:

```python
def test_health_explorer_import_is_backend_mcp_and_external_memory_free() -> None:
    code = """
import sys
import vault_graph.memory.health_explorer
for name in (
    'mcp',
    'mcp.server.fastmcp',
    'chromadb',
    'fastembed',
    'rustworkx',
    'vault_graph.mcp.mcp_tools',
    'vault_graph.storage.local.chroma_vector_store',
    'vault_graph.projection.rustworkx_projection',
    'mem0',
    'memmachine',
):
    if name in sys.modules:
        raise SystemExit(name)
"""
    completed = subprocess.run([sys.executable, "-c", code], check=False, capture_output=True, text=True)
    assert completed.returncode == 0, completed.stderr or completed.stdout
```

- [ ] **Step 8: Run verification**

Run:

```bash
uv run --python 3.12 pytest tests/test_health_explorer_service.py tests/test_mcp_import_boundaries.py -q
```

Expected: PASS.

### Task 5: Add MCP Serialization For Recent Changes And Health

**Files:**

- Modify: `src/vault_graph/mcp/mcp_memory_serialization.py`
- Modify: `src/vault_graph/mcp/mcp_tool_serialization.py`
- Modify: `tests/test_mcp_memory_tools.py`
- Modify: `tests/test_mcp_tool_serialization.py`

- [ ] **Step 1: Write failing serialization tests**

Add to `tests/test_mcp_memory_tools.py`:

```python
from typing import cast

from vault_graph.memory.health_explorer import (
    BackendReadinessRecord,
    HealthExplorerReport,
    McpRuntimeCacheRecord,
    ScaleUpAdapterReadiness,
)
from vault_graph.memory.timeline_memory import RecentChangesProjection, TimelineEvidenceRef, TimelineItem, TimelineVault
from vault_graph.mcp.mcp_memory_serialization import (
    health_explorer_report_to_payload,
    recent_changes_projection_to_payload,
    resource_links_for_recent_changes,
    timeline_warnings,
)


def make_recent_changes_projection() -> RecentChangesProjection:
    item = TimelineItem(
        item_id="timeline:document_snapshot_change:0123456789abcdef01234567",
        origin="document_snapshot_change",
        title="Indexed document: wiki/page.md",
        summary="Indexed document state changed.",
        vault_id="main",
        occurred_at="2026-06-18T00:00:00+00:00",
        sort_key="2026-06-18T00:00:00+00:00",
        evidence=(
            TimelineEvidenceRef(
                source_kind="document",
                vault_id="main",
                document_id="doc-1",
                path="wiki/page.md",
                content_hash="hash",
            ),
        ),
        store_revisions=(
            MemoryBackendRevision(kind="metadata", revision="metadata-1", vault_id="main", scope_key="main:wiki"),
        ),
        warnings=(make_warning(),),
    )
    return RecentChangesProjection(
        requested_scope=QueryScope(vault_ids=("main",), content_scopes=("wiki",)),
        actual_scopes=(QueryScope(vault_ids=("main",), content_scopes=("wiki",)),),
        since=None,
        limit=20,
        vaults=(
            TimelineVault(
                vault_id="main",
                display_name="Main",
                items=(item,),
                warnings=(make_warning(),),
                store_revisions=(),
                freshness="fresh",
            ),
        ),
        warnings=(make_warning(),),
        generated_at="2026-06-18T00:00:00+00:00",
    )


def test_recent_changes_payload_preserves_origins_evidence_revisions_and_warnings() -> None:
    payload = recent_changes_projection_to_payload(make_recent_changes_projection())
    vaults = cast(list[dict[str, object]], payload["vaults"])
    vault = vaults[0]
    items = cast(list[dict[str, object]], vault["items"])
    item = items[0]
    evidence = cast(list[dict[str, object]], item["evidence"])
    revisions = cast(list[dict[str, object]], item["store_revisions"])
    item_warnings = cast(list[dict[str, object]], item["warnings"])
    payload_warnings = cast(list[dict[str, object]], payload["warnings"])

    assert item["origin"] == "document_snapshot_change"
    assert evidence[0]["source_kind"] == "document"
    assert revisions[0]["kind"] == "metadata"
    assert item_warnings[0]["code"] == "candidate_decision"
    assert payload_warnings[0]["code"] == "candidate_decision"


def test_recent_changes_links_only_document_backed_items() -> None:
    links = resource_links_for_recent_changes(make_recent_changes_projection())

    assert [link.uri for link in links] == ["vault://main/documents/wiki%2Fpage.md"]
    assert links[0].rel == "document"


def test_timeline_warnings_collect_projection_vault_and_item_warnings() -> None:
    warnings = timeline_warnings(make_recent_changes_projection())

    assert len(warnings) == 3


def test_health_explorer_payload_preserves_backend_runtime_and_scale_up_records() -> None:
    report = HealthExplorerReport(
        requested_scope=QueryScope(vault_ids=("main",), content_scopes=("wiki",)),
        actual_scopes=(QueryScope(vault_ids=("main",), content_scopes=("wiki",)),),
        backends=(
            BackendReadinessRecord(
                backend_kind="metadata",
                backend_name="sqlite",
                vault_id="main",
                scope_key="main:wiki",
                status="ready",
                schema_compatible=True,
                freshness="fresh",
                revision="metadata-1",
                last_success_at=None,
                last_error_at=None,
                message="metadata ready",
                recovery_hint=None,
            ),
        ),
        runtime_caches=(
            McpRuntimeCacheRecord(
                cache_name="context_pack",
                current_entries=1,
                max_entries=32,
                status="ready",
                message="cache ready",
            ),
        ),
        scale_up_adapters=(
            ScaleUpAdapterReadiness(
                adapter_kind="metadata",
                target_backend="postgres",
                configured=False,
                contract_ready=True,
                migration_required=True,
                depends_on_backend_kind="metadata",
                message="metadata contract ready; no record-level migration audit was performed",
            ),
        ),
        warnings=(),
        generated_at="2026-06-18T00:00:00+00:00",
    )

    payload = health_explorer_report_to_payload(report)
    backends = cast(list[dict[str, object]], payload["backends"])
    runtime_caches = cast(list[dict[str, object]], payload["runtime_caches"])
    scale_up_adapters = cast(list[dict[str, object]], payload["scale_up_adapters"])

    assert backends[0]["backend_kind"] == "metadata"
    assert runtime_caches[0]["cache_name"] == "context_pack"
    assert scale_up_adapters[0]["target_backend"] == "postgres"
```

- [ ] **Step 2: Run failing serialization tests**

Run:

```bash
uv run --python 3.12 pytest tests/test_mcp_memory_tools.py -q
```

Expected: FAIL because serializers do not exist.

- [ ] **Step 3: Implement serializers**

In `src/vault_graph/mcp/mcp_memory_serialization.py`, add:

```python
def recent_changes_projection_to_payload(projection: RecentChangesProjection) -> dict[str, object]: ...
def health_explorer_report_to_payload(report: HealthExplorerReport) -> dict[str, object]: ...
def resource_links_for_recent_changes(projection: RecentChangesProjection) -> tuple[McpResourceLink, ...]: ...
def timeline_warnings(projection: RecentChangesProjection) -> tuple[MemoryWarning, ...]: ...
```

Rules:

- Use the existing `query_scope_to_dict(...)` shape.
- Preserve all projection, vault, and item warnings.
- Convert tuples to JSON arrays.
- Build document links only for timeline evidence with `source_kind == "document"` and a path.
- Do not create `vault://.../memory/...` URIs.
- Do not import local backend implementations.

- [ ] **Step 4: Add runtime-cache snapshot helper**

In `mcp_memory_serialization.py`, add:

```python
def runtime_cache_records_for_mcp(
    *,
    context_pack_cache: object,
    result_explanation_cache: object,
) -> tuple[McpRuntimeCacheRecord, ...]:
    return (
        _runtime_cache_record("context_pack", context_pack_cache),
        _runtime_cache_record("result_explanation", result_explanation_cache),
    )
```

Implementation reads only `len(cache)` and `cache.max_entries`. It sets `oldest_cached_at=None` and `newest_cached_at=None` because cache payload timestamps are intentionally not exposed.

- [ ] **Step 5: Extend `status_report_to_payload(...)` with optional health payload**

Change signature:

```python
def status_report_to_payload(
    report: StatusReport,
    *,
    selected_scope: QueryScope,
    health_explorer: dict[str, object] | None = None,
) -> dict[str, object]:
```

Before return:

```python
payload = {...}
if health_explorer is not None:
    payload["health_explorer"] = health_explorer
return payload
```

Existing callers remain valid because `health_explorer` defaults to `None`.

- [ ] **Step 6: Run verification**

Run:

```bash
uv run --python 3.12 pytest tests/test_mcp_memory_tools.py tests/test_mcp_tool_serialization.py -q
```

Expected: PASS.

### Task 6: Add Service Factory Handoff And `get_recent_changes` Tool

**Files:**

- Modify: `src/vault_graph/mcp/mcp_service_factory.py`
- Modify: `src/vault_graph/mcp/mcp_tools.py`
- Modify: `src/vault_graph/mcp/__init__.py`
- Create: `tests/test_mcp_recent_changes_tool.py`
- Modify: `tests/test_mcp_tools.py`
- Modify: `tests/test_mcp_service_factory.py`
- Modify: `tests/test_mcp_stdio_smoke.py`

- [ ] **Step 1: Write failing tool tests**

Create `tests/test_mcp_recent_changes_tool.py`:

```python
from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Any, cast

import pytest

from tests.test_mcp_memory_tools import make_recent_changes_projection
from tests.test_mcp_tools import RecordingFactory, RecordingToolServer, fake_services
from vault_graph.errors import MemoryProjectionError
from vault_graph.ingestion.vault_catalog import QueryScope, VaultCatalog, VaultCatalogEntry
from vault_graph.mcp.context_pack_resource_cache import ContextPackResourceCache
from vault_graph.mcp.mcp_errors import McpProtocolError
from vault_graph.mcp.mcp_service_factory import McpServices
from vault_graph.mcp.mcp_tools import GetRecentChangesInput, McpToolRegistry, parse_get_recent_changes_input, register_mcp_tools
from vault_graph.mcp.result_explanation_cache import ResultExplanationCache


class RecordingTimelineMemoryService:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []
        self.response = make_recent_changes_projection()

    def recent_changes(self, **kwargs: object) -> object:
        self.calls.append(kwargs)
        return self.response


class RecentChangesFactory(RecordingFactory):
    def __init__(self) -> None:
        super().__init__()
        self.timeline_memory_service: object = RecordingTimelineMemoryService()
        self.timeline_calls = 0

    def open_timeline_memory_service(self) -> object:
        self.timeline_calls += 1
        return self.timeline_memory_service


class FailingTimelineMemoryService:
    def recent_changes(self, **kwargs: object) -> object:
        del kwargs
        raise MemoryProjectionError("metadata_unavailable: not initialized")


def fake_multi_vault_services(tmp_path: Path) -> McpServices:
    services = fake_services(tmp_path)
    main_root = tmp_path / "main"
    work_root = tmp_path / "work"
    main_root.mkdir()
    work_root.mkdir()
    catalog = VaultCatalog.from_entries(
        entries=(
            VaultCatalogEntry.from_root(vault_id="main", root_path=main_root, display_name="Main"),
            VaultCatalogEntry.from_root(vault_id="work", root_path=work_root, display_name="Work"),
        ),
        active_vault_id="main",
    )
    return replace(services, catalog=catalog)


def test_parse_get_recent_changes_input_validates_limit_since_and_scope() -> None:
    request = parse_get_recent_changes_input(
        since="2026-06-18T00:00:00",
        scope={"vault_ids": ["main"]},
        limit=20,
    )

    assert request.since == "2026-06-18T00:00:00+00:00"
    assert request.limit == 20
    assert request.scope is not None

    with pytest.raises(McpProtocolError, match="since"):
        parse_get_recent_changes_input(since="not-a-date", limit=20)

    with pytest.raises(McpProtocolError, match="limit"):
        parse_get_recent_changes_input(limit=51)

    with pytest.raises(McpProtocolError):
        parse_get_recent_changes_input(scope={"include_cross_vault": True})


def test_get_recent_changes_uses_timeline_service_and_returns_tool_body(tmp_path: Path) -> None:
    factory = RecentChangesFactory()
    registry = McpToolRegistry(
        services=fake_services(tmp_path),
        service_factory=cast(Any, factory),
        context_pack_cache=ContextPackResourceCache(),
        result_explanation_cache=ResultExplanationCache(),
    )

    body = registry.get_recent_changes(GetRecentChangesInput(limit=7))

    timeline_service = cast(RecordingTimelineMemoryService, factory.timeline_memory_service)
    assert factory.timeline_calls == 1
    assert timeline_service.calls[0]["limit"] == 7
    assert body.tool_name == "get_recent_changes"
    assert body.payload["vaults"]
    assert body.resource_links[0].uri == "vault://main/documents/wiki%2Fpage.md"
    assert body.warnings


def test_register_mcp_tools_includes_phase_6c_tool(tmp_path: Path) -> None:
    server = RecordingToolServer()
    registry = register_mcp_tools(
        server,
        services=fake_services(tmp_path),
        service_factory=cast(Any, RecentChangesFactory()),
        context_pack_cache=ContextPackResourceCache(),
        result_explanation_cache=ResultExplanationCache(),
    )

    assert "get_recent_changes" in registry.tool_names
    assert "get_recent_changes" in server.tools


def test_get_recent_changes_supports_all_vaults_scope(tmp_path: Path) -> None:
    factory = RecentChangesFactory()
    server = RecordingToolServer()
    register_mcp_tools(
        server,
        services=fake_multi_vault_services(tmp_path),
        service_factory=cast(Any, factory),
        context_pack_cache=ContextPackResourceCache(),
        result_explanation_cache=ResultExplanationCache(),
    )

    server.tools["get_recent_changes"](scope={"all_vaults": True})

    timeline_service = cast(RecordingTimelineMemoryService, factory.timeline_memory_service)
    requested_scope = timeline_service.calls[0]["requested_scope"]
    assert isinstance(requested_scope, QueryScope)
    assert requested_scope.vault_ids == ("main", "work")


def test_get_recent_changes_maps_metadata_errors_with_scope_and_recovery_hint(tmp_path: Path) -> None:
    factory = RecentChangesFactory()
    factory.timeline_memory_service = cast(Any, FailingTimelineMemoryService())
    registry = McpToolRegistry(
        services=fake_services(tmp_path),
        service_factory=cast(Any, factory),
        context_pack_cache=ContextPackResourceCache(),
        result_explanation_cache=ResultExplanationCache(),
    )

    with pytest.raises(McpProtocolError) as exc_info:
        registry.get_recent_changes(GetRecentChangesInput())

    assert exc_info.value.payload.code == "metadata_unavailable"
    assert exc_info.value.payload.affected_vault_ids == ("main",)
    assert exc_info.value.payload.recovery_hint == "Run vg index, then vg status for the selected Vault."
```

- [ ] **Step 2: Run failing tool tests**

Run:

```bash
uv run --python 3.12 pytest tests/test_mcp_recent_changes_tool.py -q
```

Expected: FAIL because `GetRecentChangesInput` and tool registration do not exist.

- [ ] **Step 3: Add service factory methods**

In `src/vault_graph/mcp/mcp_service_factory.py`, add:

```python
def open_timeline_memory_service(self) -> TimelineMemoryService:
    from vault_graph.memory.timeline_memory import TimelineMemoryService
    from vault_graph.storage.local.sqlite_metadata_store import SQLiteMetadataStore

    catalog_service, catalog = self._catalog()
    return TimelineMemoryService(
        catalog=catalog,
        metadata_store=SQLiteMetadataStore(catalog_service.metadata_path, initialize=False),
        status_service=self.open_status_service(),
    )


def open_health_explorer_service(self) -> HealthExplorerService:
    from vault_graph.memory.health_explorer import HealthExplorerService

    _, catalog = self._catalog()
    return HealthExplorerService(
        catalog=catalog,
        status_service=self.open_status_service(),
    )
```

Add TYPE_CHECKING imports for `TimelineMemoryService` and `HealthExplorerService`.

- [ ] **Step 4: Add factory read-only test**

In `tests/test_mcp_service_factory.py`, add:

```python
def test_mcp_factory_opens_timeline_and_health_services_without_creating_memory_state(tmp_path: Path) -> None:
    from vault_graph.mcp.mcp_service_factory import McpServiceFactory

    state_path = initialized_state_for_factory(tmp_path)
    factory = McpServiceFactory(state_path=state_path)

    timeline = factory.open_timeline_memory_service()
    health = factory.open_health_explorer_service()

    assert timeline is not None
    assert health is not None
    assert not (state_path / "memory").exists()
    assert not (state_path / "data" / "memory").exists()
```

- [ ] **Step 5: Preserve Phase 6C domain error prefixes**

In `tests/test_mcp_errors.py`, add:

```python
def test_phase_6c_memory_projection_error_prefixes_are_preserved() -> None:
    invalid_since = map_exception_to_mcp_error(MemoryProjectionError("invalid_timeline_since: bad timestamp"))
    unavailable = map_exception_to_mcp_error(MemoryProjectionError("timeline_projection_unavailable: stale status"))

    assert invalid_since.kind == "invalid_parameter"
    assert invalid_since.payload.code == "invalid_timeline_since"
    assert unavailable.kind == "execution"
    assert unavailable.payload.code == "timeline_projection_unavailable"
```

Import `MemoryProjectionError`. In `src/vault_graph/mcp/mcp_errors.py`, add
`invalid_timeline_since` and `timeline_projection_unavailable` to the accepted
domain-code prefix set, and update `_kind_for_domain_code(...)` so
`invalid_timeline_since` maps to `invalid_parameter`.

- [ ] **Step 6: Implement MCP input, parser, registry method, and FastMCP handler**

In `src/vault_graph/mcp/mcp_tools.py`:

```python
from vault_graph.errors import MemoryProjectionError

McpToolName = Literal[
    ...
    "get_recent_changes",
]


@dataclass(frozen=True)
class GetRecentChangesInput:
    since: str | None = None
    scope: McpScopeInput | None = None
    limit: int = 20


def _validate_get_recent_changes_request(request: GetRecentChangesInput) -> None:
    _limit(request.limit)
    if request.scope is not None and request.scope.include_cross_vault:
        raise _invalid_arguments("get_recent_changes does not support include_cross_vault")
```

Parser:

```python
def parse_get_recent_changes_input(
    *,
    since: str | None = None,
    scope: dict[str, object] | None = None,
    limit: int = 20,
) -> GetRecentChangesInput:
    from vault_graph.memory.timeline_memory import parse_timeline_since

    try:
        parsed_since = parse_timeline_since(since)
    except MemoryProjectionError as exc:
        raise _invalid_arguments(str(exc)) from exc
    request = GetRecentChangesInput(
        since=parsed_since,
        scope=mcp_scope_input_from_raw(scope),
        limit=_limit(limit),
    )
    _validate_get_recent_changes_request(request)
    return request
```

Registry method:

```python
def get_recent_changes(self, request: GetRecentChangesInput) -> McpToolBody:
    try:
        _validate_get_recent_changes_request(request)
        selected_scope = _scope_for_tool(request.scope, catalog=self._services.catalog)
        try:
            projection = self._service_factory.open_timeline_memory_service().recent_changes(
                requested_scope=selected_scope,
                since=request.since,
                limit=request.limit,
            )
        except MemoryProjectionError as exc:
            raise map_exception_to_mcp_error(
                exc,
                affected_vault_ids=selected_scope.vault_ids,
                user_state_path=getattr(self._service_factory, "_state_path", None),
            ) from exc
        from vault_graph.mcp.mcp_memory_serialization import (
            memory_warning_to_mcp_error,
            recent_changes_projection_to_payload,
            resource_links_for_recent_changes,
            timeline_warnings,
        )

        return _tool_body(
            tool_name="get_recent_changes",
            payload=recent_changes_projection_to_payload(projection),
            resource_links=resource_links_for_recent_changes(projection),
            warnings=tuple(memory_warning_to_mcp_error(warning) for warning in timeline_warnings(projection)),
        )
    except Exception as exc:
        raise _map_tool_exception(exc, service_factory=self._service_factory) from exc
```

FastMCP handler:

```python
@server.tool("get_recent_changes", structured_output=True)
def get_recent_changes(
    since: str | None = None,
    scope: dict[str, object] | None = None,
    limit: int = 20,
) -> dict[str, object]:
    request = parse_get_recent_changes_input(since=since, scope=scope, limit=limit)
    return registry.get_recent_changes(request).to_json_dict()
```

- [ ] **Step 7: Update exact tool-list expectations**

In `tests/test_mcp_tools.py`, rename the exact test from Phase 6B to Phase 6C and include `"get_recent_changes"` after `"get_open_questions"`. Remove the assertion that it is absent.

In `tests/test_mcp_stdio_smoke.py`, rename `EXPECTED_PHASE_6B_TOOLS` to `EXPECTED_PHASE_6C_TOOLS` and add `"get_recent_changes"`.

- [ ] **Step 8: Add MCP lazy exports if needed**

In `src/vault_graph/mcp/__init__.py`, add:

```python
"GetRecentChangesInput",
"parse_get_recent_changes_input",
```

Route them through the `mcp_tools` lazy export block.

- [ ] **Step 9: Run verification**

Run:

```bash
uv run --python 3.12 pytest tests/test_mcp_recent_changes_tool.py tests/test_mcp_tools.py tests/test_mcp_errors.py tests/test_mcp_service_factory.py tests/test_mcp_stdio_smoke.py -q
```

Expected: PASS, with the smoke test skipped unless `VG_RUN_MCP_STDIO_SMOKE=1`.

### Task 7: Upgrade `vault://{vault_id}/timeline/recent`

**Files:**

- Modify: `src/vault_graph/mcp/mcp_resources.py`
- Create: `tests/test_mcp_timeline_resource.py`
- Modify: `tests/test_mcp_resources.py`
- Modify: `tests/test_mcp_resource_read_only_boundary.py`

- [ ] **Step 1: Write failing resource tests**

Create `tests/test_mcp_timeline_resource.py`:

```python
from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from tests.test_sqlite_metadata_store import make_document
from vault_graph.cli.main import app
from vault_graph.mcp.mcp_errors import McpProtocolError
from vault_graph.mcp.mcp_resources import McpResourceRequest
from vault_graph.mcp.mcp_server import McpServerConfig, create_mcp_server
from vault_graph.storage.local.sqlite_metadata_store import SQLiteMetadataStore

runner = CliRunner()


def test_timeline_recent_resource_returns_single_vault_json(tmp_path: Path) -> None:
    vault_root = tmp_path / "vault"
    vault_root.mkdir()
    state_path = tmp_path / "state"
    assert runner.invoke(app, ["init", "--vault", str(vault_root), "--state", str(state_path)]).exit_code == 0
    document = make_document("default", "wiki/page.md", "hash")
    store = SQLiteMetadataStore(state_path / "metadata" / "metadata.sqlite3", initialize=True)
    store.apply_metadata_revision(index_revision="metadata-1", documents=[document], chunks=[], tombstones=[])
    registered = create_mcp_server(McpServerConfig(state_path=state_path))

    body = registered.resource_registry.read(McpResourceRequest(uri="vault://default/timeline/recent"))

    assert body.content_mime_type == "application/json"
    assert body.metadata["requested_scope"]["vault_ids"] == ["default"]  # type: ignore[index]
    assert body.metadata["limit"] == 20
    assert body.metadata["vaults"][0]["vault_id"] == "default"  # type: ignore[index]
    assert json.loads(body.text) == body.metadata


def test_timeline_recent_resource_maps_metadata_errors_to_vault_scoped_mcp_error(tmp_path: Path) -> None:
    vault_root = tmp_path / "vault"
    vault_root.mkdir()
    state_path = tmp_path / "state"
    assert runner.invoke(app, ["init", "--vault", str(vault_root), "--state", str(state_path)]).exit_code == 0
    registered = create_mcp_server(McpServerConfig(state_path=state_path))

    with pytest.raises(McpProtocolError) as exc_info:
        registered.resource_registry.read(McpResourceRequest(uri="vault://default/timeline/recent"))

    assert exc_info.value.payload.code == "metadata_unavailable"
    assert exc_info.value.payload.affected_vault_ids == ("default",)
    assert exc_info.value.payload.recovery_hint == "Run vg index, then vg status for the selected Vault."
```

- [ ] **Step 2: Run failing resource tests**

Run:

```bash
uv run --python 3.12 pytest tests/test_mcp_timeline_resource.py -q
```

Expected: FAIL because resource still returns the Phase 5B availability error.

- [ ] **Step 3: Implement `read_recent_timeline(...)`**

In `CurrentContextResourceReader.read_recent_timeline(...)`, replace the availability error:

```python
def read_recent_timeline(self, uri: McpResourceUri) -> McpResourceBody:
    vault_id = _required_value(uri.vault_id)
    try:
        projection = self._service_factory.open_timeline_memory_service().recent_changes(
            requested_scope=self._catalog.scope_for_vault_ids((vault_id,)),
            since=None,
            limit=20,
        )
    except MemoryProjectionError as exc:
        raise McpProtocolError(
            kind="execution",
            payload=McpErrorPayload(
                code=_domain_error_code(exc),
                message=str(exc),
                severity="error",
                affected_vault_ids=(vault_id,),
                recovery_hint="Run vg index, then vg status for the selected Vault.",
            ),
        ) from exc
    from vault_graph.mcp.mcp_memory_serialization import (
        memory_warning_to_mcp_error,
        recent_changes_projection_to_payload,
        timeline_warnings,
    )

    payload = recent_changes_projection_to_payload(projection)
    warnings = tuple(memory_warning_to_mcp_error(warning) for warning in timeline_warnings(projection))
    return McpResourceBody(
        uri=uri.normalized_uri,
        content_mime_type="application/json",
        text=json.dumps(payload, sort_keys=True, ensure_ascii=False, indent=2) + "\n",
        metadata=payload,
        warnings=warnings,
    )
```

- [ ] **Step 4: Add read-only resource boundary test**

In `tests/test_mcp_resource_read_only_boundary.py`, add:

```python
def test_timeline_recent_resource_does_not_mutate_vault_or_create_memory_state(tmp_path: Path) -> None:
    vault_root = tmp_path / "vault"
    (vault_root / "wiki").mkdir(parents=True)
    (vault_root / "wiki" / "page.md").write_text("# Page\nVault body\n", encoding="utf-8")
    state_path = initialized_state(tmp_path, vault_root)
    seed_metadata(state_path)
    before = file_bytes(vault_root)
    missing_status_paths = (
        state_path / "vector" / "status.json",
        state_path / "graph" / "status.json",
    )
    registered = create_mcp_server(McpServerConfig(state_path=state_path))

    registered.resource_registry.read(McpResourceRequest(uri="vault://default/timeline/recent"))

    assert file_bytes(vault_root) == before
    assert not (state_path / "memory").exists()
    assert not (state_path / "data" / "memory").exists()
    assert all(not path.exists() for path in missing_status_paths)
```

- [ ] **Step 5: Run verification**

Run:

```bash
uv run --python 3.12 pytest tests/test_mcp_timeline_resource.py tests/test_mcp_resources.py tests/test_mcp_resource_read_only_boundary.py -q
```

Expected: PASS.

### Task 8: Extend `check_index_status` With Health Explorer Payload

**Files:**

- Modify: `src/vault_graph/mcp/mcp_tools.py`
- Modify: `src/vault_graph/mcp/mcp_tool_serialization.py`
- Modify: `src/vault_graph/mcp/mcp_prompts.py`
- Modify: `tests/test_mcp_tools.py`
- Modify: `tests/test_mcp_tool_serialization.py`
- Modify: `tests/test_mcp_prompts.py`

- [ ] **Step 1: Add failing status-health test**

In `tests/test_mcp_tools.py`, extend `RecordingFactory`:

```python
class RecordingHealthExplorerService:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []
        self.response = make_health_explorer_report()

    def inspect(self, **kwargs: object) -> object:
        self.calls.append(kwargs)
        return self.response
```

Add `self.health_explorer_service`, `self.health_calls`, and:

```python
def open_health_explorer_service(self) -> RecordingHealthExplorerService:
    self.health_calls += 1
    return self.health_explorer_service
```

Add helper:

```python
def make_health_explorer_report() -> object:
    from vault_graph.memory.health_explorer import HealthExplorerReport
    return HealthExplorerReport(
        requested_scope=QueryScope(vault_ids=("main",), content_scopes=("wiki",)),
        actual_scopes=(QueryScope(vault_ids=("main",), content_scopes=("wiki",)),),
        backends=(),
        runtime_caches=(),
        scale_up_adapters=(),
        warnings=(),
        generated_at="2026-06-18T00:00:00+00:00",
    )
```

Update `test_check_index_status_uses_status_service_without_indexing`:

```python
assert factory.health_calls == 1
assert factory.health_explorer_service.calls[0]["status_report"] is factory.status_service.report
assert "health_explorer" in body.payload
```

- [ ] **Step 2: Run failing status-health test**

Run:

```bash
uv run --python 3.12 pytest tests/test_mcp_tools.py::test_check_index_status_uses_status_service_without_indexing -q
```

Expected: FAIL because `check_index_status` does not call the health explorer service.

- [ ] **Step 3: Build runtime-cache records and health payload in `check_index_status`**

In `McpToolRegistry.check_index_status(...)`:

```python
from vault_graph.mcp.mcp_memory_serialization import (
    health_explorer_report_to_payload,
    memory_warning_to_mcp_error,
    runtime_cache_records_for_mcp,
)
from vault_graph.mcp.mcp_tool_serialization import status_report_to_payload

runtime_caches = runtime_cache_records_for_mcp(
    context_pack_cache=self._context_pack_cache,
    result_explanation_cache=self._result_explanation_cache,
)
health_report = self._service_factory.open_health_explorer_service().inspect(
    requested_scope=selected_scope,
    runtime_caches=runtime_caches,
    status_report=report,
)
payload = status_report_to_payload(
    report,
    selected_scope=selected_scope,
    health_explorer=health_explorer_report_to_payload(health_report),
)
```

Return `_tool_body(..., payload=payload, warnings=tuple(memory_warning_to_mcp_error(warning) for warning in health_report.warnings))`.

- [ ] **Step 4: Add serialization assertion**

In `tests/test_mcp_tool_serialization.py`, add:

```python
def test_status_payload_accepts_compact_health_explorer_section() -> None:
    payload = status_report_to_payload(
        make_status_report_for_serialization(),
        selected_scope=QueryScope(vault_ids=("main",), content_scopes=("wiki",)),
        health_explorer={"backends": [], "runtime_caches": [], "scale_up_adapters": [], "warnings": [], "generated_at": "now"},
    )

    assert payload["health_explorer"]["backends"] == []  # type: ignore[index]
```

- [ ] **Step 5: Update prompts**

In `src/vault_graph/mcp/mcp_prompts.py`, update prompt lines:

```python
"Call check_index_status, get_recent_changes, summarize_project_memory, then build_context_pack for the bounded implementation scope."
```

For feature history:

```python
"Call get_recent_changes, then build_context_pack with the feature as the goal."
```

For risk analysis:

```python
"Call check_index_status, get_open_questions, get_recent_changes, build_context_pack, inspect warnings, then use search_vault for unresolved risk evidence."
```

Add tests in `tests/test_mcp_prompts.py` asserting the prompts mention `get_recent_changes`.

- [ ] **Step 6: Run verification**

Run:

```bash
uv run --python 3.12 pytest tests/test_mcp_tools.py tests/test_mcp_tool_serialization.py tests/test_mcp_prompts.py -q
```

Expected: PASS.

### Task 9: Read-Only, Import, And No External-Memory Guardrails

**Files:**

- Modify: `tests/test_mcp_tool_read_only_boundary.py`
- Modify: `tests/test_mcp_import_boundaries.py`
- Modify: `tests/test_naming_conventions.py` only if needed

- [ ] **Step 1: Add MCP tool read-only boundary test**

In `tests/test_mcp_tool_read_only_boundary.py`, add:

```python
def test_get_recent_changes_does_not_mutate_vault_or_create_memory_state(tmp_path: Path) -> None:
    vault_root = tmp_path / "vault"
    (vault_root / "wiki").mkdir(parents=True)
    (vault_root / "wiki" / "page.md").write_text("# Page\nVault body\n", encoding="utf-8")
    state_path = initialized_state(tmp_path, vault_root)
    seed_search_indexes(state_path)
    before = file_bytes(vault_root)
    missing_status_paths = (
        state_path / "vector" / "status.json",
        state_path / "graph" / "status.json",
    )
    registered = create_mcp_server(McpServerConfig(state_path=state_path))

    registered.tool_registry.get_recent_changes(GetRecentChangesInput())

    assert file_bytes(vault_root) == before
    assert not (state_path / "memory").exists()
    assert not (state_path / "data" / "memory").exists()
    assert all(not path.exists() for path in missing_status_paths)
```

Import `GetRecentChangesInput`.

- [ ] **Step 2: Extend no writable memory surface scan**

In `tests/test_mcp_import_boundaries.py::test_phase_6b_memory_files_do_not_introduce_writable_memory_surfaces`, rename the test to Phase 6 memory and extend forbidden terms:

```python
forbidden = (
    "MemoryStore",
    "Memory.create",
    "Memory.query",
    "Memory.upsert",
    "Memory.link",
    "Memory.audit",
    "episode_log",
    "profile_memory",
    "preference_memory",
    "procedural_memory",
    "mem0",
    "memmachine",
)
```

Keep the scan limited to `src/vault_graph/memory/*.py` and `src/vault_graph/mcp/mcp_memory_serialization.py` so public docs can still mention future adapter boundaries.

Add a path-level guard to `tests/test_naming_conventions.py`:

```python
def test_forbidden_memory_store_paths_are_not_introduced() -> None:
    forbidden_path_parts = (
        "memory_store",
        "episode_log",
        "profile_memory",
        "preference_memory",
        "procedural_memory",
        "external_memory",
        "memory_server",
    )
    offenders = [
        str(path.relative_to(PROJECT_ROOT))
        for path in (PROJECT_ROOT / "src" / "vault_graph").rglob("*")
        if any(part in path.as_posix().casefold() for part in forbidden_path_parts)
    ]
    assert offenders == []
    assert not (PROJECT_ROOT / "data" / "memory").exists()
```

- [ ] **Step 3: Extend memory service import-boundary test**

Update `test_memory_service_module_imports_do_not_pull_index_or_local_backends` to import:

```python
import vault_graph.memory.timeline_memory
import vault_graph.memory.health_explorer
```

Keep `vault_graph.app.index_service`, local Chroma, local graph store, rustworkx, `chromadb`, `fastembed`, and external memory modules forbidden.

- [ ] **Step 4: Add status health read-only test**

In `tests/test_mcp_tool_read_only_boundary.py`, add:

```python
def test_check_index_status_health_explorer_does_not_create_status_or_memory_state(tmp_path: Path) -> None:
    vault_root = tmp_path / "vault"
    vault_root.mkdir()
    state_path = initialized_state(tmp_path, vault_root)
    registered = create_mcp_server(McpServerConfig(state_path=state_path))

    registered.tool_registry.check_index_status(CheckIndexStatusInput())

    assert not (state_path / "vector" / "status.json").exists()
    assert not (state_path / "graph" / "status.json").exists()
    assert not (state_path / "memory").exists()
    assert not (state_path / "data" / "memory").exists()
```

Import `CheckIndexStatusInput`.

- [ ] **Step 5: Run verification**

Run:

```bash
uv run --python 3.12 pytest tests/test_mcp_tool_read_only_boundary.py tests/test_mcp_resource_read_only_boundary.py tests/test_mcp_import_boundaries.py tests/test_naming_conventions.py -q
```

Expected: PASS.

### Task 10: Full Phase 6C Verification And Commit

**Files:**

- All files modified by Tasks 1-9.

- [ ] **Step 1: Run focused Phase 6C tests**

Run:

```bash
uv run --python 3.12 pytest tests/test_timeline_memory_service.py tests/test_health_explorer_service.py tests/test_mcp_recent_changes_tool.py tests/test_mcp_timeline_resource.py -q
```

Expected: PASS.

- [ ] **Step 2: Run MCP regression tests**

Run:

```bash
uv run --python 3.12 pytest tests/test_mcp_tools.py tests/test_mcp_tool_serialization.py tests/test_mcp_memory_tools.py tests/test_mcp_resources.py tests/test_mcp_server.py tests/test_mcp_service_factory.py tests/test_mcp_prompts.py tests/test_mcp_errors.py -q
```

Expected: PASS.

- [ ] **Step 3: Run read-only and import-boundary tests**

Run:

```bash
uv run --python 3.12 pytest tests/test_mcp_tool_read_only_boundary.py tests/test_mcp_resource_read_only_boundary.py tests/test_mcp_import_boundaries.py tests/test_read_only_boundary.py -q
```

Expected: PASS.

- [ ] **Step 4: Run status/index regression tests**

Run:

```bash
uv run --python 3.12 pytest tests/test_index_service_vector_reconcile.py tests/test_index_service_graph_reconcile.py tests/test_graph_status_store.py tests/test_vector_indexer.py -q
```

Expected: PASS.

- [ ] **Step 5: Run smoke test when MCP SDK is available**

Run:

```bash
VG_RUN_MCP_STDIO_SMOKE=1 uv run --python 3.12 pytest tests/test_mcp_stdio_smoke.py -q
```

Expected: PASS. If the environment lacks the MCP SDK or `uv` cannot install dependencies, record the exact failure and run the non-smoke MCP registration tests from Step 2.

- [ ] **Step 6: Run static checks**

Run:

```bash
uv run --python 3.12 ruff check src tests
uv run --python 3.12 mypy src tests
```

Expected: PASS.

- [ ] **Step 7: Search for forbidden drift**

Run:

```bash
rg -n "MemoryStore|Memory\\.create|Memory\\.query|Memory\\.upsert|Memory\\.link|Memory\\.audit|episode_log|profile_memory|preference_memory|procedural_memory|mem0|memmachine" src/vault_graph
rg -n -g '!docs/superpowers/plans/2026-06-22-phase-6c-timeline-health-explorer.md' "vault_change|durable Vault change|--include-graph for the selected scope" docs README.md src tests
rg -n -g '!docs/superpowers/plans/2026-06-22-phase-6c-timeline-health-explorer.md' "get_recent_changes\\(since=None, scope=None\\)$|check_index_status\\(\\)$" docs README.md src tests
```

Expected:

- first command has no source-code matches except test guard definitions;
- second command has no matches;
- third command has no matches.

- [ ] **Step 8: Commit**

After all required verification passes:

```bash
git add src/vault_graph tests docs/superpowers/plans/2026-06-22-phase-6c-timeline-health-explorer.md
git commit -m "feat: add phase 6c timeline health explorer"
```

If docs-only changes from planning are being committed separately, use:

```bash
git add docs/superpowers/plans/2026-06-22-phase-6c-timeline-health-explorer.md docs/PATCH_LOG.md
git commit -m "docs: add phase 6c implementation plan"
```

## State Management And Data Flow

Timeline flow:

```text
MCP get_recent_changes or timeline/recent resource
  -> parse scope and since
  -> TimelineMemoryService.recent_changes(...)
  -> actual_query_scopes(...)
  -> status_service.status(scope=actual_scope) per Vault
  -> metadata_store.list_recent_documents(actual_scope, since, limit) per Vault
  -> build document_snapshot_change, index_change, projection_change, warning items
  -> group by vault_id
  -> serialize through mcp_memory_serialization
```

Health flow:

```text
MCP check_index_status
  -> status_service.status(scope=selected_scope)
  -> runtime_cache_records_for_mcp(...)
  -> HealthExplorerService.inspect(..., status_report=report)
  -> status_report_to_payload(..., health_explorer=...)
```

State rules:

- Timeline and health output is regenerated per request.
- No timeline or health store is created.
- Runtime caches stay in-process only and are reported by counts/capacity.
- Deleting runtime caches loses only cache visibility.
- Deleting derived indexes makes timeline/health unavailable or degraded until `vg index` rebuilds them.

## Error Handling And Edge Cases

Validation errors:

- invalid `since` -> MCP `invalid_parameter`, code `invalid_tool_arguments`, message includes `invalid_timeline_since`
- `limit < 1` or `limit > 50` -> MCP `invalid_parameter`, code `invalid_tool_arguments`
- invalid scope object -> existing MCP scope validation
- `scope.include_cross_vault=True` for `get_recent_changes` -> MCP `invalid_parameter`
- unknown or disabled Vault ID -> existing catalog/scope MCP mapping

Execution errors:

- metadata unavailable or schema-incompatible -> `MemoryProjectionError("metadata_unavailable: ...")`, MCP execution error, safe hint `Run vg index, then vg status for the selected Vault.`
- metadata listing failure -> `MemoryProjectionError("metadata_unavailable: ...")` or sanitized MCP execution error
- malformed status report values -> `MemoryProjectionError("memory_projection_unavailable: ...")`

Degraded successful output:

- no recent document changes -> empty vault item list plus informational warning when useful
- untimestamped items with no `since` -> item-level `missing_timeline_timestamp`
- untimestamped items with `since` -> excluded plus top-level `timeline_items_without_timestamps_excluded`
- vector unavailable, stale, schema-incompatible, or last error -> warning item and health degraded/unavailable record
- graph unavailable, stale, schema-incompatible, or last error -> warning item and health degraded/unavailable record
- runtime cache at capacity -> health degraded record
- scale-up backend not configured -> readiness record with `configured=False`; no error

## Validation Review

Security/read-only:

- Phase 6C reads metadata snapshots and status reports only.
- MCP resources/tools do not read Vault files directly and do not call `VaultLoader`.
- Status checks must not initialize missing stores or create status files.
- Runtime cache visibility exposes counts and capacity only, not cached payloads.

Performance/scalability:

- `MetadataStore.list_recent_documents(actual_scope, since, limit)` is called once per actual Vault scope.
- Per-Vault limit prevents one noisy Vault from hiding another.
- Timeline does not read chunks, embeddings, graph traversal, or context packs.
- Scale-up readiness is computed from existing status/schema fields without remote backend calls.

Testability:

- Timeline and health services accept protocol/fake status services and deterministic clocks.
- MCP tool/resource tests use recording fakes before integration tests.
- Read-only tests assert Vault bytes and no memory state paths.
- Import-boundary tests catch eager Chroma, fastembed, rustworkx, MCP SDK, and external-memory imports.

Maintainability:

- New domain modules have precise names: `timeline_memory.py` and `health_explorer.py`.
- MCP-free DTOs stay in `vault_graph.memory`.
- MCP serialization and cache snapshots stay in `vault_graph.mcp`.
- Existing `check_index_status` remains the status tool; Phase 6C does not add a parallel health tool.

## Open Decisions

None.

Hosted monitoring, remote backend migration, independent keyword status, UI dashboards, and external-memory adapters remain future work outside Phase 6C.
