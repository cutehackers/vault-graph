# Phase 6B Project, Decision, And Issue Memory SPEC

Status: Draft for implementation planning

Date: 2026-06-18

Scope: Phase 6B

## 1. 목적

Phase 6B는 indexed Vault evidence 위에 deterministic memory projection을
추가합니다. Agent가 whole Vault를 scan하지 않고 current project state,
durable decisions, unresolved questions를 확인할 수 있게 하되, generated
output을 durable knowledge로 만들지 않습니다.

Phase 6B의 memory는 projection terminology입니다. writable memory database,
LLM summary store, external memory layer가 아닙니다. Project, decision, issue
memory의 모든 claim은 indexed Vault evidence로 되돌아갈 수 있어야 합니다.

## 2. 사용자 가치

Phase 6B는 다음 운영 질문에 답할 수 있어야 합니다.

- 이 project의 현재 상태는 무엇인가?
- 지금 중요한 decisions와 constraints는 무엇인가?
- 아직 unresolved question, TODO, blocker, revisit trigger가 무엇인가?
- 어떤 evidence와 index revision이 해당 memory item을 뒷받침하는가?
- 어떤 projection 영역이 stale, missing, ambiguous, degraded 상태인가?

출력은 사람과 agent를 위한 structured context입니다. Durable update는 여전히
Vault의 capture, validation, release gate, Git workflow를 통해야 합니다.

## 3. 성공 기준

Phase 6B는 다음 조건을 만족할 때 완료됩니다.

- `MetadataStore.list_documents(scope)`가 현재 non-tombstoned indexed document를
  read-only, scope-filtered document listing contract로 제공합니다.
- `MemorySourceReader`가 document snapshot과 bounded chunk evidence를
  `MetadataStore`로만 읽습니다. Vault file이나 SQLite table을 직접 읽지 않습니다.
- `ProjectMemoryService.summarize(...)`가 requested `QueryScope`에 대해 grouped,
  evidence-linked `ProjectMemoryProjection`을 반환합니다.
- `DecisionMemoryService.list_decisions(...)`가 durable decision evidence 위의
  decision memory를 Vault ID별로 그룹화하고, graph service가 있을 때
  topic-specific view를 기존 graph decision-trace evidence로 optional
  enrichment할 수 있습니다.
- `IssueMemoryService.open_questions(...)`가 unresolved issues, follow-ups,
  TODOs, blockers, revisit triggers를 evidence와 warnings와 함께 반환합니다.
- backing service가 존재한 뒤에만 MCP가 `summarize_project_memory`와
  `get_open_questions`를 등록합니다.
- `vault://{vault_id}/context/current`는 Phase 5B backend-availability placeholder
  대신 single-Vault project memory projection을 반환합니다.
- output은 Vault IDs, stable item IDs, evidence references, warnings, store
  revisions, freshness, actual scopes, generated timestamps를 보존합니다.
- multi-Vault output은 `vault_id`별로 그룹화하고 title만으로 documents,
  decisions, issues, entities를 merge하지 않습니다.
- Phase 6B service는 Vault에 쓰지 않고, read-only store를 initialize하지 않고,
  memory record를 persist하지 않고, external memory system을 import하지 않고,
  projection output을 source truth로 취급하지 않습니다.

## 4. 범위

- project, decision, issue projection용 MCP-free memory DTO
- `MetadataStore`의 metadata-backed document listing
- indexed chunks 기반 bounded evidence loading
- path, frontmatter, headings, 그리고 기존 graph service가 제공하는 optional
  graph evidence를 이용한 deterministic document classification
- project memory와 open-question MCP tools
- `context/current` MCP resource upgrade
- broad Vault scan보다 memory tool을 먼저 사용하도록 prompt text 업데이트
- read-only, multi-Vault, stale-state, serialization, import-boundary tests

## 5. 범위 밖

- LLM-written narrative summaries
- `ask_vault` answer synthesis
- autonomous wiki publication 또는 Vault edits
- issue나 decision 자동 해결
- durable memory database 또는 memory history
- generic writable `MemoryStore` 또는 `Memory.create/query/upsert/link/audit` API
- Mem0, MemMachine, MCP memory-server integration
- profile, preference, procedural, raw episode memory
- UI explorer screens
- remote backend migration
- hosted monitoring

## 6. 추가/수정 파일

Add:

```text
src/vault_graph/memory/memory_models.py
src/vault_graph/memory/memory_source_reader.py
src/vault_graph/memory/memory_request_context.py
src/vault_graph/memory/project_memory.py
src/vault_graph/memory/decision_memory.py
src/vault_graph/memory/issue_memory.py
src/vault_graph/mcp/mcp_memory_serialization.py
tests/test_memory_models.py
tests/test_memory_source_reader.py
tests/test_memory_request_context.py
tests/test_project_memory_service.py
tests/test_decision_memory_service.py
tests/test_issue_memory_service.py
tests/test_mcp_memory_tools.py
tests/test_mcp_current_context_resource.py
```

Modify:

