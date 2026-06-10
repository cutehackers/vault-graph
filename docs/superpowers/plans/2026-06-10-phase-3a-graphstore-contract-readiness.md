# Phase 3A GraphStore Contract And Readiness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the Phase 3A contract-readiness slice: graph record contracts, deterministic graph identities, a reusable `GraphStore` interface, local SQLite graph persistence, and `vg status` graph readiness without graph extraction, traversal, ranking, or graph search.

**Architecture:** Phase 3A is a storage and readiness boundary. Immutable graph contract records live under `vault_graph.graph`; application code reads graph readiness through an app-level service; storage consumers depend on `GraphStore`, with `SQLiteGraphStore` as the local reference backend and `InMemoryGraphStore` as the contract fake.

**Tech Stack:** Python 3.12, dataclasses, Protocol interfaces, SQLite, Typer CLI, pytest, ruff, mypy.

---

## Source Documents

Read these before implementation:

- `docs/SPEC.md`
- `docs/DESIGN.md`
- `docs/FEATURES.md`
- `docs/DECISIONS.md`
- `docs/CONVENTIONS.md`
- `docs/superpowers/specs/phase-3/README.md`
- `docs/superpowers/specs/phase-3/CONTEXT.md`
- `docs/superpowers/specs/phase-3/2026-06-10-phase-3-overview-design.md`
- `docs/superpowers/specs/phase-3/2026-06-10-phase-3a-graphstore-contract-readiness-design.md`

The implementation request mentioned `docs/superpowers/spec/phase-3/`. The
accepted repo path is `docs/superpowers/specs/phase-3/`.

## Scope Guardrails

Phase 3A implements:

- immutable graph contract records
- deterministic graph ID helpers
- graph domain errors
- `GraphStore` protocol
- in-memory graph store fake for contract tests
- SQLite graph store reference backend
- graph extraction spec default compatibility boundary
- graph manifests, revisions, tombstones, and apply result records
- `GraphReadiness` and app-level `ReadOnlyGraphReadiness`
- `vg status` graph readiness fields in text output
- `vg status --format json` machine-readable metadata/vector/graph status

Phase 3A must not implement:

- entity extraction execution
- relationship extraction execution
- `GraphIndexer`
- graph writes during `vg index`
- rustworkx `GraphProjection`
- `vg related`
- `vg decision-trace`
- `vg search --include-graph`
- graph ranking
- graph node or edge embeddings
- LLM-assisted extraction
- Neo4j
- cross-Vault entity merging
- Vault file mutation

Release-ready Phase 3A means a user can run:

```bash
vg init --vault /path/to/vault
vg status
vg status --format json
```

and see graph backend readiness without creating graph state, projection cache
state, model cache state, or modifying Vault files.

## Implementation Assumptions

- `GraphReadinessService` is implemented as `ReadOnlyGraphReadiness` in
  `src/vault_graph/app/graph_readiness_service.py`, mirroring the existing
  `ReadOnlySearchReadiness` app-layer pattern.
- `src/vault_graph/graph/graph_readiness.py` owns `GraphReadiness`,
  `GraphLineageSnapshot`, and related typed status records.
- The current expected `GraphExtractionSpec` is a small hard-coded default in
  `src/vault_graph/graph/graph_contracts.py`. Phase 3A does not add a graph
  extraction config file.
- `SQLiteGraphStore.open_read_only(path)` never creates directories or files.
- `SQLiteGraphStore.open_writable(path)` creates the local graph database only
  when called by tests or future Phase 3B indexing.
- `GraphStore.latest_revisions(scopes)` and `GraphStore.current_manifest(scopes)`
  require effective scopes: each supplied `QueryScope` must contain exactly one
  `vault_id`.
- `GraphManifest` includes records through explicit graph record scope
  memberships. Readiness then resolves evidence refs through `MetadataStore`
  before claiming freshness. Graph records without evidence refs are invalid.
- `vg status --format json` is added because the Phase 3A design requires a
  machine-readable status surface for agents.

## File Structure

Create:

- `src/vault_graph/graph/__init__.py`: exports public graph contracts.
- `src/vault_graph/graph/graph_contracts.py`: immutable graph record dataclasses, default graph extraction spec, and validation helpers.
- `src/vault_graph/graph/graph_identity.py`: deterministic ID and scope-key helpers.
- `src/vault_graph/graph/graph_readiness.py`: graph readiness, freshness, and lineage dataclasses.
- `src/vault_graph/app/graph_readiness_service.py`: app-level readiness comparison over `MetadataStore` and `GraphStore`.
- `src/vault_graph/storage/interfaces/graph_store.py`: `GraphStore` protocol and identity lookup records.
- `src/vault_graph/storage/local/sqlite_graph_store.py`: SQLite-backed local reference `GraphStore`.
- `tests/fakes/in_memory_graph_store.py`: in-memory graph store fake that satisfies the same contract tests.
- `tests/test_graph_contracts.py`
- `tests/test_graph_store_contract.py`
- `tests/test_sqlite_graph_store.py`
- `tests/test_graph_readiness.py`
- `tests/test_cli_graph_status.py`
- `tests/test_multi_vault_graph_identity.py`

Modify:

- `src/vault_graph/errors.py`: add graph domain error hierarchy.
- `src/vault_graph/storage/interfaces/__init__.py`: export graph store contracts.
- `src/vault_graph/storage/local/__init__.py`: export `SQLiteGraphStore` if local exports are already used by tests.
- `src/vault_graph/app/catalog_service.py`: add `graph_path`.
- `src/vault_graph/app/index_service.py`: include graph readiness in status reports without graph indexing.
- `src/vault_graph/cli/main.py`: wire graph store/readiness into `status`, add `--format text|json`, and render graph fields.
- Existing CLI status tests: assert graph status remains visible and read-only.

Do not modify `docs/DECISIONS.md` unless implementation review identifies a
new policy decision requiring user approval. Review-driven implementation-plan
corrections go to `docs/PATCH_LOG.md`.

## Runtime Data Flow

Status text flow:

```text
vg status
  -> CatalogService.load_catalog()
  -> resolve requested QueryScope
  -> effective_query_scopes(catalog, scope)
  -> SQLiteMetadataStore(read-only)
  -> ChromaVectorStore(read-only)
  -> SQLiteGraphStore.open_read_only(graph_path)
  -> ReadOnlyGraphReadiness.check(requested_scope, effective_scopes)
  -> render metadata/vector/graph fields
```

Status JSON flow:

```text
vg status --format json
  -> same service path
  -> explicit serializer
  -> JSON with metadata, vector, graph, vaults, and selected scope
```

Future Phase 3B write flow enabled by contracts only:

```text
GraphIndexer
  -> GraphReconcilePlan
  -> GraphStore.apply_reconcile_plan(plan)
  -> GraphApplyResult
```

Phase 3A must not call this future write flow from `vg index`.

## Error Handling

Add graph errors under `VaultGraphError`:

- `GraphStoreError`: base graph persistence/contract error
- `GraphStoreUnavailable`: backend cannot be opened or queried
- `GraphSchemaIncompatible`: schema cannot be safely read
- `GraphReadOnlyViolation`: write attempted through read-only store
- `GraphRecordInvalid`: graph record violates the contract

Use exceptions for invalid records and illegal writes. Use `GraphReadiness` for
normal operational states: `missing`, `empty`, `fresh`, `stale`,
`incompatible`, and `unavailable`.

`vg status` must not fail because graph state is missing. It should fail only
for catalog/scope errors or unexpected domain errors that already fail status
today.

---

### Task 1: Add Graph Contracts And Identity Helpers

**Files:**

- Create: `src/vault_graph/graph/__init__.py`
- Create: `src/vault_graph/graph/graph_contracts.py`
- Create: `src/vault_graph/graph/graph_identity.py`
- Modify: `src/vault_graph/errors.py`
- Test: `tests/test_graph_contracts.py`
- Test: `tests/test_multi_vault_graph_identity.py`

- [ ] **Step 1: Write failing graph contract tests**

Create `tests/test_graph_contracts.py`:

```python
from dataclasses import FrozenInstanceError

import pytest

from vault_graph.errors import GraphRecordInvalid
from vault_graph.graph.graph_contracts import (
    GraphEvidenceRef,
    GraphExtractionSpec,
    RelationshipRecord,
    current_graph_extraction_spec,
)
from vault_graph.graph.graph_identity import (
    stable_entity_id,
    stable_evidence_ref_id,
    stable_relationship_id,
)


def test_current_graph_extraction_spec_has_canonical_digest() -> None:
    spec = current_graph_extraction_spec()

    assert spec.spec_version == "graph-extraction-spec-v1"
    assert len(spec.spec_digest) == 64
    assert spec.spec_digest == GraphExtractionSpec.from_payload(spec.payload()).spec_digest


def test_entity_id_is_stable_and_vault_scoped() -> None:
    first = stable_entity_id(
        vault_id="first",
        entity_type="concept",
        normalized_name="graphrag",
        canonical_path="wiki/graphrag.md",
    )
    second = stable_entity_id(
        vault_id="second",
        entity_type="concept",
        normalized_name="graphrag",
        canonical_path="wiki/graphrag.md",
    )

    assert first == stable_entity_id(
        vault_id="first",
        entity_type="concept",
        normalized_name="graphrag",
        canonical_path="wiki/graphrag.md",
    )
    assert first != second


def test_relationship_id_includes_source_and_target_vaults() -> None:
    left = stable_relationship_id(
        relationship_type="depends_on",
        source_vault_id="first",
        source_entity_id="source",
        target_vault_id="second",
        target_entity_id="target",
    )
    reversed_edge = stable_relationship_id(
        relationship_type="depends_on",
        source_vault_id="second",
        source_entity_id="target",
        target_vault_id="first",
        target_entity_id="source",
    )

    assert left != reversed_edge


def test_evidence_ref_requires_owner_and_evidence_vault_identity() -> None:
    evidence_ref_id = stable_evidence_ref_id(
        owner_kind="relationship",
        owner_vault_id="first",
        owner_id="rel-1",
        evidence_vault_id="second",
        document_id="doc-1",
        chunk_id="chunk-1",
        anchor="decision",
    )
    ref = GraphEvidenceRef(
        evidence_ref_id=evidence_ref_id,
        owner_kind="relationship",
        owner_vault_id="first",
        owner_id="rel-1",
        evidence_vault_id="second",
        document_id="doc-1",
        chunk_id="chunk-1",
        content_hash="chunk-hash",
        section="Decision",
        anchor="decision",
        path="wiki/decision.md",
        excerpt="rendering hint",
    )

    assert ref.evidence_ref_id == evidence_ref_id
    assert ref.owner_kind == "relationship"
    assert ref.evidence_vault_id == "second"


def test_invalid_relationship_status_is_rejected() -> None:
    evidence = GraphEvidenceRef(
        evidence_ref_id="evidence",
        owner_kind="relationship",
        owner_vault_id="default",
        owner_id="rel",
        evidence_vault_id="default",
        document_id="doc",
        chunk_id="chunk",
        content_hash="chunk-hash",
        section=None,
        anchor=None,
        path="wiki/page.md",
        excerpt=None,
    )

    with pytest.raises(GraphRecordInvalid, match="unsupported relationship status"):
        RelationshipRecord(
            relationship_id="rel",
            type="depends_on",
            source_vault_id="default",
            source_entity_id="source",
            target_vault_id="default",
            target_entity_id="target",
            evidence_refs=(evidence,),
            status="confirmed",
            confidence=0.8,
            extraction_method="test",
            graph_extraction_spec_version="graph-extraction-spec-v1",
            graph_extraction_spec_digest="0" * 64,
            created_at="2026-06-10T00:00:00+00:00",
            updated_at="2026-06-10T00:00:00+00:00",
            graph_index_revision="graph-1",
        )


def test_graph_records_are_immutable() -> None:
    spec = current_graph_extraction_spec()

    with pytest.raises(FrozenInstanceError):
        spec.__setattr__("spec_version", "changed")
```

