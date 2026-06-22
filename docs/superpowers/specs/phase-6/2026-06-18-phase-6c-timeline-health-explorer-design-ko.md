# Phase 6C Timeline, Health, And Explorer Views SPEC

Status: Draft for implementation planning

Date: 2026-06-18

Scope: Phase 6C

## 1. 목적

Phase 6C는 Phase 6 memory/explorer layer의 마지막 조각으로 다음을 노출합니다.

- 최근 indexed document snapshot changes
- 현재 index/projection revision state
- backend health와 freshness
- MCP runtime cache visibility
- scale-up adapter contract readiness

사용자 가치는 operational trust입니다. 사람이나 agent가 project memory,
context pack, search, graph output을 신뢰하기 전에 다음을 확인할 수 있어야 합니다.

- 이 Vault scope에서 최근 어떤 indexed document snapshot이 바뀌었는가?
- 어떤 derived projection이 stale, missing, incompatible, degraded 상태인가?
- 현재 local backend가 이 작업에 충분히 건강한가?
- 향후 scale-up backend로 옮길 때 logical identity fields가 준비되어 있는가?

Phase 6C도 read-only projection layer입니다. Hosted monitoring, UI dashboard,
data migration system, durable memory database가 아닙니다. Durable truth는
Vault에 남고, Phase 6C output은 Vault-derived indexes와 runtime status 위에
재생성 가능한 working context입니다.

## 2. 성공 기준

Phase 6C는 다음 조건을 만족할 때 완료됩니다.

- `TimelineMemoryService.recent_changes(...)`가 요청된 `QueryScope`에 대해
  grouped `RecentChangesProjection`을 반환합니다.
- timeline item은 `document_snapshot_change`, `index_change`, `projection_change`,
  `warning` origin을 구분합니다.
- document-level recent changes는 bounded
  `MetadataStore.list_recent_documents`에서 파생되며, service는 Vault files를
  직접 읽지 않습니다.
- index/projection change timestamp는 indexed document snapshot 또는 명시적
  status field에서만 가져오며 timestamp를 만들어내지 않습니다.
- `IndexService.status(...)`는 vector/graph timeline item에 필요한 최소
  timestamp fields를 노출하되 local status-store internals는 노출하지 않습니다.
- backing service가 존재한 뒤에만 MCP가
  `get_recent_changes(since=None, scope=None, limit=20)`를 등록합니다.
- `vault://{vault_id}/timeline/recent`는 Phase 5B availability error 대신
  single-Vault structured JSON을 반환합니다.
- `HealthExplorerService.inspect(...)`는 backend readiness, runtime-cache
  readiness, scale-up contract readiness를 structured report로 반환합니다.
- `check_index_status`는 stable MCP status tool로 유지하고 compact
  health-explorer payload를 추가합니다. Phase 6C는 별도 health MCP tool을
  추가하지 않습니다.
- 모든 output은 Vault IDs, actual scopes, warnings, revisions, generated
  timestamps, safe recovery hints를 보존합니다.
- all-Vault tool output은 `vault_id`별로 group되고 path, title, backend name,
  timestamp만으로 merge하지 않습니다.
- Phase 6C path는 Vault를 mutate하지 않고, missing read-only store를
  initialize하지 않으며, memory files, episode logs, external memory systems를
  만들거나 import하지 않습니다.

## 3. 범위

- timeline DTOs, validation helpers, deterministic item IDs
- `MetadataStore`와 status-service protocol 위의 timeline service
- vector/graph run timestamp를 위한 최소 `StatusReport` 확장
- recent changes MCP tool과 parser
- `timeline/recent` MCP resource upgrade
- health/freshness explorer DTOs와 service
- context-pack/result-explanation cache용 MCP runtime-cache snapshot records
- known logical backend contract에 대한 scale-up adapter readiness records
- MCP serialization, prompt wording, service-factory handoff, import boundary
  tests
- read-only, multi-Vault, stale-state, timestamp, serialization,
  no-external-memory tests

## 4. 범위 밖

