# Vault Graph Specification

Version: 1.1

Status: Active product contract

Author: Jun Hyoung Lee

Date: 2026-06-04

Updated: 2026-06-26

## 1. Vision

Vault is the durable source of truth for project knowledge.

Vault Graph is a read-only, rebuildable knowledge access and reasoning layer
over Vault. It helps agents and humans discover context, trace decisions,
assemble task-specific context packs, and answer questions from cited Vault
evidence without turning retrieval or reasoning output into durable knowledge.

The goal is not simple document search. The goal is to make the value of Vault easier to use:

- Project memory projection
- Decision tracing
- Context management
- Agent context packs
- Evidence-first ask and reasoning
- GraphRAG-style exploration
- Development knowledge assetization

Vault remains the durable authority. Vault Graph interprets and indexes Vault.
Agents consume Vault Graph outputs as working context, cited answers, and
reasoning traces, not as a replacement for Vault.

## 2. Relationship To Vault

Vault uses a quality-gated compiled wiki model:

```text
raw source
-> LLM semantic draft
-> deterministic validation
-> durable wiki page
-> index / links / log / reports
-> Git history
```

Vault Graph must preserve this boundary.

```text
Vault
  raw/
  wiki/
  scratch/reports/
  docs/
    |
    v
Vault Graph
  MetadataStore
  VectorStore
  GraphStore
  GraphProjection
  context packs
  MCP resources/tools/prompts
```

Vault Graph does not publish durable knowledge. If a retrieved answer or context pack should become durable, it must flow back through the existing Vault workflow: source capture, semantic draft, provenance checks, lint, release gate validation, and Git history.

## 3. Design Principles

### Principle 1: Vault Is The Source Of Truth

Vault Graph never edits, renames, rewrites, or deletes files in Vault.

Vault Graph may read:

- `raw/`
- `wiki/`
- `docs/`
- `scratch/reports/`
- selected Git metadata

Vault Graph must not treat its own indexes, summaries, extracted entities, graph edges, or context packs as authoritative knowledge.

### Principle 2: All Derived Data Is Rebuildable

Everything created by Vault Graph is a projection from Vault:

- Metadata index
- Vector index
- Graph index
- Project memory projection
- Decision memory projection
- Issue memory projection
- Timeline projection
- Context packs
- Summaries

Deleting all Vault Graph state and rebuilding from Vault should produce
functionally equivalent results for the same version of the parser, chunker,
embedding model, and graph extraction spec.

### Principle 3: Agents Consume Evidence-Linked Context

Agents should not read an entire Vault for ordinary tasks. They should request a
scoped search result, context pack, decision trace, memory projection, or cited
answer.

```text
Vault
  |
  v
Vault Graph retrieval
  |
  v
Evidence / Context Pack / Answer
  |
  v
Agent
```

Vault Graph output is evidence-linked working context. It is not durable
knowledge until a human or agent intentionally publishes it back through
Vault's validation workflow.

### Principle 4: Local First

The core system must work without internet access.

Local-first requirements:

- Local filesystem indexing
- Local metadata store
- Local graph store for MVP
- Local vector store for MVP
- Configurable local embedding model
- No mandatory hosted database or SaaS dependency

Remote services may be optional scale-up integrations, but they must not be required for the default workflow.

### Principle 5: Provenance Over Fluency

Vault Graph answers should prefer cited, inspectable evidence over polished but unsupported synthesis.

Every answer, context pack, decision trace, and memory projection should
include:

- Source path or wiki page path
- Section or anchor when available
- Content hash or raw SHA-256 when available
- Retrieval reason
- Confidence or warning when the result is inferred

## 4. High-Level Architecture

```text
                +---------------------------+
                |       VaultCatalog        |
                | vault_id -> Vault root    |
                +-------------+-------------+
                              |
                              v
                +---------------------------+
                |        Vault Loader       |
                | parse, normalize, hash    |
                +-------------+-------------+
                              |
              +---------------+---------------+
              |                               |
              v                               v
      +----------------+              +----------------+
      | MetadataStore  |              | VectorStore    |
      | SQLite         |              | Chroma         |
      +-------+--------+              +-------+--------+
              |                               |
              v                               v
      +----------------+              +----------------+
      | GraphStore     |<------------>| Hybrid Search  |
      | SQLite graph   |              | rank + explain |
      +-------+--------+              +-------+--------+
              |
              v
      +----------------+
      | GraphProjection|
      | rustworkx      |
      +-------+--------+
              |
              +---------------+
                              |
                              v
                +---------------------------+
                |   Context Pack Builder    |
                +-------------+-------------+
                              |
                              v
                +---------------------------+
                | Evidence Planner / Ask    |
                | cited answer composer     |
                +-------------+-------------+
                              |
                              v
                +---------------------------+
                |       MCP / CLI / HTTP    |
                +-------------+-------------+
                              |
                              v
              Codex / Claude / Cursor / custom agents
```

## 5. Repository Structure

```text
vault-graph/
├── pyproject.toml
├── README.md
├── docs/
│   └── SPEC.md
├── configs/
│   ├── vaults.yaml
│   ├── entity_schema.yaml
│   ├── retrieval_policy.yaml
│   ├── embedding_spec.yaml
│   ├── storage_backends.yaml
│   └── scaleup_backends.example.yaml
├── data/
│   ├── metadata/
│   │   └── .gitkeep
│   ├── vector/
│   │   └── .gitkeep
│   ├── graph/
│   │   └── .gitkeep
│   ├── projection_cache/
│   │   └── .gitkeep
│   └── migrations/
│       └── .gitkeep
├── src/
│   └── vault_graph/
│       ├── app/
│       │   ├── catalog_service.py
│       │   ├── index_service.py
│       │   ├── search_readiness_service.py
│       │   ├── graph_readiness_service.py
│       │   ├── graph_retrieval_service.py
│       │   ├── answer_service.py
│       │   └── path_guard.py
│       ├── ingestion/
│       │   ├── vault_catalog.py
│       │   ├── vault_loader.py
│       │   ├── markdown_parser.py
│       │   ├── vault_frontmatter_reader.py
│       │   └── document_normalizer.py
│       ├── extraction/
│       │   ├── entity_extractor.py
│       │   ├── relationship_extractor.py
│       │   ├── decision_extractor.py
│       │   ├── issue_extractor.py
│       │   └── timeline_extractor.py
│       ├── indexing/
│       │   ├── metadata_indexer.py
│       │   ├── vector_indexer.py
│       │   ├── graph_indexer.py
│       │   ├── revision_planner.py
│       │   └── incremental_indexer.py
│       ├── projection/
│       │   ├── graph_projection.py
│       │   ├── rustworkx_projection.py
│       │   └── projection_cache.py
│       ├── retrieval/
│       │   ├── vector_retriever.py
│       │   ├── graph_retriever.py
│       │   ├── hybrid_retriever.py
│       │   ├── reranker.py
│       │   └── search_response.py
│       ├── context/
│       │   ├── context_pack.py
│       │   ├── context_pack_builder.py
│       │   ├── context_pack_renderer.py
│       │   ├── context_pack_serialization.py
│       │   └── context_pack_warnings.py
│       ├── answer/
│       │   ├── answer_plan.py
│       │   ├── evidence_planner.py
│       │   ├── answer_composer.py
│       │   ├── citation_guard.py
│       │   ├── answer_response.py
│       │   └── answer_renderer.py
│       ├── mcp/
│       │   ├── mcp_server.py
│       │   ├── mcp_service_factory.py
│       │   ├── mcp_scope.py
│       │   ├── mcp_errors.py
│       │   ├── mcp_resources.py
│       │   ├── mcp_tools.py
│       │   └── mcp_prompts.py
│       ├── memory/
│       │   ├── project_memory.py
│       │   ├── decision_memory.py
│       │   ├── issue_memory.py
│       │   └── timeline_memory.py
│       ├── storage/
│       │   ├── interfaces/
│       │   │   ├── metadata_store.py
│       │   │   ├── keyword_index.py
│       │   │   ├── vector_store.py
│       │   │   ├── graph_store.py
│       │   │   └── store_health.py
│       │   ├── local/
│       │   │   ├── sqlite_metadata_store.py
│       │   │   ├── sqlite_keyword_index.py
│       │   │   ├── chroma_vector_store.py
│       │   │   └── sqlite_graph_store.py
│       │   ├── adapters/
│       │   │   ├── postgres_metadata_store.py
│       │   │   ├── qdrant_vector_store.py
│       │   │   └── neo4j_graph_store.py
│       │   ├── migrations/
│       │   │   ├── metadata_migrations.py
│       │   │   ├── vector_migrations.py
│       │   │   └── graph_migrations.py
│       │   └── revisions.py
│       └── cli/
│           └── main.py
└── tests/
    ├── test_loader.py
    ├── test_incremental_indexing.py
    ├── test_context_pack.py
    ├── test_read_only_boundary.py
    ├── test_metadata_store_contract.py
    ├── test_vector_store_contract.py
    ├── test_graph_store_contract.py
    ├── test_graph_projection_cache.py
    ├── test_evidence_planner.py
    └── test_answer_composer.py
```

The default implementation is local-first. Files under `storage/local/` are required for MVP. Files under `storage/adapters/` define optional scale-up adapter boundaries for Postgres, Qdrant, and Neo4j; they must not make hosted services mandatory for the default workflow.

`storage/interfaces/` owns the stable store contracts. Indexing, retrieval, MCP tools, and context pack builders must depend on these interfaces instead of importing local or scale-up backend implementations directly.

`context/` owns canonical context-pack DTOs, pack assembly, warning conversion,
budget packing, JSON serialization, and Markdown rendering. It consumes
retrieval application services and storage interfaces; it must not import local
SQLite, Chroma, rustworkx, CLI, MCP, HTTP, or LLM adapters.

`mcp/` owns the MCP adapter: stdio server construction, MCP tool/resource/prompt
registration, MCP argument DTOs, MCP error mapping, and local client
configuration examples. It calls application services and must not own
retrieval ranking, graph algorithms, context-pack assembly, indexing, or Vault
publication.

`projection/` owns runtime algorithm projections only. It may read from `GraphStore` and write disposable cache files under `data/projection_cache/`, but it must not persist authoritative graph records.

## 6. Multi-Vault Model

Vault Graph should support one running instance over one or more registered Vault
repositories. Single-Vault use remains the default path: `vg init --vault
/path/to/vault` creates a `default` Vault entry when no explicit `vault_id` is
provided.

The multi-Vault boundary is `VaultCatalog`. It is the only authority for the
mapping from `vault_id` to Vault repository root. A catalog entry identifies a
readable Vault repository root, not a Vault source page or durable source
registry entry. `VaultCatalog` must never replace Vault's own source
registration, source validation, frontmatter validation, publication gate,
release gate, or Git history.

Required `VaultCatalog` entry fields:

- `vault_id`
- `root_path`
- `display_name`
- `enabled`
- `content_scopes`
- `state_namespace`
- `git_revision_policy`

Identity rules:

- `vault_id` is required on every document, chunk, entity, evidence, revision,
  warning, and context-pack record.
- Relationship records must carry `source_vault_id` and `target_vault_id`;
  relationship evidence references must carry their evidence `vault_id`.
- `path` is never globally unique by itself; file identity is `(vault_id, path)`.
- `document_id`, `chunk_id`, `entity_id`, `relationship_id`, and vector IDs
  must either include their Vault namespace fields in stable derivation or be
  stored with equivalent Vault-scoped uniqueness constraints.
- Cross-Vault search is explicit. Default queries use the active Vault unless a
  `QueryScope` names more Vault IDs.
- Cross-Vault entity merging is outside the MVP. If retrieval connects records
  across Vaults, the relationship must be an evidence-linked inferred edge, not a
  durable equivalence claim.

`QueryScope` separates repository selection from content selection:

- `vault_ids`: one or more registered Vault IDs
- `content_scopes`: `raw`, `wiki`, `docs`, `scratch/reports`, or narrower policy
  scopes
- `include_cross_vault`: false by default

CLI `--all-vaults` options are expanded into an explicit list of enabled
`vault_ids` before application services run. Stores and retrieval services do not
interpret an implicit global scope.