```text
src/vault_graph/errors.py
src/vault_graph/memory/__init__.py
src/vault_graph/storage/interfaces/metadata_store.py
src/vault_graph/storage/local/sqlite_metadata_store.py
src/vault_graph/mcp/__init__.py
src/vault_graph/mcp/mcp_errors.py
src/vault_graph/mcp/mcp_prompts.py
src/vault_graph/mcp/mcp_resources.py
src/vault_graph/mcp/mcp_server.py
src/vault_graph/mcp/mcp_service_factory.py
src/vault_graph/mcp/mcp_tools.py
tests/fakes/
tests/test_mcp_errors.py
tests/test_mcp_prompts.py
tests/test_mcp_resource_read_only_boundary.py
tests/test_mcp_resources.py
tests/test_mcp_server.py
tests/test_mcp_service_factory.py
tests/test_mcp_stdio_smoke.py
```

`data/memory/` 같은 persistence file은 추가하지 않습니다. Phase 6B projection은
request 시점에 existing derived indexes에서 계산합니다.

## 7. 기존 의존성

Phase 6B는 현재 code contract 위에 설계됩니다.

- `vault_graph.ingestion.document_normalizer`의 `DocumentSnapshot`,
  `ChunkSnapshot`
- `QueryScope`, `VaultCatalog`, `actual_query_scopes(...)`
- `MetadataStore.list_document_chunks(...)`,
  `MetadataStore.resolve_chunk_evidence(...)`
- freshness와 backend degradation을 위한 `IndexService.status(...)`
- topic-specific decision memory enrichment에 한해 optional로 사용하는
  `GraphRetrievalService.decision_trace(...)`
- Phase 6A의 `vault_graph.memory` package와 MCP read-only adapter style

MCP와 resource layer는 memory application service에 의존해야 합니다.
classification을 복제하거나 SQLite를 직접 query하거나 Vault file을 읽으면 안 됩니다.

## 8. Metadata Read Contract

Phase 6B는 direct SQLite query 없이 document-level frontmatter, path, timestamps,
hashes, index revision data가 필요합니다. `MetadataStore`에 다음 method를 추가합니다.

```python
class MetadataStore(Protocol):
    def list_documents(self, scope: QueryScope) -> tuple[DocumentSnapshot, ...]: ...
```

Local implementation rules:

- 현재 non-tombstoned documents만 반환합니다.
- metadata database가 없으면 initialize하지 않고 `()`를 반환합니다.
- `scope.vault_ids`로 filter합니다.
- chunk listing과 같은 content-scope narrowing rule로 `scope.content_scopes`를
  filter합니다.
- `vault_id`, `path`, `document_id` 순서로 정렬합니다.
- 현재 `DocumentSnapshot` field를 그대로 보존합니다:
  `vault_id`, `document_id`, `path`, `kind`, `frontmatter`,
  `frontmatter_hash`, `content_hash`, `raw_sha256`, `parser_version`,
  `last_seen_at`, `last_indexed_at`, `vault_revision`, `index_revision`.
- schema creation, migration, tombstone update, keyword/vector/graph/status
  mutation을 하지 않습니다.

이 method는 metadata evidence boundary에 속합니다. Memory service는 local SQLite
table names, row IDs, private store fields에 의존하지 않습니다.

## 9. Shared Memory Models

`src/vault_graph/memory/memory_models.py`가 shared MCP-free DTO를 소유합니다.

```python
from dataclasses import dataclass
from typing import Literal

MemoryItemKind = Literal[
    "current_state",
    "decision",
    "open_question",
    "constraint",
    "next_priority",
    "stale_area",
]
MemoryClaimStatus = Literal[
    "stated",
    "metadata_derived",
    "heading_candidate",
]
MemoryWarningSeverity = Literal["info", "warning", "error"]
MemoryFreshness = Literal["fresh", "stale", "unavailable", "unknown"]
MemoryDocumentResourceKind = Literal["document", "page", "source", "decision", "issue"]

@dataclass(frozen=True)
class MemoryEvidenceRef:
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
class MemoryWarning:
    code: str
    message: str
    severity: MemoryWarningSeverity
    affected_vault_ids: tuple[str, ...]
    recovery_hint: str | None = None

@dataclass(frozen=True)
class MemoryBackendRevision:
    kind: str
    revision: str | None
    vault_id: str | None
    scope_key: str

@dataclass(frozen=True)
class MemoryItem:
    item_id: str
    kind: MemoryItemKind
    claim_status: MemoryClaimStatus
    matched_signals: tuple[str, ...]
    document_resource_kinds: tuple[MemoryDocumentResourceKind, ...]
    title: str
    summary: str
    vault_id: str
    path: str
    status: str | None
    rank: int
    evidence: tuple[MemoryEvidenceRef, ...]
    warnings: tuple[MemoryWarning, ...]

@dataclass(frozen=True)
class ProjectMemoryVault:
    vault_id: str
    display_name: str
    current_state: tuple[MemoryItem, ...]
    decisions: tuple[MemoryItem, ...]
    open_questions: tuple[MemoryItem, ...]
    constraints: tuple[MemoryItem, ...]
    next_priorities: tuple[MemoryItem, ...]
    stale_areas: tuple[MemoryItem, ...]
    warnings: tuple[MemoryWarning, ...]
    store_revisions: tuple[MemoryBackendRevision, ...]
    freshness: MemoryFreshness

@dataclass(frozen=True)
class ProjectMemoryProjection:
    requested_scope: QueryScope
    actual_scopes: tuple[QueryScope, ...]
    vaults: tuple[ProjectMemoryVault, ...]
    warnings: tuple[MemoryWarning, ...]
    generated_at: str
```

