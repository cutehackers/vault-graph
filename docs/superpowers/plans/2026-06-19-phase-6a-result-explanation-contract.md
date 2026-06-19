# Phase 6A Result Explanation Contract Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add MCP `explain_result(result_id)` for results returned by the current MCP process from search, context-pack, related, and decision-trace tools.

**Architecture:** Keep explanation data as bounded in-process runtime context, not durable knowledge. `vault_graph.memory` owns MCP-free explanation DTOs and the `ExplainResultService`; `vault_graph.mcp` owns cache lifetime, tool registration, argument validation, serialization, and result registration from already-returned payloads.

**Tech Stack:** Python 3.12, frozen dataclasses, existing FastMCP tool registration, existing MCP service factory, bounded `OrderedDict` cache, pytest, ruff, mypy.

---

## Source Documents

Read these before implementation:

- `AGENTS.md`
- `docs/SPEC.md`
- `docs/FEATURES.md`
- `docs/DESIGN.md`
- `docs/DECISIONS.md`
- `docs/CONVENTIONS.md`
- `docs/superpowers/specs/phase-6/README.md`
- `docs/superpowers/specs/phase-6/2026-06-18-phase-6-memory-and-explorer-views-overview-design.md`
- `docs/superpowers/specs/phase-6/2026-06-18-phase-6a-result-explanation-contract-design.md`
- `docs/superpowers/plans/2026-06-18-phase-5c-mcp-tools-prompts-agent-workflows.md`

Current repo facts to preserve:

- `src/vault_graph/mcp/mcp_tools.py` currently registers five Phase 5C tools.
- `src/vault_graph/mcp/mcp_tool_serialization.py` already converts search, context-pack, related, decision-trace, and status outputs to MCP payloads and resource links.
- `src/vault_graph/mcp/context_pack_resource_cache.py` is the existing pattern for bounded in-process MCP runtime cache.
- `src/vault_graph/mcp/mcp_server.py` constructs `RegisteredMcpServer` with one `ContextPackResourceCache`.
- `src/vault_graph/mcp/mcp_prompts.py` currently forbids prompt text from mentioning `explain_result` because the tool is not registered yet.
- Search results already expose `result_id`.
- Context-pack items expose `item_id`; Phase 6A uses that value as the explainable result ID.
- Related items and decision-trace steps do not currently expose result IDs. Phase 6A must add additive `result_id` fields to those MCP payloads so callers have a value to pass to `explain_result`.
- Phase 6 uses memory terminology as read-only projection terminology. It must not introduce a generic writable `MemoryStore`, hidden episode log, profile memory database, or direct Mem0/MemMachine dependency.

## Scope

Implement Phase 6A:

- Add `vault_graph.memory` package foundation.
- Add result explanation DTOs, validation, dict serialization, and `ExplainResultService`.
- Add bounded `ResultExplanationCache` owned by the MCP runtime.
- Add explanation record builders for:
  - `SearchResponse`
  - `ContextPack`
  - `RelatedResponse`
  - `DecisionTraceResponse`
- Add additive `result_id` fields to related-item and decision-trace-step MCP payloads.
- Register explanation records after existing tools produce their normal payloads.
- Add `explain_result(result_id)` MCP tool.
- Update prompt text so agents can call `explain_result` after receiving an explainable result ID.
- Update exact tool-list tests and official stdio smoke expectations.
- Add focused unit, integration, read-only, serialization, and import-boundary tests.
- Keep the new `vault_graph.memory` package narrow: Phase 6A creates only result-explanation DTOs/services and must not add a general memory facade.

## Non-Goals

Do not implement:

- durable result history
- result lookup across MCP server restarts
- writing explanation records to SQLite, Chroma, graph state, Vault files, or a remote cache
- new retrieval, ranking, graph traversal, or context-pack selection behavior
- `ask_vault`
- project memory, open-question memory, recent-change timeline, or health explorer tools
- generic `MemoryStore`, `Memory.create`, `Memory.query`, `Memory.upsert`, `Memory.link`, or `Memory.audit`
- Mem0, MemMachine, MCP memory-server, profile memory, preference memory, procedural memory, or raw episode memory integration
- new CLI or HTTP surfaces for explanation lookup
- new prompt names
- automatic Vault source capture, wiki publication, or file edits

## Directory And File Structure

Create:

- `src/vault_graph/memory/__init__.py`: lazy exports for memory DTOs and services.
- `src/vault_graph/memory/result_explanation.py`: explanation DTOs, validation, `ExplainResultService`, JSON-safe dict conversion.
- `src/vault_graph/mcp/result_explanation_cache.py`: bounded in-process cache for explanation records.
- `tests/test_result_explanation.py`: DTO and service contract tests.
- `tests/test_mcp_result_explanation_cache.py`: cache behavior tests.
- `tests/test_mcp_explain_result.py`: registry-level tool and registration tests.

Modify:

- `src/vault_graph/errors.py`: add `ResultExplanationError`.
- `src/vault_graph/mcp/mcp_errors.py`: map result-explanation not-found errors to MCP `not_found`.
- `src/vault_graph/mcp/mcp_tool_serialization.py`: add explanation record builders and additive related/decision result IDs.
- `src/vault_graph/mcp/mcp_tools.py`: add input DTO, parser, registry dependency, registration hooks, and `explain_result` tool.
- `src/vault_graph/mcp/mcp_server.py`: create/pass `ResultExplanationCache`; expose it on `RegisteredMcpServer`.
- `src/vault_graph/mcp/__init__.py`: add lazy exports for new public MCP and memory-facing types.
- `src/vault_graph/mcp/mcp_prompts.py`: allow and mention `explain_result` after the tool is registered.
- `tests/test_mcp_tools.py`: update exact tool list and assert explanation registration.
- `tests/test_mcp_tool_serialization.py`: cover explanation builders and added result IDs.
- `tests/test_mcp_prompts.py`: require `explain_result` mention and keep other future tools forbidden.
- `tests/test_mcp_server.py`: assert server owns the explanation cache and tool list includes `explain_result`.
- `tests/test_mcp_stdio_smoke.py`: update expected tool set.
- `tests/test_mcp_tool_read_only_boundary.py`: prove explanation lookup and registration do not mutate Vault files.
- `tests/test_mcp_import_boundaries.py`: keep imports lightweight.

