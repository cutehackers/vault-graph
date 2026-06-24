# Implementation Success Criteria Acceptance Review Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Create a structured Acceptance Review document that evaluates the current implemented Vault Graph product surface against `docs/SPEC.md` Success Criteria.

**Architecture:** The review is an evidence ledger over the current checkout. It maps each product success criterion to concrete command output, source/test evidence, risks, and next actions while preserving Vault Graph as a read-only, rebuildable projection over Vault.

**Tech Stack:** Markdown, Git metadata, Python 3.12, pytest, ruff, mypy, existing Vault Graph CLI/MCP/service tests.

---

## Source Documents

Read before executing this plan:

- `AGENTS.md`
- `docs/SPEC.md`, especially section `20. Success Criteria`
- `docs/FEATURES.md`
- `docs/DESIGN.md`
- `docs/CONVENTIONS.md`
- `docs/DECISIONS.md`
- `docs/PATCH_LOG.md`
- `docs/superpowers/plans/2026-06-23-acceptance-review-guide.md`
- Relevant Phase 4, Phase 5, and Phase 6 specs when using context pack, MCP, or memory/explorer evidence
- Targeted source/test files listed in this plan

Start with the named files, named tests, and `rg` searches in this plan. Broaden to other source or test files only to answer a missing evidence question.

## Scope

Create one review artifact:

- `docs/superpowers/reviews/2026-06-23-implementation-success-criteria-acceptance-review.md`

The review evaluates implemented Phase 1-6 product behavior:

- Vault catalog, Vault loading, metadata indexing
- vector/keyword search and readiness behavior
- graph indexing, graph retrieval, `vg related`, and decision traces
- context pack generation through CLI and MCP
- MCP server, resources, tools, and prompts
- Phase 6 result explanation, project/decision/issue memory, recent changes, and health explorer projections

## Non-Goals

Do not implement:

- Phase 7 UI, HTTP serving, or browser views
- `Ask Project`, `ask_vault`, answer synthesis, LLM adapter policy, or citation-generation policy
- MacBook acceleration, non-Markdown readers, chunking migration, or external memory adapters
- `vg reset-index` or any new CLI command
- new code, tests, store interfaces, migrations, or runtime behavior
- updates to `docs/DECISIONS.md`
- updates to `docs/PATCH_LOG.md` unless this task is explicitly expanded to correct an existing plan, spec, or implementation because of a verified mismatch, defect, or risk
- Vault file edits, Vault publication, source capture, wiki mutation, or durable knowledge creation

If the review finds a code/spec mismatch, record it as a finding or follow-up. Do not fix source, specs, or Vault content during this acceptance-review task unless the user explicitly changes the scope.

## Directory And File Structure

Create:

- `docs/superpowers/reviews/2026-06-23-implementation-success-criteria-acceptance-review.md`

Do not modify:

- `src/**`
- `tests/**`
- `docs/SPEC.md`
- `docs/FEATURES.md`
- `docs/DESIGN.md`
- `docs/DECISIONS.md`
- `docs/PATCH_LOG.md`

The implementation plan may be executed while the guide file
`docs/superpowers/plans/2026-06-23-acceptance-review-guide.md` is still untracked. Do not stage or commit unless the user asks.

## Review Document Contract

The review document must use this top-level structure:

```markdown
# Vault Graph Implementation Success Criteria Acceptance Review

Status: Draft
Date: 2026-06-23
Reviewer: Codex
Branch: <branch>
Commit: <short-sha>

## 1. Executive Summary
## 2. Review Scope
## 3. Verification Commands
## 4. Success Criteria Matrix
## 5. Detailed Findings
## 6. Multi-Angle Review
## 7. Open Decisions
## 8. Recommended Next Actions
```

Section `1. Executive Summary` must include a verdict-count table and 3-6 short conclusion bullets:

```markdown
| Verdict | Count |
| --- | ---: |
| PASS | N |
| PARTIAL | N |
| GAP | N |
| NOT IN CURRENT SCOPE | N |
| UNKNOWN | N |
```

Use these verdicts only:

- `PASS`
- `PARTIAL`
- `GAP`
- `NOT IN CURRENT SCOPE`
- `UNKNOWN`

Start all criteria as `TBD` during drafting. Convert to a verdict only after current-checkout evidence has been recorded.