Decision과 issue projection도 같은 grouping pattern을 사용합니다.

```python
@dataclass(frozen=True)
class DecisionMemoryVault:
    vault_id: str
    display_name: str
    decisions: tuple[MemoryItem, ...]
    warnings: tuple[MemoryWarning, ...]
    store_revisions: tuple[MemoryBackendRevision, ...]
    freshness: MemoryFreshness

@dataclass(frozen=True)
class DecisionMemoryProjection:
    requested_scope: QueryScope
    actual_scopes: tuple[QueryScope, ...]
    topic: str | None
    vaults: tuple[DecisionMemoryVault, ...]
    warnings: tuple[MemoryWarning, ...]
    generated_at: str

@dataclass(frozen=True)
class OpenQuestionsVault:
    vault_id: str
    display_name: str
    questions: tuple[MemoryItem, ...]
    warnings: tuple[MemoryWarning, ...]
    store_revisions: tuple[MemoryBackendRevision, ...]
    freshness: MemoryFreshness

@dataclass(frozen=True)
class OpenQuestionsProjection:
    requested_scope: QueryScope
    actual_scopes: tuple[QueryScope, ...]
    vaults: tuple[OpenQuestionsVault, ...]
    warnings: tuple[MemoryWarning, ...]
    generated_at: str
```

Model rules:

- constructor는 existing retrieval/context-pack DTO처럼 required strings와 tuple
  immutability를 validate합니다.
- `MemoryItem.evidence`는 최소 한 개 chunk evidence reference를 포함해야 합니다.
  resolved chunk evidence가 없는 document는 warning을 만들고 factual memory item으로
  emit하지 않습니다.
- `MemoryItem.summary`는 deterministic excerpt 또는 metadata-derived phrase입니다.
  LLM-written conclusion이 아닙니다.
- `MemoryItem.document_resource_kinds`는 backing document에 대해 유효한 existing
  MCP document resource view를 나열합니다. 항상 `document`를 포함해야 하며,
  backing path 또는 canonical frontmatter가 기존 resource-reader classifier를
  만족할 때만 `page`, `source`, `decision`, `issue`를 포함할 수 있습니다.
  heading-only candidate는 document path나 frontmatter도 해당 resource를
  지원하지 않는 한 `decision` 또는 `issue` resource kind를 받으면 안 됩니다.
- `claim_status`는 item이 식별된 방식을 표시합니다.
  - `stated`: frontmatter type/status 또는 canonical decision/issue path처럼
    canonical Vault evidence가 classification을 직접 말합니다.
  - `metadata_derived`: path, document kind, non-canonical frontmatter가
    classification을 제안합니다.
  - `heading_candidate`: heading이 classification을 제안하지만 document가 canonical
    metadata로 말하지는 않습니다.
- text mirror와 MCP payload는 `claim_status`, `matched_signals`를 보존해야 합니다.
  그래야 heuristic candidate가 stated Vault fact처럼 보이지 않습니다.
- graph enrichment는 `graph_decision_trace` 같은 `matched_signals`로 표현합니다.
  item의 original `claim_status`를 override하지 않습니다.
- `item_id`는 canonical fields에서 만든 bounded stable handle입니다:
  `memory:<kind>:<24 hex chars>`. Hash input에는 `kind`, `vault_id`,
  `document_id`, primary evidence `chunk_id`, normalized title, normalized
  `status`, `claim_status`가 들어갑니다.
- `rank`는 Vault group과 item kind 안에서 `1`부터 시작합니다.
- top-level warnings는 scope/backend 문제, Vault-group warnings는 Vault-specific
  gap, item warnings는 item-specific ambiguity를 나타냅니다.
- Phase 6B는 decisions 또는 durable changes에 대해 evidence-backed recency를
  주장하지 않습니다. Timeline-based recent changes는 Phase 6C의 책임입니다.
  project memory가 `context/current`에서 사용될 수 있으므로, 해당 resource는
  Phase 6C가 timeline-backed recent changes를 제공하기 전까지
  `recent_changes_unavailable_until_phase_6c` info warning을 추가할 수 있습니다.

## 10. Source Reader

`MemorySourceReader`가 document와 evidence loading을 중앙화합니다.

```python
@dataclass(frozen=True)
class MemoryHeadingRef:
    chunk_id: str
    section: str
    anchor: str | None

@dataclass(frozen=True)
class MemoryDocumentRead:
    document: DocumentSnapshot
    evidence: tuple[MemoryEvidenceRef, ...]
    headings: tuple[MemoryHeadingRef, ...]
    body_excerpt: str | None
    warnings: tuple[MemoryWarning, ...]

class MemorySourceReader:
    def __init__(self, *, metadata_store: MetadataStore) -> None: ...
    def list_documents(self, *, scope: QueryScope) -> tuple[DocumentSnapshot, ...]: ...
    def read_document(
        self,
        *,
        document: DocumentSnapshot,
        max_evidence_chunks: int = 3,
        preferred_chunk_ids: tuple[str, ...] = (),
    ) -> MemoryDocumentRead: ...
```

