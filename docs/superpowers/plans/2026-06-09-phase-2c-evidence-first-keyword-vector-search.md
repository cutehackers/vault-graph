# Phase 2C Evidence-First Keyword And Vector Search Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the first release-ready `vg search` command that returns ranked, evidence-linked keyword/vector search results without mutating Vault or Vault Graph index state.

**Architecture:** Search is a read-only retrieval service over existing metadata, keyword, and vector projections. `KeywordIndex` and `VectorStore` return candidates only; `RetrievalService` owns query normalization, per-Vault scope expansion, rank fusion, evidence resolution, warnings, and `SearchResponse` assembly.

**Tech Stack:** Python 3.12, Typer CLI, SQLite/FTS5 metadata-owned keyword projection, Chroma vector store, FastEmbed local embeddings, pytest, ruff, mypy.

---

## Scope Guardrails

Phase 2C implements only:

- `vg search "query"`
- keyword candidate lookup over indexed Markdown chunks
- optional vector candidate lookup when already indexed and locally embeddable
- evidence chunk results resolved through `MetadataStore`
- text and JSON output
- degraded keyword-only search with structured warnings

Phase 2C must not implement:

- `vg ask`
- LLM answers
- graph traversal
- graph extraction
- context packs
- MCP or HTTP search serving
- Qdrant
- non-Markdown readers
- automatic indexing during search
- embedding model downloads during search
- writes to Vault content or Vault Graph projections during search

Release-ready means a user can run:

```bash
vg init --vault /path/to/vault
vg index
vg search "query"
vg search --format json "query"
vg search --all-vaults "query"
```

and receive deterministic evidence-linked results or a clear recovery diagnostic.

## File Structure

Create:

- `src/vault_graph/app/query_scope_resolution.py`: shared per-Vault actual scope resolution for indexing and search.
- `src/vault_graph/app/search_readiness_service.py`: read-only readiness implementation for metadata, keyword, vector, and model availability.
- `src/vault_graph/storage/interfaces/keyword_index.py`: keyword candidate contract.
- `src/vault_graph/storage/local/sqlite_keyword_index.py`: SQLite FTS5 keyword projection helpers and read-only keyword adapter.
- `src/vault_graph/retrieval/search_response.py`: top-level search request, response, warning, and scoped revision contracts.
- `src/vault_graph/retrieval/search_readiness.py`: retrieval-owned readiness protocol and report contracts only.
- `src/vault_graph/retrieval/retrieval_service.py`: Phase 2C search orchestration and rank fusion.
- `tests/fakes/in_memory_keyword_index.py`: deterministic keyword fake for retrieval tests.
- `tests/fakes/search_readiness.py`: deterministic readiness fake for retrieval tests.
- `tests/test_app_search_readiness_service.py`
- `tests/test_retrieval_import_boundaries.py`
- `tests/test_keyword_index_contract.py`
- `tests/test_sqlite_keyword_index.py`
- `tests/test_query_scope_resolution.py`
- `tests/test_search_response_contract.py`
- `tests/test_retrieval_service_search.py`
- `tests/test_cli_search.py`
- `tests/test_search_read_only_boundary.py`
- `tests/test_multi_vault_search.py`

Modify:

- `src/vault_graph/errors.py`: add `KeywordIndexError` and `SearchError`.
- `src/vault_graph/storage/interfaces/__init__.py`: export keyword contract records.
- `src/vault_graph/storage/local/sqlite_metadata_store.py`: create and update keyword projection in the same metadata transaction.
- `src/vault_graph/app/index_service.py`: reuse shared actual scope resolution.
- `src/vault_graph/embeddings/text_embeddings.py`: add no-download availability contract.
- `src/vault_graph/embeddings/fastembed_text_embeddings.py`: support local-files-only search-time embedding.
- `src/vault_graph/storage/local/chroma_vector_store.py`: allow read-only search over existing Chroma state without allowing writes or creating missing state.
- `tests/test_vector_indexing_read_only_boundary.py`: replace the Phase 2B "search is absent" assertion with a Phase 2C boundary assertion.
- `src/vault_graph/retrieval/__init__.py`: export search contracts and service.
- `src/vault_graph/cli/main.py`: add `vg search`.
- Existing tests that use `TextEmbeddings` fakes: add `can_embed_without_download()`.

Do not modify docs outside this plan during implementation unless code review identifies a design inconsistency. Implementation corrections go to `docs/PATCH_LOG.md`. Accepted product decisions go to `docs/DECISIONS.md` only after user approval.

---

### Task 1: Add Keyword Candidate Contract

**Files:**

- Create: `src/vault_graph/storage/interfaces/keyword_index.py`
- Modify: `src/vault_graph/errors.py`
- Modify: `src/vault_graph/storage/interfaces/__init__.py`
- Test: `tests/test_keyword_index_contract.py`

- [ ] **Step 1: Write the failing contract tests**

Create `tests/test_keyword_index_contract.py`:

```python
import pytest

from vault_graph.errors import KeywordIndexError
from vault_graph.ingestion.vault_catalog import QueryScope
from vault_graph.storage.interfaces.keyword_index import KeywordHit, KeywordQuery


def test_keyword_query_rejects_empty_text() -> None:
    with pytest.raises(KeywordIndexError, match="query_text is required"):
        KeywordQuery(query_text="  ", scope=QueryScope(vault_ids=("default",)), limit=10)


def test_keyword_query_rejects_non_positive_limit() -> None:
    with pytest.raises(KeywordIndexError, match="limit must be positive"):
        KeywordQuery(query_text="GraphRAG", scope=QueryScope(vault_ids=("default",)), limit=0)


def test_keyword_hit_requires_vault_scoped_identity() -> None:
    hit = KeywordHit(
        vault_id="default",
        document_id="default:wiki/page.md",
        chunk_id="chunk-1",
        rank=1,
        score=-1.25,
        backend="sqlite-fts5",
        index_revision="metadata-1",
        matched_fields=("text", "section"),
    )

    assert hit.vault_id == "default"
    assert hit.chunk_id == "chunk-1"
    assert hit.rank == 1
    assert hit.score == -1.25
    assert hit.matched_fields == ("text", "section")


def test_keyword_hit_rejects_unranked_candidate() -> None:
    with pytest.raises(KeywordIndexError, match="rank must be positive"):
        KeywordHit(
            vault_id="default",
            document_id="doc",
            chunk_id="chunk",
            rank=0,
            score=0.0,
            backend="sqlite-fts5",
            index_revision="metadata-1",
            matched_fields=("text",),
        )
```

- [ ] **Step 2: Run the contract tests and verify failure**

Run:

```bash
uv run --python 3.12 pytest tests/test_keyword_index_contract.py -q
```

Expected: FAIL because `KeywordIndexError`, `KeywordQuery`, and `KeywordHit` do not exist.

- [ ] **Step 3: Add keyword errors and contract records**

Add to `src/vault_graph/errors.py`:

```python
class KeywordIndexError(VaultGraphError):
    """Raised when keyword candidate lookup contracts are violated."""


class SearchError(VaultGraphError):
    """Raised when search cannot produce a valid response."""
```

Create `src/vault_graph/storage/interfaces/keyword_index.py`:

```python
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from vault_graph.errors import KeywordIndexError
from vault_graph.ingestion.vault_catalog import QueryScope
from vault_graph.storage.interfaces.store_health import StoreHealth


@dataclass(frozen=True)
class KeywordQuery:
    query_text: str
    scope: QueryScope
    limit: int

    def __post_init__(self) -> None:
        if not self.query_text.strip():
            raise KeywordIndexError("query_text is required")
        if self.limit <= 0:
            raise KeywordIndexError("limit must be positive")


@dataclass(frozen=True)
class KeywordHit:
    vault_id: str
    document_id: str
    chunk_id: str
    rank: int
    score: float
    backend: str
    index_revision: str
    matched_fields: tuple[str, ...]

    def __post_init__(self) -> None:
        _require_non_empty(self.vault_id, "vault_id")
        _require_non_empty(self.document_id, "document_id")
        _require_non_empty(self.chunk_id, "chunk_id")
        _require_non_empty(self.backend, "backend")
        _require_non_empty(self.index_revision, "index_revision")
        if self.rank <= 0:
            raise KeywordIndexError("rank must be positive")
        if not isinstance(self.matched_fields, tuple):
            raise KeywordIndexError("matched_fields must be an immutable tuple")


class KeywordIndex(Protocol):
    def search(self, query: KeywordQuery) -> tuple[KeywordHit, ...]: ...

    def health(self) -> StoreHealth: ...


def _require_non_empty(value: str, field_name: str) -> None:
    if not value:
        raise KeywordIndexError(f"{field_name} is required")
```

Update `src/vault_graph/storage/interfaces/__init__.py`:

```python
from vault_graph.storage.interfaces.keyword_index import KeywordHit, KeywordIndex, KeywordQuery

__all__ = [
    "KeywordHit",
    "KeywordIndex",
    "KeywordQuery",
]
```

If `__all__` already contains other exports, append these names without removing existing exports.

- [ ] **Step 4: Run the contract tests and verify pass**

Run:

```bash
uv run --python 3.12 pytest tests/test_keyword_index_contract.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/vault_graph/errors.py src/vault_graph/storage/interfaces/__init__.py src/vault_graph/storage/interfaces/keyword_index.py tests/test_keyword_index_contract.py
git commit -m "feat(search): add keyword candidate contract"
```

---

### Task 2: Add SQLite FTS Keyword Projection

**Files:**

- Create: `src/vault_graph/storage/local/sqlite_keyword_index.py`
- Modify: `src/vault_graph/storage/local/sqlite_metadata_store.py`
- Test: `tests/test_sqlite_keyword_index.py`
- Test: `tests/test_sqlite_metadata_store.py`

- [ ] **Step 1: Write failing SQLite keyword tests**

Create `tests/test_sqlite_keyword_index.py`:

```python
from pathlib import Path

from tests.test_sqlite_metadata_store import make_chunk, make_document
from vault_graph.ingestion.vault_catalog import QueryScope
from vault_graph.storage.interfaces.keyword_index import KeywordQuery
from vault_graph.storage.local.sqlite_keyword_index import SQLiteKeywordIndex
from vault_graph.storage.local.sqlite_metadata_store import SQLiteMetadataStore


def test_keyword_search_returns_current_chunk_candidates(tmp_path: Path) -> None:
    database_path = tmp_path / "metadata.sqlite3"
    metadata_store = SQLiteMetadataStore(database_path, initialize=True)
    document = make_document("default", "wiki/page.md", "hash-1")
    chunk = make_chunk("default", document.document_id, document.path)
    metadata_store.apply_metadata_revision(index_revision="metadata-1", documents=[document], chunks=[chunk], tombstones=[])
    keyword_index = SQLiteKeywordIndex(database_path)

    hits = keyword_index.search(
        KeywordQuery(query_text="Body", scope=QueryScope(vault_ids=("default",), content_scopes=("wiki",)), limit=10)
    )

    assert tuple((hit.vault_id, hit.document_id, hit.chunk_id) for hit in hits) == (
        ("default", document.document_id, chunk.chunk_id),
    )
    assert hits[0].backend == "sqlite-fts5"
    assert hits[0].index_revision == "metadata-1"


def test_keyword_search_filters_vault_before_limit(tmp_path: Path) -> None:
    database_path = tmp_path / "metadata.sqlite3"
    metadata_store = SQLiteMetadataStore(database_path, initialize=True)
    first = make_document("first", "wiki/same.md", "hash-first")
    second = make_document("second", "wiki/same.md", "hash-second")
    first_chunk = make_chunk("first", first.document_id, first.path)
    second_chunk = make_chunk("second", second.document_id, second.path)
    metadata_store.apply_metadata_revision(
        index_revision="metadata-1",
        documents=[first, second],
        chunks=[first_chunk, second_chunk],
        tombstones=[],
    )
    keyword_index = SQLiteKeywordIndex(database_path)

    hits = keyword_index.search(
        KeywordQuery(query_text="Body", scope=QueryScope(vault_ids=("second",), content_scopes=("wiki",)), limit=1)
    )

    assert tuple(hit.vault_id for hit in hits) == ("second",)


def test_keyword_search_filters_content_scope_before_limit(tmp_path: Path) -> None:
    database_path = tmp_path / "metadata.sqlite3"
    metadata_store = SQLiteMetadataStore(database_path, initialize=True)
    raw_doc = make_document("default", "raw/source.md", "hash-raw")
    wiki_doc = make_document("default", "wiki/page.md", "hash-wiki")
    metadata_store.apply_metadata_revision(
        index_revision="metadata-1",
        documents=[raw_doc, wiki_doc],
        chunks=[
            make_chunk("default", raw_doc.document_id, raw_doc.path),
            make_chunk("default", wiki_doc.document_id, wiki_doc.path),
        ],
        tombstones=[],
    )
    keyword_index = SQLiteKeywordIndex(database_path)

    hits = keyword_index.search(
        KeywordQuery(query_text="Body", scope=QueryScope(vault_ids=("default",), content_scopes=("wiki",)), limit=1)
    )

    assert tuple(hit.document_id for hit in hits) == (wiki_doc.document_id,)


def test_tombstoned_documents_are_removed_from_keyword_projection(tmp_path: Path) -> None:
    database_path = tmp_path / "metadata.sqlite3"
    metadata_store = SQLiteMetadataStore(database_path, initialize=True)
    document = make_document("default", "wiki/page.md", "hash-1")
    chunk = make_chunk("default", document.document_id, document.path)
    metadata_store.apply_metadata_revision(index_revision="metadata-1", documents=[document], chunks=[chunk], tombstones=[])
    metadata_store.apply_metadata_revision(
        index_revision="metadata-2",
        documents=[],
        chunks=[],
        tombstones=[("default", "wiki/page.md")],
    )
    keyword_index = SQLiteKeywordIndex(database_path)

    hits = keyword_index.search(
        KeywordQuery(query_text="Body", scope=QueryScope(vault_ids=("default",), content_scopes=("wiki",)), limit=10)
    )

    assert hits == ()


def test_missing_keyword_projection_health_is_visible(tmp_path: Path) -> None:
    keyword_index = SQLiteKeywordIndex(tmp_path / "missing.sqlite3")

    health = keyword_index.health()

    assert health.ok is False
    assert health.schema_compatible is False
    assert "not initialized" in health.message


def test_keyword_schema_version_mismatch_is_visible(tmp_path: Path) -> None:
    database_path = tmp_path / "metadata.sqlite3"
    metadata_store = SQLiteMetadataStore(database_path, initialize=True)
    with metadata_store.connect_for_tests() as connection:
        connection.execute(
            """
            UPDATE keyword_projection_metadata
            SET value = 'old-version'
            WHERE key = 'schema_version'
            """
        )
    keyword_index = SQLiteKeywordIndex(database_path)

    health = keyword_index.health()

    assert health.ok is False
    assert health.schema_compatible is False
    assert "schema version mismatch" in health.message
```

