# Phase 6 Memory And Explorer Views Overview Design

Status: Draft for implementation planning

Date: 2026-06-18

Scope: Phase 6 cross-slice overview

## 1. Purpose

Phase 6 turns Vault Graph's existing retrieval, graph, context-pack, MCP, and
status services into memory and explorer projections. The goal is to help users
and agents answer operational questions such as:

- What is the current state of this project?
- Which decisions matter for this task?
- What open questions or follow-ups remain unresolved?
- What changed recently?
- Why was this result returned?
- Which backend or projection is stale, unavailable, or not scale-up-ready?

The deliverable is not answer generation, not a UI, not hosted monitoring, not
remote backend migration, and not a new memory database. The deliverable is a
set of read-only application services plus MCP resources/tools that expose
bounded, evidence-linked projections over existing Vault-derived state.

External memory-layer projects such as Mem0 and MemMachine are useful reference
points, but Phase 6 does not follow their writable persistent-memory model.
Vault Graph uses memory terminology for read-only projections. It must not add
a generic writable memory API, hidden episode log, profile memory database, or
external memory server dependency.

All Phase 6 output remains working context. If a memory projection contains an
insight that should become durable knowledge, that insight must go through
Vault's normal source capture, validation, release gate, and Git history
workflow.

## 2. Document Map

| Document | Role |
| --- | --- |
| `README.md` | Phase 6 design folder index and reading order |
| `2026-06-18-phase-6-memory-and-explorer-views-overview-design.md` | Cross-slice overview, invariants, and handoff map |
| `2026-06-18-phase-6a-result-explanation-contract-design.md` | Result explanation contract, bounded MCP explanation cache, and `explain_result` service boundary |
| `2026-06-18-phase-6b-project-decision-issue-memory-design.md` | Project, decision, and issue memory projections |
| `2026-06-18-phase-6c-timeline-health-explorer-design.md` | Timeline, projection freshness, backend health, and scale-up readiness views |

`docs/SPEC.md` remains the top-level product contract. This folder is the
implementation-design layer for Phase 6.

## 3. Phase Slices

| Slice | Change | User Value | Explicitly Not Included |
| --- | --- | --- | --- |
| Phase 6A | Add result explanation records and a bounded MCP explanation cache | agents can call `explain_result` for results returned in the current MCP session | durable result history, answer synthesis, project memory summaries |
| Phase 6B | Add deterministic project, decision, and issue memory projections | agents can ask for current project state and open questions without whole-Vault scans | LLM-written summaries, automatic Vault publication, autonomous issue resolution |
| Phase 6C | Add recent timeline, freshness, backend health, and scale-up readiness explorer views | users and agents can see what changed and whether projections are trustworthy | hosted monitoring, remote backend migration, UI dashboards |

This slice order keeps Phase 6 simple: first make existing results explainable,
then assemble memory projections, then expose recent-change and operations
explorer views.

## 4. Cross-Slice Invariants

- Vault remains the durable source of truth.
- Memory projections are derived, read-only, disposable, and rebuildable.
- Evidence chunks remain the authority unit:
  `(vault_id, document_id, chunk_id)`.
- Memory output must preserve Vault IDs, evidence references, warnings, store
  revisions, generated timestamps, and freshness status.
- A memory item without resolved evidence is a warning, not a hidden fact.
- MCP tools are adapters over application services. They must not query SQLite,
  Chroma, rustworkx, or Vault files directly when a service boundary exists.
- MCP resources and tools must not write, rename, rewrite, delete, or publish
  Vault content.
- Default scope is the active Vault. Cross-Vault output requires explicit Vault
  IDs or explicit all-Vault selection.
- Cross-Vault memory projection groups evidence by Vault ID. It must not merge
  decisions, issues, entities, or documents from different Vaults by title or
  name alone.
- Missing, stale, unavailable, or incompatible projection state must remain
  visible through structured warnings and safe next commands.
- Phase 6 must not expose generic `Memory.create`, `Memory.query`,
  `Memory.upsert`, `Memory.link`, `Memory.audit`, or `MemoryStore` contracts.
  Use specific read services such as `ExplainResultService`,
  `ProjectMemoryService`, `DecisionMemoryService`, `IssueMemoryService`, and
  `TimelineMemoryService`.

## 5. Responsibility Map

| Component | Owns | Must Not Own |
| --- | --- | --- |
| `MetadataStore` | document/chunk evidence authority, frontmatter, content hashes, revisions | memory grouping policy, answer prose |
| `RetrievalService` | ranked evidence and signal explanations | project memory assembly |
| `GraphRetrievalService` | related entities and decision traces | durable decision authority |
| `ContextPackBuilder` | bounded task context assembly | current project memory summary |
| `IndexService.status(...)` | backend health and projection freshness inputs | MCP serialization policy |
| `vault_graph.memory` | project, decision, issue, timeline, and explanation projection services | direct backend mutation, Vault publication, generic writable memory storage |
| `vault_graph.mcp` | MCP argument DTOs, cache ownership, tool/resource registration, error mapping | memory algorithms or evidence selection |