Do not modify:

- registered Vault roots or Vault files
- `src/vault_graph/storage/local/*`
- retrieval ranking, vector search, keyword search, graph traversal, or context-pack assembly algorithms
- `docs/DECISIONS.md`
- `docs/PATCH_LOG.md` unless review finds a concrete mismatch that requires changing an existing spec or plan

## Component And Interface Spec

### `src/vault_graph/errors.py`

Add:

```python
class ResultExplanationError(VaultGraphError):
    """Raised when result explanation contracts are violated or unavailable."""
```

Use this error only for MCP-free result explanation domain failures. Tool argument parsing should still raise `McpProtocolError` through existing MCP validation helpers.

### `src/vault_graph/memory` package boundary

Create `vault_graph.memory` as a narrow projection package, not a memory
database. Phase 6A must add only:

- `src/vault_graph/memory/__init__.py`
- `src/vault_graph/memory/result_explanation.py`

Do not add `memory_store.py`, `external_memory.py`, `episode_log.py`,
`profile_memory.py`, or a generic `Memory`/`MemoryStore` interface. Future
Mem0, MemMachine, or MCP memory-server integration is a SPEC TODO and must not
be part of this implementation plan.

### `src/vault_graph/memory/result_explanation.py`

Responsibilities:

- Define immutable MCP-free explanation records.
- Validate required identity, evidence, warning, signal, and revision fields.
- Provide one read-only service that resolves a result ID from the runtime cache.
- Convert records to JSON-safe dictionaries without importing MCP modules.

Public API:

```python
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol

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


class CachedExplanationView(Protocol):
    record: ExplanationRecord
    cached_at: str


class ExplanationCacheReader(Protocol):
    def get(self, result_id: str) -> CachedExplanationView | None: ...


class ExplainResultService:
    def __init__(self, *, cache: ExplanationCacheReader) -> None: ...
    def explain(self, *, result_id: str) -> ExplanationRecord: ...


def explanation_record_to_dict(record: ExplanationRecord) -> dict[str, object]: ...
```

Validation rules:

- `result_id`, `source_kind`, `title`, `vault_id`, and `generated_at` are required.
- `summary` may be empty only when the source output also had no summary.
- `evidence` is required for all four Phase 6A source kinds.
- `signals` may be empty for graph/path-based explanations.
- `store_revisions`, `warnings`, `resource_links`, and all tuple fields must be immutable tuples.
- `ExplanationSignal.rank`, when present, must be positive.
- `ExplanationWarning.affected_vault_ids` must be a non-empty tuple.
- `resource_links` entries must be JSON-safe dictionaries containing at least `rel` and `uri`.

Service behavior:

- Blank `result_id` raises `ResultExplanationError("invalid_result_id: result_id is required")`.
- Missing cache entry raises `ResultExplanationError("result_explanation_not_found: rerun the original MCP tool and retry explain_result")`.
- The service does not read metadata, vector, graph, Vault files, or local stores.

### `src/vault_graph/memory/__init__.py`

Expose the Phase 6A public memory API lazily:

```python
__all__ = [
    "CachedExplanationView",
    "ExplainResultService",
    "ExplanationCacheReader",
    "ExplanationEvidenceRef",
    "ExplanationRecord",
    "ExplanationSignal",
    "ExplanationSourceKind",
    "ExplanationWarning",
    "ExplanationWarningSeverity",
    "explanation_record_to_dict",
]
```

Use `__getattr__` following `src/vault_graph/mcp/__init__.py` style so importing `vault_graph.memory` does not open stores or import MCP SDK code.

### `src/vault_graph/mcp/result_explanation_cache.py`

Responsibilities:

- Own MCP process cache lifetime.
- Keep records bounded by insertion order.
- Return the `CachedExplanationView` protocol shape.
- Never serialize to disk.

Public API:

```python
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime

from vault_graph.memory.result_explanation import CachedExplanationView, ExplanationRecord


@dataclass(frozen=True)
class CachedExplanation:
    record: ExplanationRecord
    cached_at: str


class ResultExplanationCache:
    def __init__(
        self,
        *,
        max_entries: int = 256,
        clock: Callable[[], datetime] | None = None,
    ) -> None: ...

    @property
    def max_entries(self) -> int: ...

    def put(self, record: ExplanationRecord) -> CachedExplanation: ...
    def put_many(self, records: tuple[ExplanationRecord, ...]) -> tuple[CachedExplanation, ...]: ...
    def get(self, result_id: str) -> CachedExplanationView | None: ...
    def __len__(self) -> int: ...
```

Rules:

- `max_entries <= 0` raises `ResultExplanationError("max_entries must be positive")`.
- `put(...)` requires a valid `ExplanationRecord`.
- `put_many(())` is a no-op returning `()`.
- Cache key is `record.result_id`.
- Re-putting an existing key replaces the record and moves it to the newest position.
- When over capacity, evict oldest entries with `popitem(last=False)`.
- Cache does not know about `state_path`, Vault roots, or storage backends.

### `src/vault_graph/mcp/mcp_tool_serialization.py`

Additive payload changes:

- `_related_item_to_dict(item, *, response)` must include `"result_id": _related_result_id(response, item)`.
- `_decision_trace_step_to_dict(step, *, response)` must include `"result_id": _decision_trace_result_id(response, step)`.
- Existing fields remain unchanged.

