# Phase 2A Retrieval Contract And VectorStore Boundary Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the Phase 2A contract-only slice: embedding contracts, vector store contracts, metadata evidence resolution, vector-hit evidence binding, and graph-ready retrieval result records without adding Chroma, vector indexing, search, graph traversal, MCP, HTTP, or CLI user search.

**Architecture:** Keep Phase 2A interface-first and local-testable. `TextEmbeddings` hides embedding mechanics, `VectorStore` returns scoped semantic candidates only, `MetadataStore` remains the evidence authority, and retrieval result records carry resolved evidence plus signal-level explanations without owning runtime search policy.

**Tech Stack:** Python 3.12, dataclasses, Protocol interfaces, SQLite from the standard library, pytest, ruff, mypy.

---

## Scope

In scope:

- `EmbeddingModelSpec`, `EmbeddingInput`, `EmbeddingVector`, and `TextEmbeddings`
- deterministic test TextEmbeddings implementation
- `VectorStore` protocol, vector records, vector queries, vector hits, tombstones, and manifests
- in-memory test vector store used only for backend-neutral contract tests
- `MetadataStore.resolve_chunk_evidence(...)`
- vector-hit-to-evidence binding guards and missing/stale evidence warnings
- graph-ready retrieval result dataclasses
- contract tests for multi-vault identity, content-scope filtering, evidence authority, model spec validation, and Phase 2A boundary protection
- documentation verification that Chroma and Qdrant remain behind the same `VectorStore` contract

Out of scope:

- Chroma collections
- Qdrant support
- vector indexing from Vault chunks
- embedding manifests on disk
- `vg search`
- vector fields in `vg status`
- keyword search
- hybrid ranking execution
- graph extraction or traversal
- MCP, HTTP, context packs, or LLM answers

## File Structure

Create these files:

- `src/vault_graph/embeddings/__init__.py`: embedding contract exports
- `src/vault_graph/embeddings/text_embeddings.py`: embedding model spec, input, vector, and TextEmbeddings protocol
- `src/vault_graph/retrieval/__init__.py`: retrieval contract exports
- `src/vault_graph/retrieval/retrieval_result.py`: retrieval signal, warning, and resolved result records
- `src/vault_graph/storage/interfaces/vector_store.py`: vector store protocol and record shapes
- `tests/__init__.py`: test package marker so `tests.fakes` imports are stable
- `tests/fakes/__init__.py`: test fake package marker
- `tests/fakes/deterministic_text_embeddings.py`: deterministic test-only `TextEmbeddings` implementation
- `tests/fakes/in_memory_vector_store.py`: backend-neutral test-only vector store
- `tests/test_text_embeddings_contract.py`: embedding contract tests
- `tests/test_vector_store_contract.py`: vector store contract tests
- `tests/test_metadata_evidence_resolution.py`: metadata evidence resolution tests
- `tests/test_retrieval_result_contract.py`: retrieval result contract tests
- `tests/test_cli_surface_boundary.py`: tests that Phase 2A does not expose Phase 2B or Phase 2C features

Modify these files:

- `src/vault_graph/errors.py`: add embedding, vector, and retrieval contract errors
- `src/vault_graph/storage/interfaces/metadata_store.py`: add `EvidenceReference` and `resolve_chunk_evidence(...)`
- `src/vault_graph/storage/local/sqlite_metadata_store.py`: implement SQLite evidence resolution
- `docs/PATCH_LOG.md`: record Phase 2A implementation corrections if review or execution changes the plan

Do not modify `src/vault_graph/cli/main.py` or `src/vault_graph/app/index_service.py` for Phase 2A.

## Task 1: TextEmbeddings Contract

**Files:**

- Modify: `src/vault_graph/errors.py`
- Create: `src/vault_graph/embeddings/__init__.py`
- Create: `src/vault_graph/embeddings/text_embeddings.py`
- Create: `tests/__init__.py`
- Create: `tests/fakes/__init__.py`
- Create: `tests/fakes/deterministic_text_embeddings.py`
- Test: `tests/test_text_embeddings_contract.py`

- [ ] **Step 1: Write the failing embedding contract tests**

Create `tests/test_text_embeddings_contract.py`:

```python
from pathlib import Path

import pytest

from tests.fakes.deterministic_text_embeddings import DeterministicTextEmbeddings
from vault_graph.embeddings.text_embeddings import EmbeddingInput, EmbeddingModelSpec, EmbeddingVector
from vault_graph.errors import TextEmbeddingsError


def test_empty_input_returns_empty_output() -> None:
    embeddings = DeterministicTextEmbeddings(
        EmbeddingModelSpec(
            model_name="deterministic",
            model_version="test",
            dimensions=4,
            spec_version="embedding-spec-v1",
        )
    )

    assert embeddings.embed(()) == ()


def test_text_embeddings_returns_stable_dimensioned_vectors() -> None:
    spec = EmbeddingModelSpec(
        model_name="deterministic",
        model_version="test",
        dimensions=4,
        spec_version="embedding-spec-v1",
    )
    embeddings = DeterministicTextEmbeddings(spec)
    inputs = (
        EmbeddingInput(input_id="first", text="alpha"),
        EmbeddingInput(input_id="second", text="beta"),
    )

    first = embeddings.embed(inputs)
    second = embeddings.embed(inputs)

    assert first == second
    assert tuple(vector.input_id for vector in first) == ("first", "second")
    assert all(vector.model_spec == spec for vector in first)
    assert all(len(vector.values) == 4 for vector in first)


def test_input_id_is_only_a_batch_correlation_key() -> None:
    spec = EmbeddingModelSpec(
        model_name="deterministic",
        model_version="test",
        dimensions=3,
        spec_version="embedding-spec-v1",
    )
    embeddings = DeterministicTextEmbeddings(spec)

    vector = embeddings.embed((EmbeddingInput(input_id="batch-item-1", text="wiki/page.md"),))[0]

    assert vector.input_id == "batch-item-1"
    assert not hasattr(vector, "vault_id")
    assert not hasattr(vector, "document_id")
    assert not hasattr(vector, "chunk_id")
    assert not hasattr(vector, "path")


def test_duplicate_input_id_fails_loudly_within_one_call() -> None:
    spec = EmbeddingModelSpec(
        model_name="deterministic",
        model_version="test",
        dimensions=4,
        spec_version="embedding-spec-v1",
    )
    embeddings = DeterministicTextEmbeddings(spec)
    inputs = (
        EmbeddingInput(input_id="duplicate", text="alpha"),
        EmbeddingInput(input_id="duplicate", text="beta"),
    )

    with pytest.raises(TextEmbeddingsError, match="input_id must be unique"):
        embeddings.embed(inputs)


def test_embedding_spec_rejects_invalid_dimensions() -> None:
    with pytest.raises(TextEmbeddingsError, match="dimensions must be positive"):
        EmbeddingModelSpec(
            model_name="deterministic",
            model_version="test",
            dimensions=0,
            spec_version="embedding-spec-v1",
        )


def test_embedding_vector_rejects_dimension_mismatch() -> None:
    spec = EmbeddingModelSpec(
        model_name="deterministic",
        model_version="test",
        dimensions=4,
        spec_version="embedding-spec-v1",
    )

    with pytest.raises(TextEmbeddingsError, match="embedding dimension mismatch"):
        EmbeddingVector(input_id="bad", values=(1.0, 2.0), model_spec=spec)


def test_text_embeddings_does_not_write_files(tmp_path: Path) -> None:
    embeddings = DeterministicTextEmbeddings(
        EmbeddingModelSpec(
            model_name="deterministic",
            model_version="test",
            dimensions=4,
            spec_version="embedding-spec-v1",
        )
    )
    before = tuple(tmp_path.iterdir())

    embeddings.embed((EmbeddingInput(input_id="one", text=str(tmp_path)),))

    assert tuple(tmp_path.iterdir()) == before
```

