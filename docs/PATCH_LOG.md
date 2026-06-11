# Patch Log

This log records implementation corrections made after review so that project
changes remain traceable to Vault Graph's core values.

## 2026-06-11 - Phase 3C Boundary Hardening Review Fixes

**Trigger:** Subagent review of the Phase 3C boundary hardening slice found
that cross-Vault readiness could reuse local graph revisions without inspecting
the same local graph manifest rows, and plain CLI import loaded the rustworkx
projection adapter too early.

**Scope:** Graph readiness, projection package exports, CLI graph service
factory imports, read-only boundary tests, multi-vault retrieval tests, and
import boundary tests.

**Core Values Protected:**

- graph retrieval remains read-only and does not auto-create derived state
- cross-Vault graph traversal preserves evidence freshness diagnostics
- plain search avoids graph projection work until explicitly requested
- public projection contracts stay lightweight while adapter loading is lazy

**Changes Applied:**

- Made `ReadOnlyGraphReadiness` use the same expanded graph lookup scopes for
  graph revisions and graph manifests when actual scopes request cross-Vault
  traversal.
- Kept readiness output attributed to the original actual scope while falling
  back to local graph revision and tombstone state for cross-Vault reads.
- Added SQLite-backed regression coverage proving cross-scope readiness still
  detects stale local graph evidence.
- Moved `RustworkxGraphProjection` loading out of CLI module import and into
  the graph retrieval factory.
- Changed `vault_graph.projection` to lazily expose `RustworkxGraphProjection`
  via `__getattr__` instead of importing rustworkx during package import.
- Added read-only state-tree, multi-vault identity, stale-scope, import
  boundary, and public export smoke tests.

**Verification:**

- subagent boundary review, code quality review, and focused re-reviews
- `uv run --python 3.12 pytest tests/test_graph_readiness.py tests/test_graph_retrieval_read_only_boundary.py tests/test_multi_vault_graph_retrieval.py tests/test_retrieval_import_boundaries.py tests/test_package_import.py -q`
- `uv run --python 3.12 pytest -q`
- `uv run --python 3.12 ruff check .`
- `uv run --python 3.12 mypy src tests`
- `git diff --check`

## 2026-06-11 - Phase 3C Opt-In Graph Search Review Fixes

**Trigger:** Subagent review of the Phase 3C `vg search --include-graph`
slice found cross-Vault scope attribution and warning-only graph revision gaps.

**Scope:** Opt-in graph search candidate conversion, `vg search` graph flags,
search response scope metadata, and graph-search regression tests.

**Core Values Protected:**

- plain search remains keyword/vector unless graph is explicitly requested
- graph search is evidence-first and degrades to visible warnings
- multi-vault graph traversal preserves explicit scope identity
- graph-derived results keep searched graph revision attribution

**Changes Applied:**

- Added `GraphSearchCandidateProvider` and wired it into search only when
  `--include-graph` is provided.
- Converted related graph paths into `RetrievalCandidate` rows only from
  relationship evidence chunks.
- Converted graph lookup, readiness, target, and ambiguity issues into
  top-level `SearchWarning` records for opt-in graph search.
- Marked requested and actual search scopes with `include_cross_vault=True`
  when graph cross-Vault traversal is requested.
- Preserved graph store revisions for fresh warning-only graph lookups such as
  `graph_target_not_found`.
- Added CLI and service regression tests for graph opt-in behavior, degradation,
  ranking weight, cross-Vault flag validation, and plain-search graph isolation.

**Verification:**

- subagent spec review, code quality review, and focused re-review
- `uv run --python 3.12 pytest tests/test_search_include_graph.py tests/test_cli_search.py -q`
- `uv run --python 3.12 pytest -q`
- `uv run --python 3.12 ruff check .`
- `uv run --python 3.12 mypy src tests`
- `git diff --check`

## 2026-06-11 - Phase 3C `vg decision-trace` Implementation Review Fixes

