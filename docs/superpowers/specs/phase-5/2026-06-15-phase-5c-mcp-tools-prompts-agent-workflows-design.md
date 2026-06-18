# Phase 5C MCP Tools, Prompts, And Agent Workflows SPEC

Status: Implementation-ready design for planning

Date: 2026-06-15

Last updated: 2026-06-18

Scope: Phase 5C

## 1. Purpose

Phase 5C exposes existing Vault Graph application services as MCP tools and
prompt templates. The goal is to let agents search, build bounded context
packs, inspect graph evidence, trace decisions, and check index status without
scanning an entire Vault and without inventing answer synthesis.

MCP remains an adapter. Tools and prompts must not become a second retrieval
engine, graph engine, context-pack builder, memory service, or Vault publishing
workflow. All output is working context until it is intentionally published
through Vault's normal source capture, validation, release gate, and Git
history workflow.

## 2. Post-5A And 5B Recheck

The original Phase 5C draft still points in the correct product direction, but
the completed Phase 5A and Phase 5B work requires a more precise design:

- Phase 5A created the stdio FastMCP boundary, `RegisteredMcpServer`,
  `McpServiceFactory`, `McpScopeInput`, and MCP error mapping. Phase 5C must
  register tools and prompts on the same server wrapper instead of creating a
  second MCP runtime.
- Phase 5B created resource templates, `McpResourceRegistry`,
  `ContextPackResourceCache`, `mcp_uri.py`, metadata readers, graph resource
  readers, and current-context availability. Phase 5C must reuse the same cache
  and URI format when returning resource links.
- `McpServiceFactory.open_read_only()` currently exposes non-graph retrieval
  and a non-graph context-pack builder. Phase 5C tools that accept
  `include_graph=True` need an explicit lazy factory path that constructs a
  graph-enabled retrieval service or context-pack builder.
- The current MCP smoke test intentionally expects no tools and no prompts.
  Phase 5C must update that expectation to the exact service-backed tool and
  prompt lists.
- FastMCP's public registration surface is enough for this slice:
  `FastMCP.tool(..., structured_output=True)` and `FastMCP.prompt(...)`. The
  implementation must not use SDK-private attributes.

No top-level product decision changes are required. The correction is a design
detail: Phase 5C must be explicit about service reuse, graph laziness, output
serialization, and prompt registration.

## 3. Success Criteria

Phase 5C is complete when:

- `vg serve --mcp` lists only the five service-backed MCP tools:
  `search_vault`, `build_context_pack`, `find_related`,
  `get_decision_trace`, and `check_index_status`.
- deferred roadmap tools such as `ask_vault`, memory summaries, open-question
  tools, recent-change tools, and result explanation are not listed.
- `vg serve --mcp` lists the seven prompt templates defined in this document.
- each tool delegates to an existing application service or context builder and
  does not query SQLite, Chroma, rustworkx, or Vault files directly when a
  service boundary exists.
- `build_context_pack` stores the rendered canonical JSON in the existing
  `RegisteredMcpServer.context_pack_cache` and returns
  `vault://context/packs/{pack_id}`.
- `search_vault`, `find_related`, `get_decision_trace`, and
  `build_context_pack` return Phase 5B resource links where useful.
- `include_graph=True` opens graph dependencies lazily; normal search, context,
  status, resource listing, and prompt listing do not import rustworkx.
- invalid arguments, unknown Vault IDs, invalid scope widening, and invalid
  cross-Vault combinations fail before graph dependencies are opened.
- tool calls do not create metadata, vector, graph, cache, model, or Vault
  files.
- all responses preserve Vault IDs, evidence refs, warnings, store revisions,
  backend use, and scope data in structured JSON.
- text mirrors contain no facts or warnings absent from structured output.
- prompts mention only currently registered Phase 5C tools and instruct agents
  to treat Vault Graph output as read-only working context.

## 4. In Scope

- FastMCP tool registration on the Phase 5A server.
- FastMCP prompt registration on the same server.
- MCP-owned tool input parsing and validation for JSON-safe arguments.
- `McpScopeInput` reuse for all scoped tools.
- service-backed tools for search, context-pack building, related entities,
  decision traces, and index status.
