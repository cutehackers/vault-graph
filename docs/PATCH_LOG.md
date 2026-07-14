# Patch Log

This log records implementation corrections made after review so that project
changes remain traceable to Vault Graph's core values.

## 2026-07-14 - Easy MCP Setup Policy Alignment

**Trigger:** User-approved setup direction changed MCP onboarding from
manual-only registration to explicit easy Codex registration through
`vg setup --mcp`.

**Scope:** Setup CLI, MCP config registration, README quick start, `SPEC.md`,
CLI onboarding design, and decision log.

**Core Values Protected:** Kept MCP onboarding simple while preserving explicit
user intent, read-only Vault behavior, config backups, and manual override
paths.

**Changes Applied:**

- Added `vg setup --mcp` as the preferred easy Codex MCP registration path.
- Added bounded Codex TOML registration for `$CODEX_HOME/config.toml` or
  `~/.codex/config.toml`.
- Preserved existing JSON config registration for explicit config paths.
- Updated docs that previously prohibited default Codex config discovery.

**Verification:**

- `uv run --python 3.12 pytest tests/test_setup_service.py tests/test_cli_mcp_config.py -q`

## 2026-06-29 - Decision Log Release Wording Alignment

**Trigger:** Final release-readiness check found that the accepted onboarding
decision still used historical "future" and "CLI TODO" wording after `vg setup`
and MCP registration commands had been implemented.

**Scope:** `docs/DECISIONS.md` setup/onboarding, CLI command documentation, and
Phase 7 UI scope decision wording.

**Core Values Protected:** Kept long-term decision memory aligned with the
implemented source-checkout install path while preserving the separation between
MCP server installation and agent MCP registration.

**Changes Applied:**

- Reworded the setup decision so `vg setup --vault PATH --agent AGENT` is the
  current source-checkout happy path, not a future placeholder.
- Replaced CLI TODO implications with current-command and future-PyPI
  boundaries.
- Reworded the CLI documentation decision so implemented commands are no longer
  described as unavailable.
- Kept the Phase 7 decision focused on UI scope while pointing HTTP serving and
  evidence-first ask to their separate implemented contracts.

**Verification:**

- `git diff --check`
- `rg -n 'future happy path|CLI TODO|Future vg setup|Future MCP registration|available product features|reserved unsupported|ask_vault still needs' docs/DECISIONS.md`

## 2026-06-26 - Release Readiness Corrections

**Trigger:** Release-readiness review found stale Ask/MCP status wording,
incomplete package long-description metadata, generic HTTP explain-result error
mapping, and noisy FastEmbed pooling warnings during first-run CLI indexing.

**Scope:** Product contract docs, package metadata, HTTP error mapping,
FastEmbed backend creation, and focused regression tests.

**Core Values Protected:** Kept user-facing docs aligned with implemented
evidence-first Ask/MCP behavior, preserved stable explainable HTTP error
contracts, improved local-first CLI ergonomics without hiding domain warnings,
and avoided inventing unresolved release metadata such as license policy.

**Changes Applied:**

- Updated `SPEC.md`, `FEATURES.md`, `DESIGN.md`, and README wording so
  `vg ask`, `ask_vault`, result explanation, and memory MCP tools are described
  as service-backed implemented capabilities rather than future targets.
- Added README package metadata to `pyproject.toml` for PyPI long-description
  checks.
- Mapped HTTP `explain-result` misses to stable
  `result_explanation_not_found`/404 and blank IDs to `invalid_result_id`/400.
- Suppressed only FastEmbed's known default-model mean-pooling `UserWarning`
  during backend creation.

**Verification:**

- `uv run --python 3.12 pytest tests/test_http_server.py::test_http_explain_result_returns_error_for_missing_record tests/test_http_server.py::test_http_explain_result_rejects_blank_result_id -q`
- `uv run --python 3.12 pytest tests/test_fastembed_text_embeddings.py::test_default_backend_factory_suppresses_known_fastembed_pooling_warning -q`
- `uv run --python 3.12 ruff check src tests`
- `uv run --python 3.12 mypy src tests`
- `uv run --python 3.12 pytest -q`
- `VG_RUN_MCP_STDIO_SMOKE=1 uv run --python 3.12 pytest tests/test_mcp_stdio_smoke.py -q`
- `rg -n 'next implementation target|next service target|next core product capability|ask_vault is the next|vg ask.*next|should call the same AnswerService|Phase 5 registers only the subset|tools that require answer synthesis|Status: Draft|Future 7A|ask_vault remains|Ask Project is moved|future phase' docs/FEATURES.md docs/SPEC.md docs/DESIGN.md README.md`
- `uv build`
- `uv run --python 3.12 --with twine python -m twine check dist/*`
- fresh wheel install smoke with `vg --help`, `vg ask --help`, and `pip check`
- tiny Vault smoke with `vg init`, `vg index`, `vg search`, and `vg ask`; stderr
  checked for known FastEmbed pooling warning text

## 2026-06-26 - HTTP Explain Result Completion

**Trigger:** Final implementation audit found that the CLI TODO plan required
HTTP `POST /explain-result` to use the explanation service, but the HTTP
adapter still returned a reserved placeholder response.

**Scope:** HTTP adapter explanation cache wiring, HTTP explanation record
serialization, MCP cache compatibility wrapper, and HTTP/CLI regression tests.

**Core Values Protected:** Preserved evidence-first explainability across
adapters, kept HTTP independent from MCP internals, and kept result explanation
state bounded to rebuildable in-process adapter cache rather than Vault writes.

**Changes Applied:**

- Added an app-level `ResultExplanationCache` under `vault_graph.memory`.
- Kept the existing MCP cache import path as a compatibility wrapper.
- Added HTTP explanation record serializers for search, context, graph, and
  ask responses without importing `vault_graph.mcp`.
- Changed HTTP `POST /explain-result` to call `ExplainResultService`.
- Added CLI setup/watch smoke tests and HTTP explanation route tests.

