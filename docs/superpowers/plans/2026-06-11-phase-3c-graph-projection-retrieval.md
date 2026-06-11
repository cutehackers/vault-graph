# Phase 3C Graph Projection And Retrieval Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build Phase 3C so users can run evidence-linked graph retrieval through `vg related`, `vg decision-trace`, and explicit `vg search --include-graph` without mutating Vault or turning graph state into a source of truth.

**Architecture:** Phase 3C is a read-only retrieval layer over Phase 3B graph state. `GraphStore` owns persisted derived graph rows, `GraphProjection` owns bounded in-memory traversal/ranking, `GraphRetrievalService` owns orchestration and evidence resolution, and `RetrievalService` remains the final owner of keyword/vector/graph candidate fusion for search.

**Tech Stack:** Python 3.12, dataclasses, Protocol interfaces, Typer CLI, SQLite read-only mode, rustworkx `PyDiGraph`, pytest, ruff, mypy.

---

## Source Documents

Read these before implementation:

- `AGENTS.md`
- `docs/SPEC.md`
- `docs/DESIGN.md`
- `docs/FEATURES.md`
- `docs/DECISIONS.md`
- `docs/CONVENTIONS.md`
- `docs/superpowers/specs/phase-3/README.md`
- `docs/superpowers/specs/phase-3/CONTEXT.md`
- `docs/superpowers/specs/phase-3/2026-06-10-phase-3-overview-design.md`
- `docs/superpowers/specs/phase-3/2026-06-10-phase-3a-graphstore-contract-readiness-design.md`
- `docs/superpowers/specs/phase-3/2026-06-10-phase-3b-local-entity-relationship-indexing-design.md`
- `docs/superpowers/specs/phase-3/2026-06-10-phase-3c-graph-projection-retrieval-design.md`

## Scope Guardrails

Phase 3C implements only:

- read-only graph target resolution
- direct graph neighborhood lookup through `GraphStore`
- bounded in-memory `GraphProjection`
- local `RustworkxGraphProjection`
- graph evidence resolution through `MetadataStore.resolve_chunk_evidence(...)`
- `GraphRetrievalService.related(...)`
- `GraphRetrievalService.decision_trace(...)`
- `vg related TARGET`
- `vg decision-trace TOPIC`
- `vg search --include-graph`
- structured graph warnings, graph revisions, and JSON/text output
- read-only, evidence, multi-vault, stale-state, ambiguity, and opt-in search tests

Phase 3C must not implement:

- `vg ask`
- answer generation
- LLM synthesis
- context-pack generation
- MCP serving
- HTTP serving
- Neo4j
- graph node embeddings or relationship embeddings
- LLM-assisted extraction
- cross-Vault entity merging
- projection-cache writes from graph commands or graph search
- automatic indexing from graph commands or graph search
- Vault file mutation

Release-ready Phase 3C means a user can run:

```bash
vg init --vault /path/to/vault
vg index
vg related GraphRAG
vg decision-trace GraphRAG
vg search "GraphRAG"
vg search "GraphRAG" --include-graph
```

and get deterministic evidence-linked graph results or clear recovery warnings, while plain `vg search "GraphRAG"` remains unchanged keyword/vector search.

## Directory And File Structure

Create:

- `src/vault_graph/graph/graph_query.py`: graph entity and relationship read query contracts used by `GraphStore`.
- `src/vault_graph/projection/__init__.py`: public projection package exports.
- `src/vault_graph/projection/graph_projection.py`: `GraphProjection` Protocol, projection DTOs, scoring constants, and validation.
- `src/vault_graph/projection/rustworkx_projection.py`: local `rustworkx.PyDiGraph` projection adapter.
- `src/vault_graph/retrieval/retrieval_candidate.py`: public candidate seam shared by keyword, vector, and graph retrieval.
- `src/vault_graph/retrieval/graph_retrieval.py`: related and decision-trace request/response/warning DTOs.
- `src/vault_graph/retrieval/graph_candidates.py`: graph candidate result DTO, `GraphCandidateProvider` Protocol, and `GraphSearchCandidateProvider`.
- `src/vault_graph/app/graph_retrieval_service.py`: deep app service for graph target resolution, traversal orchestration, readiness handling, and evidence resolution.
- `tests/test_graph_query_contract.py`
- `tests/test_graph_projection.py`
- `tests/test_graph_retrieval_contract.py`
- `tests/test_graph_retrieval_service.py`
- `tests/test_cli_related.py`
- `tests/test_cli_decision_trace.py`
- `tests/test_search_include_graph.py`
- `tests/test_graph_retrieval_read_only_boundary.py`
- `tests/test_multi_vault_graph_retrieval.py`

Modify:

- `pyproject.toml`: add `rustworkx` runtime dependency.
- `uv.lock`: update with `uv lock` after dependency change.
- `src/vault_graph/storage/interfaces/graph_store.py`: add `find_entities(...)` and `relationships_for_entities(...)`.
- `src/vault_graph/storage/interfaces/__init__.py`: export graph query contracts if graph interface exports are already used there.
- `src/vault_graph/storage/local/sqlite_graph_store.py`: implement read-only graph query methods.
- `tests/fakes/in_memory_graph_store.py`: mirror the new graph query methods for service and contract tests.
- `src/vault_graph/retrieval/retrieval_service.py`: refactor private keyword/vector candidate fusion into public `RetrievalCandidate` input, add optional graph provider, and preserve default search behavior.
- `src/vault_graph/retrieval/retrieval_result.py`: no structural change expected; keep `RetrievalSignalKind = Literal["keyword", "vector", "graph"]`.
- `src/vault_graph/retrieval/search_response.py`: add `include_graph` and `include_cross_vault` to `SearchRequest`.
- `src/vault_graph/retrieval/__init__.py`: export new retrieval contracts and graph service-facing DTOs.
- `src/vault_graph/cli/main.py`: add read-only graph retrieval service factory, `related`, `decision-trace`, `search --include-graph`, `search --include-cross-vault`, and renderers.
- `tests/test_graph_store_contract.py`: add reusable contract assertions for query extensions.
- `tests/test_sqlite_graph_store.py`: prove SQLite satisfies query-extension contract and stays read-only.
- `tests/test_retrieval_service_search.py`: update search tests for public candidate seam and graph opt-in dependency.
- `tests/test_cli_search.py`: preserve default no-graph search and add include-graph CLI behavior.
- `tests/test_retrieval_import_boundaries.py`: keep CLI/storage boundaries clean after adding graph retrieval modules.
- `tests/test_package_import.py`: update public package import smoke tests if new exports are added.

Do not modify `docs/DECISIONS.md` unless implementation reveals a new product or technical policy choice that requires user approval. Review-driven corrections to this plan belong in `docs/PATCH_LOG.md`.

## Component And Interface Spec

### Graph Query Contracts

Create `src/vault_graph/graph/graph_query.py`:

```python
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from vault_graph.errors import GraphStoreError
from vault_graph.graph.graph_contracts import EntityRecord, RelationshipRecord
from vault_graph.ingestion.vault_catalog import QueryScope

GraphEntityMatchKind = Literal["entity_id", "canonical_path", "normalized_name", "alias", "contains"]
GraphRelationshipDirection = Literal["out", "in", "both"]
MAX_GRAPH_TARGET_CANDIDATE_LIMIT = 50
DEFAULT_GRAPH_ENTITY_SCAN_LIMIT = 5000
MAX_GRAPH_ENTITY_SCAN_LIMIT = 5000
DEFAULT_GRAPH_RELATIONSHIP_READ_LIMIT = 200
MAX_GRAPH_RELATIONSHIP_READ_LIMIT = 200


@dataclass(frozen=True)
class GraphEntityIdentity:
    vault_id: str
    entity_id: str


@dataclass(frozen=True)
class GraphRelationshipIdentity:
    source_vault_id: str
    relationship_id: str


@dataclass(frozen=True)
class GraphEntityQuery:
    text: str
    actual_scopes: tuple[QueryScope, ...]
    types: tuple[str, ...] = ()
    limit: int = 20
    scan_limit: int = DEFAULT_GRAPH_ENTITY_SCAN_LIMIT

    def __post_init__(self) -> None:
        if not self.text.strip():
            raise GraphStoreError("graph entity query text is required")
        _require_actual_scopes(self.actual_scopes)
        if self.limit <= 0:
            raise GraphStoreError("graph entity query limit must be positive")
        if self.limit > MAX_GRAPH_TARGET_CANDIDATE_LIMIT:
            raise GraphStoreError("graph entity query limit is out of range")
        if self.scan_limit <= 0 or self.scan_limit > MAX_GRAPH_ENTITY_SCAN_LIMIT:
            raise GraphStoreError("graph entity query scan_limit is out of range")


@dataclass(frozen=True)
class GraphEntityMatch:
    entity: EntityRecord
    match_kind: GraphEntityMatchKind
    match_rank: int
    matched_value: str

    def __post_init__(self) -> None:
        if self.match_rank <= 0:
            raise GraphStoreError("graph entity match_rank must be positive")
        if not self.matched_value:
            raise GraphStoreError("graph entity matched_value is required")


@dataclass(frozen=True)
class GraphEntityQueryResult:
    matches: tuple[GraphEntityMatch, ...]
    truncated: bool
    affected_vault_ids: tuple[str, ...]


@dataclass(frozen=True)
class GraphRelationshipQuery:
    seeds: tuple[GraphEntityIdentity, ...]
    actual_scopes: tuple[QueryScope, ...]
    direction: GraphRelationshipDirection = "both"
    relationship_types: tuple[str, ...] = ()
    statuses: tuple[str, ...] = ("stated", "inferred", "contested")
    include_cross_vault: bool = False
    limit: int = DEFAULT_GRAPH_RELATIONSHIP_READ_LIMIT

    def __post_init__(self) -> None:
        if not self.seeds:
            raise GraphStoreError("graph relationship query seeds are required")
        _require_actual_scopes(self.actual_scopes)
        if self.direction not in ("out", "in", "both"):
            raise GraphStoreError("unsupported graph relationship direction")
        if self.limit <= 0:
            raise GraphStoreError("graph relationship query limit must be positive")
        if self.limit > MAX_GRAPH_RELATIONSHIP_READ_LIMIT:
            raise GraphStoreError("graph relationship query limit is out of range")


@dataclass(frozen=True)
class GraphRelationshipQueryResult:
    relationships: tuple[RelationshipRecord, ...]
    truncated: bool
    omitted_cross_vault_count: int
    affected_vault_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.omitted_cross_vault_count < 0:
            raise GraphStoreError("omitted_cross_vault_count must not be negative")
        if not isinstance(self.relationships, tuple):
            raise GraphStoreError("relationships must be an immutable tuple")


def _require_actual_scopes(actual_scopes: tuple[QueryScope, ...]) -> None:
    if not actual_scopes:
        raise GraphStoreError("actual_scopes are required")
    for scope in actual_scopes:
        if len(scope.vault_ids) != 1:
            raise GraphStoreError("GraphStore operations require per-Vault actual scopes")
```

Move the existing `GraphEntityIdentity` and `GraphRelationshipIdentity`
dataclasses out of `src/vault_graph/storage/interfaces/graph_store.py` and into
`graph_query.py`. Then re-export them from `graph_store.py` by importing them
from `graph_query.py`. This preserves existing imports while avoiding a circular
dependency between `graph_query.py` and `graph_store.py`.

Then add to `src/vault_graph/storage/interfaces/graph_store.py`:

```python
from vault_graph.graph.graph_query import (
    GraphEntityIdentity,
    GraphEntityMatch,
    GraphEntityQuery,
    GraphEntityQueryResult,
    GraphRelationshipIdentity,
    GraphRelationshipQuery,
    GraphRelationshipQueryResult,
)


class GraphStore(Protocol):
    ...
    def find_entities(self, query: GraphEntityQuery) -> GraphEntityQueryResult:
        raise NotImplementedError

    def relationships_for_entities(self, query: GraphRelationshipQuery) -> GraphRelationshipQueryResult:
        raise NotImplementedError
```

### Projection Contracts

Create `src/vault_graph/projection/graph_projection.py`:

```python
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol

from vault_graph.errors import GraphStoreError

GRAPH_PROJECTION_VERSION = "graph-projection-v1"
MAX_GRAPH_PROJECTION_DEPTH = 2
DEFAULT_GRAPH_RELATED_DEPTH = 1
DEFAULT_GRAPH_RESULT_LIMIT = 10
MAX_GRAPH_RESULT_LIMIT = 50
DEFAULT_GRAPH_TARGET_LIMIT = 20
DEFAULT_GRAPH_RELATIONSHIP_READ_LIMIT = 200
DEFAULT_GRAPH_PROJECTION_EDGE_LIMIT = 500
MAX_GRAPH_PROJECTION_EDGE_LIMIT = 500

GraphProjectionDirection = Literal["out", "in", "both"]


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
    direction: GraphProjectionDirection
    relationship_types: tuple[str, ...]
    statuses: tuple[str, ...]
    include_cross_vault: bool
    limit: int
    edge_limit: int

    def __post_init__(self) -> None:
        if not self.seeds:
            raise GraphStoreError("graph projection seeds are required")
        if not self.nodes:
            raise GraphStoreError("graph projection nodes are required")
        seed_keys = {(seed.vault_id, seed.entity_id) for seed in self.seeds}
        node_keys = {(node.vault_id, node.entity_id) for node in self.nodes}
        if not seed_keys <= node_keys:
            raise GraphStoreError("graph projection seeds must be present in nodes")
        if self.max_depth <= 0 or self.max_depth > MAX_GRAPH_PROJECTION_DEPTH:
            raise GraphStoreError("unsupported graph projection depth")
        if self.limit <= 0:
            raise GraphStoreError("graph projection limit must be positive")
        if self.limit > MAX_GRAPH_RESULT_LIMIT:
            raise GraphStoreError("graph projection limit is out of range")
        if self.edge_limit <= 0:
            raise GraphStoreError("graph projection edge_limit must be positive")
        if self.edge_limit > MAX_GRAPH_PROJECTION_EDGE_LIMIT:
            raise GraphStoreError("graph projection edge_limit is out of range")


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

Scoring policy:

- Status weights: `stated=1.0`, `inferred=0.75`, `contested=0.45`, `deprecated=0.0`.
- Depth weights: `depth=1 -> 1.0`, `depth=2 -> 0.6`.
- For one-edge paths: `score = edge.confidence * status_weight(edge.status) * depth_weight`.
- For two-edge paths: `score = min(edge.confidence * status_weight(edge.status) for edge in path.edges) * depth_weight`.
- Tie-breakers: higher score, lower depth, relationship type priority, target Vault ID, target normalized name, relationship ID.

### Graph Retrieval Response Contracts

Create `src/vault_graph/retrieval/graph_retrieval.py`:

```python
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from vault_graph.errors import SearchError
from vault_graph.graph.graph_contracts import EntityRecord, RelationshipRecord
from vault_graph.ingestion.vault_catalog import QueryScope
from vault_graph.projection.graph_projection import GRAPH_PROJECTION_VERSION
from vault_graph.storage.interfaces.metadata_store import EvidenceReference

GraphOutputFormat = Literal["text", "json"]
GraphWarningSeverity = Literal["info", "warning", "error"]


@dataclass(frozen=True)
class GraphRetrievalWarning:
    code: str
    message: str
    severity: GraphWarningSeverity
    affected_vault_ids: tuple[str, ...]
    scope_key: str | None = None
    entity_id: str | None = None
    relationship_id: str | None = None
    evidence_ref_id: str | None = None

    def __post_init__(self) -> None:
        if not self.code:
            raise SearchError("graph warning code is required")
        if not self.message:
            raise SearchError("graph warning message is required")
        if not self.affected_vault_ids:
            raise SearchError("graph warning affected_vault_ids is required")


@dataclass(frozen=True)
class GraphRetrievalRevision:
    kind: Literal["metadata", "graph", "projection"]
    revision: str
    scope_key: str
    vault_id: str | None = None


@dataclass(frozen=True)
class RelatedRequest:
    target: str
    requested_scope: QueryScope
    actual_scopes: tuple[QueryScope, ...]
    depth: int = 1
    direction: Literal["out", "in", "both"] = "both"
    relationship_types: tuple[str, ...] = ()
    include_cross_vault: bool = False
    limit: int = 10
    output_format: GraphOutputFormat = "text"


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

Response validation rules:

- `RelatedItem.relationship_path` must be non-empty.
- `RelatedItem.evidence` must be non-empty and must come from relationship evidence refs.
- The initial decision trace step may have an empty `relationship_path`, but it must have resolved target entity evidence.
- Non-initial decision trace steps must have non-empty relationship evidence.
- `result_count` must equal `len(items)`.
- `graph_projection_version` must be `GRAPH_PROJECTION_VERSION` even when `projection_build_id is None`.

### Graph Retrieval Service

Create `src/vault_graph/app/graph_retrieval_service.py`:

```python
from __future__ import annotations

from vault_graph.graph.graph_contracts import EntityRecord
from vault_graph.graph.graph_readiness import GraphReadiness
from vault_graph.ingestion.vault_catalog import QueryScope, VaultCatalog
from vault_graph.projection.graph_projection import GraphProjection
from vault_graph.app.graph_readiness_service import ReadOnlyGraphReadiness
from vault_graph.retrieval.graph_retrieval import (
    DecisionTraceResponse,
    GraphOutputFormat,
    RelatedResponse,
)
from vault_graph.retrieval.graph_candidates import GraphCandidateResult
from vault_graph.storage.interfaces.graph_store import GraphStore
from vault_graph.storage.interfaces.metadata_store import MetadataStore


class GraphRetrievalService:
    def __init__(
        self,
        *,
        catalog: VaultCatalog,
        metadata_store: MetadataStore,
        graph_store: GraphStore,
        graph_readiness: ReadOnlyGraphReadiness,
        projection: GraphProjection,
    ) -> None: ...

    def related(
        self,
        *,
        target: str,
        requested_scope: QueryScope,
        depth: int = 1,
        direction: str = "both",
        relationship_types: tuple[str, ...] = (),
        include_cross_vault: bool = False,
        limit: int = 10,
        output_format: GraphOutputFormat = "text",
    ) -> RelatedResponse: ...

    def decision_trace(
        self,
        *,
        topic: str,
        requested_scope: QueryScope,
        depth: int = 2,
        include_cross_vault: bool = False,
        limit: int = 10,
        output_format: GraphOutputFormat = "text",
    ) -> DecisionTraceResponse: ...

    def graph_candidates_for_search(
        self,
        *,
        query_text: str,
        requested_scope: QueryScope,
        actual_scopes: tuple[QueryScope, ...],
        limit: int,
        include_cross_vault: bool,
    ) -> GraphCandidateResult: ...
```

The service must be the only new code path that combines:

- `actual_query_scopes(...)`
- `ReadOnlyGraphReadiness.check(...)`
- `GraphStore.find_entities(...)`
- `GraphStore.relationships_for_entities(...)`
- `GraphProjection.project(...)`
- `MetadataStore.resolve_chunk_evidence(...)`

Use this helper shape in graph retrieval service tests instead of constructing a
partial `GraphReadiness`:

```python
def make_graph_readiness(
    *,
    actual_scopes: tuple[QueryScope, ...],
    freshness: str = "fresh",
    stale_count: int = 0,
    warnings: tuple[str, ...] = (),
) -> GraphReadiness:
    scope_rows = tuple(
        GraphScopeReadiness(
            vault_id=scope.vault_ids[0],
            actual_scope=graph_scope_key(scope),
            freshness=freshness,
            stale_count=stale_count,
            tombstone_count=0,
            last_graph_revision="graph-1" if freshness == "fresh" else None,
            warnings=warnings,
        )
        for scope in actual_scopes
    )
    return GraphReadiness(
        backend_name="memory-graph",
        backend_available=backend_available_for_freshness(freshness),
        schema_version="memory-graph-v1",
        schema_compatible=freshness != "incompatible",
        graph_extraction_spec_version=current_graph_extraction_spec().spec_version,
        graph_extraction_spec_digest=current_graph_extraction_spec().spec_digest,
        graph_extraction_spec_compatible=freshness != "incompatible",
        freshness=freshness,
        stale_count=stale_count,
        tombstone_count=0,
        last_graph_revision="graph-1" if freshness == "fresh" else None,
        affected_vault_ids=tuple(vault_id for scope in actual_scopes for vault_id in scope.vault_ids),
        scope_readiness=scope_rows,
        warnings=warnings,
        recovery_hint="ok" if freshness == "fresh" else "run `vg index`",
    )


def backend_available_for_freshness(freshness: str) -> bool:
    return freshness not in {"missing", "unavailable"}
```

Import `GraphReadiness`, `GraphScopeReadiness`, `graph_scope_key`, and
`current_graph_extraction_spec` in the test file that owns this helper.

### Retrieval Candidate Seam

Create `src/vault_graph/retrieval/retrieval_candidate.py`:

```python
from __future__ import annotations

from dataclasses import dataclass

from vault_graph.errors import RetrievalContractError
from vault_graph.retrieval.retrieval_result import RetrievalSignal


@dataclass(frozen=True)
class RetrievalCandidate:
    vault_id: str
    document_id: str
    chunk_id: str
    signals: tuple[RetrievalSignal, ...]

    def __post_init__(self) -> None:
        if not self.vault_id:
            raise RetrievalContractError("retrieval candidate vault_id is required")
        if not self.document_id:
            raise RetrievalContractError("retrieval candidate document_id is required")
        if not self.chunk_id:
            raise RetrievalContractError("retrieval candidate chunk_id is required")
        if not self.signals:
            raise RetrievalContractError("retrieval candidate signals are required")

```

Create `src/vault_graph/retrieval/graph_candidates.py`:

```python
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from vault_graph.ingestion.vault_catalog import QueryScope
from vault_graph.retrieval.retrieval_candidate import RetrievalCandidate
from vault_graph.retrieval.search_response import SearchStoreRevision, SearchWarning


@dataclass(frozen=True)
class GraphCandidateResult:
    candidates: tuple[RetrievalCandidate, ...]
    warnings: tuple[SearchWarning, ...]
    store_revisions: tuple[SearchStoreRevision, ...]


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


class GraphSearchSource(Protocol):
    def graph_candidates_for_search(
        self,
        *,
        query_text: str,
        requested_scope: QueryScope,
        actual_scopes: tuple[QueryScope, ...],
        limit: int,
        include_cross_vault: bool,
    ) -> GraphCandidateResult: ...
```

`RetrievalService.__init__` becomes:

```python
class RetrievalService:
    def __init__(
        self,
        *,
        catalog: VaultCatalog,
        metadata_store: MetadataStore,
        keyword_index: KeywordIndex,
        readiness: SearchReadiness,
        vector_store: VectorStore | None = None,
        text_embeddings: TextEmbeddings | None = None,
        graph_candidate_provider: GraphCandidateProvider | None = None,
    ) -> None: ...
```

`RetrievalService.search(...)` becomes:

```python
def search(
    self,
    *,
    query_text: str,
    requested_scope: QueryScope,
    limit: int = 10,
    output_format: SearchOutputFormat = "text",
    include_graph: bool = False,
    include_cross_vault: bool = False,
) -> SearchResponse: ...
```

`SIGNAL_WEIGHTS` becomes:

```python
SIGNAL_WEIGHTS: dict[RetrievalSignalKind, float] = {"keyword": 1.0, "vector": 1.0, "graph": 0.75}
```

## State Management And Data Flow

### `vg related TARGET`

```text
CLI
  -> resolve requested QueryScope from --vault-id, --all-vaults, or default
  -> validate --include-cross-vault only with --all-vaults
  -> GraphRetrievalService.related(...)
       -> actual_query_scopes(catalog, requested_scope)
       -> GraphReadinessService.check(requested_scope, actual_scopes)
       -> choose fresh actual scopes only
       -> GraphStore.find_entities(GraphEntityQuery(...))
       -> resolve unique target or return warnings/candidates
       -> for each depth frontier up to depth 2:
            GraphStore.relationships_for_entities(GraphRelationshipQuery(...))
       -> resolve relationship evidence through MetadataStore
       -> drop evidence-invalid edges before projection
       -> GraphProjection.project(...)
       -> resolve path entities and supplemental entity evidence
       -> return RelatedResponse
  -> CLI renders text or JSON
```