Create `tests/test_multi_vault_graph_identity.py`:

```python
from vault_graph.graph.graph_contracts import EntityRecord, GraphEvidenceRef, RelationshipRecord
from vault_graph.graph.graph_identity import graph_scope_key, stable_entity_id, stable_evidence_ref_id, stable_relationship_id
from vault_graph.ingestion.vault_catalog import QueryScope


def test_same_entity_name_in_two_vaults_does_not_collide() -> None:
    first = stable_entity_id(
        vault_id="first",
        entity_type="concept",
        normalized_name="retrieval",
        canonical_path="wiki/retrieval.md",
    )
    second = stable_entity_id(
        vault_id="second",
        entity_type="concept",
        normalized_name="retrieval",
        canonical_path="wiki/retrieval.md",
    )

    assert first != second


def test_cross_vault_relationship_preserves_source_target_and_evidence_vaults() -> None:
    source = stable_entity_id(
        vault_id="first",
        entity_type="system",
        normalized_name="vault graph",
        canonical_path="wiki/vault-graph.md",
    )
    target = stable_entity_id(
        vault_id="second",
        entity_type="concept",
        normalized_name="context pack",
        canonical_path="wiki/context-pack.md",
    )
    relationship_id = stable_relationship_id(
        relationship_type="references",
        source_vault_id="first",
        source_entity_id=source,
        target_vault_id="second",
        target_entity_id=target,
    )
    evidence = GraphEvidenceRef(
        evidence_ref_id=stable_evidence_ref_id(
            owner_kind="relationship",
            owner_vault_id="first",
            owner_id=relationship_id,
            evidence_vault_id="second",
            document_id="doc",
            chunk_id="chunk",
            anchor=None,
        ),
        owner_kind="relationship",
        owner_vault_id="first",
        owner_id=relationship_id,
        evidence_vault_id="second",
        document_id="doc",
        chunk_id="chunk",
        content_hash="hash",
        section=None,
        anchor=None,
        path="wiki/context-pack.md",
        excerpt=None,
    )

    relationship = RelationshipRecord(
        relationship_id=relationship_id,
        type="references",
        source_vault_id="first",
        source_entity_id=source,
        target_vault_id="second",
        target_entity_id=target,
        evidence_refs=(evidence,),
        status="stated",
        confidence=1.0,
        extraction_method="test",
        graph_extraction_spec_version="graph-extraction-spec-v1",
        graph_extraction_spec_digest="0" * 64,
        created_at="2026-06-10T00:00:00+00:00",
        updated_at="2026-06-10T00:00:00+00:00",
        graph_index_revision="graph-1",
    )

    assert relationship.source_vault_id == "first"
    assert relationship.target_vault_id == "second"
    assert relationship.evidence_refs[0].evidence_vault_id == "second"


def test_graph_scope_key_includes_cross_vault_policy() -> None:
    local = QueryScope(vault_ids=("first",), content_scopes=("wiki",), include_cross_vault=False)
    cross = QueryScope(vault_ids=("first",), content_scopes=("wiki",), include_cross_vault=True)

    assert graph_scope_key(local) == "first:wiki:local"
    assert graph_scope_key(cross) == "first:wiki:cross"
```

- [ ] **Step 2: Verify the tests fail**

Run:

```bash
uv run --python 3.12 pytest tests/test_graph_contracts.py tests/test_multi_vault_graph_identity.py -q
```

Expected: FAIL because graph modules and graph errors do not exist.

- [ ] **Step 3: Add graph domain errors**

Add to `src/vault_graph/errors.py`:

```python
class GraphStoreError(VaultGraphError):
    """Raised when graph store contracts are violated."""


class GraphStoreUnavailable(GraphStoreError):
    """Raised when graph state cannot be opened or queried."""


class GraphSchemaIncompatible(GraphStoreError):
    """Raised when graph state has an incompatible schema."""


class GraphReadOnlyViolation(GraphStoreError):
    """Raised when a graph write is attempted through a read-only store."""


class GraphRecordInvalid(GraphStoreError):
    """Raised when a graph record violates the public graph contract."""
```

- [ ] **Step 4: Add deterministic graph identity helpers**

Create `src/vault_graph/graph/graph_identity.py`:

```python
from __future__ import annotations

from vault_graph.ingestion.document_normalizer import stable_id
from vault_graph.ingestion.vault_catalog import QueryScope


def normalize_entity_name(name: str) -> str:
    return " ".join(name.casefold().strip().split())


def stable_entity_id(
    *,
    vault_id: str,
    entity_type: str,
    normalized_name: str,
    canonical_path: str | None,
) -> str:
    return stable_id("entity", vault_id, entity_type, normalized_name, canonical_path or "")


def stable_relationship_id(
    *,
    relationship_type: str,
    source_vault_id: str,
    source_entity_id: str,
    target_vault_id: str,
    target_entity_id: str,
) -> str:
    return stable_id(
        "relationship",
        relationship_type,
        source_vault_id,
        source_entity_id,
        target_vault_id,
        target_entity_id,
    )


def stable_evidence_ref_id(
    *,
    owner_kind: str,
    owner_vault_id: str,
    owner_id: str,
    evidence_vault_id: str,
    document_id: str,
    chunk_id: str,
    anchor: str | None,
) -> str:
    return stable_id(
        "graph-evidence",
        owner_kind,
        owner_vault_id,
        owner_id,
        evidence_vault_id,
        document_id,
        chunk_id,
        anchor or "",
    )


def stable_graph_tombstone_id(*, record_kind: str, record_vault_id: str, record_id: str, effective_scope: str) -> str:
    return stable_id("graph-tombstone", record_kind, record_vault_id, record_id, effective_scope)


def graph_scope_key(scope: QueryScope) -> str:
    cross_vault = "cross" if scope.include_cross_vault else "local"
    return f"{','.join(scope.vault_ids)}:{','.join(scope.content_scopes)}:{cross_vault}"


def require_effective_graph_scope(scope: QueryScope) -> None:
    if len(scope.vault_ids) != 1:
        raise ValueError("GraphStore operations require per-Vault effective scopes")
```

- [ ] **Step 5: Add graph contract dataclasses**

Create `src/vault_graph/graph/graph_contracts.py` with immutable dataclasses for:

- `GraphExtractionSpec`
- `GraphEvidenceRef`
- `EntityRecord`
- `RelationshipRecord`
- `GraphRevision`
- `GraphTombstone`
- `GraphRecordScope`
- `GraphManifestEntity`
- `GraphManifestRelationship`
- `GraphManifestEvidence`
- `GraphManifest`
- `GraphApplyResult`
- `GraphReconcilePlan`

Use these validation rules:

```python
import hashlib
import json
from dataclasses import dataclass

OWNER_KINDS = ("entity", "relationship")
ENTITY_STATUSES = ("active", "tombstoned")
RELATIONSHIP_STATUSES = ("stated", "inferred", "contested", "deprecated")
TOMBSTONE_RECORD_KINDS = ("entity", "relationship")


def _require_non_empty(value: str, field_name: str) -> None:
    if not value:
        raise GraphRecordInvalid(f"{field_name} is required")


def _require_digest(value: str, field_name: str) -> None:
    _require_non_empty(value, field_name)
    if len(value) != 64:
        raise GraphRecordInvalid(f"{field_name} must be a sha256 digest")
```

`GraphExtractionSpec` must expose:

```python
@classmethod
def from_payload(cls, payload: dict[str, object]) -> GraphExtractionSpec:
    serialized_spec = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    spec_digest = hashlib.sha256(serialized_spec.encode("utf-8")).hexdigest()
    return cls(
        spec_version=str(payload["spec_version"]),
        spec_digest=spec_digest,
        entity_schema_version=str(payload["entity_schema_version"]),
        relationship_schema_version=str(payload["relationship_schema_version"]),
        entity_extractor_name=str(payload["entity_extractor_name"]),
        entity_extractor_version=str(payload["entity_extractor_version"]),
        relationship_extractor_name=str(payload["relationship_extractor_name"]),
        relationship_extractor_version=str(payload["relationship_extractor_version"]),
        relationship_status_rules_version=str(payload["relationship_status_rules_version"]),
        confidence_rules_version=str(payload["confidence_rules_version"]),
        serialized_spec=serialized_spec,
    )

def payload(self) -> dict[str, object]:
    loaded = json.loads(self.serialized_spec)
    if not isinstance(loaded, dict):
        raise GraphRecordInvalid("serialized_spec must decode to a mapping")
    return loaded
```

The default spec is:

```python
def current_graph_extraction_spec() -> GraphExtractionSpec:
    return GraphExtractionSpec.from_payload(
        {
            "spec_version": "graph-extraction-spec-v1",
            "entity_schema_version": "entity-schema-v1",
            "relationship_schema_version": "relationship-schema-v1",
            "entity_extractor_name": "phase-3b-local-entity-extractor",
            "entity_extractor_version": "contract-v1",
            "relationship_extractor_name": "phase-3b-local-relationship-extractor",
            "relationship_extractor_version": "contract-v1",
            "relationship_status_rules_version": "relationship-status-rules-v1",
            "confidence_rules_version": "confidence-rules-v1",
        }
    )
```

Implementation detail: `from_payload(payload)` must canonicalize with
`json.dumps(payload, sort_keys=True, separators=(",", ":"))` and compute
`sha256(serialized_spec.encode("utf-8")).hexdigest()`.

Add these exact public record shapes after `GraphExtractionSpec`:

```python
@dataclass(frozen=True)
class GraphEvidenceRef:
    evidence_ref_id: str
    owner_kind: str
    owner_vault_id: str
    owner_id: str
    evidence_vault_id: str
    document_id: str
    chunk_id: str
    content_hash: str
    section: str | None = None
    anchor: str | None = None
    path: str | None = None
    excerpt: str | None = None


@dataclass(frozen=True)
class EntityRecord:
    vault_id: str
    entity_id: str
    type: str
    name: str
    normalized_name: str
    aliases: tuple[str, ...]
    canonical_path: str | None
    evidence_refs: tuple[GraphEvidenceRef, ...]
    confidence: float
    extraction_method: str
    graph_extraction_spec_version: str
    graph_extraction_spec_digest: str
    status: str
    created_at: str
    updated_at: str
    graph_index_revision: str


@dataclass(frozen=True)
class RelationshipRecord:
    relationship_id: str
    type: str
    source_vault_id: str
    source_entity_id: str
    target_vault_id: str
    target_entity_id: str
    evidence_refs: tuple[GraphEvidenceRef, ...]
    status: str
    confidence: float
    extraction_method: str
    graph_extraction_spec_version: str
    graph_extraction_spec_digest: str
    created_at: str
    updated_at: str
    graph_index_revision: str


@dataclass(frozen=True)
class GraphRevision:
    graph_run_id: str
    vault_id: str
    effective_scope: str
    graph_store_schema_version: str
    graph_extraction_spec_version: str
    graph_extraction_spec_digest: str
    graph_index_revision: str
    metadata_index_revision: str
    parser_version: str
    chunker_version: str
    entity_count: int
    relationship_count: int
    stale_count: int
    tombstone_count: int
    updated_at: str


@dataclass(frozen=True)
class GraphTombstone:
    tombstone_id: str
    record_kind: str
    record_vault_id: str
    record_id: str
    effective_scope: str
    reason: str
    graph_run_id: str
    graph_index_revision: str
    graph_extraction_spec_version: str
    graph_extraction_spec_digest: str
    tombstoned_at: str


@dataclass(frozen=True)
class GraphRecordScope:
    record_kind: str
    record_vault_id: str
    record_id: str
    effective_scope: str
    metadata_index_revision: str
    graph_index_revision: str
    graph_extraction_spec_digest: str
```

Add these manifest and apply shapes:

```python
@dataclass(frozen=True)
class GraphManifestEntity:
    vault_id: str
    entity_id: str
    evidence_ref_ids: tuple[str, ...]
    evidence_content_hashes: tuple[str, ...]
    status: str
    graph_extraction_spec_digest: str
    metadata_index_revision: str
    graph_index_revision: str


@dataclass(frozen=True)
class GraphManifestRelationship:
    source_vault_id: str
    source_entity_id: str
    target_vault_id: str
    target_entity_id: str
    relationship_id: str
    type: str
    status: str
    evidence_ref_ids: tuple[str, ...]
    evidence_content_hashes: tuple[str, ...]
    graph_extraction_spec_digest: str
    metadata_index_revision: str
    graph_index_revision: str


@dataclass(frozen=True)
class GraphManifestEvidence:
    evidence_ref_id: str
    owner_kind: str
    owner_vault_id: str
    owner_id: str
    evidence_vault_id: str
    document_id: str
    chunk_id: str
    content_hash: str
    anchor: str | None


@dataclass(frozen=True)
class GraphManifest:
    requested_scope: QueryScope
    effective_scopes: tuple[QueryScope, ...]
    entity_rows: tuple[GraphManifestEntity, ...]
    relationship_rows: tuple[GraphManifestRelationship, ...]
    evidence_rows: tuple[GraphManifestEvidence, ...]
    tombstone_rows: tuple[GraphTombstone, ...]
    graph_store_schema_version: str
    graph_extraction_spec_version: str
    graph_extraction_spec_digest: str
    revision_rows: tuple[GraphRevision, ...]


@dataclass(frozen=True)
class GraphApplyResult:
    graph_run_id: str
    applied_entity_upsert_count: int
    applied_relationship_upsert_count: int
    applied_evidence_ref_upsert_count: int
    applied_tombstone_count: int
    graph_revision_rows: tuple[GraphRevision, ...]
    warnings: tuple[str, ...]


@dataclass(frozen=True)
class GraphReconcilePlan:
    requested_scope: QueryScope
    effective_scopes: tuple[QueryScope, ...]
    graph_run_id: str
    entity_upserts: tuple[EntityRecord, ...]
    relationship_upserts: tuple[RelationshipRecord, ...]
    evidence_ref_upserts: tuple[GraphEvidenceRef, ...]
    entity_tombstones: tuple[GraphTombstone, ...]
    relationship_tombstones: tuple[GraphTombstone, ...]
    graph_revision_rows: tuple[GraphRevision, ...]
    graph_extraction_spec: GraphExtractionSpec
    projection_cache_invalidations: tuple[str, ...]
```

Validation requirements:

- `EntityRecord.evidence_refs` and `RelationshipRecord.evidence_refs` must be non-empty.
- Entity evidence refs must use `owner_kind="entity"`, `owner_vault_id=entity.vault_id`, and `owner_id=entity.entity_id`.
- Relationship evidence refs must use `owner_kind="relationship"`, `owner_vault_id=relationship.source_vault_id`, and `owner_id=relationship.relationship_id`.
- Relationship status must be one of `stated`, `inferred`, `contested`, or `deprecated`.
- `GraphManifest*` tuple fields must be immutable tuples.
- `GraphReconcilePlan` effective scopes must be per-Vault scopes; `GraphStore` may reject global multi-vault scopes.

- [ ] **Step 6: Export graph contracts**

Create `src/vault_graph/graph/__init__.py`:

```python
"""Graph contracts for derived entity and relationship state."""

from vault_graph.graph.graph_contracts import (
    EntityRecord,
    GraphApplyResult,
    GraphEvidenceRef,
    GraphExtractionSpec,
    GraphManifest,
    GraphManifestEntity,
    GraphManifestEvidence,
    GraphManifestRelationship,
    GraphRecordScope,
    GraphReconcilePlan,
    GraphRevision,
    GraphTombstone,
    RelationshipRecord,
    current_graph_extraction_spec,
)
from vault_graph.graph.graph_identity import (
    graph_scope_key,
    normalize_entity_name,
    stable_entity_id,
    stable_evidence_ref_id,
    stable_graph_tombstone_id,
    stable_relationship_id,
)

__all__ = [
    "EntityRecord",
    "GraphApplyResult",
    "GraphEvidenceRef",
    "GraphExtractionSpec",
    "GraphManifest",
    "GraphManifestEntity",
    "GraphManifestEvidence",
    "GraphManifestRelationship",
    "GraphRecordScope",
    "GraphReconcilePlan",
    "GraphRevision",
    "GraphTombstone",
    "RelationshipRecord",
    "current_graph_extraction_spec",
    "graph_scope_key",
    "normalize_entity_name",
    "stable_entity_id",
    "stable_evidence_ref_id",
    "stable_graph_tombstone_id",
    "stable_relationship_id",
]
```

- [ ] **Step 7: Verify graph contract tests pass**

Run:

```bash
uv run --python 3.12 pytest tests/test_graph_contracts.py tests/test_multi_vault_graph_identity.py -q
```

Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add src/vault_graph/graph src/vault_graph/errors.py tests/test_graph_contracts.py tests/test_multi_vault_graph_identity.py
git commit -m "feat: add graph record contracts"
```

---

### Task 2: Add GraphStore Interface And In-Memory Contract Fake

**Files:**

- Create: `src/vault_graph/storage/interfaces/graph_store.py`
- Modify: `src/vault_graph/storage/interfaces/__init__.py`
- Create: `tests/fakes/in_memory_graph_store.py`
- Test: `tests/test_graph_store_contract.py`

- [ ] **Step 1: Write failing GraphStore contract tests**

Create `tests/test_graph_store_contract.py`:

```python
from collections.abc import Callable

import pytest

from tests.fakes.in_memory_graph_store import InMemoryGraphStore
from vault_graph.errors import GraphReadOnlyViolation, GraphStoreError
from vault_graph.graph.graph_contracts import (
    EntityRecord,
    GraphEvidenceRef,
    GraphReconcilePlan,
    GraphRevision,
    GraphTombstone,
    RelationshipRecord,
    current_graph_extraction_spec,
)
from vault_graph.graph.graph_identity import (
    graph_scope_key,
    stable_entity_id,
    stable_evidence_ref_id,
    stable_graph_tombstone_id,
    stable_relationship_id,
)
from vault_graph.ingestion.vault_catalog import QueryScope
from vault_graph.storage.interfaces.graph_store import GraphEntityIdentity, GraphRelationshipIdentity, GraphStore


def make_entity(
    vault_id: str,
    *,
    name: str = "GraphRAG",
    document_id: str | None = None,
    chunk_id: str | None = None,
    content_hash: str | None = None,
    path: str = "wiki/graphrag.md",
) -> EntityRecord:
    spec = current_graph_extraction_spec()
    entity_id = stable_entity_id(
        vault_id=vault_id,
        entity_type="concept",
        normalized_name=name.casefold(),
        canonical_path=path,
    )
    resolved_document_id = document_id or f"{vault_id}-doc"
    resolved_chunk_id = chunk_id or f"{vault_id}-chunk"
    resolved_content_hash = content_hash or f"{vault_id}-hash"
    evidence = GraphEvidenceRef(
        evidence_ref_id=stable_evidence_ref_id(
            owner_kind="entity",
            owner_vault_id=vault_id,
            owner_id=entity_id,
            evidence_vault_id=vault_id,
            document_id=resolved_document_id,
            chunk_id=resolved_chunk_id,
            anchor="graphrag",
        ),
        owner_kind="entity",
        owner_vault_id=vault_id,
        owner_id=entity_id,
        evidence_vault_id=vault_id,
        document_id=resolved_document_id,
        chunk_id=resolved_chunk_id,
        content_hash=resolved_content_hash,
        section="GraphRAG",
        anchor="graphrag",
        path=path,
        excerpt="GraphRAG evidence",
    )
    return EntityRecord(
        vault_id=vault_id,
        entity_id=entity_id,
        type="concept",
        name=name,
        normalized_name=name.casefold(),
        aliases=("Graph RAG",),
        canonical_path=path,
        evidence_refs=(evidence,),
        confidence=0.9,
        extraction_method="test",
        graph_extraction_spec_version=spec.spec_version,
        graph_extraction_spec_digest=spec.spec_digest,
        status="active",
        created_at="2026-06-10T00:00:00+00:00",
        updated_at="2026-06-10T00:00:00+00:00",
        graph_index_revision="graph-1",
    )


def make_relationship(source: EntityRecord, target: EntityRecord) -> RelationshipRecord:
    spec = current_graph_extraction_spec()
    relationship_id = stable_relationship_id(
        relationship_type="depends_on",
        source_vault_id=source.vault_id,
        source_entity_id=source.entity_id,
        target_vault_id=target.vault_id,
        target_entity_id=target.entity_id,
    )
    evidence = GraphEvidenceRef(
        evidence_ref_id=stable_evidence_ref_id(
            owner_kind="relationship",
            owner_vault_id=source.vault_id,
            owner_id=relationship_id,
            evidence_vault_id=source.vault_id,
            document_id=f"{source.vault_id}-doc",
            chunk_id=f"{source.vault_id}-chunk",
            anchor="dependency",
        ),
        owner_kind="relationship",
        owner_vault_id=source.vault_id,
        owner_id=relationship_id,
        evidence_vault_id=source.vault_id,
        document_id=f"{source.vault_id}-doc",
        chunk_id=f"{source.vault_id}-chunk",
        content_hash=f"{source.vault_id}-hash",
        section="Dependency",
        anchor="dependency",
        path="wiki/graphrag.md",
        excerpt="Dependency evidence",
    )
    return RelationshipRecord(
        relationship_id=relationship_id,
        type="depends_on",
        source_vault_id=source.vault_id,
        source_entity_id=source.entity_id,
        target_vault_id=target.vault_id,
        target_entity_id=target.entity_id,
        evidence_refs=(evidence,),
        status="stated",
        confidence=0.8,
        extraction_method="test",
        graph_extraction_spec_version=spec.spec_version,
        graph_extraction_spec_digest=spec.spec_digest,
        created_at="2026-06-10T00:00:00+00:00",
        updated_at="2026-06-10T00:00:00+00:00",
        graph_index_revision="graph-1",
    )


def make_revision(scope: QueryScope, *, entity_count: int, relationship_count: int) -> GraphRevision:
    spec = current_graph_extraction_spec()
    return GraphRevision(
        graph_run_id="graph-run-1",
        vault_id=scope.vault_ids[0],
        effective_scope=graph_scope_key(scope),
        graph_store_schema_version="memory-graph-v1",
        graph_extraction_spec_version=spec.spec_version,
        graph_extraction_spec_digest=spec.spec_digest,
        graph_index_revision="graph-1",
        metadata_index_revision="metadata-1",
        parser_version="markdown-frontmatter-v1",
        chunker_version="heading-section-v1",
        entity_count=entity_count,
        relationship_count=relationship_count,
        stale_count=0,
        tombstone_count=0,
        updated_at="2026-06-10T00:00:00+00:00",
    )


def make_plan(
    *,
    entities: tuple[EntityRecord, ...],
    relationships: tuple[RelationshipRecord, ...],
    scope: QueryScope | None = None,
) -> GraphReconcilePlan:
    resolved_scope = scope or _scope_for_records(entities=entities, relationships=relationships)
    evidence_refs = tuple(ref for entity in entities for ref in entity.evidence_refs) + tuple(
        ref for relationship in relationships for ref in relationship.evidence_refs
    )
    return GraphReconcilePlan(
        requested_scope=resolved_scope,
        effective_scopes=(resolved_scope,),
        graph_run_id="graph-run-1",
        entity_upserts=entities,
        relationship_upserts=relationships,
        evidence_ref_upserts=evidence_refs,
        entity_tombstones=(),
        relationship_tombstones=(),
        graph_revision_rows=(
            make_revision(resolved_scope, entity_count=len(entities), relationship_count=len(relationships)),
        ),
        graph_extraction_spec=current_graph_extraction_spec(),
        projection_cache_invalidations=(),
    )