**Verification:**

- `uv run --python 3.12 ruff check src tests`
- `uv run --python 3.12 mypy src tests`
- `uv run --python 3.12 pytest -q`
- `uv run --python 3.12 vg --help`
- `uv run --python 3.12 vg ask --help`
- `uv run --python 3.12 vg setup --help`
- `uv run --python 3.12 vg watch --help`
- `uv run --python 3.12 vg serve --help`
- `uv run --python 3.12 vg setup --vault "$tmpdir/vault" --state "$tmpdir/state" --dry-run --print-mcp-config`
- `uv run --python 3.12 vg serve --http --host 0.0.0.0`
- `rg -n "CLI TODO|not current commands|not part of the current CLI|http_transport_not_supported_in_phase_5a|ask is not present|HTTP Adapter TODO|reserved transport|result_explanation_not_available" README.md docs/SPEC.md docs/FEATURES.md tests src`

## 2026-06-25 - Ask Design Reference Alignment

**Trigger:** While writing the implementation-ready Ask SPEC, self-review found
that the previous CLI TODO design still contained a preliminary answer DTO and
`DESIGN.md` still had historical Phase 3 wording that could be read as
excluding the now-approved `vg ask` target.

**Scope:** `docs/SPEC.md`, `docs/DESIGN.md`,
`docs/superpowers/specs/2026-06-24-cli-todo-command-implementation-design.md`,
and the new Ask design SPEC.

**Core Values Protected:** Kept one canonical answer contract, preserved
service-backed CLI/MCP parity, and avoided shallow duplicated DTOs that could
drift from evidence-first citation rules.

**Changes Applied:**

- Added the canonical Ask design reference to `SPEC.md`.
- Reworded the historical CLI note in `DESIGN.md` so it no longer conflicts
  with the accepted Ask implementation target.
- Replaced the preliminary CLI TODO answer DTO with a reference to the new
  answer-layer SPEC and `AnswerService.ask(...)` flow.

**Verification:**

- `git diff --check`
- `uv run --python 3.12 vg --help`
- `rg -n 'support_level|AnswerService\.answer|Phase 3 must not implement|ask_vault remains out of scope|Ask Project is moved|Future 7A|Status: Draft' docs/SPEC.md docs/DESIGN.md docs/FEATURES.md docs/superpowers/specs/2026-06-24-cli-todo-command-implementation-design.md docs/superpowers/specs/2026-06-25-evidence-first-ask-and-reasoning-design.md docs/DECISIONS.md README.md`
- `rg -n '2026-06-25-evidence-first-ask-and-reasoning-design|AnswerDraft|PlannedEvidence|AnswerService\.ask|answer_status|CitationGuard|EvidencePlanner' docs/SPEC.md docs/DESIGN.md docs/FEATURES.md docs/superpowers/specs/2026-06-24-cli-todo-command-implementation-design.md docs/superpowers/specs/2026-06-25-evidence-first-ask-and-reasoning-design.md`

## 2026-06-25 - Ask Vision Documentation Alignment

**Trigger:** Self-review after approving the evidence-first ask direction found
stale documentation terms that still described implemented surfaces as draft or
treated `ask_vault` only as unscheduled future work.

**Scope:** `SPEC.md`, `FEATURES.md`, `DESIGN.md`, README status wording, CLI
command target SPEC, and `DECISIONS.md` notes.

**Core Values Protected:**

- Vault remains the durable source of truth
- `ask_vault` is evidence-first reasoning, not a writable memory system
- product documentation distinguishes implemented commands from next
  implementation targets
- external memory systems remain adapters or export targets, not core
  authorities

**Changes Applied:**

- Changed top-level status wording from draft to active product, feature,
  design, or local-development contracts.
- Reframed `SPEC.md` roadmap language as product layers and added the
  `Ask And Reasoning Layer` as the next implementation target.
- Expanded `FEATURES.md` with the `Evidence-First Ask And Reasoning` feature
  summary and answer response expectations.
- Recorded the accepted `ask_vault` direction in `DECISIONS.md`.
- Updated the CLI command implementation SPEC so `vg ask` is implemented before
  setup/watch/HTTP adapter work.

**Verification:**

- `git diff --check`
- `uv run --python 3.12 vg --help`
- `rg -n "Status: Draft|ask_vault remains|Future 7A|Phase 1:|full roadmap|future MCP binding|future phase" README.md docs/SPEC.md docs/FEATURES.md docs/DESIGN.md docs/DECISIONS.md docs/superpowers/specs/2026-06-24-cli-todo-command-implementation-design.md`
- `rg -n "Next Implementation Target: Evidence-First Ask And Reasoning|Ask And Reasoning Layer|Make Evidence-First Ask The Next Core Implementation|Active product contract|Active feature contract|Active design contract|vg ask is the next" README.md docs/SPEC.md docs/FEATURES.md docs/DESIGN.md docs/DECISIONS.md docs/superpowers/specs/2026-06-24-cli-todo-command-implementation-design.md`

## 2026-06-24 - CLI TODO Registration Safety Alignment

**Trigger:** Self-review of the CLI TODO command SPEC found that README and
`SPEC.md` examples could imply implicit user-level MCP config writes, while the
new detailed SPEC requires explicit config paths for external writes.

**Scope:** CLI TODO command design, README CLI TODO examples, and `SPEC.md`
section 17.

**Core Values Protected:**

- Vault Graph does not perform hidden writes outside explicit user-selected
  targets
- MCP registration stays separate from installation
- future CLI documentation does not imply unimplemented commands are available

**Changes Applied:**

- Added the CLI TODO command implementation SPEC.
- Linked README and `SPEC.md` TODO sections to the new SPEC.
- Changed `vg mcp register` examples to require `--config-path`.
- Clarified that `vg setup --agent` prepares MCP registration and writes agent
  config only through an explicit safe target.

**Verification:**