Scale-up backends must preserve the same logical model. Postgres may implement
`vault_id` as a tenant key, Qdrant may implement it as payload filtering or
collection sharding, and Neo4j may implement it as node and edge properties, but
the application contract remains the same.

## 7. Core Capabilities

### 7.1 Project Memory Projection

Question:

```text
프로젝트 현재 상태는?
```

Response shape:

- Current goal
- Decision highlights with evidence
- Recent indexed document snapshot changes through the Phase 6C timeline view
  when available
- Open issues
- Next likely priorities
- Evidence links
- Warnings or stale areas

This is a projection from Vault, not a separate memory database.

### 7.2 Evidence-First Ask And Reasoning

Question:

```text
왜 GraphRAG를 도입했는가?
```

Response shape:

- Answer
- Direct evidence
- Inferred links
- Reasoning trace
- Unsupported or partial claims
- Warnings
- Suggested durable follow-up

`ask_vault` and `vg ask` answer natural-language questions by planning a small
set of evidence-gathering steps over existing search, graph, decision-trace,
context-pack, and memory projection services. They do not create a writable
memory layer and do not make generated answers durable Vault knowledge.

Every major answer claim must be supported by cited Vault evidence or labeled
as unsupported, partial, inferred, or missing. If evidence is insufficient, the
answer should say so and suggest the next safe Vault workflow or indexing
command instead of filling gaps with fluent synthesis.

### 7.3 Decision Tracking

Question:

```text
왜 GraphRAG를 선택했는가?
```

Response shape:

- Decision
- Context
- Alternatives
- Tradeoffs
- Evidence
- Related documents
- Related follow-up questions
- Revisit conditions

The system should prefer durable `wiki/decisions/` pages when they exist. It may use graph/vector retrieval to find supporting source pages, raw evidence, and related concepts.

### 7.4 Context Management

Question:

```text
GraphRAG MVP를 구현하기 위한 context를 생성해줘.
```

Response shape:

- Goal
- Relevant specs
- Relevant decisions
- Relevant architecture
- Relevant research
- Open issues
- Constraints
- Warnings
- Suggested next actions

### 7.5 Agent Context Packs

Context packs are structured briefs for agents.

Required fields:

- `goal`
- `context_pack_schema_version`
- `pack_id`
- `scope`
- `vaults`
- `vault_revisions`
- `backend`
- `store_revisions`
- `retrieval_policy_version`
- `budget`
- `current_state`
- `relevant_pages`
- `relevant_sources`
- `decisions`
- `constraints`
- `open_questions`
- `warnings`
- `evidence`
- `generated_at`

### 7.6 GraphRAG Exploration

Question:

```text
GraphRAG와 관련된 모든 의사결정을 보여줘.
```

The system should combine:

- keyword search
- vector search
- graph neighborhood traversal
- durable wiki link traversal
- decision-map or timeline-map traversal when available

Returned answers must distinguish:

- stated facts
- inferred relationships
- contested claims
- stale or deprecated material
- missing evidence

### 7.7 Knowledge Assetization

Vault Graph turns documents into queryable assets:

```text
Document
  -> Section
  -> Chunk
  -> Entity
  -> Relationship
  -> Evidence-linked knowledge asset
```

The final asset is still derived data. Durable knowledge remains in Vault.

## 8. Entity Model

### 8.1 Core Entities

The entity model should align with Vault's durable page model first:

- `Source`
- `WikiPage`
- `Concept`
- `Entity`
- `System`
- `Workflow`
- `Decision`
- `Claim`
- `Comparison`
- `Timeline`
- `Map`

### 8.2 Project Entities

Domain-specific entities may be extracted from page bodies and source text:

- `Project`
- `Feature`
- `Document`
- `Issue`
- `Research`
- `Meeting`
- `Architecture`
- `Tool`
- `Person`
- `TimelineEvent`

### 8.3 Entity Fields

Minimum entity fields:

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

Entity evidence references point to `MetadataStore` evidence chunks. Path lists
and wiki/source groupings are rendering views over evidence references, not
separate entity authority.

## 9. Relationship Model

Core relationship types:

- `related_to`
- `depends_on`
- `affects`
- `based_on`
- `caused_by`
- `resolved_by`
- `supersedes`
- `superseded_by`
- `discussed_in`
- `implements`
- `blocks`
- `revisit_when`
- `evidenced_by`
- `contradicts`
- `mentions`
- `links_to`

Relationship fields:

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

`RelationshipRecord` is one logical relationship with one or more evidence
references. Evidence references are stored as separate graph evidence rows,
keyed by `evidence_ref_id`, and each reference resolves to a `MetadataStore`
chunk. This avoids duplicate relationship rows when multiple chunks support the
same relationship.

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
`owner_id` is the `entity_id` or `relationship_id`. Paths and excerpts are
rendering metadata. Relationship evidence authority comes from the evidence
chunk resolved through `MetadataStore`.

Allowed relationship statuses:

- `stated`
- `inferred`
- `contested`
- `deprecated`

## 10. Storage Strategy

### 10.1 MVP

Metadata:

- file-backed `VaultCatalog` configuration for registered Vault roots
- SQLite persisted document, chunk, hash, parser state, source-state projection,
  and index revision tables as `MetadataStore`

Vector search:

- Chroma persisted embeddings and vector retrieval metadata as `VectorStore`
- local embedding model by default
- Chroma is part of the default installation for local vector indexing. It is
  a local dependency, not a hosted service requirement.

Graph:

- SQLite persisted entity, relationship, evidence, tombstone, and graph revision
  tables as `GraphStore`
- rustworkx in-memory graph projection rebuilt from `GraphStore`
- optional serialized rustworkx cache keyed by `index_revision`,
  `graph_store_revision`, `parser_version`, `chunker_version`, and
  `graph_extraction_spec_version` plus `graph_extraction_spec_digest`

### 10.2 Scale-Up

Metadata:

- Postgres

Vector search:

- Qdrant

Graph:

- Neo4j or another external graph backend behind the `GraphStore` interface

Graph algorithm runtime:

- rustworkx for local subgraph traversal, ranking, and decision trace explanation when the working subgraph fits local memory
- backend-native graph queries for large traversals that should not be materialized into process memory

### 10.3 MetadataStore Boundary

`MetadataStore` is the persisted metadata projection.

For MVP, `MetadataStore` is SQLite tables derived from registered Vault files and
indexer output. It stores document records, chunk records, Vault IDs, Vault
paths, wiki paths, source-page projection state, Vault frontmatter snapshots,
content hashes, raw SHA-256 values where available, parser state, chunker state,
and index revision metadata. It is rebuildable from Vault and must remain
non-authoritative. `VaultCatalog`, not `MetadataStore`, owns the authoritative
`vault_id` to Vault root mapping.

The boundary is mandatory:

- `MetadataStore` owns file identity, chunk identity, `(vault_id, path)` mapping,
  content hashes, parser/chunker version state, source-state projections, and
  index revision tracking for derived records.
- `MetadataStore` may record revision-scoped catalog snapshots for diagnostics,
  but it must not become the source of truth for registered Vault roots.
- `MetadataStore` must not mutate Vault files, source pages, wiki pages, docs, or scratch artifacts.
- `MetadataStore` must not store durable semantic truth that is not traceable back to Vault files and evidence references.
- `MetadataStore` must not become a frontmatter validator, source registry, publication gate, or replacement for Vault's own `tools/wiki` checks.
- Query tools must resolve document and chunk IDs back to `vault_id`, Vault
  paths, wiki paths, anchors, hashes, and revision metadata. Application services
  resolve `vault_id` display metadata through `VaultCatalog`.
- Postgres must be a scale-up `MetadataStore` implementation over the same logical record contract, not a different metadata model.

Required `MetadataStore` capabilities:

- upsert document snapshots and chunk snapshots for an index revision
- list changed, stale, deleted, and tombstoned documents
- list current non-tombstoned chunks for a `QueryScope` so vector and graph
  indexers can reconcile derived projections without reading backend tables
  directly
- resolve document IDs and chunk IDs to evidence locations
- record parser, chunker, index, and backend schema versions
- report backend health, schema compatibility, and revision freshness
- export or inspect records in the common logical metadata shape

### 10.4 VectorStore Boundary

`VectorStore` is the persisted embedding and vector retrieval projection.

For MVP, `VectorStore` is Chroma collections derived from `MetadataStore` chunks
and local embedding output. It stores embedding vectors, vector IDs, `vault_id`,
document IDs, chunk IDs, content-scope filter metadata, embedding model
metadata, embedding model spec metadata, filters, and index revision metadata.
It is rebuildable from Vault through `MetadataStore` and must remain
non-authoritative.

The boundary is mandatory:

- `VectorStore` owns embedding persistence, vector search, embedding model version state, vector index revision tracking, and vector backend replacement.
- `VectorStore` must not own document identity, chunk text authority, evidence authority, graph relationships, or durable wiki publication.
- Query tools must resolve vector hits through `MetadataStore` before returning evidence.
- Vector hits must return only semantic candidate metadata: vector IDs,
  `vault_id`, document IDs, chunk IDs, content-scope filter metadata, embedding
  model versions, index revisions, backend-local scores, and backend-local ranks.
- Vector hits must not return path, title, summary, anchor, chunk text, content
  hashes, or rendered evidence as user-facing authority. Those fields must be
  resolved through `MetadataStore` before rendering.
- Vector manifest records must include enough metadata to reconcile derived
  vector state: source chunk hash, chunker version, metadata index revision,
  embedding model spec, vector index revision, backend name, and backend schema
  version.
- Qdrant must be a scale-up `VectorStore` implementation over the same logical record contract, not a different retrieval authority.

Required `VectorStore` capabilities:

- upsert embeddings for chunk IDs from a specific metadata/index revision
- delete or tombstone embeddings for stale chunks
- run filtered vector search with `QueryScope.vault_ids`,
  `QueryScope.content_scopes`, model, and revision metadata
- apply `QueryScope.content_scopes` with the same same-or-child semantics used
  by metadata indexing before applying result limits
- validate embedding dimensions, model name, model version, and embedding model spec version
- report backend health, collection/schema compatibility, and index freshness
- export or inspect embedding manifests in the common logical vector shape

Phase 2B must expand the vector manifest and tombstone records before Chroma is
implemented:

- `VectorManifestRecord` adds `source_chunk_hash`, `chunker_version`, and
  `backend_schema_version`.
- `VectorTombstone` identifies the stale vector row with `vector_id`,
  `vault_id`, `chunk_id`, and `EmbeddingModelSpec`. `(vault_id, chunk_id)` alone
  is not precise enough once old-model and current-model records can coexist.
- `VectorStore.export_manifest(scope)` returns active manifest rows for the
  actual scope across all Chroma model-spec collections, not only the current
  `EmbeddingModelSpec`, so model-spec changes can be reconciled and old rows can
  be tombstoned.

Phase 2B vector indexing uses scope-local reconcile:

```text
MetadataStore.list_chunks(scope)
  + VectorStore.export_manifest(scope)
  + current EmbeddingModelSpec
  -> desired vector records
  -> upserts for missing or stale chunks
  -> tombstones for records no longer desired
  -> VectorStore.apply_vector_revision(...)
```

The reconcile scope is the selected `QueryScope`. A narrow run such as
`vg index --vault-id work` or a future content-scope-limited run must not mark
unselected Vaults or unrelated content scopes stale. A full rebuild expands the
work set only inside the selected scope, and it still writes only Vault Graph
derived state.

Application services must resolve a user-selected `QueryScope` against
`VaultCatalog` before vector reconcile. Multi-vault scopes are processed as
per-Vault actual scopes using the same broader/narrower content-scope rules
as `VaultLoader`. Store methods receive explicit actual scopes; they must not
infer catalog entry constraints from a global union of content scopes.

Vector records are stale when any of these fields differ from the current
desired state:

- `source_chunk_hash`
- `chunker_version`
- `metadata_index_revision`
- `EmbeddingModelSpec`
- vector backend schema version

`vector_index_revision` is manifest and status metadata, not a staleness
comparison key. Otherwise every successful vector run would make unchanged
records appear stale in the next run.

