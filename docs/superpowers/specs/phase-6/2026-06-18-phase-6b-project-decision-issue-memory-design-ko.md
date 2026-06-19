# Phase 6B Project, Decision, And Issue Memory SPEC

Status: Draft for implementation planning

Date: 2026-06-18

Scope: Phase 6B

## 1. 목적

Phase 6B는 indexed Vault evidence 위에 deterministic memory projection을
추가합니다.

- project memory: current state, recent decisions, open issues, constraints,
  next likely priorities, stale areas
- decision memory: decision documents와 graph decision traces를 topic, status,
  tradeoff, revisit condition 기준으로 그룹화
- issue memory: unresolved questions, follow-ups, missing evidence, revisit
  triggers

목표는 agent가 whole Vault를 scan하지 않고 project memory를 확인할 수 있게
하는 것이며, generated summary를 durable knowledge로 바꾸는 것이 아닙니다.

## 2. 성공 기준

Phase 6B는 다음 조건을 만족할 때 완료됩니다.

- `ProjectMemoryService.summarize(...)`는 선택된 `QueryScope`에 대해
  evidence-linked structured projection을 반환합니다.
- `DecisionMemoryService.list_decisions(...)`는 durable decisions와 inferred
  topic traces를 그룹화하되, title만으로 Vault들을 merge하지 않습니다.
- `IssueMemoryService.open_questions(...)`는 unresolved questions와 follow-ups를
  evidence와 warnings와 함께 반환합니다.
- backing service가 존재한 뒤에만 MCP가 `summarize_project_memory`와
  `get_open_questions`를 등록합니다.
- `vault://{vault_id}/context/current`는 backend availability만이 아니라
  project memory projection을 반환합니다.
- output은 Vault IDs, evidence references, warnings, store revisions,
  freshness를 보존합니다.
- memory service는 Vault에 쓰지 않고 projection output을 source truth로
  취급하지 않습니다.

## 3. 범위

- project, decision, issue memory용 `vault_graph.memory` DTOs
- metadata-backed document listing contract
- path, frontmatter, headings, graph entity type 기반 deterministic document
  classification
- project memory와 open-question MCP tools
- `context/current` MCP resource upgrade
- read-only, multi-Vault, stale-state, serialization tests

## 4. 범위 밖

- LLM-written narrative summaries
- `ask_vault` answer synthesis
- autonomous wiki publication
- issue나 decision 자동 해결
- durable memory database
- generic writable `MemoryStore` 또는 `Memory.create/query/upsert/link/audit` API
- Mem0, MemMachine, MCP memory-server integration
- profile, preference, procedural, raw episode memory
- UI explorer screens
- remote backend migration

## 5. 추가/수정 파일

Add:

```text
src/vault_graph/memory/memory_models.py
src/vault_graph/memory/memory_source_reader.py
src/vault_graph/memory/project_memory.py
src/vault_graph/memory/decision_memory.py
src/vault_graph/memory/issue_memory.py
src/vault_graph/mcp/mcp_memory_serialization.py
tests/test_memory_models.py
tests/test_memory_source_reader.py
tests/test_project_memory_service.py
tests/test_decision_memory_service.py
tests/test_issue_memory_service.py
tests/test_mcp_memory_tools.py
tests/test_mcp_current_context_resource.py
```

Modify:

```text
src/vault_graph/storage/interfaces/metadata_store.py
src/vault_graph/storage/local/sqlite_metadata_store.py
src/vault_graph/mcp/mcp_service_factory.py
src/vault_graph/mcp/mcp_resources.py
src/vault_graph/mcp/mcp_tools.py
src/vault_graph/mcp/mcp_server.py
src/vault_graph/mcp/__init__.py
tests/fakes/
tests/test_mcp_resources.py
tests/test_mcp_stdio_smoke.py
```

## 6. Metadata Read Contract

Phase 6B는 direct SQLite query 없이 document-level frontmatter와 timestamp가
필요합니다. `MetadataStore`에 다음 method를 추가합니다.

