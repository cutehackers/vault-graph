# Phase 5C MCP Tools, Prompts, And Agent Workflows Design

Status: Draft for implementation planning

Date: 2026-06-15

Scope: Phase 5C

## 1. Purpose

Phase 5C exposes the existing Vault Graph services as MCP tools and prompt
templates. The goal is to let agents retrieve bounded, evidence-linked context
without inventing answer synthesis or bypassing the CLI-tested application
services.

Tools return structured data. Prompts are lightweight workflow templates that
guide an agent toward the right tools and remind it that Vault Graph output is
working context, not durable truth.

## 2. In Scope

- Register service-backed tools for search, context packs, related entities,
  decision traces, and index status.
- Return structured output plus a text mirror for compatibility.
- Preserve all warnings, evidence refs, backend use, store revisions, and
  Vault IDs.
- Return MCP resource links where Phase 5B resources exist.
- Register prompt templates for repeatable agent workflows.
- Add tests for tool schemas, prompt text, read-only behavior, and multi-vault
  scope handling.

## 3. Out Of Scope

- `ask_vault` answer generation.
- LLM clients or hosted model calls.
- Phase 6 project memory, open-question, and recent-change projections.
- Autonomous wiki publication.
- Tools that index or mutate derived state.
- Streaming partial tool output.

## 4. Registered Tools

Phase 5C registers only tools backed by existing services:

```text
search_vault(query, scope=None, limit=10, include_graph=False, include_cross_vault=False)
build_context_pack(goal, scope=None, max_tokens=None, limit=10, include_graph=False, include_cross_vault=False)
find_related(target, scope=None, depth=1, kinds=None)
get_decision_trace(decision_or_topic, scope=None)
check_index_status(scope=None)
```

Deferred tools:

```text
ask_vault(question, mode="evidence-first", scope=None)
summarize_project_memory(scope=None)
get_open_questions(scope=None)
get_recent_changes(since=None, scope=None)
explain_result(result_id)
```

Deferred tools are not listed in MCP until their backing application services
exist. Listing a tool before it can do useful work is worse for agents than
omitting it because it teaches the model an unusable path.

## 5. Tool DTOs

All tools share `McpScopeInput` from Phase 5A.

Search input:

```python
@dataclass(frozen=True)
class SearchVaultInput:
    query: str
    scope: McpScopeInput | None = None
    limit: int = 10
    include_graph: bool = False
    include_cross_vault: bool = False
```

Context input:

```python
@dataclass(frozen=True)
class BuildContextPackInput:
    goal: str
    scope: McpScopeInput | None = None
    max_tokens: int | None = None
    limit: int = 10
    include_graph: bool = False
    include_cross_vault: bool = False
```

Related input:

```python
@dataclass(frozen=True)
class FindRelatedInput:
    target: str
    scope: McpScopeInput | None = None
    depth: int = 1
    kinds: tuple[str, ...] | None = None
```

Decision trace input:

```python
@dataclass(frozen=True)
class DecisionTraceInput:
    decision_or_topic: str
    scope: McpScopeInput | None = None
```

Status input:

```python
@dataclass(frozen=True)
class CheckIndexStatusInput:
    scope: McpScopeInput | None = None
```

Validation rules:

- Required strings must be non-empty after trimming.
- `limit` must be positive and bounded by the existing service cap.
- `max_tokens` must follow Phase 4 context budget rules.
- `depth` must be positive and bounded; Phase 5C default is `1`.
- `include_cross_vault` requires explicit graph behavior and multi-vault scope.
- Unknown `kinds` values are invalid arguments.

## 6. Tool Output Policy

Each tool returns:

- `structuredContent`: canonical JSON-compatible response
- `content`: a text mirror containing compact JSON or short Markdown
- `isError`: true only for tool execution failures, not warning-backed
  degradation

Structured output rules:

- Use existing response DTOs where possible.
- Do not expose backend-native records.
- Include `vault_id` on every evidence-bearing item.
- Include `requested_scope` and `actual_scopes` when available.
- Include store revisions and backend use when available.
- Preserve top-level and item-level warnings.
- Include resource links for generated packs and graph entities when available.

