# Phase 2B Local Vector Indexing Design

Status: Draft for implementation planning

Date: 2026-06-08

Scope: Phase 2B only

## 1. Purpose

Phase 2B turns the Phase 2A contracts into a real local vector projection.

The deliverable is not user search. The deliverable is a sustainable local
vector index that `vg index` can build, `vg status` can inspect, and future
Phase 2C search can trust as a rebuildable candidate source.

Phase 2B must preserve Vault Graph's core values:

- Vault remains the durable source of truth.
- Vector state is derived, read-only with respect to Vault, and rebuildable.
- Local-first operation works in the default install.
- Multi-vault identity and content-scope filtering stay explicit.
- Vector indexing prepares for scale-up without changing the product model.

## 2. Non-Goals

Phase 2B must not implement:

- `vg search`
- `vg ask`
- hybrid ranking
- keyword search
- graph extraction
- graph traversal
- decision traces
- context packs
- MCP serving
- HTTP serving
- Qdrant support
- hosted embedding APIs
- durable writes back to Vault

Those belong to later phases. Phase 2B should expose only vector indexing and
vector status.

## 3. Accepted Decisions

Phase 2B follows these accepted decisions.

1. Chroma is the default local `VectorStore`.

   Chroma is installed as a core dependency because vector indexing is part of
   the basic local workflow. It is not a hosted service requirement.

2. Embeddings are local-first.

   `TextEmbeddings` remains the only embedding boundary. The default production
   implementation is `FastEmbedTextEmbeddings` using
   `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`. Hosted
   implementations can be added later behind the same interface without
   changing vector indexing.

3. `vg index` updates metadata and vector projections by default.

   The command first applies metadata indexing, then reconciles vector state for
   the selected scope. `--dry-run` plans both stores and writes neither.

4. Chroma collections are keyed by `EmbeddingModelSpec`.

   Collections are not split per Vault for the MVP. Records carry `vault_id`,
   `document_id`, `chunk_id`, and `content_scope` as filter metadata.

5. `EmbeddingModelSpec` is the compatibility boundary.

   A model name, version, dimension, or spec-version change makes affected
   vector state stale. Vault Graph must not silently search mixed model specs
   together.

## 3.1 Default Embedding Policy

The default Phase 2B embedding policy is fixed:

- implementation: `FastEmbedTextEmbeddings`
- model: `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`
- model version: `faf4aa4225822f3bc6376869cb1164e8e3feedd0`
- source model revision: `e8f8c211226b894fcb81acc59f3b34ba3efd5f42`
- artifact repo: `qdrant/paraphrase-multilingual-MiniLM-L12-v2-onnx-Q`
- dimensions: `384`
- spec version: `fastembed-multilingual-minilm-l12-v2-cosine-v1`
- runtime: local CPU
- cache path: outside registered Vault roots, for example
  `~/.cache/vault-graph/embeddings`
- `embedding_batch_size`: `256`
- `embedding_parallelism`: `null`, meaning main-process embedding
- `embedding_lazy_load`: `true`
- first use: download the configured model artifact if it is missing and network
  access is available
- offline: fail with clear model-unavailable status when the artifact is not
  cached
- fallback: never silently fall back to another model

The default model is multilingual because Vault content may mix Korean and
English. Keeping the model at 384 dimensions also keeps Chroma storage small and
compatible with the existing `EmbeddingModelSpec` boundary.

## 3.2 CPU Throughput Tuning Policy

Phase 2B should expose CPU throughput tuning through the embedding adapter
configuration, not through the vector store or CLI-specific shortcuts.

`FastEmbedTextEmbeddingsConfig` should contain:

- `embedding_batch_size: int = 256`
- `embedding_parallelism: int | None = None`
- `embedding_lazy_load: bool = True`

`embedding_parallelism` uses FastEmbed semantics:

- `None`: run in the main process. This is the default because it has the least
  memory surprise on a MacBook or laptop.
- `0`: let FastEmbed detect available CPU cores.
- positive integer: use that many workers.

