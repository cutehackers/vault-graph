# Vault Graph Implementation Success Criteria Acceptance Review

Status: Verified
Date: 2026-06-24
Reviewer: Codex
Branch: main
Commit: 58ca7bc + acceptance fixes in current worktree

## 1. Executive Summary

| Verdict | Count |
| --- | ---: |
| PASS | 8 |
| PARTIAL | 0 |
| GAP | 0 |
| NOT IN CURRENT SCOPE | 0 |
| UNKNOWN | 0 |

- The implemented surface now satisfies all eight `docs/SPEC.md` Success Criteria with current-checkout code, focused acceptance tests, and a green full gate (`ruff`, `mypy`, `pytest`: 778 passed, 1 skipped; the skip is the gated MCP stdio smoke, which passes when enabled).
- Read-only safety is strong and well proven: index, search, context-pack, graph-retrieval, and MCP tool/resource paths all carry before/after file-hash or tree-snapshot tests proving Vault bytes never change, and all seven MCP prompts instruct agents to route durable changes back through Vault's workflow.
- The prior `PARTIAL` items are closed by `tests/test_acceptance_success_criteria.py`: MCP same-relative-path resource isolation, delete→rebuild from Vault Graph index state, and deterministic offline keyword-only degradation.
- No user-facing `vg reset-index` command was added. The accepted reset UX is documented deletion of Vault Graph internal index state followed by `vg index` / `vg index --vault-id`; a future reset command remains optional if a real UX gap appears.
- No `GAP` (unsatisfied criterion) was found. Phase 6 memory/explorer projections remain read-only, evidence-linked working context and do not act as a durable memory database.

## 2. Review Scope

Included phases (current implemented product surface):

- Phase 1: Vault catalog, reader, metadata store
- Phase 2: local vector indexing and keyword/vector search
- Phase 3: entity/relationship graph, `vg related`, graph retrieval, decision trace
- Phase 4: context pack contract and CLI context pack assembly
- Phase 5: MCP server, resources, tools, and prompts
- Phase 6: result explanation, project/decision/issue memory, timeline/health explorer services

Explicitly excluded as future work (do not block current acceptance):

- Phase 7B/7C UI implementation (deferred by accepted decision).
- Phase 7A local HTTP serving (`vg serve --http`).
- `Ask Project`, `ask_vault`, answer synthesis, LLM adapter policy, citation guarantees.
- MacBook acceleration, non-Markdown readers, chunking migrations, external memory adapters (TODO guidance, not acceptance scope).

## 3. Verification Commands

All commands were run against the current checkout (`main` @ `58ca7bc`).

| Command | Result |
| --- | --- |
| `git status --short --branch` | `main...origin/main [ahead 1]`; acceptance fixes and review/plan docs present |
| `git rev-parse --short HEAD` | `58ca7bc` |
| `uv run --python 3.12 ruff check src tests` | `All checks passed!` |
| `uv run --python 3.12 mypy src tests` | `Success: no issues found in 204 source files` |
| `uv run --python 3.12 pytest` | `778 passed, 1 skipped in 6.22s` |
| `VG_RUN_MCP_STDIO_SMOKE=1 uv run --python 3.12 pytest tests/test_mcp_stdio_smoke.py -q` | `1 passed` (gated transport smoke; default-skipped without the env flag) |

Focused criterion command groups (all captured from the current checkout):

