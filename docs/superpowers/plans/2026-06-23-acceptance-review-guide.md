# Acceptance Review Guide Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Produce a structured Acceptance Review document that evaluates the current implemented Vault Graph scope against `docs/SPEC.md` Success Criteria.

**Architecture:** Treat the review as an evidence ledger, not a new feature plan. The review maps product-level success criteria to current docs, code, tests, CLI/MCP behavior, and verification commands while keeping future TODO work out of scope.

**Tech Stack:** Markdown, Git metadata, Python 3.12, pytest, ruff, mypy, existing Vault Graph CLI/tests.

---

## Source Documents

Read these before writing the Acceptance Review:

- `AGENTS.md`
- `docs/SPEC.md`
- `docs/FEATURES.md`
- `docs/DESIGN.md`
- `docs/CONVENTIONS.md`
- `docs/DECISIONS.md`
- `docs/PATCH_LOG.md`
- relevant phase specs for the criteria being evaluated, especially Phase 4,
  Phase 5, and Phase 6 contracts when context packs, MCP, or memory/explorer
  projections are used as evidence
- targeted current modules and tests needed to substantiate each success
  criterion

Use `docs/SPEC.md` section `20. Success Criteria` as the authority. Do not use
the Future TODO sections as the next implementation backlog for this review.
Use `rg` and named test files first. Broader source or test scans are acceptable
only when targeted evidence is missing.

## Output Document

Create:

- `docs/superpowers/reviews/2026-06-23-implementation-success-criteria-acceptance-review.md`

Recommended title:

```markdown
# Vault Graph Implementation Success Criteria Acceptance Review
```

This `reviews` directory is intentionally separate from `specs` and `plans`:

- `specs` define desired behavior.
- `plans` define how to build behavior.
- `reviews` record whether implemented behavior satisfies accepted criteria.

Do not update `docs/DECISIONS.md` unless the user explicitly approves a decision
after reading the review. Do not update `docs/PATCH_LOG.md` unless the review
forces a correction to an existing spec, plan, or implementation.

## Scope

The Acceptance Review evaluates the current implemented product surface:

- Phase 1: Vault catalog, reader, metadata store
- Phase 2: local vector indexing and keyword/vector search
- Phase 3: entity/relationship graph, `vg related`, graph retrieval, decision trace
- Phase 4: context pack contract and CLI context pack assembly
- Phase 5: MCP server, resources, tools, and prompts
- Phase 6: result explanation, project/decision/issue memory, timeline/health explorer services

Explicitly exclude:

- Phase 7B/7C UI implementation, because the accepted decision is to defer it.
- Phase 7A local HTTP serving, because it is future work.
- `Ask Project`, `ask_vault`, answer synthesis, LLM adapter policy, and citation
  guarantees, because they are future work.
- MacBook acceleration, non-Markdown readers, chunking migrations, and external
  memory adapters, because they are TODO guidance, not current acceptance scope.

## Verdict Rubric

Use these verdicts consistently:

- `PASS`: implemented behavior is covered by current code and verification
  evidence, with no known product-impacting gap.
- `PARTIAL`: the core behavior exists, but user-facing flow, end-to-end
  acceptance evidence, or operational documentation is incomplete.
- `GAP`: the criterion is not currently satisfied.
- `NOT IN CURRENT SCOPE`: the criterion or sub-feature is explicitly future work
  and should not block current acceptance.
- `UNKNOWN`: evidence was not collected; avoid this in the final review unless
  a command cannot be run.

Rules:

- Do not mark `PASS` from design documents alone.
- Do not mark `PASS` from a unit test if the criterion is user-facing and no
  CLI/MCP/service acceptance path exists.
- Prefer `PARTIAL` when the architecture supports a criterion but the review
  lacks a reproducible acceptance scenario.
- Every `GAP` or `PARTIAL` must include a recommended next action.

## Acceptance Review Structure

Write the review with this structure:

```markdown
# Vault Graph Implementation Success Criteria Acceptance Review

Status: Draft
Date: 2026-06-23
Reviewer: Codex
Branch: <branch>
Commit: <short-sha>

## 1. Executive Summary

| Verdict | Count |
| --- | ---: |
| PASS | N |
| PARTIAL | N |
| GAP | N |
| NOT IN CURRENT SCOPE | N |
| UNKNOWN | N |

Short conclusion in 3-6 bullets.

## 2. Review Scope

Included phases and explicitly excluded future work.

## 3. Verification Commands

Commands run, exact result, and whether output was captured from the current
checkout.

## 4. Success Criteria Matrix

One row per `docs/SPEC.md` success criterion.

## 5. Detailed Findings

One subsection per criterion with evidence, risks, and next action.

## 6. Multi-Angle Review

Security/read-only, performance/scalability, testability, maintainability,
agent ergonomics, and documentation consistency.

## 7. Open Decisions

Only decisions that require user judgment.

## 8. Recommended Next Actions

Prioritized list: P0 acceptance blockers, P1 hardening, P2 future improvements.
```

## Success Criteria Matrix Template

Use this table in section 4:

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

## Evidence Requirements By Criterion

### 1. Point At Vault And Build Index Without Mutating Vault

Required evidence:

- CLI supports `vg init` and `vg index`.
- Indexing writes only to Vault Graph state paths.
- Read-only boundary tests cover Vault files.
- At least one CLI or integration test indexes a real temporary Vault fixture.

Recommended commands:

```bash
uv run --python 3.12 pytest tests/test_cli_catalog_metadata.py tests/test_metadata_indexer.py tests/test_read_only_boundary.py tests/test_vector_indexing_read_only_boundary.py tests/test_graph_indexing_read_only_boundary.py -q
```

Expected review bias:

- `PASS` if current tests and CLI code prove index writes stay outside Vault.
- `PARTIAL` if only lower-level tests pass and no user-facing CLI fixture exists.

### 2. Multi-Vault Registration And Explicit Indexing

Required evidence:

- `vg vault add`, `vg vault list`, `vg index --vault-id`, and
  `vg index --all-vaults` exist.
- Scope conflict handling rejects `--vault-id` with `--all-vaults`.
- Actual query scopes are explicit and Vault IDs are visible in output.
- `--all-vaults` expands to explicit enabled `vault_id`s before application
  services run.
- Each Vault is indexed or queried through its own actual scope; a hidden global
  all-Vault content-scope union is not acceptable evidence.
- Disabled Vaults and narrower configured content scopes are not widened.
- Store revisions and warnings are keyed by Vault and actual scope.
- `--vault-id` partial indexing does not mark unrelated Vault scopes stale.

Recommended commands:

```bash
uv run --python 3.12 pytest tests/test_vault_catalog.py tests/test_cli_catalog_metadata.py tests/test_query_scope_resolution.py tests/test_multi_vault_search.py tests/test_cli_context.py -q
```

Expected review bias:

- `PASS` when single-Vault and all-Vault CLI paths are covered.

### 3. Same Relative Path Does Not Collide

Required evidence:

- Metadata identity includes `vault_id`.
- Vector, graph, MCP, and context-pack output preserve `vault_id`.
- Tests include two Vaults with the same relative path.
- Per-Vault actual scopes and evidence identities are preserved in output.
- If there is no direct MCP same-relative-path collision test, the criterion
  must remain `PARTIAL` or record a P1 acceptance-test gap.

Recommended commands:

```bash
uv run --python 3.12 pytest tests/test_multi_vault_identity.py tests/test_multi_vault_search.py tests/test_multi_vault_graph_identity.py tests/test_multi_vault_graph_indexing.py tests/test_multi_vault_graph_retrieval.py tests/test_cli_context.py::test_cli_context_all_vaults_uses_real_retrieval_and_preserves_evidence_vault_ids -q
```

