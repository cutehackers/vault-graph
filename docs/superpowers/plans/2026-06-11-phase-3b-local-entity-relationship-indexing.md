# Phase 3B Local Entity And Relationship Indexing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the Phase 3B graph indexing slice so `vg index` can deterministically reconcile local entity, relationship, evidence, tombstone, and graph revision state for selected whole Vault scopes.

**Architecture:** Phase 3B is a deterministic indexing layer over the Phase 3A `GraphStore` contract. Metadata remains the evidence authority; `GraphIndexer` consumes a Vault-scoped `GraphSourceStore`, produces a `GraphReconcilePlan`, and writes only through `GraphStore.apply_reconcile_plan`. CLI and status surfaces extend the existing `IndexService` path instead of adding a separate graph command.

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
- `docs/superpowers/specs/phase-3/2026-06-10-phase-3b-local-entity-relationship-indexing-design.md`

The implementation request mentioned `docs/superpowers/spec/phase-3/`. The
accepted repo path is `docs/superpowers/specs/phase-3/`.

## Scope Guardrails

Phase 3B implements:

- extraction occurrence dataclasses and extractor Protocols
- a Vault-scoped `GraphSourceStore` read model over metadata and preview state
- deterministic entity extraction from document identity, headings, tags, and local links
- deterministic relationship extraction from mentions, local links, and explicit frontmatter fields
- behavior-named `GraphExtractionSpec` lineage for real deterministic indexing
- `GraphIndexer.plan` and `GraphIndexer.apply`
- scope-local graph reconcile against `GraphStore.current_manifest`
- graph revision rows using the same aggregate metadata/parser/chunker lineage as readiness
- projection cache invalidation keys in plans, without projection cache writes
- app-layer rejection of mixed-width content scopes with `unsupported_graph_scope_width`
- `IndexService` graph planning/apply after metadata, independent from vector success
- persisted local graph failure status for `vg status`
- `vg index` and `vg index --dry-run` graph fields
- `vg status` freshness becoming meaningful after graph indexing
- unit, integration, multi-vault, read-only, CLI, typing, and lint coverage

Phase 3B must not implement:

- `vg related`
- `vg decision-trace`
- `vg search --include-graph`
- implicit graph expansion in plain `vg search "query"`
- rustworkx `GraphProjection`
- projection cache creation
- LLM-assisted extraction
- general noun-phrase extraction
- graph embeddings
- cross-Vault entity merging
- cross-Vault relationship inference by name
- Neo4j or hosted graph backends
- Vault file mutation

Release-ready Phase 3B means a user can run:

```bash
vg init --vault /path/to/vault
vg index
vg status
vg status --format json
```

and see graph records reconciled under the configured Vault Graph state path,
while Vault content remains unchanged.

## Implementation Assumptions

- Phase 3A contracts already exist in:
  - `src/vault_graph/graph/graph_contracts.py`
  - `src/vault_graph/graph/graph_identity.py`
  - `src/vault_graph/storage/interfaces/graph_store.py`
  - `src/vault_graph/storage/local/sqlite_graph_store.py`
  - `tests/fakes/in_memory_graph_store.py`
- `GraphIndexer` must reuse those contracts. Do not create parallel entity,
  relationship, evidence, tombstone, manifest, or revision record types.
- `current_graph_extraction_spec()` remains the graph compatibility boundary,
  but Phase 3B must replace the Phase 3A roadmap-label placeholder names with
  behavior names before writing graph records. Use:
  - `spec_version="graph-extraction-spec-v2"`
  - `entity_extractor_name="local-deterministic-entity-extractor"`
  - `entity_extractor_version="explicit-signals-v1"`
  - `relationship_extractor_name="local-deterministic-relationship-extractor"`
  - `relationship_extractor_version="explicit-signals-v1"`
  Updating names changes the digest, so the version bump is required by the
  Phase 3A compatibility contract.
- `MetadataStore.resolve_document(document_id)` is not Vault-scoped. Phase 3B
  must add an adapter that calls it and rejects documents whose `vault_id` does
  not match the requested `vault_id`.
- `MetadataIndexer.preview` must expose the post-apply document view needed by
  dry-run graph planning without writing metadata, vector, graph, cache, or
  Vault files.
- Phase 3B supports only whole selected Vault scopes: active Vault, explicit
  `--vault-id`, or `--all-vaults`. Programmatic content-scope-limited graph
  indexing must return `unsupported_graph_scope_width` before `GraphIndexer`.

## File Structure

Create:

- `src/vault_graph/extraction/__init__.py`: public extraction package marker.
- `src/vault_graph/extraction/graph_occurrences.py`: immutable `EntityOccurrence`, `RelationshipOccurrence`, occurrence-key helpers, and extraction warning values.
- `src/vault_graph/extraction/graph_source_store.py`: `GraphSourceStore`, `GraphExtractionContext`, `MetadataGraphSourceStore`, and `PreviewGraphSourceStore`.
- `src/vault_graph/extraction/entity_extractor.py`: `EntityExtractor` Protocol and `DeterministicEntityExtractor`.
- `src/vault_graph/extraction/relationship_extractor.py`: `RelationshipExtractor` Protocol and `DeterministicRelationshipExtractor`.
- `src/vault_graph/indexing/graph_indexer.py`: `GraphIndexPlanReport`, `GraphIndexApplyResult`, and `GraphIndexer`.
- `src/vault_graph/storage/local/graph_status_store.py`: local graph run status JSON for last success and last failure.
- `tests/test_graph_occurrences.py`
- `tests/test_graph_source_store.py`
- `tests/test_entity_extractor.py`
- `tests/test_relationship_extractor.py`
- `tests/test_graph_status_store.py`
- `tests/test_graph_indexer.py`
- `tests/test_index_service_graph_reconcile.py`
- `tests/test_cli_graph_indexing.py`
- `tests/test_graph_indexing_read_only_boundary.py`
- `tests/test_multi_vault_graph_indexing.py`

Modify:

- `src/vault_graph/errors.py`: add graph indexing and extraction errors.
- `src/vault_graph/graph/graph_contracts.py`: replace roadmap-label extractor names with behavior names and bump `GraphExtractionSpec.spec_version`.
- `src/vault_graph/indexing/revision_planner.py`: add `documents_after_apply` to `MetadataIndexPreview`.
- `src/vault_graph/indexing/metadata_indexer.py`: populate preview document snapshots.
- `src/vault_graph/indexing/__init__.py`: export public Phase 3B indexer pieces only if package exports are already used.
- `src/vault_graph/storage/local/sqlite_graph_store.py`: harden read errors and clear scoped tombstones when active records reappear.
- `tests/fakes/in_memory_graph_store.py`: mirror scoped tombstone clearing for contract tests.
- `src/vault_graph/app/index_service.py`: add graph dependencies, graph plan/apply path, graph failure reporting, and scope-width validation.
- `src/vault_graph/app/catalog_service.py`: add `graph_status_path`.
- `src/vault_graph/cli/main.py`: open writable graph store for apply, render graph fields, and include graph errors in domain handling.
- Existing graph contract/readiness/store/status tests: update expected graph extraction spec version/digest and add assertions for fresh graph readiness after indexing.

Do not modify `docs/DECISIONS.md` unless implementation reveals a new policy
choice that needs user approval. Review-driven implementation-plan corrections
belong in `docs/PATCH_LOG.md`.

## Runtime Data Flow

Dry-run flow:

```text
vg index --dry-run
  -> CatalogService.load_catalog()
  -> resolve requested QueryScope
  -> MetadataIndexer.preview(scope, full)
  -> PreviewGraphSourceStore(chunks_after_apply, documents_after_apply)
  -> graph_actual_scopes(catalog, scope)
  -> validate whole selected Vault graph scopes
  -> graph health/schema gate
  -> GraphIndexer.plan(requested_scope, actual_scopes)
       -> GraphSourceStore.list_chunks(actual_scope)
       -> GraphSourceStore.resolve_document(vault_id, document_id)
       -> GraphStore.current_manifest(actual_scopes)
       -> extract occurrences
       -> dedupe desired graph records
       -> build GraphReconcilePlan
  -> render metadata, vector, and planned graph counts
```

Apply flow:

```text
vg index
  -> MetadataIndexer.apply(scope, full)
  -> VectorIndexer.apply(...) when vector dependencies are configured
  -> MetadataGraphSourceStore(metadata_store)
  -> SQLiteGraphStore.open_writable(graph_path)
  -> graph health/schema gate
  -> GraphIndexer.apply(requested_scope, actual_scopes)
       -> GraphIndexer.plan(...)
       -> GraphStore.apply_reconcile_plan(plan)
  -> record independent vector and graph failures
  -> LocalGraphStatusStore records graph success/failure for status
  -> exit 1 if any enabled derived-state step failed
```

Status flow after graph indexing:

```text
vg status --format json
  -> ReadOnlyGraphReadiness.check(...)
  -> compare latest graph revisions with current metadata lineage
  -> resolve graph evidence through MetadataStore
  -> read LocalGraphStatusStore for last graph failure
  -> report fresh/stale/missing/incompatible per actual scope
```

## Error Handling

Add these errors in `src/vault_graph/errors.py`:

```python
class GraphIndexingError(VaultGraphError):
    """Raised when graph indexing cannot complete."""


class GraphExtractionError(GraphIndexingError):
    """Raised when deterministic graph extraction produces invalid data."""


class GraphReconcileError(GraphIndexingError):
    """Raised when desired graph state cannot be reconciled with current state."""


class UnsupportedGraphScopeWidthError(GraphIndexingError):
    """Raised when graph indexing is requested for content-scope-limited paths."""
```

Error policy:

- metadata failure aborts vector and graph work
- vector failure does not prevent graph planning/apply when metadata succeeded
- graph failure does not roll back successful metadata or vector state
- graph failure returns a nonzero `vg index` exit code
- unsupported graph scope width is reported as `unsupported_graph_scope_width`
- unresolved local links become concept mentions and graph plan warnings
- invalid graph records fail loudly through `GraphExtractionError` or existing `GraphRecordInvalid`
- dry-run must not initialize graph storage
- status must remain read-only

---

### Task 1: Add Graph Occurrence Contracts

**Files:**

- Create: `src/vault_graph/extraction/__init__.py`
- Create: `src/vault_graph/extraction/graph_occurrences.py`
- Modify: `src/vault_graph/errors.py`
- Modify: `src/vault_graph/graph/graph_contracts.py`
- Test: `tests/test_graph_occurrences.py`
- Test: `tests/test_graph_contracts.py`
- Test: `tests/test_cli_graph_status.py`

- [ ] **Step 1: Write failing occurrence tests**

Create `tests/test_graph_occurrences.py`:

```python
import pytest

from vault_graph.errors import GraphExtractionError
from vault_graph.extraction.graph_occurrences import (
    EntityOccurrence,
    RelationshipOccurrence,
    entity_occurrence_key,
)


def test_entity_occurrence_key_is_vault_scoped() -> None:
    first = EntityOccurrence(
        vault_id="first",
        entity_type="Concept",
        name="GraphRAG",
        normalized_name="graphrag",
        aliases=(),
        canonical_path=None,
        evidence_vault_id="first",
        document_id="doc",
        chunk_id="chunk",
        content_hash="hash",
        section="GraphRAG",
        anchor="graphrag",
        path="wiki/page.md",
        excerpt="GraphRAG",
        confidence=0.85,
        extraction_method="heading-concept-v1",
    )
    second = EntityOccurrence(
        **{**first.__dict__, "vault_id": "second", "evidence_vault_id": "second"}
    )

    assert entity_occurrence_key(first) != entity_occurrence_key(second)


def test_entity_occurrence_rejects_missing_evidence() -> None:
    with pytest.raises(GraphExtractionError, match="chunk_id is required"):
        EntityOccurrence(
            vault_id="default",
            entity_type="Concept",
            name="GraphRAG",
            normalized_name="graphrag",
            aliases=(),
            canonical_path=None,
            evidence_vault_id="default",
            document_id="doc",
            chunk_id="",
            content_hash="hash",
            section=None,
            anchor=None,
            path="wiki/page.md",
            excerpt=None,
            confidence=0.8,
            extraction_method="test",
        )


def test_relationship_occurrence_status_is_limited() -> None:
    with pytest.raises(GraphExtractionError, match="unsupported relationship status"):
        RelationshipOccurrence(
            relationship_type="depends_on",
            source_vault_id="default",
            source_entity_key=("default", "Document", "source", "wiki/source.md"),
            target_vault_id="default",
            target_entity_key=("default", "Document", "target", "wiki/target.md"),
            evidence_vault_id="default",
            document_id="doc",
            chunk_id="chunk",
            content_hash="hash",
            section=None,
            anchor=None,
            path="wiki/source.md",
            excerpt=None,
            status="confirmed",
            confidence=0.9,
            extraction_method="test",
        )
```

- [ ] **Step 2: Verify the tests fail**

Run:

```bash
uv run --python 3.12 pytest tests/test_graph_occurrences.py -q
```

Expected: FAIL because `graph_occurrences.py` and graph indexing errors do not exist.

- [ ] **Step 3: Add graph indexing errors and behavior-named spec**

Modify `src/vault_graph/errors.py` with the error classes from the Error
Handling section. Keep existing `GraphStoreError` classes unchanged.

Modify `src/vault_graph/graph/graph_contracts.py` so
`current_graph_extraction_spec()` uses behavior names instead of roadmap labels:

```python
def current_graph_extraction_spec() -> GraphExtractionSpec:
    return GraphExtractionSpec.from_payload(
        {
            "spec_version": "graph-extraction-spec-v2",
            "entity_schema_version": "entity-schema-v1",
            "relationship_schema_version": "relationship-schema-v1",
            "entity_extractor_name": "local-deterministic-entity-extractor",
            "entity_extractor_version": "explicit-signals-v1",
            "relationship_extractor_name": "local-deterministic-relationship-extractor",
            "relationship_extractor_version": "explicit-signals-v1",
            "relationship_status_rules_version": "relationship-status-rules-v1",
            "confidence_rules_version": "confidence-rules-v1",
        }
    )
```

Update existing graph spec/status tests so they assert:

- `spec.spec_version == "graph-extraction-spec-v2"`
- extractor names contain no `phase` or roadmap labels
- current digest remains canonical through `GraphExtractionSpec.from_payload`
- the legacy Phase 3A placeholder payload has a different digest and a different
  `spec_version`
- CLI graph status text and JSON use the new version/digest

- [ ] **Step 4: Implement occurrence dataclasses**

Create `src/vault_graph/extraction/__init__.py`.

Create `src/vault_graph/extraction/graph_occurrences.py`:

```python
from __future__ import annotations

from dataclasses import dataclass

from vault_graph.errors import GraphExtractionError

EntityOccurrenceKey = tuple[str, str, str, str]


@dataclass(frozen=True)
class GraphExtractionWarning:
    code: str
    message: str
    vault_id: str
    path: str
    chunk_id: str


def _require_non_empty(value: str, field_name: str) -> None:
    if not value:
        raise GraphExtractionError(f"{field_name} is required")


@dataclass(frozen=True)
class EntityOccurrence:
    vault_id: str
    entity_type: str
    name: str
    normalized_name: str
    aliases: tuple[str, ...]
    canonical_path: str | None
    evidence_vault_id: str
    document_id: str
    chunk_id: str
    content_hash: str
    section: str | None
    anchor: str | None
    path: str
    excerpt: str | None
    confidence: float
    extraction_method: str

    def __post_init__(self) -> None:
        for field_name in (
            "vault_id",
            "entity_type",
            "name",
            "normalized_name",
            "evidence_vault_id",
            "document_id",
            "chunk_id",
            "content_hash",
            "path",
            "extraction_method",
        ):
            _require_non_empty(str(getattr(self, field_name)), field_name)
        if not isinstance(self.aliases, tuple):
            raise GraphExtractionError("aliases must be a tuple")
        if not 0 <= self.confidence <= 1:
            raise GraphExtractionError("confidence must be between 0 and 1")


@dataclass(frozen=True)
class RelationshipOccurrence:
    relationship_type: str
    source_vault_id: str
    source_entity_key: EntityOccurrenceKey
    target_vault_id: str
    target_entity_key: EntityOccurrenceKey
    evidence_vault_id: str
    document_id: str
    chunk_id: str
    content_hash: str
    section: str | None
    anchor: str | None
    path: str
    excerpt: str | None
    status: str
    confidence: float
    extraction_method: str

    def __post_init__(self) -> None:
        for field_name in (
            "relationship_type",
            "source_vault_id",
            "target_vault_id",
            "evidence_vault_id",
            "document_id",
            "chunk_id",
            "content_hash",
            "path",
            "extraction_method",
        ):
            _require_non_empty(str(getattr(self, field_name)), field_name)
        if self.status not in {"stated", "inferred", "contested", "deprecated"}:
            raise GraphExtractionError(f"unsupported relationship status: {self.status}")
        if not 0 <= self.confidence <= 1:
            raise GraphExtractionError("confidence must be between 0 and 1")


def entity_occurrence_key(occurrence: EntityOccurrence) -> EntityOccurrenceKey:
    return (
        occurrence.vault_id,
        occurrence.entity_type,
        occurrence.normalized_name,
        occurrence.canonical_path or "",
    )
```

