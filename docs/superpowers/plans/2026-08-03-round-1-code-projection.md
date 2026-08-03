# Round 1 Code Projection Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a deterministic, local-first, read-only code projection for registered Python and Dart repositories, with SQLite/FTS5 structural queries, incremental freshness, and no source-body duplication.

**Architecture:** Keep code indexing in a new `vault_graph.code_index` deep module. A Python `CodeParserAdapter` protocol wraps pinned Tree-sitter backends; extraction, resolution, storage, freshness, and querying are separate application boundaries. Code generations use a code-specific active manifest so a code rebuild never switches Vault's metadata/vector/graph generation.

**Tech Stack:** Python 3.12+, Tree-sitter Python bindings and pinned Python/Dart grammar artifacts, SQLite/FTS5, optional `watchfiles` watcher, Typer, pytest, Ruff, mypy, uv.

---

## Scope and non-goals

In scope:

- graph-owned source-repository catalog with duplicate/overlap validation
- Python and Dart syntax extraction through Tree-sitter wrappers written in Python
- repository-scoped files, modules, classes, interfaces/mixins, functions,
  methods, properties, tests, and structural relationships
- deterministic import/call/inheritance/implementation/test resolution with
  pending unresolved references
- code-specific SQLite/FTS5 projection, generation activation, and run status
- full rebuild, incremental reconcile, deletions, untracked-file hashing, and
  optional read-only watcher
- freshness states and bounded current-source evidence
- `vg code repository`, `index`, `status`, `search`, `symbol`, `callers`,
  `callees`, and `impact` CLI surfaces
- tests and acceptance fixtures proving authority, rebuild, identity, and query
  contracts

Non-goals:

- any write to Vault files, repository files, tests, manifests, or Git metadata
- copying complete repository source bodies into Graph state
- Dart SDK/Analysis Server as a mandatory runtime
- Python `ast` or Dart Analyzer as the Round 1 primary parser
- semantic embeddings, vector code search, LLM-generated edges, or code edits
- Round 2 `ProjectContextService`, `explore_project`, MCP harness guidance, or
  Vault/code cross-source relationship inference
- remote indexing or hosted storage

## Repo context inspected

- `AGENTS.md`
- `docs/SPEC.md` 1.2
- `docs/DESIGN.md`
- `docs/FEATURES.md`
- `docs/CONVENTIONS.md`
- `docs/superpowers/specs/2026-08-03-round-1-code-projection-design.md`
- `docs/superpowers/specs/2026-08-03-round-0-g-authority-projection-hygiene-design.md`
- `src/vault_graph/ingestion/vault_catalog.py`
- `src/vault_graph/app/catalog_service.py`
- `src/vault_graph/app/projection_generation.py`
- `src/vault_graph/app/local_index_service_factory.py`
- `src/vault_graph/app/path_guard.py`
- `src/vault_graph/cli/main.py`
- existing storage protocols/local SQLite stores and read-only boundary tests

## Global constraints

- Vault remains the durable knowledge authority; each registered repository
  remains the current-code authority.
- Derived code records are rebuildable evidence, never executable source.
- The repository owns all complete source plaintext. Queries read bounded lines
  from the live repository and report hash/revision drift.
- A code-only rebuild must not activate or replace the existing Vault
  `projections/active.json` generation.
- All state paths are checked with existing `CatalogService`/`path_guard`
  boundaries before writes.
- Every behavior follows `@superpowers:test-driven-development`: write a
  focused failing test, verify RED, implement the smallest change, verify
  GREEN, then refactor and commit.
- Do not push any branch or create a PR unless the user explicitly instructs it.

## Planned file structure

Create:

- `src/vault_graph/code_index/__init__.py`
- `src/vault_graph/code_index/code_models.py`
- `src/vault_graph/code_index/repository_catalog.py`
- `src/vault_graph/code_index/source_scanning.py`
- `src/vault_graph/code_index/parser_adapter.py`
- `src/vault_graph/code_index/tree_sitter_parsing.py`
- `src/vault_graph/code_index/python_parser.py`
- `src/vault_graph/code_index/dart_parser.py`
- `src/vault_graph/code_index/reference_resolution.py`
- `src/vault_graph/code_index/code_freshness.py`
- `src/vault_graph/code_index/code_watch_service.py`
- `src/vault_graph/code_index/code_generation.py`
- `src/vault_graph/code_index/code_projection_service.py`
- `src/vault_graph/code_index/code_query_service.py`
- `src/vault_graph/code_index/source_evidence_reader.py`
- `src/vault_graph/app/code_index_factory.py`
- `src/vault_graph/storage/interfaces/code_projection_store.py`
- `src/vault_graph/storage/local/sqlite_code_projection_store.py`
- `src/vault_graph/cli/code_commands.py`
- `tests/test_code_models.py`
- `tests/test_code_repository_catalog.py`
- `tests/test_code_parser_adapters.py`
- `tests/test_code_reference_resolution.py`
- `tests/test_code_freshness.py`
- `tests/test_code_generation.py`
- `tests/test_sqlite_code_projection_store.py`
- `tests/test_code_projection_service.py`
- `tests/test_code_query_service.py`
- `tests/test_code_watch_service.py`
- `tests/test_cli_code_index.py`
- `tests/test_code_read_only_boundary.py`
- `tests/test_code_index_completion.py`
- `tests/fixtures/code_index/python/...`
- `tests/fixtures/code_index/dart/...`

