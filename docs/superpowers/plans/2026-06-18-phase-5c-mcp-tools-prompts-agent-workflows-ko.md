# Phase 5C MCP Tools, Prompts, And Agent Workflows 구현 계획

> **에이전트 작업자 필수 지침:** 이 계획을 구현할 때는
> `superpowers:subagent-driven-development`를 권장하며, 필요하면
> `superpowers:executing-plans`를 사용한다. 모든 단계는 체크박스
> (`- [ ]`) 형식으로 추적한다.

**목표:** 기존 Vault Graph 검색, context-pack, graph retrieval, decision
trace, status 서비스를 읽기 전용 MCP tools로 노출하고, 에이전트가
bounded evidence-first workflow를 따르도록 prompt templates를 등록한다.

**아키텍처:** `vault_graph.mcp`는 기존 application services 위의 얇은
adapter로 유지한다. MCP는 argument DTO, validation, tool envelope,
prompt template, resource link만 소유한다. 검색, graph traversal,
context-pack assembly, status check는 현재 service module에 남긴다.

**기술 스택:** Python 3.12, official MCP Python SDK `FastMCP.tool`
(`structured_output=True`), `FastMCP.prompt`, frozen dataclasses, 기존
`McpServiceFactory`, 기존 Phase 5B resource cache와 URI helpers, pytest,
ruff, mypy.

---

## Source Documents

구현 전 다음 문서를 읽는다.

- `AGENTS.md`
- `docs/SPEC.md`
- `docs/FEATURES.md`
- `docs/DESIGN.md`
- `docs/CONVENTIONS.md`
- `docs/superpowers/specs/phase-5/README.md`
- `docs/superpowers/specs/phase-5/2026-06-15-phase-5-mcp-server-overview-design.md`
- `docs/superpowers/specs/phase-5/2026-06-15-phase-5a-mcp-server-foundation-stdio-design.md`
- `docs/superpowers/specs/phase-5/2026-06-15-phase-5b-mcp-resources-context-pack-resources-design.md`
- `docs/superpowers/specs/phase-5/2026-06-15-phase-5c-mcp-tools-prompts-agent-workflows-design.md`
- `docs/superpowers/plans/2026-06-15-phase-5a-mcp-server-foundation-stdio.md`
- `docs/superpowers/plans/2026-06-17-phase-5b-mcp-resources-context-pack-resources.md`

현재 repo 사실:

- `src/vault_graph/mcp/mcp_server.py`는 이미 하나의 `FastMCP` server를
  만들고 `RegisteredMcpServer`를 반환한다.
- `RegisteredMcpServer`는 현재 `context_pack_cache`와
  `resource_registry`를 노출한다. Phase 5C에서는 `tool_registry`와
  `prompt_registry`를 추가한다.
- `src/vault_graph/mcp/mcp_service_factory.py`의 `open_read_only()`는
  기본적으로 non-graph이고, graph service는 lazy method로 분리되어 있다.
- `McpServiceFactory.open_read_only()`는 `rustworkx`를 import하거나,
  missing store/model cache를 만들거나, indexing을 실행하거나,
  registered Vault root에 쓰면 안 된다.
- `src/vault_graph/mcp/mcp_scope.py`는 이미 `McpScopeInput`과
  `scope_from_mcp_input(...)`을 소유한다. 모든 scoped tool은 이를 재사용한다.
- `src/vault_graph/mcp/mcp_uri.py`는 `encode_resource_segment(...)`를 통해
  percent-encoded `vault://` resource segment를 소유한다.
- `src/vault_graph/mcp/context_pack_resource_cache.py`는 bounded in-process
  generated context-pack resource cache를 소유한다.
- `tests/test_mcp_stdio_smoke.py`는 현재 tools/prompts가 비어 있음을
  기대한다. Phase 5C에서는 정확한 tool/prompt 목록을 기대하도록 바꾼다.
- CLI JSON helper는 참고만 한다. MCP serialization은
  `vault_graph.cli`를 import하면 안 된다.

## Scope

Phase 5C에서 구현할 사항:

- MCP tool response serialization과 resource-link generation.
- graph-enabled retrieval/context-pack builder를 여는 lazy factory methods.
- 다음 5개 tool의 MCP input DTO와 validation.
  - `search_vault`
  - `build_context_pack`
  - `find_related`
  - `get_decision_trace`
  - `check_index_status`
- `structured_output=True`를 사용하는 FastMCP tool registration.
- 다음 7개 prompt templates 등록.
  - `generate_codex_brief`
  - `prepare_implementation_context`
  - `review_architecture_decision`
  - `summarize_feature_history`
  - `analyze_project_risk`
  - `prepare_wiki_update_context`
  - `trace_decision_history`
- `build_context_pack`에서 Phase 5B `ContextPackResourceCache`를 공유 사용.
- unit tests, read-only boundary tests, import-laziness tests, official MCP
  stdio smoke assertions.

## Non-Goals

구현하지 않는다.

- `ask_vault`
- LLM clients 또는 answer synthesis
- project-memory, issue-memory, timeline, recent-change, open-question services
- Vault source capture, validation, wiki publication, file edit 자동화
- MCP tools에서 indexing, repair, derived state mutation
- durable context-pack persistence
- resource subscriptions
- Streamable HTTP transport, authentication, remote hosting
- Phase 5C tool 이름에 대한 alias

## Directory And File Structure

생성할 파일:

- `src/vault_graph/mcp/mcp_tool_serialization.py`: service DTO를 MCP
  payload, warning, text mirror, Phase 5B resource link로 변환한다.
- `src/vault_graph/mcp/mcp_tools.py`: tool input DTO, validation,
  `McpToolBody`, `McpToolRegistry`, FastMCP tool registration을 소유한다.
- `src/vault_graph/mcp/mcp_prompts.py`: prompt names, prompt templates,
  `McpPromptRegistry`, FastMCP prompt registration을 소유한다.
- `tests/test_mcp_tool_serialization.py`
- `tests/test_mcp_tools.py`
- `tests/test_mcp_prompts.py`
- `tests/test_mcp_tool_read_only_boundary.py`

수정할 파일:

- `src/vault_graph/mcp/__init__.py`: SDK, Chroma, fastembed, graph eager
  import 없이 새 MCP public DTO와 registry type을 lazy export한다.
- `src/vault_graph/mcp/mcp_server.py`: `create_mcp_server(...)`에서 tools와
  prompts를 등록하고 `RegisteredMcpServer`에 registry를 추가한다.
- `src/vault_graph/mcp/mcp_service_factory.py`: `open_retrieval_service`와
  `open_context_pack_builder`를 추가한다.
- `tests/test_mcp_service_factory.py`: 새 lazy factory method를 검증한다.
- `tests/test_mcp_stdio_smoke.py`: official MCP client가 5개 tools, Phase
  5B resource templates, 7개 prompts를 보는지 검증한다.
- `tests/test_mcp_import_boundaries.py`: MCP import boundary가 여전히
  lightweight인지 검증한다.

수정하지 않을 것:

- registered Vault roots 또는 Vault files
- retrieval ranking logic
- graph traversal/projection algorithms
- context-pack JSON schema
- Phase 5B resource URI templates
- `docs/DECISIONS.md`
- `docs/PATCH_LOG.md` 단, review에서 실제 mismatch/defect/risk 때문에
  plan/spec을 고쳤을 때만 짧게 기록한다.

## Component And Interface Spec

### `mcp_tool_serialization.py`

역할:

- MCP tool payload JSON serialization을 소유한다.
- `vault_id`, `document_id`, `chunk_id`, evidence, warnings, revisions,
  backend fields, requested scope, actual scopes를 보존한다.
- `encode_resource_segment(...)`를 사용해 Phase 5B `vault://` resource
  links를 만든다.
- structured payload에서만 compact text mirror를 만든다.
- `vault_graph.cli`와 독립적이어야 한다.

필수 public functions:

