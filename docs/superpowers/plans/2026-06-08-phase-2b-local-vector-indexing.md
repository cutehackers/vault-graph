# Phase 2B Local Vector Indexing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the Phase 2B release slice: Chroma-backed local vector indexing, FastEmbed local CPU embeddings, metadata-to-vector reconcile, `vg index` vector updates, and `vg status` vector health without adding user search.

**Architecture:** Keep Phase 2B as a derived projection pipeline after metadata indexing. `MetadataStore` remains the chunk and evidence authority, `TextEmbeddings` converts text under one `EmbeddingModelSpec`, `VectorIndexer` owns reconcile planning and apply, and `VectorStore` hides Chroma persistence behind the Phase 2A contract. Chroma is used only as a local `PersistentClient`; Vault Graph must not run or expose a Chroma HTTP server in this slice.

**Tech Stack:** Python 3.12, dataclasses, Protocol interfaces, SQLite, Chroma local persistent client, FastEmbed, Hugging Face Hub snapshot downloads for pinned model revisions, Typer CLI, pytest, ruff, mypy.

---

## Scope

In scope:

- Core dependencies for local vector indexing: `chromadb`, `fastembed`, and direct `huggingface-hub` use for pinned model snapshots.
- `FastEmbedTextEmbeddings` as the default production local `TextEmbeddings` implementation.
- CPU tuning through `embedding_batch_size`, `embedding_parallelism`, and `embedding_lazy_load`.
- `MetadataStore.list_chunks(scope)`.
- Expanded vector records, manifests, and tombstones with freshness metadata.
- Chroma implementation of `VectorStore`.
- `VectorIndexer` plan and apply for scope-local reconcile.
- `IndexService` orchestration: metadata first, vector second.
- `vg index` vector output, dry-run vector planning, and vector failure exit behavior.
- `vg status --vault-id` and `vg status --all-vaults` with vector health, model spec, stale count, and last error.
- Read-only boundary tests for Chroma state and embedding cache paths.

Out of scope:

- `vg search`
- `vg ask`
- keyword retrieval
- hybrid ranking execution
- graph extraction
- graph traversal
- decision traces
- context packs
- MCP serving
- HTTP serving
- Qdrant
- hosted embedding APIs
- non-Markdown file indexing
- MacBook acceleration adapters

## External API Notes

Use these current API assumptions during implementation:

- Chroma `PersistentClient(path=...)` is the local disk client.
- Chroma collections support `get_or_create_collection(...)`, `upsert(...)`, `delete(...)`, `get(...)`, and `query(query_embeddings=...)`.
- Chroma collection configuration should set HNSW cosine distance with `configuration={"hnsw": {"space": "cosine"}}`.
- FastEmbed `TextEmbedding` embeds lists of strings and returns a generator of vectors.
- FastEmbed `embed(...)` supports `batch_size` and `parallel`.
- FastEmbed model loading must be wrapped so status and dry-run can inspect config without loading the model.
- Use `huggingface_hub.snapshot_download(repo_id=..., revision=..., cache_dir=...)` before constructing FastEmbed so the accepted model revision is pinned.

## File Structure

Create these files:

- `src/vault_graph/embeddings/fastembed_text_embeddings.py`: production local CPU `TextEmbeddings` adapter, default model spec, runtime config, cache-status helper, and FastEmbed lazy loading.
- `src/vault_graph/indexing/vector_indexer.py`: vector reconcile plan, vector apply result, stable vector IDs, content-scope derivation, batching, and stale-record comparison.
- `src/vault_graph/storage/local/chroma_vector_store.py`: Chroma-backed `VectorStore` implementation and Chroma schema guard.
- `src/vault_graph/storage/local/vector_status_store.py`: small JSON diagnostic state for last vector success/failure; this is derived status only.
- `tests/test_fastembed_text_embeddings.py`: default spec, config, cache, duplicate input, lazy-load, and failure tests.
- `tests/test_metadata_chunk_listing.py`: `MetadataStore.list_chunks(scope)` behavior.
- `tests/test_vector_indexer.py`: reconcile planning and apply behavior with fakes.
- `tests/test_chroma_vector_store.py`: Chroma persistence, manifest, filtering, schema, and tombstone contract tests.
- `tests/test_cli_vector_indexing.py`: CLI `index` and `status` Phase 2B behavior.
- `tests/test_vector_indexing_read_only_boundary.py`: state path, Chroma path, model cache path, and Vault mutation guards.

Modify these files:

- `pyproject.toml`: add Chroma, FastEmbed, and Hugging Face Hub dependencies.
- `uv.lock`: refresh dependency lock.
- `src/vault_graph/app/catalog_service.py`: add `vector_path`, `vector_status_path`, and `embedding_cache_path`.
- `src/vault_graph/app/index_service.py`: orchestrate metadata plus vector projection and scoped status.
- `src/vault_graph/app/path_guard.py`: reuse write-target guard for vector and cache paths.
- `src/vault_graph/cli/main.py`: wire vector defaults into `index` and scoped vector status into `status`.
- `src/vault_graph/embeddings/__init__.py`: export FastEmbed adapter classes.
- `src/vault_graph/errors.py`: add vector indexing and model-unavailable error classes if needed.
- `src/vault_graph/indexing/metadata_indexer.py`: expose a metadata preview used by vector dry-run.
- `src/vault_graph/indexing/revision_planner.py`: add metadata preview dataclass.
- `src/vault_graph/storage/interfaces/metadata_store.py`: add `list_chunks(scope)`.
- `src/vault_graph/storage/interfaces/vector_store.py`: expand records, manifests, and tombstones for Phase 2B freshness.
- `src/vault_graph/storage/local/sqlite_metadata_store.py`: implement chunk listing.
- `tests/fakes/deterministic_text_embeddings.py`: expose runtime config helpers needed by vector indexer tests.
- `tests/fakes/in_memory_vector_store.py`: support exact tombstones, multiple model-spec collections over time, and expanded manifest fields.
- Existing Phase 2A tests: update expected vector record fields while preserving Phase 2A boundary guarantees.

## Task 1: Dependency And Contract Expansion

**Files:**

- Modify: `pyproject.toml`
- Modify: `uv.lock`
- Modify: `src/vault_graph/errors.py`
- Modify: `src/vault_graph/storage/interfaces/vector_store.py`
- Modify: `tests/fakes/in_memory_vector_store.py`
- Modify: `tests/test_vector_store_contract.py`

- [ ] **Step 1: Add failing vector contract tests for Phase 2B freshness**

Add tests to `tests/test_vector_store_contract.py` that prove the expanded contract:

```python
def test_manifest_exposes_vector_freshness_fields() -> None:
    store = InMemoryVectorStore()
    record = make_record(vault_id="default", path="wiki/page.md", text="alpha", content_scope="wiki")
    store.apply_vector_revision(vector_index_revision="vector-1", records=(record,), tombstones=())

    manifest = store.export_manifest(QueryScope(vault_ids=("default",), content_scopes=("wiki",)))

    assert manifest[0].source_chunk_hash == "chunk-hash-wiki/page.md"
    assert manifest[0].chunker_version == "heading-section-v1"
    assert manifest[0].backend_schema_version == "memory-vector-v1"
    assert manifest[0].metadata_index_revision == "metadata-1"
    assert manifest[0].vector_index_revision == "vector-1"


def test_tombstone_targets_exact_vector_identity() -> None:
    store = InMemoryVectorStore()
    old_record = make_record(
        vault_id="default",
        path="wiki/page.md",
        text="alpha",
        content_scope="wiki",
        model_spec=SECOND_SPEC,
        vector_index_revision="vector-old",
    )
    new_record = make_record(
        vault_id="default",
        path="wiki/page.md",
        text="alpha",
        content_scope="wiki",
        vector_index_revision="vector-new",
    )
    store.apply_vector_revision(vector_index_revision="vector-old", records=(old_record,), tombstones=())
    store.apply_vector_revision(
        vector_index_revision="vector-new",
        records=(new_record,),
        tombstones=(
            VectorTombstone(
                vector_id=old_record.vector_id,
                vault_id=old_record.vault_id,
                chunk_id=old_record.chunk_id,
                embedding_spec=old_record.embedding.model_spec,
            ),
        ),
    )

    manifest = store.export_manifest(QueryScope(vault_ids=("default",), content_scopes=("wiki",)))

    assert tuple(row.vector_id for row in manifest) == (new_record.vector_id,)
```

Update `make_record(...)` in that file to pass:

```python
source_chunk_hash=f"chunk-hash-{path}",
chunker_version="heading-section-v1",
backend_schema_version="memory-vector-v1",
```

- [ ] **Step 2: Run the focused contract tests and verify failure**

Run:

```bash
uv run --python 3.12 pytest tests/test_vector_store_contract.py -q
```

Expected: FAIL because `VectorEmbeddingRecord`, `VectorManifestRecord`, and `VectorTombstone` do not yet expose the new fields.

- [ ] **Step 3: Add dependencies**

Modify `pyproject.toml` dependencies:

```toml
dependencies = [
  "PyYAML>=6.0.2",
  "chromadb>=1.5.9,<2.0",
  "fastembed>=0.8.0,<1.0",
  "huggingface-hub>=0.31,<1.0",
  "typer>=0.12.5",
]
```

Run:

```bash
uv lock
```

Expected: `uv.lock` updates and resolves on Python 3.12.

- [ ] **Step 4: Probe dependency API assumptions**

Run:

```bash
uv run --python 3.12 python - <<'PY'
from pathlib import Path

from fastembed import TextEmbedding

models = TextEmbedding.list_supported_models()
assert any(item["model"] == "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2" for item in models)
backend = TextEmbedding(
    model_name="sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
    specific_model_path=str(Path("/tmp/vault-graph-fastembed-probe")),
    lazy_load=True,
)
assert getattr(backend.model, "_specific_model_path", None) == str(Path("/tmp/vault-graph-fastembed-probe"))
PY
```

Expected: exits `0`. If this fails, stop and update the plan before writing
adapter code. FastEmbed 0.8.0 accepts `specific_model_path` through
`TextEmbedding(**kwargs)` and forwards it to the concrete ONNX text embedding
model, so the probe verifies actual propagation instead of the public wrapper
signature. Do not continue with an unpinned FastEmbed model load.

- [ ] **Step 5: Expand vector interface records**

Modify `src/vault_graph/storage/interfaces/vector_store.py`:

```python
@dataclass(frozen=True)
class VectorEmbeddingRecord:
    vector_id: str
    vault_id: str
    document_id: str
    chunk_id: str
    content_scope: str
    embedding: EmbeddingVector
    source_chunk_hash: str
    chunker_version: str
    metadata_index_revision: str
    vector_index_revision: str
    backend_schema_version: str


@dataclass(frozen=True)
class VectorTombstone:
    vector_id: str
    vault_id: str
    chunk_id: str
    embedding_spec: EmbeddingModelSpec


@dataclass(frozen=True)
class VectorManifestRecord:
    vector_id: str
    vault_id: str
    document_id: str
    chunk_id: str
    content_scope: str
    embedding_spec: EmbeddingModelSpec
    source_chunk_hash: str
    chunker_version: str
    metadata_index_revision: str
    vector_index_revision: str
    backend: str
    backend_schema_version: str
```