Modify:

- `pyproject.toml` and `uv.lock`: explicit parser/watcher dependencies
- `src/vault_graph/cli/main.py`: register the `code` Typer sub-app only
- `src/vault_graph/app/catalog_service.py`: expose safe state/config paths to
  the code catalog without changing Vault catalog semantics
- `docs/SPEC.md`, `docs/DESIGN.md`, `docs/FEATURES.md`, and `README.md`: document
  implemented Round 1 CLI behavior after acceptance tests pass
- relevant test documentation guards where feature matrices are asserted

Do not modify Vault files or the registered repository during implementation.

---

## Implementation Steps

### Task 1: Pin parser and watcher dependencies and establish code DTOs

**Files:**

- Modify: `pyproject.toml`
- Modify: `uv.lock`
- Create: `src/vault_graph/code_index/__init__.py`
- Create: `src/vault_graph/code_index/code_models.py`
- Create: `tests/test_code_models.py`
- Create: `tests/test_code_parser_adapters.py`

**Interfaces:**

```python
CodeRepositoryId = NewType("CodeRepositoryId", str)

@dataclass(frozen=True)
class CodeRepositoryEntry:
    repository_id: str
    root_path: Path
    display_name: str
    enabled: bool
    include_globs: tuple[str, ...]
    exclude_globs: tuple[str, ...]
    languages: tuple[str, ...]
    state_namespace: str
    git_revision_policy: str
    watch: bool

@dataclass(frozen=True)
class CodeFileSnapshot:
    repository_id: str
    relative_path: str
    language: str
    content_hash: str
    byte_count: int
    line_count: int
    source_revision: str
    is_test_file: bool
    parser_spec_version: str

@dataclass(frozen=True)
class CodeSymbolRecord:
    symbol_id: str
    repository_id: str
    file_id: str
    kind: str
    language_kind: str
    name: str
    qualified_name: str
    signature: str | None
    start_line: int
    end_line: int
    start_column: int
    end_column: int
    content_hash: str
    source_revision: str
    parser_spec_version: str

@dataclass(frozen=True)
class CodeEdgeRecord:
    edge_id: str
    repository_id: str
    source_symbol_id: str
    relation_kind: str
    target_symbol_id: str | None
    unresolved_target_key: str | None
    extraction_status: Literal["extracted", "inferred", "ambiguous", "unresolved"]
    anchor_start_line: int
    anchor_start_column: int
    parser_spec_version: str
```

`code_models.py` must also define the shared boundary records used by later
tasks: `CodeFileInput`, `CodeReferenceRecord`, `CodeParseDiagnostic`,
`PendingCodeReference`, `CodeManifest`, `CodeReconcilePlan`, `CodeApplyResult`,
`CodeSymbolQuery`, `CodeSymbolHit`, `CodeTraversalQuery`,
`CodeTraversalResult`, `CodeIndexRequest`, `CodeIndexPlan`, `CodeRunReport`,
`CodeFreshnessRequest`, `CodeFreshnessReport`, and the CLI/query request and
response records. Each record must carry repository identity and parser/schema
revision where the value affects rebuild or freshness compatibility. Later tasks
may add fields, but they must not introduce duplicate DTOs in CLI or storage
modules.

- [ ] **Step 1: Write contract tests** for required enum values, immutable
  dataclasses, non-empty repository/path identities, valid line ranges, and
  rejection of invalid extraction statuses.
- [ ] **Step 2: Run RED**

  Run: `uv run pytest tests/test_code_models.py -q`

  Expected: import failure because the code-index package and DTOs do not exist.
- [ ] **Step 3: Add dependencies via uv**

  Add a compatible pinned `tree-sitter` runtime and `tree-sitter-python` grammar.
  Resolve a reproducible pinned Dart grammar artifact (direct Python binding or
  a narrowly selected language-pack distribution) during this task; record the
  exact grammar revision/ABI in the parser spec constant. Add `watchfiles` only
  if its wheel/platform smoke test passes; otherwise keep watcher imports behind
  an optional adapter and return `watch_unavailable`.

  Do not use an unpinned Git checkout at runtime or download grammars during an
  index/search command.