These values are runtime execution settings. They must be visible in index run
metadata and status diagnostics, but they are not part of
`EmbeddingModelSpec`. Changing `embedding_batch_size` or worker count must not
stale vector records by itself.

`embedding_batch_size` is not chunk size. Current chunk boundaries come from the
`heading-section-v1` chunker and are heading-section based, not a fixed token or
character count.

`VectorIndexer` remains responsible for stable behavior:

- select only planned upsert chunks for embedding
- send texts to `TextEmbeddings` in batches
- reject duplicate input IDs before embedding
- bind every returned vector to the requested input ID
- preserve vector identity and manifest keys regardless of batch boundaries
- report configured tuning values in dry-run output without loading the model

If an embedding run fails because the configured `embedding_batch_size` or
worker count is too large, the vector step fails with diagnostics and leaves
vector state recoverable. Vault Graph must not silently lower
`embedding_batch_size`, disable parallelism, or switch embedding runtimes during
the same run.

## 4. Sustainability Plan

All derived projections should be rebuildable and recoverable through
scope-local reconcile.

Phase 2B applies that rule to vectors:

1. The vector indexer compares live `MetadataStore` chunks with the
   `VectorStore` manifest for the selected `QueryScope`.
2. `MetadataStore` exposes current chunks through a stable interface. The vector
   indexer must not read SQLite tables directly.
3. Vector manifests separate staleness comparison keys from lineage/status
   fields. Comparison keys are source chunk hash, chunker version, metadata
   revision, embedding model spec, and backend schema version. Vector revision
   and backend name are lineage/status fields.
4. Inside the selected reconcile scope, missing, deleted, tombstoned, changed,
   re-chunked, or model-stale vector records are removed, replaced, or
   tombstoned so they are not queryable as fresh results. Records outside the
   selected scope are left untouched.
5. Metadata and vector stores do not need one cross-store transaction. If vector
   indexing fails after metadata succeeds, `vg index` returns a nonzero exit,
   status reports vector state as stale or unavailable, and the next `vg index`
   recovers by reconcile.
6. Future graph indexing uses the same pattern: current metadata chunks plus
   extraction policy plus graph manifest produce the desired graph projection.
7. Current Phase 2B terminology is text chunk embedding and local vector
   indexing. "Graph embedding" is out of scope until graph node or edge
   embeddings become a separate derived projection.

## 5. Responsibility Map

| Component | Owns | Must Not Own |
| --- | --- | --- |
| `CatalogService` | state path composition and catalog-backed service wiring | Vault content mutation |
| `VaultCatalog` | registered Vault IDs and root paths | vector records or Chroma collections |
| `MetadataStore` | current document and chunk projection, hashes, parser and chunker revisions, evidence resolution | embedding generation or vector backend internals |
| `TextEmbeddings` | text-to-vector conversion under one `EmbeddingModelSpec` | storage, search, ranking, Vault identity |
| `FastEmbedTextEmbeddings` | production local CPU embedding implementation and model artifact loading | Chroma writes, fallback policy, evidence resolution |
| `VectorIndexer` | vector reconcile planning and application | metadata mutation, evidence rendering, search ranking |
| `VectorStore` | vector persistence, manifest export, scoped vector search contract, backend health | chunk text authority, path authority, durable truth |
| `IndexService` | metadata-then-vector orchestration and status assembly | backend-native Chroma details |
| CLI | user command parsing and output | direct store table access |

This keeps Phase 2B as a small number of deep modules instead of scattering
Chroma logic through CLI, metadata indexing, and retrieval code.

## 6. Runtime Flow

### 6.1 Normal Index

```text
vg index
  -> load VaultCatalog and state paths
  -> resolve QueryScope from active Vault, --vault-id, or --all-vaults
  -> MetadataIndexer.apply(scope)
  -> VectorIndexer.apply(scope, metadata_revision)
  -> StatusReport with metadata and vector fields
```

`vg index` should fail loudly if vector indexing fails, because the full
requested index operation did not complete. The output must still report that
metadata was applied when that is true, and `vg status` must show vector state
as stale or unavailable until the next successful reconcile. The CLI exit code
must be nonzero for the failed vector step.

