# Phase 3 Entity And Relationship Graph Overview Design

Status: Draft for implementation planning

Date: 2026-06-10

Scope: Phase 3 cross-slice overview

## 1. Purpose

Phase 3 turns Phase 2 evidence chunks into a rebuildable entity and
relationship graph projection.

The deliverable is not answer generation, context-pack assembly, MCP serving,
HTTP serving, or durable knowledge publication. The deliverable is an
evidence-first graph layer that supports related-item exploration, decision
trace prototypes, and optional graph retrieval signals while preserving Vault as
the source of truth.

This overview owns cross-slice invariants and dependencies. Each Phase 3 slice
owns its own detailed design document under `docs/superpowers/specs/phase-3/`.

## 2. Document Map

| Document | Role |
| --- | --- |
| `README.md` | Phase 3 design folder index and reading order |
| `2026-06-10-phase-3-overview-design.md` | Cross-slice roadmap, invariants, and handoff map |
| `2026-06-10-phase-3a-graphstore-contract-readiness-design.md` | Phase 3A graph contracts, `GraphStore`, and readiness design |
| `2026-06-10-phase-3b-local-entity-relationship-indexing-design.md` | Planned Phase 3B indexing and reconcile design |
| `2026-06-10-phase-3c-graph-projection-retrieval-design.md` | Planned Phase 3C projection and retrieval design |

`docs/SPEC.md` remains the top-level product contract. This folder is the
implementation-design layer for Phase 3.

## 3. Phase Slices

| Slice | Change | User Value | Explicitly Not Included |
| --- | --- | --- | --- |
| Phase 3A | Define graph record contracts, `GraphExtractionSpec`, `GraphStore`, scoped graph manifests, and graph readiness/status contracts | Vault Graph can represent graph state safely without changing search behavior | extraction execution, traversal, rustworkx ranking, decision traces |
| Phase 3B | Add deterministic local entity and relationship indexing with scope-local reconcile | `vg index` can build and repair derived graph state from current metadata | LLM-required extraction, cross-Vault entity merging, context packs |
| Phase 3C | Add bounded `GraphProjection`, opt-in graph retrieval signals, `vg related`, and decision trace prototype | users can inspect related entities and decision paths with evidence and warnings | `vg ask`, MCP serving, HTTP serving, Neo4j |

The slices separate persistence, indexing, and user-facing graph retrieval. This
keeps each step testable and prevents graph traversal from depending on an
unstable storage contract.

## 4. Cross-Slice Invariants

- Vault remains the durable source of truth.
- Graph state is derived, local-first, and rebuildable.
- The canonical graph evidence unit is the `MetadataStore` evidence chunk:
  `(vault_id, document_id, chunk_id)`.
- Graph output must resolve user-visible evidence through `MetadataStore`.
- Stored graph excerpts are rendering hints, not evidence authority.
- Multi-vault identity is explicit. Entity, relationship, evidence, warning,
  and revision records carry Vault IDs where collision is possible.
- Cross-Vault traversal is opt-in and preserves source, target, and evidence
  Vault IDs.
- Phase 3 must not merge entities across Vaults by name.
- Graph search is opt-in. Plain `vg search "query"` remains Phase 2C
  keyword/vector search until a graph mode is explicitly requested.
- Graph projections and caches are disposable runtime aids. They are not durable
  graph authority.

## 5. Responsibility Map

| Component | Owns | Must Not Own |
| --- | --- | --- |
| `VaultCatalog` | registered Vault IDs, active Vault, enabled Vault expansion | graph identity, extraction, ranking |
| `QueryScope` | selected Vault IDs and content scopes | implicit cross-Vault traversal |
| `MetadataStore` | document identity, chunk identity, chunk text authority, evidence resolution | graph relationship authority, graph ranking |
| `GraphStore` | persisted derived graph records, scoped manifests, graph readiness | reconcile planning, chunk text authority, runtime graph IDs |
| `GraphIndexer` | scope-local reconcile, upserts, tombstones, graph revision records | final answer rendering, graph algorithms |
| `GraphProjection` | bounded runtime graph algorithms and disposable caches | persisted source of truth |
| Retrieval layer | opt-in graph signal merge, warnings, evidence resolution | extraction, schema creation, direct SQLite access |
| CLI | argument parsing and rendering | direct storage or rustworkx access |

## 6. Slice Dependencies

```text
Phase 3A
  Graph contracts
  GraphStore
  Graph readiness
        |
        v
Phase 3B
  deterministic extractors
  GraphIndexer
  scope-local graph reconcile
        |
        v
Phase 3C
  GraphProjection
  vg related
  vg decision-trace
  optional vg search --include-graph
```

No Phase 3B implementation should bypass `GraphStore` to write graph state.
No Phase 3C implementation should bypass `GraphStore` or `MetadataStore` to
render graph evidence.

## 7. Data Flow Summary

Phase 3A readiness:

```text
vg status
  -> resolve selected Vault scope
  -> open GraphStore read-only
  -> report backend, schema, extraction spec, freshness, stale counts
```

Phase 3B indexing:

```text
vg index
  -> metadata indexing and keyword projection
  -> vector reconcile
  -> resolve QueryScope into per-Vault actual scopes
  -> MetadataStore.list_chunks(actual_scope)
  -> EntityExtractor and RelationshipExtractor
  -> GraphIndexer computes desired graph records
  -> GraphStore applies upserts, tombstones, and graph revisions
  -> GraphProjection cache invalidation
```

Phase 3C retrieval:

```text
vg related TARGET
  -> resolve selected Vault scope
  -> GraphStore readiness check
  -> GraphStore entity and relationship lookup
  -> optional GraphProjection bounded ranking
  -> MetadataStore evidence resolution
  -> render relationships, warnings, and evidence
```

Plain `vg search "query"` remains keyword/vector retrieval. Graph expansion
requires an explicit graph command or flag.

## 8. Error And Degradation Policy

- Missing or stale graph state is not fatal to plain Phase 2C search.
- Graph-specific commands fail or degrade with recovery guidance when graph
  state is missing, stale, incompatible, or partially failed.
- Invalid Vault scope, ambiguous target entity, incompatible schema, and
  unresolved graph evidence must be reported as structured domain errors or
  attributed warnings.
- Read-only graph commands must not create metadata, vector, graph,
  model-cache, projection-cache, or Vault files.

## 9. Multi-Vault Policy

- Default graph behavior uses the active Vault only.
- `--vault-id ID` uses exactly one registered Vault.
- `--all-vaults` expands to explicit enabled Vault IDs, then to per-Vault
  actual scopes before store reads.
- Identical paths, chunk IDs, entity names, aliases, headings, or relationship
  labels from different Vaults must not collide.
- Cross-Vault relationships explain source, target, and evidence Vault IDs.
- Cross-Vault relationships do not merge entities.

## 10. Handoff

Phase 3 implementation planning should proceed in this order:

1. Phase 3A: graph contracts, records, SQLite `GraphStore`, readiness, and
   contract tests.
2. Phase 3B: deterministic extractors, `GraphIndexer`, scope-local reconcile,
   dry-run, status, and graph indexing tests.
3. Phase 3C: rustworkx `GraphProjection`, opt-in graph signal integration,
   `vg related`, `vg decision-trace`, graph warnings, and CLI/read-only tests.

Each slice should preserve the rule that Vault Graph writes only derived state
and never edits Vault content.
