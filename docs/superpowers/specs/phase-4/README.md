# Phase 4 Design Documents

This folder holds detailed Phase 4 context pack design documents that would
make `docs/SPEC.md` too long if kept in the top-level contract.

`docs/SPEC.md` remains the canonical product and architecture contract. Files in
this folder explain how Phase 4 should be implemented while preserving Vault
Graph's read-only, rebuildable, evidence-first boundary.

## Documents

| File | Role |
| --- | --- |
| `2026-06-12-phase-4-context-pack-overview-design.md` | Cross-slice overview, decisions, invariants, and handoff map |
| `2026-06-12-phase-4a-context-pack-contract-builder-boundary-design.md` | Detailed JSON contract, builder boundary, data models, warning model, and budget policy |
| `2026-06-12-phase-4b-local-context-pack-assembly-rendering-design.md` | Detailed local assembly flow, CLI surface, Markdown rendering view, and verification plan |

## Reading Order

1. Read `docs/SPEC.md` for the top-level product contract.
2. Read `2026-06-12-phase-4-context-pack-overview-design.md` for Phase 4
   invariants and dependencies.
3. Read the target slice document before writing an implementation plan.