Rules:

- `list_documents(...)`는 `MetadataStore.list_documents(...)`에 delegate합니다.
- `read_document(...)`는
  `MetadataStore.list_document_chunks(vault_id=..., document_id=...)`와
  `resolve_chunk_evidence(...)`를 사용합니다.
- `MemorySourceReader`는 Phase 6B에서 scope-level `read_documents(...)` method를
  노출하지 않습니다. Service가 candidate narrowing을 소유하고, 선택된 document
  snapshot에 대해서만 `read_document(...)`를 호출합니다.
- chunk order는 indexed document order를 보존하는 `list_document_chunks(...)`를
  따릅니다.
- selected document의 모든 chunk heading을 inspect하고 `MemoryHeadingRef`로
  반환합니다. Heading inspection은 evidence payload size와 분리합니다.
- payload bound를 위해 evidence는 `max_evidence_chunks`로 cap합니다.
- `preferred_chunk_ids`를 먼저 resolve하고, 이후 document-order chunks가 evidence
  cap을 채웁니다. Service는 이를 사용해 `Decision`, `TODO`, `Blocker`, `Revisit`
  같은 heading rule에 match한 chunk가 세 번째 chunk 뒤에 있더라도 bounded evidence
  안에 우선 포함합니다.
- `headings`는 Vault file을 reparsing하지 않고 resolved chunks의 `section`에서
  가져옵니다.
- `body_excerpt`는 첫 non-empty chunk text를 deterministic maximum 280자로 trim한
  값입니다.
- unresolved chunk evidence는 `unresolved_evidence` warning을 만듭니다.
- chunk가 없는 document는 `document_has_no_chunks` warning을 만듭니다.
- read method는 indexing 실행, store initialize, Vault path access, evidence
  synthesis를 하지 않습니다.

`MemoryRequestContext`는 memory service가 공유하는 작은 per-request read
context입니다.

```python
@dataclass(frozen=True)
class MemoryVaultDocuments:
    vault_id: str
    scope: QueryScope
    documents: tuple[DocumentSnapshot, ...]

@dataclass(frozen=True)
class MemoryRequestContext:
    requested_scope: QueryScope
    actual_scopes: tuple[QueryScope, ...]
    status_report: StatusReport
    documents_by_vault: tuple[MemoryVaultDocuments, ...]
    generated_at: str
```

Context rules:

- context creation은 actual scopes를 resolve하고, `IndexService.status(...)`를
  확인하고, actual Vault scope마다 document snapshot을 한 번 listing합니다.
- metadata가 unavailable이거나 schema-incompatible이면
  `MemoryProjectionError("metadata_unavailable: ...")`를 raise합니다.
- context creation은 chunks, graph data, Vault file을 읽지 않습니다.
- `ProjectMemoryService`는 context를 한 번 만들고, 해당 context를 소비하는
  package-internal decision/issue service method를 사용합니다. 그래서 project
  memory가 metadata/status scan을 반복하지 않습니다.

## 11. Candidate Narrowing Policy

"Without scanning the whole Vault"는 Phase 6B가 request 시점에 Vault source file을
읽지 않는다는 뜻입니다. 선택된 `QueryScope`에 대해 indexed metadata rows를 scan하는
것은 허용됩니다.

Service는 chunk evidence read 전에 candidate를 좁혀야 합니다.

1. `MetadataStore.list_documents(...)`로 document snapshot을 listing합니다.
2. path, document kind, frontmatter type/status, revision metadata를 먼저
   classify합니다.
3. path, document kind, frontmatter, revision metadata, 기타 document-level indexed
   field로 match된 document에서 deterministic per-Vault candidate set을 선택합니다.
4. 선택된 candidate에 대해서만 chunks를 읽습니다.
5. 선택된 candidate에서는 모든 heading을 inspect하되 evidence와 excerpt는 cap합니다.
6. candidate set이 read cap을 초과하면 `candidate_scan_truncated` warning을
   반환합니다.

Default bounds:

- `candidate_read_limit = min(max(limit * 10, 50), 250)` per Vault and per service
  call
- `max_evidence_chunks = 3` per emitted memory item

이 constants는 나중에 tuning될 수 있지만 Phase 6B의 behavior는 같아야 합니다:
metadata-first narrowing, bounded chunk reads, deterministic ordering, visible
truncation warnings.

Heading-only match는 Phase 6B에서 metadata-selected document 내부로 의도적으로
제한합니다. Service는 arbitrary TODO heading을 발견하기 위해 large scope의 모든
document chunk를 scan하면 안 됩니다. 이 때문에 otherwise unclassified TODO를 놓칠 수
있다면 사용자가 scope를 좁히거나 이후 search/context flow를 사용해야 합니다. Phase
6B는 unbounded heading mining보다 bounded, explainable projection을 우선합니다.

## 12. Classification Policy

Classification은 deterministic하고 conservative합니다. Path segments,
frontmatter string values, heading matches는 case-insensitive로 비교합니다.

