# Phase 3C Graph Projection And Retrieval Design

Status: Draft for implementation planning

Date: 2026-06-11

Scope: Phase 3C only

## 1. Purpose

Phase 3C makes the Phase 3 graph useful to humans and agents without turning it
into a second source of truth.

The deliverable is a bounded graph retrieval layer over the Phase 3A
`GraphStore` and Phase 3B indexed graph records:

- `vg related TARGET`
- `vg decision-trace TOPIC`
- optional `vg search --include-graph`
- bounded runtime `GraphProjection` for traversal and ranking

This slice keeps the product evidence-first:

- graph records remain derived Vault Graph state
- user-visible evidence resolves through `MetadataStore`
- plain `vg search "query"` remains keyword/vector search unless graph is
  explicitly requested
- graph projection state is disposable runtime state, not durable authority

## 2. Value Alignment

| Vault Graph value | Phase 3C design rule |
| --- | --- |
| Vault is the source of truth | Graph commands read Vault Graph projections only and never mutate Vault files. |
| Derived data is rebuildable | `GraphProjection` is built from `GraphStore` rows and can be discarded at any time. |
| Evidence over fluency | Normal graph outputs resolve evidence through `MetadataStore`. |
| Local first | The default projection adapter is local `rustworkx`; no hosted graph service or LLM is required. |
| Simplicity before scale | Phase 3C builds bounded per-request projections and defers persistent projection cache writes. |
| Multi-vault correctness | Multi-Vault and cross-Vault traversal are explicit and preserve Vault IDs. |
| Changeability | CLI, search, and future MCP/HTTP adapters call app services, not SQLite or rustworkx directly. |

## 3. Scope

### 3.1 In Scope

Phase 3C implements:

- read-only graph target resolution
- graph neighborhood lookup through `GraphStore`
- bounded runtime `GraphProjection`
- `rustworkx` projection adapter
- graph evidence resolution through `MetadataStore`
- `GraphRetrievalService`
- `vg related TARGET`
- `vg decision-trace TOPIC` prototype
- optional graph signals for `vg search --include-graph`
- graph-specific warnings, recovery hints, and JSON output fields
- tests for read-only behavior, stale state, missing evidence, ambiguous
  targets, multi-vault identity, and opt-in search behavior

### 3.2 Out Of Scope

Phase 3C must not implement:

- `vg ask`
- answer generation or LLM synthesis
- context-pack generation
- MCP serving
- HTTP serving
- Neo4j
- graph node embeddings or relationship embeddings
- LLM-assisted extraction
- cross-Vault entity merging
- projection-cache writes from read-only graph commands
- automatic indexing from graph commands or search
- Vault file mutation

## 4. Core Design Choice

Phase 3C uses read-only, bounded graph retrieval.

The graph layer is valuable when it explains why items are connected. It is
harmful when it silently expands search with stale, ambiguous, or unsupported
relationships. Therefore:

- graph retrieval is opt-in
- graph commands run only over existing indexed graph state
- graph traversal is bounded by depth, candidate count, and relationship count
- graph output includes relationship status and evidence
- unresolved evidence drops a normal result and creates a warning
- ambiguous targets are not guessed

The first implementation should build projections per request. A projection
cache interface may exist later, but Phase 3C read paths must not write
projection-cache files. This keeps graph retrieval read-only and avoids adding a
cache invalidation system before there is measured need.

## 5. Package Layout

Use stable domain names, not roadmap labels.

```text
src/vault_graph/
  graph/
    graph_query.py
  projection/
    __init__.py
    graph_projection.py
    rustworkx_projection.py
  retrieval/
    graph_retrieval.py
    graph_candidates.py
  app/
    graph_retrieval_service.py
  cli/
    main.py

tests/
  test_graph_query_contract.py
  test_graph_projection.py
  test_graph_retrieval_service.py
  test_cli_related.py
  test_cli_decision_trace.py
  test_search_include_graph.py
  test_graph_retrieval_read_only_boundary.py
  test_multi_vault_graph_retrieval.py
```

Responsibilities:

- `graph_query.py` owns read-only query request and row types that extend
  `GraphStore`.
