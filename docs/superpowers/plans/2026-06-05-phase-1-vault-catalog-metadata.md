# Phase 1 Vault Catalog And MetadataStore Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the first working Vault Graph slice: Python package scaffold, `VaultCatalog`, read-only Vault document loading, SQLite `MetadataStore`, scoped metadata indexing, and CLI commands for init, vault registration, index dry-run, index apply, and status.

**Architecture:** Keep the phase intentionally narrow. CLI calls application services; application services call indexing; indexing reads through ingestion and writes only derived state through `MetadataStore`. `VaultCatalog` is the only authority for `vault_id -> root_path`, while `MetadataStore` remains a rebuildable projection keyed by `vault_id`.

**Tech Stack:** Python 3.12, Typer CLI, PyYAML, SQLite from the standard library, pytest, ruff, mypy.

---

## Decision: No Extra Detailed Spec

Do not add another detailed specification before implementation. `docs/SPEC.md`,
`docs/DESIGN.md`, and `docs/FEATURES.md` already define the product contract,
architecture, user surfaces, and multi-vault invariants. Another spec document
would duplicate those contracts and increase drift risk.

Use this plan as the implementation bridge. Its scope is Phase 1 only:

- in scope: project scaffold, catalog, document ingestion, metadata projection,
  indexing plan/apply, CLI init/vault/index/status, read-only and multi-vault
  tests
- out of scope: vector search, graph extraction, hybrid retrieval, context pack
  generation, MCP server, HTTP server, UI

## File Structure

Create these files:

- `pyproject.toml`: package metadata, dependencies, CLI entrypoint, ruff and mypy settings
- `configs/vaults.yaml`: default catalog file shape
- `src/vault_graph/__init__.py`: package version
- `src/vault_graph/errors.py`: domain exceptions exposed across package boundaries
- `src/vault_graph/ingestion/__init__.py`: ingestion exports
- `src/vault_graph/ingestion/vault_catalog.py`: `VaultCatalogEntry`, `QueryScope`, `VaultCatalog`
- `src/vault_graph/ingestion/vault_frontmatter_reader.py`: YAML frontmatter projection and hash
- `src/vault_graph/ingestion/markdown_parser.py`: heading, anchor, and section parsing
- `src/vault_graph/ingestion/document_normalizer.py`: document and chunk snapshots
- `src/vault_graph/ingestion/vault_loader.py`: read-only scan of allowed Vault paths
- `src/vault_graph/storage/__init__.py`: storage package marker
- `src/vault_graph/storage/interfaces/__init__.py`: interface exports
- `src/vault_graph/storage/interfaces/store_health.py`: backend health records
- `src/vault_graph/storage/interfaces/metadata_store.py`: metadata store protocol and records
- `src/vault_graph/storage/local/__init__.py`: local backend exports
- `src/vault_graph/storage/local/sqlite_metadata_store.py`: SQLite metadata projection
- `src/vault_graph/indexing/__init__.py`: indexing exports
- `src/vault_graph/indexing/revision_planner.py`: changed/deleted/unchanged planning
- `src/vault_graph/indexing/metadata_indexer.py`: dry-run and apply for metadata only
- `src/vault_graph/app/__init__.py`: app service exports
- `src/vault_graph/app/catalog_service.py`: state directory and catalog file resolution
- `src/vault_graph/app/index_service.py`: CLI-facing index/status service
- `src/vault_graph/cli/__init__.py`: CLI package marker
- `src/vault_graph/cli/main.py`: Typer app and `vg` commands
- `tests/conftest.py`: temp Vault and CLI fixtures
- `tests/test_package_import.py`: scaffold import check
- `tests/test_vault_catalog.py`: catalog and scope behavior
- `tests/test_vault_loader.py`: read-only scanning and frontmatter projection
- `tests/test_document_normalizer.py`: document IDs, chunk IDs, anchors
- `tests/test_sqlite_metadata_store.py`: metadata persistence contract
- `tests/test_metadata_indexer.py`: dry-run/apply/tombstone behavior
- `tests/test_cli_catalog_metadata.py`: user-facing command behavior
- `tests/test_read_only_boundary.py`: Vault files unchanged after commands
- `tests/test_multi_vault_identity.py`: same relative path in two Vaults does not collide

Do not create vector, graph, retrieval, MCP, or HTTP implementation files in
this phase.

## Task 1: Package Scaffold

**Files:**

- Create: `pyproject.toml`
- Create: `src/vault_graph/__init__.py`
- Create: `src/vault_graph/errors.py`
- Create: package `__init__.py` files listed in File Structure
- Test: `tests/test_package_import.py`

- [ ] **Step 1: Write the failing import test**

Create `tests/test_package_import.py`:

```python
from vault_graph import __version__


def test_package_exposes_version() -> None:
    assert __version__ == "0.1.0"
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
uv run --python 3.12 pytest tests/test_package_import.py -q
```

Expected: FAIL with `ModuleNotFoundError: No module named 'vault_graph'`.

- [ ] **Step 3: Add package metadata**

Create `pyproject.toml`:

```toml
[build-system]
requires = ["hatchling>=1.25"]
build-backend = "hatchling.build"

[project]
name = "vault-graph"
version = "0.1.0"
description = "Read-only, rebuildable knowledge access layer over Vault."
requires-python = ">=3.12"
dependencies = [
  "PyYAML>=6.0.2",
  "typer>=0.12.5",
]

[project.optional-dependencies]
dev = [
  "mypy>=1.11",
  "pytest>=8.3",
  "ruff>=0.6",
]

[project.scripts]
vg = "vault_graph.cli.main:app"

[tool.hatch.build.targets.wheel]
packages = ["src/vault_graph"]

[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["src"]

[tool.ruff]
line-length = 120
target-version = "py312"

[tool.ruff.lint]
select = ["E", "F", "I", "UP", "B"]

[tool.mypy]
python_version = "3.12"
strict = true
mypy_path = "src"
```

Create `src/vault_graph/__init__.py`:

```python
__version__ = "0.1.0"
```

Create `src/vault_graph/errors.py`:

```python
class VaultGraphError(Exception):
    """Base error for Vault Graph domain failures."""


class CatalogError(VaultGraphError):
    """Raised when Vault catalog configuration is invalid."""


class ReadOnlyBoundaryError(VaultGraphError):
    """Raised when an operation would write to Vault content."""


class MetadataStoreError(VaultGraphError):
    """Raised when derived metadata state cannot be read or written."""
```

Create empty `__init__.py` files for the package directories in this phase.

- [ ] **Step 4: Run scaffold checks**

Run:

```bash
uv run --python 3.12 pytest tests/test_package_import.py -q
uv run --python 3.12 ruff check .
uv run --python 3.12 mypy src
```

Expected: import test passes; ruff passes; mypy passes.

- [ ] **Step 5: Commit scaffold**

Run:

```bash
git add pyproject.toml src/vault_graph tests/test_package_import.py
git commit -m "chore: scaffold vault graph package"
```

## Task 2: VaultCatalog And QueryScope

**Files:**

- Create: `configs/vaults.yaml`
- Create: `src/vault_graph/ingestion/vault_catalog.py`
- Test: `tests/test_vault_catalog.py`

