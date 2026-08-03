# Round 0-G Authority And Projection Hygiene Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Vault Graph store each distinct chunk plaintext once, search canonical knowledge without provenance-family repetition, expose verifiable hygiene metrics, and rebuild incompatible projections transactionally.

**Architecture:** Add authority role and provenance family identity at ingestion, then carry those identities through metadata, keyword, vector, graph, and retrieval contracts. SQLite metadata owns canonical content blobs; FTS, Chroma, and graph rows own references only. Full rebuilds use an isolated projection generation and switch one active manifest only after validation.

**Tech Stack:** Python 3.12+, dataclasses, SQLite/FTS5, Chroma, Typer, MCP Python SDK, pytest, Ruff, mypy.

## Global Constraints

- Vault remains read-only and authoritative for durable knowledge.
- All Vault Graph state is rebuildable and non-authoritative.
- No Round 1 code repository registration, parsing, or indexing is included.
- Existing Vault-scoped identities and application-service boundaries remain intact.
- Every behavior change follows RED, GREEN, REFACTOR and receives focused verification before commit.

---

## File Structure

- `src/vault_graph/ingestion/document_authority.py`: pure role classification and provenance-family construction.
- `src/vault_graph/ingestion/document_normalizer.py`: carries role/family on document and chunk DTOs.
- `src/vault_graph/storage/local/sqlite_metadata_store.py`: metadata-v2 canonical blob ownership.
- `src/vault_graph/storage/local/sqlite_keyword_index.py`: contentless FTS plus reference rows.
- `src/vault_graph/storage/interfaces/{keyword_index,vector_store}.py`: role/family candidate contracts.
- `src/vault_graph/storage/local/chroma_vector_store.py`: role-aware metadata-only vectors.
- `src/vault_graph/graph/graph_contracts.py` and `src/vault_graph/storage/local/sqlite_graph_store.py`: excerpt-free graph evidence.
- `src/vault_graph/retrieval/{retrieval_result,search_response,retrieval_service}.py`: mode policy, family collapse, and reference attachment.
- `src/vault_graph/app/projection_hygiene_service.py`: read-only completion metrics.
- `src/vault_graph/app/projection_generation.py`: safe generation staging and atomic activation.
- `src/vault_graph/app/{catalog_service,local_index_service_factory}.py`: active-generation path resolution and transactional full rebuild composition.
- `src/vault_graph/cli/main.py` and `src/vault_graph/mcp/*`: user-facing mode/audit/serialization changes.

### Task 1: Authority Role And Provenance Family Domain

**Files:**

- Create: `src/vault_graph/ingestion/document_authority.py`
- Modify: `src/vault_graph/ingestion/document_normalizer.py`
- Modify: `src/vault_graph/indexing/metadata_indexer.py`
- Test: `tests/test_document_authority.py`
- Test: `tests/test_document_normalizer.py`
- Test: `tests/test_metadata_indexer.py`

**Interfaces:**

- Produces: `DocumentRole`, `classify_document_role(path, frontmatter) -> DocumentRole`
- Produces: `assign_provenance_families(items) -> tuple[NormalizedDocument, ...]`
- Produces: `DocumentSnapshot.source_role`, `DocumentSnapshot.provenance_family_id`
- Produces: matching fields on `ChunkSnapshot`

- [ ] **Step 1: Write failing role tests**

```python
@pytest.mark.parametrize(
    ("path", "frontmatter", "expected"),
    [
        ("raw/source.md", {}, "raw_evidence"),
        ("wiki/sources/source.md", {"type": "source"}, "source_manifest"),
        ("wiki/index.md", {"type": "index"}, "generated_view"),
        ("wiki/maps/topic-map.md", {"type": "map", "generated_by": "tools/wiki/cli.py"}, "generated_view"),
        ("wiki/log.md", {"type": "log"}, "operation_log"),
        ("docs/usage.md", {}, "operating_contract"),
        ("scratch/reports/audit.md", {}, "audit_record"),
        ("wiki/concepts/topic.md", {"type": "concept"}, "canonical_knowledge"),
    ],
)
def test_classify_document_role(path: str, frontmatter: dict[str, object], expected: str) -> None:
    assert classify_document_role(path=path, frontmatter=frontmatter) == expected
```