- `git diff --check`
- `uv run --python 3.12 vg --help`
- `rg -n "2026-06-24-cli-todo-command-implementation-design|--config-path|vg setup|vg mcp register|vg mcp config|vg watch|vg ask|vg serve --http" README.md docs/SPEC.md docs/superpowers/specs/2026-06-24-cli-todo-command-implementation-design.md`

## 2026-06-24 - Acceptance Review Release-Readiness Corrections

**Trigger:** Implementation success criteria acceptance review found three
remaining acceptance gaps and one Chroma read-only/rebuild stability issue.

**Scope:** Success-criteria acceptance tests, Chroma vector read-only search,
index-service cleanup, `SPEC.md` CLI documentation, review docs, and decision
log.

**Core Values Protected:**

- Vault remains read-only and cannot be mutated by indexing, search, or MCP
  resources
- Vault Graph internal index state remains rebuildable from Vault
- multi-Vault identity stays explicit across MCP resource URIs
- local-first search degrades visibly without network or model downloads

**Changes Applied:**

- Added acceptance tests for MCP same-relative-path resource isolation,
  delete→rebuild from Vault Graph internal index state, and deterministic
  offline keyword-only degradation.
- Added explicit Chroma client cleanup after indexing/status operations so
  same-process delete→rebuild does not reuse stale Chroma handles.
- Made Chroma read-only search use SQLite read-only access instead of opening a
  mutating Chroma client.
- Recorded accepted reset, offline, and CLI-documentation decisions.
- Split `SPEC.md` §17 into implemented CLI commands and CLI TODO
  commands.
- Updated the acceptance review documents from `PARTIAL` gaps to verified
  `PASS` evidence.

**Verification:**

- `uv run --python 3.12 pytest tests/test_acceptance_success_criteria.py -q`
- `uv run --python 3.12 pytest tests/test_chroma_vector_store.py tests/test_search_read_only_boundary.py tests/test_acceptance_success_criteria.py -q`
- `uv run --python 3.12 ruff check src tests`
- `uv run --python 3.12 mypy src tests`
- `uv run --python 3.12 pytest`
- `VG_RUN_MCP_STDIO_SMOKE=1 uv run --python 3.12 pytest tests/test_mcp_stdio_smoke.py -q`

## 2026-06-22 - Phase 6C Implementation Review Corrections

**Trigger:** Final implementation review found Phase 6C could under-report
vector-not-configured timeline warnings and could let multi-Vault scale-up
readiness depend on the last backend record inspected.

**Scope:** Phase 6C timeline memory, health explorer, and focused regression
tests.

**Core Values Protected:**

- timeline trust signals stay visible when vector state is missing or
  unavailable
- multi-Vault health output remains namespace-safe and does not hide a degraded
  Vault behind a healthy one
- Phase 6C stays read-only and does not add durable memory state

**Changes Applied:**

- Emitted vector status timeline warning items for not-configured or unavailable
  vector state instead of suppressing them.
- Aggregated scale-up adapter readiness across all actual Vault backend records
  instead of using only one record per backend kind.
- Added focused regression tests for vector-unavailable timeline warnings and
  multi-Vault scale-up readiness degradation.

**Verification:**

- `uv run --python 3.12 ruff check src tests`
- `uv run --python 3.12 mypy src tests`
- `uv run --python 3.12 pytest -q`
- `VG_RUN_MCP_STDIO_SMOKE=1 uv run --python 3.12 pytest tests/test_mcp_stdio_smoke.py -q`

## 2026-06-22 - Phase 6C Bounded Timeline Plan Corrections

**Trigger:** Goal completion audit and subagent review found remaining Phase 6C
SPEC references to `MetadataStore.list_documents(...)`, a wildcard-prone
content-scope SQL sketch, a timeline-specific status protocol, underspecified
status/projection timeline items, and missing strict-typing/full-regression
plan gates.

**Scope:** Phase 6C detailed SPEC documents, Phase 6C implementation plan, and
PATCH_LOG.

**Core Values Protected:**

- timeline reads stay bounded for large Vaults
- source SPEC and implementation plan use one consistent metadata contract
- Phase 6C remains scalable without adding durable timeline storage
- strict typing, multi-Vault health, and timeline trust signals are explicit

**Changes Applied:**

- Replaced completion, origin-rule, dependency, and implementation-order wording
  with `MetadataStore.list_recent_documents(scope, since, limit)`.
- Kept `list_documents(scope)` only as the Phase 6B baseline that Phase 6C
  extends.
- Reused the existing `MemoryStatusService` protocol instead of adding a
  timeline-specific status protocol.
- Required `list_recent_documents(...)` to receive exactly one actual Vault scope
  and avoid unescaped SQL wildcard matching.
- Aligned health explorer SPEC flow with per-actual-Vault status reads when no
  aggregate `check_index_status(...)` report is supplied.
- Removed fake metadata revision construction from status/projection timeline
  item mapping.
- Added exact status/projection timeline item mapping, strict runtime-cache
  snapshot typing, stronger multi-Vault health/timeline tests, and full
  regression verification.
- Tightened strict typing details for `StatusReport` type-only imports and
  `MemoryWarningSeverity` helper signatures, runtime-cache capacity protocols,
  and made one-Vault metadata scope validation run before missing-database
  fallback.

**Verification:**

- Re-ran targeted scans for stale `list_documents(...)`, requested-scope status
  reads, placeholders, and strict-typing serialization hazards.

## 2026-06-22 - Phase 6C SPEC Review Corrections

**Trigger:** Phase 6C SPEC subagent reviews found timeline origin wording could
make index-observation timestamps look like durable Vault business events,
public MCP tool signatures diverged from top-level docs, recovery hints used an
unsupported CLI flag, and health/readiness boundaries were too broad or
ambiguous.

**Scope:** Phase 6C detailed SPEC documents, Phase 6 overview documents,
top-level SPEC/FEATURES/DESIGN/README MCP signatures, external-memory decision
guardrails, and related terminology.

**Core Values Protected:**