**Trigger:** Subagent review of the Phase 3C decision trace slice found target
priority, projection-rank tie-break, text evidence identity, trace limit, and
read-only regression gaps.

**Scope:** `GraphRetrievalService.decision_trace`, `vg decision-trace` CLI
rendering, service/CLI tests, and graph retrieval review fixtures.

**Core Values Protected:**

- decision traces remain evidence-first and do not synthesize answers
- durable `Decision` entities are preferred without hiding topic fallback
- graph output preserves Vault-scoped evidence identity
- read-only graph commands do not create missing derived state or caches

**Changes Applied:**

- Made decision target resolution apply entity-type priority before match-rank
  tie-breaks and allow lexical fallback only when no exact match exists.
- Preserved projection rank after role priority and projection score while
  ordering decision trace path steps.
- Rendered text evidence with `[vault_id]` prefixes for related and decision
  trace outputs.
- Treated `limit` as total trace steps by subtracting the initial identity step
  from the projection path budget.
- Added real `vg decision-trace` factory no-mutation coverage and no-synthesis
  output assertions.

**Verification:**

- subagent exploration, spec review, code quality review, and focused re-reviews
- `uv run --python 3.12 pytest -q`
- `uv run --python 3.12 ruff check src tests`
- `uv run --python 3.12 mypy src tests`
- `git diff --check`

## 2026-06-11 - Phase 3C `vg related` Implementation Review Fixes

**Trigger:** Subagent review of the Phase 3C `vg related` CLI slice found that
text output hid cross-Vault actual-scope state, JSON output compressed nested
graph records, and the real read-only graph retrieval factory lacked regression
coverage.

**Scope:** `vg related` CLI rendering, JSON mapping, real factory read-only
regression coverage, and Vault-scoped candidate suppression.

**Core Values Protected:**

- graph retrieval remains explicit and evidence-linked in text and JSON output
- multi-vault graph output preserves Vault-scoped identities
- read-only graph commands do not create missing derived state or caches

**Changes Applied:**

- Rendered `vg related` actual scopes with the graph scope key, including
  `local`/`cross` state.
- Expanded related JSON mapping to include full nested entity, relationship,
  and graph evidence reference contract fields.
- Added a real `vg related` factory regression proving missing graph state
  returns a recovery warning without creating metadata, graph, or projection
  cache files.
- Changed resolved-target candidate suppression to compare
  `(vault_id, entity_id)`.

**Verification:**

- subagent spec review, code quality review, and focused re-reviews
- `uv run --python 3.12 pytest tests/test_cli_related.py tests/test_cli_surface_boundary.py tests/test_cli_search.py tests/test_graph_retrieval_service.py -q`
- `uv run --python 3.12 ruff check src/vault_graph/cli/main.py tests/test_cli_related.py tests/test_cli_surface_boundary.py tests/test_cli_search.py tests/test_graph_retrieval_service.py`
- `uv run --python 3.12 mypy src/vault_graph/cli/main.py tests/test_cli_related.py tests/test_cli_surface_boundary.py tests/test_cli_search.py tests/test_graph_retrieval_service.py`

## [PATCH-0001] Phase 3C Implementation Plan Review Hardening

- **Reason:** Multi-angle subagent review found Phase 3C implementation-plan
  gaps that could cause unbounded graph lookup, hidden truncation, graph-search
  degradation failures, projection/storage coupling, incomplete read-only tests,
  and duplicated retrieval signal DTOs.
- **Before:** Phase 3C plan used an unwrapped `find_entities` return value,
  allowed alias/path fallback scans without a hard scan cap, passed only seed
  nodes into `GraphProjectionInput`, did not require graph-search readiness
  failures to degrade, used a duplicate `CandidateSignal`, and left some
  read-only/multi-vault/test fixture requirements implicit.
