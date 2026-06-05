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

Vault Graph may read configured Vault paths. It may write only to the configured
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
- embedding policy version
- extraction policy version
- store schema versions
- graph projection version

If two index runs use the same Vault revision and policy versions, query
behavior should be functionally equivalent.

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

## 5. Architecture Overview

```text
Vault
  raw/ wiki/ docs/ scratch/reports/
    |
    v
VaultLoader
  scans files, reads content, records hashes
    |
    v
DocumentPipeline
  reads Vault frontmatter, parses markdown, normalizes sections, chunks text
    |
    +--> MetadataIndexer -> MetadataStore
    |
    +--> ExtractionPipeline -> GraphIndexer -> GraphStore
    |
    +--> VectorIndexer -> VectorStore
                                   |
GraphStore -----------------------+
    |
    v
GraphProjection
  rustworkx working graph and disposable cache
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
- `vg index`
- `vg index --full`
- `vg index --dry-run`
- `vg watch`
- `vg status`
- `vg ask "question"`
- `vg related TARGET`
- `vg context "goal"`
- `vg decision-trace TOPIC`
- `vg serve --mcp`
- `vg serve --http`

### 6.2 `app`

Responsibility:

- expose MCP and HTTP adapters
- own request and response translation
- share application services with CLI
- enforce read-only behavior at the serving boundary

`app/mcp_server.py` maps MCP resources, tools, and prompts to application
services. `app/http_server.py` exposes the same capabilities for custom
clients. Neither server owns retrieval logic.

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
- `relation_extractor.py`
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
- `graph_indexer.py`: writes nodes, edges, evidence, status, confidence, and
  extraction metadata
- `revision_planner.py`: compares Vault file state and policy versions against
  store state
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
- invalidate caches when revisions or policy versions change

Core modules:

- `graph_projection.py`: interface and domain-level projection operations
- `rustworkx_projection.py`: rustworkx adapter
- `projection_cache.py`: disposable cache read/write and invalidation

`GraphProjection` must not become the graph database. Query responses must
resolve graph results back through `GraphStore` evidence records.

### 6.10 `retrieval`

Responsibility:

- retrieve vector candidates
- retrieve graph candidates
- combine keyword, vector, graph, wiki link, decision-map, and timeline-map
  signals
- rerank candidates
- explain why results were returned
- build evidence-linked context packs

Core modules:

- `vector_retriever.py`
- `graph_retriever.py`
- `hybrid_retriever.py`
- `reranker.py`
- `context_pack_builder.py`

Retrieval output must include enough metadata for `explain_result(result_id)`
to describe scores, evidence, relationship status, confidence, and warnings.

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

- Vault path
- Vault Graph state path
- source scopes
- entity schema
- retrieval policy
- embedding policy
- storage backend selection
- optional scale-up backend configuration

Configuration files:

- `configs/sources.yaml`
- `configs/entity_schema.yaml`
- `configs/retrieval_policy.yaml`
- `configs/embedding_policy.yaml`
- `configs/storage_backends.yaml`
- `configs/scaleup_backends.example.yaml`

Configuration loading order:

1. built-in defaults
2. project config files
3. local user config
4. command-line overrides

Command-line overrides should be visible in status output so users can inspect
which Vault and state paths are active.

## 8. Domain Records

The implementation should prefer typed records at package boundaries. Backend
implementations can serialize these records however they need, but application
services should exchange common logical shapes.

### 8.1 Evidence Reference

An evidence reference identifies why a result exists.

Fields:

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

### 8.2 Document Snapshot

A document snapshot represents one indexed view of one Vault file.

Fields:

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

### 8.3 Chunk Snapshot

A chunk snapshot represents retrievable text derived from a document.

Fields:

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

### 8.4 Entity Record

An entity record represents a derived node.

Fields:

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
- `index_revision`

### 8.5 Relationship Record

A relationship record represents a derived edge.

Fields:

- `id`
- `type`
- `source_entity_id`
- `target_entity_id`
- `evidence_path`
- `evidence_excerpt`
- `status`
- `confidence`
- `extraction_method`
- `created_at`
- `updated_at`
- `index_revision`

Allowed statuses:

- `stated`
- `inferred`
- `contested`
- `deprecated`

### 8.6 Retrieval Result

A retrieval result is a ranked candidate with evidence and explanation data.

Fields:

- `result_id`
- `kind`
- `title`
- `summary`
- `score`
- `rank`
- `evidence`
- `signals`
- `relationship_status`
- `warnings`
- `backend`
- `index_revision`

### 8.7 Context Pack

A context pack is a structured brief generated for a goal.

Required fields:

- `goal`
- `scope`
- `vault_revision`
- `index_revision`
- `backend`
- `store_revisions`
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

`MetadataStore` owns file identity, chunk identity, path mapping, content
hashes, parser and chunker version state, source-state projections, Vault
frontmatter snapshots, tombstones, and index revision tracking.

Required operations:

- upsert document snapshots for an index revision
- upsert chunk snapshots for an index revision
- record parser and chunker versions
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

### 9.2 VectorStore

`VectorStore` owns embedding persistence, vector search, embedding model version
state, vector index revision tracking, and vector backend replacement.

Required operations:

- upsert embeddings for chunk IDs
- delete or tombstone embeddings for stale chunks
- run filtered vector search
- validate embedding dimensions
- validate embedding model and version
- validate embedding policy version
- report backend health
- report collection or schema compatibility
- report index freshness
- export embedding manifests in the common logical vector shape

Vector search must return chunk IDs and vector metadata. Callers must resolve
chunk IDs through `MetadataStore` before returning evidence to users.

### 9.3 GraphStore

`GraphStore` owns persisted node records, edge records, evidence references,
relationship status, confidence, extraction metadata, and graph revision
metadata.

Required operations:

- upsert entity records
- upsert relationship records
- tombstone stale entities and relationships
- resolve entity IDs to evidence-linked records
- resolve edge IDs to evidence-linked records
- query neighborhoods by entity
- query edges by relationship type and status
- report backend health
- report schema compatibility
- report graph revision freshness
- export records in the common logical graph shape

`GraphStore` is derived and non-authoritative, but it is the persisted graph
contract. `GraphProjection` depends on it.

### 9.4 GraphProjection

`GraphProjection` owns runtime graph algorithms over a bounded working graph.

Required operations:

- build a projection from `GraphStore`
- load a valid disposable cache
- invalidate stale caches
- traverse neighborhoods
- compute paths
- rank related nodes
- return graph results that can be resolved back to `GraphStore`
- report projection freshness

Cache keys must include:

- index revision
- graph store revision
- parser version
- chunker version
- extraction policy version
- graph projection version

## 10. Indexing Design

Indexing has two modes: planning and applying.

Planning is read-only. It scans Vault and compares file state, parser versions,
chunker versions, embedding versions, extraction policy versions, store schema
versions, and projection versions against current Vault Graph state.

Applying mutates only Vault Graph state. It updates metadata, vectors, graph
records, revision rows, and projection caches.

### 10.1 Full Rebuild

`vg index --full` should:

1. scan all configured Vault sources
2. compute file state and hashes
3. parse and normalize all included documents
4. rebuild metadata records
5. rebuild embeddings
6. rebuild graph records
7. invalidate projection caches
8. record a new index revision
9. report warnings and backend health

Full rebuild must not mutate Vault.

### 10.2 Incremental Rebuild

`vg index` should:

1. scan configured Vault sources
2. compare file state with `MetadataStore`
3. classify files as unchanged, changed, stale, deleted, or tombstoned
4. parse only affected documents
5. update affected metadata records
6. update affected vector records
7. update affected graph records
8. invalidate affected projection cache entries
9. record a new index revision
10. report warnings and backend health

If parser, chunker, embedding, extraction, or schema versions change, the
revision planner should expand the affected set accordingly.

### 10.3 Dry Run

`vg index --dry-run` should:

1. scan configured Vault sources
2. classify planned work
3. validate backend availability
4. report planned document, chunk, vector, graph, and projection changes
5. report warnings
6. exit without mutating Vault Graph state

Dry-run output is an operational planning artifact, not durable knowledge.

### 10.4 Deleted And Stale Files

Deleted Vault files should produce tombstones in Vault Graph stores. Tombstones
prevent stale derived records from appearing as fresh results while preserving
enough state to explain why a record disappeared.

Stale files should produce warnings when:

- indexed content hash differs from current content hash
- raw SHA-256 differs from the recorded value
- parser or chunker version changed
- embedding policy changed
- extraction policy changed
- projection cache is invalid

## 11. Retrieval Design

Retrieval combines multiple evidence signals while keeping output explainable.

### 11.1 Search Flow

```text
Query
  -> normalize query and scope
  -> keyword and metadata candidate lookup
  -> vector candidate lookup
  -> graph candidate lookup
  -> wiki link, decision-map, or timeline-map expansion when available
  -> candidate merge and dedupe
  -> rerank
  -> evidence resolution
  -> warning attachment
  -> response rendering