- [ ] **Step 2: Run RED**

Run: `uv run pytest tests/test_document_authority.py -q`

Expected: import failure because `document_authority` does not exist.

- [ ] **Step 3: Implement the closed vocabulary and precedence**

```python
DocumentRole = Literal[
    "raw_evidence", "canonical_knowledge", "source_manifest",
    "operating_contract", "generated_view", "operation_log", "audit_record",
]

def classify_document_role(*, path: str, frontmatter: Mapping[str, object]) -> DocumentRole:
    normalized_type = str(frontmatter.get("type") or frontmatter.get("kind") or "").casefold()
    if path.startswith("raw/"):
        return "raw_evidence"
    if path.startswith("scratch/reports/"):
        return "audit_record"
    if path.startswith("docs/"):
        return "operating_contract"
    if path == "wiki/log.md" or normalized_type == "log":
        return "operation_log"
    if path == "wiki/index.md" or path.startswith("wiki/maps/"):
        return "generated_view"
    if path.startswith("wiki/sources/") or normalized_type == "source":
        return "source_manifest"
    return "canonical_knowledge"
```

- [ ] **Step 4: Write failing family tests**

```python
def test_family_connects_raw_manifest_and_durable_pages() -> None:
    items = (
        normalized("raw/sources/a.md"),
        normalized("wiki/sources/a.md", canonical_source="raw/sources/a.md"),
        normalized("wiki/systems/a.md", derived_from=["wiki/sources/a"]),
        normalized("wiki/decisions/a.md", derived_from=["wiki/sources/a"]),
    )
    assigned = assign_provenance_families(items)
    assert len({item.document.provenance_family_id for item in assigned}) == 1
    assert {item.document.source_role for item in assigned} == {
        "raw_evidence", "source_manifest", "canonical_knowledge"
    }
```

- [ ] **Step 5: Run RED, implement union-find family assignment, and run GREEN**

Run: `uv run pytest tests/test_document_authority.py tests/test_document_normalizer.py tests/test_metadata_indexer.py -q`

Implementation requirements:

```python
def assign_provenance_families(items: tuple[NormalizedDocument, ...]) -> tuple[NormalizedDocument, ...]:
    members = _members_by_vault_and_path(items)
    families = _connected_family_roots(members)
    return tuple(_with_family(item, families[(item.document.vault_id, item.document.path)]) for item in items)
```

Expected: all focused tests pass; multi-Vault fixtures never share a family.

- [ ] **Step 6: Commit**

```bash
git add src/vault_graph/ingestion/document_authority.py src/vault_graph/ingestion/document_normalizer.py \
  src/vault_graph/indexing/metadata_indexer.py tests/test_document_authority.py \
  tests/test_document_normalizer.py tests/test_metadata_indexer.py
git commit -m "feat: classify Vault authority families"
```

### Task 2: Canonical Blob Metadata And Contentless Keyword Projection

**Files:**

- Modify: `src/vault_graph/storage/interfaces/metadata_store.py`
- Modify: `src/vault_graph/storage/interfaces/keyword_index.py`
- Modify: `src/vault_graph/storage/local/sqlite_metadata_store.py`
- Modify: `src/vault_graph/storage/local/sqlite_keyword_index.py`
- Test: `tests/test_sqlite_metadata_store.py`
- Test: `tests/test_metadata_chunk_listing.py`
- Test: `tests/test_metadata_evidence_resolution.py`
- Test: `tests/test_sqlite_keyword_index.py`
- Test: `tests/test_keyword_index_contract.py`

**Interfaces:**