- [ ] **Step 5: Verify occurrence and spec tests pass**

Run:

```bash
uv run --python 3.12 pytest tests/test_graph_occurrences.py tests/test_graph_contracts.py tests/test_cli_graph_status.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/vault_graph/errors.py src/vault_graph/graph/graph_contracts.py src/vault_graph/extraction/__init__.py src/vault_graph/extraction/graph_occurrences.py tests/test_graph_occurrences.py tests/test_graph_contracts.py tests/test_cli_graph_status.py
git commit -m "feat: add graph extraction occurrence contracts"
```

### Task 2: Add Vault-Scoped Graph Source Stores

**Files:**

- Create: `src/vault_graph/extraction/graph_source_store.py`
- Modify: `src/vault_graph/indexing/revision_planner.py`
- Modify: `src/vault_graph/indexing/metadata_indexer.py`
- Test: `tests/test_graph_source_store.py`
- Existing tests: metadata indexer tests if preview shape changes

- [ ] **Step 1: Write failing graph source tests**

Create `tests/test_graph_source_store.py`:

```python
from vault_graph.extraction.graph_source_store import MetadataGraphSourceStore, PreviewGraphSourceStore
from vault_graph.ingestion.document_normalizer import ChunkSnapshot, DocumentSnapshot
from vault_graph.ingestion.vault_catalog import QueryScope
from vault_graph.storage.interfaces.metadata_store import DocumentState


def document(vault_id: str, path: str, document_id: str) -> DocumentSnapshot:
    return DocumentSnapshot(
        vault_id=vault_id,
        document_id=document_id,
        path=path,
        kind=path.split("/", 1)[0],
        frontmatter={"title": path},
        frontmatter_hash="frontmatter",
        content_hash="content",
        raw_sha256="raw",
        parser_version="markdown-frontmatter-v1",
        last_seen_at="2026-06-11T00:00:00+00:00",
        last_indexed_at=None,
        vault_revision=None,
        index_revision="metadata-1",
    )


def chunk(vault_id: str, document_id: str, path: str) -> ChunkSnapshot:
    return ChunkSnapshot(
        vault_id=vault_id,
        chunk_id=f"{vault_id}-chunk",
        document_id=document_id,
        path=path,
        section="Title",
        anchor="title",
        text="# Title\nBody",
        token_count=3,
        content_hash=f"{vault_id}-hash",
        chunker_version="heading-section-v1",
        index_revision="metadata-1",
    )


class FakeMetadataStore:
    def __init__(self) -> None:
        self.documents = {
            "shared": document("first", "wiki/page.md", "shared"),
        }

    def list_chunks(self, scope: QueryScope) -> tuple[ChunkSnapshot, ...]:
        return (chunk("first", "shared", "wiki/page.md"),)

    def resolve_document(self, document_id: str) -> DocumentSnapshot | None:
        return self.documents.get(document_id)


def test_metadata_graph_source_resolution_is_vault_scoped() -> None:
    source = MetadataGraphSourceStore(FakeMetadataStore())

    assert source.resolve_document(vault_id="first", document_id="shared") is not None
    assert source.resolve_document(vault_id="second", document_id="shared") is None


def test_preview_graph_source_lists_chunks_and_documents_without_metadata_store() -> None:
    doc = document("default", "wiki/page.md", "doc")
    source = PreviewGraphSourceStore(chunks=(chunk("default", "doc", "wiki/page.md"),), documents=(doc,))

    assert source.list_chunks(QueryScope(vault_ids=("default",), content_scopes=("wiki",)))
    assert source.resolve_document(vault_id="default", document_id="doc") == doc
```

- [ ] **Step 2: Verify the tests fail**

Run:

```bash
uv run --python 3.12 pytest tests/test_graph_source_store.py -q
```

Expected: FAIL because source store module does not exist.

- [ ] **Step 3: Extend metadata preview with document snapshots**

Modify `src/vault_graph/indexing/revision_planner.py`:

```python
from vault_graph.ingestion.document_normalizer import ChunkSnapshot, DocumentSnapshot


@dataclass(frozen=True)
class MetadataIndexPreview:
    plan: MetadataRevisionPlan
    chunks_after_apply: tuple[ChunkSnapshot, ...]
    documents_after_apply: tuple[DocumentSnapshot, ...]
```

Modify `MetadataIndexer.preview` so it returns:

- changed documents with `index_revision=plan.index_revision`
- unchanged documents resolved from current metadata state
- changed chunks with `index_revision=plan.index_revision`
- unchanged chunks from `MetadataStore.list_chunks(scope)`

Use deterministic sorting:

```python
def _document_sort_key(document: DocumentSnapshot) -> tuple[str, str, str]:
    return (document.vault_id, document.path, document.document_id)
```

Implementation rule: if an unchanged `DocumentState.document_id` is `None` or
`MetadataStore.resolve_document` returns `None`, skip that document and let
graph planning warn or resolve fewer records. Do not write metadata during
preview.

- [ ] **Step 4: Implement graph source store module**

Create `src/vault_graph/extraction/graph_source_store.py`:

```python
from __future__ import annotations

from pathlib import PurePosixPath
from typing import Protocol

from vault_graph.ingestion.document_normalizer import ChunkSnapshot, DocumentSnapshot
from vault_graph.ingestion.vault_catalog import QueryScope
from vault_graph.storage.interfaces.metadata_store import MetadataStore


class GraphSourceStore(Protocol):
    def list_chunks(self, scope: QueryScope) -> tuple[ChunkSnapshot, ...]: ...
    def resolve_document(self, *, vault_id: str, document_id: str) -> DocumentSnapshot | None: ...


class MetadataGraphSourceStore:
    def __init__(self, metadata_store: MetadataStore) -> None:
        self._metadata_store = metadata_store

    def list_chunks(self, scope: QueryScope) -> tuple[ChunkSnapshot, ...]:
        return self._metadata_store.list_chunks(scope)

    def resolve_document(self, *, vault_id: str, document_id: str) -> DocumentSnapshot | None:
        document = self._metadata_store.resolve_document(document_id)
        if document is None or document.vault_id != vault_id:
            return None
        return document


class PreviewGraphSourceStore:
    def __init__(self, *, chunks: tuple[ChunkSnapshot, ...], documents: tuple[DocumentSnapshot, ...]) -> None:
        self._chunks = chunks
        self._documents = {(document.vault_id, document.document_id): document for document in documents}

    def list_chunks(self, scope: QueryScope) -> tuple[ChunkSnapshot, ...]:
        return tuple(
            chunk
            for chunk in self._chunks
            if chunk.vault_id in scope.vault_ids
            and any(chunk.path == content_scope or chunk.path.startswith(f"{content_scope}/")
                    for content_scope in scope.content_scopes)
        )

    def resolve_document(self, *, vault_id: str, document_id: str) -> DocumentSnapshot | None:
        return self._documents.get((vault_id, document_id))


class GraphExtractionContext:
    def __init__(
        self,
        *,
        scope: QueryScope,
        current_documents: tuple[DocumentSnapshot, ...],
        source_store: GraphSourceStore,
    ) -> None:
        self.scope = scope
        self.source_store = source_store
        self.current_document_paths = tuple(sorted(document.path for document in current_documents))
        self._documents_by_path = {(document.vault_id, document.path): document for document in current_documents}
        self._documents_by_basename = _basename_index(current_documents)

    def resolve_local_document_link(self, source_path: str, raw_target: str) -> DocumentSnapshot | None:
        target_path = _normalize_link_target(source_path=source_path, raw_target=raw_target)
        if target_path is None:
            return None
        vault_id = self.scope.vault_ids[0]
        exact = self._documents_by_path.get((vault_id, target_path))
        if exact is not None:
            return exact
        if "/" not in target_path:
            matches = self._documents_by_basename.get((vault_id, _ensure_md_suffix(target_path)), ())
            if len(matches) == 1:
                return matches[0]
        return None
```

