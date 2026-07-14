# Vault Graph TODO

This file is the single backlog for deferred work, scale-up candidates, and
future adapter directions. Keep `docs/SPEC.md` focused on the active product
contract. Promote an item from this file into a focused SPEC or implementation
plan before changing code.

## Operating Rules

- Vault remains the durable source of truth.
- Vault Graph TODOs must preserve read-only, rebuildable, local-first behavior.
- Do not add default hosted services, hidden write paths, or Vault mutation.
- Keep future adapters behind existing deep module interfaces when possible.
- Every accepted TODO needs tests for read-only behavior, multi-vault identity,
  stale-state handling, and explicit warnings before implementation.

## Deferred Product Candidates

### Browser UI Layer

Status: deferred feature.

Phase 7B and Phase 7C remain optional browser UI work over existing services.
The first UI should be a small local surface over HTTP JSON endpoints, not a new
retrieval engine, answer engine, memory store, index backend, or Vault
publication workflow.

Required direction:

- use existing application services only
- preserve Vault IDs, evidence links, warnings, revisions, and freshness
- keep `127.0.0.1` as the local default
- avoid hosted UI, auth, and remote sharing until a separate security design

### OKF-Compatible Projection

Status: deferred implementation candidate.

Vault Graph may later add OKF compatibility as a projection/export layer over
Vault-derived state. OKF must not replace Vault, become a second source of
truth, or introduce a writable knowledge core.

Required direction:

- consume Vault-derived Markdown/frontmatter and graph/search/context outputs
- export portable projection records with evidence references
- keep Vault Graph as consumer/compiler, not an OKF authoring system
- keep implementation behind an explicit spec and feature flag

## Indexing And Retrieval Scale-Up

### MacBook Local Acceleration Adapter

Status: future adapter.

The default remains `FastEmbedTextEmbeddings` on local CPU. A MacBook
acceleration path should be added as a `TextEmbeddings` adapter, not by changing
`VectorIndexer`, `VectorStore`, or Chroma behavior.

Candidate adapter names:

- `CoreMLTextEmbeddings` for ONNX Runtime CoreML Execution Provider
- `AppleAcceleratedTextEmbeddings` if the adapter may choose CoreML, MLX, or
  another Apple-local runtime

Required direction:

- implement `TextEmbeddings`
- return a complete `EmbeddingModelSpec`
- keep CPU FastEmbed as the default until benchmark and deterministic-output
  evidence exists
- package acceleration as an optional extra such as `vault-graph[apple-accel]`
- fail clearly if configured acceleration is unavailable; do not silently fall
  back to CPU
- treat runtime changes as model-spec changes unless tests prove vector
  equivalence
- keep model artifacts and compiled runtime caches outside registered Vault
  roots
- report runtime/provider/cache/active-acceleration status in `vg status`

Required validation:

- supported model operators on the selected Apple runtime
- CPU versus accelerated embedding dimension, normalization, and similarity
  drift on fixed multilingual samples
- first-run compile time, warm-run throughput, memory, and battery impact
- offline behavior after model and compiled cache are present
- read-only boundary tests
- regression tests proving acceleration failure does not corrupt metadata,
  vector manifests, or existing CPU vector projections

### Non-Markdown Document Reader Adapters

Status: future adapter.

The default indexing policy remains Markdown-only. Future non-Markdown support
must use read-only document reader adapters and must not convert, rewrite,
rename, delete, or create files inside a registered Vault root.

Recommended boundary:

```text
VaultLoader
  -> DocumentReaderRegistry
      -> MarkdownDocumentReader
      -> PlainTextDocumentReader
      -> PdfDocumentReader
      -> DocxDocumentReader
  -> DocumentNormalizer
  -> MetadataStore
  -> VectorIndexer
```

Required direction:

- start with `.txt` if a non-Markdown reader is needed
- add PDF only after source-location evidence can include page numbers and text
  offsets
- add DOCX only after heading and paragraph extraction is deterministic
- keep OCR, spreadsheets, slides, images, and audio as later optional adapters
- compute `raw_sha256` from source bytes
- return reader name, reader version, parser version, extraction warnings, and
  source locators
- keep extracted caches disposable and outside registered Vault roots
- keep optional dependencies explicit with clear status diagnostics
- enforce file-size, extraction-time, symlink, and path-escape limits

Required validation:

- unsupported files do not mutate Vault and do not break Markdown indexing
- stable hashes and deterministic chunk IDs
- reader-version or extraction-option changes stale affected records
- same relative path in different Vaults does not collide
- evidence resolution returns original Vault path and format-specific locator
- missing optional dependencies produce clear status output

### Markdown Chunking Strategy Migration

Status: future retrieval and indexing migration.

Current default: `heading-section-v1`.

Future direction:

```text
heading-section-v1
  -> markdown-block-window-v2
  -> hierarchical-retrieval-v3
```

`heading-section-v1` is explainable and easy to inspect, but uneven section
sizes can dilute semantic signal or stale large vectors after small edits.

`markdown-block-window-v2` should:

- parse structural Markdown blocks
- group adjacent blocks within token budgets
- preserve code fences and tables unless deterministic split rules apply
- include compact heading breadcrumbs in embedded text
- keep evidence rendering tied to original Vault paths, headings, anchors, and
  hashes
- tombstone old-version vectors only inside the selected `QueryScope`

`hierarchical-retrieval-v3` should:

- separate matched fine chunks from expanded parent/neighbor context
- keep expansion in retrieval, not `VectorStore`
- explain `matched_chunk_id`, `context_chunk_ids`, parent section, retrieval
  reason, and warnings
- version retrieval policy separately from chunker version and context-pack
  schema version

Required validation:

- deterministic chunk IDs for unchanged Markdown
- stable chunk IDs for unrelated edits
- large sections split under `max_tokens`
- small sections receive heading breadcrumb context
- chunker-version changes stale affected metadata and vector records
- parent/neighbor expansion respects `QueryScope`
- retrieval-policy changes do not stale vectors when chunk text is unchanged
- no Vault file mutation

### Backend Scale-Up

Status: future backend implementations.

Potential scale-up targets:

- Postgres-backed `MetadataStore`
- Qdrant-backed `VectorStore`
- Neo4j-backed `GraphStore`

Required direction:

- keep the existing store interfaces as the contract
- keep SQLite/Chroma local defaults until scale-up evidence exists
- preserve multi-vault identity and evidence authority
- reuse contract tests for backend parity
- never let backend-specific fields become user-facing authority

## Serving, Security, And Agent Adapters

### Remote HTTP And Authentication

Status: future security design.

Current HTTP serving is local-only and read-only. Remote serving, authentication,
TLS, origin policy, and hosted deployment require a separate security design.

Required direction:

- keep `127.0.0.1` as the default bind address
- document threat model before exposing remote access
- preserve read-only behavior
- avoid store-direct HTTP endpoints
- keep HTTP as an adapter over application services

### LLM-Backed Answer Composer

Status: future answer adapter.

The default answer composer remains deterministic and extractive. An LLM-backed
composer may be added only behind `AnswerComposer`.

Required direction:

- preserve `CitationGuard`
- label unsupported claims as partial or insufficient evidence
- never write answer content into Vault Graph indexes as authority
- keep hosted model usage optional and explicit
- preserve deterministic fallback behavior

### External Memory Layer Adapter And Export Target

Status: future adapter/export target.

External memory systems such as Mem0, MemMachine, or MCP memory servers may be
useful later for personalization, cross-session recall, or shared memory between
agent runtimes. They must consume projection exports; they must not become a
Vault Graph core store.

Required direction:

- Vault remains the durable source of truth
- Vault Graph memory projections remain read-only, disposable, and rebuildable
- no external adapter may write, rename, rewrite, delete, publish, or validate
  Vault content
- no generated memory may become a fact unless captured in Vault and re-indexed
- outbound records include `vault_id`, evidence refs, store revisions,
  generated timestamps, freshness, warnings, and export schema version
- profile, preference, procedural, and raw episode memories stay outside Vault
  Graph core unless represented as durable Vault notes

Recommended future adapter shape:

```python
class MemoryProjectionExporter(Protocol):
    def export_project_memory(
        self,
        projection: ProjectMemoryProjection,
    ) -> tuple[MemoryExportRecord, ...]: ...

    def export_recent_changes(
        self,
        projection: RecentChangesProjection,
    ) -> tuple[MemoryExportRecord, ...]: ...
```

Required validation:

- exported records are reproducible from the same Vault-derived state
- deleting the external adapter loses no Vault Graph truth
- no external memory dependency is imported by default
- adapter failures do not break search, context packs, graph, or memory
  projections
- cross-Vault exports preserve Vault IDs and never merge by title alone

## CLI And Operations

### Reset Index Command

Status: future ergonomic CLI.

`vg reset-index` is not required for the current release. Users can delete
Vault Graph internal state and run `vg index` again. Add a command only after a
real user-facing gap appears.

Required direction:

- call an application service, not ad hoc path deletion
- enforce path safety so only Vault Graph state is removed
- never delete Vault content
- explain the equivalent manual recovery path in command output

### Release And Publishing Operations

Status: ongoing operations.

Keep PyPI publishing behind GitHub Release, environment approval, and Trusted
Publishing. Local `uv publish` remains outside the normal release path.

Required direction:

- PR and push run verification only
- TestPyPI is manual
- PyPI runs only from a published GitHub Release
- `pypi` environment approval is required
- publishing uses OIDC, not API tokens or GitHub secrets