```

Every candidate must resolve to evidence before it is shown as a normal result.
Candidates without enough evidence may appear only as warnings or inferred
follow-up suggestions.

### 11.2 Vector Retrieval

Vector retrieval searches `VectorStore` and returns vector IDs, chunk IDs,
scores, filters, embedding model metadata, and index revision metadata.

The caller then resolves chunk IDs through `MetadataStore` to attach path,
section, anchor, content hash, raw SHA-256, and Vault revision.

### 11.3 Graph Retrieval

Graph retrieval starts with entity lookup or candidate documents, expands
neighborhoods through `GraphStore`, and may use `GraphProjection` for bounded
algorithmic ranking.

Graph results must distinguish relationship status:

- `stated`: directly supported by durable text
- `inferred`: derived by extraction or traversal
- `contested`: conflicts or unresolved disagreement exists
- `deprecated`: stale or superseded relationship

### 11.4 Hybrid Ranking

Hybrid ranking should combine:

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

`ask_vault(question, mode="evidence-first")` should:

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

### 12.1 Selection Rules

The builder should prioritize:

1. explicit user scope
2. current durable specs and architecture pages
3. durable decisions
4. relevant concepts, systems, and workflows
5. recent durable changes
6. open questions and unresolved warnings
7. raw evidence when it explains a durable page

The builder should avoid:

- unrelated full-Vault dumps
- duplicated evidence excerpts
- unsupported synthesis
- stale records without warning labels
- context that exceeds the configured token budget

### 12.2 Assembly Flow

```text
Goal
  -> scope normalization
  -> hybrid retrieval
  -> decision and constraint extraction
  -> current-state summary
  -> evidence grouping
  -> warning collection
  -> token-budget packing
  -> JSON or Markdown rendering