If metadata indexing succeeds but vector indexing fails, Vault Graph must keep
the metadata revision and report vector freshness as stale or unavailable. The
`vg index` command should return a nonzero exit for the failed vector step while
making the applied metadata revision visible in output and status. The next
`vg index` must be able to recover through the same reconcile algorithm. Vault
Graph should not require a cross-store transaction between `MetadataStore` and
`VectorStore`.

### 10.5 GraphStore And GraphProjection Boundary

`GraphStore` is the persisted graph projection.

For MVP, `GraphStore` is SQLite tables derived from Vault files and indexer
output. It stores entity records, relationship records, `vault_id` fields,
evidence references, relationship status, confidence, extraction metadata,
tombstones, and index revision metadata. It is rebuildable from Vault and must
remain non-authoritative.

`GraphProjection` is the runtime graph used for algorithms.

For MVP, `GraphProjection` is a rustworkx graph built from `GraphStore` rows. It
is used for traversal, path finding, ranking, neighborhood expansion, and
decision trace prototypes. It may be serialized only as a cache. A serialized
rustworkx graph must be disposable and must be invalidated when any graph store
row, parser version, chunker version, graph extraction spec version, graph
store revision, or index revision changes.

The boundary is mandatory:

- `GraphStore` owns persistence, revision tracking, evidence linkage, and backend replacement.
- `GraphProjection` owns in-process graph algorithms and temporary working subgraphs.
- Query tools must return evidence-linked results from `GraphStore`, not opaque
  rustworkx runtime indices.
- rustworkx must not be treated as the durable graph database.
- Neo4j must not become a second source of truth; it is a scale-up `GraphStore` implementation over the same derived projection contract.
- Scale-up backends must preserve the same Vault IDs, entity IDs, relationship
  IDs, relationship types, evidence references, confidence fields, revision
  fields, and read-only Vault boundary as the MVP SQLite store.
- Every backend must support full rebuild, incremental update, dry-run planning, stale projection detection, and reproducible export back to the common graph store contract.

### 10.6 Scale-Up Boundary Requirements

Scale-up must be adapter-driven, not architecture-changing.

The MVP local stores are the reference contract:

- `MetadataStore`: SQLite for documents, chunks, hashes, parser state, and index
  revisions.
- `VectorStore`: Chroma for embeddings and vector retrieval metadata, including
  `vault_id` filters.
- `GraphStore`: SQLite for entity records, relationship records, evidence,
  relationship status, confidence, Vault IDs, tombstones, and graph revisions.
- `GraphProjection`: rustworkx for local in-memory graph algorithms over a bounded working subgraph.

Scale-up backends may replace implementations, but not contracts:

- Postgres may replace SQLite-backed metadata when larger teams need concurrent access or stronger operational tooling.
- Qdrant may replace Chroma-backed vector retrieval when vector volume, filtering, or serving latency requires it.
- Neo4j may replace SQLite-backed graph persistence when graph traversal volume or query complexity exceeds local SQL traversal.
- rustworkx may remain as a local algorithm adapter for explainable working subgraphs even when Neo4j is the graph store.

All persistent store adapters must expose the same common revision model:

- stable record IDs for the records they own
- Vault ID, Vault path, wiki path, section or anchor, content hash, and raw
  SHA-256 where available
- parser, chunker, embedding model spec, graph extraction spec, metadata store,
  vector store, and graph store versions where applicable
- index revision, vault revision, backend name, backend schema version, and last validated timestamp
- evidence references for every returned record that contributes to an answer, trace, warning, or context pack

Each store also owns store-specific records:

- `MetadataStore`: document IDs, chunk IDs, file state, source-state projection,
  parser state, chunker state, and tombstones
- `VectorStore`: vector IDs, Vault IDs, document IDs, chunk IDs, content-scope
  filter metadata, embedding model, embedding model version, embedding model spec
  version, filters, backend-local ranks, and backend-local retrieval scores
- `GraphStore`: Vault IDs, entity IDs, relationship IDs, relationship type,
  relationship status, confidence, extraction method, and evidence references
- `GraphProjection`: projection build ID, graph projection version, source graph revision, cache validity, and algorithm runtime metadata

Scale-up must preserve local-first operation:

- A default installation must run without hosted services.
- Optional remote or server backends must have explicit configuration.
- If an optional backend is unavailable, Vault Graph should fail with a clear backend health error or fall back to the local store only when configured to do so.
- Backend health, schema compatibility, index revision freshness, and projection freshness must be visible through CLI/MCP status surfaces.

Scale-up must preserve reproducibility:

- Every persistent backend must support full rebuild from Vault.
- Every persistent backend must support dry-run migration planning before mutation.
- Every persistent backend must support export or inspection in the common logical record shape.
- Contract tests must compare local SQLite/Chroma/rustworkx results against scale-up backend results for representative metadata lookup, vector retrieval, graph traversal, ranking, context-pack, and decision-trace queries.
- Vector contract tests must prove filtering by both `QueryScope.vault_ids` and
  `QueryScope.content_scopes` before result limits are applied.
- Retrieval contract tests must prove final evidence is resolved through
  `MetadataStore`, not trusted from vector hits.
- Query responses must include evidence references and the backend/revision
  metadata used to produce each contributing signal or store record.

Scale-up storage must remain replaceable. It must not change the source-of-truth boundary.

## 11. Incremental Indexing

Vault Graph tracks file state with:

- `path`
- `vault_id`
- `kind`
- `content_hash`
- `raw_sha256`
- `frontmatter_hash`
- `parser_version`
- `chunker_version`
- chunk content hash copied into vector manifests as `source_chunk_hash`
- `metadata_store_schema_version`
- `vector_store_schema_version`
- `embedding_model`
- `embedding_model_version`
- `graph_extraction_spec_version`
- `graph_extraction_spec_digest`
- `graph_store_schema_version`
- `graph_projection_version`
- `last_indexed_at`
- `last_seen_at`

Indexing flow:

```text
Scan VaultCatalog entries selected by the indexing scope
  -> Detect changes
  -> Read Vault frontmatter and parse markdown
  -> Normalize document
  -> Chunk content
  -> Update MetadataStore document, chunk, hash, and revision rows
  -> Reconcile VectorStore embeddings and vector revision metadata when vector
     indexing is enabled
  -> Phase 3+: extract entities and relationships
  -> Phase 3+: update GraphStore entity, relationship, evidence, and revision
     rows
  -> Phase 3+: invalidate or rebuild GraphProjection cache
  -> Record index revision
```

The indexer must support:

- full rebuild
- incremental rebuild
- stale file detection
- deleted file tombstones
- parser or embedding model spec migration
- metadata store schema migration
- vector store schema migration
- graph store schema migration
- graph projection cache invalidation
- dry-run mode

For multiple registered Vaults, indexing plans work per `vault_id` and then
record one logical index revision for the applied run. The default indexing
scope is the active Vault. A partial run such as `vg index --vault-id work` must
not mark unrelated Vaults stale. `vg index --all-vaults` is the explicit
whole-catalog operation.

### Vault Source Boundary

Incremental indexing must not replace Vault source registration.

Vault Graph may cache `raw_sha256`, source-page metadata, frontmatter fields, registry status, duplicate signals, and stale-file signals only as read-only projections derived from Vault. These cached values help decide what to re-index; they are not a second source registry, a frontmatter validation authority, or durable knowledge.

Vault Graph must not create, edit, rename, delete, merge, redirect, deprecate, or publish Vault source pages or wiki pages during indexing. It must not write to `raw/`, `wiki/`, `docs/`, or `scratch/` as part of scan, parse, normalize, chunk, extraction, or index-update work.

Source registration, source drift handling, slug collision handling, durable duplicate review, frontmatter schema validation, wiki index mutation, wiki log mutation, semantic draft publication, and release-gate validation remain owned by Vault's existing `tools/wiki` workflow.

If indexing detects an unregistered source, source drift, deleted source, possible duplicate, or extraction insight that should become durable, Vault Graph must report it as a warning, context-pack item, or explicit command suggestion. The durable follow-up must flow through Vault's normal source capture, semantic draft, validation, review, and Git history path.

## 12. Read-Only Boundary

The project must enforce read-only behavior at multiple levels:

- CLI operations are read-only with respect to Vault.
- File operations are restricted to configured Vault Graph state directories.
- Tests assert that indexing does not mutate Vault files.
- MCP tools that return context do not write to Vault.
- Any future "capture back to Vault" feature must produce an explicit draft artifact or command suggestion, not silently edit Vault.

Non-goals for MVP:

- automatic wiki publication
- automatic raw source mutation
- automatic contradiction resolution
- autonomous truth arbitration

## 13. MCP Server

Vault Graph's main agent integration surface is MCP.

MCP is appropriate because it can expose:

- resources for documents and generated context
- tools for search and context building
- prompts for repeatable agent workflows

Supported clients:

- Codex
- Claude
- Cursor
- OpenCode
- custom agents

## 14. MCP Resources

Initial resource URIs:

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

Resource responses must include evidence metadata where relevant, including
`vault_id` for any Vault-derived record. `vault://context/packs/{id}` is a
generated artifact URI; each context pack stores the `QueryScope` used at
creation time.

## 15. MCP Tools

Product tool surface:

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

Tool responses must separate:

- answer
- evidence
- inferred links
- warnings
- suggested durable follow-up

Tool `scope` arguments use `QueryScope`. If no scope is provided, tools search
the active Vault only. Cross-Vault retrieval requires explicit `vault_ids`.
MCP registration exposes only the subset backed by existing application
services. `ask_vault`, result explanation, and memory projection tools are
registered because their backing application services exist; future tools must
wait for the same service-backed boundary.

## 16. MCP Prompts

Initial prompts:

- `generate_codex_brief`
- `prepare_implementation_context`
- `review_architecture_decision`
- `summarize_feature_history`
- `analyze_project_risk`
- `prepare_wiki_update_context`
- `trace_decision_history`

Prompts should instruct agents to treat Vault Graph output as working context and to publish durable knowledge only through Vault's validation workflow.

## 17. CLI

Implemented CLI after the first product implementation:

```bash
vg init --vault /path/to/vault
vg init --vault-id main --vault /path/to/vault
vg vault add work --path /path/to/other-vault
vg vault list
vg index
vg index --vault-id main
vg index --all-vaults
vg index --full
vg index --dry-run
vg status
vg related GraphRAG
vg related --vault-id main GraphRAG
vg context "GraphRAG MVP 구현"
vg context --vault-id main "GraphRAG MVP 구현"
vg decision-trace GraphRAG
vg decision-trace --vault-id main GraphRAG
vg serve --mcp
vg ask "왜 GraphRAG를 도입했지?"
vg ask --vault-id main "..."
vg setup --vault /path/to/vault --agent codex
vg mcp register --agent codex --state ~/.vault-graph --config-path /path/to/agent-config.json
vg mcp config --agent codex --state ~/.vault-graph --print
vg watch
vg serve --http
```

CLI commands should be explicit about which Vault ID, Vault path, and index state
path they use. Commands that accept `--vault-id` operate on one registered Vault.
Commands that accept `--all-vaults` must expand to visible selected Vault IDs in
their output. Commands without either option use the active Vault. Implemented
commands are covered by acceptance tests and keep Vault content read-only.

Setup commands should keep installation separate from MCP registration:
installing Vault Graph makes `vg` available, while MCP registration only writes
or prints agent configuration that starts `vg serve --mcp`. External agent
config writes require an explicit config path until a safe default-path policy is
accepted. `vg setup` should use `~/.vault-graph` as its default state path when
`--state` is omitted.
Detailed implementation design for `vg ask` and the CLI onboarding targets lives in
`docs/superpowers/specs/2026-06-24-cli-todo-command-implementation-design.md`.
The canonical answer-layer contract for `vg ask` and `ask_vault` lives in
`docs/superpowers/specs/2026-06-25-evidence-first-ask-and-reasoning-design.md`.

## 18. Context Pack Contract

A context pack is a structured artifact generated from Vault Graph retrieval
for a concrete human or agent task. It is working context, not durable
knowledge.

The canonical context pack format is JSON. Markdown is a rendering view over
that JSON and must not add facts, drop evidence, or hide warnings.

