# Phase 3A GraphStore Contract And Readiness Design

Status: Draft for implementation planning

Date: 2026-06-10

Scope: Phase 3A only

## 1. Purpose

Phase 3A defines the graph contracts that must exist before Vault Graph can
index, traverse, or search graph relationships.

This slice is intentionally contract-first. It adds record shapes,
`GraphExtractionSpec`, `GraphStore`, graph manifests, graph revisions, and graph
readiness reporting. It does not run entity extraction, write graph records from
Vault content, build rustworkx projections, rank graph neighborhoods, or expose
graph retrieval commands.

The value is a stable deep module boundary:

- consumers can ask whether graph state is available and compatible
- future Phase 3B indexing can write graph state through one contract
- future Phase 3C retrieval can read graph candidates through one contract
- future Neo4j support can reuse the same contract tests

## 2. Non-Goals

Phase 3A must not implement:

- deterministic entity or relationship extraction execution
- `GraphIndexer` reconcile logic
- `vg index` graph writes beyond readiness wiring needed for status
- rustworkx `GraphProjection`
- `vg related`
- `vg decision-trace`
- `vg search --include-graph`
- graph ranking
- graph node or edge embeddings
- LLM-assisted extraction
- Neo4j
- cross-Vault entity merging
- any Vault file mutation

## 3. Core Contract

Phase 3A introduces these stable boundaries:

| Boundary | Role |
| --- | --- |
| `GraphExtractionSpec` | compatibility and staleness boundary for graph records |
| `EntityRecord` | derived entity projection record |
| `RelationshipRecord` | derived directed relationship projection record |
| `GraphEvidenceRef` | owner-scoped link from a graph record to one `MetadataStore` evidence chunk |
| `GraphRevision` | per Vault/actual-scope graph lineage and freshness row |
| `GraphManifest` | scoped current-state read model for future reconcile |
| `GraphReconcilePlan` | completed graph write plan produced by future `GraphIndexer` |
| `GraphReadinessService` | app-level readiness check combining graph state and metadata lineage |
| `GraphReadiness` | read-only graph backend, schema, lineage, and recovery status |
| `GraphStore` | interface for graph persistence and scoped record reads |
| `SQLiteGraphStore` | local reference implementation behind the `GraphStore` interface |

Rules:

- Graph state is derived Vault Graph state. It is rebuildable and
  non-authoritative.
- The canonical evidence key is `(vault_id, document_id, chunk_id)`.
- `GraphStore` stores graph records and evidence links, not final answer text.
- User-facing graph output in later slices must re-resolve evidence through
  `MetadataStore`.
- Graph identities include `vault_id` wherever a collision is possible.
- Cross-Vault relationships are allowed only as explicit relationship records
  with source, target, and evidence Vault IDs. They do not merge entities.

## 4. Package Layout

Use names that describe stable domain roles, not roadmap internals.

```text
src/vault_graph/
  graph/
    __init__.py
    graph_contracts.py
    graph_identity.py
    graph_readiness.py
  storage/
    interfaces/
      graph_store.py
    local/
      sqlite_graph_store.py

tests/
  fakes/
    in_memory_graph_store.py
  test_graph_contracts.py
  test_graph_store_contract.py
  test_sqlite_graph_store.py
  test_graph_readiness.py
  test_multi_vault_graph_identity.py
```

Rationale:

- `graph_contracts.py` owns immutable record dataclasses or equivalent typed
  models.
- `graph_identity.py` owns deterministic ID derivation.
- `graph_readiness.py` owns readiness/result types, not backend persistence.
- `storage/interfaces/graph_store.py` mirrors the existing store-boundary
  pattern.
- `storage/local/sqlite_graph_store.py` is the default local implementation and
  reference backend.

Avoid names such as `phase3a.py`, `graph_utils.py`, `manager.py`, or
`neo4j_ready.py`.

## 5. Architecture

Phase 3A runtime flow is readiness-only.

```text
vg status
  -> CatalogService resolves active Vault or requested Vaults
  -> MetadataStore provides current metadata lineage for actual scopes
  -> VectorStore status remains unchanged
  -> GraphStore.open_read_only(...)
  -> GraphReadinessService compares graph revisions with metadata lineage and expected GraphExtractionSpec
  -> status output includes graph backend/schema/spec/freshness fields
```

Future Phase 3B write flow uses the contracts added here.

```text
MetadataStore current chunks
  -> EntityExtractor / RelationshipExtractor
  -> GraphIndexer desired graph records
  -> GraphStore.current_manifest(actual_scope)
  -> GraphStore.apply_reconcile_plan(...)
  -> GraphRevision rows
```

