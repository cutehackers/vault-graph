# Phase 2C Evidence-First Keyword And Vector Search Design

Status: Draft for implementation planning

Date: 2026-06-09

Scope: Phase 2C only

## 1. Purpose

Phase 2C adds the first user-facing search command.

The deliverable is not answer generation, graph traversal, or context-pack
assembly. The deliverable is a read-only search surface that returns ranked,
inspectable Vault evidence from keyword and vector signals.

Phase 2C must preserve Vault Graph's core values:

- Vault remains the durable source of truth.
- Search reads existing projections and does not mutate Vault or Vault Graph
  index state.
- Every normal result resolves through `MetadataStore` before rendering.
- Keyword and vector stores return candidates, not authority.
- Multi-vault identity stays explicit.
- The design is simple now and can accept graph signals later without changing
  the search result contract.

## 2. Non-Goals

Phase 2C must not implement:

- `vg ask`
- LLM answer generation
- context packs
- graph extraction
- graph traversal
- decision traces
- MCP serving
- HTTP serving
- Qdrant support
- non-Markdown readers
- chunker migration
- automatic indexing during search
- embedding model downloads during search
- writes back to Vault

Those belong to later phases or future TODOs. Phase 2C should expose only
evidence search.

## 3. Accepted Decisions

Phase 2C follows these accepted decisions.

1. Evidence chunk is the canonical search result unit.

   A normal result preserves full resolved evidence identity
   `(vault_id, document_id, chunk_id)` through `MetadataStore`. Document, page,
   source, and section displays are grouping or rendering views over chunk
   evidence.

2. Keyword lookup is metadata-owned.

   The local implementation should use SQLite FTS5 or an equivalent rebuildable
   projection over current chunks and document metadata. `RetrievalService` must
   not query SQLite tables directly.

3. Vector lookup remains semantic-candidate-only.

   `VectorStore.search` returns `VectorHit` metadata only. The retrieval layer
   resolves paths, anchors, chunk text, warnings, and revisions through
   `MetadataStore`.

4. Fusion is rank-based.

   Phase 2C uses reciprocal-rank-style fusion over per-signal ranks. It must not
   compare keyword scores and vector distances as one global relevance scale.

5. Search degrades visibly.

   Metadata and keyword projection are required. Vector is optional at query
   time: missing Chroma state, stale vector projection, incompatible vector
   schema, or unavailable local model artifacts degrade to keyword-only search
   with top-level warnings.

6. `vg search` is read-only.

   Search does not run indexing, create schemas, create Chroma collections,
   update vector status, download models, or write derived state. Recovery
   guidance points the user to `vg index`.

## 4. Responsibility Map

| Component | Owns | Must Not Own |
| --- | --- | --- |
| `VaultCatalog` | registered Vault IDs, active Vault, enabled Vault expansion | search ranking or derived records |
| `QueryScope` | selected Vault IDs and content scopes | graph traversal policy |
| `MetadataStore` | chunk identity, document identity, evidence resolution, chunk text authority | vector similarity, keyword ranking policy, durable truth |
| `KeywordIndex` | metadata-owned lexical candidate lookup over current chunks | evidence authority, final rendering, graph relationships |
| `TextEmbeddings` | query text embedding under one `EmbeddingModelSpec` | storage, ranking, evidence resolution |
| `VectorStore` | filtered semantic candidate lookup | snippets, path/title authority, chunk text, fusion policy |
| `RetrievalService` or `HybridRetriever` | query normalization, candidate lookup, merge, dedupe, rank fusion, evidence resolution, warnings, final response | Vault mutation, backend-native table queries |
| CLI | argument parsing and output rendering | direct SQLite/Chroma access |

This keeps Phase 2C as a few deep modules: candidate stores stay simple, and the
retrieval service owns the policy that combines them.

## 5. Architecture