- graph-enabled search and context-pack construction through lazy service
  factory methods.
- canonical MCP tool response envelopes with structured payloads, warnings,
  resource links, and text mirrors.
- resource-link helpers that use Phase 5B `vault://` URI encoding.
- tests for schemas, registration, read-only safety, graph laziness,
  multi-Vault identity, prompt wording, and stdio smoke behavior.

## 5. Out Of Scope

- `ask_vault` answer generation
- LLM clients, hosted model calls, or answer synthesis
- Phase 6 project-memory, timeline, open-question, and recent-change
  projections
- autonomous wiki publication or Vault file editing
- indexing, repairing, or mutating derived state from MCP tools
- resource subscriptions or notifications
- durable context-pack persistence
- streaming partial tool output
- Streamable HTTP transport, authentication, or remote hosting

## 6. Files To Add Or Modify

Add:

```text
src/vault_graph/mcp/mcp_tools.py
src/vault_graph/mcp/mcp_tool_serialization.py
src/vault_graph/mcp/mcp_prompts.py
```

Modify:

```text
src/vault_graph/mcp/__init__.py
src/vault_graph/mcp/mcp_server.py
src/vault_graph/mcp/mcp_service_factory.py
tests/test_mcp_stdio_smoke.py
```

Add tests:

```text
tests/test_mcp_tools.py
tests/test_mcp_tool_serialization.py
tests/test_mcp_prompts.py
tests/test_mcp_tool_read_only_boundary.py
```

Use existing tests as regression coverage:

```text
tests/test_mcp_import_boundaries.py
tests/test_mcp_service_factory.py
tests/test_mcp_resources.py
tests/test_context_pack_resource_cache.py
tests/test_search_include_graph.py
tests/test_multi_vault_search.py
tests/test_multi_vault_graph_retrieval.py
```

## 7. Existing Service Dependency Contract

Phase 5C must reuse these current services and DTOs:

```text
McpServiceFactory.open_read_only()
McpServiceFactory.open_status_service()
McpServiceFactory.open_graph_retrieval_service()
McpServiceFactory.open_graph_resource_service()
McpServiceFactory.open_graph_search_candidate_provider()

RetrievalService.search(...)
SearchContextPackBuilder.build(...)
ContextPackResourceCache.put(...)
ContextPackResourceCache.get(...)
GraphRetrievalService.related(...)
GraphRetrievalService.decision_trace(...)
IndexService.status(...)
```

Phase 5C adds two factory methods because the current `McpServices` object is
intentionally non-graph by default:

```python
class McpServiceFactory:
    def open_retrieval_service(self, *, include_graph: bool = False) -> RetrievalService: ...

    def open_context_pack_builder(self, *, include_graph: bool = False) -> ContextPackBuilder: ...
```

Factory rules:

- `open_read_only()` remains the cheap base service bundle used at startup.
- `open_retrieval_service(include_graph=False)` returns the same behavior as
  the base retrieval service without opening graph dependencies.
- `open_retrieval_service(include_graph=True)` constructs a retrieval service
  with `GraphSearchCandidateProvider` from
  `open_graph_search_candidate_provider()`.
- `open_context_pack_builder(include_graph=True)` constructs a
  `SearchContextPackBuilder` over a graph-enabled retrieval service.
- graph-enabled methods remain lazy and may import rustworkx only after a tool
  explicitly requests graph behavior.
- no factory method initializes missing stores, creates state directories, runs
  indexing, or writes model caches.

Tool routing uses the base `McpServices` object for the common non-graph path
and calls the factory only for status or explicit graph behavior.

## 8. Tool Registration Boundary

`src/vault_graph/mcp/mcp_tools.py` owns tool registration and dispatch. It is
the only MCP module that should know FastMCP tool names.