Phase 3C read flow extends the same records and store boundary.

```text
GraphStore graph lookup methods defined by Phase 3C
  -> MetadataStore.resolve_chunk_evidence(...)
  -> graph command or retrieval output
```

The Phase 3C flow is shown to prove the 3A records are usable later. Phase 3A
must not implement graph traversal or graph retrieval behavior.

Phase 3A must not add direct SQLite reads in CLI, retrieval, extraction, or
indexing code. All graph access goes through `GraphStore`.

## 6. Data Models

All records should be immutable typed values at service boundaries. SQLite row
models may differ internally, but conversion must preserve these logical fields.

### 6.1 GraphExtractionSpec

Required fields:

- `spec_version`
- `spec_digest`
- `entity_schema_version`
- `relationship_schema_version`
- `entity_extractor_name`
- `entity_extractor_version`
- `relationship_extractor_name`
- `relationship_extractor_version`
- `relationship_status_rules_version`
- `confidence_rules_version`
- `serialized_spec`

Rules:

- `GraphExtractionSpec` is not user preference or backend configuration.
- It describes the extraction contract that produced graph records.
- Any required-field change makes affected graph records stale.
- `spec_digest` is a canonical hash of the serialized spec payload. It is the
  precise compatibility key.
- The spec version and digest are stored on entity records, relationship
  records, manifests, and graph revisions.
- `graph_specs` stores the full serialized spec snapshot so status can explain
  why a current spec differs from a stored spec.
- Same version with different digest is incompatible. Different version with a
  compatible migration policy is stale until reindexed; without such a policy it
  is incompatible.

### 6.2 EntityRecord

Required fields:

- `vault_id`
- `entity_id`
- `type`
- `name`
- `normalized_name`
- `aliases`
- `canonical_path`
- `evidence_refs`
- `confidence`
- `extraction_method`
- `graph_extraction_spec_version`
- `graph_extraction_spec_digest`
- `status`
- `created_at`
- `updated_at`
- `graph_index_revision`

Rules:

- `entity_id` is deterministic and Vault-scoped.
- Default ID derivation is a stable hash of `vault_id`, entity type,
  normalized canonical name, and canonical path when available.
- `canonical_path` is optional. It helps stability when an entity is tied to a
  durable wiki page path, but path alone is not authority.
- `aliases` and `confidence` are projection metadata.
- `status` starts with `active` or `tombstoned` in Phase 3A. Relationship status
  uses the graph relationship status vocabulary below.
- Same names in different Vaults remain different entities.

### 6.3 RelationshipRecord

Required fields:

- `relationship_id`
- `type`
- `source_vault_id`
- `source_entity_id`
- `target_vault_id`
- `target_entity_id`
- `evidence_refs`
- `status`
- `confidence`
- `extraction_method`
- `graph_extraction_spec_version`
- `graph_extraction_spec_digest`
- `created_at`
- `updated_at`
- `graph_index_revision`

Relationship status values:

- `stated`: directly supported by durable Vault text or explicit links
- `inferred`: derived by local extraction or graph traversal
- `contested`: conflicting evidence or unresolved disagreement exists
- `deprecated`: stale, superseded, or marked obsolete by durable Vault text

Rules:

- `relationship_id` is deterministic and Vault-scoped.
- Default ID derivation is a stable hash of relationship type, source
  Vault/entity ID, and target Vault/entity ID.
- All Phase 3 relationships are stored as directed records, including broad
  labels such as `related_to`.
- Symmetric user behavior queries both directions. It must not rewrite
  relationship identity.
- A relationship can carry multiple `GraphEvidenceRef` rows.
- A relationship does not merge entity identities, even when source and target
  live in different Vaults.

### 6.4 GraphEvidenceRef

Required fields:

- `evidence_ref_id`
- `owner_kind`
- `owner_vault_id`
- `owner_id`
- `evidence_vault_id`
- `document_id`
- `chunk_id`
- `content_hash`

Optional fields:

- `section`
- `anchor`
- `path`
- `excerpt`

Rules:

- `owner_kind` is `entity` or `relationship`.
- `owner_vault_id` is the entity Vault ID for entity evidence and the source
  Vault ID for relationship evidence.
- `owner_id` is `entity_id` for entity evidence and `relationship_id` for
  relationship evidence.
- `evidence_ref_id` is derived from owner kind, owner Vault ID, owner ID,
  evidence Vault/document/chunk ID, and anchor when available.