Text mirror rules:

- It may be JSON text for machine consumption or Markdown for readability.
- It must not omit warnings that exist in structured output.
- It must not add facts that are absent from structured output.

## 7. Tool Flows

`search_vault`:

```text
SearchVaultInput
  -> McpScopeInput to QueryScope
  -> RetrievalService.search(...)
  -> structured SearchResponse
  -> optional resource links for evidence documents
```

`build_context_pack`:

```text
BuildContextPackInput
  -> ContextPackRequest
  -> ContextPackBuilder.build(...)
  -> ContextPack JSON
  -> ContextPackResourceCache.put(...)
  -> return pack JSON plus vault://context/packs/{pack_id}
```

`find_related`:

```text
FindRelatedInput
  -> graph scope validation
  -> GraphRetrievalService.related(...)
  -> evidence resolution through MetadataStore
  -> structured graph response plus graph entity resource links
```

`get_decision_trace`:

```text
DecisionTraceInput
  -> GraphRetrievalService.decision_trace(...)
  -> durable decision evidence preferred
  -> warnings for inferred, stale, missing, contested, or deprecated links
```

`check_index_status`:

```text
CheckIndexStatusInput
  -> resolve scope
  -> read metadata/vector/graph status
  -> structured health and freshness response
```

## 8. Prompt Templates

Phase 5C registers these prompts:

```text
generate_codex_brief(goal, scope=None)
prepare_implementation_context(goal, scope=None)
review_architecture_decision(topic, scope=None)
summarize_feature_history(topic, scope=None)
analyze_project_risk(topic_or_goal, scope=None)
prepare_wiki_update_context(topic, scope=None)
trace_decision_history(topic, scope=None)
```

Prompt rules:

- Prompts are user-controlled templates, not autonomous operations.
- Prompts must tell the agent to call the appropriate Vault Graph MCP tools
  instead of reading the whole Vault.
- Prompts must state that Vault Graph output is working context.
- Prompts must tell the agent not to edit Vault files through Vault Graph.
- Prompts must preserve evidence and warnings in the final answer.
- Prompts that suggest durable follow-up must route it back through Vault's
  source capture, validation, release gate, and Git workflow.

Example prompt skeleton:

```text
Use Vault Graph as read-only working context for: {goal}

1. Call build_context_pack with the provided scope.
2. Inspect warnings before using evidence.
3. Cite evidence refs from the context pack.
4. If durable knowledge should be added or changed, propose a Vault workflow
   follow-up. Do not publish through Vault Graph.
```

## 9. Security And Agent Ergonomics

- Tool names should be concrete and unsurprising.
- Tool descriptions must not contain hidden instructions that conflict with the
  user's prompt.
- Tool descriptions must state read-only behavior and scope defaults.
- Prompts must not ask agents to bypass warnings.
- Prompt and tool outputs must avoid local absolute paths unless they are
  already part of explicit configuration output.
- Tool calls must be bounded by `limit`, `max_tokens`, and graph depth.
- Expensive graph behavior is opt-in.

## 10. Tests Required Before Implementation

Phase 5C implementation must include tests for:

- registered tool list contains only service-backed tools.
- deferred tools are not listed.
- each tool input schema includes required fields, defaults, and bounds.
- invalid scope, invalid limit, invalid max tokens, and invalid cross-Vault graph
  combinations fail before opening graph dependencies.
- search tool delegates to `RetrievalService` and preserves warnings.
- context tool delegates to `ContextPackBuilder`, preserves JSON schema, and
  returns a context-pack resource link.
- related and decision-trace tools open graph services only when called.
- status tool reports metadata/vector/graph freshness without mutating state.
- all tool calls leave registered Vault file hashes unchanged.
- structured output and text mirror contain the same warnings.
- prompt templates include read-only, evidence-first, warning, and durable
  follow-up language.
- prompt templates reference only registered Phase 5C tools.

## 11. Handoff To Phase 6

Phase 6 may add `summarize_project_memory`, `get_open_questions`,
`get_recent_changes`, and richer `explain_result` only after memory and explorer
projection services exist. Phase 5C should leave clean extension points but no
listed tools without backing services.
