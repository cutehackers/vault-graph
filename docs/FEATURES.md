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

This matrix describes the intended product surface across phases. The Phase 2
slice table below defines when search-related surfaces become available. A
matrix entry can describe a future MCP or HTTP binding even when the current
phase exposes only the CLI.

| Feature | CLI | MCP Tool | MCP Resource | Output |
| --- | --- | --- | --- | --- |
| Initialize Vault Graph | `vg init --vault /path/to/vault` | - | - | Default Vault path and state setup |
| Register Vault | `vg vault add ID --path /path/to/vault`, `vg vault list` | - | - | Vault catalog entries |
| Index Vault | `vg index`, `vg index --vault-id ID`, `vg index --all-vaults`, `vg index --full`, `vg index --dry-run` | - | - | Index revision, change plan, warnings |
| Watch Vault | `vg watch` | - | - | Continuous index refresh |
| Check Status | `vg status` | `check_index_status()` | - | Vault IDs/paths, backend health, schema compatibility, freshness, warnings |
| Ask Vault | `vg ask "question"` | `ask_vault(question, mode="evidence-first", scope=None)` | - | Answer, evidence, inferred links, warnings |
| Search Vault | `vg search "query"` | `search_vault(query, scope=None, limit=10)` | document/page/source resources | Ranked evidence-linked results |
| Find Related Items | `vg related TARGET` | `find_related(target, scope=None, depth=1, kinds=None)` | `vault://{vault_id}/graph/entities/{id}` | Related entities, paths, evidence |
| Trace Decision | `vg decision-trace TOPIC` | `get_decision_trace(decision_or_topic, scope=None)` | `vault://{vault_id}/decisions/{id}` | Decision, context, alternatives, tradeoffs |
| Build Context Pack | `vg context "goal"` | `build_context_pack(goal, scope=None, max_tokens=None)` | `vault://context/packs/{id}` | JSON or Markdown agent brief |
| Summarize Project Memory | - | `summarize_project_memory(scope=None)` | `vault://{vault_id}/context/current` | Current state, recent decisions, open issues |
| Get Open Questions | - | `get_open_questions(scope=None)` | `vault://{vault_id}/issues/{id}` | Open questions and unresolved follow-ups |
| Get Recent Changes | - | `get_recent_changes(since=None, scope=None)` | `vault://{vault_id}/timeline/recent` | Recent durable and indexed changes |
| Explain Result | - | `explain_result(result_id)` | - | Retrieval reason, evidence, scores, warnings |
| Serve MCP | `vg serve --mcp` | - | all MCP resources | MCP server for agents |
| Serve HTTP | `vg serve --http` | - | - | HTTP access surface |

## Phase 2 User-Facing Slices

Phase 2 exposes search in slices. Phase 2A is internal contract readiness only.
User-facing vector status arrives in Phase 2B, and user-facing search arrives in
Phase 2C. This keeps the first visible search surface evidence-first and
explainable.

| Slice | Change | Explicitly Not Included |
| --- | --- | --- |
| Phase 2A | Internal retrieval and `VectorStore` contracts | user search, vector status output, graph traversal, answers |
| Phase 2B | `vg index` and `vg status` include Chroma-backed local vector projection state | user search, graph traversal, answers, context packs |
| Phase 2C | `vg search "query"` returns keyword/vector ranked evidence | graph traversal, `vg ask`, MCP serving |

Graph-based expansion joins search after Phase 3. Until then, hybrid retrieval
means keyword plus vector retrieval with graph-ready result fields and
per-signal explanations.

## CLI Features

### Initialize

```bash
vg init --vault /path/to/vault
vg init --vault-id main --vault /path/to/vault
vg vault add work --path /path/to/other-vault
vg vault list
```

Configures one or more Vault roots and the Vault Graph state location. If no
Vault ID is provided, `vg init --vault /path/to/vault` creates the active entry
with `vault_id: default`. Commands should be explicit about which Vault ID,
Vault path, and index state path they use.

Commands that support Vault selection use the active Vault by default.
`--vault-id ID` selects one Vault. `--all-vaults` expands to all enabled Vault
IDs and must make that selection visible in output.

### Index

```bash
vg index
vg index --vault-id main
vg index --all-vaults
vg index --full
vg index --dry-run
```

Builds or refreshes Vault-derived indexes.

User-visible behavior:

- detects changed, stale, and deleted files
- supports incremental and full rebuilds
- in Phase 2B, updates metadata first and then reconciles the local vector
  projection for the selected scope
- uses the active Vault by default
- supports `--vault-id ID` for one Vault and `--all-vaults` for all enabled
  Vaults
- reports index revision information
- in Phase 2B, reports vector upserts, tombstones, unchanged records, stale
  records, model spec, backend health, and recoverable vector failures
- in Phase 2B dry-run output, reports configured `embedding_batch_size`,
  parallelism, lazy loading, and planned embedding count without loading the
  model