- **After:** Phase 3C plan and design now use `GraphEntityQueryResult` with
  truncation metadata, bounded entity scan/read/result/projection limits,
  `graph_target_scan_truncated` and `graph_relationship_read_truncated`
  warnings, `GraphProjectionInput.nodes`, existing `RetrievalSignal` records in
  `RetrievalCandidate`, `requested_scope` in graph candidate providers,
  explicit graph-search readiness degradation tests, broader read-only state
  tree assertions, and executable smoke setup.
- **Scope:** `docs/superpowers/plans/2026-06-11-phase-3c-graph-projection-retrieval.md`,
  `docs/superpowers/specs/phase-3/2026-06-10-phase-3c-graph-projection-retrieval-design.md`,
  `docs/PATCH_LOG.md`

## 2026-06-11 - Phase 3C Design Consistency Update

**Trigger:** Phase 3C implementation planning needed a detailed design, while
the top-level Phase 3 contract still described the Phase 3C slice as planned.

**Scope:** Phase 3A/3C design documents, Phase 3 design index, overview, and
top-level SPEC link references.

**Core Values Protected:**

- graph retrieval remains explicit, evidence-first, and read-only
- `GraphProjection` stays a bounded runtime view, not graph authority
- default search remains keyword/vector unless graph is explicitly requested
- multi-vault graph traversal preserves source, target, and evidence Vault IDs

**Changes Applied:**

- Added the Phase 3C graph projection and retrieval design.
- Linked Phase 3C from the Phase 3 README, overview, and top-level SPEC.
- Removed stale "future Phase 3C" wording from the Phase 3A handoff.
- Specified read-only graph commands, target resolution, graph warnings,
  evidence resolution, and opt-in graph search integration.
- Tightened graph evidence gating so every relationship edge must resolve
  relationship evidence before ranking, rendering, or search fusion.
- Changed stale and empty graph scopes to omit normal graph results by default.
- Fixed all-vault same-name target handling as ambiguity-only, not automatic
  multi-seed traversal.
- Added graph query result wrappers, projection input/result types, and a public
  retrieval candidate seam for opt-in graph search.
- Kept persistent projection-cache writes out of Phase 3C read paths.

**Verification:**

- grill-with-docs consistency pass
- multi-angle subagent review and focused re-review
- stale-path and Markdown consistency scans

## 2026-06-11 - Phase 3B Implementation Review Fixes

**Trigger:** Subagent implementation review found that delete/tombstone graph
reconciles could still report stale readiness and double-count tombstones.

**Scope:** Phase 3B graph indexing, graph readiness, and regression tests.

**Core Values Protected:**

- `vg status` reflects current rebuildable graph state after successful indexing
- tombstones remain latest-state derived records, not stale active evidence
- relationship occurrence status is preserved across the indexing boundary
- repeated graph indexing is idempotent for already tombstoned records

**Changes Applied:**

- Excluded tombstoned entities and deprecated relationships from graph evidence
  freshness checks.
- Reported current manifest tombstone counts without adding latest-run work
  counts from graph revisions.
- Stopped planning repeat tombstones for records already tombstoned in the
  selected actual scope.
- Preserved `RelationshipOccurrence.status` when creating relationship records.
- Added regression coverage for delete reindex freshness, stale-count reset
  after content refresh, repeat-delete idempotence, and relationship status
  pass-through.

**Verification:**

- subagent implementation review and focused re-review
- `uv run --python 3.12 pytest -q`
- `uv run --python 3.12 ruff check src tests`
- `uv run --python 3.12 mypy src`
- `uv run --python 3.12 mypy tests`

## 2026-06-11 - Phase 3B Implementation Plan Review Hardening

**Trigger:** Multi-angle review of the Phase 3B implementation plan found gaps
in lineage staleness, dry-run safety, graph failure status, tombstone repair,
scope normalization, and extractor package alignment.

**Scope:** Phase 3B implementation plan only.

**Core Values Protected:**

- graph indexing remains read-only, rebuildable, and evidence-linked
- status surfaces report graph freshness and failures without hidden state
- whole-Vault graph scopes stay consistent across single-vault and all-vault runs
- deterministic extraction uses stable domain names instead of roadmap labels
- Phase 3B does not leak graph traversal into default search