Public helper additions:

```python
from vault_graph.memory.result_explanation import ExplanationRecord


def explanation_records_for_search(response: SearchResponse) -> tuple[ExplanationRecord, ...]: ...
def explanation_records_for_context_pack(pack: ContextPack) -> tuple[ExplanationRecord, ...]: ...
def explanation_records_for_related(response: RelatedResponse) -> tuple[ExplanationRecord, ...]: ...
def explanation_records_for_decision_trace(response: DecisionTraceResponse) -> tuple[ExplanationRecord, ...]: ...
def explanation_payload_to_resource_links(payload: dict[str, object]) -> tuple[McpResourceLink, ...]: ...
```

Private helper additions:

```python
def _evidence_ref_from_metadata(evidence: EvidenceReference) -> ExplanationEvidenceRef: ...
def _evidence_ref_from_context(evidence: ContextEvidence) -> ExplanationEvidenceRef: ...
def _warning_from_retrieval(warning: RetrievalWarning, *, vault_id: str) -> ExplanationWarning: ...
def _warning_from_search(warning: SearchWarning) -> ExplanationWarning: ...
def _warning_from_context(warning: ContextPackWarning) -> ExplanationWarning: ...
def _warning_from_graph(warning: GraphRetrievalWarning) -> ExplanationWarning: ...
def _signal_from_retrieval(signal: RetrievalSignal) -> ExplanationSignal: ...
def _signal_from_context(signal: ContextPackSignal) -> ExplanationSignal: ...
def _store_revision_dicts_for_search(response: SearchResponse, result: RetrievalResult) -> tuple[dict[str, object], ...]: ...
def _store_revision_dicts_for_context(pack: ContextPack) -> tuple[dict[str, object], ...]: ...
def _store_revision_dicts_for_graph(response: RelatedResponse | DecisionTraceResponse) -> tuple[dict[str, object], ...]: ...
def _links_to_dicts(links: tuple[McpResourceLink, ...]) -> tuple[dict[str, object], ...]: ...
def _links_from_dicts(values: tuple[dict[str, object], ...]) -> tuple[McpResourceLink, ...]: ...
def _related_result_id(response: RelatedResponse, item: RelatedItem) -> str: ...
def _decision_trace_result_id(response: DecisionTraceResponse, step: DecisionTraceStep) -> str: ...
def _runtime_result_id(prefix: str, identity: dict[str, object]) -> str: ...
def _relationship_status_for_path(path: tuple[RelationshipRecord, ...]) -> str | None: ...
```

Result ID rules:

- Search explanation `result_id` is `RetrievalResult.result_id`.
- Context-pack explanation `result_id` is `ContextPackItem.item_id`.
- Related explanation `result_id` is a fixed-length runtime handle:

```python
_runtime_result_id(
    "related",
    {
        "target": response.target,
        "vault_id": item.entity.vault_id,
        "entity_id": item.entity.entity_id,
        "rank": item.rank,
        "relationship_path": [relationship.relationship_id for relationship in item.relationship_path],
    },
)
```

- Decision-trace explanation `result_id` is a fixed-length runtime handle:

```python
_runtime_result_id(
    "decision_trace",
    {
        "topic": response.topic,
        "role": step.role,
        "vault_id": step.entity.vault_id,
        "entity_id": step.entity.entity_id,
        "rank": step.rank,
        "relationship_path": [relationship.relationship_id for relationship in step.relationship_path],
    },
)
```

These IDs are explainable runtime handles, not durable product identifiers.
Graph handles must hash canonical identity data and must not concatenate raw
target/topic text into cache keys.

Record construction rules:

- Search records:
  - one record per `response.results`
  - title, summary, vault ID, evidence, signals, relationship status, result warnings, matching response warnings, result revisions, response revisions, and resource links come from the already-returned response
- Context-pack records:
  - one record per item in `current_state`, `relevant_pages`, `relevant_sources`, `decisions`, `constraints`, and `open_questions`
  - item evidence refs resolve against `pack.evidence`; if an item references missing pack evidence, do not synthesize a record for that item and add no hidden fact
  - use `item.item_id` as `result_id`
- Related records:
  - one record per `response.items`
  - title from `item.entity.name`
  - summary from `item.explanation`
  - relationship status from `_relationship_status_for_path(item.relationship_path)`
- Decision-trace records:
  - one record per `response.steps`
  - title from `f"{step.role}: {step.entity.name}"`
  - summary from `step.explanation`
  - relationship status from `step.relationship_status`

Warning matching policy:

- Include item/result-level warnings directly.
- Include top-level search/graph/context warnings when their affected Vault IDs
  overlap the record evidence Vault IDs and their document/chunk/evidence refs
  are empty or match the record evidence.
- Do not hide top-level degraded-mode warnings that affect the record Vault.

Text mirror rule:

- `explain_result` text must be `tool_text_mirror(payload)`.
- Do not write separate human prose that could introduce facts absent from the structured payload.

### `src/vault_graph/mcp/mcp_tools.py`

Update tool name literal:

```python
McpToolName = Literal[
    "search_vault",
    "build_context_pack",
    "find_related",
    "get_decision_trace",
    "check_index_status",
    "explain_result",
]
```

Add input DTO:

```python
@dataclass(frozen=True)
class ExplainResultInput:
    result_id: str
```

Update registry constructor:

```python
from vault_graph.mcp.result_explanation_cache import ResultExplanationCache


class McpToolRegistry:
    def __init__(
        self,
        *,
        services: McpServices,
        service_factory: McpServiceFactory,
        context_pack_cache: ContextPackResourceCache,
        result_explanation_cache: ResultExplanationCache,
    ) -> None:
        self._services = services
        self._service_factory = service_factory
        self._context_pack_cache = context_pack_cache
        self._result_explanation_cache = result_explanation_cache
        self._explain_result_service = ExplainResultService(cache=result_explanation_cache)
        self.tool_names = (
            "search_vault",
            "build_context_pack",
            "find_related",
            "get_decision_trace",
            "check_index_status",
            "explain_result",
        )
```

