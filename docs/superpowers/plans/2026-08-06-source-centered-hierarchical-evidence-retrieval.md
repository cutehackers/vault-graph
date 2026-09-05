# Implementation Plan: Source-Centered Hierarchical Evidence Retrieval

**Status:** Proposed; do not record as an accepted decision until reviewed.

## Goal

Make the final Vault Graph retrieval model source-centered without turning
`chunk` into the canonical knowledge unit:

```text
Vault raw/wiki source
  -> format-neutral structural document
  -> bounded leaf evidence projection
  -> lexical/vector/graph candidate signals
  -> canonical document/Section result
  -> matched evidence spans + bounded context
```

The default knowledge result should be a canonical wiki document or Section
with supporting Evidence references. Leaf chunks remain the internal recall
and evidence-addressing unit. `evidence` and explicit drill-down modes may
still expose leaf results.

## Scope

- Establish a versioned parent-aware retrieval result contract.
- Preserve `MetadataStore.content_blobs` as the single derived plaintext owner.
- Preserve `Vault` as the durable source of truth and registered repositories as
  the current code authority.
- Keep keyword, vector, and graph stores reference-oriented.
- Aggregate matched leaf evidence by a deterministic document/Section parent.
- Make context expansion return resolved Evidence references, not only chunk IDs.
- Add a benchmark that compares full-document, flat-leaf, and hierarchical
  retrieval behavior before changing default ranking semantics.
- Keep Markdown as the only enabled default reader while making Reader
  discovery compatible with PlainText, PDF, and DOCX adapters.
- Keep code retrieval AST/symbol/edge based and separate from document
  Chunking.

## Non-goals

- Do not add Chunking, embeddings, vector storage, or search-result writes to
  `vault-builder`.
- Do not edit, rename, rewrite, delete, or publish files inside `Vault`.
- Do not create a second durable knowledge store in Vault Graph.
- Do not treat LLM-generated summaries, Claims, or Entities as Evidence
  authority.
- Do not apply prose Chunking to source code.
- Do not implement OCR, spreadsheets, slides, images, or audio readers.
- Do not introduce a hosted backend or an LLM dependency for the first
  hierarchical retrieval slice.
- Do not add a user-configurable chunk-size option before benchmark evidence
  shows that it is necessary.
- Do not change the existing AST code projection contract as part of the
  document retrieval migration.

## Final architecture

### Authority and projection boundary

| Layer | Authority and responsibility |
|---|---|
| `Vault/raw` | Immutable source material and original Evidence |
| `Vault/wiki` | Human/agent-reviewed durable compiled knowledge |
| `vault-builder` | Vault structure, provenance, validation, and explicit migration |
| `MetadataStore` | Rebuildable document, parent, leaf text, hash, locator, and revision projection |
| `KeywordIndex` | Rebuildable lexical candidate projection |
| `VectorStore` | Rebuildable semantic candidate projection; no text authority |
| `GraphStore` | Rebuildable entity/relationship projection; Evidence references only |
| Retrieval layer | Candidate fusion, parent grouping, context expansion, and warnings |
| Code projection | Rebuildable AST symbol/edge graph over the registered repository |

`MetadataStore` may cache extracted leaf text because the current accepted
projection contract gives it the single derived plaintext owner. That cache is
not Vault authority: it is valid only with its source hash, locator, parser and
chunker lineage, Vault revision, and metadata revision.

### Retrieval result semantics

The result contract changes by search mode:

- `knowledge`: one result per canonical provenance family and selected
  document/Section parent; `evidence` contains one or more matched leaf
  references, and `context_evidence` contains bounded parent/neighbor refs.
- `evidence`: leaf evidence results remain available for exact drill-down.
- `operating`, `audit`, and `all`: preserve role-aware behavior while using the
  same parent and Evidence reference fields.

The user-facing result is therefore:

```text
canonical document/Section
  + matched Evidence spans
  + parent/neighbor context
  + provenance-family references
  + source and projection revisions
  + freshness and conflict warnings
```

The search limit applies to canonical result containers in `knowledge` mode,
not to the number of leaf hits hidden inside each result. Evidence and context
budgets remain independently bounded.

### Query flow