```python
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Literal, Protocol

McpToolName = Literal[
    "search_vault",
    "build_context_pack",
    "find_related",
    "get_decision_trace",
    "check_index_status",
]

class McpToolServer(Protocol):
    def tool(
        self,
        name: str | None = None,
        title: str | None = None,
        description: str | None = None,
        annotations: object | None = None,
        icons: list[object] | None = None,
        meta: dict[str, Any] | None = None,
        structured_output: bool | None = None,
    ) -> Callable[[Callable[..., object]], Callable[..., object]]: ...

@dataclass(frozen=True)
class McpResourceLink:
    rel: str
    uri: str
    title: str | None = None
    vault_id: str | None = None
    document_id: str | None = None
    chunk_id: str | None = None

@dataclass(frozen=True)
class McpToolBody:
    tool_name: McpToolName
    payload: dict[str, object]
    resource_links: tuple[McpResourceLink, ...]
    warnings: tuple[McpErrorPayload, ...]
    text: str

    def to_json_dict(self) -> dict[str, object]: ...

class McpToolRegistry:
    def __init__(
        self,
        *,
        services: McpServices,
        service_factory: McpServiceFactory,
        context_pack_cache: ContextPackResourceCache,
    ) -> None: ...

    def search_vault(self, request: SearchVaultInput) -> McpToolBody: ...
    def build_context_pack(self, request: BuildContextPackInput) -> McpToolBody: ...
    def find_related(self, request: FindRelatedInput) -> McpToolBody: ...
    def get_decision_trace(self, request: DecisionTraceInput) -> McpToolBody: ...
    def check_index_status(self, request: CheckIndexStatusInput) -> McpToolBody: ...

def register_mcp_tools(
    server: McpToolServer,
    *,
    services: McpServices,
    service_factory: McpServiceFactory,
    context_pack_cache: ContextPackResourceCache,
) -> McpToolRegistry: ...
```

Registration rules:

- register only through the public `FastMCP.tool(...)` decorator.
- set `structured_output=True` for every tool.
- tool handler signatures use JSON-safe arguments (`str`, `int`, `bool`,
  `dict[str, object] | None`, and `list[str] | None`) so generated MCP schemas
  stay predictable.
- handlers convert raw arguments into typed input dataclasses before dispatch.
- handlers return `McpToolBody.to_json_dict()`.
- do not use FastMCP private attributes to inspect, patch, or emit tool
  results.
- do not import CLI helper functions from `vault_graph.cli.main`.

`mcp_server.py` changes:

```python
@dataclass(frozen=True)
class RegisteredMcpServer:
    server: McpServer
    services: McpServices
    service_factory: McpServiceFactory
    server_version: str
    context_pack_cache: ContextPackResourceCache
    resource_registry: McpResourceRegistry
    tool_registry: McpToolRegistry
    prompt_registry: McpPromptRegistry
```

`create_mcp_server(...)` constructs the resource cache once, registers
resources, registers tools with the same cache, registers prompts, and returns
the expanded wrapper.

## 9. Tool Input DTOs

All tools share `McpScopeInput` from Phase 5A. Raw MCP JSON scope objects are
converted to `McpScopeInput` before `scope_from_mcp_input(...)` is called.