- `(owner_kind, owner_vault_id, owner_id, evidence_vault_id, document_id,
  chunk_id, anchor)` is unique.
- `path`, `section`, `anchor`, and `excerpt` are rendering metadata.
- Later user-visible output must resolve the evidence chunk through
  `MetadataStore`; stored excerpts are never final evidence authority.

### 6.5 GraphRevision

Required fields:

- `graph_run_id`
- `vault_id`
- `actual_scope`
- `graph_store_schema_version`
- `graph_extraction_spec_version`
- `graph_extraction_spec_digest`
- `graph_index_revision`
- `metadata_index_revision`
- `parser_version`
- `chunker_version`
- `entity_count`
- `relationship_count`
- `stale_count`
- `tombstone_count`
- `updated_at`

Rules:

- Graph freshness is tracked per Vault/actual scope.
- A multi-vault run records one `graph_run_id` and one child graph revision row
  per affected Vault/actual scope.
- `graph_index_revision` is lineage and status metadata. It is not a staleness
  comparison key.
- Staleness comparison uses evidence content hash, parser version, chunker
  version, metadata index revision, graph store schema version, and
  `GraphExtractionSpec` digest.
- No revision row may represent a global all-vault content-scope union.

### 6.6 GraphManifest

`GraphManifest` is a scoped read model used by future Phase 3B reconcile.

Required fields:

- requested scope
- actual scopes
- entity manifest rows
- relationship manifest rows
- evidence manifest rows
- tombstone rows
- graph store schema version
- graph extraction spec version
- graph extraction spec digest
- graph revision metadata

Rules:

- `GraphManifest` is not a second durable authority.
- It must be generated from `GraphStore` rows for the selected actual scopes.
- It must not include records outside the selected actual scopes.
- Entity manifest rows contain `vault_id`, `entity_id`, evidence ref IDs,
  evidence content hashes, status, graph extraction spec digest, metadata index
  revision, and graph index revision.
- Relationship manifest rows contain source Vault/entity ID, target
  Vault/entity ID, `relationship_id`, relationship type, status, evidence ref
  IDs, evidence content hashes, graph extraction spec digest, metadata index
  revision, and graph index revision.
- Evidence manifest rows contain `evidence_ref_id`, owner kind, owner Vault ID,
  owner ID, evidence Vault/document/chunk ID, content hash, and anchor.
- Tombstone rows use the `GraphTombstone` shape below.

### 6.7 GraphTombstone

Required fields:

- `tombstone_id`
- `record_kind`
- `record_vault_id`
- `record_id`
- `actual_scope`
- `reason`
- `graph_run_id`
- `graph_index_revision`
- `graph_extraction_spec_version`
- `graph_extraction_spec_digest`
- `tombstoned_at`

Rules:

- `record_kind` is `entity` or `relationship`.
- `record_vault_id` is the entity Vault ID for entity tombstones and the source
  Vault ID for relationship tombstones.
- Tombstones are scoped. A narrow graph reconcile must not tombstone records
  outside its actual scope.
- Tombstones are derived state and may be rebuilt from current metadata plus the
  graph extraction spec.

### 6.8 GraphLineageSnapshot

`GraphLineageSnapshot` is the app-level input that lets readiness determine
freshness honestly.

Required fields:

- requested scope
- actual scopes
- metadata index revisions by Vault/actual scope
- parser version
- chunker version
- graph store schema version
- expected graph extraction spec version
- expected graph extraction spec digest

Rules:

- `MetadataStore` and app-layer status services provide current metadata
  lineage.
- `GraphStore` provides stored graph revisions, stored graph spec snapshots,
  schema health, stale counts, and tombstone counts.
- `GraphReadinessService` compares both sides and returns `GraphReadiness`.
- `GraphStore` alone must not claim `fresh` when current metadata lineage was
  not supplied.

### 6.9 GraphReadiness

Required fields:

- `backend_name`
- `backend_available`
- `schema_version`
- `schema_compatible`
- `graph_extraction_spec_version`
- `graph_extraction_spec_digest`
- `graph_extraction_spec_compatible`
- `freshness`
- `stale_count`
- `tombstone_count`
- `last_graph_revision`
- `affected_vault_ids`
- `warnings`
- `recovery_hint`

Freshness values:

- `missing`: graph store or required tables do not exist
- `empty`: graph store exists but no graph revision exists for the scope
- `fresh`: graph revision is compatible with requested scope and current
  metadata lineage snapshot
- `stale`: graph records exist but lineage or extraction spec is stale
- `incompatible`: schema or extraction spec is incompatible
- `unavailable`: backend cannot be opened