```python
def query_scope_to_dict(scope: QueryScope) -> dict[str, object]: ...
def search_response_to_payload(response: SearchResponse) -> dict[str, object]: ...
def context_pack_to_payload(pack: ContextPack) -> dict[str, object]: ...
def related_response_to_payload(response: RelatedResponse) -> dict[str, object]: ...
def decision_trace_response_to_payload(response: DecisionTraceResponse) -> dict[str, object]: ...
def status_report_to_payload(report: StatusReport, *, selected_scope: QueryScope) -> dict[str, object]: ...
def resource_links_for_search(response: SearchResponse) -> tuple[McpResourceLink, ...]: ...
def resource_links_for_context_pack(pack: ContextPack) -> tuple[McpResourceLink, ...]: ...
def resource_links_for_related(response: RelatedResponse) -> tuple[McpResourceLink, ...]: ...
def resource_links_for_decision_trace(response: DecisionTraceResponse) -> tuple[McpResourceLink, ...]: ...
def tool_text_mirror(payload: dict[str, object]) -> str: ...
```

구현 규칙:

- CLI JSON helper의 shape는 참고만 하고 import하지 않는다.
- `context_pack_to_payload(pack)`은 `context_pack_to_dict(pack)`와 같아야 한다.
- `tool_text_mirror(...)`는 `json.dumps(..., allow_nan=False)`를 사용한다.
- deterministic link de-duplication key는 `(rel, uri)`를 사용한다.
- circular import를 피하기 위해 `McpResourceLink`는 `mcp_tools.py`에 두고,
  serialization helper는 `McpToolRegistry` method 내부에서 import한다.

### `mcp_tools.py`

역할:

- Phase 5C tool names를 소유한다.
- JSON-safe FastMCP handler signatures를 소유한다.
- raw MCP arguments를 frozen input DTO로 변환한다.
- graph service를 열기 전에 argument validation을 끝낸다.
- 기존 application service로 dispatch한다.
- service exception은 `map_exception_to_mcp_error(...)`로 변환한다.
- 하나의 canonical MCP tool envelope을 반환한다.

필수 tool names:

```python
McpToolName = Literal[
    "search_vault",
    "build_context_pack",
    "find_related",
    "get_decision_trace",
    "check_index_status",
]
```

필수 input DTO:

```python
@dataclass(frozen=True)
class SearchVaultInput:
    query: str
    scope: McpScopeInput | None = None
    limit: int = 10
    include_graph: bool = False
    include_cross_vault: bool = False

@dataclass(frozen=True)
class BuildContextPackInput:
    goal: str
    scope: McpScopeInput | None = None
    max_tokens: int | None = None
    limit: int = DEFAULT_CONTEXT_RETRIEVAL_LIMIT
    include_graph: bool = False
    include_cross_vault: bool = False

@dataclass(frozen=True)
class FindRelatedInput:
    target: str
    scope: McpScopeInput | None = None
    depth: int = DEFAULT_GRAPH_RELATED_DEPTH
    kinds: tuple[str, ...] = ()
    limit: int = DEFAULT_GRAPH_RESULT_LIMIT
    include_cross_vault: bool = False

@dataclass(frozen=True)
class DecisionTraceInput:
    decision_or_topic: str
    scope: McpScopeInput | None = None
    limit: int = DEFAULT_GRAPH_RESULT_LIMIT
    include_cross_vault: bool = False

@dataclass(frozen=True)
class CheckIndexStatusInput:
    scope: McpScopeInput | None = None
```

핵심 validation:

- required string은 strip 후 비어 있으면 실패한다.
- `limit`은 `1..50` 범위여야 한다.
- `max_tokens`는 주어졌다면 양수여야 한다.
- `depth`는 `1..MAX_GRAPH_PROJECTION_DEPTH` 범위여야 한다.
- `scope.all_vaults`와 `scope.vault_ids`는 동시에 사용할 수 없다.
- `scope.content_scopes`는 configured content scope를 좁힐 수만 있다.
- top-level `include_cross_vault`가 authoritative하다.
- `scope["include_cross_vault"]`가 top-level 값과 다르면
  `invalid_tool_arguments`로 실패한다.
- `search_vault`와 `build_context_pack`에서 `include_cross_vault=True`이면
  `include_graph=True`가 필요하다.
- graph tools에서 `include_cross_vault=True`이면 선택된 Vault가 2개 이상이어야 한다.
- validation error는 graph dependency를 열기 전에 발생해야 한다.

### `mcp_prompts.py`

