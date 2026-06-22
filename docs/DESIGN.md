# Vault Graph Detailed Design

Status: Draft

Source specification: `docs/SPEC.md`

This document expands the Vault Graph specification into implementation-level
module boundaries, runtime flows, data contracts, and verification expectations.
It is subordinate to `docs/SPEC.md`: when the two documents disagree, the
specification is the active product and architecture contract.

## 1. Purpose

Vault Graph is a read-only, rebuildable access layer over Vault. It indexes
Vault content, exposes evidence-linked retrieval, builds context packs, and
helps agents trace project memory without turning derived output into durable
knowledge.

The detailed design has three goals:

- make implementation boundaries clear enough for test-driven work
- preserve the Vault source-of-truth boundary in every runtime path
- keep storage backends replaceable without changing user-facing behavior

This document does not redefine product scope. It translates the existing
specification into a stable design that can guide implementation.

## 2. Authority And Document Roles

Vault Graph has three current documentation surfaces:

- `docs/SPEC.md`: product, architecture, storage contracts, indexing rules,
  roadmap, and success criteria
- `docs/FEATURES.md`: CLI, MCP, HTTP, and user-facing behavior catalog
- `docs/CONVENTIONS.md`: Python naming, package structure, typing, linting,
  and test guidance
- `docs/DESIGN.md`: implementation-level module and flow design

The design follows these authority rules:

- Vault remains the durable source of truth.
- Vault Graph state is always derived from Vault and can be deleted.
- Context packs, summaries, graph relationships, embeddings, and indexes are
  working context, not durable knowledge.
- Durable publication belongs to Vault's source capture, semantic draft,
  validation, release gate, and Git history workflow.

## 3. Scope

### 3.1 In Scope

Vault Graph implements:

- local Vault configuration
- read-only Vault scanning
- Markdown parsing and Vault frontmatter projection
- normalized document and chunk projection
- metadata indexing
- vector indexing
- entity and relationship extraction
- graph indexing
- rustworkx graph projection
- hybrid retrieval
- decision tracing
- project, decision, issue, and timeline memory projections
- context pack generation
- CLI commands
- MCP resources, tools, and prompts
- optional HTTP serving over the same application services

### 3.2 Out Of Scope

Vault Graph does not implement:

- automatic wiki publication
- automatic raw source registration
- raw source mutation
- wiki page mutation
- documentation mutation inside Vault
- contradiction resolution as durable truth
- autonomous truth arbitration
- required hosted storage or SaaS dependencies

Any insight that should become durable must be returned as a warning, context
pack item, or suggested Vault workflow command. Vault Graph must not silently
perform that workflow.

## 4. Design Invariants

These invariants must hold across CLI, MCP, HTTP, indexing, retrieval, and test
fixtures.

### 4.1 Read-Only Vault Boundary

Vault Graph may read registered Vault paths. It may write only to the configured
Vault Graph state directory.

Allowed writes:

- `data/metadata/`
- `data/vector/`
- `data/graph/`
- `data/projection_cache/`
- `data/migrations/`
- configured equivalents outside the repository

Forbidden writes:

- Vault `raw/`
- Vault `wiki/`
- Vault `docs/`
- Vault `scratch/`
- Vault Git metadata
- any path outside the configured Vault Graph state directory

### 4.2 Rebuildability

All persisted Vault Graph data must be rebuildable from Vault plus explicit
runtime policies:

- parser version
- chunker version
- embedding model and version
- embedding model spec version
- graph extraction spec version
- store schema versions
- graph projection version

If two index runs use the same Vault revision and runtime contract versions,
query behavior should be functionally equivalent.

### 4.3 Evidence-First Output

Every answer, decision trace, related item, warning, and context-pack item must
be traceable to evidence when evidence exists. Output must distinguish:

- stated facts
- inferred relationships
- contested claims
- deprecated material
- stale indexes or projections
- missing evidence

### 4.4 Interface-First Storage

Application services depend on store interfaces, not concrete backends.

The MVP local backends define the reference behavior:

- `MetadataStore`: SQLite
- `VectorStore`: Chroma
- `GraphStore`: SQLite
- `GraphProjection`: rustworkx runtime projection

Scale-up adapters must preserve these contracts instead of changing the domain
model.

### 4.5 Multi-Vault Namespace

One Vault Graph instance may index multiple registered Vault repositories. The
default installation still behaves like a single-Vault system by creating one
active `default` catalog entry.

Every derived record must carry its Vault namespace. Documents, chunks, entities,
evidence, warnings, and revisions carry `vault_id`; relationship records carry
source, target, and evidence Vault IDs. Paths are unique only inside a Vault, so
file identity is `(vault_id, path)`. Cross-Vault retrieval must be explicit in
`QueryScope`; default queries use the active Vault only. Cross-Vault entity
merging is outside the MVP and may appear only as evidence-linked inferred
relationships.

## 5. Architecture Overview

```text
VaultCatalog
  vault_id -> Vault root
    |
    v
VaultLoader
  scans enabled Vault roots, reads content, records hashes
    |
    v
DocumentPipeline
  reads Vault frontmatter, parses markdown, normalizes sections, chunks text
    |
    v
MetadataIndexer -> MetadataStore
                     |
                     +--> VectorIndexer -> VectorStore
                     |
                     +--> GraphIndexer -> GraphStore
                                            |
                                            v
                                      GraphProjection
    |
    v
RetrievalServices
  vector retrieval, graph retrieval, hybrid ranking, explanations
    |
    v
ContextPackBuilder / MemoryServices / DecisionTraceService
    |
    v
CLI / MCP / HTTP
```

The important dependency direction is from interfaces toward derived stores.
No retrieval or serving layer may bypass evidence resolution through
`MetadataStore` and `GraphStore`.

## 6. Package Boundary Design

The repository structure in `docs/SPEC.md` defines the implementation packages.
Each package should behave as a deep module: a small public interface hiding
its internal parsing, storage, ranking, or projection complexity.

### 6.1 `cli`

Responsibility:

- parse command-line arguments
- load runtime configuration
- call application services
- render user-facing output
- return meaningful exit codes

The CLI must not parse Vault files, query storage backends directly, or mutate
Vault content. It should treat application services as its only execution
boundary.

Initial commands:

- `vg init --vault /path/to/vault`
- `vg init --vault-id main --vault /path/to/vault`
- `vg vault add work --path /path/to/other-vault`
- `vg vault list`
- `vg index`
- `vg index --vault-id main`
- `vg index --all-vaults`
- `vg index --full`
- `vg index --dry-run`
- `vg watch`
- `vg status`
- `vg status --vault-id main`
- `vg status --all-vaults`
- `vg ask "question"`
- `vg related TARGET`
- `vg context "goal"`
- `vg decision-trace TOPIC`
- `vg serve --mcp`
- `vg serve --http`

This command list is the full roadmap surface. Phase 3 implementation scope is
limited to graph readiness/indexing plus `vg related`, `vg decision-trace`, and
explicit graph search modes. `vg ask`, context packs, MCP serving, and HTTP
serving remain later-phase work.

Phase 3 implementation planning must use the detailed slice documents under
`docs/superpowers/specs/phase-3/`. `docs/SPEC.md` stays the top-level contract;
the Phase 3 folder owns long-form 3A/3B/3C design details.

### 6.2 `app`

Responsibility:

- own application services shared by CLI, MCP, and future HTTP adapters
- compose indexing, retrieval, graph, context, readiness, and catalog services
- enforce read-only behavior at the serving boundary

The `app` package is not a protocol adapter package. MCP adapter code belongs
under `vault_graph.mcp`; future HTTP adapter code should likewise stay outside
the application service package. Neither adapter may own retrieval logic.

### 6.3 `ingestion`

Responsibility:

- load Vault documents from allowed read paths
- read Vault frontmatter as projection input
- parse Markdown into sections and anchors
- normalize documents into stable records
- compute content hashes
- produce chunks for indexing

The ingestion package is pure read and transform logic. It writes nothing to
Vault and should be easy to test with fixture directories.

Vault frontmatter handling is intentionally narrow. Ingestion may read
frontmatter fields, compute a frontmatter hash, and expose selected fields for
index freshness, filtering, routing, and evidence display. It must not re-own
Vault's durable frontmatter schema, source registry rules, source-count
validation, publication gate, or release-gate checks.

Core modules:

- `vault_catalog.py`: loads registered Vault roots and active Vault selection
- `vault_loader.py`: scans configured Vault roots and reads file content
- `vault_frontmatter_reader.py`: reads Vault YAML frontmatter and derives
  projection fields and frontmatter hashes
- `markdown_parser.py`: extracts headings, sections, anchors, links, and body
  ranges
- `document_normalizer.py`: turns parser output into canonical document,
  section, and chunk records

### 6.4 `extraction`

Responsibility:

- extract candidate entities
- extract candidate relationships
- extract decision references
- extract issue and open-question references
- extract timeline events
- attach evidence references and confidence metadata

Extraction output is never durable truth. It is a typed proposal for indexing.
Every extracted record must carry an evidence path or warning explaining why
evidence is missing.

Core modules:

- `entity_extractor.py`
- `relationship_extractor.py`
- `decision_extractor.py`
- `issue_extractor.py`
- `timeline_extractor.py`

### 6.5 `indexing`

Responsibility:

- plan full and incremental index work
- apply document, vector, and graph updates to derived stores
- coordinate tombstones for deleted or stale files
- record revision metadata
- invalidate graph projection caches
- support dry-run planning without mutation

Core modules:

- `metadata_indexer.py`: writes document, section, chunk, hash, parser, and
  source-state projections
- `vector_indexer.py`: embeds chunks and writes vector records
- `graph_indexer.py`: writes entity records, relationship records, evidence,
  status, confidence, and graph extraction metadata
- `revision_planner.py`: compares Vault file state and runtime contract versions
  against store state
- `incremental_indexer.py`: orchestrates scan, parse, extract, store update,
  and projection invalidation

The indexer is the only package that should mutate Vault Graph state during
normal indexing.

### 6.6 `storage.interfaces`

Responsibility:

- define stable logical contracts for stores
- define health and freshness reports
- keep application code backend-independent

Interfaces:

- `metadata_store.py`
- `keyword_index.py`
- `vector_store.py`
- `graph_store.py`
- `store_health.py`

Interfaces should use project domain records rather than backend-native record
shapes. This prevents SQLite, Chroma, Neo4j, or Qdrant details from leaking into
retrieval and context-pack code.

### 6.7 `storage.local`

Responsibility:

- provide MVP local-first backend implementations
- run without hosted services
- implement the same logical contracts used by scale-up adapters

Local implementations:

- `sqlite_metadata_store.py`
- `sqlite_keyword_index.py`
- `chroma_vector_store.py`
- `sqlite_graph_store.py`

Local backends are the reference implementation for contract tests.

### 6.8 `storage.adapters`

Responsibility:

- provide optional scale-up backend implementations
- preserve local-first behavior
- preserve common record IDs, revisions, evidence fields, and health reports

Adapters:

- `postgres_metadata_store.py`
- `qdrant_vector_store.py`
- `neo4j_graph_store.py`

Adapters must not introduce new source-of-truth semantics. If a remote backend
is unavailable, Vault Graph should report a backend health error or fall back
only when fallback is explicitly configured.

### 6.9 `projection`

Responsibility:

- build runtime graph projections from `GraphStore`
- run bounded graph algorithms
- cache disposable projection artifacts
- invalidate caches when revisions or runtime contract versions change

Core modules:

- `graph_projection.py`: interface and domain-level projection operations
- `rustworkx_projection.py`: rustworkx adapter
- `projection_cache.py`: disposable cache read/write and invalidation

`GraphProjection` must not become the graph database. Query responses must
resolve graph results back through `GraphStore` evidence records.

### 6.10 `retrieval`

Phase 2C responsibility:

- expose CLI search over existing projections
- normalize user queries
- resolve requested search scope into per-Vault actual scopes
- check read-only search readiness for metadata, keyword, vector, and model
  availability
- retrieve keyword candidates
- retrieve vector candidates
- merge and dedupe candidates by `(vault_id, chunk_id)`
- apply rank-based keyword/vector fusion
- resolve evidence through `MetadataStore`
- assemble `SearchResponse` warnings and evidence-linked results

Later retrieval responsibility:

- retrieve graph candidates
- combine graph, wiki link, decision-map, and timeline-map signals
- apply richer reranking policy
- explain why non-search results were returned
- build evidence-linked context packs

Core modules:

- `vector_retriever.py`
- `graph_retriever.py`
- `hybrid_retriever.py`
- `reranker.py`
- `search_response.py`

Retrieval output must include enough metadata for `explain_result(result_id)`
to describe scores, evidence, relationship status, confidence, and warnings.

Phase 2C keeps search simple and evidence-first:

- `KeywordIndex` exposes metadata-owned lexical candidate lookup over current
  chunks and document metadata. The local implementation may use SQLite FTS5,
  but retrieval services must not query SQLite tables directly. The protocol
  belongs under `storage.interfaces`; the local implementation may share the
  metadata SQLite database.
- `VectorStore` remains semantic-candidate-only. It never returns rendered
  evidence, paths, titles, snippets, or chunk text authority.
- `RetrievalService` or `HybridRetriever` owns candidate merge, dedupe,
  reciprocal-rank-style fusion, warnings, evidence resolution, and final
  `SearchResponse` assembly.
- The canonical search result unit is an evidence chunk. Candidate merge can use
  `(vault_id, chunk_id)`, but resolved evidence identity is
  `(vault_id, document_id, chunk_id)`.
  Document, page, source, and section views are renderer groupings over chunk
  evidence.
- `RetrievalService` expands requested scopes into per-Vault actual scopes
  before calling `KeywordIndex` or `VectorStore`; it must not pass an all-vault
  content-scope union directly to candidate stores.
- Search readiness belongs behind a read-only service or protocol. Retrieval
  must not import `LocalVectorStatusStore` directly or duplicate
  `IndexService.status()` internals.
- Search-time query embedding uses a local-only embedding availability contract.
  Missing local model artifacts degrade vector search instead of downloading or
  writing cache files.
- Keyword projection is a metadata subprojection for the local backend. It is
  updated with the metadata revision during indexing and exposed to retrieval
  through read-only `KeywordIndex`.
- `SearchResponse` records requested scope, actual scopes, result count,
  candidate counts, degraded mode, attributed warnings, and store revisions.
- Search may degrade to keyword-only when vector search is unavailable, stale,
  or missing local model artifacts. The response must include top-level
  warnings.
- `vg search` is read-only over existing projections. It must not index, create
  schema, create Chroma collections, update vector status, or download
  embedding models.

### 6.11 `memory`

Responsibility:

- assemble project memory projections
- assemble decision memory projections
- assemble issue memory projections
- assemble timeline memory projections

Core modules:

- `project_memory.py`
- `decision_memory.py`
- `issue_memory.py`
- `timeline_memory.py`

Memory projections are query products over Vault-derived indexes. They are not
separate memories and must not store durable knowledge.

## 7. Runtime Configuration

Runtime configuration should be explicit about:

- Vault catalog entries
- Vault Graph state path
- active Vault ID
- content scopes
- entity schema
- retrieval policy
- embedding model spec
- storage backend selection
- optional scale-up backend configuration

Phase 2B default configuration uses Chroma as the local vector backend and
`FastEmbedTextEmbeddings` as the local `TextEmbeddings` implementation. Chroma
and FastEmbed are core local dependencies for the default Phase 2B install, not
hosted service requirements. Scale-up backends such as Qdrant and hosted
embedding adapters remain explicit adapter swaps.

Default embedding configuration:

- `model_name`: `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`
- `model_version`: `faf4aa4225822f3bc6376869cb1164e8e3feedd0`
- `dimensions`: `384`
- `spec_version`: `fastembed-multilingual-minilm-l12-v2-cosine-v1`
- `source_model_revision`: `e8f8c211226b894fcb81acc59f3b34ba3efd5f42`
- `artifact_repo_id`: `qdrant/paraphrase-multilingual-MiniLM-L12-v2-onnx-Q`
- runtime: local CPU
- cache path: outside registered Vault roots, for example
  `~/.cache/vault-graph/embeddings`

Default embedding throughput configuration:

- `embedding_batch_size`: `256`
- `embedding_parallelism`: `null`, meaning single main-process embedding
- `embedding_lazy_load`: `true`

`embedding_parallelism` may be set to `0` for CPU-core auto-detection or to a
positive worker count. These values tune local execution only. They are recorded
in run metadata and diagnostics, but they are not part of
`EmbeddingModelSpec`.

If the model artifact is missing, the implementation may download the configured
artifact on first use. If the artifact is unavailable offline, indexing fails
with a clear vector/model status. It must not silently fall back to a different
model.

Configuration files:

- `configs/vaults.yaml`
- `configs/entity_schema.yaml`
- `configs/retrieval_policy.yaml`
- `configs/embedding_spec.yaml`
- `configs/storage_backends.yaml`
- `configs/scaleup_backends.example.yaml`

Configuration loading order:

1. built-in defaults
2. project config files
3. local user config
4. command-line overrides

Command-line overrides should be visible in status output so users can inspect
which Vault IDs, Vault paths, and state paths are active.

## 8. Domain Records

The implementation should prefer typed records at package boundaries. Backend
implementations can serialize these records however they need, but application
services should exchange common logical shapes.

### 8.1 Vault Catalog Entry

A Vault catalog entry identifies one readable Vault repository root.

Fields:

- `vault_id`
- `root_path`
- `display_name`
- `enabled`
- `content_scopes`
- `state_namespace`
- `git_revision_policy`

`VaultCatalogEntry` is not a Vault source registry record. It does not validate,
publish, register, or mutate Vault source pages.

### 8.2 Query Scope

A query scope separates repository selection from content selection.

Fields:

- `vault_ids`
- `content_scopes`
- `include_cross_vault`

When no query scope is provided, services use the active Vault only and
`include_cross_vault=false`.

### 8.3 Evidence Reference

An evidence reference identifies why a result exists.

Fields:

- `vault_id`
- `path`
- `wiki_path`
- `section`
- `anchor`
- `content_hash`
- `raw_sha256`
- `vault_revision`
- `index_revision`
- `excerpt`
- `retrieval_reason`
- `confidence`
- `warning`

### 8.4 Document Snapshot

A document snapshot represents one indexed view of one Vault file.

Fields:

- `vault_id`
- `document_id`
- `path`
- `kind`
- `frontmatter`
- `frontmatter_hash`
- `content_hash`
- `raw_sha256`
- `parser_version`
- `last_seen_at`
- `last_indexed_at`
- `vault_revision`
- `index_revision`

### 8.5 Chunk Snapshot

A chunk snapshot represents retrievable text derived from a document.

Fields:

- `vault_id`
- `chunk_id`
- `document_id`
- `path`
- `section`
- `anchor`
- `text`
- `token_count`
- `content_hash`
- `chunker_version`
- `index_revision`

### 8.6 Entity Record

An entity record represents a derived node.

Fields:

- `vault_id`
- `entity_id`
- `type`
- `name`
- `normalized_name`
- `aliases`
- `canonical_path`
- `evidence_refs`
- `status`
- `confidence`
- `extraction_method`
- `graph_extraction_spec_version`
- `graph_extraction_spec_digest`
- `created_at`
- `updated_at`
- `graph_index_revision`

Entity evidence references resolve through `MetadataStore` chunk evidence.
Source path and wiki path displays are rendering views over evidence, not
separate entity authority.

### 8.7 Relationship Record

A relationship record represents a derived edge.

Fields:

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

`relationship_id` must be derived from relationship type, source entity, target
entity, source Vault ID, and target Vault ID. Evidence references are stored as
separate graph evidence rows keyed by `evidence_ref_id`. A relationship does not
imply a durable cross-Vault equivalence claim.

Phase 3 stores all relationships as directed records. Symmetric retrieval
behavior, when useful, belongs to query/view policy and must not rewrite
relationship identity.

Graph evidence reference fields:

- `evidence_ref_id`
- `owner_kind`
- `owner_vault_id`
- `owner_id`
- `evidence_vault_id`
- `document_id`
- `chunk_id`
- `content_hash`
- `section`
- `anchor`
- `path`
- `excerpt`

`owner_kind` is `entity` or `relationship`. `owner_vault_id` is the entity Vault
ID for entity evidence and the source Vault ID for relationship evidence.
`owner_id` is the `entity_id` or `relationship_id`. Path, section, anchor, and
excerpt fields are rendering metadata. User-visible relationship evidence must
resolve back through `MetadataStore` chunk evidence.

Allowed statuses:

- `stated`
- `inferred`
- `contested`
- `deprecated`

### 8.8 Retrieval Result

A retrieval result is a ranked candidate with evidence and explanation data.
The retrieval layer owns final ordering. Backend scores remain attached to
individual signals because keyword, vector, and graph scores are not globally
comparable.

Fields:

- `vault_id`
- `result_id`
- `kind`
- `title`
- `summary`
- `rank`
- `evidence`
- `signals`
- `relationship_status`
- `warnings`
- `store_revisions`

### 8.9 Context Pack

A context pack is a structured brief generated for a goal.

Required fields:

- `context_pack_schema_version`
- `pack_id`
- `goal`
- `scope`
- `vaults`
- `vault_revisions`
- `backend`
- `store_revisions`
- `retrieval_policy_version`
- `budget`
- `generated_at`
- `current_state`
- `relevant_pages`
- `relevant_sources`
- `decisions`
- `constraints`
- `open_questions`
- `warnings`
- `evidence`

The JSON shape in `docs/SPEC.md` is the minimum contract. Markdown rendering may
reorder sections for readability, but it must preserve the same content fields.

## 9. Store Contracts

### 9.1 MetadataStore

`MetadataStore` owns file identity, chunk identity, `(vault_id, path)` mapping,
content hashes, parser and chunker version state, source-state projections, Vault
frontmatter snapshots, tombstones, and index revision tracking for derived
records. `VaultCatalog` owns the authoritative `vault_id` to Vault root mapping.
`MetadataStore` may keep revision-scoped catalog snapshots only for diagnostics
and freshness reporting.

Required operations:

- upsert document snapshots for an index revision
- upsert chunk snapshots for an index revision
- record parser and chunker versions
- list current non-tombstoned chunks for a `QueryScope`
- list changed documents
- list stale documents
- list tombstoned documents
- resolve document IDs to evidence locations
- resolve chunk IDs to evidence locations
- report backend health
- report schema compatibility
- report revision freshness
- export records in the common logical metadata shape

Forbidden behavior:

- mutating Vault files
- owning durable semantic truth
- storing untraceable claims
- replacing Vault source registration
- validating Vault frontmatter as a publication gate
- replacing Vault's `tools/wiki` validation workflow
- treating paths as globally unique without `vault_id`
- owning registered Vault root configuration

### 9.2 VectorStore

`VectorStore` owns embedding persistence, vector search, embedding model version
state, vector index revision tracking, and vector backend replacement.

Required operations:

- upsert embeddings for chunk IDs
- delete or tombstone embeddings for stale chunks
- run filtered vector search with `QueryScope.vault_ids` and
  `QueryScope.content_scopes`
- apply content-scope filters with the same same-or-child semantics used by
  metadata indexing before returning limited vector hits
- validate embedding dimensions
- validate embedding model and version
- validate embedding model spec version
- report backend health
- report collection or schema compatibility
- report index freshness
- export embedding manifests in the common logical vector shape

Manifest records must carry reconcile metadata.

Staleness comparison keys:

- source chunk hash copied from `ChunkSnapshot.content_hash`
- chunker version
- metadata index revision
- embedding model spec
- backend schema version

Lineage and status fields:

- vector index revision
- backend name

`vector_index_revision` must not be used as a staleness comparison key. It
changes on successful writes and would otherwise make unchanged vectors stale on
the next run.

Vector search must return only semantic candidate metadata: `vault_id`, document
IDs, chunk IDs, content-scope filter metadata, backend-local scores, ranks, and
vector metadata. Callers must resolve document and chunk evidence through
`MetadataStore` before returning evidence to users.

### 9.3 GraphStore

`GraphStore` owns persisted entity records, relationship records, graph evidence
reference rows, relationship status, confidence, graph extraction metadata,
tombstones, backend health, schema compatibility, and graph revision metadata.
`GraphIndexer` owns reconcile planning; `GraphStore` supplies the current scoped
manifest and applies the completed reconcile plan.

Required operations:

- export the current graph manifest for selected actual scopes
- upsert entity records
- upsert relationship records
- tombstone stale entities and relationships
- resolve entity IDs to evidence-linked records
- resolve relationship IDs to evidence-linked records
- query neighborhoods by Vault-scoped entity
- query relationships by evidence chunk, relationship type, status, confidence,
  and scope
- report backend health
- report schema compatibility
- report graph revision freshness
- report stale counts
- report graph extraction spec compatibility
- export records in the common logical graph shape

`GraphStore` is derived and non-authoritative, but it is the persisted graph
contract. It must support write-capable indexing construction and read-only
retrieval construction as separate modes. `GraphProjection` depends on it.

### 9.4 GraphProjection

`GraphProjection` owns runtime graph algorithms over a bounded working graph.

Required operations:

- build a projection from `GraphStore`
- load a valid disposable cache
- invalidate stale caches
- traverse neighborhoods
- compute paths
- rank related entities
- return graph results that can be resolved back to `GraphStore`
- report projection freshness

Cache keys must include:

- Vault IDs
- index revision
- graph store revision
- parser version
- chunker version
- graph extraction spec version
- graph projection version

## 10. Indexing Design

Indexing has two modes: planning and applying.

Planning is read-only. It scans Vault and compares file state, parser versions,
chunker versions, embedding model specs, graph extraction specs, store schema
versions, and projection versions against current Vault Graph state.

Applying mutates only Vault Graph state. It updates metadata, vectors, graph
records, revision rows, and projection caches as each phase enables those
projections.

### 10.1 Full Rebuild

`vg index --full` should:

1. scan VaultCatalog entries selected by the indexing scope
2. compute file state and hashes
3. parse and normalize all included documents
4. rebuild metadata records
5. rebuild embeddings when vector indexing is enabled
6. Phase 3+: rebuild graph records
7. Phase 3+: invalidate projection caches
8. record a new index revision
9. report warnings and backend health

Full rebuild must not mutate Vault.

### 10.2 Incremental Rebuild

`vg index` should:

1. scan VaultCatalog entries selected by the indexing scope
2. compare file state with `MetadataStore`
3. classify files as unchanged, changed, stale, deleted, or tombstoned
4. parse only affected documents
5. update affected metadata records
6. update affected vector records when vector indexing is enabled
7. Phase 3+: update affected graph records
8. Phase 3+: invalidate affected projection cache entries
9. record a new index revision
10. report warnings and backend health

If parser, chunker, embedding, extraction, or schema versions change, the
revision planner should expand the affected set accordingly.

### 10.3 Dry Run

`vg index --dry-run` should:

1. scan VaultCatalog entries selected by the indexing scope
2. classify planned work
3. validate backend availability
4. report planned document, chunk, and enabled projection changes
5. report warnings
6. exit without mutating Vault Graph state

Dry-run output is an operational planning artifact, not durable knowledge.

The default indexing scope is the active Vault. A command such as `vg index
--vault-id work` updates derived state for `work` and must not mark records from
other registered Vaults stale. `vg index --all-vaults` is the explicit operation
for a whole-catalog run.

### 10.4 Deleted And Stale Files

Deleted Vault files should produce tombstones in Vault Graph stores. Tombstones
prevent stale derived records from appearing as fresh results while preserving
enough state to explain why a record disappeared.

Stale files should produce warnings when:

- indexed content hash differs from current content hash
- raw SHA-256 differs from the recorded value
- parser or chunker version changed
- embedding model spec changed
- graph extraction spec changed
- projection cache is invalid

### 10.5 Phase 2B Vector Reconcile

Phase 2B indexing adds one production projection after metadata indexing:
Chroma-backed local vector state.

The implementation should keep a simple dependency direction:

```text
IndexService
  -> MetadataIndexer
  -> VectorIndexer

VectorIndexer
  -> MetadataStore.list_chunks(actual_scope)
  -> VectorStore.export_manifest(actual_scope)
  -> TextEmbeddings.embed(...)
  -> VectorStore.apply_vector_revision(...)
```

`VectorIndexer` owns the reconcile plan. It compares desired chunks from
`MetadataStore` with existing manifest rows from `VectorStore` under the
selected actual `QueryScope`.

`VectorIndexer` must pass only planned upsert texts to `TextEmbeddings`. It
embeds them in batches using the configured `embedding_batch_size` and
`embedding_parallelism`, then binds every returned vector back to its requested
`input_id` before creating vector records. Batching and worker count must not
alter vector IDs, manifest keys, status semantics, or failure behavior.

If embedding fails because the configured `embedding_batch_size` or worker count
exceeds the machine's available memory or runtime capacity, `VectorIndexer`
returns a failed vector result with diagnostics. It must not silently lower
`embedding_batch_size`, disable parallelism, or switch embedding runtimes during
the same run.

`IndexService` must resolve the user-selected scope against `VaultCatalog`
before calling vector reconcile. For multi-vault runs, it must process per-Vault
actual scopes using the same broader/narrower content-scope rule as
`VaultLoader`. This prevents a global union of content scopes from selecting or
tombstoning records that are not enabled for a specific Vault.

Desired vector state is keyed by:

- `vault_id`
- `document_id`
- `chunk_id`
- `content_scope`
- `ChunkSnapshot.content_hash` as `source_chunk_hash`
- `chunker_version`
- `metadata_index_revision`
- `EmbeddingModelSpec`

The plan produces:

- upserts for new chunks
- upserts for chunks with changed hash, chunker version, metadata revision, or
  embedding model spec
- tombstones for selected-scope manifest rows whose chunks are deleted,
  tombstoned, changed to a new vector ID, or stale under the current model spec
- unchanged counts for status and dry-run output
- warnings for unhealthy vector backend, incompatible schema, or embedding
  failures

Scope handling must match metadata indexing. `vg index --vault-id work` updates
only the selected Vault and must not tombstone vector records for other Vaults.
Content-scope-limited reconcile uses same-or-child semantics before deciding
that a record is stale.

`IndexService` coordinates metadata and vector indexing without pretending they
are one database transaction. If metadata indexing succeeds and vector indexing
fails, the service keeps the metadata revision, returns a nonzero CLI exit for
the failed vector step, and marks vector freshness as stale or unavailable. A
later `vg index` must recover by running the same reconcile flow again.