def _scope_for_records(
    *,
    entities: tuple[EntityRecord, ...],
    relationships: tuple[RelationshipRecord, ...],
) -> QueryScope:
    if entities:
        return QueryScope(vault_ids=(entities[0].vault_id,), content_scopes=("wiki",))
    if relationships:
        return QueryScope(vault_ids=(relationships[0].source_vault_id,), content_scopes=("wiki",))
    return QueryScope(vault_ids=("default",), content_scopes=("wiki",))


def graph_store_contract(factory: Callable[[], GraphStore]) -> None:
    store = factory()
    source = make_entity("default")
    target = make_entity("default", name="Context Pack")
    relationship = make_relationship(source, target)
    result = store.apply_reconcile_plan(make_plan(entities=(source, target), relationships=(relationship,)))

    assert result.applied_entity_upsert_count == 2
    assert result.applied_relationship_upsert_count == 1
    assert result.applied_evidence_ref_upsert_count == 3
    assert store.get_entity(vault_id="default", entity_id=source.entity_id) == source
    assert store.get_relationship(source_vault_id="default", relationship_id=relationship.relationship_id) == relationship
    assert store.resolve_entities((GraphEntityIdentity("default", source.entity_id),)) == (source,)
    assert store.resolve_relationships((GraphRelationshipIdentity("default", relationship.relationship_id),)) == (
        relationship,
    )
    manifest = store.current_manifest((QueryScope(vault_ids=("default",), content_scopes=("wiki")),))
    assert tuple(row.entity_id for row in manifest.entity_rows) == (target.entity_id, source.entity_id)
    assert tuple(row.relationship_id for row in manifest.relationship_rows) == (relationship.relationship_id,)
    assert len(manifest.evidence_rows) == 3
    assert {row.metadata_index_revision for row in manifest.entity_rows} == {"metadata-1"}
    assert {row.graph_index_revision for row in manifest.relationship_rows} == {"graph-1"}
    assert {row.graph_extraction_spec_digest for row in manifest.entity_rows} == {
        current_graph_extraction_spec().spec_digest,
    }
    assert {row.content_hash for row in manifest.evidence_rows} == {"default-hash"}
    assert manifest.relationship_rows[0].source_vault_id == "default"
    assert manifest.relationship_rows[0].target_vault_id == "default"
    assert store.latest_revisions((QueryScope(vault_ids=("default",), content_scopes=("wiki")),))[0].graph_index_revision == "graph-1"


def test_in_memory_graph_store_satisfies_contract() -> None:
    graph_store_contract(lambda: InMemoryGraphStore())


def test_read_only_graph_store_rejects_apply() -> None:
    store = InMemoryGraphStore(read_only=True)
    source = make_entity("default")

    with pytest.raises(GraphReadOnlyViolation):
        store.apply_reconcile_plan(make_plan(entities=(source,), relationships=()))


def test_current_manifest_rejects_global_all_vault_scope() -> None:
    store = InMemoryGraphStore()

    with pytest.raises(GraphStoreError, match="per-Vault effective scopes"):
        store.current_manifest((QueryScope(vault_ids=("first", "second"), content_scopes=("wiki",)),))


def test_tombstones_are_scoped_records() -> None:
    store = InMemoryGraphStore()
    source = make_entity("default")
    scope = QueryScope(vault_ids=("default",), content_scopes=("wiki",))
    spec = current_graph_extraction_spec()
    tombstone = GraphTombstone(
        tombstone_id=stable_graph_tombstone_id(
            record_kind="entity",
            record_vault_id="default",
            record_id=source.entity_id,
            effective_scope=graph_scope_key(scope),
        ),
        record_kind="entity",
        record_vault_id="default",
        record_id=source.entity_id,
        effective_scope=graph_scope_key(scope),
        reason="missing_from_scope",
        graph_run_id="graph-run-2",
        graph_index_revision="graph-2",
        graph_extraction_spec_version=spec.spec_version,
        graph_extraction_spec_digest=spec.spec_digest,
        tombstoned_at="2026-06-10T00:01:00+00:00",
    )
    plan = GraphReconcilePlan(
        requested_scope=scope,
        effective_scopes=(scope,),
        graph_run_id="graph-run-2",
        entity_upserts=(),
        relationship_upserts=(),
        evidence_ref_upserts=(),
        entity_tombstones=(tombstone,),
        relationship_tombstones=(),
        graph_revision_rows=(make_revision(scope, entity_count=0, relationship_count=0),),
        graph_extraction_spec=spec,
        projection_cache_invalidations=(),
    )

    result = store.apply_reconcile_plan(plan)
    repeat = store.apply_reconcile_plan(plan)

    assert result.applied_tombstone_count == 1
    assert repeat.applied_tombstone_count == 1
    assert store.current_manifest((scope,)).tombstone_rows[0].record_vault_id == "default"
    assert len(store.current_manifest((scope,)).tombstone_rows) == 1
```

- [ ] **Step 2: Verify the contract tests fail**

Run:

```bash
uv run --python 3.12 pytest tests/test_graph_store_contract.py -q
```

Expected: FAIL because the `GraphStore` interface and fake do not exist.

- [ ] **Step 3: Add `GraphStore` protocol**

Create `src/vault_graph/storage/interfaces/graph_store.py`:

```python
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from vault_graph.graph.graph_contracts import (
    EntityRecord,
    GraphApplyResult,
    GraphExtractionSpec,
    GraphManifest,
    GraphReconcilePlan,
    GraphRevision,
    RelationshipRecord,
)
from vault_graph.ingestion.vault_catalog import QueryScope
from vault_graph.storage.interfaces.store_health import StoreHealth


@dataclass(frozen=True)
class GraphEntityIdentity:
    vault_id: str
    entity_id: str


@dataclass(frozen=True)
class GraphRelationshipIdentity:
    source_vault_id: str
    relationship_id: str


class GraphStore(Protocol):
    def health(self) -> StoreHealth:
        raise NotImplementedError

    def stored_specs(self) -> tuple[GraphExtractionSpec, ...]:
        raise NotImplementedError

    def latest_revisions(self, scopes: tuple[QueryScope, ...]) -> tuple[GraphRevision, ...]:
        raise NotImplementedError

    def current_manifest(self, scopes: tuple[QueryScope, ...]) -> GraphManifest:
        raise NotImplementedError

    def get_entity(self, *, vault_id: str, entity_id: str) -> EntityRecord | None:
        raise NotImplementedError

    def get_relationship(self, *, source_vault_id: str, relationship_id: str) -> RelationshipRecord | None:
        raise NotImplementedError

    def resolve_entities(self, identities: tuple[GraphEntityIdentity, ...]) -> tuple[EntityRecord, ...]:
        raise NotImplementedError

    def resolve_relationships(
        self,
        identities: tuple[GraphRelationshipIdentity, ...],
    ) -> tuple[RelationshipRecord, ...]:
        raise NotImplementedError

    def apply_reconcile_plan(self, plan: GraphReconcilePlan) -> GraphApplyResult:
        raise NotImplementedError
```

- [ ] **Step 4: Add in-memory fake**

Create `tests/fakes/in_memory_graph_store.py`.

Implementation requirements:

- constructor accepts `read_only: bool = False` and `health_override: StoreHealth | None = None`
- store entities by `(vault_id, entity_id)`
- store relationships by `(source_vault_id, relationship_id)`
- store evidence refs by `(owner_kind, owner_vault_id, owner_id, evidence_vault_id, document_id, chunk_id, anchor)`
- store revisions by `(vault_id, effective_scope)`
- store tombstones by `tombstone_id`
- store graph extraction specs by digest when applying a plan
- store record scope memberships by `(record_kind, record_vault_id, record_id, effective_scope)` from plan effective scopes
- reject writes when `read_only=True`
- reject any manifest or revision scope with more than one `vault_id`
- return `StoreHealth(ok=True, backend="memory-graph", schema_version="memory-graph-v1", schema_compatible=True, message="ok")`
- `current_manifest(scopes)` filters graph records by explicit record scope memberships, not by cached evidence `path`
- when `scope.include_cross_vault is False`, `current_manifest(scope)` excludes relationships whose source, target, or evidence Vault IDs differ from `scope.vault_ids[0]`
- when any supplied scope has `include_cross_vault is True`, `current_manifest(scopes)` may include cross-Vault relationships only when source, target, and evidence Vault IDs are all in the union of supplied scope Vault IDs
- `resolve_entities(identities)` and `resolve_relationships(identities)` preserve requested identity order and omit missing records
- `stored_specs()` returns specs sorted by `(spec_version, spec_digest)`

- [ ] **Step 5: Export graph store interface records**

Modify `src/vault_graph/storage/interfaces/__init__.py` to include:

```python
from vault_graph.storage.interfaces.graph_store import GraphEntityIdentity, GraphRelationshipIdentity, GraphStore
```

and update `__all__`.

- [ ] **Step 6: Verify the in-memory contract passes**

Run:

```bash
uv run --python 3.12 pytest tests/test_graph_store_contract.py -q
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add src/vault_graph/storage/interfaces tests/fakes/in_memory_graph_store.py tests/test_graph_store_contract.py
git commit -m "feat: define graph store contract"
```

---

### Task 3: Add SQLiteGraphStore Reference Backend

**Files:**

- Create: `src/vault_graph/storage/local/sqlite_graph_store.py`
- Modify: `src/vault_graph/storage/local/__init__.py`
- Test: `tests/test_sqlite_graph_store.py`
- Modify: `tests/test_graph_store_contract.py`

- [ ] **Step 1: Write failing SQLite graph store tests**

Create `tests/test_sqlite_graph_store.py`:

```python
import sqlite3
from pathlib import Path

import pytest

from tests.test_graph_store_contract import graph_store_contract, make_entity, make_plan
from vault_graph.errors import GraphReadOnlyViolation
from vault_graph.ingestion.vault_catalog import QueryScope
from vault_graph.storage.local.sqlite_graph_store import GRAPH_SCHEMA_VERSION, SQLiteGraphStore


def test_sqlite_graph_store_satisfies_contract(tmp_path: Path) -> None:
    graph_store_contract(lambda: SQLiteGraphStore.open_writable(tmp_path / "graph.sqlite3"))


def test_sqlite_graph_store_persists_records(tmp_path: Path) -> None:
    path = tmp_path / "graph.sqlite3"
    writable = SQLiteGraphStore.open_writable(path)
    entity = make_entity("default")
    writable.apply_reconcile_plan(make_plan(entities=(entity,), relationships=()))

    readonly = SQLiteGraphStore.open_read_only(path)

    assert readonly.get_entity(vault_id="default", entity_id=entity.entity_id) == entity
    assert readonly.health().ok is True
    assert readonly.health().schema_version == GRAPH_SCHEMA_VERSION


def test_sqlite_graph_store_stamps_revision_schema_version(tmp_path: Path) -> None:
    path = tmp_path / "graph.sqlite3"
    store = SQLiteGraphStore.open_writable(path)
    entity = make_entity("default")
    store.apply_reconcile_plan(make_plan(entities=(entity,), relationships=()))

    revision = store.latest_revisions((QueryScope(vault_ids=("default",), content_scopes=("wiki")),))[0]

    assert revision.graph_store_schema_version == GRAPH_SCHEMA_VERSION


def test_read_only_missing_graph_store_does_not_create_state(tmp_path: Path) -> None:
    path = tmp_path / "missing" / "graph.sqlite3"
    store = SQLiteGraphStore.open_read_only(path)

    health = store.health()
    manifest = store.current_manifest((QueryScope(vault_ids=("default",), content_scopes=("wiki",)),))

    assert health.ok is False
    assert health.schema_compatible is False
    assert "not initialized" in health.message
    assert manifest.entity_rows == ()
    assert not path.exists()
    assert not path.parent.exists()