- timeline output stays evidence-first and does not claim durable events that
  Vault Graph only observed through indexing
- MCP contracts remain consistent across detailed and top-level docs
- recovery guidance stays executable against the current CLI
- Phase 6 remains read-only, rebuildable, and free of writable memory drift

**Changes Applied:**

- Replaced the old Vault-change-style origin label with
  `document_snapshot_change` and clarified that timeline timestamps are index
  observation timestamps.
- Added `limit=20` to `get_recent_changes(...)` and `scope=None` to
  `check_index_status(...)` across public docs.
- Replaced unsupported graph recovery guidance with `vg index` plus
  `vg status`.
- Clarified that timeline output is regenerated from metadata snapshots and
  status reports, while runtime-cache visibility belongs to health explorer.
- Narrowed scale-up readiness to status/schema-derived contract checks, not
  record-level migration audits.
- Extended memory-boundary guardrails to preference and procedural memory.

**Verification:**

- Rechecked Phase 6C detailed SPECs against Phase 6 overview, top-level MCP
  signatures, current CLI flags, and subagent findings.
- Searched for stale timeline origin labels, unsupported Phase 6C recovery
  hints, and mismatched `get_recent_changes` / `check_index_status`
  signatures.

## 2026-06-22 - Phase 6B Implementation Review Corrections

**Trigger:** Phase 6B implementation review found issue-memory candidate caps
could be consumed by resolved items, project-memory group scans needed tighter
bounded chunk reads, ambiguous project classifications were not surfaced, DTO
validation was too permissive, and memory service imports crossed the
`IndexService` boundary too eagerly.

**Scope:** Phase 6B memory projection services, MCP memory import boundaries,
memory DTO validation, and regression tests.

**Core Values Protected:**

- memory projections stay evidence-first, bounded, and explicit about
  heuristic ambiguity
- open-question recall does not hide active work behind resolved documents
- MCP memory modules remain lightweight and free of local backend side effects
- DTOs reject invalid memory shapes before serialization

**Changes Applied:**

- Excluded resolved issue statuses before applying candidate caps.
- Added project-memory ambiguous-classification warnings and bounded chunk-read
  behavior for large candidate sets.
- Tightened `MemoryItem` validation for signals, resource kinds, evidence, and
  warnings.
- Replaced direct memory-service `IndexService` imports with a minimal
  status-service protocol.
- Added focused regression coverage for the corrected behavior.

**Verification:**

- `uv run --python 3.12 pytest tests/test_project_memory_service.py tests/test_memory_models.py tests/test_mcp_import_boundaries.py -q`
- `uv run --python 3.12 pytest tests/test_decision_memory_service.py tests/test_issue_memory_service.py tests/test_project_memory_service.py tests/test_memory_models.py tests/test_memory_request_context.py tests/test_memory_source_reader.py tests/test_mcp_memory_tools.py tests/test_mcp_current_context_resource.py tests/test_mcp_service_factory.py tests/test_mcp_tools.py tests/test_mcp_resources.py tests/test_mcp_server.py tests/test_mcp_prompts.py tests/test_mcp_errors.py tests/test_mcp_tool_read_only_boundary.py tests/test_mcp_resource_read_only_boundary.py tests/test_mcp_import_boundaries.py tests/test_metadata_resource_reader.py tests/test_sqlite_metadata_store.py -q`

## 2026-06-19 - Phase 6B Implementation Plan Review Corrections

**Trigger:** Phase 6B implementation-plan subagent reviews found public MCP
tool signatures lagged behind the detailed SPEC, `recent` wording implied
unsupported recency evidence, memory resource-link rules lacked enough DTO data,
and `context/current` error handling could lose Vault-specific recovery hints.

**Scope:** Phase 6B implementation plan, Phase 6 overview/SPEC documents,
top-level SPEC/FEATURES/DESIGN MCP memory signatures, Phase 4 context-pack
selection wording, and current-context wording.

**Core Values Protected:**

- memory projections remain evidence-first and avoid unsupported recency claims
- MCP contracts stay bounded, canonical, and implementation-ready
- resource links remain valid existing Vault Graph resources instead of broken
  memory-specific URIs
- metadata failures stay explicit with safe recovery guidance

**Changes Applied:**

- Added bounded `limit` arguments for Phase 6B memory tools in top-level docs.
- Changed project memory wording from recent decisions to decision highlights
  and kept recent-change claims in the Phase 6C timeline boundary.
- Clarified Phase 4 context-pack selection wording so durable change evidence
  does not imply Phase 6B provides timeline-backed recency.
- Added `document_resource_kinds` to memory items so serializers can build valid
  decision/issue/source/page links.
- Added direct `MemoryProjectionError` handling guidance for `context/current`.
- Added `MemoryRequestContext` to the Phase 6B SPEC/plan so project memory can
  reuse one metadata status and document listing pass.
- Added import-cycle, lazy-export, and `invalid_memory_limit` checks to the
  Phase 6B implementation plan.

**Verification:**

- Rechecked Phase 6B SPEC/plan terminology, top-level MCP signatures, resource
  link rules, and Markdown formatting against review findings.

## 2026-06-19 - Phase 6B Memory SPEC Review Corrections

**Trigger:** Phase 6B subagent review found that heuristic memory items could
look like stated Vault facts, open-question rules could include resolved issues,
memory item IDs could collide within one document, graph enrichment was not
fully lazy, and large-scope document reads needed a clearer bounded policy.

**Scope:** Phase 6B project, decision, and issue memory SPEC documents.

**Core Values Protected:**

- memory projections remain evidence-first and distinguish stated facts from
  inferred or heuristic candidates
- Phase 6B stays read-only, rebuildable, multi-vault-safe, and bounded for
  large Vaults
- graph behavior remains explicit and lazy instead of opening graph projection
  paths during ordinary project-memory reads

**Changes Applied:**

