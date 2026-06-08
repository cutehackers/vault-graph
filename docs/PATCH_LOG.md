# Patch Log

This log records implementation corrections made after review so that Phase 1
changes remain traceable to Vault Graph's core values.

## 2026-06-05 - Phase 1 Pre-Implementation Review Hardening

**Trigger:** Subagent review found Phase 1 risks before implementation.

**Scope:** `2026-06-05-phase-1-vault-catalog-metadata`

**Core Values Protected:**

- Vault remains read-only
- derived state is rebuildable
- multi-vault identity is explicit
- local-first tooling remains verifiable

**Changes Applied:**

- Added a state path guard so Vault Graph state cannot be written inside a
  registered Vault root.
- Made metadata dry-run use a non-initializing SQLite store so dry-run does not
  create metadata directories, databases, or schema.
- Validated `VaultCatalogEntry.content_scopes` so configured scan roots cannot
  escape the Vault root.
- Expanded metadata freshness checks beyond content hash to include
  frontmatter hash, raw SHA-256, parser version, and tombstone state.
- Made chunk IDs unique for repeated headings within the same document by
  including chunk position in stable ID derivation.
- Added `vg index --full` and rejected conflicting `--vault-id` plus
  `--all-vaults` selection.
- Moved development tools into `dependency-groups.dev` so `uv run pytest`,
  `uv run ruff`, and `uv run mypy` use repository-local tooling.
- Verified the installed `vg` console script is exposed by the package.

**Verification:**

- `uv run --python 3.12 pytest -q`
- `uv run --python 3.12 ruff check src tests`
- `uv run --python 3.12 mypy src`
- `uv run --python 3.12 vg --help`

## 2026-06-05 - Phase 1 Post-Implementation Boundary Review Fixes

**Trigger:** Subagent implementation reviews found read-only, dry-run, scope,
and tombstone gaps.

**Scope:** Phase 1 implementation under `src/vault_graph/`, tests, and CLI
composition.

**Core Values Protected:**

- Vault Graph must not write inside registered Vault roots.
- Dry-run planning must not initialize derived state.
- Stale derived records must not appear fresh after tombstoning.
- Multi-vault and content-scope selection must remain explicit and bounded.

**Changes Applied:**

- Re-ran the state-path guard after loading an existing catalog and before any
  write-capable metadata store is opened.
- Added write-target validation for catalog and metadata files so symlinked
  state subdirectories cannot redirect writes into Vault content.
- Made `SQLiteMetadataStore` non-initializing by default; write-capable callers
  must opt in with `initialize=True`.
- Deleted chunk rows when documents are tombstoned and filtered tombstoned
  documents from document resolution/export.
- Added schema compatibility checks to metadata health and exposed schema status
  in `vg status`.
- Added chunker-version freshness comparison during incremental planning.
- Refactored metadata apply so one loaded snapshot is used for both planning and
  writing a revision.
- Rejected unsupported content scopes such as empty scope, `.`, parent
  traversal, arbitrary roots, and unsupported `scratch` subtrees.
- Skipped symlinked Markdown files during Vault loading to avoid indexing
  targets outside the registered Vault root.
- Rendered catalog and read-only boundary errors as user-facing CLI failures.
- Typed `IndexService` against the `MetadataStore` interface instead of the
  SQLite backend.

**Verification:**

- `uv run --python 3.12 pytest -q`
- `uv run --python 3.12 ruff check src tests`
- `uv run --python 3.12 mypy src`

## 2026-06-05 - Phase 1 Final Indexing Scope Fixes

**Trigger:** Final subagent review found two remaining P1 indexing-state
consistency blockers.

**Scope:** `MetadataIndexer` deletion planning and regression tests.

**Core Values Protected:**

- `QueryScope` must not let a narrow content scan alter unrelated derived
  records.
- Tombstones must be idempotent derived state, not repeatedly reported as new
  deletes.

**Changes Applied:**

- Filtered current metadata state by effective `QueryScope.content_scopes`
  before computing deleted paths.
- Excluded already tombstoned document states from later `deleted_paths`.
- Added regression tests for partial content-scope indexing and repeated
  tombstone planning.

**Verification:**

- `uv run --python 3.12 pytest tests/test_metadata_indexer.py -q`

## 2026-06-05 - Phase 1 Narrow Policy Scope Fix

**Trigger:** Final subagent re-review found that a query scope narrower than a
catalog entry scope could be treated as empty and then tombstone existing files.

**Scope:** `VaultLoader` effective content-scope calculation and metadata
indexer regression tests.

**Core Values Protected:**

- Narrow policy scopes must refine a registered Vault scope, not erase it.
- `QueryScope` must be safe for incremental indexing.

**Changes Applied:**

- Made effective loader scopes prefix-aware: `entry=wiki` with
  `query=wiki/systems` scans `wiki/systems`, while broader queries remain
  constrained by the entry scope.
- Added regression tests for narrower policy scope loading and indexing.

**Verification:**

- `uv run --python 3.12 pytest tests/test_vault_loader.py::test_loader_allows_query_scope_narrower_than_entry_scope tests/test_metadata_indexer.py::test_narrower_policy_scope_indexes_existing_file_under_broader_entry_scope -q`
