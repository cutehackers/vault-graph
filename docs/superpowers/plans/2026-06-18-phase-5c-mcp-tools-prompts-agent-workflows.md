# Phase 5C MCP Tools, Prompts, And Agent Workflows Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Expose the existing Vault Graph search, context-pack, graph retrieval, decision trace, and status services as read-only MCP tools, and register prompt templates that guide agents toward bounded evidence-first workflows.

**Architecture:** Keep `vault_graph.mcp` as a thin adapter over existing application services. MCP owns argument DTOs, validation, tool envelopes, prompt templates, and resource links; retrieval, graph traversal, context-pack assembly, and status checks stay in their current service modules.

**Tech Stack:** Python 3.12, official MCP Python SDK `FastMCP.tool` with `structured_output=True` and `FastMCP.prompt`, frozen dataclasses, existing `McpServiceFactory`, existing Phase 5B resource cache and URI helpers, pytest, ruff, mypy.

---

## Source Documents

Read these before implementation:

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

Current repo facts to preserve:

- `src/vault_graph/mcp/mcp_server.py` already constructs one `FastMCP` server and returns `RegisteredMcpServer`.
- `RegisteredMcpServer` currently exposes `context_pack_cache` and `resource_registry`; Phase 5C must add `tool_registry` and `prompt_registry`.
- `src/vault_graph/mcp/mcp_service_factory.py` currently keeps `open_read_only()` non-graph by default and exposes lazy graph service methods.
- `McpServiceFactory.open_read_only()` must not import `rustworkx`, create missing stores, create model caches, run indexing, or write registered Vault roots.
- `src/vault_graph/mcp/mcp_scope.py` already owns `McpScopeInput` and `scope_from_mcp_input(...)`; all scoped tools must reuse it.
- `src/vault_graph/mcp/mcp_uri.py` already owns percent-encoded `vault://` resource segments through `encode_resource_segment(...)`.
- `src/vault_graph/mcp/context_pack_resource_cache.py` already owns the bounded in-process generated context-pack resource cache.
- `tests/test_mcp_stdio_smoke.py` currently expects zero tools and zero prompts; Phase 5C must replace those assertions with exact Phase 5C lists.
- CLI JSON helpers in `src/vault_graph/cli/main.py` are useful shape references, but MCP serialization must not import from `vault_graph.cli`.

## Scope

Implement Phase 5C:

- MCP tool response serialization and resource-link generation.
- Lazy graph-enabled retrieval and context-pack builder factory methods.
- MCP input DTOs and validation for five tools:
  - `search_vault`
  - `build_context_pack`
  - `find_related`
  - `get_decision_trace`
  - `check_index_status`
- FastMCP tool registration with `structured_output=True`.
- MCP prompt registration for seven prompt templates:
  - `generate_codex_brief`
  - `prepare_implementation_context`
  - `review_architecture_decision`
  - `summarize_feature_history`
  - `analyze_project_risk`
  - `prepare_wiki_update_context`
  - `trace_decision_history`
- Shared use of the Phase 5B `ContextPackResourceCache` by `build_context_pack`.
- Unit tests, read-only boundary tests, import-laziness tests, and official MCP stdio smoke assertions.

## Non-Goals

Do not implement:

- `ask_vault`
- LLM clients or answer synthesis
- project-memory, issue-memory, timeline, recent-change, or open-question services
- automatic Vault source capture, validation, wiki publication, or file edits
- indexing, repairing, or mutating derived state from MCP tools
- durable context-pack persistence
- resource subscriptions
- Streamable HTTP transport, authentication, or remote hosting
- tool aliases for the five Phase 5C tool names

## Directory And File Structure

Create:

- `src/vault_graph/mcp/mcp_tool_serialization.py`: convert service DTOs to JSON-compatible MCP payloads, warnings, text mirrors, and Phase 5B resource links.
- `src/vault_graph/mcp/mcp_tools.py`: tool input DTOs, validation, `McpToolBody`, `McpToolRegistry`, and FastMCP tool registration.
- `src/vault_graph/mcp/mcp_prompts.py`: prompt names, prompt templates, `McpPromptRegistry`, and FastMCP prompt registration.
- `tests/test_mcp_tool_serialization.py`
- `tests/test_mcp_tools.py`
- `tests/test_mcp_prompts.py`
- `tests/test_mcp_tool_read_only_boundary.py`

Modify:

- `src/vault_graph/mcp/__init__.py`: add lazy exports for new public MCP DTOs and registration types without eager SDK, Chroma, fastembed, or graph imports.
- `src/vault_graph/mcp/mcp_server.py`: register tools and prompts in `create_mcp_server(...)`; add `tool_registry` and `prompt_registry` to `RegisteredMcpServer`.
- `src/vault_graph/mcp/mcp_service_factory.py`: add `open_retrieval_service(include_graph: bool = False)` and `open_context_pack_builder(include_graph: bool = False)`.
- `tests/test_mcp_service_factory.py`: cover the two new lazy factory methods.
- `tests/test_mcp_stdio_smoke.py`: assert the official MCP client lists the five tools, Phase 5B resource templates, and seven prompts.
- `tests/test_mcp_import_boundaries.py`: ensure importing `vault_graph.mcp` and `vault_graph.mcp.mcp_service_factory` still stays lightweight.

Do not modify:

- registered Vault roots or Vault files
- retrieval ranking logic
- graph traversal/projection algorithms
- context-pack JSON schema
- Phase 5B resource URI templates
- `docs/DECISIONS.md`
- `docs/PATCH_LOG.md` unless implementation review changes this plan or a related spec because it finds a concrete mismatch, defect, or risk

## Component And Interface Spec

### `src/vault_graph/mcp/mcp_tool_serialization.py`

Responsibilities:

- Own MCP JSON serialization for tool payloads.
- Preserve `vault_id`, `document_id`, `chunk_id`, evidence, warnings, revisions, backend fields, requested scope, and actual scopes.
- Generate Phase 5B `vault://` resource links through `encode_resource_segment(...)`.
- Generate compact text mirrors from structured payloads only.
- Stay independent from `vault_graph.cli`.

Public functions:

```python
from vault_graph.app.index_service import StatusReport
from vault_graph.context.context_pack import ContextPack
from vault_graph.ingestion.vault_catalog import QueryScope
from vault_graph.mcp.mcp_tools import McpResourceLink
from vault_graph.retrieval.graph_retrieval import DecisionTraceResponse, RelatedResponse
from vault_graph.retrieval.search_response import SearchResponse


def query_scope_to_dict(scope: QueryScope) -> dict[str, object]:
    return {
        "vault_ids": list(scope.vault_ids),
        "content_scopes": list(scope.content_scopes),
        "include_cross_vault": scope.include_cross_vault,
    }


def search_response_to_payload(response: SearchResponse) -> dict[str, object]:
    raise NotImplementedError


def context_pack_to_payload(pack: ContextPack) -> dict[str, object]:
    raise NotImplementedError


def related_response_to_payload(response: RelatedResponse) -> dict[str, object]:
    raise NotImplementedError


def decision_trace_response_to_payload(response: DecisionTraceResponse) -> dict[str, object]:
    raise NotImplementedError


def status_report_to_payload(report: StatusReport, *, selected_scope: QueryScope) -> dict[str, object]:
    raise NotImplementedError


def resource_links_for_search(response: SearchResponse) -> tuple[McpResourceLink, ...]:
    raise NotImplementedError


def resource_links_for_context_pack(pack: ContextPack) -> tuple[McpResourceLink, ...]:
    raise NotImplementedError


def resource_links_for_related(response: RelatedResponse) -> tuple[McpResourceLink, ...]:
    raise NotImplementedError


def resource_links_for_decision_trace(response: DecisionTraceResponse) -> tuple[McpResourceLink, ...]:
    raise NotImplementedError


def tool_text_mirror(payload: dict[str, object]) -> str:
    raise NotImplementedError
```

Implementation detail:

- Copy the value shape of CLI JSON helpers only where it matches the MCP contract.
- Use `context_pack_to_dict(pack)` for `context_pack_to_payload(pack)`.
- Use `json.dumps(payload, sort_keys=True, ensure_ascii=False, allow_nan=False)` for `tool_text_mirror(...)`.
- Raise `ContextPackError`, `SearchError`, or `TypeError` only at serialization boundaries; tool handlers map them through `map_exception_to_mcp_error(...)`.
- Use deterministic link de-duplication keyed by `(rel, uri)`.
- Avoid a circular import by keeping `McpResourceLink` in `mcp_tools.py` and importing serialization helpers inside `McpToolRegistry` methods, not at the top of `mcp_tools.py`.

### `src/vault_graph/mcp/mcp_tools.py`

Responsibilities:

- Own the Phase 5C tool names.
- Own JSON-safe FastMCP handler signatures.
- Convert raw MCP arguments into frozen input DTOs.
- Validate arguments before opening graph services.
- Dispatch to existing application services.
- Map service exceptions through `map_exception_to_mcp_error(...)`.
- Return one canonical MCP tool envelope.

Public contract:

```python
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Literal, Protocol

from vault_graph.mcp.context_pack_resource_cache import ContextPackResourceCache
from vault_graph.mcp.mcp_errors import McpErrorPayload
from vault_graph.mcp.mcp_scope import McpScopeInput
from vault_graph.mcp.mcp_service_factory import McpServiceFactory, McpServices

McpToolName = Literal[
    "search_vault",
    "build_context_pack",
    "find_related",
    "get_decision_trace",
    "check_index_status",
]

MAX_MCP_TOOL_LIMIT = 50


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
    ) -> Callable[[Callable[..., object]], Callable[..., object]]:
        raise NotImplementedError


@dataclass(frozen=True)
class McpResourceLink:
    rel: str
    uri: str
    title: str | None = None
    vault_id: str | None = None
    document_id: str | None = None
    chunk_id: str | None = None

    def to_json_dict(self) -> dict[str, object]:
        return {
            "rel": self.rel,
            "uri": self.uri,
            "title": self.title,
            "vault_id": self.vault_id,
            "document_id": self.document_id,
            "chunk_id": self.chunk_id,
        }


@dataclass(frozen=True)
class McpToolBody:
    tool_name: McpToolName
    payload: dict[str, object]
    resource_links: tuple[McpResourceLink, ...]
    warnings: tuple[McpErrorPayload, ...]
    text: str

    def to_json_dict(self) -> dict[str, object]:
        return {
            "tool_name": self.tool_name,
            "payload": self.payload,
            "resource_links": [link.to_json_dict() for link in self.resource_links],
            "warnings": [_warning_to_dict(warning) for warning in self.warnings],
            "text": self.text,
        }
```

Input DTOs:

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

Registry contract:

```python
class McpToolRegistry:
    tool_names: tuple[McpToolName, ...]

    def __init__(
        self,
        *,
        services: McpServices,
        service_factory: McpServiceFactory,
        context_pack_cache: ContextPackResourceCache,
    ) -> None:
        self._services = services
        self._service_factory = service_factory
        self._context_pack_cache = context_pack_cache
        self.tool_names = (
            "search_vault",
            "build_context_pack",
            "find_related",
            "get_decision_trace",
            "check_index_status",
        )

    def search_vault(self, request: SearchVaultInput) -> McpToolBody:
        raise NotImplementedError

    def build_context_pack(self, request: BuildContextPackInput) -> McpToolBody:
        raise NotImplementedError

    def find_related(self, request: FindRelatedInput) -> McpToolBody:
        raise NotImplementedError

    def get_decision_trace(self, request: DecisionTraceInput) -> McpToolBody:
        raise NotImplementedError

    def check_index_status(self, request: CheckIndexStatusInput) -> McpToolBody:
        raise NotImplementedError
```

Required raw parsing helpers:

```python
def mcp_scope_input_from_raw(
    scope: dict[str, object] | None,
    *,
    include_cross_vault: bool = False,
) -> McpScopeInput | None:
    raise NotImplementedError


def parse_search_vault_input(
    *,
    query: str,
    scope: dict[str, object] | None,
    limit: int,
    include_graph: bool,
    include_cross_vault: bool,
) -> SearchVaultInput:
    raise NotImplementedError


def parse_build_context_pack_input(
    *,
    goal: str,
    scope: dict[str, object] | None,
    max_tokens: int | None,
    limit: int,
    include_graph: bool,
    include_cross_vault: bool,
) -> BuildContextPackInput:
    raise NotImplementedError


def parse_find_related_input(
    *,
    target: str,
    scope: dict[str, object] | None,
    depth: int,
    kinds: list[str] | None,
    limit: int,
    include_cross_vault: bool,
) -> FindRelatedInput:
    raise NotImplementedError


def parse_decision_trace_input(
    *,
    decision_or_topic: str,
    scope: dict[str, object] | None,
    limit: int,
    include_cross_vault: bool,
) -> DecisionTraceInput:
    raise NotImplementedError


def parse_check_index_status_input(*, scope: dict[str, object] | None) -> CheckIndexStatusInput:
    raise NotImplementedError
```

Parsing rules:

- Strip required strings and reject empty values.
- Convert `scope["vault_ids"]` and `scope["content_scopes"]` from list/tuple of strings to tuples.
- Reject unknown scope keys.
- Reject non-boolean `all_vaults` and `include_cross_vault`.
- Treat the top-level tool argument `include_cross_vault` as authoritative. If
  `scope["include_cross_vault"]` is present and differs from the top-level
  value, reject the call with `invalid_tool_arguments`.
- When constructing `McpScopeInput`, copy the top-level `include_cross_vault`
  value into `McpScopeInput.include_cross_vault`.
- Reject `scope.all_vaults` plus `scope.vault_ids`.
- Reject `limit` outside `1..50`.
- Reject `max_tokens <= 0`.
- Reject `depth < 1` and `depth > MAX_GRAPH_PROJECTION_DEPTH`.
- Reject `include_cross_vault=True` for `search_vault` and `build_context_pack` unless `include_graph=True`.
- For graph tools, reject `include_cross_vault=True` unless `scope_from_mcp_input(...)` resolves at least two selected Vault IDs.
- Map validation failures to `McpProtocolError(kind="invalid_parameter", payload.code="invalid_tool_arguments")`.

Service error mapping rules:

- Preserve an existing `McpProtocolError`.
- Convert `CatalogError`, `SearchError`, `ContextPackError`, `GraphStoreError`,
  `KeywordIndexError`, `VectorStoreError`, `TextEmbeddingsError`, and
  `ReadOnlyBoundaryError` through `map_exception_to_mcp_error(...)`.
- Convert unexpected exceptions through `map_exception_to_mcp_error(...)` so
  local paths are redacted consistently with Phase 5A.

Tool flow details:

- `search_vault`: use `services.retrieval_service` when `include_graph=False`; use `service_factory.open_retrieval_service(include_graph=True)` when `include_graph=True`.
- `build_context_pack`: use `services.context_pack_builder` when `include_graph=False`; use `service_factory.open_context_pack_builder(include_graph=True)` when `include_graph=True`; render with `services.context_pack_renderer.render_json(pack)`; store via `context_pack_cache.put(pack, rendered_json=rendered_json)`.
- `find_related`: use `service_factory.open_graph_retrieval_service().related(...)` after raw validation and scope validation.
- `get_decision_trace`: use `service_factory.open_graph_retrieval_service().decision_trace(...)` after raw validation and scope validation.
- `check_index_status`: use `service_factory.open_status_service().status(scope=selected_scope)`.

### `src/vault_graph/mcp/mcp_prompts.py`

Responsibilities:

- Own prompt names and prompt text.
- Keep prompt text transparent, compact, read-only, and limited to registered Phase 5C tools.
- Avoid hidden instructions that conflict with the user's task.

Public contract:

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
    ) -> Callable[[Callable[..., object]], Callable[..., object]]:
        raise NotImplementedError


PHASE_5C_PROMPT_NAMES = (
    "generate_codex_brief",
    "prepare_implementation_context",
    "review_architecture_decision",
    "summarize_feature_history",
    "analyze_project_risk",
    "prepare_wiki_update_context",
    "trace_decision_history",
)


