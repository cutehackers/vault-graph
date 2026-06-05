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
  metadata index
  vector index
  graph index
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
                |           Vault           |
                | raw / wiki / docs / logs  |
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
      | Metadata Index |              | Vector Index   |
      | SQLite         |              | Chroma         |
      +-------+--------+              +-------+--------+
              |                               |
              v                               v
      +----------------+              +----------------+
      | Graph Index    |<------------>| Hybrid Search  |
      | NetworkX       |              | rank + explain |
      +-------+--------+              +-------+--------+
              |                               |
              +---------------+---------------+
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
│   ├── sources.yaml
│   ├── entity_schema.yaml
│   ├── retrieval_policy.yaml
│   └── embedding_policy.yaml
├── data/
│   └── .gitkeep
├── src/
│   └── vault_graph/
│       ├── app/
│       │   ├── mcp_server.py
│       │   └── http_server.py
│       ├── ingestion/
│       │   ├── vault_loader.py
│       │   ├── markdown_parser.py
│       │   ├── frontmatter_parser.py
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
│       │   └── incremental_indexer.py
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
│       │   ├── sqlite_store.py
│       │   ├── vector_store.py
│       │   └── graph_store.py
│       └── cli/
│           └── main.py
└── tests/
    ├── test_loader.py
    ├── test_incremental_indexing.py
    ├── test_context_pack.py
    └── test_read_only_boundary.py
```

## 6. Core Capabilities

### 6.1 Project Memory Projection

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

### 6.2 Decision Tracking

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

### 6.3 Context Management

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

### 6.4 Agent Context Packs

Context packs are structured briefs for agents.

Required fields:

- `goal`
- `scope`
- `current_state`
- `relevant_pages`
- `relevant_sources`
- `decisions`
- `constraints`
- `open_questions`
- `warnings`
- `evidence`
- `generated_at`
- `vault_revision`
- `index_revision`

### 6.5 GraphRAG Exploration

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

### 6.6 Knowledge Assetization

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

## 7. Entity Model

### 7.1 Core Entities

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

### 7.2 Project Entities

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

### 7.3 Entity Fields

Minimum entity fields:

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

## 8. Relationship Model

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
- `source_entity_id`
- `target_entity_id`
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

## 9. Storage Strategy

### 9.1 MVP

Metadata:

- SQLite

Vector search:

- Chroma
- local embedding model by default

Graph:

- NetworkX persisted from SQLite-derived edge tables or serialized graph state

### 9.2 Scale-Up

Metadata:

- Postgres

Vector search:

- Qdrant

Graph:

- Neo4j

Scale-up storage must remain replaceable. It must not change the source-of-truth boundary.

## 10. Incremental Indexing

Vault Graph tracks file state with:

- `path`
- `kind`
- `content_hash`
- `raw_sha256`
- `frontmatter_hash`
- `parser_version`
- `chunker_version`
- `embedding_model`
- `embedding_model_version`
- `extraction_policy_version`
- `last_indexed_at`
- `last_seen_at`

Indexing flow:

```text
Scan Vault
  -> Detect changes
  -> Parse frontmatter and markdown
  -> Normalize document
  -> Chunk content
  -> Extract entities
  -> Extract relationships
  -> Update metadata index
  -> Update vector index
  -> Update graph index
  -> Record index revision
```

The indexer must support:

- full rebuild
- incremental rebuild
- stale file detection
- deleted file tombstones
- parser or embedding policy migration
- dry-run mode

### Vault Source Boundary

Incremental indexing must not replace Vault source registration.

Vault Graph may cache `raw_sha256`, source-page metadata, registry status, duplicate signals, and stale-file signals only as read-only projections derived from Vault. These cached values help decide what to re-index; they are not a second source registry and must not become durable knowledge.

Vault Graph must not create, edit, rename, delete, merge, redirect, deprecate, or publish Vault source pages or wiki pages during indexing. It must not write to `raw/`, `wiki/`, `docs/`, or `scratch/` as part of scan, parse, normalize, chunk, extraction, or index-update work.

Source registration, source drift handling, slug collision handling, durable duplicate review, wiki index mutation, wiki log mutation, semantic draft publication, and release-gate validation remain owned by Vault's existing `tools/wiki` workflow.

If indexing detects an unregistered source, source drift, deleted source, possible duplicate, or extraction insight that should become durable, Vault Graph must report it as a warning, context-pack item, or explicit command suggestion. The durable follow-up must flow through Vault's normal source capture, semantic draft, validation, review, and Git history path.

## 11. Read-Only Boundary

The project must enforce read-only behavior at multiple levels:

- CLI defaults to read-only mode.
- File operations are restricted to configured Vault Graph state directories.
- Tests assert that indexing does not mutate Vault files.
- MCP tools that return context do not write to Vault.
- Any future "capture back to Vault" feature must produce an explicit draft artifact or command suggestion, not silently edit Vault.

Non-goals for MVP:

- automatic wiki publication
- automatic raw source mutation
- automatic contradiction resolution
- autonomous truth arbitration

## 12. MCP Server

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

## 13. MCP Resources

Initial resource URIs:

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

Resource responses must include evidence metadata where relevant.

## 14. MCP Tools

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

Tool responses must separate:

- answer
- evidence
- inferred links
- warnings
- suggested durable follow-up

## 15. MCP Prompts

Initial prompts:

- `generate_codex_brief`
- `prepare_implementation_context`
- `review_architecture_decision`
- `summarize_feature_history`
- `analyze_project_risk`
- `prepare_wiki_update_context`
- `trace_decision_history`

Prompts should instruct agents to treat Vault Graph output as working context and to publish durable knowledge only through Vault's validation workflow.

## 16. CLI

Initial CLI:

```bash
vg init --vault /path/to/vault
vg index
vg index --full
vg index --dry-run
vg watch
vg status
vg ask "왜 GraphRAG를 도입했지?"
vg related GraphRAG
vg context "GraphRAG MVP 구현"
vg decision-trace GraphRAG
vg serve --mcp
vg serve --http
```

CLI commands should be explicit about which Vault path and which index state path they use.

## 17. Context Pack Contract

A context pack is a structured JSON or Markdown artifact generated from Vault Graph retrieval.

Minimum JSON shape:

```json
{
  "goal": "Implement GraphRAG MVP",
  "scope": ["wiki", "docs"],
  "vault_revision": "git-sha-or-file-snapshot-id",
  "index_revision": "index-revision-id",
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

## 18. Roadmap

### Phase 1: Vault Reader And Metadata Index

- Vault path configuration
- Markdown and frontmatter parser
- source/page/document normalization
- SQLite metadata index
- read-only boundary tests

### Phase 2: Vector Search And Hybrid Retrieval

- chunking policy
- local embedding integration
- Chroma vector store
- vector search
- hybrid keyword/vector retrieval
- evidence-first answer format

### Phase 3: Entity And Relationship Graph

- entity extraction
- relationship extraction
- NetworkX graph projection
- graph traversal retrieval
- decision trace prototype

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

### Phase 7: Optional UI

- Ask Project
- Decision Explorer
- Agent Workspace
- Timeline View

## 19. Success Criteria

Vault Graph is successful when:

- A user can point it at a Vault and build an index without mutating Vault.
- An agent can request a context pack for a concrete task instead of reading the whole Vault.
- Decision traces include evidence and distinguish stated facts from inferred links.
- All indexes can be deleted and rebuilt from Vault.
- Local-first operation works without internet access.
- Retrieval output never bypasses Vault's durable publication workflow.

## 20. Final Vision

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