- [ ] **Step 2: Run the SQLite keyword tests and verify failure**

Run:

```bash
uv run --python 3.12 pytest tests/test_sqlite_keyword_index.py -q
```

Expected: FAIL because the SQLite keyword adapter and projection do not exist.

- [ ] **Step 3: Implement SQLite keyword projection helpers and adapter**

Create `src/vault_graph/storage/local/sqlite_keyword_index.py`:

```python
from __future__ import annotations

import json
import re
import sqlite3
from pathlib import Path, PurePosixPath
from typing import Any

from vault_graph.errors import KeywordIndexError
from vault_graph.ingestion.document_normalizer import ChunkSnapshot, DocumentSnapshot
from vault_graph.ingestion.vault_catalog import QueryScope
from vault_graph.storage.interfaces.keyword_index import KeywordHit, KeywordQuery
from vault_graph.storage.interfaces.store_health import StoreHealth

SQLITE_KEYWORD_BACKEND = "sqlite-fts5"
KEYWORD_SCHEMA_VERSION = "sqlite-keyword-v1"

KEYWORD_SCHEMA = """
CREATE TABLE IF NOT EXISTS keyword_projection_metadata (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL
);

CREATE VIRTUAL TABLE IF NOT EXISTS keyword_chunks USING fts5(
  vault_id UNINDEXED,
  document_id UNINDEXED,
  chunk_id UNINDEXED,
  path,
  section,
  anchor UNINDEXED,
  title,
  frontmatter,
  text,
  content_scope UNINDEXED,
  index_revision UNINDEXED,
  tokenize='unicode61'
);
"""

REQUIRED_KEYWORD_COLUMNS = (
    "vault_id",
    "document_id",
    "chunk_id",
    "path",
    "section",
    "anchor",
    "title",
    "frontmatter",
    "text",
    "content_scope",
    "index_revision",
)


class SQLiteKeywordIndex:
    def __init__(self, database_path: Path) -> None:
        self._database_path = database_path.expanduser().resolve()

    def search(self, query: KeywordQuery) -> tuple[KeywordHit, ...]:
        health = self.health()
        if not health.ok or not health.schema_compatible:
            raise KeywordIndexError(f"keyword index unavailable: {health.message}. Run `vg index`.")
        match_query = _match_query(query.query_text)
        vault_placeholders = ", ".join("?" for _ in query.scope.vault_ids)
        path_clause, path_args = _content_scope_clause(query.scope.content_scopes)
        with self._connect_readonly() as connection:
            rows = connection.execute(
                f"""
                SELECT vault_id, document_id, chunk_id, path, section, title, frontmatter, text,
                       index_revision, bm25(keyword_chunks) AS score
                FROM keyword_chunks
                WHERE keyword_chunks MATCH ?
                  AND vault_id IN ({vault_placeholders})
                  AND ({path_clause})
                ORDER BY score ASC, vault_id ASC, path ASC, chunk_id ASC
                LIMIT ?
                """,
                (match_query, *query.scope.vault_ids, *path_args, query.limit),
            ).fetchall()
        return tuple(_keyword_hit_from_row(rank=rank, row=row) for rank, row in enumerate(rows, start=1))

    def health(self) -> StoreHealth:
        if not self._database_path.exists():
            return StoreHealth(
                ok=False,
                backend=SQLITE_KEYWORD_BACKEND,
                schema_version=KEYWORD_SCHEMA_VERSION,
                schema_compatible=False,
                message="not initialized",
            )
        try:
            with self._connect_readonly() as connection:
                tables = {
                    str(row["name"])
                    for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
                }
                missing = {"keyword_projection_metadata", "keyword_chunks"} - tables
                if missing:
                    return StoreHealth(
                        ok=False,
                        backend=SQLITE_KEYWORD_BACKEND,
                        schema_version=KEYWORD_SCHEMA_VERSION,
                        schema_compatible=False,
                        message=f"schema incompatible: missing {', '.join(sorted(missing))}",
                    )
                version = connection.execute(
                    "SELECT value FROM keyword_projection_metadata WHERE key = 'schema_version'"
                ).fetchone()
                if version is None or str(version["value"]) != KEYWORD_SCHEMA_VERSION:
                    return StoreHealth(
                        ok=False,
                        backend=SQLITE_KEYWORD_BACKEND,
                        schema_version=KEYWORD_SCHEMA_VERSION,
                        schema_compatible=False,
                        message="schema incompatible: keyword schema version mismatch",
                    )
                columns = {
                    str(row["name"])
                    for row in connection.execute("PRAGMA table_info(keyword_chunks)").fetchall()
                }
                missing_columns = set(REQUIRED_KEYWORD_COLUMNS) - columns
                if missing_columns:
                    return StoreHealth(
                        ok=False,
                        backend=SQLITE_KEYWORD_BACKEND,
                        schema_version=KEYWORD_SCHEMA_VERSION,
                        schema_compatible=False,
                        message=f"schema incompatible: missing keyword columns {', '.join(sorted(missing_columns))}",
                    )
        except sqlite3.Error as exc:
            return StoreHealth(
                ok=False,
                backend=SQLITE_KEYWORD_BACKEND,
                schema_version=KEYWORD_SCHEMA_VERSION,
                schema_compatible=False,
                message=str(exc),
            )
        return StoreHealth(
            ok=True,
            backend=SQLITE_KEYWORD_BACKEND,
            schema_version=KEYWORD_SCHEMA_VERSION,
            schema_compatible=True,
            message="ok",
        )

    def _connect_readonly(self) -> sqlite3.Connection:
        connection = sqlite3.connect(f"file:{self._database_path}?mode=ro", uri=True)
        connection.row_factory = sqlite3.Row
        return connection


def apply_keyword_revision(
    connection: sqlite3.Connection,
    *,
    index_revision: str,
    documents: list[DocumentSnapshot],
    chunks: list[ChunkSnapshot],
    tombstones: list[tuple[str, str]],
) -> None:
    ensure_keyword_schema(connection)
    for document in documents:
        connection.execute(
            "DELETE FROM keyword_chunks WHERE vault_id = ? AND document_id = ?",
            (document.vault_id, document.document_id),
        )
    for vault_id, path in tombstones:
        connection.execute("DELETE FROM keyword_chunks WHERE vault_id = ? AND path = ?", (vault_id, path))
    documents_by_id = {(document.vault_id, document.document_id): document for document in documents}
    for chunk in chunks:
        document = documents_by_id[(chunk.vault_id, chunk.document_id)]
        connection.execute(
            """
            INSERT INTO keyword_chunks (
              vault_id, document_id, chunk_id, path, section, anchor, title, frontmatter,
              text, content_scope, index_revision
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                chunk.vault_id,
                chunk.document_id,
                chunk.chunk_id,
                chunk.path,
                chunk.section or "",
                chunk.anchor or "",
                _title_for_document(document),
                json.dumps(document.frontmatter, sort_keys=True),
                chunk.text,
                _content_scope_for_path(chunk.path),
                index_revision,
            ),
        )


def ensure_keyword_schema(connection: sqlite3.Connection) -> None:
    connection.executescript(KEYWORD_SCHEMA)
    connection.execute(
        """
        INSERT INTO keyword_projection_metadata (key, value)
        VALUES ('schema_version', ?)
        ON CONFLICT(key) DO UPDATE SET value = excluded.value
        """,
        (KEYWORD_SCHEMA_VERSION,),
    )


def _match_query(query_text: str) -> str:
    tokens = re.findall(r"[\w가-힣]+", query_text, flags=re.UNICODE)
    if not tokens:
        raise KeywordIndexError("query_text has no searchable tokens")
    quoted_tokens = []
    for token in tokens:
        escaped = token.replace('"', '""')
        quoted_tokens.append(f'"{escaped}"')
    return " OR ".join(quoted_tokens)


def _content_scope_clause(content_scopes: tuple[str, ...]) -> tuple[str, tuple[str, ...]]:
    clauses: list[str] = []
    args: list[str] = []
    for content_scope in content_scopes:
        clauses.append("(path = ? OR path LIKE ?)")
        args.extend((content_scope, f"{content_scope}/%"))
    return " OR ".join(clauses), tuple(args)


def _keyword_hit_from_row(*, rank: int, row: sqlite3.Row) -> KeywordHit:
    return KeywordHit(
        vault_id=str(row["vault_id"]),
        document_id=str(row["document_id"]),
        chunk_id=str(row["chunk_id"]),
        rank=rank,
        score=float(row["score"]),
        backend=SQLITE_KEYWORD_BACKEND,
        index_revision=str(row["index_revision"]),
        matched_fields=_matched_fields(row),
    )


def _matched_fields(row: sqlite3.Row) -> tuple[str, ...]:
    return tuple(
        field
        for field in ("title", "section", "frontmatter", "text", "path")
        if str(row[field] or "").strip()
    )


def _title_for_document(document: DocumentSnapshot) -> str:
    title = document.frontmatter.get("title")
    return str(title) if title is not None else PurePosixPath(document.path).stem


def _content_scope_for_path(path: str) -> str:
    parent = PurePosixPath(path).parent.as_posix()
    if parent == ".":
        return path.split("/", 1)[0]
    return parent
```

- [ ] **Step 4: Wire keyword updates into metadata transactions**

Modify `src/vault_graph/storage/local/sqlite_metadata_store.py`:

```python
from vault_graph.storage.local.sqlite_keyword_index import apply_keyword_revision, ensure_keyword_schema
```

In `__init__`, after `connection.executescript(SCHEMA)`:

```python
ensure_keyword_schema(connection)
```

In `apply_metadata_revision`, inside the same `with self._connect() as connection:` block and after document/chunk/tombstone writes:

```python
apply_keyword_revision(
    connection,
    index_revision=index_revision,
    documents=documents,
    chunks=chunks,
    tombstones=tombstones,
)
```

This must remain in the same SQLite transaction. If keyword projection update fails, the metadata revision must fail too.

- [ ] **Step 5: Run SQLite metadata and keyword tests**

Run:

```bash
uv run --python 3.12 pytest tests/test_sqlite_metadata_store.py tests/test_sqlite_keyword_index.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/vault_graph/storage/local/sqlite_keyword_index.py src/vault_graph/storage/local/sqlite_metadata_store.py tests/test_sqlite_keyword_index.py tests/test_sqlite_metadata_store.py
git commit -m "feat(search): add sqlite keyword projection"
```

---

### Task 3: Share Per-Vault Actual Scope Resolution

**Files:**

- Create: `src/vault_graph/app/query_scope_resolution.py`
- Modify: `src/vault_graph/app/index_service.py`
- Test: `tests/test_query_scope_resolution.py`
- Test: `tests/test_index_service_vector_reconcile.py`

- [ ] **Step 1: Write failing scope resolution tests**

Create `tests/test_query_scope_resolution.py`:

```python
from pathlib import Path

from vault_graph.app.query_scope_resolution import actual_query_scopes
from vault_graph.ingestion.vault_catalog import QueryScope, VaultCatalog, VaultCatalogEntry


def _entry(tmp_path: Path, vault_id: str, scopes: tuple[str, ...]) -> VaultCatalogEntry:
    root = tmp_path / vault_id
    root.mkdir()
    return VaultCatalogEntry.from_root(vault_id=vault_id, root_path=root, content_scopes=scopes)


def test_actual_scopes_keep_each_vault_narrow(tmp_path: Path) -> None:
    catalog = VaultCatalog.from_entries(
        entries=[
            _entry(tmp_path, "first", ("wiki",)),
            _entry(tmp_path, "second", ("docs",)),
        ],
        active_vault_id="first",
    )

    scopes = actual_query_scopes(
        catalog=catalog,
        scope=QueryScope(vault_ids=("first", "second"), content_scopes=("wiki", "docs")),
    )

    assert tuple(scope.vault_ids for scope in scopes) == (("first",), ("second",))
    assert tuple(scope.content_scopes for scope in scopes) == (("wiki",), ("docs",))


def test_actual_scopes_use_narrower_child_scope(tmp_path: Path) -> None:
    catalog = VaultCatalog.from_entries(
        entries=[_entry(tmp_path, "default", ("wiki",))],
        active_vault_id="default",
    )

    scopes = actual_query_scopes(
        catalog=catalog,
        scope=QueryScope(vault_ids=("default",), content_scopes=("wiki/systems",)),
    )

    assert scopes[0].content_scopes == ("wiki/systems",)


def test_actual_scopes_skip_disjoint_scope_pairs(tmp_path: Path) -> None:
    catalog = VaultCatalog.from_entries(
        entries=[_entry(tmp_path, "default", ("wiki",))],
        active_vault_id="default",
    )

    scopes = actual_query_scopes(
        catalog=catalog,
        scope=QueryScope(vault_ids=("default",), content_scopes=("docs",)),
    )

    assert scopes == ()
```

- [ ] **Step 2: Run scope tests and verify failure**

Run:

```bash
uv run --python 3.12 pytest tests/test_query_scope_resolution.py -q
```

Expected: FAIL because `actual_query_scopes` does not exist.

- [ ] **Step 3: Add shared scope resolution module**

Create `src/vault_graph/app/query_scope_resolution.py`:

```python
from __future__ import annotations

from vault_graph.ingestion.vault_catalog import QueryScope, VaultCatalog


def actual_query_scopes(*, catalog: VaultCatalog, scope: QueryScope) -> tuple[QueryScope, ...]:
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

- [ ] **Step 4: Replace the private vector scope resolver**

Modify `src/vault_graph/app/index_service.py`:

```python
from vault_graph.app.query_scope_resolution import actual_query_scopes
```

Replace:

```python
_actual_vector_scopes(catalog=self._catalog, scope=scope)
```

with:

```python
actual_query_scopes(catalog=self._catalog, scope=scope)
```

Remove the private `_actual_vector_scopes` and `_is_same_or_child` functions from `index_service.py`.

- [ ] **Step 5: Run scope and Phase 2B index service tests**

Run:

```bash
uv run --python 3.12 pytest tests/test_query_scope_resolution.py tests/test_index_service_vector_reconcile.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/vault_graph/app/query_scope_resolution.py src/vault_graph/app/index_service.py tests/test_query_scope_resolution.py
git commit -m "refactor(app): share actual query scope resolution"
```

---

### Task 4: Add SearchResponse Contract

**Files:**

- Create: `src/vault_graph/retrieval/search_response.py`
- Modify: `src/vault_graph/retrieval/__init__.py`
- Test: `tests/test_search_response_contract.py`

- [ ] **Step 1: Write failing response contract tests**

Create `tests/test_search_response_contract.py`:

```python
import pytest

from tests.test_retrieval_result_contract import make_evidence, make_signal, make_store_revisions
from vault_graph.errors import SearchError
from vault_graph.ingestion.vault_catalog import QueryScope
from vault_graph.retrieval import RetrievalResult
from vault_graph.retrieval.search_response import (
    SearchOutputFormat,
    SearchRequest,
    SearchResponse,
    SearchStoreRevision,
    SearchWarning,
)


def _result() -> RetrievalResult:
    return RetrievalResult(
        result_id="default:chunk:rank-1",
        vault_id="default",
        kind="evidence_chunk",
        title="wiki/page.md#section",
        summary="Body",
        rank=1,
        evidence=(make_evidence(),),
        signals=(make_signal(kind="keyword"),),
        relationship_status="not_applicable",
        warnings=(),
        store_revisions=make_store_revisions(),
    )


def test_search_request_rejects_empty_query() -> None:
    with pytest.raises(SearchError, match="query_text is required"):
        SearchRequest(
            query_text=" ",
            requested_scope=QueryScope(vault_ids=("default",)),
            actual_scopes=(QueryScope(vault_ids=("default",)),),
            limit=10,
            output_format="text",
        )


def test_search_response_records_query_wide_degraded_state() -> None:
    warning = SearchWarning(
        code="vector_unavailable",
        message="Vector search is unavailable",
        severity="warning",
        affected_vault_ids=("default",),
    )
    response = SearchResponse(
        query_text="GraphRAG",
        requested_scope=QueryScope(vault_ids=("default",)),
        actual_scopes=(QueryScope(vault_ids=("default",)),),
        limit=10,
        result_count=1,
        candidate_count=2,
        dropped_candidate_count=1,
        results=(_result(),),
        warnings=(warning,),
        degraded=True,
        store_revisions=(
            SearchStoreRevision(
                kind="metadata",
                revision="metadata-1",
                scope_key="default:wiki",
                vault_id="default",
            ),
        ),
        generated_at="2026-06-09T00:00:00+00:00",
    )

    assert response.degraded is True
    assert response.warnings[0].affected_vault_ids == ("default",)
    assert response.result_count == len(response.results)


def test_search_response_rejects_result_count_mismatch() -> None:
    with pytest.raises(SearchError, match="result_count must match results"):
        SearchResponse(
            query_text="GraphRAG",
            requested_scope=QueryScope(vault_ids=("default",)),
            actual_scopes=(QueryScope(vault_ids=("default",)),),
            limit=10,
            result_count=2,
            candidate_count=1,
            dropped_candidate_count=0,
            results=(_result(),),
            warnings=(),
            degraded=False,
            store_revisions=(
                SearchStoreRevision(
                    kind="metadata",
                    revision="metadata-1",
                    scope_key="default:wiki",
                    vault_id="default",
                ),
            ),
            generated_at="2026-06-09T00:00:00+00:00",
        )


def test_search_warning_requires_vault_attribution() -> None:
    with pytest.raises(SearchError, match="affected_vault_ids is required"):
        SearchWarning(
            code="vector_unavailable",
            message="Vector search is unavailable",
            severity="warning",
            affected_vault_ids=(),
        )


def test_store_revision_requires_scope_attribution() -> None:
    with pytest.raises(SearchError, match="scope_key is required"):
        SearchStoreRevision(kind="metadata", revision="metadata-1", scope_key="")


def test_search_output_format_type_allows_text_and_json() -> None:
    text_format: SearchOutputFormat = "text"
    json_format: SearchOutputFormat = "json"

    assert text_format == "text"
    assert json_format == "json"
```

- [ ] **Step 2: Run response tests and verify failure**

Run:

```bash
uv run --python 3.12 pytest tests/test_search_response_contract.py -q
```

Expected: FAIL because search response contracts do not exist.

- [ ] **Step 3: Add response contracts**

Create `src/vault_graph/retrieval/search_response.py`:

```python
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from vault_graph.errors import SearchError
from vault_graph.ingestion.vault_catalog import QueryScope
from vault_graph.retrieval.retrieval_result import RetrievalResult, RetrievalSeverity

SearchOutputFormat = Literal["text", "json"]


@dataclass(frozen=True)
class SearchStoreRevision:
    kind: str
    revision: str
    scope_key: str
    vault_id: str | None = None

    def __post_init__(self) -> None:
        _require_non_empty(self.kind, "kind")
        _require_non_empty(self.revision, "revision")
        _require_non_empty(self.scope_key, "scope_key")


@dataclass(frozen=True)
class SearchWarning:
    code: str
    message: str
    severity: RetrievalSeverity
    affected_vault_ids: tuple[str, ...]
    document_id: str | None = None
    chunk_id: str | None = None
    source_id: str | None = None

    def __post_init__(self) -> None:
        _require_non_empty(self.code, "code")
        _require_non_empty(self.message, "message")
        if not isinstance(self.affected_vault_ids, tuple):
            raise SearchError("affected_vault_ids must be an immutable tuple")
        if not self.affected_vault_ids:
            raise SearchError("affected_vault_ids is required")


@dataclass(frozen=True)
class SearchRequest:
    query_text: str
    requested_scope: QueryScope
    actual_scopes: tuple[QueryScope, ...]
    limit: int
    output_format: SearchOutputFormat

    def __post_init__(self) -> None:
        if not self.query_text.strip():
            raise SearchError("query_text is required")
        if self.limit <= 0:
            raise SearchError("limit must be positive")
        if self.output_format not in ("text", "json"):
            raise SearchError("unsupported_format")


@dataclass(frozen=True)
class SearchResponse:
    query_text: str
    requested_scope: QueryScope
    actual_scopes: tuple[QueryScope, ...]
    limit: int
    result_count: int
    candidate_count: int
    dropped_candidate_count: int
    results: tuple[RetrievalResult, ...]
    warnings: tuple[SearchWarning, ...]
    degraded: bool
    store_revisions: tuple[SearchStoreRevision, ...]
    generated_at: str

    def __post_init__(self) -> None:
        if not self.query_text.strip():
            raise SearchError("query_text is required")
        if self.limit <= 0:
            raise SearchError("limit must be positive")
        if self.result_count != len(self.results):
            raise SearchError("result_count must match results")
        if self.candidate_count < 0:
            raise SearchError("candidate_count must not be negative")
        if self.dropped_candidate_count < 0:
            raise SearchError("dropped_candidate_count must not be negative")
        if not isinstance(self.results, tuple):
            raise SearchError("results must be an immutable tuple")
        if not isinstance(self.warnings, tuple):
            raise SearchError("warnings must be an immutable tuple")
        if not isinstance(self.store_revisions, tuple):
            raise SearchError("store_revisions must be an immutable tuple")


def _require_non_empty(value: str, field_name: str) -> None:
    if not value:
        raise SearchError(f"{field_name} is required")
```

Update `src/vault_graph/retrieval/__init__.py` to export:

```python
from vault_graph.retrieval.search_response import (
    SearchOutputFormat,
    SearchRequest,
    SearchResponse,
    SearchStoreRevision,
    SearchWarning,
)
```

Append these names to `__all__`.

- [ ] **Step 4: Run response tests and verify pass**

Run:

```bash
uv run --python 3.12 pytest tests/test_search_response_contract.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/vault_graph/retrieval/search_response.py src/vault_graph/retrieval/__init__.py tests/test_search_response_contract.py
git commit -m "feat(search): add search response contract"
```

---

### Task 5: Add No-Download Embedding And Search Readiness Boundaries

**Files:**

- Modify: `src/vault_graph/embeddings/text_embeddings.py`
- Modify: `src/vault_graph/embeddings/fastembed_text_embeddings.py`
- Modify: `tests/fakes/deterministic_text_embeddings.py`
- Create: `src/vault_graph/retrieval/search_readiness.py`
- Create: `src/vault_graph/app/search_readiness_service.py`
- Test: `tests/test_text_embeddings_contract.py`
- Test: `tests/test_fastembed_text_embeddings.py`
- Test: `tests/test_app_search_readiness_service.py`
- Test: `tests/test_retrieval_import_boundaries.py`

- [ ] **Step 1: Write failing no-download and readiness tests**

Append to `tests/test_text_embeddings_contract.py`:

```python
from vault_graph.embeddings.text_embeddings import EmbeddingModelSpec