| Criterion | Command (abbreviated) | Result |
| ---: | --- | --- |
| 1 | `pytest test_cli_catalog_metadata test_metadata_indexer test_read_only_boundary test_vector_indexing_read_only_boundary test_graph_indexing_read_only_boundary` | 31 passed |
| 2 | `pytest test_vault_catalog test_cli_catalog_metadata test_query_scope_resolution test_multi_vault_search test_cli_context` | 44 passed |
| 3 | `pytest test_multi_vault_identity test_multi_vault_search test_multi_vault_graph_identity test_multi_vault_graph_indexing test_multi_vault_graph_retrieval test_cli_context::...preserves_evidence_vault_ids test_acceptance_success_criteria::...mcp_document_resources...` | Covered by full suite; acceptance file: 3 passed |
| 4 | `pytest test_context_pack_builder test_context_pack_evidence_budget test_context_pack_warnings test_cli_context test_mcp_tools::build_context_pack... test_context_pack_read_only_boundary` | 87 passed |
| 5 | `pytest test_graph_retrieval_service test_cli_decision_trace test_mcp_tools::decision_trace...` | 19 passed |
| 6 | `pytest test_cli_catalog_metadata::test_cli_index_accepts_full_option test_index_service_vector_reconcile test_index_service_graph_reconcile test_acceptance_success_criteria::...deleted_vault_graph_index_state...` | Covered by full suite; acceptance file: 3 passed |
| 7 | `pytest test_fastembed_text_embeddings test_app_search_readiness_service test_retrieval_service_search test_search_read_only_boundary test_acceptance_success_criteria::...offline_search_threshold...` | Covered by full suite; acceptance file: 3 passed |
| 8 | `pytest test_search_read_only_boundary test_graph_retrieval_read_only_boundary test_context_pack_read_only_boundary test_mcp_tool_read_only_boundary test_mcp_resource_read_only_boundary test_mcp_prompts` | 27 passed |
| Phase 6 | `pytest test_result_explanation test_mcp_explain_result test_project_memory_service test_decision_memory_service test_issue_memory_service test_timeline_memory_service test_health_explorer_service test_mcp_memory_tools test_mcp_recent_changes_tool test_mcp_current_context_resource test_mcp_timeline_resource` | 88 passed |

No command failed for environment or product reasons. The only default skip (MCP stdio smoke) was run explicitly and passed, so it does not change any verdict.

## 4. Success Criteria Matrix

| # | Success Criterion | Verdict | Evidence | Gap / Risk | Recommended Next Action |
| ---: | --- | --- | --- | --- | --- |
| 1 | A user can point it at a Vault and build an index without mutating Vault. | PASS | `vg init`/`vg index` (`cli/main.py:262`, `:298`); `path_guard.assert_write_target_allowed` (`app/path_guard.py:19`); `test_read_only_boundary.py::test_index_commands_do_not_modify_vault_files` hashes Vault files before/after and asserts unchanged; init rejects state path / symlink inside Vault. | None product-impacting. | Keep current read-only boundary tests in CI gate. |
| 2 | A user can register multiple Vaults and index one Vault or all Vaults explicitly. | PASS | `vg vault add`/`list` (`cli/main.py:274`,`:290`), `--vault-id`/`--all-vaults` (`:301`,`:302`); mutual-exclusion guard (`:306`) + `test_cli_index_rejects_conflicting_vault_scope_options`; `scope_for_all_enabled` expands to enabled IDs (`vault_catalog.py:155`); per-Vault actual scopes (`query_scope_resolution.py`); `vault_ids` echoed in output (`:321`). | None product-impacting. | None. |
| 3 | Two Vaults with the same relative path do not collide in metadata, vector, graph, MCP, or context-pack output. | PASS | Identity is `(vault_id, path)` (`sqlite_metadata_store.py` PK); direct collision tests for metadata (`test_multi_vault_identity.py`), graph (`test_multi_vault_graph_identity.py`), context-pack (`test_context_pack_builder.py::test_same_chunk_id_from_two_vaults_remains_distinct`), vector (`test_multi_vault_search.py::test_all_vault_search_keeps_identical_paths_separate`), and MCP resources (`test_acceptance_success_criteria.py::test_mcp_document_resources_keep_same_relative_paths_separate_by_vault_id`). | None product-impacting. | Keep the MCP collision test in the acceptance gate. |
| 4 | An agent can request a context pack for a concrete task instead of reading the whole Vault. | PASS | `vg context` (`cli/main.py:367`) and `build_context_pack` MCP tool (`mcp_tools.py:240`), both calling `ContextPackBuilder.build`; bounded by retrieval limit (`context_pack_builder.py:290`), token budget (`:221`), evidence-item budget (`:183`), excerpt truncation (`:404`), omission warnings (`:451`); `test_budget_packing_drops_items_when_evidence_budget_exceeded` proves over-budget evidence is omitted with a `budget_omitted` warning; read-only boundary test confirms no Vault dump. | None product-impacting. | None. |
| 5 | Decision traces include evidence and distinguish stated facts from inferred links. | PASS | `vg decision-trace` (`cli/main.py:536`) and `get_decision_trace` MCP tool (`mcp_tools.py:328`); `DecisionTraceStep.evidence` + `relationship_status` (`graph_retrieval.py:113-114`); status values `stated`/`inferred`/`contested`/`not_applicable` (`graph_retrieval_service.py:738`,`:776`); topic fallback warns `topic_not_durable_decision` (`:255`); missing-evidence warns `graph_evidence_missing` (`:720`). Proven in service, CLI (JSON shows `relationship_path[].status`), and MCP payload. | None product-impacting. | None. |
| 6 | All indexes can be deleted and rebuilt from Vault. | PASS | Derived state lives under `state_path/{metadata,vector,graph}`, never inside Vault (`catalog_service.py`); `vg index --full` rebuilds from Vault (`test_cli_index_accepts_full_option`); vector/graph scope-local reconcile rebuilds derived projections; `test_acceptance_success_criteria.py::test_deleted_vault_graph_index_state_rebuilds_from_vault_without_mutating_vault` deletes metadata/vector/graph state, runs `vg index --vault-id`, verifies metadata/keyword/vector/graph freshness, and asserts Vault hashes unchanged. | None product-impacting. | Keep documented state deletion + `vg index`; defer `vg reset-index` until a real user-facing gap appears. |
| 7 | Local-first operation works without internet access. | PASS | Search-time embedding forces `local_files_only=True` (`cli/main.py:257`, `mcp_service_factory.py:317`); `can_embed_without_download()` checks local artifact without download (`fastembed_text_embeddings.py:77`); `test_acceptance_success_criteria.py::test_offline_search_threshold_degrades_without_embedding_or_cache_mutation` sets `HF_HUB_OFFLINE`, fakes model unavailability, asserts keyword-only results and visible warnings, and proves no embedding/cache mutation occurs. | None product-impacting. | Keep deterministic offline smoke in CI; reserve real cached-model network-blocked testing for manual release checks. |
| 8 | Retrieval output never bypasses Vault's durable publication workflow. | PASS | Read-only boundary tests for search, graph retrieval, context pack, MCP tools, and MCP resources all snapshot Vault bytes before/after and assert unchanged; all seven MCP prompts carry the shared instruction to route durable changes through Vault capture/validation/release/Git and "Do not publish through Vault Graph" (`mcp_prompts.py:37`, `test_mcp_prompts.py`); retrieval stores opened read-only (`cli/main.py:146`). | None product-impacting. | None. |