- `projection/graph_projection.py` owns the projection protocol and projection
  result types.
- `projection/rustworkx_projection.py` owns the local adapter implementation.
- `retrieval/graph_candidates.py` adapts graph results into existing
  `RetrievalSignal(kind="graph")` candidates for opt-in search.
- `retrieval/graph_retrieval.py` owns related-item and decision-trace response
  types.
- `app/graph_retrieval_service.py` is the deep module that CLI, future MCP, and
  future HTTP adapters call.
- CLI renders service responses only.

Avoid names such as `phase3c.py`, `graph_utils.py`, `graph_manager.py`,
`rustworkx_store.py`, or `decision_ai.py`.

## 6. Architecture

```text
CLI
  -> CatalogService resolves requested QueryScope
  -> GraphRetrievalService
       -> actual_query_scopes(...)
       -> GraphReadinessService.check(...)
       -> GraphStore graph target and neighborhood reads
       -> GraphProjection bounded traversal/ranking
       -> MetadataStore.resolve_chunk_evidence(...)
       -> related / decision trace / graph search response
```

Rules:

- CLI must not import `SQLiteGraphStore` row helpers or `rustworkx`.
- `GraphRetrievalService` must not mutate graph, metadata, vector, keyword,
  model-cache, projection-cache, or Vault files.
- `GraphProjection` must not read SQLite directly.
- `GraphProjection` receives typed graph rows from `GraphStore`.
- Search keeps `RetrievalService` as the final owner of candidate fusion and
  final evidence chunk ranking.

## 7. Data Flow

### 7.1 `vg related TARGET`

```text
vg related TARGET
  -> resolve selected QueryScope
  -> expand to per-Vault actual scopes
  -> check graph readiness
  -> keep only fresh graph scopes
  -> resolve TARGET to one active graph entity
  -> if no unique target: return warnings and target candidates
  -> read active relationships around target from GraphStore
  -> resolve relationship evidence through MetadataStore
  -> drop unsupported relationship edges with warnings
  -> build bounded GraphProjection
  -> rank related entities and paths
  -> attach supplemental target entity evidence through MetadataStore
  -> render related items, paths, evidence, warnings, and revisions
```

Default behavior:

- scope: active Vault only
- depth: `1`
- max depth in Phase 3C: `2`
- direction: `both`
- limit: `10`
- relationship status filter: `stated`, `inferred`, `contested`
- deprecated relationships are omitted unless explicitly requested later

CLI shape:

```text
vg related TARGET
vg related --vault-id main TARGET
vg related --all-vaults TARGET
vg related --all-vaults --include-cross-vault TARGET
vg related --depth 2 --relationship-type depends_on TARGET
vg related --format json TARGET
```

### 7.2 `vg decision-trace TOPIC`

```text
vg decision-trace TOPIC
  -> resolve selected QueryScope
  -> check graph readiness
  -> keep only fresh graph scopes
  -> prefer Decision entities matching TOPIC
  -> if no Decision entity: fall back to Concept or Document with warning
  -> expand evidence-valid decision relationships with bounded projection
  -> group trace steps by relationship type and status
  -> resolve evidence through MetadataStore
  -> render decision, context, alternatives/tradeoff links when present,
     related evidence, warnings, and revisions
```

The Phase 3C decision trace is a trace, not an answer. It must not synthesize a
final recommendation. It may label sections such as "decision", "supports",
"depends on", "implements", "supersedes", "blocks", and "mentions" when those
relationships exist in the graph.

Relationship type priority:

1. `supersedes`
2. `depends_on`
3. `blocks`
4. `implements`
5. `related_to`
6. `mentions`
7. other relationship types in deterministic lexical order

If the target is not a durable decision entity, the response must include
`topic_not_durable_decision` and clearly mark the trace as a topic trace.

### 7.3 `vg search --include-graph`

```text
vg search "query" --include-graph
  -> normal keyword/vector search readiness
  -> graph readiness check
  -> keyword/vector candidates
  -> graph candidate provider resolves query as a graph target
  -> bounded graph expansion produces evidence-validated graph candidates
  -> RetrievalService fuses keyword, vector, and graph signals
  -> MetadataStore evidence resolution
  -> evidence chunk results plus graph warnings
```