Rules:

- Readiness is a typed status object, not an exception.
- Fatal backend construction errors may raise domain errors, but normal missing
  or stale graph state should be represented as readiness.
- `vg status` may render readiness before graph indexing exists.
- `fresh` requires a `GraphLineageSnapshot`. Without current metadata lineage,
  readiness may report backend/schema/spec status but must not report `fresh`.

### 6.10 GraphApplyResult

Required fields:

- graph run ID
- applied entity upsert count
- applied relationship upsert count
- applied evidence ref upsert count
- applied tombstone count
- graph revision rows
- warnings

Rules:

- `GraphApplyResult` reports what a backend applied. It does not decide what
  should have been applied.
- Phase 3A defines the shape for contract tests. App-level graph indexing uses
  it in Phase 3B.

### 6.11 GraphReconcilePlan

`GraphReconcilePlan` is the future Phase 3B write boundary between
`GraphIndexer` and `GraphStore`.

Required fields:

- requested scope
- actual scopes
- graph run ID
- entity upserts
- relationship upserts
- evidence ref upserts
- entity tombstones
- relationship tombstones
- graph revision rows
- graph extraction spec metadata
- projection cache invalidation metadata

Rules:

- `GraphIndexer` owns planning.
- `GraphStore` owns applying the completed plan atomically within its backend
  where practical.
- Phase 3A defines this boundary so write-capable store tests have a stable
  target. App-level graph indexing does not use it until Phase 3B.
- The plan must not include records outside the selected actual scopes.
- Tombstones use `GraphTombstone`.

## 7. GraphStore Interface

The interface should separate construction mode from operations.

Construction modes:

- `open_read_only(...)`: used by status and future retrieval commands
- `open_writable(...)`: reserved for Phase 3B indexing

Read-only operations required in Phase 3A:

- `health() -> StoreHealth`
- `stored_specs() -> tuple[GraphExtractionSpec, ...]`
- `latest_revisions(scopes) -> tuple[GraphRevision, ...]`
- `current_manifest(scopes) -> GraphManifest`
- `get_entity(vault_id, entity_id) -> EntityRecord | None`
- `get_relationship(source_vault_id, relationship_id) -> RelationshipRecord | None`
- `resolve_entities(identities) -> tuple[EntityRecord, ...]`
- `resolve_relationships(identities) -> tuple[RelationshipRecord, ...]`

Future graph lookup, relationship query, and neighborhood traversal operations
belong to Phase 3C. Phase 3A must not define required traversal result types.
This keeps contract readiness from becoming graph retrieval.

Write operation contract defined in Phase 3A:

- `apply_reconcile_plan(plan) -> GraphApplyResult`

Rules:

- Read-only stores must reject write operations with a domain error.
- `GraphStore` applies a completed plan; it does not decide what should be
  upserted or tombstoned.
- Read methods must filter by `vault_id` before returning results.
- Read methods return graph records only. They do not render final snippets or
  retrieve chunk text.
- Record lookups must include Vault scope even when a backend uses
  namespace-encoded IDs. This keeps the public contract safe for future backends
  that enforce Vault-scoped uniqueness with database constraints.
- SQLite-specific row IDs must not leak through the interface.
- Interface contract tests must run against both the in-memory fake and
  `SQLiteGraphStore`.

## 8. SQLite Reference Store

The local implementation is SQLite under the Vault Graph state path.

Logical tables:

- `graph_entities`
- `graph_relationships`
- `graph_evidence_refs`
- `graph_revisions`
- `graph_tombstones`
- `graph_specs`

Index requirements:

- entities by `(vault_id, entity_id)`
- entities by `(vault_id, normalized_name)`
- entities by `(vault_id, type, normalized_name)`
- relationships by `(source_vault_id, relationship_id)`
- relationships by `(source_vault_id, source_entity_id)`
- relationships by `(target_vault_id, target_entity_id)`
- relationships by `(type, status)`
- evidence refs by `(evidence_vault_id, document_id, chunk_id)`
- evidence refs by `(owner_kind, owner_vault_id, owner_id)`
- revisions by `(vault_id, actual_scope)`

Rules:

- SQLite is the reference backend, not the public contract.
- Future Neo4j support must satisfy `GraphStore` contract tests rather than
  copy SQLite schema details.
- Migrations must be additive when possible and fail loudly on incompatible
  schema versions.
- Deleting the graph database and rerunning future graph indexing must rebuild
  functionally equivalent records for the same Vault content and spec versions.