역할:

- prompt names와 prompt text를 소유한다.
- prompt text는 투명하고 짧고 read-only이며 Phase 5C registered tools만 언급한다.
- 사용자의 task와 충돌하는 hidden instruction을 넣지 않는다.

등록할 prompt names:

```text
generate_codex_brief
prepare_implementation_context
review_architecture_decision
summarize_feature_history
analyze_project_risk
prepare_wiki_update_context
trace_decision_history
```

모든 prompt에 들어가야 할 언어:

```text
Use Vault Graph as read-only working context.
Do not read the whole Vault when a scoped context pack is enough.
Inspect warnings before relying on evidence.
Preserve vault_id, document IDs, chunk IDs, and resource links.
If durable knowledge should change, propose the Vault source capture, validation, release gate, and Git workflow. Do not publish through Vault Graph.
```

prompt text에서 허용되는 tool references:

- `search_vault`
- `build_context_pack`
- `find_related`
- `get_decision_trace`
- `check_index_status`

prompt text에서 금지되는 deferred tool references:

- `ask_vault`
- `summarize_project_memory`
- `get_open_questions`
- `get_recent_changes`
- `explain_result`

### `mcp_service_factory.py`

추가할 factory methods:

```python
def open_retrieval_service(self, *, include_graph: bool = False) -> RetrievalService: ...
def open_context_pack_builder(self, *, include_graph: bool = False) -> ContextPackBuilder: ...
```

구현 방향:

- 기존 `open_read_only()` 구성 로직을 private `_open_retrieval_components()`
  helper로 추출한다.
- `RetrievalService` private fields를 읽지 않는다.
- `_build_retrieval_service(...)` helper가 graph provider 주입 여부만 결정한다.
- `_build_context_pack_builder(...)` helper가 같은 components의 metadata store를
  evidence resolver로 사용한다.
- `include_graph=True`일 때만 `open_graph_search_candidate_provider()`를 호출한다.

### `mcp_server.py`

`McpServer` protocol에 다음을 추가한다.

```python
async def list_tools(self) -> Any: ...
async def list_prompts(self) -> Any: ...
```

`RegisteredMcpServer`에 다음 field를 추가한다.

```python
tool_registry: McpToolRegistry
prompt_registry: McpPromptRegistry
```

`create_mcp_server(...)` registration order:

```text
register_mcp_resources(...)
register_mcp_tools(...)
register_mcp_prompts(...)
```

## State Management And Data Flow

Server startup:

```text
vg serve --mcp --state PATH
  -> create_mcp_server(config)
  -> McpServiceFactory.open_read_only()
  -> ContextPackResourceCache(max_entries=32)
  -> register_mcp_resources(...)
  -> register_mcp_tools(...)
  -> register_mcp_prompts(...)
  -> stdio transport
```

Search:

```text
raw MCP args
  -> SearchVaultInput
  -> scope_from_mcp_input(...)
  -> RetrievalService.search(...)
  -> search_response_to_payload(...)
  -> resource_links_for_search(...)
  -> McpToolBody.to_json_dict()
```

Context pack:

```text
raw MCP args
  -> BuildContextPackInput
  -> scope_from_mcp_input(...)
  -> ContextPackRequest(...)
  -> ContextPackBuilder.build(...)
  -> services.context_pack_renderer.render_json(pack)
  -> ContextPackResourceCache.put(pack, rendered_json=...)
  -> context_pack_to_payload(...)
  -> McpToolBody with vault://context/packs/{pack_id}
```

Graph tools:

```text
raw MCP args
  -> FindRelatedInput or DecisionTraceInput
  -> scope_from_mcp_input(..., allow_graph_cross_vault=True)
  -> service_factory.open_graph_retrieval_service()
  -> GraphRetrievalService.related(...) or decision_trace(...)
  -> MCP payload, warnings, and graph/evidence resource links
```

Status:

```text
raw MCP args
  -> CheckIndexStatusInput
  -> scope_from_mcp_input(...)
  -> service_factory.open_status_service().status(scope=...)
  -> status_report_to_payload(...)
```

## Error Handling And Edge Cases