- [ ] **Step 2: Run the embedding test to verify it fails**

Run:

```bash
uv run --python 3.12 pytest tests/test_text_embeddings_contract.py -q
```

Expected: FAIL with `ModuleNotFoundError` for `vault_graph.embeddings` or `tests.fakes`.

- [ ] **Step 3: Add embedding domain errors**

Append these classes to `src/vault_graph/errors.py`:

```python
class TextEmbeddingsError(VaultGraphError):
    """Raised when text embeddings contracts are violated."""


class VectorStoreError(VaultGraphError):
    """Raised when vector store contracts are violated."""


class RetrievalContractError(VaultGraphError):
    """Raised when retrieval result contracts are violated."""
```

- [ ] **Step 4: Add the text embeddings contract**

Create `src/vault_graph/embeddings/text_embeddings.py`:

```python
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from vault_graph.errors import TextEmbeddingsError


@dataclass(frozen=True)
class EmbeddingModelSpec:
    model_name: str
    model_version: str
    dimensions: int
    spec_version: str

    def __post_init__(self) -> None:
        _require_non_empty(self.model_name, "model_name")
        _require_non_empty(self.model_version, "model_version")
        _require_non_empty(self.spec_version, "spec_version")
        if self.dimensions <= 0:
            raise TextEmbeddingsError("dimensions must be positive")


@dataclass(frozen=True)
class EmbeddingInput:
    input_id: str
    text: str

    def __post_init__(self) -> None:
        _require_non_empty(self.input_id, "input_id")


@dataclass(frozen=True)
class EmbeddingVector:
    input_id: str
    values: tuple[float, ...]
    model_spec: EmbeddingModelSpec

    def __post_init__(self) -> None:
        _require_non_empty(self.input_id, "input_id")
        if len(self.values) != self.model_spec.dimensions:
            raise TextEmbeddingsError(
                f"embedding dimension mismatch: expected {self.model_spec.dimensions}, got {len(self.values)}"
            )


class TextEmbeddings(Protocol):
    def model_spec(self) -> EmbeddingModelSpec: ...

    def embed(self, inputs: tuple[EmbeddingInput, ...]) -> tuple[EmbeddingVector, ...]: ...


def _require_non_empty(value: str, field_name: str) -> None:
    if not value:
        raise TextEmbeddingsError(f"{field_name} is required")
```

Create `src/vault_graph/embeddings/__init__.py`:

```python
from vault_graph.embeddings.text_embeddings import (
    EmbeddingInput,
    EmbeddingModelSpec,
    TextEmbeddings,
    EmbeddingVector,
)

__all__ = [
    "EmbeddingInput",
    "EmbeddingModelSpec",
    "TextEmbeddings",
    "EmbeddingVector",
]
```

- [ ] **Step 5: Add the deterministic test TextEmbeddings implementation**

Create `tests/__init__.py`:

```python
"""Vault Graph tests."""
```

Create `tests/fakes/__init__.py`:

```python
"""Test-only fakes for backend-neutral contract tests."""
```

Create `tests/fakes/deterministic_text_embeddings.py`:

```python
from __future__ import annotations

import hashlib

from vault_graph.embeddings.text_embeddings import EmbeddingInput, EmbeddingModelSpec, EmbeddingVector
from vault_graph.errors import TextEmbeddingsError


class DeterministicTextEmbeddings:
    def __init__(self, model_spec: EmbeddingModelSpec) -> None:
        self._model_spec = model_spec

    def model_spec(self) -> EmbeddingModelSpec:
        return self._model_spec

    def embed(self, inputs: tuple[EmbeddingInput, ...]) -> tuple[EmbeddingVector, ...]:
        _validate_unique_input_ids(inputs)
        return tuple(
            EmbeddingVector(
                input_id=item.input_id,
                values=_values_for_text(text=item.text, dimensions=self._model_spec.dimensions),
                model_spec=self._model_spec,
            )
            for item in inputs
        )


def _values_for_text(*, text: str, dimensions: int) -> tuple[float, ...]:
    digest = hashlib.sha256(text.encode("utf-8")).digest()
    return tuple(round((digest[index % len(digest)] / 255.0) * 2.0 - 1.0, 6) for index in range(dimensions))


def _validate_unique_input_ids(inputs: tuple[EmbeddingInput, ...]) -> None:
    seen: set[str] = set()
    for item in inputs:
        if item.input_id in seen:
            raise TextEmbeddingsError("input_id must be unique within one embedding call")
        seen.add(item.input_id)
```

- [ ] **Step 6: Run embedding checks**

Run:

```bash
uv run --python 3.12 pytest tests/test_text_embeddings_contract.py -q
uv run --python 3.12 ruff check src tests
uv run --python 3.12 mypy src
```

Expected: all commands pass.

- [ ] **Step 7: Commit embedding contract**

Run:

```bash
git add src/vault_graph/errors.py src/vault_graph/embeddings tests/__init__.py tests/fakes tests/test_text_embeddings_contract.py
git commit -m "feat: add text embeddings contract"
```

## Task 2: VectorStore Contract And In-Memory Contract Fake

**Files:**

- Create: `src/vault_graph/storage/interfaces/vector_store.py`
- Create: `tests/fakes/in_memory_vector_store.py`
- Test: `tests/test_vector_store_contract.py`

- [ ] **Step 1: Write the failing vector store contract tests**

Create `tests/test_vector_store_contract.py`:

```python
import pytest

from tests.fakes.deterministic_text_embeddings import DeterministicTextEmbeddings
from tests.fakes.in_memory_vector_store import InMemoryVectorStore
from vault_graph.embeddings.text_embeddings import EmbeddingInput, EmbeddingModelSpec
from vault_graph.errors import VectorStoreError
from vault_graph.ingestion.vault_catalog import QueryScope
from vault_graph.storage.interfaces.vector_store import VectorEmbeddingRecord, VectorQuery, VectorTombstone


SPEC = EmbeddingModelSpec(
    model_name="deterministic",
    model_version="test",
    dimensions=4,
    spec_version="embedding-spec-v1",
)

SECOND_SPEC = EmbeddingModelSpec(
    model_name="deterministic",
    model_version="test-v2",
    dimensions=4,
    spec_version="embedding-spec-v2",
)


def make_record(
    *,
    vault_id: str,
    path: str,
    text: str,
    content_scope: str,
    model_spec: EmbeddingModelSpec = SPEC,
) -> VectorEmbeddingRecord:
    embeddings = DeterministicTextEmbeddings(model_spec)
    embedding = embeddings.embed((EmbeddingInput(input_id=f"{vault_id}:{path}", text=text),))[0]
    chunk_id = f"{vault_id}:{path}:chunk"
    return VectorEmbeddingRecord(
        vector_id=make_vector_id(vault_id=vault_id, chunk_id=chunk_id, model_spec=model_spec),
        vault_id=vault_id,
        document_id=f"{vault_id}:{path}:document",
        chunk_id=chunk_id,
        content_scope=content_scope,
        embedding=embedding,
        metadata_index_revision="metadata-1",
        vector_index_revision="vector-1",
    )


def make_query(*, text: str, scope: QueryScope, limit: int = 10) -> VectorQuery:
    embeddings = DeterministicTextEmbeddings(SPEC)
    query_vector = embeddings.embed((EmbeddingInput(input_id="query", text=text),))[0]
    return VectorQuery(query_vector=query_vector, scope=scope, limit=limit, embedding_spec=SPEC)


def make_vector_id(*, vault_id: str, chunk_id: str, model_spec: EmbeddingModelSpec) -> str:
    spec_key = "|".join(
        (
            model_spec.model_name,
            model_spec.model_version,
            str(model_spec.dimensions),
            model_spec.spec_version,
        )
    )
    return f"{vault_id}:{chunk_id}:{spec_key}:vector"


def test_search_returns_scoped_semantic_candidates() -> None:
    store = InMemoryVectorStore()
    expected = make_record(vault_id="default", path="wiki/page.md", text="alpha", content_scope="wiki")
    other = make_record(vault_id="other", path="wiki/page.md", text="alpha", content_scope="wiki")
    store.apply_vector_revision(vector_index_revision="vector-1", records=(expected, other), tombstones=())

    hits = store.search(make_query(text="alpha", scope=QueryScope(vault_ids=("default",), content_scopes=("wiki",))))

    assert tuple(hit.vault_id for hit in hits) == ("default",)
    assert hits[0].document_id == expected.document_id
    assert hits[0].chunk_id == expected.chunk_id
    assert hits[0].content_scope == "wiki"
    assert hits[0].rank == 1
    assert hits[0].backend == "memory-vector"


def test_search_filters_content_scope_before_limit() -> None:
    store = InMemoryVectorStore()
    raw = make_record(vault_id="default", path="raw/source.md", text="exact query", content_scope="raw")
    wiki = make_record(vault_id="default", path="wiki/page.md", text="different text", content_scope="wiki")
    store.apply_vector_revision(vector_index_revision="vector-1", records=(raw, wiki), tombstones=())

    hits = store.search(
        make_query(
            text="exact query",
            scope=QueryScope(vault_ids=("default",), content_scopes=("wiki",)),
            limit=1,
        )
    )

    assert len(hits) == 1
    assert hits[0].content_scope == "wiki"
    assert hits[0].chunk_id == wiki.chunk_id


def test_content_scope_filter_uses_same_or_child_semantics() -> None:
    store = InMemoryVectorStore()
    broad = make_record(vault_id="default", path="wiki/index.md", text="broad", content_scope="wiki")
    child = make_record(vault_id="default", path="wiki/systems/vault.md", text="child", content_scope="wiki/systems")
    store.apply_vector_revision(vector_index_revision="vector-1", records=(broad, child), tombstones=())

    broad_hits = store.search(
        make_query(text="child", scope=QueryScope(vault_ids=("default",), content_scopes=("wiki",)))
    )
    narrow_hits = store.search(
        make_query(text="broad", scope=QueryScope(vault_ids=("default",), content_scopes=("wiki/systems",)))
    )

    assert {hit.content_scope for hit in broad_hits} == {"wiki", "wiki/systems"}
    assert tuple(hit.content_scope for hit in narrow_hits) == ("wiki/systems",)


def test_include_cross_vault_does_not_expand_vector_scope() -> None:
    store = InMemoryVectorStore()
    first = make_record(vault_id="first", path="wiki/page.md", text="same", content_scope="wiki")
    second = make_record(vault_id="second", path="wiki/page.md", text="same", content_scope="wiki")
    store.apply_vector_revision(vector_index_revision="vector-1", records=(first, second), tombstones=())

    hits = store.search(
        make_query(
            text="same",
            scope=QueryScope(vault_ids=("first",), content_scopes=("wiki",), include_cross_vault=True),
        )
    )

    assert tuple(hit.vault_id for hit in hits) == ("first",)


def test_same_relative_path_in_different_vaults_does_not_collide() -> None:
    store = InMemoryVectorStore()
    first = make_record(vault_id="first", path="wiki/same.md", text="same", content_scope="wiki")
    second = make_record(vault_id="second", path="wiki/same.md", text="same", content_scope="wiki")
    store.apply_vector_revision(vector_index_revision="vector-1", records=(first, second), tombstones=())

    hits = store.search(
        make_query(
            text="same",
            scope=QueryScope(vault_ids=("first", "second"), content_scopes=("wiki",)),
        )
    )

    assert sorted((hit.vault_id, hit.chunk_id) for hit in hits) == [
        ("first", first.chunk_id),
        ("second", second.chunk_id),
    ]


def test_vector_id_is_stable_for_vault_chunk_and_model_spec() -> None:
    first = make_record(vault_id="default", path="wiki/page.md", text="alpha", content_scope="wiki")
    second = make_record(
        vault_id="default",
        path="wiki/page.md",
        text="alpha",
        content_scope="wiki",
        model_spec=SECOND_SPEC,
    )

    assert first.chunk_id == second.chunk_id
    assert first.vector_id == make_vector_id(vault_id=first.vault_id, chunk_id=first.chunk_id, model_spec=SPEC)
    assert second.vector_id == make_vector_id(
        vault_id=second.vault_id,
        chunk_id=second.chunk_id,
        model_spec=SECOND_SPEC,
    )
    assert first.vector_id != second.vector_id


def test_tombstone_removes_only_named_vault_and_chunk() -> None:
    store = InMemoryVectorStore()
    first = make_record(vault_id="first", path="wiki/same.md", text="same", content_scope="wiki")
    second = make_record(vault_id="second", path="wiki/same.md", text="same", content_scope="wiki")
    store.apply_vector_revision(vector_index_revision="vector-1", records=(first, second), tombstones=())
    store.apply_vector_revision(
        vector_index_revision="vector-2",
        records=(),
        tombstones=(VectorTombstone(vault_id="first", chunk_id=first.chunk_id),),
    )

    hits = store.search(
        make_query(
            text="same",
            scope=QueryScope(vault_ids=("first", "second"), content_scopes=("wiki",)),
        )
    )

    assert tuple((hit.vault_id, hit.chunk_id) for hit in hits) == (("second", second.chunk_id),)


def test_store_rejects_records_from_multiple_model_specs() -> None:
    store = InMemoryVectorStore()
    first = make_record(vault_id="default", path="wiki/page.md", text="alpha", content_scope="wiki")
    second = make_record(
        vault_id="default",
        path="wiki/page.md",
        text="alpha",
        content_scope="wiki",
        model_spec=SECOND_SPEC,
    )

    with pytest.raises(VectorStoreError, match="embedding model spec mismatch"):
        store.apply_vector_revision(vector_index_revision="vector-1", records=(first, second), tombstones=())


def test_model_spec_mismatch_fails_loudly() -> None:
    store = InMemoryVectorStore()
    record = make_record(vault_id="default", path="wiki/page.md", text="alpha", content_scope="wiki")
    store.apply_vector_revision(vector_index_revision="vector-1", records=(record,), tombstones=())
    incompatible_spec = EmbeddingModelSpec(
        model_name="deterministic",
        model_version="other",
        dimensions=4,
        spec_version="embedding-spec-v1",
    )
    embeddings = DeterministicTextEmbeddings(incompatible_spec)
    query_vector = embeddings.embed((EmbeddingInput(input_id="query", text="alpha"),))[0]

    with pytest.raises(VectorStoreError, match="embedding model spec mismatch"):
        store.search(
            VectorQuery(
                query_vector=query_vector,
                scope=QueryScope(vault_ids=("default",), content_scopes=("wiki",)),
                limit=10,
                embedding_spec=incompatible_spec,
            )
        )


def test_vector_hits_do_not_expose_evidence_fields() -> None:
    store = InMemoryVectorStore()
    record = make_record(vault_id="default", path="wiki/page.md", text="alpha", content_scope="wiki")
    store.apply_vector_revision(vector_index_revision="vector-1", records=(record,), tombstones=())

    hit = store.search(make_query(text="alpha", scope=QueryScope(vault_ids=("default",), content_scopes=("wiki",))))[0]

    for field_name in ("path", "text", "title", "summary", "anchor", "evidence", "content_hash"):
        assert not hasattr(hit, field_name)


def test_manifest_and_health_are_inspectable() -> None:
    store = InMemoryVectorStore()
    record = make_record(vault_id="default", path="wiki/page.md", text="alpha", content_scope="wiki")
    store.apply_vector_revision(vector_index_revision="vector-1", records=(record,), tombstones=())

    manifest = store.export_manifest(QueryScope(vault_ids=("default",), content_scopes=("wiki",)))
    health = store.health()

    assert len(manifest) == 1
    assert manifest[0].vector_id == record.vector_id
    assert manifest[0].content_scope == "wiki"
    assert health.ok is True
    assert health.backend == "memory-vector"
    assert health.schema_compatible is True
```