## 5. Detailed Findings

### 5.1 Criterion 1 — Index without mutating Vault

- **Verdict:** PASS
- **Evidence:** `vg init` (`cli/main.py:262`) and `vg index` (`:298`) exist. `app/path_guard.py:19` (`assert_write_target_allowed`) confines all writes to the configured state path and rejects targets inside any Vault root. `test_read_only_boundary.py::test_index_commands_do_not_modify_vault_files` hashes every Vault file before and after `index --dry-run` and `index`, asserting bytes are unchanged. Init rejects a state path inside Vault and a symlink redirect into Vault. `test_vector_indexing_read_only_boundary.py` and `test_graph_indexing_read_only_boundary.py` take full tree snapshots and prove indexing writes only Vault Graph state. A real temporary Vault fixture is indexed via the CLI in `test_cli_catalog_metadata.py`.
- **Risk:** None product-impacting.
- **Recommended Next Action:** Keep the read-only boundary suite in the required CI gate.

### 5.2 Criterion 2 — Multi-Vault registration and explicit indexing

- **Verdict:** PASS
- **Evidence:** `vg vault add`/`vg vault list` (`cli/main.py:274`,`:290`); `vg index --vault-id` and `--all-vaults` (`:301`,`:302`). The CLI rejects both flags together (`:306`), covered by `test_cli_index_rejects_conflicting_vault_scope_options`. `--all-vaults` expands through `VaultCatalog.scope_for_all_enabled()` (`vault_catalog.py:155`) to explicit enabled `vault_id`s, then to per-Vault actual scopes (`query_scope_resolution.py`), before services run — verified by `test_all_vaults_expands_only_enabled_entries` and `test_actual_scopes_keep_each_vault_narrow`. `vault_ids` are echoed in index/search output. `test_all_vault_graph_apply_creates_revisions_per_normalized_vault_scope` shows revisions are keyed per Vault scope, so a `--vault-id` run does not mark unrelated Vaults stale.
- **Risk:** None product-impacting.
- **Recommended Next Action:** None.

### 5.3 Criterion 3 — Same relative path does not collide