No state is written. Missing, empty, or stale graph scopes return empty graph results plus warnings. Incompatible or unavailable graph store is fatal for graph-specific commands.

### `vg decision-trace TOPIC`

```text
CLI
  -> resolve requested QueryScope
  -> GraphRetrievalService.decision_trace(...)
       -> target resolution with type priority Decision, WikiPage, Document, Concept, other
       -> if exact non-Decision target wins, mark trace_kind="topic"
       -> add topic_not_durable_decision warning
       -> bounded relationship expansion, default depth 2
       -> evidence gate relationship paths
       -> rank steps by relationship priority and projection score
       -> add initial decision/topic identity step only when entity evidence resolves
       -> return DecisionTraceResponse
```

Decision trace is not an answer. It must never synthesize a recommendation.

### `vg search "query" --include-graph`

```text
CLI
  -> validate --include-cross-vault requires --include-graph and --all-vaults
  -> RetrievalService.search(include_graph=True, include_cross_vault=...)
       -> normal search readiness
       -> keyword candidates
       -> vector candidates when ready
       -> GraphCandidateProvider.candidates(...) only when include_graph=True
       -> fuse keyword/vector/graph RetrievalCandidate rows
       -> resolve final evidence through MetadataStore
       -> return SearchResponse with graph warnings and graph revisions
```

Plain `vg search "query"` must not open or read graph state. This must be enforced by a test using a graph provider or graph store fake that fails on access.

## Error Handling And Edge Cases

Fatal for graph commands:

- invalid Vault scope
- graph store schema incompatible
- graph store unavailable
- metadata store unavailable
- `depth <= 0` or `depth > 2`
- `limit <= 0`
- unsupported direction
- unsupported output format
- `--include-cross-vault` without `--all-vaults`

Non-fatal graph command warnings:

- `target_not_found`: no exact or suggestion target exists
- `ambiguous_graph_target`: multiple equal-best target matches
- `topic_not_durable_decision`: `decision-trace` used a non-Decision target
- `graph_stale`: selected graph scope is stale and omitted
- `graph_empty`: selected graph scope has no graph revision or graph rows
- `graph_target_scan_truncated`: target fallback scan hit its hard row cap
- `graph_relationship_read_truncated`: direct neighborhood read hit its hard relationship cap
- `graph_projection_truncated`: projection edge/read/result limits truncated output
- `cross_vault_relationship_omitted`: cross-Vault relationship was filtered or points outside selected scope
- `graph_evidence_missing`: relationship or required target evidence did not resolve through metadata
- `deprecated_relationship_omitted`: deprecated relationship was omitted

Opt-in graph search behavior:

- missing keyword index remains fatal because search cannot run
- graph missing, empty, stale, incompatible, or unavailable is non-fatal if keyword search can run
- graph readiness failures in opt-in search are converted to `SearchWarning`
  records and must not escape as fatal `SearchError` unless keyword/metadata
  search itself cannot run
- graph query failure returns keyword/vector results plus `graph_query_failed`
- no graph target returns keyword/vector results plus `graph_target_not_found`
- ambiguous graph target returns keyword/vector results plus `ambiguous_graph_target`
- graph warnings must include affected Vault IDs

Multi-vault edge cases:

- `--all-vaults GraphRAG` with same normalized name in two Vaults returns `ambiguous_graph_target` and no traversal.
- `--vault-id main GraphRAG` can traverse only `main`.
- `--all-vaults --include-cross-vault GraphRAG` may traverse cross-Vault relationships, but still must not merge same-name entities.
- Cross-Vault relationship output must preserve source, target, and evidence Vault IDs.
- Relationships pointing to Vault IDs outside the selected scope are omitted with `cross_vault_relationship_omitted`.

Read-only edge cases:

- Graph commands must not create missing metadata, vector, graph, embedding cache, graph status, or projection cache files.
- Graph search must not call `vg index`, `IndexService`, writable stores, or Chroma writes.
- `GraphProjection` must not write `data/projection_cache/`.

---

### Task 1: Add Rustworkx Dependency And Graph Query Contracts

**Files:**

- Modify: `pyproject.toml`
- Modify: `uv.lock`
- Create: `src/vault_graph/graph/graph_query.py`
- Modify: `src/vault_graph/storage/interfaces/graph_store.py`
- Modify: `src/vault_graph/storage/interfaces/__init__.py`
- Test: `tests/test_graph_query_contract.py`

- [ ] **Step 1: Write failing graph query contract tests**

Create `tests/test_graph_query_contract.py`:

```python
import pytest

from vault_graph.errors import GraphStoreError
from vault_graph.graph.graph_query import GraphEntityIdentity, GraphEntityMatch, GraphEntityQuery, GraphRelationshipQuery
from vault_graph.ingestion.vault_catalog import QueryScope
from tests.test_graph_store_contract import make_entity


def test_graph_entity_query_requires_text() -> None:
    with pytest.raises(GraphStoreError, match="graph entity query text is required"):
        GraphEntityQuery(text=" ", actual_scopes=(QueryScope(vault_ids=("default",), content_scopes=("wiki",)),))


def test_graph_entity_query_requires_actual_scopes() -> None:
    with pytest.raises(GraphStoreError, match="per-Vault actual scopes"):
        GraphEntityQuery(text="GraphRAG", actual_scopes=(QueryScope(vault_ids=("a", "b"), content_scopes=("wiki",)),))


def test_graph_relationship_query_requires_seed() -> None:
    with pytest.raises(GraphStoreError, match="seeds are required"):
        GraphRelationshipQuery(
            seeds=(),
            actual_scopes=(QueryScope(vault_ids=("default",), content_scopes=("wiki",)),),
        )


def test_graph_entity_match_keeps_match_metadata() -> None:
    entity = make_entity("default", name="GraphRAG")
    match = GraphEntityMatch(entity=entity, match_kind="normalized_name", match_rank=1, matched_value="graphrag")

    assert match.entity == entity
    assert match.match_kind == "normalized_name"
    assert match.match_rank == 1


def test_graph_relationship_query_accepts_cross_vault_flag() -> None:
    query = GraphRelationshipQuery(
        seeds=(GraphEntityIdentity("default", "entity-1"),),
        actual_scopes=(QueryScope(vault_ids=("default",), content_scopes=("wiki",), include_cross_vault=True),),
        include_cross_vault=True,
    )

    assert query.direction == "both"
    assert query.statuses == ("stated", "inferred", "contested")


def test_graph_entity_query_rejects_unbounded_scan_limit() -> None:
    with pytest.raises(GraphStoreError, match="scan_limit is out of range"):
        GraphEntityQuery(
            text="GraphRAG",
            actual_scopes=(QueryScope(vault_ids=("default",), content_scopes=("wiki",)),),
            scan_limit=5001,
        )


def test_graph_relationship_query_rejects_unbounded_read_limit() -> None:
    with pytest.raises(GraphStoreError, match="limit is out of range"):
        GraphRelationshipQuery(
            seeds=(GraphEntityIdentity("default", "entity-1"),),
            actual_scopes=(QueryScope(vault_ids=("default",), content_scopes=("wiki",)),),
            limit=201,
        )
```

- [ ] **Step 2: Run test and verify failure**

Run:

```bash
uv run --python 3.12 pytest tests/test_graph_query_contract.py -q
```

Expected: FAIL because `vault_graph.graph.graph_query` does not exist.

- [ ] **Step 3: Add dependency**

Run:

```bash
uv add "rustworkx>=0.17,<1.0"
```

Expected: `pyproject.toml` gains the runtime dependency and `uv.lock` is updated. Do not manually edit `uv.lock`.

- [ ] **Step 4: Add graph query dataclasses**

Implement `src/vault_graph/graph/graph_query.py` exactly as specified in "Graph Query Contracts".

- [ ] **Step 5: Extend GraphStore Protocol**

Modify `src/vault_graph/storage/interfaces/graph_store.py` to import and expose:

```python
def find_entities(self, query: GraphEntityQuery) -> GraphEntityQueryResult:
    raise NotImplementedError

def relationships_for_entities(self, query: GraphRelationshipQuery) -> GraphRelationshipQueryResult:
    raise NotImplementedError
```

- [ ] **Step 6: Export contracts**

If `src/vault_graph/storage/interfaces/__init__.py` exports graph interfaces, add:

```python
GraphEntityIdentity
GraphEntityQuery
GraphEntityMatch
GraphEntityQueryResult
GraphRelationshipIdentity
GraphRelationshipQuery
GraphRelationshipQueryResult
```

- [ ] **Step 7: Verify contract tests pass**

Run:

```bash
uv run --python 3.12 pytest tests/test_graph_query_contract.py -q
```

Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add pyproject.toml uv.lock src/vault_graph/graph/graph_query.py src/vault_graph/storage/interfaces/graph_store.py src/vault_graph/storage/interfaces/__init__.py tests/test_graph_query_contract.py
git commit -m "feat(graph): add graph query contracts"
```

### Task 2: Implement GraphStore Query Methods

**Files:**

- Modify: `tests/test_graph_store_contract.py`
- Modify: `tests/test_sqlite_graph_store.py`
- Modify: `tests/fakes/in_memory_graph_store.py`
- Modify: `src/vault_graph/storage/local/sqlite_graph_store.py`

- [ ] **Step 1: Add reusable GraphStore query contract tests**

Append to `tests/test_graph_store_contract.py`:

Add imports:

```python
from vault_graph.graph.graph_query import GraphEntityIdentity, GraphEntityQuery, GraphRelationshipQuery
```

If not already imported in the file, also add:

```python
from vault_graph.graph.graph_contracts import GraphReconcilePlan, current_graph_extraction_spec
```

```python
def graph_store_query_contract(factory: Callable[[], GraphStore]) -> None:
    store = factory()
    source = make_entity("default", name="GraphRAG", path="wiki/graphrag.md")
    target = make_entity("default", name="Evidence Search", path="wiki/search.md")
    relationship = make_relationship(source, target)
    store.apply_reconcile_plan(make_plan(entities=(source, target), relationships=(relationship,)))
    scope = QueryScope(vault_ids=("default",), content_scopes=("wiki",))

    result = store.find_entities(GraphEntityQuery(text="GraphRAG", actual_scopes=(scope,)))
    matches = result.matches
    assert tuple(match.match_kind for match in matches[:1]) == ("normalized_name",)
    assert matches[0].entity.entity_id == source.entity_id
    assert result.truncated is False

    alias_matches = store.find_entities(GraphEntityQuery(text="Graph RAG", actual_scopes=(scope,))).matches
    assert any(match.match_kind == "alias" and match.entity.entity_id == source.entity_id for match in alias_matches)

    path_matches = store.find_entities(GraphEntityQuery(text="wiki/graphrag.md", actual_scopes=(scope,))).matches
    assert path_matches[0].match_kind == "canonical_path"

    suggestion_matches = store.find_entities(GraphEntityQuery(text="Graph", actual_scopes=(scope,))).matches
    assert all(match.match_kind in {"contains", "normalized_name", "alias", "canonical_path"} for match in suggestion_matches)

    relationship_result = store.relationships_for_entities(
        GraphRelationshipQuery(seeds=(GraphEntityIdentity("default", source.entity_id),), actual_scopes=(scope,))
    )
    assert relationship_result.relationships == (relationship,)
    assert relationship_result.truncated is False

    in_result = store.relationships_for_entities(
        GraphRelationshipQuery(
            seeds=(GraphEntityIdentity("default", target.entity_id),),
            actual_scopes=(scope,),
            direction="in",
        )
    )
    assert in_result.relationships == (relationship,)

    out_result = store.relationships_for_entities(
        GraphRelationshipQuery(
            seeds=(GraphEntityIdentity("default", source.entity_id),),
            actual_scopes=(scope,),
            direction="out",
        )
    )
    assert out_result.relationships == (relationship,)

    type_filtered = store.relationships_for_entities(
        GraphRelationshipQuery(
            seeds=(GraphEntityIdentity("default", source.entity_id),),
            actual_scopes=(scope,),
            relationship_types=("depends_on",),
        )
    )
    assert type_filtered.relationships == (relationship,)

    type_miss = store.relationships_for_entities(
        GraphRelationshipQuery(
            seeds=(GraphEntityIdentity("default", source.entity_id),),
            actual_scopes=(scope,),
            relationship_types=("blocks",),
        )
    )
    assert type_miss.relationships == ()

    truncated = store.relationships_for_entities(
        GraphRelationshipQuery(
            seeds=(GraphEntityIdentity("default", source.entity_id),),
            actual_scopes=(scope,),
            limit=1,
        )
    )
    assert truncated.relationships == (relationship,)
    assert truncated.truncated is False