@dataclass(frozen=True)
class McpPromptRegistry:
    prompt_names: tuple[str, ...] = PHASE_5C_PROMPT_NAMES

    def render(self, name: str, arguments: dict[str, object]) -> str:
        raise NotImplementedError


def register_mcp_prompts(server: McpPromptServer) -> McpPromptRegistry:
    raise NotImplementedError
```

Every prompt must include this shared language:

```text
Use Vault Graph as read-only working context.
Do not read the whole Vault when a scoped context pack is enough.
Inspect warnings before relying on evidence.
Preserve vault_id, document IDs, chunk IDs, and resource links.
If durable knowledge should change, propose the Vault source capture, validation, release gate, and Git workflow. Do not publish through Vault Graph.
```

Tool references allowed in prompt text:

- `search_vault`
- `build_context_pack`
- `find_related`
- `get_decision_trace`
- `check_index_status`

Tool references forbidden in prompt text:

- `ask_vault`
- `summarize_project_memory`
- `get_open_questions`
- `get_recent_changes`
- `explain_result`

### `src/vault_graph/mcp/mcp_service_factory.py`

Add `open_retrieval_service(include_graph: bool = False)` and
`open_context_pack_builder(include_graph: bool = False)`. Implement both by
extracting the existing `open_read_only()` construction into a private
`_open_retrieval_components()` helper returning catalog, metadata store, keyword
index, vector store, text embeddings, and readiness. This keeps
`RetrievalService` a deep module and avoids leaking its internals.

Final shape:

```python
@dataclass(frozen=True)
class _RetrievalComponents:
    catalog_service: CatalogService
    catalog: VaultCatalog
    metadata_store: MetadataStore
    keyword_index: KeywordIndex
    vector_store: VectorStore
    text_embeddings: FastEmbedTextEmbeddings
    readiness: SearchReadiness


def open_retrieval_service(self, *, include_graph: bool = False) -> RetrievalService:
    components = self._open_retrieval_components()
    return self._build_retrieval_service(components=components, include_graph=include_graph)


def _build_retrieval_service(
    self,
    *,
    components: _RetrievalComponents,
    include_graph: bool,
) -> RetrievalService:
    from vault_graph.retrieval.retrieval_service import RetrievalService

    return RetrievalService(
        catalog=components.catalog,
        metadata_store=components.metadata_store,
        keyword_index=components.keyword_index,
        vector_store=components.vector_store,
        text_embeddings=components.text_embeddings,
        readiness=components.readiness,
        graph_candidate_provider=(
            self.open_graph_search_candidate_provider() if include_graph else None
        ),
    )


def open_context_pack_builder(self, *, include_graph: bool = False) -> ContextPackBuilder:
    components = self._open_retrieval_components()
    retrieval_service = self._build_retrieval_service(components=components, include_graph=include_graph)
    return self._build_context_pack_builder(components=components, retrieval_service=retrieval_service)


def _build_context_pack_builder(
    self,
    *,
    components: _RetrievalComponents,
    retrieval_service: RetrievalService,
) -> ContextPackBuilder:
    from vault_graph.context.context_pack_builder import MetadataContextEvidenceResolver, SearchContextPackBuilder

    return SearchContextPackBuilder(
        catalog=components.catalog,
        retrieval_service=retrieval_service,
        evidence_resolver=MetadataContextEvidenceResolver(metadata_store=components.metadata_store),
    )
```

Keep `open_read_only()` equivalent to:

```python
components = self._open_retrieval_components()
retrieval_service = self._build_retrieval_service(components=components, include_graph=False)
context_pack_builder = self._build_context_pack_builder(
    components=components,
    retrieval_service=retrieval_service,
)
return McpServices(
    catalog_service=components.catalog_service,
    catalog=components.catalog,
    metadata_store=components.metadata_store,
    retrieval_service=retrieval_service,
    context_pack_builder=context_pack_builder,
    context_pack_renderer=DefaultContextPackRenderer(),
)
```

### `src/vault_graph/mcp/mcp_server.py`

Update the `McpServer` protocol:

```python
class McpServer(Protocol):
    @property
    def name(self) -> str:
        raise NotImplementedError

    def run(self, transport: McpTransport = "stdio", mount_path: str | None = None) -> None:
        raise NotImplementedError

    async def list_resources(self) -> list[Any]:
        raise NotImplementedError

    async def list_resource_templates(self) -> list[Any]:
        raise NotImplementedError

    async def read_resource(self, uri: str) -> Iterable[Any]:
        raise NotImplementedError

    async def list_tools(self) -> Any:
        raise NotImplementedError

    async def list_prompts(self) -> Any:
        raise NotImplementedError
```

Update `RegisteredMcpServer`:

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

In `create_mcp_server(...)`:

```python
from vault_graph.mcp.mcp_prompts import register_mcp_prompts
from vault_graph.mcp.mcp_tools import register_mcp_tools

resource_registry = register_mcp_resources(
    server,
    services=services,
    service_factory=factory,
    context_pack_cache=context_pack_cache,
)
tool_registry = register_mcp_tools(
    server,
    services=services,
    service_factory=factory,
    context_pack_cache=context_pack_cache,
)
prompt_registry = register_mcp_prompts(server)
return RegisteredMcpServer(
    server=server,
    services=services,
    service_factory=factory,
    server_version=config.server_version,
    context_pack_cache=context_pack_cache,
    resource_registry=resource_registry,
    tool_registry=tool_registry,
    prompt_registry=prompt_registry,
)
```

### `src/vault_graph/mcp/__init__.py`

Add lazy exports:

```python
"McpPromptRegistry",
"McpResourceLink",
"McpToolBody",
"McpToolRegistry",
"PHASE_5C_PROMPT_NAMES",
"register_mcp_prompts",
"register_mcp_tools",
```

Add `__getattr__` branches that import only from `mcp_prompts` or `mcp_tools` when those names are requested.

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

- Empty required strings: `invalid_tool_arguments`.
- Non-object `scope`: `invalid_tool_arguments`.
- Unknown scope keys: `invalid_tool_arguments`.
- `all_vaults` combined with `vault_ids`: `catalog_error` from `scope_from_mcp_input(...)` or `invalid_tool_arguments` before scope resolution.
- `content_scopes=[]`: catalog validation error through `scope_from_mcp_input(...)`.
- Content scope widening: catalog validation error through `scope_from_mcp_input(...)`.
- Unknown or disabled Vault IDs: existing catalog error mapping.
- `limit < 1` or `limit > 50`: `invalid_tool_arguments`.
- `max_tokens <= 0`: `invalid_tool_arguments`.
- `depth` outside graph projection max: `invalid_tool_arguments`.
- Cross-Vault search/context without graph: `invalid_tool_arguments`.
- Cross-Vault graph tools with fewer than two selected Vaults: `invalid_tool_arguments`.
- Search metadata/keyword unavailable: mapped existing `SearchError` through `map_exception_to_mcp_error(...)`.
- Vector unavailable: preserve existing warning-backed keyword degradation.
- Graph tool unavailable: execution error; do not silently convert graph tools to non-graph results.
- Graph expansion in search/context unavailable: preserve existing warning-backed partial behavior from backing services.
- Context pack budget truncation: successful tool response with top-level warnings and payload warnings.
- Context-pack cache miss is handled by Phase 5B resource reads, not by tool calls.
- Unexpected exceptions: `internal_error` with paths redacted by `mcp_errors.py`.

## Implementation Steps

### Task 1: Tool Envelope And Serialization Contract

**Files:**

- Create: `src/vault_graph/mcp/mcp_tools.py`
- Create: `src/vault_graph/mcp/mcp_tool_serialization.py`
- Create: `tests/test_mcp_tool_serialization.py`

- [ ] **Step 1: Write failing serialization tests**

Add focused tests that build DTOs directly and assert JSON shape, warning preservation, resource links, and no CLI import.

```python
def test_query_scope_to_dict_preserves_cross_vault_state() -> None:
    scope = QueryScope(vault_ids=("main", "work"), content_scopes=("wiki",), include_cross_vault=True)

    assert query_scope_to_dict(scope) == {
        "vault_ids": ["main", "work"],
        "content_scopes": ["wiki"],
        "include_cross_vault": True,
    }