- [ ] **Step 1: Write catalog behavior tests**

Create `tests/test_vault_catalog.py`:

```python
from pathlib import Path

import pytest

from vault_graph.errors import CatalogError
from vault_graph.ingestion.vault_catalog import QueryScope, VaultCatalog, VaultCatalogEntry


def test_catalog_uses_default_active_vault(tmp_path: Path) -> None:
    vault_root = tmp_path / "vault"
    vault_root.mkdir()

    catalog = VaultCatalog.from_entries(
        entries=[VaultCatalogEntry.from_root(vault_id="default", root_path=vault_root)],
        active_vault_id="default",
    )

    scope = catalog.default_scope()

    assert scope == QueryScope(vault_ids=("default",), content_scopes=("raw", "wiki", "docs", "scratch/reports"))
    assert catalog.resolve("default").root_path == vault_root.resolve()


def test_duplicate_vault_ids_are_rejected(tmp_path: Path) -> None:
    vault_root = tmp_path / "vault"
    vault_root.mkdir()
    entry = VaultCatalogEntry.from_root(vault_id="main", root_path=vault_root)

    with pytest.raises(CatalogError, match="duplicate vault_id"):
        VaultCatalog.from_entries(entries=[entry, entry], active_vault_id="main")


def test_all_vaults_expands_only_enabled_entries(tmp_path: Path) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"
    third = tmp_path / "third"
    first.mkdir()
    second.mkdir()
    third.mkdir()

    catalog = VaultCatalog.from_entries(
        entries=[
            VaultCatalogEntry.from_root(vault_id="first", root_path=first),
            VaultCatalogEntry.from_root(vault_id="second", root_path=second),
            VaultCatalogEntry.from_root(vault_id="third", root_path=third, enabled=False),
        ],
        active_vault_id="first",
    )

    assert catalog.scope_for_all_enabled().vault_ids == ("first", "second")


def test_explicit_scope_rejects_unknown_vault_id(tmp_path: Path) -> None:
    vault_root = tmp_path / "vault"
    vault_root.mkdir()
    catalog = VaultCatalog.from_entries(
        entries=[VaultCatalogEntry.from_root(vault_id="default", root_path=vault_root)],
        active_vault_id="default",
    )

    with pytest.raises(CatalogError, match="unknown vault_id"):
        catalog.scope_for_vault_ids(["missing"])
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
uv run --python 3.12 pytest tests/test_vault_catalog.py -q
```

Expected: FAIL because `vault_graph.ingestion.vault_catalog` does not exist.

- [ ] **Step 3: Implement catalog records and scope expansion**

Create `configs/vaults.yaml`:

```yaml
active_vault_id: default
vaults:
  - vault_id: default
    root_path: /absolute/path/to/vault
    display_name: Default Vault
    enabled: true
    content_scopes:
      - raw
      - wiki
      - docs
      - scratch/reports
    state_namespace: default
    git_revision_policy: head
```

Create `src/vault_graph/ingestion/vault_catalog.py` with this public API:

```python
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import yaml

from vault_graph.errors import CatalogError

DEFAULT_CONTENT_SCOPES = ("raw", "wiki", "docs", "scratch/reports")


@dataclass(frozen=True)
class QueryScope:
    vault_ids: tuple[str, ...]
    content_scopes: tuple[str, ...] = DEFAULT_CONTENT_SCOPES
    include_cross_vault: bool = False


@dataclass(frozen=True)
class VaultCatalogEntry:
    vault_id: str
    root_path: Path
    display_name: str
    enabled: bool
    content_scopes: tuple[str, ...]
    state_namespace: str
    git_revision_policy: str

    @classmethod
    def from_root(
        cls,
        *,
        vault_id: str,
        root_path: Path,
        display_name: str | None = None,
        enabled: bool = True,
        content_scopes: Iterable[str] = DEFAULT_CONTENT_SCOPES,
        state_namespace: str | None = None,
        git_revision_policy: str = "head",
    ) -> "VaultCatalogEntry":
        if not vault_id:
            raise CatalogError("vault_id is required")
        resolved_root = root_path.expanduser().resolve()
        if not resolved_root.exists() or not resolved_root.is_dir():
            raise CatalogError(f"vault root does not exist: {resolved_root}")
        return cls(
            vault_id=vault_id,
            root_path=resolved_root,
            display_name=display_name or vault_id,
            enabled=enabled,
            content_scopes=tuple(content_scopes),
            state_namespace=state_namespace or vault_id,
            git_revision_policy=git_revision_policy,
        )


class VaultCatalog:
    def __init__(self, *, entries: tuple[VaultCatalogEntry, ...], active_vault_id: str) -> None:
        self._entries = entries
        self._active_vault_id = active_vault_id
        self._by_id = {entry.vault_id: entry for entry in entries}
        if len(self._by_id) != len(entries):
            raise CatalogError("duplicate vault_id in VaultCatalog")
        if active_vault_id not in self._by_id:
            raise CatalogError(f"active vault_id is not registered: {active_vault_id}")

    @classmethod
    def from_entries(cls, *, entries: Iterable[VaultCatalogEntry], active_vault_id: str) -> "VaultCatalog":
        return cls(entries=tuple(entries), active_vault_id=active_vault_id)

    @classmethod
    def load(cls, path: Path) -> "VaultCatalog":
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        entries = [
            VaultCatalogEntry.from_root(
                vault_id=item["vault_id"],
                root_path=Path(item["root_path"]),
                display_name=item.get("display_name"),
                enabled=bool(item.get("enabled", True)),
                content_scopes=item.get("content_scopes", DEFAULT_CONTENT_SCOPES),
                state_namespace=item.get("state_namespace"),
                git_revision_policy=item.get("git_revision_policy", "head"),
            )
            for item in data.get("vaults", [])
        ]
        return cls.from_entries(entries=entries, active_vault_id=data.get("active_vault_id", "default"))

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        payload: dict[str, Any] = {
            "active_vault_id": self._active_vault_id,
            "vaults": [
                {
                    "vault_id": entry.vault_id,
                    "root_path": str(entry.root_path),
                    "display_name": entry.display_name,
                    "enabled": entry.enabled,
                    "content_scopes": list(entry.content_scopes),
                    "state_namespace": entry.state_namespace,
                    "git_revision_policy": entry.git_revision_policy,
                }
                for entry in self._entries
            ],
        }
        path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")

    @property
    def active_vault_id(self) -> str:
        return self._active_vault_id

    def entries(self) -> tuple[VaultCatalogEntry, ...]:
        return self._entries

    def resolve(self, vault_id: str) -> VaultCatalogEntry:
        try:
            return self._by_id[vault_id]
        except KeyError as exc:
            raise CatalogError(f"unknown vault_id: {vault_id}") from exc

    def default_scope(self) -> QueryScope:
        entry = self.resolve(self._active_vault_id)
        return QueryScope(vault_ids=(entry.vault_id,), content_scopes=entry.content_scopes)

    def scope_for_vault_ids(self, vault_ids: Iterable[str]) -> QueryScope:
        entries = tuple(self.resolve(vault_id) for vault_id in vault_ids)
        content_scopes = tuple(dict.fromkeys(scope for entry in entries for scope in entry.content_scopes))
        return QueryScope(vault_ids=tuple(entry.vault_id for entry in entries), content_scopes=content_scopes)

    def scope_for_all_enabled(self) -> QueryScope:
        enabled = tuple(entry for entry in self._entries if entry.enabled)
        if not enabled:
            raise CatalogError("no enabled VaultCatalog entries")
        return QueryScope(vault_ids=tuple(entry.vault_id for entry in enabled), content_scopes=DEFAULT_CONTENT_SCOPES)
```