- [ ] **Step 4: Implement DTOs and parser-spec constants** with no filesystem
  side effects at import time.
- [ ] **Step 5: Run GREEN and static checks**

  Run: `uv run pytest tests/test_code_models.py -q`

  Expected: all DTO tests pass. Also run `uv run ruff check src/vault_graph/code_index tests/test_code_models.py`.
- [ ] **Step 6: Commit**

```bash
git add pyproject.toml uv.lock src/vault_graph/code_index tests/test_code_models.py tests/test_code_parser_adapters.py
git commit -m "feat: add code projection contracts"
```

### Task 2: Implement repository catalog and path safety

**Files:**

- Create: `src/vault_graph/code_index/repository_catalog.py`
- Modify: `src/vault_graph/app/catalog_service.py`
- Modify: `src/vault_graph/app/path_guard.py` only if a narrowly scoped reusable
  outside-Vault assertion is required
- Test: `tests/test_code_repository_catalog.py`
- Test: `tests/test_code_read_only_boundary.py`

**Interfaces:**

```python
class CodeRepositoryCatalog(Protocol):
    def entries(self) -> tuple[CodeRepositoryEntry, ...]: ...
    def resolve(self, repository_id: str) -> CodeRepositoryEntry: ...
    def save(self, entry: CodeRepositoryEntry) -> None: ...
    def remove(self, repository_id: str) -> None: ...

class CodeRepositoryCatalogService:
    def load(self) -> CodeRepositoryCatalog: ...
    def add(self, entry: CodeRepositoryEntry) -> CodeRepositoryCatalog: ...
    def remove(self, repository_id: str) -> CodeRepositoryCatalog: ...
```

- [ ] **Step 1: Write failing catalog tests** for YAML round-trip, missing root,
  duplicate ID, canonical duplicate root, parent/child overlap, empty or
  traversal globs, symlink escape, unsupported language, and a code root equal to
  or inside a registered Vault root.
- [ ] **Step 2: Run RED**

  Run: `uv run pytest tests/test_code_repository_catalog.py -q`

  Expected: missing `CodeRepositoryCatalogService` import.
- [ ] **Step 3: Implement catalog loading/saving** at
  `STATE/configs/repositories.yaml`. Normalize roots with `expanduser().resolve()`;
  preserve stable order; hash include/exclude/language policy for manifests.
  Reuse `CatalogService` to obtain Vault roots and existing path guards. A code
  catalog write must stay inside Graph state and outside all registered Vaults.
- [ ] **Step 4: Implement overlap and policy validation** before writing any
  catalog change. `remove` removes only catalog/state records and never calls
  filesystem deletion on the repository root.
- [ ] **Step 5: Run GREEN**

  Run: `uv run pytest tests/test_code_repository_catalog.py tests/test_code_read_only_boundary.py -q`

  Expected: all catalog and path-fingerprint tests pass; no Vault/repository
  files change.
- [ ] **Step 6: Commit**

```bash
git add src/vault_graph/code_index/repository_catalog.py src/vault_graph/app/catalog_service.py \
  src/vault_graph/app/path_guard.py tests/test_code_repository_catalog.py tests/test_code_read_only_boundary.py
git commit -m "feat: register code repositories safely"
```

### Task 3: Build the Tree-sitter parser adapter boundary

**Files:**

- Create: `src/vault_graph/code_index/parser_adapter.py`
- Create: `src/vault_graph/code_index/tree_sitter_parsing.py`
- Create: `src/vault_graph/code_index/python_parser.py`
- Create: `src/vault_graph/code_index/dart_parser.py`
- Modify: `src/vault_graph/code_index/code_models.py`
- Test: `tests/test_code_parser_adapters.py`
- Test fixtures: `tests/fixtures/code_index/python/basic_project/...`
- Test fixtures: `tests/fixtures/code_index/dart/basic_project/...`

**Interfaces:**

```python
class CodeParserAdapter(Protocol):
    language: str
    parser_spec_version: str

    def parse(self, file: CodeFileInput) -> CodeParseResult: ...

@dataclass(frozen=True)
class CodeParseResult:
    file: CodeFileSnapshot
    symbols: tuple[CodeSymbolRecord, ...]
    references: tuple[CodeReferenceRecord, ...]
    diagnostics: tuple[CodeParseDiagnostic, ...]
```

- [ ] **Step 1: Add fixture files** covering Python modules/classes/functions/
  methods/imports/calls/inheritance/tests and Dart classes/mixins/extensions/
  async functions/imports/annotations/tests. Include one malformed file and one
  unsupported construct for diagnostics.
