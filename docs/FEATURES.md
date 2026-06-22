# Vault Graph User-Facing Features

Status: Draft

This document lists the features and interfaces exposed to Vault Graph users. It
focuses on what a user or agent can invoke directly through CLI, MCP resources,
MCP tools, MCP prompts, and HTTP serving.

For architecture, storage contracts, indexing internals, and roadmap details,
see `docs/SPEC.md`.

The feature matrix is the intended product surface across the full roadmap. The
phase slice sections below define what is in scope for each implementation
phase.

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
| Check Status | `vg status` | `check_index_status(scope=None)` | - | Vault IDs/paths, backend health, schema compatibility, freshness, warnings |
| Ask Vault | `vg ask "question"` | `ask_vault(question, mode="evidence-first", scope=None)` | - | Answer, evidence, inferred links, warnings |
| Search Vault | `vg search "query"` | `search_vault(query, scope=None, limit=10)` | document/page/source resources | Ranked evidence-linked results |
| Find Related Items | `vg related TARGET` | `find_related(target, scope=None, depth=1, kinds=None)` | `vault://{vault_id}/graph/entities/{id}` | Related entities, paths, evidence |
| Trace Decision | `vg decision-trace TOPIC` | `get_decision_trace(decision_or_topic, scope=None)` | `vault://{vault_id}/decisions/{id}` | Decision, context, alternatives, tradeoffs |
| Build Context Pack | `vg context "goal"` | `build_context_pack(goal, scope=None, max_tokens=None)` | `vault://context/packs/{id}` | JSON or Markdown agent brief |
| Summarize Project Memory | - | `summarize_project_memory(scope=None, limit=10)` | `vault://{vault_id}/context/current` | Current state, decision highlights, open issues |
| Get Open Questions | - | `get_open_questions(scope=None, limit=20)` | `vault://{vault_id}/issues/{id}` | Open questions and unresolved follow-ups |
| Get Recent Changes | - | `get_recent_changes(since=None, scope=None, limit=20)` | `vault://{vault_id}/timeline/recent` | Recent indexed document snapshot and projection changes |
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

## Phase 3 User-Facing Slices

Phase 3 exposes graph behavior in small, evidence-first slices. Graph records
remain derived projections over Vault metadata; graph commands must resolve
normal evidence through `MetadataStore` before rendering user-facing output.

| Slice | User-Facing Change | Explicitly Not Included |
| --- | --- | --- |
| Phase 3A | `vg status` can report graph backend readiness once graph contracts exist | graph traversal, graph ranking, decision traces |
| Phase 3B | `vg index` can reconcile local entity and relationship graph state for selected Vault scopes | LLM-required extraction, cross-Vault entity merging, context packs |
| Phase 3C | `vg related TARGET`, `vg decision-trace TOPIC`, and optional `vg search --include-graph` expose graph evidence and warnings | `vg ask`, MCP serving, HTTP serving, Neo4j |

Default `vg search "query"` stays keyword/vector evidence search until graph
relevance is proven through focused tests. Users must opt into graph expansion
with an explicit graph command or flag.

## Phase 4 User-Facing Slices

Phase 4 exposes context packs as bounded, evidence-linked working briefs.
Context packs are not answers and are not durable Vault knowledge.

| Slice | User-Facing Change | Explicitly Not Included |
| --- | --- | --- |
| Phase 4A | no new command; stabilizes the canonical JSON context pack contract and builder boundary | CLI context command, MCP serving, HTTP serving, pack persistence |
| Phase 4B | `vg context "goal"` returns JSON or Markdown context packs with evidence, revisions, and first-class warnings | `vg ask`, MCP serving, HTTP serving, automatic Vault publication |

Markdown context output is a rendering view over canonical JSON. Users must opt
into graph expansion with `--include-graph`; plain `vg context "goal"` uses
keyword/vector retrieval only.

## Phase 5 User-Facing Slices

Phase 5 exposes the existing Vault Graph services through MCP for local agents.
MCP is an adapter over the same evidence-first services used by CLI commands;
it does not add answer synthesis, memory projections, or Vault publication.

| Slice | User-Facing Change | Explicitly Not Included |
| --- | --- | --- |
| Phase 5A | `vg serve --mcp` starts a local stdio MCP server and provides Codex-compatible local configuration examples | Streamable HTTP, authentication, remote hosting, tools that synthesize answers |
| Phase 5B | MCP resource templates expose read-only indexed Vault documents, pages, sources, graph entities, current context availability, and generated context packs | resource subscriptions, durable context-pack persistence, full-Vault resource dumps |
| Phase 5C | MCP tools expose service-backed search, context-pack building, related entities, decision traces, and index status; prompts guide common agent workflows | `ask_vault`, Phase 6 memory tools, autonomous wiki updates, LLM clients |

Only service-backed tools are listed in Phase 5. Future roadmap tools such as
`ask_vault`, `summarize_project_memory`, `get_open_questions`,
`get_recent_changes`, and `explain_result` become MCP tools only after their
application services exist.

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
- in Phase 3B, reports graph entity upserts, relationship upserts, evidence
  reference upserts, tombstones, stale graph records, affected Vault IDs,
  `GraphExtractionSpec`, graph revision metadata, and projection cache
  invalidations
- in Phase 3B, returns a nonzero exit if metadata/vector work succeeds but graph
  reconcile fails, while preserving completed earlier projection state in output
  and status