- [ ] **Step 2: Run the vector test to verify it fails**

Run:

```bash
uv run --python 3.12 pytest tests/test_vector_store_contract.py -q
```

Expected: FAIL with `ModuleNotFoundError` for `vault_graph.storage.interfaces.vector_store` or `tests.fakes.in_memory_vector_store`.

- [ ] **Step 3: Add the vector store interface**

Create `src/vault_graph/storage/interfaces/vector_store.py`:

```python
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from vault_graph.embeddings.text_embeddings import EmbeddingModelSpec, EmbeddingVector
from vault_graph.errors import CatalogError, VectorStoreError
from vault_graph.ingestion.vault_catalog import QueryScope
from vault_graph.storage.interfaces.store_health import StoreHealth


@dataclass(frozen=True)
class VectorEmbeddingRecord:
    vector_id: str
    vault_id: str
    document_id: str
    chunk_id: str
    content_scope: str
    embedding: EmbeddingVector
    metadata_index_revision: str
    vector_index_revision: str

    def __post_init__(self) -> None:
        _require_non_empty(self.vector_id, "vector_id")
        _require_non_empty(self.vault_id, "vault_id")
        _require_non_empty(self.document_id, "document_id")
        _require_non_empty(self.chunk_id, "chunk_id")
        _require_non_empty(self.content_scope, "content_scope")
        _require_non_empty(self.metadata_index_revision, "metadata_index_revision")
        _require_non_empty(self.vector_index_revision, "vector_index_revision")
        _validate_single_content_scope(vault_id=self.vault_id, content_scope=self.content_scope)


@dataclass(frozen=True)
class VectorTombstone:
    vault_id: str
    chunk_id: str

    def __post_init__(self) -> None:
        _require_non_empty(self.vault_id, "vault_id")
        _require_non_empty(self.chunk_id, "chunk_id")


@dataclass(frozen=True)
class VectorQuery:
    query_vector: EmbeddingVector
    scope: QueryScope
    limit: int
    embedding_spec: EmbeddingModelSpec

    def __post_init__(self) -> None:
        if self.limit <= 0:
            raise VectorStoreError("limit must be positive")
        if self.query_vector.model_spec != self.embedding_spec:
            raise VectorStoreError("query vector model spec must match embedding_spec")


@dataclass(frozen=True)
class VectorHit:
    vector_id: str
    vault_id: str
    document_id: str
    chunk_id: str
    content_scope: str
    score: float
    rank: int
    embedding_spec: EmbeddingModelSpec
    metadata_index_revision: str
    vector_index_revision: str
    backend: str

    def __post_init__(self) -> None:
        _require_non_empty(self.vector_id, "vector_id")
        _require_non_empty(self.vault_id, "vault_id")
        _require_non_empty(self.document_id, "document_id")
        _require_non_empty(self.chunk_id, "chunk_id")
        _require_non_empty(self.content_scope, "content_scope")
        _require_non_empty(self.metadata_index_revision, "metadata_index_revision")
        _require_non_empty(self.vector_index_revision, "vector_index_revision")
        _require_non_empty(self.backend, "backend")
        if self.rank <= 0:
            raise VectorStoreError("rank must be positive")
        _validate_single_content_scope(vault_id=self.vault_id, content_scope=self.content_scope)


@dataclass(frozen=True)
class VectorManifestRecord:
    vector_id: str
    vault_id: str
    document_id: str
    chunk_id: str
    content_scope: str
    embedding_spec: EmbeddingModelSpec
    metadata_index_revision: str
    vector_index_revision: str
    backend: str


class VectorStore(Protocol):
    def apply_vector_revision(
        self,
        *,
        vector_index_revision: str,
        records: tuple[VectorEmbeddingRecord, ...],
        tombstones: tuple[VectorTombstone, ...],
    ) -> None: ...

    def search(self, query: VectorQuery) -> tuple[VectorHit, ...]: ...

    def health(self) -> StoreHealth: ...

    def export_manifest(self, scope: QueryScope) -> tuple[VectorManifestRecord, ...]: ...


def _require_non_empty(value: str, field_name: str) -> None:
    if not value:
        raise VectorStoreError(f"{field_name} is required")


def _validate_single_content_scope(*, vault_id: str, content_scope: str) -> None:
    try:
        QueryScope(vault_ids=(vault_id,), content_scopes=(content_scope,))
    except CatalogError as exc:
        raise VectorStoreError(str(exc)) from exc
```

- [ ] **Step 4: Add the in-memory vector store fake**

Create `tests/fakes/in_memory_vector_store.py`:

```python
from __future__ import annotations

from vault_graph.embeddings.text_embeddings import EmbeddingModelSpec, EmbeddingVector
from vault_graph.errors import VectorStoreError
from vault_graph.ingestion.vault_catalog import QueryScope
from vault_graph.storage.interfaces.store_health import StoreHealth
from vault_graph.storage.interfaces.vector_store import (
    VectorEmbeddingRecord,
    VectorHit,
    VectorManifestRecord,
    VectorQuery,
    VectorTombstone,
)


class InMemoryVectorStore:
    def __init__(self) -> None:
        self._records: dict[tuple[str, str], VectorEmbeddingRecord] = {}
        self._embedding_spec: EmbeddingModelSpec | None = None

    def apply_vector_revision(
        self,
        *,
        vector_index_revision: str,
        records: tuple[VectorEmbeddingRecord, ...],
        tombstones: tuple[VectorTombstone, ...],
    ) -> None:
        if not vector_index_revision:
            raise VectorStoreError("vector_index_revision is required")
        next_embedding_spec = self._validated_embedding_spec(records)
        for record in records:
            if record.vector_index_revision != vector_index_revision:
                raise VectorStoreError("record vector_index_revision must match revision being applied")
        for tombstone in tombstones:
            self._records.pop((tombstone.vault_id, tombstone.chunk_id), None)
        for record in records:
            self._records[(record.vault_id, record.chunk_id)] = record
        self._embedding_spec = next_embedding_spec

    def search(self, query: VectorQuery) -> tuple[VectorHit, ...]:
        if self._embedding_spec is not None and query.embedding_spec != self._embedding_spec:
            raise VectorStoreError("embedding model spec mismatch")
        scoped_records = tuple(record for record in self._records.values() if _record_in_scope(record, query.scope))
        scored = sorted(
            ((_dot_product(query.query_vector, record.embedding), record) for record in scoped_records),
            key=lambda item: (-item[0], item[1].vault_id, item[1].chunk_id, item[1].vector_id),
        )
        return tuple(
            VectorHit(
                vector_id=record.vector_id,
                vault_id=record.vault_id,
                document_id=record.document_id,
                chunk_id=record.chunk_id,
                content_scope=record.content_scope,
                score=score,
                rank=rank,
                embedding_spec=record.embedding.model_spec,
                metadata_index_revision=record.metadata_index_revision,
                vector_index_revision=record.vector_index_revision,
                backend="memory-vector",
            )
            for rank, (score, record) in enumerate(scored[: query.limit], start=1)
        )

    def health(self) -> StoreHealth:
        return StoreHealth(
            ok=True,
            backend="memory-vector",
            schema_version="memory-vector-v1",
            schema_compatible=True,
            message="ok",
        )

    def export_manifest(self, scope: QueryScope) -> tuple[VectorManifestRecord, ...]:
        records = sorted(
            (record for record in self._records.values() if _record_in_scope(record, scope)),
            key=lambda record: (record.vault_id, record.chunk_id, record.vector_id),
        )
        return tuple(
            VectorManifestRecord(
                vector_id=record.vector_id,
                vault_id=record.vault_id,
                document_id=record.document_id,
                chunk_id=record.chunk_id,
                content_scope=record.content_scope,
                embedding_spec=record.embedding.model_spec,
                metadata_index_revision=record.metadata_index_revision,
                vector_index_revision=record.vector_index_revision,
                backend="memory-vector",
            )
            for record in records
        )

    def _validated_embedding_spec(self, records: tuple[VectorEmbeddingRecord, ...]) -> EmbeddingModelSpec | None:
        next_embedding_spec = self._embedding_spec
        for record in records:
            if next_embedding_spec is None:
                next_embedding_spec = record.embedding.model_spec
            elif next_embedding_spec != record.embedding.model_spec:
                raise VectorStoreError("embedding model spec mismatch")
        return next_embedding_spec


def _record_in_scope(record: VectorEmbeddingRecord, scope: QueryScope) -> bool:
    return record.vault_id in scope.vault_ids and _content_scope_in_scope(
        record_scope=record.content_scope,
        query_scopes=scope.content_scopes,
    )


def _content_scope_in_scope(*, record_scope: str, query_scopes: tuple[str, ...]) -> bool:
    return any(
        record_scope == query_scope or record_scope.startswith(f"{query_scope}/") for query_scope in query_scopes
    )


def _dot_product(left: EmbeddingVector, right: EmbeddingVector) -> float:
    if left.model_spec.dimensions != right.model_spec.dimensions:
        raise VectorStoreError("embedding dimension mismatch")
    return sum(left_value * right_value for left_value, right_value in zip(left.values, right.values, strict=True))
```

