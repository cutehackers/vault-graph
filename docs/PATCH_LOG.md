# Patch Log

This log records implementation corrections made after review so that project
changes remain traceable to Vault Graph's core values.

## 2026-06-08 - Phase 2B Implementation Correction

**Trigger:** Phase 2B implementation dependency probe found that FastEmbed 0.8.0
does not expose `specific_model_path` in the `TextEmbedding` wrapper signature.

**Scope:** `docs/superpowers/plans/2026-06-08-phase-2b-local-vector-indexing.md`
and Phase 2B vector contract tests.

**Core Values Protected:**

- local embeddings remain revision-pinned instead of silently loading an
  unpinned model
- vector revisions remain internally consistent
- implementation corrections stay separate from accepted product decisions

**Changes Applied:**

- Changed the FastEmbed API probe to verify actual `specific_model_path`
  propagation through `TextEmbedding(**kwargs)` into the concrete ONNX model.
- Clarified vector test fixture setup so `record.vector_index_revision` matches
  the revision being applied.
- Corrected the metadata chunk-listing test example so chunk text follows the
  existing `heading-section-v1` contract: headings are section metadata, not
  repeated inside chunk text.
- Corrected the default FastEmbed version identity so
  `EmbeddingModelSpec.model_version` pins the actual FastEmbed ONNX artifact
  revision (`faf4aa4225822f3bc6376869cb1164e8e3feedd0`) while the original
  `sentence-transformers` revision remains provenance metadata.
- Hardened Chroma dry-run/status reads so read-only paths inspect
  `chroma.sqlite3` without opening `PersistentClient` or creating Chroma state.
- Added Chroma collection schema metadata validation for Vault Graph
  collections.
- Changed vector embedding batch input IDs to include `vault_id` plus
  `chunk_id`, preserving the storage contract where chunk IDs are unique only
  inside a Vault.
- Added production Chroma revision-consistency validation so direct adapter
  calls cannot persist records under a mismatched vector revision.
- Added CLI coverage for vector-step failure after metadata success.

**Verification:**

- `uv run --python 3.12 python - <<'PY' ... PY` FastEmbed propagation probe
- `uv run --python 3.12 pytest tests/test_vector_store_contract.py -q`

## 2026-06-08 - Phase 2B Implementation Plan Review Hardening

**Trigger:** Subagent review found Phase 2B implementation-plan gaps before
coding.

**Scope:** `docs/superpowers/plans/2026-06-08-phase-2b-local-vector-indexing.md`.

**Core Values Protected:**

- vector state remains scope-local, rebuildable, and recoverable
- multi-vault content scopes stay explicit
- dry-run remains read-only and non-initializing
- Chroma and FastEmbed remain replaceable behind stable boundaries

**Changes Applied:**

- Added metadata preview planning so vector dry-run can see post-metadata chunks
  without writing SQLite state.
- Added per-Vault effective-scope requirements and tests for vector reconcile.
- Changed vector status planning from global state to scope/model-spec keyed
  status records.
- Added Chroma no-create read tests for dry-run, exact tombstone matching, and
  dependency API probes for FastEmbed revision-pinned loading.
- Kept existing `IndexService.plan/apply` compatibility and added
  `run_plan/run_apply` for Phase 2B orchestration.
- Added cache-path read-only guard coverage and corrected Typer missing-command
  assertions to use `result.output`.

**Verification:**

- subagent review focused on product/spec consistency
- subagent review focused on implementation feasibility
- self-review against the Phase 2B design acceptance criteria
- `git diff --check`

## 2026-06-08 - Phase 2B Spec Consistency Update

**Trigger:** Phase 2B local vector indexing decisions required the core product,
design, feature, and decision documents to agree before implementation planning.

**Scope:** Phase 2B documentation for local vector indexing.

**Core Values Protected:**

- vector state remains read-only, rebuildable, and recoverable
- local-first default remains simple for users
- vector indexing remains separate from search and graph traversal
- multi-vault and content-scope consistency remain explicit

**Changes Applied:**

- Expanded `docs/SPEC.md` Phase 2B with the accepted Chroma, embedding,
  indexing, collection, and model-spec decisions.
- Added scope-local reconcile requirements for vector sustainability and future
  graph indexing alignment.
- Updated `docs/DESIGN.md` with `MetadataStore.list_chunks(scope)`,
  `VectorIndexer` responsibilities, manifest reconcile metadata, and partial
  failure behavior.
- Updated `docs/FEATURES.md` so Phase 2B user-facing behavior stays limited to
  `vg index` and `vg status`.