Heading rule은 metadata-selected document만 refine합니다. Document는 path,
document kind, frontmatter, revision metadata, 기타 document-level indexed field를
통해 metadata-selected가 됩니다. Phase 6B는 otherwise unclassified document 전체의
heading을 scan하지 않습니다.

Decision candidates:

- path가 `wiki/decisions/`로 시작
- frontmatter `type`이 `decision`
- frontmatter `decision`이 존재
- metadata-selected document 내부 heading에 `Decision`, `Alternatives`,
  `Tradeoff`, `Revisit` 포함
- optional graph decision-trace enrichment가 decision entity를 식별

Decision classification rules:

- `stated` decision은 canonical decision path, frontmatter `type: decision`, 또는
  explicit decision frontmatter가 필요합니다.
- heading-only decision match는 `candidate_decision` warning을 가진
  `heading_candidate` item입니다. Useful context이지만 text mirror에서 durable
  decision으로 label하면 안 됩니다.
- graph-enriched decision context는 underlying item의 original `claim_status`를
  유지합니다. Graph evidence가 relationship context를 추가하면 `matched_signals`에
  `graph_decision_trace`를 포함합니다.

Open-question candidates:

- path가 `wiki/issues/`로 시작하고 document가 active 또는 unresolved status를 가짐
- frontmatter `type`이 `issue`, `question`, `follow_up`이고 document가 active 또는
  unresolved status를 가짐
- frontmatter `status`가 `open`, `unresolved`, `todo`, `blocked`, `revisit`
- heading에 `Open Questions`, `Question`, `Follow-up`, `TODO`, `Blocker`,
  `Revisit` 포함. 단, metadata-selected document 내부 heading에 한정합니다.

Open-question exclusion rules:

- frontmatter `status`가 `closed`, `resolved`, `done`, `accepted`, `superseded`,
  `deprecated`, `cancelled`이면 `open_question` output에서 제외합니다.
- missing status인 issue document는 metadata-selected document 내부에서 explicit
  open-question heading이 match된 경우에만 emit하고 `missing_issue_status` warning을
  포함합니다.
- missing status이고 explicit open-question heading도 없으면 open fact로 emit하지
  않습니다.

Current-state candidates:

- frontmatter `type`이 `project_status`, `status`, `roadmap`, `plan`, `overview`
- path에 `status`, `roadmap`, `plan`, `overview` 포함
- selected Vault scope 안에 있는 project documents 예: `docs/SPEC.md`,
  `docs/FEATURES.md`
- root-level `README.md`는 Phase 6B에서 의도적으로 제외합니다. 현재 `QueryScope`
  roots가 repository-root document를 포함하지 않기 때문입니다.

Constraint candidates:

- frontmatter에 `constraint`, `policy`, `boundary`, `invariant` 포함
- path에 `policy`, `decision`, `convention`, `boundary` 포함
- heading에 `Constraint`, `Policy`, `Boundary`, `Invariant`, `Non-goal` 포함

Next-priority candidates:

- frontmatter에 `priority`, `next`, `roadmap`, `phase` 포함
- heading에 `Next`, `Priorities`, `Roadmap`, `Implementation Order`, `TODO` 포함
  단, metadata-selected document 내부 heading에 한정합니다.

Stale-area candidates:

- document frontmatter `status`가 `stale`, `deprecated`, `superseded`
- path 또는 heading이 deprecated/superseded project area를 나타냄

Backend stale, unavailable, incompatible state는 `stale_area` `MemoryItem`이 아니라
`freshness`와 warnings에 속합니다. Vault document 자체가 stale area에 대한 evidence를
제공할 때만 `stale_area` item으로 emit합니다.

Ambiguous classification:

- 한 document가 여러 rule에 match하면 여러 group에 나타날 수 있습니다.
- ambiguous item은 matched groups를 포함한 `ambiguous_classification` warning을
  가집니다.
- classifier는 ambiguity를 숨기고 한 group만 고르면 안 됩니다.

Ranking:

1. exact frontmatter type/status matches
2. path-root matches
3. heading matches
4. optional graph-enriched decision trace matches
5. fallback path-name matches

같은 rank tier에서는 `vault_id`, normalized path, stable `item_id` 순서로 정렬합니다.

## 13. Services

Services는 MCP-free, read-only입니다. 모든 service는 store read 전에
`actual_query_scopes(catalog=catalog, scope=requested_scope)`로 requested scope를
expand합니다.

Project memory:

```python
class ProjectMemoryService:
    def __init__(
        self,
        *,
        catalog: VaultCatalog,
        source_reader: MemorySourceReader,
        decision_service: DecisionMemoryService,
        issue_service: IssueMemoryService,
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
from vault_graph.retrieval.graph_retrieval import GraphOutputFormat

class DecisionTraceProvider(Protocol):
    def decision_trace(
        self,
        *,
        topic: str,
        requested_scope: QueryScope,
        depth: int = 2,
        include_cross_vault: bool = False,
        limit: int = 10,
        output_format: GraphOutputFormat = "text",
    ) -> DecisionTraceResponse: ...

class DecisionMemoryService:
    def __init__(
        self,
        *,
        catalog: VaultCatalog,
        source_reader: MemorySourceReader,
        status_service: IndexService,
        decision_trace_provider_factory: Callable[[], DecisionTraceProvider] | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None: ...

    def list_decisions(
        self,
        *,
        requested_scope: QueryScope,
        topic: str | None = None,
        limit: int = 20,
        include_graph: bool = False,
    ) -> DecisionMemoryProjection: ...

    def _list_decisions_from_context(
        self,
        *,
        context: MemoryRequestContext,
        topic: str | None = None,
        limit: int = 20,
        include_graph: bool = False,
    ) -> DecisionMemoryProjection: ...
```