Add parser and validator:

```python
def parse_explain_result_input(*, result_id: str) -> ExplainResultInput:
    request = ExplainResultInput(result_id=_required_string(result_id, "result_id"))
    _validate_explain_result_request(request)
    return request


def _validate_explain_result_request(request: ExplainResultInput) -> None:
    _required_string(request.result_id, "result_id")
```

Add registry method:

```python
def explain_result(self, request: ExplainResultInput) -> McpToolBody:
    try:
        _validate_explain_result_request(request)
        record = self._explain_result_service.explain(result_id=request.result_id)
        from vault_graph.memory.result_explanation import explanation_record_to_dict
        from vault_graph.mcp.mcp_tool_serialization import explanation_payload_to_resource_links

        payload = explanation_record_to_dict(record)
        return _tool_body(
            tool_name="explain_result",
            payload=payload,
            resource_links=explanation_payload_to_resource_links(payload),
            warnings=tuple(
                McpErrorPayload(
                    code=warning.code,
                    message=warning.message,
                    severity=warning.severity,
                    affected_vault_ids=warning.affected_vault_ids,
                    recovery_hint=warning.recovery_hint,
                )
                for warning in record.warnings
            ),
        )
    except Exception as exc:
        raise _map_tool_exception(exc, service_factory=self._service_factory) from exc
```

Add FastMCP registration:

```python
@server.tool("explain_result", structured_output=True)
def explain_result(result_id: str) -> dict[str, object]:
    request = parse_explain_result_input(result_id=result_id)
    return registry.explain_result(request).to_json_dict()
```

Registration hooks in existing tools:

- In `search_vault`, call `explanation_records_for_search(response)` after
  building the response, build the normal body first, then store records only
  after body assembly succeeds.
- In `build_context_pack`, call `explanation_records_for_context_pack(pack)` after the pack is built and after the context-pack resource cache is written.
- In `find_related`, call `explanation_records_for_related(response)` after
  the graph response is available, build the normal body first, then store
  records only after body assembly succeeds.
- In `get_decision_trace`, call `explanation_records_for_decision_trace(response)`
  after the graph response is available, build the normal body first, then
  store records only after body assembly succeeds.
- `check_index_status` registers no explanation records in Phase 6A because status rows are operational output, not result items.

Implementation pattern:

```python
records = explanation_records_for_search(response)
body = _tool_body(...)
self._result_explanation_cache.put_many(records)
return body
```

Do not change the existing tool payloads except for additive related/decision `result_id` fields.

### `src/vault_graph/mcp/mcp_server.py`

Modify imports and registered server shape:

```python
from vault_graph.mcp.result_explanation_cache import ResultExplanationCache


@dataclass(frozen=True)
class RegisteredMcpServer:
    server: McpServer
    services: McpServices
    service_factory: McpServiceFactory
    server_version: str
    context_pack_cache: ContextPackResourceCache
    result_explanation_cache: ResultExplanationCache
    resource_registry: McpResourceRegistry
    tool_registry: McpToolRegistry
    prompt_registry: McpPromptRegistry
```

In `create_mcp_server(...)`:

```python
context_pack_cache = ContextPackResourceCache(max_entries=32)
result_explanation_cache = ResultExplanationCache(max_entries=256)
tool_registry = register_mcp_tools(
    server,
    services=services,
    service_factory=factory,
    context_pack_cache=context_pack_cache,
    result_explanation_cache=result_explanation_cache,
)
```

Return `result_explanation_cache` on `RegisteredMcpServer`.

### `src/vault_graph/mcp/mcp_errors.py`

Add `ResultExplanationError` to imports and mapping:

```python
from vault_graph.errors import ResultExplanationError
```

Map:

```python
if isinstance(exc, ResultExplanationError):
    code = _code_for_domain_error(exc)
    return _error(
        _kind_for_domain_code(code),
        code,
        _sanitize_error_message(str(exc), user_state_path=user_state_path),
        affected_vault_ids,
        recovery_hint=(
            "Rerun the original MCP tool and pass a result_id from the new response."
            if code == "result_explanation_not_found"
            else None
        ),
    )
```

Extend `_kind_for_domain_code(...)`:

```python
if code == "result_explanation_not_found":
    return "not_found"
if code == "invalid_result_id":
    return "invalid_parameter"
```

### `src/vault_graph/mcp/__init__.py`

Add lazy exports:

```python
"CachedExplanation",
"ResultExplanationCache",
"ExplainResultInput",
"parse_explain_result_input",
```

Do not import `FastMCP`, Chroma, FastEmbed, or graph modules during package import.

### `src/vault_graph/mcp/mcp_prompts.py`

Keep `PHASE_5C_PROMPT_NAMES` unchanged. Add one shared line now that `explain_result` is registered:

```python
"Use explain_result for result_id or context item_id values you plan to rely on."
```

Do not mention `ask_vault`, `summarize_project_memory`, `get_open_questions`, or `get_recent_changes`.

## State Management And Data Flow

Normal tool registration flow:

```text
create_mcp_server(...)
  -> ContextPackResourceCache(max_entries=32)
  -> ResultExplanationCache(max_entries=256)
  -> register_mcp_tools(..., result_explanation_cache=...)
  -> McpToolRegistry creates ExplainResultService(cache=...)
```

Search explanation flow:

```text
search_vault(...)
  -> existing RetrievalService.search(...)
  -> existing payload/resource links/warnings
  -> explanation_records_for_search(response)
  -> ResultExplanationCache.put_many(records)
  -> return unchanged search envelope
```

