# Phase 2A Retrieval Contract And VectorStore Boundary Design

Status: Draft for user review

Date: 2026-06-08

Scope: Phase 2A only

## 1. Purpose

Phase 2A defines the smallest stable retrieval and vector contracts needed before
Vault Graph adds local vector indexing in Phase 2B and user-visible search in
Phase 2C.

This phase is intentionally contract-only. It should make the next phases easier
to build without prematurely coupling Vault Graph to Chroma, Qdrant, graph
traversal, LLM answer generation, MCP, HTTP, or CLI search surfaces.

The design follows the project boundary:

- Vault remains the durable source of truth.
- Vault Graph state remains read-only and rebuildable.
- Vector search returns semantic candidates, not final evidence.
- Metadata resolution remains the authority for document and chunk evidence.
- Retrieval policy remains outside `VectorStore`.

## 2. Non-Goals

Phase 2A must not implement:

- Chroma collections
- Qdrant support
- vector indexing from real Vault chunks
- `vg search`
- `vg ask`
- `vg status` vector output
- hybrid ranking implementation
- keyword search implementation
- graph extraction
- graph traversal
- context packs
- MCP or HTTP serving
- LLM answer generation

Those belong to later slices. Phase 2A should only define contracts and
deterministic contract tests.

## 3. Recommended Direction

Use the contract-only approach.

Phase 2A introduces:

- `TextEmbeddings` contract
- `EmbeddingModelSpec` metadata
- `VectorStore` contract
- `VectorHit` and vector manifest record shapes
- graph-ready retrieval result shapes
- deterministic test-only `TextEmbeddings` implementation and in-memory vector store
- contract tests that future Chroma and Qdrant implementations must satisfy

This gives Vault Graph a deep, narrow boundary: consumers can depend on simple
interfaces while embedding generation, vector storage, and backend replacement
stay hidden.

## 4. Responsibility Map

| Component | Owns | Must Not Own |
| --- | --- | --- |
| `VaultCatalog` | registered Vault identity, active Vault, root path resolution | derived index state, retrieval policy |
| `QueryScope` | selected Vault IDs and content scopes | candidate ranking, backend filtering policy beyond scope fields |
| `MetadataStore` | document identity, chunk identity, evidence resolution, source hashes, metadata revision | embedding generation, vector similarity, durable semantic truth |
| `TextEmbeddings` | converting text into embedding vectors under one model spec | storage, search, evidence resolution, ranking |
| `EmbeddingModelSpec` | model name, model version, dimensions, spec version | backend choice, ranking policy, Vault identity |
| `VectorStore` | persisted embeddings, vector revision state, filtered semantic candidate lookup | chunk text authority, path authority, evidence authority, hybrid ranking, graph relationships |
| `RetrievalResult` contract | final graph-ready result shape after evidence resolution | vector backend behavior, global backend scores, ranking algorithm |
| `HybridRetriever` | Phase 2C candidate merge, dedupe, ranking, warnings, evidence resolution | Phase 2A implementation |
| `GraphStore` | Phase 3 relationship candidates | Phase 2A implementation |

## 5. Architecture

Phase 2A defines the boundary, not the runtime flow.

```text
Phase 2A contracts

TextEmbeddings
  -> EmbeddingVector
  -> VectorStore
  -> VectorHit

MetadataStore
  -> resolve_chunk_evidence(...)

Retrieval result contracts
  -> EvidenceReference
  -> RetrievalSignal
  -> RetrievalWarning
  -> RetrievalResult
```

Phase 2B uses these contracts to build real vector indexing:

```text
MetadataStore chunks
  -> TextEmbeddings
  -> VectorStore.apply_vector_revision(...)
```

Phase 2C uses these contracts to build user-visible search:

```text
query text
  -> TextEmbeddings
  -> VectorStore.search(...)
  -> keyword candidates
  -> HybridRetriever
  -> MetadataStore.resolve_chunk_evidence(...), scoped by `vault_id`
  -> RetrievalResult
```

Phase 3 adds graph candidates to the same result contract:

```text
GraphStore relationship candidates
  -> HybridRetriever
  -> RetrievalResult.signals[kind="graph"]
```

## 6. Package Layout

Use precise modules that match the existing Phase 1 style.

```text
src/vault_graph/
  embeddings/
    __init__.py
    text_embeddings.py
  retrieval/
    __init__.py
    retrieval_result.py
  storage/
    interfaces/
      vector_store.py

tests/
  fakes/
    deterministic_text_embeddings.py
    in_memory_vector_store.py
  test_text_embeddings_contract.py
  test_vector_store_contract.py
  test_retrieval_result_contract.py
```