Expected review bias:

- `PASS` only if each surface named in the criterion is covered or the review
  clearly maps existing tests to that surface.
- `PARTIAL` if one named surface, such as MCP or context-pack, lacks direct
  collision evidence.

### 4. Agent Context Pack Instead Of Whole Vault

Required evidence:

- `vg context "goal"` exists.
- `build_context_pack` MCP tool exists.
- Context pack output includes bounded goal, evidence, warnings, budgets,
  revisions, and selected Vault identity.
- Context pack builder does not read or emit the whole Vault by default.
- Evidence proves context packs are bounded: retrieval limits, token budgets,
  evidence budgets, excerpt truncation, and omission warnings are exercised.
- At least one fixture contains irrelevant documents or over-budget evidence and
  proves the output excludes or warns instead of dumping every document.
- CLI and MCP context surfaces call `ContextPackBuilder` over retrieval results;
  they must not enumerate Vault files or MCP resources directly.

Recommended commands:

```bash
uv run --python 3.12 pytest tests/test_context_pack_builder.py tests/test_context_pack_evidence_budget.py tests/test_context_pack_warnings.py tests/test_cli_context.py tests/test_mcp_tools.py::test_build_context_pack_renders_and_caches_pack_json tests/test_context_pack_read_only_boundary.py -q
```

Expected review bias:

- `PASS` if CLI and MCP both use the service-backed context pack boundary.

### 5. Decision Trace Evidence And Stated/Inferred Distinction

Required evidence:

- `vg decision-trace TOPIC` exists.
- MCP `get_decision_trace` exists.
- Decision trace steps include evidence references.
- Relationship status is visible and distinguishes stated/inferred or reports
  `not_applicable` for initial decision resolution.
- Topic fallback warns when no durable decision entity exists.

Recommended commands:

```bash
uv run --python 3.12 pytest tests/test_graph_retrieval_service.py tests/test_cli_decision_trace.py tests/test_mcp_tools.py::test_decision_trace_opens_graph_service_after_validation -q
```

Expected review bias:

- `PASS` if evidence and relationship status are visible in both service and
  CLI/MCP payloads.

### 6. Delete And Rebuild All Indexes From Vault

Required evidence:

- Derived state lives outside Vault roots.
- Fresh state indexing rebuilds metadata, vector, keyword, graph, and projection
  data from Vault-derived inputs.
- Full rebuild or state deletion scenario is documented or tested.
- Any deletion scenario targets only the configured Vault Graph state path or a
  fixture-owned derived-state namespace.
- Deletion/rebuild scenarios must reject registered Vault roots and Vault
  `raw/`, `wiki/`, `docs/`, and `scratch/` paths as deletion targets.
- Vault file hashes are captured before and after reset/rebuild acceptance
  scenarios and must remain unchanged.
- Prefer a bounded fixture and scope-local rebuild first: delete derived state
  for one Vault namespace, rebuild with `vg index --vault-id`, then verify
  metadata, keyword, vector, and graph surfaces. Reserve `--all-vaults` rebuild
  for bounded fixtures or deliberate scale tests with recorded counts and
  duration.

Recommended commands:

```bash
uv run --python 3.12 pytest tests/test_cli_catalog_metadata.py::test_cli_index_accepts_full_option tests/test_index_service_vector_reconcile.py tests/test_index_service_graph_reconcile.py -q
```

Expected review bias:

- Mark `PARTIAL` unless the review finds a supported user-facing reset/delete
  flow or a documented acceptance scenario that deletes Vault Graph state and
  rebuilds it from Vault.
- Do not invent a reset command inside this review. If needed, record an Open
  Decision asking whether to add `vg reset-index` or keep state-directory
  deletion as the accepted local workflow.

### 7. Local-First Offline Operation

Required evidence:

- Search-time query embedding uses local-only/no-download mode.
- Missing model artifacts degrade or fail with visible warnings rather than
  hidden downloads in read-only paths.