- 빈 required string은 `invalid_tool_arguments`.
- object가 아닌 `scope`는 `invalid_tool_arguments`.
- unknown scope key는 `invalid_tool_arguments`.
- `all_vaults`와 `vault_ids` 동시 사용은 scope validation error.
- empty `content_scopes`는 catalog validation error.
- content scope widening은 catalog validation error.
- unknown/disabled Vault ID는 기존 catalog error mapping을 따른다.
- `limit < 1` 또는 `limit > 50`은 `invalid_tool_arguments`.
- `max_tokens <= 0`은 `invalid_tool_arguments`.
- depth 범위 오류는 `invalid_tool_arguments`.
- graph 없는 cross-Vault search/context는 `invalid_tool_arguments`.
- graph tool의 cross-Vault 요청에서 Vault가 2개 미만이면 `invalid_tool_arguments`.
- metadata/keyword unavailable은 기존 `SearchError`를 MCP error로 변환한다.
- vector unavailable은 기존 warning-backed keyword degradation을 보존한다.
- graph tool failure는 non-graph result로 조용히 downgrade하지 않는다.
- search/context graph expansion failure는 service가 partial response를 낼 수 있을 때 warning으로 보존한다.
- context-pack budget truncation은 successful response이며 warning을 포함한다.
- unexpected exception은 `internal_error`이고 path redaction은 `mcp_errors.py`를 따른다.

## Implementation Steps

### Task 1: Tool Envelope And Serialization Contract

**Files**

- Create: `src/vault_graph/mcp/mcp_tools.py`
- Create: `src/vault_graph/mcp/mcp_tool_serialization.py`
- Create: `tests/test_mcp_tool_serialization.py`

- [ ] **Step 1: failing serialization tests 작성**
  - `query_scope_to_dict`가 cross-vault state를 보존하는지 테스트한다.
  - `context_pack_to_payload(pack)`이 `context_pack_to_dict(pack)`와 같은지 테스트한다.
  - search resource links가 Phase 5B URI encoding을 사용하는지 테스트한다.
  - `mcp_tool_serialization.py`가 `vault_graph.cli`를 import하지 않는지 테스트한다.

- [ ] **Step 2: serialization tests failure 확인**

```bash
uv run --python 3.12 pytest tests/test_mcp_tool_serialization.py -q
```

Expected: `mcp_tool_serialization.py`가 없어서 실패한다.

- [ ] **Step 3: shared MCP tool DTO 생성**
  - `McpToolName`
  - `McpResourceLink`
  - `McpToolBody`
  - `_warning_to_dict(...)`

- [ ] **Step 4: `mcp_tool_serialization.py` 구현**
  - payload conversion helpers
  - warning conversion helpers
  - resource link helpers
  - `tool_text_mirror(...)`

- [ ] **Step 5: serialization tests 통과 확인**

```bash
uv run --python 3.12 pytest tests/test_mcp_tool_serialization.py -q
```

- [ ] **Step 6: commit**

```bash
git add src/vault_graph/mcp/mcp_tools.py src/vault_graph/mcp/mcp_tool_serialization.py tests/test_mcp_tool_serialization.py
git commit -m "feat(mcp): add tool serialization boundary"
```

### Task 2: Lazy Graph Factory Methods

**Files**

- Modify: `src/vault_graph/mcp/mcp_service_factory.py`
- Modify: `tests/test_mcp_service_factory.py`

- [ ] **Step 1: failing factory tests 작성**
  - `open_retrieval_service(include_graph=False)`가 lightweight인지 검증한다.
  - `open_context_pack_builder(include_graph=True)`가 graph projection을 lazy로 여는지 검증한다.

- [ ] **Step 2: factory tests failure 확인**

```bash
uv run --python 3.12 pytest tests/test_mcp_service_factory.py -q
```

- [ ] **Step 3: `_RetrievalComponents`와 `_open_retrieval_components()` 추가**
  - catalog, metadata store, keyword index, vector store, text embeddings,
    readiness를 하나의 read-only component bundle로 구성한다.

- [ ] **Step 4: public factory methods 구현**
  - `open_retrieval_service(include_graph=False)`
  - `open_context_pack_builder(include_graph=False)`
  - `_build_retrieval_service(...)`
  - `_build_context_pack_builder(...)`