Rules:

- `vg search "query"` without `--include-graph` must not read graph state.
- Graph unavailability must not make opt-in search fail if keyword search is
  available. It returns keyword/vector results with `graph_unavailable` or
  `graph_stale` warnings.
- Graph candidates are still evidence-chunk candidates. Entity and relationship
  rows are not final search result identities.
- Graph candidates must use `RetrievalSignal(kind="graph")`.
- Graph signal explanations must include the seed entity and relationship that
  produced the signal.
- Graph candidate fusion must not hide direct keyword/vector evidence. The
  default graph signal weight should be lower than or equal to direct evidence
  signal weights.

## 8. GraphStore Read Contract Extensions

Phase 3A `GraphStore` already owns persistence. Phase 3C adds read-only graph
query methods so services do not depend on SQLite internals.

```python
@dataclass(frozen=True)
class GraphEntityQuery:
    text: str
    actual_scopes: tuple[QueryScope, ...]
    types: tuple[str, ...] = ()
    limit: int = 20
    scan_limit: int = 5000

@dataclass(frozen=True)
class GraphEntityMatch:
    entity: EntityRecord
    match_kind: Literal["entity_id", "canonical_path", "normalized_name", "alias", "contains"]
    match_rank: int
    matched_value: str

@dataclass(frozen=True)
class GraphEntityQueryResult:
    matches: tuple[GraphEntityMatch, ...]
    truncated: bool
    affected_vault_ids: tuple[str, ...]

@dataclass(frozen=True)
class GraphRelationshipQuery:
    seeds: tuple[GraphEntityIdentity, ...]
    actual_scopes: tuple[QueryScope, ...]
    direction: Literal["out", "in", "both"] = "both"
    relationship_types: tuple[str, ...] = ()
    statuses: tuple[str, ...] = ("stated", "inferred", "contested")
    include_cross_vault: bool = False
    limit: int = 200

@dataclass(frozen=True)
class GraphRelationshipQueryResult:
    relationships: tuple[RelationshipRecord, ...]
    truncated: bool
    omitted_cross_vault_count: int
    affected_vault_ids: tuple[str, ...]

class GraphStore(Protocol):
    def find_entities(self, query: GraphEntityQuery) -> GraphEntityQueryResult: ...
    def relationships_for_entities(
        self,
        query: GraphRelationshipQuery,
    ) -> GraphRelationshipQueryResult: ...
```

`find_entities` rules:

- search only active entities
- match normalized name, aliases, canonical path, and entity ID
- return match metadata so target resolution can distinguish exact matches,
  suggestions, and equal-best ambiguity without duplicating store rules
- use indexed exact probes where indexes exist before bounded fallback scans
- keep canonical-path, alias, and contained-text fallback scans under
  `scan_limit` until a schema-versioned lookup table or index is added later
- return truncation metadata if fallback scans reach `scan_limit`
- keep results scoped by actual scopes
- sort exact normalized-name matches before alias/path/substring matches
- preserve Vault identity in every result
- never merge entities with the same name across Vaults

`relationships_for_entities` rules:

- return direct relationships whose source or target is connected to the seed
  frontier
- apply status, type, direction, scope, and cross-Vault filters in the store
- omit deprecated relationships by default
- include evidence refs on returned relationships
- return omission metadata when cross-Vault relationships are filtered out
- respect `limit` and return deterministic ordering
- never create graph state or projection-cache state

`GraphStore` must not own multi-hop traversal. `GraphRetrievalService` expands
frontiers up to the requested depth by making bounded direct-neighborhood reads,
then `GraphProjection` computes and ranks paths over the typed rows. This keeps
persistence, orchestration, and graph algorithms separate.

SQLite implementation notes:

- existing indexes on entity name, relationship source, relationship target,
  relationship type/status, and evidence owner are sufficient for direct
  neighborhood lookup
- Phase 3C v1 may scan the bounded scoped entity result set for alias and
  canonical-path matching because aliases currently live in `aliases_json` and
  `canonical_path` has no dedicated index