def test_text_embeddings_exposes_no_download_availability() -> None:
    spec = EmbeddingModelSpec(
        model_name="deterministic",
        model_version="test",
        dimensions=4,
        spec_version="embedding-spec-v1",
    )
    embeddings = DeterministicTextEmbeddings(spec)

    assert embeddings.can_embed_without_download() is True
```

Append to `tests/test_fastembed_text_embeddings.py`:

```python
from pathlib import Path

import pytest


def test_fastembed_can_check_local_artifact_without_loading_backend(tmp_path: Path) -> None:
    calls: list[str] = []

    def resolver(_: FastEmbedTextEmbeddingsConfig) -> Path:
        calls.append("resolver")
        return tmp_path / "snapshot"

    embeddings = FastEmbedTextEmbeddings(
        config=FastEmbedTextEmbeddingsConfig(cache_dir=tmp_path, local_files_only=True),
        snapshot_resolver=resolver,
        backend_factory=lambda _config, _path: pytest.fail("backend must not load"),
    )

    assert embeddings.can_embed_without_download() is True
    assert calls == ["resolver"]
```

Create `tests/test_app_search_readiness_service.py`:

```python
from dataclasses import replace
from pathlib import Path

from tests.fakes.deterministic_text_embeddings import DeterministicTextEmbeddings
from tests.fakes.in_memory_vector_store import InMemoryVectorStore
from tests.test_sqlite_metadata_store import make_chunk, make_document
from tests.test_vector_indexer import SPEC
from vault_graph.app.search_readiness_service import ReadOnlySearchReadiness
from vault_graph.indexing.vector_indexer import VectorIndexer
from vault_graph.ingestion.vault_catalog import QueryScope
from vault_graph.storage.interfaces.store_health import StoreHealth
from vault_graph.storage.local.sqlite_metadata_store import SQLiteMetadataStore


class HealthyKeywordIndex:
    def health(self) -> StoreHealth:
        return StoreHealth(ok=True, backend="keyword", schema_version="v1", schema_compatible=True, message="ok")


def metadata_store_with_chunk(tmp_path: Path, *, content_hash: str = "chunk") -> tuple[SQLiteMetadataStore, QueryScope]:
    store = SQLiteMetadataStore(tmp_path / "metadata.sqlite3", initialize=True)
    document = make_document("default", "wiki/page.md", "hash")
    chunk = make_chunk("default", document.document_id, document.path)
    chunk = replace(chunk, content_hash=content_hash, index_revision="metadata-1")
    store.apply_metadata_revision(index_revision="metadata-1", documents=[document], chunks=[chunk], tombstones=[])
    return store, QueryScope(vault_ids=("default",), content_scopes=("wiki",))


def test_search_readiness_reports_vector_freshness(tmp_path: Path) -> None:
    metadata_store, scope = metadata_store_with_chunk(tmp_path)
    vector_store = InMemoryVectorStore()
    embeddings = DeterministicTextEmbeddings(SPEC)
    VectorIndexer(chunk_store=metadata_store, vector_store=vector_store, text_embeddings=embeddings).apply(
        scopes=(scope,)
    )
    readiness = ReadOnlySearchReadiness(
        metadata_store=metadata_store,
        keyword_index=HealthyKeywordIndex(),
        vector_store=vector_store,
        text_embeddings=embeddings,
    )

    report = readiness.check(actual_scopes=(scope,))

    assert report.metadata_health.ok is True
    assert report.keyword_health.ok is True
    assert report.vector_health is not None
    assert report.vector_stale_count == 0
    assert report.can_embed_without_download is True
    assert {revision.kind for revision in report.store_revisions} >= {"metadata", "keyword", "vector"}
    assert all(revision.scope_key for revision in report.store_revisions)


def test_search_readiness_reports_stale_vector_without_status_store(tmp_path: Path) -> None:
    old_store, scope = metadata_store_with_chunk(tmp_path / "old", content_hash="old")
    vector_store = InMemoryVectorStore()
    embeddings = DeterministicTextEmbeddings(SPEC)
    VectorIndexer(chunk_store=old_store, vector_store=vector_store, text_embeddings=embeddings).apply(scopes=(scope,))
    new_store, _ = metadata_store_with_chunk(tmp_path / "new", content_hash="changed")
    readiness = ReadOnlySearchReadiness(
        metadata_store=new_store,
        keyword_index=HealthyKeywordIndex(),
        vector_store=vector_store,
        text_embeddings=embeddings,
    )

    report = readiness.check(actual_scopes=(scope,))

    assert report.vector_stale_count == 2
```

- [ ] **Step 2: Run tests and verify failure**

Run:

```bash
uv run --python 3.12 pytest tests/test_text_embeddings_contract.py tests/test_fastembed_text_embeddings.py tests/test_app_search_readiness_service.py -q
```

Expected: FAIL because the no-download method and readiness boundary do not exist.

- [ ] **Step 3: Extend TextEmbeddings protocol and deterministic fake**

Modify `src/vault_graph/embeddings/text_embeddings.py`:

```python
class TextEmbeddings(Protocol):
    def model_spec(self) -> EmbeddingModelSpec: ...

    def can_embed_without_download(self) -> bool: ...

    def embed(self, inputs: tuple[EmbeddingInput, ...]) -> tuple[EmbeddingVector, ...]: ...
```

Modify `tests/fakes/deterministic_text_embeddings.py`:

```python
    def can_embed_without_download(self) -> bool:
        return True
```

- [ ] **Step 4: Add local-files-only support to FastEmbed**

Modify `FastEmbedTextEmbeddingsConfig` in `src/vault_graph/embeddings/fastembed_text_embeddings.py`:

```python
    local_files_only: bool = False
```

Add to `FastEmbedTextEmbeddings`:

```python
    def can_embed_without_download(self) -> bool:
        try:
            self._snapshot_resolver(self._config_for_local_files_only())
        except TextEmbeddingsError:
            return False
        except Exception:
            return False
        return True

    def _config_for_local_files_only(self) -> FastEmbedTextEmbeddingsConfig:
        return FastEmbedTextEmbeddingsConfig(
            model_name=self._config.model_name,
            model_version=self._config.model_version,
            dimensions=self._config.dimensions,
            spec_version=self._config.spec_version,
            artifact_repo_id=self._config.artifact_repo_id,
            source_model_revision=self._config.source_model_revision,
            cache_dir=self._config.cache_dir,
            embedding_batch_size=self._config.embedding_batch_size,
            embedding_parallelism=self._config.embedding_parallelism,
            embedding_lazy_load=self._config.embedding_lazy_load,
            local_files_only=True,
        )
```

Modify `_resolve_snapshot`:

```python
        return Path(
            snapshot_download(
                repo_id=config.artifact_repo_id,
                revision=config.model_version,
                cache_dir=str(config.cache_dir.expanduser()),
                local_files_only=config.local_files_only,
            )
        )
```

Search-time construction must use `local_files_only=True`; indexing keeps the default `False`.

- [ ] **Step 5: Add readiness protocol and read-only app implementation**

Create `src/vault_graph/retrieval/search_readiness.py`:

```python
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from vault_graph.ingestion.vault_catalog import QueryScope
from vault_graph.retrieval.search_response import SearchStoreRevision
from vault_graph.storage.interfaces.store_health import StoreHealth


@dataclass(frozen=True)
class SearchReadinessReport:
    metadata_health: StoreHealth
    keyword_health: StoreHealth
    vector_health: StoreHealth | None
    vector_stale_count: int | None
    can_embed_without_download: bool
    store_revisions: tuple[SearchStoreRevision, ...]


class SearchReadiness(Protocol):
    def check(self, *, actual_scopes: tuple[QueryScope, ...]) -> SearchReadinessReport: ...
```

This module must not import `vault_graph.indexing`, `vault_graph.storage.local.vector_status_store`, or concrete local backends.

Create `src/vault_graph/app/search_readiness_service.py`:

```python
from __future__ import annotations

from vault_graph.embeddings.text_embeddings import TextEmbeddings
from vault_graph.indexing.vector_indexer import VectorIndexer
from vault_graph.ingestion.vault_catalog import QueryScope
from vault_graph.retrieval.search_readiness import SearchReadinessReport
from vault_graph.retrieval.search_response import SearchStoreRevision
from vault_graph.storage.interfaces.keyword_index import KeywordIndex
from vault_graph.storage.interfaces.metadata_store import MetadataStore
from vault_graph.storage.interfaces.store_health import StoreHealth
from vault_graph.storage.interfaces.vector_store import VectorStore


class ReadOnlySearchReadiness:
    def __init__(
        self,
        *,
        metadata_store: MetadataStore,
        keyword_index: KeywordIndex,
        vector_store: VectorStore | None = None,
        text_embeddings: TextEmbeddings | None = None,
    ) -> None:
        self._metadata_store = metadata_store
        self._keyword_index = keyword_index
        self._vector_store = vector_store
        self._text_embeddings = text_embeddings

    def check(self, *, actual_scopes: tuple[QueryScope, ...]) -> SearchReadinessReport:
        metadata_health = self._metadata_store.health()
        keyword_health = self._keyword_index.health()
        vector_health = self._vector_store.health() if self._vector_store is not None else None
        can_embed = self._text_embeddings.can_embed_without_download() if self._text_embeddings is not None else False
        stale_count = self._vector_stale_count(actual_scopes=actual_scopes, vector_health=vector_health)
        store_revisions = self._store_revisions(actual_scopes=actual_scopes, vector_health=vector_health)
        return SearchReadinessReport(
            metadata_health=metadata_health,
            keyword_health=keyword_health,
            vector_health=vector_health,
            vector_stale_count=stale_count,
            can_embed_without_download=can_embed,
            store_revisions=store_revisions,
        )

    def _vector_stale_count(
        self,
        *,
        actual_scopes: tuple[QueryScope, ...],
        vector_health: StoreHealth | None,
    ) -> int | None:
        if self._vector_store is None or self._text_embeddings is None or vector_health is None:
            return None
        if not vector_health.ok or not vector_health.schema_compatible:
            return None
        plan = VectorIndexer(
            chunk_store=self._metadata_store,
            vector_store=self._vector_store,
            text_embeddings=self._text_embeddings,
        ).plan(scopes=actual_scopes, full=False)
        return plan.upsert_count + plan.tombstone_count

    def _store_revisions(
        self,
        *,
        actual_scopes: tuple[QueryScope, ...],
        vector_health: StoreHealth | None,
    ) -> tuple[SearchStoreRevision, ...]:
        revisions: list[SearchStoreRevision] = []
        for scope in actual_scopes:
            scope_key = _scope_key(scope)
            chunks = self._metadata_store.list_chunks(scope)
            metadata_revision = _revision_from_values(
                tuple(chunk.index_revision for chunk in chunks),
                fallback=f"empty:{self._metadata_store.health().schema_version}",
            )
            revisions.append(SearchStoreRevision(kind="metadata", revision=metadata_revision, scope_key=scope_key))
            revisions.append(SearchStoreRevision(kind="keyword", revision=metadata_revision, scope_key=scope_key))
            if self._vector_store is not None and vector_health is not None and vector_health.ok:
                manifest = self._vector_store.export_manifest(scope)
                vector_revision = _revision_from_values(
                    tuple(row.vector_index_revision for row in manifest),
                    fallback=f"empty:{vector_health.schema_version}",
                )
                revisions.append(SearchStoreRevision(kind="vector", revision=vector_revision, scope_key=scope_key))
        return tuple(revisions)


def _scope_key(scope: QueryScope) -> str:
    return f"{','.join(scope.vault_ids)}:{','.join(scope.content_scopes)}"


def _revision_from_values(values: tuple[str | None, ...], *, fallback: str) -> str:
    revisions = tuple(sorted({value for value in values if value}))
    return ",".join(revisions) if revisions else fallback
```

This app service may use `VectorIndexer.plan(...)` because it is outside the retrieval package. It must still use read-only stores in search construction and must not import or write `LocalVectorStatusStore`.

Create `tests/test_retrieval_import_boundaries.py`:

```python
from pathlib import Path


def test_retrieval_package_does_not_import_indexing_or_local_status_store() -> None:
    retrieval_files = Path("src/vault_graph/retrieval").glob("*.py")
    combined = "\n".join(path.read_text(encoding="utf-8") for path in retrieval_files)

    assert "vault_graph.indexing" not in combined
    assert "vector_status_store" not in combined
    assert "ReadOnlySearchReadiness" not in combined