Context-pack explanation flow:

```text
build_context_pack(...)
  -> existing ContextPackBuilder.build(...)
  -> ContextPackResourceCache.put(pack, rendered_json=...)
  -> explanation_records_for_context_pack(pack)
  -> ResultExplanationCache.put_many(records)
  -> return existing context-pack envelope
```

Related and decision-trace explanation flow:

```text
find_related(...) or get_decision_trace(...)
  -> existing GraphRetrievalService call
  -> payload now includes additive result_id per item/step
  -> explanation_records_for_related/decision_trace(response)
  -> ResultExplanationCache.put_many(records)
  -> return graph envelope
```

Explanation lookup flow:

```text
explain_result(result_id)
  -> parse_explain_result_input(...)
  -> ExplainResultService.explain(result_id=...)
  -> ResultExplanationCache.get(result_id)
  -> explanation_record_to_dict(record)
  -> return MCP envelope with payload, resource_links, warnings, text mirror
```

State guarantees:

- Cache state is in-memory only.
- Cache state is safe to lose.
- Cache miss does not run the original query automatically.
- Cache miss returns `not_found` with a rerun hint.
- Cache registration reads only already-returned service DTOs.
- No Phase 6A code writes to Vault or creates derived stores.

## Error Handling And Edge Cases

- Blank `result_id` argument:
  - parser raises `McpProtocolError(kind="invalid_parameter", code="invalid_tool_arguments")`
- Missing or evicted explanation record:
  - service raises `ResultExplanationError("result_explanation_not_found: ...")`
  - MCP mapping returns `kind="not_found"` and recovery hint to rerun the original tool
- Cache capacity exceeded:
  - oldest record evicted
  - newer records remain explainable
- Repeated result ID:
  - latest record replaces previous entry and moves to newest position
- Search response with zero results:
  - no records registered
  - tool still returns normal search envelope
- Context-pack item references missing pack evidence:
  - no explanation record for that item
  - no fabricated evidence
- Related/decision trace response with warnings and no items/steps:
  - no records registered
  - tool warnings remain visible in the original response
- Unsupported values in `resource_links` dicts:
  - explanation DTO validation fails before caching
- Server restart:
  - cache is empty
  - `explain_result` returns not found
- Prompt text:
  - may mention `explain_result`
  - must not mention unregistered future tools

## Implementation Tasks

### Task 1: Domain DTOs, Service, And Error Mapping

**Files:**

- Modify: `src/vault_graph/errors.py`
- Modify: `src/vault_graph/mcp/mcp_errors.py`
- Create: `src/vault_graph/memory/__init__.py`
- Create: `src/vault_graph/memory/result_explanation.py`
- Test: `tests/test_result_explanation.py`
- Test: `tests/test_mcp_errors.py`

- [ ] **Step 1: Write failing DTO validation tests**

Add tests:

```python
def test_explanation_record_requires_identity_and_evidence() -> None: ...
def test_explanation_warning_requires_affected_vault_ids() -> None: ...
def test_explain_result_service_rejects_blank_result_id() -> None: ...
def test_explain_result_service_reports_missing_result_id() -> None: ...
def test_explanation_record_to_dict_is_json_safe() -> None: ...
```

Run:

```bash
uv run --python 3.12 pytest tests/test_result_explanation.py -q
```

Expected: fail because `vault_graph.memory.result_explanation` does not exist.

- [ ] **Step 2: Add `ResultExplanationError` and MCP mapping tests**

In `tests/test_mcp_errors.py`, add:

```python
def test_result_explanation_not_found_maps_to_mcp_not_found() -> None:
    error = map_exception_to_mcp_error(
        ResultExplanationError("result_explanation_not_found: missing result explanation")
    )

    assert error.kind == "not_found"
    assert error.payload.code == "result_explanation_not_found"
    assert "Rerun the original MCP tool" in (error.payload.recovery_hint or "")
```

Run:

```bash
uv run --python 3.12 pytest tests/test_mcp_errors.py -q
```

Expected: fail until error class and mapping are implemented.

- [ ] **Step 3: Implement DTOs, service, and lazy memory exports**

Implement the API exactly from the component spec. Keep the module MCP-free.

- [ ] **Step 4: Implement MCP error mapping**

Add `ResultExplanationError` mapping and `_kind_for_domain_code(...)` cases.

- [ ] **Step 5: Verify Task 1**

Run:

```bash
uv run --python 3.12 pytest tests/test_result_explanation.py tests/test_mcp_errors.py -q
```

Expected: pass.

- [ ] **Step 6: Commit Task 1**

```bash
git add src/vault_graph/errors.py src/vault_graph/memory src/vault_graph/mcp/mcp_errors.py tests/test_result_explanation.py tests/test_mcp_errors.py
git commit -m "feat(memory): add result explanation contract"
```

### Task 2: Bounded Result Explanation Cache

**Files:**

- Create: `src/vault_graph/mcp/result_explanation_cache.py`
- Modify: `src/vault_graph/mcp/__init__.py`
- Test: `tests/test_mcp_result_explanation_cache.py`

- [ ] **Step 1: Write failing cache tests**

Add tests:

```python
def test_result_explanation_cache_stores_and_returns_records() -> None: ...
def test_result_explanation_cache_evicts_oldest_record() -> None: ...
def test_result_explanation_cache_reput_moves_record_to_newest() -> None: ...
def test_result_explanation_cache_put_many_is_bounded() -> None: ...
def test_result_explanation_cache_rejects_non_positive_max_entries() -> None: ...
```

Use fixed clock values like `datetime(2026, 6, 19, tzinfo=UTC)`.

Run:

```bash
uv run --python 3.12 pytest tests/test_mcp_result_explanation_cache.py -q
```

Expected: fail because cache module does not exist.

- [ ] **Step 2: Implement cache**