- **Verdict:** PASS
- **Evidence:** File identity is `(vault_id, path)` with a composite primary key in `sqlite_metadata_store.py` and a unique `document_id`. Direct same-relative-path / same-name collision tests exist for **metadata** (`test_multi_vault_identity.py::test_two_vaults_with_same_relative_path_do_not_collide`), **graph** (`test_multi_vault_graph_identity.py::test_same_entity_name_in_two_vaults_does_not_collide` and the manifest separation tests), and **context-pack** (`test_context_pack_builder.py::test_same_chunk_id_from_two_vaults_remains_distinct`, plus `test_cli_context_all_vaults_uses_real_retrieval_and_preserves_evidence_vault_ids`). **Vector** is covered through `test_multi_vault_search.py::test_all_vault_search_keeps_identical_paths_separate` (two Vaults with `wiki/same.md`, results keyed and `result_id`-namespaced by `vault_id`).
- **Acceptance closure:** `test_acceptance_success_criteria.py::test_mcp_document_resources_keep_same_relative_paths_separate_by_vault_id` adds the direct MCP resource scenario: two Vaults each expose `wiki/same.md`, and `vault://main/documents/wiki%2Fsame.md` plus `vault://work/documents/wiki%2Fsame.md` resolve to distinct content and distinct `document_id`s under their own `vault_id`.
- **Risk:** None product-impacting.
- **Recommended Next Action:** Keep this acceptance test in the multi-Vault gate.

### 5.4 Criterion 4 — Agent context pack instead of whole Vault

- **Verdict:** PASS
- **Evidence:** `vg context "goal"` (`cli/main.py:367`) and the `build_context_pack` MCP tool (`mcp_tools.py:240`) both construct a `ContextPackRequest` and call `ContextPackBuilder.build` over retrieval results — neither enumerates Vault files. The `ContextPack` DTO (`context_pack.py:272`) carries goal, scope (requested + actual), vaults, vault_revisions, store_revisions, budget, evidence, and warnings. Boundedness is enforced and tested: retrieval limit cap (`context_pack_builder.py:290`), token budget check (`:221`), evidence-item budget (`:183`), excerpt truncation with `excerpt_truncated` warning (`:404`), and `budget_omitted` warnings (`:451`). `test_budget_packing_drops_items_when_evidence_budget_exceeded` proves over-budget evidence is omitted (not dumped) with a visible warning; `test_omitted_multi_evidence_item_does_not_leave_orphan_evidence` proves no orphaned evidence. `test_context_pack_read_only_boundary.py` proves building a pack does not mutate Vault.
- **Risk:** None product-impacting.
- **Recommended Next Action:** None.

### 5.5 Criterion 5 — Decision trace evidence and stated/inferred distinction

- **Verdict:** PASS
- **Evidence:** `vg decision-trace TOPIC` (`cli/main.py:536`) and the `get_decision_trace` MCP tool (`mcp_tools.py:328`). `DecisionTraceStep` carries `evidence: tuple[EvidenceReference, ...]` and `relationship_status` (`graph_retrieval.py:113-114`). The service sets the initial decision step to `not_applicable` and derives path-step status as the minimum across edges (`graph_retrieval_service.py:738`,`:776`), distinguishing `stated` from `inferred`/`contested`. Topic fallback emits a `topic_not_durable_decision` warning when the target is not a durable decision entity (`:255`); missing entity evidence emits `graph_evidence_missing` (`:720`). The distinction is visible in the service result, the CLI JSON (`relationship_path[].status` and per-step `evidence`), and the MCP payload (`test_decision_trace_opens_graph_service_after_validation`).
- **Risk:** None product-impacting.
- **Recommended Next Action:** None.

### 5.6 Criterion 6 — Delete and rebuild all indexes from Vault

- **Verdict:** PASS
- **Evidence:** Rebuildable state lives under `state_path/{metadata,vector,graph}`, outside Vault roots (`catalog_service.py`). `vg index --full` forces a full rebuild from Vault (`test_cli_index_accepts_full_option`; `metadata_indexer.py` reloads all documents when `full=True` or state is absent). Scope-local reconcile rebuilds vector and graph projections from `MetadataStore` chunks (`test_index_service_vector_reconcile.py`, `test_index_service_graph_reconcile.py`), and `test_delete_reconcile_reports_fresh_readiness` covers deleted-Vault-file reconcile.
- **Acceptance closure:** `test_acceptance_success_criteria.py::test_deleted_vault_graph_index_state_rebuilds_from_vault_without_mutating_vault` deletes the configured Vault Graph metadata/vector/graph index state, runs `vg index --vault-id default`, verifies metadata/keyword/vector/graph freshness, and asserts Vault file hashes are identical before and after. During this closure, `ChromaVectorStore.close()` and `IndexService.close()` were added so same-process delete→rebuild does not retain stale Chroma handles.
- **Risk:** None product-impacting. The accepted UX does not add a destructive command.
- **Recommended Next Action:** Documented state-directory deletion plus `vg index` is enough before public release; add `vg reset-index` only if a real user-facing gap appears.