Issue memory:

```python
class IssueMemoryService:
    def __init__(
        self,
        *,
        catalog: VaultCatalog,
        source_reader: MemorySourceReader,
        status_service: IndexService,
        clock: Callable[[], datetime] | None = None,
    ) -> None: ...

    def open_questions(
        self,
        *,
        requested_scope: QueryScope,
        limit: int = 20,
    ) -> OpenQuestionsProjection: ...

    def _open_questions_from_context(
        self,
        *,
        context: MemoryRequestContext,
        limit: int = 20,
    ) -> OpenQuestionsProjection: ...
```

Service rules:

- service는 document listing 전에 `IndexService.status(...)`를 호출합니다.
  metadata health가 unavailable 또는 schema-incompatible이면 low-level store의
  empty result를 empty project로 취급하지 않고
  `MemoryProjectionError("metadata_unavailable: ...")`를 raise합니다.
- standalone decision/issue service call은 자체 `MemoryRequestContext`를 만들고,
  project memory는 context를 한 번 만들어 package-internal decision/issue service
  method에 전달합니다.
- `limit`은 `1..50`입니다. 더 큰 MCP limit은 validation error입니다.
- limit은 Vault group별, primary group별로 적용됩니다.
  `ProjectMemoryService`에서는 각 group이 최대 `limit` item을 가집니다.
- `ProjectMemoryService`는 decision/open-question classification을 복제하지 않고
  decision service와 issue service 결과를 compose합니다.
- `DecisionMemoryService`는 durable decision document를 우선합니다.
- Graph trace enrichment는 additive이며
  `decision_trace_provider_factory`를 통해 existing read-only graph service만
  사용합니다.
- `decision_trace_provider_factory`는 `topic is not None`이고 `include_graph=True`인
  경우에만 호출됩니다. Project-memory summary는 side effect로 graph service를 열면
  안 됩니다.
- factory는 concrete `GraphRetrievalService`를 반환합니다. 이 service가
  `DecisionTraceProvider`를 만족하므로 adapter는 필요하지 않습니다.
- Decision enrichment는 provider를 호출할 때 `output_format="json"`을 명시하고,
  later slice가 public depth control을 설계하기 전까지 default graph `depth=2`를
  유지합니다.
- graph enrichment를 사용할 수 없으면 durable metadata-backed decision을 반환하고
  warning을 붙입니다.
- Store revisions는 document `index_revision`과 status service revision fields에서
  구성합니다. Missing revision은 invented string이 아니라 `None`입니다.
- stale/unavailable backend는 warnings와 freshness fields를 만듭니다. text mirror에서
  사라지면 안 됩니다.

## 14. MCP Tools And Resources

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

MCP tool registration rules:

- `McpToolName`에 `summarize_project_memory`, `get_open_questions`를 append합니다.
- `tests/test_mcp_stdio_smoke.py`는 exact expected tool list를 업데이트합니다.
- tools는 `scope_from_mcp_input(...)`으로 scope를 resolve합니다.
- tools는 active-Vault default, explicit `vault_ids`, `all_vaults`를 지원합니다.
- `include_cross_vault`는 graph-only이며 이 memory tool에서는 허용하지 않습니다.
- `DecisionMemoryService.list_decisions(...)`는 Phase 6B에서 새 MCP tool로 노출하지
  않습니다. 기존 `get_decision_trace`가 graph-specific decision-tracing surface로
  남습니다. Decision memory는 project memory 내부에 공급되고, 필요하면 future
  explicit tool로 노출할 수 있습니다.

Serialization:

```python
def project_memory_projection_to_payload(
    projection: ProjectMemoryProjection,
) -> dict[str, object]: ...

def open_questions_projection_to_payload(
    projection: OpenQuestionsProjection,
) -> dict[str, object]: ...

def resource_links_for_memory_projection(
    projection: ProjectMemoryProjection | OpenQuestionsProjection,
) -> tuple[McpResourceLink, ...]: ...
```

Resource-link rules:

- 모든 evidence-backed item은 underlying document 또는 page resource로 link합니다.
- resource serializer는 어떤 existing resource link가 유효한지 판단할 때
  `MemoryItem.document_resource_kinds`를 사용합니다.
- `document_resource_kinds`에 `issue`가 있는 `open_question` item은 existing
  `vault://{vault_id}/issues/{document_id}` resource에도 link합니다.
- `document_resource_kinds`에 `decision`이 있는 decision item은 existing
  `vault://{vault_id}/decisions/{document_id}` resource에도 link합니다.
- memory tool은 새 writable memory resource URI를 만들면 안 됩니다.