```python
class MetadataStore(Protocol):
    def list_documents(self, scope: QueryScope) -> tuple[DocumentSnapshot, ...]: ...
```

Local implementation rules:

- non-tombstoned documents만 반환합니다.
- explicit `QueryScope.vault_ids`와 `content_scopes`로 filter합니다.
- deterministic output을 위해 `vault_id`, path 순서로 정렬합니다.
- read-only mode에서 schema를 initialize하지 않습니다.
- frontmatter, content hashes, `last_seen_at`, `last_indexed_at`,
  `vault_revision`, `index_revision`을 보존합니다.

이 method는 read-only이며 metadata evidence boundary에 속합니다. memory
service는 local SQLite table을 직접 query하지 않습니다.

## 7. Shared Memory Models

`src/vault_graph/memory/memory_models.py`가 shared MCP-free DTO를 소유합니다.

```python
from dataclasses import dataclass
from typing import Literal

MemoryItemKind = Literal[
    "current_state",
    "decision",
    "issue",
    "constraint",
    "next_priority",
    "stale_area",
]

MemoryWarningSeverity = Literal["info", "warning", "error"]

@dataclass(frozen=True)
class MemoryEvidenceRef:
    vault_id: str
    document_id: str
    chunk_id: str | None
    path: str
    section: str | None
    anchor: str | None
    content_hash: str
    raw_sha256: str | None
    metadata_index_revision: str | None
    vault_revision: str | None

@dataclass(frozen=True)
class MemoryWarning:
    code: str
    message: str
    severity: MemoryWarningSeverity
    affected_vault_ids: tuple[str, ...]
    recovery_hint: str | None = None

@dataclass(frozen=True)
class MemoryItem:
    item_id: str
    kind: MemoryItemKind
    title: str
    summary: str
    vault_id: str
    path: str
    status: str | None
    rank: int
    evidence: tuple[MemoryEvidenceRef, ...]
    warnings: tuple[MemoryWarning, ...]

@dataclass(frozen=True)
class ProjectMemoryProjection:
    requested_scope: QueryScope
    actual_scopes: tuple[QueryScope, ...]
    current_state: tuple[MemoryItem, ...]
    recent_decisions: tuple[MemoryItem, ...]
    open_questions: tuple[MemoryItem, ...]
    constraints: tuple[MemoryItem, ...]
    next_priorities: tuple[MemoryItem, ...]
    stale_areas: tuple[MemoryItem, ...]
    warnings: tuple[MemoryWarning, ...]
    store_revisions: tuple[dict[str, object], ...]
    generated_at: str
```

Model rules:

- `MemoryItem.summary`는 excerpt 또는 deterministic metadata summary입니다.
  LLM-written conclusion이 아닙니다.
- `MemoryItem`에는 최소 한 개 evidence reference가 필요합니다.
- `item_id`는 같은 `(kind, vault_id, document_id, path, status)`에 대해
  stable해야 합니다.
- projection group은 비어 있을 수 있지만, confidence에 영향을 주는 gap은
  top-level warning을 만듭니다.

## 8. Source Reader

`MemorySourceReader`가 document와 evidence loading을 중앙화합니다.

```python
@dataclass(frozen=True)
class MemoryDocumentRead:
    document: DocumentSnapshot
    evidence: tuple[MemoryEvidenceRef, ...]
    warnings: tuple[MemoryWarning, ...]

class MemorySourceReader:
    def __init__(self, *, metadata_store: MetadataStore) -> None: ...
    def list_documents(self, *, scope: QueryScope) -> tuple[DocumentSnapshot, ...]: ...
    def read_document(self, *, document: DocumentSnapshot, max_chunks: int = 3) -> MemoryDocumentRead: ...
    def read_documents(self, *, scope: QueryScope, max_chunks_per_document: int = 3) -> tuple[MemoryDocumentRead, ...]: ...
```

Rules:

- Vault files를 직접 읽지 않습니다.
- metadata store evidence resolution을 사용합니다.
- chunks가 없거나 unresolved evidence가 있으면 `MemoryDocumentRead.warnings`에
  warning을 반환합니다.
- memory payload가 커지지 않도록 document당 evidence를 cap합니다.

## 9. No Generic Writable Memory API

Phase 6B는 generic memory facade가 아니라 구체적인 read service를 노출합니다.
구현은 다음을 추가하면 안 됩니다.

- `MemoryStore`, `Memory.create`, `Memory.query`, `Memory.upsert`,
  `Memory.link`, `Memory.audit`
- writable project memory records
- raw episode logs 또는 session transcript storage
- profile, preference, procedural memory tables
- direct Mem0, MemMachine, MCP memory-server dependencies

향후 external memory adapter는 `ProjectMemoryProjection`,
`DecisionMemoryProjection`, `OpenQuestionsProjection`을 export할 수 있지만,
이 DTO를 outbound evidence-linked projection으로만 소비해야 합니다. Vault Graph
store에 write back하거나 agent-generated memory를 source truth로 만들면 안 됩니다.

## 10. Classification Policy

Classification은 deterministic하고 conservative합니다.

Decision candidates:

- path가 `wiki/decisions/`로 시작
- frontmatter `type: decision`
- graph service가 명시적으로 available할 때 graph entity type `Decision`

Issue 또는 open-question candidates:

- path가 `wiki/issues/`로 시작
- frontmatter `type: issue`
- frontmatter `status`가 `open`, `unresolved`, `todo`, `blocked`
- heading에 `Open Questions`, `Follow-up`, `TODO`, `Revisit` 포함

Current-state candidates:

- frontmatter `type`이 `project_status`, `status`, `roadmap`
- path에 `status`, `roadmap`, `plan`, `overview` 포함
- selected Vault scope 안의 root project documents 예: `README.md`,
  `docs/SPEC.md`, `docs/FEATURES.md`

Next-priority candidates:

- frontmatter `priority`, `next`, `roadmap`
- heading에 `Next`, `Priorities`, `Roadmap`, `Implementation Order` 포함

classification이 ambiguous하면 동일 evidence를 가진 item이 여러 group에
나타날 수 있고 `ambiguous_classification` warning을 포함합니다.

## 11. Services

Project memory:

```python
class ProjectMemoryService:
    def __init__(
        self,
        *,
        catalog: VaultCatalog,
        source_reader: MemorySourceReader,
        status_service: IndexService,
        clock: Callable[[], datetime] | None = None,
    ) -> None: ...

    def summarize(
        self,
        *,
        requested_scope: QueryScope,
        limit: int = 10,
    ) -> ProjectMemoryProjection: ...
```

Decision memory:

```python
@dataclass(frozen=True)
class DecisionMemoryProjection:
    requested_scope: QueryScope
    actual_scopes: tuple[QueryScope, ...]
    decisions: tuple[MemoryItem, ...]
    warnings: tuple[MemoryWarning, ...]
    store_revisions: tuple[dict[str, object], ...]
    generated_at: str

class DecisionMemoryService:
    def list_decisions(
        self,
        *,
        requested_scope: QueryScope,
        topic: str | None = None,
        limit: int = 20,
    ) -> DecisionMemoryProjection: ...
```

Issue memory:

```python
@dataclass(frozen=True)
class OpenQuestionsProjection:
    requested_scope: QueryScope
    actual_scopes: tuple[QueryScope, ...]
    questions: tuple[MemoryItem, ...]
    warnings: tuple[MemoryWarning, ...]
    store_revisions: tuple[dict[str, object], ...]
    generated_at: str

class IssueMemoryService:
    def open_questions(
        self,
        *,
        requested_scope: QueryScope,
        limit: int = 20,
    ) -> OpenQuestionsProjection: ...
```

service는 store read 전에 `actual_query_scopes(...)`로 requested scope를
expand해야 합니다.