```text
Query + QueryScope
  -> authority/role and Vault scope filter
  -> keyword/vector/graph leaf candidates
  -> leaf candidate fusion
  -> MetadataStore Evidence resolution
  -> provenance-family selection
  -> document/Section parent grouping
  -> bounded parent/neighbor expansion
  -> source freshness and Evidence validation
  -> canonical result rendering
```

The first implementation may use the existing leaf indexes and group resolved
candidates by parent. A separate coarse parent index or parent-filtered vector
search is an optimization to add only if the benchmark demonstrates a recall,
latency, or scale problem. The authority model does not depend on that
optimization.

## Repo context

The plan is based on:

- `docs/SPEC.md`: read-only/rebuildable boundaries, `MetadataStore` authority,
  current `(vault_id, document_id, chunk_id)` Evidence identity, scope-local
  reconcile, graph boundaries, context packs, and code authority.
- `docs/FEATURES.md`: current `knowledge` search surface, context-pack fields,
  MCP/CLI compatibility, and user-visible warning guarantees.
- `docs/DESIGN.md`: deep-module boundaries, ingestion, storage, retrieval,
  context assembly, and test strategy.
- `docs/CONVENTIONS.md`: module naming, interface-first design, typing, and
  deterministic test rules.
- `docs/TODO.md`: format-neutral Reader adapters and the current
  `document-block-window-v2` / `parent-neighbor-v1` boundary.
- `docs/SEARCH_ARCHITECTURE.md`: current structural Reader -> leaf chunk ->
  metadata/vector -> parent-neighbor flow and its documented limitations.
- `src/vault_graph/ingestion/document_models.py`: immutable source, structural
  block, unit, and format-neutral locator contracts.
- `src/vault_graph/ingestion/document_chunking.py`: current non-overlapping
  `document-block-window-v2` planner.
- `src/vault_graph/ingestion/document_normalizer.py`: document/chunk identity
  and snapshot construction.
- `src/vault_graph/storage/interfaces/metadata_store.py`: metadata-owned text,
  document/chunk resolution, locators, and family Evidence.
- `src/vault_graph/storage/local/sqlite_metadata_store.py`: `metadata-v3`,
  `content_blobs`, chunk metadata, locator persistence, and rebuild boundary.
- `src/vault_graph/storage/local/sqlite_keyword_index.py`: contentless FTS5
  projection over path, section, title, frontmatter, and leaf text.
- `src/vault_graph/retrieval/retrieval_service.py`: candidate fusion, family
  collapse, Evidence resolution, and current context expansion seam.
- `src/vault_graph/retrieval/context_expansion.py`: current bounded
  `parent-neighbor-v1` implementation.
- `src/vault_graph/context/context_pack_builder.py`: current resolved Evidence
  assembly and token-budget behavior.
- `tests/test_retrieval_service_search.py`,
  `tests/test_context_expansion.py`, `tests/test_metadata_indexer.py`,
  `tests/test_vector_indexer.py`, and related store/Reader tests.

`vault-builder` was also inspected. Its existing raw immutability, source
manifest, `canonical_source`, `raw_sha256`, claim provenance, and validation
contracts are sufficient. No `vault-builder` code change is required for this
retrieval architecture. An optional later contract-only change may make
`docx` and `plaintext` explicit `source_kind` values, but it is not a blocker
for search.

## Implementation steps

### 1. Add a deterministic retrieval benchmark before changing defaults

Create `tests/benchmarks/test_hierarchical_retrieval_benchmark.py` and a small
deterministic fixture corpus covering:

- short single-Section wiki pages;
- long decision pages with definitions, exceptions, and trade-offs;
- repeated headings and repeated concepts across pages;
- one provenance family containing raw source, source manifest, and canonical
  wiki page;
- exact-term, semantic, decision-rationale, cross-page, and missing-evidence
  queries;
- a code-plus-wiki query that must keep code and Vault Evidence separate.

Expose three named policies in the benchmark only:

```text
full_document
flat_leaf_v2
hierarchical_evidence_v1
```

Measure at least:

- supporting Evidence recall at `k`;
- canonical result duplication by provenance family;
- matched-Evidence support coverage;
- context token use and omission/truncation warnings;
- changed leaf count and vector reconcile work after a local edit;
- deterministic result ordering and result identity;
- query-time wall-clock measurements on a fixed local fixture.