Keep validation rules:

- all string fields are non-empty
- `content_scope` is validated through `QueryScope`
- `VectorQuery.query_vector.model_spec` must equal `VectorQuery.embedding_spec`
- `VectorHit` remains evidence-free and does not expose path, text, anchor, or source hash

- [ ] **Step 6: Update in-memory vector fake**

Modify `tests/fakes/in_memory_vector_store.py`:

```python
class InMemoryVectorStore:
    def __init__(self) -> None:
        self._records: dict[str, VectorEmbeddingRecord] = {}

    def apply_vector_revision(
        self,
        *,
        vector_index_revision: str,
        records: tuple[VectorEmbeddingRecord, ...],
        tombstones: tuple[VectorTombstone, ...],
    ) -> None:
        if not vector_index_revision:
            raise VectorStoreError("vector_index_revision is required")
        _validate_single_record_spec(records)
        for record in records:
            if record.vector_index_revision != vector_index_revision:
                raise VectorStoreError("record vector_index_revision must match revision being applied")
        for tombstone in tombstones:
            existing = self._records.get(tombstone.vector_id)
            if existing is not None and existing.vault_id == tombstone.vault_id and existing.chunk_id == tombstone.chunk_id:
                if existing.embedding.model_spec == tombstone.embedding_spec:
                    self._records.pop(tombstone.vector_id, None)
        for record in records:
            self._records[record.vector_id] = record

    def search(self, query: VectorQuery) -> tuple[VectorHit, ...]:
        scoped_records = tuple(
            record
            for record in self._records.values()
            if record.embedding.model_spec == query.embedding_spec and _record_in_scope(record, query.scope)
        )
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
```

`export_manifest(scope)` must return records across all model specs in scope. `search(query)` must search only the requested `EmbeddingModelSpec`.

Add this helper:

```python
def _validate_single_record_spec(records: tuple[VectorEmbeddingRecord, ...]) -> None:
    specs = {record.embedding.model_spec for record in records}
    if len(specs) > 1:
        raise VectorStoreError("embedding model spec mismatch")
```

Update the existing model-spec search test so a valid query using a different
`EmbeddingModelSpec` returns empty hits instead of raising a store-level
mismatch. Keep `test_vector_query_rejects_query_vector_model_spec_mismatch`
unchanged, because `VectorQuery` must still reject a query vector whose own
model spec disagrees with the requested `embedding_spec`.

Use this replacement test:

```python
def test_search_with_valid_different_model_spec_returns_no_hits() -> None:
    store = InMemoryVectorStore()
    record = make_record(vault_id="default", path="wiki/page.md", text="alpha", content_scope="wiki")
    store.apply_vector_revision(vector_index_revision="vector-1", records=(record,), tombstones=())
    query_vector = DeterministicTextEmbeddings(SECOND_SPEC).embed((EmbeddingInput(input_id="query", text="alpha"),))[0]

    hits = store.search(
        VectorQuery(
            query_vector=query_vector,
            scope=QueryScope(vault_ids=("default",), content_scopes=("wiki",)),
            limit=10,
            embedding_spec=SECOND_SPEC,
        )
    )

    assert hits == ()
```

- [ ] **Step 7: Run vector contract tests**

Run:

```bash
uv run --python 3.12 pytest tests/test_vector_store_contract.py -q
```

Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add pyproject.toml uv.lock src/vault_graph/errors.py src/vault_graph/storage/interfaces/vector_store.py tests/fakes/in_memory_vector_store.py tests/test_vector_store_contract.py
git commit -m "feat: expand vector manifest contract for phase 2b"
```

## Task 2: Metadata Chunk Listing Boundary

**Files:**

- Modify: `src/vault_graph/indexing/metadata_indexer.py`
- Modify: `src/vault_graph/indexing/revision_planner.py`
- Modify: `src/vault_graph/storage/interfaces/metadata_store.py`
- Modify: `src/vault_graph/storage/local/sqlite_metadata_store.py`
- Create: `tests/test_metadata_chunk_listing.py`

- [ ] **Step 1: Write failing chunk-listing tests**

Create `tests/test_metadata_chunk_listing.py`:

```python
from pathlib import Path

from vault_graph.indexing.metadata_indexer import MetadataIndexer
from vault_graph.ingestion.vault_catalog import QueryScope, VaultCatalog, VaultCatalogEntry
from vault_graph.storage.local.sqlite_metadata_store import SQLiteMetadataStore


def write_page(root: Path, path: str, body: str) -> None:
    file_path = root / path
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(body, encoding="utf-8")


def make_catalog(root: Path, vault_id: str = "default") -> VaultCatalog:
    return VaultCatalog.from_entries(
        entries=[VaultCatalogEntry.from_root(vault_id=vault_id, root_path=root)],
        active_vault_id=vault_id,
    )


def test_list_chunks_returns_current_non_tombstoned_chunks(tmp_path: Path) -> None:
    vault_root = tmp_path / "vault"
    write_page(vault_root, "wiki/page.md", "# Page\nBody\n")
    catalog = make_catalog(vault_root)
    store = SQLiteMetadataStore(tmp_path / "state" / "metadata.sqlite3", initialize=True)
    indexer = MetadataIndexer(catalog=catalog, metadata_store=store)
    indexer.apply(scope=catalog.default_scope())

    chunks = store.list_chunks(QueryScope(vault_ids=("default",), content_scopes=("wiki",)))

    assert len(chunks) == 1
    assert chunks[0].vault_id == "default"
    assert chunks[0].path == "wiki/page.md"
    assert chunks[0].text == "Body"
    assert chunks[0].content_hash
    assert chunks[0].chunker_version == "heading-section-v1"
    assert chunks[0].index_revision is not None


def test_list_chunks_filters_vault_and_content_scope(tmp_path: Path) -> None:
    first_root = tmp_path / "first"
    second_root = tmp_path / "second"
    write_page(first_root, "wiki/page.md", "# First\nBody\n")
    write_page(first_root, "docs/page.md", "# Docs\nBody\n")
    write_page(second_root, "wiki/page.md", "# Second\nBody\n")
    catalog = VaultCatalog.from_entries(
        entries=[
            VaultCatalogEntry.from_root(vault_id="first", root_path=first_root),
            VaultCatalogEntry.from_root(vault_id="second", root_path=second_root),
        ],
        active_vault_id="first",
    )
    store = SQLiteMetadataStore(tmp_path / "state" / "metadata.sqlite3", initialize=True)
    MetadataIndexer(catalog=catalog, metadata_store=store).apply(scope=catalog.scope_for_all_enabled())

    chunks = store.list_chunks(QueryScope(vault_ids=("first",), content_scopes=("wiki",)))

    assert tuple((chunk.vault_id, chunk.path) for chunk in chunks) == (("first", "wiki/page.md"),)


def test_list_chunks_excludes_tombstoned_documents(tmp_path: Path) -> None:
    vault_root = tmp_path / "vault"
    write_page(vault_root, "wiki/page.md", "# Page\nBody\n")
    catalog = make_catalog(vault_root)
    store = SQLiteMetadataStore(tmp_path / "state" / "metadata.sqlite3", initialize=True)
    indexer = MetadataIndexer(catalog=catalog, metadata_store=store)
    indexer.apply(scope=catalog.default_scope())
    (vault_root / "wiki" / "page.md").unlink()
    indexer.apply(scope=catalog.default_scope())

    chunks = store.list_chunks(QueryScope(vault_ids=("default",), content_scopes=("wiki",)))

    assert chunks == ()


def test_metadata_preview_contains_chunks_after_apply_without_writing(tmp_path: Path) -> None:
    vault_root = tmp_path / "vault"
    write_page(vault_root, "wiki/page.md", "# Page\nBody\n")
    catalog = make_catalog(vault_root)
    store = SQLiteMetadataStore(tmp_path / "state" / "metadata.sqlite3")
    preview = MetadataIndexer(catalog=catalog, metadata_store=store).preview(scope=catalog.default_scope())

    assert preview.plan.changed_paths == (("default", "wiki/page.md"),)
    assert len(preview.chunks_after_apply) == 1
    assert preview.chunks_after_apply[0].index_revision == preview.plan.index_revision
    assert not (tmp_path / "state" / "metadata.sqlite3").exists()
```

- [ ] **Step 2: Run tests and verify failure**

Run:

```bash
uv run --python 3.12 pytest tests/test_metadata_chunk_listing.py -q
```

Expected: FAIL because `MetadataStore.list_chunks` does not exist.

- [ ] **Step 3: Add metadata preview dataclass**

Modify `src/vault_graph/indexing/revision_planner.py`:

```python
from vault_graph.ingestion.document_normalizer import ChunkSnapshot


@dataclass(frozen=True)
class MetadataIndexPreview:
    plan: MetadataRevisionPlan
    chunks_after_apply: tuple[ChunkSnapshot, ...]
```

`chunks_after_apply` means the chunk set that vector dry-run should use if the
metadata plan were applied. Changed and new chunks must carry the new
`plan.index_revision`; unchanged chunks must keep their current stored
`index_revision`; deleted documents must not contribute chunks.

- [ ] **Step 4: Add `MetadataIndexer.preview(...)`**

Modify `src/vault_graph/indexing/metadata_indexer.py`:

```python
def preview(self, *, scope: QueryScope, full: bool = False) -> MetadataIndexPreview:
    plan, normalized = self._build_plan(scope=scope, full=full)
    changed_keys = set(plan.changed_paths)
    changed_chunks = tuple(
        replace(chunk, index_revision=plan.index_revision)
        for item in normalized
        if (item.document.vault_id, item.document.path) in changed_keys
        for chunk in item.chunks
    )
    unchanged_chunks = tuple(
        chunk
        for chunk in self._metadata_store.list_chunks(scope)
        if (chunk.vault_id, chunk.path) in set(plan.unchanged_paths)
    )
    return MetadataIndexPreview(plan=plan, chunks_after_apply=tuple(sorted(changed_chunks + unchanged_chunks, key=_chunk_sort_key)))
```

Add imports:

```python
from dataclasses import replace
from vault_graph.indexing.revision_planner import MetadataIndexPreview, MetadataRevisionPlan
```

Add helper:

```python
def _chunk_sort_key(chunk: ChunkSnapshot) -> tuple[str, str, str]:
    return (chunk.vault_id, chunk.path, chunk.chunk_id)
```

This preview is required because `vg index --dry-run` must report vector work
without writing metadata first. Do not make vector dry-run read new chunks from
SQLite, because dry-run must not create or update SQLite state.

- [ ] **Step 5: Add protocol method**

Modify `src/vault_graph/storage/interfaces/metadata_store.py`:

```python
from vault_graph.ingestion.vault_catalog import QueryScope


class MetadataStore(Protocol):
    def list_chunks(self, scope: QueryScope) -> tuple[ChunkSnapshot, ...]:
        pass