def test_context_pack_payload_matches_canonical_context_pack_dict() -> None:
    pack = replace(make_pack(), pack_id="pack-1")

    assert context_pack_to_payload(pack) == context_pack_to_dict(pack)


def test_search_resource_links_use_phase_5b_uri_encoding() -> None:
    response = make_search_response(path="wiki/decisions/phase 5.md")

    links = resource_links_for_search(response)

    assert ("evidence", "vault://main/documents/wiki%2Fdecisions%2Fphase%205.md") in {
        (link.rel, link.uri) for link in links
    }
    assert ("page", "vault://main/pages/wiki%2Fdecisions%2Fphase%205.md") in {
        (link.rel, link.uri) for link in links
    }


def test_tool_serialization_does_not_import_cli_helpers() -> None:
    source = Path("src/vault_graph/mcp/mcp_tool_serialization.py").read_text(encoding="utf-8")

    assert "vault_graph.cli" not in source
```

Use helper factories in the test file:

```python
def make_evidence(path: str = "wiki/page.md") -> EvidenceReference:
    return EvidenceReference(
        vault_id="main",
        document_id="doc-1",
        chunk_id="chunk-1",
        path=path,
        section="Section",
        anchor="section",
        content_hash="hash",
        raw_sha256="raw",
        metadata_index_revision="metadata-1",
        vault_revision="git-sha",
    )
```

- [ ] **Step 2: Run serialization tests to verify failure**

Run:

```bash
uv run --python 3.12 pytest tests/test_mcp_tool_serialization.py -q
```

Expected: fail with `ModuleNotFoundError: No module named 'vault_graph.mcp.mcp_tool_serialization'`.

- [ ] **Step 3: Create the shared MCP tool DTOs**

Create `src/vault_graph/mcp/mcp_tools.py` with only these shared records first:

```python
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from vault_graph.mcp.mcp_errors import McpErrorPayload

McpToolName = Literal[
    "search_vault",
    "build_context_pack",
    "find_related",
    "get_decision_trace",
    "check_index_status",
]


@dataclass(frozen=True)
class McpResourceLink:
    rel: str
    uri: str
    title: str | None = None
    vault_id: str | None = None
    document_id: str | None = None
    chunk_id: str | None = None

    def to_json_dict(self) -> dict[str, object]:
        return {
            "rel": self.rel,
            "uri": self.uri,
            "title": self.title,
            "vault_id": self.vault_id,
            "document_id": self.document_id,
            "chunk_id": self.chunk_id,
        }


@dataclass(frozen=True)
class McpToolBody:
    tool_name: McpToolName
    payload: dict[str, object]
    resource_links: tuple[McpResourceLink, ...]
    warnings: tuple[McpErrorPayload, ...]
    text: str

    def to_json_dict(self) -> dict[str, object]:
        return {
            "tool_name": self.tool_name,
            "payload": self.payload,
            "resource_links": [link.to_json_dict() for link in self.resource_links],
            "warnings": [_warning_to_dict(warning) for warning in self.warnings],
            "text": self.text,
        }


def _warning_to_dict(warning: McpErrorPayload) -> dict[str, object]:
    return {
        "code": warning.code,
        "message": warning.message,
        "severity": warning.severity,
        "affected_vault_ids": list(warning.affected_vault_ids),
        "recovery_hint": warning.recovery_hint,
    }
```

This initial file must not import `mcp_tool_serialization.py`.

- [ ] **Step 4: Implement `mcp_tool_serialization.py`**

Implement these helpers:

- `query_scope_to_dict`
- `evidence_to_dict`
- `retrieval_signal_to_dict`
- `search_warning_to_dict`
- `graph_warning_to_dict`
- `mcp_warning_from_search`
- `mcp_warning_from_graph`
- `mcp_warning_from_context`
- `search_response_to_payload`
- `context_pack_to_payload`
- `related_response_to_payload`
- `decision_trace_response_to_payload`
- `status_report_to_payload`
- `resource_links_for_search`
- `resource_links_for_context_pack`
- `resource_links_for_related`
- `resource_links_for_decision_trace`
- `tool_text_mirror`

Use this link helper:

```python
def _links_for_evidence(evidence: EvidenceReference) -> tuple[McpResourceLink, ...]:
    encoded_path = encode_resource_segment(evidence.path)
    links = [
        McpResourceLink(
            rel="evidence",
            uri=f"vault://{evidence.vault_id}/documents/{encoded_path}",
            title=evidence.path,
            vault_id=evidence.vault_id,
            document_id=evidence.document_id,
            chunk_id=evidence.chunk_id,
        )
    ]
    if evidence.path.startswith("wiki/"):
        links.append(
            McpResourceLink(
                rel="page",
                uri=f"vault://{evidence.vault_id}/pages/{encoded_path}",
                title=evidence.path,
                vault_id=evidence.vault_id,
                document_id=evidence.document_id,
                chunk_id=evidence.chunk_id,
            )
        )
    if evidence.path.startswith(("raw/", "docs/", "scratch/reports/")):
        links.append(
            McpResourceLink(
                rel="source",
                uri=f"vault://{evidence.vault_id}/sources/{encode_resource_segment(evidence.document_id)}",
                title=evidence.path,
                vault_id=evidence.vault_id,
                document_id=evidence.document_id,
                chunk_id=evidence.chunk_id,
            )
        )
    if evidence.path.startswith("wiki/decisions/"):
        links.append(
            McpResourceLink(
                rel="decision",
                uri=f"vault://{evidence.vault_id}/decisions/{encode_resource_segment(evidence.document_id)}",
                title=evidence.path,
                vault_id=evidence.vault_id,
                document_id=evidence.document_id,
                chunk_id=evidence.chunk_id,
            )
        )
    if evidence.path.startswith("wiki/issues/"):
        links.append(
            McpResourceLink(
                rel="issue",
                uri=f"vault://{evidence.vault_id}/issues/{encode_resource_segment(evidence.document_id)}",
                title=evidence.path,
                vault_id=evidence.vault_id,
                document_id=evidence.document_id,
                chunk_id=evidence.chunk_id,
            )
        )
    return tuple(links)
```

- [ ] **Step 5: Run serialization tests to verify pass**

Run:

```bash
uv run --python 3.12 pytest tests/test_mcp_tool_serialization.py -q
```

Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add src/vault_graph/mcp/mcp_tools.py src/vault_graph/mcp/mcp_tool_serialization.py tests/test_mcp_tool_serialization.py
git commit -m "feat(mcp): add tool serialization boundary"
```

### Task 2: Lazy Graph Factory Methods

**Files:**

- Modify: `src/vault_graph/mcp/mcp_service_factory.py`
- Modify: `tests/test_mcp_service_factory.py`

- [ ] **Step 1: Write failing factory tests**

Add tests:

```python
def test_mcp_factory_open_retrieval_service_without_graph_is_lightweight(tmp_path: Path) -> None:
    state_path = initialized_state_for_factory(tmp_path)
    factory = McpServiceFactory(state_path=state_path)

    service = factory.open_retrieval_service(include_graph=False)

    assert service is not None
    assert "vault_graph.projection.rustworkx_projection" not in sys.modules


def test_mcp_factory_open_context_pack_builder_with_graph_imports_projection_lazily(tmp_path: Path) -> None:
    state_path = initialized_state_for_factory(tmp_path)
    factory = McpServiceFactory(state_path=state_path)

    factory.open_context_pack_builder(include_graph=False)
    assert "vault_graph.projection.rustworkx_projection" not in sys.modules

    factory.open_context_pack_builder(include_graph=True)

    assert "vault_graph.projection.rustworkx_projection" in sys.modules
```

Use existing `CliRunner` initialization style from `tests/test_mcp_service_factory.py`.

- [ ] **Step 2: Run factory tests to verify failure**

Run:

```bash
uv run --python 3.12 pytest tests/test_mcp_service_factory.py -q
```

Expected: fail because `open_retrieval_service` and `open_context_pack_builder` do not exist.

