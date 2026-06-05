# Vault Graph Specification

Version: 1.0

Status: Draft

Author: Jun Hyoung Lee

Date: 2026-06-04

## 1. Vision

Vault is the durable source of truth for project knowledge.

Vault Graph is a read-only, rebuildable knowledge access layer over Vault. It helps agents and humans discover context, trace decisions, and assemble task-specific context packs without turning retrieval output into durable knowledge.

The goal is not simple document search. The goal is to make the value of Vault easier to use:

- Project memory projection
- Decision tracing
- Context management
- Agent context packs
- GraphRAG-style exploration
- Development knowledge assetization

Vault remains the durable authority. Vault Graph interprets and indexes Vault. Agents consume Vault Graph outputs as context, not as a replacement for Vault.

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

Deleting all Vault Graph state and rebuilding from Vault should produce functionally equivalent results for the same version of the parser, chunker, embedding model, and extraction policy.

### Principle 3: Agents Consume Context Packs

Agents should not read an entire Vault for ordinary tasks. They should request a scoped context pack.

```text
Vault
  |
  v
Vault Graph retrieval
  |
  v
Context Pack
  |
  v
Agent
```

A context pack is an evidence-linked working brief. It is not durable knowledge until a human or agent intentionally publishes it back through Vault's validation workflow.

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

Every context pack and decision trace should include:

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
      | SQLite edges   |              | rank + explain |
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
│   ├── embedding_policy.yaml
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
│       │   ├── mcp_server.py
│       │   └── http_server.py
│       ├── ingestion/
│       │   ├── vault_catalog.py
│       │   ├── vault_loader.py
│       │   ├── markdown_parser.py
│       │   ├── vault_frontmatter_reader.py
│       │   └── document_normalizer.py
│       ├── extraction/
│       │   ├── entity_extractor.py
│       │   ├── relation_extractor.py
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
│       │   └── context_pack_builder.py
│       ├── memory/
│       │   ├── project_memory.py
│       │   ├── decision_memory.py
│       │   ├── issue_memory.py
│       │   └── timeline_memory.py
│       ├── storage/
│       │   ├── interfaces/
│       │   │   ├── metadata_store.py
│       │   │   ├── vector_store.py
│       │   │   ├── graph_store.py
│       │   │   └── store_health.py
│       │   ├── local/
│       │   │   ├── sqlite_metadata_store.py
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
    └── test_graph_projection_cache.py