The canonical evidence unit remains the `MetadataStore` evidence chunk:

```text
(vault_id, document_id, chunk_id)
```

Every normal pack item that makes a factual claim must reference at least one
evidence chunk. Stored excerpts are rendering content only; `MetadataStore`
remains the evidence authority.

Detailed Phase 4 contracts live under `docs/superpowers/specs/phase-4/`:

- `2026-06-12-phase-4-context-pack-overview-design.md`: cross-slice roadmap,
  decisions, invariants, and handoff map
- `2026-06-12-phase-4a-context-pack-contract-builder-boundary-design.md`: Phase
  4A JSON contract, builder boundary, data models, warnings, and budget policy
- `2026-06-12-phase-4b-local-context-pack-assembly-rendering-design.md`: Phase
  4B local assembly, CLI context command, Markdown rendering, and verification
  plan

Minimum JSON shape:

```json
{
  "context_pack_schema_version": "context-pack-v1",
  "pack_id": "sha256-of-canonical-pack-identity",
  "goal": "Implement GraphRAG MVP",
  "scope": {
    "requested": {
      "vault_ids": ["main"],
      "content_scopes": ["wiki", "docs"],
      "include_cross_vault": false
    },
    "actual_scopes": [
      {
        "vault_ids": ["main"],
        "content_scopes": ["wiki", "docs"],
        "include_cross_vault": false,
        "scope_key": "main:wiki,docs:local"
      }
    ]
  },
  "vaults": [
    {
      "vault_id": "main",
      "display_name": "Main Vault"
    }
  ],
  "vault_revisions": [
    {
      "vault_id": "main",
      "revision": "git-sha-or-file-snapshot-id",
      "revision_kind": "git"
    }
  ],
  "backend": {
    "metadata_store": {
      "name": "sqlite",
      "used": true
    },
    "keyword_index": {
      "name": "sqlite-fts5",
      "used": true
    },
    "vector_store": {
      "name": "chroma",
      "used": true
    },
    "graph_store": {
      "name": null,
      "used": false
    },
    "graph_projection": {
      "name": null,
      "used": false
    }
  },
  "retrieval_policy_version": "retrieval-policy-v1",
  "budget": {
    "max_tokens": 8000,
    "max_evidence_items": 24,
    "max_excerpt_tokens": 320,
    "used_tokens": 0,
    "omitted_items": 0
  },
  "store_revisions": [
    {
      "kind": "metadata",
      "revision": "metadata-revision-id",
      "vault_id": "main",
      "scope_key": "main:wiki,docs:local"
    },
    {
      "kind": "keyword",
      "revision": "keyword-revision-id",
      "vault_id": "main",
      "scope_key": "main:wiki,docs:local"
    },
    {
      "kind": "vector",
      "revision": "vector-revision-id",
      "vault_id": "main",
      "scope_key": "main:wiki,docs:local"
    }
  ],
  "generated_at": "2026-06-04T00:00:00+09:00",
  "current_state": [],
  "relevant_pages": [],
  "relevant_sources": [],
  "decisions": [],
  "constraints": [],
  "open_questions": [],
  "warnings": [],
  "evidence": []
}
```

Context packs should be small enough for an agent to read directly and rich
enough to avoid a full Vault scan.

Phase 4 context pack policy:

- default `max_tokens` is 8,000 estimated context tokens
- default `max_evidence_items` is 24
- default `max_excerpt_tokens` is 320 per evidence item
- default retrieval limit is 10 results before context pack classification
- warnings are first-class top-level and item-level records
- stale, missing, contested, deprecated, truncated, and omitted material must
  remain visible
- graph signals are opt-in through an explicit graph option
- cross-Vault graph expansion requires all-Vault scope plus explicit
  cross-Vault graph mode
- graph backend and projection metadata are marked `used=false` and graph store
  revisions are omitted unless graph mode is explicitly requested

`ContextPackBuilder` is the deep module for Phase 4. CLI, MCP, and HTTP
surfaces must call the builder instead of assembling pack sections directly.
The builder depends on application services and store interfaces, not concrete
local backend adapters.

## 19. Product Layers And Implementation Status

The first product implementation is complete enough that the main specification
now describes stable product layers instead of only planned phases. Historical
slice names such as `Phase 2B` remain in detailed design filenames, decision
logs, and compatibility notes where they preserve traceability.

### Foundation Layer: Vault Catalog, Vault Reader, And MetadataStore

- Vault catalog configuration with a default single-Vault entry
- Markdown parser and Vault frontmatter reader
- source/page/document normalization
- SQLite `MetadataStore` document, chunk, hash, source-state projection, and
  revision tables
- `MetadataStore` interface and backend health checks
- MetadataStore contract tests for future Postgres support
- read-only boundary tests

### Retrieval Layer: Vector Search And Graph-Ready Hybrid Retrieval

The retrieval layer was split into large slices so the retrieval contract could
stabilize before graph extraction and MCP serving were added. The retrieval
direction is evidence-first graph-ready hybrid retrieval. Keyword and vector
evidence are the default signals; graph signals are explicit opt-in signals.

#### Retrieval Contract And VectorStore Boundary

- `TextEmbeddings` interface and deterministic test implementation
- embedding model spec metadata: model name, model version, dimensions, and spec
  version
- `VectorStore` interface, vector hit record shape, backend health checks, and
  schema compatibility checks
- content-scope filter metadata for vector records and vector hits
- same-or-child content-scope filtering before vector result limits
- `MetadataStore` evidence-resolution contract for joining document and chunk
  evidence before results are rendered
- path-consistent evidence resolution so mismatched document/chunk rows cannot
  become normal evidence
- graph-ready retrieval result schema with per-signal explanations
- explicit rule that `VectorStore` returns semantic candidates only and never
  owns document identity, chunk text authority, evidence authority, graph
  relationships, or durable wiki publication
- contract tests that future Chroma and Qdrant support must satisfy

#### Local Vector Indexing

Local vector indexing makes the vector projection rebuildable, inspectable, and
recoverable from `MetadataStore` chunks.

Accepted Phase 2B decisions:

- Chroma is the default local `VectorStore` and is installed as a core
  dependency, not as a manual optional package.
- `TextEmbeddings` remains local-first by default. Hosted embedding providers
  may be added later only behind the same interface.
- The default production local embedding implementation is
  `FastEmbedTextEmbeddings` with
  `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`.
- `vg index` updates metadata and vector projections by default. `--dry-run`
  plans both stores without mutating derived state.
- Chroma uses logical collections keyed by `EmbeddingModelSpec`. Vault
  selection remains payload/filter metadata through `vault_id`, `document_id`,
  `chunk_id`, and `content_scope`; collections are not split per Vault for the
  MVP.
- Any `EmbeddingModelSpec` change makes affected vector records stale and
  requires reindexing under the new model spec. Mixed model specs must not be
  silently searched together.

Sustainability and consistency requirements:

- Use scope-local reconcile. The vector indexer compares current live chunks
  from `MetadataStore` with the `VectorStore` manifest for the selected
  `QueryScope`, then converges the vector projection to the desired state.
- Add a `MetadataStore` live chunk listing boundary for vector indexing. The
  vector indexer must not read SQLite tables directly.
- Extend vector records or manifest records with staleness comparison keys:
  `source_chunk_hash`, `chunker_version`, `metadata_index_revision`,
  `EmbeddingModelSpec`, and backend schema version. Keep `vector_index_revision`
  and backend name as manifest/status metadata, not as staleness comparison
  keys.
- Within the selected reconcile scope, tombstone or replace vector records when
  a chunk is deleted, a document is tombstoned, a chunk hash changes, the
  chunker version changes, or the embedding model spec changes. Records outside
  the selected scope must be left untouched.
- Do not require a cross-store transaction between metadata and vector stores.
  If metadata indexing succeeds and vector indexing fails, report vector state
  as stale or unavailable through status, return a nonzero `vg index` exit for
  the failed vector step, and recover on the next `vg index`.
- Apply the same derived-projection rule to future graph indexing:
  current metadata chunks plus `GraphExtractionSpec` plus graph manifest produce
  the desired graph projection. Graph records remain derived and
  non-authoritative.
- Avoid the term "graph embedding" for the current product scope. Phase 2B is
  text chunk embedding and local vector indexing. Later graph node or edge
  embeddings, if added, are separate derived vector projections.

Default embedding policy:

- `model_name`: `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`
- `model_version`: `faf4aa4225822f3bc6376869cb1164e8e3feedd0` recorded in
  `EmbeddingModelSpec` as the pinned FastEmbed ONNX artifact revision
- `source_model_revision`: `e8f8c211226b894fcb81acc59f3b34ba3efd5f42` recorded
  as provenance for the original `sentence-transformers` model
- `artifact_repo_id`: `qdrant/paraphrase-multilingual-MiniLM-L12-v2-onnx-Q`
- `dimensions`: `384`
- `spec_version`: `fastembed-multilingual-minilm-l12-v2-cosine-v1`
- runtime: local CPU through `FastEmbedTextEmbeddings`
- cache: outside registered Vault roots, for example
  `~/.cache/vault-graph/embeddings`
- first-use behavior: download the configured model artifact when it is missing
  and network access is available
- offline behavior: fail with a clear model-unavailable status when the artifact
  is not cached
- fallback behavior: never silently fall back to a different model
- revision behavior: any model revision, dimension, or spec-version change makes
  affected vector records stale

Embedding throughput tuning:

- Phase 2B keeps local CPU as the default runtime. Throughput tuning must happen
  through `FastEmbedTextEmbeddings` configuration, not through new vector-store
  behavior.
- `embedding_batch_size` is not chunk size. Current chunk boundaries come from
  the `heading-section-v1` chunker and are heading-section based, not a fixed
  token or character count.
- `embedding_batch_size` controls how many chunk texts are embedded per model
  call. The default is `256`. Lower values reduce memory pressure. Higher values
  may improve throughput on large Vaults.
- `embedding_parallelism` controls FastEmbed worker parallelism. The default is
  `null`, which runs in the main process and is the safest laptop default. `0`
  means auto-detect available CPU cores. A positive integer uses that many
  workers.
- `embedding_lazy_load` defaults to `true` so the model artifact is loaded only
  when embeddings are actually requested. This avoids loading a model during
  status checks and reduces unnecessary startup cost.
- `embedding_batch_size`, `embedding_parallelism`, and `embedding_lazy_load` are
  runtime execution settings. They must be recorded in vector index run metadata
  and status diagnostics, but they are not part of `EmbeddingModelSpec` and must
  not stale otherwise compatible vectors.
- `VectorIndexer` must preserve input order and bind every returned vector back
  to its requested `input_id`. Duplicate input IDs in one batch are an error.
- If embedding fails because `embedding_batch_size` or worker count is too large
  for the machine, `vg index` must fail the vector step clearly and preserve
  recoverable stale vector status. It must not silently change tuning values and
  continue.
- `vg index --dry-run` reports planned embedding counts and configured tuning
  values without loading the model, creating Chroma collections, or writing
  Vault Graph state.

Required implementation capabilities:

- Chroma `VectorStore` collections derived from `MetadataStore` chunks
- vector indexer for full and incremental reconcile runs
- stale chunk embedding deletion or tombstoning
- CPU embedding batch and parallelism tuning through `FastEmbedTextEmbeddings`
- vector revision metadata and embedding manifest export
- `vg index` integration for metadata plus vector projection updates
- `vg status` visibility for vector backend health, schema compatibility,
  freshness, model spec, stale counts, status scope, and recoverable failure
  messages
- read-only boundary tests proving vector indexing writes only to Vault Graph
  state and never mutates Vault

#### Evidence-First Keyword And Vector Search

Evidence-first keyword and vector search is the first user-facing search
surface. It returns ranked, inspectable Vault evidence from keyword and vector
signals while keeping Vault Graph read-only, rebuildable, and graph-ready.

Accepted Phase 2C decisions:

- The canonical search result unit is an evidence chunk resolved through
  `MetadataStore`. Its full resolved evidence identity is
  `(vault_id, document_id, chunk_id)`.
- Document, page, source, or section results are rendering/grouping views over
  evidence chunks. They are not separate canonical retrieval identities in Phase
  2C.