- hosted monitoring, alerts, dashboards, subscriptions
- Postgres, Qdrant, Neo4j 또는 remote backend migration
- background file watchers
- answer synthesis 또는 `ask_vault`
- automatic Vault repair, publication, validation, wiki updates
- Phase 6A in-process explanation cache를 넘어서는 durable result history
- raw session transcripts, hidden episode logs, profile memory, preference
  memory, procedural memory
- Mem0, MemMachine, MCP memory-server integration

## 5. 추가/수정 파일

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

Phase 6C에서는 `data/memory/`, timeline database, status history store, external
memory dependency를 추가하지 않습니다.

## 6. 기존 의존성

Phase 6C는 현재 계약 위에 올라갑니다.

- `QueryScope`, `VaultCatalog`, `actual_query_scopes(...)`
- Phase 6B의 `MetadataStore.list_documents(scope)`와 Phase 6C에서 추가하는
  bounded `MetadataStore.list_recent_documents(scope, since, limit)`
- `memory_request_context.py`의 기존 `MemoryStatusService` protocol
- `DocumentSnapshot.last_seen_at`, `last_indexed_at`, `content_hash`,
  `raw_sha256`, `vault_revision`, `index_revision`
- `vault_graph.app.index_service`의 `StatusReport`
- Phase 6A `ResultExplanationCache`
- Phase 4/5 `ContextPackResourceCache`
- 기존 MCP scope parsing, resource URI parsing, tool envelope shapes
- Phase 6B `MemoryWarning`, `MemoryBackendRevision`, warning-to-MCP
  serialization style, 그리고 `vault_graph.errors`의 `MemoryProjectionError`

MCP layer는 Phase 6C application service에 의존해야 합니다. SQLite, Chroma,
graph store, status JSON file, Vault file을 직접 query하면 안 됩니다.

## 7. Status Report 확장

Phase 6C는 timeline/health view를 위해 vector/graph run timestamp가 필요합니다.
`IndexService.status(...)`가 이미 읽는 vector/graph status store에서 다음 optional
fields를 `StatusReport`에 추가합니다.

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

- 기존 fields와 payload keys는 backward-compatible하게 유지합니다.
- status-store file path나 raw JSON payload는 노출하지 않습니다.
- run timestamp가 없으면 `None`을 사용합니다.
- status check 중 status-store file을 생성하지 않습니다.
- MCP status serialization은 새 timestamp fields를 기존 `vector`, `graph`
  object 아래에 포함합니다.
- tests는 status file이 없는 경우와 성공한 vector/graph run timestamp가 있는
  경우를 모두 검증합니다.

## 8. Timeline Data Model

`src/vault_graph/memory/timeline_memory.py`가 timeline DTO를 소유합니다.
두 번째 warning/revision vocabulary를 만들지 않기 위해 `memory_models.py`의
`MemoryWarning`, `MemoryBackendRevision`을 재사용할 수 있습니다.

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

- constructors는 required strings, tuple immutability, allowed literal values,
  warning types를 Phase 6B DTO와 같은 방식으로 검증합니다.
- 모든 `TimelineEvidenceRef`는 `vault_id`가 필요합니다.
- `source_kind="document"`는 `document_id`, `path`, `content_hash`가 필요합니다.
- `_status`로 끝나는 `source_kind`는 `backend_kind`와 `scope_key`가 필요합니다.
- `TimelineItem.evidence`는 `origin="warning"`이 아닌 한 비어 있으면 안 됩니다.
- `warning` item은 affected Vault IDs가 있는 warning을 하나 이상 가져야 합니다.
- `item_id` 형식은 `timeline:<origin>:<24 hex chars>`입니다.
- item ID hash input에는 origin, Vault ID, source kind, document ID 또는 backend
  kind, path 또는 scope key, revision, occurred timestamp가 들어갑니다.
- `sort_key`는 timestamp가 있으면 timestamp에서 파생하고, 없으면
  `no-time:<vault_id>:<path-or-backend>:<item_id>` 형식을 사용합니다.
- `freshness`는 `fresh`, `stale`, `degraded`, `unavailable`, `unknown` 중 하나를
  사용합니다.
- text mirror는 `origin`, `occurred_at`, warnings, evidence source kinds를
  보존하여 status record가 durable Vault fact처럼 보이지 않게 합니다.