```

- [ ] **Step 6: Implement SQLite chunk listing**

Add to `SQLiteMetadataStore`:

```python
def list_chunks(self, scope: QueryScope) -> tuple[ChunkSnapshot, ...]:
    if not scope.vault_ids:
        return ()
    if not self._database_path.exists():
        return ()
    vault_placeholders = ", ".join("?" for _ in scope.vault_ids)
    with self._connect() as connection:
        rows = connection.execute(
            f"""
            SELECT c.vault_id, c.chunk_id, c.document_id, c.path, c.section, c.anchor,
                   c.text, c.token_count, c.content_hash, c.chunker_version, c.index_revision
            FROM chunks c
            INNER JOIN documents d
              ON d.vault_id = c.vault_id
             AND d.document_id = c.document_id
             AND d.path = c.path
            WHERE c.vault_id IN ({vault_placeholders})
              AND d.is_tombstoned = 0
            ORDER BY c.vault_id, c.path, c.chunk_id
            """,
            scope.vault_ids,
        ).fetchall()
    return tuple(
        _chunk_snapshot_from_row(row)
        for row in rows
        if _path_in_content_scope(path=str(row["path"]), content_scopes=scope.content_scopes)
    )
```

Add helper:

```python
def _path_in_content_scope(*, path: str, content_scopes: tuple[str, ...]) -> bool:
    return any(path == scope or path.startswith(f"{scope}/") for scope in content_scopes)
```

- [ ] **Step 7: Run metadata chunk-listing tests**

Run:

```bash
uv run --python 3.12 pytest tests/test_metadata_chunk_listing.py tests/test_sqlite_metadata_store.py tests/test_metadata_indexer.py -q
```

Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add src/vault_graph/indexing/metadata_indexer.py src/vault_graph/indexing/revision_planner.py src/vault_graph/storage/interfaces/metadata_store.py src/vault_graph/storage/local/sqlite_metadata_store.py tests/test_metadata_chunk_listing.py
git commit -m "feat: list metadata chunks for vector indexing"
```

## Task 3: FastEmbed TextEmbeddings Adapter

**Files:**

- Create: `src/vault_graph/embeddings/fastembed_text_embeddings.py`
- Modify: `src/vault_graph/embeddings/__init__.py`
- Modify: `tests/fakes/deterministic_text_embeddings.py`
- Create: `tests/test_fastembed_text_embeddings.py`

- [ ] **Step 1: Write failing FastEmbed adapter tests**

Create `tests/test_fastembed_text_embeddings.py`:

```python
from pathlib import Path

import pytest

from vault_graph.embeddings.fastembed_text_embeddings import (
    DEFAULT_FASTEMBED_MODEL_SPEC,
    FastEmbedTextEmbeddings,
    FastEmbedTextEmbeddingsConfig,
)
from vault_graph.embeddings.text_embeddings import EmbeddingInput, EmbeddingVector
from vault_graph.errors import TextEmbeddingsError


def test_default_model_spec_is_fixed() -> None:
    assert DEFAULT_FASTEMBED_MODEL_SPEC.model_name == "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
    assert DEFAULT_FASTEMBED_MODEL_SPEC.model_version == "faf4aa4225822f3bc6376869cb1164e8e3feedd0"
    assert DEFAULT_FASTEMBED_MODEL_SPEC.dimensions == 384
    assert DEFAULT_FASTEMBED_MODEL_SPEC.spec_version == "fastembed-multilingual-minilm-l12-v2-cosine-v1"


def test_runtime_config_does_not_change_model_spec(tmp_path: Path) -> None:
    first = FastEmbedTextEmbeddingsConfig(cache_dir=tmp_path / "cache", embedding_batch_size=16)
    second = FastEmbedTextEmbeddingsConfig(cache_dir=tmp_path / "cache", embedding_batch_size=512, embedding_parallelism=0)

    assert first.model_spec() == second.model_spec()


def test_duplicate_input_ids_fail_before_backend_load(tmp_path: Path) -> None:
    embeddings = FastEmbedTextEmbeddings(
        config=FastEmbedTextEmbeddingsConfig(cache_dir=tmp_path / "cache"),
        backend_factory=lambda _, __: pytest.fail("backend must not load"),
    )

    with pytest.raises(TextEmbeddingsError, match="input_id must be unique"):
        embeddings.embed(
            (
                EmbeddingInput(input_id="same", text="alpha"),
                EmbeddingInput(input_id="same", text="beta"),
            )
        )


def test_embed_binds_backend_vectors_to_input_ids(tmp_path: Path) -> None:
    class Backend:
        def embed(self, documents: list[str], *, batch_size: int, parallel: int | None):
            assert documents == ["alpha", "beta"]
            assert batch_size == 256
            assert parallel is None
            return ([0.1] * 384, [0.2] * 384)

    embeddings = FastEmbedTextEmbeddings(
        config=FastEmbedTextEmbeddingsConfig(cache_dir=tmp_path / "cache"),
        backend_factory=lambda _, __: Backend(),
        snapshot_resolver=lambda _: tmp_path / "cache" / "snapshot",
    )

    vectors = embeddings.embed((EmbeddingInput(input_id="a", text="alpha"), EmbeddingInput(input_id="b", text="beta")))

    assert vectors == (
        EmbeddingVector(input_id="a", values=tuple([0.1] * 384), model_spec=DEFAULT_FASTEMBED_MODEL_SPEC),
        EmbeddingVector(input_id="b", values=tuple([0.2] * 384), model_spec=DEFAULT_FASTEMBED_MODEL_SPEC),
    )


def test_backend_dimension_mismatch_fails_loudly(tmp_path: Path) -> None:
    class Backend:
        def embed(self, documents: list[str], *, batch_size: int, parallel: int | None):
            return ([0.1] * 2,)

    embeddings = FastEmbedTextEmbeddings(
        config=FastEmbedTextEmbeddingsConfig(cache_dir=tmp_path / "cache"),
        backend_factory=lambda _, __: Backend(),
        snapshot_resolver=lambda _: tmp_path / "cache" / "snapshot",
    )

    with pytest.raises(TextEmbeddingsError, match="embedding dimension mismatch"):
        embeddings.embed((EmbeddingInput(input_id="a", text="alpha"),))


def test_model_unavailable_error_is_clear(tmp_path: Path) -> None:
    def fail_snapshot(_: FastEmbedTextEmbeddingsConfig) -> Path:
        raise TextEmbeddingsError("embedding model unavailable: offline and not cached")

    embeddings = FastEmbedTextEmbeddings(
        config=FastEmbedTextEmbeddingsConfig(cache_dir=tmp_path / "cache"),
        backend_factory=lambda _, __: pytest.fail("backend must not load"),
        snapshot_resolver=fail_snapshot,
    )

    with pytest.raises(TextEmbeddingsError, match="embedding model unavailable"):
        embeddings.embed((EmbeddingInput(input_id="a", text="alpha"),))
```

- [ ] **Step 2: Run tests and verify failure**

Run:

```bash
uv run --python 3.12 pytest tests/test_fastembed_text_embeddings.py -q
```

Expected: FAIL because `fastembed_text_embeddings.py` does not exist.

- [ ] **Step 3: Implement config and adapter**

Create `src/vault_graph/embeddings/fastembed_text_embeddings.py`:

```python
from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from vault_graph.embeddings.text_embeddings import EmbeddingInput, EmbeddingModelSpec, EmbeddingVector
from vault_graph.errors import TextEmbeddingsError

DEFAULT_FASTEMBED_MODEL_SPEC = EmbeddingModelSpec(
    model_name="sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
    model_version="faf4aa4225822f3bc6376869cb1164e8e3feedd0",
    dimensions=384,
    spec_version="fastembed-multilingual-minilm-l12-v2-cosine-v1",
)

FASTEMBED_ARTIFACT_REPO_ID = "qdrant/paraphrase-multilingual-MiniLM-L12-v2-onnx-Q"
SOURCE_MODEL_REVISION = "e8f8c211226b894fcb81acc59f3b34ba3efd5f42"


class FastEmbedBackend(Protocol):
    def embed(self, documents: list[str], *, batch_size: int, parallel: int | None) -> Iterable[Iterable[float]]: ...


@dataclass(frozen=True)
class FastEmbedTextEmbeddingsConfig:
    model_name: str = DEFAULT_FASTEMBED_MODEL_SPEC.model_name
    model_version: str = DEFAULT_FASTEMBED_MODEL_SPEC.model_version
    dimensions: int = DEFAULT_FASTEMBED_MODEL_SPEC.dimensions
    spec_version: str = DEFAULT_FASTEMBED_MODEL_SPEC.spec_version
    artifact_repo_id: str = FASTEMBED_ARTIFACT_REPO_ID
    source_model_revision: str = SOURCE_MODEL_REVISION
    cache_dir: Path = Path("~/.cache/vault-graph/embeddings")
    embedding_batch_size: int = 256
    embedding_parallelism: int | None = None
    embedding_lazy_load: bool = True

    def __post_init__(self) -> None:
        if self.embedding_batch_size <= 0:
            raise TextEmbeddingsError("embedding_batch_size must be positive")
        if self.embedding_parallelism is not None and self.embedding_parallelism < 0:
            raise TextEmbeddingsError("embedding_parallelism must be None, 0, or positive")

    def model_spec(self) -> EmbeddingModelSpec:
        return EmbeddingModelSpec(
            model_name=self.model_name,
            model_version=self.model_version,
            dimensions=self.dimensions,
            spec_version=self.spec_version,
        )


class FastEmbedTextEmbeddings:
    def __init__(
        self,
        *,
        config: FastEmbedTextEmbeddingsConfig,
        backend_factory: Callable[[FastEmbedTextEmbeddingsConfig, Path], FastEmbedBackend] | None = None,
        snapshot_resolver: Callable[[FastEmbedTextEmbeddingsConfig], Path] | None = None,
    ) -> None:
        self._config = config
        self._backend_factory = backend_factory or _default_backend_factory
        self._snapshot_resolver = snapshot_resolver or _resolve_snapshot
        self._backend: FastEmbedBackend | None = None
        if not config.embedding_lazy_load:
            self._backend = self._load_backend()

    @property
    def config(self) -> FastEmbedTextEmbeddingsConfig:
        return self._config

    def model_spec(self) -> EmbeddingModelSpec:
        return self._config.model_spec()

    def embed(self, inputs: tuple[EmbeddingInput, ...]) -> tuple[EmbeddingVector, ...]:
        _validate_unique_input_ids(inputs)
        if not inputs:
            return ()
        backend = self._backend or self._load_backend()
        self._backend = backend
        documents = [item.text for item in inputs]
        raw_vectors = tuple(
            backend.embed(
                documents,
                batch_size=self._config.embedding_batch_size,
                parallel=self._config.embedding_parallelism,
            )
        )
        if len(raw_vectors) != len(inputs):
            raise TextEmbeddingsError("embedding output count must match input count")
        return tuple(
            EmbeddingVector(
                input_id=item.input_id,
                values=tuple(float(value) for value in values),
                model_spec=self.model_spec(),
            )
            for item, values in zip(inputs, raw_vectors, strict=True)
        )

    def _load_backend(self) -> FastEmbedBackend:
        snapshot_path = self._snapshot_resolver(self._config)
        try:
            return self._backend_factory(self._config, snapshot_path)
        except Exception as exc:
            raise TextEmbeddingsError(f"embedding model unavailable: {exc}") from exc
```