## 9. Error Handling

Public graph errors inherit from one `GraphStoreError` base. Phase 3A should
keep public exceptions small and use typed readiness for ordinary state.

Public domain errors:

- `GraphStoreUnavailable`: backend cannot be opened or queried
- `GraphSchemaIncompatible`: schema cannot be safely read
- `GraphReadOnlyViolation`: a write was attempted through a read-only store
- `GraphRecordInvalid`: a supplied graph record violates the contract

Normal missing, empty, stale, and spec-mismatch states should be returned
through `GraphReadiness` when possible, not raised.

Readiness warnings:

- graph store missing
- graph store empty for requested scope
- stale graph revision
- stale graph extraction spec
- incompatible graph schema
- unresolved graph evidence reference
- partially failed previous graph run

Recovery guidance:

- missing or empty graph store: run `vg index` after Phase 3B exists
- stale graph state: rerun `vg index` for the affected Vault scope
- incompatible schema: run the supported migration or rebuild graph state
- incompatible extraction spec: rerun graph indexing with the current spec
- unresolved evidence: rerun metadata indexing, then graph indexing

Phase 3A must not hide incompatible schema or invalid records behind empty
results. Returning no results is valid only when the store is compatible and
the selected scope genuinely has no matching graph records.

## 10. Multi-Vault Rules

Multi-vault correctness is part of Phase 3A, not a later cleanup.

Rules:

- Every entity record includes `vault_id`.
- Every relationship record includes source and target Vault IDs.
- Every evidence ref includes owner kind, owner Vault ID, owner ID, and evidence
  Vault ID.
- Every graph revision is scoped to one Vault/actual scope.
- `--all-vaults` style scopes are expanded before store reads.
- Store methods must not accept or create one global all-vault content-scope
  union.
- Same relative path, document ID, chunk ID, entity name, alias, heading, or
  relationship label in two Vaults must not collide.
- Cross-Vault relationships are explicit records; they are not name-based
  entity merges.

## 11. Status Surface

Phase 3A may extend `vg status` with graph readiness fields, even before graph
indexing exists.

Human-readable status should include:

- graph backend name
- graph backend availability
- graph schema compatibility
- graph extraction spec version and compatibility
- graph extraction spec digest
- graph freshness
- stale graph record count
- tombstone count
- last graph revision per Vault/actual scope when present
- recovery hint

Machine-readable status should expose the same data as structured fields so
future agents can decide whether graph commands are safe to call.

Status must not create graph stores, run migrations, write projection caches, or
modify Vault content when called in read-only mode.

## 12. Testing

Required contract tests:

- deterministic entity ID derivation includes `vault_id`
- deterministic relationship ID derivation includes source and target Vault IDs
- `GraphEvidenceRef` requires owner kind, owner Vault ID, owner ID, and evidence
  Vault ID
- entity-owned and relationship-owned evidence refs derive deterministic IDs
- read-only `GraphStore` rejects writes
- `GraphStore.current_manifest` is scoped
- `GraphReadinessService` reports missing, empty, fresh, stale, incompatible,
  and unavailable states from graph state plus metadata lineage
- entity lookup requires Vault ID
- relationship lookup requires source Vault ID
- `apply_reconcile_plan` returns `GraphApplyResult`
- tombstone rows preserve record kind, record Vault ID, scope, reason, and graph
  index revision
- same entity names in two Vaults do not collide
- same evidence chunk IDs in two Vaults do not collide
- SQLite implementation satisfies the same contract as the in-memory fake

Required read-only tests:

- `vg status` with graph readiness does not write Vault content
- `vg status` with graph readiness does not create vector, model-cache, or
  projection-cache files
- read-only graph store opening does not run write migrations silently

Required schema tests:

- compatible schema reports usable readiness
- incompatible schema reports recovery guidance
- missing tables report `missing` or `incompatible` deterministically
- graph extraction spec mismatch reports stale or incompatible readiness

## 13. Implementation Handoff

Phase 3A should be implemented in this order:

1. Add graph record models and identity helpers.
2. Add `GraphStore` interface and in-memory contract fake.
3. Add `GraphReadinessService`, `GraphManifest`, `GraphTombstone`, and domain
   errors.
4. Add SQLite schema and `SQLiteGraphStore`.
5. Add status wiring that reads graph readiness without creating graph state.
6. Add contract, SQLite, read-only, and multi-vault tests.

Stop at contract readiness. Phase 3B should begin only after Phase 3A can prove
the graph store boundary is stable, scope-aware, read-only safe, and reusable by
future backends.