```python
MAX_MCP_TOOL_LIMIT = 50

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

Validation rules:

- required strings are stripped and must remain non-empty.
- `limit` must be `1 <= limit <= MAX_MCP_TOOL_LIMIT`.
- context `max_tokens`, when provided, must be positive and use Phase 4 context
  budget semantics.
- `FindRelatedInput.depth` must be between `1` and
  `MAX_GRAPH_PROJECTION_DEPTH`.
- `kinds` maps to graph `relationship_types`; empty means no relationship-type
  filter.
- `scope.all_vaults` and `scope.vault_ids` are mutually exclusive.
- `scope.content_scopes` may narrow configured content scopes, never widen
  them.
- `include_cross_vault=True` requires explicit graph behavior and a multi-Vault
  requested scope.
- `SearchVaultInput.include_cross_vault=True` requires
  `include_graph=True`.
- `BuildContextPackInput.include_cross_vault=True` requires
  `include_graph=True`.
- `FindRelatedInput` and `DecisionTraceInput` are graph tools, so they allow
  `include_cross_vault=True` only when the requested scope contains more than
  one Vault.
- validation errors map to `invalid_tool_arguments` or existing catalog error
  codes before graph services are opened.

## 10. Tool Response Contract

Every tool returns one canonical JSON envelope:

```json
{
  "tool_name": "search_vault",
  "payload": {},
  "resource_links": [],
  "warnings": [],
  "text": "compact mirror generated from the same payload"
}
```

Rules:

- `payload` is the service DTO rendered to JSON-compatible values.
- `resource_links` are follow-up Phase 5B URIs, never direct filesystem paths.
- `warnings` is a normalized top-level copy of relevant warnings for agent
  ergonomics; the original warning data also remains in `payload`.
- `text` is a compact JSON or short Markdown mirror generated from the same
  structured data.
- the text mirror must not add facts, omit warnings, or hide degraded state.
- local absolute paths are omitted or redacted unless they are the explicit
  user-provided `--state` path already allowed by `mcp_errors.py`.
- `isError` is controlled by the MCP SDK error path. Warning-backed degraded
  results are successful tool responses with warnings.

## 11. Tool Serialization Boundary

`src/vault_graph/mcp/mcp_tool_serialization.py` owns JSON-compatible rendering
for service DTOs and resource links. MCP tools must not import CLI JSON helper
functions.

Required functions:

```python
def query_scope_to_dict(scope: QueryScope) -> dict[str, object]: ...

def search_response_to_payload(response: SearchResponse) -> dict[str, object]: ...

def context_pack_to_payload(pack: ContextPack) -> dict[str, object]: ...

def related_response_to_payload(response: RelatedResponse) -> dict[str, object]: ...

def decision_trace_response_to_payload(
    response: DecisionTraceResponse,
) -> dict[str, object]: ...

def status_report_to_payload(
    report: StatusReport,
    *,
    selected_scope: QueryScope,
) -> dict[str, object]: ...

def resource_links_for_search(response: SearchResponse) -> tuple[McpResourceLink, ...]: ...

def resource_links_for_context_pack(pack: ContextPack) -> tuple[McpResourceLink, ...]: ...

def resource_links_for_related(response: RelatedResponse) -> tuple[McpResourceLink, ...]: ...

def resource_links_for_decision_trace(
    response: DecisionTraceResponse,
) -> tuple[McpResourceLink, ...]: ...

def tool_text_mirror(payload: dict[str, object]) -> str: ...
```

Serialization rules:

- preserve `vault_id`, `document_id`, and `chunk_id` for every evidence-bearing
  item.
- preserve `requested_scope`, `actual_scopes`, store revisions, generated time,
  backend use, graph projection version, and graph build IDs where available.
- keep float scores JSON-safe and deterministic.
- convert tuples to lists, dataclasses to objects, and unsupported values to
  explicit serialization errors.
- do not serialize backend-native objects directly.
- keep `context_pack_to_payload(pack)` identical to
  `context_pack_to_dict(pack)` except for MCP envelope additions.

Resource-link rules:

- evidence-bearing documents always get a document resource link:
  `vault://{vault_id}/documents/{encoded_path}`.
- wiki paths under `wiki/` also get a page resource link:
  `vault://{vault_id}/pages/{encoded_path}`.
- source-like paths under `raw/`, `docs/`, or `scratch/reports/` may get a
  source resource link by `document_id`:
  `vault://{vault_id}/sources/{encoded_document_id}`.
- decision-like paths under `wiki/decisions/` may get:
  `vault://{vault_id}/decisions/{encoded_document_id}`.
- issue-like paths under `wiki/issues/` may get:
  `vault://{vault_id}/issues/{encoded_document_id}`.
- graph entities get:
  `vault://{vault_id}/graph/entities/{encoded_entity_id}`.
- context packs get:
  `vault://context/packs/{encoded_pack_id}`.
- all encoding uses `encode_resource_segment(...)` from `mcp_uri.py`.

## 12. Tool Flows

### 12.1 `search_vault`

MCP signature:

```python
def search_vault(
    query: str,
    scope: dict[str, object] | None = None,
    limit: int = 10,
    include_graph: bool = False,
    include_cross_vault: bool = False,
) -> dict[str, object]: ...
```

Flow:

```text
raw args
  -> SearchVaultInput
  -> scope_from_mcp_input(..., allow_graph_cross_vault=include_graph)
  -> choose retrieval service:
       include_graph false: services.retrieval_service
       include_graph true: service_factory.open_retrieval_service(include_graph=True)
  -> RetrievalService.search(output_format="json", ...)
  -> search_response_to_payload(...)
  -> resource_links_for_search(...)
  -> McpToolBody.to_json_dict()
```

Graph behavior:

- default search is keyword/vector only.
- graph candidates are included only when `include_graph=True`.
- cross-Vault graph expansion is included only when both `include_graph=True`
  and `include_cross_vault=True`.
- graph lookup warnings are preserved; vector-to-keyword degradation remains
  the existing retrieval-service behavior.

### 12.2 `build_context_pack`

MCP signature:

```python
def build_context_pack(
    goal: str,
    scope: dict[str, object] | None = None,
    max_tokens: int | None = None,
    limit: int = DEFAULT_CONTEXT_RETRIEVAL_LIMIT,
    include_graph: bool = False,
    include_cross_vault: bool = False,
) -> dict[str, object]: ...
```

Flow:

```text
raw args
  -> BuildContextPackInput
  -> scope_from_mcp_input(..., allow_graph_cross_vault=include_graph)
  -> ContextPackBudget(max_tokens=max_tokens or DEFAULT_CONTEXT_MAX_TOKENS)
  -> ContextPackRequest(...)
  -> choose builder:
       include_graph false: services.context_pack_builder
       include_graph true: service_factory.open_context_pack_builder(include_graph=True)
  -> ContextPackBuilder.build(...)
  -> render_context_pack_json(pack)
  -> context_pack_cache.put(pack, rendered_json=...)
  -> return pack payload plus vault://context/packs/{pack_id}
```

Rules:

- cache insertion is the only write-like operation in this tool, and the cache
  is in-process only.
- the tool must not create durable pack files.
- `resource_links` includes the generated context-pack URI plus evidence and
  graph links derived from pack content.
- the returned payload includes the canonical context-pack JSON fields.

### 12.3 `find_related`

MCP signature:

```python
def find_related(
    target: str,
    scope: dict[str, object] | None = None,
    depth: int = DEFAULT_GRAPH_RELATED_DEPTH,
    kinds: list[str] | None = None,
    limit: int = DEFAULT_GRAPH_RESULT_LIMIT,
    include_cross_vault: bool = False,
) -> dict[str, object]: ...
```

Flow:

```text
raw args
  -> FindRelatedInput
  -> scope_from_mcp_input(..., allow_graph_cross_vault=True)
  -> service_factory.open_graph_retrieval_service()
  -> GraphRetrievalService.related(output_format="json", ...)
  -> related_response_to_payload(...)
  -> resource_links_for_related(...)
  -> McpToolBody.to_json_dict()
```

Rules:

- graph dependencies open only after raw validation and scope validation pass.
- `kinds` maps to graph relationship type filters.
- relationships preserve `stated`, `inferred`, `contested`, and `deprecated`
  status data as provided by graph services.
- target ambiguity and missing graph readiness follow existing
  `GraphRetrievalService` warnings/errors.

### 12.4 `get_decision_trace`

MCP signature:

```python
def get_decision_trace(
    decision_or_topic: str,
    scope: dict[str, object] | None = None,
    limit: int = DEFAULT_GRAPH_RESULT_LIMIT,
    include_cross_vault: bool = False,
) -> dict[str, object]: ...
```

Flow:

```text
raw args
  -> DecisionTraceInput
  -> scope_from_mcp_input(..., allow_graph_cross_vault=True)
  -> service_factory.open_graph_retrieval_service()
  -> GraphRetrievalService.decision_trace(output_format="json", ...)
  -> decision_trace_response_to_payload(...)
  -> resource_links_for_decision_trace(...)
  -> McpToolBody.to_json_dict()
```