```

Also add a cross-Vault omission contract:

```python
def graph_store_cross_vault_query_contract(factory: Callable[[], GraphStore]) -> None:
    store = factory()
    first_scope = QueryScope(vault_ids=("first",), content_scopes=("wiki",))
    second_scope = QueryScope(vault_ids=("second",), content_scopes=("wiki",))
    source = make_entity("first", name="GraphRAG")
    target = make_entity("second", name="Search")
    relationship = make_relationship(source, target)
    evidence_refs = source.evidence_refs + target.evidence_refs + relationship.evidence_refs
    plan = GraphReconcilePlan(
        requested_scope=QueryScope(vault_ids=("first", "second"), content_scopes=("wiki",)),
        actual_scopes=(first_scope, second_scope),
        graph_run_id="graph-run-1",
        entity_upserts=(source, target),
        relationship_upserts=(relationship,),
        evidence_ref_upserts=evidence_refs,
        entity_tombstones=(),
        relationship_tombstones=(),
        graph_revision_rows=(
            make_revision(first_scope, entity_count=1, relationship_count=1),
            make_revision(second_scope, entity_count=1, relationship_count=0),
        ),
        graph_extraction_spec=current_graph_extraction_spec(),
        projection_cache_invalidations=(),
    )
    store.apply_reconcile_plan(plan)

    local_result = store.relationships_for_entities(
        GraphRelationshipQuery(seeds=(GraphEntityIdentity("first", source.entity_id),), actual_scopes=(first_scope,))
    )
    assert local_result.relationships == ()
    assert local_result.omitted_cross_vault_count == 1

    cross_result = store.relationships_for_entities(
        GraphRelationshipQuery(
            seeds=(GraphEntityIdentity("first", source.entity_id),),
            actual_scopes=(
                QueryScope(vault_ids=("first",), content_scopes=("wiki",), include_cross_vault=True),
                QueryScope(vault_ids=("second",), content_scopes=("wiki",), include_cross_vault=True),
            ),
            include_cross_vault=True,
        )
    )
    assert cross_result.relationships == (relationship,)
```

Add these reusable contract assertions in the same file:

- `GraphEntityQuery(types=("Concept",))` excludes `WikiPage` and `Document`
  entities.
- `GraphEntityQuery(...)` excludes entities whose `status == "tombstoned"`.
- `GraphRelationshipQuery(statuses=("stated",))` excludes `inferred`,
  `contested`, and `deprecated` relationships.
- `GraphRelationshipQuery(statuses=("inferred",))` returns only inferred
  relationships when present.
- `GraphRelationshipQuery(statuses=("stated", "inferred", "contested"))`
  omits deprecated relationships by default.
- `GraphRelationshipQuery(direction="out")` omits incoming-only relationships.
- `GraphRelationshipQuery(direction="in")` omits outgoing-only relationships.
- `GraphRelationshipQuery(limit=1)` sets `truncated=True` when two or more
  relationships match before the limit is applied.
- `GraphEntityQuery(scan_limit=1)` can set `GraphEntityQueryResult.truncated`
  for fallback alias/contains scans when more scoped active rows remain.

- [ ] **Step 2: Wire contract tests to fake and SQLite**

Add tests:

```python
def test_in_memory_graph_store_query_contract() -> None:
    graph_store_query_contract(lambda: InMemoryGraphStore())


def test_sqlite_graph_store_query_contract(tmp_path: Path) -> None:
    graph_store_query_contract(lambda: SQLiteGraphStore.open_writable(tmp_path / "graph.sqlite3"))
```

Add equivalent cross-Vault contract calls.

- [ ] **Step 3: Run tests and verify failure**

Run:

```bash
uv run --python 3.12 pytest tests/test_graph_store_contract.py tests/test_sqlite_graph_store.py -q
```

Expected: FAIL because fake and SQLite stores do not implement `find_entities` and `relationships_for_entities`.

- [ ] **Step 4: Implement fake store query methods**

In `tests/fakes/in_memory_graph_store.py`, implement:

```python
def find_entities(self, query: GraphEntityQuery) -> GraphEntityQueryResult:
    ...

def relationships_for_entities(self, query: GraphRelationshipQuery) -> GraphRelationshipQueryResult:
    ...
```

Fake store rules:

- Use active entities only: `entity.status == "active"`.
- Scope by selected actual Vault IDs and content scopes through `_record_scopes`.
- Apply `query.types` exactly when provided.
- Normalize query text with `normalize_entity_name(...)`.
- Match order:
  - `entity_id`: exact `entity.entity_id == query.text`
  - `canonical_path`: exact `entity.canonical_path == query.text`
  - `normalized_name`: exact `entity.normalized_name == normalized_text`
  - `alias`: any `normalize_entity_name(alias) == normalized_text`
  - `contains`: suggestion only when normalized text is contained in `entity.normalized_name` or normalized alias
- Sort by `(match_rank, entity.vault_id, entity.normalized_name, entity.entity_id)`.
- Limit after sorting.

Relationship rules:

- Seed key is `(vault_id, entity_id)`.
- Direction:
  - `out`: source in seeds
  - `in`: target in seeds
  - `both`: source or target in seeds
- Apply `relationship_types`, `statuses`, actual scope, cross-Vault, and limit filters.
- Omitted cross-Vault relationships increment `omitted_cross_vault_count`.
- Sort by `(source_vault_id, target_vault_id, type, relationship_id)`.
- `truncated=True` when more matching rows exist than `query.limit`.

- [ ] **Step 5: Implement SQLite query methods**

In `src/vault_graph/storage/local/sqlite_graph_store.py`:

- Keep read-only connections in read-only mode.
- Do not create tables from read-only query methods.
- For `find_entities`, query active records by selected Vault IDs and optional type filters.
- Decode `aliases_json` in Python for alias matching.
- Use indexed exact probes for `entity_id` and `normalized_name` before any
  fallback scan.
- Use `query.scan_limit` as a hard cap for canonical-path, alias, and
  contained-text fallback scans over scoped active entities.
- Return `GraphEntityQueryResult.truncated=True` when the fallback scan reaches
  `query.scan_limit` before all scoped active entities are evaluated.
- Do not silently continue scanning past `query.scan_limit`.
- For `relationships_for_entities`, query relationships by source/target seed IDs using existing relationship columns.
- Reuse `_relationship_allowed(...)` for local/cross-Vault rules.
- Fetch relationship evidence refs through `_evidence_refs_for_owner(...)`.
- Wrap SQLite errors in `GraphStoreUnavailable`.

Minimum SQLite helper shape:

```python
def _entity_scope_matches(entity: EntityRecord, scopes: tuple[QueryScope, ...]) -> bool: ...
def _match_entity(entity: EntityRecord, raw_text: str, normalized_text: str) -> tuple[GraphEntityMatch, ...]: ...
def _relationship_matches_seed(relationship: RelationshipRecord, seeds: set[tuple[str, str]], direction: str) -> bool: ...
```

- [ ] **Step 6: Verify query contracts pass**

Run:

```bash
uv run --python 3.12 pytest tests/test_graph_store_contract.py tests/test_sqlite_graph_store.py -q
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add tests/test_graph_store_contract.py tests/test_sqlite_graph_store.py tests/fakes/in_memory_graph_store.py src/vault_graph/storage/local/sqlite_graph_store.py
git commit -m "feat(graph): add read-only graph lookup methods"
```

### Task 3: Add Graph Projection Contract

**Files:**

- Create: `src/vault_graph/projection/__init__.py`
- Create: `src/vault_graph/projection/graph_projection.py`
- Test: `tests/test_graph_projection.py`

- [ ] **Step 1: Write failing projection contract tests**

Create `tests/test_graph_projection.py` with validation tests:

```python
import pytest

from vault_graph.errors import GraphStoreError
from vault_graph.projection.graph_projection import (
    DEFAULT_GRAPH_PROJECTION_EDGE_LIMIT,
    DEFAULT_GRAPH_RESULT_LIMIT,
    GRAPH_PROJECTION_VERSION,
    GraphProjectionEdge,
    GraphProjectionInput,
    GraphProjectionNode,
)


def node(vault_id: str, entity_id: str, name: str) -> GraphProjectionNode:
    return GraphProjectionNode(
        vault_id=vault_id,
        entity_id=entity_id,
        type="Concept",
        name=name,
        normalized_name=name.casefold(),
    )


def edge(source: GraphProjectionNode, target: GraphProjectionNode, relationship_id: str = "rel-1") -> GraphProjectionEdge:
    return GraphProjectionEdge(
        source_vault_id=source.vault_id,
        source_entity_id=source.entity_id,
        target_vault_id=target.vault_id,
        target_entity_id=target.entity_id,
        relationship_id=relationship_id,
        relationship_type="related_to",
        status="stated",
        confidence=0.9,
        evidence_ref_ids=("evidence-1",),
        graph_index_revision="graph-1",
    )


def test_projection_input_rejects_depth_above_phase_limit() -> None:
    source = node("default", "source", "GraphRAG")
    target = node("default", "target", "Search")
    with pytest.raises(GraphStoreError, match="unsupported graph projection depth"):
        GraphProjectionInput(
            seeds=(source,),
            nodes=(source, target),
            relationships=(edge(source, target),),
            actual_scope_keys=("default:wiki",),
            source_graph_revisions=("graph-1",),
            max_depth=3,
            direction="both",
            relationship_types=(),
            statuses=("stated",),
            include_cross_vault=False,
            limit=DEFAULT_GRAPH_RESULT_LIMIT,
            edge_limit=DEFAULT_GRAPH_PROJECTION_EDGE_LIMIT,
        )


def test_projection_version_is_stable() -> None:
    assert GRAPH_PROJECTION_VERSION == "graph-projection-v1"
```

- [ ] **Step 2: Run tests and verify failure**

Run:

```bash
uv run --python 3.12 pytest tests/test_graph_projection.py -q
```

Expected: FAIL because `vault_graph.projection` does not exist.

- [ ] **Step 3: Implement projection contract module**

Implement `src/vault_graph/projection/graph_projection.py` exactly as specified in "Projection Contracts".

Create `src/vault_graph/projection/__init__.py`:

```python
from vault_graph.projection.graph_projection import (
    DEFAULT_GRAPH_PROJECTION_EDGE_LIMIT,
    DEFAULT_GRAPH_RELATED_DEPTH,
    DEFAULT_GRAPH_RELATIONSHIP_READ_LIMIT,
    DEFAULT_GRAPH_RESULT_LIMIT,
    DEFAULT_GRAPH_TARGET_LIMIT,
    GRAPH_PROJECTION_VERSION,
    MAX_GRAPH_PROJECTION_DEPTH,
    MAX_GRAPH_PROJECTION_EDGE_LIMIT,
    MAX_GRAPH_RESULT_LIMIT,
    GraphPath,
    GraphProjection,
    GraphProjectionEdge,
    GraphProjectionInput,
    GraphProjectionNode,
    GraphProjectionResult,
)

__all__ = [
    "DEFAULT_GRAPH_PROJECTION_EDGE_LIMIT",
    "DEFAULT_GRAPH_RELATED_DEPTH",
    "DEFAULT_GRAPH_RELATIONSHIP_READ_LIMIT",
    "DEFAULT_GRAPH_RESULT_LIMIT",
    "DEFAULT_GRAPH_TARGET_LIMIT",
    "GRAPH_PROJECTION_VERSION",
    "MAX_GRAPH_PROJECTION_DEPTH",
    "MAX_GRAPH_PROJECTION_EDGE_LIMIT",
    "MAX_GRAPH_RESULT_LIMIT",
    "GraphPath",
    "GraphProjection",
    "GraphProjectionEdge",
    "GraphProjectionInput",
    "GraphProjectionNode",
    "GraphProjectionResult",
]
```

- [ ] **Step 4: Verify projection contract tests pass**

Run:

```bash
uv run --python 3.12 pytest tests/test_graph_projection.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/vault_graph/projection/__init__.py src/vault_graph/projection/graph_projection.py tests/test_graph_projection.py
git commit -m "feat(projection): add graph projection contract"
```

### Task 4: Implement Rustworkx Graph Projection

**Files:**

- Create: `src/vault_graph/projection/rustworkx_projection.py`
- Modify: `src/vault_graph/projection/__init__.py`
- Test: `tests/test_graph_projection.py`

- [ ] **Step 1: Add failing projection behavior tests**

Append tests:

```python
from dataclasses import replace