Output envelope는 existing MCP tool body를 따릅니다.

```json
{
  "tool_name": "summarize_project_memory",
  "payload": {
    "requested_scope": {},
    "actual_scopes": [],
    "vaults": [],
    "warnings": [],
    "generated_at": "..."
  },
  "resource_links": [],
  "warnings": [],
  "text": "{...}"
}
```

Resource upgrade:

```text
vault://{vault_id}/context/current
```

Resource rules:

- resource는 정확히 한 Vault의 `ProjectMemoryProjection`을 반환합니다.
- resource scope는 `catalog.scope_for_vault_ids((vault_id,))`입니다.
- URI가 하나의 Vault ID를 가지므로 all-Vault summary는 tool-only입니다.
- resource는 `application/json`을 유지합니다.
- project memory가 unavailable하면 `Run vg index` 또는 `Run vg status` recovery
  hint를 포함한 MCP resource error를 반환합니다.

Prompt updates:

- `generate_codex_brief`, `prepare_implementation_context`는 Phase 6B tool이
  존재하면 broad search 전에 `summarize_project_memory`를 호출해야 합니다.
- risk와 wiki-update prompts는 unresolved follow-up context가 중요할 때
  `get_open_questions`를 호출해야 합니다.
- prompt는 read-only Vault boundary를 유지하고 Vault Graph로 publication을
  제안하면 안 됩니다.

## 15. Service Factory Handoff

`McpServiceFactory`는 lazy read-only construction method를 추가합니다.

```python
class McpServiceFactory:
    def open_memory_source_reader(self) -> MemorySourceReader: ...
    def open_decision_memory_service(self) -> DecisionMemoryService: ...
    def open_issue_memory_service(self) -> IssueMemoryService: ...
    def open_project_memory_service(self) -> ProjectMemoryService: ...
```

Rules:

- 각 method는 `initialize=False`와 existing read-only flags로 store를 엽니다.
- graph retrieval은 factory로 전달하고,
  `DecisionMemoryService.list_decisions(..., topic=..., include_graph=True)`가
  topic-specific graph enrichment를 요청할 때만 lazy open합니다.
- repeated construction이 실제 문제가 되기 전에는 memory service를 `McpServices`
  field로 만들지 않습니다.
- memory-specific storage directory를 만들지 않습니다.

## 16. Error And Degradation Policy

`src/vault_graph/errors.py`에 `MemoryProjectionError`를 추가합니다.

MCP error mapping:

- invalid MCP tool limit은 `mcp_tools._limit(...)`의 existing
  `invalid_tool_arguments` code와 `invalid_parameter` kind를 사용합니다.
- `memory_projection_unavailable` -> `execution`
- `metadata_unavailable` -> `execution`
- `memory_evidence_unresolved` -> requested projection에서 evidence-backed item을
  전혀 반환할 수 없을 때만 `execution`
- `invalid_memory_limit` -> direct service call에 대해서는 `execution`; MCP tool
  call은 그 전에 `invalid_tool_arguments`로 invalid limit을 reject해야 합니다.

Behavior rules:

- invalid scope 또는 unknown Vault ID: validation error
- disabled Vault ID: existing scope handling의 validation error
- missing metadata backend: `Run vg index` 안내가 포함된 execution error
- metadata backend가 있지만 empty: successful empty projection +
  `no_memory_items_found`
- stale metadata: freshness `stale`과 warnings가 포함된 successful projection
- missing vector backend: warning only
- missing graph backend: topic-specific decision-memory call이 graph enrichment를
  명시적으로 요청한 경우를 제외하고 warning only
- matching memory item 없음: successful empty projection +
  `no_memory_items_found`
- text mirror는 structured payload의 warning을 누락하면 안 됩니다.

## 17. Multi-Vault Policy

- default tools는 active Vault를 사용합니다.
- explicit `all_vaults`는 service call 전에 enabled Vault entries로 expand합니다.
- projection은 actual Vault scope마다 하나의 Vault group을 포함합니다.
- stable item IDs는 `vault_id`를 포함하며 title, path, entity name만으로 merge하지
  않습니다.
- warnings는 affected Vault IDs를 포함합니다.
- resource URI는 single-Vault only입니다.
- cross-Vault graph relationship grouping은 Phase 6B 범위 밖입니다.

## 18. Read-Only And Rebuildability

- Phase 6B는 Vault files와 derived memory files에 쓰지 않습니다.
- Projection output은 현재 `MetadataStore`, optional graph service output, status
  service state에서 rebuild됩니다.
- metadata/vector/graph store를 삭제해도 derived state만 사라집니다. `vg index`를
  다시 실행하면 evidence basis가 재생성됩니다.
- External memory system은 이후 이 projection을 export할 수 있지만 Phase 6B fact의
  source가 될 수 없습니다.

## 19. Tests

Required tests:

- `MetadataStore.list_documents(...)`가 non-tombstoned documents를 반환하고,
  `DocumentSnapshot` fields를 보존하고, `QueryScope`로 filter하고, deterministic
  order를 지키고, missing database를 initialize하지 않음