Rules:

- durable decision evidence is preferred by the graph service when available.
- topic traces are allowed but must preserve the existing
  `topic_not_durable_decision` warning.
- returned resource links include decision document links and graph entity links
  where evidence exists.

### 12.5 `check_index_status`

MCP signature:

```python
def check_index_status(
    scope: dict[str, object] | None = None,
) -> dict[str, object]: ...
```

Flow:

```text
raw args
  -> CheckIndexStatusInput
  -> scope_from_mcp_input(...)
  -> service_factory.open_status_service()
  -> IndexService.status(scope=...)
  -> status_report_to_payload(...)
  -> McpToolBody.to_json_dict()
```

Rules:

- status is read-only. It may compute freshness by planning against current
  metadata state, but it must not apply indexing or create missing stores.
- output includes metadata, vector, embedding, and graph readiness data.
- unlike `vault://{vault_id}/context/current`, this tool is a detailed agent
  readiness report, not a compact availability resource.

## 13. Prompt Registration Boundary

`src/vault_graph/mcp/mcp_prompts.py` owns prompt templates. Prompts are
user-controlled templates, not autonomous operations.

```python
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

class McpPromptServer(Protocol):
    def prompt(
        self,
        name: str | None = None,
        title: str | None = None,
        description: str | None = None,
        icons: list[object] | None = None,
    ) -> Callable[[Callable[..., object]], Callable[..., object]]: ...

@dataclass(frozen=True)
class McpPromptRegistry:
    prompt_names: tuple[str, ...]

    def render(self, name: str, arguments: dict[str, object]) -> str: ...

def register_mcp_prompts(server: McpPromptServer) -> McpPromptRegistry: ...
```

Registration rules:

- register only through the public `FastMCP.prompt(...)` decorator.
- prompt functions accept only simple JSON-safe arguments.
- prompts return plain text templates.
- prompt text must mention only registered Phase 5C tools.
- prompts must not include hidden instructions that conflict with the user's
  request.
- prompts must not instruct agents to edit Vault files through Vault Graph.
- prompts must tell agents to preserve warnings and evidence references.
- prompts that suggest durable follow-up must route work back through Vault's
  validation workflow.

## 14. Prompt Templates

Phase 5C registers exactly these prompts:

```text
generate_codex_brief(goal, scope=None)
prepare_implementation_context(goal, scope=None)
review_architecture_decision(topic, scope=None)
summarize_feature_history(topic, scope=None)
analyze_project_risk(topic_or_goal, scope=None)
prepare_wiki_update_context(topic, scope=None)
trace_decision_history(topic, scope=None)
```

Required prompt language:

- "Use Vault Graph as read-only working context."
- "Do not read the whole Vault when a scoped context pack is enough."
- "Inspect warnings before relying on evidence."
- "Preserve `vault_id`, document IDs, chunk IDs, and resource links."
- "If durable knowledge should change, propose the Vault source capture,
  validation, release gate, and Git workflow. Do not publish through Vault
  Graph."

Tool guidance per prompt:

| Prompt | Required tool guidance |
| --- | --- |
| `generate_codex_brief` | call `build_context_pack` first; use returned resource links for follow-up evidence |
| `prepare_implementation_context` | call `search_vault`, then `build_context_pack`; call graph tools only when graph context is explicitly useful |
| `review_architecture_decision` | call `get_decision_trace`; use `find_related` for related constraints or systems |
| `summarize_feature_history` | call `search_vault` and `get_decision_trace`; build a context pack when the topic spans multiple pages |
| `analyze_project_risk` | call `search_vault`; call `find_related` when entity or dependency risk matters; preserve warnings |
| `prepare_wiki_update_context` | call `build_context_pack`; propose Vault workflow follow-up instead of editing through Vault Graph |
| `trace_decision_history` | call `get_decision_trace`; read returned decision/entity resource links only when deeper evidence is needed |

## 15. Error And Warning Policy

