# Phase 3 Entity And Relationship Graph

This context defines the shared language for Phase 3 graph work in Vault Graph.
It exists to keep graph terminology evidence-first, read-only, and consistent
with Vault as the source of truth.

## Language

### Source And Evidence

**Vault**:
The durable source of truth that Vault Graph reads from and never mutates.
_Avoid_: graph database, knowledge database, mutable workspace

**Vault Graph**:
A read-only, rebuildable access layer over one or more registered Vaults.
_Avoid_: source of truth, authoring system, durable knowledge store

**Evidence Chunk**:
A Vault-derived text unit that can support search results, graph entities, and
graph relationships.
_Avoid_: fact, final answer, graph payload

**Evidence Authority**:
The rule that user-visible claims must resolve back to Vault-derived evidence
through metadata, not rely on cached graph excerpts.
_Avoid_: graph authority, vector authority, excerpt authority

### Graph Concepts

**Entity**:
A Vault-scoped meaningful subject discovered from evidence, such as a concept,
project, decision, issue, system, workflow, or document.
_Avoid_: global entity, knowledge object, source record

**Relationship**:
A directed, evidence-linked connection from one entity to another.
_Avoid_: undirected edge, fact, merged identity

**Stated Relationship**:
A relationship directly supported by durable Vault text or explicit Vault links.
_Avoid_: confirmed fact, ground truth edge

**Inferred Relationship**:
A relationship derived by local extraction or graph traversal and presented with
its evidence and confidence.
_Avoid_: hidden fact, generated truth

**Contested Relationship**:
A relationship with conflicting evidence or unresolved disagreement.
_Avoid_: error, duplicate, invalid edge

**Deprecated Relationship**:
A relationship that is stale, superseded, or marked obsolete by durable Vault
text.
_Avoid_: deleted relationship, removed fact

**Graph Evidence Ref**:
An owner-scoped link from an entity or relationship to one evidence chunk.
_Avoid_: evidence text, citation, source of truth

**Graph State**:
Derived entity, relationship, evidence, revision, and manifest data that can be
deleted and rebuilt from Vault-derived metadata.
_Avoid_: durable knowledge, canonical graph, source data

### Graph Boundaries

**Graph Store**:
The persisted derived graph boundary for entity records, relationship records,
evidence refs, revisions, and readiness data.
_Avoid_: graph authority, traversal engine, source database

**Graph Projection**:
A bounded runtime graph view used for traversal, paths, and ranking.
_Avoid_: graph database, durable graph, persisted authority

**Graph Indexer**:
The component that reconciles current evidence chunks into derived graph state.
_Avoid_: extractor, answer generator, Vault writer

**Graph Extraction Spec**:
The versioned contract that defines how graph entities and relationships were
derived from evidence.
_Avoid_: user preference, backend configuration, ranking policy

**Graph Readiness**:
The status of graph backend health, schema compatibility, extraction spec
compatibility, freshness, and recovery guidance.
_Avoid_: graph availability only, search readiness, health check

**Graph Manifest**:
A scoped current-state view used to compare existing graph state with desired
graph state during reconcile.
_Avoid_: second source of truth, global inventory, cache

**Graph Revision**:
A Vault-scoped lineage marker that records which metadata and graph extraction
state produced graph records.
_Avoid_: content version, Vault revision, cache key only

**Graph Tombstone**:
A derived marker that a graph entity or relationship is no longer current for a
selected scope.
_Avoid_: Vault delete, hard delete, permanent removal

### Scope And Vaults

**Effective Scope**:
The concrete Vault and content-scope selection used by a store operation after
user scope has been resolved.
_Avoid_: global scope, implicit all-vault scope

**Cross-Vault Relationship**:
A relationship whose source, target, or evidence belongs to different Vaults and
is only considered when cross-Vault graph behavior is explicit.
_Avoid_: merged entity, global relationship, automatic federation

**Vault-Scoped Identity**:
The rule that entity, relationship, evidence, warning, and revision identity must
include Vault identity wherever collisions are possible.
_Avoid_: path-only identity, name-only identity, global ID by default