The benchmark must report results rather than silently choose a new threshold.
It is a regression/decision artifact, not durable Vault knowledge.

### 2. Introduce deterministic parent identity in the ingestion projection

Modify:

- `src/vault_graph/ingestion/document_chunking.py`
- `src/vault_graph/ingestion/document_normalizer.py`
- `src/vault_graph/storage/interfaces/metadata_store.py`
- `src/vault_graph/storage/local/sqlite_metadata_store.py`
- `tests/test_document_chunking.py`
- `tests/test_document_normalizer.py`
- `tests/test_metadata_chunk_listing.py`
- `tests/test_metadata_v3.py`

Add a structural parent identity to each `ChunkDraft` and `ChunkSnapshot`:

- `parent_id`: Vault-scoped deterministic ID;
- `parent_kind`: `document` or `section`;
- existing `section_path` remains the display and hierarchy coordinate.

Derive a Section parent from the normalized `section_path` and the first
reader-emitted structural block key for that Section. Derive a document parent
for preamble/no-heading content. The identity derivation must include
`vault_id` and `document_id`; repeated headings must not collide, and an
unrelated edit before a Section must not change an unchanged Section parent.

Persist `parent_id` and `parent_kind` in the metadata chunk projection. Bump
the metadata schema version and make incompatible pre-release state fail with
the existing rebuild guidance. Do not create a second plaintext table: parent
rows reference existing chunks and `content_blobs`.

Add store operations only where the existing interface needs them:

```python
def list_parent_chunks(
    self,
    *,
    vault_id: str,
    parent_id: str,
) -> tuple[ChunkSnapshot, ...]: ...
```

Keep `list_document_chunks` for the current context-expansion contract. All
new operations must use the logical interface; retrieval must not query SQLite
tables directly.

Verify:

- same source and same parser/chunker versions produce identical parent and
  leaf IDs;
- unrelated Section edits preserve unaffected parent and leaf IDs;
- repeated headings remain distinct;
- parent metadata is rebuilt and tombstoned with its document;
- Vault files remain unchanged.

### 3. Expand Evidence references into a canonical source-addressable bundle

Modify:

- `src/vault_graph/storage/interfaces/metadata_store.py`
- `src/vault_graph/retrieval/retrieval_result.py`
- `src/vault_graph/retrieval/search_response.py`
- `src/vault_graph/retrieval/context_expansion.py`
- `src/vault_graph/retrieval/retrieval_service.py`
- `src/vault_graph/context/context_pack.py`
- `src/vault_graph/context/context_pack_builder.py`
- `src/vault_graph/context/context_pack_serialization.py`
- `src/vault_graph/mcp/mcp_tool_serialization.py`
- `src/vault_graph/mcp/metadata_resource_reader.py`

Extend `EvidenceReference` with `parent_id` and `parent_kind`. Preserve
`path`, `section_path`, `source_locators`, `raw_sha256`, `vault_revision`, and
`metadata_index_revision` as the source-addressing and freshness fields.

Extend `RetrievalResult` with:

```python
canonical_document_id: str
canonical_parent_id: str
canonical_parent_kind: Literal["document", "section"]
canonical_section_path: tuple[str, ...]
context_evidence: tuple[EvidenceReference, ...]
retrieval_policy_version: str
```

Extend `SearchResponse` with the same `retrieval_policy_version` so a caller
can distinguish a leaf-result response from the parent-aware response without
inspecting individual results.

Keep `matched_chunk_id` and `context_chunk_ids` as compatibility/rendering
fields for the first migration release, but make the Evidence references the
canonical result payload. A `knowledge` result may contain multiple matched
leaf Evidence references from one parent.

Extend `ContextEvidence` with `section_path`, `source_locators`, `parent_id`,
and `parent_kind`. The JSON and MCP serializers must expose these fields while
preserving existing `vault_id`, `document_id`, and `chunk_id` references.

Change `ContextExpander` to return resolved Evidence references in addition to
IDs. It must continue to enforce `QueryScope`, the existing token budget, and
`parent-neighbor-v1` policy semantics until a separately versioned context
policy is accepted.