```

The default implementation is local-first. Files under `storage/local/` are required for MVP. Files under `storage/adapters/` define optional scale-up adapter boundaries for Postgres, Qdrant, and Neo4j; they must not make hosted services mandatory for the default workflow.

`storage/interfaces/` owns the stable store contracts. Indexing, retrieval, MCP tools, and context pack builders must depend on these interfaces instead of importing local or scale-up backend implementations directly.

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
- Relationship and edge records must carry `source_vault_id`,
  `target_vault_id`, and `evidence_vault_id`.
- `path` is never globally unique by itself; file identity is `(vault_id, path)`.
- `document_id`, `chunk_id`, `entity_id`, `edge_id`, and vector IDs must either
  include their Vault namespace fields in stable derivation or be stored with
  equivalent Vault-scoped uniqueness constraints.
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
- Recent decisions
- Recent durable changes
- Open issues
- Next likely priorities
- Evidence links
- Warnings or stale areas

This is a projection from Vault, not a separate memory database.

### 7.2 Decision Tracking

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

### 7.3 Context Management

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

### 7.4 Agent Context Packs

Context packs are structured briefs for agents.

Required fields:

- `goal`
- `scope`
- `vaults`
- `backend`
- `store_revisions`
- `current_state`
- `relevant_pages`
- `relevant_sources`
- `decisions`
- `constraints`
- `open_questions`
- `warnings`
- `evidence`
- `generated_at`
- `vault_revisions`
- `index_revision`

### 7.5 GraphRAG Exploration

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

### 7.6 Knowledge Assetization

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
- `id`
- `type`
- `name`
- `aliases`
- `canonical_path`
- `source_paths`
- `wiki_paths`
- `first_seen_at`
- `last_seen_at`
- `confidence`
- `extraction_method`
- `content_hash`

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

- `id`
- `type`
- `source_vault_id`
- `source_entity_id`
- `target_vault_id`
- `target_entity_id`
- `evidence_vault_id`
- `evidence_path`
- `evidence_excerpt`
- `status`
- `confidence`
- `extraction_method`
- `created_at`
- `updated_at`

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

Graph:

- SQLite persisted node, edge, evidence, and graph revision tables as `GraphStore`
- rustworkx in-memory graph projection rebuilt from `GraphStore`
- optional serialized rustworkx cache keyed by `index_revision`, `parser_version`, `chunker_version`, and `extraction_policy_version`

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
- resolve document IDs and chunk IDs to evidence locations
- record parser, chunker, index, and backend schema versions
- report backend health, schema compatibility, and revision freshness
- export or inspect records in the common logical metadata shape

### 10.4 VectorStore Boundary

`VectorStore` is the persisted embedding and vector retrieval projection.

For MVP, `VectorStore` is Chroma collections derived from `MetadataStore` chunks
and local embedding output. It stores embedding vectors, vector IDs, `vault_id`,
document IDs, chunk IDs, embedding model metadata, embedding policy metadata,
filters, and index revision metadata. It is rebuildable from Vault through
`MetadataStore` and must remain non-authoritative.

The boundary is mandatory:

- `VectorStore` owns embedding persistence, vector search, embedding model version state, vector index revision tracking, and vector backend replacement.
- `VectorStore` must not own document identity, chunk text authority, evidence authority, graph relationships, or durable wiki publication.
- Query tools must resolve vector hits through `MetadataStore` before returning evidence.
- Vector results must return `vault_id`, Vault paths, wiki paths, chunk IDs,
  content hashes, embedding model versions, and retrieval scores.
- Qdrant must be a scale-up `VectorStore` implementation over the same logical record contract, not a different retrieval authority.

Required `VectorStore` capabilities:

- upsert embeddings for chunk IDs from a specific metadata/index revision
- delete or tombstone embeddings for stale chunks
- run filtered vector search with `QueryScope`, model, and revision metadata
- validate embedding dimensions, model name, model version, and embedding policy version
- report backend health, collection/schema compatibility, and index freshness
- export or inspect embedding manifests in the common logical vector shape

### 10.5 GraphStore And GraphProjection Boundary

`GraphStore` is the persisted graph projection.

For MVP, `GraphStore` is SQLite tables derived from Vault files and indexer
output. It stores node records, edge records, `vault_id` fields, evidence
references, relationship status, confidence, extraction metadata, and index
revision metadata. It is rebuildable from Vault and must remain
non-authoritative.

`GraphProjection` is the runtime graph used for algorithms.

For MVP, `GraphProjection` is a rustworkx graph built from `GraphStore` rows. It is used for traversal, path finding, ranking, neighborhood expansion, and decision trace prototypes. It may be serialized only as a cache. A serialized rustworkx graph must be disposable and must be invalidated when any graph store row, parser version, chunker version, extraction policy version, or index revision changes.

The boundary is mandatory:

- `GraphStore` owns persistence, revision tracking, evidence linkage, and backend replacement.
- `GraphProjection` owns in-process graph algorithms and temporary working subgraphs.
- Query tools must return evidence-linked results from `GraphStore`, not opaque rustworkx node IDs.
- rustworkx must not be treated as the durable graph database.
- Neo4j must not become a second source of truth; it is a scale-up `GraphStore` implementation over the same derived projection contract.
- Scale-up backends must preserve the same Vault IDs, node IDs, edge IDs,
  relationship types, evidence references, confidence fields, revision fields,
  and read-only Vault boundary as the MVP SQLite store.
- Every backend must support full rebuild, incremental update, dry-run planning, stale projection detection, and reproducible export back to the common graph store contract.

### 10.6 Scale-Up Boundary Requirements

Scale-up must be adapter-driven, not architecture-changing.

The MVP local stores are the reference contract:

- `MetadataStore`: SQLite for documents, chunks, hashes, parser state, and index
  revisions.
- `VectorStore`: Chroma for embeddings and vector retrieval metadata, including
  `vault_id` filters.
- `GraphStore`: SQLite for graph nodes, edges, evidence, relationship status,
  confidence, Vault IDs, and graph revisions.
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
- parser, chunker, embedding, extraction, metadata store, vector store, and graph store versions where applicable
- index revision, vault revision, backend name, backend schema version, and last validated timestamp
- evidence references for every returned record that contributes to an answer, trace, warning, or context pack

Each store also owns store-specific records:

- `MetadataStore`: document IDs, chunk IDs, file state, source-state projection,
  parser state, chunker state, and tombstones
- `VectorStore`: vector IDs, Vault IDs, document IDs, chunk IDs, embedding model,
  embedding model version, embedding policy version, filters, and retrieval
  scores
- `GraphStore`: Vault IDs, entity IDs, edge IDs, relationship type, relationship
  status, confidence, extraction method, and evidence path
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
- Query responses must include the backend name, index revision, and evidence references used to produce the result.

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
- `metadata_store_schema_version`
- `vector_store_schema_version`
- `embedding_model`
- `embedding_model_version`
- `extraction_policy_version`
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
  -> Extract entities
  -> Extract relationships
  -> Update MetadataStore document, chunk, hash, and revision rows
  -> Update VectorStore embeddings and vector revision metadata
  -> Update GraphStore node, edge, evidence, and revision rows
  -> Invalidate or rebuild GraphProjection cache
  -> Record index revision
```

The indexer must support:

- full rebuild
- incremental rebuild
- stale file detection
- deleted file tombstones
- parser or embedding policy migration
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

Initial tools:

- `search_vault(query, scope=None, limit=10)`
- `ask_vault(question, mode="evidence-first", scope=None)`
- `find_related(target, scope=None, depth=1, kinds=None)`
- `get_decision_trace(decision_or_topic, scope=None)`
- `build_context_pack(goal, scope=None, max_tokens=None)`
- `summarize_project_memory(scope=None)`
- `get_open_questions(scope=None)`
- `get_recent_changes(since=None, scope=None)`
- `explain_result(result_id)`
- `check_index_status()`

Tool responses must separate:

- answer
- evidence
- inferred links
- warnings
- suggested durable follow-up

Tool `scope` arguments use `QueryScope`. If no scope is provided, tools search
the active Vault only. Cross-Vault retrieval requires explicit `vault_ids`.

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

Initial CLI:

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
vg watch
vg status
vg ask "왜 GraphRAG를 도입했지?"
vg ask --vault-id main "왜 GraphRAG를 도입했지?"
vg related GraphRAG
vg related --vault-id main GraphRAG
vg context "GraphRAG MVP 구현"
vg context --vault-id main "GraphRAG MVP 구현"
vg decision-trace GraphRAG
vg decision-trace --vault-id main GraphRAG
vg serve --mcp
vg serve --http
```

CLI commands should be explicit about which Vault ID, Vault path, and index state
path they use. Commands that accept `--vault-id` operate on one registered Vault.
Commands that accept `--all-vaults` must expand to visible selected Vault IDs in
their output. Commands without either option use the active Vault.

## 18. Context Pack Contract

A context pack is a structured JSON or Markdown artifact generated from Vault Graph retrieval.

Minimum JSON shape:

```json
{
  "goal": "Implement GraphRAG MVP",
  "scope": {
    "vault_ids": ["main"],
    "content_scopes": ["wiki", "docs"],
    "include_cross_vault": false
  },
  "vaults": [
    {
      "vault_id": "main",
      "display_name": "Main Vault"
    }
  ],
  "vault_revisions": {
    "main": "git-sha-or-file-snapshot-id"
  },
  "index_revision": "index-revision-id",
  "backend": {
    "metadata_store": "sqlite",
    "vector_store": "chroma",
    "graph_store": "sqlite",
    "graph_projection": "rustworkx"
  },
  "store_revisions": {
    "metadata": "metadata-revision-id",
    "vector": "vector-revision-id",
    "graph": "graph-revision-id",
    "projection": "projection-cache-or-build-id"
  },
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

Context packs should be small enough for an agent to read directly and rich enough to avoid a full Vault scan.

## 19. Roadmap

### Phase 1: Vault Catalog, Vault Reader, And MetadataStore

- Vault catalog configuration with a default single-Vault entry
- Markdown parser and Vault frontmatter reader
- source/page/document normalization
- SQLite `MetadataStore` document, chunk, hash, source-state projection, and
  revision tables
- `MetadataStore` interface and backend health checks
- MetadataStore contract tests for future Postgres support
- read-only boundary tests

### Phase 2: Vector Search And Hybrid Retrieval

- chunking policy
- local embedding integration
- Chroma `VectorStore` collections
- `VectorStore` interface and backend health checks
- vector search
- hybrid keyword/vector retrieval
- evidence-first answer format
- VectorStore contract tests for future Qdrant support

### Phase 3: Entity And Relationship Graph

- entity extraction
- relationship extraction
- SQLite `GraphStore` node, edge, evidence, and revision tables
- rustworkx `GraphProjection` adapter
- graph traversal retrieval from `GraphStore` evidence with rustworkx ranking support
- decision trace prototype
- projection cache invalidation tests
- GraphStore backend contract tests for future Neo4j support

### Phase 4: Context Pack Builder

- context pack JSON contract
- Markdown context pack rendering
- ranking and evidence grouping
- stale/conflict warnings

### Phase 5: MCP Server

- MCP resources
- MCP tools
- MCP prompts
- Codex-compatible local configuration examples

### Phase 6: Memory And Explorer Views

- project memory projection
- decision explorer
- timeline explorer
- issue explorer
- storage backend health view
- projection freshness view
- scale-up backend adapter readiness checks

### Phase 7: Optional UI

- Ask Project
- Decision Explorer
- Agent Workspace
- Timeline View

## 20. Success Criteria

Vault Graph is successful when:

- A user can point it at a Vault and build an index without mutating Vault.
- A user can register multiple Vaults and index one Vault or all Vaults
  explicitly.
- Two Vaults with the same relative path do not collide in metadata, vector,
  graph, MCP, or context-pack output.
- An agent can request a context pack for a concrete task instead of reading the whole Vault.
- Decision traces include evidence and distinguish stated facts from inferred links.
- All indexes can be deleted and rebuilt from Vault.
- Local-first operation works without internet access.
- Retrieval output never bypasses Vault's durable publication workflow.

## 21. Final Vision

Vault stores durable project knowledge.

Vault Graph makes that knowledge easier to discover, trace, and package for agents.

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
MCP
  |
  v
Codex / Agents
```

Vault Graph is not just a search system. It is an intelligent, read-only knowledge access layer that helps preserve project context, expose decision history, and let AI agents work from grounded context while Vault remains the durable source of truth.