- in Phase 2B, returns a nonzero exit if metadata succeeds but vector reconcile
  fails, while preserving the applied metadata revision in output and status
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
vg status --vault-id main
vg status --all-vaults
```

Reports operational status.

The status surface should show:

- configured Vault IDs and paths
- configured index state path
- backend health
- schema compatibility
- index revision freshness
- in Phase 2B, Chroma vector backend health, schema compatibility, active
  `EmbeddingModelSpec`, vector revision, stale count, status scope, and last
  vector failure
- in Phase 2B, default local embedding model, model revision, model cache
  availability, throughput tuning, and model-unavailable errors
- graph projection freshness
- stale or invalid cache warnings

By default, freshness fields use the active Vault. `--vault-id ID` reports one
Vault, and `--all-vaults` reports all enabled Vaults with explicit Vault IDs in
the output.

### Ask

```bash
vg ask "Why did we adopt GraphRAG?"
vg ask --vault-id main "Why did we adopt GraphRAG?"
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
vg related --vault-id main GraphRAG
```

Finds items related to a concept, project, decision, issue, system, workflow, or
other indexed entity.

Results should include evidence paths and distinguish stated relationships from
inferred, contested, deprecated, or stale relationships.

### Context

```bash
vg context "Implement GraphRAG MVP"
vg context --vault-id main "Implement GraphRAG MVP"
```

Builds a scoped context pack for a concrete task.

The output should be small enough for an agent to read directly and rich enough
to avoid a full Vault scan.

### Decision Trace

```bash
vg decision-trace GraphRAG
vg decision-trace --vault-id main GraphRAG
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
vault://{vault_id}/documents/{path}
vault://{vault_id}/pages/{path}
vault://{vault_id}/sources/{id}
vault://{vault_id}/concepts/{name}
vault://{vault_id}/decisions/{id}
vault://{vault_id}/issues/{id}
vault://{vault_id}/timeline/recent
vault://{vault_id}/context/current
vault://context/packs/{id}
vault://{vault_id}/graph/entities/{id}
```

Resource responses should include evidence metadata when relevant, such as Vault
ID, Vault path, wiki path, section or anchor, content hash, raw SHA-256,
retrieval reason, confidence, warning, vault revision, and index revision.
`vault://context/packs/{id}` is a generated artifact URI. The pack body records
the `QueryScope` used when it was created.

## MCP Tools

### `search_vault(query, scope=None, limit=10)`

Searches Vault-derived indexes and returns ranked, evidence-linked results.
The optional `scope` is a `QueryScope`; without it, search uses the active Vault
only. Cross-Vault retrieval must be explicit.

This is the future MCP binding over the same search service. Phase 2C exposes
the CLI command only; MCP serving remains a later phase.

The Phase 2C CLI surface is:

```bash
vg search "GraphRAG"
vg search --vault-id main "GraphRAG"
vg search --all-vaults "GraphRAG"
```

Phase 2C search combines keyword and vector candidates. Graph candidates,
decision-map expansion, and timeline-map expansion are later signals that must
use the same evidence-linked result contract.

Phase 2C's canonical result is an evidence chunk resolved through
`MetadataStore`. The categories below are rendering and grouping views over
chunk evidence, not separate retrieval identities.

Expected rendering groups:

- matching documents
- matching wiki pages
- matching sources
- matching chunks
- matching entities after graph indexing exists
- warnings for stale or missing evidence

Each normal result preserves `vault_id`, `document_id`, `chunk_id`, path,
section or anchor, retrieval signals, result warnings, and store revision
metadata. Query-wide degraded conditions, such as vector search unavailable,
appear as top-level warnings.

### `ask_vault(question, mode="evidence-first", scope=None)`

Answers a natural-language question with cited evidence.

The default mode should prefer inspectable evidence over fluent unsupported
synthesis. The optional `scope` is a `QueryScope`; without it, the active Vault
is used.

### `find_related(target, scope=None, depth=1, kinds=None)`

Finds related entities through graph traversal, wiki links, decision maps,
timeline maps, or hybrid retrieval.

The response should distinguish stated, inferred, contested, and deprecated
relationships. Cross-Vault traversal requires explicit `vault_ids` in
`QueryScope`.

### `get_decision_trace(decision_or_topic, scope=None)`

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
- `vaults`
- `backend`
- `store_revisions`
- `current_state`
- `relevant_pages`
- `relevant_sources`
- `decisions`
- `constraints`
- `open_questions`
- `warnings`
- `evidence`
- `generated_at`
- `vault_revisions`
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

### `get_recent_changes(since=None, scope=None)`

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
  "scope": {
    "vault_ids": ["main"],
    "content_scopes": ["wiki", "docs"],
    "include_cross_vault": false
  },
  "vaults": [
    {
      "vault_id": "main",
      "display_name": "Main Vault"
    }
  ],
  "vault_revisions": {
    "main": "git-sha-or-file-snapshot-id"
  },
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

- read-only access to Vault
- local-first operation without mandatory hosted services
- evidence-first responses
- clear separation between stated facts and inferred links
- visible warnings for stale, missing, contested, or deprecated material
- reproducible indexes that can be deleted and rebuilt from Vault
- Vault-scoped identity so registered Vaults with matching relative paths do not
  collide
- explicit backend health and index freshness status
- durable knowledge publication only through Vault