- Added `claim_status` and `matched_signals` to memory items.
- Kept graph enrichment in `matched_signals` instead of a separate claim status.
- Tightened open-question status rules and excluded resolved/closed items.
- Included primary evidence chunk and claim status in stable item IDs.
- Added metadata-first candidate narrowing, chunk-read caps, and truncation
  warnings.
- Limited heading-only matches to metadata-selected documents so Phase 6B does
  not drift into unbounded chunk mining.
- Removed scope-level bulk document reads from the source-reader contract so
  services own candidate narrowing before evidence loading.
- Replaced eager graph-service injection with a lazy decision-trace provider
  factory and moved backend stale state to freshness/warnings.
- Aligned the decision-trace provider protocol with the current
  `GraphRetrievalService.decision_trace(...)` signature.

**Verification:**

- Rechecked English/Korean Phase 6B SPEC parity, Markdown formatting, and review
  findings against the current Phase 6 docs and MCP/code boundaries.

## 2026-06-19 - Phase 6A Result Explanation Review Corrections

**Trigger:** Phase 6A code-quality review found result explanation records could
be cached before a tool response was successfully returned, graph result IDs
were raw delimiter-based strings, and context-pack warnings could be dropped for
later evidence from another Vault.

**Scope:** Phase 6A result explanation implementation, detailed SPEC, and
implementation plan.

**Core Values Protected:**

- explainability reflects only results actually returned to the caller
- runtime handles stay bounded and current-session scoped
- evidence warnings remain visible across multi-vault context-pack items

**Changes Applied:**

- Moved result explanation cache writes after payload, resource link, warning,
  and text mirror assembly succeeds.
- Replaced raw related/decision-trace result IDs with fixed-length canonical
  hash runtime handles.
- Matched context-pack warnings against all record evidence Vault IDs, not just
  the first evidence item.
- Added regression tests for failed tool serialization, unbounded graph inputs,
  and multi-vault context-pack warnings.

**Verification:**

- Added failing regression tests first, implemented fixes, and reran the focused
  Phase 6A/MCP suites before final full verification.

## 2026-06-19 - Phase 6 External Memory Boundary Clarification

**Trigger:** External memory-layer review found Phase 6 used memory terminology
without explicitly separating Vault Graph projections from writable systems such
as Mem0, MemMachine, or MCP memory servers.

**Scope:** Phase 6 top-level SPEC, Phase 6 README/overview, Phase 6A/6B/6C
detailed SPEC documents, Phase 6A implementation plan, and decision log.

**Core Values Protected:**

- Vault remains the durable source of truth
- memory output stays read-only, evidence-linked, disposable, and rebuildable
- Phase 6 implementation remains simple and production-ready without hidden
  writable memory stores

**Changes Applied:**

- Added Phase 6 memory taxonomy for working, semantic/project, episodic/timeline,
  profile/preference, and procedural memory.
- Explicitly prohibited generic writable `MemoryStore` APIs, hidden episode
  logs, profile memory databases, and direct external memory-server dependencies
  in Phase 6 core.
- Added a SPEC TODO for future Mem0, MemMachine, or MCP memory-server adapters as
  export targets over evidence-linked projections.
- Updated the Phase 6A plan with tests and risk mitigations that prevent the new
  `vault_graph.memory` package from drifting into a writable memory layer.

**Verification:**

- Rechecked Phase 6 SPEC, detailed SPECs, and the Phase 6A plan for matching
  external-memory boundaries, read-only projection language, and future-adapter
  scope.

## 2026-06-18 - Phase 6 SPEC Self-Grill Corrections

**Trigger:** Phase 6 SPEC self-grill found the Phase 6B source-reader contract
said unresolved evidence should return warnings, but the planned
`evidence_for_document(...)` signature returned only evidence records.

**Scope:** Phase 6B project, decision, and issue memory SPEC documents.

**Core Values Protected:**

- memory projections keep evidence gaps visible
- implementation handoff stays unambiguous
- source-reader boundary remains a deep module instead of leaking warning policy

**Changes Applied:**

- Replaced the evidence-only source-reader method with `MemoryDocumentRead`.
- Added `read_document(...)` and `read_documents(...)` contracts that return
  evidence plus warnings together.
- Updated the Korean Phase 6B copy with the same contract.

**Verification:**

- Rechecked Phase 6 docs for references to Phase 6 MCP tools, read-only
  boundaries, and source-reader warning behavior.

## 2026-06-18 - Phase 5C Implementation Verification Corrections

**Trigger:** Phase 5C implementation verification found MCP factory laziness
tests depended on shared pytest import state, and self-review found the MCP
status payload shortened the accepted `embedding_batch_size` terminology.

**Scope:** Phase 5C MCP status serialization and factory laziness tests.

**Core Values Protected:**

- implementation tests remain reliable and order-independent
- MCP payload terminology stays aligned with accepted project language
- graph dependencies remain explicit and lazy

**Changes Applied:**

- Moved factory laziness checks into subprocesses with fresh interpreters.
- Preserved `embedding_batch_size`, `embedding_parallelism`, and
  `embedding_lazy_load` keys in the MCP status payload.
- Added a focused assertion for the status payload embedding key.

**Verification:**

- Reran focused MCP tool/serialization tests after the correction.

## 2026-06-18 - Phase 5C Stenc SPEC Refresh

**Trigger:** Review compared the current Phase 5C Markdown SPEC against the
Stenc Phase 5C spec JSON and found the Stenc document still reflected older
draft-level content.

**Scope:** Phase 5C Stenc SPEC source and generated Stenc page.

**Core Values Protected:**

- Stenc JSON remains aligned with the current Markdown source of truth
- MCP contracts stay retrievable for future implementation and RAG context
- generated docs preserve read-only, service-backed, evidence-first Phase 5C
  boundaries

**Changes Applied:**

- Refreshed the Phase 5C Stenc SPEC JSON from the current Phase 5C Markdown
  SPEC.
- Added current Phase 5C requirements for exact tool and prompt lists, lazy
  graph factory methods, tool serialization, prompt registry, context-pack cache
  handoff, read-only boundaries, and verification gates.