```text
vg search "query"
  -> CatalogService loads VaultCatalog and state paths
  -> CLI resolves requested QueryScope
  -> RetrievalService.search(SearchRequest)
      -> expand requested scope into per-Vault actual scopes
      -> metadata and keyword readiness checks
      -> normalize query
      -> KeywordIndex.search(...) per actual scope
      -> optional no-download TextEmbeddings query vector
      -> optional VectorStore.search(...) per actual scope
      -> merge by (vault_id, chunk_id)
      -> rank-based fusion
      -> MetadataStore.resolve_chunk_evidence(...)
      -> MetadataStore.resolve_chunk(...) for display text
      -> SearchResponse
  -> CLI renders text or JSON
```

Phase 3 graph candidates join at the candidate merge step. They must produce a
new `RetrievalSignal(kind="graph")`; they must not change evidence identity.

## 6. Data Contracts

### 6.1 KeywordIndex

Phase 2C should add a small protocol:

```python
class KeywordIndex(Protocol):
    def search(self, query: KeywordQuery) -> tuple[KeywordHit, ...]: ...

    def health(self) -> StoreHealth: ...
```

`KeywordIndex` may be implemented by `SQLiteMetadataStore` or by a small adapter
over the same SQLite database. The public boundary should stay logical and not
return SQLite rows.

### 6.2 KeywordQuery

Required fields:

- `query_text`
- `scope`
- `limit`

Rules:

- The query text is already normalized by the retrieval service.
- `limit` is the candidate limit, not the final response limit.
- The index applies `QueryScope.vault_ids` and `QueryScope.content_scopes`
  before limiting results.

### 6.3 KeywordHit

Required fields:

- `vault_id`
- `document_id`
- `chunk_id`
- `rank`
- `score`
- `backend`
- `index_revision`
- `matched_fields`

Rules:

- `rank` is 1-based and backend-local.
- `score` is diagnostic only.
- `matched_fields` may include `chunk_text`, `section`, `path`, `title`, or
  projected frontmatter field names.
- `KeywordHit` must not be rendered as final evidence without
  `MetadataStore` resolution.

### 6.4 SearchRequest

Required fields:

- `query_text`
- `requested_scope`
- `actual_scopes`
- `limit`
- `output_format`

Rules:

- Empty or whitespace-only queries are invalid.
- `limit` must be positive. The CLI default is `10`.
- `output_format` starts with `text` and `json`.
- `actual_scopes` are per-Vault scopes resolved through `VaultCatalog`.
- Candidate stores receive actual scopes, not an all-vault union scope.

### 6.5 SearchResponse

Required fields:

- `query_text`
- `requested_scope`
- `actual_scopes`
- `limit`
- `result_count`
- `candidate_count`
- `dropped_candidate_count`
- `results`
- `warnings`
- `degraded`
- `store_revisions`
- `generated_at`

Rules:

- `results` contains `RetrievalResult` records.
- `warnings` contains query-wide warning records with structured attribution.
- `degraded=True` means the search completed without all configured signals.
- Store revisions include at least metadata, keyword, and vector when available,
  keyed by Vault or actual scope when the response spans multiple Vaults.
- `result_id` values are search-output identifiers derived from Vault-scoped
  candidate identity, such as `(vault_id, chunk_id)` plus response rank or query
  context. They are not durable Vault IDs.
- If the existing `RetrievalSignal.source_id` field is reused, the value must
  include or derive from Vault-scoped candidate identity. A source ID based on a
  path, document ID, or chunk ID without `vault_id` is not acceptable for
  multi-vault output.

The existing `RetrievalResult` remains the per-result contract. Phase 2C adds a
top-level response contract because degraded search is often query-wide, not
result-specific.

Warning records used by search must carry structured attribution:

- `code`
- `message`
- `severity`
- `affected_vault_ids`
- optional `document_id`
- optional `chunk_id`
- optional `source_id`