- Added the accepted Phase 2B architecture decision to `docs/DECISIONS.md`.
- After grill-with-docs and subagent review, separated vector staleness
  comparison keys from lineage/status fields so `vector_index_revision` does
  not stale every run.
- Phase-gated generic graph indexing flow as Phase 3+ so Phase 2B cannot expand
  into graph extraction or traversal.
- Added per-Vault effective-scope requirements for `MetadataStore.list_chunks`
  and `VectorStore.export_manifest`.
- Clarified vector tombstone identity for model-spec collection reconcile.
- Clarified `vg index` partial-failure behavior as nonzero exit plus preserved
  metadata revision and stale vector status.
- Closed the Phase 2B default embedding decision by accepting
  `FastEmbedTextEmbeddings` with
  `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` as the default
  local embedding path, pinned to FastEmbed artifact revision
  `faf4aa4225822f3bc6376869cb1164e8e3feedd0`; source-model provenance remains
  `e8f8c211226b894fcb81acc59f3b34ba3efd5f42`.
- Added CPU embedding throughput tuning guidance for `embedding_batch_size`,
  parallelism, lazy loading, dry-run output, and failure behavior.
- Added a SPEC TODO for a future MacBook acceleration adapter that keeps CPU
  FastEmbed as the default and treats Apple acceleration as an explicit
  `TextEmbeddings` adapter.
- Added a SPEC TODO for future non-Markdown document reader adapters while
  keeping Phase 2B indexing Markdown-only by default.

**Verification:**

- grill-with-docs consistency pass
- subagent review focused on product value, software design integrity, and
  implementation-plan readiness
- `git diff --check`
- `uv run --python 3.12 pytest -q`
- `uv run --python 3.12 ruff check src tests`
- `uv run --python 3.12 mypy src`
- `uv run --python 3.12 mypy tests`

## 2026-06-08 - Phase 2A Plan Review Hardening

**Trigger:** Subagent review found Phase 2A plan gaps before implementation.

**Scope:** Phase 2A retrieval contract and `VectorStore` implementation plan.

**Core Values Protected:**

- multi-vault evidence remains explicit
- vector state remains rebuildable from model-spec-aware records
- vector hits do not become evidence authority
- missing or stale evidence remains visible as diagnostics

**Changes Applied:**

- Removed the plan's cross-vault-hostile assumption that every result evidence
  item must share the result `vault_id`.
- Added a vector-hit-to-evidence binding guard to the plan so normal vector
  results require matching `vault_id`, `document_id`, and `chunk_id`.
- Added model-spec-aware vector ID derivation and mixed-model-spec rejection to
  the in-memory `VectorStore` contract plan.
- Added missing/stale evidence warning tests and duplicate embedding input ID
  tests to the plan.
- Added final documentation verification for the Chroma/Qdrant shared
  `VectorStore` contract.

**Verification:**

- `git diff --check`

## 2026-06-08 - Phase 2A Implementation Review Fixes

**Trigger:** Subagent implementation reviews found contract consistency gaps
while implementing Phase 2A.

**Scope:** Phase 2A embedding, vector, metadata evidence, retrieval result, and
boundary tests.

**Core Values Protected:**

- `QueryScope` filtering remains consistent across metadata and vector layers
- failed derived-state writes do not leave misleading fake backend state
- metadata remains the evidence authority
- retrieval result revision metadata stays immutable and inspectable

**Changes Applied:**

- Made `VectorStore` content-scope filtering use same-or-child semantics before
  applying result limits.
- Added a regression test so a failed mixed-model vector revision does not pin
  an empty vector store to the wrong embedding model spec.
- Required `MetadataStore.resolve_chunk_evidence(...)` to match document and
  chunk paths before returning evidence.
- Scoped `MetadataStore.resolve_chunk(...)` by `vault_id` so duplicate chunk IDs
  across registered Vaults cannot resolve ambiguously.
- Replaced mutable retrieval `store_revisions` mappings in the Phase 2A
  contract with immutable `StoreRevision` records.
- Added Phase 2A boundary tests proving `vg search` and vector status output
  remain out of scope.

**Verification:**

- `uv run --python 3.12 pytest tests/test_vector_store_contract.py -q`
- `uv run --python 3.12 pytest tests/test_metadata_evidence_resolution.py tests/test_sqlite_metadata_store.py -q`
- `uv run --python 3.12 pytest tests/test_retrieval_result_contract.py -q`
- `uv run --python 3.12 pytest tests/test_phase_2a_boundary.py -q`
- `uv run --python 3.12 ruff check src tests`
- `uv run --python 3.12 mypy src`
- `uv run --python 3.12 mypy tests`

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
