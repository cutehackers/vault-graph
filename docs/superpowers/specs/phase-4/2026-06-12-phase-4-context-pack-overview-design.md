# Phase 4 Context Pack Builder Overview Design

Status: Draft for implementation planning

Date: 2026-06-12

Scope: Phase 4 cross-slice overview

## 1. Purpose

Phase 4 turns evidence-first retrieval into a bounded context pack that a human
or agent can use for a concrete task without reading an entire Vault.

The deliverable is not answer generation, MCP serving, HTTP serving, durable
Vault publication, or a new knowledge store. The deliverable is a canonical
JSON context pack contract plus a Markdown rendering view over that same JSON.

Context packs remain working context. If a pack contains an insight that should
become durable knowledge, that insight must go back through Vault's normal
source capture, validation, release gate, and Git history workflow.

## 2. Document Map

| Document | Role |
| --- | --- |
| `README.md` | Phase 4 design folder index and reading order |
| `2026-06-12-phase-4-context-pack-overview-design.md` | Cross-slice overview, decisions, invariants, and implementation handoff map |
| `2026-06-12-phase-4a-context-pack-contract-builder-boundary-design.md` | Phase 4A JSON contract, builder boundary, data models, warnings, and budget policy |
| `2026-06-12-phase-4b-local-context-pack-assembly-rendering-design.md` | Phase 4B local assembly, CLI surface, Markdown rendering, and verification plan |

`docs/SPEC.md` remains the top-level product contract. This folder is the
implementation-design layer for Phase 4.

## 3. Phase Slices

| Slice | Change | User Value | Explicitly Not Included |
| --- | --- | --- | --- |
| Phase 4A | Define `ContextPack` JSON contract, `ContextPackBuilder` boundary, warning model, budget policy, and renderer boundary | future CLI/MCP/HTTP surfaces share one stable pack schema | CLI command, Markdown output, persistence, LLM answer synthesis |
| Phase 4B | Add local pack assembly through existing retrieval services plus Markdown rendering view | `vg context "goal"` can return a bounded evidence-linked brief | MCP serving, HTTP serving, durable pack store, automatic Vault publication |

Two slices are enough for Phase 4. A separate persistence slice would add
complexity before MCP resources exist. Phase 5 may add a rebuildable generated
artifact resource over the Phase 4 contract.

## 4. Accepted Phase 4 Decisions

- Canonical format is JSON. Markdown is a rendering view generated from the JSON
  contract and must not add facts or hide warnings.
- The evidence chunk remains the authority unit:
  `(vault_id, document_id, chunk_id)`.
- Warnings are first-class top-level and item-level records. Stale, missing,
  contested, deprecated, truncated, and omitted material must remain visible.
- Public `max_tokens` means an estimated context budget for excerpt-bearing
  content, not a model-specific tokenizer guarantee.
- Default context budget is 8,000 estimated tokens, with at most 24 evidence
  items and at most 320 excerpt tokens per item in Phase 4.
- Graph signals are opt-in for context packs. `vg context "goal"` uses
  keyword/vector retrieval by default; `--include-graph` explicitly adds graph
  signals and graph warnings.
- Cross-Vault graph expansion remains opt-in and requires both all-Vault scope
  and `--include-cross-vault`.

## 5. Cross-Slice Invariants

- Vault remains the durable source of truth.
- Context packs are derived, disposable, and rebuildable.
- `ContextPackBuilder` reads through application services and store interfaces;
  it must not query local SQLite, Chroma, or rustworkx adapters directly.
- User-visible context pack evidence resolves through `MetadataStore`.
- Stored excerpts are rendering content, not evidence authority.
- Pack output must preserve `QueryScope`, selected Vault IDs, actual scopes,
  store revisions, backend names, generated timestamp, and schema version.
- Multi-vault identity is explicit. Evidence, warnings, source groups, and
  revisions carry Vault IDs where collision is possible.
- Context packing must be deterministic for the same goal, scope, retrieval
  policy, store revisions, budget, and retrieval results. `generated_at`
  records emission time and is excluded from `pack_id`.
- Pack renderers must never suppress warnings to make output look cleaner.

## 6. Responsibility Map

| Component | Owns | Must Not Own |
| --- | --- | --- |
| `VaultCatalog` | registered Vault IDs, active Vault, enabled Vault expansion | pack ranking, evidence synthesis |
| `QueryScope` | selected Vault IDs, content scopes, cross-Vault flag | implicit scope widening |
| `RetrievalService` | keyword/vector retrieval, optional graph candidate fusion, result warnings | pack schema, Markdown rendering |
| `GraphRetrievalService` | graph evidence only when explicitly requested | default context expansion |
| `MetadataStore` | evidence chunk authority and resolved document/chunk metadata | pack ranking policy |
| `ContextPackBuilder` | goal normalization, retrieval orchestration, grouping, budgets, warnings, JSON DTO assembly | direct backend queries, durable publication, answer generation |
| `ContextPackRenderer` | JSON serialization and Markdown rendering view | changing selected evidence or hiding warnings |
| CLI | argument parsing and output format selection | direct store access, context synthesis outside builder |

## 7. Data Flow Summary

Phase 4A contract flow:

```text
ContextPackRequest
  -> QueryScope normalization
  -> ContextPackBudget validation
  -> ContextPackBuilder contract
  -> ContextPack JSON DTO
```

Phase 4B local assembly flow:

```text
vg context GOAL
  -> resolve selected Vault scope
  -> RetrievalService.search(goal)
  -> optional graph retrieval signal when --include-graph is set
  -> MetadataStore evidence resolution through retrieval response
  -> classify evidence into pages, sources, decisions, constraints, questions
  -> deterministic budget packing
  -> ContextPack JSON
  -> optional Markdown rendering view
```

## 8. Error And Degradation Policy

- Invalid scope, unsupported output format, invalid budget, and missing required
  metadata state are fatal command errors.
- Vector backend unavailability follows existing search degradation behavior
  when keyword retrieval can still return evidence.
- Graph unavailability is a warning when graph was explicitly requested and
  keyword/vector evidence can still produce a pack.
- Missing evidence references remove the affected item from normal sections and
  add a warning with the unresolved reference.
- Budget omission and excerpt truncation are warnings, not silent behavior.
- Contested or deprecated graph relationships remain visible as warnings and
  status labels. Phase 4 must not resolve contradictions.

## 9. Multi-Vault Policy

- Default context packs use the active Vault only.
- `--vault-id ID` uses exactly one registered Vault.
- `--all-vaults` expands to explicit enabled Vault IDs and records actual
  scopes in the pack.
- Cross-Vault graph relationships require `--all-vaults --include-graph
  --include-cross-vault`.
- Identical paths, titles, chunk IDs, warning codes, or graph entity names from
  different Vaults must not collide because each pack item carries `vault_id`.

## 10. Handoff

Phase 4 implementation planning should proceed in this order:

1. Phase 4A: context pack DTOs, JSON schema contract tests, warning model,
   budget policy, builder interface, and renderer boundary.
2. Phase 4B: local builder implementation, `vg context`, JSON output,
   Markdown rendering, budget/truncation tests, read-only tests, and multi-vault
   warning attribution tests.

Each slice should preserve the rule that Vault Graph writes only derived state
and never edits Vault content.