def test_read_only_sqlite_graph_store_rejects_apply(tmp_path: Path) -> None:
    path = tmp_path / "graph.sqlite3"
    SQLiteGraphStore.open_writable(path)
    readonly = SQLiteGraphStore.open_read_only(path)
    entity = make_entity("default")

    with pytest.raises(GraphReadOnlyViolation):
        readonly.apply_reconcile_plan(make_plan(entities=(entity,), relationships=()))


def test_sqlite_graph_health_reports_missing_required_table(tmp_path: Path) -> None:
    path = tmp_path / "graph.sqlite3"
    with sqlite3.connect(path) as connection:
        connection.execute("CREATE TABLE graph_entities (vault_id TEXT)")

    store = SQLiteGraphStore.open_read_only(path)

    health = store.health()
    assert health.ok is False
    assert health.schema_compatible is False
    assert "missing" in health.message
```

- [ ] **Step 2: Verify the SQLite tests fail**

Run:

```bash
uv run --python 3.12 pytest tests/test_sqlite_graph_store.py -q
```

Expected: FAIL because `SQLiteGraphStore` does not exist.

- [ ] **Step 3: Add SQLite schema constants**

Create `src/vault_graph/storage/local/sqlite_graph_store.py` with:

```python
GRAPH_SQLITE_BACKEND = "sqlite-graph"
GRAPH_SCHEMA_VERSION = "sqlite-graph-v1"
```

Use this logical schema:

```sql
CREATE TABLE IF NOT EXISTS graph_metadata (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS graph_specs (
  spec_digest TEXT PRIMARY KEY,
  spec_version TEXT NOT NULL,
  entity_schema_version TEXT NOT NULL,
  relationship_schema_version TEXT NOT NULL,
  entity_extractor_name TEXT NOT NULL,
  entity_extractor_version TEXT NOT NULL,
  relationship_extractor_name TEXT NOT NULL,
  relationship_extractor_version TEXT NOT NULL,
  relationship_status_rules_version TEXT NOT NULL,
  confidence_rules_version TEXT NOT NULL,
  serialized_spec TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS graph_entities (
  vault_id TEXT NOT NULL,
  entity_id TEXT NOT NULL,
  type TEXT NOT NULL,
  name TEXT NOT NULL,
  normalized_name TEXT NOT NULL,
  aliases_json TEXT NOT NULL,
  canonical_path TEXT,
  confidence REAL NOT NULL,
  extraction_method TEXT NOT NULL,
  graph_extraction_spec_version TEXT NOT NULL,
  graph_extraction_spec_digest TEXT NOT NULL,
  status TEXT NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  graph_index_revision TEXT NOT NULL,
  PRIMARY KEY (vault_id, entity_id)
);

CREATE TABLE IF NOT EXISTS graph_relationships (
  source_vault_id TEXT NOT NULL,
  relationship_id TEXT NOT NULL,
  type TEXT NOT NULL,
  source_entity_id TEXT NOT NULL,
  target_vault_id TEXT NOT NULL,
  target_entity_id TEXT NOT NULL,
  status TEXT NOT NULL,
  confidence REAL NOT NULL,
  extraction_method TEXT NOT NULL,
  graph_extraction_spec_version TEXT NOT NULL,
  graph_extraction_spec_digest TEXT NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  graph_index_revision TEXT NOT NULL,
  PRIMARY KEY (source_vault_id, relationship_id)
);

CREATE TABLE IF NOT EXISTS graph_evidence_refs (
  evidence_ref_id TEXT PRIMARY KEY,
  owner_kind TEXT NOT NULL,
  owner_vault_id TEXT NOT NULL,
  owner_id TEXT NOT NULL,
  evidence_vault_id TEXT NOT NULL,
  document_id TEXT NOT NULL,
  chunk_id TEXT NOT NULL,
  content_hash TEXT NOT NULL,
  section TEXT,
  anchor TEXT,
  anchor_key TEXT NOT NULL,
  path TEXT,
  excerpt TEXT,
  UNIQUE (owner_kind, owner_vault_id, owner_id, evidence_vault_id, document_id, chunk_id, anchor_key)
);

CREATE TABLE IF NOT EXISTS graph_record_scopes (
  record_kind TEXT NOT NULL,
  record_vault_id TEXT NOT NULL,
  record_id TEXT NOT NULL,
  effective_scope TEXT NOT NULL,
  metadata_index_revision TEXT NOT NULL,
  graph_index_revision TEXT NOT NULL,
  graph_extraction_spec_digest TEXT NOT NULL,
  PRIMARY KEY (record_kind, record_vault_id, record_id, effective_scope)
);

CREATE TABLE IF NOT EXISTS graph_revisions (
  graph_run_id TEXT NOT NULL,
  vault_id TEXT NOT NULL,
  effective_scope TEXT NOT NULL,
  graph_store_schema_version TEXT NOT NULL,
  graph_extraction_spec_version TEXT NOT NULL,
  graph_extraction_spec_digest TEXT NOT NULL,
  graph_index_revision TEXT NOT NULL,
  metadata_index_revision TEXT NOT NULL,
  parser_version TEXT NOT NULL,
  chunker_version TEXT NOT NULL,
  entity_count INTEGER NOT NULL,
  relationship_count INTEGER NOT NULL,
  stale_count INTEGER NOT NULL,
  tombstone_count INTEGER NOT NULL,
  updated_at TEXT NOT NULL,
  PRIMARY KEY (vault_id, effective_scope, graph_index_revision)
);

CREATE TABLE IF NOT EXISTS graph_tombstones (
  tombstone_id TEXT PRIMARY KEY,
  record_kind TEXT NOT NULL,
  record_vault_id TEXT NOT NULL,
  record_id TEXT NOT NULL,
  effective_scope TEXT NOT NULL,
  reason TEXT NOT NULL,
  graph_run_id TEXT NOT NULL,
  graph_index_revision TEXT NOT NULL,
  graph_extraction_spec_version TEXT NOT NULL,
  graph_extraction_spec_digest TEXT NOT NULL,
  tombstoned_at TEXT NOT NULL
);
```

Add indexes:

```sql
CREATE INDEX IF NOT EXISTS idx_graph_entities_name ON graph_entities (vault_id, normalized_name);
CREATE INDEX IF NOT EXISTS idx_graph_entities_type_name ON graph_entities (vault_id, type, normalized_name);
CREATE INDEX IF NOT EXISTS idx_graph_relationships_source ON graph_relationships (source_vault_id, source_entity_id);
CREATE INDEX IF NOT EXISTS idx_graph_relationships_target ON graph_relationships (target_vault_id, target_entity_id);
CREATE INDEX IF NOT EXISTS idx_graph_relationships_type_status ON graph_relationships (type, status);
CREATE INDEX IF NOT EXISTS idx_graph_evidence_chunk ON graph_evidence_refs (evidence_vault_id, document_id, chunk_id);
CREATE INDEX IF NOT EXISTS idx_graph_evidence_owner ON graph_evidence_refs (owner_kind, owner_vault_id, owner_id);
CREATE INDEX IF NOT EXISTS idx_graph_record_scopes_scope ON graph_record_scopes (effective_scope, record_kind);
CREATE INDEX IF NOT EXISTS idx_graph_revisions_scope ON graph_revisions (vault_id, effective_scope, updated_at);
```

- [ ] **Step 4: Implement SQLiteGraphStore construction modes**

Add classmethods:

```python
@classmethod
def open_read_only(cls, database_path: Path) -> SQLiteGraphStore:
    return cls(database_path, initialize=False, read_only=True)


@classmethod
def open_writable(cls, database_path: Path) -> SQLiteGraphStore:
    return cls(database_path, initialize=True, read_only=False)
```

Rules:

- `initialize=True` creates parent directories and runs schema creation.
- writable initialization upserts `('schema_version', GRAPH_SCHEMA_VERSION)` into `graph_metadata`.
- `read_only=True` uses `sqlite3.connect(f"file:{path}?mode=ro", uri=True)`.
- read methods return empty values when the database path does not exist.
- read-only methods do not run migrations, create tables, or create parent directories.
- `health()` validates required tables, schema version in `graph_metadata`, and required columns.

- [ ] **Step 5: Implement SQLite apply and read methods**

`apply_reconcile_plan(plan)` must:

- raise `GraphReadOnlyViolation` when `read_only=True`
- validate all plan effective scopes are per-Vault scopes
- insert the plan `graph_extraction_spec` into `graph_specs`
- stamp each revision row with the backend's own `GRAPH_SCHEMA_VERSION`; do not trust a mismatched `graph_store_schema_version` supplied by the plan
- upsert entity rows
- upsert relationship rows
- upsert evidence ref rows
- write `anchor_key = ref.anchor or ""` for evidence uniqueness because SQLite allows duplicate `NULL` values in unique indexes
- upsert `graph_record_scopes` rows for each entity and relationship in each plan effective scope, carrying the applied metadata revision, graph revision, and spec digest
- upsert tombstone rows by `tombstone_id`; tombstones model latest derived state per record/scope, not immutable history
- update tombstoned entity rows to `status='tombstoned'`
- update tombstoned relationship rows to `status='deprecated'`
- insert graph revision rows
- commit in one SQLite transaction
- return `GraphApplyResult`

`current_manifest(scopes)` must:

- validate per-Vault effective scopes
- include records whose `graph_record_scopes.effective_scope` matches selected scope keys
- keep cached evidence `path`, `section`, and `excerpt` only as rendering hints in manifest evidence rows
- exclude cross-Vault relationships unless at least one supplied effective scope has `include_cross_vault=True` and source, target, and evidence Vault IDs are all inside the union of supplied scope Vault IDs
- include tombstones whose `effective_scope` matches selected scope keys
- return empty rows for missing read-only databases
- not expose SQLite row IDs

- [ ] **Step 6: Add SQLite store to the contract test**

Modify `tests/test_graph_store_contract.py`:

```python
from pathlib import Path

from vault_graph.storage.local.sqlite_graph_store import SQLiteGraphStore


def test_sqlite_graph_store_satisfies_shared_contract(tmp_path: Path) -> None:
    graph_store_contract(lambda: SQLiteGraphStore.open_writable(tmp_path / "graph.sqlite3"))
```

- [ ] **Step 7: Verify SQLite graph store tests pass**

Run:

```bash
uv run --python 3.12 pytest tests/test_graph_store_contract.py tests/test_sqlite_graph_store.py -q
```

Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add src/vault_graph/storage/local/sqlite_graph_store.py src/vault_graph/storage/local/__init__.py tests/test_graph_store_contract.py tests/test_sqlite_graph_store.py
git commit -m "feat: add sqlite graph store"
```

---

### Task 4: Add Graph Readiness Types And Service

**Files:**

- Create: `src/vault_graph/graph/graph_readiness.py`
- Create: `src/vault_graph/app/graph_readiness_service.py`
- Test: `tests/test_graph_readiness.py`

- [ ] **Step 1: Write failing graph readiness tests**

Create `tests/test_graph_readiness.py`:

```python
from pathlib import Path

from tests.fakes.in_memory_graph_store import InMemoryGraphStore
from tests.test_graph_store_contract import make_entity, make_plan, make_relationship
from tests.test_sqlite_metadata_store import make_chunk, make_document
from vault_graph.app.graph_readiness_service import ReadOnlyGraphReadiness
from vault_graph.errors import GraphStoreUnavailable
from vault_graph.graph.graph_contracts import GraphManifest, current_graph_extraction_spec
from vault_graph.ingestion.vault_catalog import QueryScope
from vault_graph.storage.interfaces.store_health import StoreHealth
from vault_graph.storage.local.sqlite_metadata_store import SQLiteMetadataStore


def metadata_store_with_chunk(
    tmp_path: Path,
    *,
    vault_id: str = "default",
    index_revision: str = "metadata-1",
) -> SQLiteMetadataStore:
    store, _, _, _ = metadata_store_with_chunk_ids(tmp_path, vault_id=vault_id, index_revision=index_revision)
    return store


def metadata_store_with_chunk_ids(
    tmp_path: Path,
    *,
    vault_id: str = "default",
    index_revision: str = "metadata-1",
) -> tuple[SQLiteMetadataStore, str, str, str]:
    store = SQLiteMetadataStore(tmp_path / "metadata.sqlite3", initialize=True)
    document = make_document(vault_id, "wiki/page.md", "hash")
    document = type(document)(
        vault_id=document.vault_id,
        document_id=document.document_id,
        path=document.path,
        kind=document.kind,
        frontmatter=document.frontmatter,
        frontmatter_hash=document.frontmatter_hash,
        content_hash=document.content_hash,
        raw_sha256=document.raw_sha256,
        parser_version="markdown-frontmatter-v1",
        last_seen_at=document.last_seen_at,
        last_indexed_at=document.last_indexed_at,
        vault_revision=document.vault_revision,
        index_revision=document.index_revision,
    )
    chunk = make_chunk("default", document.document_id, document.path)
    chunk = type(chunk)(
        vault_id=chunk.vault_id,
        chunk_id=chunk.chunk_id,
        document_id=chunk.document_id,
        path=chunk.path,
        section=chunk.section,
        anchor=chunk.anchor,
        text=chunk.text,
        token_count=chunk.token_count,
        content_hash=chunk.content_hash,
        chunker_version="heading-section-v1",
        index_revision=index_revision,
    )
    store.apply_metadata_revision(index_revision=index_revision, documents=[document], chunks=[chunk], tombstones=[])
    return store, document.document_id, chunk.chunk_id, chunk.content_hash


def test_graph_readiness_reports_missing_graph_store(tmp_path: Path) -> None:
    metadata_store = metadata_store_with_chunk(tmp_path)
    graph_store = InMemoryGraphStore(health_override=StoreHealth(
        ok=False,
        backend="memory-graph",
        schema_version="memory-graph-v1",
        schema_compatible=False,
        message="not initialized",
    ))
    service = ReadOnlyGraphReadiness(
        metadata_store=metadata_store,
        graph_store=graph_store,
        expected_spec=current_graph_extraction_spec(),
    )

    report = service.check(
        requested_scope=QueryScope(vault_ids=("default",), content_scopes=("wiki",)),
        effective_scopes=(QueryScope(vault_ids=("default",), content_scopes=("wiki")),),
    )

    assert report.backend_name == "memory-graph"
    assert report.backend_available is False
    assert report.freshness == "missing"
    assert "run `vg index`" in report.recovery_hint


def test_graph_readiness_reports_empty_when_store_has_no_revision(tmp_path: Path) -> None:
    metadata_store = metadata_store_with_chunk(tmp_path)
    service = ReadOnlyGraphReadiness(
        metadata_store=metadata_store,
        graph_store=InMemoryGraphStore(),
        expected_spec=current_graph_extraction_spec(),
    )

    report = service.check(
        requested_scope=QueryScope(vault_ids=("default",), content_scopes=("wiki",)),
        effective_scopes=(QueryScope(vault_ids=("default",), content_scopes=("wiki")),),
    )

    assert report.freshness == "empty"
    assert report.last_graph_revision is None


def test_graph_readiness_reports_unavailable_when_manifest_read_fails(tmp_path: Path) -> None:
    class FailingGraphStore(InMemoryGraphStore):
        def current_manifest(self, scopes: tuple[QueryScope, ...]) -> GraphManifest:
            raise GraphStoreUnavailable("graph read failed")

    metadata_store = metadata_store_with_chunk(tmp_path)
    graph_store = FailingGraphStore()
    entity = make_entity("default")
    graph_store.apply_reconcile_plan(make_plan(entities=(entity,), relationships=()))
    service = ReadOnlyGraphReadiness(
        metadata_store=metadata_store,
        graph_store=graph_store,
        expected_spec=current_graph_extraction_spec(),
    )

    report = service.check(
        requested_scope=QueryScope(vault_ids=("default",), content_scopes=("wiki",)),
        effective_scopes=(QueryScope(vault_ids=("default",), content_scopes=("wiki")),),
    )

    assert report.freshness == "unavailable"
    assert "graph read failed" in report.recovery_hint


def test_graph_readiness_reports_fresh_when_lineage_matches(tmp_path: Path) -> None:
    metadata_store, document_id, chunk_id, content_hash = metadata_store_with_chunk_ids(tmp_path)
    graph_store = InMemoryGraphStore()
    entity = make_entity(
        "default",
        document_id=document_id,
        chunk_id=chunk_id,
        content_hash=content_hash,
        path="wiki/page.md",
    )
    graph_store.apply_reconcile_plan(make_plan(entities=(entity,), relationships=()))
    service = ReadOnlyGraphReadiness(
        metadata_store=metadata_store,
        graph_store=graph_store,
        expected_spec=current_graph_extraction_spec(),
    )

    report = service.check(
        requested_scope=QueryScope(vault_ids=("default",), content_scopes=("wiki",)),
        effective_scopes=(QueryScope(vault_ids=("default",), content_scopes=("wiki")),),
    )

    assert report.freshness == "fresh"
    assert report.graph_extraction_spec_compatible is True
    assert report.stale_count == 0
    assert report.tombstone_count == 0
    assert report.last_graph_revision == "graph-1"


def test_graph_readiness_reports_scope_rows_for_all_vaults(tmp_path: Path) -> None:
    first_store, document_id, chunk_id, content_hash = metadata_store_with_chunk_ids(
        tmp_path,
        vault_id="first",
        index_revision="metadata-1",
    )
    graph_store = InMemoryGraphStore()
    first_entity = make_entity(
        "first",
        document_id=document_id,
        chunk_id=chunk_id,
        content_hash=content_hash,
        path="wiki/page.md",
    )
    graph_store.apply_reconcile_plan(
        make_plan(
            entities=(first_entity,),
            relationships=(),
            scope=QueryScope(vault_ids=("first",), content_scopes=("wiki")),
        )
    )
    service = ReadOnlyGraphReadiness(
        metadata_store=first_store,
        graph_store=graph_store,
        expected_spec=current_graph_extraction_spec(),
    )

    report = service.check(
        requested_scope=QueryScope(vault_ids=("first", "second"), content_scopes=("wiki",)),
        effective_scopes=(
            QueryScope(vault_ids=("first",), content_scopes=("wiki")),
            QueryScope(vault_ids=("second",), content_scopes=("wiki")),
        ),
    )

    assert report.freshness == "empty"
    assert tuple((row.vault_id, row.freshness) for row in report.scope_readiness) == (
        ("first", "fresh"),
        ("second", "empty"),
    )
    assert tuple(row.last_graph_revision for row in report.scope_readiness) == ("graph-1", None)


def test_graph_readiness_reports_stale_when_graph_evidence_is_unresolved(tmp_path: Path) -> None:
    metadata_store = metadata_store_with_chunk(tmp_path)
    graph_store = InMemoryGraphStore()
    entity = make_entity("default", document_id="missing-doc", chunk_id="missing-chunk")
    graph_store.apply_reconcile_plan(make_plan(entities=(entity,), relationships=()))
    service = ReadOnlyGraphReadiness(
        metadata_store=metadata_store,
        graph_store=graph_store,
        expected_spec=current_graph_extraction_spec(),
    )

    report = service.check(
        requested_scope=QueryScope(vault_ids=("default",), content_scopes=("wiki",)),
        effective_scopes=(QueryScope(vault_ids=("default",), content_scopes=("wiki")),),
    )

    assert report.freshness == "stale"
    assert any("unresolved graph evidence" in warning for warning in report.warnings)
    assert "rerun metadata indexing, then graph indexing" in report.recovery_hint


def test_graph_readiness_reports_stale_when_metadata_revision_changes(tmp_path: Path) -> None:
    old_metadata = metadata_store_with_chunk(tmp_path / "old", index_revision="metadata-1")
    graph_store = InMemoryGraphStore()
    entity = make_entity("default")
    graph_store.apply_reconcile_plan(make_plan(entities=(entity,), relationships=()))
    new_metadata = metadata_store_with_chunk(tmp_path / "new", index_revision="metadata-2")
    service = ReadOnlyGraphReadiness(
        metadata_store=new_metadata,
        graph_store=graph_store,
        expected_spec=current_graph_extraction_spec(),
    )

    report = service.check(
        requested_scope=QueryScope(vault_ids=("default",), content_scopes=("wiki",)),
        effective_scopes=(QueryScope(vault_ids=("default",), content_scopes=("wiki")),),
    )

    assert old_metadata.health().ok is True
    assert report.freshness == "stale"
    assert "rerun `vg index`" in report.recovery_hint


def test_graph_readiness_reports_incompatible_when_spec_digest_conflicts(tmp_path: Path) -> None:
    metadata_store = metadata_store_with_chunk(tmp_path)
    graph_store = InMemoryGraphStore()
    entity = make_entity("default")
    graph_store.apply_reconcile_plan(make_plan(entities=(entity,), relationships=()))
    different_spec = current_graph_extraction_spec().__class__.from_payload(
        {
            **current_graph_extraction_spec().payload(),
            "entity_schema_version": "entity-schema-v2",
        }
    )
    service = ReadOnlyGraphReadiness(
        metadata_store=metadata_store,
        graph_store=graph_store,
        expected_spec=different_spec,
    )

    report = service.check(
        requested_scope=QueryScope(vault_ids=("default",), content_scopes=("wiki",)),
        effective_scopes=(QueryScope(vault_ids=("default",), content_scopes=("wiki")),),
    )

    assert report.freshness == "incompatible"
    assert report.graph_extraction_spec_compatible is False
```

- [ ] **Step 2: Verify readiness tests fail**

Run:

```bash
uv run --python 3.12 pytest tests/test_graph_readiness.py -q
```

Expected: FAIL because graph readiness modules do not exist.

- [ ] **Step 3: Add graph readiness dataclasses**

Create `src/vault_graph/graph/graph_readiness.py`:

```python
from __future__ import annotations

from dataclasses import dataclass

from vault_graph.ingestion.vault_catalog import QueryScope

GRAPH_FRESHNESS_VALUES = ("missing", "empty", "fresh", "stale", "incompatible", "unavailable")


@dataclass(frozen=True)
class GraphLineageScope:
    vault_id: str
    effective_scope: str
    metadata_index_revision: str
    parser_version: str
    chunker_version: str


@dataclass(frozen=True)
class GraphLineageSnapshot:
    requested_scope: QueryScope
    effective_scopes: tuple[QueryScope, ...]
    metadata_lineage: tuple[GraphLineageScope, ...]
    graph_store_schema_version: str
    expected_graph_extraction_spec_version: str
    expected_graph_extraction_spec_digest: str


@dataclass(frozen=True)
class GraphScopeReadiness:
    vault_id: str
    effective_scope: str
    freshness: str
    stale_count: int
    tombstone_count: int
    last_graph_revision: str | None
    warnings: tuple[str, ...]


@dataclass(frozen=True)
class GraphReadiness:
    backend_name: str
    backend_available: bool
    schema_version: str
    schema_compatible: bool
    graph_extraction_spec_version: str
    graph_extraction_spec_digest: str
    graph_extraction_spec_compatible: bool
    freshness: str
    stale_count: int
    tombstone_count: int
    last_graph_revision: str | None
    affected_vault_ids: tuple[str, ...]
    scope_readiness: tuple[GraphScopeReadiness, ...]
    warnings: tuple[str, ...]
    recovery_hint: str
```

- [ ] **Step 4: Implement `ReadOnlyGraphReadiness`**

Create `src/vault_graph/app/graph_readiness_service.py`.

Constructor:

```python
class ReadOnlyGraphReadiness:
    def __init__(
        self,
        *,
        metadata_store: MetadataStore,
        graph_store: GraphStore,
        expected_spec: GraphExtractionSpec,
    ) -> None:
        self._metadata_store = metadata_store
        self._graph_store = graph_store
        self._expected_spec = expected_spec
```

Public method:

```python
def check(self, *, requested_scope: QueryScope, effective_scopes: tuple[QueryScope, ...]) -> GraphReadiness:
    graph_health = self._graph_store.health()
    return self._readiness_from_health(
        graph_health=graph_health,
        requested_scope=requested_scope,
        effective_scopes=effective_scopes,
    )
```

Readiness algorithm:

1. Get `graph_health = graph_store.health()`.
2. If `graph_health.ok is False` and message contains `not initialized`, return `freshness="missing"`.
3. If `graph_health.ok is False` and `schema_compatible is False`, return `freshness="incompatible"`.
4. If `graph_health.ok is False`, return `freshness="unavailable"`.
5. Build metadata lineage from `MetadataStore.list_chunks(scope)` and `MetadataStore.list_document_states(scope.vault_ids)`.
6. Call `graph_store.stored_specs()` and `graph_store.latest_revisions(effective_scopes)`.
7. Call `graph_store.current_manifest(effective_scopes)` and resolve every manifest evidence key through `MetadataStore.resolve_chunk_evidence(vault_id=evidence.evidence_vault_id, document_id=evidence.document_id, chunk_id=evidence.chunk_id)`.
8. If any evidence ref cannot be resolved or its `content_hash` differs from metadata, mark the affected scope `stale` with an `unresolved graph evidence` or `stale graph evidence` warning.
9. Build one `GraphScopeReadiness` per effective scope.
10. If no revision exists for an effective scope, that scope is `empty`.
11. If stored spec same version has different digest, affected scopes are `incompatible`.
12. If latest revision digest does not match expected digest, affected scopes are `stale`.
13. If latest revision metadata/parser/chunker/schema lineage differs from current metadata lineage, affected scopes are `stale`.
14. If all compared lineage and evidence checks match for a scope, that scope is `fresh`.
15. Aggregate top-level freshness in this severity order: `unavailable`, `incompatible`, `stale`, `empty`, `missing`, `fresh`.

Metadata lineage rules:

- metadata revision is a comma-joined sorted set of chunk `index_revision` values, or `empty:<metadata_schema_version>`
- parser version is a comma-joined sorted set of matching document `parser_version` values, or `unknown`
- chunker version is a comma-joined sorted set of chunk `chunker_version` values, or `empty`
- document states must be filtered by the same-or-child content-scope path rule

- [ ] **Step 5: Verify readiness tests pass**

Run:

```bash
uv run --python 3.12 pytest tests/test_graph_readiness.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/vault_graph/graph/graph_readiness.py src/vault_graph/app/graph_readiness_service.py tests/test_graph_readiness.py
git commit -m "feat: add graph readiness service"
```

---

### Task 5: Wire Graph Readiness Into Status

**Files:**

- Modify: `src/vault_graph/app/catalog_service.py`
- Modify: `src/vault_graph/app/index_service.py`
- Modify: `src/vault_graph/cli/main.py`
- Test: `tests/test_cli_graph_status.py`
- Modify: existing status tests as needed

- [ ] **Step 1: Write failing CLI graph status tests**

Create `tests/test_cli_graph_status.py`:

```python
import json
from pathlib import Path

from typer.testing import CliRunner

from vault_graph.cli.main import app

runner = CliRunner()


def test_cli_status_reports_graph_readiness_without_creating_graph_state(tmp_path: Path) -> None:
    vault_root = tmp_path / "vault"
    vault_root.mkdir()
    state_path = tmp_path / "state"
    assert runner.invoke(app, ["init", "--vault", str(vault_root), "--state", str(state_path)]).exit_code == 0

    result = runner.invoke(app, ["status", "--state", str(state_path)])

    assert result.exit_code == 0
    assert "graph_backend: sqlite-graph" in result.stdout
    assert "graph_freshness: missing" in result.stdout
    assert "graph_schema_compatible: False" in result.stdout
    assert "graph_extraction_spec_version: graph-extraction-spec-v1" in result.stdout
    assert "graph_extraction_spec_digest: a0b9dbf6a6fff27580fe2fbb0b81a9799d63a14bcad2aef614d243fed93ffe37" in result.stdout
    assert not (state_path / "graph").exists()


def test_cli_status_json_reports_graph_readiness(tmp_path: Path) -> None:
    vault_root = tmp_path / "vault"
    vault_root.mkdir()
    state_path = tmp_path / "state"
    assert runner.invoke(app, ["init", "--vault", str(vault_root), "--state", str(state_path)]).exit_code == 0

    result = runner.invoke(app, ["status", "--state", str(state_path), "--format", "json"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["active_vault_id"] == "default"
    assert payload["graph"]["backend_name"] == "sqlite-graph"
    assert payload["graph"]["freshness"] == "missing"
    assert payload["graph"]["graph_extraction_spec_version"] == "graph-extraction-spec-v1"
    assert payload["graph"]["graph_extraction_spec_digest"] == "a0b9dbf6a6fff27580fe2fbb0b81a9799d63a14bcad2aef614d243fed93ffe37"
    assert payload["graph"]["scope_readiness"][0]["vault_id"] == "default"
    assert payload["graph"]["scope_readiness"][0]["freshness"] == "missing"
    assert payload["selected_scope"]["vault_ids"] == ["default"]


def test_cli_status_rejects_unknown_format(tmp_path: Path) -> None:
    vault_root = tmp_path / "vault"
    vault_root.mkdir()
    state_path = tmp_path / "state"
    assert runner.invoke(app, ["init", "--vault", str(vault_root), "--state", str(state_path)]).exit_code == 0

    result = runner.invoke(app, ["status", "--state", str(state_path), "--format", "xml"])

    assert result.exit_code == 1
    assert "unsupported_format" in result.stdout


def test_cli_status_all_vaults_uses_explicit_graph_scope(tmp_path: Path) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"
    first.mkdir()
    second.mkdir()
    state_path = tmp_path / "state"
    assert runner.invoke(app, ["init", "--vault-id", "first", "--vault", str(first), "--state", str(state_path)]).exit_code == 0
    assert runner.invoke(app, ["vault", "add", "second", "--path", str(second), "--state", str(state_path)]).exit_code == 0

    result = runner.invoke(app, ["status", "--state", str(state_path), "--all-vaults", "--format", "json"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["selected_scope"]["vault_ids"] == ["first", "second"]
    assert payload["graph"]["affected_vault_ids"] == ["first", "second"]
    assert [row["vault_id"] for row in payload["graph"]["scope_readiness"]] == ["first", "second"]
```

- [ ] **Step 2: Verify CLI tests fail**

Run:

```bash
uv run --python 3.12 pytest tests/test_cli_graph_status.py -q
```

Expected: FAIL because status does not include graph fields or JSON output.

- [ ] **Step 3: Add graph state path**

Modify `src/vault_graph/app/catalog_service.py`:

```python
self.graph_path = self.state_path / "graph" / "graph.sqlite3"
```

In `_service(state, initialize_store=True)` inside `src/vault_graph/cli/main.py`,
add:

```python
config.assert_write_target_safe(target_path=config.graph_path, catalog=catalog)
```

This assertion is a future-write guard only. Phase 3A must not initialize the
graph path during `vg index`.

- [ ] **Step 4: Extend `StatusReport`**

Modify `src/vault_graph/app/index_service.py`:

```python
from vault_graph.app.graph_readiness_service import ReadOnlyGraphReadiness
from vault_graph.graph.graph_readiness import GraphReadiness
from vault_graph.ingestion.query_scope_resolution import effective_query_scopes
```

Add `graph_readiness: GraphReadiness` to `StatusReport`.

Add optional constructor dependency:

```python
graph_readiness: ReadOnlyGraphReadiness | None = None
```

In `status(scope)`, resolve:

```python
effective_scopes = effective_query_scopes(catalog=self._catalog, scope=resolved_scope)
graph_readiness = self._graph_readiness.check(
    requested_scope=resolved_scope,
    effective_scopes=effective_scopes,
) if self._graph_readiness is not None else _graph_not_configured_readiness(resolved_scope)
```

Keep metadata and vector status behavior unchanged.

- [ ] **Step 5: Wire graph store into CLI service construction**

Modify `src/vault_graph/cli/main.py` imports:

```python
from vault_graph.app.graph_readiness_service import ReadOnlyGraphReadiness
from vault_graph.errors import GraphStoreError
from vault_graph.graph.graph_contracts import current_graph_extraction_spec
from vault_graph.storage.local.sqlite_graph_store import SQLiteGraphStore
```

Also add `GraphStoreError` to `_exit_on_domain_error(...)` so unexpected graph
domain errors render as user-facing CLI failures instead of tracebacks. Normal
missing, empty, stale, incompatible, and unavailable graph states should still
return through `GraphReadiness`.

In `_service(state, initialize_store)`, construct:

```python
graph_store = SQLiteGraphStore.open_read_only(config.graph_path)
```

and pass:

```python
graph_readiness=ReadOnlyGraphReadiness(
    metadata_store=metadata_store,
    graph_store=graph_store,
    expected_spec=current_graph_extraction_spec(),
),
```

Do not call `SQLiteGraphStore.open_writable(path)` from CLI in Phase 3A.

- [ ] **Step 6: Add `vg status --format text|json`**

Modify `status` in `src/vault_graph/cli/main.py`:

```python
output_format: str = typer.Option("text", "--format", help="Output format: text or json."),
```

Validate:

```python
if output_format not in {"text", "json"}:
    typer.echo("unsupported_format")
    raise typer.Exit(1)
```

If JSON, call `_status_report_json(report, config=config, selected_scope=scope)`.

Text output must include:

```text
graph_backend: sqlite-graph
graph_backend_available: False
graph_schema_version: sqlite-graph-v1
graph_schema_compatible: False
graph_extraction_spec_version: graph-extraction-spec-v1
graph_extraction_spec_digest: a0b9dbf6a6fff27580fe2fbb0b81a9799d63a14bcad2aef614d243fed93ffe37
graph_extraction_spec_compatible: False
graph_freshness: missing
graph_stale_count: 0
graph_tombstone_count: 0
graph_last_revision: None
graph_scope: default:raw,wiki,docs,scratch/reports:local missing None
graph_recovery_hint: run `vg index` after graph indexing is available
```

- [ ] **Step 7: Add explicit status JSON serializer**

Add a private CLI helper:

```python
def _status_report_json(report: StatusReport, *, config: CatalogService, selected_scope: QueryScope) -> dict[str, object]:
    graph = report.graph_readiness
    return {
        "state": str(config.state_path),
        "active_vault_id": report.active_vault_id,
        "vaults": [{"vault_id": vault_id, "root_path": root_path} for vault_id, root_path in report.vaults],
        "selected_scope": _scope_json(selected_scope),
        "metadata": {
            "ok": report.metadata_ok,
            "schema_compatible": report.metadata_schema_compatible,
            "message": report.metadata_message,
        },
        "vector": {
            "ok": report.vector_ok,
            "backend": report.vector_backend,
            "schema_compatible": report.vector_schema_compatible,
            "message": report.vector_message,
            "embedding_model": report.embedding_model,
            "embedding_model_version": report.embedding_model_version,
            "embedding_dimensions": report.embedding_dimensions,
            "embedding_spec_version": report.embedding_spec_version,
            "embedding_batch_size": report.embedding_batch_size,
            "embedding_parallelism": report.embedding_parallelism,
            "embedding_lazy_load": report.embedding_lazy_load,
            "revision": report.vector_revision,
            "stale_count": report.vector_stale_count,
            "last_error": report.vector_last_error,
            "status_scope": report.vector_status_scope,
        },
        "graph": {
            "backend_name": graph.backend_name,
            "backend_available": graph.backend_available,
            "schema_version": graph.schema_version,
            "schema_compatible": graph.schema_compatible,
            "graph_extraction_spec_version": graph.graph_extraction_spec_version,
            "graph_extraction_spec_digest": graph.graph_extraction_spec_digest,
            "graph_extraction_spec_compatible": graph.graph_extraction_spec_compatible,
            "freshness": graph.freshness,
            "stale_count": graph.stale_count,
            "tombstone_count": graph.tombstone_count,
            "last_graph_revision": graph.last_graph_revision,
            "affected_vault_ids": list(graph.affected_vault_ids),
            "scope_readiness": [
                {
                    "vault_id": row.vault_id,
                    "effective_scope": row.effective_scope,
                    "freshness": row.freshness,
                    "stale_count": row.stale_count,
                    "tombstone_count": row.tombstone_count,
                    "last_graph_revision": row.last_graph_revision,
                    "warnings": list(row.warnings),
                }
                for row in graph.scope_readiness
            ],
            "warnings": list(graph.warnings),
            "recovery_hint": graph.recovery_hint,
        },
    }
```

- [ ] **Step 8: Verify CLI status tests pass**

Run:

```bash
uv run --python 3.12 pytest tests/test_cli_graph_status.py tests/test_cli_vector_indexing.py tests/test_cli_surface_boundary.py -q
```

Expected: PASS.

- [ ] **Step 9: Commit**

```bash
git add src/vault_graph/app/catalog_service.py src/vault_graph/app/index_service.py src/vault_graph/cli/main.py tests/test_cli_graph_status.py tests/test_cli_vector_indexing.py tests/test_cli_surface_boundary.py
git commit -m "feat: report graph readiness in status"
```

---

### Task 6: Add Read-Only And Multi-Vault Regression Coverage

**Files:**

- Modify: `tests/test_read_only_boundary.py`
- Modify: `tests/test_vector_indexing_read_only_boundary.py`
- Modify: `tests/test_multi_vault_graph_identity.py`
- Optional Test: `tests/test_cli_graph_status.py`

- [ ] **Step 1: Add read-only status boundary tests**

Add to `tests/test_read_only_boundary.py`:

```python
def test_status_with_graph_readiness_does_not_modify_vault_or_create_graph_state(tmp_path: Path) -> None:
    vault_root = tmp_path / "vault"
    (vault_root / "wiki").mkdir(parents=True)
    (vault_root / "wiki" / "page.md").write_text("# Page\nBody\n", encoding="utf-8")
    state_path = tmp_path / "state"
    runner = CliRunner()
    runner.invoke(app, ["init", "--vault", str(vault_root), "--state", str(state_path)])
    before = file_bytes(vault_root)

    result = runner.invoke(app, ["status", "--state", str(state_path)])

    assert result.exit_code == 0
    assert file_bytes(vault_root) == before
    assert not (state_path / "graph").exists()
    assert not (state_path / "projection_cache").exists()
```

- [ ] **Step 2: Add graph path guard test**

Add to `tests/test_vector_indexing_read_only_boundary.py`:

```python
def test_graph_state_path_cannot_be_inside_vault_root(tmp_path: Path) -> None:
    vault_root = tmp_path / "vault"
    vault_root.mkdir()
    state_path = vault_root / ".vault-graph"

    result = runner.invoke(app, ["init", "--vault", str(vault_root), "--state", str(state_path)])

    assert result.exit_code != 0
    assert "state path must not be inside a registered Vault" in result.stdout
```

This overlaps with the state-path guard but preserves graph-specific intent in
the Phase 3A regression suite.

- [ ] **Step 3: Add multi-Vault SQLite graph regression**

Add to `tests/test_multi_vault_graph_identity.py`:

```python
from tests.test_graph_store_contract import make_entity, make_plan
from vault_graph.ingestion.vault_catalog import QueryScope
from vault_graph.storage.local.sqlite_graph_store import SQLiteGraphStore


def test_sqlite_graph_manifest_keeps_same_names_separate_by_vault(tmp_path: Path) -> None:
    store = SQLiteGraphStore.open_writable(tmp_path / "graph.sqlite3")
    first = make_entity("first", name="Shared")
    second = make_entity("second", name="Shared")
    store.apply_reconcile_plan(
        make_plan(
            entities=(first,),
            relationships=(),
            scope=QueryScope(vault_ids=("first",), content_scopes=("wiki")),
        )
    )
    store.apply_reconcile_plan(
        make_plan(
            entities=(second,),
            relationships=(),
            scope=QueryScope(vault_ids=("second",), content_scopes=("wiki")),
        )
    )

    first_manifest = store.current_manifest((QueryScope(vault_ids=("first",), content_scopes=("wiki")),))
    second_manifest = store.current_manifest((QueryScope(vault_ids=("second",), content_scopes=("wiki")),))

    assert tuple(row.vault_id for row in first_manifest.entity_rows) == ("first",)
    assert tuple(row.vault_id for row in second_manifest.entity_rows) == ("second",)


def test_sqlite_graph_manifest_requires_explicit_cross_vault_scope(tmp_path: Path) -> None:
    store = SQLiteGraphStore.open_writable(tmp_path / "graph.sqlite3")
    source = make_entity("first", name="Source")
    target = make_entity("second", name="Target")
    relationship = make_relationship(source, target)
    store.apply_reconcile_plan(
        make_plan(
            entities=(source,),
            relationships=(),
            scope=QueryScope(vault_ids=("first",), content_scopes=("wiki")),
        )
    )
    store.apply_reconcile_plan(
        make_plan(
            entities=(target,),
            relationships=(),
            scope=QueryScope(vault_ids=("second",), content_scopes=("wiki")),
        )
    )
    store.apply_reconcile_plan(
        make_plan(
            entities=(),
            relationships=(relationship,),
            scope=QueryScope(vault_ids=("first",), content_scopes=("wiki"), include_cross_vault=True),
        )
    )

    local_manifest = store.current_manifest((QueryScope(vault_ids=("first",), content_scopes=("wiki")),))
    cross_manifest = store.current_manifest(
        (
            QueryScope(vault_ids=("first",), content_scopes=("wiki"), include_cross_vault=True),
            QueryScope(vault_ids=("second",), content_scopes=("wiki"), include_cross_vault=True),
        )
    )

    assert local_manifest.relationship_rows == ()
    assert tuple(row.relationship_id for row in cross_manifest.relationship_rows) == (relationship.relationship_id,)
```

- [ ] **Step 4: Verify regression tests pass**

Run:

```bash
uv run --python 3.12 pytest tests/test_read_only_boundary.py tests/test_vector_indexing_read_only_boundary.py tests/test_multi_vault_graph_identity.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add tests/test_read_only_boundary.py tests/test_vector_indexing_read_only_boundary.py tests/test_multi_vault_graph_identity.py
git commit -m "test: harden graph readiness boundaries"
```

---

### Task 7: Final Verification And Documentation Trace

**Files:**

- Modify only if review found a real implementation correction:
  - `docs/PATCH_LOG.md`
  - `docs/DECISIONS.md`

- [ ] **Step 1: Run focused Phase 3A tests**

Run:

```bash
uv run --python 3.12 pytest \
  tests/test_graph_contracts.py \
  tests/test_graph_store_contract.py \
  tests/test_sqlite_graph_store.py \
  tests/test_graph_readiness.py \
  tests/test_cli_graph_status.py \
  tests/test_multi_vault_graph_identity.py \
  -q
```

Expected: PASS.

- [ ] **Step 2: Run read-only and CLI regression tests**

Run:

```bash
uv run --python 3.12 pytest \
  tests/test_read_only_boundary.py \
  tests/test_vector_indexing_read_only_boundary.py \
  tests/test_cli_vector_indexing.py \
  tests/test_cli_surface_boundary.py \
  -q
```

Expected: PASS.

- [ ] **Step 3: Run the full suite**

Run:

```bash
uv run --python 3.12 pytest -q
```

Expected: PASS.

- [ ] **Step 4: Run static checks**

Run:

```bash
uv run --python 3.12 ruff check src tests
uv run --python 3.12 mypy src
uv run --python 3.12 mypy tests
git diff --check
```

Expected: all commands exit `0`.

- [ ] **Step 5: Update patch log only when implementation changed the plan or design**

If implementation review required a correction, add a short concrete entry to
`docs/PATCH_LOG.md` with the actual trigger, scope, protected values, applied
changes, and verification commands. Do not add a generic template entry. Do not
add an entry if implementation follows the plan without correction.

- [ ] **Step 6: Record decisions only with user approval**

If a reviewer finds a policy decision that is not already accepted, stop and ask
the user. Use `docs/DECISIONS.md` only after approval.

- [ ] **Step 7: Final commit**

If prior tasks used task-level commits, make no extra commit unless verification
or documentation changed files. If implementing in one batch, commit all Phase
3A implementation files with exact paths:

```bash
git add \
  src/vault_graph/graph/__init__.py \
  src/vault_graph/graph/graph_contracts.py \
  src/vault_graph/graph/graph_identity.py \
  src/vault_graph/graph/graph_readiness.py \
  src/vault_graph/app/catalog_service.py \
  src/vault_graph/app/graph_readiness_service.py \
  src/vault_graph/app/index_service.py \
  src/vault_graph/cli/main.py \
  src/vault_graph/errors.py \
  src/vault_graph/storage/interfaces/__init__.py \
  src/vault_graph/storage/interfaces/graph_store.py \
  src/vault_graph/storage/local/__init__.py \
  src/vault_graph/storage/local/sqlite_graph_store.py \
  tests/fakes/in_memory_graph_store.py \
  tests/test_cli_graph_status.py \
  tests/test_cli_surface_boundary.py \
  tests/test_cli_vector_indexing.py \
  tests/test_graph_contracts.py \
  tests/test_graph_readiness.py \
  tests/test_graph_store_contract.py \
  tests/test_multi_vault_graph_identity.py \
  tests/test_read_only_boundary.py \
  tests/test_sqlite_graph_store.py \
  tests/test_vector_indexing_read_only_boundary.py
git add docs/PATCH_LOG.md  # only when implementation corrections changed it
git commit -m "feat: add graph store readiness"
```

## Acceptance Criteria

- `GraphExtractionSpec` has a canonical digest and is stored with records,
  manifests, and revisions.
- Entity IDs include `vault_id`.
- Relationship IDs include relationship type, source Vault/entity ID, and
  target Vault/entity ID.
- Evidence refs include owner kind, owner Vault ID, owner ID, and evidence
  Vault ID.
- `GraphStore` methods never expose SQLite row IDs.
- `GraphStore.current_manifest(scopes)` accepts only per-Vault effective scopes.
- In-memory and SQLite stores satisfy the same contract tests.
- Read-only graph store opening does not create missing graph files.
- `vg status` reports graph readiness when graph state is missing.
- `vg status --format json` exposes machine-readable graph readiness.
- `vg index` still does not write graph records in Phase 3A.
- No command mutates Vault content.
- Full tests, ruff, mypy, and `git diff --check` pass.

## Self-Review Checklist

- Spec coverage: every Phase 3A design boundary maps to a task above.
- Non-goals: no task adds extraction execution, `GraphIndexer`, `GraphProjection`, graph retrieval, or graph commands.
- Placeholder scan: every task has concrete paths, checks, and failure behavior.
- Type consistency: graph contract names match `docs/superpowers/specs/phase-3/2026-06-10-phase-3a-graphstore-contract-readiness-design.md`.
- Multi-vault consistency: entity, relationship, evidence, revision, and tombstone identity all carry Vault identity where collisions are possible.
- Read-only consistency: status uses read-only graph opening and missing graph state is a readiness value, not a write-trigger.

Plan complete and saved to `docs/superpowers/plans/2026-06-10-phase-3a-graphstore-contract-readiness.md`.