Add helpers in the same file:

```python
def _validate_unique_input_ids(inputs: tuple[EmbeddingInput, ...]) -> None:
    seen: set[str] = set()
    for item in inputs:
        if item.input_id in seen:
            raise TextEmbeddingsError("input_id must be unique within one embedding call")
        seen.add(item.input_id)


def _resolve_snapshot(config: FastEmbedTextEmbeddingsConfig) -> Path:
    try:
        from huggingface_hub import snapshot_download

        return Path(
            snapshot_download(
                repo_id=config.artifact_repo_id,
                revision=config.model_version,
                cache_dir=str(config.cache_dir.expanduser()),
            )
        )
    except Exception as exc:
        raise TextEmbeddingsError(f"embedding model unavailable: {exc}") from exc


def _default_backend_factory(config: FastEmbedTextEmbeddingsConfig, snapshot_path: Path) -> FastEmbedBackend:
    from fastembed import TextEmbedding

    return TextEmbedding(
        model_name=config.model_name,
        specific_model_path=str(snapshot_path),
        cache_dir=str(config.cache_dir.expanduser()),
        lazy_load=config.embedding_lazy_load,
    )
```

The adapter must always construct the production FastEmbed backend from the pinned snapshot path returned by `snapshot_download(..., revision=config.model_version, ...)`. If the installed FastEmbed version removes `specific_model_path`, stop implementation and update the plan with an explicit replacement path before continuing; do not silently use an unpinned model download.

- [ ] **Step 4: Export adapter**

Modify `src/vault_graph/embeddings/__init__.py`:

```python
from vault_graph.embeddings.fastembed_text_embeddings import (
    DEFAULT_FASTEMBED_MODEL_SPEC,
    FastEmbedTextEmbeddings,
    FastEmbedTextEmbeddingsConfig,
)
from vault_graph.embeddings.text_embeddings import EmbeddingInput, EmbeddingModelSpec, EmbeddingVector, TextEmbeddings

__all__ = [
    "DEFAULT_FASTEMBED_MODEL_SPEC",
    "EmbeddingInput",
    "EmbeddingModelSpec",
    "EmbeddingVector",
    "FastEmbedTextEmbeddings",
    "FastEmbedTextEmbeddingsConfig",
    "TextEmbeddings",
]
```

- [ ] **Step 5: Run FastEmbed adapter tests**

Run:

```bash
uv run --python 3.12 pytest tests/test_fastembed_text_embeddings.py tests/test_text_embeddings_contract.py -q
```

Expected: PASS without downloading the real model.

- [ ] **Step 6: Commit**

```bash
git add src/vault_graph/embeddings/__init__.py src/vault_graph/embeddings/fastembed_text_embeddings.py tests/fakes/deterministic_text_embeddings.py tests/test_fastembed_text_embeddings.py
git commit -m "feat: add fastembed text embeddings adapter"
```

## Task 4: Chroma VectorStore Adapter

**Files:**

- Create: `src/vault_graph/storage/local/chroma_vector_store.py`
- Create: `tests/test_chroma_vector_store.py`

- [ ] **Step 1: Write failing Chroma adapter tests**

Create `tests/test_chroma_vector_store.py`:

```python
from pathlib import Path

import pytest

from tests.test_vector_store_contract import SECOND_SPEC, SPEC, make_query, make_record
from vault_graph.errors import VectorStoreError
from vault_graph.ingestion.vault_catalog import QueryScope
from vault_graph.storage.local.chroma_vector_store import CHROMA_VECTOR_SCHEMA_VERSION, ChromaVectorStore
from vault_graph.storage.interfaces.vector_store import VectorTombstone


def test_chroma_persists_records_and_exports_manifest(tmp_path: Path) -> None:
    store = ChromaVectorStore(tmp_path / "chroma", initialize=True)
    record = make_record(vault_id="default", path="wiki/page.md", text="alpha", content_scope="wiki")

    store.apply_vector_revision(vector_index_revision="vector-1", records=(record,), tombstones=())
    reopened = ChromaVectorStore(tmp_path / "chroma", initialize=False)

    manifest = reopened.export_manifest(QueryScope(vault_ids=("default",), content_scopes=("wiki",)))

    assert tuple(row.vector_id for row in manifest) == (record.vector_id,)
    assert manifest[0].backend == "chroma"
    assert manifest[0].backend_schema_version == CHROMA_VECTOR_SCHEMA_VERSION


def test_chroma_filters_scope_before_limit(tmp_path: Path) -> None:
    store = ChromaVectorStore(tmp_path / "chroma", initialize=True)
    wiki = make_record(vault_id="default", path="wiki/page.md", text="exact query", content_scope="wiki")
    docs = make_record(vault_id="default", path="docs/page.md", text="exact query", content_scope="docs")
    other = make_record(vault_id="other", path="wiki/page.md", text="exact query", content_scope="wiki")
    store.apply_vector_revision(vector_index_revision="vector-1", records=(wiki, docs, other), tombstones=())

    hits = store.search(make_query(text="exact query", scope=QueryScope(vault_ids=("default",), content_scopes=("wiki",)), limit=1))

    assert tuple((hit.vault_id, hit.content_scope) for hit in hits) == (("default", "wiki"),)


def test_chroma_exports_old_model_manifest_rows(tmp_path: Path) -> None:
    store = ChromaVectorStore(tmp_path / "chroma", initialize=True)
    old_record = make_record(
        vault_id="default",
        path="wiki/page.md",
        text="alpha",
        content_scope="wiki",
        model_spec=SECOND_SPEC,
    )
    store.apply_vector_revision(vector_index_revision="vector-old", records=(old_record,), tombstones=())

    manifest = store.export_manifest(QueryScope(vault_ids=("default",), content_scopes=("wiki",)))

    assert tuple(row.embedding_spec for row in manifest) == (SECOND_SPEC,)


def test_chroma_exact_tombstone_removes_record(tmp_path: Path) -> None:
    store = ChromaVectorStore(tmp_path / "chroma", initialize=True)
    record = make_record(vault_id="default", path="wiki/page.md", text="alpha", content_scope="wiki")
    store.apply_vector_revision(vector_index_revision="vector-1", records=(record,), tombstones=())
    store.apply_vector_revision(
        vector_index_revision="vector-2",
        records=(),
        tombstones=(
            VectorTombstone(
                vector_id=record.vector_id,
                vault_id=record.vault_id,
                chunk_id=record.chunk_id,
                embedding_spec=record.embedding.model_spec,
            ),
        ),
    )

    assert store.search(make_query(text="alpha", scope=QueryScope(vault_ids=("default",), content_scopes=("wiki",)))) == ()


def test_chroma_tombstone_requires_matching_vault_chunk_and_spec(tmp_path: Path) -> None:
    store = ChromaVectorStore(tmp_path / "chroma", initialize=True)
    record = make_record(vault_id="default", path="wiki/page.md", text="alpha", content_scope="wiki")
    store.apply_vector_revision(vector_index_revision="vector-1", records=(record,), tombstones=())
    store.apply_vector_revision(
        vector_index_revision="vector-2",
        records=(),
        tombstones=(
            VectorTombstone(
                vector_id=record.vector_id,
                vault_id="other",
                chunk_id=record.chunk_id,
                embedding_spec=record.embedding.model_spec,
            ),
        ),
    )

    manifest = store.export_manifest(QueryScope(vault_ids=("default",), content_scopes=("wiki",)))

    assert tuple(row.vector_id for row in manifest) == (record.vector_id,)


def test_chroma_missing_path_reports_uninitialized_health(tmp_path: Path) -> None:
    store = ChromaVectorStore(tmp_path / "missing", initialize=False)

    health = store.health()

    assert health.ok is False
    assert health.backend == "chroma"
    assert health.schema_compatible is False
    assert "not initialized" in health.message


def test_chroma_missing_readonly_path_export_and_search_do_not_create_state(tmp_path: Path) -> None:
    path = tmp_path / "missing"
    store = ChromaVectorStore(path, initialize=False)

    manifest = store.export_manifest(QueryScope(vault_ids=("default",), content_scopes=("wiki",)))
    hits = store.search(make_query(text="alpha", scope=QueryScope(vault_ids=("default",), content_scopes=("wiki",))))

    assert manifest == ()
    assert hits == ()
    assert not path.exists()
```

- [ ] **Step 2: Run tests and verify failure**

Run:

```bash
uv run --python 3.12 pytest tests/test_chroma_vector_store.py -q
```

Expected: FAIL because `ChromaVectorStore` does not exist.

- [ ] **Step 3: Implement Chroma adapter**

Create `src/vault_graph/storage/local/chroma_vector_store.py` with these core pieces:

```python
from __future__ import annotations

import hashlib
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from vault_graph.embeddings.text_embeddings import EmbeddingModelSpec
from vault_graph.errors import VectorStoreError
from vault_graph.ingestion.vault_catalog import QueryScope
from vault_graph.storage.interfaces.store_health import StoreHealth
from vault_graph.storage.interfaces.vector_store import (
    VectorEmbeddingRecord,
    VectorHit,
    VectorManifestRecord,
    VectorQuery,
    VectorStore,
    VectorTombstone,
)

CHROMA_VECTOR_SCHEMA_VERSION = "chroma-vector-v1"
CHROMA_BACKEND = "chroma"
COLLECTION_PREFIX = "vault_graph"


class ChromaVectorStore(VectorStore):
    def __init__(self, path: Path, *, initialize: bool = False) -> None:
        self._path = path.expanduser().resolve()
        self._initialize = initialize
        self._client: Any | None = None
        if initialize:
            self._path.mkdir(parents=True, exist_ok=True)

    def apply_vector_revision(
        self,
        *,
        vector_index_revision: str,
        records: tuple[VectorEmbeddingRecord, ...],
        tombstones: tuple[VectorTombstone, ...],
    ) -> None:
        if not vector_index_revision:
            raise VectorStoreError("vector_index_revision is required")
        client = self._require_client()
        for tombstone in tombstones:
            collection = self._get_collection_if_exists(client, tombstone.embedding_spec)
            if collection is not None:
                metadata = collection.get(ids=[tombstone.vector_id], include=["metadatas"])["metadatas"]
                if metadata and _metadata_matches_tombstone(metadata[0], tombstone):
                    collection.delete(ids=[tombstone.vector_id])
        for embedding_spec, grouped in _group_records_by_spec(records).items():
            collection = self._get_or_create_collection(client, embedding_spec)
            collection.upsert(
                ids=[record.vector_id for record in grouped],
                embeddings=[list(record.embedding.values) for record in grouped],
                metadatas=[_metadata_for_record(record) for record in grouped],
            )
```

Implement:

- `_client()` using `chromadb.PersistentClient(path=str(self._path))`
- `_get_or_create_collection(...)` with metadata plus `configuration={"hnsw": {"space": "cosine"}}`
- `_collection_name(spec)` using `sha256` of model name, model version, dimensions, and spec version
- `_metadata_for_record(record)` with only scalar Chroma metadata values
- `export_manifest(scope)` by iterating Vault Graph collections, reading metadatas, and filtering with same-or-child content-scope semantics
- `search(query)` by first collecting scoped IDs, then calling `collection.query(query_embeddings=[...], ids=scoped_ids, n_results=query.limit, include=["metadatas", "distances"])`
- `health()` returning uninitialized status without creating the path when `initialize=False` and the path is missing
- `export_manifest(scope)` returning `()` without creating the path when `initialize=False` and the path is missing
- `search(query)` returning `()` without creating the path when `initialize=False` and the path is missing
- `_metadata_matches_tombstone(metadata, tombstone)` checking `vector_id`,
  `vault_id`, `chunk_id`, and all `EmbeddingModelSpec` fields before deleting

`search(query)` must never pass `query_texts` or documents to Chroma. Vault Graph supplies raw embeddings so Chroma does not own embedding policy.

- [ ] **Step 4: Run Chroma tests**

Run:

```bash
uv run --python 3.12 pytest tests/test_chroma_vector_store.py tests/test_vector_store_contract.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/vault_graph/storage/local/chroma_vector_store.py tests/test_chroma_vector_store.py
git commit -m "feat: add local chroma vector store"
```

## Task 5: VectorIndexer Plan And Apply

**Files:**

- Create: `src/vault_graph/indexing/vector_indexer.py`
- Create: `tests/test_vector_indexer.py`

- [ ] **Step 1: Write failing vector indexer tests**

Create `tests/test_vector_indexer.py`:

```python
from dataclasses import replace

import pytest

from tests.fakes.deterministic_text_embeddings import DeterministicTextEmbeddings
from tests.fakes.in_memory_vector_store import InMemoryVectorStore
from vault_graph.embeddings.text_embeddings import EmbeddingModelSpec
from vault_graph.errors import TextEmbeddingsError, VectorStoreError
from vault_graph.indexing.vector_indexer import VectorIndexer, stable_vector_id
from vault_graph.ingestion.document_normalizer import ChunkSnapshot
from vault_graph.ingestion.vault_catalog import QueryScope


SPEC = EmbeddingModelSpec(model_name="deterministic", model_version="v1", dimensions=4, spec_version="spec-v1")
SECOND_SPEC = EmbeddingModelSpec(model_name="deterministic", model_version="v2", dimensions=4, spec_version="spec-v2")


class ChunkStore:
    def __init__(self, chunks: tuple[ChunkSnapshot, ...]) -> None:
        self.chunks = chunks

    def list_chunks(self, scope: QueryScope) -> tuple[ChunkSnapshot, ...]:
        return tuple(
            chunk
            for chunk in self.chunks
            if chunk.vault_id in scope.vault_ids
            and any(chunk.path == content_scope or chunk.path.startswith(f"{content_scope}/") for content_scope in scope.content_scopes)
        )


def chunk(vault_id: str = "default", path: str = "wiki/page.md", text: str = "alpha") -> ChunkSnapshot:
    return ChunkSnapshot(
        vault_id=vault_id,
        chunk_id=f"{vault_id}:{path}:chunk",
        document_id=f"{vault_id}:{path}:document",
        path=path,
        section="Page",
        anchor="page",
        text=text,
        token_count=len(text.split()),
        content_hash=f"hash:{text}",
        chunker_version="heading-section-v1",
        index_revision="metadata-1",
    )


def test_plan_marks_new_chunks_for_upsert() -> None:
    indexer = VectorIndexer(
    chunk_store=ChunkStore((chunk(),)),
        vector_store=InMemoryVectorStore(),
        text_embeddings=DeterministicTextEmbeddings(SPEC),
    )

    plan = indexer.plan(scopes=(QueryScope(vault_ids=("default",), content_scopes=("wiki",)),))

    assert plan.upsert_count == 1
    assert plan.tombstone_count == 0
    assert plan.unchanged_count == 0
    assert plan.embedding_count == 1


def test_apply_embeds_upserts_and_records_manifest() -> None:
    vector_store = InMemoryVectorStore()
    indexer = VectorIndexer(
        chunk_store=ChunkStore((chunk(),)),
        vector_store=vector_store,
        text_embeddings=DeterministicTextEmbeddings(SPEC),
    )

    result = indexer.apply(scopes=(QueryScope(vault_ids=("default",), content_scopes=("wiki",)),))

    manifest = vector_store.export_manifest(QueryScope(vault_ids=("default",), content_scopes=("wiki",)))
    assert result.upsert_count == 1
    assert result.tombstone_count == 0
    assert manifest[0].source_chunk_hash == "hash:alpha"
    assert manifest[0].metadata_index_revision == "metadata-1"


def test_changed_chunk_hash_replaces_existing_vector() -> None:
    vector_store = InMemoryVectorStore()
    first = chunk(text="alpha")
    VectorIndexer(
        chunk_store=ChunkStore((first,)),
        vector_store=vector_store,
        text_embeddings=DeterministicTextEmbeddings(SPEC),
    ).apply(scopes=(QueryScope(vault_ids=("default",), content_scopes=("wiki",)),))
    second = replace(first, text="beta", content_hash="hash:beta")
    indexer = VectorIndexer(
        chunk_store=ChunkStore((second,)),
        vector_store=vector_store,
        text_embeddings=DeterministicTextEmbeddings(SPEC),
    )

    plan = indexer.plan(scopes=(QueryScope(vault_ids=("default",), content_scopes=("wiki",)),))
    result = indexer.apply(scopes=(QueryScope(vault_ids=("default",), content_scopes=("wiki",)),))

    assert plan.upsert_count == 1
    assert plan.tombstone_count == 1
    assert result.upsert_count == 1


def test_model_spec_change_tombstones_old_model_row() -> None:
    vector_store = InMemoryVectorStore()
    VectorIndexer(
        chunk_store=ChunkStore((chunk(),)),
        vector_store=vector_store,
        text_embeddings=DeterministicTextEmbeddings(SPEC),
    ).apply(scopes=(QueryScope(vault_ids=("default",), content_scopes=("wiki",)),))
    indexer = VectorIndexer(
        chunk_store=ChunkStore((chunk(),)),
        vector_store=vector_store,
        text_embeddings=DeterministicTextEmbeddings(SECOND_SPEC),
    )

    result = indexer.apply(scopes=(QueryScope(vault_ids=("default",), content_scopes=("wiki",)),))
    manifest = vector_store.export_manifest(QueryScope(vault_ids=("default",), content_scopes=("wiki",)))

    assert result.upsert_count == 1
    assert result.tombstone_count == 1
    assert tuple(row.embedding_spec for row in manifest) == (SECOND_SPEC,)


def test_narrow_scope_does_not_tombstone_other_vault() -> None:
    vector_store = InMemoryVectorStore()
    chunks = (chunk(vault_id="first"), chunk(vault_id="second"))
    VectorIndexer(
        chunk_store=ChunkStore(chunks),
        vector_store=vector_store,
        text_embeddings=DeterministicTextEmbeddings(SPEC),
    ).apply(scopes=(QueryScope(vault_ids=("first", "second"), content_scopes=("wiki",)),))
    indexer = VectorIndexer(
        chunk_store=ChunkStore((chunk(vault_id="second"),)),
        vector_store=vector_store,
        text_embeddings=DeterministicTextEmbeddings(SPEC),
    )

    result = indexer.apply(scopes=(QueryScope(vault_ids=("second",), content_scopes=("wiki",)),))
    manifest = vector_store.export_manifest(QueryScope(vault_ids=("first", "second"), content_scopes=("wiki",)))

    assert result.tombstone_count == 0
    assert sorted(row.vault_id for row in manifest) == ["first", "second"]
```

- [ ] **Step 2: Run tests and verify failure**

Run:

```bash
uv run --python 3.12 pytest tests/test_vector_indexer.py -q
```

Expected: FAIL because `VectorIndexer` does not exist.

- [ ] **Step 3: Implement vector indexer dataclasses and planning**

Create `src/vault_graph/indexing/vector_indexer.py` with:

```python
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import PurePosixPath
from typing import Protocol

from vault_graph.embeddings.text_embeddings import EmbeddingInput, EmbeddingModelSpec, TextEmbeddings
from vault_graph.ingestion.document_normalizer import ChunkSnapshot, stable_id
from vault_graph.ingestion.vault_catalog import QueryScope
from vault_graph.storage.interfaces.vector_store import (
    VectorEmbeddingRecord,
    VectorManifestRecord,
    VectorStore,
    VectorTombstone,
)


class ChunkListingStore(Protocol):
    def list_chunks(self, scope: QueryScope) -> tuple[ChunkSnapshot, ...]:
        pass


@dataclass(frozen=True)
class VectorRevisionPlan:
    vector_index_revision: str
    mode: str
    scopes: tuple[QueryScope, ...]
    embedding_spec: EmbeddingModelSpec
    embedding_batch_size: int
    embedding_parallelism: int | None
    embedding_lazy_load: bool
    upsert_chunks: tuple[ChunkSnapshot, ...]
    tombstones: tuple[VectorTombstone, ...]
    unchanged_count: int
    warnings: tuple[str, ...]

    @property
    def upsert_count(self) -> int:
        return len(self.upsert_chunks)

    @property
    def tombstone_count(self) -> int:
        return len(self.tombstones)

    @property
    def embedding_count(self) -> int:
        return len(self.upsert_chunks)
```

Add `VectorApplyResult` with the same counts plus `failed: bool` and `error: str | None`.

Implement `VectorIndexer` with a narrow chunk-listing dependency:

```python
class VectorIndexer:
    def __init__(
        self,
        *,
        chunk_store: ChunkListingStore,
        vector_store: VectorStore,
        text_embeddings: TextEmbeddings,
        embedding_batch_size: int = 256,
        embedding_parallelism: int | None = None,
        embedding_lazy_load: bool = True,
    ) -> None:
        self._chunk_store = chunk_store
        self._vector_store = vector_store
        self._text_embeddings = text_embeddings
        self._embedding_batch_size = embedding_batch_size
        self._embedding_parallelism = embedding_parallelism
        self._embedding_lazy_load = embedding_lazy_load
```

Planning rules:

- desired vector ID: `stable_id("vector", vault_id, chunk_id, model_spec_key)`
- content scope: parent directory of `ChunkSnapshot.path`
- upsert when no current row exists under current spec
- upsert when source chunk hash, chunker version, metadata revision, embedding spec, or backend schema version differs
- tombstone current rows in selected scope with no desired chunk
- tombstone old-model rows for the same `(vault_id, chunk_id)`
- do not use `vector_index_revision` as a staleness comparison key
- depend on `ChunkListingStore`, not the full `MetadataStore`, so tests and
  dry-run previews can supply only the chunk-listing boundary
- read `backend_schema_version` from `VectorStore.health().schema_version`; the
  indexer must not hard-code Chroma schema constants

- [ ] **Step 4: Implement apply with batching**

Implement `VectorIndexer.apply(...)`:

```python
def apply(self, *, scopes: tuple[QueryScope, ...], full: bool = False) -> VectorApplyResult:
    plan = self.plan(scopes=scopes, full=full)
    try:
        embeddings = self._embed_chunks(plan.upsert_chunks)
        records = tuple(self._record_for_chunk(plan, chunk, embeddings[chunk.chunk_id]) for chunk in plan.upsert_chunks)
        self._vector_store.apply_vector_revision(
            vector_index_revision=plan.vector_index_revision,
            records=records,
            tombstones=plan.tombstones,
        )
        return VectorApplyResult.from_plan(plan, failed=False, error=None)
    except Exception as exc:
        return VectorApplyResult.from_plan(plan, failed=True, error=str(exc))
```