- [ ] **Step 2: Write failing adapter tests** asserting stable symbol kinds,
  qualified names, line/column ranges, file hashes, `CONTAINS`/`DEFINES` raw
  references, parser version metadata, and syntax-error diagnostics.
- [ ] **Step 3: Run RED**

  Run: `uv run pytest tests/test_code_parser_adapters.py -q`

  Expected: missing parser adapter implementation or missing grammar import.
- [ ] **Step 4: Implement shared Tree-sitter loader** that constructs a parser
  only from installed, pinned grammar artifacts. It must never download files,
  write caches, or shell out to Dart/Python runtimes during a query.
- [ ] **Step 5: Implement Python adapter** using Tree-sitter queries for module,
  class, function, method, property, import, call, inheritance, and test
  candidates. Keep extraction deterministic by sorting nodes by source range and
  qualified identity.
- [ ] **Step 6: Implement Dart adapter** using the pinned Dart grammar for
  library/class/mixin/extension/function/method/property/import/annotation/test
  candidates. Mark grammar gaps as diagnostics; never infer missing symbols from
  text search.
- [ ] **Step 7: Run GREEN and parser fixture gate**

  Run: `uv run pytest tests/test_code_parser_adapters.py -q`

  Expected: repeated parses produce byte-equivalent normalized records; malformed
  fixtures return bounded diagnostics without crashing the repository run.
- [ ] **Step 8: Commit**

```bash
git add src/vault_graph/code_index tests/test_code_parser_adapters.py tests/fixtures/code_index
git commit -m "feat: parse Python and Dart code structure"
```

### Task 4: Add code-specific generation and SQLite/FTS5 storage

**Files:**

- Create: `src/vault_graph/code_index/code_generation.py`
- Create: `src/vault_graph/storage/interfaces/code_projection_store.py`
- Create: `src/vault_graph/storage/local/sqlite_code_projection_store.py`
- Test: `tests/test_code_generation.py`
- Test: `tests/test_sqlite_code_projection_store.py`

**Interfaces:**

```python
class CodeProjectionGenerationManager:
    def stage(self, repository_ids: tuple[str, ...]) -> CodeGenerationLayout: ...
    def active_layout(self, repository_ids: tuple[str, ...]) -> CodeGenerationLayout | None: ...
    def activate(self, staged: CodeGenerationLayout) -> None: ...
    def discard(self, staged: CodeGenerationLayout) -> None: ...

class CodeProjectionStore(Protocol):
    def health(self) -> StoreHealth: ...
    def current_manifest(self, repository_ids: tuple[str, ...]) -> CodeManifest: ...
    def apply_reconcile_plan(self, plan: CodeReconcilePlan) -> CodeApplyResult: ...
    def search_symbols(self, query: CodeSymbolQuery) -> tuple[CodeSymbolHit, ...]: ...
    def get_symbol(self, symbol_id: str) -> CodeSymbolRecord | None: ...
    def traverse(self, query: CodeTraversalQuery) -> CodeTraversalResult: ...
```

- [ ] **Step 1: Write generation safety tests** for staging, activation,
  preservation of the previous code generation, unsafe manifest paths, and
  proof that activating code does not change the existing Vault
  `projections/active.json`.
- [ ] **Step 2: Run RED**

  Run: `uv run pytest tests/test_code_generation.py -q`

  Expected: missing code generation manager.
- [ ] **Step 3: Implement code-specific layout** under
  `STATE/projections/code/generations/<generation_id>/code.sqlite3` with
  `STATE/projections/code/active.json`. Do not reuse the global
  `ProjectionGenerationManager.activate()` for code-only runs; that manager
  switches the Vault projection root.
- [ ] **Step 4: Write failing SQLite schema tests** checking schema version
  `code-projection-v1`, required tables (`repositories`, `files`, `symbols`,
  `edges`, `pending_references`, `symbol_fts`, `projection_runs`,
  `file_fingerprints`), unique identities, same-repository endpoints, and the
  absence of complete source-body/excerpt columns.
- [ ] **Step 5: Run RED**

  Run: `uv run pytest tests/test_sqlite_code_projection_store.py -q`

  Expected: missing store/schema methods.
- [ ] **Step 6: Implement SQLite store** with transactional reconcile plans,
  contentless or metadata-only FTS fields for path/name/qualified name/signature/
  language/kind, deterministic ordering, and read-only open mode. Store no
  source body or rendered excerpt.
- [ ] **Step 7: Implement health/manifest checks** including schema/parser/policy
  compatibility and dangling resolved-endpoint checks.
- [ ] **Step 8: Run GREEN and commit**

  Run: `uv run pytest tests/test_code_generation.py tests/test_sqlite_code_projection_store.py -q`