Tool error payload codes:

- `invalid_tool_arguments`
- `catalog_error`
- `keyword_index_unavailable`
- `vector_store_error`
- `text_embeddings_error`
- `search_error`
- `context_pack_error`
- `graph_unavailable`
- `resource_not_found`
- `metadata_unavailable`
- `read_only_boundary_error`
- `internal_error`

Policy:

- argument parsing errors become invalid-parameter MCP errors with
  `invalid_tool_arguments`.
- `CatalogError` and invalid scope errors remain invalid-parameter MCP errors.
- missing or unhealthy indexes become execution errors unless the underlying
  service returns a warning-backed degraded result.
- vector query failures may degrade to keyword-only search when
  `RetrievalService` returns warnings.
- graph tool failures do not silently degrade to non-graph results.
- search/context graph expansion failures appear as graph warnings when the
  underlying service can still produce a valid partial response.
- unexpected exceptions become internal MCP errors with local paths redacted by
  `mcp_errors.py`.
- warnings are first-class fields; prompts and text mirrors must not hide them.

## 16. Security And Read-Only Requirements

- tools never execute shell commands.
- tools never accept raw filesystem roots.
- tools never call `VaultLoader`.
- tools never edit, rename, delete, rewrite, or publish Vault files.
- tools never create missing metadata, vector, graph, projection, model, cache,
  or Vault files.
- tools do not expose local absolute paths except the explicit configured
  `--state` path when already permitted by error mapping.
- all tool reads are scoped through `VaultCatalog` and `QueryScope`.
- graph dependencies are opened only for explicit graph tool calls or
  `include_graph=True`.
- stdout remains MCP protocol-only; diagnostics go to stderr.
- prompt content is transparent workflow guidance, not hidden policy injection.

## 17. Multi-Vault Requirements

- `scope=None` uses the active Vault.
- `scope.vault_ids` selects explicit Vault IDs.
- `scope.all_vaults=true` expands to all enabled Vault IDs.
- `scope.content_scopes` narrows the selected Vault scope only.
- `include_cross_vault=true` requires explicit graph behavior and at least two
  selected Vault IDs.
- every evidence-bearing result preserves `vault_id`.
- resource links include `vault_id` for Vault-derived resources.
- generated context-pack resources record requested and actual scopes inside the
  pack payload.
- identical paths, document IDs, chunk IDs, entity names, or warning codes from
  different Vaults must not collide in MCP output.

## 18. Agent Ergonomics

Tool names are intentionally boring and direct. They should be easy for an
agent to infer:

- use `search_vault` for evidence search.
- use `build_context_pack` for bounded task context.
- use `find_related` for graph neighborhood evidence.
- use `get_decision_trace` for decision/topic history.
- use `check_index_status` before assuming missing evidence is a content
  problem.

Tool descriptions must state:

- read-only behavior
- active-Vault default scope
- explicit multi-Vault and cross-Vault requirements
- warning preservation
- context is not durable truth

Do not add convenience aliases in Phase 5C. Aliases multiply the MCP surface and
teach agents multiple ways to do the same thing.

## 19. Implementation Flow

Server startup:

```text
vg serve --mcp --state PATH
  -> create_mcp_server(config)
  -> McpServiceFactory.open_read_only()
  -> create ContextPackResourceCache(max_entries=32)
  -> register_mcp_resources(...)
  -> register_mcp_tools(...)
  -> register_mcp_prompts(...)
  -> run stdio transport
```

Non-graph search:

```text
search_vault(query="...", include_graph=false)
  -> base services.retrieval_service
  -> keyword/vector search
  -> evidence resource links
```

Graph search:

```text
search_vault(query="...", include_graph=true)
  -> service_factory.open_retrieval_service(include_graph=true)
  -> lazy GraphRetrievalService and GraphSearchCandidateProvider
  -> keyword/vector/graph search
  -> evidence and graph resource links
```

Context pack resource handoff:

```text
build_context_pack(goal="...")
  -> ContextPackBuilder.build(...)
  -> render_context_pack_json(pack)
  -> ContextPackResourceCache.put(pack, rendered_json=...)
  -> return vault://context/packs/{pack_id}
```

