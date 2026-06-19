# Phase 6A Result Explanation Contract SPEC

Status: Draft for implementation planning

Date: 2026-06-18

Scope: Phase 6A

## 1. 목적

Phase 6A는 MCP를 통해 반환된 Vault Graph 결과를 나중에 설명할 수 있게
만듭니다. agent는 `search_vault`, `build_context_pack`, `find_related`,
`get_decision_trace`가 반환한 결과에 대해 `explain_result(result_id)`를
호출하고, 그 결과가 왜 반환되었는지 설명하는 evidence, signals,
relationship status, warnings, store revisions를 받을 수 있어야 합니다.

이 설명은 durable memory store가 아닙니다. 현재 MCP process가 이미 반환한
결과 위에 만든 bounded runtime view입니다.

## 2. 성공 기준

Phase 6A는 다음 조건을 만족할 때 완료됩니다.

- `ExplainResultService`가 존재한 뒤에만 MCP가 `explain_result`를 등록합니다.
- `explain_result(result_id)`는 현재 MCP session에서 search, context-pack,
  related, decision-trace tool이 반환한 결과에 대한 structured explanation을
  반환합니다.
- explanation payload는 Vault IDs, document IDs, chunk IDs, resource links,
  evidence paths, signal scores, relationship status, warnings, store revisions를
  보존합니다.
- 누락되었거나 evicted된 explanation record는 original tool call rerun 안내와
  함께 not-found error를 반환합니다.
- explanation record는 Vault에 쓰이거나 durable knowledge로 저장되지 않습니다.
- text mirror는 structured output에 없는 사실을 추가하지 않습니다.

## 3. 범위

- `vault_graph.memory` package foundation
- result explanation DTOs와 serializers
- bounded in-process MCP explanation cache
- 기존 MCP tools의 explanation registration
- `explain_result` MCP tool과 input validation
- cache behavior, read-only boundary, serialization, current-session lookup
  focused tests

## 4. 범위 밖

- durable result history
- MCP server restart 이후의 result lookup
- answer synthesis 또는 `ask_vault`
- project memory summaries
- timeline projection
- generic `MemoryStore` 또는 writable memory API
- Mem0, MemMachine, MCP memory-server integration
- profile, preference, procedural, raw episode memory
- remote cache, database, observability backend
- automatic Vault publication

## 5. 추가/수정 파일

Add:

```text
src/vault_graph/memory/__init__.py
src/vault_graph/memory/result_explanation.py
src/vault_graph/mcp/result_explanation_cache.py
tests/test_result_explanation.py
tests/test_mcp_explain_result.py
tests/test_mcp_result_explanation_cache.py
```

Modify:

```text
src/vault_graph/mcp/mcp_server.py
src/vault_graph/mcp/mcp_tools.py
src/vault_graph/mcp/mcp_tool_serialization.py
src/vault_graph/mcp/__init__.py
tests/test_mcp_tools.py
tests/test_mcp_tool_serialization.py
tests/test_mcp_stdio_smoke.py
tests/test_mcp_tool_read_only_boundary.py
```

## 6. Data Model

`src/vault_graph/memory/result_explanation.py`가 MCP-free explanation DTO를
소유합니다.

```python
from dataclasses import dataclass
from typing import Literal

ExplanationSourceKind = Literal[
    "search_result",
    "context_pack_item",
    "related_item",
    "decision_trace_step",
]

ExplanationWarningSeverity = Literal["info", "warning", "error"]

@dataclass(frozen=True)
class ExplanationEvidenceRef:
    vault_id: str
    document_id: str
    chunk_id: str
    path: str
    section: str | None
    anchor: str | None
    content_hash: str
    raw_sha256: str | None
    metadata_index_revision: str | None
    vault_revision: str | None

@dataclass(frozen=True)
class ExplanationSignal:
    kind: str
    source_id: str | None
    rank: int | None
    score: float | None
    backend: str | None
    index_revision: str | None
    explanation: str

@dataclass(frozen=True)
class ExplanationWarning:
    code: str
    message: str
    severity: ExplanationWarningSeverity
    affected_vault_ids: tuple[str, ...]
    recovery_hint: str | None = None

@dataclass(frozen=True)
class ExplanationRecord:
    result_id: str
    source_kind: ExplanationSourceKind
    title: str
    summary: str
    vault_id: str
    evidence: tuple[ExplanationEvidenceRef, ...]
    signals: tuple[ExplanationSignal, ...]
    relationship_status: str | None
    store_revisions: tuple[dict[str, object], ...]
    warnings: tuple[ExplanationWarning, ...]
    resource_links: tuple[dict[str, object], ...]
    generated_at: str
```

Validation rules:

- `result_id`, `source_kind`, `title`, `vault_id`, `generated_at`은 필수입니다.
- 일반 결과에는 `evidence`가 필요합니다.
- `signals`는 graph 또는 context output처럼 relationship path로 설명되는
  경우에만 비어 있을 수 있습니다.
- 모든 warning은 affected Vault IDs를 가져야 합니다.

## 7. Cache Boundary

`src/vault_graph/mcp/result_explanation_cache.py`가 MCP runtime cache를
소유합니다.

```python
@dataclass(frozen=True)
class CachedExplanation:
    record: ExplanationRecord
    cached_at: str

class ResultExplanationCache:
    def __init__(self, *, max_entries: int = 256) -> None: ...
    def put(self, record: ExplanationRecord) -> None: ...
    def put_many(self, records: tuple[ExplanationRecord, ...]) -> None: ...
    def get(self, result_id: str) -> CachedExplanation | None: ...
    def __len__(self) -> int: ...
```

Cache rules:

- cache는 in-process이며 insertion order 기준 bounded입니다.
- `ContextPackResourceCache`처럼 `RegisteredMcpServer`와 함께 생성됩니다.
- disk에 serialize되지 않고 source of truth도 아닙니다.
- eviction은 허용됩니다. caller는 original query나 context tool을 다시 실행할
  수 있습니다.
- cache insertion은 Vault Graph state path나 Vault files를 mutate하지 않습니다.

## 8. Service Boundary

Phase 6A의 `ExplainResultService`는 cache만 읽습니다.

```python
class ExplainResultService:
    def __init__(self, *, cache: ResultExplanationCache) -> None: ...
    def explain(self, *, result_id: str) -> ExplanationRecord: ...
```

Errors:

- blank result ID: validation error
- missing result ID: recovery hint가 있는 not found
- malformed cached record: execution error이며 해당 cache entry는 무시

MVP에서는 result가 emit될 때 explanation record를 capture하므로 metadata,
vector, graph, Vault file reads가 필요하지 않습니다.

## 9. MCP Tool Contract

service가 존재한 뒤 MCP tool list에 `explain_result`를 추가합니다.

Input DTO:

```python
@dataclass(frozen=True)
class ExplainResultInput:
    result_id: str
```

Output envelope:

```json
{
  "tool_name": "explain_result",
  "payload": {
    "result_id": "...",
    "source_kind": "search_result",
    "title": "...",
    "summary": "...",
    "evidence": [],
    "signals": [],
    "relationship_status": "not_applicable",
    "store_revisions": [],
    "warnings": [],
    "generated_at": "..."
  },
  "resource_links": [],
  "warnings": [],
  "text": "{...}"
}
```

Registration rules:

- `McpToolRegistry.tool_names`에 `explain_result`를 append합니다.
- 기존 Phase 5C tool names와 behavior는 유지합니다.
- `tests/test_mcp_stdio_smoke.py`의 expected tool list를 업데이트합니다.
- prompt template은 tool이 등록된 뒤에만 `explain_result`를 언급할 수 있습니다.
- search result ID와 context-pack item ID는 이미 bounded handle입니다.
  related와 decision-trace의 `result_id`는 graph result identity를 canonical
  hash로 만든 고정 길이 runtime handle이어야 합니다. target/topic 같은 raw
  user input을 그대로 이어 붙이면 안 됩니다.

## 10. Explanation Registration

`mcp_tool_serialization.py`는 MCP-free conversion helper를 노출해야 합니다.

```python
def explanation_records_for_search(response: SearchResponse) -> tuple[ExplanationRecord, ...]: ...
def explanation_records_for_context_pack(pack: ContextPack) -> tuple[ExplanationRecord, ...]: ...
def explanation_records_for_related(response: RelatedResponse) -> tuple[ExplanationRecord, ...]: ...
def explanation_records_for_decision_trace(response: DecisionTraceResponse) -> tuple[ExplanationRecord, ...]: ...
```

`McpToolRegistry`는 service response가 준비된 뒤 helper를 호출합니다.
하지만 `ResultExplanationCache` 저장은 normal payload, resource links,
warnings, text mirror가 모두 성공적으로 assembled된 이후에만 수행합니다.
반환 전에 실패한 tool call은 explainable record를 남기면 안 됩니다.

helper는 tool payload를 변경하지 않습니다. 이미 반환되는 data에서 explanation
record만 만듭니다.

## 11. Read-Only And Rebuildability

- explanation cache는 runtime state이지 durable projection state가 아닙니다.
- cache를 삭제해도 최근 explainability convenience만 잃습니다.
- 같은 indexed Vault state에서 original MCP tool을 다시 실행하면 기능적으로
  동등한 explanation record를 다시 만들 수 있어야 합니다.
- Phase 6A path는 `VaultLoader`, `IndexService.run_apply(...)`, local store
  initializer, file-write API를 호출하지 않습니다.

## 12. Tests

Required tests:

- DTO validation은 blank IDs와 일반 결과의 missing evidence를 reject합니다.
- cache는 `max_entries` 초과 시 가장 오래된 record를 evict합니다.
- `explain_result`는 eviction 후 not found를 반환합니다.
- search, context-pack, related, decision-trace tool call은 explanation record를
  register합니다.
- `explain_result` output은 evidence, signals, warnings, revisions, resource
  links를 보존합니다.
- read-only boundary test는 tool calls가 Vault files를 mutate하지 않음을
  증명합니다.
- official MCP stdio smoke는 새 exact tool set을 확인합니다.

Verification commands:

```bash
uv run --python 3.12 pytest tests/test_result_explanation.py tests/test_mcp_explain_result.py tests/test_mcp_result_explanation_cache.py -q
uv run --python 3.12 pytest tests/test_mcp_tools.py tests/test_mcp_tool_serialization.py tests/test_mcp_tool_read_only_boundary.py -q
VG_RUN_MCP_STDIO_SMOKE=1 uv run --python 3.12 pytest tests/test_mcp_stdio_smoke.py -q
uv run --python 3.12 ruff check src tests
uv run --python 3.12 mypy src tests
```

## 13. Risks And Mitigations

- **Risk:** result ID가 query를 넘어 durable하지 않다.
  **Mitigation:** `explain_result`를 현재 MCP process로 명확히 제한하고,
  missing이면 rerun guidance를 반환합니다.
- **Risk:** cache record가 payload data를 중복한다.
  **Mitigation:** cache를 bounded로 유지하고 tool에 필요한 structured
  explanation fields만 저장합니다.
- **Risk:** prompt text가 등록되지 않은 tool에 의존한다.
  **Mitigation:** `explain_result` 등록 이후에만 prompt와 tests를 업데이트합니다.

## 14. Open Decisions

Phase 6A에는 없음. Durable result history는 의도적으로 범위 밖입니다.