- [ ] **Step 5: factory/import tests 실행**

```bash
uv run --python 3.12 pytest tests/test_mcp_service_factory.py tests/test_mcp_import_boundaries.py -q
```

- [ ] **Step 6: commit**

```bash
git add src/vault_graph/mcp/mcp_service_factory.py tests/test_mcp_service_factory.py tests/test_mcp_import_boundaries.py
git commit -m "feat(mcp): add lazy graph retrieval factories"
```

### Task 3: Tool Registry And Argument Validation

**Files**

- Modify: `src/vault_graph/mcp/mcp_tools.py`
- Create: `tests/test_mcp_tools.py`

- [ ] **Step 1: registry/validation failing tests 작성**
  - 정확히 5개 Phase 5C tools만 등록되는지 검증한다.
  - 모든 tool이 `structured_output=True`인지 검증한다.
  - deferred tool인 `ask_vault`가 등록되지 않는지 검증한다.
  - invalid query/goal/target/topic/limit/max_tokens/scope mismatch가
    `invalid_tool_arguments`로 실패하는지 검증한다.

- [ ] **Step 2: registry tests failure 확인**

```bash
uv run --python 3.12 pytest tests/test_mcp_tools.py -q
```

- [ ] **Step 3: tool DTO module 확장**
  - `McpToolServer`
  - 5개 input DTO
  - `McpToolRegistry`
  - `_invalid_arguments(...)`
  - `_tool_body(...)`
  - `_map_tool_exception(...)`
  - `mcp_scope_input_from_raw(...)`

- [ ] **Step 4: `register_mcp_tools(...)` 구현**
  - FastMCP public decorator만 사용한다.
  - handler signature는 JSON-safe type만 사용한다.
  - raw args를 input DTO로 변환 후 registry method로 dispatch한다.

- [ ] **Step 5: registry/validation tests 통과 확인**

```bash
uv run --python 3.12 pytest tests/test_mcp_tools.py -q
```

- [ ] **Step 6: commit**

```bash
git add src/vault_graph/mcp/mcp_tools.py tests/test_mcp_tools.py
git commit -m "feat(mcp): register service-backed tool boundary"
```

### Task 4: Search, Context Pack, And Status Tool Dispatch

**Files**

- Modify: `src/vault_graph/mcp/mcp_tools.py`
- Modify: `tests/test_mcp_tools.py`

- [ ] **Step 1: non-graph tool dispatch failing tests 작성**
  - `search_vault`가 `include_graph=False`일 때 base retrieval service를 쓰는지 검증한다.
  - `build_context_pack`이 pack JSON을 render하고 shared cache에 넣는지 검증한다.
  - `check_index_status`가 indexing 없이 status service만 호출하는지 검증한다.

- [ ] **Step 2: dispatch tests failure 확인**

```bash
uv run --python 3.12 pytest tests/test_mcp_tools.py -q
```

- [ ] **Step 3: search dispatch 구현**
  - `include_graph=False`: `services.retrieval_service`
  - `include_graph=True`: `service_factory.open_retrieval_service(include_graph=True)`

- [ ] **Step 4: context-pack dispatch 구현**
  - `include_graph=False`: `services.context_pack_builder`
  - `include_graph=True`: `service_factory.open_context_pack_builder(include_graph=True)`
  - `services.context_pack_renderer.render_json(pack)`
  - `context_pack_cache.put(pack, rendered_json=...)`
  - `vault://context/packs/{pack_id}` link 반환

- [ ] **Step 5: status dispatch 구현**
  - `service_factory.open_status_service().status(scope=selected_scope)`
  - `status_report_to_payload(...)`

- [ ] **Step 6: non-graph tests 실행**

```bash
uv run --python 3.12 pytest tests/test_mcp_tools.py tests/test_mcp_tool_serialization.py -q
```

- [ ] **Step 7: commit**

```bash
git add src/vault_graph/mcp/mcp_tools.py tests/test_mcp_tools.py
git commit -m "feat(mcp): dispatch search context and status tools"
```

### Task 5: Graph Tool Dispatch And Cross-Vault Validation

**Files**