- Consumes: role/family fields from Task 1.
- Produces: metadata-v2 tables `content_blobs`, reference-only `chunks`.
- Produces: `KeywordQuery.source_roles`, role/family fields on `KeywordHit`.

- [ ] **Step 1: Write failing single-body tests**

```python
def test_equal_chunk_bodies_share_one_blob_and_keep_two_evidence_rows(tmp_path: Path) -> None:
    store = SQLiteMetadataStore(tmp_path / "metadata.sqlite3", initialize=True)
    first = make_chunk("first", text="same body")
    second = make_chunk("second", text="same body")
    store.apply_metadata_revision(
        index_revision="r1",
        documents=[make_document(first), make_document(second)],
        chunks=[first, second],
        tombstones=[],
    )
    with store.connect_for_tests() as connection:
        assert connection.execute("SELECT COUNT(*) FROM content_blobs").fetchone()[0] == 1
        columns = {row[1] for row in connection.execute("PRAGMA table_info(chunks)")}
    assert "text" not in columns
    assert store.resolve_chunk(vault_id="main", chunk_id=first.chunk_id).text == "same body"
```

- [ ] **Step 2: Run RED**

Run: `uv run pytest tests/test_sqlite_metadata_store.py tests/test_metadata_chunk_listing.py tests/test_metadata_evidence_resolution.py -q`

Expected: missing `content_blobs` and current `chunks.text` assertion failure.

- [ ] **Step 3: Implement metadata-v2**

Use this schema shape and join rule:

```sql
CREATE TABLE content_blobs (
  blob_hash TEXT PRIMARY KEY,
  text TEXT NOT NULL,
  byte_count INTEGER NOT NULL
);
CREATE TABLE chunks (
  vault_id TEXT NOT NULL,
  chunk_id TEXT NOT NULL,
  document_id TEXT NOT NULL,
  path TEXT NOT NULL,
  section TEXT,
  anchor TEXT,
  blob_hash TEXT NOT NULL REFERENCES content_blobs(blob_hash),
  token_count INTEGER NOT NULL,
  content_hash TEXT NOT NULL,
  chunker_version TEXT NOT NULL,
  index_revision TEXT,
  source_role TEXT NOT NULL,
  provenance_family_id TEXT NOT NULL,
  PRIMARY KEY (vault_id, chunk_id)
);
```

All chunk reads select `b.text` through `JOIN content_blobs b ON b.blob_hash = c.blob_hash`.
After replacing/tombstoning chunks, delete blobs for which no chunk exists.

- [ ] **Step 4: Write failing contentless FTS tests**

```python
def test_keyword_projection_has_no_plaintext_columns_and_filters_role_before_limit(tmp_path: Path) -> None:
    path = tmp_path / "metadata.sqlite3"
    seed_keyword_documents(path, roles=("raw_evidence", "canonical_knowledge"), text="alpha")
    hits = SQLiteKeywordIndex(path).search(
        KeywordQuery(query_text="alpha", scope=scope, limit=1, source_roles=("canonical_knowledge",))
    )
    assert hits[0].source_role == "canonical_knowledge"
    with sqlite3.connect(path) as connection:
        sql = connection.execute(
            "SELECT sql FROM sqlite_master WHERE name = 'keyword_chunks'"
        ).fetchone()[0]
        assert "content=''" in sql
        assert connection.execute("SELECT text FROM keyword_chunks").fetchone()[0] is None
```

- [ ] **Step 5: Run RED, implement keyword-v2, and run GREEN**

Run: `uv run pytest tests/test_sqlite_keyword_index.py tests/test_keyword_index_contract.py -q`

Implementation requirements:

```python
@dataclass(frozen=True)
class KeywordQuery:
    query_text: str
    scope: QueryScope
    limit: int
    source_roles: tuple[DocumentRole, ...] = ()

@dataclass(frozen=True)
class KeywordHit:
    ...
    source_role: DocumentRole
    provenance_family_id: str
```

`keyword_rows` owns only IDs, role, family, scope, and revision. Delete FTS rows
before mapping rows. Determine matched fields with row-ID plus column-scoped FTS
queries.