```

- [ ] **Step 6: Run readiness and embedding tests**

Run:

```bash
uv run --python 3.12 pytest tests/test_text_embeddings_contract.py tests/test_fastembed_text_embeddings.py tests/test_app_search_readiness_service.py tests/test_retrieval_import_boundaries.py -q
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add src/vault_graph/embeddings/text_embeddings.py src/vault_graph/embeddings/fastembed_text_embeddings.py src/vault_graph/retrieval/search_readiness.py src/vault_graph/app/search_readiness_service.py tests/fakes/deterministic_text_embeddings.py tests/test_text_embeddings_contract.py tests/test_fastembed_text_embeddings.py tests/test_app_search_readiness_service.py tests/test_retrieval_import_boundaries.py
git commit -m "feat(search): add read-only search readiness"
```

---

### Task 6: Add RetrievalService Keyword Search And Fusion

**Files:**

- Create: `src/vault_graph/retrieval/retrieval_service.py`
- Modify: `src/vault_graph/retrieval/__init__.py`
- Create: `tests/fakes/in_memory_keyword_index.py`
- Create: `tests/fakes/search_readiness.py`
- Test: `tests/test_retrieval_service_search.py`

- [ ] **Step 1: Write failing retrieval service tests**

Create `tests/fakes/in_memory_keyword_index.py`:

```python
from __future__ import annotations

from vault_graph.storage.interfaces.keyword_index import KeywordHit, KeywordQuery
from vault_graph.storage.interfaces.store_health import StoreHealth


class InMemoryKeywordIndex:
    def __init__(
        self,
        hits: tuple[KeywordHit, ...] = (),
        *,
        content_scope_by_key: dict[tuple[str, str], str] | None = None,
    ) -> None:
        self._hits = hits
        self._content_scope_by_key = content_scope_by_key or {}

    def search(self, query: KeywordQuery) -> tuple[KeywordHit, ...]:
        scoped = tuple(
            hit
            for hit in self._hits
            if hit.vault_id in query.scope.vault_ids
            and _content_scope_in_scope(
                record_scope=self._content_scope_by_key.get((hit.vault_id, hit.chunk_id), "wiki"),
                query_scopes=query.scope.content_scopes,
            )
        )
        return scoped[: query.limit]

    def health(self) -> StoreHealth:
        return StoreHealth(ok=True, backend="memory-keyword", schema_version="v1", schema_compatible=True, message="ok")


def _content_scope_in_scope(*, record_scope: str, query_scopes: tuple[str, ...]) -> bool:
    return any(record_scope == query_scope or record_scope.startswith(f"{query_scope}/") for query_scope in query_scopes)
```

Create `tests/fakes/search_readiness.py`:

```python
from __future__ import annotations

from vault_graph.retrieval.search_readiness import SearchReadinessReport
from vault_graph.retrieval.search_response import SearchStoreRevision
from vault_graph.storage.interfaces.store_health import StoreHealth


def ready_report(
    *,
    vector_ok: bool = False,
    vector_stale_count: int | None = None,
    can_embed_without_download: bool = False,
    scope_key: str = "default:wiki",
) -> SearchReadinessReport:
    return SearchReadinessReport(
        metadata_health=StoreHealth(ok=True, backend="metadata", schema_version="v1", schema_compatible=True, message="ok"),
        keyword_health=StoreHealth(ok=True, backend="keyword", schema_version="v1", schema_compatible=True, message="ok"),
        vector_health=StoreHealth(ok=vector_ok, backend="vector", schema_version="v1", schema_compatible=vector_ok, message="ok" if vector_ok else "not initialized"),
        vector_stale_count=vector_stale_count,
        can_embed_without_download=can_embed_without_download,
        store_revisions=(
            SearchStoreRevision(kind="metadata", revision="metadata-1", scope_key=scope_key),
            SearchStoreRevision(kind="keyword", revision="metadata-1", scope_key=scope_key),
        )
        + (
            (SearchStoreRevision(kind="vector", revision="vector-1", scope_key=scope_key),)
            if vector_ok
            else ()
        ),
    )
```

Create `tests/test_retrieval_service_search.py` with these first tests:

```python
from pathlib import Path

import pytest

from tests.fakes.deterministic_text_embeddings import DeterministicTextEmbeddings
from tests.fakes.in_memory_keyword_index import InMemoryKeywordIndex
from tests.fakes.in_memory_vector_store import InMemoryVectorStore
from tests.fakes.search_readiness import ready_report
from tests.test_sqlite_metadata_store import make_chunk, make_document
from tests.test_vector_indexer import SPEC
from vault_graph.embeddings.text_embeddings import EmbeddingInput
from vault_graph.errors import SearchError
from vault_graph.indexing.vector_indexer import stable_vector_id
from vault_graph.ingestion.vault_catalog import QueryScope, VaultCatalog, VaultCatalogEntry
from vault_graph.retrieval.retrieval_service import RetrievalService
from vault_graph.retrieval.search_readiness import SearchReadinessReport
from vault_graph.storage.interfaces.keyword_index import KeywordHit
from vault_graph.storage.interfaces.vector_store import VectorEmbeddingRecord
from vault_graph.storage.local.sqlite_metadata_store import SQLiteMetadataStore


class StaticReadiness:
    def __init__(self, report: SearchReadinessReport) -> None:
        self._report = report

    def check(self, *, actual_scopes: tuple[QueryScope, ...]) -> SearchReadinessReport:
        return self._report


def _catalog(tmp_path: Path, vault_id: str = "default") -> VaultCatalog:
    root = tmp_path / vault_id
    root.mkdir()
    return VaultCatalog.from_entries(
        entries=[VaultCatalogEntry.from_root(vault_id=vault_id, root_path=root)],
        active_vault_id=vault_id,
    )


def _metadata_store(tmp_path: Path) -> tuple[SQLiteMetadataStore, str, str]:
    store = SQLiteMetadataStore(tmp_path / "metadata.sqlite3", initialize=True)
    document = make_document("default", "wiki/page.md", "hash-1")
    chunk = make_chunk("default", document.document_id, document.path)
    store.apply_metadata_revision(index_revision="metadata-1", documents=[document], chunks=[chunk], tombstones=[])
    return store, document.document_id, chunk.chunk_id


def _keyword_hit(document_id: str, chunk_id: str, rank: int = 1) -> KeywordHit:
    return KeywordHit(
        vault_id="default",
        document_id=document_id,
        chunk_id=chunk_id,
        rank=rank,
        score=-1.0,
        backend="memory-keyword",
        index_revision="metadata-1",
        matched_fields=("text",),
    )


def test_keyword_only_search_returns_evidence_chunk(tmp_path: Path) -> None:
    catalog = _catalog(tmp_path)
    store, document_id, chunk_id = _metadata_store(tmp_path)
    service = RetrievalService(
        catalog=catalog,
        metadata_store=store,
        keyword_index=InMemoryKeywordIndex((_keyword_hit(document_id, chunk_id),)),
        readiness=StaticReadiness(ready_report(vector_ok=False)),
    )

    response = service.search(
        query_text="Body",
        requested_scope=catalog.default_scope(),
        limit=10,
        output_format="text",
    )

    assert response.result_count == 1
    assert response.results[0].kind == "evidence_chunk"
    assert response.results[0].evidence[0].vault_id == "default"
    assert response.results[0].signals[0].kind == "keyword"
    assert response.degraded is True
    assert response.warnings[0].code == "vector_unavailable"


def test_empty_query_fails_before_candidate_lookup(tmp_path: Path) -> None:
    catalog = _catalog(tmp_path)
    store, document_id, chunk_id = _metadata_store(tmp_path)
    service = RetrievalService(
        catalog=catalog,
        metadata_store=store,
        keyword_index=InMemoryKeywordIndex((_keyword_hit(document_id, chunk_id),)),
        readiness=StaticReadiness(ready_report(vector_ok=False)),
    )

    with pytest.raises(SearchError, match="query_text is required"):
        service.search(query_text=" ", requested_scope=catalog.default_scope(), limit=10, output_format="text")


def test_keyword_and_vector_signals_merge_by_vault_chunk(tmp_path: Path) -> None:
    catalog = _catalog(tmp_path)
    store, document_id, chunk_id = _metadata_store(tmp_path)
    embeddings = DeterministicTextEmbeddings(SPEC)
    chunk = store.resolve_chunk(vault_id="default", chunk_id=chunk_id)
    assert chunk is not None
    vector = embeddings.embed((EmbeddingInput(input_id="default:chunk", text=chunk.text),))[0]
    record = VectorEmbeddingRecord(
        vector_id=stable_vector_id(vault_id="default", chunk_id=chunk_id, embedding_spec=SPEC),
        vault_id="default",
        document_id=document_id,
        chunk_id=chunk_id,
        content_scope="wiki",
        embedding=vector,
        source_chunk_hash=chunk.content_hash,
        chunker_version=chunk.chunker_version,
        metadata_index_revision="metadata-1",
        vector_index_revision="vector-1",
        backend_schema_version="memory-vector-v1",
    )
    vector_store = InMemoryVectorStore()
    vector_store.apply_vector_revision(vector_index_revision="vector-1", records=(record,), tombstones=())
    service = RetrievalService(
        catalog=catalog,
        metadata_store=store,
        keyword_index=InMemoryKeywordIndex((_keyword_hit(document_id, chunk_id),)),
        vector_store=vector_store,
        text_embeddings=embeddings,
        readiness=StaticReadiness(ready_report(vector_ok=True, vector_stale_count=0, can_embed_without_download=True)),
    )

    response = service.search(query_text="Body", requested_scope=catalog.default_scope(), limit=10, output_format="text")

    assert response.result_count == 1
    assert tuple(signal.kind for signal in response.results[0].signals) == ("keyword", "vector")
    assert response.degraded is False


def test_zero_result_search_still_reports_store_revisions(tmp_path: Path) -> None:
    catalog = _catalog(tmp_path)
    store, _, _ = _metadata_store(tmp_path)
    service = RetrievalService(
        catalog=catalog,
        metadata_store=store,
        keyword_index=InMemoryKeywordIndex(()),
        readiness=StaticReadiness(ready_report(vector_ok=False)),
    )

    response = service.search(query_text="missing", requested_scope=catalog.default_scope(), limit=10, output_format="text")

    assert response.result_count == 0
    assert {revision.kind for revision in response.store_revisions} >= {"metadata", "keyword"}
    assert all(revision.scope_key for revision in response.store_revisions)
```

- [ ] **Step 2: Run retrieval tests and verify failure**

Run:

```bash
uv run --python 3.12 pytest tests/test_retrieval_service_search.py -q
```

Expected: FAIL because `RetrievalService` does not exist.

- [ ] **Step 3: Implement RetrievalService**

Create `src/vault_graph/retrieval/retrieval_service.py`:

```python
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from vault_graph.app.query_scope_resolution import actual_query_scopes
from vault_graph.embeddings.text_embeddings import EmbeddingInput, TextEmbeddings
from vault_graph.errors import KeywordIndexError, SearchError, TextEmbeddingsError, VectorStoreError
from vault_graph.ingestion.document_normalizer import ChunkSnapshot
from vault_graph.ingestion.vault_catalog import QueryScope, VaultCatalog
from vault_graph.retrieval.retrieval_result import (
    RetrievalResult,
    RetrievalSignal,
    RetrievalWarning,
    StoreRevision,
    warning_for_stale_vector,
)
from vault_graph.retrieval.search_readiness import SearchReadiness, SearchReadinessReport
from vault_graph.retrieval.search_response import (
    SearchOutputFormat,
    SearchRequest,
    SearchResponse,
    SearchStoreRevision,
    SearchWarning,
)
from vault_graph.storage.interfaces.keyword_index import KeywordHit, KeywordIndex, KeywordQuery
from vault_graph.storage.interfaces.metadata_store import EvidenceReference, MetadataStore
from vault_graph.storage.interfaces.vector_store import VectorHit, VectorQuery, VectorStore