```

### 12.3 Token Budgeting

When `max_tokens` is set, the builder should keep required fields and evidence
metadata before long excerpts. If content must be omitted, it should include a
warning that names the omitted category.

## 13. Decision Trace Design

`get_decision_trace(decision_or_topic)` should prefer durable
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
- recent decisions
- recent durable changes
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

Timeline memory groups durable changes and derived index changes. It must label
whether an item is a durable Vault change, an indexed projection change, or a
warning.

## 15. MCP Design

MCP is the primary agent integration surface.

### 15.1 Resources

Initial resources:

```text
vault://documents/{path}
vault://pages/{path}
vault://sources/{id}
vault://concepts/{name}
vault://decisions/{id}
vault://issues/{id}
vault://timeline/recent
vault://context/current
vault://context/packs/{id}
vault://graph/entities/{id}
```

Resources are read-only views over Vault or Vault Graph projections. Responses
should include evidence metadata when relevant.

### 15.2 Tools

Initial tools:

- `search_vault(query, scope=None, limit=10)`
- `ask_vault(question, mode="evidence-first")`
- `find_related(target, depth=1, kinds=None)`
- `get_decision_trace(decision_or_topic)`
- `build_context_pack(goal, scope=None, max_tokens=None)`
- `summarize_project_memory(scope=None)`
- `get_open_questions(scope=None)`
- `get_recent_changes(since=None)`
- `explain_result(result_id)`
- `check_index_status()`

Tools call application services and return structured, evidence-linked data.
They must not write to Vault.

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

Recommended common options:

- `--vault PATH`
- `--state PATH`
- `--config PATH`
- `--json`
- `--verbose`

Command behavior:

- `vg init`: validates paths and writes Vault Graph configuration only
- `vg index`: applies incremental derived-state updates
- `vg index --full`: applies full derived-state rebuild
- `vg index --dry-run`: reports planned derived-state updates without mutation
- `vg watch`: runs repeated incremental indexing
- `vg status`: reports backend and revision health
- `vg ask`: renders evidence-first answers
- `vg related`: renders related entities and evidence
- `vg context`: renders JSON or Markdown context packs
- `vg decision-trace`: renders decision traces
- `vg serve --mcp`: starts the MCP server
- `vg serve --http`: starts the HTTP server

All commands should print active Vault and state paths when the operation could
otherwise be ambiguous.

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

When possible, user-facing errors should include the active Vault path, active
state path, backend name, revision metadata, and a suggested safe next command.

## 19. Read-Only Enforcement

Read-only behavior should be enforced in three layers.

### 19.1 Path Guard

All write operations must go through a path guard that allows writes only under
the configured Vault Graph state path. The guard should reject writes to the
configured Vault path.

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
- `embedding_policy_version`
- `extraction_policy_version`
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
- future Postgres behavior against the metadata contract
- future Qdrant behavior against the vector contract
- future Neo4j behavior against the graph contract

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

### 21.4 Integration Tests

Integration tests should cover:

- full rebuild over a fixture Vault
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
2. vector search and hybrid retrieval
3. entity and relationship graph
4. context pack builder
5. MCP server
6. memory and explorer projections
7. optional UI

Each phase should preserve the read-only boundary and include focused tests
before expanding the next layer.

## 23. Design Checks

Before a phase is considered complete, verify:

- Vault files are unchanged by Vault Graph commands
- generated state can be deleted and rebuilt
- result evidence resolves back to Vault paths and revisions
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
- `vg status` reports backend health, schema compatibility, index freshness,
  and projection freshness
- `vg ask` returns evidence-first answers with warnings instead of unsupported
  claims
- `vg context` returns a context pack matching the required JSON contract
- `vg decision-trace` prefers durable decision pages and labels inferred graph
  relationships
- MCP tools expose the same read-only behavior as CLI commands
- all derived indexes can be deleted and rebuilt from Vault

Vault Graph is valuable only while it keeps Vault authoritative. Every module
boundary, store contract, warning, and test should protect that rule.