- [ ] **Step 6: Run focused metadata/keyword suite and commit**

Run: `uv run pytest tests/test_sqlite_metadata_store.py tests/test_metadata_chunk_listing.py tests/test_metadata_evidence_resolution.py tests/test_sqlite_keyword_index.py tests/test_keyword_index_contract.py -q`

```bash
git add src/vault_graph/storage/interfaces/metadata_store.py src/vault_graph/storage/interfaces/keyword_index.py \
  src/vault_graph/storage/local/sqlite_metadata_store.py src/vault_graph/storage/local/sqlite_keyword_index.py \
  tests/test_sqlite_metadata_store.py tests/test_metadata_chunk_listing.py \
  tests/test_metadata_evidence_resolution.py tests/test_sqlite_keyword_index.py tests/test_keyword_index_contract.py
git commit -m "feat: store canonical chunk bodies once"
```

### Task 3: Reference-Only Vector And Graph Projections

**Files:**

- Modify: `src/vault_graph/storage/interfaces/vector_store.py`
- Modify: `src/vault_graph/storage/local/chroma_vector_store.py`
- Modify: `src/vault_graph/indexing/vector_indexer.py`
- Modify: `src/vault_graph/graph/graph_contracts.py`
- Modify: `src/vault_graph/extraction/graph_occurrences.py`
- Modify: `src/vault_graph/extraction/entity_extractor.py`
- Modify: `src/vault_graph/extraction/relationship_extractor.py`
- Modify: `src/vault_graph/indexing/graph_indexer.py`
- Modify: `src/vault_graph/storage/local/sqlite_graph_store.py`
- Modify: `src/vault_graph/cli/main.py`
- Modify: `src/vault_graph/mcp/graph_resource_reader.py`
- Test: `tests/test_vector_store_contract.py`
- Test: `tests/test_chroma_vector_store.py`
- Test: `tests/test_graph_contracts.py`
- Test: `tests/test_graph_store_contract.py`
- Test: `tests/test_sqlite_graph_store.py`
- Test: `tests/test_graph_resource_reader.py`

**Interfaces:**

- Consumes: role/family chunk metadata.
- Produces: role-filtered vector candidates without plaintext metadata.
- Produces: excerpt-free `GraphEvidenceRef` and sqlite-graph-v2.

- [ ] **Step 1: Write failing vector policy tests**

```python
def test_vector_metadata_is_reference_only_and_role_filter_runs_before_limit(tmp_path: Path) -> None:
    store, query_vector, embedding_spec = seeded_vector_store(tmp_path)
    hits = store.search(VectorQuery(
        query_vector=query_vector,
        scope=QueryScope(vault_ids=("main",), content_scopes=("raw", "wiki")),
        source_roles=("canonical_knowledge",),
        limit=1,
        embedding_spec=embedding_spec,
    ))
    assert hits[0].source_role == "canonical_knowledge"
    metadata = raw_chroma_metadata(tmp_path)
    assert not ({"text", "document", "excerpt", "summary", "body"} & metadata.keys())
```

- [ ] **Step 2: Run RED and implement vector role/family metadata**

Run: `uv run pytest tests/test_vector_store_contract.py tests/test_chroma_vector_store.py tests/test_vector_indexer.py -q`

Add `source_role` and `provenance_family_id` to embedding, manifest, and hit
records. Add `source_roles` to `VectorQuery`. Include both fields in staleness
comparison and Chroma/read-only SQLite filtering before limiting.

- [ ] **Step 3: Write failing graph excerpt-removal tests**

```python
def test_graph_schema_and_contract_do_not_persist_excerpt(tmp_path: Path) -> None:
    store = SQLiteGraphStore.open_writable(tmp_path / "graph.sqlite3")
    assert "excerpt" not in {row[1] for row in store.connect_for_tests().execute(
        "PRAGMA table_info(graph_evidence_refs)"
    )}
    assert "excerpt" not in GraphEvidenceRef.__dataclass_fields__
```