RANK_CONSTANT = 60.0
SIGNAL_WEIGHTS = {"keyword": 1.0, "vector": 1.0}
```

Use this implementation shape:

```python
class RetrievalService:
    def __init__(
        self,
        *,
        catalog: VaultCatalog,
        metadata_store: MetadataStore,
        keyword_index: KeywordIndex,
        vector_store: VectorStore | None = None,
        text_embeddings: TextEmbeddings | None = None,
        readiness: SearchReadiness,
    ) -> None:
        self._catalog = catalog
        self._metadata_store = metadata_store
        self._keyword_index = keyword_index
        self._vector_store = vector_store
        self._text_embeddings = text_embeddings
        self._readiness = readiness

    def search(
        self,
        *,
        query_text: str,
        requested_scope: QueryScope,
        limit: int = 10,
        output_format: SearchOutputFormat = "text",
    ) -> SearchResponse:
        normalized_query = query_text.strip()
        actual_scopes = actual_query_scopes(catalog=self._catalog, scope=requested_scope)
        request = SearchRequest(
            query_text=normalized_query,
            requested_scope=requested_scope,
            actual_scopes=actual_scopes,
            limit=limit,
            output_format=output_format,
        )
        return self._search_request(request)
```

Implement `_search_request` with these rules:

```python
    def _search_request(self, request: SearchRequest) -> SearchResponse:
        candidate_limit = max(request.limit * 4, 20)
        readiness = self._readiness.check(actual_scopes=request.actual_scopes)
        fatal = _fatal_readiness_error(readiness)
        if fatal is not None:
            raise fatal
        warnings = list(_warnings_for_readiness(readiness, request.actual_scopes))
        keyword_hits = self._keyword_hits(request=request, candidate_limit=candidate_limit)
        vector_hits = self._vector_hits(request=request, candidate_limit=candidate_limit, readiness=readiness, warnings=warnings)
        candidates = _fuse_candidates(keyword_hits=keyword_hits, vector_hits=vector_hits)
        results, dropped, missing_warnings = self._resolve_results(
            candidates=candidates,
            request=request,
        )
        warnings.extend(missing_warnings)
        limited_results = tuple(results[: request.limit])
        return SearchResponse(
            query_text=request.query_text,
            requested_scope=request.requested_scope,
            actual_scopes=request.actual_scopes,
            limit=request.limit,
            result_count=len(limited_results),
            candidate_count=len(keyword_hits) + len(vector_hits),
            dropped_candidate_count=dropped,
            results=limited_results,
            warnings=tuple(warnings),
            degraded=bool(warnings),
            store_revisions=readiness.store_revisions,
            generated_at=datetime.now(UTC).isoformat(),
        )
```

Internal helper requirements:

- `_fatal_readiness_error` raises `SearchError("metadata_unavailable: ...")` when metadata health is not ok or schema incompatible.
- `_fatal_readiness_error` raises `SearchError("keyword_index_unavailable: ... Run `vg index`.")` when keyword health is not ok or schema incompatible.
- `_warnings_for_readiness` emits `vector_unavailable`, `vector_stale`, `embedding_model_unavailable`, and `degraded_keyword_only` as appropriate. Every warning must set `affected_vault_ids` to the non-empty Vault IDs from the affected actual scopes.
- `_keyword_hits` calls `KeywordIndex.search(KeywordQuery(...))` once per actual scope and never queries SQLite directly.
- `_vector_hits` skips vector search when readiness says vector is unavailable, stale, or the model cannot embed without download.
- `_vector_hits` embeds one query input with `EmbeddingInput(input_id="query", text=request.query_text)` and calls `VectorStore.search(VectorQuery(...))` once per actual scope.
- `_vector_hits` catches `TextEmbeddingsError` and `VectorStoreError`, adds query-wide warnings, and returns no vector hits.
- `_fuse_candidates` merges by `(vault_id, chunk_id)` and uses `weight / (RANK_CONSTANT + signal_rank)`.
- Result sorting is `fused_score DESC`, `best_signal_rank ASC`, `vault_id ASC`, `path ASC`, `chunk_id ASC`.
- `_resolve_results` uses `MetadataStore.resolve_chunk_evidence(...)` and `MetadataStore.resolve_chunk(...)`; candidates that fail either resolution are dropped with `missing_evidence`.
- `RetrievalResult.kind` is `evidence_chunk`.
- `RetrievalResult.result_id` includes `vault_id`, `chunk_id`, and rank.
- `RetrievalSignal.source_id` includes `vault_id` and `chunk_id`.
- Result summary is a bounded excerpt, for example first 240 characters with whitespace collapsed.
- `SearchResponse.store_revisions` comes from `SearchReadinessReport.store_revisions`, not from returned results. This preserves revision attribution for zero-result searches, dropped candidates, and degraded search.
- `SearchResponse.warnings` must never contain an unattributed warning. Use all requested/actual Vault IDs for query-wide conditions such as `degraded_keyword_only`.

- [ ] **Step 4: Add focused helper dataclasses**

Inside `retrieval_service.py`, add internal immutable records:

```python
@dataclass(frozen=True)
class _SignalCandidate:
    kind: str
    vault_id: str
    document_id: str
    chunk_id: str
    rank: int
    score: float
    backend: str
    index_revision: str
    source_id: str


@dataclass(frozen=True)
class _FusedCandidate:
    vault_id: str
    document_id: str
    chunk_id: str
    fused_score: float
    best_signal_rank: int
    signals: tuple[_SignalCandidate, ...]
```

Keep these private. Do not create a public candidate abstraction until another retrieval signal needs it.

- [ ] **Step 5: Export RetrievalService**

Update `src/vault_graph/retrieval/__init__.py`:

```python
from vault_graph.retrieval.retrieval_service import RetrievalService
```

Append `"RetrievalService"` to `__all__`.

- [ ] **Step 6: Run retrieval service tests**

Run:

```bash
uv run --python 3.12 pytest tests/test_retrieval_service_search.py -q
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add src/vault_graph/retrieval/retrieval_service.py src/vault_graph/retrieval/__init__.py tests/fakes/in_memory_keyword_index.py tests/fakes/search_readiness.py tests/test_retrieval_service_search.py
git commit -m "feat(search): add evidence-first retrieval service"
```

---

### Task 7: Enable Read-Only Vector Query Path

**Files:**

- Modify: `src/vault_graph/storage/local/chroma_vector_store.py`
- Test: `tests/test_chroma_vector_store.py`

- [ ] **Step 1: Write failing read-only vector tests**

Append to `tests/test_chroma_vector_store.py`:

```python
def test_read_only_search_does_not_create_missing_chroma_state(tmp_path: Path) -> None:
    store = ChromaVectorStore(tmp_path / "missing", initialize=False, read_only=True)
    query = make_query(text="alpha", scope=QueryScope(vault_ids=("default",), content_scopes=("wiki",)))

    hits = store.search(query)

    assert hits == ()
    assert not (tmp_path / "missing" / "chroma.sqlite3").exists()
```

Append an existing-state test using the current helper functions in `tests/test_chroma_vector_store.py`:

```python
def test_read_only_search_can_query_existing_chroma_state(tmp_path: Path) -> None:
    path = tmp_path / "chroma"
    writable = ChromaVectorStore(path, initialize=True)
    record = make_record(vault_id="default", path="wiki/page.md", text="alpha", content_scope="wiki")
    writable.apply_vector_revision(vector_index_revision="vector-1", records=(record,), tombstones=())
    before = _tree_snapshot(path)
    readonly = ChromaVectorStore(path, initialize=False, read_only=True)

    hits = readonly.search(make_query(text="alpha", scope=QueryScope(vault_ids=("default",), content_scopes=("wiki",))))

    assert tuple((hit.vault_id, hit.chunk_id) for hit in hits) == (("default", record.chunk_id),)
    assert _tree_snapshot(path) == before


def _tree_snapshot(root: Path) -> dict[str, tuple[int, bytes]]:
    return {
        str(path.relative_to(root)): (path.stat().st_size, path.read_bytes())
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }
```

- [ ] **Step 2: Run Chroma tests and verify failure**

Run:

```bash
uv run --python 3.12 pytest tests/test_chroma_vector_store.py -q
```

Expected: the existing-state read-only search test fails because read-only search returns empty.

- [ ] **Step 3: Modify `ChromaVectorStore.search`**

In `src/vault_graph/storage/local/chroma_vector_store.py`, replace:

```python
        if self._read_only:
            return ()
```

with:

```python
        if self._read_only and not self._database_path.exists():
            return ()
```

Keep `apply_vector_revision` rejecting read-only writes. Keep `_get_collection_if_exists`; never call `_get_or_create_collection` in `search`.

- [ ] **Step 4: Run Chroma tests**

Run:

```bash
uv run --python 3.12 pytest tests/test_chroma_vector_store.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/vault_graph/storage/local/chroma_vector_store.py tests/test_chroma_vector_store.py
git commit -m "fix(search): allow read-only vector queries"
```

---

### Task 8: Add `vg search` CLI And Output Rendering

**Files:**

- Modify: `src/vault_graph/cli/main.py`
- Test: `tests/test_cli_search.py`
- Test: `tests/test_search_read_only_boundary.py`
- Test: `tests/test_vector_indexing_read_only_boundary.py`

- [ ] **Step 1: Write failing CLI tests**

Create `tests/test_cli_search.py`:

```python
import json
from pathlib import Path

from pytest import MonkeyPatch
from typer.testing import CliRunner

from tests.test_cli_vector_indexing import _ConfiguredDeterministicTextEmbeddings
from vault_graph.cli.main import app

runner = CliRunner()


def write_page(root: Path, path: str, body: str) -> None:
    file_path = root / path
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(body, encoding="utf-8")


def _deterministic_text_embeddings(_: object) -> _ConfiguredDeterministicTextEmbeddings:
    from tests.test_vector_indexer import SPEC

    return _ConfiguredDeterministicTextEmbeddings(SPEC)