- Fixed Stenc `codeBlocks` serialization so the updated JSON validates against
  the canonical Stenc schema.

**Verification:**

- Validated the updated Stenc JSON source.
- Regenerated Stenc static pages and ran rendered-page checks.

## 2026-06-18 - Phase 5C Implementation Plan Review Corrections

**Trigger:** Phase 5C implementation-plan review found sequencing and boundary
risks around MCP tool DTO ownership, serialization imports, graph factory
construction, cross-Vault argument authority, server protocol typing, and tool
error mapping.

**Scope:** Phase 5C MCP tools/prompts implementation plan.

**Core Values Protected:**

- MCP remains a thin adapter over application services
- tool serialization avoids circular imports and CLI coupling
- graph behavior stays explicit, lazy, and validation-first
- cross-Vault output remains unambiguous and Vault-scoped

**Changes Applied:**

- Moved shared tool DTO creation before tool serialization so
  `mcp_tool_serialization.py` has a stable `McpResourceLink` owner.
- Replaced duplicate/private-field factory guidance with shared helper
  construction for retrieval services and context-pack builders.
- Made top-level `include_cross_vault` authoritative and added mismatch
  validation for `scope.include_cross_vault`.
- Added `list_tools` and `list_prompts` to the planned MCP server protocol and
  required service exception mapping through `mcp_errors.py`.

**Verification:**

- Rechecked the plan against the Phase 5C SPEC success criteria, current
  `vault_graph.mcp` code, and the existing Phase 5A/5B plan style.

## 2026-06-18 - Phase 5C MCP Tool SPEC Alignment

**Trigger:** Phase 5C SPEC recheck against the completed Phase 5A/5B MCP
runtime and resource work found that the draft did not define the graph-enabled
retrieval handoff, shared context-pack cache reuse, tool serialization boundary,
or prompt registration contract in implementation-ready detail.

**Scope:** Phase 5C MCP tools, prompts, service factory handoff, resource-link
serialization, smoke-test expectations, and read-only boundary tests.

**Core Values Protected:**

- MCP remains a thin adapter over application services
- graph behavior stays explicit and lazy
- context-pack resources reuse generated in-process cache state
- tool and prompt output preserves evidence, warnings, and Vault IDs

**Changes Applied:**

- Rewrote the Phase 5C design as an implementation-ready SPEC.
- Added lazy `McpServiceFactory` handoff requirements for graph-enabled search
  and context-pack building.
- Added MCP-owned tool serialization, resource-link, tool registry, and prompt
  registry boundaries.
- Updated test requirements so Phase 5C changes the stdio smoke expectations
  from empty tools/prompts to exact service-backed lists.

**Verification:**

- Compared the updated SPEC against `docs/SPEC.md`, `docs/DESIGN.md`,
  `docs/FEATURES.md`, Phase 5A/5B design docs, and current `vault_graph.mcp`
  code.
- Verified the installed MCP SDK exposes public `FastMCP.tool(...)` and
  `FastMCP.prompt(...)` registration APIs.

## 2026-06-17 - Phase 5B Implementation Plan Chunk Order Correction

**Trigger:** Phase 5B implementation-plan review found that ordering document
resource chunks by `chunk_id` would sort stable hashes, not preserve
`heading-section-v1` document order.

**Scope:** Phase 5B MCP resource implementation plan for
`MetadataStore.list_document_chunks(...)` and SQLite metadata-store tests.

**Core Values Protected:**

- evidence resources preserve indexed document structure
- no metadata schema migration is introduced just for MCP serving
- resource rendering remains simple and rebuildable from existing indexed state

**Changes Applied:**

- Changed the planned SQLite document-chunk query from `ORDER BY c.path,
  c.chunk_id` to `ORDER BY c.rowid`.
- Added a test requirement that chunk order remains document insertion order
  even when lexical `chunk_id` order differs.

**Verification:**

- Inspected the current `metadata-v1` SQLite schema and
  `apply_metadata_revision(...)` chunk insertion flow.
- Rechecked the Phase 5B plan against the SPEC requirement that resources
  preserve `heading-section-v1` chunk order.

## 2026-06-17 - Phase 5B MCP Resource SPEC Corrections

**Trigger:** Phase 5B SPEC self-grill against the completed Phase 5A FastMCP
implementation found that raw slash path examples and dynamic per-resource
metadata would not map cleanly onto the public FastMCP resource-template API.

**Scope:** Phase 5B MCP resource URI contract, resource body contract, context
pack cache boundary, and resource implementation handoff.

**Core Values Protected:**

- MCP remains a thin adapter over the completed Phase 5A server foundation
- URI parsing fails closed for path traversal and multi-Vault collisions
- evidence metadata and warnings stay first-class in resource output
- context-pack resources remain generated working context, not durable state

**Changes Applied:**

- Replaced raw slash document URI examples with FastMCP-compatible
  percent-encoded single-segment path rules.
- Changed Phase 5B resource output to a canonical JSON envelope so dynamic
  evidence metadata and warnings do not depend on SDK-private attributes.
- Made `list_document_chunks(vault_id, document_id)` a required
  `MetadataStore` extension for scalable document resource rendering.
- Added explicit graph resource service, current-context availability, timeline
  unavailable, and context-pack cache handoff contracts.

**Verification:**

- Compared Phase 5B design with current Phase 5A `vault_graph.mcp`
  implementation.
- Inspected the installed MCP SDK FastMCP resource-template behavior.
- Checked consistency against `docs/SPEC.md`, `docs/DESIGN.md`,
  `docs/FEATURES.md`, and `docs/CONVENTIONS.md`.

## 2026-06-15 - Phase 5A Implementation Plan Review Corrections

**Trigger:** Security, performance, testability, and maintainability subagent
reviews found Phase 5A plan gaps around path redaction, runtime dependency
scope, startup import laziness, service handoff ownership, and smoke-test
coverage.