- [ ] **Step 4: Run RED, remove graph excerpts, and run GREEN**

Run: `uv run pytest tests/test_graph_contracts.py tests/test_graph_store_contract.py tests/test_sqlite_graph_store.py tests/test_graph_resource_reader.py -q`

Remove excerpt creation, persistence, row decoding, upsert fields, and CLI/MCP
serialization. Preserve path/section/anchor and metadata evidence resolution.
Bump graph schema and extraction-spec versions.

- [ ] **Step 5: Commit**

```bash
git add src/vault_graph/storage/interfaces/vector_store.py src/vault_graph/storage/local/chroma_vector_store.py \
  src/vault_graph/indexing/vector_indexer.py src/vault_graph/graph/graph_contracts.py \
  src/vault_graph/extraction src/vault_graph/indexing/graph_indexer.py \
  src/vault_graph/storage/local/sqlite_graph_store.py src/vault_graph/cli/main.py \
  src/vault_graph/mcp/graph_resource_reader.py tests/test_vector_store_contract.py \
  tests/test_chroma_vector_store.py tests/test_graph_contracts.py tests/test_graph_store_contract.py \
  tests/test_sqlite_graph_store.py tests/test_graph_resource_reader.py
git commit -m "feat: make vector and graph projections reference-only"
```

### Task 4: Role-Aware Retrieval And Family Collapse

**Files:**

- Modify: `src/vault_graph/retrieval/retrieval_result.py`
- Modify: `src/vault_graph/retrieval/search_response.py`
- Modify: `src/vault_graph/retrieval/retrieval_service.py`
- Modify: `src/vault_graph/retrieval/retrieval_candidate.py`
- Modify: `src/vault_graph/retrieval/graph_candidates.py`
- Modify: `src/vault_graph/cli/main.py`
- Modify: `src/vault_graph/mcp/mcp_tools.py`
- Modify: `src/vault_graph/mcp/mcp_tool_serialization.py`
- Test: `tests/test_retrieval_service_search.py`
- Test: `tests/test_search_response_contract.py`
- Test: `tests/test_cli_search.py`
- Test: `tests/test_mcp_tools.py`
- Test: `tests/test_mcp_tool_serialization.py`
- Test: `tests/test_multi_vault_search.py`

**Interfaces:**

- Produces: `SearchMode = Literal["knowledge", "evidence", "operating", "audit", "all"]`.
- Produces: `RetrievalResult.provenance_family_id`, `supporting_evidence`, `audit_records`.
- Produces: `SearchResponse.result_family_duplication`.

- [ ] **Step 1: Write failing collapse and explicit-mode tests**

```python
def test_default_search_returns_one_canonical_result_per_family_with_references() -> None:
    response = service.search(query_text="GraphRAG", requested_scope=scope, mode="knowledge", limit=10)
    assert [item.evidence[0].path for item in response.results] == ["wiki/systems/graphrag.md"]
    assert {item.path for item in response.results[0].supporting_evidence} == {
        "wiki/sources/graphrag.md", "raw/sources/graphrag.md"
    }
    assert response.result_family_duplication == 0.0

def test_evidence_mode_expands_source_and_raw_members() -> None:
    response = service.search(query_text="GraphRAG", requested_scope=scope, mode="evidence", limit=10)
    assert {item.evidence[0].path for item in response.results} == {
        "wiki/sources/graphrag.md", "raw/sources/graphrag.md"
    }
```

- [ ] **Step 2: Run RED**

Run: `uv run pytest tests/test_retrieval_service_search.py tests/test_search_response_contract.py -q`

- [ ] **Step 3: Implement mode policy and collapse**

```python
SEARCH_MODE_ROLES: dict[SearchMode, tuple[DocumentRole, ...]] = {
    "knowledge": ("canonical_knowledge",),
    "evidence": ("source_manifest", "raw_evidence"),
    "operating": ("operating_contract",),
    "audit": ("generated_view", "operation_log", "audit_record"),
    "all": ALL_DOCUMENT_ROLES,
}
```