- if alias/path lookup becomes slow, add a schema-versioned graph store change
  with either a canonical-path index or normalized alias table and health checks
- read-only connections must use SQLite read-only mode

## 9. Target Resolution

`GraphTargetResolver` is part of `GraphRetrievalService`.

Inputs:

- raw target text
- actual scopes
- optional entity type preference
- output limit for candidate suggestions

Resolution order:

1. exact `entity_id` within selected Vaults
2. exact canonical path
3. exact normalized name
4. alias match
5. contained normalized text match as suggestions only

Decision-trace type priority:

1. `Decision`
2. `WikiPage`
3. `Document`
4. `Concept`
5. any other type

Rules:

- zero matches returns a successful response with `target_not_found` warning
  and no normal graph paths
- multiple equal-best matches returns `ambiguous_graph_target` with candidate
  suggestions and no traversal
- traversal may run only for a unique exact `entity_id`, canonical path,
  normalized name, or alias match
- contained text matches are suggestions only and never trigger traversal in
  Phase 3C
- cross-Vault same-name matches stay separate target candidates
- all-vault same-name matches are ambiguity, not automatic multi-seed traversal
- the resolver must not call keyword, vector, or LLM search to invent a target

## 10. GraphProjection Contract

`GraphProjection` owns runtime graph algorithms over a bounded working graph.

```python
GRAPH_PROJECTION_VERSION = "graph-projection-v1"

@dataclass(frozen=True)
class GraphProjectionNode:
    vault_id: str
    entity_id: str
    type: str
    name: str
    normalized_name: str

@dataclass(frozen=True)
class GraphProjectionEdge:
    source_vault_id: str
    source_entity_id: str
    target_vault_id: str
    target_entity_id: str
    relationship_id: str
    relationship_type: str
    status: str
    confidence: float
    evidence_ref_ids: tuple[str, ...]
    graph_index_revision: str

@dataclass(frozen=True)
class GraphPath:
    seed: GraphProjectionNode
    target: GraphProjectionNode
    edges: tuple[GraphProjectionEdge, ...]
    depth: int
    score: float
    explanation: str

@dataclass(frozen=True)
class GraphProjectionInput:
    seeds: tuple[GraphProjectionNode, ...]
    nodes: tuple[GraphProjectionNode, ...]
    relationships: tuple[GraphProjectionEdge, ...]
    actual_scope_keys: tuple[str, ...]
    source_graph_revisions: tuple[str, ...]
    max_depth: int
    direction: Literal["out", "in", "both"]
    relationship_types: tuple[str, ...]
    statuses: tuple[str, ...]
    include_cross_vault: bool
    limit: int
    edge_limit: int

@dataclass(frozen=True)
class GraphProjectionResult:
    projection_build_id: str
    graph_projection_version: str
    source_graph_revisions: tuple[str, ...]
    node_count: int
    edge_count: int
    truncated: bool
    paths: tuple[GraphPath, ...]

class GraphProjection(Protocol):
    def project(self, request: GraphProjectionInput) -> GraphProjectionResult: ...
```

Projection build input:

- resolved seed entities
- resolved endpoint entity nodes for every relationship included in the working
  graph
- relationship rows returned by `GraphStore`
- graph revisions for selected actual scopes
- projection version
- query parameters
- limits and truncation policy

Projection build output:

- `projection_build_id`
- `graph_projection_version`
- source graph revisions
- node count
- edge count
- truncation flags
- paths

`projection_build_id` is a deterministic hash of:

- `GRAPH_PROJECTION_VERSION`
- actual scope keys
- seed identities
- working node identities
- graph revision identifiers
- depth, direction, relationship type filters, and cross-Vault flag

It is a runtime correlation ID and future cache key. It is not durable
knowledge.

## 11. Bounded Traversal And Ranking

Phase 3C must stay bounded by default.

Limits:

- default depth: `1`
- maximum depth: `2`
- default result limit: `10`
- default target candidate limit: `20`
- default relationship read limit: `200`
- default projection edge limit: `500`

If a limit truncates traversal, the response includes
`graph_projection_truncated`.

Ranking score:

```text
score =
  relationship_confidence
  * status_weight
  * depth_weight
```