- in Phase 3B, reports vector and graph indexing failures independently when
  both are enabled
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
- in Phase 3, graph backend health, graph schema compatibility,
  `GraphExtractionSpec`, graph revisions by Vault/actual scope, stale graph
  record counts, tombstone counts, last graph failure, and graph projection cache
  freshness
- stale or invalid vector/graph cache warnings

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
vg related --all-vaults GraphRAG
```

Finds items related to a concept, project, decision, issue, system, workflow, or
other indexed entity.

Results should include evidence paths and distinguish stated relationships from
inferred, contested, deprecated, or stale relationships.

### Context

```bash
vg context "Implement GraphRAG MVP"
vg context --vault-id main "Implement GraphRAG MVP"
vg context --all-vaults "Implement GraphRAG MVP"
vg context --include-graph "Implement GraphRAG MVP"
vg context --format json "Implement GraphRAG MVP"
vg context --format markdown "Implement GraphRAG MVP"
vg context --max-tokens 8000 "Implement GraphRAG MVP"
```

Builds a scoped context pack for a concrete task.

The output should be small enough for an agent to read directly and rich enough
to avoid a full Vault scan.

Phase 4 context behavior:

- JSON is the canonical artifact
- Markdown is a rendering view over the JSON artifact
- evidence chunks remain the authority unit
- stale, missing, contested, deprecated, truncated, and omitted material appears
  as warnings
- `--include-graph` is required for graph signals
- `--include-cross-vault` requires `--all-vaults --include-graph`
- graph backend and graph revision fields are not used by default context packs

### Decision Trace

```bash
vg decision-trace GraphRAG
vg decision-trace --vault-id main GraphRAG
vg decision-trace --all-vaults GraphRAG
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

The feature matrix lists the full roadmap. Phase 5 registers only tools backed
by existing application services. Tools that require answer synthesis or Phase 6
memory projections are deferred instead of being listed before they work.

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
- `context_pack_schema_version`
- `pack_id`
- `scope`
- `vaults`
- `vault_revisions`
- `backend`
- `store_revisions`
- `retrieval_policy_version`
- `budget`
- `current_state`
- `relevant_pages`
- `relevant_sources`
- `decisions`
- `constraints`
- `open_questions`
- `warnings`
- `evidence`
- `generated_at`

### `summarize_project_memory(scope=None, limit=10)`

Summarizes the current project memory projection.

The response should include:

- current goal
- decision highlights with evidence
- recent-change handoff to `get_recent_changes` when Phase 6C is available
- open issues
- next likely priorities
- evidence links
- warnings or stale areas

### `get_open_questions(scope=None, limit=20)`

Returns unresolved questions, incomplete follow-ups, missing evidence warnings,
or items that should be revisited.

### `get_recent_changes(since=None, scope=None, limit=20)`

Returns recent indexed document snapshot and projection changes from
Vault-derived metadata and revision state.

The response should identify whether each item is an indexed document snapshot
change, an indexed projection change, or a warning. `limit` defaults to `20`,
is validated as `1..50`, and applies per Vault group.

### `explain_result(result_id)`

Explains why a search, answer, context-pack item, or graph result was returned.

The explanation should include retrieval reason, evidence path, relationship
status, confidence, scores when available, and warnings.

### `check_index_status(scope=None)`

Reports index and backend status for agents. `scope=None` uses the active
Vault; explicit scope selects one or more Vaults.

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

A context pack is a structured artifact generated from Vault Graph retrieval.
JSON is canonical. Markdown is a rendering view over the same JSON payload.

Minimum JSON shape:

```json
{
  "context_pack_schema_version": "context-pack-v1",
  "pack_id": "sha256-of-canonical-pack-identity",
  "goal": "Implement GraphRAG MVP",
  "scope": {
    "requested": {
      "vault_ids": ["main"],
      "content_scopes": ["wiki", "docs"],
      "include_cross_vault": false
    },
    "actual_scopes": [
      {
        "vault_ids": ["main"],
        "content_scopes": ["wiki", "docs"],
        "include_cross_vault": false,
        "scope_key": "main:wiki,docs:local"
      }
    ]
  },
  "vaults": [
    {
      "vault_id": "main",
      "display_name": "Main Vault"
    }
  ],
  "vault_revisions": [
    {
      "vault_id": "main",
      "revision": "git-sha-or-file-snapshot-id",
      "revision_kind": "git"
    }
  ],
  "backend": {
    "metadata_store": {
      "name": "sqlite",
      "used": true
    },
    "keyword_index": {
      "name": "sqlite-fts5",
      "used": true
    },
    "vector_store": {
      "name": "chroma",
      "used": true
    },
    "graph_store": {
      "name": null,
      "used": false
    },
    "graph_projection": {
      "name": null,
      "used": false
    }
  },
  "retrieval_policy_version": "retrieval-policy-v1",
  "budget": {
    "max_tokens": 8000,
    "max_evidence_items": 24,
    "max_excerpt_tokens": 320,
    "used_tokens": 0,
    "omitted_items": 0
  },
  "store_revisions": [
    {
      "kind": "metadata",
      "revision": "metadata-revision-id",
      "vault_id": "main",
      "scope_key": "main:wiki,docs:local"
    },
    {
      "kind": "keyword",
      "revision": "keyword-revision-id",
      "vault_id": "main",
      "scope_key": "main:wiki,docs:local"
    },
    {
      "kind": "vector",
      "revision": "vector-revision-id",
      "vault_id": "main",
      "scope_key": "main:wiki,docs:local"
    }
  ],
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