Keep `_normalize_link_target`, `_ensure_md_suffix`, and `_basename_index` as
private pure helpers in this module. Use `PurePosixPath` and reject external
URLs, empty targets, and path escapes that normalize above the Vault-relative
root.

- [ ] **Step 5: Verify source store and metadata tests pass**

Run:

```bash
uv run --python 3.12 pytest tests/test_graph_source_store.py tests/test_metadata_indexer.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/vault_graph/indexing/revision_planner.py src/vault_graph/indexing/metadata_indexer.py src/vault_graph/extraction/graph_source_store.py tests/test_graph_source_store.py tests/test_metadata_indexer.py
git commit -m "feat: add graph source store views"
```

### Task 3: Implement Deterministic Entity Extraction

**Files:**

- Create: `src/vault_graph/extraction/entity_extractor.py`
- Test: `tests/test_entity_extractor.py`

- [ ] **Step 1: Write failing entity extractor tests**

Create tests for these behaviors:

- document-level entity from `wiki/page.md` is `WikiPage`
- document-level entity from `raw/source.md` is `Source`
- decision entity from `docs/decisions/choice.md` or frontmatter `type: decision`
- heading concept entity skips generic headings such as `Overview`
- frontmatter tags create `Concept` occurrences with stripped `#`
- resolvable `[[Target]]` creates a target document entity occurrence
- unresolved `[[Missing]]` creates a `Concept` occurrence with extraction method `unresolved-local-link-concept-v1`
- frontmatter relationship fields create target entity occurrences through the
  real metadata document snapshot path, not by manually supplying target
  entities in the test

Run:

```bash
uv run --python 3.12 pytest tests/test_entity_extractor.py -q
```

Expected: FAIL because `entity_extractor.py` does not exist.

- [ ] **Step 2: Implement public interface and deterministic extractor**

Create `src/vault_graph/extraction/entity_extractor.py`:

```python
from __future__ import annotations

import re
from pathlib import PurePosixPath
from typing import Protocol

from vault_graph.graph.graph_contracts import GraphExtractionSpec
from vault_graph.graph.graph_identity import normalize_entity_name
from vault_graph.extraction.graph_occurrences import EntityOccurrence
from vault_graph.extraction.graph_source_store import GraphExtractionContext
from vault_graph.ingestion.document_normalizer import ChunkSnapshot, DocumentSnapshot
from vault_graph.ingestion.vault_catalog import QueryScope


class EntityExtractor(Protocol):
    def extract(
        self,
        *,
        chunk: ChunkSnapshot,
        document: DocumentSnapshot | None,
        context: GraphExtractionContext,
        scope: QueryScope,
        spec: GraphExtractionSpec,
    ) -> tuple[EntityOccurrence, ...]: ...


class DeterministicEntityExtractor:
    def extract(
        self,
        *,
        chunk: ChunkSnapshot,
        document: DocumentSnapshot | None,
        context: GraphExtractionContext,
        scope: QueryScope,
        spec: GraphExtractionSpec,
    ) -> tuple[EntityOccurrence, ...]:
        occurrences: list[EntityOccurrence] = []
        if document is not None:
            occurrences.append(_document_entity(chunk=chunk, document=document))
            occurrences.extend(_tag_entities(chunk=chunk, document=document))
            occurrences.extend(_frontmatter_target_entities(chunk=chunk, document=document, context=context))
        if chunk.section and not _generic_heading(chunk.section):
            occurrences.append(_heading_entity(chunk))
        occurrences.extend(_link_entities(chunk=chunk, context=context))
        return tuple(_dedupe_occurrences(occurrences))
```

Required private helpers:

- `_document_entity(chunk, document) -> EntityOccurrence`
- `_document_entity_type(document) -> str`
- `_document_name(document, chunk) -> str`
- `_aliases(document) -> tuple[str, ...]`
- `_heading_entity(chunk) -> EntityOccurrence`
- `_tag_entities(chunk, document) -> tuple[EntityOccurrence, ...]`
- `_link_entities(chunk, context) -> tuple[EntityOccurrence, ...]`
- `_frontmatter_target_entities(chunk, document, context) -> tuple[EntityOccurrence, ...]`
- `_local_links(text) -> tuple[ParsedLocalLink, ...]`
- `_dedupe_occurrences(occurrences) -> tuple[EntityOccurrence, ...]`

Entity type rules:

```text
frontmatter type/kind == decision OR path contains /decisions/ -> Decision
path starts wiki/ -> WikiPage
path starts raw/ -> Source
otherwise -> Document
```

Name selection order:

```text
frontmatter title
first H1 in chunk text
basename without .md
Vault-relative path
```

Supported local links:

```text
[label](relative/path.md)
[label](../relative/path.md#anchor)
[[Page]]
[[Page|Label]]
```

External URLs and same-page anchors are ignored. Unresolved local links become
`Concept` occurrences, not document entities.

- [ ] **Step 3: Verify entity extractor tests pass**

Run:

```bash
uv run --python 3.12 pytest tests/test_entity_extractor.py -q
```

Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add src/vault_graph/extraction/entity_extractor.py tests/test_entity_extractor.py
git commit -m "feat: add deterministic entity extraction"
```

### Task 4: Implement Deterministic Relationship Extraction

**Files:**

- Create: `src/vault_graph/extraction/relationship_extractor.py`
- Test: `tests/test_relationship_extractor.py`

- [ ] **Step 1: Write failing relationship extractor tests**

Create tests for:

- heading concept produces `mentions`
- frontmatter tag concept produces `mentions`
- unresolved local link concept produces `mentions`
- resolvable local Markdown/wiki link produces `links_to`
- frontmatter `depends_on`, `blocks`, `implements`, `supersedes`, `related`, and `revisit_when` produce the expected relationship type when target entity exists
- frontmatter relationship fields pass through the actual entity extractor
  output from document snapshots so `GraphIndexer` can persist the relationship
- duplicate relationships for the same source, target, type, and evidence chunk are removed

Run:

```bash
uv run --python 3.12 pytest tests/test_relationship_extractor.py -q
```

Expected: FAIL because `relationship_extractor.py` does not exist.

- [ ] **Step 2: Implement public interface and deterministic extractor**

Create `src/vault_graph/extraction/relationship_extractor.py`:

```python
from __future__ import annotations

from typing import Protocol

from vault_graph.graph.graph_contracts import GraphExtractionSpec
from vault_graph.extraction.graph_occurrences import EntityOccurrence, RelationshipOccurrence, entity_occurrence_key
from vault_graph.extraction.graph_source_store import GraphExtractionContext
from vault_graph.ingestion.document_normalizer import ChunkSnapshot, DocumentSnapshot
from vault_graph.ingestion.vault_catalog import QueryScope


class RelationshipExtractor(Protocol):
    def extract(
        self,
        *,
        chunk: ChunkSnapshot,
        document: DocumentSnapshot | None,
        entities: tuple[EntityOccurrence, ...],
        context: GraphExtractionContext,
        scope: QueryScope,
        spec: GraphExtractionSpec,
    ) -> tuple[RelationshipOccurrence, ...]: ...