Pass roles to keyword/vector queries before candidate limits. Resolve graph
candidates before role eligibility. In knowledge mode, resolve all family
members through a new `MetadataStore.list_family_evidence(vault_id, family_id)`
read boundary and attach reference-only lists. Apply final limit after collapse.

- [ ] **Step 4: Add CLI/MCP mode tests, implement adapters, and run GREEN**

Run: `uv run pytest tests/test_cli_search.py tests/test_mcp_tools.py tests/test_mcp_tool_serialization.py tests/test_multi_vault_search.py -q`

CLI uses `--mode knowledge` by default. MCP `SearchVaultInput.mode` accepts the
same five values. JSON/text rendering includes family ID, supporting evidence,
audit records, and duplication metric.

- [ ] **Step 5: Commit**

```bash
git add src/vault_graph/retrieval src/vault_graph/cli/main.py src/vault_graph/mcp/mcp_tools.py \
  src/vault_graph/mcp/mcp_tool_serialization.py src/vault_graph/storage/interfaces/metadata_store.py \
  src/vault_graph/storage/local/sqlite_metadata_store.py tests/test_retrieval_service_search.py \
  tests/test_search_response_contract.py tests/test_cli_search.py tests/test_mcp_tools.py \
  tests/test_mcp_tool_serialization.py tests/test_multi_vault_search.py
git commit -m "feat: collapse search by provenance family"
```

### Task 5: Projection Hygiene Audit

**Files:**

- Create: `src/vault_graph/app/projection_hygiene_service.py`
- Modify: `src/vault_graph/storage/interfaces/metadata_store.py`
- Modify: `src/vault_graph/storage/interfaces/keyword_index.py`
- Modify: `src/vault_graph/storage/interfaces/vector_store.py`
- Modify: `src/vault_graph/storage/interfaces/graph_store.py`
- Modify: local store implementations for read-only audit counters
- Modify: `src/vault_graph/cli/main.py`
- Test: `tests/test_projection_hygiene_service.py`
- Test: `tests/test_cli_projection_audit.py`

**Interfaces:**

- Produces: `ProjectionHygieneService.audit(...) -> ProjectionHygieneReport`.
- Produces: `vg projection-audit` text/JSON output.

- [ ] **Step 1: Write failing metric tests**

```python
def test_hygiene_report_proves_single_body_and_zero_dangling_refs() -> None:
    report = service.audit(scope=scope, queries=("GraphRAG",))
    assert report.plaintext_amplification == 1.0
    assert report.persisted_search_projection_plaintext_bytes == 0
    assert report.result_family_duplication == 0.0
    assert report.dangling_keyword_refs == 0
    assert report.dangling_vector_refs == 0
    assert report.dangling_graph_refs == 0
```

- [ ] **Step 2: Run RED**

Run: `uv run pytest tests/test_projection_hygiene_service.py -q`

- [ ] **Step 3: Implement read-only inventory DTOs and service**

```python
@dataclass(frozen=True)
class ProjectionHygieneReport:
    role_counts: tuple[RoleCount, ...]
    canonical_blob_count: int
    canonical_blob_bytes: int
    logical_chunk_bytes: int
    persisted_search_projection_plaintext_bytes: int
    plaintext_amplification: float
    dangling_keyword_refs: int
    dangling_vector_refs: int
    dangling_graph_refs: int
    result_family_duplication: float | None
    schema_versions: tuple[SchemaVersion, ...]
    active_generation_id: str | None
```

Store audit methods run read-only SQL or backend manifest export. The service
uses `RetrievalService` only for explicitly supplied audit queries.

- [ ] **Step 4: Add CLI tests and implement `projection-audit`**

Run: `uv run pytest tests/test_cli_projection_audit.py tests/test_projection_hygiene_service.py -q`