from vault_graph.projection.rustworkx_projection import RustworkxGraphProjection


def test_rustworkx_projection_returns_depth_one_paths_in_deterministic_order() -> None:
    seed = node("default", "seed", "GraphRAG")
    high = node("default", "high", "Hybrid Retrieval")
    low = node("default", "low", "Contested Link")
    relationships = (
        edge(seed, low, "rel-low"),
        replace(edge(seed, high, "rel-high"), confidence=1.0),
    )

    result = RustworkxGraphProjection().project(
        GraphProjectionInput(
            seeds=(seed,),
            nodes=(seed, high, low),
            relationships=relationships,
            actual_scope_keys=("default:wiki",),
            source_graph_revisions=("graph-1",),
            max_depth=1,
            direction="out",
            relationship_types=(),
            statuses=("stated",),
            include_cross_vault=False,
            limit=10,
            edge_limit=500,
        )
    )

    assert result.graph_projection_version == GRAPH_PROJECTION_VERSION
    assert result.paths[0].target.entity_id == "high"
    assert result.paths[0].score > result.paths[1].score
    assert result.projection_build_id


def test_rustworkx_projection_sets_truncated_when_edge_limit_is_hit() -> None:
    seed = node("default", "seed", "GraphRAG")
    targets = tuple(node("default", f"target-{index}", f"Target {index}") for index in range(3))
    relationships = tuple(edge(seed, target, f"rel-{index}") for index, target in enumerate(targets))

    result = RustworkxGraphProjection().project(
        GraphProjectionInput(
            seeds=(seed,),
            nodes=(seed, *targets),
            relationships=relationships,
            actual_scope_keys=("default:wiki",),
            source_graph_revisions=("graph-1",),
            max_depth=1,
            direction="out",
            relationship_types=(),
            statuses=("stated",),
            include_cross_vault=False,
            limit=10,
            edge_limit=2,
        )
    )

    assert result.truncated is True
    assert result.edge_count == 2
```

Also test:

- `direction="in"` traverses target-to-source.
- `direction="both"` traverses both ways without duplicating identical paths.
- depth 2 returns two-edge paths and applies depth weight.
- `deprecated` edges produce score `0.0` and should not be included unless status filter includes it later.

- [ ] **Step 2: Run tests and verify failure**

Run:

```bash
uv run --python 3.12 pytest tests/test_graph_projection.py -q
```

Expected: FAIL because `RustworkxGraphProjection` does not exist.

- [ ] **Step 3: Implement RustworkxGraphProjection**

Implementation requirements:

- Import `rustworkx as rx`.
- Use `rx.PyDiGraph(multigraph=True)`.
- Sort `request.nodes` by `(vault_id, normalized_name, entity_id)` before adding to the graph for deterministic node indices.
- Store `GraphProjectionNode` as node payloads and `GraphProjectionEdge` as edge payloads.
- Maintain `node_index_by_identity: dict[tuple[str, str], int]`.
- Enforce `request.edge_limit` before projection. If relationships exceed the edge limit, sort deterministically, keep only the first `edge_limit`, and set `truncated=True`.
- Enumerate simple paths up to `request.max_depth` with no repeated node identities.
- Respect `direction`, `relationship_types`, and `statuses`.
- Do not include seed-to-seed paths.
- Score paths using the policy in "Projection Contracts".
- Build `projection_build_id` with SHA-256 over:
  - `GRAPH_PROJECTION_VERSION`
  - sorted actual scope keys
  - sorted seed identities
  - sorted working node identities
  - sorted source graph revisions
  - max depth
  - direction
  - sorted relationship types
  - sorted statuses
  - include cross-Vault flag
  - limit
- Return at most `request.limit` paths.

Minimum public class:

```python
class RustworkxGraphProjection:
    def project(self, request: GraphProjectionInput) -> GraphProjectionResult:
        ...
```

- [ ] **Step 4: Export RustworkxGraphProjection**

Add to `src/vault_graph/projection/__init__.py`:

```python
from vault_graph.projection.rustworkx_projection import RustworkxGraphProjection
```

and include it in `__all__`.

- [ ] **Step 5: Verify projection behavior**

Run:

```bash
uv run --python 3.12 pytest tests/test_graph_projection.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/vault_graph/projection/__init__.py src/vault_graph/projection/rustworkx_projection.py tests/test_graph_projection.py
git commit -m "feat(projection): add rustworkx graph projection"
```

### Task 5: Add Graph Retrieval Response Contracts

**Files:**

- Create: `src/vault_graph/retrieval/graph_retrieval.py`
- Modify: `src/vault_graph/retrieval/__init__.py`
- Test: `tests/test_graph_retrieval_contract.py`

- [ ] **Step 1: Write failing graph retrieval DTO tests**

Create `tests/test_graph_retrieval_contract.py`:

```python
import pytest

from tests.test_graph_store_contract import make_entity, make_relationship
from vault_graph.errors import SearchError
from vault_graph.ingestion.vault_catalog import QueryScope
from vault_graph.projection.graph_projection import GRAPH_PROJECTION_VERSION
from vault_graph.retrieval.graph_retrieval import GraphRetrievalWarning, RelatedItem, RelatedResponse


def test_graph_warning_requires_vault_attribution() -> None:
    with pytest.raises(SearchError, match="affected_vault_ids"):
        GraphRetrievalWarning(code="graph_stale", message="stale", severity="warning", affected_vault_ids=())


def test_related_response_counts_items() -> None:
    source = make_entity("default")
    target = make_entity("default", name="Search")
    relationship = make_relationship(source, target)
    evidence = relationship.evidence_refs[0]
    item = RelatedItem(
        rank=1,
        entity=target,
        relationship_path=(relationship,),
        evidence=(
            make_metadata_evidence_from_graph_ref(evidence),
        ),
        score=0.9,
        explanation="GraphRAG related_to Search",
    )
    response = RelatedResponse(
        target="GraphRAG",
        resolved_target=source,
        target_candidates=(),
        requested_scope=QueryScope(vault_ids=("default",), content_scopes=("wiki",)),
        actual_scopes=(QueryScope(vault_ids=("default",), content_scopes=("wiki",)),),
        projection_build_id="projection-1",
        graph_projection_version=GRAPH_PROJECTION_VERSION,
        result_count=1,
        items=(item,),
        warnings=(),
        store_revisions=(),
        generated_at="2026-06-11T00:00:00+00:00",
    )

    assert response.result_count == 1
```

Use a local helper in the test file to create an `EvidenceReference` from a `GraphEvidenceRef`.

- [ ] **Step 2: Run tests and verify failure**

Run:

```bash
uv run --python 3.12 pytest tests/test_graph_retrieval_contract.py -q
```

Expected: FAIL because `graph_retrieval.py` does not exist.

- [ ] **Step 3: Implement graph retrieval DTOs**

Create `src/vault_graph/retrieval/graph_retrieval.py` as specified in "Graph Retrieval Response Contracts".

Add validation:

- warning code/message/affected Vault IDs required
- `RelatedItem.rank > 0`
- `RelatedItem.relationship_path` required
- `RelatedItem.evidence` required
- `RelatedResponse.result_count == len(items)`
- `DecisionTraceStep.rank > 0`
- non-initial decision steps must include relationship evidence

- [ ] **Step 4: Export graph retrieval DTOs**

Modify `src/vault_graph/retrieval/__init__.py` to export:

```python
GraphRetrievalWarning
GraphRetrievalRevision
RelatedRequest
RelatedItem
RelatedResponse
DecisionTraceStep
DecisionTraceResponse
```

- [ ] **Step 5: Verify DTO tests pass**

Run:

```bash
uv run --python 3.12 pytest tests/test_graph_retrieval_contract.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/vault_graph/retrieval/graph_retrieval.py src/vault_graph/retrieval/__init__.py tests/test_graph_retrieval_contract.py
git commit -m "feat(retrieval): add graph retrieval response contracts"
```

### Task 6: Implement GraphRetrievalService.related

**Files:**

- Create: `src/vault_graph/app/graph_retrieval_service.py`
- Test: `tests/test_graph_retrieval_service.py`
- Test: `tests/test_graph_retrieval_read_only_boundary.py`
- Test: `tests/test_multi_vault_graph_retrieval.py`

- [ ] **Step 1: Write failing related service tests**

Create `tests/test_graph_retrieval_service.py` with helpers that build:

- a `VaultCatalog`
- `SQLiteMetadataStore` evidence rows
- `InMemoryGraphStore` graph records
- `StaticGraphReadiness` returning
  `make_graph_readiness(actual_scopes=(scope,), freshness="fresh")`
- `RustworkxGraphProjection`

Required tests:

```python
def test_related_returns_evidence_linked_items(tmp_path: Path) -> None: ...
def test_related_target_not_found_returns_warning_without_traversal(tmp_path: Path) -> None: ...
def test_related_ambiguous_target_returns_candidates_without_guessing(tmp_path: Path) -> None: ...
def test_related_drops_relationship_path_when_relationship_evidence_is_missing(tmp_path: Path) -> None: ...
def test_related_stale_graph_scope_returns_no_normal_results(tmp_path: Path) -> None: ...
def test_related_depth_above_two_fails(tmp_path: Path) -> None: ...
```

Expected assertions:

- normal results have `item.evidence` from `MetadataStore`, not stored graph excerpts
- `target_not_found` has no `items`
- `ambiguous_graph_target` has `target_candidates` and no `items`
- missing relationship evidence emits `graph_evidence_missing`
- stale scopes emit `graph_stale` and are omitted
- depth `3` raises `SearchError` or `GraphStoreError` with `unsupported graph projection depth`

- [ ] **Step 2: Add read-only boundary test**

Create `tests/test_graph_retrieval_read_only_boundary.py`:

```python
def test_related_does_not_create_missing_state_files(tmp_path: Path) -> None:
    state = tmp_path / ".vault-graph"
    vault = tmp_path / "vault"
    vault.mkdir()
    runner = CliRunner()

    init_result = runner.invoke(app, ["init", "--vault", str(vault), "--state", str(state)])
    assert init_result.exit_code == 0

    result = runner.invoke(app, ["related", "--state", str(state), "GraphRAG"])

    assert result.exit_code in {0, 1}
    assert not (state / "data" / "projection_cache").exists()