This can extend the existing `RetrievalWarning` contract or define a
search-specific warning type. The implementation plan should choose the smaller
change after checking current tests, but multi-vault JSON output must not leave
Vault-scoped warnings ambiguous.

## 7. Keyword Projection Design

The local keyword projection should live with the metadata backend because it is
derived from current chunks and document metadata.

Phase 2C fixes the local ownership rule: keyword projection is a metadata
subprojection.

Recommended SQLite implementation:

- Add an FTS5 table or equivalent projection for current chunks.
- Store `vault_id`, `document_id`, `chunk_id`, path, section, heading text, and
  searchable metadata fields.
- Update or rebuild keyword rows in the same SQLite transaction that writes
  documents and chunks.
- Remove keyword rows for tombstoned documents.
- Keep keyword projection revision aligned with metadata index revision.
- If keyword projection update fails during indexing, fail the metadata revision
  instead of publishing inconsistent metadata and keyword state.

Search must open this projection read-only. If the table is missing or
incompatible, search fails with a clear `vg index` recovery hint instead of
creating schema during search.

For Korean and English content, Phase 2C should not introduce a complex
language-analysis subsystem. SQLite FTS5 with a Unicode-aware tokenizer is a
reasonable MVP. Better tokenization can replace the local keyword adapter later
without changing `KeywordIndex`.

## 8. Vector Query Design

Vector query uses the Phase 2A and Phase 2B contracts:

1. Check vector backend health and schema compatibility.
2. Check selected-scope vector freshness through a read-only search-readiness
   boundary.
3. Ensure the configured local embedding model artifact is already available
   through a no-download embedding availability check.
4. Embed the query text with `TextEmbeddings`.
5. Call `VectorStore.search(VectorQuery(...))`.

Phase 2C must add one of these explicit embedding availability contracts before
query embedding is wired into search:

- `TextEmbeddings.artifact_status()`
- `TextEmbeddings.can_embed_without_download()`
- `FastEmbedTextEmbeddingsConfig(local_files_only=True)` plus a health check

The chosen contract must prove that search can decide whether query embedding is
possible without invoking a download or writing model cache files.

Search-time embedding must not download model artifacts. If the artifact is not
available locally, the response degrades to keyword-only with a warning such as
`embedding_model_unavailable`.

Vector lookup is skipped, with a top-level warning, when:

- `VectorStore` is not configured
- Chroma state is missing
- vector schema is incompatible
- vector projection is stale for the selected scope
- embedding model artifact is unavailable
- query embedding fails

If vector lookup is skipped and keyword evidence exists, `vg search` exits `0`
and prints the warning. If keyword projection is also unavailable, search fails.

`RetrievalService` must depend on a read-only `SearchReadiness` or
projection-status boundary for vector freshness. It must not import
`LocalVectorStatusStore` directly and must not duplicate `IndexService.status()`
logic inside retrieval.

## 9. Candidate Fusion

Phase 2C should use reciprocal-rank-style fusion:

```text
fused_score = sum(signal_weight / (rank_constant + signal_rank))
```

Defaults:

- `keyword` weight: `1.0`
- `vector` weight: `1.0`
- `rank_constant`: `60`
- final `limit`: `10`
- candidate pool: at least `max(limit * 4, 20)` per signal

Rules:

- Merge candidates by `(vault_id, chunk_id)`.
- Preserve every contributing signal.
- Raw keyword and vector scores remain signal metadata only.
- Sort by fused score descending, then best signal rank ascending, then
  `vault_id`, path, and `chunk_id`.
- Drop candidates that cannot resolve evidence and add a response warning.
- Attach result-level stale warnings when a vector hit revision differs from the
  resolved evidence revision.

This keeps ranking deterministic and easy to replace later.

## 10. Evidence Rendering

Normal result assembly uses `MetadataStore` twice:

1. `resolve_chunk_evidence(vault_id, document_id, chunk_id)` returns authority
   fields such as path, anchor, hashes, and metadata revision.