Mirror `ContextPackResourceCache` style:

- `OrderedDict[str, CachedExplanation]`
- UTC ISO cached timestamp
- insertion-order eviction
- no filesystem access

- [ ] **Step 3: Add lazy exports**

Expose `CachedExplanation` and `ResultExplanationCache` from `vault_graph.mcp`.

- [ ] **Step 4: Verify Task 2**

Run:

```bash
uv run --python 3.12 pytest tests/test_mcp_result_explanation_cache.py -q
```

Expected: pass.

- [ ] **Step 5: Commit Task 2**

```bash
git add src/vault_graph/mcp/result_explanation_cache.py src/vault_graph/mcp/__init__.py tests/test_mcp_result_explanation_cache.py
git commit -m "feat(mcp): add result explanation cache"
```

### Task 3: Explanation Serialization And Explainable Graph Result IDs

**Files:**

- Modify: `src/vault_graph/mcp/mcp_tool_serialization.py`
- Test: `tests/test_mcp_tool_serialization.py`

- [ ] **Step 1: Write failing serialization tests**

Add tests:

```python
def test_search_explanation_records_preserve_result_evidence_signals_and_revisions() -> None: ...
def test_context_pack_explanation_records_use_item_id_as_result_id() -> None: ...
def test_related_payload_includes_result_id() -> None: ...
def test_related_explanation_records_preserve_graph_evidence_and_relationship_status() -> None: ...
def test_decision_trace_payload_includes_result_id() -> None: ...
def test_decision_trace_explanation_records_preserve_step_evidence() -> None: ...
def test_explanation_payload_resource_links_round_trip() -> None: ...
```

Use existing helpers:

- `make_search_response(...)`
- `make_pack(...)`
- `make_related_response()`
- `make_decision_trace_response()`

Run:

```bash
uv run --python 3.12 pytest tests/test_mcp_tool_serialization.py -q
```

Expected: fail because helpers and additive IDs do not exist.

- [ ] **Step 2: Add additive result IDs to related and decision payloads**

Change:

```python
def related_response_to_payload(response: RelatedResponse) -> dict[str, object]:
    ...
    "items": [_related_item_to_dict(item, response=response) for item in response.items],
```

Change:

```python
def decision_trace_response_to_payload(response: DecisionTraceResponse) -> dict[str, object]:
    ...
    "steps": [_decision_trace_step_to_dict(step, response=response) for step in response.steps],
```

Update the private dict helpers to include `result_id`.

- [ ] **Step 3: Implement explanation record builders**

Implement public helpers and private conversion helpers from the component spec.

Keep these rules:

- convert only already-returned DTO data
- do not call stores, services, loaders, or indexes
- do not import CLI
- keep output JSON-safe

- [ ] **Step 4: Verify Task 3**

Run:

```bash
uv run --python 3.12 pytest tests/test_mcp_tool_serialization.py -q
```

Expected: pass.

- [ ] **Step 5: Commit Task 3**

```bash
git add src/vault_graph/mcp/mcp_tool_serialization.py tests/test_mcp_tool_serialization.py
git commit -m "feat(mcp): build result explanation records"
```

### Task 4: MCP Tool Registry Registration And Lookup

**Files:**

- Modify: `src/vault_graph/mcp/mcp_tools.py`
- Test: `tests/test_mcp_tools.py`
- Test: `tests/test_mcp_explain_result.py`

- [ ] **Step 1: Write failing registry tests**

In `tests/test_mcp_tools.py`, update exact tool list to include `explain_result`.

Add tests in `tests/test_mcp_explain_result.py`:

```python
def test_search_tool_registers_explanation_records(tmp_path: Path) -> None: ...
def test_context_pack_tool_registers_explanation_records(tmp_path: Path) -> None: ...
def test_related_tool_registers_explanation_records(tmp_path: Path) -> None: ...
def test_decision_trace_tool_registers_explanation_records(tmp_path: Path) -> None: ...
def test_explain_result_returns_cached_search_record(tmp_path: Path) -> None: ...
def test_explain_result_returns_not_found_for_missing_record(tmp_path: Path) -> None: ...
def test_explain_result_validation_rejects_blank_result_id(tmp_path: Path) -> None: ...
def test_check_index_status_does_not_register_explanation_records(tmp_path: Path) -> None: ...
```

Use `ResultExplanationCache(max_entries=...)` and the fake service factory patterns already in `tests/test_mcp_tools.py`.

Run:

```bash
uv run --python 3.12 pytest tests/test_mcp_tools.py tests/test_mcp_explain_result.py -q
```

Expected: fail because registry does not accept or use `ResultExplanationCache`.

- [ ] **Step 2: Update registry constructor and tool names**

Add `result_explanation_cache` parameter and `ExplainResultService` member.

Every current test constructing `McpToolRegistry(...)` must pass `ResultExplanationCache()`.

- [ ] **Step 3: Add parser, validator, and `explain_result` method**

Implement `ExplainResultInput`, `parse_explain_result_input(...)`, `_validate_explain_result_request(...)`, and `McpToolRegistry.explain_result(...)`.

- [ ] **Step 4: Register explanation records from existing tools**

Update `search_vault`, `build_context_pack`, `find_related`, and `get_decision_trace` registry methods to call the appropriate `explanation_records_for_*` helper and `put_many(...)`.

Do not register explanations for failed tool calls.

- [ ] **Step 5: Register FastMCP `explain_result`**

Add a `@server.tool("explain_result", structured_output=True)` handler at the end of `register_mcp_tools(...)`.

- [ ] **Step 6: Verify Task 4**

Run:

```bash
uv run --python 3.12 pytest tests/test_mcp_tools.py tests/test_mcp_explain_result.py -q
```

Expected: pass.

- [ ] **Step 7: Commit Task 4**