**Scope:** Phase 5A MCP stdio implementation plan for dependency selection,
`vault_graph.mcp` package boundaries, error mapping, service factory
construction, CLI serve tests, and verification gates.

**Core Values Protected:**

- MCP remains a thin adapter over read-only application services
- stdio startup avoids hidden indexing, model loading, graph projection, and
  stdout contamination
- local path details are not leaked through MCP error payloads
- Phase 5B/5C can reuse owned service boundaries without SDK-private coupling

**Changes Applied:**

- Changed the planned runtime dependency from `mcp[cli]` to `mcp`.
- Replaced private FastMCP attribute handoff with an owned
  `RegisteredMcpServer` wrapper.
- Changed `McpServices` to expose interface-typed services and renamed
  `config` to `catalog_service`.
- Moved status, graph, vector, FastEmbed, Chroma, and rustworkx imports behind
  method boundaries.
- Added explicit absolute-path redaction rules and tests for domain/internal
  MCP errors.
- Strengthened service-factory read-only constructor tests and startup import
  laziness tests.
- Made the official MCP stdio smoke test timeout-bounded and required in final
  verification.

**Verification:**

- Security, performance, testability, and maintainability subagent reviews.
- Plan red-flag and stale-reference scans.
- `git diff --no-index --check /dev/null docs/superpowers/plans/2026-06-15-phase-5a-mcp-server-foundation-stdio.md`

## 2026-06-15 - Phase 5 MCP SPEC Alignment Corrections

**Trigger:** Phase 5 SPEC self-grill found that roadmap bullets were too thin
for implementation planning and older docs could imply MCP should register
answer or memory tools before those services exist.

**Scope:** `docs/SPEC.md`, `docs/DESIGN.md`, `docs/FEATURES.md`, and new Phase
5 detailed design documents under `docs/superpowers/specs/phase-5/`.

**Core Values Protected:**

- MCP remains an adapter over application services, not a second reasoning layer
- Vault Graph stays read-only, rebuildable, and evidence-first through MCP
- Phase 5 exposes only service-backed tools instead of unavailable tool entries
- context-pack resources remain generated working context, not durable knowledge

**Changes Applied:**

- Split Phase 5 into overview, 5A stdio foundation, 5B resources, and 5C
  tools/prompts design documents.
- Expanded `docs/SPEC.md` Phase 5 summary with slice contracts and invariants.
- Aligned `docs/FEATURES.md` and `docs/DESIGN.md` with the service-backed MCP
  tool policy.
- Replaced the old `app/mcp_server.py` adapter wording with a dedicated
  `vault_graph.mcp` adapter boundary.

**Verification:**

- Self-grill against `docs/SPEC.md`, `docs/DESIGN.md`, `docs/FEATURES.md`, and
  Phase 4 context-pack handoff docs.
- Placeholder/stale-reference scans over Phase 5 docs and core docs.
- Phase 5 file/link existence checks.

## 2026-06-15 - Phase 4B Implementation Review Corrections

**Trigger:** Final subagent review found Phase 4B implementation gaps around
single-Vault cross-Vault validation order, builder actual-scope validation, and
test coverage masking.

**Scope:** `vg context` CLI wiring, `SearchContextPackBuilder` response
validation, and Phase 4B CLI/builder tests.

**Core Values Protected:**

- invalid context requests fail before opening search, graph, or builder
  dependencies
- context packs cannot accept retrieval responses that widen Vault, content, or
  cross-Vault scope
- multi-Vault context assembly preserves evidence Vault identity through the
  real local retrieval path
- degraded vector search remains visible as first-class context warnings

**Changes Applied:**

- Moved `ContextPackRequest` validation before context builder creation.
- Rejected actual scopes that exceed requested Vault IDs, content scopes, or
  cross-Vault mode.
- Added real all-Vault CLI context coverage and degraded vector fallback
  coverage.
- Strengthened builder tests so signal-count ordering and current-state suffix
  classification are independently proven.
- Added explicit exit-code assertions for CLI validation failures.

**Verification:**

- Security, performance, testability, and maintainability subagent reviews.
- `uv run --python 3.12 pytest tests/test_cli_context.py tests/test_context_pack_builder.py -q`
- `uv run --python 3.12 pytest tests/test_cli_context.py tests/test_cli_search.py tests/test_cli_surface_boundary.py tests/test_context_pack_renderer.py tests/test_context_pack_builder.py tests/test_context_pack_serialization.py tests/test_context_pack_import_boundaries.py -q`
- `uv run --python 3.12 pytest -q`
- `uv run --python 3.12 ruff check src tests`
- `uv run --python 3.12 mypy src tests`
- `git diff --check`

## 2026-06-12 - Phase 4B Implementation Plan Review Hardening

**Trigger:** Security, performance, testability, and maintainability subagent
reviews found Phase 4B plan gaps around scope validation order, renderer safety,
multi-vault preservation, and read-only integration coverage.

**Scope:** Phase 4B implementation plan for local context pack assembly,
Markdown rendering, CLI wiring, and verification coverage.

**Core Values Protected:**

- invalid context requests fail before opening read-only stores or graph state
- context Markdown remains evidence-linked without unsafe Vault-derived text
  injection
- multi-vault evidence, warnings, and revisions preserve Vault identity
- context assembly stays bounded without overstating all-Vault retrieval limits
- CLI remains a thin adapter over the `vault_graph.context` deep module

**Changes Applied:**

- Reordered the planned `vg context` flow to load the catalog, resolve scope,
  then create read-only retrieval and builder dependencies.
- Removed the shallow context build helper and kept pack assembly behind
  `SearchContextPackBuilder`.
- Added a shared Markdown warning formatter, safe code-span helper, and renderer
  tests for escaped Vault-derived text.
- Replaced brittle CLI source-string boundary checks with fake-renderer
  delegation tests.
- Added tests for unknown Vault scope, graph read-only behavior, all-Vault
  read-only behavior, multi-vault evidence/warning/revision preservation, and
  builder retrieval-limit caps.