class DeterministicRelationshipExtractor:
    def extract(
        self,
        *,
        chunk: ChunkSnapshot,
        document: DocumentSnapshot | None,
        entities: tuple[EntityOccurrence, ...],
        context: GraphExtractionContext,
        scope: QueryScope,
        spec: GraphExtractionSpec,
    ) -> tuple[RelationshipOccurrence, ...]:
        if document is None:
            return ()
        document_entity = _document_entity(entities)
        if document_entity is None:
            return ()
        relationships = []
        relationships.extend(_mention_relationships(chunk=chunk, source=document_entity, entities=entities))
        relationships.extend(_link_relationships(chunk=chunk, source=document_entity, entities=entities))
        relationships.extend(_frontmatter_relationships(chunk=chunk, document=document, source=document_entity, entities=entities))
        return tuple(_dedupe_relationships(relationships))
```

Relationship rules:

| Entity occurrence method/type | Relationship |
| --- | --- |
| `heading-concept-v1` | `mentions` |
| `frontmatter-tag-concept-v1` | `mentions` |
| `unresolved-local-link-concept-v1` | `mentions` |
| `local-link-target-document-v1` | `links_to` |
| `frontmatter-related-target-v1` | `related_to` |
| `frontmatter-depends-on-target-v1` | `depends_on` |
| `frontmatter-blocks-target-v1` | `blocks` |
| `frontmatter-implements-target-v1` | `implements` |
| `frontmatter-supersedes-target-v1` | `supersedes` |
| `frontmatter-revisit-when-concept-v1` | `revisit_when` |

Use `status="stated"` for Phase 3B deterministic relationships. Use confidence
from the Phase 3B design table.

- [ ] **Step 3: Verify relationship extractor tests pass**

Run:

```bash
uv run --python 3.12 pytest tests/test_relationship_extractor.py -q
```

Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add src/vault_graph/extraction/relationship_extractor.py tests/test_relationship_extractor.py
git commit -m "feat: add deterministic relationship extraction"
```

### Task 5: Harden Graph Store Apply And Graph Status State

**Files:**

- Create: `src/vault_graph/storage/local/graph_status_store.py`
- Modify: `src/vault_graph/storage/local/sqlite_graph_store.py`
- Modify: `tests/fakes/in_memory_graph_store.py`
- Modify: `src/vault_graph/app/catalog_service.py`
- Test: `tests/test_graph_status_store.py`
- Test: `tests/test_graph_store_contract.py`
- Test: `tests/test_sqlite_graph_store.py`

- [ ] **Step 1: Write failing status and tombstone repair tests**

Cover:

- `LocalGraphStatusStore.record_failure` preserves the previous successful graph revision
- `LocalGraphStatusStore.record_success` clears the last graph error
- active entity upsert clears the matching scoped entity tombstone
- active relationship upsert clears the matching scoped relationship tombstone
- `SQLiteGraphStore.current_manifest` converts read-time SQLite failures into `GraphStoreUnavailable`

Run:

```bash
uv run --python 3.12 pytest tests/test_graph_status_store.py tests/test_graph_store_contract.py tests/test_sqlite_graph_store.py -q
```

Expected: FAIL because graph status storage and tombstone repair are not implemented.

- [ ] **Step 2: Add local graph status store**

Create `src/vault_graph/storage/local/graph_status_store.py` using the same
small JSON pattern as `LocalVectorStatusStore`:

```python
@dataclass(frozen=True)
class GraphRunStatus:
    scope_key: str
    graph_spec_key: str
    last_success_revision: str | None = None
    last_success_at: str | None = None
    last_error: str | None = None
    last_error_at: str | None = None


class LocalGraphStatusStore:
    def read(self, *, scope_key: str, graph_spec_key: str) -> GraphRunStatus: ...
    def record_success(self, *, scope_key: str, graph_spec_key: str, graph_index_revision: str) -> None: ...
    def record_failure(self, *, scope_key: str, graph_spec_key: str, error: str) -> None: ...
```

Add helpers:

```python
def graph_spec_key(spec: GraphExtractionSpec) -> str:
    return f"{spec.spec_version}|{spec.spec_digest}"


def graph_scope_status_key(scope: QueryScope) -> str:
    return f"{','.join(scope.vault_ids)}:{','.join(scope.content_scopes)}:{'cross' if scope.include_cross_vault else 'local'}"
```

Only `record_*` creates the file. `read` must not create parent directories or
files, preserving status/dry-run read-only behavior.

- [ ] **Step 3: Add graph status path**

Modify `src/vault_graph/app/catalog_service.py`:

```python
self.graph_status_path = self.state_path / "graph" / "status.json"
```

When CLI initializes stores for apply, validate this write target with
`assert_write_target_safe` alongside `graph_path`.

- [ ] **Step 4: Clear scoped tombstones on active upsert**

Modify both SQLite and in-memory graph stores so applying an active upsert clears
the matching tombstone for the same `(record_kind, record_vault_id, record_id,
actual_scope)`.

SQLite implementation rule:

- after `_upsert_record_scopes(...)` for an entity, delete matching
  `graph_tombstones` rows for the entity/scopes that were just upserted
- after `_upsert_record_scopes(...)` for a relationship, delete matching
  `graph_tombstones` rows for the relationship/scopes that were just upserted
- do not delete tombstones for other scopes
- do not hard-delete graph records themselves

In-memory implementation rule:

- remove the matching `_tombstones_by_record_scope` entry and `_tombstones`
  value when an active upsert records scope membership

This is derived-state repair, not durable history deletion. The latest graph
state for the selected scope should reflect the current Vault-derived records.

- [ ] **Step 5: Harden SQLite read failures**

Wrap `SQLiteGraphStore.current_manifest`, `get_entity`, `get_relationship`,
`stored_specs`, and `latest_revisions` read-time `sqlite3.Error` failures and
raise `GraphStoreUnavailable(str(exc))`. `health()` remains the preferred schema
gate, but read methods should not leak raw SQLite exceptions across the
`GraphStore` boundary.

- [ ] **Step 6: Verify graph store/status hardening**

Run:

```bash
uv run --python 3.12 pytest tests/test_graph_status_store.py tests/test_graph_store_contract.py tests/test_sqlite_graph_store.py -q
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add src/vault_graph/storage/local/graph_status_store.py src/vault_graph/storage/local/sqlite_graph_store.py tests/fakes/in_memory_graph_store.py src/vault_graph/app/catalog_service.py tests/test_graph_status_store.py tests/test_graph_store_contract.py tests/test_sqlite_graph_store.py
git commit -m "feat: harden graph store status behavior"
```

### Task 6: Implement GraphIndexer Planning

**Files:**

- Create: `src/vault_graph/indexing/graph_indexer.py`
- Test: `tests/test_graph_indexer.py`

- [ ] **Step 1: Write failing graph indexer planning tests**

Cover these behaviors with `PreviewGraphSourceStore` and `InMemoryGraphStore`:

- `plan` creates a `GraphReconcilePlan` without applying it
- desired document, heading, tag, and link records become entity upserts
- desired relationships become relationship upserts
- evidence refs are deduped and owner-scoped
- a second identical plan after applying the first plan has no entity or relationship upserts
- a changed chunk content hash makes the affected graph record stale
- missing current records create tombstones scoped to the selected actual scope
- all-vault planning returns one revision row per actual Vault scope
- same heading/path in two Vaults produces different entity IDs
- `include_cross_vault=False` does not create cross-Vault relationships
- unresolved links create both concept mentions and `unresolved_local_link` graph warnings
- frontmatter relationship fields flow from real `DocumentSnapshot.frontmatter`
  through entity extraction, relationship extraction, and persisted
  `RelationshipRecord` rows
- metadata index revision, parser version, chunker version, graph store schema
  version, and graph extraction spec digest changes each make affected records stale
- projection cache invalidation keys are produced for changed actual scopes and
  no projection cache files are created

Run:

```bash
uv run --python 3.12 pytest tests/test_graph_indexer.py -q
```

Expected: FAIL because `graph_indexer.py` does not exist.

- [ ] **Step 2: Implement plan/apply report dataclasses**

Create `src/vault_graph/indexing/graph_indexer.py` with:

```python
@dataclass(frozen=True)
class GraphIndexPlanReport:
    reconcile_plan: GraphReconcilePlan
    mode: str
    stale_count: int
    warnings: tuple[str, ...]


@dataclass(frozen=True)
class GraphIndexApplyResult:
    reconcile_plan: GraphReconcilePlan | None
    apply_result: GraphApplyResult | None
    mode: str
    stale_count: int
    warnings: tuple[str, ...]
    failed: bool
    error: str | None
```