`_embed_chunks(...)` must:

- create `EmbeddingInput(input_id=chunk.chunk_id, text=chunk.text)`
- reject duplicate chunk IDs before calling `TextEmbeddings.embed(...)`
- send batches of size `embedding_batch_size`
- bind each returned `EmbeddingVector.input_id` back to the original chunk
- raise if an output is missing, extra, or uses a different model spec

- [ ] **Step 5: Run vector indexer tests**

Run:

```bash
uv run --python 3.12 pytest tests/test_vector_indexer.py tests/test_vector_store_contract.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/vault_graph/indexing/vector_indexer.py tests/test_vector_indexer.py
git commit -m "feat: reconcile vector index from metadata chunks"
```

## Task 6: Status Store And Service Wiring

**Files:**

- Create: `src/vault_graph/storage/local/vector_status_store.py`
- Modify: `src/vault_graph/app/catalog_service.py`
- Modify: `src/vault_graph/app/index_service.py`
- Create: `tests/test_index_service_vector_reconcile.py`

- [ ] **Step 1: Write failing service tests**

Create `tests/test_index_service_vector_reconcile.py`:

```python
from pathlib import Path

from tests.fakes.deterministic_text_embeddings import DeterministicTextEmbeddings
from tests.fakes.in_memory_vector_store import InMemoryVectorStore
from tests.test_vector_indexer import SPEC
from tests.test_vector_store_contract import make_record
from vault_graph.app.index_service import IndexService
from vault_graph.ingestion.vault_catalog import VaultCatalog, VaultCatalogEntry
from vault_graph.storage.local.sqlite_metadata_store import SQLiteMetadataStore
from vault_graph.storage.local.vector_status_store import (
    LocalVectorStatusStore,
    embedding_spec_key,
    scope_key_for_status,
)


def write_page(root: Path, path: str, body: str) -> None:
    file_path = root / path
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(body, encoding="utf-8")


def test_index_service_applies_metadata_then_vector(tmp_path: Path) -> None:
    vault_root = tmp_path / "vault"
    write_page(vault_root, "wiki/page.md", "# Page\nBody\n")
    catalog = VaultCatalog.from_entries(
        entries=[VaultCatalogEntry.from_root(vault_id="default", root_path=vault_root)],
        active_vault_id="default",
    )
    metadata_store = SQLiteMetadataStore(tmp_path / "state" / "metadata.sqlite3", initialize=True)
    vector_store = InMemoryVectorStore()
    status_store = LocalVectorStatusStore(tmp_path / "state" / "vector" / "status.json")
    service = IndexService(
        catalog=catalog,
        metadata_store=metadata_store,
        vector_store=vector_store,
        text_embeddings=DeterministicTextEmbeddings(SPEC),
        vector_status_store=status_store,
    )

    scope = catalog.default_scope()
    report = service.run_apply(scope=scope)
    status = status_store.read(scope_key=scope_key_for_status(scope), embedding_spec_key=embedding_spec_key(SPEC))

    assert report.metadata.index_revision.startswith("metadata-")
    assert report.vector is not None
    assert report.vector.failed is False
    assert vector_store.export_manifest(catalog.default_scope())
    assert status.last_error is None


def test_index_service_records_vector_failure_after_metadata_success(tmp_path: Path) -> None:
    class FailingEmbeddings(DeterministicTextEmbeddings):
        def embed(self, inputs):
            raise RuntimeError("model unavailable")

    vault_root = tmp_path / "vault"
    write_page(vault_root, "wiki/page.md", "# Page\nBody\n")
    catalog = VaultCatalog.from_entries(
        entries=[VaultCatalogEntry.from_root(vault_id="default", root_path=vault_root)],
        active_vault_id="default",
    )
    metadata_store = SQLiteMetadataStore(tmp_path / "state" / "metadata.sqlite3", initialize=True)
    status_store = LocalVectorStatusStore(tmp_path / "state" / "vector" / "status.json")
    service = IndexService(
        catalog=catalog,
        metadata_store=metadata_store,
        vector_store=InMemoryVectorStore(),
        text_embeddings=FailingEmbeddings(SPEC),
        vector_status_store=status_store,
    )

    scope = catalog.default_scope()
    report = service.run_apply(scope=scope)
    status = status_store.read(scope_key=scope_key_for_status(scope), embedding_spec_key=embedding_spec_key(SPEC))

    assert report.metadata.index_revision.startswith("metadata-")
    assert report.vector is not None
    assert report.vector.failed is True
    assert "model unavailable" in (status.last_error or "")


def test_index_service_successful_retry_clears_vector_error(tmp_path: Path) -> None:
    class FailingEmbeddings(DeterministicTextEmbeddings):
        def embed(self, inputs):
            raise RuntimeError("model unavailable")

    vault_root = tmp_path / "vault"
    write_page(vault_root, "wiki/page.md", "# Page\nBody\n")
    catalog = VaultCatalog.from_entries(
        entries=[VaultCatalogEntry.from_root(vault_id="default", root_path=vault_root)],
        active_vault_id="default",
    )
    metadata_store = SQLiteMetadataStore(tmp_path / "state" / "metadata.sqlite3", initialize=True)
    vector_store = InMemoryVectorStore()
    status_store = LocalVectorStatusStore(tmp_path / "state" / "vector" / "status.json")
    scope = catalog.default_scope()
    failing = IndexService(
        catalog=catalog,
        metadata_store=metadata_store,
        vector_store=vector_store,
        text_embeddings=FailingEmbeddings(SPEC),
        vector_status_store=status_store,
    )
    failing.run_apply(scope=scope)
    succeeding = IndexService(
        catalog=catalog,
        metadata_store=metadata_store,
        vector_store=vector_store,
        text_embeddings=DeterministicTextEmbeddings(SPEC),
        vector_status_store=status_store,
    )

    report = succeeding.run_apply(scope=scope)
    status = status_store.read(scope_key=scope_key_for_status(scope), embedding_spec_key=embedding_spec_key(SPEC))

    assert report.vector is not None
    assert report.vector.failed is False
    assert status.last_error is None


def test_index_service_uses_per_vault_actual_scopes_for_vector_reconcile(tmp_path: Path) -> None:
    first_root = tmp_path / "first"
    second_root = tmp_path / "second"
    write_page(first_root, "wiki/page.md", "# First\nBody\n")
    write_page(second_root, "docs/page.md", "# Second\nBody\n")
    catalog = VaultCatalog.from_entries(
        entries=[
            VaultCatalogEntry.from_root(vault_id="first", root_path=first_root, content_scopes=("wiki",)),
            VaultCatalogEntry.from_root(vault_id="second", root_path=second_root, content_scopes=("docs",)),
        ],
        active_vault_id="first",
    )
    metadata_store = SQLiteMetadataStore(tmp_path / "state" / "metadata.sqlite3", initialize=True)
    vector_store = InMemoryVectorStore()
    outside_first_scope = make_record(vault_id="first", path="docs/old.md", text="old", content_scope="docs")
    vector_store.apply_vector_revision(vector_index_revision="vector-old", records=(outside_first_scope,), tombstones=())
    service = IndexService(
        catalog=catalog,
        metadata_store=metadata_store,
        vector_store=vector_store,
        text_embeddings=DeterministicTextEmbeddings(SPEC),
        vector_status_store=LocalVectorStatusStore(tmp_path / "state" / "vector" / "status.json"),
    )

    service.run_apply(scope=catalog.scope_for_all_enabled())
    manifest = vector_store.export_manifest(catalog.scope_for_all_enabled())

    assert ("first", outside_first_scope.chunk_id) in tuple((row.vault_id, row.chunk_id) for row in manifest)
```

- [ ] **Step 2: Run service tests and verify failure**

Run:

```bash
uv run --python 3.12 pytest tests/test_index_service_vector_reconcile.py -q
```

Expected: FAIL because `IndexService` does not accept vector dependencies and `LocalVectorStatusStore` does not exist.

- [ ] **Step 3: Add vector paths to CatalogService**

Modify `src/vault_graph/app/catalog_service.py`:

```python
def __init__(self, *, state_path: Path, embedding_cache_path: Path | None = None) -> None:
    self.state_path = state_path.expanduser().resolve()
    self.config_path = self.state_path / "configs" / "vaults.yaml"
    self.metadata_path = self.state_path / "metadata" / "metadata.sqlite3"
    self.vector_path = self.state_path / "vector" / "chroma"
    self.vector_status_path = self.state_path / "vector" / "status.json"
    self.embedding_cache_path = (
        embedding_cache_path.expanduser().resolve()
        if embedding_cache_path is not None
        else Path("~/.cache/vault-graph/embeddings").expanduser().resolve()
    )
```

Before vector writes, call:

```python
config.assert_write_target_safe(target_path=config.vector_path, catalog=catalog)
config.assert_write_target_safe(target_path=config.vector_status_path, catalog=catalog)
config.assert_cache_target_safe(target_path=config.embedding_cache_path, catalog=catalog)
```

The cache path is allowed outside `state_path` only if it is also outside
registered Vault roots. Do not call `assert_write_target_safe(...)` for
embedding caches, because that helper intentionally requires targets to be under
the Vault Graph state path.

- [ ] **Step 4: Implement status store**

Create `src/vault_graph/storage/local/vector_status_store.py`:

```python
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

from vault_graph.embeddings.text_embeddings import EmbeddingModelSpec
from vault_graph.ingestion.vault_catalog import QueryScope


@dataclass(frozen=True)
class VectorRunStatus:
    scope_key: str
    embedding_spec_key: str
    last_success_revision: str | None = None
    last_success_at: str | None = None
    last_error: str | None = None
    last_error_at: str | None = None


class LocalVectorStatusStore:
    def __init__(self, path: Path) -> None:
        self._path = path.expanduser().resolve()

    def read(self, *, scope_key: str, embedding_spec_key: str) -> VectorRunStatus:
        if not self._path.exists():
            return VectorRunStatus(scope_key=scope_key, embedding_spec_key=embedding_spec_key)
        loaded = json.loads(self._path.read_text(encoding="utf-8"))
        payload = loaded.get("runs", {}).get(_run_key(scope_key=scope_key, embedding_spec_key=embedding_spec_key), {})
        return VectorRunStatus(
            scope_key=scope_key,
            embedding_spec_key=embedding_spec_key,
            last_success_revision=payload.get("last_success_revision"),
            last_success_at=payload.get("last_success_at"),
            last_error=payload.get("last_error"),
            last_error_at=payload.get("last_error_at"),
        )

    def record_success(self, *, scope_key: str, embedding_spec_key: str, vector_index_revision: str) -> None:
        now = datetime.now(UTC).isoformat()
        self._write_run(
            VectorRunStatus(
                scope_key=scope_key,
                embedding_spec_key=embedding_spec_key,
                last_success_revision=vector_index_revision,
                last_success_at=now,
                last_error=None,
                last_error_at=None,
            )
        )

    def record_failure(self, *, scope_key: str, embedding_spec_key: str, error: str) -> None:
        current = self.read(scope_key=scope_key, embedding_spec_key=embedding_spec_key)
        self._write_run(
            VectorRunStatus(
                scope_key=scope_key,
                embedding_spec_key=embedding_spec_key,
                last_success_revision=current.last_success_revision,
                last_success_at=current.last_success_at,
                last_error=error,
                last_error_at=datetime.now(UTC).isoformat(),
            )
        )

    def _write_run(self, status: VectorRunStatus) -> None:
        loaded = json.loads(self._path.read_text(encoding="utf-8")) if self._path.exists() else {"runs": {}}
        loaded.setdefault("runs", {})[
            _run_key(scope_key=status.scope_key, embedding_spec_key=status.embedding_spec_key)
        ] = asdict(status)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(json.dumps(loaded, sort_keys=True, indent=2), encoding="utf-8")


def embedding_spec_key(spec: EmbeddingModelSpec) -> str:
    return "|".join((spec.model_name, spec.model_version, str(spec.dimensions), spec.spec_version))


def scope_key_for_status(scope: QueryScope) -> str:
    return f"{','.join(scope.vault_ids)}:{','.join(scope.content_scopes)}"


def _run_key(*, scope_key: str, embedding_spec_key: str) -> str:
    return f"{scope_key}|{embedding_spec_key}"
```