Rationale:

- `text_embeddings.py` owns the embedding lifecycle contract.
- `vector_store.py` follows the existing `metadata_store.py` interface pattern.
- `retrieval_result.py` owns result shapes only, not search execution.
- test fakes stay out of production code until a production feature needs them.

Avoid module names such as `utils.py`, `helpers.py`, `manager.py`, or generic
shared buckets.

## 7. Embedding Contract

### 7.1 EmbeddingModelSpec

`EmbeddingModelSpec` is immutable metadata that makes vectors comparable and
rebuildable.

Required fields:

- `model_name`
- `model_version`
- `dimensions`
- `spec_version`

Optional future fields may include normalization and distance metric policy, but
Phase 2A should not add them unless needed by the first local vector backend.

`EmbeddingModelSpec` is not a backend configuration object. It does not name
Chroma, Qdrant, filesystem paths, network endpoints, ranking weights, or
retrieval modes.

### 7.2 EmbeddingInput

`EmbeddingInput` represents one text item to embed.

Required fields:

- `input_id`
- `text`

Rules:

- `input_id` must be unique within one embedding call.
- `input_id` is a batch correlation key, not durable Vault identity.
- Phase 2B indexers must join embedding output back to `(vault_id, document_id,
  chunk_id)` before creating `VectorEmbeddingRecord`.
- `TextEmbeddings` implementations remain Vault-agnostic and must not interpret
  Vault IDs, paths, or content scopes.

### 7.3 EmbeddingVector

`EmbeddingVector` is the output of `TextEmbeddings`.

Required fields:

- `input_id`
- `values`
- `model_spec`

Rules:

- `len(values)` must equal `model_spec.dimensions`.
- vectors must not carry Vault paths, chunk text, or evidence fields.
- vectors may be produced in batches, but output order must preserve input order
  or include enough `input_id` data to restore it.

### 7.4 TextEmbeddings

`TextEmbeddings` converts text into embedding vectors.

Expected protocol:

```python
class TextEmbeddings(Protocol):
    def model_spec(self) -> EmbeddingModelSpec: ...

    def embed(self, inputs: tuple[EmbeddingInput, ...]) -> tuple[EmbeddingVector, ...]: ...
```

Rules:

- `TextEmbeddings` output must use exactly the implementation's
  `EmbeddingModelSpec`.
- empty input returns an empty tuple.
- dimension mismatch is a `TextEmbeddings` contract error, not a retriever concern.
- `TextEmbeddings` implementations must not write Vault files.
- `TextEmbeddings` implementations must not write vector store state directly.
- `TextEmbeddings` implementations must not decide retrieval ranking.

## 8. VectorStore Contract

`VectorStore` stores embeddings and returns semantic candidates. It is a
candidate provider, not a retrieval engine.

### 8.1 VectorEmbeddingRecord

`VectorEmbeddingRecord` is the record accepted by `VectorStore`.

Required fields:

- `vector_id`
- `vault_id`
- `document_id`
- `chunk_id`
- `content_scope`
- `embedding`
- `metadata_index_revision`
- `vector_index_revision`

Rules:

- `vault_id`, `document_id`, and `chunk_id` are required for every record.
- `content_scope` is required and must be derived from the metadata document
  path using the active `QueryScope` content-scope vocabulary.
- `content_scope` is filter metadata, not user evidence.
- content-scope matching uses same-or-child semantics: a query for `wiki`
  includes records scoped to `wiki/systems`, while a query for `wiki/systems`
  does not include a broader `wiki` record.
- `vector_id` must be stable for `(vault_id, chunk_id, embedding.model_spec)`.
- `embedding.model_spec.dimensions` must match the vector length.
- `metadata_index_revision` records which metadata projection the embedding came
  from.
- `vector_index_revision` records the vector projection revision being written.

The vector store may keep internal backend metadata and source chunk hashes for
stale detection, but those fields are not user evidence and must not replace
`MetadataStore` resolution.

### 8.2 VectorHit

`VectorHit` is the only normal search output from `VectorStore`.

Required fields:

- `vector_id`
- `vault_id`
- `document_id`
- `chunk_id`
- `content_scope`
- `score`
- `rank`
- `embedding_spec`
- `metadata_index_revision`
- `vector_index_revision`
- `backend`

Rules:

- `VectorHit` must not include chunk text.
- `VectorHit` must not include final title, summary, path, anchor, or rendered
  evidence.