- Search output may group multiple chunk hits from the same document for
  readability, but each normal result must preserve the matched `chunk_id`,
  `document_id`, `vault_id`, path, section or anchor, evidence revision,
  retrieval signals, and warnings.
- Keyword lookup must be exposed through a stable metadata-owned lexical
  candidate boundary. `RetrievalService` must not read SQLite tables directly.
  The local implementation may use SQLite FTS5 or an equivalent rebuildable
  metadata projection over current chunks and document metadata.
- Keyword candidate fields should include current chunk text, section heading,
  path, and searchable document metadata such as title/frontmatter when
  available. The final rendered authority still comes from
  `MetadataStore` evidence resolution, not from the keyword index row.
- Vector lookup uses `VectorStore.search` and returns semantic candidate
  metadata only. `VectorStore` must not return path, title, chunk text, rendered
  snippets, durable summaries, or evidence authority.
- `RetrievalService` or `HybridRetriever` owns query normalization, keyword
  candidate lookup, vector candidate lookup, candidate merge, Vault-scoped
  dedupe, rank fusion, warnings, evidence resolution, and final result assembly.
- Fusion must be rank-based, such as reciprocal-rank-style fusion. Phase 2C must
  not treat keyword scores and vector scores as directly comparable global
  relevance scores.
- `vg search` is read-only over existing projections. It must not run indexing,
  create metadata schema, create Chroma collections, download embedding models,
  or write Vault Graph index state during search. If vector query embedding
  cannot run from already available local model artifacts, search degrades to
  keyword-only with a visible warning.
- Metadata store absence or schema incompatibility is a search failure with a
  clear `vg index` recovery hint.
- Vector store absence, stale vector state, offline embedding model, or vector
  schema incompatibility should degrade to keyword-only search when keyword
  evidence is available. The response must include a visible top-level warning;
  it must not silently hide the degraded mode.
- Phase 2C needs a top-level search response contract, not only per-result
  warnings. Result-level warnings describe individual evidence problems; response
  warnings describe query-wide conditions such as vector backend unavailable,
  stale vector projection, truncated results, empty index state, or dropped
  candidates.
- `vg search` must never auto-index. It reads existing Vault Graph projections
  only. If required projections are missing or stale, it reports warnings or
  recovery guidance instead of mutating Vault Graph state.
- Phase 2C keeps the existing Markdown `heading-section-v1` chunks. It must not
  introduce `markdown-block-window-v2`, `hierarchical-retrieval-v3`, or any
  chunker migration. Those remain later retrieval-policy or chunking migrations.

Search boundary:

```text
vg search "query"
  -> resolve requested QueryScope from active Vault, --vault-id, or --all-vaults
  -> expand requested scope into per-Vault actual scopes
  -> check metadata and keyword projection readiness
  -> normalize query text
  -> keyword candidate lookup per actual scope
  -> optional no-download vector query embedding
  -> optional VectorStore.search per actual scope
  -> merge candidates by (vault_id, chunk_id)
  -> rank-based fusion
  -> MetadataStore evidence resolution
  -> evidence chunk results plus top-level response warnings
```

The service boundary should be `RetrievalService.search(...)` or
`HybridRetriever.search(...)`. CLI, MCP, and HTTP adapters must not query
SQLite FTS tables or Chroma collections directly. Phase 2C implements the CLI
surface only; MCP and HTTP use the same service later.

Resolved search scope contract:

- `RetrievalService` must not pass a global all-vault content-scope union
  directly to `KeywordIndex` or `VectorStore`.
- User selection is first represented as a requested `QueryScope`, then expanded
  through `VaultCatalog` into per-Vault actual scopes using the same
  broader/narrower content-scope rules as Phase 2B vector indexing.
- If the requested scope is narrower than a catalog entry scope, use the
  requested scope for that Vault.
- If the catalog entry scope is narrower than the requested scope, use the
  catalog entry scope for that Vault.
- If neither scope contains the other, that Vault contributes no candidates for
  that content scope.
- Candidate lookup runs per actual scope and results are merged afterward.
  This prevents one Vault's configured content scopes from widening another
  Vault's search.
- `SearchResponse` records both the requested scope and the actual scopes
  used for candidate lookup.

Keyword projection contract:

- Add a small keyword candidate boundary such as `KeywordIndex`.
- The local implementation may be backed by SQLite FTS5 inside the metadata
  database or an equivalent rebuildable metadata projection.
- Keyword projection rows are rebuilt from current Markdown chunks and selected
  document metadata. They are not a second source of truth.
- Phase 2C treats keyword projection as a metadata subprojection. The local
  SQLite implementation updates keyword rows in the same transaction as the
  metadata revision. If keyword projection update fails during indexing, the
  metadata revision fails rather than publishing inconsistent metadata and
  keyword state.
- Search reads keyword state through a read-only `KeywordIndex` adapter. It
  must not use a keyword projection writer or open a write-capable metadata
  store.
- Keyword lookup returns candidate metadata only: `vault_id`, `document_id`,
  `chunk_id`, matched fields, backend-local rank, backend-local score,
  backend name, and keyword index revision.
- Keyword lookup must filter by `QueryScope.vault_ids` and
  `QueryScope.content_scopes` before applying result limits.
- Keyword results must not be rendered until the matched chunk is resolved
  through `MetadataStore`.

Vector candidate contract:

- Query embeddings use the configured `TextEmbeddings` and current
  `EmbeddingModelSpec`.
- Phase 2C must add a read-only embedding availability boundary, such as
  `TextEmbeddings.artifact_status()` or `can_embed_without_download()`, before
  search-time query embedding is enabled.
- Search-time query embedding must run in local-only/no-download mode. A missing
  local model artifact is a vector-unavailable condition, not a reason to mutate
  cache state during search.
- `VectorStore.search` returns `VectorHit` records only. It must not return
  rendered snippets, path authority, title authority, summaries, or chunk text.
- The retrieval layer must reject or warn on vector hits whose
  `(vault_id, document_id, chunk_id)` cannot be resolved through
  `MetadataStore`.
- Vector candidates must be skipped, with a top-level warning, when vector
  health, schema compatibility, model availability, or freshness is not safe
  enough for normal search.
- Vector readiness must be checked through a read-only `SearchReadiness` or
  projection-status boundary. Retrieval must not duplicate `IndexService.status`
  logic or import local status-store implementations directly.

Fusion and ranking contract:

- Dedupe candidates by `(vault_id, chunk_id)`, then preserve the full resolved
  evidence identity `(vault_id, document_id, chunk_id)` on every normal result.
- Keep all contributing signals for each candidate. A chunk can have keyword,
  vector, and later graph signals.
- Use rank-based fusion. A reciprocal-rank-style default is acceptable:
  `fused_score = sum(signal_weight / (rank_constant + signal_rank))`.
- Default Phase 2C signal weights are `keyword=1.0` and `vector=1.0`; the
  default `rank_constant` is `60`.
- Raw keyword scores and raw vector distances are diagnostic signal metadata,
  not directly comparable global relevance scores.
- Sort final results deterministically by fused rank, best contributing signal
  rank, `vault_id`, path, and `chunk_id` so repeat searches are stable.
- `--limit` controls final evidence results. Candidate pools may be larger than
  the final limit, but this is retrieval policy and must not affect store
  identity or evidence authority.

Search response contract:

- A search response has query text, requested `QueryScope`, actual scopes,
  limit, result count, candidate counts, dropped candidate count, results,
  top-level warnings, degraded-mode flag, generated timestamp, and store
  revision metadata.
- A normal search result is a `RetrievalResult` whose evidence contains the
  matched evidence chunk resolved from `MetadataStore`.
- Result IDs are search-output identifiers, not durable Vault identities.
- Result IDs and `RetrievalSignal.source_id` values must include or derive from
  Vault-scoped candidate identity. They must not depend on path, document ID, or
  chunk ID without `vault_id`.
- Every result includes `vault_id`, `document_id`, `chunk_id`, path, section or
  anchor, per-signal explanations, store revisions, and result-level warnings.
- Top-level warnings and result-level warnings must be structurally attributable
  when scope is relevant. They carry `affected_vault_ids` and may carry
  candidate identity fields such as `vault_id`, `document_id`, and `chunk_id`.
- Store revisions are keyed by scope. A multi-vault response must not report one
  ambiguous `metadata` or `vector` revision without Vault or actual-scope
  attribution.
- Top-level warnings describe query-wide conditions such as keyword projection
  stale, vector unavailable, stale vector projection, embedding model
  unavailable, truncated candidates, empty index state, or dropped candidates
  with missing evidence.
- Fatal search errors are not successful `SearchResponse` warnings. Invalid
  scope, invalid query, unsupported output format, missing metadata store,
  incompatible metadata schema, missing keyword projection, and incompatible
  keyword schema return a nonzero exit with recovery guidance.
- Missing metadata evidence prevents a candidate from becoming a normal result.
  The response records the drop as a warning instead of returning unsupported
  evidence.
- Empty searches complete successfully with zero results when projections are
  healthy. Missing required projections fail with recovery guidance.

CLI contract:

```bash
vg search "GraphRAG"
vg search --vault-id main "GraphRAG"
vg search --all-vaults "GraphRAG"
vg search --limit 20 --format json "GraphRAG"
```

CLI behavior:

- uses the active Vault by default
- rejects `--vault-id` together with `--all-vaults`
- prints the resolved Vault IDs in output
- supports `--limit` with a positive integer default of `10`
- supports human-readable output and an optional machine-readable format
- returns exit code `0` for successful search, including keyword-only degraded
  search with warnings
- returns nonzero for invalid scope, invalid query, missing required metadata or
  keyword projection, schema incompatibility, or unsupported output format
- never creates metadata, keyword, vector, model-cache, or Vault files during
  search

Multi-vault rules:

- Default search uses the active Vault only.
- `--vault-id ID` searches exactly one registered Vault.
- `--all-vaults` expands to explicit enabled Vault IDs before stores are
  queried, then to per-Vault actual scopes before candidate lookup.
- Candidate identity, dedupe, evidence resolution, result grouping, and warning
  attribution all include `vault_id`.
- Identical relative paths, document IDs, chunk IDs, or headings from different
  Vaults must not collide.
- Document grouping is by `(vault_id, document_id)`, not by path alone.
- Phase 2C search grouping must use resolved `EvidenceReference` and
  `RetrievalResult` fields. It must not call document-level resolution by
  `document_id` alone.
- `include_cross_vault` does not enable graph traversal or entity merging in
  Phase 2C.

Required implementation capabilities:

- keyword candidate lookup over metadata-owned current chunks
- vector candidate lookup over `VectorStore`
- per-Vault actual search scope resolution before candidate lookup
- no-download embedding availability checks for search-time query embedding
- read-only search readiness checks for metadata, keyword, vector, and model
  availability
- rank-based candidate fusion for keyword and vector signals
- `RetrievalService` or `HybridRetriever` service boundary
- `vg search "query"` user surface with `--vault-id`, `--all-vaults`, `--limit`,
  and optional machine-readable output
- `SearchResponse` with requested scope, actual scopes, result count,
  candidate counts, degraded flag, attributed warnings, and store revisions
- search results resolved through `MetadataStore` before rendering
- evidence-linked result format with per-signal explanations and stale or
  missing evidence warnings
- top-level response warnings for degraded or partially available search
- degraded keyword-only behavior when vector search is unavailable but keyword
  evidence is available
- read-only tests proving `vg search` never mutates Vault content or Vault Graph
  index state
- multi-vault tests proving search identity, filtering, grouping, and dedupe use
  `vault_id`

The retrieval layer excludes durable Vault publication, direct store access from
adapters, and unsupported answer synthesis. Graph traversal, context packs, MCP,
memory projections, and answer synthesis are separate layers over the same
evidence contract.

### Graph Layer: Entity And Relationship Graph

The graph layer turns retrieval evidence chunks into a rebuildable entity and
relationship graph projection. The goal is to make relationships inspectable and
retrievable without turning graph state into durable Vault knowledge.

Detailed Phase 3 contracts live under `docs/superpowers/specs/phase-3/`:

- `2026-06-10-phase-3-overview-design.md`: cross-slice roadmap, invariants, and
  handoff map
