# Phase 3 Design Documents

This folder holds detailed Phase 3 design documents that would make
`docs/SPEC.md` too long if kept in the top-level contract.

`docs/SPEC.md` remains the canonical product and architecture contract. Files in
this folder explain how each Phase 3 slice should be implemented while staying
inside that contract.

## Documents

| File | Role |
| --- | --- |
| `CONTEXT.md` | Shared Phase 3 glossary and terminology boundaries |
| `2026-06-10-phase-3-overview-design.md` | Cross-slice overview, common invariants, and implementation handoff map |
| `2026-06-10-phase-3a-graphstore-contract-readiness-design.md` | Detailed Phase 3A design for graph contracts, `GraphStore`, and readiness |

## Planned Slice Documents

These files should be added before those slices move into implementation
planning:

- `2026-06-10-phase-3b-local-entity-relationship-indexing-design.md`
- `2026-06-10-phase-3c-graph-projection-retrieval-design.md`

## Reading Order

1. Read `docs/SPEC.md` for the top-level product contract.
2. Read `CONTEXT.md` for shared Phase 3 terms.
3. Read `2026-06-10-phase-3-overview-design.md` for Phase 3 invariants and
   dependencies.
4. Read the target slice document before writing an implementation plan.