```bash
git add src/vault_graph/code_index/code_generation.py \
  src/vault_graph/storage/interfaces/code_projection_store.py \
  src/vault_graph/storage/local/sqlite_code_projection_store.py \
  tests/test_code_generation.py tests/test_sqlite_code_projection_store.py
git commit -m "feat: store code projection generations"
```

### Task 5: Implement deterministic reference resolution and pending retries

**Files:**

- Create: `src/vault_graph/code_index/reference_resolution.py`
- Modify: `src/vault_graph/code_index/code_models.py`
- Modify: `src/vault_graph/storage/interfaces/code_projection_store.py`
- Modify: `src/vault_graph/storage/local/sqlite_code_projection_store.py`
- Test: `tests/test_code_reference_resolution.py`

**Interfaces:**

```python
class CodeReferenceResolver:
    def resolve(
        self,
        *,
        files: tuple[CodeFileSnapshot, ...],
        symbols: tuple[CodeSymbolRecord, ...],
        references: tuple[CodeReferenceRecord, ...],
        previous_pending: tuple[PendingCodeReference, ...],
    ) -> ResolutionResult: ...
```

- [ ] **Step 1: Write failing resolution tests** for local imports, package/
  relative imports, same-file calls, cross-file calls, inheritance,
  implementation, test-to-production target, duplicate edge collapse,
  unresolved pending entries, retry after a target file changes, and ambiguous
  dynamic calls.
- [ ] **Step 2: Run RED**

  Run: `uv run pytest tests/test_code_reference_resolution.py -q`

  Expected: missing resolver and unresolved reference models.
- [ ] **Step 3: Implement deterministic symbol indexes** keyed by repository,
  module/import path, qualified name, and kind. Keep repository boundaries
  strict; cross-repository targets remain unresolved.
- [ ] **Step 4: Implement relation-specific resolution** for `IMPORTS`,
  `CALLS`, `EXTENDS`, `IMPLEMENTS`, and `TESTS`. Use only static evidence. A
  name collision or dynamic dispatch becomes `ambiguous`, not a confident edge.
- [ ] **Step 5: Implement pending-reference persistence/retry** keyed by target
  namespace and affected file/symbol identity. Retry only impacted references
  during incremental runs.
- [ ] **Step 6: Run GREEN and commit**

  Run: `uv run pytest tests/test_code_reference_resolution.py -q`

```bash
git add src/vault_graph/code_index/reference_resolution.py src/vault_graph/code_index/code_models.py \
  src/vault_graph/storage/interfaces/code_projection_store.py \
  src/vault_graph/storage/local/sqlite_code_projection_store.py tests/test_code_reference_resolution.py
git commit -m "feat: resolve code graph relationships"
```

### Task 6: Add scanning, fingerprints, freshness, and projection service

**Files:**

- Create: `src/vault_graph/code_index/source_scanning.py`
- Create: `src/vault_graph/code_index/code_freshness.py`
- Create: `src/vault_graph/code_index/code_projection_service.py`
- Create: `src/vault_graph/app/code_index_factory.py`
- Modify: `src/vault_graph/code_index/code_generation.py`
- Test: `tests/test_code_freshness.py`
- Test: `tests/test_code_projection_service.py`

**Interfaces:**

```python
class CodeProjectionService:
    def plan(self, request: CodeIndexRequest) -> CodeIndexPlan: ...
    def apply(self, request: CodeIndexRequest) -> CodeRunReport: ...
    def status(self, repository_ids: tuple[str, ...]) -> CodeFreshnessReport: ...

class CodeFreshnessService:
    def compare(self, request: CodeFreshnessRequest) -> CodeFreshnessReport: ...
```

- [ ] **Step 1: Write failing scanner tests** for include/exclude matching,
  default generated/vendor/VCS exclusions, language detection, symlink escape,
  deterministic file order, content hashes, line counts, Git HEAD + dirty
  working-tree revision, and non-Git content-hash fallback.
- [ ] **Step 2: Run RED**

  Run: `uv run pytest tests/test_code_freshness.py -q`

  Expected: missing scanner/freshness implementation.
- [ ] **Step 3: Implement `source_scanning.py`** as a read-only scanner. Read
  each selected file once for hash and parser input; never follow a symlink
  outside the canonical repository root.
- [ ] **Step 4: Implement freshness states** `fresh`, `stale`, `syncing`,
  `partial`, `unavailable`, and `unknown`. Include pending/deleted paths,
  parser/schema/policy versions, and previous run diagnostics.
- [ ] **Step 5: Write failing service tests** for full build, incremental added/
  modified/deleted files, unchanged untracked files, parser errors producing
  partial status, activation rollback after failure, and full-vs-incremental
  normalized equivalence.