`vg index --dry-run` reports metadata and vector work but writes neither store.
`vg index --full` rebuilds vector records for the selected scope under the
current `EmbeddingModelSpec`.

Dry-run output should include the configured `embedding_batch_size`,
`embedding_parallelism`, `embedding_lazy_load`, and the number of chunks that
would be embedded. Dry-run must not load the embedding model or initialize
backend state.

`vg status` reports freshness for the active Vault by default. Phase 2B status
should also support `--vault-id ID` and `--all-vaults`, and it must print the
scope used for vector freshness and stale counts.

The Phase 2B implementation must not add `vg search`, `vg ask`, graph
traversal, context packs, MCP serving, or HTTP serving.

## 11. Retrieval Design

Retrieval combines multiple evidence signals while keeping output explainable.
Phase 2 implements graph-ready hybrid retrieval with keyword and vector signals.
Graph signals join the same retrieval contract only after `GraphStore` exists in
Phase 3.

### 11.1 Search Flow

Phase 2C flow:

```text
Query
  -> normalize query and requested QueryScope
  -> expand to per-Vault actual scopes
  -> check read-only search readiness
  -> keyword candidate lookup
  -> vector candidate lookup
  -> candidate merge and dedupe
  -> rank-based fusion
  -> evidence resolution
  -> warning attachment
  -> response rendering
```

Later retrieval policy can add graph candidates, wiki link expansion,
decision-map expansion, timeline-map expansion, and richer reranking after Phase
2C. Those later signals must join the same candidate and evidence-resolution
contract instead of changing store authority.

Every candidate must resolve to evidence before it is shown as a normal result.
Candidates without enough evidence may appear only as warnings or inferred
follow-up suggestions.

If no `QueryScope` is provided, retrieval uses the active Vault only. Cross-Vault
retrieval requires explicit `vault_ids`. Candidate merge and dedupe must use
Vault-scoped identity; identical paths or entity names from different Vaults are
not equivalent by default.

The retrieval layer, not `VectorStore`, owns hybrid policy. `VectorStore` returns
semantic candidates only. `GraphStore` returns relationship candidates only.
Keyword lookup returns lexical candidates only. The retrieval layer merges these
signals, preserves per-signal explanations, and resolves evidence before
rendering.

### 11.2 Vector Retrieval

Vector retrieval searches `VectorStore` and returns vector IDs, Vault IDs,
document IDs, chunk IDs, content-scope filter metadata, backend-local scores,
ranks, filters, embedding model metadata, and index revision metadata.

The caller then resolves document and chunk IDs through `MetadataStore` to
attach `vault_id`, path, section, anchor, content hash, raw SHA-256, and Vault
revision.

### 11.3 Graph Retrieval

Graph retrieval starts with entity lookup or candidate documents, expands
neighborhoods through `GraphStore`, and may use `GraphProjection` for bounded
algorithmic ranking.

Cross-Vault graph traversal is opt-in. When a traversal crosses Vault IDs, the
relationship must include source, target, and evidence Vault IDs plus evidence
explaining why the relationship exists.

Graph results must distinguish relationship status:

- `stated`: directly supported by durable text
- `inferred`: derived by extraction or traversal
- `contested`: conflicts or unresolved disagreement exists
- `deprecated`: stale or superseded relationship

### 11.4 Hybrid Ranking

Hybrid ranking should preserve signal-specific explanations and avoid treating
backend scores as directly comparable. Phase 2 should use rank-based fusion for
keyword and vector candidates. Phase 3 may add graph proximity as another
signal.

The long-term ranking inputs are:

- keyword match strength
- vector similarity
- graph proximity
- durable wiki page priority
- decision page priority
- recency when relevant
- evidence quality
- relationship status
- stale or deprecated penalties

The ranking layer should preserve per-signal explanations so
`explain_result(result_id)` can describe why the result was returned.

### 11.5 Evidence-First Answering

`ask_vault(question, mode="evidence-first", scope=None)` should:

1. run hybrid retrieval
2. group evidence by source and claim
3. produce a concise answer only from supported evidence
4. label inferred links explicitly
5. attach warnings for stale, missing, contested, or deprecated material
6. suggest durable follow-up when useful

If evidence is weak, the answer should say so instead of filling the gap with
unsupported synthesis.

## 12. Context Pack Design

`build_context_pack(goal, scope=None, max_tokens=None)` turns retrieval output
into an agent-readable brief.

The canonical context pack artifact is JSON. Markdown is a rendering view over
the JSON payload and must not add facts, omit evidence, or hide warnings.

Detailed Phase 4 designs live under `docs/superpowers/specs/phase-4/`.
`docs/SPEC.md` remains the top-level contract; the Phase 4 folder owns the
long-form 4A/4B design details.

### 12.1 Selection Rules

The builder should prioritize:

1. explicit user scope
2. current durable specs and architecture pages
3. durable decisions
4. relevant concepts, systems, and workflows
5. available durable change evidence
6. open questions and unresolved warnings
7. raw evidence when it explains a durable page

Timeline-backed recent-change projection remains a Phase 6C responsibility.

The builder should avoid:

- unrelated full-Vault dumps
- duplicated evidence excerpts
- unsupported synthesis
- stale records without warning labels
- context that exceeds the configured token budget

### 12.2 Assembly Flow

```text
Goal
  -> QueryScope normalization
  -> hybrid retrieval
  -> optional graph retrieval only when graph mode is explicit
  -> decision and constraint extraction
  -> current-state summary
  -> evidence grouping
  -> warning collection
  -> token-budget packing
  -> JSON or Markdown rendering
```

### 12.3 Token Budgeting

Public `max_tokens` is an estimated context budget for excerpt-bearing content,
based on stored chunk token counts and deterministic truncation. It is not a
model-specific tokenizer guarantee.

Phase 4 defaults:

- `max_tokens`: 8,000
- `max_evidence_items`: 24
- `max_excerpt_tokens`: 320 per evidence item

The builder keeps required metadata, scope, backend, revisions, warnings, and
evidence metadata before long excerpts. If content must be omitted or
truncated, it includes `budget_omitted` or `excerpt_truncated` warnings.

### 12.4 Graph Signals

Context packs use keyword/vector retrieval by default. Graph signals are
included only when the caller explicitly requests graph mode.