Default weights:

- `stated`: `1.0`
- `inferred`: `0.75`
- `contested`: `0.45`
- `deprecated`: `0.0` unless explicitly requested later
- depth 1: `1.0`
- depth 2: `0.6`

Every relationship edge must have at least one resolved relationship evidence
chunk before it enters `GraphProjection`. Missing relationship evidence drops
the edge before ranking; it is not represented as a lower score. Target entity
evidence may supplement display, but it must not save an unsupported
relationship path.

Tie-breakers:

1. higher score
2. lower depth
3. relationship type priority
4. target Vault ID
5. target entity normalized name
6. relationship ID

Phase 3C must not use hidden LLM confidence or global PageRank-style ranking.
Those can be added later only behind explicit versioned retrieval policy tests.

## 12. Response Models

### 12.1 Shared Graph Warning

```python
@dataclass(frozen=True)
class GraphRetrievalWarning:
    code: str
    message: str
    severity: Literal["info", "warning", "error"]
    affected_vault_ids: tuple[str, ...]
    scope_key: str | None = None
    entity_id: str | None = None
    relationship_id: str | None = None
    evidence_ref_id: str | None = None

@dataclass(frozen=True)
class GraphRetrievalRevision:
    kind: Literal["metadata", "graph", "projection"]
    revision: str
    scope_key: str
    vault_id: str | None = None
```

### 12.2 Related Response

```python
@dataclass(frozen=True)
class RelatedRequest:
    target: str
    requested_scope: QueryScope
    actual_scopes: tuple[QueryScope, ...]
    depth: int
    direction: Literal["out", "in", "both"]
    relationship_types: tuple[str, ...]
    include_cross_vault: bool
    limit: int
    output_format: Literal["text", "json"]

@dataclass(frozen=True)
class RelatedItem:
    rank: int
    entity: EntityRecord
    relationship_path: tuple[RelationshipRecord, ...]
    evidence: tuple[EvidenceReference, ...]
    score: float
    explanation: str

@dataclass(frozen=True)
class RelatedResponse:
    target: str
    resolved_target: EntityRecord | None
    target_candidates: tuple[EntityRecord, ...]
    requested_scope: QueryScope
    actual_scopes: tuple[QueryScope, ...]
    projection_build_id: str | None
    graph_projection_version: str
    result_count: int
    items: tuple[RelatedItem, ...]
    warnings: tuple[GraphRetrievalWarning, ...]
    store_revisions: tuple[GraphRetrievalRevision, ...]
    generated_at: str
```

### 12.3 Decision Trace Response

```python
@dataclass(frozen=True)
class DecisionTraceStep:
    rank: int
    role: str
    entity: EntityRecord
    relationship_path: tuple[RelationshipRecord, ...]
    evidence: tuple[EvidenceReference, ...]
    relationship_status: str
    explanation: str

@dataclass(frozen=True)
class DecisionTraceResponse:
    topic: str
    trace_kind: Literal["decision", "topic"]
    resolved_target: EntityRecord | None
    target_candidates: tuple[EntityRecord, ...]
    requested_scope: QueryScope
    actual_scopes: tuple[QueryScope, ...]
    projection_build_id: str | None
    graph_projection_version: str
    steps: tuple[DecisionTraceStep, ...]
    warnings: tuple[GraphRetrievalWarning, ...]
    store_revisions: tuple[GraphRetrievalRevision, ...]
    generated_at: str
```

Rules:

- normal items and steps require every relationship edge in the path to have at
  least one resolved relationship `EvidenceReference`
- target candidates may be returned without evidence only as suggestions, not
  as normal related results
- output must include store revisions for metadata and graph state when results
  are returned
- JSON output uses the same field names as dataclasses

## 13. Evidence Resolution

Graph evidence resolution must use `MetadataStore.resolve_chunk_evidence(...)`.

For each relationship path:

1. collect relationship evidence refs for every edge
2. resolve each edge's relationship refs to metadata evidence
3. drop the whole path if any edge has zero resolved relationship evidence
4. emit `graph_evidence_missing` for each dropped edge or path
5. collect target entity evidence refs only after the path evidence gate passes
6. resolve target entity evidence as supplemental display evidence
7. run final scoring/reranking only over evidence-valid paths