```

Also assert the registered Vault root contains no created Vault Graph files.

- [ ] **Step 3: Add multi-vault target tests**

Create `tests/test_multi_vault_graph_retrieval.py`:

```python
def test_all_vault_same_name_target_is_ambiguous_without_auto_multi_seed(tmp_path: Path) -> None: ...
def test_all_vault_include_cross_vault_same_name_target_is_still_ambiguous(tmp_path: Path) -> None: ...
def test_cross_vault_relationships_are_omitted_without_include_cross_vault(tmp_path: Path) -> None: ...
def test_cross_vault_relationship_output_preserves_source_target_and_evidence_vault_ids(tmp_path: Path) -> None: ...
def test_stale_graph_scope_does_not_stale_unrelated_fresh_vault(tmp_path: Path) -> None: ...
```

- [ ] **Step 4: Run tests and verify failure**

Run:

```bash
uv run --python 3.12 pytest tests/test_graph_retrieval_service.py tests/test_graph_retrieval_read_only_boundary.py tests/test_multi_vault_graph_retrieval.py -q
```

Expected: FAIL because `GraphRetrievalService` does not exist.

- [ ] **Step 5: Implement service constructor and related flow**

Create `src/vault_graph/app/graph_retrieval_service.py`.

Implement in these red-green substeps. Run the listed test after each substep:

1. Target resolution only:
   - Make `test_related_target_not_found_returns_warning_without_traversal`
     and `test_related_ambiguous_target_returns_candidates_without_guessing`
     pass.
   - Run: `uv run --python 3.12 pytest tests/test_graph_retrieval_service.py -q -k "target_not_found or ambiguous_target"`
2. Readiness filtering only:
   - Make `test_related_stale_graph_scope_returns_no_normal_results` pass.
   - Run: `uv run --python 3.12 pytest tests/test_graph_retrieval_service.py -q -k stale_graph_scope`
3. Relationship evidence gate only:
   - Make `test_related_drops_relationship_path_when_relationship_evidence_is_missing` pass.
   - Run: `uv run --python 3.12 pytest tests/test_graph_retrieval_service.py -q -k evidence_is_missing`
4. Projection and item assembly:
   - Make `test_related_returns_evidence_linked_items` and
     `test_related_depth_above_two_fails` pass.
   - Run: `uv run --python 3.12 pytest tests/test_graph_retrieval_service.py -q`

Implementation details:

- Use `actual_query_scopes(catalog=self._catalog, scope=requested_scope)`.
- If `include_cross_vault=True`, create actual scopes with `include_cross_vault=True`; do not mutate the original `QueryScope`.
- Call `self._graph_readiness.check(requested_scope=requested_scope, actual_scopes=actual_scopes)`.
- Fatal readiness:
  - `freshness in {"incompatible", "unavailable"}` raises `SearchError`.
  - metadata unavailable from readiness warnings raises `SearchError` for graph-specific commands.
- Fresh scope selection:
  - include only `GraphScopeReadiness.freshness == "fresh"`.
  - missing/empty/stale scopes become warnings and are omitted.
  - if no fresh scopes remain, return response with no items and warnings.
- Target resolution:
  - call `GraphStore.find_entities(GraphEntityQuery(text=target, actual_scopes=fresh_scopes, limit=20))`.
  - if `GraphEntityQueryResult.truncated` is true, add `graph_target_scan_truncated`.
  - use `GraphEntityQueryResult.matches` for target resolution.
  - choose unique best match only when `match_kind` is one of `entity_id`, `canonical_path`, `normalized_name`, `alias`.
  - if best matches include multiple entities with same best rank, return `ambiguous_graph_target`.
  - if only `contains` matches exist, return `target_not_found` plus candidates.
- Frontier expansion:
  - `frontier = (GraphEntityIdentity(resolved.vault_id, resolved.entity_id),)`.
  - for each depth level, call `relationships_for_entities(...)` with `limit=200`.
  - if `GraphRelationshipQueryResult.truncated` is true at any depth, add
    `graph_relationship_read_truncated`.
  - if `GraphRelationshipQueryResult.omitted_cross_vault_count > 0`, add
    `cross_vault_relationship_omitted`.
  - collect unique relationships by `(source_vault_id, relationship_id)`.
  - next frontier is the opposite endpoint identities not already visited.
  - stop after `depth`.
- Evidence gate:
  - for each collected relationship, resolve each `GraphEvidenceRef` using `MetadataStore.resolve_chunk_evidence(...)`.
  - if zero refs resolve for a relationship, omit that edge and add `graph_evidence_missing`.
  - do not let target entity evidence substitute for relationship evidence.
- Projection:
  - convert resolved target and all relationship endpoints into
    `GraphProjectionNode` before calling the projection.
  - pass every endpoint node through `GraphProjectionInput.nodes`; the
    projection adapter must not invent node names/types and must not read
    `GraphStore`.
  - convert evidence-valid relationships into `GraphProjectionEdge`.
  - call `self._projection.project(...)`.
  - if projection result is truncated, add `graph_projection_truncated`.
- Response:
  - build `RelatedItem` rows from projection paths.
  - resolve each path target entity using `GraphStore.get_entity(...)` or a local entity map.
  - evidence is relationship evidence deduped by `(vault_id, document_id, chunk_id)`.
  - supplemental target entity evidence may be appended only after relationship evidence passes.
  - store revisions include metadata evidence revisions, graph readiness revisions, and projection build ID.

- [ ] **Step 6: Verify related service tests pass**

Run:

```bash
uv run --python 3.12 pytest tests/test_graph_retrieval_service.py tests/test_graph_retrieval_read_only_boundary.py tests/test_multi_vault_graph_retrieval.py -q
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add src/vault_graph/app/graph_retrieval_service.py tests/test_graph_retrieval_service.py tests/test_graph_retrieval_read_only_boundary.py tests/test_multi_vault_graph_retrieval.py
git commit -m "feat(app): add evidence-first graph retrieval service"
```

### Task 7: Add `vg related`

**Files:**

- Modify: `src/vault_graph/cli/main.py`
- Test: `tests/test_cli_related.py`
- Test: `tests/test_cli_surface_boundary.py`

- [ ] **Step 1: Write failing CLI related tests**

Create `tests/test_cli_related.py`:

```python
def test_cli_related_text_renders_evidence_linked_items(tmp_path: Path, monkeypatch: MonkeyPatch) -> None: ...
def test_cli_related_json_uses_related_response_contract(tmp_path: Path, monkeypatch: MonkeyPatch) -> None: ...
def test_cli_related_rejects_include_cross_vault_without_all_vaults(tmp_path: Path) -> None: ...
def test_cli_related_ambiguous_target_exits_zero_with_warning(tmp_path: Path, monkeypatch: MonkeyPatch) -> None: ...
```

Use monkeypatching at `_graph_retrieval_service` level to return deterministic service responses. Do not require indexing in CLI unit tests.

- [ ] **Step 2: Run tests and verify failure**

Run:

```bash
uv run --python 3.12 pytest tests/test_cli_related.py tests/test_cli_surface_boundary.py -q
```

Expected: FAIL because `related` command is not registered.

- [ ] **Step 3: Add graph retrieval service factory**

In `src/vault_graph/cli/main.py`, add:

```python
def _graph_retrieval_service(state: Path) -> tuple[CatalogService, VaultCatalog, GraphRetrievalService]:
    config, catalog = _catalog(state)
    metadata_store = SQLiteMetadataStore(config.metadata_path, initialize=False)
    graph_store = SQLiteGraphStore.open_read_only(config.graph_path)
    readiness = ReadOnlyGraphReadiness(
        metadata_store=metadata_store,
        graph_store=graph_store,
        expected_spec=current_graph_extraction_spec(),
    )
    return (
        config,
        catalog,
        GraphRetrievalService(
            catalog=catalog,
            metadata_store=metadata_store,
            graph_store=graph_store,
            graph_readiness=readiness,
            projection=RustworkxGraphProjection(),
        ),
    )
```

This function must not initialize stores and must not assert write targets.

- [ ] **Step 4: Add `related` command**

Add:

```python
@app.command()
def related(
    target: str = typer.Argument(..., help="Graph target entity, path, alias, or entity ID."),
    state: Path = typer.Option(Path(".vault-graph"), "--state", help="Vault Graph state path."),
    vault_id: str | None = typer.Option(None, "--vault-id", help="Search one registered Vault ID."),
    all_vaults: bool = typer.Option(False, "--all-vaults", help="Search all enabled registered Vaults."),
    include_cross_vault: bool = typer.Option(False, "--include-cross-vault", help="Include explicit cross-Vault graph relationships."),
    depth: int = typer.Option(1, "--depth", help="Graph traversal depth, max 2."),
    relationship_type: list[str] | None = typer.Option(None, "--relationship-type", help="Relationship type filter."),
    limit: int = typer.Option(10, "--limit", help="Maximum related items."),
    output_format: str = typer.Option("text", "--format", help="Output format: text or json."),
) -> None:
    ...
```

Validation:

- `all_vaults` and `vault_id` are mutually exclusive.
- `include_cross_vault` requires `all_vaults`.
- `output_format in {"text", "json"}`.
- `depth` and `limit` are passed to service; service is final authority.

- [ ] **Step 5: Add related renderers**

Add:

```python
def _render_related_response(response: RelatedResponse) -> None: ...
def _related_response_json(response: RelatedResponse) -> dict[str, object]: ...
def _graph_warning_json(warning: GraphRetrievalWarning) -> dict[str, object]: ...
def _graph_revision_json(revision: GraphRetrievalRevision) -> dict[str, object]: ...
def _entity_json(entity: EntityRecord | None) -> dict[str, object] | None: ...
def _relationship_json(relationship: RelationshipRecord) -> dict[str, object]: ...
```

Text rendering must include:

- warnings first
- `target`
- resolved target with `[vault_id] name (type)`
- actual scopes
- projection version and build ID
- result count
- per item: rank, vault ID, entity name, relationship path, status, depth, score, evidence path/anchor, graph signal

- [ ] **Step 6: Update CLI surface test**

Modify `tests/test_cli_surface_boundary.py` to assert:

- `related` is present
- `decision-trace` is not present until Task 8 or update same test in Task 8
- `ask` and context-pack commands remain absent

- [ ] **Step 7: Verify CLI related tests pass**

Run:

```bash
uv run --python 3.12 pytest tests/test_cli_related.py tests/test_cli_surface_boundary.py -q
```

Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add src/vault_graph/cli/main.py tests/test_cli_related.py tests/test_cli_surface_boundary.py
git commit -m "feat(cli): add related graph command"
```

### Task 8: Implement Decision Trace Service And CLI

**Files:**

- Modify: `src/vault_graph/app/graph_retrieval_service.py`
- Modify: `src/vault_graph/cli/main.py`
- Test: `tests/test_graph_retrieval_service.py`
- Test: `tests/test_cli_decision_trace.py`
- Test: `tests/test_cli_surface_boundary.py`

- [ ] **Step 1: Add failing decision trace service tests**

Append to `tests/test_graph_retrieval_service.py`:

```python
def test_decision_trace_prefers_decision_entity(tmp_path: Path) -> None: ...
def test_decision_trace_falls_back_to_topic_trace_with_warning(tmp_path: Path) -> None: ...
def test_decision_trace_orders_relationship_roles_by_priority(tmp_path: Path) -> None: ...
def test_decision_trace_does_not_synthesize_recommendation(tmp_path: Path) -> None: ...
```

Expected behavior:

- `Decision` exact match wins over `WikiPage`, `Document`, and `Concept`.
- If fallback target is not `Decision`, `trace_kind == "topic"` and warning code is `topic_not_durable_decision`.
- Relationship role priority is `supersedes`, `depends_on`, `blocks`, `implements`, `related_to`, `mentions`, then lexical.
- No output field is named `answer`, `recommendation`, or `final`.

- [ ] **Step 2: Add failing CLI decision trace tests**

Create `tests/test_cli_decision_trace.py`:

```python
def test_cli_decision_trace_text_renders_steps(tmp_path: Path, monkeypatch: MonkeyPatch) -> None: ...
def test_cli_decision_trace_json_uses_response_contract(tmp_path: Path, monkeypatch: MonkeyPatch) -> None: ...
def test_cli_decision_trace_topic_trace_warning_is_visible(tmp_path: Path, monkeypatch: MonkeyPatch) -> None: ...
```

- [ ] **Step 3: Run tests and verify failure**

Run:

```bash
uv run --python 3.12 pytest tests/test_graph_retrieval_service.py tests/test_cli_decision_trace.py tests/test_cli_surface_boundary.py -q
```

Expected: FAIL because `decision_trace` behavior and CLI command do not exist.

- [ ] **Step 4: Implement `GraphRetrievalService.decision_trace`**

Implementation details:

Implement in these red-green substeps:

1. Decision target priority:
   - Make `test_decision_trace_prefers_decision_entity` pass.
   - Run: `uv run --python 3.12 pytest tests/test_graph_retrieval_service.py -q -k decision_trace_prefers`
2. Topic fallback:
   - Make `test_decision_trace_falls_back_to_topic_trace_with_warning` pass.
   - Run: `uv run --python 3.12 pytest tests/test_graph_retrieval_service.py -q -k topic_trace`
3. Role ordering:
   - Make `test_decision_trace_orders_relationship_roles_by_priority` pass.
   - Run: `uv run --python 3.12 pytest tests/test_graph_retrieval_service.py -q -k roles_by_priority`