### 6.2 Dry Run

```text
vg index --dry-run
  -> MetadataIndexer.plan(scope)
  -> VectorIndexer.plan(scope)
  -> report planned metadata and vector changes
  -> no MetadataStore or VectorStore writes
```

Dry-run may open stores in read-only or non-initializing mode. It must not create
Chroma collections, SQLite schema, state directories, or Vault files.

### 6.3 Full Rebuild

`vg index --full` rebuilds metadata and vector state for the selected scope. For
vectors, full rebuild means all manifest rows in the selected scope are treated
as stale unless they match the current desired chunk, model spec, schema, and
revision state.

The selected scope still matters. A full rebuild for one Vault must not
tombstone vector records from another Vault.

## 7. Data Contracts

### 7.1 MetadataStore Chunk Listing

Phase 2B adds one `MetadataStore` boundary:

```python
class MetadataStore(Protocol):
    def list_chunks(self, scope: QueryScope) -> tuple[ChunkSnapshot, ...]: ...
```

Rules:

- Return only current, non-tombstoned chunks.
- Filter by `QueryScope.vault_ids`.
- Filter by `QueryScope.content_scopes` with the same same-or-child semantics
  used by metadata indexing.
- Receive an effective per-Vault `QueryScope` from application services. The
  store must not infer catalog entry scope from a global all-vault scope union.
- Return `ChunkSnapshot` records, not backend-native rows.
- Include chunk text because embedding generation needs it.
- Include `content_hash`, `chunker_version`, and `index_revision` because vector
  freshness depends on them.

`IndexService` or `VectorIndexer` must resolve user selection through
`VaultCatalog` first. For all-vault runs, reconcile is planned over per-Vault
effective scopes that match `VaultLoader` behavior:

- if the query scope is narrower than the catalog entry scope, use the query
  scope
- if the catalog entry scope is narrower than the query scope, use the catalog
  entry scope
- if neither contains the other, that scope pair contributes no work

### 7.2 Content Scope Derivation

`VectorEmbeddingRecord.content_scope` is filter metadata, not evidence.

For a document path, derive content scope from the normalized parent directory:

- `wiki/page.md` -> `wiki`
- `wiki/systems/runtime.md` -> `wiki/systems`
- `docs/SPEC.md` -> `docs`
- `scratch/reports/phase-2/note.md` -> `scratch/reports/phase-2`

This keeps same-or-child filtering useful:

- a query scope of `wiki` includes `wiki/systems`
- a query scope of `wiki/systems` does not include unrelated `wiki/decisions`
- a query scope of `docs` includes `docs/SPEC.md`

### 7.3 Vector Record Freshness

Phase 2A record shapes remain the public boundary. Phase 2B expands vector
records, manifest records, and tombstones before Chroma is implemented.

Staleness comparison keys:

- `source_chunk_hash`: copied from `ChunkSnapshot.content_hash`
- `chunker_version`: copied from `ChunkSnapshot.chunker_version`
- `metadata_index_revision`: copied from `ChunkSnapshot.index_revision`
- `embedding_spec`: copied from `TextEmbeddings.model_spec()`
- `backend_schema_version`: local Chroma adapter schema version

Lineage and status fields:

- `vector_index_revision`: created by the vector indexer
- `backend`: `chroma` for the Phase 2B implementation

These fields are for rebuildability and status. They must not become
user-facing evidence. Normal search results in Phase 2C still resolve evidence
through `MetadataStore`.

`vector_index_revision` is not a staleness comparison key. If it were, every
successful vector run would make unchanged records stale in the next run.

`VectorTombstone` should identify the exact stale row:

- `vector_id`
- `vault_id`
- `chunk_id`
- `embedding_spec`

The current `(vault_id, chunk_id)` identity is too broad once old-model and
current-model rows can coexist during model-spec reconcile.

### 7.4 Vector IDs

Keep the Phase 2A vector ID rule:

```text
vector_id = stable_id("vector", vault_id, chunk_id, embedding_model_spec_key)
```

When a chunk hash changes under the same `chunk_id`, the vector indexer may
replace the existing record under the same vector ID. When a backend stores stale
rows under a previous vector ID, the vector indexer tombstones them. The
required behavior is that stale vectors are no longer queryable as fresh records.

### 7.5 Chroma Collection Strategy

Use one logical Chroma collection per `EmbeddingModelSpec`.

Vector schema version is collection metadata for compatibility checks. It is not
part of the accepted product-level collection key. If a schema version is
incompatible, the adapter should fail loudly or require an explicit rebuild or
migration path rather than silently mixing schemas.

Collection metadata stores:

- model name
- model version
- dimensions
- spec version
- vector schema version
- backend name

Record payload stores:

- `vector_id`
- `vault_id`
- `document_id`
- `chunk_id`
- `content_scope`
- `source_chunk_hash`
- `chunker_version`
- `metadata_index_revision`
- `vector_index_revision`

The MVP does not create one collection per Vault. Vault filtering stays in
payload metadata so a single Vault Graph instance can index multiple Vaults
without changing the storage contract.

## 8. Reconcile Algorithm

The vector indexer works in two phases: plan and apply.

### 8.1 Planning

Inputs:

- selected effective `QueryScope`
- current `EmbeddingModelSpec`
- live chunks from `MetadataStore.list_chunks(effective_scope)`
- active manifest rows from `VectorStore.export_manifest(effective_scope)`
- current vector backend health

Steps:

1. Build desired records from live chunks.
2. Build current records from manifest rows.
3. Mark a desired record for upsert when no current row exists.
4. Mark a desired record for upsert when staleness comparison keys differ.
5. Mark a current row for tombstone when it has no matching desired chunk in
   the selected effective scope.
6. Count unchanged records when all staleness comparison keys match.
7. Record warnings for backend health or schema compatibility problems.

`VectorStore.export_manifest(scope)` must return active manifest rows for the
effective scope across all Chroma model-spec collections, not only the current
`EmbeddingModelSpec`. Otherwise the vector indexer cannot see old-model rows
that should be tombstoned after a model-spec change.

### 8.2 Applying

Inputs:

- vector plan
- `TextEmbeddings`
- `VectorStore`

Steps:

1. Embed only chunks planned for upsert.
2. Join each `EmbeddingVector.input_id` back to the desired chunk record.
3. Create `VectorEmbeddingRecord` values with freshness metadata.
4. Create `VectorTombstone` values for stale manifest rows.
5. Call `VectorStore.apply_vector_revision(...)` once for the plan.
6. Return result counts and warnings to `IndexService`.

The vector indexer should batch embeddings, but batching is an internal
optimization. It must not change vector identity, status output, or failure
semantics. Batch boundaries must not leak into vector IDs, collection names,
manifest comparison keys, or retrieval result metadata.

## 9. Status Contract

Phase 2B extends `vg status` with vector fields.

Minimum human-readable fields:

- `vector_ok`
- `vector_backend`
- `vector_schema_compatible`
- `vector_message`
- `embedding_model`
- `embedding_model_version`
- `embedding_dimensions`
- `embedding_spec_version`
- `vector_revision`
- `vector_stale_count`
- `vector_last_error`

Status must distinguish:

- no vector index has been built yet
- vector backend is unavailable
- vector backend schema is incompatible
- vector records are stale against metadata
- vector records are stale because the model spec changed
- vector state is fresh for the selected scope
- status scope used for freshness counts

`vg status` uses the active Vault by default. Phase 2B should add the same
selection flags as `vg index`: `--vault-id ID` and `--all-vaults`. Status output
must print the scope used for vector freshness fields so `vector_stale_count`
is not ambiguous in a multi-vault setup.

MCP status later should expose the same logical fields through
`check_index_status()`, but Phase 2B only needs the CLI surface.

## 10. Error Handling

Contract errors should fail loudly:

- embedding dimensions do not match `EmbeddingModelSpec`
- Chroma collection metadata does not match `EmbeddingModelSpec`
- vector backend schema is incompatible
- duplicate embedding input IDs appear in one batch
- `VectorStore` returns records outside `QueryScope`
- a manifest row is missing `vault_id`, `chunk_id`, `content_scope`, or model
  metadata

Recoverable degraded state should be visible through status:

- metadata succeeded but vector indexing failed
- Chroma state path is missing or uninitialized
- no local embedding model is configured
- configured model artifact is not cached and cannot be downloaded
- vector manifest has stale records
- model spec changed since the last vector run

Vault Graph should not silently fall back to a different embedding model.

## 11. Read-Only Boundary

Phase 2B writes only Vault Graph state:

- metadata state
- Chroma vector state
- vector revision metadata
- derived status metadata

Phase 2B must not write:

- Vault `raw/`
- Vault `wiki/`
- Vault `docs/`
- Vault `scratch/`
- Vault Git metadata
- any path inside a registered Vault root

The state path guard from Phase 1 applies to Chroma paths as well. The default
Chroma path should live under the configured Vault Graph state directory, for
example:

```text
state/vector/chroma
```

## 12. Multi-Vault Rules

Multi-vault support is mandatory in the design even when the default path is a
single active Vault.

Rules:

- Every vector record includes `vault_id`.
- Every manifest row includes `vault_id`.
- Every Chroma payload includes `vault_id`.
- Search filters in Phase 2C must use explicit `QueryScope.vault_ids`.
- Reconcile plans use Vault-scoped keys.
- Identical relative paths or chunk IDs from different Vaults must not collide.
- `--all-vaults` expands to explicit Vault IDs before services run.
- `include_cross_vault` does not grant any graph traversal behavior in Phase 2B.

## 13. Scale-Up Path

The Phase 2B design should make Qdrant a backend replacement later, not a new
architecture.

The stable contract is:

- `TextEmbeddings`
- `EmbeddingModelSpec`
- `VectorStore`
- `VectorIndexer`
- `QueryScope`
- vector manifest reconcile metadata
- metadata evidence resolution through `MetadataStore`

Qdrant can replace Chroma when vector volume, filtering, or serving latency
requires it. It must still satisfy the same manifest, filter, model-spec, and
evidence-resolution rules.

Future graph indexing should reuse the reconcile pattern:

```text
MetadataStore live chunks
  + extraction policy
  + GraphStore manifest
  -> desired graph records
  -> upserts and tombstones
```

This keeps derived projections consistent without making graph records or
vectors durable knowledge.

## 14. Testing Strategy

Phase 2B should be test-driven.

### 14.1 MetadataStore Tests

Verify:

- `list_chunks(scope)` returns only current non-tombstoned chunks.
- Vault ID filtering works.
- content-scope filtering uses same-or-child semantics.
- duplicate relative paths across Vaults do not collide.

### 14.2 VectorIndexer Plan Tests

Verify:

- new chunks become upserts.
- unchanged chunks remain unchanged.
- changed chunk hashes become upserts.
- changed chunker versions become upserts.
- changed `metadata_index_revision` marks affected records stale.
- changed `EmbeddingModelSpec` marks affected records stale.
- changed backend schema version marks affected records stale or incompatible.
- old-model manifest rows are visible and tombstoned after model-spec change.
- deleted or tombstoned chunks create vector tombstones.
- narrow Vault scope does not tombstone records from other Vaults.
- all-vault scope uses per-Vault effective scopes rather than a global scope
  union.
- dry-run creates no Chroma state or metadata state.

### 14.3 Chroma VectorStore Tests

Verify:

- records are persisted and reloaded.
- collection metadata matches `EmbeddingModelSpec`.
- schema mismatch fails loudly.
- query filtering applies `vault_id` and `content_scope` before limits.
- manifest export returns staleness comparison keys and lineage/status fields.
- manifest export can include old-model rows in the selected scope.
- tombstoned records are not returned as search hits.

### 14.4 CLI And Status Tests

Verify:

- `vg index` updates metadata and vector status.
- `vg index --dry-run` reports vector work without writes.
- vector failure after metadata success is visible and recoverable.
- `vg status` reports vector health, schema, model spec, revision, stale count,
  and last error.
- `vg status` prints the freshness scope and supports active-vault,
  `--vault-id`, and `--all-vaults` status checks.
- vector failure after metadata success returns a nonzero `vg index` exit while
  preserving the applied metadata revision in output and status.
- Phase 2B still does not expose `vg search`.

### 14.5 Read-Only Tests

Verify:

- vector indexing never writes under a registered Vault root.
- Chroma state path cannot be configured inside a Vault root.
- embedding model cache cannot be configured inside a Vault root.
- `FastEmbedTextEmbeddings` does not mutate Vault files.

### 14.6 FastEmbed TextEmbeddings Tests

Verify:

- default `EmbeddingModelSpec` uses
  `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`, 384
  dimensions, and spec version `fastembed-multilingual-minilm-l12-v2-cosine-v1`.
- model revision is recorded in `EmbeddingModelSpec.model_version`.
- missing uncached artifacts produce a clear model-unavailable error when
  offline.
- no silent fallback to another model is possible.
- cache path is outside registered Vault roots.
- default throughput config is `embedding_batch_size` `256`,
  `embedding_parallelism` `None`, and `embedding_lazy_load` `True`.
- changing `embedding_batch_size` or `embedding_parallelism` does not change
  `EmbeddingModelSpec`.
- duplicate input IDs in one embedding request fail before backend inference.
- dry-run reports tuning values without loading the embedding model.
- oversized `embedding_batch_size` or worker failures surface as vector-step
  diagnostics and do not trigger automatic fallback tuning.

## 15. Acceptance Criteria

Phase 2B is complete when:

- Chroma is installed as a default local dependency.
- FastEmbed is installed as a default local dependency.
- `FastEmbedTextEmbeddings` is the default production local embedding
  implementation.
- `FastEmbedTextEmbeddings` supports explicit CPU `embedding_batch_size`,
  `embedding_parallelism`, and `embedding_lazy_load` tuning.
- Chroma implements the existing `VectorStore` contract.
- `MetadataStore.list_chunks(scope)` exists and is covered by tests.
- `VectorIndexer` can plan and apply scope-local reconcile.
- vector manifests include staleness comparison keys and lineage/status fields
  required for sustainable reindexing.
- `vg index` applies metadata plus vector projection updates by default.
- `vg index --dry-run` plans metadata plus vector changes without writes.
- `vg index --dry-run` creates no Chroma collections, SQLite schema, state
  directories, or Vault files.
- `vg status` exposes vector backend health, schema compatibility, freshness,
  model spec, stale count, and recoverable failure messages.
- `vg index --dry-run` reports configured `embedding_batch_size` and
  `embedding_parallelism` without loading the model or initializing vector
  backend state.
- model spec changes do not silently mix incompatible vectors.
- missing uncached model artifacts fail clearly offline and never trigger silent
  fallback.
- multi-vault vector records do not collide.
- stale vectors are deleted, replaced, or tombstoned so they cannot appear
  fresh.
- no Vault content is mutated.
- `vg search`, graph traversal, answers, context packs, MCP, and HTTP remain out
  of scope.

## 16. Implementation Planning Notes

The implementation plan should be sliced in this order:

1. Extend contracts and tests for chunk listing and vector manifest freshness.
2. Implement `FastEmbedTextEmbeddings`, model artifact/cache validation, and CPU
   throughput tuning config.
3. Implement Chroma behind `VectorStore`.
4. Implement `VectorIndexer` planning with an in-memory store fake.
5. Implement `VectorIndexer` apply with `TextEmbeddings`.
6. Wire `IndexService`, `CatalogService`, `vg index`, and `vg status`.
7. Add failure recovery and read-only boundary tests.
8. Run full static and test verification.

This order keeps the stable interfaces first, then adds backend details, then
opens user-visible status. It matches Vault Graph's preference for simple,
deep, replaceable modules.