- [ ] **Step 5: Wire IndexService**

Modify `IndexService.__init__` to accept optional vector dependencies:

```python
def __init__(
    self,
    *,
    catalog: VaultCatalog,
    metadata_store: MetadataStore,
    vector_store: VectorStore | None = None,
    text_embeddings: TextEmbeddings | None = None,
    vector_status_store: LocalVectorStatusStore | None = None,
) -> None:
    self._catalog = catalog
    self._metadata_store = metadata_store
    self._vector_store = vector_store
    self._text_embeddings = text_embeddings
    self._vector_status_store = vector_status_store
```

Keep the existing `plan(...)` and `apply(...)` methods returning
`MetadataRevisionPlan` so Phase 1 CLI callers and tests do not break before CLI
wiring changes. Add new Phase 2B methods `run_plan(...)` and `run_apply(...)`
that return `IndexRunReport`:

```python
@dataclass(frozen=True)
class IndexRunReport:
    metadata: MetadataRevisionPlan
    vector: VectorRevisionPlan | VectorApplyResult | None

    @property
    def exit_code(self) -> int:
        return 1 if getattr(self.vector, "failed", False) else 0
```

Rules:

- `run_plan(...)` must call `MetadataIndexer.preview(...)`, wrap
  `preview.chunks_after_apply` in a chunk-listing preview store, and pass that
  store to `VectorIndexer.plan(...)`.
- `run_apply(...)` must call `MetadataIndexer.apply(...)` first and
  `VectorIndexer.apply(...)` second.
- Existing `plan(...)` and `apply(...)` remain metadata-only compatibility
  methods until a later cleanup explicitly removes them.
- Both `run_plan(...)` and `run_apply(...)` must resolve the requested
  `QueryScope` into per-Vault actual vector scopes before vector reconcile.
- On vector failure, record failure in `LocalVectorStatusStore` and return `exit_code == 1`.
- On vector success, record success.
- If vector dependencies are not provided, preserve old metadata-only behavior for focused tests that construct `IndexService` directly.

Use this private preview store in `src/vault_graph/app/index_service.py`:

```python
class _PreviewChunkStore:
    def __init__(self, chunks: tuple[ChunkSnapshot, ...]) -> None:
        self._chunks = chunks

    def list_chunks(self, scope: QueryScope) -> tuple[ChunkSnapshot, ...]:
        return tuple(
            chunk
            for chunk in self._chunks
            if chunk.vault_id in scope.vault_ids
            and any(chunk.path == content_scope or chunk.path.startswith(f"{content_scope}/") for content_scope in scope.content_scopes)
        )
```

Add this private actual-scope helper in `src/vault_graph/app/index_service.py`:

```python
def _actual_vector_scopes(*, catalog: VaultCatalog, scope: QueryScope) -> tuple[QueryScope, ...]:
    actual_scopes: list[QueryScope] = []
    for vault_id in scope.vault_ids:
        entry = catalog.resolve(vault_id)
        content_scopes: list[str] = []
        for query_scope in scope.content_scopes:
            for entry_scope in entry.content_scopes:
                if _is_same_or_child(path=query_scope, parent=entry_scope):
                    content_scopes.append(query_scope)
                elif _is_same_or_child(path=entry_scope, parent=query_scope):
                    content_scopes.append(entry_scope)
        deduped = tuple(dict.fromkeys(content_scopes))
        if deduped:
            actual_scopes.append(
                QueryScope(
                    vault_ids=(entry.vault_id,),
                    content_scopes=deduped,
                    include_cross_vault=scope.include_cross_vault,
                )
            )
    return tuple(actual_scopes)


def _is_same_or_child(*, path: str, parent: str) -> bool:
    return path == parent or path.startswith(f"{parent}/")
```

`IndexService.run_plan(...)` must instantiate `VectorIndexer` with
`chunk_store=_PreviewChunkStore(preview.chunks_after_apply)`. `IndexService.run_apply(...)`
must instantiate `VectorIndexer` with `chunk_store=self._metadata_store` after
metadata apply succeeds, because the SQLite metadata projection then contains
the committed chunk state. Both methods must pass
`scopes=_actual_vector_scopes(catalog=self._catalog, scope=scope)` to the
vector indexer.

When recording vector status, use:

```python
scope_key = scope_key_for_status(scope)
spec_key = embedding_spec_key(self._text_embeddings.model_spec())
```

and pass those keys to `record_success(...)`, `record_failure(...)`, and
`read(...)`. Status records must never be global across all Vaults.

Extend `StatusReport` with vector fields and make `IndexService.status(...)`
accept a resolved `scope: QueryScope`:

```python
@dataclass(frozen=True)
class StatusReport:
    active_vault_id: str
    vaults: tuple[tuple[str, str], ...]
    metadata_ok: bool
    metadata_schema_compatible: bool
    metadata_message: str
    vector_ok: bool
    vector_backend: str
    vector_schema_compatible: bool
    vector_message: str
    embedding_model: str
    embedding_model_version: str
    embedding_dimensions: int
    embedding_spec_version: str
    embedding_batch_size: int
    embedding_parallelism: int | None
    embedding_lazy_load: bool
    vector_revision: str | None
    vector_stale_count: int
    vector_last_error: str | None
    vector_status_scope: str
```

`vector_stale_count` should be computed by running vector plan against the
selected scope and counting planned upserts plus tombstones. If vector backend
is missing or incompatible, return a clear vector message and do not create
vector state.

- [ ] **Step 6: Run service tests**

Run:

```bash
uv run --python 3.12 pytest tests/test_index_service_vector_reconcile.py tests/test_metadata_indexer.py -q
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add src/vault_graph/app/catalog_service.py src/vault_graph/app/index_service.py src/vault_graph/storage/local/vector_status_store.py tests/test_index_service_vector_reconcile.py
git commit -m "feat: wire vector indexing through index service"
```

## Task 7: CLI Index And Status

**Files:**

- Modify: `src/vault_graph/cli/main.py`
- Create: `tests/test_cli_vector_indexing.py`
- Modify: `tests/test_cli_catalog_metadata.py`

- [ ] **Step 1: Write failing CLI tests**

Create `tests/test_cli_vector_indexing.py`:

```python
from pathlib import Path

from typer.testing import CliRunner

from vault_graph.app.catalog_service import CatalogService
from vault_graph.cli.main import app
from vault_graph.errors import ReadOnlyBoundaryError

runner = CliRunner()


def write_page(root: Path, path: str, body: str) -> None:
    file_path = root / path
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(body, encoding="utf-8")


def test_cli_index_dry_run_reports_vector_plan_without_writes(tmp_path: Path) -> None:
    vault_root = tmp_path / "vault"
    write_page(vault_root, "wiki/page.md", "# Page\nBody\n")
    state_path = tmp_path / "state"
    runner.invoke(app, ["init", "--vault", str(vault_root), "--state", str(state_path)])

    result = runner.invoke(app, ["index", "--state", str(state_path), "--dry-run"])

    assert result.exit_code == 0
    assert "vector_mode: incremental" in result.stdout
    assert "vector_upserts: 1" in result.stdout
    assert "embedding_batch_size: 256" in result.stdout
    assert not (state_path / "metadata").exists()
    assert not (state_path / "vector").exists()


def test_cli_status_reports_vector_fields(tmp_path: Path) -> None:
    vault_root = tmp_path / "vault"
    vault_root.mkdir()
    state_path = tmp_path / "state"
    runner.invoke(app, ["init", "--vault", str(vault_root), "--state", str(state_path)])

    result = runner.invoke(app, ["status", "--state", str(state_path)])

    assert result.exit_code == 0
    assert "vector_ok:" in result.stdout
    assert "vector_backend: chroma" in result.stdout
    assert "embedding_model: sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2" in result.stdout
    assert "embedding_dimensions: 384" in result.stdout
    assert "vector_status_scope: default:raw,wiki,docs,scratch/reports" in result.stdout


def test_cli_status_supports_vault_scope_flags(tmp_path: Path) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"
    first.mkdir()
    second.mkdir()
    state_path = tmp_path / "state"
    runner.invoke(app, ["init", "--vault-id", "first", "--vault", str(first), "--state", str(state_path)])
    runner.invoke(app, ["vault", "add", "second", "--path", str(second), "--state", str(state_path)])

    one = runner.invoke(app, ["status", "--state", str(state_path), "--vault-id", "second"])
    all_vaults = runner.invoke(app, ["status", "--state", str(state_path), "--all-vaults"])

    assert one.exit_code == 0
    assert "vector_status_scope: second:" in one.stdout
    assert all_vaults.exit_code == 0
    assert "vector_status_scope: first,second:" in all_vaults.stdout
```

- [ ] **Step 2: Run CLI tests and verify failure**

Run:

```bash
uv run --python 3.12 pytest tests/test_cli_vector_indexing.py -q
```

Expected: FAIL because CLI does not wire vector dependencies or status flags.

- [ ] **Step 3: Wire production defaults**

Modify `_service(...)` in `src/vault_graph/cli/main.py` so non-dry-run indexing constructs:

```python
vector_store = ChromaVectorStore(config.vector_path, initialize=initialize_store)
text_embeddings = FastEmbedTextEmbeddings(
    config=FastEmbedTextEmbeddingsConfig(cache_dir=config.embedding_cache_path)
)
vector_status_store = LocalVectorStatusStore(config.vector_status_path)
```

Before non-dry-run vector writes, assert:

```python
config.assert_write_target_safe(target_path=config.vector_path, catalog=catalog)
config.assert_write_target_safe(target_path=config.vector_status_path, catalog=catalog)
config.assert_cache_target_safe(target_path=config.embedding_cache_path, catalog=catalog)
```

For `--dry-run`, construct `ChromaVectorStore(config.vector_path, initialize=False)` and `FastEmbedTextEmbeddings(...)` but do not call `embed(...)`.