Rules:

- stored `GraphEvidenceRef.path`, `section`, `anchor`, and `excerpt` are
  rendering hints only
- resolved `EvidenceReference` supplies the user-visible path, section, anchor,
  content hash, raw SHA-256, metadata index revision, and Vault revision
- evidence from different Vault IDs must remain separate in output
- duplicate evidence chunks are deduped by `(vault_id, document_id, chunk_id)`
  in stable order
- stored entity evidence can supplement the displayed target, but it cannot
  substitute for missing relationship evidence

## 14. Search Integration

Phase 3C extends `RetrievalService.search(...)` with an explicit graph option.
Before graph signals are added, Phase 3C should expose the retrieval candidate
seam that is currently private inside `RetrievalService`.

Recommended request change:

```python
@dataclass(frozen=True)
class SearchRequest:
    ...
    include_graph: bool = False
    include_cross_vault: bool = False

@dataclass(frozen=True)
class RetrievalCandidate:
    vault_id: str
    document_id: str
    chunk_id: str
    signals: tuple[RetrievalSignal, ...]

@dataclass(frozen=True)
class GraphCandidateResult:
    candidates: tuple[RetrievalCandidate, ...]
    warnings: tuple[SearchWarning, ...]
    store_revisions: tuple[SearchStoreRevision, ...]
```

Recommended service dependency:

```python
class GraphCandidateProvider(Protocol):
    def candidates(
        self,
        *,
        query_text: str,
        requested_scope: QueryScope,
        actual_scopes: tuple[QueryScope, ...],
        limit: int,
        include_cross_vault: bool,
    ) -> GraphCandidateResult: ...
```

`GraphCandidateResult` contains:

- graph `RetrievalCandidate` rows keyed by `(vault_id, document_id, chunk_id)`
- candidate signals using the existing public `RetrievalSignal` shape
- graph warnings already shaped as `SearchWarning`
- graph store revisions already shaped as `SearchStoreRevision`

Candidate rules:

- graph candidates come from target resolution plus bounded graph expansion
- graph candidates resolve to evidence chunks before becoming normal results
- graph candidates never bypass keyword/vector result validation
- keyword, vector, and graph adapters all feed `RetrievalCandidate` values into
  one fusion path
- graph-specific signal explanations must be preserved; `RetrievalService` must
  not replace them with generic text
- graph warnings are top-level `SearchWarning` records
- graph store revisions join `SearchResponse.store_revisions`

Fusion rules:

- keep reciprocal-rank-style fusion owned by `RetrievalService`
- add graph as another signal kind
- default graph weight must not exceed direct keyword/vector weights; a safe
  initial value is `0.75` when keyword and vector are `1.0`
- if graph is stale or unavailable, omit graph candidates and return normal
  keyword/vector results with warnings

CLI:

```text
vg search "query" --include-graph
vg search "query" --include-graph --include-cross-vault --all-vaults
```

`--include-cross-vault` is valid only with `--include-graph` and a multi-vault
requested scope such as `--all-vaults`. Otherwise CLI returns
`include_cross_vault_requires_multi_vault_graph_scope`.

## 15. Error And Degradation Policy

Fatal for graph commands:

- invalid Vault scope
- graph store schema incompatible
- graph store unavailable for graph-specific command
- metadata store unavailable for graph-specific command
- unsupported depth
- unsupported output format

Non-fatal warnings for graph commands:

- `target_not_found`
- `ambiguous_graph_target`
- `topic_not_durable_decision`
- `graph_stale`
- `graph_empty`
- `graph_unavailable`
- `graph_target_scan_truncated`
- `graph_relationship_read_truncated`
- `graph_projection_truncated`
- `cross_vault_relationship_omitted`
- `graph_evidence_missing`
- `deprecated_relationship_omitted`

Opt-in graph search behavior:

- keyword index missing remains fatal because search cannot run
- graph missing, empty, stale, incompatible, or unavailable is non-fatal when
  keyword search can run