- [ ] **Step 3: Implement `GraphIndexer.__init__`**

Signature:

```python
class GraphIndexer:
    def __init__(
        self,
        *,
        source_store: GraphSourceStore,
        graph_store: GraphStore,
        entity_extractor: EntityExtractor,
        relationship_extractor: RelationshipExtractor,
        graph_extraction_spec: GraphExtractionSpec,
        metadata_schema_version: str,
        now: Callable[[], str] | None = None,
        graph_run_id_factory: Callable[[], str] | None = None,
        graph_revision_factory: Callable[[], str] | None = None,
    ) -> None: ...
```

Default IDs:

```text
graph_run_id: graph-run-YYYYmmddHHMMSSffffff
graph_index_revision: graph-YYYYmmddHHMMSSffffff
```

Use injectable factories in tests for deterministic records.

- [ ] **Step 4: Implement `GraphIndexer.plan`**

Signature:

```python
def plan(
    self,
    *,
    requested_scope: QueryScope,
    actual_scopes: tuple[QueryScope, ...],
    full: bool = False,
) -> GraphIndexPlanReport: ...
```

Algorithm:

1. Validate every `actual_scope` has exactly one `vault_id`.
2. For each actual scope, call `source_store.list_chunks(actual_scope)`.
3. Resolve documents through `source_store.resolve_document(vault_id=chunk.vault_id, document_id=chunk.document_id)`.
4. Build `GraphExtractionContext` from current documents in that actual scope.
5. Run entity extractor per chunk.
6. Run relationship extractor per chunk using that chunk's entity occurrences.
7. Dedupe entity occurrences by `entity_occurrence_key`.
8. Convert desired entities to `EntityRecord` with `stable_entity_id`.
9. Convert desired relationships to `RelationshipRecord` with `stable_relationship_id`.
10. Create `GraphEvidenceRef` rows with `stable_evidence_ref_id`.
11. Read `graph_store.current_manifest(actual_scopes)`.
12. Compare desired state to manifest state.
13. Upsert missing or stale desired records.
14. Tombstone manifest records absent from desired state.
15. Create one `GraphRevision` per actual scope.
16. Return `GraphIndexPlanReport`.

Staleness rules:

- missing current manifest row -> upsert
- current spec digest differs -> upsert
- current status is tombstoned/deprecated when desired is active/stated -> upsert
- current graph store schema lineage differs from `graph_store.health().schema_version` -> upsert
- current `metadata_index_revision` differs from desired record scope lineage -> upsert
- current parser or chunker lineage differs at the revision level -> count stale and produce a revision row
- evidence ref IDs differ -> upsert
- evidence content hashes differ -> upsert
- relationship source, target, type, or status differs -> upsert
- absent current row in desired state -> tombstone
- `graph_index_revision` alone must not make a record stale

Revision lineage:

```python
def _revision_from_values(values: tuple[str | None, ...], *, fallback: str) -> str:
    revisions = tuple(sorted({value for value in values if value}))
    return ",".join(revisions) if revisions else fallback
```

Use:

- metadata lineage from selected chunks' `index_revision`, fallback `empty:<metadata_store.health().schema_version>` when app code passes metadata health, or `empty` only in isolated unit tests without a metadata health source
- parser lineage from selected documents' `parser_version`, fallback `unknown`
- chunker lineage from selected chunks' `chunker_version`, fallback `empty`

Implementation rule: `IndexService` must pass the metadata health schema
version into `GraphIndexer` so empty-scope graph revisions match
`ReadOnlyGraphReadiness._metadata_lineage`.

Warnings:

- `GraphIndexer.plan` owns app-level warnings, not `GraphStore`.
- If an extracted entity occurrence has
  `extraction_method="unresolved-local-link-concept-v1"`, add one warning with
  code `unresolved_local_link`, the Vault ID, path, chunk ID, and link text.
- Warnings are deduped and sorted by `(code, vault_id, path, chunk_id, message)`.

Projection cache invalidation keys:

- compute keys only for actual scopes with entity upserts, relationship upserts,
  or tombstones
- key format: `graph-projection:{graph_scope_key(actual_scope)}`
- write keys into `GraphReconcilePlan.projection_cache_invalidations`
- do not create, delete, or write files under `data/projection_cache/` in Phase 3B

- [ ] **Step 5: Implement `GraphIndexer.apply`**

Signature:

```python
def apply(
    self,
    *,
    requested_scope: QueryScope,
    actual_scopes: tuple[QueryScope, ...],
    full: bool = False,
) -> GraphIndexApplyResult: ...
```

Implementation:

- call `plan`
- pass `report.reconcile_plan` to `graph_store.apply_reconcile_plan`
- return failed result with `reconcile_plan=None`, `apply_result=None`, and
  `error=str(exc)` when planning fails with `GraphIndexingError`,
  `GraphStoreError`, or `GraphRecordInvalid`
- return failed result with `reconcile_plan=report.reconcile_plan`,
  `apply_result=None`, and `error=str(exc)` when applying fails with
  `GraphIndexingError`, `GraphStoreError`, or `GraphRecordInvalid`
- do not catch unrelated exceptions silently

- [ ] **Step 6: Verify graph indexer tests pass**

Run:

```bash
uv run --python 3.12 pytest tests/test_graph_indexer.py -q
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add src/vault_graph/indexing/graph_indexer.py tests/test_graph_indexer.py
git commit -m "feat: add graph indexer planning"
```

### Task 7: Wire Graph Indexing Into IndexService

**Files:**

- Modify: `src/vault_graph/app/index_service.py`
- Test: `tests/test_index_service_graph_reconcile.py`
- Test: `tests/test_multi_vault_graph_indexing.py`

- [ ] **Step 1: Write failing service tests**

Cover:

- `run_plan` returns graph planned counts and does not apply to graph store
- `run_apply` writes graph records after metadata
- vector failure still allows graph apply when metadata succeeded
- graph failure returns `IndexRunReport.exit_code == 1`
- metadata failure prevents graph indexing
- unsupported content-scope graph width returns graph failure with `unsupported_graph_scope_width`
- unsupported content-scope graph width does not call `GraphIndexer.plan`,
  `GraphStore.current_manifest`, `GraphStore.apply_reconcile_plan`, or create
  graph tombstones
- all-vault apply creates graph revisions per Vault actual scope
- all-vault graph scopes normalize each Vault to that entry's configured
  `content_scopes` order, so later single-vault status/indexing uses the same
  `graph_scope_key`
- graph failure is recorded in `LocalGraphStatusStore` and visible through status

Run:

```bash
uv run --python 3.12 pytest tests/test_index_service_graph_reconcile.py tests/test_multi_vault_graph_indexing.py -q
```

Expected: FAIL because `IndexService` has no graph plan/apply result.

- [ ] **Step 2: Extend `IndexRunReport`**

Modify `src/vault_graph/app/index_service.py`:

```python
@dataclass(frozen=True)
class IndexRunReport:
    metadata: MetadataRevisionPlan
    vector: VectorRevisionPlan | VectorApplyResult | None
    graph: GraphIndexPlanReport | GraphIndexApplyResult | None

    @property
    def exit_code(self) -> int:
        return 1 if getattr(self.vector, "failed", False) or getattr(self.graph, "failed", False) else 0
```

- [ ] **Step 3: Add graph dependencies to `IndexService.__init__`**

Add optional constructor parameters:

```python
graph_store: GraphStore | None = None
graph_extraction_spec: GraphExtractionSpec | None = None
graph_status_store: LocalGraphStatusStore | None = None
```

Keep graph indexing disabled only when `graph_store is None`. CLI should pass a
store in both dry-run and apply modes.

- [ ] **Step 4: Add graph source helpers**

Add private methods:

```python
def _graph_plan(
    self,
    *,
    source_store: GraphSourceStore,
    scope: QueryScope,
    full: bool,
) -> GraphIndexPlanReport | GraphIndexApplyResult | None: ...

def _graph_apply(
    self,
    *,
    source_store: GraphSourceStore,
    scope: QueryScope,
    full: bool,
) -> GraphIndexApplyResult | None: ...

def _graph_indexer(self, *, source_store: GraphSourceStore) -> GraphIndexer: ...
```

