# Phase 6C Timeline, Health, And Explorer Views SPEC

Status: Draft for implementation planning

Date: 2026-06-18

Scope: Phase 6C

## 1. 목적

Phase 6C는 recent changes, projection freshness, backend health, scale-up
adapter readiness를 노출하여 memory와 explorer layer를 완성합니다.

사용자와 agent는 memory, context, graph output을 신뢰하기 전에 최근 무엇이
바뀌었는지, Vault Graph projection이 신뢰 가능한 상태인지 확인할 수 있어야
합니다.

## 2. 성공 기준

Phase 6C는 다음 조건을 만족할 때 완료됩니다.

- `TimelineMemoryService.recent_changes(...)`는 durable Vault-derived changes와
  derived projection changes를 origin label과 함께 반환합니다.
- backing service가 존재한 뒤에만 MCP가 `get_recent_changes`를 등록합니다.
- `vault://{vault_id}/timeline/recent`는 Phase 5B availability error가 아니라
  structured timeline projection을 반환합니다.
- `HealthExplorerService.inspect(...)`는 metadata, vector, graph, projection,
  MCP cache, adapter readiness를 하나의 evidence-linked payload로 보고합니다.
- scale-up readiness checks는 data migration이나 hosted service 없이 logical
  contract readiness를 보고합니다.
- stale 또는 unavailable projection은 structured warning으로 보입니다.
- timeline이나 health view는 Vault나 derived indexes를 mutate하지 않습니다.

## 3. 범위

- timeline DTOs와 service
- recent changes MCP tool
- `timeline/recent` MCP resource upgrade
- health/freshness explorer DTOs와 service
- configured 또는 known backend contract에 대한 scale-up adapter readiness records
- origin labeling, freshness, multi-Vault scoping, serialization, read-only tests

## 4. 범위 밖

- hosted monitoring
- Postgres, Qdrant, Neo4j로 data migration
- background watchers 또는 resource subscriptions
- UI dashboards
- alert delivery
- answer synthesis
- raw session transcript 또는 episode log storage
- external persistent memory server integration
- automatic Vault repair 또는 publication

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

`src/vault_graph/memory/timeline_memory.py`가 timeline DTO를 소유합니다.

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

- `vault_change`: metadata snapshots, hashes, `last_seen_at`,
  `last_indexed_at`, optional Vault Git revision에서 파생된 document-level change
- `index_change`: metadata, keyword, vector revision state
- `projection_change`: graph 또는 context projection revision state
- `warning`: stale, unavailable, incompatible, missing projection state

Timeline record는 projection record입니다. Vault evidence로 뒷받침되지 않으면
durable business event라고 주장하지 않습니다.

External memory-layer system은 episodic memory를 persistent event history로
모델링하는 경우가 많습니다. Phase 6C는 그 아이디어의 projection 형태만
사용합니다. Raw conversation transcripts, agent session logs, user profiles,
hidden episode stores는 Vault Graph core 범위 밖입니다. 어떤 conversation이나
event가 durable해야 한다면 먼저 Vault에 capture되어야 하며, 이후 normal indexing을
통해 timeline에 나타나야 합니다.

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

- `actual_query_scopes(...)`로 requested scope를 expand합니다.
- `MetadataStore.list_documents(...)`로 metadata document snapshots를 읽습니다.
- `IndexService.status(...)`로 projection freshness를 읽습니다.
- `since`가 있으면 ISO-8601 timestamp로 parse합니다.
- non-positive limit과 MCP tool limit 초과를 reject합니다.
- descending timestamp, Vault ID, path, item ID 순으로 deterministic ordering합니다.
- timestamp가 없어 fallback sorting을 사용하면 warning을 포함합니다.

## 8. Health Explorer Data Model

`src/vault_graph/memory/health_explorer.py`가 operations-facing DTO를 소유합니다.

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

health explorer는 기존 status와 configuration 위의 operations projection입니다.
store를 create하거나 repair하지 않습니다.

## 9. Scale-Up Readiness Policy

Phase 6C readiness check는 migration이 아니라 contract check입니다.

각 record는 다음 질문에 답해야 합니다.