**Changes Applied:**

- Moved extraction modules in the plan to `src/vault_graph/extraction/`.
- Required behavior-named `GraphExtractionSpec` values and a version bump before
  real graph indexing writes records.
- Added graph status persistence for last graph success and failure.
- Added graph store hardening for scoped tombstone repair and SQLite read errors.
- Added lineage parity with graph readiness, including metadata schema fallback.
- Added projection-cache invalidation plan keys without projection-cache writes.
- Added unresolved-link warnings, dry-run side-effect checks, unsupported-scope
  no-op checks, and default-search no-scope-creep regression coverage.

**Verification:**

- multi-angle subagent plan review
- plan self-review against Phase 3B spec and current Phase 3A contracts
- Markdown fence and stale-path scans

## 2026-06-11 - Phase 3B Design Consistency Update

**Trigger:** Phase 3B detailed design was needed before implementation, and the
core documents still described the Phase 3B slice as planned.

**Scope:** Phase 3B design document, Phase 3 design index, top-level SPEC,
feature surface, and extraction module naming references.

**Core Values Protected:**

- graph indexing remains read-only and rebuildable over Vault-derived evidence
- Phase 3B stays deterministic and local-first before graph retrieval is exposed
- graph reconcile remains per Vault/actual scope
- source module names describe domain responsibility instead of schedule labels

**Changes Applied:**

- Added the Phase 3B local entity and relationship indexing design.
- Linked Phase 3B from the Phase 3 README, overview, and top-level SPEC.
- Clarified Phase 3B index output for independent vector and graph indexing failures.
- Standardized the extraction module reference to `relationship_extractor.py`.
- Added Vault-scoped `GraphSourceStore` and `GraphExtractionContext` boundaries
  after implementation-readiness review.
- Limited Phase 3B graph indexing to whole selected Vault scopes until an
  overlap-aware manifest contract exists.
- Clarified that `projection_cache_invalidations` are plan keys only in Phase
  3B, not projection-cache writes.

**Verification:**

- grill-with-docs consistency pass
- multi-angle subagent review and focused re-review
- stale-term and forbidden naming scans
- `uv run --python 3.12 pytest -q`
- `uv run --python 3.12 ruff check src tests`
- `uv run --python 3.12 mypy src`
- `uv run --python 3.12 mypy tests`
- `git diff --check`

## 2026-06-10 - Phase 3A Implementation Review Fixes

**Trigger:** Subagent review of the Phase 3A implementation found consistency
risks in graph record scope membership, evidence freshness attribution, SQLite
schema health, extraction spec compatibility, tombstone idempotence, and
metadata-health handling.

**Scope:** Phase 3A graph contracts, graph stores, readiness service, CLI
status integration, and regression tests.

**Core Values Protected:**

- graph records remain scoped to the owning Vault/actual scope
- stale evidence in one Vault does not make unrelated Vault scopes stale
- SQLite graph readiness reports incompatible schema before read paths fail
- `GraphExtractionSpec` remains the compatibility boundary until a migration
  policy is explicitly accepted
- graph tombstones stay rebuildable latest-state records, not append-only facts
- `vg status` stays read-only when metadata or graph state is unavailable

**Changes Applied:**

- Added shared multi-scope `GraphStore` contract coverage and scoped record
  membership by record owner Vault.
- Changed graph evidence freshness checks from global manifest warnings to
  per-actual-scope warnings.
- Expanded SQLite graph schema health checks to every column read or written by
  the backend.
- Treated graph extraction spec version/digest drift as incompatible without a
  migration policy.
- Made tombstone application keep the latest tombstone per
  `(record_kind, record_vault_id, record_id, actual_scope)`.
- Short-circuited graph readiness when metadata health is unavailable or
  incompatible.
- Added SQLite-backed graph readiness coverage and stricter status read-only
  state-cache assertions.

**Verification:**

