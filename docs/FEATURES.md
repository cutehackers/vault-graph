# Vault Graph User-Facing Features

Status: Draft

This document lists the features and interfaces exposed to Vault Graph users. It
focuses on what a user or agent can invoke directly through CLI, MCP resources,
MCP tools, MCP prompts, and HTTP serving.

For architecture, storage contracts, indexing internals, and roadmap details,
see `docs/SPEC.md`.

## Product Boundary

Vault Graph is a read-only, rebuildable knowledge access layer over Vault.

It can:

- read Vault content
- build local indexes from Vault
- search and explain Vault-derived results
- generate evidence-linked context for humans and agents
- expose that context through CLI, MCP, and HTTP

It does not:

- publish durable wiki pages
- mutate raw sources
- edit Vault documents
- resolve contradictions automatically
- replace Vault as the source of truth

Any insight that should become durable knowledge must go back through Vault's
normal source capture, draft, validation, release gate, and Git history workflow.

## Feature Matrix

| Feature | CLI | MCP Tool | MCP Resource | Output |
| --- | --- | --- | --- | --- |
| Initialize Vault Graph | `vg init --vault /path/to/vault` | - | - | Vault path and state setup |
| Index Vault | `vg index`, `vg index --full`, `vg index --dry-run` | - | - | Index revision, change plan, warnings |
| Watch Vault | `vg watch` | - | - | Continuous index refresh |
| Check Status | `vg status` | `check_index_status()` | - | Backend health, index freshness, warnings |
| Ask Vault | `vg ask "question"` | `ask_vault(question, mode="evidence-first")` | - | Answer, evidence, inferred links, warnings |
| Search Vault | - | `search_vault(query, scope=None, limit=10)` | document/page/source resources | Ranked evidence-linked results |
| Find Related Items | `vg related TARGET` | `find_related(target, depth=1, kinds=None)` | `vault://graph/entities/{id}` | Related entities, paths, evidence |
| Trace Decision | `vg decision-trace TOPIC` | `get_decision_trace(decision_or_topic)` | `vault://decisions/{id}` | Decision, context, alternatives, tradeoffs |
| Build Context Pack | `vg context "goal"` | `build_context_pack(goal, scope=None, max_tokens=None)` | `vault://context/packs/{id}` | JSON or Markdown agent brief |
| Summarize Project Memory | - | `summarize_project_memory(scope=None)` | `vault://context/current` | Current state, recent decisions, open issues |
| Get Open Questions | - | `get_open_questions(scope=None)` | `vault://issues/{id}` | Open questions and unresolved follow-ups |
| Get Recent Changes | - | `get_recent_changes(since=None)` | `vault://timeline/recent` | Recent durable and indexed changes |
| Explain Result | - | `explain_result(result_id)` | - | Retrieval reason, evidence, scores, warnings |
| Serve MCP | `vg serve --mcp` | - | all MCP resources | MCP server for agents |
| Serve HTTP | `vg serve --http` | - | - | HTTP access surface |

## CLI Features

### Initialize

```bash
vg init --vault /path/to/vault
```

Configures the Vault path and the Vault Graph state location. Commands should be
explicit about which Vault path and index state path they use.

### Index

```bash
vg index
vg index --full
vg index --dry-run
```

Builds or refreshes Vault-derived indexes.

User-visible behavior:

- detects changed, stale, and deleted files
- supports incremental and full rebuilds
- reports index revision information
- reports warnings for source drift, duplicates, stale data, or missing evidence
- supports dry-run planning before index mutation

Indexing must not mutate Vault files.

### Watch

```bash
vg watch
```

Watches Vault for changes and keeps Vault Graph indexes fresh.

### Status

```bash
vg status
```

Reports operational status.

The status surface should show:

- configured Vault path
- configured index state path
- backend health
- schema compatibility
- index revision freshness
- graph projection freshness
- stale or invalid cache warnings

### Ask

```bash
vg ask "Why did we adopt GraphRAG?"
```

Asks a natural-language question against Vault-derived knowledge.

The answer should separate:

- answer
- evidence
- inferred links
- warnings
- suggested durable follow-up

### Related

```bash
vg related GraphRAG
```

Finds items related to a concept, project, decision, issue, system, workflow, or
other indexed entity.

Results should include evidence paths and distinguish stated relationships from
inferred, contested, deprecated, or stale relationships.

### Context

```bash
vg context "Implement GraphRAG MVP"
```

Builds a scoped context pack for a concrete task.

The output should be small enough for an agent to read directly and rich enough
to avoid a full Vault scan.

### Decision Trace

```bash
vg decision-trace GraphRAG
```

Explains a decision or topic through durable decision pages, related evidence,
source pages, concepts, tradeoffs, and revisit conditions.

### Serve

```bash
vg serve --mcp
vg serve --http
```

Starts a server interface for agents or custom clients.

## MCP Resources