- `2026-06-10-phase-3a-graphstore-contract-readiness-design.md`: Phase 3A
  `GraphStore`, graph records, extraction result contracts, and readiness
  contract
- `2026-06-10-phase-3b-local-entity-relationship-indexing-design.md`: Phase 3B
  deterministic local entity and relationship indexing through scope-local
  graph reconcile
- `2026-06-10-phase-3c-graph-projection-retrieval-design.md`: Phase 3C
  bounded `GraphProjection`, graph retrieval commands, and opt-in graph search

`docs/SPEC.md` remains the top-level product and architecture contract; slice
documents hold implementation details that would otherwise make this file too
long.

Phase 3 slices:

| Slice | Contract | Detailed Design | Explicitly Not Included |
| --- | --- | --- | --- |
| Phase 3A | Define graph record contracts, `GraphExtractionSpec`, `GraphStore`, scoped graph manifests, and graph readiness/status contracts | `docs/superpowers/specs/phase-3/2026-06-10-phase-3a-graphstore-contract-readiness-design.md` | entity extraction execution, graph traversal, rustworkx ranking, decision traces |
| Phase 3B | Build local deterministic entity and relationship indexing through scope-local graph reconcile | `docs/superpowers/specs/phase-3/2026-06-10-phase-3b-local-entity-relationship-indexing-design.md` | LLM-required extraction, cross-Vault entity merging, context packs |
| Phase 3C | Add bounded `GraphProjection`, opt-in graph retrieval signals, `vg related`, and decision trace prototype | `docs/superpowers/specs/phase-3/2026-06-10-phase-3c-graph-projection-retrieval-design.md` | `vg ask`, MCP serving, HTTP serving, Neo4j |

Phase 3 invariants:

- Vault remains the durable source of truth. Graph records, evidence refs,
  manifests, revisions, and projection caches are derived Vault Graph state.
- The canonical graph evidence unit is the `MetadataStore` evidence chunk:
  `(vault_id, document_id, chunk_id)`.
- User-visible graph output must resolve evidence through `MetadataStore` before
  rendering. Stored graph excerpts are rendering hints, not evidence authority.
- Graph identities are deterministic and Vault-scoped. Identical entity names,
  paths, headings, chunk IDs, or relationship labels from different Vaults must
  not collide.
- Cross-Vault graph behavior is opt-in and must preserve source, target, and
  evidence Vault IDs. Phase 3 must not merge entities across Vaults by name.
- Relationship status is explicit: `stated`, `inferred`, `contested`, or
  `deprecated`.
- Phase 3 stores relationships as directed records. Symmetric behavior belongs
  to query/view policy, not relationship identity.
- Graph indexing uses scope-local reconcile. Records outside the selected
  actual scope are left untouched.
- `GraphExtractionSpec` is the graph compatibility and staleness boundary.
  Its version plus canonical digest identifies the extraction contract. Changes
  to extractor/schema/status/confidence rules make affected graph records stale
  or incompatible.
- Graph search is opt-in. Plain `vg search "query"` remains Phase 2C
  keyword/vector evidence search until explicit graph mode is requested.

Phase 3 execution flow:

```text
Phase 3A
  -> graph contracts and readiness only

Phase 3B
  -> MetadataStore.list_chunks(actual_scope)
  -> deterministic EntityExtractor and RelationshipExtractor
  -> GraphIndexer scope-local reconcile
  -> GraphStore upserts, tombstones, graph revisions

Phase 3C
  -> GraphStore graph candidates
  -> optional GraphProjection bounded traversal/ranking
  -> MetadataStore evidence resolution
  -> graph CLI output or explicit graph retrieval signal
```

Required Phase 3 test themes:

- read-only boundary tests for graph indexing and graph retrieval
- rebuild tests from Vault-derived metadata
- scope-local reconcile tests
- multi-vault identity and warning attribution tests
- evidence authority tests through `MetadataStore`
- graph readiness and compatibility tests
- reusable `GraphStore` contract tests for future backend implementations

Phase 3 explicitly excludes LLM answer generation, context pack generation, MCP
serving, HTTP serving, durable Vault publication, default hosted graph backends,
Qdrant implementation, Neo4j implementation, and cross-Vault entity merging.

### Context Pack Layer

The context pack layer turns retrieval and graph signals into bounded,
evidence-linked context packs. It keeps JSON canonical and Markdown as a
rendering view so agents can consume task-specific briefs without reading the
whole Vault.

Phase 4 slices:

| Slice | Contract | Detailed Design | Explicitly Not Included |
| --- | --- | --- | --- |
| Phase 4A | Define canonical JSON context pack contract, `ContextPackBuilder` boundary, warning model, budget policy, and renderer boundary | `docs/superpowers/specs/phase-4/2026-06-12-phase-4a-context-pack-contract-builder-boundary-design.md` | `vg context`, MCP serving, HTTP serving, pack persistence, answer synthesis |
| Phase 4B | Add local context pack assembly through existing retrieval services plus Markdown rendering view | `docs/superpowers/specs/phase-4/2026-06-12-phase-4b-local-context-pack-assembly-rendering-design.md` | `vg ask`, MCP serving, HTTP serving, durable pack store, automatic Vault publication |

Phase 4 invariants:

- Context packs are derived working context, not durable knowledge.
- JSON is the canonical artifact. Markdown is a rendering view.
- Evidence chunks remain authoritative for all pack items.
- Warnings are first-class and cannot be hidden by renderers.
- Budget omission and excerpt truncation are explicit warnings.
- Graph signals are opt-in for context packs, matching Phase 3 search policy.
- `ContextPackBuilder` depends on retrieval and storage interfaces, not local
  backend implementations.

### MCP Adapter Layer

The MCP adapter layer exposes retrieval, graph, context-pack, status, and
memory services to local agents. MCP is an adapter layer, not a new reasoning
engine or knowledge store. It must preserve the same read-only, evidence-first,
Vault-scoped behavior as CLI commands.

Detailed Phase 5 contracts live under `docs/superpowers/specs/phase-5/`:

- `2026-06-15-phase-5-mcp-server-overview-design.md`: cross-slice roadmap,
  invariants, service-backed tool policy, and handoff map
- `2026-06-15-phase-5a-mcp-server-foundation-stdio-design.md`: Phase 5A local
  stdio server foundation, service factory, capability registration, error
  mapping, and Codex configuration examples
- `2026-06-15-phase-5b-mcp-resources-context-pack-resources-design.md`: Phase
  5B read-only resources, resource templates, URI validation, and generated
  context-pack resource cache
- `2026-06-15-phase-5c-mcp-tools-prompts-agent-workflows-design.md`: Phase 5C
  service-backed tools, prompt templates, structured output policy, and agent
  workflow contracts

Phase 5 slices:

| Slice | Contract | Detailed Design | Explicitly Not Included |
| --- | --- | --- | --- |
| Phase 5A | Add a local stdio MCP server boundary, `vg serve --mcp`, read-only service construction, capability registration, and Codex-compatible local config examples | `docs/superpowers/specs/phase-5/2026-06-15-phase-5a-mcp-server-foundation-stdio-design.md` | Streamable HTTP transport, authentication, remote hosting, answer synthesis, memory projections |
| Phase 5B | Expose read-only MCP resource templates for indexed Vault documents/pages/sources, graph entities, current context, and generated context packs | `docs/superpowers/specs/phase-5/2026-06-15-phase-5b-mcp-resources-context-pack-resources-design.md` | Vault file mutation, resource subscriptions, durable pack persistence, full-Vault resource dumps |
| Phase 5C | Expose service-backed MCP tools and prompts over existing search, graph, decision-trace, status, and context-pack services | `docs/superpowers/specs/phase-5/2026-06-15-phase-5c-mcp-tools-prompts-agent-workflows-design.md` | answer and memory service implementations delivered by later layers, autonomous wiki publication, LLM clients |

Phase 5 invariants:

- MCP tools, resources, and prompts are adapters over application services.
- The server must not write to Vault or create durable knowledge outside Vault.
- The default transport is local stdio. Streamable HTTP belongs to a later HTTP
  serving phase because it needs origin validation, authentication, and network
  hardening.
- The MCP process may write only Vault Graph derived state when a later explicit
  indexing tool exists. Phase 5 tools are read-only and must not index.
- Tool responses use structured JSON as the contract and may include text as a
  compatibility mirror. Warnings remain first-class.
- Only tools backed by existing services are registered. Later answer and memory
  tools are allowed in the MCP surface only because their application services
  exist.
- Context-pack resources are generated artifacts. Without a durable pack store,
  `vault://context/packs/{pack_id}` is backed only by a bounded in-process cache
  and can be regenerated by calling `build_context_pack`.
- Multi-vault behavior follows `QueryScope`: active Vault by default,
  `vault_ids` only when explicit, and cross-Vault graph expansion only when
  explicit.

### Memory And Explorer Projection Layer

The memory and explorer projection layer turns search, graph, context-pack,
MCP, and status services into read-only projections. These projections help
users and agents understand current project state, unresolved questions, recent
changes, and why prior Vault Graph results were returned.

Memory is still derived working context. Phase 6 must not create a second
knowledge base, publish durable wiki pages, edit Vault files, or use summaries
as evidence authority. Durable knowledge still flows back through Vault's
source capture, validation, release gate, and Git history workflow.

Phase 6 may borrow memory-layer terminology from systems such as Mem0 and
MemMachine, but Vault Graph uses those ideas only as read-only projections over
Vault-derived evidence. It must not add a generic writable `MemoryStore`,
`Memory.create`, `Memory.query`, `Memory.upsert`, `Memory.link`,
`Memory.audit`, hidden episode log, user-profile memory database, preference
memory database, or procedural memory database in the core product.

Detailed Phase 6 contracts live under `docs/superpowers/specs/phase-6/`:

- `2026-06-18-phase-6-memory-and-explorer-views-overview-design.md`:
  cross-slice roadmap, invariants, and handoff map
- `2026-06-18-phase-6a-result-explanation-contract-design.md`: Phase 6A result
  explanation records, explanation cache boundary, and `explain_result`
  service contract
- `2026-06-18-phase-6b-project-decision-issue-memory-design.md`: Phase 6B
  project memory, decision memory, and issue/open-question projections
- `2026-06-18-phase-6c-timeline-health-explorer-design.md`: Phase 6C timeline,
  projection freshness, backend health, and scale-up adapter readiness views

Phase 6 slices:

| Slice | Contract | Detailed Design | Explicitly Not Included |
| --- | --- | --- | --- |
| Phase 6A | Add a result explanation contract that can explain search, context-pack, graph, and decision-trace results returned by the current MCP session | `docs/superpowers/specs/phase-6/2026-06-18-phase-6a-result-explanation-contract-design.md` | durable result history, answer synthesis, full project memory summaries |
| Phase 6B | Add deterministic project, decision, and issue memory projections over indexed Vault evidence | `docs/superpowers/specs/phase-6/2026-06-18-phase-6b-project-decision-issue-memory-design.md` | LLM-written summaries, automatic wiki updates, hidden Vault writes |
| Phase 6C | Add recent timeline, freshness, backend health, and scale-up adapter readiness explorer views | `docs/superpowers/specs/phase-6/2026-06-18-phase-6c-timeline-health-explorer-design.md` | remote backend migrations, hosted monitoring, UI dashboards |

Phase 6 invariants:

- Memory projections are query products over existing Vault-derived indexes.
- Evidence chunks remain the authority unit for user-visible claims.
- Project, decision, issue, and timeline outputs carry Vault IDs, evidence
  references, warnings, store revisions, and freshness status.
- Missing or stale projection state must be visible as warnings or structured
  errors with a safe next command.
- No generic writable memory API is introduced in Phase 6. External memory
  systems remain future adapters or export targets over evidence-linked
  projections, not new authorities inside Vault Graph.
- `summarize_project_memory`, `get_open_questions`, `get_recent_changes`, and
  `explain_result` are MCP tools because their backing application services
  exist.
- `vault://{vault_id}/context/current` and `vault://{vault_id}/timeline/recent`
  are read-only projection resources backed by Phase 6 services.

### Ask And Reasoning Layer