- `content_scope` may be returned only as filter metadata.
- `score` is backend-local and must not be treated as comparable to keyword or
  graph scores.
- `rank` is local to the vector result set.
- callers must resolve `document_id` and `chunk_id` through `MetadataStore`
  before presenting a normal result to users.

This resolves the possible ambiguity in `docs/SPEC.md`: vector stores may keep
metadata needed for freshness checks, but user-facing evidence fields are
resolved from `MetadataStore`, not trusted from vector hits.

### 8.3 VectorQuery

`VectorQuery` describes a semantic lookup.

Required fields:

- `query_vector`
- `scope`
- `limit`
- `embedding_spec`

Rules:

- `scope` is a `QueryScope`.
- default scope handling belongs to application services, not `VectorStore`.
- `VectorStore` must filter by `scope.vault_ids` and `scope.content_scopes`.
- scope filtering must happen before the final `limit` is applied. If a backend
  cannot push down all scope filters, the adapter must overfetch and post-filter
  before returning hits.
- content-scope filtering must use the same same-or-child rule as metadata
  indexing so narrower policy scopes and broader Vault scopes stay consistent.
- `VectorStore` must not treat identical paths from different Vaults as the same
  item.
- multiple Vault IDs are allowed only because `QueryScope` explicitly names
  them.
- cross-vault graph relationships are not inferred by vector search.

### 8.4 VectorStore Protocol

Expected protocol:

```python
class VectorStore(Protocol):
    def apply_vector_revision(
        self,
        *,
        vector_index_revision: str,
        records: tuple[VectorEmbeddingRecord, ...],
        tombstones: tuple[VectorTombstone, ...],
    ) -> None: ...

    def search(self, query: VectorQuery) -> tuple[VectorHit, ...]: ...

    def health(self) -> StoreHealth: ...

    def export_manifest(self, scope: QueryScope) -> tuple[VectorManifestRecord, ...]: ...
```

Rules:

- `apply_vector_revision` writes only Vault Graph derived state.
- stale records are removed or tombstoned by `chunk_id` plus `vault_id`.
- `search` returns only scoped semantic candidates.
- `health` uses the existing `StoreHealth` shape unless implementation evidence
  shows it is insufficient.
- `export_manifest` returns inspectable projection metadata, not source truth.

## 9. MetadataStore Evidence Resolution Boundary

Phase 2A must add a deep evidence-resolution boundary to `MetadataStore` before
retrieval result assembly depends on it.

Expected protocol addition:

```python
class MetadataStore(Protocol):
    def resolve_chunk_evidence(
        self,
        *,
        vault_id: str,
        document_id: str,
        chunk_id: str,
    ) -> EvidenceReference | None: ...
```

Rules:

- the method validates that `vault_id`, `document_id`, and `chunk_id` refer to
  the same current, non-tombstoned metadata records.
- evidence resolution must also verify that the chunk path matches the resolved
  document path; malformed rows with matching IDs but mismatched paths must not
  become normal evidence.
- the method joins document-level evidence such as `raw_sha256` and
  `vault_revision` with chunk-level evidence such as section, anchor, and chunk
  hash.
- mismatched IDs must not produce normal evidence.
- missing or stale records return `None` or a typed diagnostic that retrieval can
  convert into a warning.
- `HybridRetriever` must not assemble evidence by learning metadata table
  internals.

## 10. Retrieval Result Contract

Phase 2A defines a graph-ready result shape before graph storage exists.

### 10.1 EvidenceReference

`EvidenceReference` is attached only after metadata resolution.

Required fields:

- `vault_id`
- `document_id`
- `chunk_id`
- `path`
- `section`
- `anchor`
- `content_hash`
- `raw_sha256`
- `metadata_index_revision`
- `vault_revision`

Rules:

- `path`, `section`, `anchor`, hashes, and revision data come from
  `MetadataStore.resolve_chunk_evidence(...)`.
- unresolved candidates cannot become normal `RetrievalResult` evidence.
- missing evidence is represented as a warning or diagnostic candidate.

### 10.2 RetrievalSignal

`RetrievalSignal` explains why a result was found.

Required fields:

- `kind`
- `source_id`
- `rank`
- `score`
- `backend`
- `index_revision`
- `explanation`

Allowed initial `kind` values:

- `keyword`
- `vector`
- `graph`

Phase 2A only defines these values. Phase 2C produces `keyword` and `vector`
signals. Phase 3 may produce `graph` signals.

Rules:

- signal scores are not globally comparable.
- backend and revision metadata belongs on signals and evidence, not on the
  result as a single global value.
- ranking fusion must preserve signal-specific explanations.
- vector signals refer to `VectorHit.vector_id`.
- graph signals remain unused until `GraphStore` exists.

### 10.3 RetrievalWarning

`RetrievalWarning` captures degraded result quality.

Required fields:

- `code`
- `message`
- `severity`

Recommended initial warning codes:

- `missing_evidence`
- `stale_metadata`
- `stale_vector`
- `model_spec_mismatch`
- `scope_excluded`
- `backend_unhealthy`
- `graph_unavailable`

### 10.4 RetrievalResult

`RetrievalResult` is the resolved, user-facing result shape.

Required fields:

- `result_id`
- `vault_id`
- `kind`
- `title`
- `summary`
- `rank`
- `evidence`
- `signals`
- `relationship_status`
- `warnings`
- `store_revisions`

Rules:

- `evidence` must be non-empty for normal rendered results.
- `relationship_status` may be `not_applicable` before graph search exists.
- result identity must be Vault-scoped.
- summaries must be derived from resolved evidence, not vector store payloads.
- top-level `rank` is the final ordering chosen by the retrieval layer.
- there is no top-level backend score because signal scores are not globally
  comparable.
- backend and index revision details must remain attached to `signals`,
  `evidence`, and `store_revisions`.
- the internal Python contract should keep `store_revisions` immutable, using
  `tuple[StoreRevision, ...]` or an equivalent immutable record shape rather
  than a mutable mapping.
- warnings travel with the result and must not be hidden by renderers.
- `RetrievalResult` must not globally require every evidence item to have the
  same `vault_id` as the result, because later graph relationship results may
  use separate source, target, and evidence Vault IDs.
- Normal vector-backed document result assembly still must verify that
  `VectorHit.vault_id`, `document_id`, and `chunk_id` match the resolved
  `EvidenceReference` before rendering.

## 11. Multi-Vault Consistency Rules

Phase 2A must preserve the multi-vault model introduced in Phase 1.

Rules:

- every vector record includes `vault_id`.
- every vector hit includes `vault_id`.
- every vector record and hit includes `content_scope` filter metadata.
- every retrieval result includes `vault_id`.
- every evidence reference includes `vault_id`.
- dedupe keys include `vault_id`.
- identical relative paths from different Vaults are different records.
- default query scope is resolved before calling `VectorStore`.
- `VectorStore` receives an explicit `QueryScope`; it does not read
  `VaultCatalog`.
- `VectorStore` must not treat `QueryScope.include_cross_vault` as graph
  traversal permission.
- cross-vault graph traversal remains Phase 3 work.

This keeps `VaultCatalog` as the only authority for registered Vault roots while
allowing vector backends to filter safely by Vault identity.

## 12. Error Handling

Phase 2A should fail loudly at contract boundaries.

Contract errors:

- embedding vector dimensions do not match model spec dimensions
- vector record model spec does not match collection model spec
- search query model spec is incompatible with stored vectors
- `QueryScope` has no Vault IDs
- vector record is missing `vault_id`, `document_id`, `chunk_id`, or
  `content_scope`
- vector search returns a candidate outside `QueryScope`
- vector hit IDs do not match resolved metadata evidence
- vector backend reports incompatible schema

Degraded retrieval warnings:

- vector backend is unhealthy
- metadata evidence cannot be resolved
- vector revision is stale against metadata revision
- graph signal is requested before graph storage exists

Implementation guidance:

- use explicit project errors when a contract is violated.
- use `RetrievalWarning` when a candidate can be explained but should not be
  rendered as normal evidence.
- do not silently fall back to a different embedding model spec.

## 13. Testing Strategy

Phase 2A should be test-driven and deterministic.

### 12.1 TextEmbeddings Tests

Verify:

- empty input returns empty output.
- the deterministic `TextEmbeddings` implementation returns stable vectors.
- all vectors match `EmbeddingModelSpec.dimensions`.
- output records preserve input IDs.
- input IDs are treated as embedding-call correlation keys, not durable Vault
  identity.
- `TextEmbeddings` does not write files.

### 12.2 VectorStore Contract Tests

Use a test-only in-memory vector store to define backend-neutral behavior.

Verify:

- upserted records can be searched by vector query.
- search filters by `QueryScope.vault_ids`.
- search filters by `QueryScope.content_scopes` before applying `limit`.
- `QueryScope.include_cross_vault` does not grant graph traversal behavior in
  `VectorStore`.