In `index(...)`, call:

```python
report = service.run_plan(scope=scope, full=full) if dry_run else service.run_apply(scope=scope, full=full)
```

Do not call the metadata-only compatibility methods `service.plan(...)` or
`service.apply(...)` from CLI after Phase 2B wiring.

- [ ] **Step 4: Update `vg index` output**

Print:

```text
vector_mode: incremental
vector_revision: vector-20260608123000000000
vector_upserts: N
vector_tombstones: N
vector_unchanged: N
vector_stale: N
embedding_model: sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2
embedding_model_version: faf4aa4225822f3bc6376869cb1164e8e3feedd0
embedding_dimensions: 384
embedding_spec_version: fastembed-multilingual-minilm-l12-v2-cosine-v1
embedding_batch_size: 256
embedding_parallelism: None
embedding_lazy_load: True
```

If vector apply fails after metadata apply:

- print metadata fields
- print `vector_failed: True`
- print `vector_last_error: model unavailable`
- exit with code `1`

- [ ] **Step 5: Update `vg status` scope flags and output**

Add to `status(...)`:

```python
vault_id: str | None = typer.Option(None, "--vault-id", help="Report one registered Vault ID.")
all_vaults: bool = typer.Option(False, "--all-vaults", help="Report all enabled registered Vaults.")
```

Use the same conflict handling as `index(...)`.

Call `service.status(scope=scope)` after resolving the same active-vault,
`--vault-id`, or `--all-vaults` selection. The status implementation must read
the vector run status using `scope_key_for_status(scope)` and the active
embedding spec key, so status fields match the selected scope.

Print minimum Phase 2B vector fields:

```text
vector_ok: False
vector_backend: chroma
vector_schema_compatible: False
vector_message: not initialized
embedding_model: sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2
embedding_model_version: faf4aa4225822f3bc6376869cb1164e8e3feedd0
embedding_dimensions: 384
embedding_spec_version: fastembed-multilingual-minilm-l12-v2-cosine-v1
embedding_batch_size: 256
embedding_parallelism: None
embedding_lazy_load: True
vector_revision: None
vector_stale_count: 0
vector_last_error: None
vector_status_scope: default:raw,wiki,docs,scratch/reports
```

- [ ] **Step 6: Run CLI tests**

Run:

```bash
uv run --python 3.12 pytest tests/test_cli_vector_indexing.py tests/test_cli_catalog_metadata.py -q
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add src/vault_graph/cli/main.py tests/test_cli_vector_indexing.py tests/test_cli_catalog_metadata.py
git commit -m "feat: expose phase 2b vector index status"
```

## Task 8: Read-Only Boundary And Failure Recovery

**Files:**

- Modify: `src/vault_graph/app/path_guard.py`
- Modify: `src/vault_graph/app/catalog_service.py`
- Create: `tests/test_vector_indexing_read_only_boundary.py`
- Modify: `tests/test_read_only_boundary.py`

- [ ] **Step 1: Write failing read-only and recovery tests**

Create `tests/test_vector_indexing_read_only_boundary.py`:

```python
from pathlib import Path

from typer.testing import CliRunner

from vault_graph.cli.main import app

runner = CliRunner()


def test_vector_state_path_cannot_be_inside_vault_root(tmp_path: Path) -> None:
    vault_root = tmp_path / "vault"
    vault_root.mkdir()
    state_path = vault_root / ".vault-graph"

    result = runner.invoke(app, ["init", "--vault", str(vault_root), "--state", str(state_path)])

    assert result.exit_code != 0
    assert "state path must not be inside a registered Vault" in result.stdout


def test_dry_run_does_not_create_vector_or_metadata_state(tmp_path: Path) -> None:
    vault_root = tmp_path / "vault"
    (vault_root / "wiki").mkdir(parents=True)
    (vault_root / "wiki" / "page.md").write_text("# Page\nBody\n", encoding="utf-8")
    state_path = tmp_path / "state"
    runner.invoke(app, ["init", "--vault", str(vault_root), "--state", str(state_path)])

    result = runner.invoke(app, ["index", "--state", str(state_path), "--dry-run"])

    assert result.exit_code == 0
    assert not (state_path / "metadata").exists()
    assert not (state_path / "vector").exists()
    assert (vault_root / "wiki" / "page.md").read_text(encoding="utf-8") == "# Page\nBody\n"


def test_vector_indexing_slice_does_not_expose_search_command() -> None:
    result = runner.invoke(app, ["search", "query"])

    assert result.exit_code != 0
    assert "No such command" in result.output


def test_embedding_cache_path_cannot_be_inside_vault_root(tmp_path: Path) -> None:
    vault_root = tmp_path / "vault"
    vault_root.mkdir()
    config = CatalogService(
        state_path=tmp_path / "state",
        embedding_cache_path=vault_root / ".cache" / "vault-graph" / "embeddings",
    )
    catalog = config.create_default_catalog(vault_root=vault_root)

    try:
        config.assert_cache_target_safe(target_path=config.embedding_cache_path, catalog=catalog)
    except ReadOnlyBoundaryError as exc:
        assert "must not be inside a registered Vault" in str(exc)
    else:
        raise AssertionError("cache path inside a Vault root should fail")
```

- [ ] **Step 2: Run tests and verify failure if guards are incomplete**

Run:

```bash
uv run --python 3.12 pytest tests/test_vector_indexing_read_only_boundary.py tests/test_read_only_boundary.py -q
```

Expected: PASS after Task 7 guard wiring. If it fails, fix only the guard path causing the failure.

- [ ] **Step 3: Add cache guard**

Add:

```python
def assert_target_outside_vaults(*, target_path: Path, vault_roots: Iterable[Path]) -> None:
    resolved_target = target_path.expanduser().resolve(strict=False)
    for vault_root in vault_roots:
        resolved_vault = vault_root.expanduser().resolve()
        if resolved_target == resolved_vault or resolved_vault in resolved_target.parents:
            raise ReadOnlyBoundaryError(
                f"Vault Graph target path must not be inside a registered Vault: {resolved_target}"
            )
```

Then add `CatalogService.assert_cache_target_safe(...)` that calls it.

- [ ] **Step 4: Run read-only tests**

Run:

```bash
uv run --python 3.12 pytest tests/test_vector_indexing_read_only_boundary.py tests/test_read_only_boundary.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/vault_graph/app/path_guard.py src/vault_graph/app/catalog_service.py tests/test_vector_indexing_read_only_boundary.py tests/test_read_only_boundary.py
git commit -m "test: guard phase 2b vector read only boundary"
```

## Task 9: End-To-End Verification And Documentation Sync

**Files:**

- Modify only if needed: `docs/PATCH_LOG.md`
- Modify only if needed: `docs/DECISIONS.md`
- Modify only if needed: `README.md`

- [ ] **Step 1: Run the full verification suite**

Run:

```bash
uv run --python 3.12 pytest -q
uv run --python 3.12 ruff check src tests
uv run --python 3.12 mypy src
uv run --python 3.12 mypy tests
git diff --check
```

Expected:

- pytest passes
- ruff passes
- mypy passes for `src`
- mypy passes for `tests`
- `git diff --check` prints no whitespace errors

- [ ] **Step 2: Run a local CLI smoke test**

Run:

```bash
tmpdir="$(mktemp -d)"
mkdir -p "$tmpdir/vault/wiki"
printf '# Page\nBody\n' > "$tmpdir/vault/wiki/page.md"
uv run --python 3.12 vg init --vault "$tmpdir/vault" --state "$tmpdir/state"
uv run --python 3.12 vg index --state "$tmpdir/state" --dry-run
uv run --python 3.12 vg status --state "$tmpdir/state"
```

Expected:

- init prints `initialized vault_id: default`
- dry-run prints `vector_upserts: 1`
- status prints `vector_backend: chroma`
- no files are created under `$tmpdir/vault`

- [ ] **Step 3: Update patch log only for implementation corrections**

If implementation uncovered a correction to the Phase 2B plan or specs, append to `docs/PATCH_LOG.md`:

```markdown
## 2026-06-08 - Phase 2B Implementation Plan Correction

**Trigger:** Phase 2B implementation exposed a mismatch between the design plan
and the existing code or dependency behavior.

**Scope:** Phase 2B local vector indexing implementation plan.

**Correction:** Add concrete bullets describing the exact files, fields, or
runtime behavior that changed.

**Reason:** Explain why the correction preserves the Phase 2B scope and Vault
Graph read-only, rebuildable projection model.
```

Do not add an entry if implementation follows the accepted plan without corrections.

- [ ] **Step 4: Add a decision only if a product or policy choice is required**

If implementation requires changing an accepted product or architecture policy, add a short accepted entry to `docs/DECISIONS.md` only after user approval. Examples that require user approval:

- replacing Chroma as the default local `VectorStore`
- replacing the accepted default embedding model
- allowing network-hosted embedding by default
- allowing `vg search` in Phase 2B
- indexing non-Markdown files in Phase 2B

Implementation details that follow the accepted Phase 2B design belong in `docs/PATCH_LOG.md`, not `docs/DECISIONS.md`.

- [ ] **Step 5: Commit final implementation**

```bash
git add docs/PATCH_LOG.md docs/DECISIONS.md README.md
git commit -m "docs: sync phase 2b implementation notes"
```

Skip this commit if no docs changed.

## Completion Criteria

Phase 2B is complete when all of these are true:

- `chromadb`, `fastembed`, and `huggingface-hub` are default dependencies.
- `FastEmbedTextEmbeddings` is available and uses the accepted multilingual MiniLM model spec.
- `embedding_batch_size`, `embedding_parallelism`, and `embedding_lazy_load` are visible in index/status diagnostics and do not alter `EmbeddingModelSpec`.
- `MetadataStore.list_chunks(scope)` returns current non-tombstoned chunks with text and freshness fields.
- `VectorStore` records and manifests include source chunk hash, chunker version, metadata revision, model spec, backend schema version, backend, and vector revision.
- Chroma persists vectors locally under the Vault Graph state path and is not used through HTTP.
- `VectorIndexer.plan(...)` and `VectorIndexer.apply(...)` converge selected scopes without touching records outside scope.
- Old-model rows are visible through manifest export and tombstoned during model-spec reconcile.
- `vg index` applies metadata then vector by default.
- `vg index --dry-run` reports metadata and vector work without creating metadata state, vector state, Chroma collections, or Vault files.
- `vg status`, `vg status --vault-id ID`, and `vg status --all-vaults` report vector health and scope.
- A vector failure after metadata success returns nonzero from `vg index`, preserves metadata, records vector failure status, and can recover on the next successful index.
- No Vault content is written, renamed, deleted, or rewritten.
- `vg search`, graph traversal, answers, context packs, MCP, and HTTP remain absent from Phase 2B.

## Final Verification Commands

Run before claiming completion:

```bash
uv run --python 3.12 pytest -q
uv run --python 3.12 ruff check src tests
uv run --python 3.12 mypy src
uv run --python 3.12 mypy tests
git diff --check
git status --short --branch
```

Expected final state:

- tests pass
- static checks pass
- no whitespace errors
- worktree contains only intentional Phase 2B implementation changes