- graph query failure returns keyword/vector results with `graph_query_failed`
- no graph target returns keyword/vector results with `graph_target_not_found`
- ambiguous graph target returns keyword/vector results with
  `ambiguous_graph_target`

All warnings must include affected Vault IDs. Warnings tied to a scope should
include `scope_key`.

## 16. Multi-Vault Policy

Default:

- active Vault only
- no cross-Vault traversal

`--vault-id ID`:

- exactly one registered Vault
- no cross-Vault traversal
- `--include-cross-vault` is invalid and returns
  `include_cross_vault_requires_multi_vault_graph_scope`

`--all-vaults`:

- expands to all enabled Vault IDs
- queries each per-Vault actual scope
- does not traverse relationships that cross Vault IDs unless
  `--include-cross-vault` is set
- same-name or same-alias target matches across Vaults are ambiguity, not
  automatic multi-seed traversal

`--include-cross-vault`:

- permits relationships where source, target, or evidence Vault IDs differ
- is accepted only for explicit graph retrieval with a multi-vault requested
  scope
- still does not merge same-name entities
- relationship output must show source, target, and evidence Vault IDs
- if a cross-Vault relationship points to a Vault outside the selected scope,
  omit it with `cross_vault_relationship_omitted`

Identity rules:

- target candidates are keyed by `(vault_id, entity_id)`
- relationships are keyed by `(source_vault_id, relationship_id)`
- evidence is keyed by `(evidence_vault_id, document_id, chunk_id)`
- projection nodes are keyed by `(vault_id, entity_id)`

## 17. CLI Rendering

Text output for `vg related`:

```text
target: GraphRAG
resolved_target: [main] GraphRAG (Concept)
actual_scopes: main:raw,wiki,docs,scratch/reports
projection: graph-projection-v1 <projection_build_id>
results: 3
1. [main] Hybrid Retrieval
   relationship: related_to stated depth=1 score=0.91
   path: wiki/retrieval.md#Hybrid Retrieval
   evidence: wiki/graphrag.md#Related
   signals: graph:1
warning: graph_stale [main] run `vg index`
```

Text output for `vg decision-trace`:

```text
topic: GraphRAG
trace_kind: decision
resolved_target: [main] Use GraphRAG For Retrieval (Decision)
projection: graph-projection-v1 <projection_build_id>
steps: 4
1. decision [main] Use GraphRAG For Retrieval
   evidence: wiki/decisions/graphrag.md#Decision
2. depends_on [main] Evidence-First Hybrid Retrieval
   status: stated
   evidence: wiki/decisions/graphrag.md#Context
```

JSON output must include:

- request fields
- resolved target or target candidates
- projection build metadata
- item or step rows
- resolved evidence
- relationship status
- warnings
- store revisions

## 18. Readiness

Graph commands use the Phase 3A `GraphReadinessService` contract opened through
read-only `MetadataStore` and `GraphStore` interfaces. The current local
implementation is `ReadOnlyGraphReadiness`.

Readiness behavior:

- `missing`: graph-specific commands return recovery guidance; opt-in search
  degrades to keyword/vector
- `empty`: graph-specific commands return zero normal results plus recovery
  guidance; opt-in search degrades to keyword/vector with an affected-scope
  warning
- `stale`: graph-specific commands return no normal results for stale scopes by
  default; opt-in search may include graph only for scopes whose stale count is
  zero
- `incompatible`: graph-specific commands fail; opt-in search omits graph
- `unavailable`: graph-specific commands fail; opt-in search omits graph
- `fresh`: graph can be used

Per-scope readiness matters. A multi-vault request may use fresh graph state for
one Vault and warn or omit graph state for another Vault. If no selected scope
is fresh, graph-specific commands return a successful empty response for
`missing`, `empty`, or `stale` and a fatal error for `incompatible` or
`unavailable`.

## 19. Projection Cache Policy

Phase 3C implements the in-memory, no-cache subset of `GraphProjection`.
Persistent projection cache protocol and tests are deferred.

Rules:

- graph commands build in-memory projections per request
- read-only commands must not create `data/projection_cache/`
- `projection_build_id` is deterministic and can become a future cache key
- `GraphIndexer` projection invalidation keys remain plan metadata until a
  later cache implementation exists