Verify:

- every normal result and context-pack Evidence item resolves through
  `MetadataStore`;
- missing leaf or parent Evidence becomes a visible warning, never an
  unsupported normal result;
- locators survive SQLite round-trip and MCP/JSON serialization;
- no generated context text is written to Vault or to vector/graph stores.

### 4. Add a deep hierarchical result assembler

Create:

- `src/vault_graph/retrieval/hierarchical_result_assembly.py`
- `tests/test_hierarchical_result_assembly.py`

Define a focused `HierarchicalResultAssembler` that receives already fused,
resolved leaf candidates and returns canonical result containers. It must not
access SQLite, Chroma, CLI, MCP, or Vault paths directly.

Required behavior:

1. In `knowledge` mode, select the highest-ranked canonical document per
   provenance family, but retain all matching leaves from that selected
   document until parent grouping is complete.
2. Group those retained leaves by
   `(vault_id, canonical_document_id, parent_id)`.
3. Use `section` as the canonical parent kind when `section_path` is non-empty;
   otherwise use `document`.
4. Merge all contributing keyword/vector/graph signals for the group while
   retaining signal-specific rank and explanation.
5. Rank groups by their best fused leaf rank, then deterministically by Vault,
   path, parent ID, and first leaf order.
6. Apply the public `limit` after parent grouping.
7. Attach source-manifest/raw Evidence and audit records from the selected
   provenance family without presenting them as duplicate canonical results.
8. Preserve explicit `evidence` mode as leaf-oriented drill-down.

Update `RetrievalService._resolve_results` and `_expand_context` to delegate
grouping and bundle assembly to this module. The service must not collapse a
provenance family to one leaf before the assembler has collected the selected
parent's matched Evidence. The service remains responsible
for scope, readiness, candidate retrieval, warnings, and application-level
composition; it must not grow a second grouping implementation.

Add a versioned `retrieval_policy_version`, initially
`hierarchical-evidence-v1`, to `SearchResponse`, `RetrievalResult`, context
packs, and explanations where the policy affects output.

### 5. Make lexical metadata explicitly hierarchical without duplicating text

Modify:

- `src/vault_graph/storage/interfaces/keyword_index.py`
- `src/vault_graph/storage/local/sqlite_keyword_index.py`
- `tests/test_sqlite_keyword_index.py`
- `tests/test_retrieval_service_search.py`

Keep the existing FTS leaf rows as the initial backend. Ensure the indexed
fields and candidate contract expose full `section_path`, parent identity, and
document title/frontmatter as searchable metadata. The local FTS projection
must remain contentless/reference-oriented where the current schema requires
it, and final rendering must still resolve through `MetadataStore`.

Do not add a second parent plaintext store. A parent candidate is a grouping of
metadata-owned leaf references. If benchmark results show that leaf-first
candidate retrieval misses relevant long-document Sections, add a separate
`ParentCandidateIndex` in a later slice with the same interface-first and
rebuildable contract; do not silently change the vector or metadata authority.

### 6. Preserve vector and graph projection boundaries

Modify only the affected contracts and tests in:

- `src/vault_graph/storage/interfaces/vector_store.py`
- `src/vault_graph/indexing/vector_indexer.py`
- `src/vault_graph/retrieval/graph_candidates.py`
- graph index/retrieval tests where parent fields are serialized.

The first hierarchical result slice must not re-embed unchanged leaf text.
Changes to `retrieval_policy_version`, parent grouping, or context expansion
alone must not stale vectors. Reader, parser, chunker, source hash, embedding
model, and backend schema changes retain their existing stale/reconcile rules.

Vector hits remain semantic candidates only. Graph records remain entity,
relationship, and Evidence-reference projections. Both resolve parent and leaf
metadata through `MetadataStore` before rendering.

Add regression tests proving:

- graph Evidence never stores an authoritative excerpt;
- vector/graph candidates with missing metadata Evidence are dropped with
  warnings;
- a policy-only change does not create vector upserts or tombstones;
- scope-local reconcile and multi-Vault identity remain unchanged.

### 7. Complete format-neutral Reader discovery, then add adapters separately

Modify:

- `src/vault_graph/ingestion/vault_loader.py`
- `src/vault_graph/ingestion/document_readers.py`
- `tests/test_vault_loader.py`
- `tests/test_document_readers.py`
- `tests/test_read_only_boundary.py` or the closest existing boundary suite.

Make `VaultLoader` enumerate files supported by the supplied
`DocumentReaderRegistry` instead of hardcoding `*.md`. Unsupported files must
be skipped with a deterministic warning and must not break Markdown indexing.
The default registry remains Markdown-only until an adapter is explicitly
registered and tested.

Then deliver optional readers as independent slices:

1. `PlainTextDocumentReader`: deterministic paragraph/line locators and no
   optional dependency.
2. `PdfDocumentReader`: page and text-offset locators, explicit dependency
   health, and bounded extraction failure behavior.
3. `DocxDocumentReader`: deterministic heading, paragraph, table, and locator
   output behind an explicit dependency.

Every adapter must return the existing `ExtractedDocument` contract. No adapter
may mutate or create files inside Vault. Reader version and extraction-option
changes must stale only affected metadata/vector/graph projections.

### 8. Keep the code path AST-native and combine authorities above retrieval

Do not modify the code parser to emit prose chunks. Keep:

- repository source as code authority;
- symbol, import, call, inheritance, and test edges as the code projection;
- bounded live source reads after fingerprint validation;
- Vault and code Evidence as distinct identities.

Update only the project-context integration tests if the new Vault result shape
changes serialization. `explore_project` should return a Section/document
container for Vault Evidence plus bounded code symbols and source links, with
separate revisions and freshness warnings.

### 9. Update the active contracts after implementation passes

After code and tests are green, update:

- `docs/SPEC.md`: canonical knowledge result, parent/leaf Evidence model,
  policy version, context bundle fields, and changed staleness rules.
- `docs/FEATURES.md`: default `knowledge` rendering versus explicit `evidence`
  drill-down and MCP/CLI result fields.
- `docs/DESIGN.md`: parent grouping module, Evidence bundle boundary, and
  Reader discovery.
- `docs/SEARCH_ARCHITECTURE.md`: replace the chunk-centric diagram with the
  document/Section -> leaf Evidence -> canonical result flow.
- `docs/TODO.md`: mark the hierarchical result slice complete and retain
  PlainText/PDF/DOCX as independent adapter work.

Do not update `docs/DECISIONS.md` until the user accepts the architecture.
Use `docs/PATCH_LOG.md` only for corrections caused by review or verification,
following the repository template.

## Errors and edge cases

- **Document without headings:** use a document parent and retain empty
  `section_path`.
- **Repeated headings:** use structural block identity in `parent_id`; never
  use heading text alone.
- **One parent with many leaf hits:** return one canonical result with multiple
  matched Evidence refs, subject to evidence and context budgets.
- **Long parent:** keep leaf retrieval bounded; add only explicitly selected
  context refs and emit budget warnings when omitted.
- **Cross-parent neighbors:** do not cross a Section or document boundary
  unless a future policy explicitly says so; the initial policy stays within
  the same document and `QueryScope`.
- **Stale source or projection:** do not present stale text as normal fresh
  Evidence; attach the existing warning and recovery guidance.
- **Missing metadata blob or locator:** drop the candidate from normal results,
  preserve an attributable warning, and never trust a vector or graph excerpt.
- **Provenance family without canonical knowledge:** omit it from default
  `knowledge` results or report the missing canonical role; expose it only in
  an explicit drill-down mode.
- **Multi-Vault collision:** every parent, document, chunk, warning, signal,
  and result ID must retain `vault_id` scope.
- **Unsupported Reader format:** skip safely, report the format and recovery
  hint, and continue indexing supported files.
- **Code index unavailable:** preserve the existing deterministic Vault-only
  fallback and visible warning; never treat it as fresh code.

## Tests

### Unit

- parent ID derivation and repeated-heading handling;
- parent grouping and deterministic ordering;
- multi-reference Evidence bundle validation;
- context Evidence resolution and budget warnings;
- full section-path and locator round-trips;
- unsupported Reader handling.

### Contract and integration

