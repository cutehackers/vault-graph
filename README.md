# Vault Graph

Status: Draft

Vault Graph is a read-only, rebuildable knowledge access layer over Vault.

It helps humans and agents search Vault, trace decisions, inspect project
memory, and build task-specific context packs without turning retrieval output
into durable knowledge.

Vault remains the source of truth. Vault Graph reads, indexes, retrieves, and
explains Vault-derived context. It does not publish wiki pages, mutate raw
sources, edit Vault documents, or replace Vault's validation workflow.

## User Interfaces

Vault Graph is designed to expose three user-facing interfaces:

- CLI for local commands and direct human use
- MCP for Codex, Claude, Cursor, OpenCode, and custom agents
- HTTP for custom clients and optional UI surfaces

For the full user-facing feature catalog, see
[`docs/FEATURES.md`](docs/FEATURES.md).

For architecture and storage contracts, see [`docs/SPEC.md`](docs/SPEC.md).
For the Phase 2 search slices, see the roadmap in [`docs/SPEC.md`](docs/SPEC.md)
and the user-facing slice table in [`docs/FEATURES.md`](docs/FEATURES.md).

## Interface Preview

This section previews the intended product interface across phases. Phase 2A is
internal contract work only; vector status appears in Phase 2B and `vg search`
appears in Phase 2C.

### Initialize

```bash
vg init --vault /path/to/vault
vg init --vault-id main --vault /path/to/vault
vg vault add work --path /path/to/other-vault
vg vault list
```

Configure one or more Vault roots and the Vault Graph state location. If no
Vault ID is provided, `vg init --vault /path/to/vault` creates the active entry
with `vault_id: default`.

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

Build or refresh Vault-derived projections as each phase is implemented:
metadata first, then vector search, then graph records. The dry-run mode shows
the planned indexing changes before mutation of Vault Graph state. Indexing
must not mutate Vault files.

### Watch

```bash
vg watch
```

Watch Vault changes and keep indexes fresh.

### Status

```bash
vg status
```

Show configured Vault IDs and paths, backend health, schema compatibility, index
freshness, projection freshness, and warnings.

### Search

```bash
vg search "GraphRAG"
vg search --vault-id main "GraphRAG"
vg search --all-vaults "GraphRAG"
```

Search returns ranked, evidence-linked results. Phase 2 search starts with
keyword and vector signals; graph signals are added after graph indexing exists.

### Ask

```bash
vg ask "Why did we adopt GraphRAG?"
vg ask --vault-id main "Why did we adopt GraphRAG?"
```

Ask an evidence-first question against Vault-derived context. Answers should
separate evidence, inferred links, warnings, and suggested durable follow-up.

### Find Related Context

```bash
vg related GraphRAG
vg related --vault-id main GraphRAG
```

Find documents, decisions, concepts, issues, systems, workflows, and entities
related to a target topic.

### Build A Context Pack

```bash
vg context "Implement GraphRAG MVP"
vg context --vault-id main "Implement GraphRAG MVP"
```

Generate a scoped JSON or Markdown brief for a human or agent. Context packs are
working context, not durable knowledge.

### Trace A Decision

```bash
vg decision-trace GraphRAG
vg decision-trace --vault-id main GraphRAG
```

Trace a decision or topic through durable decisions, related evidence, source
pages, concepts, tradeoffs, and revisit conditions.

### Serve

```bash
vg serve --mcp
vg serve --http
```

Expose Vault Graph through MCP or HTTP.

## MCP Surface

Initial MCP tools:

- `search_vault(query, scope=None, limit=10)`
- `ask_vault(question, mode="evidence-first", scope=None)`
- `find_related(target, scope=None, depth=1, kinds=None)`
- `get_decision_trace(decision_or_topic, scope=None)`
- `build_context_pack(goal, scope=None, max_tokens=None)`
- `summarize_project_memory(scope=None)`
- `get_open_questions(scope=None)`
- `get_recent_changes(since=None, scope=None)`
- `explain_result(result_id)`
- `check_index_status()`

Initial MCP resources:

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

`vault://context/packs/{id}` is a generated artifact URI. The pack body records
the `QueryScope` used when it was created.

Initial MCP prompts:

- `generate_codex_brief`
- `prepare_implementation_context`
- `review_architecture_decision`
- `summarize_feature_history`
- `analyze_project_risk`
- `prepare_wiki_update_context`
- `trace_decision_history`

## Guarantees

Vault Graph user-facing features should preserve these guarantees:

- read-only access to Vault
- local-first operation without mandatory hosted services
- evidence-first answers
- clear separation between stated facts and inferred links
- warnings for stale, missing, contested, or deprecated material
- reproducible indexes that can be deleted and rebuilt from Vault
- Vault-scoped identity for multiple registered Vault roots
- visible backend health and index freshness status
- durable knowledge publication only through Vault

## Documentation

- [`docs/FEATURES.md`](docs/FEATURES.md): user-facing features and interfaces
- [`docs/SPEC.md`](docs/SPEC.md): product specification, architecture, storage
  contracts, indexing rules, and roadmap