- Modify: `src/vault_graph/mcp/mcp_tools.py`
- Modify: `tests/test_mcp_tools.py`

- [ ] **Step 1: graph dispatch failing tests 작성**
  - `find_related`가 validation 이후 graph service를 lazy로 여는지 검증한다.
  - `get_decision_trace`가 validation 이후 graph service를 lazy로 여는지 검증한다.
  - invalid graph tool arguments는 graph service를 열기 전에 실패하는지 검증한다.

- [ ] **Step 2: graph tests failure 확인**

```bash
uv run --python 3.12 pytest tests/test_mcp_tools.py -q
```

- [ ] **Step 3: `find_related` dispatch 구현**
  - `scope_from_mcp_input(..., allow_graph_cross_vault=True)`
  - `GraphRetrievalService.related(...)`
  - graph/evidence resource links 보존

- [ ] **Step 4: `get_decision_trace` dispatch 구현**
  - `scope_from_mcp_input(..., allow_graph_cross_vault=True)`
  - `GraphRetrievalService.decision_trace(...)`
  - decision/entity resource links 보존

- [ ] **Step 5: graph dispatch tests 통과 확인**

```bash
uv run --python 3.12 pytest tests/test_mcp_tools.py -q
```

- [ ] **Step 6: commit**

```bash
git add src/vault_graph/mcp/mcp_tools.py tests/test_mcp_tools.py
git commit -m "feat(mcp): dispatch graph tools"
```

### Task 6: Prompt Registry

**Files**

- Create: `src/vault_graph/mcp/mcp_prompts.py`
- Create: `tests/test_mcp_prompts.py`

- [ ] **Step 1: prompt failing tests 작성**
  - 정확히 7개 Phase 5C prompts만 등록되는지 검증한다.
  - prompt text가 registered tools만 언급하는지 검증한다.
  - read-only, evidence-first, warning, durable follow-up language가 있는지 검증한다.
  - unknown prompt name이 `invalid_prompt`로 실패하는지 검증한다.

- [ ] **Step 2: prompt tests failure 확인**

```bash
uv run --python 3.12 pytest tests/test_mcp_prompts.py -q
```

- [ ] **Step 3: prompt registry 구현**
  - `PHASE_5C_PROMPT_NAMES`
  - `McpPromptRegistry.render(...)`
  - prompt render helper 7개
  - `register_mcp_prompts(server)`

- [ ] **Step 4: prompt tests 통과 확인**

```bash
uv run --python 3.12 pytest tests/test_mcp_prompts.py -q
```

- [ ] **Step 5: commit**

```bash
git add src/vault_graph/mcp/mcp_prompts.py tests/test_mcp_prompts.py
git commit -m "feat(mcp): add agent workflow prompts"
```

### Task 7: Server Wiring, Lazy Exports, Smoke, And Read-Only Boundary

**Files**

- Modify: `src/vault_graph/mcp/__init__.py`
- Modify: `src/vault_graph/mcp/mcp_server.py`
- Modify: `tests/test_mcp_server.py`
- Modify: `tests/test_mcp_stdio_smoke.py`
- Create: `tests/test_mcp_tool_read_only_boundary.py`

- [ ] **Step 1: server wiring failing tests 작성**
  - `create_mcp_server(...)`가 resources, tools, prompts를 모두 등록하는지 검증한다.
  - official MCP client smoke test가 tools/prompts/resource templates를 보는지 검증한다.

- [ ] **Step 2: read-only boundary tests 작성**
  - invalid tool arguments가 missing state directory를 만들지 않는지 검증한다.
  - tool call이 Vault file bytes를 바꾸지 않는지 검증한다.

- [ ] **Step 3: wiring/read-only tests failure 확인**

```bash
uv run --python 3.12 pytest tests/test_mcp_server.py tests/test_mcp_tool_read_only_boundary.py tests/test_mcp_stdio_smoke.py -q
```

- [ ] **Step 4: `create_mcp_server(...)`에 tools/prompts 연결**
  - resources -> tools -> prompts 순서로 등록한다.

- [ ] **Step 5: lazy exports 추가**
  - `src/vault_graph/mcp/__init__.py`에 새 symbols를 lazy export한다.
  - `import vault_graph.mcp`가 SDK, graph, Chroma, fastembed를 eager import하지 않는지 확인한다.