- metadata schema upgrade/rebuild and content-blob single-owner invariant;
- keyword/vector/graph candidate resolution through `MetadataStore`;
- knowledge-mode family collapse plus parent grouping;
- evidence-mode leaf drill-down;
- same parent and chunk IDs across repeated incremental runs;
- changed parent/chunk stale reconciliation;
- policy-only changes without vector re-embedding;
- full and incremental indexing over Markdown fixtures;
- multi-Vault same-path and same-chunk collision safety;
- CLI, MCP, context-pack, and resource serialization;
- code/Vault project-context separation;
- no mutation of Vault files or `vault-builder` files.

### Benchmark gate

Do not declare the hierarchical default successful unless the fixed benchmark
shows:

- no regression in supporting Evidence recall against the current flat-leaf
  baseline;
- lower or equal provenance-family duplication in `knowledge` mode;
- canonical results carry their matched Evidence and parent context;
- token and omission behavior stays within the existing context contract;
- an unrelated local edit does not expand vector work beyond the affected
  leaf/parent policy;
- repeated runs produce deterministic result identity and ordering.

## Verification

Run from `/Users/junhyounglee/workspace/vault-graph`:

```bash
uv run pytest -q
uv run ruff check .
uv run ruff format --check .
uv run mypy src
uv run pytest -q tests/benchmarks/test_hierarchical_retrieval_benchmark.py
git diff --check
```

For a fixture Vault, additionally verify:

```bash
vg index --full --dry-run
vg index --full
vg search --format json "<query>"
vg search --mode evidence --format json "<query>"
vg context --format json "<task>"
vg projection-audit
```

Expected signals:

- default knowledge results show document/Section containers with leaf Evidence
  references;
- explicit evidence mode shows leaf drill-down;
- warnings identify stale, missing, omitted, or unsupported material;
- vector and graph projections contain references, not duplicate authoritative
  result text;
- deleting Vault Graph Data Home and rebuilding reproduces the same logical
  results;
- Vault and registered repository hashes remain unchanged.

## Validation review

- **Security/read-only:** no writes to `Vault`, `vault-builder`, or registered
  repositories; only Graph-owned derived state changes.
- **Performance/scalability:** grouping is bounded after candidate retrieval;
  parent-index or parent-filtered vector work is benchmark-gated rather than
  added speculatively; content blobs remain deduplicated.
- **Testability:** pure parent identity, grouping, Reader, store, and
  serialization contracts can be tested independently before end-to-end
  indexing.
- **Maintainability:** `HierarchicalResultAssembler` hides grouping policy;
  `RetrievalService` remains orchestration; stores remain interfaces; no
  protocol adapter or backend receives retrieval logic.
- **Agent ergonomics:** the default result answers “which canonical Section
  supports this?” while explicit Evidence mode still permits exact leaf
  inspection. Code context remains AST-native.
- **Changeability:** parser/chunker/reader lineage still controls index
  freshness; retrieval-policy changes do not force unnecessary re-embedding.

## Open decisions

1. **Canonical parent default.** Recommendation: return `section` when a
   Section exists and `document` for preamble/single-container documents;
   preserve leaf results under explicit `evidence` mode.
2. **Parent identity storage.** Recommendation: persist `parent_id` and
   `parent_kind` on chunk metadata rather than create a second parent plaintext
   store. This handles repeated headings and keeps the migration small.
3. **Coarse parent index.** Recommendation: do not add a new parent vector index
   in the first slice. Decide from the benchmark whether parent-aware grouping
   is sufficient or whether a dedicated `ParentCandidateIndex` is warranted.
4. **`vault-builder` source kinds.** Recommendation: make `docx` and
   `plaintext` explicit only when their durable ingest/reporting workflow needs
   the distinction. It is not required for Vault Graph Reader support.

## Expected outcome

The completed migration will make the architectural truth explicit:

```text
Vault = original and durable knowledge authority
vault-builder = provenance and quality-gated Vault workflow
vault-graph MetadataStore = rebuildable extracted-text projection
chunk = internal leaf retrieval/evidence coordinate
document/Section = canonical default search result
graph = derived relationships over Evidence references
code projection = AST-native current-code graph
```

This preserves the strengths already implemented in Vault Graph while removing
the conceptual risk that users or agents mistake a flat list of chunks for the
knowledge base itself.