- [ ] **Step 4: Run catalog tests**

Run:

```bash
uv run --python 3.12 pytest tests/test_vault_catalog.py -q
uv run --python 3.12 ruff check src tests
uv run --python 3.12 mypy src
```

Expected: tests pass; ruff passes; mypy passes.

- [ ] **Step 5: Commit catalog**

Run:

```bash
git add configs/vaults.yaml src/vault_graph/ingestion/vault_catalog.py tests/test_vault_catalog.py
git commit -m "feat: add vault catalog"
```

## Task 3: Read-Only Vault Loading

**Files:**

- Create: `src/vault_graph/ingestion/vault_frontmatter_reader.py`
- Create: `src/vault_graph/ingestion/vault_loader.py`
- Test: `tests/test_vault_loader.py`

- [ ] **Step 1: Write loader tests**

Create `tests/test_vault_loader.py`:

```python
from pathlib import Path

from vault_graph.ingestion.vault_catalog import QueryScope, VaultCatalogEntry
from vault_graph.ingestion.vault_loader import VaultLoader


def test_loader_reads_allowed_markdown_paths(tmp_path: Path) -> None:
    vault_root = tmp_path / "vault"
    (vault_root / "wiki").mkdir(parents=True)
    (vault_root / "data").mkdir()
    (vault_root / "wiki" / "systems.md").write_text("---\ntitle: Systems\n---\n# Systems\nBody\n", encoding="utf-8")
    (vault_root / "data" / "derived.md").write_text("# Derived\n", encoding="utf-8")

    entry = VaultCatalogEntry.from_root(vault_id="default", root_path=vault_root)
    loader = VaultLoader()

    documents = loader.load_documents(entry=entry, scope=QueryScope(vault_ids=("default",), content_scopes=("wiki",)))

    assert [document.path for document in documents] == ("wiki/systems.md",)
    assert documents[0].vault_id == "default"
    assert documents[0].frontmatter.data == {"title": "Systems"}


def test_loader_does_not_modify_vault_files(tmp_path: Path) -> None:
    vault_root = tmp_path / "vault"
    (vault_root / "raw").mkdir(parents=True)
    note = vault_root / "raw" / "note.md"
    note.write_text("# Note\n", encoding="utf-8")
    before = note.read_bytes()

    entry = VaultCatalogEntry.from_root(vault_id="default", root_path=vault_root)
    loader = VaultLoader()
    loader.load_documents(entry=entry, scope=QueryScope(vault_ids=("default",), content_scopes=("raw",)))

    assert note.read_bytes() == before
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
uv run --python 3.12 pytest tests/test_vault_loader.py -q
```

Expected: FAIL because `VaultLoader` does not exist.

- [ ] **Step 3: Implement frontmatter projection**

Create `src/vault_graph/ingestion/vault_frontmatter_reader.py`:

```python
from __future__ import annotations

import hashlib
from dataclasses import dataclass

import yaml


@dataclass(frozen=True)
class FrontmatterProjection:
    data: dict[str, object]
    body: str
    frontmatter_hash: str


def read_frontmatter(text: str) -> FrontmatterProjection:
    if not text.startswith("---\n"):
        return FrontmatterProjection(data={}, body=text, frontmatter_hash=hashlib.sha256(b"").hexdigest())

    closing = text.find("\n---\n", 4)
    if closing == -1:
        return FrontmatterProjection(data={}, body=text, frontmatter_hash=hashlib.sha256(b"").hexdigest())

    raw_frontmatter = text[4:closing]
    parsed = yaml.safe_load(raw_frontmatter) or {}
    data = parsed if isinstance(parsed, dict) else {}
    body = text[closing + len("\n---\n") :]
    digest = hashlib.sha256(raw_frontmatter.encode("utf-8")).hexdigest()
    return FrontmatterProjection(data=data, body=body, frontmatter_hash=digest)
```

- [ ] **Step 4: Implement read-only Vault loader**

Create `src/vault_graph/ingestion/vault_loader.py`:

```python
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

from vault_graph.ingestion.vault_catalog import QueryScope, VaultCatalogEntry
from vault_graph.ingestion.vault_frontmatter_reader import FrontmatterProjection, read_frontmatter


@dataclass(frozen=True)
class LoadedVaultDocument:
    vault_id: str
    root_path: Path
    path: str
    text: str
    raw_sha256: str
    content_hash: str
    frontmatter: FrontmatterProjection


class VaultLoader:
    def load_documents(self, *, entry: VaultCatalogEntry, scope: QueryScope) -> tuple[LoadedVaultDocument, ...]:
        documents: list[LoadedVaultDocument] = []
        for content_scope in scope.content_scopes:
            scope_root = entry.root_path / content_scope
            if not scope_root.exists():
                continue
            for markdown_path in sorted(scope_root.rglob("*.md")):
                if not markdown_path.is_file():
                    continue
                relative_path = markdown_path.relative_to(entry.root_path).as_posix()
                text = markdown_path.read_text(encoding="utf-8")
                raw_sha256 = hashlib.sha256(text.encode("utf-8")).hexdigest()
                frontmatter = read_frontmatter(text)
                content_hash = hashlib.sha256(frontmatter.body.encode("utf-8")).hexdigest()
                documents.append(
                    LoadedVaultDocument(
                        vault_id=entry.vault_id,
                        root_path=entry.root_path,
                        path=relative_path,
                        text=text,
                        raw_sha256=raw_sha256,
                        content_hash=content_hash,
                        frontmatter=frontmatter,
                    )
                )
        return tuple(documents)
```

- [ ] **Step 5: Run loader tests**

Run:

```bash
uv run --python 3.12 pytest tests/test_vault_loader.py -q
uv run --python 3.12 ruff check src tests
uv run --python 3.12 mypy src
```

Expected: tests pass; ruff passes; mypy passes.

- [ ] **Step 6: Commit loader**

Run:

```bash
git add src/vault_graph/ingestion/vault_frontmatter_reader.py src/vault_graph/ingestion/vault_loader.py tests/test_vault_loader.py
git commit -m "feat: add read-only vault loader"
```

## Task 4: Document Normalization And Chunking

**Files:**

- Create: `src/vault_graph/ingestion/markdown_parser.py`
- Create: `src/vault_graph/ingestion/document_normalizer.py`
- Test: `tests/test_document_normalizer.py`

- [ ] **Step 1: Write normalization tests**

Create `tests/test_document_normalizer.py`:

```python
from pathlib import Path

from vault_graph.ingestion.document_normalizer import DocumentNormalizer
from vault_graph.ingestion.vault_frontmatter_reader import read_frontmatter
from vault_graph.ingestion.vault_loader import LoadedVaultDocument


def test_document_and_chunk_ids_are_vault_scoped(tmp_path: Path) -> None:
    text = "---\ntitle: Same\n---\n# Same Title\nBody\n"
    frontmatter = read_frontmatter(text)
    first = LoadedVaultDocument(
        vault_id="first",
        root_path=tmp_path / "first",
        path="wiki/same.md",
        text=text,
        raw_sha256="raw-first",
        content_hash="content",
        frontmatter=frontmatter,
    )
    second = LoadedVaultDocument(
        vault_id="second",
        root_path=tmp_path / "second",
        path="wiki/same.md",
        text=text,
        raw_sha256="raw-second",
        content_hash="content",
        frontmatter=frontmatter,
    )

    normalizer = DocumentNormalizer()
    first_snapshot = normalizer.normalize(first)
    second_snapshot = normalizer.normalize(second)

    assert first_snapshot.document.document_id != second_snapshot.document.document_id
    assert first_snapshot.chunks[0].chunk_id != second_snapshot.chunks[0].chunk_id
    assert first_snapshot.chunks[0].anchor == "same-title"


def test_document_normalizer_preserves_vault_id_and_path(tmp_path: Path) -> None:
    text = "# Decision\nWe chose local-first indexing.\n"
    loaded = LoadedVaultDocument(
        vault_id="default",
        root_path=tmp_path,
        path="wiki/decisions/local-first.md",
        text=text,
        raw_sha256="raw",
        content_hash="content",
        frontmatter=read_frontmatter(text),
    )

    snapshot = DocumentNormalizer().normalize(loaded)

    assert snapshot.document.vault_id == "default"
    assert snapshot.document.path == "wiki/decisions/local-first.md"
    assert snapshot.chunks[0].text == "We chose local-first indexing."
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
uv run --python 3.12 pytest tests/test_document_normalizer.py -q
```

Expected: FAIL because `DocumentNormalizer` does not exist.

- [ ] **Step 3: Implement markdown section parsing**

Create `src/vault_graph/ingestion/markdown_parser.py`:

```python
from __future__ import annotations

import re
from dataclasses import dataclass

HEADING_PATTERN = re.compile(r"^(#{1,6})\s+(.+)$", re.MULTILINE)


@dataclass(frozen=True)
class MarkdownSection:
    heading: str | None
    anchor: str | None
    text: str


def make_anchor(heading: str) -> str:
    lowered = heading.strip().lower()
    slug = re.sub(r"[^a-z0-9가-힣]+", "-", lowered).strip("-")
    return slug or "section"


def parse_sections(markdown_body: str) -> tuple[MarkdownSection, ...]:
    matches = list(HEADING_PATTERN.finditer(markdown_body))
    if not matches:
        stripped = markdown_body.strip()
        return (MarkdownSection(heading=None, anchor=None, text=stripped),) if stripped else ()

    sections: list[MarkdownSection] = []
    for index, match in enumerate(matches):
        heading = match.group(2).strip()
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(markdown_body)
        section_text = markdown_body[start:end].strip()
        if section_text:
            sections.append(MarkdownSection(heading=heading, anchor=make_anchor(heading), text=section_text))
    return tuple(sections)
```

- [ ] **Step 4: Implement normalized document and chunk records**

Create `src/vault_graph/ingestion/document_normalizer.py`:

```python
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from vault_graph.ingestion.markdown_parser import parse_sections
from vault_graph.ingestion.vault_loader import LoadedVaultDocument

PARSER_VERSION = "markdown-frontmatter-v1"
CHUNKER_VERSION = "heading-section-v1"


@dataclass(frozen=True)
class DocumentSnapshot:
    vault_id: str
    document_id: str
    path: str
    kind: str
    frontmatter: dict[str, Any]
    frontmatter_hash: str
    content_hash: str
    raw_sha256: str
    parser_version: str
    last_seen_at: str
    last_indexed_at: str | None
    vault_revision: str | None
    index_revision: str | None


@dataclass(frozen=True)
class ChunkSnapshot:
    vault_id: str
    chunk_id: str
    document_id: str
    path: str
    section: str | None
    anchor: str | None
    text: str
    token_count: int
    content_hash: str
    chunker_version: str
    index_revision: str | None


@dataclass(frozen=True)
class NormalizedDocument:
    document: DocumentSnapshot
    chunks: tuple[ChunkSnapshot, ...]


def stable_id(*parts: str) -> str:
    return hashlib.sha256(":".join(parts).encode("utf-8")).hexdigest()


class DocumentNormalizer:
    def normalize(self, loaded: LoadedVaultDocument) -> NormalizedDocument:
        now = datetime.now(UTC).isoformat()
        document_id = stable_id("document", loaded.vault_id, loaded.path)
        document = DocumentSnapshot(
            vault_id=loaded.vault_id,
            document_id=document_id,
            path=loaded.path,
            kind=loaded.path.split("/", 1)[0],
            frontmatter=dict(loaded.frontmatter.data),
            frontmatter_hash=loaded.frontmatter.frontmatter_hash,
            content_hash=loaded.content_hash,
            raw_sha256=loaded.raw_sha256,
            parser_version=PARSER_VERSION,
            last_seen_at=now,
            last_indexed_at=None,
            vault_revision=None,
            index_revision=None,
        )
        chunks = tuple(
            ChunkSnapshot(
                vault_id=loaded.vault_id,
                chunk_id=stable_id("chunk", loaded.vault_id, loaded.path, section.anchor or str(index)),
                document_id=document_id,
                path=loaded.path,
                section=section.heading,
                anchor=section.anchor,
                text=section.text,
                token_count=len(section.text.split()),
                content_hash=stable_id("chunk-content", section.text),
                chunker_version=CHUNKER_VERSION,
                index_revision=None,
            )
            for index, section in enumerate(parse_sections(loaded.frontmatter.body))
        )
        return NormalizedDocument(document=document, chunks=chunks)
```

- [ ] **Step 5: Run normalization tests**

Run:

```bash
uv run --python 3.12 pytest tests/test_document_normalizer.py -q
uv run --python 3.12 ruff check src tests
uv run --python 3.12 mypy src
```

Expected: tests pass; ruff passes; mypy passes.

- [ ] **Step 6: Commit normalizer**

Run:

```bash
git add src/vault_graph/ingestion/markdown_parser.py src/vault_graph/ingestion/document_normalizer.py tests/test_document_normalizer.py
git commit -m "feat: normalize vault documents"
```

## Task 5: SQLite MetadataStore

**Files:**

- Create: `src/vault_graph/storage/interfaces/store_health.py`
- Create: `src/vault_graph/storage/interfaces/metadata_store.py`
- Create: `src/vault_graph/storage/local/sqlite_metadata_store.py`
- Test: `tests/test_sqlite_metadata_store.py`

- [ ] **Step 1: Write metadata store contract tests**

Create `tests/test_sqlite_metadata_store.py`:

```python
from pathlib import Path

from vault_graph.ingestion.document_normalizer import ChunkSnapshot, DocumentSnapshot
from vault_graph.storage.local.sqlite_metadata_store import SQLiteMetadataStore


def make_document(vault_id: str, path: str, content_hash: str) -> DocumentSnapshot:
    return DocumentSnapshot(
        vault_id=vault_id,
        document_id=f"{vault_id}:{path}",
        path=path,
        kind=path.split("/", 1)[0],
        frontmatter={},
        frontmatter_hash="frontmatter",
        content_hash=content_hash,
        raw_sha256=f"raw:{content_hash}",
        parser_version="parser",
        last_seen_at="2026-06-05T00:00:00+00:00",
        last_indexed_at=None,
        vault_revision=None,
        index_revision=None,
    )


def make_chunk(vault_id: str, document_id: str, path: str) -> ChunkSnapshot:
    return ChunkSnapshot(
        vault_id=vault_id,
        chunk_id=f"{vault_id}:{path}:chunk",
        document_id=document_id,
        path=path,
        section="Section",
        anchor="section",
        text="Body",
        token_count=1,
        content_hash="chunk",
        chunker_version="chunker",
        index_revision=None,
    )


def test_store_upserts_and_resolves_document(tmp_path: Path) -> None:
    store = SQLiteMetadataStore(tmp_path / "metadata.sqlite3")
    document = make_document("default", "wiki/page.md", "hash-1")
    chunk = make_chunk("default", document.document_id, document.path)

    store.apply_metadata_revision(index_revision="rev-1", documents=[document], chunks=[chunk], tombstones=[])

    resolved = store.resolve_document(document_id=document.document_id)
    assert resolved is not None
    assert resolved.vault_id == "default"
    assert resolved.path == "wiki/page.md"
    assert store.health().ok is True


def test_store_keeps_same_relative_path_separate_by_vault_id(tmp_path: Path) -> None:
    store = SQLiteMetadataStore(tmp_path / "metadata.sqlite3")
    first = make_document("first", "wiki/same.md", "hash-first")
    second = make_document("second", "wiki/same.md", "hash-second")

    store.apply_metadata_revision(index_revision="rev-1", documents=[first, second], chunks=[], tombstones=[])

    assert store.resolve_document(document_id=first.document_id).content_hash == "hash-first"
    assert store.resolve_document(document_id=second.document_id).content_hash == "hash-second"


def test_store_tombstones_only_named_vault_and_path(tmp_path: Path) -> None:
    store = SQLiteMetadataStore(tmp_path / "metadata.sqlite3")
    first = make_document("first", "wiki/same.md", "hash-first")
    second = make_document("second", "wiki/same.md", "hash-second")
    store.apply_metadata_revision(index_revision="rev-1", documents=[first, second], chunks=[], tombstones=[])

    store.apply_metadata_revision(index_revision="rev-2", documents=[], chunks=[], tombstones=[("first", "wiki/same.md")])

    assert store.document_state("first", "wiki/same.md").is_tombstoned is True
    assert store.document_state("second", "wiki/same.md").is_tombstoned is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
uv run --python 3.12 pytest tests/test_sqlite_metadata_store.py -q
```

Expected: FAIL because `SQLiteMetadataStore` does not exist.

- [ ] **Step 3: Define store health and metadata interface**

Create `src/vault_graph/storage/interfaces/store_health.py`:

```python
from dataclasses import dataclass


@dataclass(frozen=True)
class StoreHealth:
    ok: bool
    backend: str
    schema_version: str
    message: str
```

Create `src/vault_graph/storage/interfaces/metadata_store.py`:

```python
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from vault_graph.ingestion.document_normalizer import ChunkSnapshot, DocumentSnapshot
from vault_graph.storage.interfaces.store_health import StoreHealth


@dataclass(frozen=True)
class DocumentState:
    vault_id: str
    path: str
    document_id: str | None
    content_hash: str | None
    raw_sha256: str | None
    parser_version: str | None
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

    def health(self) -> StoreHealth: ...
```

- [ ] **Step 4: Implement SQLite metadata projection**

Create `src/vault_graph/storage/local/sqlite_metadata_store.py` with these tables:

```python
SCHEMA_VERSION = "metadata-v1"

SCHEMA = """
CREATE TABLE IF NOT EXISTS documents (
  vault_id TEXT NOT NULL,
  document_id TEXT NOT NULL,
  path TEXT NOT NULL,
  kind TEXT NOT NULL,
  frontmatter_json TEXT NOT NULL,
  frontmatter_hash TEXT NOT NULL,
  content_hash TEXT NOT NULL,
  raw_sha256 TEXT NOT NULL,
  parser_version TEXT NOT NULL,
  last_seen_at TEXT NOT NULL,
  last_indexed_at TEXT,
  vault_revision TEXT,
  index_revision TEXT,
  is_tombstoned INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY (vault_id, path),
  UNIQUE (document_id)
);

CREATE TABLE IF NOT EXISTS chunks (
  vault_id TEXT NOT NULL,
  chunk_id TEXT NOT NULL,
  document_id TEXT NOT NULL,
  path TEXT NOT NULL,
  section TEXT,
  anchor TEXT,
  text TEXT NOT NULL,
  token_count INTEGER NOT NULL,
  content_hash TEXT NOT NULL,
  chunker_version TEXT NOT NULL,
  index_revision TEXT,
  PRIMARY KEY (vault_id, chunk_id)
);

CREATE TABLE IF NOT EXISTS index_revisions (
  index_revision TEXT PRIMARY KEY,
  created_at TEXT NOT NULL
);
"""
```

The class must expose:

```python
class SQLiteMetadataStore:
    def __init__(self, database_path: Path) -> None: ...

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

    def health(self) -> StoreHealth: ...
```

Implementation requirements:

- create parent directory for the SQLite database path
- create schema in `__init__`
- serialize frontmatter with `json.dumps(..., sort_keys=True)`
- set `is_tombstoned=0` when upserting a document
- set `is_tombstoned=1` only for the exact `(vault_id, path)` tombstone pair
- never store or infer Vault root paths
- never write outside the SQLite database path

- [ ] **Step 5: Run metadata store tests**

Run:

```bash
uv run --python 3.12 pytest tests/test_sqlite_metadata_store.py -q
uv run --python 3.12 ruff check src tests
uv run --python 3.12 mypy src
```

Expected: tests pass; ruff passes; mypy passes.

- [ ] **Step 6: Commit metadata store**

Run:

```bash
git add src/vault_graph/storage tests/test_sqlite_metadata_store.py
git commit -m "feat: add sqlite metadata store"
```

## Task 6: Metadata Index Planning And Apply

**Files:**

- Create: `src/vault_graph/indexing/revision_planner.py`
- Create: `src/vault_graph/indexing/metadata_indexer.py`
- Test: `tests/test_metadata_indexer.py`

- [ ] **Step 1: Write indexer tests**

Create `tests/test_metadata_indexer.py`:

```python
from pathlib import Path

from vault_graph.indexing.metadata_indexer import MetadataIndexer
from vault_graph.ingestion.vault_catalog import VaultCatalog, VaultCatalogEntry
from vault_graph.storage.local.sqlite_metadata_store import SQLiteMetadataStore


def make_vault(root: Path, body: str = "# Page\nBody\n") -> None:
    (root / "wiki").mkdir(parents=True)
    (root / "wiki" / "page.md").write_text(body, encoding="utf-8")


def test_dry_run_reports_changes_without_writing_store(tmp_path: Path) -> None:
    vault_root = tmp_path / "vault"
    make_vault(vault_root)
    catalog = VaultCatalog.from_entries(
        entries=[VaultCatalogEntry.from_root(vault_id="default", root_path=vault_root)],
        active_vault_id="default",
    )
    store = SQLiteMetadataStore(tmp_path / "state" / "metadata.sqlite3")

    plan = MetadataIndexer(catalog=catalog, metadata_store=store).plan(scope=catalog.default_scope())

    assert plan.changed_paths == (("default", "wiki/page.md"),)
    assert store.list_document_states(("default",)) == ()


def test_apply_writes_metadata_projection(tmp_path: Path) -> None:
    vault_root = tmp_path / "vault"
    make_vault(vault_root)
    catalog = VaultCatalog.from_entries(
        entries=[VaultCatalogEntry.from_root(vault_id="default", root_path=vault_root)],
        active_vault_id="default",
    )
    store = SQLiteMetadataStore(tmp_path / "state" / "metadata.sqlite3")

    result = MetadataIndexer(catalog=catalog, metadata_store=store).apply(scope=catalog.default_scope())

    assert result.index_revision.startswith("metadata-")
    assert store.document_state("default", "wiki/page.md").is_tombstoned is False


def test_scoped_apply_does_not_tombstone_other_vaults(tmp_path: Path) -> None:
    first_root = tmp_path / "first"
    second_root = tmp_path / "second"
    make_vault(first_root, "# First\nBody\n")
    make_vault(second_root, "# Second\nBody\n")
    catalog = VaultCatalog.from_entries(
        entries=[
            VaultCatalogEntry.from_root(vault_id="first", root_path=first_root),
            VaultCatalogEntry.from_root(vault_id="second", root_path=second_root),
        ],
        active_vault_id="first",
    )
    store = SQLiteMetadataStore(tmp_path / "state" / "metadata.sqlite3")
    indexer = MetadataIndexer(catalog=catalog, metadata_store=store)
    indexer.apply(scope=catalog.scope_for_all_enabled())

    (first_root / "wiki" / "page.md").unlink()
    indexer.apply(scope=catalog.scope_for_vault_ids(["first"]))

    assert store.document_state("first", "wiki/page.md").is_tombstoned is True
    assert store.document_state("second", "wiki/page.md").is_tombstoned is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
uv run --python 3.12 pytest tests/test_metadata_indexer.py -q
```

Expected: FAIL because `MetadataIndexer` does not exist.

- [ ] **Step 3: Implement revision plan records**

Create `src/vault_graph/indexing/revision_planner.py`:

```python
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class MetadataRevisionPlan:
    index_revision: str
    vault_ids: tuple[str, ...]
    changed_paths: tuple[tuple[str, str], ...]
    unchanged_paths: tuple[tuple[str, str], ...]
    deleted_paths: tuple[tuple[str, str], ...]
    warnings: tuple[str, ...]
```

- [ ] **Step 4: Implement metadata indexer**

Create `src/vault_graph/indexing/metadata_indexer.py` with this public API:

```python
from __future__ import annotations

from datetime import UTC, datetime

from vault_graph.indexing.revision_planner import MetadataRevisionPlan
from vault_graph.ingestion.document_normalizer import DocumentNormalizer, NormalizedDocument
from vault_graph.ingestion.vault_catalog import QueryScope, VaultCatalog
from vault_graph.ingestion.vault_loader import VaultLoader
from vault_graph.storage.interfaces.metadata_store import MetadataStore


class MetadataIndexer:
    def __init__(self, *, catalog: VaultCatalog, metadata_store: MetadataStore) -> None:
        self._catalog = catalog
        self._metadata_store = metadata_store
        self._loader = VaultLoader()
        self._normalizer = DocumentNormalizer()

    def plan(self, *, scope: QueryScope) -> MetadataRevisionPlan:
        index_revision = f"metadata-{datetime.now(UTC).strftime('%Y%m%d%H%M%S%f')}"
        normalized = self._load_normalized(scope)
        current_by_key = {(state.vault_id, state.path): state for state in self._metadata_store.list_document_states(scope.vault_ids)}
        loaded_by_key = {(item.document.vault_id, item.document.path): item for item in normalized}
        changed: list[tuple[str, str]] = []
        unchanged: list[tuple[str, str]] = []
        for key, item in loaded_by_key.items():
            current = current_by_key.get(key)
            if current is None or current.content_hash != item.document.content_hash or current.is_tombstoned:
                changed.append(key)
            else:
                unchanged.append(key)
        deleted = [key for key in current_by_key if key not in loaded_by_key]
        return MetadataRevisionPlan(
            index_revision=index_revision,
            vault_ids=scope.vault_ids,
            changed_paths=tuple(sorted(changed)),
            unchanged_paths=tuple(sorted(unchanged)),
            deleted_paths=tuple(sorted(deleted)),
            warnings=(),
        )

    def apply(self, *, scope: QueryScope) -> MetadataRevisionPlan:
        plan = self.plan(scope=scope)
        normalized = self._load_normalized(scope)
        changed_keys = set(plan.changed_paths)
        changed_documents = [item.document for item in normalized if (item.document.vault_id, item.document.path) in changed_keys]
        changed_chunks = [
            chunk
            for item in normalized
            if (item.document.vault_id, item.document.path) in changed_keys
            for chunk in item.chunks
        ]
        self._metadata_store.apply_metadata_revision(
            index_revision=plan.index_revision,
            documents=changed_documents,
            chunks=changed_chunks,
            tombstones=list(plan.deleted_paths),
        )
        return plan

    def _load_normalized(self, scope: QueryScope) -> tuple[NormalizedDocument, ...]:
        normalized: list[NormalizedDocument] = []
        for vault_id in scope.vault_ids:
            entry = self._catalog.resolve(vault_id)
            for loaded in self._loader.load_documents(entry=entry, scope=scope):
                normalized.append(self._normalizer.normalize(loaded))
        return tuple(normalized)
```

- [ ] **Step 5: Run indexer tests**

Run:

```bash
uv run --python 3.12 pytest tests/test_metadata_indexer.py -q
uv run --python 3.12 ruff check src tests
uv run --python 3.12 mypy src
```

Expected: tests pass; ruff passes; mypy passes.

- [ ] **Step 6: Commit indexer**

Run:

```bash
git add src/vault_graph/indexing tests/test_metadata_indexer.py
git commit -m "feat: add metadata indexer"
```

## Task 7: App Services And CLI

**Files:**

- Create: `src/vault_graph/app/catalog_service.py`
- Create: `src/vault_graph/app/index_service.py`
- Create: `src/vault_graph/cli/main.py`
- Test: `tests/test_cli_catalog_metadata.py`

- [ ] **Step 1: Write CLI tests**

Create `tests/test_cli_catalog_metadata.py`:

```python
from pathlib import Path

from typer.testing import CliRunner

from vault_graph.cli.main import app

runner = CliRunner()


def test_cli_init_creates_default_catalog(tmp_path: Path) -> None:
    vault_root = tmp_path / "vault"
    vault_root.mkdir()
    state_path = tmp_path / "state"

    result = runner.invoke(app, ["init", "--vault", str(vault_root), "--state", str(state_path)])

    assert result.exit_code == 0
    assert "default" in result.stdout
    assert (state_path / "configs" / "vaults.yaml").exists()


def test_cli_index_dry_run_reports_scope(tmp_path: Path) -> None:
    vault_root = tmp_path / "vault"
    (vault_root / "wiki").mkdir(parents=True)
    (vault_root / "wiki" / "page.md").write_text("# Page\nBody\n", encoding="utf-8")
    state_path = tmp_path / "state"
    runner.invoke(app, ["init", "--vault", str(vault_root), "--state", str(state_path)])

    result = runner.invoke(app, ["index", "--state", str(state_path), "--dry-run"])

    assert result.exit_code == 0
    assert "vault_ids: default" in result.stdout
    assert "changed: 1" in result.stdout


def test_cli_vault_add_and_list(tmp_path: Path) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"
    first.mkdir()
    second.mkdir()
    state_path = tmp_path / "state"
    runner.invoke(app, ["init", "--vault", str(first), "--state", str(state_path)])

    add_result = runner.invoke(app, ["vault", "add", "work", "--path", str(second), "--state", str(state_path)])
    list_result = runner.invoke(app, ["vault", "list", "--state", str(state_path)])

    assert add_result.exit_code == 0
    assert list_result.exit_code == 0
    assert "default" in list_result.stdout
    assert "work" in list_result.stdout
```

- [ ] **Step 2: Run CLI tests to verify they fail**

Run:

```bash
uv run --python 3.12 pytest tests/test_cli_catalog_metadata.py -q
```

Expected: FAIL because `vault_graph.cli.main` does not exist.

- [ ] **Step 3: Implement config service**

Create `src/vault_graph/app/catalog_service.py` with this public API:

```python
from __future__ import annotations

from pathlib import Path

from vault_graph.ingestion.vault_catalog import VaultCatalog, VaultCatalogEntry


class CatalogService:
    def __init__(self, *, state_path: Path) -> None:
        self.state_path = state_path.expanduser().resolve()
        self.config_path = self.state_path / "configs" / "vaults.yaml"
        self.metadata_path = self.state_path / "metadata" / "metadata.sqlite3"

    def create_default_catalog(self, *, vault_root: Path, vault_id: str = "default") -> VaultCatalog:
        catalog = VaultCatalog.from_entries(
            entries=[VaultCatalogEntry.from_root(vault_id=vault_id, root_path=vault_root)],
            active_vault_id=vault_id,
        )
        catalog.save(self.config_path)
        return catalog

    def load_catalog(self) -> VaultCatalog:
        return VaultCatalog.load(self.config_path)

    def save_catalog(self, catalog: VaultCatalog) -> None:
        catalog.save(self.config_path)
```

- [ ] **Step 4: Implement index service**

Create `src/vault_graph/app/index_service.py`:

```python
from __future__ import annotations

from dataclasses import dataclass

from vault_graph.indexing.metadata_indexer import MetadataIndexer
from vault_graph.indexing.revision_planner import MetadataRevisionPlan
from vault_graph.ingestion.vault_catalog import QueryScope, VaultCatalog
from vault_graph.storage.local.sqlite_metadata_store import SQLiteMetadataStore


@dataclass(frozen=True)
class StatusReport:
    active_vault_id: str
    vault_ids: tuple[str, ...]
    metadata_ok: bool
    metadata_message: str


class IndexService:
    def __init__(self, *, catalog: VaultCatalog, metadata_store: SQLiteMetadataStore) -> None:
        self._catalog = catalog
        self._metadata_store = metadata_store

    def plan(self, *, scope: QueryScope) -> MetadataRevisionPlan:
        return MetadataIndexer(catalog=self._catalog, metadata_store=self._metadata_store).plan(scope=scope)

    def apply(self, *, scope: QueryScope) -> MetadataRevisionPlan:
        return MetadataIndexer(catalog=self._catalog, metadata_store=self._metadata_store).apply(scope=scope)

    def status(self) -> StatusReport:
        health = self._metadata_store.health()
        return StatusReport(
            active_vault_id=self._catalog.active_vault_id,
            vault_ids=tuple(entry.vault_id for entry in self._catalog.entries()),
            metadata_ok=health.ok,
            metadata_message=health.message,
        )
```

- [ ] **Step 5: Implement Typer CLI**

Create `src/vault_graph/cli/main.py` with commands:

```python
from __future__ import annotations

from pathlib import Path

import typer

from vault_graph.app.catalog_service import CatalogService
from vault_graph.app.index_service import IndexService
from vault_graph.ingestion.vault_catalog import VaultCatalog, VaultCatalogEntry
from vault_graph.storage.local.sqlite_metadata_store import SQLiteMetadataStore

app = typer.Typer(no_args_is_help=True)
vault_app = typer.Typer(no_args_is_help=True)
app.add_typer(vault_app, name="vault")


def _service(state: Path) -> tuple[CatalogService, VaultCatalog, IndexService]:
    config = CatalogService(state_path=state)
    catalog = config.load_catalog()
    metadata_store = SQLiteMetadataStore(config.metadata_path)
    return config, catalog, IndexService(catalog=catalog, metadata_store=metadata_store)


@app.command()
def init(vault: Path = typer.Option(...), state: Path = typer.Option(Path(".vault-graph")), vault_id: str = "default") -> None:
    config = CatalogService(state_path=state)
    catalog = config.create_default_catalog(vault_root=vault, vault_id=vault_id)
    typer.echo(f"initialized vault_id: {catalog.active_vault_id}")
    typer.echo(f"state: {config.state_path}")


@vault_app.command("add")
def vault_add(vault_id: str, path: Path = typer.Option(...), state: Path = typer.Option(Path(".vault-graph"))) -> None:
    config, catalog, _ = _service(state)
    entries = list(catalog.entries())
    entries.append(VaultCatalogEntry.from_root(vault_id=vault_id, root_path=path))
    updated = VaultCatalog.from_entries(entries=entries, active_vault_id=catalog.active_vault_id)
    config.save_catalog(updated)
    typer.echo(f"added vault_id: {vault_id}")


@vault_app.command("list")
def vault_list(state: Path = typer.Option(Path(".vault-graph"))) -> None:
    _, catalog, _ = _service(state)
    for entry in catalog.entries():
        active = " active" if entry.vault_id == catalog.active_vault_id else ""
        typer.echo(f"{entry.vault_id}{active} {entry.root_path}")


@app.command()
def index(
    state: Path = typer.Option(Path(".vault-graph")),
    vault_id: str | None = typer.Option(None),
    all_vaults: bool = typer.Option(False),
    dry_run: bool = typer.Option(False),
) -> None:
    _, catalog, service = _service(state)
    if all_vaults:
        scope = catalog.scope_for_all_enabled()
    elif vault_id:
        scope = catalog.scope_for_vault_ids([vault_id])
    else:
        scope = catalog.default_scope()
    plan = service.plan(scope=scope) if dry_run else service.apply(scope=scope)
    typer.echo(f"vault_ids: {', '.join(plan.vault_ids)}")
    typer.echo(f"index_revision: {plan.index_revision}")
    typer.echo(f"changed: {len(plan.changed_paths)}")
    typer.echo(f"unchanged: {len(plan.unchanged_paths)}")
    typer.echo(f"deleted: {len(plan.deleted_paths)}")


@app.command()
def status(state: Path = typer.Option(Path(".vault-graph"))) -> None:
    _, _, service = _service(state)
    report = service.status()
    typer.echo(f"active_vault_id: {report.active_vault_id}")
    typer.echo(f"vault_ids: {', '.join(report.vault_ids)}")
    typer.echo(f"metadata_ok: {report.metadata_ok}")
    typer.echo(f"metadata: {report.metadata_message}")
```