- `uv run --python 3.12 pytest tests/test_graph_readiness.py -q`
- `uv run --python 3.12 pytest tests/test_graph_store_contract.py tests/test_sqlite_graph_store.py tests/test_multi_vault_graph_identity.py -q`
- focused read-only status regression

## 2026-06-10 - Phase 3A Implementation Plan Review Hardening

**Trigger:** Multi-angle subagent review found that the first Phase 3A
implementation plan left important graph readiness, manifest, and multi-vault
details under-specified.

**Scope:** `docs/superpowers/plans/2026-06-10-phase-3a-graphstore-contract-readiness.md`.

**Core Values Protected:**

- graph readiness cannot claim freshness without metadata-resolved evidence
- graph manifests stay scoped without treating cached path text as authority
- multi-vault graph status remains per Vault/actual scope
- `GraphStore` stays a deep boundary with explicit records and backend-stamped
  schema lineage
- graph status remains read-only and typed when graph state is missing or
  unavailable

**Changes Applied:**

- Added exact graph dataclass shapes for manifest rows, apply results, reconcile
  plans, and explicit graph record scope membership.
- Changed manifest membership to use explicit actual-scope rows instead of
  cached graph evidence paths.
- Required readiness to resolve graph evidence through `MetadataStore` and mark
  unresolved or stale evidence as stale with recovery guidance.
- Added per-scope graph readiness rows and status JSON output for all-vault
  graph status.
- Added explicit cross-vault manifest behavior using `include_cross_vault`.
- Required SQLite graph stores to stamp backend schema version and upsert schema
  metadata.
- Chose latest tombstone per record/scope through UPSERT for idempotent
  rebuildable derived state.
- Added graph-domain error handling to the CLI status boundary.

**Verification:**

- multi-angle subagent review
- placeholder and stale-path scans
- `git diff --check`

## 2026-06-10 - Phase 3 Graph Specification Clarification

**Trigger:** Phase 3 roadmap text was too thin to hand off to implementation,
and older graph wording still mixed node/edge identity with Phase 2C's
evidence-chunk authority.

**Scope:** Phase 3 specification, design, search architecture, and user-facing
feature documentation.

**Core Values Protected:**

- graph state remains read-only, rebuildable derived state over Vault
- relationship evidence resolves through metadata evidence chunks
- multi-vault graph identity stays explicit and collision-safe
- Phase 3 scales through clear `GraphStore` and `GraphProjection` boundaries
- default search behavior does not silently widen through inferred graph signals

**Changes Applied:**

- Expanded Phase 3 into definite Phase 3A, 3B, and 3C slices.
- Moved detailed Phase 3 graph design handoff under
  `docs/superpowers/specs/phase-3/` so `docs/SPEC.md` stays a concise top-level
  contract.
- Added a focused Phase 3A `GraphStore` contract and readiness design document.
- Clarified `GraphExtractionSpec` as the graph staleness and compatibility
  boundary.
- Replaced stale node/edge and extraction-policy wording with entity,
  relationship, and graph-extraction-spec terminology.
- Added Phase 3 user-facing slice expectations for graph readiness, graph
  indexing, `vg related`, `vg decision-trace`, and opt-in graph search.
- Aligned search architecture with evidence-chunk-based graph results.
- Fixed subagent review findings by making relationship evidence a child
  evidence-row contract, assigning graph reconcile planning to `GraphIndexer`,
  defining scoped graph manifests, and making graph revisions per
  Vault/actual scope under a run-level ID.
- Fixed relationship identity ambiguity by storing Phase 3 relationships as
  directed records and leaving symmetric behavior to query/view policy.
- Narrowed Phase 3A back to contract readiness by moving traversal-style lookup
  APIs to Phase 3C, making graph record lookups Vault-scoped, and introducing
  `GraphReadinessService` for metadata-lineage-aware freshness checks.
- Replaced ambiguous optional evidence ownership fields with explicit
  `owner_kind`, `owner_vault_id`, `owner_id`, and `evidence_vault_id`.