- [ ] **Step 6: Run RED**

  Run: `uv run pytest tests/test_code_projection_service.py -q`

  Expected: missing service/factory implementation.
- [ ] **Step 7: Implement the staged workflow**

  ```text
  catalog -> scan/fingerprint -> parse changed files -> stage records
         -> resolve affected references -> audit -> activate code manifest
  ```

  Full runs stage a complete repository snapshot. Incremental runs replace
  changed files as one unit, tombstone deleted symbols/edges, retry affected
  pending references, and leave other repository namespaces untouched. A failed
  run leaves the previous code generation active.
- [ ] **Step 8: Implement `code_index_factory.py`** to construct catalog,
  parser adapters, resolver, code store, generation manager, freshness service,
  and projection service. No CLI/MCP adapter may construct SQLite internals.
- [ ] **Step 9: Run GREEN and commit**

  Run: `uv run pytest tests/test_code_freshness.py tests/test_code_projection_service.py -q`

```bash
git add src/vault_graph/code_index/source_scanning.py src/vault_graph/code_index/code_freshness.py \
  src/vault_graph/code_index/code_projection_service.py src/vault_graph/app/code_index_factory.py \
  src/vault_graph/code_index/code_generation.py tests/test_code_freshness.py tests/test_code_projection_service.py
git commit -m "feat: build incremental code projections"
```

### Task 7: Add structural query and bounded source evidence services

**Files:**

- Create: `src/vault_graph/code_index/code_query_service.py`
- Create: `src/vault_graph/code_index/source_evidence_reader.py`
- Modify: `src/vault_graph/storage/interfaces/code_projection_store.py`
- Test: `tests/test_code_query_service.py`

**Interfaces:**

```python
class CodeQueryService:
    def search_symbols(self, request: CodeSymbolSearchRequest) -> CodeSearchResponse: ...
    def get_symbol(self, request: CodeSymbolRequest) -> CodeSymbolResponse: ...
    def get_file_outline(self, request: CodeFileOutlineRequest) -> CodeFileOutlineResponse: ...
    def get_callers(self, request: CodeTraversalRequest) -> CodeTraversalResponse: ...
    def get_callees(self, request: CodeTraversalRequest) -> CodeTraversalResponse: ...
    def get_impact(self, request: CodeImpactRequest) -> CodeTraversalResponse: ...
```

- [ ] **Step 1: Write failing query tests** for FTS symbol/path search, stable
  ordering, repository scope, kind/path filters, symbol lookup, file outline,
  callers, callees, impact depth/limit, cycle detection, and exclusion of
  ambiguous/unresolved edges from confident traversal.
- [ ] **Step 2: Run RED**

  Run: `uv run pytest tests/test_code_query_service.py -q`

  Expected: missing query service and response models.
- [ ] **Step 3: Implement read-only query DTOs and traversal** through the
  `CodeProjectionStore` protocol. Enforce repository namespace, depth, limit,
  deterministic ordering, and warnings for stale/partial/unknown states.
- [ ] **Step 4: Implement `source_evidence_reader.py`** using the existing path
  guard pattern. Read only bounded current lines after structural selection;
  compare current hash to indexed hash and return `source_changed_since_index`
  or `source_unavailable` instead of a stored excerpt.
- [ ] **Step 5: Run GREEN and commit**

  Run: `uv run pytest tests/test_code_query_service.py -q`

```bash
git add src/vault_graph/code_index/code_query_service.py src/vault_graph/code_index/source_evidence_reader.py \
  src/vault_graph/storage/interfaces/code_projection_store.py tests/test_code_query_service.py
git commit -m "feat: query code structure with live evidence"
```

### Task 8: Add CLI commands and read-only service wiring

**Files:**

- Create: `src/vault_graph/cli/code_commands.py`
- Modify: `src/vault_graph/cli/main.py`
- Modify: `src/vault_graph/app/code_index_factory.py`
- Test: `tests/test_cli_code_index.py`
- Test: `tests/test_code_read_only_boundary.py`

**Interfaces/commands:**

```text
vg code repository add ID --path PATH [--language python|dart ...]
vg code repository list [--format text|json]
vg code repository remove ID [--format text|json]
vg code index [--repository-id ID] [--full] [--dry-run] [--format text|json]
vg code status [--repository-id ID] [--verify] [--format text|json]
vg code search QUERY [--repository-id ID] [--kind KIND] [--limit N] [--format text|json]
vg code symbol SYMBOL_OR_ID [--source] [--format text|json]
vg code callers SYMBOL_OR_ID [--depth N] [--format text|json]
vg code callees SYMBOL_OR_ID [--depth N] [--format text|json]
vg code impact SYMBOL_OR_ID [--depth N] [--format text|json]
```