### 5.7 Criterion 7 — Local-first offline operation

- **Verdict:** PASS
- **Evidence:** Search-time query embedding is constructed with `local_files_only=True` in both the CLI (`cli/main.py:257`) and the MCP service factory (`mcp_service_factory.py:317`), which flows to `huggingface_hub.snapshot_download(local_files_only=...)` (`fastembed_text_embeddings.py:148`). `can_embed_without_download()` (`:77`) checks local artifact availability without triggering a download, and `ReadOnlySearchReadiness.check()` surfaces it. When the model artifact or vector projection is unavailable, search degrades to keyword-only with visible warnings (`test_retrieval_service_search.py::test_keyword_only_search_returns_evidence_chunk`, `::test_vector_query_failure_degrades_with_visible_warning`) and never mutates Vault or state (`test_search_read_only_boundary.py`).
- **Acceptance closure:** `test_acceptance_success_criteria.py::test_offline_search_threshold_degrades_without_embedding_or_cache_mutation` sets `HF_HUB_OFFLINE`, uses an offline `TextEmbeddings` fake whose `can_embed_without_download()` returns `False`, asserts keyword-only results plus `embedding_model_unavailable` and `degraded_keyword_only` warnings, and proves `embed()` is not called and no cache path is created.
- **Risk:** None product-impacting. The deterministic smoke is CI-friendly; real cached-model network blocking remains a manual release check.
- **Recommended Next Action:** Keep deterministic offline smoke in CI.

### 5.8 Criterion 8 — Retrieval output does not bypass Vault publication

- **Verdict:** PASS
- **Evidence:** Read-only boundary tests cover search (`test_search_read_only_boundary.py`), graph retrieval (`test_graph_retrieval_read_only_boundary.py`), context pack (`test_context_pack_read_only_boundary.py`), MCP tools (`test_mcp_tool_read_only_boundary.py`), and MCP resources (`test_mcp_resource_read_only_boundary.py`); each snapshots Vault bytes before/after and asserts no change. All seven MCP prompts include the shared instruction to propose Vault source capture / validation / release-gate / Git and "Do not publish through Vault Graph" (`mcp_prompts.py:37`), verified by `test_mcp_prompts.py`. Retrieval stores are opened read-only (`cli/main.py:146`, `initialize=False, read_only=True`). No retrieval command writes Vault files or publishes wiki pages.
- **Risk:** None product-impacting.
- **Recommended Next Action:** None.

### 5.9 Phase 6 Projection Coverage (supporting evidence)

All Phase 6 services are implemented, pass their tests (88 passed across the Phase 6 group), and remain read-only, evidence-linked projections — not a durable memory database and not answer synthesis.

| Projection | Service / Test | Carries vault_id + evidence + warnings | Read-only |
| --- | --- | --- | --- |
| Result explanation | `test_result_explanation.py`, `test_mcp_explain_result.py` | Yes (identity + evidence + signals) | Cache view, no write |
| Project memory | `test_project_memory_service.py` | Yes | Projection over metadata |
| Decision memory | `test_decision_memory_service.py` | Yes (claim_status + evidence) | Projection + optional graph trace |
| Issue / open-question memory | `test_issue_memory_service.py` | Yes (status + evidence) | Projection |
| Timeline memory | `test_timeline_memory_service.py`, `test_mcp_timeline_resource.py` | Yes (revisions + generated_at) | Projection |
| Health explorer | `test_health_explorer_service.py` | Yes (backend status, scope vault_ids) | Read-only inspection |
| MCP memory tools / recent changes / current context | `test_mcp_memory_tools.py`, `test_mcp_recent_changes_tool.py`, `test_mcp_current_context_resource.py` | Yes (preserved in JSON payload) | Serialization / resource read |

These projections support criteria 4, 5, and 8 (bounded context, evidence-linked decisions, read-only working context) and introduce no generic writable memory API.

## 6. Multi-Angle Review

### 6.1 Security / Read-Only Safety