- same relative content from different Vault IDs does not collide.
- stale records can be tombstoned by `vault_id` and `chunk_id`.
- dimension mismatch fails loudly.
- model spec mismatch fails loudly.
- vector hits omit path, text, title, summary, and final evidence fields.
- health reports backend name, schema version, compatibility, and message.
- manifest export is stable and inspectable.

### 12.3 Retrieval Contract Tests

Verify:

- normal results require evidence.
- `EvidenceReference` is assembled only through
  `MetadataStore.resolve_chunk_evidence(...)`.
- `VectorHit.vault_id`, `document_id`, and `chunk_id` must match resolved
  metadata evidence before becoming a normal result.
- vector signals can be attached without graph signals.
- graph signal kind is accepted but not produced by Phase 2A runtime.
- warnings remain visible on result records.
- result identity and dedupe examples are Vault-scoped.
- result-level backend scores are not exposed; backend score metadata stays on
  `RetrievalSignal`.

### 12.4 Static Checks

Phase 2A should pass:

```bash
pytest -q
ruff check src tests
mypy src
```

No new runtime dependency should be required for Phase 2A.

## 14. Acceptance Criteria

Phase 2A is complete when:

- `TextEmbeddings` and `EmbeddingModelSpec` contracts are implemented.
- vector store protocol and record shapes are implemented.
- vector records and hits carry `content_scope` filter metadata.
- vector search enforces both Vault ID and content-scope filtering.
- metadata evidence can be resolved through one deep `MetadataStore` boundary.
- graph-ready retrieval result shapes are implemented.
- deterministic test `TextEmbeddings` implementation exists for contract tests.
- in-memory test vector store exists for contract tests.
- tests prove multi-vault identity is preserved.
- tests prove content-scope filtering is preserved.
- tests prove vector hits are not evidence authority.
- tests prove vector hit IDs match resolved metadata evidence before result
  rendering.
- tests prove model spec and dimension mismatches fail loudly.
- documentation states that Chroma and Qdrant must implement the same
  `VectorStore` contract.
- no Vault files are mutated by Phase 2A tests.
- no user-facing search command is introduced.
- no vector backend status is added to `vg status`.

## 15. Scale-Up Path

The scale-up path should not change the public contracts.

Phase 2B:

- implement Chroma as a `VectorStore`.
- build embeddings from `MetadataStore` chunks.
- add vector projection freshness to indexing and status.

Phase 2C:

- implement keyword candidate lookup.
- call `VectorStore.search`.
- merge candidates in `HybridRetriever`.
- resolve evidence through `MetadataStore`.
- expose `vg search`.

Phase 3:

- implement `GraphStore`.
- add graph signals to the same retrieval result contract.
- keep graph traversal opt-in for cross-vault relationships.

Later scale-up:

- implement Qdrant behind the same `VectorStore` protocol.
- preserve the same record shape, scope filtering, model spec validation, and
  evidence-resolution boundary.

## 16. Design Risks

Risk: `VectorStore` becomes too smart.

Mitigation: keep `VectorHit` small and require `MetadataStore` evidence
resolution before rendering.

Risk: backend scores are treated as globally comparable.

Mitigation: record local scores and ranks on `RetrievalSignal`, omit top-level
backend scores from `RetrievalResult`, and let `HybridRetriever` own rank-based
fusion in Phase 2C.

Risk: multi-vault identity drifts back to path-only assumptions.

Mitigation: require `vault_id` on all vector, evidence, and retrieval records;
add contract tests with duplicate paths across Vault IDs.

Risk: content-scope filtering becomes a late retrieval patch.

Mitigation: require `content_scope` filter metadata in vector records and prove
`VectorStore.search(...)` applies `QueryScope.content_scopes` before `limit`.

Risk: Phase 2A accidentally becomes Phase 2B.

Mitigation: keep Chroma, vector indexing, CLI status, and search out of scope.

Risk: graph-ready fields imply graph behavior exists.

Mitigation: allow graph signal types in the result contract, but do not produce
graph candidates until `GraphStore` exists.

## 17. Final Decision

Proceed with Phase 2A as a contract-only slice.

The design should optimize for deep modules, low complexity, and future
changeability:

- `TextEmbeddings` hides model mechanics.
- `VectorStore` hides vector backend mechanics.
- `MetadataStore` remains evidence authority.
- retrieval result contracts prepare for graph signals without requiring graph
  implementation.
- future Chroma and Qdrant backends plug into the same boundary.