- [ ] **Step 5: Run vector store checks**

Run:

```bash
uv run --python 3.12 pytest tests/test_vector_store_contract.py -q
uv run --python 3.12 ruff check src tests
uv run --python 3.12 mypy src
```

Expected: all commands pass.

- [ ] **Step 6: Commit vector contract**

Run:

```bash
git add src/vault_graph/storage/interfaces/vector_store.py tests/fakes/in_memory_vector_store.py tests/test_vector_store_contract.py
git commit -m "feat: add vector store contract"
```

## Task 3: MetadataStore Evidence Resolution

**Files:**

- Modify: `src/vault_graph/storage/interfaces/metadata_store.py`
- Modify: `src/vault_graph/storage/local/sqlite_metadata_store.py`
- Test: `tests/test_metadata_evidence_resolution.py`

- [ ] **Step 1: Write the failing evidence resolution tests**

Create `tests/test_metadata_evidence_resolution.py`:

```python
from pathlib import Path

from vault_graph.ingestion.document_normalizer import ChunkSnapshot, DocumentSnapshot
from vault_graph.storage.local.sqlite_metadata_store import SQLiteMetadataStore


def make_document(vault_id: str, path: str, content_hash: str) -> DocumentSnapshot:
    return DocumentSnapshot(
        vault_id=vault_id,
        document_id=f"{vault_id}:{path}:document",
        path=path,
        kind=path.split("/", 1)[0],
        frontmatter={},
        frontmatter_hash="frontmatter",
        content_hash=content_hash,
        raw_sha256=f"raw:{content_hash}",
        parser_version="parser",
        last_seen_at="2026-06-08T00:00:00+00:00",
        last_indexed_at=None,
        vault_revision="vault-rev-1",
        index_revision=None,
    )


def make_chunk(document: DocumentSnapshot, text: str = "Body") -> ChunkSnapshot:
    return ChunkSnapshot(
        vault_id=document.vault_id,
        chunk_id=f"{document.vault_id}:{document.path}:chunk",
        document_id=document.document_id,
        path=document.path,
        section="Section",
        anchor="section",
        text=text,
        token_count=len(text.split()),
        content_hash=f"chunk:{document.content_hash}",
        chunker_version="chunker",
        index_revision=None,
    )


def test_resolve_chunk_evidence_joins_document_and_chunk(tmp_path: Path) -> None:
    store = SQLiteMetadataStore(tmp_path / "metadata.sqlite3", initialize=True)
    document = make_document("default", "wiki/page.md", "document-hash")
    chunk = make_chunk(document)
    store.apply_metadata_revision(index_revision="metadata-1", documents=[document], chunks=[chunk], tombstones=[])

    evidence = store.resolve_chunk_evidence(
        vault_id="default",
        document_id=document.document_id,
        chunk_id=chunk.chunk_id,
    )

    assert evidence is not None
    assert evidence.vault_id == "default"
    assert evidence.document_id == document.document_id
    assert evidence.chunk_id == chunk.chunk_id
    assert evidence.path == "wiki/page.md"
    assert evidence.section == "Section"
    assert evidence.anchor == "section"
    assert evidence.content_hash == chunk.content_hash
    assert evidence.raw_sha256 == document.raw_sha256
    assert evidence.metadata_index_revision == "metadata-1"
    assert evidence.vault_revision == "vault-rev-1"


def test_resolve_chunk_evidence_rejects_mismatched_ids(tmp_path: Path) -> None:
    store = SQLiteMetadataStore(tmp_path / "metadata.sqlite3", initialize=True)
    first = make_document("first", "wiki/same.md", "first-hash")
    second = make_document("second", "wiki/same.md", "second-hash")
    first_chunk = make_chunk(first)
    second_chunk = make_chunk(second)
    store.apply_metadata_revision(
        index_revision="metadata-1",
        documents=[first, second],
        chunks=[first_chunk, second_chunk],
        tombstones=[],
    )

    assert (
        store.resolve_chunk_evidence(
            vault_id="first",
            document_id=second.document_id,
            chunk_id=first_chunk.chunk_id,
        )
        is None
    )
    assert (
        store.resolve_chunk_evidence(
            vault_id="first",
            document_id=first.document_id,
            chunk_id=second_chunk.chunk_id,
        )
        is None
    )


def test_resolve_chunk_evidence_returns_none_after_tombstone(tmp_path: Path) -> None:
    store = SQLiteMetadataStore(tmp_path / "metadata.sqlite3", initialize=True)
    document = make_document("default", "wiki/page.md", "document-hash")
    chunk = make_chunk(document)
    store.apply_metadata_revision(index_revision="metadata-1", documents=[document], chunks=[chunk], tombstones=[])
    store.apply_metadata_revision(
        index_revision="metadata-2",
        documents=[],
        chunks=[],
        tombstones=[("default", "wiki/page.md")],
    )

    assert (
        store.resolve_chunk_evidence(
            vault_id="default",
            document_id=document.document_id,
            chunk_id=chunk.chunk_id,
        )
        is None
    )
```

- [ ] **Step 2: Run the evidence test to verify it fails**

Run:

```bash
uv run --python 3.12 pytest tests/test_metadata_evidence_resolution.py -q
```

Expected: FAIL with `AttributeError` because `SQLiteMetadataStore.resolve_chunk_evidence` does not exist.

- [ ] **Step 3: Add evidence reference to the metadata interface**

Update `src/vault_graph/storage/interfaces/metadata_store.py` so it includes `EvidenceReference` and the new protocol method:

```python
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from vault_graph.ingestion.document_normalizer import ChunkSnapshot, DocumentSnapshot
from vault_graph.storage.interfaces.store_health import StoreHealth


@dataclass(frozen=True)
class EvidenceReference:
    vault_id: str
    document_id: str
    chunk_id: str
    path: str
    section: str | None
    anchor: str | None
    content_hash: str
    raw_sha256: str
    metadata_index_revision: str | None
    vault_revision: str | None


@dataclass(frozen=True)
class DocumentState:
    vault_id: str
    path: str
    document_id: str | None
    frontmatter_hash: str | None
    content_hash: str | None
    raw_sha256: str | None
    parser_version: str | None
    chunker_version: str | None
    is_tombstoned: bool


class MetadataStore(Protocol):
    def apply_metadata_revision(
        self,
        *,
        index_revision: str,
        documents: list[DocumentSnapshot],
        chunks: list[ChunkSnapshot],
        tombstones: list[tuple[str, str]],
    ) -> None: ...

    def document_state(self, vault_id: str, path: str) -> DocumentState: ...

    def list_document_states(self, vault_ids: tuple[str, ...]) -> tuple[DocumentState, ...]: ...

    def resolve_document(self, document_id: str) -> DocumentSnapshot | None: ...

    def resolve_chunk(self, *, vault_id: str, chunk_id: str) -> ChunkSnapshot | None: ...

    def resolve_chunk_evidence(
        self,
        *,
        vault_id: str,
        document_id: str,
        chunk_id: str,
    ) -> EvidenceReference | None: ...

    def health(self) -> StoreHealth: ...
```

- [ ] **Step 4: Implement SQLite evidence resolution**

Modify the import in `src/vault_graph/storage/local/sqlite_metadata_store.py`:

```python
from vault_graph.storage.interfaces.metadata_store import DocumentState, EvidenceReference
```

Add this method to `SQLiteMetadataStore` after `resolve_chunk(...)`:

```python
    def resolve_chunk_evidence(
        self,
        *,
        vault_id: str,
        document_id: str,
        chunk_id: str,
    ) -> EvidenceReference | None:
        if not self._database_path.exists():
            return None
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT d.vault_id, d.document_id, c.chunk_id, d.path, c.section, c.anchor,
                       c.content_hash, d.raw_sha256, c.index_revision, d.vault_revision
                FROM documents d
                INNER JOIN chunks c ON c.vault_id = d.vault_id AND c.document_id = d.document_id
                WHERE d.vault_id = ?
                  AND d.document_id = ?
                  AND c.chunk_id = ?
                  AND d.is_tombstoned = 0
                """,
                (vault_id, document_id, chunk_id),
            ).fetchone()
        if row is None:
            return None
        return _evidence_reference_from_row(row)
```

Add this helper near the existing row mapping helpers:

```python
def _evidence_reference_from_row(row: sqlite3.Row) -> EvidenceReference:
    return EvidenceReference(
        vault_id=str(row["vault_id"]),
        document_id=str(row["document_id"]),
        chunk_id=str(row["chunk_id"]),
        path=str(row["path"]),
        section=str(row["section"]) if row["section"] is not None else None,
        anchor=str(row["anchor"]) if row["anchor"] is not None else None,
        content_hash=str(row["content_hash"]),
        raw_sha256=str(row["raw_sha256"]),
        metadata_index_revision=str(row["index_revision"]) if row["index_revision"] is not None else None,
        vault_revision=str(row["vault_revision"]) if row["vault_revision"] is not None else None,
    )
```

- [ ] **Step 5: Run metadata evidence checks**

Run:

```bash
uv run --python 3.12 pytest tests/test_metadata_evidence_resolution.py tests/test_sqlite_metadata_store.py -q
uv run --python 3.12 ruff check src tests
uv run --python 3.12 mypy src
```

Expected: all commands pass.

- [ ] **Step 6: Commit metadata evidence resolution**

Run:

```bash
git add src/vault_graph/storage/interfaces/metadata_store.py src/vault_graph/storage/local/sqlite_metadata_store.py tests/test_metadata_evidence_resolution.py
git commit -m "feat: resolve chunk evidence through metadata store"
```

## Task 4: Retrieval Result Contract

**Files:**

- Create: `src/vault_graph/retrieval/__init__.py`
- Create: `src/vault_graph/retrieval/retrieval_result.py`
- Test: `tests/test_retrieval_result_contract.py`

- [ ] **Step 1: Write the failing retrieval result tests**

Create `tests/test_retrieval_result_contract.py`:

```python
import pytest

from vault_graph.embeddings.text_embeddings import EmbeddingModelSpec
from vault_graph.errors import RetrievalContractError
from vault_graph.retrieval.retrieval_result import (
    RetrievalResult,
    RetrievalSignal,
    RetrievalWarning,
    StoreRevision,
    require_vector_hit_evidence_match,
    warning_for_missing_vector_evidence,
    warning_for_stale_vector,
)
from vault_graph.storage.interfaces.metadata_store import EvidenceReference
from vault_graph.storage.interfaces.vector_store import VectorHit


def make_store_revisions() -> tuple[StoreRevision, ...]:
    return (
        StoreRevision(kind="metadata", revision="metadata-1"),
        StoreRevision(kind="vector", revision="vector-1"),
    )


def make_evidence(vault_id: str = "default") -> EvidenceReference:
    return EvidenceReference(
        vault_id=vault_id,
        document_id=f"{vault_id}:document",
        chunk_id=f"{vault_id}:chunk",
        path="wiki/page.md",
        section="Section",
        anchor="section",
        content_hash="chunk-hash",
        raw_sha256="raw-hash",
        metadata_index_revision="metadata-1",
        vault_revision="vault-rev-1",
    )


def make_vector_hit(vault_id: str = "default") -> VectorHit:
    return VectorHit(
        vector_id=f"{vault_id}:vector",
        vault_id=vault_id,
        document_id=f"{vault_id}:document",
        chunk_id=f"{vault_id}:chunk",
        content_scope="wiki",
        score=0.75,
        rank=1,
        embedding_spec=EmbeddingModelSpec(
            model_name="deterministic",
            model_version="test",
            dimensions=4,
            spec_version="embedding-spec-v1",
        ),
        metadata_index_revision="metadata-1",
        vector_index_revision="vector-1",
        backend="memory-vector",
    )


def test_retrieval_result_requires_evidence() -> None:
    signal = RetrievalSignal(
        kind="vector",
        source_id="vector-1",
        rank=1,
        score=0.5,
        backend="memory-vector",
        index_revision="vector-1",
        explanation="semantic candidate",
    )

    with pytest.raises(RetrievalContractError, match="evidence is required"):
        RetrievalResult(
            result_id="default:wiki/page.md:section",
            vault_id="default",
            kind="document",
            title="Page",
            summary="Body",
            rank=1,
            evidence=(),
            signals=(signal,),
            relationship_status="not_applicable",
            warnings=(),
            store_revisions=make_store_revisions(),
        )


def test_vector_signal_keeps_backend_score_off_result() -> None:
    signal = RetrievalSignal(
        kind="vector",
        source_id="vector-1",
        rank=1,
        score=0.75,
        backend="memory-vector",
        index_revision="vector-1",
        explanation="semantic candidate",
    )
    result = RetrievalResult(
        result_id="default:wiki/page.md:section",
        vault_id="default",
        kind="document",
        title="Page",
        summary="Body",
        rank=1,
        evidence=(make_evidence(),),
        signals=(signal,),
        relationship_status="not_applicable",
        warnings=(),
        store_revisions=make_store_revisions(),
    )

    assert result.signals[0].score == 0.75
    assert result.signals[0].backend == "memory-vector"
    assert not hasattr(result, "score")
    assert not hasattr(result, "backend")
    assert not hasattr(result, "index_revision")


def test_graph_signal_kind_is_accepted_without_graph_runtime() -> None:
    signal = RetrievalSignal(
        kind="graph",
        source_id="edge-1",
        rank=1,
        score=1.0,
        backend="graph-store",
        index_revision="graph-1",
        explanation="relationship candidate",
    )
    result = RetrievalResult(
        result_id="default:wiki/page.md:section",
        vault_id="default",
        kind="document",
        title="Page",
        summary="Body",
        rank=1,
        evidence=(make_evidence(),),
        signals=(signal,),
        relationship_status="inferred",
        warnings=(),
        store_revisions=(
            StoreRevision(kind="metadata", revision="metadata-1"),
            StoreRevision(kind="graph", revision="graph-1"),
        ),
    )

    assert result.signals[0].kind == "graph"
    assert result.relationship_status == "inferred"


def test_retrieval_result_allows_cross_vault_evidence_for_relationships() -> None:
    signal = RetrievalSignal(
        kind="graph",
        source_id="edge-1",
        rank=1,
        score=1.0,
        backend="graph-store",
        index_revision="graph-1",
        explanation="cross-vault relationship candidate",
    )
    result = RetrievalResult(
        result_id="source:target:relationship",
        vault_id="source",
        kind="relationship",
        title="Related decision",
        summary="Evidence lives in a separate Vault",
        rank=1,
        evidence=(make_evidence(vault_id="evidence"),),
        signals=(signal,),
        relationship_status="inferred",
        warnings=(),
        store_revisions=(
            StoreRevision(kind="metadata", revision="metadata-1"),
            StoreRevision(kind="graph", revision="graph-1"),
        ),
    )

    assert result.evidence[0].vault_id == "evidence"


def test_vector_hit_ids_must_match_resolved_evidence_before_result() -> None:
    hit = make_vector_hit()
    evidence = make_evidence()

    require_vector_hit_evidence_match(hit=hit, evidence=evidence)


def test_vector_hit_evidence_mismatch_rejects_normal_result() -> None:
    hit = make_vector_hit(vault_id="default")
    evidence = make_evidence(vault_id="other")

    with pytest.raises(RetrievalContractError, match="vector hit ids must match evidence"):
        require_vector_hit_evidence_match(hit=hit, evidence=evidence)


def test_missing_vector_evidence_becomes_visible_warning() -> None:
    warning = warning_for_missing_vector_evidence(make_vector_hit())

    assert warning.code == "missing_evidence"
    assert warning.severity == "warning"


def test_vector_revision_mismatch_becomes_stale_warning() -> None:
    hit = make_vector_hit()
    evidence = make_evidence()
    stale_evidence = EvidenceReference(
        vault_id=evidence.vault_id,
        document_id=evidence.document_id,
        chunk_id=evidence.chunk_id,
        path=evidence.path,
        section=evidence.section,
        anchor=evidence.anchor,
        content_hash=evidence.content_hash,
        raw_sha256=evidence.raw_sha256,
        metadata_index_revision="metadata-2",
        vault_revision=evidence.vault_revision,
    )

    warning = warning_for_stale_vector(hit=hit, evidence=stale_evidence)

    assert warning is not None
    assert warning.code == "stale_vector"
    assert warning.severity == "warning"


def test_warnings_remain_visible_on_result() -> None:
    warning = RetrievalWarning(
        code="graph_unavailable",
        message="GraphStore is not configured in Phase 2A",
        severity="warning",
    )
    result = RetrievalResult(
        result_id="default:wiki/page.md:section",
        vault_id="default",
        kind="document",
        title="Page",
        summary="Body",
        rank=1,
        evidence=(make_evidence(),),
        signals=(),
        relationship_status="not_applicable",
        warnings=(warning,),
        store_revisions=(StoreRevision(kind="metadata", revision="metadata-1"),),
    )

    assert result.warnings == (warning,)
```

- [ ] **Step 2: Run the retrieval test to verify it fails**

Run:

```bash
uv run --python 3.12 pytest tests/test_retrieval_result_contract.py -q
```

Expected: FAIL with `ModuleNotFoundError` for `vault_graph.retrieval`.

- [ ] **Step 3: Add retrieval result records**

Create `src/vault_graph/retrieval/retrieval_result.py`:

```python
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from vault_graph.errors import RetrievalContractError
from vault_graph.storage.interfaces.metadata_store import EvidenceReference
from vault_graph.storage.interfaces.vector_store import VectorHit

RetrievalSignalKind = Literal["keyword", "vector", "graph"]
RetrievalSeverity = Literal["info", "warning", "error"]
RelationshipStatus = Literal["not_applicable", "stated", "inferred", "contested", "deprecated"]


@dataclass(frozen=True)
class StoreRevision:
    kind: str
    revision: str

    def __post_init__(self) -> None:
        _require_non_empty(self.kind, "kind")
        _require_non_empty(self.revision, "revision")


@dataclass(frozen=True)
class RetrievalSignal:
    kind: RetrievalSignalKind
    source_id: str
    rank: int
    score: float
    backend: str
    index_revision: str
    explanation: str

    def __post_init__(self) -> None:
        _require_non_empty(self.source_id, "source_id")
        _require_non_empty(self.backend, "backend")
        _require_non_empty(self.index_revision, "index_revision")
        _require_non_empty(self.explanation, "explanation")
        if self.rank <= 0:
            raise RetrievalContractError("signal rank must be positive")


@dataclass(frozen=True)
class RetrievalWarning:
    code: str
    message: str
    severity: RetrievalSeverity

    def __post_init__(self) -> None:
        _require_non_empty(self.code, "code")
        _require_non_empty(self.message, "message")


@dataclass(frozen=True)
class RetrievalResult:
    result_id: str
    vault_id: str
    kind: str
    title: str
    summary: str
    rank: int
    evidence: tuple[EvidenceReference, ...]
    signals: tuple[RetrievalSignal, ...]
    relationship_status: RelationshipStatus
    warnings: tuple[RetrievalWarning, ...]
    store_revisions: tuple[StoreRevision, ...]

    def __post_init__(self) -> None:
        _require_non_empty(self.result_id, "result_id")
        _require_non_empty(self.vault_id, "vault_id")
        _require_non_empty(self.kind, "kind")
        _require_non_empty(self.title, "title")
        if self.rank <= 0:
            raise RetrievalContractError("result rank must be positive")
        if not self.evidence:
            raise RetrievalContractError("evidence is required for retrieval results")
        if not isinstance(self.store_revisions, tuple):
            raise RetrievalContractError("store_revisions must be an immutable tuple")
        if any(not isinstance(store_revision, StoreRevision) for store_revision in self.store_revisions):
            raise RetrievalContractError("store_revisions must contain StoreRevision records")


def require_vector_hit_evidence_match(*, hit: VectorHit, evidence: EvidenceReference) -> None:
    if (
        hit.vault_id != evidence.vault_id
        or hit.document_id != evidence.document_id
        or hit.chunk_id != evidence.chunk_id
    ):
        raise RetrievalContractError("vector hit ids must match evidence before rendering")


def warning_for_missing_vector_evidence(hit: VectorHit) -> RetrievalWarning:
    return RetrievalWarning(
        code="missing_evidence",
        message=f"Metadata evidence could not be resolved for vector hit: {hit.vector_id}",
        severity="warning",
    )


def warning_for_stale_vector(*, hit: VectorHit, evidence: EvidenceReference) -> RetrievalWarning | None:
    if hit.metadata_index_revision == evidence.metadata_index_revision:
        return None
    return RetrievalWarning(
        code="stale_vector",
        message=f"Vector hit metadata revision is stale for evidence: {hit.vector_id}",
        severity="warning",
    )


def _require_non_empty(value: str, field_name: str) -> None:
    if not value:
        raise RetrievalContractError(f"{field_name} is required")
```