- Documented the existing per-scope all-Vault retrieval fanout and the
  evidence-excerpt meaning of `--max-tokens`.

**Verification:**

- Security, performance, testability, and maintainability subagent reviews.
- Placeholder and stale-reference scans over the implementation plan.
- Plan structure and current worktree checks.

## 2026-06-12 - Phase 4A Implementation Review Hardening

**Trigger:** Security, performance, testability, and maintainability subagent
reviews found Phase 4A implementation gaps after the first context-pack code
pass.

**Scope:** `vault_graph.context` implementation, Phase 4A context-pack tests,
and context package import-boundary checks.

**Core Values Protected:**

- context packs fail closed when retrieval widens scope unexpectedly
- evidence excerpts and JSON serialization remain safe and deterministic
- budget packing does not leave orphan evidence or hidden omissions
- graph metadata stays opt-in for default context packs
- context package imports stay lightweight and backend-agnostic

**Changes Applied:**

- Added response-scope and result-evidence validation before pack assembly.
- Staged evidence per item and committed it only after the full item fits the
  evidence and token budgets.
- Applied section priority during budget packing so decisions and constraints
  are not displaced by lower-value page hits.
- Validated resolved evidence paths against Vault-relative actual content
  scopes and rejected resolver chunk/evidence mismatches.
- Made Markdown excerpt fences collision-safe and JSON serialization reject
  non-finite float values.
- Added Markdown sections for budget, backend use, Vault revisions, and store
  revisions so the renderer does not hide JSON contract metadata.
- Normalized `stale_vector` to `stale_projection` while preserving
  `source_code`.
- Omitted graph and projection store revisions from non-graph context packs.
- Kept builder exports lazy while making them visible through `dir()` and
  import-boundary tests.

**Verification:**

- `uv run --python 3.12 pytest tests/test_context_pack_contract.py tests/test_context_pack_serialization.py tests/test_context_pack_docs_contract.py tests/test_context_pack_warnings.py tests/test_context_pack_evidence_budget.py tests/test_context_pack_builder.py tests/test_context_pack_import_boundaries.py tests/test_context_pack_read_only_boundary.py -q`
- `uv run --python 3.12 pytest tests/test_retrieval_service_search.py tests/test_search_response_contract.py tests/test_search_include_graph.py tests/test_graph_retrieval_service.py tests/test_multi_vault_graph_retrieval.py -q`
- `uv run --python 3.12 ruff check src tests`
- `uv run --python 3.12 mypy src tests`

## 2026-06-12 - Phase 4A Implementation Plan Review Hardening

**Trigger:** Multi-angle subagent review of the Phase 4A implementation plan
found warning attribution, budget, renderer, package-boundary, and schema-test
gaps that could weaken the context-pack contract before implementation.

**Scope:** Phase 4A implementation plan, Phase 4A design notes, top-level
package-boundary docs, and agent documentation rules.

**Core Values Protected:**

- context packs preserve Vault-scoped evidence identity
- warnings remain visible across JSON and Markdown rendering
- context assembly stays bounded and read-only
- `vault_graph.context` becomes an explicit deep module boundary
- docs and DTO schema drift is caught by tests before implementation

**Changes Applied:**

- Required single-Vault attribution before converting search warnings into
  evidence refs.
- Required result-level retrieval warnings to survive as item warnings.
- Added Vault-relative path validation, Markdown escaping, and fail-closed DTO
  serialization rules.
- Changed budget behavior to resolve deduped evidence only within budget and
  aggregate omission warnings.
- Added docs/DTO schema parity, nested JSON shape, warning mapping, resolver
  protocol, budget accounting, import-boundary, and read-only test requirements.
- Recorded `vault_graph.context` as the package boundary in `docs/SPEC.md` and
  `docs/DESIGN.md`.
- Tightened cross-Vault request validation in the Phase 4A design.

**Verification:**

- Security, performance, testability, and maintainability subagent reviews.
- Placeholder scan over the implementation plan.
- Markdown formatting and whitespace checks.

## 2026-06-12 - Phase 4 Context Pack SPEC Alignment

**Trigger:** Phase 4 context pack design needed to move from roadmap bullets to
a detailed, implementation-ready SPEC while staying aligned with Phase 1-3
retrieval and graph contracts.

**Scope:** `docs/SPEC.md`, `docs/DESIGN.md`, `docs/FEATURES.md`,
`docs/DECISIONS.md`, and new Phase 4 detailed design documents.

**Core Values Protected:**

- context packs remain derived working context, not durable Vault knowledge
- evidence chunks remain the context pack authority unit
- Markdown output cannot hide JSON warnings or invent facts
- graph expansion stays explicit instead of silently widening retrieval scope
- future MCP/HTTP serving can reuse one stable context pack contract

**Changes Applied:**

- Added Phase 4 slice documents under `docs/superpowers/specs/phase-4/`.
- Expanded the top-level Phase 4 `docs/SPEC.md` contract with JSON-canonical
  context packs, evidence authority, budget defaults, warning policy, and
  graph opt-in behavior.
- Aligned `docs/DESIGN.md` and `docs/FEATURES.md` with the Phase 4 context pack
  contract.
- Clarified that candidate merge may use `(vault_id, chunk_id)`, while resolved
  evidence identity is `(vault_id, document_id, chunk_id)`.
- Recorded the accepted Phase 4 context pack policy in `docs/DECISIONS.md`.

**Verification:**

- Phase 3 smoke verification using `init`, `index`, `status`, `related`,
  `decision-trace`, and `search --include-graph` on a temporary Vault.
- Self-grill corrections for multi-vault revision attribution and deterministic
  `pack_id` identity.
- Subagent review and re-review for product value alignment, implementation
  readiness, and multi-vault/evidence/warning consistency.
- JSON contract parse checks for `docs/SPEC.md` and `docs/FEATURES.md`.
- Full local test, lint, typing, and `git diff --check` verification.

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