## 12. MCP Tools And Resources

Add tools:

```text
summarize_project_memory(scope=None, limit=10)
get_open_questions(scope=None, limit=20)
```

MCP input DTOs:

```python
@dataclass(frozen=True)
class SummarizeProjectMemoryInput:
    scope: McpScopeInput | None = None
    limit: int = 10

@dataclass(frozen=True)
class GetOpenQuestionsInput:
    scope: McpScopeInput | None = None
    limit: int = 20
```

Resource upgrade:

```text
vault://{vault_id}/context/current
```

이 resource는 선택된 single Vault의 `ProjectMemoryProjection`을 반환합니다.
resource URI는 하나의 Vault ID를 가지므로 all-Vault summary는 tool-only로
유지합니다.

## 13. Error And Degradation Policy

- invalid scope 또는 unknown Vault ID: validation error
- missing metadata backend: `Run vg index` 안내가 포함된 execution error
- stale metadata: warning과 freshness fields
- missing vector backend: warning only. memory는 metadata evidence로 계속 동작
- missing graph backend: caller가 graph-derived decision grouping을 요청하지
  않는 한 warning only
- matching memory item 없음: successful empty projection과
  `no_memory_items_found` warning

## 14. Multi-Vault Policy

- default tools는 active Vault를 사용합니다.
- explicit all-Vault scope는 output을 `vault_id`별로 그룹화합니다.
- item IDs는 `vault_id`를 포함하며 title만으로 merge하지 않습니다.
- warnings는 affected Vault IDs를 포함합니다.
- Cross-Vault graph relationship grouping은 future graph memory slice에서
  명시적으로 요청하기 전까지 Phase 6B 범위 밖입니다.

## 15. Tests

Required tests:

- `MetadataStore.list_documents(...)` contract와 local implementation
- path, frontmatter, headings classification
- project memory가 evidence와 warnings를 deterministic하게 그룹화
- open questions가 issue docs와 follow-up headings를 포함
- decision memory가 durable decision docs를 우선
- 같은 path를 가진 multi-Vault documents가 충돌하지 않음
- MCP tools가 structured memory projection을 serialize
- `context/current`가 single Vault project memory를 반환
- read-only boundary tests가 Vault file mutation 없음 확인
- import 또는 boundary tests가 Phase 6B에 writable `MemoryStore`나 external
  memory dependency가 추가되지 않았음을 확인

Verification commands:

```bash
uv run --python 3.12 pytest tests/test_memory_models.py tests/test_memory_source_reader.py -q
uv run --python 3.12 pytest tests/test_project_memory_service.py tests/test_decision_memory_service.py tests/test_issue_memory_service.py -q
uv run --python 3.12 pytest tests/test_mcp_memory_tools.py tests/test_mcp_current_context_resource.py tests/test_mcp_resources.py -q
uv run --python 3.12 ruff check src tests
uv run --python 3.12 mypy src tests
```

## 16. Risks And Mitigations

- **Risk:** deterministic memory가 LLM summary보다 덜 자연스럽다.
  **Mitigation:** structured groups와 evidence를 우선 보존합니다. answer
  synthesis는 later phase입니다.
- **Risk:** broad document classification이 noisy memory를 만든다.
  **Mitigation:** classifier를 conservative하게 유지하고 limit을 두며 ambiguous
  items에 warning을 붙입니다.
- **Risk:** document listing 추가가 `MetadataStore`를 넓힌다.
  **Mitigation:** read-only, scope-filtered, contract-tested method로 제한하고
  local/future scale-up backends 모두 같은 contract를 따르게 합니다.
- **Risk:** "memory" naming 때문에 generic writable memory layer가 추가될 수 있다.
  **Mitigation:** 구체적인 read service만 유지하고 writable memory-store 또는
  external memory dependency를 거부하는 boundary test를 추가합니다.

## 17. Open Decisions

Phase 6B에는 없음. LLM-written project summaries는 범위 밖입니다.