The ask and reasoning layer is the implemented answer surface. It turns the
existing evidence-first services into cited answers without adding a writable
memory system or making generated answers durable Vault knowledge.

The layer owns `vg ask` and the MCP tool
`ask_vault(question, mode="evidence-first", scope=None)`.

Core responsibilities:

- plan evidence gathering for a natural-language question
- call existing application services instead of querying stores directly
- compose an answer only from resolved Vault evidence
- label inferred, partial, stale, contested, deprecated, and unsupported claims
- preserve `vault_id`, evidence references, warnings, store revisions, and
  freshness status in every answer response
- provide a reasoning trace that explains which evidence groups were used and
  why
- suggest durable follow-up through Vault workflow guidance when the answer
  exposes missing evidence, contradictions, or useful publication candidates

It is not a memory layer:

- no generic writable `MemoryStore`
- no hidden episode log
- no profile, preference, or procedural memory database
- no agent-generated fact enters Vault Graph as authority unless it is captured
  in Vault and re-indexed
- no automatic Vault file edit, rename, rewrite, delete, publish, or validation

Ask flow:

```text
vg ask "question"
  -> resolve QueryScope
  -> AnswerService.ask(...)
  -> EvidencePlanner.plan(...)
  -> RetrievalService.search(...)
  -> optional GraphRetrievalService expansion
  -> optional DecisionTraceService lookup
  -> optional MemoryProjectionService lookup
  -> evidence grouping and conflict/staleness checks
  -> AnswerComposer.compose(...)
  -> CitationGuard.validate(...)
  -> AnswerResponse with answer, claims, evidence, reasoning trace, warnings
```

Service boundary:

- `AnswerService` is the application-service entrypoint used by CLI, MCP, and
  later HTTP adapters.
- `EvidencePlanner` decides which existing services to call. It does not read
  SQLite, Chroma, graph stores, projection caches, or Vault files directly.
- `AnswerComposer` turns an `AnswerPlan` plus resolved evidence into an answer
  draft. `AnswerService` attaches evidence, reasoning trace, `answer_id`, and
  `generated_at` before `CitationGuard` validates the final `AnswerResponse`.
  The default composer should be deterministic and extractive enough to run
  locally without hosted LLM access.
- Any later LLM composer must be an adapter behind `AnswerComposer`, must run
  after evidence planning, and must pass the same citation guard.
- `CitationGuard` rejects normal answer claims that cannot be tied to evidence
  or explicitly labeled as unsupported, partial, inferred, or missing.

Answer response contract:

- `answer_id`: generated response identifier, not a durable Vault identity
- `question`
- `scope`: requested and actual `QueryScope`
- `answer`: concise natural-language answer
- `answer_status`: `supported`, `partial`, or `insufficient_evidence`
- `claims`: claim text, status, evidence refs, and warnings
- `evidence`: resolved evidence refs with `vault_id`, document/chunk identity,
  path, section or anchor, store revisions, and retrieval reason
- `reasoning_trace`: planned steps, services used, result counts, dropped
  evidence, and conflict/staleness notes
- `warnings`: top-level answer warnings
- `suggested_follow_up`: optional durable Vault workflow guidance
- `generated_at`

Default behavior:

- Use the active Vault by default.
- Require explicit `--vault-id` or all-Vault scope for multi-vault answering.
- Prefer concise answers over broad reports.
- Return `insufficient_evidence` instead of inventing missing context.
- Preserve read-only behavior; answering must not run indexing, download models,
  mutate Vault Graph indexes, or write Vault content.
- Surface stale or missing projections as warnings or structured errors with a
  safe next command.

Implemented capabilities:

- `vg ask "question"` and `vg ask --vault-id ID "question"`
- MCP `ask_vault(...)` over the same `AnswerService`
- `AnswerService`, `EvidencePlanner`, `AnswerComposer`, `CitationGuard`, and
  `AnswerResponse` contracts
- answer planning over search, graph, decision trace, context-pack, and memory
  projection services where available
- evidence grouping, conflict/staleness handling, and citation validation
- local deterministic composer as the default implementation
- tests proving unsupported claims are labeled or rejected
- tests proving answer generation writes no Vault content and does not mutate
  derived index state
- multi-vault tests proving evidence and claims preserve `vault_id`
- degraded-mode tests for missing graph, memory, vector, or stale projection
  state

Detailed implementation design:

- `docs/superpowers/specs/2026-06-25-evidence-first-ask-and-reasoning-design.md`

### Optional UI Layer

The optional UI layer adds a local HTTP and browser surface over existing Vault
Graph application services. It is an adapter and view layer, not a new
retrieval engine, reasoning engine, memory store, index backend, or Vault
publication workflow.

The UI exists to make memory projections and evidence flows easier to inspect. It should show
Vault-derived evidence, warnings, freshness, backend health, decisions, open
questions, and generated context in a browser without changing the source of
truth. CLI and MCP remain first-class interfaces; the UI is optional.

The UI may later call `AnswerService` after the ask layer exists, but it must
not implement its own answer engine, memory store, evidence planner, LLM client,
or citation policy. A query workspace may link search, project memory, open
questions, context packs, and answer responses; it must preserve all warnings
and evidence links from the service response.

Detailed Phase 7B and 7C contracts live under
`docs/superpowers/specs/phase-7/`. Local HTTP serving is a separate adapter
task and answer synthesis belongs to the ask layer, not to the UI layer.

Phase 7 slices:

| Slice | Contract | Detailed Design | Explicitly Not Included |
| --- | --- | --- | --- |
| HTTP Adapter | Local read-only HTTP JSON adapter for existing application services through `vg serve --http` | `docs/superpowers/specs/2026-06-24-cli-todo-command-implementation-design.md` | hosted HTTP, authentication, remote sharing, browser UI, direct store access |
| Phase 7B | Add a minimal Timeline and Health UI over recent changes, projection freshness, backend health, and scale-up adapter readiness | `docs/superpowers/specs/phase-7/2026-06-23-phase-7b-timeline-health-ui-design.md` | decision workspace, context-pack editing, LLM answers, hosted monitoring |
| Phase 7C | Add Decision Explorer and Agent Workspace views over decision traces, project memory, open questions, context-pack previews, evidence links, and durable follow-up suggestions | `docs/superpowers/specs/phase-7/2026-06-23-phase-7c-decision-agent-workspace-design.md` | independent answer engine, automatic wiki publication, Vault edits, durable context-pack storage |

Phase 7 invariants:

- HTTP and UI adapters call application services only. They must not query
  SQLite, Chroma, graph stores, or projection internals directly.
- The HTTP server is local-first. The default bind address is `127.0.0.1`;
  remote serving requires a later security design.
- The first UI should be a small static browser surface served by the local HTTP
  adapter. A separate frontend build system requires an explicit later design.
- Every UI view preserves evidence links, Vault IDs, warnings, store revisions,
  and freshness state when those fields exist in the service response.
- Multi-vault behavior follows `QueryScope`: active Vault by default, explicit
  Vault IDs or all-Vault scope only when requested, and visible Vault identity in
  output.
- The UI must not create, edit, rename, delete, or publish Vault content.
- Generated context packs, memory projections, and timeline views remain
  derived working context, not durable knowledge.
- If the UI surfaces ask results later, it must call `AnswerService` and render
  the existing evidence, warning, and claim-status contract unchanged.

## 20. Success Criteria

Vault Graph is successful when:

- A user can point it at a Vault and build an index without mutating Vault.
- A user can register multiple Vaults and index one Vault or all Vaults
  explicitly.
- Two Vaults with the same relative path do not collide in metadata, vector,
  graph, MCP, or context-pack output.
- An agent can request a context pack for a concrete task instead of reading the
  whole Vault.
- A user or agent can ask a natural-language question and receive a concise
  answer whose major claims are cited, labeled as inferred or partial, or
  rejected as insufficiently supported.
- Decision traces include evidence and distinguish stated facts from inferred links.
- All indexes can be deleted and rebuilt from Vault.
- Local-first operation works without internet access.
- Retrieval output never bypasses Vault's durable publication workflow.
- Answering never creates a second durable memory source or silently promotes
  generated claims to Vault truth.

## 21. Final Vision

Vault stores durable project knowledge.

Vault Graph makes that knowledge easier to discover, trace, package, and reason
over for humans and agents.

```text
Vault
  |
  v
Vault Graph
  |
  v
Hybrid Retrieval / GraphRAG
  |
  v
Context Pack
  |
  v
Evidence-First Ask
  |
  v
CLI / MCP
  |
  v
Codex / Agents
```

Vault Graph is not just a search system. It is an intelligent, read-only
knowledge access and reasoning layer that helps preserve project context,
expose decision history, package task context, and answer questions from
grounded Vault evidence while Vault remains the durable source of truth.

## TODO: MacBook Local Acceleration Adapter

Phase 2B intentionally keeps `FastEmbedTextEmbeddings` on local CPU. A future
MacBook acceleration path should be added as an adapter, not by changing
`VectorIndexer`, `VectorStore`, or Chroma behavior.

Candidate adapter names:

- `CoreMLTextEmbeddings` if implemented through ONNX Runtime CoreML Execution
  Provider.
- `AppleAcceleratedTextEmbeddings` if the implementation may choose CoreML, MLX,
  or another Apple-local runtime behind one adapter.

Future adapter rules:

- Implement the existing `TextEmbeddings` interface and return a complete
  `EmbeddingModelSpec`.
- Keep CPU FastEmbed as the default until Apple acceleration has deterministic
  output checks, dependency checks, and benchmark evidence.
- Package Apple acceleration as an explicit optional install target, for example
  `vault-graph[apple-accel]`, unless later evidence shows it is as simple and
  reliable as the CPU default.
- Do not silently fall back from Apple acceleration to CPU. If a user configured
  an Apple runtime and the runtime is unavailable, status must report the missing
  provider and indexing must fail the vector step clearly.
- Treat runtime changes as model-spec changes unless tests prove vector
  equivalence. A CPU vector projection and a CoreML/MLX vector projection must
  not be searched together under one logical model spec by accident.
- Keep all model artifacts and compiled runtime caches outside registered Vault
  roots. CoreML compiled-model caches must be keyed by model hash or model
  revision so stale compiled artifacts cannot be reused invisibly.
- Add `vg status` diagnostics for embedding runtime, provider availability,
  cache path, and whether acceleration is active.

Required validation before implementing this TODO:

- Confirm the selected model's ONNX operators are supported by the Apple runtime.
- Compare CPU and accelerated embeddings for dimension, normalization, and
  similarity drift on a fixed multilingual sample set.
- Benchmark first-run compile time, warm-run throughput, memory usage, and
  battery impact on Apple Silicon.
- Prove offline behavior after the model and compiled cache are present.
- Prove read-only boundaries: no Vault file is written, renamed, deleted, or
  rewritten by the acceleration adapter.
- Add regression tests showing acceleration failure does not corrupt metadata,
  vector manifests, or existing CPU vector projections.

## TODO: Non-Markdown Document Reader Adapters

The default indexing policy remains Markdown-only. Phase 2B must keep `.md`
files as the only indexed document type and must not expand the local vector
indexing slice into binary document extraction.

Future non-Markdown support should be added through read-only document reader
adapters. It must not convert, rewrite, rename, delete, or create files inside a
registered Vault root.

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

Adapter responsibilities:

- detect supported file extensions and MIME hints
- read source bytes without mutating the Vault
- compute `raw_sha256` from source bytes
- extract deterministic text and source-location metadata
- report reader name, reader version, parser version, and extraction warnings
- return normalized document input to the existing metadata pipeline

Adapter non-responsibilities:

- no Vault file mutation
- no durable Markdown conversion inside Vault
- no source registration or publication workflow replacement
- no vector persistence
- no retrieval ranking policy
- no hosted extraction service by default

Recommended rollout order:

1. Keep `.md` as the default and only required reader.
2. Add `.txt` as the first non-Markdown reader if needed because it has no
   binary extraction dependency.
3. Add PDF text-layer extraction only after source-location evidence can include
   page numbers and text offsets.
4. Add DOCX only after heading and paragraph extraction can be made
   deterministic.
5. Treat OCR, scanned PDFs, spreadsheets, slides, images, and audio as later
   optional adapters with explicit dependencies and clear status warnings.