4. No answer synthesis:
   - Make `test_decision_trace_does_not_synthesize_recommendation` pass.
   - Run: `uv run --python 3.12 pytest tests/test_graph_retrieval_service.py -q -k synthesize`
5. CLI rendering:
   - Then implement CLI text/JSON rendering and run
     `uv run --python 3.12 pytest tests/test_cli_decision_trace.py -q`.

- Reuse target resolution with type priority:
  - `Decision`
  - `WikiPage`
  - `Document`
  - `Concept`
  - any other type by lexical order
- If target type is not `Decision`, add `topic_not_durable_decision` warning and set `trace_kind="topic"`.
- Default depth is `2`.
- Relationship filters default to all supported non-deprecated statuses and no type filter.
- Use the same evidence gate as `related`.
- Add initial identity step:
  - `role="decision"` when target type is `Decision`
  - `role="topic"` otherwise
  - `relationship_path=()`
  - evidence from resolved target entity evidence only
  - omit initial step with `graph_evidence_missing` if target entity evidence does not resolve
- Convert projection paths to `DecisionTraceStep`:
  - role from first relationship type in path
  - `relationship_status` from the strongest status in path; for mixed status use the lowest status weight label
  - explanation from `GraphPath.explanation`
- Sort by relationship type priority, then projection score/rank.

- [ ] **Step 5: Add `decision-trace` command**

In `src/vault_graph/cli/main.py`, add:

```python
@app.command("decision-trace")
def decision_trace(
    topic: str = typer.Argument(..., help="Decision entity, topic, path, alias, or entity ID."),
    state: Path = typer.Option(Path(".vault-graph"), "--state", help="Vault Graph state path."),
    vault_id: str | None = typer.Option(None, "--vault-id", help="Search one registered Vault ID."),
    all_vaults: bool = typer.Option(False, "--all-vaults", help="Search all enabled registered Vaults."),
    include_cross_vault: bool = typer.Option(False, "--include-cross-vault", help="Include explicit cross-Vault graph relationships."),
    limit: int = typer.Option(10, "--limit", help="Maximum trace steps."),
    output_format: str = typer.Option("text", "--format", help="Output format: text or json."),
) -> None:
    ...
```

Use the same scope validation as `related`.

- [ ] **Step 6: Add decision trace renderers**

Add:

```python
def _render_decision_trace_response(response: DecisionTraceResponse) -> None: ...
def _decision_trace_response_json(response: DecisionTraceResponse) -> dict[str, object]: ...
```

Text output must include:

- warnings first
- `topic`
- `trace_kind`
- resolved target
- projection version and build ID
- step count
- per step: rank, role, vault ID, entity name, status, evidence path/anchor

- [ ] **Step 7: Update CLI surface test**

Modify `tests/test_cli_surface_boundary.py` to assert:

- `related` is present
- `decision-trace` is present
- `ask`, MCP serving, HTTP serving, and context-pack commands remain absent

- [ ] **Step 8: Verify decision trace tests pass**

Run:

```bash
uv run --python 3.12 pytest tests/test_graph_retrieval_service.py tests/test_cli_decision_trace.py tests/test_cli_surface_boundary.py -q
```

Expected: PASS.

- [ ] **Step 9: Commit**

```bash
git add src/vault_graph/app/graph_retrieval_service.py src/vault_graph/cli/main.py tests/test_graph_retrieval_service.py tests/test_cli_decision_trace.py tests/test_cli_surface_boundary.py
git commit -m "feat(cli): add decision trace graph command"
```

### Task 9: Refactor RetrievalService To Public Candidate Seam

**Files:**

- Create: `src/vault_graph/retrieval/retrieval_candidate.py`
- Create: `src/vault_graph/retrieval/graph_candidates.py`
- Modify: `src/vault_graph/retrieval/retrieval_service.py`
- Modify: `src/vault_graph/retrieval/search_response.py`
- Modify: `src/vault_graph/retrieval/__init__.py`
- Test: `tests/test_retrieval_service_search.py`
- Test: `tests/test_search_response_contract.py`

- [ ] **Step 1: Write failing candidate seam tests**

Append to `tests/test_retrieval_service_search.py`:

```python
def test_retrieval_candidate_seam_preserves_signal_explanations(tmp_path: Path) -> None: ...
def test_search_without_include_graph_does_not_call_graph_candidate_provider(tmp_path: Path) -> None: ...
```

Use a fake graph provider:

```python
class FailingGraphCandidateProvider:
    def candidates(self, **_: object) -> GraphCandidateResult:
        raise AssertionError("graph provider must not be called by default search")
```

Use a deterministic graph provider:

```python
class StaticGraphCandidateProvider:
    def __init__(self, result: GraphCandidateResult) -> None:
        self.result = result

    def candidates(
        self,
        *,
        query_text: str,
        requested_scope: QueryScope,
        actual_scopes: tuple[QueryScope, ...],
        limit: int,
        include_cross_vault: bool,
    ) -> GraphCandidateResult:
        return self.result
```

- [ ] **Step 2: Add SearchRequest contract tests**

In `tests/test_search_response_contract.py`, assert:

```python
request = SearchRequest(
    query_text="GraphRAG",
    requested_scope=QueryScope(vault_ids=("default",), content_scopes=("wiki",)),
    actual_scopes=(QueryScope(vault_ids=("default",), content_scopes=("wiki",)),),
    limit=10,
    output_format="text",
    include_graph=True,
    include_cross_vault=False,
)
assert request.include_graph is True
```

- [ ] **Step 3: Run tests and verify failure**

Run:

```bash
uv run --python 3.12 pytest tests/test_retrieval_service_search.py tests/test_search_response_contract.py -q
```

Expected: FAIL because public candidate seam and graph request flags do not exist.

- [ ] **Step 4: Add retrieval candidate and graph provider contract modules**

Create `src/vault_graph/retrieval/retrieval_candidate.py` exactly as specified in "Retrieval Candidate Seam".

Create `src/vault_graph/retrieval/graph_candidates.py` with
`GraphCandidateResult`, `GraphCandidateProvider`, and `GraphSearchSource` as
specified in "Retrieval Candidate Seam". Do not add `GraphSearchCandidateProvider`
until Task 10.

- [ ] **Step 5: Extend SearchRequest**

Modify `src/vault_graph/retrieval/search_response.py`:

```python
@dataclass(frozen=True)
class SearchRequest:
    ...
    include_graph: bool = False
    include_cross_vault: bool = False
```

No extra validation is needed in this DTO beyond existing request validation. CLI and service enforce cross-Vault graph scope rules.

- [ ] **Step 6: Refactor candidate fusion**

In `src/vault_graph/retrieval/retrieval_service.py`:

- Replace private `_SignalCandidate` with existing public `RetrievalSignal`.
- Replace private `_FusedCandidate.signals` type with `tuple[RetrievalSignal, ...]`.
- Add private helpers:

```python
def _keyword_candidates(self, *, request: SearchRequest, candidate_limit: int) -> tuple[RetrievalCandidate, ...]: ...
def _vector_candidates(... ) -> tuple[RetrievalCandidate, ...]: ...
def _graph_candidates(self, *, request: SearchRequest, candidate_limit: int, warnings: list[SearchWarning]) -> tuple[RetrievalCandidate, ...]: ...
def _fuse_candidates(candidates: tuple[RetrievalCandidate, ...]) -> tuple[_FusedCandidate, ...]: ...
```

- Preserve reciprocal-rank-style scoring.
- Preserve keyword/vector behavior exactly when `include_graph=False`.
- Preserve graph signal explanations exactly in final `RetrievalSignal.explanation`.
- Add graph store revisions from `GraphCandidateResult.store_revisions` to `SearchResponse.store_revisions`.
- Add graph warnings from `GraphCandidateResult.warnings` to `SearchResponse.warnings`.
- Set `candidate_count` to total signal candidate rows before evidence resolution.

No `_retrieval_signal` adapter should be needed after this refactor; fused
candidates already contain `RetrievalSignal` records. Preserve each signal's
original `explanation`.

```python
signals=candidate.signals
```

- [ ] **Step 7: Export candidate seam**

Modify `src/vault_graph/retrieval/__init__.py` to export:

```python
GraphCandidateProvider
GraphCandidateResult
RetrievalCandidate
```

- [ ] **Step 8: Verify retrieval seam tests pass**

Run:

```bash
uv run --python 3.12 pytest tests/test_retrieval_service_search.py tests/test_search_response_contract.py -q
```

Expected: PASS.

- [ ] **Step 9: Commit**

```bash
git add src/vault_graph/retrieval/retrieval_candidate.py src/vault_graph/retrieval/graph_candidates.py src/vault_graph/retrieval/retrieval_service.py src/vault_graph/retrieval/search_response.py src/vault_graph/retrieval/__init__.py tests/test_retrieval_service_search.py tests/test_search_response_contract.py
git commit -m "feat(retrieval): expose shared retrieval candidate seam"
```

### Task 10: Add Graph Candidate Provider And Search Flags

**Files:**

- Modify: `src/vault_graph/retrieval/graph_candidates.py`
- Modify: `src/vault_graph/app/graph_retrieval_service.py`
- Modify: `src/vault_graph/cli/main.py`
- Modify: `src/vault_graph/retrieval/retrieval_service.py`
- Modify: `src/vault_graph/retrieval/__init__.py`
- Test: `tests/test_search_include_graph.py`
- Test: `tests/test_cli_search.py`

- [ ] **Step 1: Write failing graph search tests**

Create `tests/test_search_include_graph.py`:

```python
def test_search_include_graph_adds_graph_signal_without_hiding_keyword_signal(tmp_path: Path) -> None: ...
def test_search_include_graph_preserves_graph_signal_explanation(tmp_path: Path) -> None: ...
def test_search_graph_target_not_found_degrades_to_keyword_vector(tmp_path: Path) -> None: ...
def test_search_graph_query_failure_degrades_to_keyword_vector(tmp_path: Path) -> None: ...
def test_search_graph_missing_degrades_to_keyword_vector(tmp_path: Path) -> None: ...
def test_search_graph_empty_degrades_to_keyword_vector(tmp_path: Path) -> None: ...
def test_search_graph_stale_degrades_to_keyword_vector(tmp_path: Path) -> None: ...
def test_search_graph_incompatible_degrades_to_keyword_vector(tmp_path: Path) -> None: ...
def test_search_graph_unavailable_degrades_to_keyword_vector(tmp_path: Path) -> None: ...
def test_graph_signal_weight_does_not_outrank_stronger_direct_evidence(tmp_path: Path) -> None: ...
```

Expected behavior:

- final result signals can include `("keyword", "graph")`
- graph explanation mentions seed entity and relationship type
- warnings are top-level `SearchResponse.warnings`
- graph store revisions join `SearchResponse.store_revisions`
- keyword-only direct evidence remains ranked above a graph-only weak result when direct evidence score is stronger

- [ ] **Step 2: Add CLI search flag tests**

Modify `tests/test_cli_search.py`:

```python
def test_cli_search_without_include_graph_does_not_open_graph_store(tmp_path: Path, monkeypatch: MonkeyPatch) -> None: ...
def test_cli_search_include_graph_renders_graph_signal(tmp_path: Path, monkeypatch: MonkeyPatch) -> None: ...
def test_cli_search_include_cross_vault_requires_include_graph_and_all_vaults(tmp_path: Path) -> None: ...
```

The default no-graph test should monkeypatch graph opening to fail and then prove plain search still succeeds.

- [ ] **Step 3: Run tests and verify failure**

Run:

```bash
uv run --python 3.12 pytest tests/test_search_include_graph.py tests/test_cli_search.py -q
```

Expected: FAIL because graph candidate provider and CLI flags do not exist.

- [ ] **Step 4: Implement graph candidate provider**

Modify `src/vault_graph/retrieval/graph_candidates.py` to add the concrete
`GraphSearchCandidateProvider`.

Implement in these red-green substeps:

1. Provider request/response wiring:
   - Make `test_search_graph_target_not_found_degrades_to_keyword_vector` pass.
   - Run: `uv run --python 3.12 pytest tests/test_search_include_graph.py -q -k target_not_found`
2. Readiness degradation:
   - Make missing, empty, stale, incompatible, and unavailable degradation tests
     pass.
   - Run: `uv run --python 3.12 pytest tests/test_search_include_graph.py -q -k "missing or empty or stale or incompatible or unavailable"`