- [ ] **Step 3: Refactor factory construction without private service field access**

Add a private dataclass and helper:

```python
@dataclass(frozen=True)
class _RetrievalComponents:
    catalog_service: CatalogService
    catalog: VaultCatalog
    metadata_store: MetadataStore
    keyword_index: KeywordIndex
    vector_store: VectorStore
    text_embeddings: FastEmbedTextEmbeddings
    readiness: SearchReadiness
```

Add:

```python
def _open_retrieval_components(self) -> _RetrievalComponents:
    from vault_graph.app.search_readiness_service import ReadOnlySearchReadiness
    from vault_graph.storage.local.chroma_vector_store import ChromaVectorStore
    from vault_graph.storage.local.sqlite_keyword_index import SQLiteKeywordIndex
    from vault_graph.storage.local.sqlite_metadata_store import SQLiteMetadataStore

    catalog_service, catalog = self._catalog()
    metadata_store = SQLiteMetadataStore(catalog_service.metadata_path, initialize=False)
    keyword_index = SQLiteKeywordIndex(catalog_service.metadata_path)
    vector_store = ChromaVectorStore(catalog_service.vector_path, initialize=False, read_only=True)
    text_embeddings = self._search_text_embeddings(catalog_service)
    readiness = ReadOnlySearchReadiness(
        metadata_store=metadata_store,
        keyword_index=keyword_index,
        vector_store=vector_store,
        text_embeddings=text_embeddings,
    )
    return _RetrievalComponents(
        catalog_service=catalog_service,
        catalog=catalog,
        metadata_store=metadata_store,
        keyword_index=keyword_index,
        vector_store=vector_store,
        text_embeddings=text_embeddings,
        readiness=readiness,
    )
```

Use `TYPE_CHECKING` imports to avoid eager imports for `KeywordIndex`, `VectorStore`, and `SearchReadiness`.

- [ ] **Step 4: Implement new public factory methods**

Add:

```python
def open_retrieval_service(self, *, include_graph: bool = False) -> RetrievalService:
    components = self._open_retrieval_components()
    return self._build_retrieval_service(components=components, include_graph=include_graph)


def _build_retrieval_service(
    self,
    *,
    components: _RetrievalComponents,
    include_graph: bool,
) -> RetrievalService:
    from vault_graph.retrieval.retrieval_service import RetrievalService

    return RetrievalService(
        catalog=components.catalog,
        metadata_store=components.metadata_store,
        keyword_index=components.keyword_index,
        vector_store=components.vector_store,
        text_embeddings=components.text_embeddings,
        readiness=components.readiness,
        graph_candidate_provider=(
            self.open_graph_search_candidate_provider() if include_graph else None
        ),
    )


def open_context_pack_builder(self, *, include_graph: bool = False) -> ContextPackBuilder:
    components = self._open_retrieval_components()
    retrieval_service = self._build_retrieval_service(components=components, include_graph=include_graph)
    return self._build_context_pack_builder(components=components, retrieval_service=retrieval_service)


def _build_context_pack_builder(
    self,
    *,
    components: _RetrievalComponents,
    retrieval_service: RetrievalService,
) -> ContextPackBuilder:
    from vault_graph.context.context_pack_builder import MetadataContextEvidenceResolver, SearchContextPackBuilder

    return SearchContextPackBuilder(
        catalog=components.catalog,
        retrieval_service=retrieval_service,
        evidence_resolver=MetadataContextEvidenceResolver(metadata_store=components.metadata_store),
    )
```

Update `open_read_only()` to call the helper and preserve existing behavior.

- [ ] **Step 5: Run factory/import tests**

Run:

```bash
uv run --python 3.12 pytest tests/test_mcp_service_factory.py tests/test_mcp_import_boundaries.py -q
```

Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add src/vault_graph/mcp/mcp_service_factory.py tests/test_mcp_service_factory.py tests/test_mcp_import_boundaries.py
git commit -m "feat(mcp): add lazy graph retrieval factories"
```

### Task 3: Tool Registry And Argument Validation

**Files:**

- Modify: `src/vault_graph/mcp/mcp_tools.py`
- Create: `tests/test_mcp_tools.py`

- [ ] **Step 1: Write failing registry and validation tests**

Add a fake server:

```python
class RecordingToolServer:
    def __init__(self) -> None:
        self.tools: dict[str, Callable[..., object]] = {}
        self.structured_output: dict[str, bool | None] = {}

    def tool(
        self,
        name: str | None = None,
        *,
        title: str | None = None,
        description: str | None = None,
        annotations: object | None = None,
        icons: list[object] | None = None,
        meta: dict[str, object] | None = None,
        structured_output: bool | None = None,
    ) -> Callable[[Callable[..., object]], Callable[..., object]]:
        def decorator(func: Callable[..., object]) -> Callable[..., object]:
            assert name is not None
            self.tools[name] = func
            self.structured_output[name] = structured_output
            return func

        return decorator
```

Add tests:

```python
def test_register_mcp_tools_registers_exact_phase_5c_tools() -> None:
    server = RecordingToolServer()

    registry = register_mcp_tools(
        server,
        services=fake_services(),
        service_factory=fake_factory(),
        context_pack_cache=ContextPackResourceCache(),
    )

    assert registry.tool_names == (
        "search_vault",
        "build_context_pack",
        "find_related",
        "get_decision_trace",
        "check_index_status",
    )
    assert tuple(server.tools) == registry.tool_names
    assert all(server.structured_output[name] is True for name in registry.tool_names)
    assert "ask_vault" not in server.tools


@pytest.mark.parametrize(
    ("tool_name", "kwargs"),
    [
        ("search_vault", {"query": "   "}),
        ("build_context_pack", {"goal": ""}),
        ("find_related", {"target": "", "depth": 1}),
        ("get_decision_trace", {"decision_or_topic": ""}),
        ("search_vault", {"query": "q", "limit": 51}),
        ("build_context_pack", {"goal": "g", "max_tokens": 0}),
        ("search_vault", {"query": "q", "include_cross_vault": True, "scope": {"include_cross_vault": False}}),
    ],
)
def test_tool_validation_errors_are_structured(tool_name: str, kwargs: dict[str, object]) -> None:
    server = RecordingToolServer()
    register_mcp_tools(server, services=fake_services(), service_factory=fake_factory(), context_pack_cache=ContextPackResourceCache())

    with pytest.raises(McpProtocolError) as exc_info:
        server.tools[tool_name](**kwargs)

    assert exc_info.value.kind == "invalid_parameter"
    assert exc_info.value.payload.code == "invalid_tool_arguments"
```

- [ ] **Step 2: Run registry tests to verify failure**

Run:

```bash
uv run --python 3.12 pytest tests/test_mcp_tools.py -q
```

Expected: fail because `register_mcp_tools`, `McpToolRegistry`, and input DTOs do not exist yet.

- [ ] **Step 3: Extend the existing tool DTO module with registry inputs**

Task 1 already created `McpToolName`, `McpResourceLink`, `McpToolBody`, and `_warning_to_dict(...)`. Keep those definitions and add `McpToolServer`, all five input DTOs, `McpToolRegistry`, `_invalid_arguments(...)`, `_tool_body(...)`, `_map_tool_exception(...)`, and `mcp_scope_input_from_raw(...)`.

Use this scope parser behavior:

```python
def mcp_scope_input_from_raw(
    scope: dict[str, object] | None,
    *,
    include_cross_vault: bool = False,
) -> McpScopeInput | None:
    if scope is None:
        return McpScopeInput(include_cross_vault=include_cross_vault) if include_cross_vault else None
    if not isinstance(scope, dict):
        raise _invalid_arguments("scope must be an object")
    allowed = {"vault_ids", "all_vaults", "content_scopes", "include_cross_vault"}
    extra = set(scope) - allowed
    if extra:
        raise _invalid_arguments(f"unsupported scope keys: {', '.join(sorted(extra))}")
    scope_cross_vault = _optional_bool(scope.get("include_cross_vault"), "include_cross_vault", default=include_cross_vault)
    if scope_cross_vault != include_cross_vault:
        raise _invalid_arguments("scope.include_cross_vault must match include_cross_vault")
    return McpScopeInput(
        vault_ids=_optional_string_tuple(scope.get("vault_ids"), "vault_ids"),
        all_vaults=_optional_bool(scope.get("all_vaults"), "all_vaults", default=False),
        content_scopes=_optional_string_tuple(scope.get("content_scopes"), "content_scopes"),
        include_cross_vault=include_cross_vault,
    )