Create `src/vault_graph/retrieval/__init__.py`:

```python
from vault_graph.retrieval.retrieval_result import (
    RelationshipStatus,
    RetrievalResult,
    RetrievalSeverity,
    RetrievalSignal,
    RetrievalSignalKind,
    RetrievalWarning,
    StoreRevision,
    require_vector_hit_evidence_match,
    warning_for_missing_vector_evidence,
    warning_for_stale_vector,
)

__all__ = [
    "RelationshipStatus",
    "RetrievalResult",
    "RetrievalSeverity",
    "RetrievalSignal",
    "RetrievalSignalKind",
    "RetrievalWarning",
    "StoreRevision",
    "require_vector_hit_evidence_match",
    "warning_for_missing_vector_evidence",
    "warning_for_stale_vector",
]
```

- [ ] **Step 4: Run retrieval result checks**

Run:

```bash
uv run --python 3.12 pytest tests/test_retrieval_result_contract.py -q
uv run --python 3.12 ruff check src tests
uv run --python 3.12 mypy src
```

Expected: all commands pass.

- [ ] **Step 5: Commit retrieval result contract**

Run:

```bash
git add src/vault_graph/retrieval tests/test_retrieval_result_contract.py
git commit -m "feat: add retrieval result contract"
```

## Task 5: Phase 2A Boundary Tests

**Files:**

- Test: `tests/test_cli_surface_boundary.py`

- [ ] **Step 1: Write boundary tests that protect Phase 2A scope**

Create `tests/test_cli_surface_boundary.py`:

```python
from pathlib import Path

from typer.testing import CliRunner

from vault_graph.cli.main import app

runner = CliRunner()


def test_cli_surface_does_not_expose_search_before_search_slice() -> None:
    result = runner.invoke(app, ["search", "query"])

    assert result.exit_code != 0
    assert "No such command" in result.output


def test_cli_status_reports_metadata_fields(tmp_path: Path) -> None:
    vault_root = tmp_path / "vault"
    vault_root.mkdir()
    state_path = tmp_path / "state"
    runner.invoke(app, ["init", "--vault", str(vault_root), "--state", str(state_path)])

    result = runner.invoke(app, ["status", "--state", str(state_path)])

    assert result.exit_code == 0
    assert "metadata_ok:" in result.stdout
    assert "vector_ok:" not in result.stdout
    assert "vector_schema_compatible:" not in result.stdout
```

- [ ] **Step 2: Run the boundary tests**

Run:

```bash
uv run --python 3.12 pytest tests/test_cli_surface_boundary.py -q
```

Expected: boundary tests pass because Phase 2A has not added `vg search` or vector status output.

- [ ] **Step 3: Run boundary checks with static checks**

Run:

```bash
uv run --python 3.12 pytest tests/test_cli_surface_boundary.py -q
uv run --python 3.12 ruff check src tests
uv run --python 3.12 mypy src
```

Expected: all commands pass.

- [ ] **Step 4: Commit boundary tests**

Run:

```bash
git add tests/test_cli_surface_boundary.py
git commit -m "test: protect phase 2a retrieval boundary"
```

## Task 6: Documentation And Final Acceptance Verification

**Files:**

- Review: `docs/SPEC.md`
- Review: `docs/DESIGN.md`
- Review: `docs/superpowers/specs/2026-06-08-phase-2a-retrieval-contract-vectorstore-boundary-design.md`
- Modify if needed: `docs/PATCH_LOG.md`

- [ ] **Step 1: Verify documentation matches the implemented Phase 2A contract**

Run:

```bash
rg -n "contract tests that future Chroma and Qdrant" docs/SPEC.md docs/superpowers/specs
old_embedding_terms='Embedding''Provider|Embedding''Policy|embedding_''policy|policy_''mismatch'
same_vault_invariant='evidence_''vault_id_must_match_result_''vault_id'
same_vault_invariant="${same_vault_invariant/evidence_vault_id/evidence vault_id}"
same_vault_invariant="${same_vault_invariant/result_vault_id/result vault_id}"
same_vault_invariant="${same_vault_invariant//_/ }"
rg -n "$old_embedding_terms" docs README.md --glob '!docs/superpowers/plans/2026-06-08-phase-2a-retrieval-contract-vectorstore-boundary.md'
rg -n "$same_vault_invariant" docs/SPEC.md docs/DESIGN.md docs/superpowers --glob '!docs/superpowers/plans/2026-06-08-phase-2a-retrieval-contract-vectorstore-boundary.md'
```

Expected:

- Chroma and Qdrant are both described as future implementations of the same
  `VectorStore` contract.
- old embedding provider/policy terms are absent.
- no global same-Vault evidence invariant remains.

- [ ] **Step 2: Update `docs/PATCH_LOG.md` only if execution changed the plan**

Record review-driven corrections that protect read-only behavior,
rebuildability, evidence authority, or multi-vault consistency. Do not duplicate
accepted architecture decisions that already live in `docs/DECISIONS.md`.

- [ ] **Step 3: Run the final Phase 2A verification set**

Run:

```bash
uv run --python 3.12 pytest -q
uv run --python 3.12 ruff check src tests
uv run --python 3.12 mypy src
git diff --check
```

Expected: all commands pass.

- [ ] **Step 4: Commit final documentation alignment if changed**

Run:

```bash
git add docs/PATCH_LOG.md docs/SPEC.md docs/DESIGN.md docs/superpowers/specs docs/superpowers/plans
git commit -m "docs: align phase 2a implementation acceptance"
```

## Self-Review Checklist

Spec coverage:

- `TextEmbeddings` contract: Task 1
- duplicate embedding input ID validation: Task 1
- Deterministic test `TextEmbeddings` implementation: Task 1
- Vector store protocol and records: Task 2
- Content-scope filter metadata: Task 2
- Scope filtering before limits: Task 2
- Multi-vault identity preservation: Task 2
- model-spec-aware vector identity and mixed-spec rejection: Task 2
- Metadata evidence resolution: Task 3
- Vector hits are not evidence authority: Task 2 and Task 3
- VectorHit-to-EvidenceReference ID binding before normal result rendering: Task 4
- missing and stale vector evidence warnings: Task 4
- Graph-ready retrieval result schema: Task 4
- Signal-level backend and revision metadata: Task 4
- No user-visible search or vector status in Phase 2A: Task 5
- Chroma and Qdrant shared `VectorStore` contract documentation: Task 6

Type consistency:

- `EvidenceReference` is owned by `MetadataStore` because metadata resolution is the evidence authority.
- `RetrievalResult` imports `EvidenceReference` instead of teaching retrieval code metadata table internals.
- `RetrievalResult` does not globally require evidence to share the result `vault_id`; vector-backed normal result assembly uses `require_vector_hit_evidence_match(...)` instead.
- `VectorStore` imports `QueryScope` and never imports `VaultCatalog`, preserving explicit scope resolution.
- Test fakes live under `tests/fakes` and do not become production backends.

Final verification:

```bash
uv run --python 3.12 pytest -q
uv run --python 3.12 ruff check src tests
uv run --python 3.12 mypy src
git diff --check
```

## Execution Handoff

Use `superpowers:subagent-driven-development` for execution if multiple agents are available. Use one fresh implementation subagent per task, then review the diff before starting the next task.

Use `superpowers:executing-plans` for inline execution when working in a single session.