Prompt listing:

```text
list_prompts()
  -> registered FastMCP prompt metadata
  -> no store reads
  -> no graph imports
```

## 20. Tests Required Before Implementation

Required focused tests:

- `tests/test_mcp_tools.py`
  - registers exactly the five Phase 5C tools.
  - does not list deferred tools.
  - each handler has JSON-safe arguments and `structured_output=True`.
  - invalid query, goal, target, topic, limit, max tokens, depth, and scope
    values fail with structured MCP errors.
  - `search_vault` delegates to `RetrievalService.search(...)` and preserves
    warnings, revisions, scopes, evidence, and resource links.
  - `build_context_pack` delegates to `ContextPackBuilder.build(...)`, renders
    canonical JSON, stores it in the shared in-process cache, and returns
    `vault://context/packs/{pack_id}`.
  - `find_related` and `get_decision_trace` open graph retrieval lazily and
    preserve graph warnings, entity IDs, relationship statuses, and resource
    links.
  - `check_index_status` returns metadata/vector/embedding/graph readiness
    without applying indexes.
- `tests/test_mcp_tool_serialization.py`
  - serializes search, context-pack, related, decision-trace, and status DTOs
    without importing CLI helpers.
  - preserves every `vault_id`, `document_id`, and `chunk_id` in evidence.
  - emits Phase 5B resource links with percent-encoded URI segments.
  - keeps text mirrors derived from structured payloads and warning-complete.
- `tests/test_mcp_prompts.py`
  - registers exactly the seven Phase 5C prompts.
  - prompt text mentions only registered tools.
  - prompt text includes read-only, evidence-first, warning, and durable
    follow-up language.
  - prompt listing does not read stores or import graph dependencies.
- `tests/test_mcp_tool_read_only_boundary.py`
  - all tool calls leave registered Vault file bytes unchanged.
  - all tool calls avoid creating missing state directories.
  - invalid argument calls fail before graph dependencies are opened.
  - `include_graph=False` search and context calls do not import rustworkx.
  - `include_graph=True` calls import graph dependencies only after validation.
- update `tests/test_mcp_stdio_smoke.py`
  - official MCP client sees the five tools.
  - official MCP client sees resource templates from Phase 5B.
  - official MCP client sees the seven prompts.
  - stdout contains only protocol messages.

Required final verification:

```bash
uv run --python 3.12 pytest tests/test_mcp_tools.py tests/test_mcp_tool_serialization.py tests/test_mcp_prompts.py tests/test_mcp_tool_read_only_boundary.py tests/test_mcp_stdio_smoke.py -q
uv run --python 3.12 pytest -q
uv run --python 3.12 ruff check src tests
uv run --python 3.12 mypy src tests
git diff --check
```

## 21. Handoff To Implementation Plan

The implementation plan should proceed in this order:

1. Add tool serialization helpers and tests.
2. Add lazy graph-enabled retrieval/context-pack factory methods.
3. Add `McpToolRegistry` and register the five tools.
4. Add prompt registry and register the seven prompts.
5. Wire tools/prompts into `create_mcp_server(...)`.
6. Update stdio smoke tests and read-only boundary tests.

Do not implement `ask_vault`, timeline summaries, memory projections, or Vault
publication helpers as part of Phase 5C.

## 22. Handoff To Phase 6

Phase 6 may add project-memory summaries, open-question tools, recent-change
tools, timeline projections, and result explanations only after the backing
application services exist. Phase 5C leaves extension points through
`McpToolRegistry`, `McpToolBody`, and `mcp_tool_serialization.py`, but it must
not list tools without real service-backed behavior.

## 23. Open Decisions

None.

The design uses existing accepted project decisions:

- Vault remains the source of truth.
- Vault Graph is a read-only, rebuildable, evidence-first access layer.
- MCP is an adapter over application services.
- Phase 5 registers only service-backed behavior.
- generated context packs are working context and remain in-process until a
  durable pack store is explicitly designed.