## 6. Shared Data Flow

Phase 6 services read through existing application services and storage
interfaces:

```text
MCP tool/resource or future CLI surface
  -> resolve QueryScope
  -> open read-only application service
  -> assemble projection from MetadataStore, RetrievalService, GraphRetrievalService, or IndexService
  -> resolve evidence through MetadataStore
  -> return structured JSON with warnings, revisions, and resource links
```

No Phase 6 service should run indexing as a side effect. If state is missing,
the response should tell the caller to run `vg index` or `vg status`.

## 7. Memory Taxonomy And External Layer Boundary

Phase 6 adopts useful memory-layer taxonomy without adopting a new memory store:

- Working memory maps to bounded runtime caches such as
  `ResultExplanationCache` and generated context-pack resource caches. It is
  current-process state and can disappear at any time.
- Semantic or project memory maps to Phase 6B deterministic projections over
  `MetadataStore`, retrieval signals, graph traces, frontmatter, paths, and
  headings. It is regenerated from Vault-derived indexes.
- Episodic or timeline memory maps to Phase 6C timeline projections over
  indexed document snapshot changes and derived projection changes. It is not a
  hidden transcript, raw session log store, or durable business-event ledger.
- Profile and preference memory are out of scope for Vault Graph core. If they
  become useful, they should live either as durable Vault notes or in an
  explicitly configured external adapter.
- Procedural memory is out of scope until prompt and workflow policy are
  explicitly designed.

Future Mem0, MemMachine, or MCP memory-server integration should be an adapter
or export target over evidence-linked projections. Such adapters may consume
projection output, but they must not replace Vault, mutate Vault Graph stores,
or feed agent-generated memory back as fact without the normal Vault workflow.

## 8. Result Explanation Position

`explain_result(result_id)` cannot depend on a durable result-history database in
Phase 6. Search result IDs currently include rank and are useful inside one
response, but they are not durable product memory.

Phase 6A therefore introduces explanation records and a bounded in-process MCP
explanation cache:

- search, context-pack, related, and decision-trace tools can register
  explanation records when returning results;
- `explain_result(result_id)` resolves only records from the current MCP
  process;
- if the server restarted or the cache evicted the record, the tool returns a
  not-found error with guidance to rerun the original query;
- no explanation record becomes durable Vault knowledge.

This mirrors the existing generated context-pack resource cache policy.

## 9. Memory Projection Position

Phase 6B memory is deterministic. It may classify indexed documents by path,
frontmatter, headings, graph entity type, and existing retrieval signals, but it
must not invent missing project state.

The initial project memory projection should return structured groups:

- current state
- decision highlights with evidence
- open questions and follow-ups
- constraints
- next likely priorities
- warnings and stale areas
- evidence links

Timeline-based recent indexed document snapshot changes belong to Phase 6C.

If a group has no evidence, the group is empty and a warning explains the gap.

## 10. Timeline And Health Position

Phase 6C timeline output combines indexed document snapshot changes and derived
projection changes. Each timeline item must label its origin:

- `document_snapshot_change`
- `index_change`
- `projection_change`
- `warning`

Backend health and scale-up readiness views reuse existing status fields and add
adapter readiness records. They report whether local and future scale-up
backends can satisfy the same logical contracts; they do not migrate data.

## 11. Error And Degradation Policy

- Invalid scope, unknown Vault IDs, malformed result IDs, and unsupported time
  filters are validation errors.
- Missing metadata state is fatal for memory projections because evidence cannot
  be resolved.
- Missing vector state degrades memory projections only when keyword or metadata
  evidence remains enough for the requested view.
- Missing graph state is a warning for project memory and a fatal error only for
  graph-required views.
- Missing explanation-cache entries return not found with a safe rerun hint.
- Stale projections are returned only with visible warnings and freshness
  fields.

## 12. Multi-Vault Policy

- `scope=None` uses the active Vault.
- `scope.vault_ids` selects explicit Vault IDs.
- all-Vault expansion happens before application services run.
- Memory projections group output by Vault when identical paths, titles,
  decisions, issue names, or entity labels appear in multiple Vaults.
- Cross-Vault graph relationships remain opt-in and preserve source, target,
  and evidence Vault IDs.

## 13. Handoff

Phase 6 implementation planning should proceed in this order:

1. Phase 6A: explanation DTOs, explanation cache, service boundary, MCP
   `explain_result`, and regression tests for current search/context/graph tool
   outputs.
2. Phase 6B: metadata-backed document listing contract, memory DTOs, project
   memory service, decision memory service, issue memory service, MCP tools, and
   `context/current` resource upgrade.
3. Phase 6C: timeline service, `timeline/recent` resource upgrade, recent
   changes MCP tool, health/freshness explorer service, scale-up readiness
   records, and status serialization tests.

Each slice should preserve the rule that Vault Graph writes only derived state
and never edits Vault content.