- `MemorySourceReader`가 chunks에서 bounded evidence를 읽고, chunk order를 보존하고,
  unresolved evidence에 warning을 만들고, Vault file을 직접 읽지 않음
- `MemoryRequestContext`가 document listing 전에 metadata status를 확인하고,
  actual Vault scope마다 document를 한 번 listing하고, 하나의 generated timestamp를
  사용함
- metadata-selected document 내부 heading classification이 첫 세 chunk 뒤에 있는
  heading도 inspect하고, matched heading chunks를 bounded evidence set 안에 우선 포함
- memory DTO가 blank IDs, mutable sequences, missing evidence, invalid `rank`
  values, affected Vault IDs 없는 warnings를 reject
- path, frontmatter, headings, status values, ambiguous matches, no-match behavior
  classification
- open-question classification이 resolved/closed/done issues를 제외하고, missing
  status는 heading candidate로만 사용될 때 warning을 붙임
- large scopes가 metadata-first candidate narrowing을 사용하고,
  `candidate_read_limit`을 enforce하고, `candidate_scan_truncated` warning을 emit
- project memory가 current state, decisions, open questions, constraints,
  priorities, stale areas를 deterministic하게 그룹화
- decision memory가 durable decision document를 우선하고, graph service가 inject된
  경우에만 graph-derived warning/enrichment를 추가
- open questions가 issue docs, TODO headings, blockers, follow-ups, revisit triggers
  포함
- 같은 path/title/status를 가진 multi-Vault documents가 충돌하지 않음
- MCP tools가 structured memory projections, resource links, warnings, text mirrors를
  serialize
- `get_open_questions`가 issue-backed open question에 existing issue resource link를
  반환하고 memory-resource URI를 만들지 않음
- memory resource links가 `document_resource_kinds`를 사용하여 frontmatter-backed
  decision/issue document에는 valid existing resource link를 제공하고,
  heading-only candidate에는 broken decision/issue link를 만들지 않음
- MCP tool validation이 non-integer 또는 out-of-range limit을 existing
  `invalid_tool_arguments` error로 reject
- `context/current`가 single-Vault project memory projection을 반환
- read-only boundary tests가 Vault file mutation과 read-only store initialization이
  없음을 확인
- import 또는 boundary tests가 Phase 6B에 writable `MemoryStore`, external memory
  dependency, raw episode log, profile memory table이 추가되지 않았음을 확인
- prompt tests가 Phase 6B prompt line이 registered tools만 언급함을 확인

Verification commands:

```bash
uv run --python 3.12 pytest tests/test_memory_models.py tests/test_memory_source_reader.py -q
uv run --python 3.12 pytest tests/test_project_memory_service.py tests/test_decision_memory_service.py tests/test_issue_memory_service.py -q
uv run --python 3.12 pytest tests/test_mcp_memory_tools.py tests/test_mcp_current_context_resource.py tests/test_mcp_resources.py -q
VG_RUN_MCP_STDIO_SMOKE=1 uv run --python 3.12 pytest tests/test_mcp_stdio_smoke.py -q
uv run --python 3.12 ruff check src tests
uv run --python 3.12 mypy src tests
```

## 20. Implementation Handoff

Phase 6B는 다음 순서로 구현합니다.

1. `MemoryProjectionError`, memory DTO, focused model tests 추가
2. `MetadataStore.list_documents(...)` protocol/local SQLite implementation과
   contract tests 추가
3. `MemorySourceReader`, `MemoryRequestContext`, evidence/context tests 추가
4. `DecisionMemoryService`, `IssueMemoryService` 추가
5. decision/issue projection을 compose하는 `ProjectMemoryService` 추가
6. MCP memory serialization과 service-factory open methods 추가
7. `summarize_project_memory`, `get_open_questions`, prompt updates, stdio
   tool-list tests 추가
8. `vault://{vault_id}/context/current` upgrade
9. read-only/import-boundary tests와 full verification 실행

## 21. Risks And Mitigations

- **Risk:** deterministic memory가 LLM summary보다 덜 자연스럽다.
  **Mitigation:** structured groups와 evidence를 먼저 보존합니다. answer synthesis는
  범위 밖입니다.
- **Risk:** broad document classification이 noisy memory를 만든다.
  **Mitigation:** classifier를 conservative하게 유지하고, Vault별로 result를 bound하고,
  deterministic evidence를 rank하고, ambiguous item에 warning을 붙입니다.
- **Risk:** document listing이 `MetadataStore`를 넓힌다.
  **Mitigation:** read-only, scope-filtered, contract-tested method로 제한하고
  local/future scale-up backend가 같은 contract를 따르게 합니다.
- **Risk:** "memory" naming이 generic writable layer를 유도한다.
  **Mitigation:** 구체적인 read service만 노출하고 writable memory-store 또는 external
  memory dependency를 거부하는 boundary test를 추가합니다.
- **Risk:** all-Vault memory output이 source ownership을 숨긴다.
  **Mitigation:** Vault ID별로 grouping하고 item IDs, warnings, evidence refs, store
  revisions, resource links에 Vault ID를 요구합니다.

## 22. Open Decisions

Phase 6B에는 없음. LLM-written project summaries, durable memory history,
external memory adapters는 범위 밖입니다.