- [ ] **Step 6: focused MCP tests 실행**

```bash
uv run --python 3.12 pytest tests/test_mcp_server.py tests/test_mcp_tools.py tests/test_mcp_prompts.py tests/test_mcp_tool_read_only_boundary.py tests/test_mcp_import_boundaries.py -q
```

- [ ] **Step 7: commit**

```bash
git add src/vault_graph/mcp/__init__.py src/vault_graph/mcp/mcp_server.py tests/test_mcp_server.py tests/test_mcp_stdio_smoke.py tests/test_mcp_tool_read_only_boundary.py
git commit -m "feat(mcp): wire tools and prompts into server"
```

### Task 8: Final Integration Verification

**Files**

- Phase 5C source와 tests 전체 review.

- [ ] **Step 1: required focused tests 실행**

```bash
uv run --python 3.12 pytest tests/test_mcp_tools.py tests/test_mcp_tool_serialization.py tests/test_mcp_prompts.py tests/test_mcp_tool_read_only_boundary.py tests/test_mcp_stdio_smoke.py -q
```

- [ ] **Step 2: MCP/context-pack regression tests 실행**

```bash
uv run --python 3.12 pytest tests/test_mcp_server.py tests/test_mcp_service_factory.py tests/test_mcp_resources.py tests/test_context_pack_resource_cache.py tests/test_search_include_graph.py tests/test_multi_vault_search.py tests/test_multi_vault_graph_retrieval.py -q
```

- [ ] **Step 3: full quality gates 실행**

```bash
uv run --python 3.12 pytest -q
uv run --python 3.12 ruff check src tests
uv run --python 3.12 mypy src tests
git diff --check
```

- [ ] **Step 4: verification adjustments가 있으면 final commit**

```bash
git add src/vault_graph/mcp tests
git commit -m "test(mcp): verify phase 5c integration"
```

변경이 없다면 이 commit은 생략한다.

## Validation Review

Security/read-only:

- tools는 JSON-safe scalar와 scope object만 받는다.
- 모든 read는 `QueryScope`, catalog validation, application services,
  metadata-backed evidence resolution을 통한다.
- Phase 5C tool은 `VaultLoader`를 호출하지 않고, Vault files를 쓰지 않으며,
  indexing이나 durable context-pack persistence를 하지 않는다.

Performance/scalability:

- startup, resource listing, prompt listing, non-graph search/context/status는
  `rustworkx`를 피한다.
- graph dependency는 graph tool 또는 `include_graph=True`에서만 열린다.
- tool result limit은 `MAX_MCP_TOOL_LIMIT = 50`으로 제한한다.
- resource links는 반환된 evidence에서만 만든다.

Testability:

- serialization, factory laziness, tool validation, tool dispatch, prompts,
  server wiring, read-only boundaries를 독립적으로 테스트한다.
- live MCP client는 opt-in stdio smoke에만 사용한다.
- 전체 gate는 `pytest`, `ruff`, `mypy`, `git diff --check`이다.

Maintainability/deep module:

- MCP는 adapter-specific DTO, envelope, prompt text, resource link만 소유한다.
- retrieval, graph traversal, context-pack assembly, status는 application/domain
  service에 남는다.
- `mcp_tool_serialization.py`는 CLI rendering helper 복사를 방지한다.
- `mcp_service_factory.py`가 runtime construction을 소유하며, tools는 store
  backend를 직접 import하지 않는다.

Agent ergonomics:

- tool names는 직접적이고 예측 가능하다.
- prompt templates는 bounded context pack과 warning inspection을 유도한다.
- MCP surface는 Phase 5C service-backed tools만 노출한다.

## Open Decisions

None.

이 계획은 기존 승인된 결정들을 따른다.

- Vault는 source of truth이다.
- Vault Graph는 read-only, rebuildable, evidence-first working context이다.
- MCP는 application services 위의 adapter이다.
- Phase 5는 service-backed behavior만 등록한다.
- generated context packs는 durable pack store가 별도 설계되기 전까지
  in-process MCP resource cache에만 남는다.