- [ ] **Step 6: Run CLI tests**

Run:

```bash
uv run --python 3.12 pytest tests/test_cli_catalog_metadata.py -q
uv run --python 3.12 ruff check src tests
uv run --python 3.12 mypy src
```

Expected: tests pass; ruff passes; mypy passes.

- [ ] **Step 7: Commit CLI**

Run:

```bash
git add src/vault_graph/app src/vault_graph/cli tests/test_cli_catalog_metadata.py
git commit -m "feat: expose phase one cli"
```

## Task 8: Read-Only And Multi-Vault Integration Gates

**Files:**

- Create: `tests/conftest.py`
- Create: `tests/test_read_only_boundary.py`
- Create: `tests/test_multi_vault_identity.py`

- [ ] **Step 1: Add shared test fixture helpers**

Create `tests/conftest.py`:

```python
from pathlib import Path

import pytest


@pytest.fixture
def vault_with_page(tmp_path: Path) -> Path:
    vault_root = tmp_path / "vault"
    (vault_root / "wiki").mkdir(parents=True)
    (vault_root / "wiki" / "page.md").write_text("# Page\nBody\n", encoding="utf-8")
    return vault_root
```

- [ ] **Step 2: Write read-only boundary test**

Create `tests/test_read_only_boundary.py`:

```python
from pathlib import Path

from typer.testing import CliRunner

from vault_graph.cli.main import app


def file_bytes(root: Path) -> dict[str, bytes]:
    return {path.relative_to(root).as_posix(): path.read_bytes() for path in sorted(root.rglob("*")) if path.is_file()}


def test_index_commands_do_not_modify_vault_files(tmp_path: Path) -> None:
    vault_root = tmp_path / "vault"
    (vault_root / "wiki").mkdir(parents=True)
    (vault_root / "wiki" / "page.md").write_text("---\ntitle: Page\n---\n# Page\nBody\n", encoding="utf-8")
    state_path = tmp_path / "state"
    runner = CliRunner()
    runner.invoke(app, ["init", "--vault", str(vault_root), "--state", str(state_path)])
    before = file_bytes(vault_root)

    dry_run = runner.invoke(app, ["index", "--state", str(state_path), "--dry-run"])
    apply = runner.invoke(app, ["index", "--state", str(state_path)])

    assert dry_run.exit_code == 0
    assert apply.exit_code == 0
    assert file_bytes(vault_root) == before
```

- [ ] **Step 3: Write multi-vault identity integration test**

Create `tests/test_multi_vault_identity.py`:

```python
from pathlib import Path

from typer.testing import CliRunner

from vault_graph.cli.main import app
from vault_graph.storage.local.sqlite_metadata_store import SQLiteMetadataStore


def test_two_vaults_with_same_relative_path_do_not_collide(tmp_path: Path) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"
    (first / "wiki").mkdir(parents=True)
    (second / "wiki").mkdir(parents=True)
    (first / "wiki" / "same.md").write_text("# Same\nFirst body\n", encoding="utf-8")
    (second / "wiki" / "same.md").write_text("# Same\nSecond body\n", encoding="utf-8")
    state_path = tmp_path / "state"
    runner = CliRunner()

    assert runner.invoke(app, ["init", "--vault-id", "first", "--vault", str(first), "--state", str(state_path)]).exit_code == 0
    assert runner.invoke(app, ["vault", "add", "second", "--path", str(second), "--state", str(state_path)]).exit_code == 0
    assert runner.invoke(app, ["index", "--all-vaults", "--state", str(state_path)]).exit_code == 0

    store = SQLiteMetadataStore(state_path / "metadata" / "metadata.sqlite3")
    first_state = store.document_state("first", "wiki/same.md")
    second_state = store.document_state("second", "wiki/same.md")

    assert first_state.document_id is not None
    assert second_state.document_id is not None
    assert first_state.document_id != second_state.document_id
    assert first_state.content_hash != second_state.content_hash
```

- [ ] **Step 4: Run full Phase 1 gate**

Run:

```bash
uv run --python 3.12 pytest -q
uv run --python 3.12 ruff check src tests
uv run --python 3.12 mypy src
git diff --check
```

Expected:

- all pytest tests pass
- ruff passes
- mypy passes
- `git diff --check` exits 0

- [ ] **Step 5: Commit integration gates**

Run:

```bash
git add tests/conftest.py tests/test_read_only_boundary.py tests/test_multi_vault_identity.py
git commit -m "test: guard read-only multi-vault metadata indexing"
```

## Phase 1 Completion Criteria

Phase 1 is complete only when all of these are true:

- `vg init --vault /path/to/vault --state /tmp/state` creates a default active
  Vault catalog entry with `vault_id: default`
- `vg init --vault-id first --vault /path/to/vault --state /tmp/state` creates
  a non-default active Vault catalog entry
- `vg vault add ID --path /path/to/vault --state /tmp/state` registers an
  additional Vault without touching any Vault files
- `vg vault list --state /tmp/state` shows all registered Vault IDs and paths
- `vg index --dry-run --state /tmp/state` reports planned metadata changes and
  does not write metadata rows
- `vg index --state /tmp/state` writes SQLite metadata projection rows
- `vg index --vault-id ID --state /tmp/state` indexes only that Vault and does
  not tombstone records from other Vaults
- `vg index --all-vaults --state /tmp/state` expands to all enabled Vault IDs
- `vg status --state /tmp/state` reports active Vault ID, registered Vault IDs,
  and metadata backend health
- Vault content bytes are identical before and after Phase 1 CLI commands
- two Vaults with `wiki/same.md` produce separate document IDs and metadata rows

## Final Verification Command

Run this before considering Phase 1 ready for Phase 2:

```bash
uv run --python 3.12 pytest -q
uv run --python 3.12 ruff check src tests
uv run --python 3.12 mypy src
git diff --check
git status --short --branch
```

Expected final state:

- tests pass
- ruff passes
- mypy passes
- whitespace check passes
- branch shows only intentional changes, or a clean worktree after commits

## Self-Review

- Spec coverage: This plan covers `docs/SPEC.md` Phase 1 and the Phase 1
  implementation order in `docs/DESIGN.md`.
- Multi-vault consistency: `VaultCatalog` is the only authority for root paths;
  all metadata identities use `vault_id`; same relative paths are tested.
- Read-only boundary: loader and CLI tests compare Vault file bytes before and
  after indexing.
- Scope control: vector, graph, retrieval, context packs, MCP, HTTP, and UI are
  not part of this phase.
- Placeholder scan: no unresolved placeholder terms are intentionally present.