- [ ] **Step 1: Write failing CLI tests** for repository add/list/remove,
  invalid/overlapping roots, full and dry-run indexing, status state output,
  JSON/text output, symbol/callers/callees/impact results, invalid arguments,
  nonzero unavailable/failed-run exit codes, and no-write dry-run behavior.
- [ ] **Step 2: Run RED**

  Run: `uv run pytest tests/test_cli_code_index.py -q`

  Expected: `code` command group is not registered.
- [ ] **Step 3: Implement `code_commands.py`** as a thin Typer adapter. It must
  call `CodeRepositoryCatalogService`, `CodeProjectionService`, and
  `CodeQueryService`; it must not import SQLite or parser implementation
  details directly.
- [ ] **Step 4: Register `code_app` in `cli/main.py`** without changing existing
  Vault `init`, `index`, `search`, MCP, or answer command behavior.
- [ ] **Step 5: Add `--format text|json` validation and serialization** for
  repository, run, freshness, symbol,
  traversal, diagnostics, and bounded source evidence DTOs. Make warnings and
  affected paths structurally attributable.
- [ ] **Step 6: Run GREEN and commit**

  Run: `uv run pytest tests/test_cli_code_index.py tests/test_code_read_only_boundary.py -q`

```bash
git add src/vault_graph/cli/code_commands.py src/vault_graph/cli/main.py \
  src/vault_graph/app/code_index_factory.py tests/test_cli_code_index.py tests/test_code_read_only_boundary.py
git commit -m "feat: expose code index CLI"
```

### Task 9: Add optional watcher and freshness synchronization

**Files:**

- Create: `src/vault_graph/code_index/code_watch_service.py`
- Modify: `src/vault_graph/cli/code_commands.py`
- Modify: `pyproject.toml` and `uv.lock` only if the approved watcher backend
  has compatible wheels
- Test: `tests/test_code_watch_service.py`

- [ ] **Step 1: Write failing watcher tests** using a fake event source for
  debounce/coalescing, include/exclude filtering, changed/deleted paths,
  successful reconcile before `fresh`, and interrupted reconcile producing
  `partial` without changing source files.
- [ ] **Step 2: Run RED**

  Run: `uv run pytest tests/test_code_watch_service.py -q`

  Expected: missing watcher service.
- [ ] **Step 3: Implement the watcher behind a protocol**. Prefer a pinned
  `watchfiles` backend with native OS events; if the optional package is not
  installed or unsupported, return `watch_unavailable` and do not silently fall
  back to a polling loop in the normal command.
- [ ] **Step 4: Wire `vg code watch`** to the same incremental service used by
  CLI indexing. The watcher may write only code Graph state and must stop cleanly
  without touching repository or Vault files.
- [ ] **Step 5: Run GREEN and commit**

  Run: `uv run pytest tests/test_code_watch_service.py -q`

```bash
git add src/vault_graph/code_index/code_watch_service.py src/vault_graph/cli/code_commands.py \
  pyproject.toml uv.lock tests/test_code_watch_service.py
git commit -m "feat: watch code projections safely"
```

### Task 10: Documentation, completion fixtures, and acceptance gate

**Files:**

- Modify: `docs/SPEC.md`
- Modify: `docs/DESIGN.md`
- Modify: `docs/FEATURES.md`
- Modify: `README.md`
- Create: `tests/test_code_index_completion.py`
- Modify: `tests/test_readme_onboarding_contract.py` only for new implemented
  CLI/help assertions
- Test fixtures: `tests/fixtures/code_index/completion_project/...`

- [ ] **Step 1: Add the completion fixture** containing Python and Dart files,
  imports/calls/inheritance/tests, a malformed file, a generated/excluded file,
  and an untracked file. Record expected normalized symbols/edges.
- [ ] **Step 2: Write failing completion tests** for:
  - repeated full-build byte-equivalent normalized graph
  - full vs incremental equivalence after add/modify/delete
  - zero duplicate edges and dangling resolved endpoints
  - no source body/excerpt columns or plaintext ownership in SQLite
  - stale/partial/unavailable/unknown states never reported as fresh
  - bounded live source evidence and changed-source warnings
  - repository, Vault, and Git fingerprints unchanged after index/status/query
  - CLI completion gate without MCP, embeddings, network, or hosted services
- [ ] **Step 3: Run RED**

  Run: `uv run pytest tests/test_code_index_completion.py -q`

  Expected: missing integrated code projection behavior or assertion failures.
- [ ] **Step 4: Implement only the minimum integration/documentation changes**
  needed to expose the already-tested Round 1 contract. Keep Round 2 MCP and
  Vault/code cross-source composition explicitly deferred.