```

- [ ] **Step 4: Implement `register_mcp_tools(...)` with JSON-safe handlers**

Register:

```python
@server.tool("search_vault", structured_output=True)
def search_vault(
    query: str,
    scope: dict[str, object] | None = None,
    limit: int = 10,
    include_graph: bool = False,
    include_cross_vault: bool = False,
) -> dict[str, object]:
    request = parse_search_vault_input(
        query=query,
        scope=scope,
        limit=limit,
        include_graph=include_graph,
        include_cross_vault=include_cross_vault,
    )
    return registry.search_vault(request).to_json_dict()
```

Repeat the same direct shape for the other four tools. Do not inspect FastMCP private state.

- [ ] **Step 5: Run registry and validation tests**

Run:

```bash
uv run --python 3.12 pytest tests/test_mcp_tools.py -q
```

Expected: registration and validation tests pass; dispatch tests that require service behavior may still be absent at this step.

- [ ] **Step 6: Commit**

```bash
git add src/vault_graph/mcp/mcp_tools.py tests/test_mcp_tools.py
git commit -m "feat(mcp): register service-backed tool boundary"
```

### Task 4: Search, Context Pack, And Status Tool Dispatch

**Files:**

- Modify: `src/vault_graph/mcp/mcp_tools.py`
- Modify: `tests/test_mcp_tools.py`

- [ ] **Step 1: Add failing dispatch tests for non-graph tools**

Add fake services:

```python
class RecordingRetrievalService:
    def __init__(self, response: SearchResponse) -> None:
        self.response = response
        self.calls: list[dict[str, object]] = []

    def search(self, **kwargs: object) -> SearchResponse:
        self.calls.append(kwargs)
        return self.response


class RecordingContextPackBuilder:
    def __init__(self, pack: ContextPack) -> None:
        self.pack = pack
        self.requests: list[ContextPackRequest] = []

    def build(self, request: ContextPackRequest) -> ContextPack:
        self.requests.append(request)
        return self.pack
```

Add tests:

```python
def test_search_vault_uses_base_retrieval_service_when_graph_false() -> None:
    response = make_search_response(path="wiki/page.md")
    retrieval = RecordingRetrievalService(response)
    services = fake_services(retrieval_service=retrieval)
    registry = McpToolRegistry(services=services, service_factory=fake_factory(), context_pack_cache=ContextPackResourceCache())

    body = registry.search_vault(SearchVaultInput(query="GraphRAG", limit=3))

    assert retrieval.calls[0]["query_text"] == "GraphRAG"
    assert retrieval.calls[0]["limit"] == 3
    assert retrieval.calls[0]["include_graph"] is False
    assert body.tool_name == "search_vault"
    assert body.payload["result_count"] == 1
    assert any(link.uri.startswith("vault://main/documents/") for link in body.resource_links)


def test_build_context_pack_renders_and_caches_pack_json() -> None:
    pack = replace(make_pack(), pack_id="pack-1")
    cache = ContextPackResourceCache()
    builder = RecordingContextPackBuilder(pack)
    services = fake_services(context_pack_builder=builder, context_pack_renderer=DefaultContextPackRenderer())
    registry = McpToolRegistry(services=services, service_factory=fake_factory(), context_pack_cache=cache)

    body = registry.build_context_pack(BuildContextPackInput(goal="Implement MCP tools"))

    assert cache.get("pack-1") is not None
    assert any(link.uri == "vault://context/packs/pack-1" for link in body.resource_links)
    assert body.payload["pack_id"] == "pack-1"


def test_check_index_status_uses_status_service_without_indexing() -> None:
    factory = fake_factory(status_report=make_status_report())
    registry = McpToolRegistry(services=fake_services(), service_factory=factory, context_pack_cache=ContextPackResourceCache())

    body = registry.check_index_status(CheckIndexStatusInput())

    assert factory.status_calls == 1
    assert body.payload["metadata"]["ok"] is True
```

- [ ] **Step 2: Run dispatch tests to verify failure**

Run:

```bash
uv run --python 3.12 pytest tests/test_mcp_tools.py -q
```

Expected: fail where registry methods return incomplete bodies or do not call services.

- [ ] **Step 3: Implement search dispatch**

Implementation behavior:

```python
def search_vault(self, request: SearchVaultInput) -> McpToolBody:
    selected_scope = _scope_for_tool(
        request.scope,
        catalog=self._services.catalog,
        allow_graph_cross_vault=request.include_graph,
    )
    _reject_cross_vault_without_graph(request.include_cross_vault, include_graph=request.include_graph)
    retrieval_service = (
        self._service_factory.open_retrieval_service(include_graph=True)
        if request.include_graph
        else self._services.retrieval_service
    )
    response = retrieval_service.search(
        query_text=request.query,
        requested_scope=selected_scope,
        limit=request.limit,
        output_format="json",
        include_graph=request.include_graph,
        include_cross_vault=request.include_cross_vault,
    )
    payload = search_response_to_payload(response)
    return _tool_body(
        tool_name="search_vault",
        payload=payload,
        resource_links=resource_links_for_search(response),
        warnings=tuple(mcp_warning_from_search(warning) for warning in response.warnings),
    )
```

- [ ] **Step 4: Implement context-pack dispatch**

Implementation behavior:

```python
def build_context_pack(self, request: BuildContextPackInput) -> McpToolBody:
    selected_scope = _scope_for_tool(
        request.scope,
        catalog=self._services.catalog,
        allow_graph_cross_vault=request.include_graph,
    )
    _reject_cross_vault_without_graph(request.include_cross_vault, include_graph=request.include_graph)
    budget = ContextPackBudget(max_tokens=request.max_tokens or DEFAULT_CONTEXT_MAX_TOKENS)
    pack_request = ContextPackRequest(
        goal=request.goal,
        requested_scope=selected_scope,
        budget=budget,
        retrieval_limit=request.limit,
        include_graph=request.include_graph,
        include_cross_vault=request.include_cross_vault,
    )
    builder = (
        self._service_factory.open_context_pack_builder(include_graph=True)
        if request.include_graph
        else self._services.context_pack_builder
    )
    pack = builder.build(pack_request)
    rendered_json = self._services.context_pack_renderer.render_json(pack)
    self._context_pack_cache.put(pack, rendered_json=rendered_json)
    payload = context_pack_to_payload(pack)
    return _tool_body(
        tool_name="build_context_pack",
        payload=payload,
        resource_links=(
            McpResourceLink(rel="context_pack", uri=f"vault://context/packs/{encode_resource_segment(pack.pack_id)}", title=pack.goal),
            *resource_links_for_context_pack(pack),
        ),
        warnings=tuple(mcp_warning_from_context(warning) for warning in pack.warnings),
    )
```

- [ ] **Step 5: Implement status dispatch**

Implementation behavior:

```python
def check_index_status(self, request: CheckIndexStatusInput) -> McpToolBody:
    selected_scope = _scope_for_tool(request.scope, catalog=self._services.catalog)
    report = self._service_factory.open_status_service().status(scope=selected_scope)
    payload = status_report_to_payload(report, selected_scope=selected_scope)
    return _tool_body(tool_name="check_index_status", payload=payload, resource_links=(), warnings=())