2. `resolve_chunk(vault_id, chunk_id)` returns current chunk text and section
   data for display snippets or summaries.

Rules:

- `RetrievalResult.evidence` must contain resolved evidence.
- `RetrievalResult.kind` should be `evidence_chunk` for Phase 2C.
- Title rendering may use path plus section heading.
- Summary rendering may use a bounded excerpt from resolved chunk text.
- Document grouping is a renderer concern. It groups by `(vault_id,
  document_id)`.
- Search results must always show `vault_id` when more than one Vault was
  selected.

If evidence resolution fails, the candidate is not returned as a normal result.
Returning a result with unsupported evidence would violate the project value of
provenance over fluency.

## 11. CLI Surface

Phase 2C adds:

```bash
vg search "GraphRAG"
vg search --vault-id main "GraphRAG"
vg search --all-vaults "GraphRAG"
vg search --limit 20 --format json "GraphRAG"
```

Rules:

- Active Vault is the default scope.
- `--vault-id` and `--all-vaults` are mutually exclusive.
- `--limit` must be positive and defaults to `10`.
- `--format` supports `text` and `json`.
- Human output prints resolved Vault IDs, warnings, and ranked evidence.
- JSON output uses `SearchResponse` fields and does not invent a different
  contract.

Exit codes:

- `0`: search completed, including degraded keyword-only search with warnings
- `1`: invalid query, invalid scope, missing required metadata or keyword
  projection, schema incompatibility, unsupported format, or other search
  failure

No-results is not an error when projections are healthy.

## 12. Multi-Vault Rules

Multi-vault behavior is mandatory.

Rules:

- Default search uses the active Vault only.
- `--vault-id ID` searches exactly one Vault.
- `--all-vaults` expands to explicit enabled Vault IDs, then to per-Vault
  actual scopes before candidate stores run.
- Actual scope resolution follows the Phase 2B rule: use the narrower of the
  requested scope and catalog entry scope when one contains the other; skip
  disjoint scope pairs.
- Candidate merge identity is `(vault_id, chunk_id)`. Resolved evidence identity
  is `(vault_id, document_id, chunk_id)`.
- Document grouping is `(vault_id, document_id)`.
- Result IDs must include `vault_id` or otherwise be derived from
  Vault-scoped identity.
- Identical relative paths or headings across Vaults must not collide.
- Warnings include the affected Vault ID when the condition is Vault-scoped.
- Store revisions include Vault or actual-scope attribution in multi-vault
  responses.
- Search grouping must use resolved evidence/result fields. It must not call
  document-level resolution by `document_id` alone.
- `include_cross_vault` remains inert for graph traversal because Phase 2C has
  no graph traversal.

## 13. Error And Warning Policy

Fatal errors are command diagnostics, not successful `SearchResponse` warnings.

Fail search:

- metadata store is missing
- metadata schema is incompatible
- keyword projection is missing or incompatible
- query is empty
- scope is invalid
- requested output format is unsupported

Degrade with warning:

- vector store is missing
- vector schema is incompatible
- vector projection is stale
- embedding model artifact is unavailable locally
- query embedding fails
- vector candidates cannot resolve evidence but keyword results remain

Return zero results:

- projections are healthy but no keyword or vector candidate resolves to
  evidence

Recommended degraded response warning codes:

- `vector_unavailable`
- `vector_stale`
- `embedding_model_unavailable`
- `degraded_keyword_only`
- `missing_evidence`
- `truncated_candidates`
- `empty_index`

Recommended fatal diagnostic codes:

- `metadata_unavailable`
- `keyword_index_unavailable`
- `unsupported_format`

## 14. Read-Only Boundary

`vg search` must not write:

- Vault files
- Vault Git metadata
- metadata SQLite schema or rows
- keyword FTS schema or rows
- Chroma collections or records
- vector status records
- embedding model cache files