Use:

- `PreviewGraphSourceStore(chunks=preview.chunks_after_apply, documents=preview.documents_after_apply)` in `run_plan`
- `MetadataGraphSourceStore(self._metadata_store)` in `run_apply`
- `_graph_plan` runs health/scope validation and never records status
- `_graph_apply` runs health/scope validation, applies through `GraphIndexer`,
  and records graph success/failure to `LocalGraphStatusStore`

- [ ] **Step 5: Add supported graph scope validation**

Add:

```python
def _graph_actual_scopes(*, catalog: VaultCatalog, requested_scope: QueryScope) -> tuple[QueryScope, ...]:
    actual_scopes = actual_query_scopes(catalog=catalog, scope=requested_scope)
    normalized: list[QueryScope] = []
    for actual_scope in actual_scopes:
        entry = catalog.resolve(actual_scope.vault_ids[0])
        if set(actual_scope.content_scopes) != set(entry.content_scopes):
            raise UnsupportedGraphScopeWidthError(
                "unsupported_graph_scope_width: graph indexing supports only whole selected Vault scopes"
            )
        normalized.append(
            QueryScope(
                vault_ids=(entry.vault_id,),
                content_scopes=entry.content_scopes,
                include_cross_vault=requested_scope.include_cross_vault,
            )
        )
    return tuple(normalized)


def _validate_supported_graph_scopes(
    *,
    actual_scopes: tuple[QueryScope, ...],
) -> None:
    for actual_scope in actual_scopes:
        if len(actual_scope.vault_ids) != 1:
            raise UnsupportedGraphScopeWidthError(
                "unsupported_graph_scope_width: graph indexing requires per-Vault actual scopes"
            )
```

Call `_graph_actual_scopes` and `_validate_supported_graph_scopes` before
constructing `GraphIndexer`. Return a failed `GraphIndexApplyResult`-shaped
result for app reporting without calling `GraphIndexer`, `current_manifest`, or
`apply_reconcile_plan`.

- [ ] **Step 6: Add graph health/schema gate**

Before constructing `GraphIndexer`, call `graph_store.health()`.

Evaluate the gate in this order:

1. If this is dry-run and `health.message` contains `not initialized`, allow
   planning to continue against `GraphStore.current_manifest`, which returns an
   empty manifest without creating graph storage.
2. Else if `ok` is false or `schema_compatible` is false, return a failed graph
   result:

```python
GraphIndexApplyResult(
    reconcile_plan=None,
    apply_result=None,
    mode="full" if full else "incremental",
    stale_count=0,
    warnings=(health.message,),
    failed=True,
    error=health.message,
)
```

In apply mode, CLI opens a writable store, so a missing graph DB is initialized
under the configured state path before the health gate.

Do not call `GraphIndexer.plan`, `current_manifest`, or `apply_reconcile_plan`
after a failed health gate. The only exception is the missing-store dry-run case
above, where `current_manifest` is intentionally used as an empty read model.

- [ ] **Step 7: Record graph status**

Add private status helpers:

```python
def _record_graph_status(self, *, scope: QueryScope, result: GraphIndexApplyResult) -> None: ...
def _graph_status(self, *, scope: QueryScope) -> GraphRunStatus | None: ...
```

Use `graph_scope_status_key(scope)` and `graph_spec_key(self._graph_extraction_spec)`.

Record:

- success when `result.failed is False`, using the latest graph revision from
  `result.apply_result.graph_revision_rows`
- failure when `result.failed is True`, preserving previous success revision
- nothing during dry-run

Extend `StatusReport` with:

```python
graph_status_scope: str
graph_last_error: str | None
```

- [ ] **Step 8: Update `run_plan`**

Flow:

```python
preview = MetadataIndexer(...).preview(scope=scope, full=full)
vector_plan = self._vector_plan(chunk_store=_PreviewChunkStore(preview.chunks_after_apply), scope=scope, full=full)
graph_plan = self._graph_plan(
    source_store=PreviewGraphSourceStore(chunks=preview.chunks_after_apply, documents=preview.documents_after_apply),
    scope=scope,
    full=full,
)
return IndexRunReport(metadata=preview.plan, vector=vector_plan, graph=graph_plan)
```

Use `_graph_actual_scopes` inside `_graph_plan`, not the vector/search
`actual_query_scopes` result.

- [ ] **Step 9: Update `run_apply`**

Flow:

```python
metadata_plan = MetadataIndexer(...).apply(scope=scope, full=full)
vector_result = None
if vector dependencies configured:
    vector_result = self._vector_indexer(chunk_store=self._metadata_store).apply(...)
    self._record_vector_status(...)
graph_result = self._graph_apply(source_store=MetadataGraphSourceStore(self._metadata_store), scope=scope, full=full)
return IndexRunReport(metadata=metadata_plan, vector=vector_result, graph=graph_result)
```

Do not skip graph because vector failed. Do skip graph if metadata apply raises.

- [ ] **Step 10: Verify service tests pass**

Run:

```bash
uv run --python 3.12 pytest tests/test_index_service_graph_reconcile.py tests/test_multi_vault_graph_indexing.py -q
```

Expected: PASS.

- [ ] **Step 11: Commit**

```bash
git add src/vault_graph/app/index_service.py src/vault_graph/storage/local/graph_status_store.py tests/test_index_service_graph_reconcile.py tests/test_multi_vault_graph_indexing.py
git commit -m "feat: wire graph indexing into index service"
```

### Task 8: Wire CLI Graph Index Output

**Files:**

- Modify: `src/vault_graph/cli/main.py`
- Test: `tests/test_cli_graph_indexing.py`
- Existing test: `tests/test_cli_graph_status.py`

- [ ] **Step 1: Write failing CLI tests**

Cover:

- `vg index --dry-run` prints graph planned fields and does not create graph DB
- `vg index` prints graph apply fields and creates graph DB under state path
- `vg index` returns nonzero when graph apply fails, while metadata state remains
- `vg status --format json` reports `graph.freshness == "fresh"` after graph indexing
- `vg status` text and JSON report `graph_last_error` after a graph apply failure
- `vg index` with vector failure prints both `vector_failed: True` and graph success fields

Run:

```bash
uv run --python 3.12 pytest tests/test_cli_graph_indexing.py tests/test_cli_graph_status.py -q
```

Expected: FAIL because CLI does not render graph index output.

- [ ] **Step 2: Open writable graph store only for apply**

Modify `_service` in `src/vault_graph/cli/main.py`:

```python
graph_store = (
    SQLiteGraphStore.open_writable(config.graph_path)
    if initialize_store
    else SQLiteGraphStore.open_read_only(config.graph_path)
)
```

Pass `graph_store=graph_store` and
`graph_extraction_spec=current_graph_extraction_spec()` into `IndexService`.
Pass `graph_status_store=LocalGraphStatusStore(config.graph_status_path)`.

Dry-run and status must keep `initialize_store=False`, so they must not create
graph storage.

- [ ] **Step 3: Render graph fields in `index`**

After vector output, add:

```python
if report.graph is not None:
    graph = report.graph
    plan = graph.reconcile_plan
    typer.echo(f"graph_mode: {graph.mode}")
    typer.echo(f"graph_run_id: {plan.graph_run_id if plan is not None else None}")
    typer.echo(f"graph_revision: {_graph_revision_text(graph)}")
    typer.echo(f"graph_entities_upserted: {len(plan.entity_upserts) if plan is not None else 0}")
    typer.echo(f"graph_relationships_upserted: {len(plan.relationship_upserts) if plan is not None else 0}")
    typer.echo(f"graph_evidence_refs_upserted: {len(plan.evidence_ref_upserts) if plan is not None else 0}")
    typer.echo(f"graph_tombstones: {_graph_tombstone_count(plan)}")
    typer.echo(f"graph_stale: {graph.stale_count}")
    typer.echo(f"graph_extraction_spec_version: {current_graph_extraction_spec().spec_version}")
    typer.echo(f"graph_extraction_spec_digest: {current_graph_extraction_spec().spec_digest}")
    typer.echo(f"graph_failed: {getattr(graph, 'failed', False)}")
    typer.echo(f"graph_last_error: {getattr(graph, 'error', None)}")
    for warning in graph.warnings:
        typer.echo(f"graph_warning: {warning}")
```