- scale-up backend가 configured인가?
- 이 backend kind에 대한 adapter contract가 repository에 존재하는가?
- 현재 local logical identity fields를 backend에 mapping할 수 있는가?
- 사용 전에 migration이 필요한가?
- 어떤 현재 projection이 stale 또는 incompatible인가?

Initial backend kinds:

- metadata: 현재 local SQLite, future Postgres contract
- vector: 현재 local Chroma, future Qdrant contract
- graph: 현재 local SQLite/rustworkx, future Neo4j contract

scale-up backend config가 없으면 `configured=False`, `contract_ready=False`와
neutral message를 반환합니다. health report를 실패시키지 않습니다.

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

이 resource는 single Vault의 `RecentChangesProjection`을 default limit 20,
`since` filter 없음으로 반환합니다.

Health explorer exposure:

- `check_index_status`를 stable MCP status tool로 유지합니다.
- service가 존재한 뒤 status payload에 health explorer fields를 추가합니다.
- implementation plan에서 기존 status payload가 너무 넓어진다는 증거가 나오기
  전까지 별도 MCP health tool은 추가하지 않습니다.

## 11. Error And Degradation Policy

- invalid `since`: ISO-8601 guidance가 있는 validation error
- unknown Vault ID: validation error
- missing metadata: document changes를 list할 수 없으므로 timeline execution error
- missing vector 또는 graph state: warning records
- incompatible backend schema: metadata-backed changes를 list할 수 있는지에 따라
  warning 또는 error
- no recent changes: successful empty projection

## 12. Multi-Vault Policy

- tools는 기본적으로 active Vault를 사용합니다.
- resource URI는 single-Vault입니다.
- explicit all-Vault tool scope는 item을 Vault ID별로 그룹화하고 path만으로
  merge하지 않습니다.
- 같은 timestamp는 deterministic output을 위해 Vault ID와 path로 정렬합니다.
- scale-up readiness record는 평가한 scope를 보고합니다.

## 13. Tests

Required tests:

- recent changes가 origin을 `vault_change`, `index_change`,
  `projection_change`, `warning`으로 분류
- `since`가 ISO timestamp를 올바르게 filter
- timestamp가 없어도 timeline output이 deterministic
- `timeline/recent` resource가 single Vault structured JSON 반환
- `get_recent_changes`가 tool output과 warnings serialize
- health explorer가 store mutation 없이 metadata, vector, graph, scale-up
  readiness 보고
- 같은 path를 가진 multi-Vault timelines가 충돌하지 않음
- read-only boundary tests가 Vault file mutation과 store initialization 없음 확인
- boundary tests가 raw episode log, session transcript, external memory-server
  persistence가 생성되지 않았음을 확인

Verification commands:

```bash
uv run --python 3.12 pytest tests/test_timeline_memory_service.py tests/test_health_explorer_service.py -q
uv run --python 3.12 pytest tests/test_mcp_recent_changes_tool.py tests/test_mcp_timeline_resource.py tests/test_mcp_resources.py tests/test_mcp_tools.py -q
VG_RUN_MCP_STDIO_SMOKE=1 uv run --python 3.12 pytest tests/test_mcp_stdio_smoke.py -q
uv run --python 3.12 ruff check src tests
uv run --python 3.12 mypy src tests
```

## 14. Risks And Mitigations

- **Risk:** timeline 사용자가 projection timestamp를 durable business event로
  오해할 수 있다.
  **Mitigation:** 모든 item에 `origin`과 evidence를 포함하고 projection change를
  별도로 label합니다.
- **Risk:** scale-up readiness가 speculative config system이 된다.
  **Mitigation:** known backend kinds와 contract readiness만 보고하고 migration
  behavior는 추가하지 않습니다.
- **Risk:** status payload가 너무 커진다.
  **Mitigation:** `HealthExplorerService`를 MCP serialization과 분리하고
  `check_index_status`에는 compact summary fields만 노출합니다.
- **Risk:** episodic-memory terminology 때문에 raw session 저장 압력이 생긴다.
  **Mitigation:** timeline item은 Vault-derived metadata와 projection status 위의
  projection만 사용합니다. Durable event는 먼저 Vault에 들어가야 합니다.

## 15. Open Decisions

Phase 6C에는 없음. Hosted monitoring과 remote backend migration은 future work로
남깁니다.