Cross-Vault graph expansion requires all-Vault scope plus explicit
cross-Vault graph mode. This mirrors Phase 3 search and prevents context packs
from silently widening the user's scope.

### 12.5 Builder Boundary

`ContextPackBuilder` owns pack assembly, section classification, budget packing,
warning conversion, and JSON DTO construction.

The `vault_graph.context` package owns context-pack DTOs, builder boundary,
warning conversion, budget packing, JSON serialization, and Markdown rendering.
The builder depends on application services and storage interfaces. It must not
import local SQLite, Chroma, rustworkx, CLI, MCP, HTTP, or LLM adapters. CLI,
MCP, and HTTP surfaces must call the builder instead of assembling pack
sections directly.

## 13. Decision Trace Design

`get_decision_trace(decision_or_topic, scope=None)` should prefer durable
`wiki/decisions/` pages when available.

Flow:

1. resolve the decision ID, title, or topic
2. load matching durable decisions
3. retrieve related source pages, concepts, systems, workflows, and issues
4. expand graph relationships with status labels
5. attach alternatives, tradeoffs, revisit conditions, and evidence
6. warn when the trace depends on inferred or stale relationships

The decision trace response should include:

- decision
- context
- alternatives
- tradeoffs
- evidence
- related documents
- related follow-up questions
- revisit conditions
- warnings

## 14. Memory Projection Design

Memory modules assemble read-only projections over indexed Vault content.

### 14.1 Project Memory

Project memory answers "what is the current state?" for a project or scope.

Output:

- current goal
- decision highlights with evidence
- recent-change handoff to the Phase 6C timeline view
- open issues
- next likely priorities
- evidence links
- stale-area warnings

### 14.2 Decision Memory

Decision memory groups decisions by topic, status, tradeoff, revisit condition,
and related evidence.

### 14.3 Issue Memory

Issue memory groups open questions, unresolved follow-ups, missing evidence, and
revisit triggers.

### 14.4 Timeline Memory

Timeline memory groups indexed document snapshot changes and derived index
changes. It must label whether an item is a document snapshot change, an indexed
projection change, or a warning.

## 15. MCP Design

MCP is the primary agent integration surface.

Detailed Phase 5 designs live under `docs/superpowers/specs/phase-5/`.
`docs/SPEC.md` remains the top-level contract; the Phase 5 folder owns the
long-form 5A/5B/5C design details.

The MCP server is an adapter over application services. It must not introduce a
second retrieval, graph, context-pack, answer, or memory implementation.
Phase 5 registers only tools backed by existing services; answer synthesis and
rich memory projections remain later phases until their application services
exist.

### 15.1 Resources

Initial resources:

```text
vault://{vault_id}/documents/{path}
vault://{vault_id}/pages/{path}
vault://{vault_id}/sources/{id}
vault://{vault_id}/concepts/{name}
vault://{vault_id}/decisions/{id}
vault://{vault_id}/issues/{id}
vault://{vault_id}/timeline/recent
vault://{vault_id}/context/current
vault://context/packs/{id}
vault://{vault_id}/graph/entities/{id}
```

Resources are read-only views over Vault or Vault Graph projections. Responses
should include `vault_id` and evidence metadata when relevant.
`vault://context/packs/{id}` is a generated artifact URI; the pack body records
the `QueryScope` used at creation time.

### 15.2 Tools

Full roadmap tools:

- `search_vault(query, scope=None, limit=10)`
- `ask_vault(question, mode="evidence-first", scope=None)`
- `find_related(target, scope=None, depth=1, kinds=None)`
- `get_decision_trace(decision_or_topic, scope=None)`
- `build_context_pack(goal, scope=None, max_tokens=None)`
- `summarize_project_memory(scope=None, limit=10)`
- `get_open_questions(scope=None, limit=20)`
- `get_recent_changes(since=None, scope=None, limit=20)`
- `explain_result(result_id)`
- `check_index_status(scope=None)`

Tools call application services and return structured, evidence-linked data.
They must not write to Vault.

Tool `scope` arguments use `QueryScope`. Without scope, tools query only the
active Vault. Cross-Vault retrieval requires explicit Vault IDs.
Phase 5 registers only the subset backed by existing application services; tools
that require answer synthesis or Phase 6 memory projections stay out of the
listed MCP tool set until those services exist.

### 15.3 Prompts

Initial prompts:

- `generate_codex_brief`
- `prepare_implementation_context`
- `review_architecture_decision`
- `summarize_feature_history`
- `analyze_project_risk`
- `prepare_wiki_update_context`
- `trace_decision_history`

Prompts must instruct agents to treat Vault Graph output as working context and
to publish durable knowledge only through Vault's validation workflow.

## 16. CLI Design

CLI commands should render human-readable output by default and offer structured
output where useful.

The CLI section describes the full product surface. Phase 3 must not implement
`vg ask`, context packs, MCP serving, or HTTP serving.

Recommended common options:

- `--vault-id ID`
- `--all-vaults`
- `--vault PATH`
- `--state PATH`
- `--config PATH`
- `--json`
- `--verbose`

Command behavior:

- `vg init`: validates paths and writes Vault Graph configuration only
- `vg vault add`: registers an additional readable Vault root
- `vg vault list`: lists configured Vault IDs, paths, and enabled status
- `vg index`: applies incremental derived-state updates for the active Vault
- `vg index --vault-id ID`: applies derived-state updates for one Vault
- `vg index --all-vaults`: applies derived-state updates for all enabled Vaults
- `vg index --full`: applies full derived-state rebuild for the selected scope
- `vg index --dry-run`: reports planned derived-state updates without mutation
- `vg watch`: runs repeated incremental indexing
- `vg status`: reports backend and revision health for the active Vault
- `vg status --vault-id ID`: reports backend and revision health for one Vault
- `vg status --all-vaults`: reports backend and revision health for all enabled
  Vaults with explicit Vault IDs
- `vg ask`: renders evidence-first answers
- `vg related`: renders related entities and evidence
- `vg context`: renders JSON or Markdown context packs
- `vg decision-trace`: renders decision traces
- `vg serve --mcp`: starts the MCP server
- `vg serve --http`: starts the HTTP server

All commands should print active Vault ID, Vault path, and state path when the
operation could otherwise be ambiguous. Commands that operate across Vaults must
make the selected Vault IDs visible.