Implement `_graph_revision_text` and `_graph_tombstone_count` as private CLI
helpers. Keep text keys exactly as specified in the Phase 3B design.

In `status`, render:

```python
typer.echo(f"graph_status_scope: {report.graph_status_scope}")
typer.echo(f"graph_last_error: {report.graph_last_error}")
```

In status JSON, add these fields inside the `graph` object:

```python
"status_scope": report.graph_status_scope,
"last_error": report.graph_last_error,
```

- [ ] **Step 4: Update domain error handling**

Add `GraphIndexingError` to `_exit_on_domain_error` catch tuple.

- [ ] **Step 5: Exit after rendering all enabled failures**

Do not exit immediately after vector failure. Render graph fields first, then:

```python
if report.exit_code:
    raise typer.Exit(report.exit_code)
```

- [ ] **Step 6: Verify CLI tests pass**

Run:

```bash
uv run --python 3.12 pytest tests/test_cli_graph_indexing.py tests/test_cli_graph_status.py -q
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add src/vault_graph/cli/main.py tests/test_cli_graph_indexing.py tests/test_cli_graph_status.py
git commit -m "feat: expose graph indexing in cli"
```

### Task 9: Add Read-Only, SQLite, And Regression Coverage

**Files:**

- Test: `tests/test_graph_indexing_read_only_boundary.py`
- Existing tests: `tests/test_sqlite_graph_store.py`, `tests/test_graph_readiness.py`, `tests/test_naming_conventions.py`, `tests/test_cli_search.py`

- [ ] **Step 1: Add read-only boundary tests**

Cover:

- `vg index --dry-run` does not create `state/graph`
- `vg index --dry-run` does not create metadata DB files
- `vg index --dry-run` does not create vector DB files
- `vg index --dry-run` does not create vector status files
- `vg index --dry-run` does not write embedding model cache files
- `vg index --dry-run` does not modify Vault files
- graph extraction does not open Vault files directly after metadata preview/apply
- graph apply writes only under configured Vault Graph state
- `vg status` remains read-only before and after graph indexing
- graph projection cache directory is not created by Phase 3B
- unsupported graph content-scope width does not call graph planning, manifest
  reads, apply, or tombstone creation

Run:

```bash
uv run --python 3.12 pytest tests/test_graph_indexing_read_only_boundary.py -q
```

Expected: FAIL before tests are implemented, then PASS after CLI/service wiring
is complete.

- [ ] **Step 2: Add SQLite-backed integration assertions**

Extend existing SQLite graph/readiness tests or add focused tests to prove:

- `SQLiteGraphStore.open_writable` receives `GraphReconcilePlan` from `GraphIndexer.apply`
- `ReadOnlyGraphReadiness` reports fresh after a graph index apply
- stale evidence becomes stale after metadata content changes
- stale `GraphExtractionSpec` is repaired by reindexing selected scopes
- changed `GraphExtractionSpec` digest uses a changed `spec_version`
- active upsert clears matching scoped tombstones in SQLite and in-memory graph stores

- [ ] **Step 3: Add search no-scope-creep regression**

Add or extend `tests/test_cli_search.py`:

- run `vg index` so metadata/vector/graph state exists
- run `vg search "query"`
- assert output remains Phase 2C keyword/vector evidence search
- assert no graph traversal fields, graph ranking, `related`, `decision-trace`,
  or `include_graph` behavior appears

This proves Phase 3B indexing does not silently widen default search.

- [ ] **Step 4: Verify focused graph suite**

Run:

```bash
uv run --python 3.12 pytest \
  tests/test_graph_occurrences.py \
  tests/test_graph_source_store.py \
  tests/test_entity_extractor.py \
  tests/test_relationship_extractor.py \
  tests/test_graph_status_store.py \
  tests/test_graph_contracts.py \
  tests/test_graph_indexer.py \
  tests/test_index_service_graph_reconcile.py \
  tests/test_multi_vault_graph_indexing.py \
  tests/test_cli_graph_indexing.py \
  tests/test_graph_indexing_read_only_boundary.py \
  tests/test_graph_store_contract.py \
  tests/test_graph_readiness.py \
  tests/test_sqlite_graph_store.py \
  tests/test_cli_graph_status.py \
  tests/test_cli_search.py \
  -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add tests/test_graph_indexing_read_only_boundary.py tests/test_sqlite_graph_store.py tests/test_graph_readiness.py tests/test_cli_search.py
git commit -m "test: cover graph indexing read only behavior"
```

### Task 10: Final Verification And Documentation Check

**Files:**

- Modify: `docs/PATCH_LOG.md` only if implementation review required plan/design corrections.
- Modify: `docs/DECISIONS.md` only if a new user-approved policy decision was made.

- [ ] **Step 1: Search for forbidden or stale terminology**

Run:

```bash
rg -n "phase2b|phase2c" src tests docs --glob '!docs/CONVENTIONS.md'
```

Expected: no output for source-file phase labels. The forbidden naming rule is
covered by `tests/test_naming_conventions.py`; do not write the forbidden term
into new docs or code outside `docs/CONVENTIONS.md`.

- [ ] **Step 2: Run full test suite**

Run:

```bash
uv run --python 3.12 pytest -q
```

Expected: all tests pass.

- [ ] **Step 3: Run lint**

Run:

```bash
uv run --python 3.12 ruff check src tests
```

Expected: `All checks passed!`

- [ ] **Step 4: Run type checks**

Run:

```bash
uv run --python 3.12 mypy src
uv run --python 3.12 mypy tests
```

Expected: both commands report success.

- [ ] **Step 5: Check whitespace**

Run:

```bash
git diff --check
```

Expected: no output.

- [ ] **Step 6: Final commit**

```bash
git status --short
git add \
  src/vault_graph/errors.py \
  src/vault_graph/graph/graph_contracts.py \
  src/vault_graph/extraction \
  src/vault_graph/indexing/revision_planner.py \
  src/vault_graph/indexing/metadata_indexer.py \
  src/vault_graph/indexing/graph_indexer.py \
  src/vault_graph/storage/local/graph_status_store.py \
  src/vault_graph/storage/local/sqlite_graph_store.py \
  src/vault_graph/app/catalog_service.py \
  src/vault_graph/app/index_service.py \
  src/vault_graph/cli/main.py \
  tests/fakes/in_memory_graph_store.py \
  tests/test_graph_occurrences.py \
  tests/test_graph_source_store.py \
  tests/test_entity_extractor.py \
  tests/test_relationship_extractor.py \
  tests/test_graph_status_store.py \
  tests/test_graph_indexer.py \
  tests/test_index_service_graph_reconcile.py \
  tests/test_multi_vault_graph_indexing.py \
  tests/test_cli_graph_indexing.py \
  tests/test_graph_indexing_read_only_boundary.py \
  tests/test_graph_contracts.py \
  tests/test_graph_store_contract.py \
  tests/test_sqlite_graph_store.py \
  tests/test_graph_readiness.py \
  tests/test_cli_graph_status.py \
  tests/test_cli_search.py
git commit -m "feat: add local graph indexing"
```

Do not push unless the user explicitly asks.

## Completion Checklist

- [ ] `GraphIndexer` writes only through `GraphStore.apply_reconcile_plan`.
- [ ] Graph dry-run does not create graph, projection cache, metadata, vector, or Vault files.
- [ ] Graph apply writes only under the configured Vault Graph state path.
- [ ] Plain `vg search "query"` behavior is unchanged.
- [ ] `vg index` reports graph counts and independent vector/graph failures.
- [ ] `vg status --format json` reports fresh graph readiness after indexing.
- [ ] Multi-vault graph identities and revisions remain per Vault/actual scope.
- [ ] Unsupported content-scope graph indexing returns `unsupported_graph_scope_width`.
- [ ] No Phase 3C graph traversal, ranking, projection, or graph search behavior is introduced.
- [ ] Full verification commands pass.