- Added graph extraction spec digest/snapshot requirements so compatibility is
  not inferred from version strings alone.
- Added Phase 3 index/status reliability signals and cross-Vault graph command
  examples to the user-facing feature document.

**Verification:**

- grill-with-docs consistency pass
- multi-angle subagent review
- stale-term grep checks
- `git diff --check`

## 2026-06-09 - Phase 2C Implementation Review Fixes

**Trigger:** Subagent review of the Phase 2C implementation found consistency
gaps in search readiness, warning attribution, read-only vector failure
visibility, and CLI output.

**Scope:** Phase 2C keyword/vector search implementation.

**Core Values Protected:**

- search remains evidence-first and inspectable
- search failures return clear recovery diagnostics instead of raw backend
  errors
- multi-vault degraded conditions stay attributed to the affected Vault/scope
- retrieval stays independent from app-layer orchestration
- CLI JSON remains a stable public response shape

**Changes Applied:**

- Stopped readiness revision calculation when metadata or keyword schemas are
  incompatible, so `vg search` reports domain errors with `vg index` recovery
  guidance.
- Added scope-level vector staleness readiness and warning attribution.
- Made existing Chroma client failures visible as `VectorStoreError` so
  retrieval can emit `vector_query_failed` warnings instead of silent empty
  vector results.
- Moved actual query scope resolution to the ingestion/catalog boundary and
  kept the app module as a thin compatibility export.
- Made keyword index revision reporting owned by the keyword interface instead
  of inferring keyword provenance from metadata revisions.
- Tightened SQLite keyword `matched_fields` to report fields that contain query
  tokens.
- Added resolved Vault/actual-scope lines to text search output and replaced
  `asdict` JSON rendering with explicit serializers.

**Verification:**

- subagent review focused on product/spec alignment
- subagent review focused on read-only and multi-vault invariants
- subagent review focused on code quality and interface boundaries
- `uv run --python 3.12 pytest -q`
- `uv run --python 3.12 ruff check src tests`
- `uv run --python 3.12 mypy src`
- `uv run --python 3.12 mypy tests`

## 2026-06-09 - Test Source Naming Cleanup

**Trigger:** Phase labels in test source filenames made the code surface feel
tied to a temporary roadmap slice instead of stable Vault Graph behavior.

**Scope:** test source filenames and implementation-plan references.

**Core Values Protected:**

- test names describe product behavior instead of schedule labels
- future search and vector work stays easier to navigate and extend
- documentation can keep roadmap phase labels while code keeps domain names

**Changes Applied:**

- Renamed CLI, vector-indexing, vector-reconcile, and CLI-surface boundary
  tests from phase-based filenames to behavior-based filenames.
- Updated implementation-plan references so future Phase 2C work creates
  behavior-named test files such as `test_cli_search.py`,
  `test_retrieval_service_search.py`, and `test_multi_vault_search.py`.
- Kept phase labels in roadmap/specification document filenames where they
  describe project history rather than source ownership.

**Verification:**

- `rg` check for stale phase-based test file and function names
- focused renamed test suite
- `git diff --check`

## 2026-06-09 - Phase 2C Implementation Plan Review Hardening

**Trigger:** Subagent review found implementation-plan gaps before coding.

**Scope:** `docs/superpowers/plans/2026-06-09-phase-2c-evidence-first-keyword-vector-search.md`.

**Core Values Protected:**

- search remains evidence-first
- `vg search` remains read-only over existing projections
- retrieval stays independent from indexing and local status-store internals
- multi-vault warnings, revisions, results, and signals remain explicitly attributed

**Changes Applied:**

- Moved concrete search-readiness freshness calculation to an app-layer service
  while keeping retrieval dependent only on a readiness protocol.
- Required store revisions to be scope-attributed and search warnings to carry
  non-empty affected Vault IDs.
- Changed response revision assembly to come from readiness, not returned
  results, so zero-result and degraded searches still report projection state.