Verdict definitions:

- `PASS`: implemented behavior is covered by current code and verification evidence, with no known product-impacting gap.
- `PARTIAL`: core behavior exists, but user-facing flow, end-to-end acceptance evidence, or operational documentation is incomplete.
- `GAP`: the criterion is not currently satisfied.
- `NOT IN CURRENT SCOPE`: the criterion or sub-feature is explicitly future work and should not block current acceptance.
- `UNKNOWN`: evidence was not collected; avoid this in the final review unless a command cannot be run.

## Data Flow

```text
SPEC Success Criteria
  -> targeted source/test inspection
  -> focused verification commands
  -> command result records
  -> per-criterion verdicts
  -> detailed findings
  -> multi-angle review
  -> P0/P1/P2 next actions and open decisions
```

Rules:

- Design docs explain intent; they are not implementation proof.
- Unit tests support evidence, but user-facing criteria need CLI/MCP/service acceptance evidence where available.
- Future TODO sections are not current implementation backlog.
- All review recommendations must preserve read-only Vault boundaries.

## Implementation Tasks

### Task 1: Capture Current Checkout Snapshot

**Files:**

- Create: `docs/superpowers/reviews/2026-06-23-implementation-success-criteria-acceptance-review.md`

- [ ] Create `docs/superpowers/reviews/` if it does not exist.
- [ ] Run:

```bash
git status --short --branch
git rev-parse --short HEAD
```

- [ ] Record branch, commit, dirty/untracked files, and whether the review is based on the current checkout.
- [ ] Add the review header and `Status: Draft`.
- [ ] Add the Executive Summary verdict-count table with all counts set to `TBD` or `0` until evidence is gathered.
- [ ] Add 3-6 placeholder conclusion bullets that will be finalized after the matrix is complete.
- [ ] Add `Review Scope` with included Phase 1-6 surfaces and excluded future work.

Expected outcome:

- Review file exists.
- All success criteria are present with `TBD` verdicts.
- Phase 7 and future TODO items are explicitly out of scope.

### Task 2: Build The Success Criteria Matrix

**Files:**

- Modify: `docs/superpowers/reviews/2026-06-23-implementation-success-criteria-acceptance-review.md`

- [ ] Copy the eight success criteria from `docs/SPEC.md` exactly.
- [ ] Add this matrix:

```markdown
| # | Success Criterion | Verdict | Evidence | Gap / Risk | Recommended Next Action |
| ---: | --- | --- | --- | --- | --- |
| 1 | A user can point it at a Vault and build an index without mutating Vault. | TBD | TBD | TBD | TBD |
| 2 | A user can register multiple Vaults and index one Vault or all Vaults explicitly. | TBD | TBD | TBD | TBD |
| 3 | Two Vaults with the same relative path do not collide in metadata, vector, graph, MCP, or context-pack output. | TBD | TBD | TBD | TBD |
| 4 | An agent can request a context pack for a concrete task instead of reading the whole Vault. | TBD | TBD | TBD | TBD |
| 5 | Decision traces include evidence and distinguish stated facts from inferred links. | TBD | TBD | TBD | TBD |
| 6 | All indexes can be deleted and rebuilt from Vault. | TBD | TBD | TBD | TBD |
| 7 | Local-first operation works without internet access. | TBD | TBD | TBD | TBD |
| 8 | Retrieval output never bypasses Vault's durable publication workflow. | TBD | TBD | TBD | TBD |
```

- [ ] Add an `Evidence Standard` subsection explaining that `PASS` requires current code/test/command proof, not docs alone.

Expected outcome:

- The matrix is readable in one screen.
- No criterion starts as `PASS`.

### Task 3: Gather Criterion 1 Evidence

**Files:**

- Modify: review document only

Criterion:

- A user can point it at a Vault and build an index without mutating Vault.

Inspect:

- `src/vault_graph/cli/main.py`
- `src/vault_graph/app/catalog_service.py`
- `src/vault_graph/app/index_service.py`
- `tests/test_cli_catalog_metadata.py`
- `tests/test_metadata_indexer.py`
- `tests/test_read_only_boundary.py`
- `tests/test_vector_indexing_read_only_boundary.py`
- `tests/test_graph_indexing_read_only_boundary.py`

Run:

```bash
uv run --python 3.12 pytest tests/test_cli_catalog_metadata.py tests/test_metadata_indexer.py tests/test_read_only_boundary.py tests/test_vector_indexing_read_only_boundary.py tests/test_graph_indexing_read_only_boundary.py -q
```

Record:

- command result
- CLI support for `vg init` and `vg index`
- evidence that writes stay under Vault Graph state, not registered Vault roots
- final verdict and next action

Expected verdict bias:

- `PASS` if CLI indexing and read-only boundary tests pass.
- `PARTIAL` if evidence is service-only and lacks CLI fixture coverage.

### Task 4: Gather Criterion 2 Evidence

**Files:**

- Modify: review document only

Criterion:

- A user can register multiple Vaults and index one Vault or all Vaults explicitly.

Inspect:

- `src/vault_graph/ingestion/vault_catalog.py`
- `src/vault_graph/app/query_scope_resolution.py`
- `src/vault_graph/cli/main.py`
- `tests/test_vault_catalog.py`
- `tests/test_cli_catalog_metadata.py`
- `tests/test_query_scope_resolution.py`
- `tests/test_multi_vault_search.py`
- `tests/test_cli_context.py`

Run:

```bash
uv run --python 3.12 pytest tests/test_vault_catalog.py tests/test_cli_catalog_metadata.py tests/test_query_scope_resolution.py tests/test_multi_vault_search.py tests/test_cli_context.py -q
```

Record:

- `vg vault add` and `vg vault list` evidence
- `vg index --vault-id` and `vg index --all-vaults` evidence
- conflict rejection for `--vault-id` with `--all-vaults`
- per-Vault actual scope behavior
- disabled or narrower content-scope handling
- explicit enabled Vault IDs before application services run
- no hidden global all-Vault content-scope union
- Vault/scope-keyed revisions and warnings
- proof that `--vault-id` partial indexing does not mark unrelated Vault scopes stale

Expected verdict bias:

- `PASS` only if successful one-Vault and all-Vault paths are proven with explicit enabled Vault IDs, per-Vault actual scopes, no widened disabled/narrow scopes, Vault/scope-keyed revisions/warnings, and no unrelated stale marks.
- `PARTIAL` if all-Vault behavior is only shown outside indexing.

### Task 5: Gather Criterion 3 Evidence

**Files:**

- Modify: review document only

Criterion:

- Two Vaults with the same relative path do not collide in metadata, vector, graph, MCP, or context-pack output.

Inspect:

- `tests/test_multi_vault_identity.py`
- `tests/test_multi_vault_search.py`
- `tests/test_multi_vault_graph_identity.py`
- `tests/test_multi_vault_graph_indexing.py`
- `tests/test_multi_vault_graph_retrieval.py`
- `tests/test_cli_context.py`
- `tests/test_mcp_scope.py`
- `tests/test_mcp_tool_serialization.py`

Run:

```bash
uv run --python 3.12 pytest tests/test_multi_vault_identity.py tests/test_multi_vault_search.py tests/test_multi_vault_graph_identity.py tests/test_multi_vault_graph_indexing.py tests/test_multi_vault_graph_retrieval.py tests/test_cli_context.py::test_cli_context_all_vaults_uses_real_retrieval_and_preserves_evidence_vault_ids -q
```

MCP-focused evidence:

```bash
uv run --python 3.12 pytest tests/test_mcp_scope.py tests/test_mcp_tool_serialization.py -q
```

Record:

- same-relative-path fixture evidence
- `vault_id` preservation in metadata/search/graph/context-pack evidence
- whether MCP has direct same-relative-path collision coverage
- if the MCP command is not run, whether MCP evidence is indirect and therefore insufficient for `PASS`

Expected verdict bias:

- `PASS` if every named surface is directly or convincingly covered.
- `PARTIAL` with a P1 acceptance-test gap if MCP same-relative-path evidence is indirect.

### Task 6: Gather Criterion 4 Evidence

**Files:**

- Modify: review document only

Criterion:

- An agent can request a context pack for a concrete task instead of reading the whole Vault.

Inspect:

- `src/vault_graph/context/context_pack_builder.py`
- `src/vault_graph/context/context_pack.py`
- `src/vault_graph/mcp/mcp_tools.py`
- `tests/test_context_pack_builder.py`
- `tests/test_context_pack_evidence_budget.py`
- `tests/test_context_pack_warnings.py`
- `tests/test_cli_context.py`
- `tests/test_mcp_tools.py`
- `tests/test_context_pack_read_only_boundary.py`

Run:

```bash
uv run --python 3.12 pytest tests/test_context_pack_builder.py tests/test_context_pack_evidence_budget.py tests/test_context_pack_warnings.py tests/test_cli_context.py tests/test_mcp_tools.py::test_build_context_pack_renders_and_caches_pack_json tests/test_context_pack_read_only_boundary.py -q
```

Record:

- `vg context "goal"` evidence
- MCP `build_context_pack` evidence
- context budget, evidence budget, truncation, omission warning evidence
- evidence that context packs use retrieval results and do not enumerate or emit the whole Vault
- negative fixture evidence: irrelevant documents are present, over-budget evidence is present, output stays within configured budgets, and omissions/truncations are warned
- proof that CLI/MCP context surfaces call `ContextPackBuilder` over retrieval results instead of enumerating Vault files or MCP resources

Expected verdict bias:

- `PASS` only with bounded-context proof.
- `PARTIAL` if the context pack exists but boundedness is not proven.

### Task 7: Gather Criterion 5 Evidence

**Files:**

- Modify: review document only

Criterion:

- Decision traces include evidence and distinguish stated facts from inferred links.

Inspect:

- `src/vault_graph/app/graph_retrieval_service.py`
- `src/vault_graph/mcp/mcp_tools.py`
- `src/vault_graph/mcp/mcp_tool_serialization.py`
- `tests/test_graph_retrieval_service.py`
- `tests/test_cli_decision_trace.py`
- `tests/test_mcp_tools.py`

Run:

```bash
uv run --python 3.12 pytest tests/test_graph_retrieval_service.py tests/test_cli_decision_trace.py tests/test_mcp_tools.py::test_decision_trace_opens_graph_service_after_validation -q
```

Record:

- `vg decision-trace TOPIC` evidence
- MCP `get_decision_trace` evidence
- evidence references on trace steps
- relationship status values such as `stated`, `inferred`, and `not_applicable`
- topic fallback warning behavior

Expected verdict bias:

- `PASS` if service, CLI, and MCP all preserve evidence/status.

### Task 8: Gather Criterion 6 Evidence

**Files:**

- Modify: review document only

Criterion:

- All indexes can be deleted and rebuilt from Vault.

Inspect:

- `src/vault_graph/app/path_guard.py`
- `src/vault_graph/app/catalog_service.py`
- `src/vault_graph/app/index_service.py`
- `tests/test_cli_catalog_metadata.py`
- `tests/test_index_service_vector_reconcile.py`
- `tests/test_index_service_graph_reconcile.py`
- read-only boundary tests from Task 3

Run:

```bash
uv run --python 3.12 pytest tests/test_cli_catalog_metadata.py::test_cli_index_accepts_full_option tests/test_index_service_vector_reconcile.py tests/test_index_service_graph_reconcile.py -q
```

Record:

- evidence that derived state is outside Vault roots
- evidence that full or fresh indexing rebuilds derived projections
- whether there is a supported user-facing delete/reset acceptance scenario
- whether Vault file hashes are proven unchanged during reset/rebuild evidence
- proof that any deletion evidence targets only a bounded fixture-owned namespace or configured Vault Graph derived-state path
- proof that registered Vault roots and Vault `raw/`, `wiki/`, `docs/`, and `scratch/` paths are rejected as deletion targets
- a bounded scope-local scenario first: delete only derived state for one `vault_id`, rebuild with `vg index --vault-id`, verify metadata/keyword/vector/graph surfaces, and record counts/duration for any later `--all-vaults` rebuild

Expected verdict bias:

- `PASS` requires deletion evidence from a bounded fixture or configured Vault Graph derived-state path only; the scenario must reject registered Vault roots and Vault `raw/`, `wiki/`, `docs/`, and `scratch/` paths, and must prove Vault file hashes are unchanged before/after rebuild.
- `PARTIAL` unless a concrete safe derived-state deletion plus rebuild scenario exists.
- If the review recommends a future command, keep it as an Open Decision. Do not add it to `docs/DECISIONS.md`.