```

- [ ] **Step 6: Run non-graph tool dispatch tests**

Run:

```bash
uv run --python 3.12 pytest tests/test_mcp_tools.py tests/test_mcp_tool_serialization.py -q
```

Expected: all tests in these files pass.

- [ ] **Step 7: Commit**

```bash
git add src/vault_graph/mcp/mcp_tools.py tests/test_mcp_tools.py
git commit -m "feat(mcp): dispatch search context and status tools"
```

### Task 5: Graph Tool Dispatch And Cross-Vault Validation

**Files:**

- Modify: `src/vault_graph/mcp/mcp_tools.py`
- Modify: `tests/test_mcp_tools.py`

- [ ] **Step 1: Add failing graph dispatch tests**

Add tests:

```python
def test_find_related_opens_graph_service_after_validation() -> None:
    graph_service = RecordingGraphRetrievalService(related_response=make_related_response())
    factory = fake_factory(graph_retrieval_service=graph_service)
    registry = McpToolRegistry(services=fake_services(), service_factory=factory, context_pack_cache=ContextPackResourceCache())

    body = registry.find_related(FindRelatedInput(target="GraphRAG", depth=1, kinds=("depends_on",), limit=5))

    assert factory.graph_calls == 1
    assert graph_service.related_calls[0]["target"] == "GraphRAG"
    assert graph_service.related_calls[0]["relationship_types"] == ("depends_on",)
    assert body.tool_name == "find_related"
    assert body.payload["result_count"] == 1


def test_decision_trace_opens_graph_service_after_validation() -> None:
    graph_service = RecordingGraphRetrievalService(decision_trace_response=make_decision_trace_response())
    factory = fake_factory(graph_retrieval_service=graph_service)
    registry = McpToolRegistry(services=fake_services(), service_factory=factory, context_pack_cache=ContextPackResourceCache())

    body = registry.get_decision_trace(DecisionTraceInput(decision_or_topic="Phase 5"))

    assert factory.graph_calls == 1
    assert graph_service.decision_trace_calls[0]["topic"] == "Phase 5"
    assert body.tool_name == "get_decision_trace"


def test_invalid_graph_tool_arguments_fail_before_opening_graph_service() -> None:
    factory = fake_factory()
    registry = McpToolRegistry(services=fake_services(), service_factory=factory, context_pack_cache=ContextPackResourceCache())

    with pytest.raises(McpProtocolError):
        registry.find_related(FindRelatedInput(target="", depth=1))

    assert factory.graph_calls == 0
```

- [ ] **Step 2: Run graph tests to verify failure**

Run:

```bash
uv run --python 3.12 pytest tests/test_mcp_tools.py -q
```

Expected: graph dispatch assertions fail until registry methods call graph services.

- [ ] **Step 3: Implement `find_related` dispatch**

Implementation behavior:

```python
def find_related(self, request: FindRelatedInput) -> McpToolBody:
    selected_scope = _scope_for_tool(
        request.scope,
        catalog=self._services.catalog,
        allow_graph_cross_vault=True,
    )
    _validate_graph_cross_vault_request(selected_scope, include_cross_vault=request.include_cross_vault)
    response = self._service_factory.open_graph_retrieval_service().related(
        target=request.target,
        requested_scope=selected_scope,
        depth=request.depth,
        relationship_types=request.kinds,
        include_cross_vault=request.include_cross_vault,
        limit=request.limit,
        output_format="json",
    )
    payload = related_response_to_payload(response)
    return _tool_body(
        tool_name="find_related",
        payload=payload,
        resource_links=resource_links_for_related(response),
        warnings=tuple(mcp_warning_from_graph(warning) for warning in response.warnings),
    )
```

- [ ] **Step 4: Implement `get_decision_trace` dispatch**

Implementation behavior:

```python
def get_decision_trace(self, request: DecisionTraceInput) -> McpToolBody:
    selected_scope = _scope_for_tool(
        request.scope,
        catalog=self._services.catalog,
        allow_graph_cross_vault=True,
    )
    _validate_graph_cross_vault_request(selected_scope, include_cross_vault=request.include_cross_vault)
    response = self._service_factory.open_graph_retrieval_service().decision_trace(
        topic=request.decision_or_topic,
        requested_scope=selected_scope,
        include_cross_vault=request.include_cross_vault,
        limit=request.limit,
        output_format="json",
    )
    payload = decision_trace_response_to_payload(response)
    return _tool_body(
        tool_name="get_decision_trace",
        payload=payload,
        resource_links=resource_links_for_decision_trace(response),
        warnings=tuple(mcp_warning_from_graph(warning) for warning in response.warnings),
    )
```

- [ ] **Step 5: Run graph dispatch tests**

Run:

```bash
uv run --python 3.12 pytest tests/test_mcp_tools.py -q
```

Expected: all tool tests pass.

- [ ] **Step 6: Commit**

```bash
git add src/vault_graph/mcp/mcp_tools.py tests/test_mcp_tools.py
git commit -m "feat(mcp): dispatch graph tools"
```

### Task 6: Prompt Registry

**Files:**

- Create: `src/vault_graph/mcp/mcp_prompts.py`
- Create: `tests/test_mcp_prompts.py`

- [ ] **Step 1: Write failing prompt tests**

Add a fake prompt server:

```python
class RecordingPromptServer:
    def __init__(self) -> None:
        self.prompts: dict[str, Callable[..., object]] = {}

    def prompt(
        self,
        name: str | None = None,
        *,
        title: str | None = None,
        description: str | None = None,
        icons: list[object] | None = None,
    ) -> Callable[[Callable[..., object]], Callable[..., object]]:
        def decorator(func: Callable[..., object]) -> Callable[..., object]:
            assert name is not None
            self.prompts[name] = func
            return func

        return decorator
```

Add tests:

```python
def test_register_mcp_prompts_registers_exact_phase_5c_prompts() -> None:
    server = RecordingPromptServer()

    registry = register_mcp_prompts(server)

    assert registry.prompt_names == PHASE_5C_PROMPT_NAMES
    assert tuple(server.prompts) == PHASE_5C_PROMPT_NAMES


def test_prompt_text_mentions_only_registered_phase_5c_tools() -> None:
    registry = McpPromptRegistry()
    text = registry.render("generate_codex_brief", {"goal": "Implement tools", "scope": "main"})

    for required in ("build_context_pack", "read-only working context", "Inspect warnings", "resource links"):
        assert required in text
    for forbidden in ("ask_vault", "summarize_project_memory", "get_open_questions", "get_recent_changes", "explain_result"):
        assert forbidden not in text


def test_unknown_prompt_name_raises_invalid_parameter() -> None:
    registry = McpPromptRegistry()

    with pytest.raises(McpProtocolError) as exc_info:
        registry.render("ask_vault", {})

    assert exc_info.value.payload.code == "invalid_prompt"
```

- [ ] **Step 2: Run prompt tests to verify failure**

Run:

```bash
uv run --python 3.12 pytest tests/test_mcp_prompts.py -q
```

Expected: fail because `mcp_prompts.py` does not exist.

- [ ] **Step 3: Implement prompt registry and prompt functions**

Implement `PHASE_5C_PROMPT_NAMES`, `McpPromptRegistry.render(...)`, `_prompt_header(...)`, `_scope_line(...)`, and one render helper per prompt.

Example `generate_codex_brief` body:

```python
def _generate_codex_brief(goal: str, scope: str | None) -> str:
    return _join_prompt_lines(
        "Use Vault Graph as read-only working context.",
        f"Goal: {goal}",
        _scope_line(scope),
        "Call build_context_pack first. Use returned resource links for follow-up evidence.",
        "Do not read the whole Vault when a scoped context pack is enough.",
        "Inspect warnings before relying on evidence.",
        "Preserve vault_id, document IDs, chunk IDs, and resource links.",
        "If durable knowledge should change, propose the Vault source capture, validation, release gate, and Git workflow. Do not publish through Vault Graph.",
    )
```

Register each prompt with a JSON-safe signature:

```python
@server.prompt("generate_codex_brief")
def generate_codex_brief(goal: str, scope: str | None = None) -> str:
    return registry.render("generate_codex_brief", {"goal": goal, "scope": scope})