The command may read:

- Vault Graph config
- metadata SQLite state
- keyword projection state
- Chroma vector state
- vector status or manifest state
- already cached local model artifacts

This is stricter than indexing. `vg index` may build derived projections;
`vg search` must only inspect them.

## 15. Scale-Up Path

Phase 2C should make scale-up backend replacement straightforward:

- `KeywordIndex` can move from SQLite FTS5 to Postgres full-text search without
  changing `RetrievalService`.
- `VectorStore` can move from Chroma to Qdrant without changing evidence
  resolution.
- Graph retrieval can add `GraphStore` candidates as another signal without
  changing the canonical evidence chunk result unit.
- Reranking can replace reciprocal-rank fusion behind retrieval policy without
  changing store contracts.

The stable contract is:

- `QueryScope`
- `KeywordIndex`
- `VectorStore`
- `MetadataStore.resolve_chunk_evidence(...)`
- `RetrievalResult`
- `SearchResponse`

## 16. Testing Strategy

Phase 2C should be test-driven.

### 16.1 KeywordIndex Tests

Verify:

- query returns current chunk candidates
- tombstoned documents are not returned
- Vault ID filtering works before limits
- content-scope filtering works before limits
- duplicate paths across Vaults do not collide
- schema missing or incompatible health is visible
- backend scores are not treated as final evidence

### 16.2 RetrievalService Tests

Verify:

- empty query fails
- requested all-vault scope expands into per-Vault actual scopes
- keyword-only search returns evidence chunks
- vector-only candidates do not render without metadata evidence
- keyword and vector signals merge by `(vault_id, chunk_id)`
- reciprocal-rank-style fusion produces deterministic order
- vector readiness is checked through a read-only boundary
- vector stale state degrades to keyword-only with a top-level warning
- missing local model artifact degrades to keyword-only without download
- missing keyword projection fails with `vg index` recovery guidance
- store revisions are present in the response
- multi-vault store revisions and warnings are Vault-attributed
- result IDs and signal source IDs are Vault-scoped
- result warnings distinguish stale vector evidence from query-wide warnings

### 16.3 CLI Tests

Verify:

- `vg search "query"` uses active Vault by default
- `--vault-id` selects one Vault
- `--all-vaults` selects all enabled Vaults
- `--vault-id` plus `--all-vaults` fails
- `--limit` controls final result count
- `--format json` returns the response contract
- degraded keyword-only search exits `0` with warnings
- missing required projections exits nonzero

### 16.4 Read-Only Tests

Verify:

- search does not mutate Vault files
- search does not create metadata DB files
- search does not create FTS tables
- search does not create Chroma files or collections
- search does not write vector status
- search does not download model artifacts
- search does not change existing index revisions
- search does not call a write-capable keyword projection path

### 16.5 Multi-Vault Tests

Verify:

- identical relative paths from two Vaults produce separate results
- identical chunk IDs across Vaults do not collide
- dedupe uses `(vault_id, chunk_id)`
- grouping uses `(vault_id, document_id)`
- all-vault search does not widen one Vault with another Vault's content scopes
- `--all-vaults` output includes Vault IDs
- warnings identify affected Vault IDs when applicable

## 17. Implementation Plan Handoff

The implementation plan should be split into small slices:

1. Add `KeywordIndex`, `KeywordQuery`, and `KeywordHit` contracts plus tests.
2. Add local SQLite FTS-backed keyword projection and metadata apply integration.
3. Add per-Vault actual search scope resolution.
4. Add `SearchResponse` and retrieval service fusion tests with fakes.
5. Add read-only `SearchReadiness` and no-download embedding availability.
6. Add vector query integration and degraded-mode handling.
7. Add `vg search` CLI output and read-only tests.
8. Add multi-vault search coverage.

Each slice should preserve the rule that search reads projections and never
mutates Vault or index state.