## 9. Timeline Origin Rules

`document_snapshot_change` items:

- `MetadataStore.list_recent_documents(scope, since, limit)`가 반환한
  `DocumentSnapshot`에서 파생됩니다.
- `occurred_at = last_indexed_at or last_seen_at`을 사용하되, durable business
  event timestamp가 아니라 index observation timestamp로 표시합니다.
- title은 `Indexed document: <path>` 형식입니다.
- path, document kind, content hash, raw SHA-256, metadata index revision, Vault
  revision 같은 indexed document state만 요약합니다.
- Vault document 자체가 다른 evidence로 반환되지 않는 한 "project decided X" 같은
  business event를 추론하지 않습니다.

`index_change` items:

- `StatusReport`에서 metadata/vector status를 파생합니다.
- vector `last_success_at` 또는 `last_error_at`이 있으면 사용합니다.
- explicit timestamp가 없으면 `occurred_at=None`입니다.
- keyword는 독립 status contract가 생기기 전까지 metadata의 일부로 봅니다.

`projection_change` items:

- graph readiness/status를 다룹니다.
- graph `last_success_at` 또는 `last_error_at`이 있으면 사용합니다.
- MCP runtime cache는 포함하지 않습니다. Runtime cache는 recent-change timeline
  item이 아니라 health explorer record입니다.

`warning` items:

- missing metadata, incompatible schema, stale vector/graph, timestamp gaps,
  unsupported scope, degraded projection state를 나타냅니다.
- `Run vg index`, `Run vg status` 같은 safe recovery hint를 포함합니다.
- timeline 신뢰도에 영향을 주는 warning은 top-level warning에만 숨기지 않습니다.

## 10. Timestamp And Since Policy

`since`는 ISO-8601 timestamp string입니다. Service와 MCP parser는 timezone-aware
값을 받아야 하며, timezone-naive 값은 parser가 명시적으로 UTC로 normalize할 때만
허용합니다.

Rules:

- invalid `since`는 ISO-8601 guidance가 있는 validation error입니다.
- `since` filtering은 `occurred_at`에 적용됩니다.
- `since`가 있으면 `occurred_at=None` items는 제외하고
  `timeline_items_without_timestamps_excluded` top-level warning을 냅니다.
- `since`가 없으면 `occurred_at=None` items를 timestamped items 뒤에 포함하고
  item-level `missing_timeline_timestamp` warning을 붙입니다.
- filename, title, rank에서 timestamp를 합성하지 않습니다.
- ordering은 descending `occurred_at`, `vault_id`, normalized path/backend kind,
  `item_id` 순입니다.
- default limit은 `20`, 허용 범위는 `1..50`, limit은 Vault group별로 적용합니다.

## 11. Timeline Service

Memory module은 `IndexService`를 직접 import하지 않고 기존 neutral memory
status protocol을 사용합니다.