- Core tests do not require network by default.
- An explicit offline acceptance scenario exists or is proposed.
- The offline scenario disables or fakes network/download paths. A normal
  online test run is not enough evidence for "without internet access."
- No hosted service, implicit model download, or remote MCP/HTTP dependency is
  required for the acceptance path.

Recommended commands:

```bash
uv run --python 3.12 pytest tests/test_fastembed_text_embeddings.py tests/test_app_search_readiness_service.py tests/test_retrieval_service_search.py tests/test_search_read_only_boundary.py -q
```

Expected review bias:

- Mark `PARTIAL` if code has local-only boundaries but no hermetic offline
  acceptance scenario was run.
- Recommended next action should be a deterministic offline smoke test, not a
  hosted dependency or broad infrastructure change.

### 8. Retrieval Output Does Not Bypass Vault Publication Workflow

Required evidence:

- Search, graph, context-pack, memory, and MCP outputs are read-only projections.
- Prompts/tools tell agents to route durable changes through Vault workflow.
- No retrieval command writes Vault files or publishes wiki pages.
- Read-only tests cover CLI/MCP/context-pack/graph retrieval paths.

Recommended commands:

```bash
uv run --python 3.12 pytest tests/test_search_read_only_boundary.py tests/test_graph_retrieval_read_only_boundary.py tests/test_context_pack_read_only_boundary.py tests/test_mcp_tool_read_only_boundary.py tests/test_mcp_resource_read_only_boundary.py tests/test_mcp_prompts.py -q
```

Expected review bias:

- `PASS` if commands and prompts preserve the Vault publication boundary.

## Required Verification Commands

Use a tiered gate. Run focused criterion commands while gathering evidence. Run
the full suite once before publishing the final review. Re-run only affected
checks after Markdown-only edits unless code or tests changed.

Run these before finalizing the review:

```bash
git status --short --branch
git rev-parse --short HEAD
uv run --python 3.12 ruff check src tests
uv run --python 3.12 mypy src tests
uv run --python 3.12 pytest
```

MCP stdio smoke is gated and skipped by default. For MCP transport acceptance,
run it explicitly or record the skip as an evidence gap:

```bash
VG_RUN_MCP_STDIO_SMOKE=1 uv run --python 3.12 pytest tests/test_mcp_stdio_smoke.py -q
```

Record the exact result in the review. If a command cannot run, record:

- command
- failure reason
- whether failure is environment-related or product-related
- whether the missing evidence changes any verdict

## Multi-Angle Review Requirements

After drafting the Acceptance Review, validate it from these angles:

### Security / Read-Only Safety

Check:

- No review recommendation implies Vault writes through Vault Graph.
- Any reset/delete recommendation is limited to Vault Graph derived state.
- Paths and command examples do not encourage deleting registered Vault roots.
- MCP and future HTTP surfaces remain local/read-only in the acceptance framing.

### Performance / Scalability

Check:

- Review does not require full-Vault dumps as a normal acceptance path.
- Multi-Vault checks preserve `QueryScope` and explicit Vault IDs.
- Recommended acceptance scenarios use bounded fixtures unless deliberately
  testing scale.
- Any rebuild/reset recommendation acknowledges derived state can be rebuilt
  scope-locally when possible.

### Testability / CI

Check:

- Each criterion has at least one reproducible command.
- Commands are specific enough for a future agent to rerun.
- `PARTIAL` criteria identify the missing acceptance test or fixture.
- The review distinguishes unit/contract coverage from end-to-end acceptance.

### Maintainability / Deep Modules

Check:

- Recommendations do not couple CLI directly to SQLite, Chroma, or graph internals.
- Any proposed new command would call application services, not stores directly.
- The review does not create a new durable knowledge source or hidden memory layer.
- Terminology follows current project language: `vault_id`, `QueryScope`,
  evidence chunks, derived projections, actual scopes, context packs.