- any future persistent projection cache must live under the configured state
  path, never inside registered Vault roots
- cache entries must be disposable and rebuildable from `GraphStore`

This keeps Phase 3C simple while preserving the future scale-up path.

## 20. Testing Requirements

Contract tests:

- `GraphStore.find_entities` respects scope, status, type, alias, path, and
  deterministic ordering
- `GraphStore.find_entities` returns match metadata for exact, alias, path, and
  suggestion-only contained matches
- `GraphStore.relationships_for_entities` returns direct relationships and
  respects direction, type, status, cross-Vault, and limit filters
- `GraphStore.relationships_for_entities` reports cross-Vault omission metadata
- `GraphRetrievalService` performs bounded depth expansion without pushing
  multi-hop traversal into `GraphStore`
- `GraphProjection.project` returns deterministic bounded paths, build metadata,
  and truncation flags
- graph response models require resolved relationship evidence for every edge in
  normal results

CLI tests:

- `vg related TARGET` returns evidence-linked related items
- `vg related` reports ambiguous target candidates without guessing
- `vg related --all-vaults TARGET` reports ambiguity for same-name targets
  across Vaults instead of running automatic multi-seed traversal
- `vg decision-trace TOPIC` prefers `Decision` entities
- `vg decision-trace` falls back to topic trace with warning
- `vg search "query"` does not read graph state by default
- `vg search "query" --include-graph` returns graph signals when graph is fresh
- `--include-cross-vault` requires graph inclusion and a multi-vault graph scope

Read-only tests:

- graph commands do not modify Vault files
- graph commands do not create metadata, vector, graph, model-cache, or
  projection-cache files
- graph search does not auto-index
- projection cache directory is not created by read-only graph commands

Multi-vault tests:

- same entity names in different Vaults remain separate target candidates
- all-vault same-name lookup is ambiguity-only until the user selects a Vault or
  exact entity identity
- cross-Vault relationships are omitted unless explicitly included
- cross-Vault relationship output preserves source, target, and evidence Vault
  IDs
- omitted cross-Vault relationships produce attributed warnings or omission
  metadata
- stale graph state in one Vault does not stale unrelated Vault results

Evidence tests:

- unresolved relationship evidence for any edge drops the whole normal graph path
  and emits warnings
- target entity evidence cannot substitute for missing relationship evidence
- stored graph excerpts are not rendered as authority when metadata evidence is
  missing
- result evidence path, section, anchor, content hash, and revision come from
  `MetadataStore`

Search tests:

- keyword, vector, and graph adapters feed one public `RetrievalCandidate` seam
- graph candidates use `RetrievalSignal(kind="graph")`
- graph-specific signal explanations are preserved in final results
- graph warnings join top-level `SearchResponse.warnings`
- graph store revisions join `SearchResponse.store_revisions`
- graph signal weight does not outrank stronger direct evidence unexpectedly
- graph missing, empty, stale, incompatible, or unavailable degrades to
  keyword/vector results

## 21. Implementation Handoff

Recommended implementation order:

1. Add graph query dataclasses and read-only `GraphStore` result wrappers.
2. Implement SQLite graph read methods with contract tests.
3. Add `projection/` input/result protocol and `RustworkxGraphProjection`.
4. Add graph retrieval response types and evidence resolution helpers.
5. Implement `GraphRetrievalService.related(...)`.
6. Add `vg related` text and JSON output.
7. Implement `GraphRetrievalService.decision_trace(...)`.
8. Add `vg decision-trace` text and JSON output.
9. Add the public `RetrievalCandidate` seam for keyword/vector search.
10. Add `GraphCandidateProvider` and `vg search --include-graph`.
11. Run full read-only, multi-vault, evidence, CLI, and search regression tests.

Completion criteria:

- graph retrieval is useful without LLMs or hosted graph services
- normal graph results always resolve metadata evidence
- no read-only graph command writes any state
- default search output is unchanged without `--include-graph`
- multi-vault identity remains explicit and collision-safe
- future MCP/HTTP adapters can reuse the same app service without direct store
  access