### Task 9: Gather Criterion 7 Evidence

**Files:**

- Modify: review document only

Criterion:

- Local-first operation works without internet access.

Inspect:

- `src/vault_graph/embeddings/fastembed_text_embeddings.py`
- `src/vault_graph/app/search_readiness_service.py`
- `src/vault_graph/retrieval/retrieval_service.py`
- `src/vault_graph/cli/main.py`
- `tests/test_fastembed_text_embeddings.py`
- `tests/test_app_search_readiness_service.py`
- `tests/test_retrieval_service_search.py`
- `tests/test_search_read_only_boundary.py`

Run:

```bash
uv run --python 3.12 pytest tests/test_fastembed_text_embeddings.py tests/test_app_search_readiness_service.py tests/test_retrieval_service_search.py tests/test_search_read_only_boundary.py -q
```

Record:

- local-only/no-download search behavior
- missing model or unavailable vector behavior
- whether the command actually disables network/download paths

Expected verdict bias:

- `PARTIAL` until a hermetic offline smoke exists.
- Recommended next action should be a deterministic offline smoke test with network/download calls disabled or faked.

### Task 10: Gather Criterion 8 Evidence

**Files:**

- Modify: review document only

Criterion:

- Retrieval output never bypasses Vault's durable publication workflow.

Inspect:

- `src/vault_graph/cli/main.py`
- `src/vault_graph/mcp/mcp_prompts.py`
- `tests/test_cli_search.py`
- `tests/test_cli_related.py`
- `tests/test_cli_context.py`
- `tests/test_cli_decision_trace.py`
- `tests/test_cli_surface_boundary.py`
- `tests/test_search_read_only_boundary.py`
- `tests/test_graph_retrieval_read_only_boundary.py`
- `tests/test_context_pack_read_only_boundary.py`
- `tests/test_mcp_tool_read_only_boundary.py`
- `tests/test_mcp_resource_read_only_boundary.py`
- `tests/test_mcp_prompts.py`

Run:

```bash
uv run --python 3.12 pytest tests/test_cli_search.py tests/test_cli_related.py tests/test_cli_context.py tests/test_cli_decision_trace.py tests/test_cli_surface_boundary.py tests/test_search_read_only_boundary.py tests/test_graph_retrieval_read_only_boundary.py tests/test_context_pack_read_only_boundary.py tests/test_mcp_tool_read_only_boundary.py tests/test_mcp_resource_read_only_boundary.py tests/test_mcp_prompts.py -q
```

Record:

- read-only retrieval evidence
- prompt wording that routes durable changes through Vault workflow
- absence of Vault publication or mutation in retrieval tools
- Task 11 Phase 6 evidence showing project/decision/issue memory, result explanation, recent changes, timeline, health, and MCP memory projections remain read-only working context

Expected verdict bias:

- `PASS` only after CLI/MCP prompts, tools, read-only tests, and Task 11 Phase 6 evidence prove durable changes are routed through Vault workflow.
- `PARTIAL` if Phase 6 projection outputs are not checked for publication-boundary safety.

### Task 11: Gather Phase 6 Projection Evidence

**Files:**

- Modify: review document only

Purpose:

- Phase 6 is in current implemented scope, but it supports success criteria rather than adding a separate `SPEC.md` success criterion. Record it as cross-cutting evidence for agent ergonomics, evidence-first output, and publication-boundary safety.

Inspect:

- `src/vault_graph/memory/**`
- `src/vault_graph/mcp/mcp_memory_serialization.py`
- `src/vault_graph/mcp/mcp_tools.py`
- `src/vault_graph/mcp/mcp_resources.py`

Run:

```bash
uv run --python 3.12 pytest tests/test_result_explanation.py tests/test_mcp_explain_result.py tests/test_project_memory_service.py tests/test_decision_memory_service.py tests/test_issue_memory_service.py tests/test_timeline_memory_service.py tests/test_health_explorer_service.py tests/test_mcp_memory_tools.py tests/test_mcp_recent_changes_tool.py tests/test_mcp_current_context_resource.py tests/test_mcp_timeline_resource.py -q
```

Record:

- result explanation evidence
- project/decision/issue memory evidence
- timeline and health explorer evidence
- whether all Phase 6 projections remain read-only working context
- `QueryScope` evidence: active Vault by default, explicit Vault IDs for multi-vault, and no hidden cross-vault widening
- limit enforcement evidence for memory, recent changes, and open questions
- Vault IDs, revisions, warnings, and freshness fields in outputs
- evidence that projections do not become full project memory dumps or durable memory authority

Expected outcome:

- Section `6. Multi-Angle Review` or `5. Detailed Findings` explains how Phase 6 supports the current acceptance review without turning memory projections into durable knowledge.

### Task 12: Run Final Verification Commands

**Files:**

- Modify: review document only

Run once before finalizing:

```bash
git status --short --branch
git rev-parse --short HEAD
uv run --python 3.12 ruff check src tests
uv run --python 3.12 mypy src tests
uv run --python 3.12 pytest
```

MCP stdio smoke is skipped by default. For MCP transport evidence, either run:

```bash
VG_RUN_MCP_STDIO_SMOKE=1 uv run --python 3.12 pytest tests/test_mcp_stdio_smoke.py -q
```

or record the skip as an MCP transport evidence gap.

Record:

- exact command
- pass/fail/skip result
- whether failure is environment-related or product-related
- whether missing evidence changes a verdict
- final branch/SHA and whether they match the review header. Update the review header and Section 3 if the checkout changed during evidence gathering.

Do not rerun `ruff`, `mypy`, or the full test suite after review-document-only edits unless source or tests changed. After Markdown-only edits, rerun the targeted command that was affected plus the final document checks in `Verification`.

### Task 13: Fill Detailed Findings

**Files:**

- Modify: review document only

For each criterion, add:

```markdown
### 5.N <Criterion Short Name>

Verdict: TBD

Evidence:
- `<file>` / `<test>` / `<command>`: <short evidence>

Risk:
- <risk if any>

Recommended Next Action:
- <P0/P1/P2 action>
```

Rules:

- Keep each finding short and evidence-linked.
- Do not paste long command output.
- Use `PARTIAL` for unproven acceptance paths instead of optimistic `PASS`.
- Distinguish acceptance-test gaps from product implementation gaps.

### Task 14: Add Multi-Angle Review

**Files:**

- Modify: review document only

Add subsections:

- Security / Read-Only Safety
- Performance / Scalability
- Testability / CI
- Maintainability / Deep Modules
- Product / Agent Ergonomics
- Documentation Consistency
- Phase 6 Projection Coverage

For each subsection, write:

```markdown
Assessment: PASS | PARTIAL | GAP

Findings:
- ...

Corrections Applied:
- Review-document-only corrections, if any.
```

Rules:

- Apply corrections only to the review document.
- Record source/spec/code mismatches as findings or follow-ups.
- Do not add pending decisions to `docs/DECISIONS.md`.
- Do not add `PATCH_LOG.md` entries unless the user separately approves a correction to an existing document or implementation.

### Task 15: Evaluate Open Decision Candidates

**Files:**

- Modify: review document only

Evaluate these candidates. Add one to `Open Decisions` only if gathered evidence shows real user judgment is needed. Otherwise move non-destructive test/documentation follow-ups to `Recommended Next Actions`.

1. Index Reset UX
   - Context: `SPEC.md` requires indexes can be deleted and rebuilt.
   - Options:
     - document/test derived-state deletion plus `vg index`
     - future `vg reset-index` command
   - Recommendation: document/test derived-state deletion first.
   - Status: pending user approval.

2. Offline Acceptance Threshold
   - Context: `SPEC.md` requires local-first offline behavior.
   - Options:
     - deterministic smoke with network/download paths disabled or faked
     - real cached model plus OS-level network blocking
   - Recommendation: deterministic smoke first.
   - Status: pending user approval.

If evidence shows these are not user decisions, move only non-destructive test/documentation follow-ups to Recommended Next Actions. Any future destructive reset CLI command, including `vg reset-index`, must remain an Open Decision until explicit user approval.

### Task 16: Finalize Recommended Next Actions

**Files:**

- Modify: review document only

Add:

```markdown
## 8. Recommended Next Actions

### P0 Acceptance Blockers
- ...

### P1 Acceptance Hardening
- ...

### P2 Future Improvements
- ...
```

Rules:

- P0: current success criterion cannot be accepted without it.
- P1: current implementation likely works, but evidence is incomplete.
- P2: future TODO or quality improvement, not a current acceptance blocker.
- Do not classify Phase 7 UI, answer synthesis, non-MD readers, Mac acceleration, or external memory adapters as P0/P1 for this review.

## Errors And Edge Cases

Handle these cases in the review:

- A command fails because of a product defect: mark affected criteria `GAP` or `PARTIAL` and record recovery guidance.
- A command fails because of local environment: mark evidence as missing, explain why, and avoid `PASS`.
- MCP stdio smoke is skipped: record skip and decide whether it affects MCP transport confidence.
- No direct MCP same-relative-path collision test exists: keep criterion 3 `PARTIAL` or record a P1 test gap.
- No reset/delete acceptance scenario exists: keep criterion 6 `PARTIAL`.
- No hermetic offline smoke exists: keep criterion 7 `PARTIAL`.
- Dirty worktree exists: record it in review scope so future readers know what state was evaluated.
- Documentation and implementation disagree: record mismatch as a finding. Do not update source docs inside this task without user approval.

## Verification

Minimum plan-completion verification:

```bash
rg -n "^\\| [1-8] \\|.*\\| TBD \\|" docs/superpowers/reviews/2026-06-23-implementation-success-criteria-acceptance-review.md
rg -n "^\\| [1-8] \\|.*\\| UNKNOWN \\|" docs/superpowers/reviews/2026-06-23-implementation-success-criteria-acceptance-review.md
rg -n "^\\| [1-8] \\|.*\\| PASS \\|" docs/superpowers/reviews/2026-06-23-implementation-success-criteria-acceptance-review.md
rg -n "Phase 7|TODO|MacBook|Non-Markdown|External Memory|ask_vault|Ask Project" docs/superpowers/reviews/2026-06-23-implementation-success-criteria-acceptance-review.md
rg -n "[ \t]$" docs/superpowers/reviews/2026-06-23-implementation-success-criteria-acceptance-review.md
git diff --check
```

Expected signals:

- unresolved-verdict greps are manual inspection commands; `TBD` or `UNKNOWN` rows require explicit explanation before finalizing.
- `PASS` rows require a manual PASS Evidence Gate: every `PASS` row must cite at least one current-checkout command with exit status/result in Section 3 plus source/test evidence. Skipped, failed, or environment-blocked evidence cannot support `PASS`.
- future work terms appear only in the excluded-scope or P2 sections.
- trailing-whitespace search returns no matches.
- `git diff --check` reports no whitespace errors.

## Risks And Mitigations

| Risk | Mitigation |
| --- | --- |
| Review becomes a future backlog instead of current acceptance | Keep Future TODO and Phase 7 work in excluded scope or P2 only. |
| PASS is assigned from design intent, not implementation evidence | Start every row as `TBD`; require command/source/test evidence before verdict changes. |
| Reset/rebuild guidance encourages unsafe deletion | Limit deletion evidence to configured Vault Graph state; reject Vault roots and verify Vault file hashes. |
| Multi-vault behavior is accepted without actual-scope proof | Require per-Vault actual scope, Vault-scoped revisions, and no global content-scope union evidence. |
| Context pack criterion ignores boundedness | Require budget/truncation/omission evidence and no full-Vault enumeration. |
| Offline criterion is accepted from normal online tests | Keep criterion 7 `PARTIAL` until network/download-disabled smoke exists. |
| Review edits source/spec docs without approval | Review document only; record mismatches as findings or follow-ups. |

## Validation Review

Before executing this plan, validate the plan itself from these angles:

- Security/read-only: plan writes only a review document and does not authorize Vault mutation.
- Performance/scalability: plan uses targeted commands first and reserves full suite for final validation.
- Testability: every success criterion has concrete command evidence or an explicit evidence gap.
- Maintainability/deep modules: plan preserves application-service boundaries and avoids direct store-coupled recommendations.
- Product/agent ergonomics: review output is structured, short enough to scan, and useful to future agents.

## Open Decisions

No decision is required to execute this implementation plan. The review document may surface these user decisions after evidence is gathered:

- whether to add a future `vg reset-index` command
- what offline acceptance threshold is sufficient before public release

Keep those decisions in the review document until the user approves them. Do not add them to `docs/DECISIONS.md` during this task.