def test_cli_search_uses_active_vault_by_default(tmp_path: Path, monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setattr("vault_graph.cli.main._text_embeddings", _deterministic_text_embeddings)
    monkeypatch.setattr("vault_graph.cli.main._search_text_embeddings", _deterministic_text_embeddings)
    vault_root = tmp_path / "vault"
    write_page(vault_root, "wiki/page.md", "# Page\nGraphRAG evidence\n")
    state_path = tmp_path / "state"
    runner.invoke(app, ["init", "--vault", str(vault_root), "--state", str(state_path)])
    runner.invoke(app, ["index", "--state", str(state_path)])

    result = runner.invoke(app, ["search", "--state", str(state_path), "GraphRAG"])

    assert result.exit_code == 0
    assert "default" in result.stdout
    assert "wiki/page.md" in result.stdout
    assert "GraphRAG evidence" in result.stdout


def test_cli_search_json_uses_search_response_contract(tmp_path: Path, monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setattr("vault_graph.cli.main._text_embeddings", _deterministic_text_embeddings)
    monkeypatch.setattr("vault_graph.cli.main._search_text_embeddings", _deterministic_text_embeddings)
    vault_root = tmp_path / "vault"
    write_page(vault_root, "wiki/page.md", "# Page\nGraphRAG evidence\n")
    state_path = tmp_path / "state"
    runner.invoke(app, ["init", "--vault", str(vault_root), "--state", str(state_path)])
    runner.invoke(app, ["index", "--state", str(state_path)])

    result = runner.invoke(app, ["search", "--state", str(state_path), "--format", "json", "GraphRAG"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["query_text"] == "GraphRAG"
    assert payload["result_count"] == 1
    assert payload["results"][0]["vault_id"] == "default"
    assert payload["results"][0]["kind"] == "evidence_chunk"
    assert payload["warnings"] == []


def test_cli_search_scope_flags_are_mutually_exclusive(tmp_path: Path) -> None:
    vault_root = tmp_path / "vault"
    vault_root.mkdir()
    state_path = tmp_path / "state"
    runner.invoke(app, ["init", "--vault", str(vault_root), "--state", str(state_path)])

    result = runner.invoke(app, ["search", "--state", str(state_path), "--vault-id", "default", "--all-vaults", "GraphRAG"])

    assert result.exit_code == 1
    assert "Use either --vault-id or --all-vaults" in result.stdout


def test_cli_search_missing_keyword_projection_exits_nonzero_without_writes(tmp_path: Path) -> None:
    vault_root = tmp_path / "vault"
    write_page(vault_root, "wiki/page.md", "# Page\nGraphRAG evidence\n")
    state_path = tmp_path / "state"
    runner.invoke(app, ["init", "--vault", str(vault_root), "--state", str(state_path)])

    result = runner.invoke(app, ["search", "--state", str(state_path), "GraphRAG"])

    assert result.exit_code == 1
    assert "keyword_index_unavailable" in result.stdout or "metadata_unavailable" in result.stdout
    assert not (state_path / "metadata" / "metadata.sqlite3").exists()


def test_search_text_embeddings_uses_local_files_only(tmp_path: Path) -> None:
    from vault_graph.app.catalog_service import CatalogService

    config = CatalogService(state_path=tmp_path / "state", embedding_cache_path=tmp_path / "embedding-cache")

    embeddings = _search_text_embeddings(config)

    assert embeddings.config.local_files_only is True
```

Create `tests/test_search_read_only_boundary.py`:

```python
from pathlib import Path

from pytest import MonkeyPatch
from typer.testing import CliRunner

from vault_graph.cli.main import app

runner = CliRunner()


def write_page(root: Path, path: str, body: str) -> None:
    file_path = root / path
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(body, encoding="utf-8")


def test_search_missing_indexes_does_not_create_metadata_or_vector_state(tmp_path: Path) -> None:
    vault_root = tmp_path / "vault"
    write_page(vault_root, "wiki/page.md", "# Page\nBody\n")
    state_path = tmp_path / "state"
    runner.invoke(app, ["init", "--vault", str(vault_root), "--state", str(state_path)])

    result = runner.invoke(app, ["search", "--state", str(state_path), "Body"])

    assert result.exit_code == 1
    assert not (state_path / "metadata" / "metadata.sqlite3").exists()
    assert not (state_path / "vector" / "chroma" / "chroma.sqlite3").exists()
    assert not (state_path / "vector" / "status.json").exists()


def test_successful_search_does_not_mutate_existing_state_or_vault(tmp_path: Path, monkeypatch: MonkeyPatch) -> None:
    from tests.test_cli_search import _deterministic_text_embeddings

    monkeypatch.setattr("vault_graph.cli.main._text_embeddings", _deterministic_text_embeddings)
    monkeypatch.setattr("vault_graph.cli.main._search_text_embeddings", _deterministic_text_embeddings)
    vault_root = tmp_path / "vault"
    write_page(vault_root, "wiki/page.md", "# Page\nGraphRAG evidence\n")
    state_path = tmp_path / "state"
    runner.invoke(app, ["init", "--vault", str(vault_root), "--state", str(state_path)])
    runner.invoke(app, ["index", "--state", str(state_path)])
    before_vault = _tree_snapshot(vault_root)
    before_state = _tree_snapshot(state_path)

    result = runner.invoke(app, ["search", "--state", str(state_path), "GraphRAG"])

    assert result.exit_code == 0
    assert _tree_snapshot(vault_root) == before_vault
    assert _tree_snapshot(state_path) == before_state


def _tree_snapshot(root: Path) -> dict[str, tuple[int, bytes]]:
    return {
        str(path.relative_to(root)): (path.stat().st_size, path.read_bytes())
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }
```

- [ ] **Step 2: Run CLI tests and verify failure**

Run:

```bash
uv run --python 3.12 pytest tests/test_cli_search.py -q
```

Expected: FAIL because `vg search` does not exist.

- [ ] **Step 3: Add CLI service construction**

Modify `src/vault_graph/cli/main.py` imports:

```python
import json
from dataclasses import asdict
```

Add imports:

```python
from vault_graph.ingestion.vault_catalog import QueryScope
from vault_graph.app.search_readiness_service import ReadOnlySearchReadiness
from vault_graph.retrieval import RetrievalService, SearchResponse, SearchWarning
from vault_graph.storage.local.sqlite_keyword_index import SQLiteKeywordIndex
```

Update `_exit_on_domain_error` to catch:

```python
except (CatalogError, ReadOnlyBoundaryError, KeywordIndexError, SearchError, TextEmbeddingsError, VectorStoreError) as exc:
```

Add the missing error imports.

Add service construction:

```python
def _search_service(state: Path) -> tuple[CatalogService, VaultCatalog, RetrievalService]:
    config, catalog = _catalog(state)
    metadata_store = SQLiteMetadataStore(config.metadata_path, initialize=False)
    keyword_index = SQLiteKeywordIndex(config.metadata_path)
    vector_store = ChromaVectorStore(config.vector_path, initialize=False, read_only=True)
    text_embeddings = _search_text_embeddings(config)
    return config, catalog, RetrievalService(
        catalog=catalog,
        metadata_store=metadata_store,
        keyword_index=keyword_index,
        vector_store=vector_store,
        text_embeddings=text_embeddings,
        readiness=ReadOnlySearchReadiness(
            metadata_store=metadata_store,
            keyword_index=keyword_index,
            vector_store=vector_store,
            text_embeddings=text_embeddings,
        ),
    )


def _search_text_embeddings(config: CatalogService) -> FastEmbedTextEmbeddings:
    return FastEmbedTextEmbeddings(
        config=FastEmbedTextEmbeddingsConfig(
            cache_dir=config.embedding_cache_path,
            local_files_only=True,
        )
    )
```

- [ ] **Step 4: Add `search` command**

Add to `src/vault_graph/cli/main.py`:

```python
@app.command()
def search(
    query: str = typer.Argument(..., help="Search query text."),
    state: Path = typer.Option(Path(".vault-graph"), "--state", help="Vault Graph state path."),
    vault_id: str | None = typer.Option(None, "--vault-id", help="Search one registered Vault ID."),
    all_vaults: bool = typer.Option(False, "--all-vaults", help="Search all enabled registered Vaults."),
    limit: int = typer.Option(10, "--limit", help="Maximum number of final results."),
    output_format: str = typer.Option("text", "--format", help="Output format: text or json."),
) -> None:
    if all_vaults and vault_id:
        typer.echo("Use either --vault-id or --all-vaults, not both.")
        raise typer.Exit(1)
    if output_format not in {"text", "json"}:
        typer.echo("unsupported_format")
        raise typer.Exit(1)
    _, catalog, service = _exit_on_domain_error(lambda: _search_service(state))
    if all_vaults:
        scope = _exit_on_domain_error(catalog.scope_for_all_enabled)
    elif vault_id is not None:
        selected_vault_id = vault_id
        scope = _exit_on_domain_error(lambda: catalog.scope_for_vault_ids([selected_vault_id]))
    else:
        scope = _exit_on_domain_error(catalog.default_scope)
    response = _exit_on_domain_error(
        lambda: service.search(
            query_text=query,
            requested_scope=scope,
            limit=limit,
            output_format=output_format,  # type: ignore[arg-type]
        )
    )
    if output_format == "json":
        typer.echo(json.dumps(_search_response_json(response), sort_keys=True, indent=2))
    else:
        _render_search_response(response)
```

The `config` variable can be assigned to `_` if ruff reports it unused.

- [ ] **Step 5: Add output helpers**

Add to `src/vault_graph/cli/main.py`:

```python
def _render_search_response(response: SearchResponse) -> None:
    if response.warnings:
        for warning in response.warnings:
            scope = ",".join(warning.affected_vault_ids)
            typer.echo(f"warning: {warning.code} [{scope}] {warning.message}")
    typer.echo(f"query: {response.query_text}")
    typer.echo(f"results: {response.result_count}")
    for result in response.results:
        evidence = result.evidence[0]
        typer.echo(f"{result.rank}. [{result.vault_id}] {result.title}")
        typer.echo(f"   path: {evidence.path}")
        if evidence.section:
            typer.echo(f"   section: {evidence.section}")
        typer.echo(f"   summary: {result.summary}")
        signal_text = ", ".join(f"{signal.kind}:{signal.rank}" for signal in result.signals)
        typer.echo(f"   signals: {signal_text}")


def _search_response_json(response: SearchResponse) -> dict[str, object]:
    return {
        "query_text": response.query_text,
        "requested_scope": _scope_json(response.requested_scope),
        "actual_scopes": [_scope_json(scope) for scope in response.actual_scopes],
        "limit": response.limit,
        "result_count": response.result_count,
        "candidate_count": response.candidate_count,
        "dropped_candidate_count": response.dropped_candidate_count,
        "results": [asdict(result) for result in response.results],
        "warnings": [_warning_json(warning) for warning in response.warnings],
        "degraded": response.degraded,
        "store_revisions": [asdict(revision) for revision in response.store_revisions],
        "generated_at": response.generated_at,
    }


def _scope_json(scope: QueryScope) -> dict[str, object]:
    return {
        "vault_ids": list(scope.vault_ids),
        "content_scopes": list(scope.content_scopes),
        "include_cross_vault": scope.include_cross_vault,
    }


def _warning_json(warning: SearchWarning) -> dict[str, object]:
    return {
        "code": warning.code,
        "message": warning.message,
        "severity": warning.severity,
        "affected_vault_ids": list(warning.affected_vault_ids),
        "document_id": warning.document_id,
        "chunk_id": warning.chunk_id,
        "source_id": warning.source_id,
    }
```

- [ ] **Step 6: Run CLI and read-only tests**

Update `tests/test_vector_indexing_read_only_boundary.py` by replacing the Phase 2B assertion that `search` is absent. Phase 2C must expose `search`, while later answer/context commands remain absent:

```python
def test_search_exposes_search_but_not_answer_or_context_commands() -> None:
    result = runner.invoke(app, ["--help"])

    assert result.exit_code == 0
    assert "search" in result.output
    assert "ask" not in result.output
    assert "context" not in result.output
```

Run:

```bash
uv run --python 3.12 pytest tests/test_cli_search.py tests/test_search_read_only_boundary.py tests/test_vector_indexing_read_only_boundary.py -q
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add src/vault_graph/cli/main.py tests/test_cli_search.py tests/test_search_read_only_boundary.py tests/test_vector_indexing_read_only_boundary.py
git commit -m "feat(cli): add evidence-first search command"
```

---

### Task 9: Add Multi-Vault Search Coverage

**Files:**

- Test: `tests/test_multi_vault_search.py`
- Modify only if tests reveal a real bug: `src/vault_graph/retrieval/retrieval_service.py`, `src/vault_graph/cli/main.py`, or `src/vault_graph/storage/local/sqlite_keyword_index.py`

- [ ] **Step 1: Write multi-vault tests**

Create `tests/test_multi_vault_search.py`:

```python
import json
from pathlib import Path

from pytest import MonkeyPatch
from typer.testing import CliRunner

from tests.test_cli_search import _deterministic_text_embeddings, write_page
from vault_graph.cli.main import app

runner = CliRunner()


def test_all_vault_search_keeps_identical_paths_separate(tmp_path: Path, monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setattr("vault_graph.cli.main._text_embeddings", _deterministic_text_embeddings)
    monkeypatch.setattr("vault_graph.cli.main._search_text_embeddings", _deterministic_text_embeddings)
    first = tmp_path / "first"
    second = tmp_path / "second"
    write_page(first, "wiki/same.md", "# Same\nGraphRAG from first\n")
    write_page(second, "wiki/same.md", "# Same\nGraphRAG from second\n")
    state_path = tmp_path / "state"
    runner.invoke(app, ["init", "--vault-id", "first", "--vault", str(first), "--state", str(state_path)])
    runner.invoke(app, ["vault", "add", "second", "--path", str(second), "--state", str(state_path)])
    runner.invoke(app, ["index", "--state", str(state_path), "--all-vaults"])

    result = runner.invoke(app, ["search", "--state", str(state_path), "--all-vaults", "--format", "json", "GraphRAG"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert sorted(item["vault_id"] for item in payload["results"]) == ["first", "second"]
    assert all(item["kind"] == "evidence_chunk" for item in payload["results"])
    assert len({item["result_id"] for item in payload["results"]}) == 2


def test_single_vault_search_does_not_leak_other_vault_results(tmp_path: Path, monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setattr("vault_graph.cli.main._text_embeddings", _deterministic_text_embeddings)
    monkeypatch.setattr("vault_graph.cli.main._search_text_embeddings", _deterministic_text_embeddings)
    first = tmp_path / "first"
    second = tmp_path / "second"
    write_page(first, "wiki/same.md", "# Same\nGraphRAG from first\n")
    write_page(second, "wiki/same.md", "# Same\nGraphRAG from second\n")
    state_path = tmp_path / "state"
    runner.invoke(app, ["init", "--vault-id", "first", "--vault", str(first), "--state", str(state_path)])
    runner.invoke(app, ["vault", "add", "second", "--path", str(second), "--state", str(state_path)])
    runner.invoke(app, ["index", "--state", str(state_path), "--all-vaults"])

    result = runner.invoke(app, ["search", "--state", str(state_path), "--vault-id", "second", "--format", "json", "GraphRAG"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert [item["vault_id"] for item in payload["results"]] == ["second"]
    assert "from second" in payload["results"][0]["summary"]
```

Append these service-level regressions to `tests/test_retrieval_service_search.py`:

```python
from dataclasses import replace


def _multi_vault_catalog(tmp_path: Path) -> VaultCatalog:
    first = tmp_path / "first-root"
    second = tmp_path / "second-root"
    first.mkdir()
    second.mkdir()
    return VaultCatalog.from_entries(
        entries=[
            VaultCatalogEntry.from_root(vault_id="first", root_path=first, content_scopes=("wiki",)),
            VaultCatalogEntry.from_root(vault_id="second", root_path=second, content_scopes=("docs",)),
        ],
        active_vault_id="first",
    )


def _hit(vault_id: str, document_id: str, chunk_id: str, rank: int) -> KeywordHit:
    return KeywordHit(
        vault_id=vault_id,
        document_id=document_id,
        chunk_id=chunk_id,
        rank=rank,
        score=-float(rank),
        backend="memory-keyword",
        index_revision="metadata-1",
        matched_fields=("text",),
    )


def test_all_vault_search_does_not_widen_content_scopes_per_vault(tmp_path: Path) -> None:
    catalog = _multi_vault_catalog(tmp_path)
    store = SQLiteMetadataStore(tmp_path / "metadata.sqlite3", initialize=True)
    first_allowed = make_document("first", "wiki/allowed.md", "first-allowed")
    first_leak = make_document("first", "docs/leak.md", "first-leak")
    second_allowed = make_document("second", "docs/allowed.md", "second-allowed")
    second_leak = make_document("second", "wiki/leak.md", "second-leak")
    documents = [first_allowed, first_leak, second_allowed, second_leak]
    chunks = [make_chunk(document.vault_id, document.document_id, document.path) for document in documents]
    store.apply_metadata_revision(index_revision="metadata-1", documents=documents, chunks=chunks, tombstones=[])
    keyword_hits = tuple(_hit(chunk.vault_id, chunk.document_id, chunk.chunk_id, rank) for rank, chunk in enumerate(chunks, start=1))
    content_scope_by_key = {
        (chunk.vault_id, chunk.chunk_id): chunk.path.split("/", 1)[0]
        for chunk in chunks
    }
    service = RetrievalService(
        catalog=catalog,
        metadata_store=store,
        keyword_index=InMemoryKeywordIndex(keyword_hits, content_scope_by_key=content_scope_by_key),
        readiness=StaticReadiness(ready_report(vector_ok=False, scope_key="first:wiki|second:docs")),
    )

    response = service.search(
        query_text="Body",
        requested_scope=catalog.scope_for_all_enabled(),
        limit=10,
        output_format="json",
    )

    assert tuple(scope.vault_ids for scope in response.actual_scopes) == (("first",), ("second",))
    assert tuple(scope.content_scopes for scope in response.actual_scopes) == (("wiki",), ("docs",))
    assert sorted(result.evidence[0].path for result in response.results) == ["docs/allowed.md", "wiki/allowed.md"]


def test_same_chunk_id_across_vaults_does_not_collapse_keyword_vector_fusion(tmp_path: Path) -> None:
    first = tmp_path / "first-root"
    second = tmp_path / "second-root"
    first.mkdir()
    second.mkdir()
    catalog = VaultCatalog.from_entries(
        entries=[
            VaultCatalogEntry.from_root(vault_id="first", root_path=first),
            VaultCatalogEntry.from_root(vault_id="second", root_path=second),
        ],
        active_vault_id="first",
    )
    store = SQLiteMetadataStore(tmp_path / "metadata.sqlite3", initialize=True)
    first_doc = make_document("first", "wiki/same.md", "first")
    second_doc = make_document("second", "wiki/same.md", "second")
    first_chunk = replace(make_chunk("first", first_doc.document_id, first_doc.path), chunk_id="shared-chunk", text="GraphRAG first")
    second_chunk = replace(make_chunk("second", second_doc.document_id, second_doc.path), chunk_id="shared-chunk", text="GraphRAG second")
    store.apply_metadata_revision(
        index_revision="metadata-1",
        documents=[first_doc, second_doc],
        chunks=[first_chunk, second_chunk],
        tombstones=[],
    )
    embeddings = DeterministicTextEmbeddings(SPEC)
    vector_store = InMemoryVectorStore()
    vector_records = []
    for chunk in (first_chunk, second_chunk):
        embedding = embeddings.embed((EmbeddingInput(input_id=f"{chunk.vault_id}:{chunk.chunk_id}", text=chunk.text),))[0]
        vector_records.append(
            VectorEmbeddingRecord(
                vector_id=stable_vector_id(vault_id=chunk.vault_id, chunk_id=chunk.chunk_id, embedding_spec=SPEC),
                vault_id=chunk.vault_id,
                document_id=chunk.document_id,
                chunk_id=chunk.chunk_id,
                content_scope="wiki",
                embedding=embedding,
                source_chunk_hash=chunk.content_hash,
                chunker_version=chunk.chunker_version,
                metadata_index_revision="metadata-1",
                vector_index_revision="vector-1",
                backend_schema_version="memory-vector-v1",
            )
        )
    vector_store.apply_vector_revision(vector_index_revision="vector-1", records=tuple(vector_records), tombstones=())
    service = RetrievalService(
        catalog=catalog,
        metadata_store=store,
        keyword_index=InMemoryKeywordIndex(
            (
                _hit("first", first_doc.document_id, "shared-chunk", 1),
                _hit("second", second_doc.document_id, "shared-chunk", 2),
            )
        ),
        vector_store=vector_store,
        text_embeddings=embeddings,
        readiness=StaticReadiness(ready_report(vector_ok=True, vector_stale_count=0, can_embed_without_download=True)),
    )

    response = service.search(
        query_text="GraphRAG",
        requested_scope=catalog.scope_for_all_enabled(),
        limit=10,
        output_format="json",
    )

    assert sorted((result.vault_id, result.evidence[0].chunk_id) for result in response.results) == [
        ("first", "shared-chunk"),
        ("second", "shared-chunk"),
    ]
    assert len({result.result_id for result in response.results}) == 2
    assert all(result.vault_id in signal.source_id for result in response.results for signal in result.signals)
```

- [ ] **Step 2: Run multi-vault tests**

Run:

```bash
uv run --python 3.12 pytest tests/test_multi_vault_search.py -q
```

Expected: PASS. If it fails, fix only the narrow bug shown by the test.

- [ ] **Step 3: Add mandatory result, warning, and store-revision attribution checks**

Extend the JSON assertions so missing attribution fails:

```python
assert all(item.get("scope_key") for item in payload["store_revisions"])
assert all(warning.get("affected_vault_ids") for warning in payload["warnings"])
assert all(item["vault_id"] in item["result_id"] for item in payload["results"])
```

Then update serialization or response assembly to satisfy it.

- [ ] **Step 4: Commit**

```bash
git add tests/test_multi_vault_search.py src/vault_graph/retrieval/retrieval_service.py src/vault_graph/cli/main.py src/vault_graph/storage/local/sqlite_keyword_index.py
git commit -m "test(search): cover multi-vault search identity"
```

Only include source files that actually changed.

---

### Task 10: Final Verification And Documentation Trace

**Files:**

- Modify if implementation review produced corrections: `docs/PATCH_LOG.md`
- Modify only with user-approved policy decisions: `docs/DECISIONS.md`
- No changes expected: `docs/SPEC.md`, `docs/DESIGN.md`, `docs/FEATURES.md`

- [ ] **Step 1: Run focused Phase 2C tests**

Run:

```bash
uv run --python 3.12 pytest \
  tests/test_keyword_index_contract.py \
  tests/test_sqlite_keyword_index.py \
  tests/test_query_scope_resolution.py \
  tests/test_search_response_contract.py \
  tests/test_app_search_readiness_service.py \
  tests/test_retrieval_import_boundaries.py \
  tests/test_retrieval_service_search.py \
  tests/test_chroma_vector_store.py \
  tests/test_cli_search.py \
  tests/test_search_read_only_boundary.py \
  tests/test_multi_vault_search.py \
  -q
```

Expected: PASS.

- [ ] **Step 2: Run full repository tests and static checks**

Run:

```bash
uv run --python 3.12 pytest -q
uv run --python 3.12 ruff check src tests
uv run --python 3.12 mypy src
uv run --python 3.12 mypy tests
git diff --check
```

Expected: all commands pass.

- [ ] **Step 3: Verify read-only behavior manually**

Run against a temporary Vault:

```bash
tmpdir="$(mktemp -d)"
mkdir -p "$tmpdir/vault/wiki"
printf '# Page\nGraphRAG evidence\n' > "$tmpdir/vault/wiki/page.md"
uv run --python 3.12 vg init --vault "$tmpdir/vault" --state "$tmpdir/state"
uv run --python 3.12 vg search --state "$tmpdir/state" "GraphRAG"
test ! -e "$tmpdir/state/metadata/metadata.sqlite3"
test ! -e "$tmpdir/state/vector/chroma/chroma.sqlite3"
uv run --python 3.12 vg index --state "$tmpdir/state"
uv run --python 3.12 vg search --state "$tmpdir/state" "GraphRAG"
```

Expected:

- search before indexing exits nonzero and does not create metadata/vector state
- index creates derived projections
- search after indexing exits zero and returns an evidence chunk
- Vault files under `$tmpdir/vault` are unchanged

- [ ] **Step 4: Update PATCH_LOG only if review or implementation required corrections**

If subagent or implementation review finds a plan/code correction, append this format to `docs/PATCH_LOG.md`:

```markdown
## 2026-06-09 - Phase 2C Implementation Plan Review Hardening

**Trigger:** Subagent review found implementation-plan gaps before coding.

**Scope:** `docs/superpowers/plans/2026-06-09-phase-2c-evidence-first-keyword-vector-search.md`.

**Core Values Protected:**

- search remains evidence-first
- `vg search` remains read-only
- keyword/vector stores remain candidate sources
- multi-vault identity remains explicit

**Changes Applied:**

- [specific correction]

**Verification:**

- subagent review focused on product/spec consistency
- subagent review focused on implementation readiness
- subagent review focused on multi-vault and read-only consistency
- `git diff --check`
```

Do not add this entry if no corrections were applied.

- [ ] **Step 5: Record user-approved decisions only if needed**

If a review identifies a decision that changes product policy, stop and ask the user. After approval, add a short entry to `docs/DECISIONS.md` using the existing format:

```markdown
## 2026-06-09 - [Decision Title]

**Question:** [one sentence]

**Decision:** [accepted decision]

**Reason:** [why it matters]

**Implications:**

- [guardrail]
```

Do not add implementation details, test plans, or review notes to `docs/DECISIONS.md`.

- [ ] **Step 6: Final commit**

```bash
git status --short
git add docs/superpowers/plans/2026-06-09-phase-2c-evidence-first-keyword-vector-search.md docs/PATCH_LOG.md docs/DECISIONS.md
git commit -m "docs: add phase 2c search implementation plan"
```

Only stage `docs/PATCH_LOG.md` or `docs/DECISIONS.md` if they changed.

## Implementation Review Checklist

Before marking Phase 2C implementation complete, verify every item below with current evidence:

- `vg search` exists in `uv run --python 3.12 vg --help`.
- `vg search "query"` uses active Vault by default.
- `vg search --vault-id ID "query"` searches exactly one Vault.
- `vg search --all-vaults "query"` expands enabled Vaults into per-Vault actual scopes.
- `--vault-id` and `--all-vaults` are mutually exclusive.
- `--limit` controls final result count.
- `--format json` returns the `SearchResponse` contract.
- Missing metadata or keyword projection exits nonzero and points to `vg index`.
- Missing vector state degrades to keyword-only with exit code `0` when keyword search is healthy.
- Search never initializes metadata SQLite state.
- Search never creates keyword FTS schema.
- Search never creates Chroma state when absent.
- Search never writes vector status.
- Search never downloads embedding model artifacts.
- Search resolves all normal results through `MetadataStore.resolve_chunk_evidence(...)`.
- Candidate dedupe uses `(vault_id, chunk_id)`.
- Result IDs and signal source IDs include Vault-scoped identity.
- Multi-vault JSON warnings include affected Vault IDs.
- Store revisions include metadata, keyword, and vector when available.
- Graph traversal, answer generation, context packs, MCP, and HTTP remain out of Phase 2C.

## Execution Handoff

Recommended execution mode:

1. Subagent-Driven: one implementation subagent per task, with review after each task.
2. Inline Execution: execute tasks in this session using `superpowers:executing-plans`, with review checkpoints after Tasks 2, 6, 8, and 10.

Use Subagent-Driven for this plan unless there is a strong reason to keep all edits in one session. The tasks have clean boundaries and frequent commits, which makes review and rollback straightforward.