3. Graph signal conversion:
   - Make graph signal and explanation tests pass.
   - Run: `uv run --python 3.12 pytest tests/test_search_include_graph.py -q -k "graph_signal or explanation"`
4. Fusion weight behavior:
   - Make `test_graph_signal_weight_does_not_outrank_stronger_direct_evidence`
     pass.
   - Run: `uv run --python 3.12 pytest tests/test_search_include_graph.py -q -k weight`
5. CLI flag validation:
   - Implement CLI flags and run `uv run --python 3.12 pytest tests/test_cli_search.py -q -k graph`.

Add:

```python
class GraphSearchCandidateProvider:
    def __init__(self, *, graph_retrieval_service: GraphSearchSource) -> None:
        self._graph_retrieval_service = graph_retrieval_service

    def candidates(
        self,
        *,
        query_text: str,
        requested_scope: QueryScope,
        actual_scopes: tuple[QueryScope, ...],
        limit: int,
        include_cross_vault: bool,
    ) -> GraphCandidateResult:
        return self._graph_retrieval_service.graph_candidates_for_search(
            query_text=query_text,
            requested_scope=requested_scope,
            actual_scopes=actual_scopes,
            limit=limit,
            include_cross_vault=include_cross_vault,
        )
```

In `GraphRetrievalService.graph_candidates_for_search(...)`:

- Use `requested_scope` for readiness and warning attribution.
- Resolve `query_text` as graph target over `actual_scopes`.
- If no unique target, return no candidates with `graph_target_not_found` or `ambiguous_graph_target`.
- Use bounded related expansion.
- For each `RelatedItem`, create graph candidates only from relationship evidence chunks.
- Candidate identity is `(evidence.vault_id, evidence.document_id, evidence.chunk_id)`.
- Import `RetrievalSignal` from `vault_graph.retrieval.retrieval_result`.
- Signal:

```python
RetrievalSignal(
    kind="graph",
    source_id=f"graph:{relationship.source_vault_id}:{relationship.relationship_id}:{evidence.chunk_id}",
    rank=item.rank,
    score=item.score,
    backend="graph-projection-v1",
    index_revision=relationship.graph_index_revision,
    explanation=f"{seed.name} -> {item.entity.name} via {relationship.type}",
)
```

- Convert graph retrieval warnings to `SearchWarning`.
- Convert graph retrieval revisions to `SearchStoreRevision`.
- Catch `GraphStoreError` and return `graph_query_failed` warnings instead of raising.
- Catch graph-specific `SearchError` from readiness or graph retrieval inside
  `GraphCandidateProvider.candidates(...)` and convert it to a graph warning
  when keyword/metadata search has already passed readiness.
- Map graph readiness failures to warning codes:
  - missing or empty graph state: `graph_empty`
  - stale graph state: `graph_stale`
  - incompatible or unavailable graph state: `graph_unavailable`

- [ ] **Step 5: Wire graph provider into CLI search only when requested**

In `_search_service`, keep current no-graph behavior by default. Add a new helper:

```python
def _search_service(
    state: Path,
    *,
    include_graph: bool = False,
) -> tuple[CatalogService, VaultCatalog, RetrievalService]:
    ...
    graph_candidate_provider = None
    if include_graph:
        _, _, graph_service = _graph_retrieval_service(state)
        graph_candidate_provider = GraphSearchCandidateProvider(graph_retrieval_service=graph_service)
    return RetrievalService(..., graph_candidate_provider=graph_candidate_provider)
```

Plain search must not call `_graph_retrieval_service(state)`.

- [ ] **Step 6: Add CLI flags**

Modify `search(...)` command:

```python
include_graph: bool = typer.Option(False, "--include-graph", help="Include explicit graph retrieval signals."),
include_cross_vault: bool = typer.Option(False, "--include-cross-vault", help="Include explicit cross-Vault graph relationships."),
```

Validation:

- `include_cross_vault` requires `include_graph and all_vaults`.
- On invalid combination, print `include_cross_vault_requires_multi_vault_graph_scope` and exit `1`.

Pass flags to service:

```python
service.search(
    query_text=query,
    requested_scope=scope,
    limit=limit,
    output_format=output_format,
    include_graph=include_graph,
    include_cross_vault=include_cross_vault,
)
```

- [ ] **Step 7: Verify graph search tests pass**

Run:

```bash
uv run --python 3.12 pytest tests/test_search_include_graph.py tests/test_cli_search.py -q
```

Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add src/vault_graph/retrieval/graph_candidates.py src/vault_graph/app/graph_retrieval_service.py src/vault_graph/cli/main.py src/vault_graph/retrieval/retrieval_service.py src/vault_graph/retrieval/__init__.py tests/test_search_include_graph.py tests/test_cli_search.py
git commit -m "feat(search): add opt-in graph retrieval signals"
```

### Task 11: Harden Read-Only, Multi-Vault, And Import Boundaries

**Files:**

- Modify: `tests/test_graph_retrieval_read_only_boundary.py`
- Modify: `tests/test_multi_vault_graph_retrieval.py`
- Modify: `tests/test_retrieval_import_boundaries.py`
- Modify: `tests/test_package_import.py`

- [ ] **Step 1: Add read-only regression cases**

Add tests proving:

- `vg related` does not create missing `metadata.sqlite3`.
- `vg related` does not create missing `graph.sqlite3`.
- `vg related` does not create vector, keyword, embedding-cache, graph-status,
  or projection-cache state.
- `vg decision-trace` does not create metadata, vector, keyword, graph,
  embedding-cache, graph-status, or projection-cache state.
- `vg search --include-graph` does not create metadata, vector, keyword, graph,
  embedding-cache, graph-status, or projection-cache state.
- `vg related` does not create `data/projection_cache/`.
- `vg decision-trace` does not create any projection cache.
- `vg search --include-graph` does not auto-index.
- plain `vg search` does not open graph store or projection modules.

Use a before/after state-tree helper:

```python
def state_tree(path: Path) -> tuple[str, ...]:
    if not path.exists():
        return ()
    return tuple(sorted(str(child.relative_to(path)) for child in path.rglob("*")))
```

For each read-only command, capture `before = state_tree(state)` before the
command and assert `state_tree(state) == before` after the command when stores
are missing. Keep the catalog file created by `vg init` outside the command
under test.

- [ ] **Step 2: Add multi-vault regression cases**

Add tests proving:

- target candidates are keyed by `(vault_id, entity_id)`.
- `--all-vaults --include-cross-vault` with same-name targets still returns
  `ambiguous_graph_target`; include-cross-vault permits relationships after a
  unique target is selected, not implicit multi-seed traversal.
- relationship output preserves `(source_vault_id, relationship_id)`.
- evidence output preserves `(vault_id, document_id, chunk_id)`.
- stale graph state in one Vault produces warning for that Vault only.
- fresh graph state in another selected Vault can still produce results.

- [ ] **Step 3: Add import boundary tests**

Modify `tests/test_retrieval_import_boundaries.py`:

- CLI may import `GraphRetrievalService` and response DTOs.
- CLI must not import rustworkx directly.
- `GraphProjection` must not import SQLite stores.
- `GraphRetrievalService` may import interfaces, not local SQLite helpers.
- `RetrievalService` may depend on `GraphCandidateProvider`, not `SQLiteGraphStore`.

- [ ] **Step 4: Run boundary tests and verify failure or pass**

Run:

```bash
uv run --python 3.12 pytest tests/test_graph_retrieval_read_only_boundary.py tests/test_multi_vault_graph_retrieval.py tests/test_retrieval_import_boundaries.py tests/test_package_import.py -q
```

Expected: PASS after any necessary small boundary fixes.

- [ ] **Step 5: Commit**

```bash
git add tests/test_graph_retrieval_read_only_boundary.py tests/test_multi_vault_graph_retrieval.py tests/test_retrieval_import_boundaries.py tests/test_package_import.py
git commit -m "test(graph): harden graph retrieval boundaries"
```

### Task 12: Final Verification

**Files:**

- No new production files expected unless previous tasks reveal a defect.

- [ ] **Step 1: Run targeted graph and retrieval suite**

Run:

```bash
uv run --python 3.12 pytest \
  tests/test_graph_query_contract.py \
  tests/test_graph_store_contract.py \
  tests/test_sqlite_graph_store.py \
  tests/test_graph_projection.py \
  tests/test_graph_retrieval_contract.py \
  tests/test_graph_retrieval_service.py \
  tests/test_cli_related.py \
  tests/test_cli_decision_trace.py \
  tests/test_search_include_graph.py \
  tests/test_graph_retrieval_read_only_boundary.py \
  tests/test_multi_vault_graph_retrieval.py \
  tests/test_retrieval_service_search.py \
  tests/test_cli_search.py \
  -q
```

Expected: PASS.

- [ ] **Step 2: Run full test suite**

Run:

```bash
uv run --python 3.12 pytest -q
```

Expected: PASS.

- [ ] **Step 3: Run lint**

Run:

```bash
uv run --python 3.12 ruff check src tests
```

Expected: PASS.

- [ ] **Step 4: Run typing**

Run:

```bash
uv run --python 3.12 mypy src
uv run --python 3.12 mypy tests
```

Expected: PASS.

- [ ] **Step 5: Run formatting drift check**

Run:

```bash
git diff --check
```

Expected: no output and exit code `0`.

- [ ] **Step 6: Manual behavior smoke checks**

Run against a small temporary Vault:

```bash
rm -rf /tmp/vault-graph-smoke-vault /tmp/vault-graph-smoke-state
mkdir -p /tmp/vault-graph-smoke-vault/wiki/decisions
cat > /tmp/vault-graph-smoke-vault/wiki/graphrag.md <<'EOF'
---
title: GraphRAG
tags: [GraphRAG, Retrieval]
depends_on: decisions/use-graphrag.md
---

# GraphRAG

GraphRAG connects graph relationships with evidence-first retrieval.
EOF
cat > /tmp/vault-graph-smoke-vault/wiki/decisions/use-graphrag.md <<'EOF'
---
type: decision
title: Use GraphRAG
related: ../graphrag.md
---

# Use GraphRAG

Decision: use GraphRAG when relationship evidence improves retrieval context.
EOF
uv run --python 3.12 vg init --vault /tmp/vault-graph-smoke-vault --state /tmp/vault-graph-smoke-state
uv run --python 3.12 vg index --state /tmp/vault-graph-smoke-state
uv run --python 3.12 vg related --state /tmp/vault-graph-smoke-state GraphRAG
uv run --python 3.12 vg decision-trace --state /tmp/vault-graph-smoke-state GraphRAG
uv run --python 3.12 vg search --state /tmp/vault-graph-smoke-state "GraphRAG"
uv run --python 3.12 vg search --state /tmp/vault-graph-smoke-state "GraphRAG" --include-graph
```

Expected:

- graph commands return evidence-linked results or clear warnings
- plain search output does not include graph-specific signals
- include-graph search can include `graph` signals when graph is fresh
- no files are written under the registered Vault root

- [ ] **Step 7: Final commit**

```bash
git status --short
git add -A
git commit -m "feat(graph): add phase 3c graph retrieval"
```

## Completion Checklist

- [ ] `GraphStore` query methods are reusable by SQLite and future graph backends.
- [ ] `GraphProjection` is bounded, deterministic, and disposable.
- [ ] `GraphRetrievalService` is the single deep module for graph retrieval orchestration.
- [ ] `vg related` returns evidence-linked related items.
- [ ] `vg decision-trace` returns trace steps, not synthesized answers.
- [ ] plain `vg search "query"` does not read graph state.
- [ ] `vg search "query" --include-graph` adds graph signals only when explicitly requested.
- [ ] relationship evidence is required before graph paths enter ranking or search fusion.
- [ ] multi-vault and cross-Vault output preserve Vault-scoped identities.
- [ ] graph commands and graph search never mutate Vault content.
- [ ] graph commands and graph search never create projection-cache files.
- [ ] `uv run --python 3.12 pytest -q` passes.
- [ ] `uv run --python 3.12 ruff check src tests` passes.
- [ ] `uv run --python 3.12 mypy src` passes.
- [ ] `uv run --python 3.12 mypy tests` passes.
- [ ] `git diff --check` passes.