```

- [ ] **Step 4: Run prompt tests**

Run:

```bash
uv run --python 3.12 pytest tests/test_mcp_prompts.py -q
```

Expected: all prompt tests pass.

- [ ] **Step 5: Commit**

```bash
git add src/vault_graph/mcp/mcp_prompts.py tests/test_mcp_prompts.py
git commit -m "feat(mcp): add agent workflow prompts"
```

### Task 7: Server Wiring, Lazy Exports, Smoke, And Read-Only Boundary

**Files:**

- Modify: `src/vault_graph/mcp/__init__.py`
- Modify: `src/vault_graph/mcp/mcp_server.py`
- Modify: `tests/test_mcp_server.py`
- Modify: `tests/test_mcp_stdio_smoke.py`
- Create: `tests/test_mcp_tool_read_only_boundary.py`

- [ ] **Step 1: Write failing server wiring tests**

Update `tests/test_mcp_server.py`:

```python
def test_create_mcp_server_registers_resources_tools_and_prompts(tmp_path: Path) -> None:
    state_path = initialized_state(tmp_path)

    registered = create_mcp_server(McpServerConfig(state_path=state_path))

    assert registered.resource_registry is not None
    assert registered.tool_registry.tool_names == (
        "search_vault",
        "build_context_pack",
        "find_related",
        "get_decision_trace",
        "check_index_status",
    )
    assert registered.prompt_registry.prompt_names == PHASE_5C_PROMPT_NAMES
```

Update `tests/test_mcp_stdio_smoke.py`:

```python
tool_names = {tool.name for tool in tools.tools}
prompt_names = {prompt.name for prompt in prompts.prompts}
assert tool_names == {
    "search_vault",
    "build_context_pack",
    "find_related",
    "get_decision_trace",
    "check_index_status",
}
assert prompt_names == set(PHASE_5C_PROMPT_NAMES)
```

- [ ] **Step 2: Add read-only boundary tests**

Create `tests/test_mcp_tool_read_only_boundary.py` with tests:

```python
def test_invalid_tool_arguments_do_not_create_missing_state_or_open_graph(tmp_path: Path) -> None:
    vault_root = tmp_path / "vault"
    vault_root.mkdir()
    state_path = initialized_state(tmp_path, vault_root)
    registered = create_mcp_server(McpServerConfig(state_path=state_path))

    with pytest.raises(McpProtocolError):
        registered.tool_registry.search_vault(SearchVaultInput(query="", include_graph=True))

    assert not (state_path / "metadata").exists()
    assert not (state_path / "vector").exists()
    assert not (state_path / "graph").exists()
    assert not (state_path / "projection_cache").exists()


def test_successful_context_pack_tool_does_not_mutate_vault_bytes(tmp_path: Path) -> None:
    vault_root = tmp_path / "vault"
    (vault_root / "wiki").mkdir(parents=True)
    (vault_root / "wiki" / "page.md").write_text("# Page\nVault body\n", encoding="utf-8")
    state_path = initialized_state(tmp_path, vault_root)
    seed_search_indexes(state_path)
    before = file_bytes(vault_root)
    registered = create_mcp_server(McpServerConfig(state_path=state_path))

    try:
        registered.tool_registry.build_context_pack(BuildContextPackInput(goal="Build MCP context"))
    except McpProtocolError:
        pass

    assert file_bytes(vault_root) == before
```

The second test accepts a tool error if local search dependencies are unavailable in the fixture; the invariant is that Vault bytes remain unchanged.

- [ ] **Step 3: Run wiring/read-only tests to verify failure**

Run:

```bash
uv run --python 3.12 pytest tests/test_mcp_server.py tests/test_mcp_tool_read_only_boundary.py tests/test_mcp_stdio_smoke.py -q
```

Expected: server tests fail until registries are wired; stdio smoke is skipped unless `VG_RUN_MCP_STDIO_SMOKE=1`.

- [ ] **Step 4: Wire tools and prompts into `create_mcp_server(...)`**

Modify `mcp_server.py` exactly as defined in the component spec. Keep resource registration first, then tool registration, then prompt registration.

- [ ] **Step 5: Add lazy exports**

Modify `__all__` and `__getattr__` in `src/vault_graph/mcp/__init__.py` for new symbols. Confirm `import vault_graph.mcp` still does not import SDK, graph, Chroma, or fastembed runtime clients.

- [ ] **Step 6: Run focused MCP tests**

Run:

```bash
uv run --python 3.12 pytest tests/test_mcp_server.py tests/test_mcp_tools.py tests/test_mcp_prompts.py tests/test_mcp_tool_read_only_boundary.py tests/test_mcp_import_boundaries.py -q
```

Expected: all focused tests pass.

- [ ] **Step 7: Commit**

```bash
git add src/vault_graph/mcp/__init__.py src/vault_graph/mcp/mcp_server.py tests/test_mcp_server.py tests/test_mcp_stdio_smoke.py tests/test_mcp_tool_read_only_boundary.py
git commit -m "feat(mcp): wire tools and prompts into server"
```

### Task 8: Final Integration Verification

**Files:**

- Review all Phase 5C source and tests.

- [ ] **Step 1: Run required focused tests**

Run:

```bash
uv run --python 3.12 pytest tests/test_mcp_tools.py tests/test_mcp_tool_serialization.py tests/test_mcp_prompts.py tests/test_mcp_tool_read_only_boundary.py tests/test_mcp_stdio_smoke.py -q
```

Expected: focused tests pass; stdio smoke remains skipped unless `VG_RUN_MCP_STDIO_SMOKE=1`.

- [ ] **Step 2: Run MCP and context-pack regression tests**

Run:

```bash
uv run --python 3.12 pytest tests/test_mcp_server.py tests/test_mcp_service_factory.py tests/test_mcp_resources.py tests/test_context_pack_resource_cache.py tests/test_search_include_graph.py tests/test_multi_vault_search.py tests/test_multi_vault_graph_retrieval.py -q
```

Expected: all tests pass.

- [ ] **Step 3: Run full quality gates**

Run:

```bash
uv run --python 3.12 pytest -q
uv run --python 3.12 ruff check src tests
uv run --python 3.12 mypy src tests
git diff --check
```

Expected: all commands pass.

- [ ] **Step 4: Final commit**

If Task 8 produces only verification adjustments, commit them:

```bash
git add src/vault_graph/mcp tests
git commit -m "test(mcp): verify phase 5c integration"
```

Skip this commit when Task 8 made no file changes.

## Validation Review

Security and read-only safety:

- Tools accept only JSON-safe scalars and scope objects, not filesystem paths.
- All tool reads go through `QueryScope`, catalog validation, existing services, and metadata-backed evidence resolution.
- No Phase 5C tool calls `VaultLoader`, writes Vault files, runs indexing, creates missing stores, or persists context packs.
- Generated context-pack cache is bounded and in-process only.

Performance and scalability:

- Default startup, resource listing, prompt listing, non-graph search, non-graph context, and status avoid `rustworkx`.
- Graph dependencies open only for graph tools or `include_graph=True`.
- Tool result limits are capped at `MAX_MCP_TOOL_LIMIT = 50`.
- Resource links are generated from returned evidence only; no full-Vault scans are introduced.

Testability:

- Serialization, factory laziness, tool validation, tool dispatch, prompts, server wiring, and read-only boundaries are independently testable.
- Tests use deterministic DTOs and fake services instead of live MCP clients except for the existing opt-in stdio smoke.
- Full repo gates remain `pytest`, `ruff`, `mypy`, and `git diff --check`.

Maintainability and deep-module boundaries:

- MCP owns adapter-specific DTOs, envelopes, prompt text, and resource links.
- Retrieval, graph traversal, context-pack assembly, and status remain in application/domain services.
- `mcp_tool_serialization.py` prevents tool handlers from copying CLI rendering helpers.
- `mcp_service_factory.py` owns runtime construction; MCP tools do not import store backends directly.

Agent ergonomics:

- Tool names are direct and unambiguous.
- Prompt templates guide agents to bounded context packs and warning inspection.
- The MCP surface lists only Phase 5C service-backed tools and avoids deferred roadmap names.

## Open Decisions

None.

The plan follows existing accepted decisions:

- Vault remains the source of truth.
- Vault Graph is read-only, rebuildable, evidence-first working context.
- MCP is an adapter over application services.
- Phase 5 registers only service-backed behavior.
- Generated context packs remain in the in-process MCP resource cache until a durable pack store is explicitly designed.