- No recommendation in this review implies Vault writes through Vault Graph. The reset/delete acceptance test for criterion 6 is explicitly limited to Vault Graph internal index state and asserts Vault hashes are unchanged. Path examples never delete registered Vault roots or `raw/`/`wiki/`/`docs/`/`scratch/`. MCP remains local stdio and read-only; no HTTP surface is introduced. Chroma read-only search now uses SQLite read-only access instead of opening a mutating Chroma client.

### 6.2 Performance / Scalability

- No criterion is accepted via a full-Vault dump; criterion 4 explicitly proves bounded context (budgets, truncation, omission warnings). Multi-Vault checks preserve `QueryScope` and explicit `vault_id`s, and `--all-vaults` expands to per-Vault actual scopes before stores run. Acceptance scenarios for criteria 6 and 7 use bounded fixtures and scope-local rebuild/degradation, not whole-catalog scale runs. The reconcile model rebuilds index state scope-locally.

### 6.3 Testability / CI

- Every criterion has at least one reproducible, specific command (Section 3) that a future agent can rerun. The former gaps are now covered by `tests/test_acceptance_success_criteria.py`: MCP collision resource test, delete→rebuild scenario, and deterministic offline smoke.

### 6.4 Maintainability / Deep Modules

- The changes keep deep-module boundaries: CLI and MCP continue to call application services (`RetrievalService`, `GraphRetrievalService`, `IndexService`), not backend stores directly. Chroma-specific cleanup stays inside `ChromaVectorStore` and `IndexService.close()`. No new durable knowledge source, hidden memory layer, or destructive CLI command is introduced. Terminology used here matches the project: `vault_id`, `QueryScope`, evidence chunks, index state, derived projections, actual scopes, context packs.

### 6.5 Product / Agent Ergonomics

- A human can read the Executive Summary and Matrix in under a page and know what works. Agents have concrete file/test evidence and rerunnable commands per criterion. The former Open Decisions are resolved and recorded in `docs/DECISIONS.md`. Future TODO items (acceleration, non-Markdown readers, chunking migrations, external memory, `vg ask`, HTTP serving) are kept out of the acceptance blockers.

### 6.6 Documentation Consistency

- `SPEC.md`, `FEATURES.md`, and `DESIGN.md` were treated as source context, not as proof of implementation; every PASS is backed by code plus a test, never by a design doc alone. `SPEC.md` §17 now separates implemented CLI commands from CLI TODO commands and replaces the old "Initial CLI" wording. `docs/DECISIONS.md` records the accepted reset, offline, and CLI-documentation decisions, and `docs/PATCH_LOG.md` records the acceptance-review correction.

### 6.7 Phase 6 Projection Coverage

- Result explanation, project/decision/issue/timeline memory, health explorer, and MCP memory resources/tools are all included as supporting evidence (Section 5.9) and are read-only working context, not a durable memory database. The review does not treat any Phase 6 output as answer synthesis or as a replacement for Vault publication.

## 7. Resolved Decisions

### Resolved Decision 1: Index Reset UX (criterion 6)

Accepted: document and test deletion of Vault Graph internal index state followed by `vg index` / `vg index --vault-id`. Do not add `vg reset-index` before public release unless a real user-facing gap appears. Recorded in `docs/DECISIONS.md`.

### Resolved Decision 2: Offline Acceptance Threshold (criterion 7)

Accepted: require a deterministic offline smoke test with network/download paths disabled or faked. Keep real cached-model plus OS-level network-blocking checks as optional manual release checks. Recorded in `docs/DECISIONS.md`.

### Resolved Decision 3: CLI Documentation Clarity (§17)

Accepted: replace "Initial CLI" with implemented CLI commands plus a CLI TODO block. `vg watch`, `vg ask`, and `vg serve --http` are not current product features. Recorded in `docs/DECISIONS.md`.

## 8. Completed Acceptance Actions

### Closed blockers

1. **MCP same-relative-path collision test (criterion 3):** added and passing.
2. **Delete→rebuild acceptance test (criterion 6):** added and passing.
3. **Deterministic offline smoke test (criterion 7):** added and passing.
4. **CLI documentation clarity:** `SPEC.md` §17 now distinguishes implemented commands from CLI TODO commands.

### Remaining future work, not acceptance blockers

5. MacBook acceleration, non-Markdown readers, chunking migrations, external memory adapters, `ask_vault`/answer synthesis, and Phase 7 UI/HTTP remain future scope.
6. A guided `vg reset-index` command remains optional future UX if manual state-directory deletion becomes confusing for real users.