Assert state tree and Vault fingerprints before/after the command. With no
query, JSON renders `result_family_duplication: null`.

- [ ] **Step 5: Commit**

```bash
git add src/vault_graph/app/projection_hygiene_service.py src/vault_graph/storage src/vault_graph/cli/main.py \
  tests/test_projection_hygiene_service.py tests/test_cli_projection_audit.py
git commit -m "feat: audit projection hygiene metrics"
```

### Task 6: Transactional Projection Generations

**Files:**

- Create: `src/vault_graph/app/projection_generation.py`
- Modify: `src/vault_graph/app/catalog_service.py`
- Modify: `src/vault_graph/app/local_index_service_factory.py`
- Modify: `src/vault_graph/app/setup_service.py`
- Modify: `src/vault_graph/cli/main.py`
- Modify: `src/vault_graph/errors.py`
- Test: `tests/test_projection_generation.py`
- Test: `tests/test_cli_projection_migration.py`
- Test: `tests/test_setup_service.py`

**Interfaces:**

- Produces: `ProjectionGenerationManager.active_layout()`.
- Produces: `stage()`, `activate(staged)`, `discard(staged)`.
- Produces: `LocalIndexServiceBundle.commit_projection()` and rollback in `close()`.

- [ ] **Step 1: Write failing manifest safety and atomicity tests**

```python
def test_activation_switches_one_manifest_and_preserves_previous_generation(tmp_path: Path) -> None:
    manager = ProjectionGenerationManager(tmp_path)
    first = manager.stage()
    manager.activate(first)
    second = manager.stage()
    manager.activate(second)
    assert manager.active_layout().generation_id == second.generation_id
    assert first.root_path.exists()

@pytest.mark.parametrize("relative_path", ["../escape", "/absolute", "link-outside"])
def test_active_manifest_rejects_unsafe_generation_paths(tmp_path: Path, relative_path: str) -> None:
    write_active_manifest(tmp_path, generation_path=relative_path)
    with pytest.raises(ProjectionGenerationError):
        ProjectionGenerationManager(tmp_path).active_layout()
```

- [ ] **Step 2: Run RED and implement safe generation manager**

Run: `uv run pytest tests/test_projection_generation.py -q`

Write manifests through a same-directory temporary file, flush/fsync, then
`os.replace`. Resolve and validate every generation path under the state root;
reject symlinks and traversal.

- [ ] **Step 3: Write failing migration behavior tests**

```python
def test_v1_state_requires_full_and_failed_full_keeps_old_active(tmp_path: Path) -> None:
    seed_v1_state(tmp_path)
    incremental = runner.invoke(app, ["index", "--state", str(tmp_path)])
    assert incremental.exit_code == 1
    assert "projection_migration_required" in incremental.stdout
    failed = runner.invoke(app, ["index", "--state", str(tmp_path), "--full"])
    assert failed.exit_code == 1
    assert active_manifest(tmp_path) is None
```

- [ ] **Step 4: Integrate factory/CLI/setup activation and run GREEN**

Run: `uv run pytest tests/test_cli_projection_migration.py tests/test_setup_service.py tests/test_cli_catalog_metadata.py tests/test_acceptance_success_criteria.py -q`

The factory stages a generation for full rebuild of existing state. CLI calls
`commit_projection()` only when every enabled projection succeeds. `close()`
discards an uncommitted staging generation. Read-only services resolve the
active manifest; no manifest continues to resolve compatible legacy paths.

- [ ] **Step 5: Commit**

```bash
git add src/vault_graph/app/projection_generation.py src/vault_graph/app/catalog_service.py \
  src/vault_graph/app/local_index_service_factory.py src/vault_graph/app/setup_service.py \
  src/vault_graph/cli/main.py src/vault_graph/errors.py tests/test_projection_generation.py \
  tests/test_cli_projection_migration.py tests/test_setup_service.py
git commit -m "feat: activate projection rebuilds atomically"
```

### Task 7: Documentation, Regression Verification, And Completion Evidence

