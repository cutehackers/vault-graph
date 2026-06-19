# Phase 6 Design Documents

This folder holds detailed Phase 6 design documents that would make
`docs/SPEC.md` too long if kept in the top-level contract.

`docs/SPEC.md` remains the canonical product and architecture contract. Files in
this folder explain how Phase 6 should add memory and explorer projections while
preserving Vault Graph as a read-only, rebuildable, evidence-first access layer
over Vault.

Phase 6 memory is projection terminology, not permission to add a writable
memory database. External systems such as Mem0 or MemMachine remain future
adapter/export targets only.

## Documents

| File | Role |
| --- | --- |
| `2026-06-18-phase-6-memory-and-explorer-views-overview-design.md` | Cross-slice overview, invariants, dependencies, and implementation handoff map |
| `2026-06-18-phase-6a-result-explanation-contract-design.md` | Phase 6A result explanation records, bounded MCP explanation cache, and `explain_result` service boundary |
| `2026-06-18-phase-6b-project-decision-issue-memory-design.md` | Phase 6B project, decision, and issue memory projections over indexed evidence |
| `2026-06-18-phase-6c-timeline-health-explorer-design.md` | Phase 6C recent timeline, projection freshness, backend health, and scale-up readiness views |

Korean copies use the same filename with `-ko.md`.

## Reading Order

1. Read `docs/SPEC.md` for the top-level product contract.
2. Read `2026-06-18-phase-6-memory-and-explorer-views-overview-design.md` for
   Phase 6 invariants and dependencies.
3. Read the target slice document before writing an implementation plan.