Vault Graph exposes read-only MCP resources for documents, pages, generated
context, timeline data, and graph entities.

Initial resource URIs:

```text
vault://documents/{path}
vault://pages/{path}
vault://sources/{id}
vault://concepts/{name}
vault://decisions/{id}
vault://issues/{id}
vault://timeline/recent
vault://context/current
vault://context/packs/{id}
vault://graph/entities/{id}
```

Resource responses should include evidence metadata when relevant, such as Vault
path, wiki path, section or anchor, content hash, raw SHA-256, retrieval reason,
confidence, warning, vault revision, and index revision.

## MCP Tools

### `search_vault(query, scope=None, limit=10)`

Searches Vault-derived indexes and returns ranked, evidence-linked results.

Expected result categories:

- matching documents
- matching wiki pages
- matching sources
- matching chunks
- matching entities
- warnings for stale or missing evidence

### `ask_vault(question, mode="evidence-first")`

Answers a natural-language question with cited evidence.

The default mode should prefer inspectable evidence over fluent unsupported
synthesis.

### `find_related(target, depth=1, kinds=None)`

Finds related entities through graph traversal, wiki links, decision maps,
timeline maps, or hybrid retrieval.

The response should distinguish stated, inferred, contested, and deprecated
relationships.

### `get_decision_trace(decision_or_topic)`

Returns a decision trace for a decision ID, topic, or search phrase.

The response should include:

- decision
- context
- alternatives
- tradeoffs
- evidence
- related documents
- related follow-up questions
- revisit conditions

### `build_context_pack(goal, scope=None, max_tokens=None)`

Builds a structured brief for a human or agent.

Required fields:

- `goal`
- `scope`
- `current_state`
- `relevant_pages`
- `relevant_sources`
- `decisions`
- `constraints`
- `open_questions`
- `warnings`
- `evidence`
- `generated_at`
- `vault_revision`
- `index_revision`

### `summarize_project_memory(scope=None)`

Summarizes the current project memory projection.

The response should include:

- current goal
- recent decisions
- recent durable changes
- open issues
- next likely priorities
- evidence links
- warnings or stale areas

### `get_open_questions(scope=None)`

Returns unresolved questions, incomplete follow-ups, missing evidence warnings,
or items that should be revisited.

### `get_recent_changes(since=None)`

Returns recent changes from Vault-derived metadata and revision state.

The response should identify whether each item is a durable Vault change, an
indexed projection change, or a warning.

### `explain_result(result_id)`

Explains why a search, answer, context-pack item, or graph result was returned.

The explanation should include retrieval reason, evidence path, relationship
status, confidence, scores when available, and warnings.

### `check_index_status()`

Reports index and backend status for agents.

The response should include backend name, schema version, index revision,
freshness, projection cache status, and health warnings.

## MCP Prompts

Vault Graph provides prompts for repeatable agent workflows.

Initial prompts:

- `generate_codex_brief`
- `prepare_implementation_context`
- `review_architecture_decision`
- `summarize_feature_history`
- `analyze_project_risk`
- `prepare_wiki_update_context`
- `trace_decision_history`

Prompts must instruct agents to treat Vault Graph output as working context.
Durable publication still belongs to Vault's validation workflow.

## Context Pack Output

A context pack is a structured JSON or Markdown artifact generated from Vault
Graph retrieval.

Minimum JSON shape:

```json
{
  "goal": "Implement GraphRAG MVP",
  "scope": ["wiki", "docs"],
  "vault_revision": "git-sha-or-file-snapshot-id",
  "index_revision": "index-revision-id",
  "backend": {
    "metadata_store": "sqlite",
    "vector_store": "chroma",
    "graph_store": "sqlite",
    "graph_projection": "rustworkx"
  },
  "store_revisions": {
    "metadata": "metadata-revision-id",
    "vector": "vector-revision-id",
    "graph": "graph-revision-id",
    "projection": "projection-cache-or-build-id"
  },
  "generated_at": "2026-06-04T00:00:00+09:00",
  "current_state": [],
  "relevant_pages": [],
  "relevant_sources": [],
  "decisions": [],
  "constraints": [],
  "open_questions": [],
  "warnings": [],
  "evidence": []
}
```

## Optional UI Features

The optional UI can expose the same capabilities visually.

Planned views:

- Ask Project
- Decision Explorer
- Agent Workspace
- Timeline View

These views should not create a second source of truth. They should display
Vault-derived context, evidence, warnings, and durable follow-up suggestions.

## User-Visible Guarantees

Vault Graph should preserve these guarantees for every user-facing feature:

- read-only access to Vault by default
- local-first operation without mandatory hosted services
- evidence-first responses
- clear separation between stated facts and inferred links
- visible warnings for stale, missing, contested, or deprecated material
- reproducible indexes that can be deleted and rebuilt from Vault
- explicit backend health and index freshness status
- durable knowledge publication only through Vault