### Product / Agent Ergonomics

Check:

- A human can understand what currently works in under one page.
- Agents can find concrete evidence and next commands without scanning the whole
  repository.
- Open Decisions are few, important, and phrased with a recommendation.
- Future TODO items are not mixed into current acceptance blockers.

### Documentation Consistency

Check:

- `SPEC.md`, `FEATURES.md`, and `DESIGN.md` are treated as source context, not
  proof of implementation.
- Any mismatch found between docs and implementation is called out.
- `PATCH_LOG.md` is used only if an existing document must be corrected because
  of the review.
- `DECISIONS.md` is used only after user approval.

### Phase 6 Projection Coverage

Check:

- Result explanation, project memory, decision memory, issue/open-question
  memory, timeline memory, health explorer, and MCP memory resources/tools are
  either included as supporting evidence or explicitly marked as not required by
  a particular success criterion.
- Phase 6 projections remain read-only working context, not a durable memory
  database.
- The review does not treat Phase 6 output as answer synthesis or as a
  replacement for Vault publication.

Recommended command:

```bash
uv run --python 3.12 pytest tests/test_result_explanation.py tests/test_mcp_explain_result.py tests/test_project_memory_service.py tests/test_decision_memory_service.py tests/test_issue_memory_service.py tests/test_timeline_memory_service.py tests/test_health_explorer_service.py tests/test_mcp_memory_tools.py tests/test_mcp_recent_changes_tool.py tests/test_mcp_current_context_resource.py tests/test_mcp_timeline_resource.py -q
```

## Open Decisions To Consider

Include these only if the evidence supports them. Keep them in the review under
`Open Decisions`; do not add them to `docs/DECISIONS.md` without approval.

### Decision Candidate 1: Index Reset UX

Context:

`docs/SPEC.md` says all indexes can be deleted and rebuilt from Vault. Current
acceptance must decide whether that requires a user-facing command or whether a
documented derived-state deletion workflow is enough before public release.

Options:

- Option A: document and test deletion of configured Vault Graph derived state,
  followed by `vg index`.
  - Pros: smallest surface, avoids adding a destructive command too early.
  - Cons: less guided for users.
- Option B: add a future `vg reset-index` command that deletes only derived
  Vault Graph state after path-safety checks.
  - Pros: safer guided UX.
  - Cons: expands CLI with a destructive operation and requires careful safety
    design.

Trade-offs:

Option A is simpler and enough for pre-release acceptance if the rebuild test is
strong. Option B may be better before public release if users need a safer
workflow.

Recommendation:

Prefer Option A now. Add `vg reset-index` only if the Acceptance Review shows a
real user-facing gap.

Question:

Should Vault Graph add an explicit user-facing command such as `vg reset-index`
for deleting derived index state, or is documented state-directory deletion plus
`vg index` enough before public release?

### Decision Candidate 2: Offline Acceptance Threshold

Context:

`docs/SPEC.md` requires local-first offline operation. The current code has
local-only search-time boundaries, but acceptance needs a reproducible threshold.

Options:

- Option A: require a deterministic offline smoke test with network/download
  paths disabled or faked.
  - Pros: CI-friendly and directly proves the boundary.
  - Cons: may use fakes rather than a real cached model.
- Option B: require a real cached model artifact and OS-level network blocking.
  - Pros: closer to a real laptop scenario.
  - Cons: less reliable in CI and more environment-dependent.

Trade-offs:

Option A is the simplest stable acceptance threshold. Option B can be added as a
manual release check later.

Recommendation:

Prefer Option A now.

Question:

What counts as sufficient proof of local-first offline behavior?

## Task Checklist

### Task 1: Create The Review Directory And Draft Document

**Files:**

- Create: `docs/superpowers/reviews/2026-06-23-implementation-success-criteria-acceptance-review.md`

