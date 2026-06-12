# Phase 4B Local Context Pack Assembly And Rendering Design

Status: Draft for implementation planning

Date: 2026-06-12

Scope: Phase 4B only

## 1. Purpose

Phase 4B exposes the Phase 4A context pack contract through a local CLI command
and Markdown rendering view.

The goal is that a user can run:

```bash
vg context "Implement GraphRAG MVP"
vg context "Implement GraphRAG MVP" --format json
vg context "Implement GraphRAG MVP" --format markdown
vg context "Implement GraphRAG MVP" --include-graph
```

and receive a bounded, evidence-linked context pack without mutating Vault.

Phase 4B implements:

- `vg context GOAL`
- JSON output using `ContextPack` as the canonical artifact
- Markdown rendering generated from the JSON payload
- `--max-tokens`
- `--vault-id`, `--all-vaults`, `--include-graph`, and
  `--include-cross-vault` scope flags
- warnings for stale, missing, contested, deprecated, truncated, and omitted
  material
- read-only and multi-vault tests

Phase 4B must not implement:

- `vg ask`
- MCP serving
- HTTP serving
- durable context pack persistence
- automatic Vault publication
- LLM-generated summaries or answers

## 2. CLI Surface

Command:

```bash
vg context GOAL
```

Options:

```text
--state PATH
--vault-id ID
--all-vaults
--format json|markdown
--max-tokens N
--limit N
--include-graph
--include-cross-vault
```

Defaults:

- `--format markdown` for human CLI readability
- `--max-tokens 8000`
- `--limit 10` retrieval results before pack classification
- active Vault scope
- graph disabled
- cross-Vault graph disabled

Validation:

- `--vault-id` and `--all-vaults` are mutually exclusive.
- `--include-cross-vault` requires `--all-vaults --include-graph`.
- `--max-tokens` must be positive and at least 1000.
- unsupported formats return `unsupported_format`.

Even though Markdown is the default CLI view, JSON remains the canonical
artifact. Tests should assert the JSON contract first.

## 3. Assembly Flow

```text
vg context GOAL
  -> validate CLI options
  -> load VaultCatalog
  -> resolve QueryScope
  -> create ContextPackRequest
  -> ContextPackBuilder.build(request)
     -> RetrievalService.search(goal, limit=request.retrieval_limit, include_graph=request.include_graph)
     -> preserve SearchResponse warnings
     -> classify SearchResponse results
     -> create ContextEvidence entries
     -> apply deterministic budget packing
     -> compute pack_id from canonical identity JSON without pack_id or generated_at
  -> render JSON or Markdown
```

The CLI should not classify results, truncate excerpts, or rewrite warnings.
Those responsibilities belong to `ContextPackBuilder`.

## 4. Classification Rules

Phase 4B uses deterministic, local rules.

| Section | Rule |
| --- | --- |
| `decisions` | path contains `/decisions/` or graph entity type is `Decision` |
| `constraints` | heading or path includes `constraint`, `principle`, `invariant`, `policy`, or `convention` |
| `open_questions` | heading or path includes `question`, `todo`, `follow-up`, `issue`, or `revisit` |
| `relevant_pages` | `wiki/` or `docs/` evidence not classified above |
| `relevant_sources` | `raw/` or source-like evidence |
| `current_state` | evidence-backed status-like Vault content selected by retrieval |

Classification must be conservative. If a result cannot be confidently
classified, put it in `relevant_pages` or `relevant_sources` rather than
inventing a stronger meaning.

Store freshness summaries are not evidence chunks. They belong in warnings,
backend metadata, vault revisions, or store revisions, not normal
`current_state` items.

Phase 4B does not run an LLM classifier.

## 5. Evidence Grouping

Evidence grouping deduplicates by:

```text
(vault_id, document_id, chunk_id)
```

If multiple retrieval results point to the same evidence chunk, the pack keeps
one top-level `ContextEvidence` entry and merges retrieval reasons:

```text
keyword
vector
graph
```

Section items may share evidence refs. Shared evidence does not duplicate
excerpt tokens in budget accounting.

## 6. Ranking And Packing

Phase 4B consumes the ranking produced by `RetrievalService`. It does not
compare keyword, vector, and graph backend scores directly.

Packing order inside each section:

1. lower retrieval rank
2. more signal kinds
3. durable page path before raw source path
4. lexical `(vault_id, path, chunk_id)` tie-break

Section priority follows Phase 4A:

1. warnings and recovery hints
2. decisions
3. constraints
4. open questions
5. current state
6. relevant pages
7. relevant sources
8. optional graph-related evidence

When the budget is exhausted, omitted items produce `budget_omitted` warnings.

## 7. Markdown Rendering

Markdown output is a view over JSON.

Required Markdown sections:

```markdown
# Context Pack

## Goal
## Scope
## Warnings
## Decisions
## Constraints
## Open Questions
## Current State
## Relevant Pages
## Relevant Sources
## Evidence
## Revisions
```

Rendering rules:

- Always render `Warnings`, even when empty.
- Evidence lines include `[vault_id] path#anchor` when anchor exists.
- Warnings include code, severity, affected Vault IDs, and recovery hint.
- Truncated excerpts include a visible `[truncated]` marker.
- Omitted sections include a visible warning, not just a missing heading.
- Markdown must not include any fact absent from JSON.

## 8. Read-Only Boundary

`vg context` may read:

- catalog config
- metadata store
- keyword projection
- vector projection
- graph store only when `--include-graph` is set

`vg context` must not write:

- registered Vault files
- metadata/vector/graph stores
- projection cache
- context pack cache
- embedding model cache

Phase 4B should open stores read-only. If required projections are missing, the
command should fail or degrade through warnings according to the Phase 4A error
policy.

## 9. Multi-Vault Behavior

Default:

```bash
vg context "goal"
```

uses the active Vault only.

Single Vault:

```bash
vg context --vault-id work "goal"
```

uses exactly that Vault.

All Vaults:

```bash
vg context --all-vaults "goal"
```

uses all enabled Vaults and records each Vault in `scope.requested.vault_ids`,
`scope.actual_scopes`, `vaults`, warnings, evidence refs, and store revisions.

Cross-Vault graph:

```bash
vg context --all-vaults --include-graph --include-cross-vault "goal"
```

is the only Phase 4B mode that may include cross-Vault graph relationships.

## 10. Error Handling

Fatal CLI errors:

| Code | Condition |
| --- | --- |
| `empty_goal` | goal is blank |
| `unsupported_format` | output format is not `json` or `markdown` |
| `context_budget_too_small` | `--max-tokens` is below 1000 |
| `invalid_scope` | selected Vault ID is missing or mutually exclusive flags are used |
| `metadata_unavailable` | metadata projection is required and unavailable |

Non-fatal warnings:

| Code | Condition |
| --- | --- |
| `search_degraded` | retrieval ran with missing vector support or stale projections |
| `graph_unavailable` | graph was requested but cannot be used |
| `missing_evidence` | an item cannot resolve its evidence chunk |
| `stale_projection` | source projection is stale |
| `contested_relationship` | graph status is contested |
| `deprecated_relationship` | graph status is deprecated |
| `budget_omitted` | item omitted due to budget |
| `excerpt_truncated` | excerpt shortened due to budget |

## 11. Tests Required Before Implementation

Phase 4B implementation must include tests for:

- `vg context --format json` returns the Phase 4A JSON contract.
- `vg context --format markdown` renders from JSON and includes warnings.
- `--limit` is passed into `ContextPackRequest.retrieval_limit`.
- plain `vg context` does not open graph retrieval state.
- `--include-graph` opens graph retrieval read-only and preserves graph
  warnings.
- `--include-cross-vault` is rejected without `--all-vaults --include-graph`.
- budget truncation and omission are deterministic and warning-backed.
- missing metadata exits nonzero without creating metadata/vector/graph/cache
  files.
- multi-vault packs preserve Vault IDs on evidence, warnings, and revisions.
- read-only boundary tests prove no registered Vault files are changed.
- import boundary tests prove context pack code depends on interfaces, not
  local backend adapters.

## 12. Handoff To Phase 5

Phase 5 MCP should expose `build_context_pack(goal, scope=None,
max_tokens=None)` over the Phase 4 JSON contract. It may add generated resource
URIs such as `vault://context/packs/{id}`, but it should not change the
canonical pack schema without bumping `context_pack_schema_version`.