- [ ] **Step 5: Run GREEN and documentation guards**

  Run:

  ```bash
  uv run pytest tests/test_code_index_completion.py tests/test_cli_code_index.py tests/test_code_read_only_boundary.py -q
  rg -n "vg code|code projection|Round 1|source repository" docs/SPEC.md docs/DESIGN.md docs/FEATURES.md README.md
  ```

  Expected: completion suite passes; docs describe only implemented CLI scope
  and do not claim MCP/project-context functionality.
- [ ] **Step 6: Commit**

```bash
git add docs/SPEC.md docs/DESIGN.md docs/FEATURES.md README.md \
  tests/test_code_index_completion.py tests/test_readme_onboarding_contract.py tests/fixtures/code_index
git commit -m "docs: document Round 1 code projection"
```

---

## Validation review

Before implementation handoff, review the plan across these angles:

- **Security/read-only safety:** repository/Vault roots are canonicalized and
  rejected when overlapping; all writes are inside Graph state; source reads
  are bounded; no watcher or CLI path can write source/Git files; code-only
  activation cannot switch Vault's active manifest.
- **Performance/scalability:** hashes avoid re-parsing unchanged files; FTS
  handles symbol/path candidates; incremental resolution retries only affected
  references; traversal is depth/limit bounded; watcher events are debounced;
  run/query metrics are recorded before any numeric SLA is chosen.
- **Testability:** parser fixtures are deterministic; stores have protocol-level
  tests; full/incremental equivalence is normalized; fake watcher events avoid
  timing dependence; read-only fingerprints cover Vault/repository/Git paths.
- **Maintainability/deep modules:** adapters do not own storage; CLI does not
  own parsing; query service does not read SQL; Tree-sitter nodes do not leak
  beyond parser adapters; code catalog does not replace `VaultCatalog`.
- **Agent ergonomics:** CLI returns bounded line evidence, stable identities,
  relation provenance, and explicit freshness warnings; Round 2 can consume the
  same `CodeQueryService` without reimplementing traversal.

## Errors and edge cases covered

- missing/non-directory roots, duplicate IDs, duplicate roots, and overlapping
  repositories
- code root equal to/inside Vault, symlink escape, invalid glob, and unsupported
  language
- parser syntax errors, grammar gaps, changed-during-parse files, and missing
  source at query time
- ambiguous/dynamic calls, unresolved targets, cross-repository references, and
  retry after target changes
- added/modified/deleted files, unchanged untracked files, interrupted runs,
  stale/partial/unknown state, unavailable store, and unsafe generation paths
- dry-run no-write behavior, watcher unavailable, and bounded traversal limits

## Verification commands

After all tasks:

```bash
uv run pytest -q
uv run ruff check .
uv run ruff format --check .
uv run mypy src
uv build
git diff --check
```

Expected signals:

- all existing tests plus Round 1 tests pass
- no Ruff or mypy errors
- package build succeeds with parser dependencies included
- completion fixture reports zero duplicate/dangling resolved edges
- repository/Vault/Git fingerprints are unchanged
- local `main`/feature worktree is clean after the final local commit
- no remote push is performed

## Risks and mitigations

| Risk | Mitigation |
| --- | --- |
| Dart grammar is community-maintained or incomplete | Pin revision/ABI, fixture-gate required constructs, expose partial diagnostics, defer Dart Analyzer enrichment |
| Parser dependency wheels differ by platform | Dependency smoke test before implementation; use a reproducible grammar artifact and fail clearly when unavailable |
| Code-only activation breaks Vault projections | Separate code active manifest and generation namespace; test existing Vault manifest hash before/after |
| Dynamic calls create false impact | Keep uncertain edges labeled and out of confident traversal |
| Source changes after indexing | Hash live bounded reads and return explicit freshness warnings |
| Watcher event storms or partial runs | Debounce/coalesce events, use same transactional reconcile, retain prior active generation |
| FTS becomes a second source body | Store only structural fields and assert forbidden body/excerpt columns are absent |
| CLI grows into a second application service | Keep `code_commands.py` thin and route all behavior through code-index services |

## Open decisions

No new product decision is required before implementation. The plan follows the
approved design recommendations:

- Tree-sitter is the Round 1 primary parser; Dart Analyzer is optional later.
- The watcher is opt-in and unavailable is explicit when its optional backend is
  not installed.
- Code projection activation is independent from Vault projection activation.
- Numeric performance targets are established after the completion fixture
  baseline, not guessed in the first implementation.

## Handoff

Plan path: `docs/superpowers/plans/2026-08-03-round-1-code-projection.md`

Implementation must use either `@superpowers:subagent-driven-development`
(recommended) or `@superpowers:executing-plans`. Each task should be reviewed
and committed locally before the next task. No remote branch push is implied by
this plan.