```python
class TimelineMemoryService:
    def __init__(
        self,
        *,
        catalog: VaultCatalog,
        metadata_store: MetadataStore,
        status_service: MemoryStatusService,
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

1. `limit` 검증과 `since` parsing
2. `actual_query_scopes(...)`로 actual scopes resolution
3. actual Vault scope마다 `status_service.status(scope=actual_scope)` 1회 호출
4. metadata health가 unavailable 또는 schema-incompatible이면
   `MemoryProjectionError("metadata_unavailable: ...")`
5. actual one-Vault scope마다
   `MetadataStore.list_recent_documents(actual_scope, since, limit)` 1회 호출.
   `list_recent_documents(...)`는 multi-Vault scope를 거부하므로 all-Vault
   timeline은 `actual_query_scopes(...)`로 먼저 분리합니다.
6. document, index, projection, warning items 생성
7. `since`와 per-Vault limit 적용
8. top-level, Vault-level, item-level warnings를 포함한 grouped output 반환

Service rules:

- Phase 6C에서 `TimelineMemoryService`는 chunk evidence나 Vault files를 직접
  읽지 않습니다. 기존 status service는 projection freshness 계산 중 derived
  chunk metadata를 내부적으로 inspect할 수 있습니다.
- `VaultLoader`, `IndexService.run_apply(...)`, graph traversal, vector search,
  context-pack builder를 호출하지 않습니다.
- store 생성, migration, stale index repair를 하지 않습니다.
- metadata-unavailable은 indexed document snapshots를 list할 수 없으므로
  fatal입니다.
- vector/graph unavailable은 timeline 실패가 아니라 warning item과 health
  warning입니다.
- document snapshot은 observed metadata timestamp를 사용합니다. status 또는
  projection-only item은 timestamp가 없을 수 있으며, 이 gap은 visible하게
  유지합니다.

## 12. Health Explorer Data Model

`src/vault_graph/memory/health_explorer.py`가 operations-facing DTO를 소유합니다.
MCP-free이며 MCP cache implementation에 직접 의존하지 않습니다.

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

- backend record는 `scope_key`와 `vault_id` 또는 all-scope marker message가
  필요합니다.
- runtime-cache record는 counts/capacity만 노출하고 cached payload는 노출하지
  않습니다.
- scale-up record는 readiness statement이며 migration이나 config write가 아닙니다.
- degraded/unavailable backend는 recovery hint 또는 local recovery가 없는 이유를
  message에 포함해야 합니다.

## 13. Health Explorer Service

```python
class HealthExplorerService:
    def __init__(
        self,
        *,
        catalog: VaultCatalog,
        status_service: MemoryStatusService,
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

1. actual scopes resolution
2. `check_index_status(...)`가 `status_report`를 제공하면 그것을 사용하고,
   없으면 actual Vault scope마다 `status_service.status(scope=actual_scope)` 1회 호출
3. metadata, keyword, vector, graph status를 backend readiness records로 변환
4. MCP layer가 제공한 runtime-cache records 추가
5. known backend contracts에 대한 static scale-up readiness records 추가
6. stale, unavailable, incompatible, unknown state를 structured warnings로 반환

Backend mapping:

- metadata는 `metadata_ok`와 `metadata_schema_compatible`이 true일 때 `ready`
- keyword는 Phase 6C에서 metadata-coupled projection으로만 보고합니다. 나중에
  독립 health가 생기면 report shape 변경 없이 분리할 수 있습니다.
- vector는 vector health OK, schema-compatible, `vector_stale_count == 0`이면
  `ready`; stale이거나 last error가 있지만 last success revision이 있으면
  `degraded`
- graph는 `StatusReport.graph_readiness.freshness`,
  `graph_last_success_revision`, `graph_last_error`를 사용합니다.
- MCP runtime cache는 configured이고 capacity 미만이면 `ready`, capacity에
  도달하면 `degraded`, omitted이면 `not_configured`입니다.

Service는 local files를 inspect하거나 stores/backends를 instantiate하지 않습니다.
`McpServiceFactory`가 existing read-only status service와 함께 구성합니다.

## 14. Scale-Up Readiness Policy

Phase 6C readiness check는 status/schema-derived contract check이며, migration도
record-level migration audit도 아닙니다. 현재 status report와 알려진 store DTO
contract를 바탕으로 future adapter를 지원할 logical contract가 준비되어 보이는지
답합니다.

| Adapter Kind | Target Backend | Depends On | Contract Ready When |
| --- | --- | --- | --- |
| `metadata` | `postgres` | metadata | metadata status가 healthy/schema-compatible이고 current metadata DTO contract가 documents, chunks, evidence refs, tombstones, revisions, health fields를 정의 |
| `vector` | `qdrant` | vector | vector status가 available/schema-compatible이고 current vector DTO contract가 vector IDs, embedding model specs, metadata revisions, tombstones를 정의 |
| `graph` | `neo4j` | graph | graph readiness가 available/schema-compatible이고 current graph DTO contract가 entity IDs, relationship IDs, graph revisions, evidence memberships, scope keys를 정의 |

Rules:

- scale-up backend config가 없으면 `configured=False`이고, `contract_ready`는
  status/schema health와 알려진 local logical contract만 기준으로 합니다.
- `migration_required=True`는 target backend 사용 전 data movement가 필요하다는
  뜻이며 migration을 실행하지 않습니다.
- local metadata가 missing이면 local identity contract의 status/schema 기반을
  증명할 수 없으므로 모든 adapter readiness가 degraded입니다.
- stale vector/graph state는 logical fields가 있으면 unavailable이 아니라
  degraded로 표시합니다.
- readiness output은 record-level migration audit이 수행되지 않았음을 명시해야
  하며, Phase 6C에 remote backend가 필요하다고 암시하면 안 됩니다.

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

- `McpToolName`과 `McpToolRegistry.tool_names`에 `get_recent_changes`를 추가합니다.
- `tests/test_mcp_stdio_smoke.py` exact tool list를 갱신합니다.
- `scope`는 `scope_from_mcp_input(...)`로 parse합니다.
- active-Vault default, explicit `vault_ids`, `all_vaults`를 지원합니다.
- `include_cross_vault`는 reject합니다. timeline grouping은 all-Vault selection이지
  cross-Vault graph traversal이 아닙니다.
- `limit`은 기존 `MAX_MCP_TOOL_LIMIT`로 검증합니다.
- MCP 호출에서는 service invocation 전에 `since`를 검증합니다.
- output은 기존 MCP tool envelope를 따릅니다.

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

- document-backed `document_snapshot_change` item은
  `vault://{vault_id}/documents/{path}`로 link합니다.
- Phase 6B document classifier를 의도적으로 재사용하기 전까지 page/source/decision/issue
  link는 timeline item에서 내보내지 않습니다.
- status-backed item은 document link를 갖지 않습니다.
- timeline-specific writable resource URI는 추가하지 않습니다.

## 16. MCP Resource Contract

Upgrade:

```text
vault://{vault_id}/timeline/recent
```

Rules:

- 정확히 한 Vault의 `RecentChangesProjection`을 반환합니다.
- resource scope는 `catalog.scope_for_vault_ids((vault_id,))`입니다.
- default limit은 `20`, `since=None`입니다.
- content type은 `application/json`입니다.
- metadata는 structured payload를 mirror합니다.
- all-Vault timeline은 URI가 single-Vault라서 tool-only입니다.
- errors는 affected Vault ID와 safe recovery hint를 포함합니다.

`CurrentContextResourceReader.read_recent_timeline(...)` method name은 작은 patch를
위해 유지해도 됩니다. 다만 구현은 `TimelineMemoryService`에 delegate해야 합니다.
읽기가 어려워지면 별도 mechanical change로 neutral projection-resource reader로
rename합니다.

## 17. MCP Status Health Exposure

`check_index_status(scope=None)`를 stable tool로 유지하고 payload를 확장합니다.

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

- `McpToolRegistry.check_index_status(...)`는 기존 `StatusReport`가 준비된 뒤
  `HealthExplorerService.inspect(..., status_report=report)`를 호출합니다.
- `get_recent_changes`와 `timeline/recent`는 별도 status payload가 필요하지
  않으므로 timeline service가 status를 내부에서 읽어도 됩니다.
- runtime cache snapshot은 MCP layer가 `ContextPackResourceCache`,
  `ResultExplanationCache`에서 `len(...)`과 `max_entries`로 만듭니다.
- cached context-pack body나 explanation record를 status payload에 serialize하지
  않습니다.
- prompt text는 health/freshness 확인용으로 `check_index_status`를 언급할 수
  있지만 autonomous repair를 암시하면 안 됩니다.

## 18. Serialization Boundary

기존 memory serialization 근처에 MCP adapter serializers를 추가합니다.

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

- projection, vault, item level의 모든 warnings를 보존합니다.
- 기존 MCP payload와 같은 `query_scope_to_dict(...)` shape를 사용합니다.
- text mirror는 existing tool body처럼 JSON mirror이고 structured output에 없는
  사실을 추가하지 않습니다.
- MCP error warning은 `memory_warning_to_mcp_error(...)`를 재사용합니다.
- serialization module은 local backend implementation을 import하지 않습니다.

## 19. Service Factory Handoff

`McpServiceFactory`는 lazy read-only construction methods를 추가합니다.

```python
class McpServiceFactory:
    def open_timeline_memory_service(self) -> TimelineMemoryService: ...
    def open_health_explorer_service(self) -> HealthExplorerService: ...
```

Rules:

- metadata store는 `initialize=False`로 엽니다.
- status access는 `open_status_service()`를 사용합니다.
- repeated construction이 measured problem이 되기 전까지 `McpServices` field로
  추가하지 않습니다.
- timeline-specific storage directory를 만들지 않습니다.
- imports는 lazy하게 유지하여 `vault_graph.mcp` import가 Chroma, graph store,
  embedding model을 즉시 import하지 않게 합니다.

## 20. Error And Degradation Policy

Validation errors:

- invalid `since`
- non-integer, non-positive, out-of-range `limit`
- invalid scope object
- unknown 또는 disabled Vault ID

Execution errors:

- missing 또는 schema-incompatible metadata state
- document listing을 막는 metadata store error
- safe health conversion을 막는 malformed status report

Degraded successful output:

- no recent changes
- missing document timestamps
- vector backend missing, stale, schema-incompatible, last run failed
- graph backend missing, stale, schema-incompatible, last run failed
- MCP runtime caches at capacity
- scale-up backend not configured

Recovery hints:

- metadata unavailable: `Run vg index, then vg status for the selected Vault.`
- stale vector: `Run vg index for the selected scope to refresh vector state.`
- stale graph: `Run vg index for the selected scope, then vg status.`
- missing timestamp: `Re-index the selected scope to refresh indexed timestamps.`

정확한 CLI flags는 Phase 6C 구현 시점의 실제 command와 맞춰야 합니다. User-facing
error에서 지원하지 않는 command를 만들면 안 됩니다.

## 21. Multi-Vault Policy

- `scope=None`은 active Vault를 사용합니다.
- explicit `vault_ids`는 해당 Vault를 선택합니다.
- `all_vaults=True`는 service 실행 전에 enabled Vault entries 전체로 확장됩니다.
- `RecentChangesProjection.vaults`는 actual Vault scope마다 하나의
  `TimelineVault`를 가집니다.
- per-Vault `limit`은 noisy Vault 하나가 다른 Vault를 가리지 않게 합니다.
- item ID는 `vault_id`를 포함합니다.
- 다른 Vault의 같은 path, timestamp, revision은 merge하지 않습니다.
- resource URI는 single-Vault only입니다.
- graph cross-Vault traversal은 timeline/health explorer 범위 밖입니다.

## 22. Read-Only And Rebuildability

- Phase 6C는 Vault files를 쓰지 않습니다.
- Phase 6C는 derived timeline/health files를 쓰지 않습니다.
- Timeline output은 current metadata snapshots와 status reports에서 재생성됩니다.
  Runtime-cache snapshots는 health explorer output에 속합니다.
- Runtime cache를 삭제해도 cache visibility만 잃고 Vault Graph truth는 잃지 않습니다.
- Derived indexes를 삭제하면 `vg index`로 다시 rebuild하기 전까지 timeline/health
  output은 unavailable 또는 degraded가 됩니다.
- External memory systems는 나중에 Phase 6C projections를 export할 수 있지만
  timeline/health facts의 source가 될 수 없습니다.

Required boundary tests:

- write-capable metadata/vector/graph store를 여는 call path가 없음
- read-only timeline 또는 health check 중 status file write나 status file creation
  없음
- `IndexService.run_apply(...)` 호출 없음
- registered Vault source files 직접 read 없음
- `MemoryStore`, `Memory.create/query/upsert/link/audit`, episode-log,
  profile-memory, preference-memory, procedural-memory, external memory
  dependency 추가 없음

## 23. Tests

Required tests:

- timeline DTOs가 blank IDs, invalid origins, mutable sequences, invalid evidence
  shapes, warning 없는 warning items를 reject합니다.
- document timeline item은 `last_seen_at`보다 `last_indexed_at`을 우선 사용합니다.
- missing document timestamps는 item warnings와 deterministic fallback order를
  만듭니다.
- `since`는 timestamped items를 filter하고 untimestamped items를 visible warning과
  함께 제외합니다.
- recent changes는 `document_snapshot_change`, `index_change`,
  `projection_change`, `warning` origin을 분류합니다.
- grouping 후 per-Vault limits가 적용됩니다.
- identical paths/timestamps/revisions를 가진 multi-Vault timelines가 충돌하지
  않습니다.
- metadata-unavailable은 MCP에서 safe recovery hint가 있는 `MemoryProjectionError`로
  매핑됩니다.
- vector/graph unavailable state는 timeline 실패가 아니라 warning item으로
  반환됩니다.
- `StatusReport` timestamp fields가 `check_index_status`를 통해 serialize됩니다.
- health explorer가 metadata, keyword, vector, graph, runtime-cache, scale-up
  readiness state를 deterministic하게 mapping합니다.
- runtime-cache records는 counts/capacity만 노출하고 cached payload는 노출하지
  않습니다.
- `get_recent_changes`는 input validation, payload, resource links, warnings,
  text mirrors를 검증합니다.
- `timeline/recent` resource는 single Vault structured JSON을 반환합니다.
- `check_index_status`는 compact `health_explorer` output을 포함합니다.
- prompt tests는 tool이 등록된 뒤에만 `get_recent_changes`를 언급합니다.
- import-boundary tests는 Phase 6C module import 시 local backend import가 없음을
  확인합니다.
- read-only boundary tests는 Vault mutation과 store initialization이 없음을
  확인합니다.
- raw episode log, session transcript, profile memory, preference memory,
  procedural memory, external memory-server persistence가 생성되지 않았음을
  boundary tests로 확인합니다.

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

Phase 6C 구현 순서:

1. `StatusReport`에 vector/graph timestamp fields를 추가하고 status serialization
   tests를 갱신합니다.
2. timeline DTOs, stable timeline item IDs, timestamp parsing, model tests를
   추가합니다.
3. `MetadataStore.list_recent_documents(...)`와 status-service protocol 위에
   `TimelineMemoryService`를 추가합니다.
4. health explorer DTOs와 `HealthExplorerService`를 추가합니다.
5. recent changes와 health explorer report용 MCP serializers를 추가합니다.
6. `McpServiceFactory.open_timeline_memory_service()`와
   `open_health_explorer_service()`를 추가합니다.
7. `GetRecentChangesInput`, parser, registry method, MCP tool, tool tests를
   추가합니다.
8. `vault://{vault_id}/timeline/recent`를 upgrade합니다.
9. `check_index_status`에 compact health-explorer output을 추가합니다.
10. prompts와 stdio smoke expectations를 갱신합니다.
11. read-only/import-boundary tests, focused Phase 6C tests, full static checks를
    실행합니다.

## 25. Risks And Mitigations

- **Risk:** 사용자가 timeline timestamp를 durable business event로 오해한다.
  **Mitigation:** title/summary는 indexed/projection state change라고 말하고,
  모든 item은 `origin`과 evidence source kind를 가진다.
- **Risk:** health explorer가 speculative migration/config system이 된다.
  **Mitigation:** contract readiness만 보고하고 remote config 생성, data
  migration, hosted service 요구를 하지 않는다.
- **Risk:** status payload가 너무 커진다.
  **Mitigation:** `HealthExplorerService`를 분리하고 `check_index_status` 아래에
  compact structured section만 serialize한다.
- **Risk:** timeline output이 unbounded whole-Vault scan이 된다.
  **Mitigation:** metadata snapshots만 사용하고 per-Vault limits를 적용하며 chunk
  evidence 또는 Vault source files를 직접 읽지 않는다. 기존 status/freshness
  service는 derived chunk metadata를 inspect할 수 있다.
- **Risk:** memory terminology 때문에 raw episode storage 압력이 생긴다.
  **Mitigation:** Phase 6C는 Vault-derived timeline projections와 runtime cache
  readiness만 노출한다. Durable event는 먼저 Vault에 들어가야 한다.
- **Risk:** all-Vault recent changes가 source ownership을 숨긴다.
  **Mitigation:** Vault ID로 group하고 item IDs, evidence, warnings, revisions,
  resource links에 Vault IDs를 포함한다.

## 26. Open Decisions

Phase 6C에는 없음.

Hosted monitoring, remote backend migration, independent keyword status, external
memory adapters는 future work로 남깁니다.