Evidence and identity requirements:

- Every extracted document and chunk must still carry `vault_id`, path,
  `document_id`, `chunk_id`, `raw_sha256`, content hash, parser version,
  chunker version, and index revision.
- Evidence for non-Markdown chunks must include source locators such as page
  number, paragraph index, heading path, line range, or byte/text offset when the
  format supports it.
- `VectorStore` must continue to store only semantic candidate metadata.
  Rendered evidence must still resolve through `MetadataStore`.
- Unsupported non-Markdown files should be skipped or reported as warnings by a
  future explicit feature flag. They must not make Markdown indexing fail by
  default.

Freshness and rebuild rules:

- Reader version, parser version, chunker version, source bytes hash, extraction
  options, and dependency schema version are staleness inputs.
- Extracted text caches, if added, must live outside registered Vault roots and
  must be disposable.
- A reader change that alters extracted text or chunk boundaries must stale the
  affected metadata and vector records through normal reconcile.
- Non-Markdown adapters must use the same multi-vault identity rules as
  Markdown: paths are unique only inside a `vault_id`.

Dependency and safety rules:

- Non-Markdown readers should be optional install extras until they are proven
  simple and reliable enough for the default install.
- Missing optional dependencies should produce explicit status diagnostics, not
  silent partial extraction.
- Readers must enforce file-size and extraction-time limits so one large file
  cannot make local indexing unpredictable.
- Symlink and path-escape protections must match Markdown loading.

Required tests before implementing this TODO:

- unsupported non-Markdown files do not mutate Vault and do not break Markdown
  indexing
- each reader computes stable `raw_sha256` from source bytes
- extracted text and chunk IDs are deterministic for the same source file and
  reader version
- reader-version or extraction-option changes stale affected records
- multi-vault files with the same relative path do not collide
- evidence resolution returns the original Vault path and format-specific
  locator
- missing optional extraction dependencies produce clear status output
- extraction caches, if any, are outside registered Vault roots

## TODO: Markdown Chunking Strategy Migration

Phase 2B uses `heading-section-v1` so local vector indexing can ship against a
simple, explainable chunk boundary. That policy is intentionally a starting
point, not the final Markdown retrieval strategy. Future chunking must evolve
through versioned chunker policies so existing metadata, vector manifests, and
retrieval behavior can migrate without changing `VectorStore` or making Vault
Graph a durable knowledge source.

This section is a future migration guide only. It does not add Phase 2B
implementation scope, does not enable `vg search`, and does not change the
accepted Phase 2B rule that vector indexing uses Markdown `heading-section-v1`
chunks.

The long-term direction is:

```text
heading-section-v1
  -> markdown-block-window-v2
  -> hierarchical-retrieval-v3
```

Each policy version must produce deterministic chunk IDs for the same Vault
file, reader version, parser version, chunker version, source text, and
chunker configuration. A chunker version or configuration change that alters
chunk boundaries or chunk text must stale affected metadata and vector records
through the normal reconcile path.

### `heading-section-v1`

`heading-section-v1` treats each Markdown heading section as the retrievable
chunk boundary.

Strengths:

- easy to understand and inspect
- preserves Markdown heading structure naturally
- makes evidence resolution straightforward because each chunk maps to one
  section or anchor
- keeps Phase 2B focused on rebuildable local vector indexing rather than
  ranking quality work

Known limits:

- large sections can exceed embedding input limits or dilute semantic signal
- small sections can lack enough local context for reliable retrieval
- uneven section sizes create uneven vector granularity and ranking behavior
- a small edit inside a large section stales the whole section vector

Phase 2B should keep this policy as the default until vector indexing,
manifest export, stale detection, and `vg status` diagnostics are stable.

### `markdown-block-window-v2`

`markdown-block-window-v2` should keep Markdown structure as authority but use a
token-budgeted block window as the embedding unit.

The parser should first produce structural blocks:

- heading breadcrumb
- paragraph
- list
- table
- block quote
- code fence
- frontmatter-derived searchable fields, if any

The chunker should then group adjacent blocks inside a heading section until a
target token budget is reached. It should avoid splitting semantic blocks when
possible. A table, list, or code fence should remain intact unless it exceeds
the hard maximum by itself, in which case the split rule must be deterministic
and recorded in the chunker policy.

Recommended configuration fields:

- `target_tokens`
- `min_tokens`
- `max_tokens`
- `overlap_tokens`
- `preserve_code_fences`
- `preserve_tables`
- `include_heading_breadcrumb`

The chunk text embedded by `TextEmbeddings` should include a compact breadcrumb
prefix, for example:

```text
Document title > Parent heading > Current heading

Chunk body...
```

The breadcrumb is search context, not durable content. Evidence rendering must
still resolve the chunk through `MetadataStore` and show the original Vault
path, heading, anchor, content hash, and line or block locator when available.

Chunk identity should be stable across unrelated edits. A recommended logical
identity shape is:

```text
vault_id + document_id + heading_path + block_range + chunker_version
```

The chunk content hash should be computed from the exact embedded chunk text
plus chunker configuration that affects text. This lets one changed block stale
only the affected block-window chunks instead of every vector in a large
heading section.

Migration from `heading-section-v1` to `markdown-block-window-v2` must be a
full chunker-version migration for selected scopes:

1. Metadata indexing parses Markdown into structural blocks.
2. The new chunker produces `markdown-block-window-v2` chunk snapshots.
3. `MetadataStore` records the new chunker version and current chunk IDs.
4. `VectorIndexer` compares live chunks with the vector manifest.
5. Old `heading-section-v1` vectors inside the selected scope are tombstoned.
6. New `markdown-block-window-v2` chunks are embedded and upserted.
7. `vg status` reports chunker version, stale vector count, and the selected
   reconcile scope.

The migration must not require a cross-store transaction. If metadata migration
succeeds but vector reindexing fails, the vector projection is stale or
unavailable and must recover on the next `vg index`.

Required tests before implementing `markdown-block-window-v2`:

- deterministic chunk IDs for unchanged Markdown
- stable chunk IDs for unrelated edits in other sections
- large sections split under `max_tokens`
- small sections receive heading breadcrumb context
- code fences and tables are preserved or split by explicit deterministic rules
- chunker-version changes stale affected metadata and vector records
- old-version vectors are tombstoned only inside the selected `QueryScope`
- evidence resolution still returns the original Vault path and anchor
- no Vault file is written, renamed, deleted, or rewritten

### `hierarchical-retrieval-v3`

`hierarchical-retrieval-v3` should separate the search unit from the context
assembly unit.

This is a post-2C retrieval-policy direction, not a Phase 2B indexing
deliverable and not a Phase 2C search deliverable.

Fine-grained chunks should be used for recall:

- block-window chunks from `markdown-block-window-v2`
- stable chunk IDs
- vector and keyword candidate lookup
- content-scope filtering before result limits

Parent context should be used for understanding:

- heading section
- parent heading chain
- sibling chunks near the hit
- document-level metadata
- explicit links and future graph relationships

The retrieval layer, not `VectorStore`, owns this expansion. `VectorStore`
continues to return semantic candidate metadata only. `MetadataStore` resolves
chunk IDs to evidence and provides the parent or neighboring context needed for
ranking, explanations, search output, and future context packs.

Recommended retrieval flow:

```text
QueryScope
  -> keyword candidate lookup
  -> vector candidate lookup
  -> candidate merge and dedupe by chunk ID
  -> MetadataStore evidence resolution
  -> parent and neighbor context expansion
  -> ranking and context-budget selection
  -> evidence-linked result or context-pack item
```

The system should keep both levels explicit in result explanations:

- `matched_chunk_id`: the fine chunk that matched the query
- `context_chunk_ids`: neighboring chunks included for context
- `parent_section`: heading section used for expansion
- `retrieval_reason`: keyword, vector, graph, or hybrid signal
- `warnings`: stale, missing, oversized, truncated, or conflicting evidence

This makes ranking tunable without changing vector storage. It also prevents
large sections from dominating vector search while still giving agents enough
context to work safely.

Migration from `markdown-block-window-v2` to `hierarchical-retrieval-v3` should
not force a vector rebuild if chunk IDs, chunk text, chunker version, and
embedding model spec are unchanged. It is primarily a retrieval-policy
migration. It should be versioned separately from the chunker:

- `chunker_version` controls chunk boundaries and vector staleness.
- `retrieval_policy_version` controls candidate fusion, context expansion, and
  context-budget selection.
- `context_pack_schema_version` controls rendered pack fields.

If `hierarchical-retrieval-v3` requires additional metadata such as block
offsets, parent-child section links, or neighbor chunk ordering, metadata
indexing may need a schema migration. That schema migration must not by itself
stale vectors unless the embedded chunk text or chunk IDs change.

Required tests before implementing `hierarchical-retrieval-v3`:

- vector hits still resolve through `MetadataStore`
- parent and neighbor expansion respects `QueryScope`
- context expansion does not cross Vaults unless explicit `vault_ids` are used
- retrieval explanations distinguish matched chunks from expanded context
- context budgets truncate deterministically
- stale or missing parent context produces visible warnings
- retrieval-policy changes do not stale vectors when chunk text is unchanged
- graph expansion, when added later, joins as another retrieval signal rather
  than a vector-store responsibility

### Migration Guardrails

Chunking and retrieval evolution must follow these guardrails:

- Keep Markdown as the only required reader until the non-Markdown adapter TODO
  graduates separately.
- Keep chunking inside the metadata/indexing pipeline. Do not move chunk
  boundary decisions into `VectorStore`.
- Keep `VectorStore` ignorant of path, title, rendered text, and evidence
  authority.
- Keep every policy version inspectable through status or manifest export.
- Keep old projections disposable and rebuildable from Vault.
- Do not silently mix different `EmbeddingModelSpec` values in one search.
- Do not silently mix incompatible chunker versions in one retrieval policy.
- Prefer full selected-scope reindexing for chunker migrations and lightweight
  retrieval-policy migrations when only ranking or context expansion changes.
- Record enough run metadata to explain whether a stale result came from source
  text, parser version, chunker version, embedding model spec, store schema, or
  retrieval policy.

## TODO: External Memory Layer Adapter And Export Target

External memory systems such as Mem0, MemMachine, or an MCP memory server may be
useful later for agent personalization, cross-session recall, or shared memory
between multiple agent runtimes. This is a future adapter/export direction only.
It does not change Phase 6 and must not make Vault Graph a writable memory
system.

The accepted boundary is:

```text
Vault
  -> Vault Graph derived indexes
  -> evidence-linked memory projections
  -> optional external memory adapter or export target
```

The adapter direction should preserve these rules:

- Vault remains the durable source of truth.
- Vault Graph memory projections remain read-only, disposable, and rebuildable.
- External memory systems consume projection exports; they do not become
  `MetadataStore`, `VectorStore`, `GraphStore`, or `vault_graph.memory`
  replacements.
- No external adapter may write, rename, rewrite, delete, publish, or validate
  Vault content.
- No external adapter may feed agent-generated memories back into Vault Graph as
  facts unless those memories are captured in Vault and re-indexed through the
  normal Vault workflow.
- Outbound records must include `vault_id`, evidence references, store
  revisions, generated timestamps, freshness status, warnings, and export
  schema version.
- Profile, preference, procedural, and raw episode memories stay outside Vault
  Graph core. If the user wants them, they must live in Vault as durable notes or
  in an explicitly configured external adapter.

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

`MemoryExportRecord` should be an outbound DTO, not a writable memory entity. It
should contain only projection metadata, evidence refs, labels, warnings, and a
compact summary already present in structured Vault Graph output.

Do not implement this TODO until Phase 6A, 6B, and 6C are complete and stable.
Required validation before implementation:

- prove exported records are reproducible from the same Vault-derived state
- prove disabling or deleting the external memory adapter loses no Vault Graph
  truth
- prove no external-memory dependency is imported by default
- prove adapter failures produce warnings or export errors without breaking
  search, context-pack, graph, or Phase 6 memory projections
- prove cross-Vault exports preserve Vault IDs and never merge by title alone
- document whether the adapter is push export, pull resource, or MCP tool
  integration before adding any code
