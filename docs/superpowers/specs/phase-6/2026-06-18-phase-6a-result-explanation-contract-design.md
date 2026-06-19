# Phase 6A Result Explanation Contract SPEC

Status: Draft for implementation planning

Date: 2026-06-18

Scope: Phase 6A

## 1. Purpose

Phase 6A makes Vault Graph results explainable after they are returned through
MCP. Agents should be able to call `explain_result(result_id)` for a result from
`search_vault`, `build_context_pack`, `find_related`, or
`get_decision_trace` and receive the evidence, signals, relationship status,
warnings, and store revisions that justify that result.

The explanation is not a durable memory store. It is a bounded runtime view over
results already returned by the current MCP process.

## 2. Success Criteria

Phase 6A is complete when:

- MCP registers `explain_result` only after an `ExplainResultService` exists.
- `explain_result(result_id)` returns a structured explanation for results
  emitted by search, context-pack, related, and decision-trace tools in the
  current MCP session.
- explanation payloads preserve Vault IDs, document IDs, chunk IDs, resource
  links, evidence paths, signal scores, relationship status, warnings, and store
  revisions.
- missing or evicted explanation records return a not-found error with guidance
  to rerun the original tool call.
- no explanation record is written to Vault or persisted as durable knowledge.
- text mirrors contain no facts absent from structured output.

## 3. In Scope

- `vault_graph.memory` package foundation.
- result explanation DTOs and serializers.
- bounded in-process MCP explanation cache.
- explanation registration from existing MCP tools.
- `explain_result` MCP tool and input validation.
- focused tests for cache behavior, read-only boundaries, serialization, and
  current-session lookup.

## 4. Out Of Scope

- durable result history
- result lookup across MCP server restarts
- answer synthesis or `ask_vault`
- project memory summaries
- timeline projection
- generic `MemoryStore` or writable memory API
- Mem0, MemMachine, or MCP memory-server integration
- profile, preference, procedural, or raw episode memory
- remote cache, database, or observability backend
- automatic Vault publication

## 5. Files To Add Or Modify

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

`src/vault_graph/memory/result_explanation.py` owns MCP-free explanation DTOs.

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

- `result_id`, `source_kind`, `title`, `vault_id`, and `generated_at` are
  required.
- `evidence` is required unless the source kind is a warning-only operational
  result.
- `signals` can be empty only for graph or context outputs that explain through
  relationship paths instead of search signals.
- all warning records must carry affected Vault IDs.

## 7. Cache Boundary

`src/vault_graph/mcp/result_explanation_cache.py` owns the MCP runtime cache.

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

- The cache is in-process and bounded by insertion order.
- It is created with `RegisteredMcpServer`, like `ContextPackResourceCache`.
- It is not serialized to disk and is not a source of truth.
- Eviction is acceptable; callers can rerun the original query or context tool.
- Cache insertion must not mutate Vault Graph state paths or Vault files.

## 8. Service Boundary

`ExplainResultService` reads only the cache in Phase 6A.

```python
class ExplainResultService:
    def __init__(self, *, cache: ResultExplanationCache) -> None: ...
    def explain(self, *, result_id: str) -> ExplanationRecord: ...
```

Errors:

- blank result ID: validation error
- missing result ID: not found with recovery hint
- malformed cached record: execution error and cache entry ignored

No metadata, vector, graph, or Vault file reads are required for the MVP because
the explanation record is captured when the result is emitted.

## 9. MCP Tool Contract

Add `explain_result` to the MCP tool list after the service exists.

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

- `McpToolRegistry.tool_names` appends `explain_result`.
- Existing Phase 5C tool names and behavior remain unchanged.
- `tests/test_mcp_stdio_smoke.py` updates the expected tool list.
- Prompt templates may mention `explain_result` only after the tool is
  registered.
- Search result IDs and context-pack item IDs are already bounded handles.
  Related and decision-trace `result_id` values must be additive, fixed-length
  runtime handles derived from a canonical hash of the graph result identity.
  They must not concatenate raw user input such as target or topic text.

## 10. Explanation Registration

`mcp_tool_serialization.py` should expose MCP-free conversion helpers:

```python
def explanation_records_for_search(response: SearchResponse) -> tuple[ExplanationRecord, ...]: ...
def explanation_records_for_context_pack(pack: ContextPack) -> tuple[ExplanationRecord, ...]: ...
def explanation_records_for_related(response: RelatedResponse) -> tuple[ExplanationRecord, ...]: ...
def explanation_records_for_decision_trace(response: DecisionTraceResponse) -> tuple[ExplanationRecord, ...]: ...
```

`McpToolRegistry` calls these helpers after the service response is available.
It stores records in `ResultExplanationCache` only after the normal payload,
resource links, warnings, and text mirror are assembled successfully. A tool
call that fails before returning must not leave explainable records behind.

The helpers must not change the tool payload. They only create explanation
records from already-returned data.

## 11. Read-Only And Rebuildability

- The explanation cache is runtime state, not durable projection state.
- Deleting the cache loses only recent explainability convenience.
- Rerunning the original MCP tool against the same indexed Vault state should
  recreate functionally equivalent explanation records.
- No Phase 6A path may call `VaultLoader`, `IndexService.run_apply(...)`, local
  store initializers, or file-write APIs.

## 12. Tests

Required tests:

- DTO validation rejects blank IDs and missing evidence for normal results.
- cache evicts the oldest record after `max_entries`.
- `explain_result` returns not found after eviction.
- search, context-pack, related, and decision-trace tool calls register
  explanation records.
- `explain_result` output preserves evidence, signals, warnings, revisions, and
  resource links.
- read-only boundary test proves tool calls do not mutate Vault files.
- official MCP stdio smoke lists the new exact tool set.

Verification commands:

```bash
uv run --python 3.12 pytest tests/test_result_explanation.py tests/test_mcp_explain_result.py tests/test_mcp_result_explanation_cache.py -q
uv run --python 3.12 pytest tests/test_mcp_tools.py tests/test_mcp_tool_serialization.py tests/test_mcp_tool_read_only_boundary.py -q
VG_RUN_MCP_STDIO_SMOKE=1 uv run --python 3.12 pytest tests/test_mcp_stdio_smoke.py -q
uv run --python 3.12 ruff check src tests
uv run --python 3.12 mypy src tests
```

## 13. Risks And Mitigations

- **Risk:** result IDs are not durable across queries.
  **Mitigation:** clearly scope `explain_result` to the current MCP process and
  return rerun guidance when missing.
- **Risk:** cache records duplicate payload data.
  **Mitigation:** keep the cache bounded and store only structured explanation
  fields needed by the tool.
- **Risk:** prompt text starts relying on unregistered tools.
  **Mitigation:** update prompts and tests only after `explain_result` is
  registered.

## 14. Open Decisions

None for Phase 6A. Durable result history is intentionally out of scope.