**Files:**

- Modify: `docs/SPEC.md`
- Modify: `docs/DESIGN.md`
- Modify: `docs/FEATURES.md`
- Modify: `docs/PATCH_LOG.md` only if implementation corrected an approved plan mismatch
- Modify: `README.md`
- Create: `docs/superpowers/reports/2026-08-03-round-0-g-completion-report-ko.md`
- Test: documentation contract tests as required

**Interfaces:**

- Consumes: all implemented contracts.
- Produces: Korean completion report with baseline/post metrics and workflow position.

- [ ] **Step 1: Update active contracts and user guidance**

Replace remaining v1/excerpt/co-equal default-search language with the actual
v2 role/family/blob/generation contracts. Document search modes,
`projection-audit`, and `vg index --full` migration recovery. Do not add Round 1
commands.

- [ ] **Step 2: Run focused full static and test verification**

```bash
uv run pytest -q
uv run ruff check .
uv run ruff format --check .
uv run mypy src
uv build
```

Expected: zero failures/errors and successful sdist/wheel build.

- [ ] **Step 3: Run disposable local-Vault baseline/post audit**

Use temporary state roots outside `/Users/junhyounglee/vault`. Record the Vault
Git tree and an all-file SHA-256 fingerprint before and after. Index the same
Vault revision, run:

```bash
uv run vg projection-audit --state "$ROUND0G_STATE" --query "Vault Graph" --query "Rail" --format json
uv run vg search --state "$ROUND0G_STATE" --mode knowledge --format json "Vault Graph"
```

Delete only the disposable active generation, rebuild, repeat, and compare
normalized search/audit payloads.

- [ ] **Step 4: Write the completion report**

The report must include:

- Round 0-V status and contract version
- Round 0-G implementation summary
- baseline and post `plaintext_amplification`
- query-by-query family duplication and total metric
- dangling reference counts
- rebuild equivalence evidence
- Vault read-only fingerprint evidence
- explicit statement that Round 1 has not started
- workflow:

```text
Round 0-V complete
  -> Round 0-G complete
  -> joint completion metrics complete
  -> Round 1 code index next
  -> Round 2 MCP/coding harness later
```

- [ ] **Step 5: Verify diff, commit docs/report, and perform final review**

```bash
git diff --check
git status --short
git add docs README.md
git commit -m "docs: report Round 0-G completion"
```

Review the full branch for read-only safety, plaintext ownership, schema
compatibility, performance, deterministic rebuilds, multi-Vault identity, and
adapter consistency. Fix any defect through a new failing test before claiming
completion.

## Validation Review

- Security/read-only: generation paths are state-root constrained; audit and
  search open stores read-only; Vault fingerprints are compared.
- Performance/scalability: one blob per body, role filtering before limits,
  indexed family/role columns, and bounded family reference resolution avoid
  full-Vault scans on ordinary queries.
- Testability: each task exposes a pure or protocol boundary and has a focused
  RED/GREEN suite.
- Maintainability/deep modules: authority classification, generation lifecycle,
  and hygiene metrics each have one named owner; adapters do not reimplement
  policy.
- Agent ergonomics: default knowledge mode removes repeated evidence while
  explicit modes retain drill-down; completion metrics are machine-readable.

## Risks

- FTS5 contentless delete support varies by SQLite version. Mitigation: test
  runtime support and rebuild the FTS table transactionally; if
  `contentless_delete=1` is unavailable on a supported Python runtime, use FTS5
  delete commands while keeping the table contentless.
- Chroma metadata schema changes make v1 vectors incompatible. Mitigation:
  generation rebuild; never mix v1/v2 records.
- Family collapse can hide useful revisions. Mitigation: knowledge mode only,
  deterministic reference attachment, and explicit evidence/audit/all modes.
- Multi-store rebuild can partially fail. Mitigation: no active-manifest switch
  until metadata, vector, graph, and hygiene validation succeed.

## Open Decisions

None.