- Added keyword projection schema-version and FTS-column compatibility checks to
  the implementation plan.
- Strengthened no-download and read-only tests to cover embedding local-only
  checks, existing Chroma state, existing Vault Graph state, and vector status.
- Added implementation-plan coverage for the existing Phase 2B test that must
  change once `vg search` becomes visible in Phase 2C.
- Added service-level multi-vault regressions for content-scope widening and
  same-`chunk_id` keyword/vector fusion collisions.

**Verification:**

- subagent review focused on product/spec consistency
- subagent review focused on implementation readiness
- subagent review focused on multi-vault and read-only consistency
- `git diff --check`

## 2026-06-09 - Phase 2C Search Design Consistency Update

**Trigger:** Phase 2C detailed design needed to fix ambiguity between
user-facing document/page/source search categories and the evidence-chunk result
unit required by the product boundary.

**Scope:** `docs/SPEC.md`, `docs/DESIGN.md`, `docs/FEATURES.md`,
`docs/DECISIONS.md`, `docs/SEARCH_ARCHITECTURE.md`, and
`docs/superpowers/specs/2026-06-09-phase-2c-evidence-first-keyword-vector-search-design.md`.

**Core Values Protected:**

- search remains evidence-first instead of answer-first
- search reads existing projections and does not mutate Vault or index state
- keyword and vector stores remain candidate sources, not evidence authority
- multi-vault result identity remains explicit

**Changes Applied:**

- Fixed Phase 2C around evidence chunk as the canonical search result unit.
- Clarified document/page/source/section search output as grouping views.
- Added a metadata-owned `KeywordIndex` boundary for lexical candidates.
- Added a top-level `SearchResponse` warning contract for degraded search.
- Required rank-based keyword/vector fusion and visible keyword-only degrade
  behavior when vector search is unavailable.
- Required `vg search` to avoid indexing, schema creation, Chroma creation,
  vector status writes, and embedding model downloads.
- Added per-Vault actual search scopes so all-vault search cannot widen one
  Vault with another Vault's content scopes.
- Added explicit no-download embedding readiness and read-only search readiness
  boundaries.
- Fixed keyword projection ownership as a metadata subprojection updated with
  the metadata revision.
- Added structured warning and store-revision attribution requirements for
  multi-vault search responses.

**Verification:**

- grill-with-docs consistency pass
- subagent review focused on product value, software design, and multi-vault
  consistency
- `git diff --check`

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
- Added per-Vault actual-scope requirements and tests for vector reconcile.
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
- Added per-Vault actual-scope requirements for `MetadataStore.list_chunks`
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
- `uv run --python 3.12 pytest tests/test_cli_surface_boundary.py -q`
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

- Filtered current metadata state by actual `QueryScope.content_scopes`
  before computing deleted paths.
- Excluded already tombstoned document states from later `deleted_paths`.
- Added regression tests for partial content-scope indexing and repeated
  tombstone planning.

**Verification:**

- `uv run --python 3.12 pytest tests/test_metadata_indexer.py -q`

## 2026-06-05 - Phase 1 Narrow Policy Scope Fix

**Trigger:** Final subagent re-review found that a query scope narrower than a
catalog entry scope could be treated as empty and then tombstone existing files.

**Scope:** `VaultLoader` actual content-scope calculation and metadata
indexer regression tests.

**Core Values Protected:**

- Narrow policy scopes must refine a registered Vault scope, not erase it.
- `QueryScope` must be safe for incremental indexing.

**Changes Applied:**

- Made actual loader scopes prefix-aware: `entry=wiki` with
  `query=wiki/systems` scans `wiki/systems`, while broader queries remain
  constrained by the entry scope.
- Added regression tests for narrower policy scope loading and indexing.

**Verification:**

- `uv run --python 3.12 pytest tests/test_vault_loader.py::test_loader_allows_query_scope_narrower_than_entry_scope tests/test_metadata_indexer.py::test_narrower_policy_scope_indexes_existing_file_under_broader_entry_scope -q`