- [ ] Create the `docs/superpowers/reviews/` directory if it does not exist.
- [ ] Add the review header, scope, and verdict rubric.
- [ ] Copy the eight `docs/SPEC.md` Success Criteria exactly into the matrix.
- [ ] Fill initial verdicts using only evidence gathered from current code,
      tests, and commands.

### Task 2: Gather Evidence

**Files:**

- Modify: `docs/superpowers/reviews/2026-06-23-implementation-success-criteria-acceptance-review.md`

- [ ] Run the required verification commands.
- [ ] Run focused command groups for each criterion where needed.
- [ ] Record test names, source paths, and command results.
- [ ] Mark weak areas as `PARTIAL`, not `PASS`.

### Task 3: Add Detailed Findings

**Files:**

- Modify: `docs/superpowers/reviews/2026-06-23-implementation-success-criteria-acceptance-review.md`

- [ ] Add one subsection per success criterion.
- [ ] For each subsection include `Verdict`, `Evidence`, `Risk`, and
      `Recommended Next Action`.
- [ ] Keep each finding short enough to scan.
- [ ] Do not paste long command output; summarize the meaningful result.

### Task 4: Run Multi-Angle Review

**Files:**

- Modify: `docs/superpowers/reviews/2026-06-23-implementation-success-criteria-acceptance-review.md`

- [ ] Dispatch or perform named reviews for security/read-only safety,
      performance/scalability, testability/CI, maintainability/deep modules,
      product/agent ergonomics, and documentation consistency.
- [ ] Apply corrections to the Acceptance Review document only when they are
      aligned with Vault Graph values.
- [ ] Record source, spec, or code mismatches as findings, patch-log candidates,
      or separately approved follow-up work. Do not edit code, specs, or Vault
      content as part of the Acceptance Review unless the user explicitly asks.
- [ ] Record only unresolved user-choice items under `Open Decisions`.

### Task 5: Finalize

**Files:**

- Modify: `docs/superpowers/reviews/2026-06-23-implementation-success-criteria-acceptance-review.md`

- [ ] Re-run `git diff --check`.
- [ ] Re-run any verification commands affected by edits.
- [ ] Ensure the final review does not treat future TODO work as current
      implementation scope.
- [ ] Summarize next actions as P0/P1/P2.

## Initial Verdict Discipline

Start every matrix row as `TBD`. Change a row to `PASS`, `PARTIAL`, or `GAP`
only after recording current-checkout evidence. The table below is not a verdict
table; it is a risk prompt for the reviewer.

| # | Criterion | Review Bias After Evidence |
| ---: | --- | --- |
| 1 | Point at Vault and build index without mutating Vault | likely `PASS` only after CLI and read-only evidence |
| 2 | Register multiple Vaults and index one or all explicitly | likely `PASS` only after successful `--vault-id`, `--all-vaults`, and actual-scope evidence |
| 3 | Same relative path does not collide across surfaces | `PASS` or `PARTIAL` depending on MCP/context-pack collision evidence |
| 4 | Agent can request context pack for concrete task | likely `PASS` only after bounded-context evidence |
| 5 | Decision traces include evidence and distinguish stated/inferred | likely `PASS` after service, CLI, and MCP evidence |
| 6 | All indexes can be deleted and rebuilt from Vault | `PARTIAL` until reset/delete acceptance evidence exists |
| 7 | Local-first operation works without internet access | `PARTIAL` until offline smoke evidence exists |
| 8 | Retrieval output never bypasses Vault publication workflow | likely `PASS` only after CLI/MCP prompts, tools, and sample outputs prove durable changes route through Vault workflow |

## Final Output Expectations

The completed Acceptance Review should make these questions easy to answer:

- What does Vault Graph currently satisfy?
- Which success criteria are only partially proven?
- Which gaps are acceptance-test gaps versus product implementation gaps?
- Which next actions are required before moving to any future TODO work?
- Which items genuinely require user approval?