```bash
git add src/vault_graph/mcp/mcp_tools.py tests/test_mcp_tools.py tests/test_mcp_explain_result.py
git commit -m "feat(mcp): add explain result tool"
```

### Task 5: MCP Server Wiring, Exports, Prompts, And Smoke Expectations

**Files:**

- Modify: `src/vault_graph/mcp/mcp_server.py`
- Modify: `src/vault_graph/mcp/__init__.py`
- Modify: `src/vault_graph/mcp/mcp_prompts.py`
- Modify: `tests/test_mcp_server.py`
- Modify: `tests/test_mcp_prompts.py`
- Modify: `tests/test_mcp_stdio_smoke.py`
- Modify: `tests/test_mcp_import_boundaries.py`

- [ ] **Step 1: Write failing server and prompt tests**

Update tests:

```python
def test_create_mcp_server_registers_resources_tools_prompts_and_explanation_cache(tmp_path: Path) -> None: ...
def test_prompt_text_mentions_only_registered_tools_after_phase_6a() -> None: ...
```

Update expected official stdio tool set:

```python
EXPECTED_PHASE_6A_TOOLS = {
    "search_vault",
    "build_context_pack",
    "find_related",
    "get_decision_trace",
    "check_index_status",
    "explain_result",
}
```

Run:

```bash
uv run --python 3.12 pytest tests/test_mcp_server.py tests/test_mcp_prompts.py tests/test_mcp_stdio_smoke.py tests/test_mcp_import_boundaries.py -q
```

Expected: fail until server wiring and prompt text are updated. The stdio smoke remains skipped unless `VG_RUN_MCP_STDIO_SMOKE=1` is set.

- [ ] **Step 2: Wire `ResultExplanationCache` into `create_mcp_server(...)`**

Create the cache once per MCP process and pass it to tool registration.

- [ ] **Step 3: Update `RegisteredMcpServer`**

Add `result_explanation_cache` field and assertions in tests.

- [ ] **Step 4: Update prompts**

Add one shared line recommending `explain_result` for returned result IDs. Keep all future unregistered memory tools out of prompts.

- [ ] **Step 5: Update imports and exact smoke expectations**

Keep `vault_graph.mcp` import lightweight and update expected tool list.

- [ ] **Step 6: Verify Task 5**

Run:

```bash
uv run --python 3.12 pytest tests/test_mcp_server.py tests/test_mcp_prompts.py tests/test_mcp_stdio_smoke.py tests/test_mcp_import_boundaries.py -q
```

Expected: pass, with `tests/test_mcp_stdio_smoke.py` skipped unless the environment variable is set.

- [ ] **Step 7: Commit Task 5**

```bash
git add src/vault_graph/mcp/mcp_server.py src/vault_graph/mcp/__init__.py src/vault_graph/mcp/mcp_prompts.py tests/test_mcp_server.py tests/test_mcp_prompts.py tests/test_mcp_stdio_smoke.py tests/test_mcp_import_boundaries.py
git commit -m "feat(mcp): wire result explanations into server"
```

### Task 6: Read-Only Boundary And End-To-End Regression Tests

**Files:**

- Modify: `tests/test_mcp_tool_read_only_boundary.py`
- Modify: `tests/test_mcp_explain_result.py`

- [ ] **Step 1: Add read-only regression tests**

Add tests:

```python
def test_search_then_explain_result_does_not_mutate_vault_bytes(tmp_path: Path) -> None: ...
def test_context_pack_then_explain_result_does_not_mutate_vault_bytes(tmp_path: Path) -> None: ...
def test_explain_result_cache_miss_does_not_create_state_paths(tmp_path: Path) -> None: ...
```

Use existing `initialized_state(...)`, `seed_search_indexes(...)`, and `file_bytes(...)` patterns.

- [ ] **Step 2: Add registry-level eviction integration**

In `tests/test_mcp_explain_result.py`, add:

```python
def test_explain_result_not_found_after_cache_eviction(tmp_path: Path) -> None: ...
```

Use `ResultExplanationCache(max_entries=1)`.

- [ ] **Step 3: Verify Task 6**

Run:

```bash
uv run --python 3.12 pytest tests/test_mcp_tool_read_only_boundary.py tests/test_mcp_explain_result.py -q
```

Expected: pass.

- [ ] **Step 4: Commit Task 6**

```bash
git add tests/test_mcp_tool_read_only_boundary.py tests/test_mcp_explain_result.py
git commit -m "test(mcp): verify result explanation boundaries"
```

### Task 7: Full Verification And Hygiene

**Files:**

- All files modified in Tasks 1-6.

- [ ] **Step 1: Run focused Phase 6A tests**

```bash
uv run --python 3.12 pytest tests/test_result_explanation.py tests/test_mcp_result_explanation_cache.py tests/test_mcp_explain_result.py -q
```

Expected: pass.

- [ ] **Step 2: Run MCP regression tests**

```bash
uv run --python 3.12 pytest tests/test_mcp_tools.py tests/test_mcp_tool_serialization.py tests/test_mcp_prompts.py tests/test_mcp_server.py tests/test_mcp_tool_read_only_boundary.py -q
```

Expected: pass.

- [ ] **Step 3: Run official MCP stdio smoke**

```bash
VG_RUN_MCP_STDIO_SMOKE=1 uv run --python 3.12 pytest tests/test_mcp_stdio_smoke.py -q
```

Expected: pass and list exactly the Phase 6A tool set.

- [ ] **Step 4: Run full repository tests**

```bash
uv run --python 3.12 pytest -q
```

Expected: pass.

- [ ] **Step 5: Run static checks**

```bash
uv run --python 3.12 ruff check src tests
uv run --python 3.12 mypy src tests
git diff --check
```

Expected: all pass with no output from `git diff --check`.

- [ ] **Step 6: Commit final cleanup if needed**

Only commit if Task 7 required fixes:

```bash
git add src tests
git commit -m "chore: finalize phase 6a result explanation"
```

## Test Matrix

Required tests by behavior:

| Behavior | Test File |
| --- | --- |
| DTO validation and dict serialization | `tests/test_result_explanation.py` |
| service cache lookup and not found | `tests/test_result_explanation.py` |
| cache eviction and insertion order | `tests/test_mcp_result_explanation_cache.py` |
| search explanation registration | `tests/test_mcp_explain_result.py` |
| context-pack explanation registration | `tests/test_mcp_explain_result.py` |
| related explanation registration | `tests/test_mcp_explain_result.py` |
| decision-trace explanation registration | `tests/test_mcp_explain_result.py` |
| additive related/decision result IDs | `tests/test_mcp_tool_serialization.py` |
| exact tool list | `tests/test_mcp_tools.py`, `tests/test_mcp_stdio_smoke.py` |
| prompt mentions only registered tools | `tests/test_mcp_prompts.py` |
| read-only Vault boundary | `tests/test_mcp_tool_read_only_boundary.py` |
| import boundaries | `tests/test_mcp_import_boundaries.py` |
| no generic writable memory layer or external memory dependency | `tests/test_mcp_import_boundaries.py`, `tests/test_mcp_tool_read_only_boundary.py` |

## Verification Commands

Run before considering implementation complete:

```bash
uv run --python 3.12 pytest tests/test_result_explanation.py tests/test_mcp_result_explanation_cache.py tests/test_mcp_explain_result.py -q
uv run --python 3.12 pytest tests/test_mcp_tools.py tests/test_mcp_tool_serialization.py tests/test_mcp_prompts.py tests/test_mcp_server.py tests/test_mcp_tool_read_only_boundary.py -q
VG_RUN_MCP_STDIO_SMOKE=1 uv run --python 3.12 pytest tests/test_mcp_stdio_smoke.py -q
uv run --python 3.12 pytest -q
uv run --python 3.12 ruff check src tests
uv run --python 3.12 mypy src tests
git diff --check
```

## Risks And Mitigations

- **Risk:** callers expect `result_id` to work after server restart.
  **Mitigation:** service returns `not_found` with rerun guidance; docs and prompts call this current-session explainability.
- **Risk:** related and decision-trace payload schema changes break callers expecting exact fields.
  **Mitigation:** add only additive `result_id` fields and keep all existing keys unchanged.
- **Risk:** raw graph result IDs expose unbounded user input or collide through
  delimiter ambiguity.
  **Mitigation:** derive graph `result_id` values from canonical identity hashes
  with fixed-length runtime handles.
- **Risk:** explanation records drift from returned payloads.
  **Mitigation:** build records only from already-returned DTOs, write cache
  entries only after body assembly succeeds, and cover record-vs-payload
  preservation in tests.
- **Risk:** cache becomes a hidden durable knowledge source.
  **Mitigation:** in-process only, bounded, no disk writes, no state path dependency, read-only boundary tests.
- **Risk:** `vault_graph.memory` package foundation is misread as permission to build a writable agent memory layer.
  **Mitigation:** implement only `result_explanation.py`; import-boundary and read-only tests reject generic memory-store, episode-log, profile-memory, or external memory dependencies.
- **Risk:** prompt text starts mentioning future tools again.
  **Mitigation:** update prompt test to allow `explain_result` but continue forbidding `ask_vault`, project memory, open questions, and recent changes.
- **Risk:** explanation registration failures make existing tools fail.
  **Mitigation:** generated records should be deterministic from valid DTOs; tests cover each source. Do not swallow validation failures because malformed explanation output would make the new contract unreliable.

## Validation Review

Security and read-only safety:

- The cache has no path, state, or file API.
- The service reads only cache entries.
- Existing tool registration hooks consume already-returned DTOs.
- Read-only boundary tests compare Vault bytes before and after search/context/explain flows.
- No Mem0, MemMachine, MCP memory-server, raw episode log, profile memory, or generic writable `MemoryStore` appears in the Phase 6A implementation surface.

Performance and scalability:

- Cache is bounded at 256 entries.
- Record builders run O(number of returned result items), not over the full Vault.
- No extra metadata, vector, graph, or Vault reads happen at explanation time.
- Scale-up remains compatible because the cache stores logical evidence IDs, revisions, resource links, and warnings rather than backend-native row IDs.

Testability:

- DTOs, cache, serialization, registry behavior, server wiring, prompts, and read-only boundaries are each testable without a live MCP client.
- Official stdio smoke remains the final MCP SDK compatibility check.
- Result ID eviction and not-found behavior have deterministic tests through small cache sizes.

Maintainability and deep-module boundaries:

- `vault_graph.memory.result_explanation` is the deep domain module.
- `vault_graph.mcp.result_explanation_cache` owns runtime cache mechanics.
- `mcp_tool_serialization.py` owns conversion from current service DTOs to explanation records.
- `mcp_tools.py` remains the adapter that registers records and exposes the tool.
- No retrieval, graph, context-pack, or storage module learns about MCP caches.
- The `vault_graph.memory` package stays deep and narrow; future external memory adapters are not introduced until the SPEC TODO graduates into its own design.

Agent ergonomics:

- Existing result IDs remain usable.
- Related and decision-trace outputs gain explicit `result_id`.
- Context-pack item IDs become accepted explanation handles without changing the canonical context-pack schema.
- Prompts tell agents when to call `explain_result` without advertising future memory tools.

## Open Decisions

None. Phase 6A intentionally uses bounded current-process cache lookup and excludes durable result history.

## Patch Log Impact

Add a `docs/PATCH_LOG.md` entry for the 2026-06-19 memory-layer boundary
clarification because external memory-layer review changed Phase 6 specs and
this plan to prevent a concrete architectural drift risk.