## 17. HTTP Design

HTTP is an optional adapter over the same services used by CLI and MCP.

The HTTP server should expose stable JSON endpoints for:

- status
- search
- ask
- related items
- decision traces
- context packs
- project memory
- open questions
- recent changes
- result explanations

The HTTP adapter must not introduce behavior that is unavailable through the
application service layer.

## 18. Warning And Error Model

Vault Graph should prefer explicit warnings over silent degradation.

Warning categories:

- `unknown_vault_id`
- `vault_disabled`
- `stale_index`
- `stale_projection`
- `missing_evidence`
- `contested_claim`
- `deprecated_relationship`
- `unregistered_source`
- `source_drift`
- `possible_duplicate`
- `backend_unhealthy`
- `schema_incompatible`
- `token_budget_omission`

Errors should be raised at clear boundaries:

- configuration errors before command execution
- backend health errors before mutation
- schema compatibility errors before query or index work
- path boundary errors before filesystem writes
- evidence resolution errors before rendering unsupported results

When possible, user-facing errors should include the active Vault ID, active
Vault path, active state path, backend name, revision metadata, and a suggested
safe next command.

## 19. Read-Only Enforcement

Read-only behavior should be enforced in three layers.

### 19.1 Path Guard

All write operations must go through a path guard that allows writes only under
the configured Vault Graph state path. The guard should reject writes to every
registered Vault path.

### 19.2 Store Boundary

Only store implementations may write derived state. Ingestion, extraction,
retrieval, projection algorithms, memory services, CLI, MCP, and HTTP adapters
should not perform arbitrary file writes.

### 19.3 Contract Tests

Tests should create a fixture Vault, run indexing and retrieval operations, and
assert that Vault file hashes do not change.

Required coverage:

- indexing does not mutate Vault
- dry-run does not mutate Vault Graph state
- MCP tools do not mutate Vault
- context-pack generation does not mutate Vault
- projection cache writes stay under the state path

## 20. Versioning And Freshness

Index and projection records should include enough version metadata to decide
whether a result is fresh.

Revision fields:

- `vault_id`
- `vault_revision`
- `index_revision`
- `metadata_revision`
- `vector_revision`
- `graph_revision`
- `projection_revision`
- `parser_version`
- `chunker_version`
- `embedding_model`
- `embedding_model_version`
- `embedding_spec_version`
- `graph_extraction_spec_version`
- `graph_extraction_spec_digest`
- `metadata_store_schema_version`
- `vector_store_schema_version`
- `graph_store_schema_version`
- `graph_projection_version`
- `backend_name`
- `backend_schema_version`
- `last_validated_at`

Status output should report freshness separately for metadata, vector, graph,
and projection state.

## 21. Testing Strategy

Testing should follow the roadmap phases in `docs/SPEC.md` and keep fixtures
deterministic.

### 21.1 Unit Tests

Unit tests should cover:

- Vault catalog loading and active Vault selection
- QueryScope normalization
- Vault frontmatter projection
- Markdown section parsing
- document normalization
- chunking
- entity extraction
- relationship extraction
- warning classification
- context-pack assembly
- ranking explanation assembly

### 21.2 Contract Tests

Contract tests should cover:

- `MetadataStore` local behavior
- `VectorStore` local behavior
- `GraphStore` local behavior
- `VectorStore` filtering by `QueryScope.vault_ids` and
  `QueryScope.content_scopes`
- metadata evidence resolution before retrieval result rendering
- future Postgres behavior against the metadata contract
- future Qdrant behavior against the vector contract
- future Neo4j behavior against the graph contract
- Vault-scoped identity uniqueness across local and scale-up backends

Scale-up backends should pass the same representative behavior tests as local
backends.

### 21.3 Boundary Tests

Boundary tests should cover:

- no Vault mutation during indexing
- no Vault mutation during MCP tool calls
- no Vault mutation during context-pack generation
- no writes outside the state path
- dry-run planning without store mutation
- projection cache invalidation on revision changes
- partial indexing does not mark unrelated Vault IDs stale

### 21.4 Integration Tests

Integration tests should cover:

- full rebuild over a fixture Vault
- full rebuild over two fixture Vaults with colliding relative paths
- incremental rebuild after a changed document
- tombstone behavior after a deleted document
- search result evidence resolution
- decision trace evidence resolution
- context-pack JSON contract
- CLI status output
- MCP tool response shape

## 22. Implementation Order

Implementation should follow the phase order from `docs/SPEC.md`.

1. Vault reader and `MetadataStore`
2. Phase 2A: retrieval contract and `VectorStore` boundary
3. Phase 2B: local vector indexing
4. Phase 2C: evidence-first keyword and vector search
5. entity and relationship graph
6. context pack builder
7. MCP server
8. memory and explorer projections
9. optional UI

Each phase should preserve the read-only boundary and include focused tests
before expanding the next layer.

## 23. Design Checks

Before a phase is considered complete, verify:

- Vault files are unchanged by Vault Graph commands
- generated state can be deleted and rebuilt
- result evidence resolves back to Vault IDs, Vault paths, and revisions
- status surfaces report backend health and freshness
- warnings are visible for stale, missing, contested, or deprecated material
- application services depend on storage interfaces rather than concrete
  backends
- local-first operation works without hosted services

## 24. Acceptance Criteria

The design is satisfied when:

- `vg index --dry-run` can explain planned derived-state changes without
  mutation
- `vg index` can build local metadata, vector, and graph projections without
  mutating Vault
- `vg index --vault-id ID` updates only that Vault's derived state
- `vg index --all-vaults` can rebuild all registered Vault projections
- `vg status` reports backend health, schema compatibility, index freshness,
  and projection freshness
- `vg ask` returns evidence-first answers with warnings instead of unsupported
  claims
- `vg context` returns a context pack matching the required JSON contract
- `vg decision-trace` prefers durable decision pages and labels inferred graph
  relationships
- MCP tools expose the same read-only behavior as CLI commands
- all derived indexes can be deleted and rebuilt from Vault
- two registered Vaults with the same relative path do not collide in metadata,
  vector, graph, MCP, or context-pack output

Vault Graph is valuable only while it keeps Vault authoritative. Every module
boundary, store contract, warning, and test should protect that rule.
