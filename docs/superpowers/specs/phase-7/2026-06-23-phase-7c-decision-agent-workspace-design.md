# Phase 7C Decision Explorer And Agent Workspace SPEC

Status: Draft for implementation planning

Date: 2026-06-23

Scope: Phase 7C

## 1. Purpose

Phase 7C defines read-only browser views for decision exploration and agent
workspace assembly over existing Vault Graph services.

The user value is focused project understanding. A human should be able to
inspect decisions, open questions, current project memory, context-pack
previews, evidence links, warnings, and durable follow-up suggestions without
asking an LLM to generate unsupported answers and without scanning the whole
Vault manually.

Phase 7C is not `Ask Project`, not `ask_vault`, and not answer synthesis. It is
a visual workspace over evidence-linked projections and generated working
context.

## 2. Relationship To Phase 7A And Future Ask

Local HTTP serving is a future adapter task. This spec defines the 7C view model
and interaction contract so the later adapter can serve it without changing the
application-service boundary.

`Ask Project`, `ask_vault`, answer synthesis, LLM adapter policy, and citation
guarantees move to a future phase. Phase 7C may include a query or goal input
only when the result is one of these existing read-only products:

- filtered decision trace;
- project memory projection;
- open-question projection;
- generated context-pack preview;
- evidence/resource detail.

The UI must not present those products as a synthesized answer.

## 3. User Value

Phase 7C supports three workflows:

1. **Decision Explorer:** inspect durable and candidate decisions, their claim
   status, matched signals, evidence, warnings, related trace context, and
   revisit conditions.
2. **Agent Workspace:** assemble current project memory, open questions,
   constraints, next priorities, and context-pack preview for a concrete task.
3. **Durable follow-up handoff:** identify what should be reviewed or captured
   in Vault later, without publishing or editing Vault content from the UI.

## 4. Success Criteria

Phase 7C is complete when:

- Decision Explorer renders `DecisionMemoryProjection` and decision trace output
  while preserving `claim_status`, `matched_signals`, evidence, warnings,
  Vault IDs, ranks, and freshness;
- Agent Workspace renders `ProjectMemoryProjection`, `OpenQuestionsProjection`,
  and context-pack preview without turning generated context into durable
  knowledge;
- every evidence-backed item links to a read-only resource route or equivalent
  resource URI;
- heading candidates and metadata-derived items are visually distinct from
  stated Vault facts;
- context packs remain canonical JSON with optional Markdown preview only as a
  rendering view;
- the workspace can be cleared by reloading or changing URL/query state; no
  persistent browser workspace store is introduced;
- no UI action writes, publishes, repairs, indexes, or mutates Vault content or
  Vault Graph stores;
- tests cover decision status labels, warning propagation, evidence links,
  multi-Vault grouping, context-pack warning display, and absence of answer
  synthesis.

## 5. In Scope

- Decision Explorer view model and screen contract.
- Agent Workspace view model and screen contract.
- Read-only goal/topic controls that call existing services.
- Project memory, open questions, decision memory, decision trace, and
  context-pack preview rendering.
- Evidence detail panel shared by decision and workspace views.
- Warning and freshness display.
- Durable follow-up suggestion display as text and links, not actions that edit
  Vault.
- Tests for view-model mapping, read-only boundaries, and phase-scope guards.

## 6. Out Of Scope

- Phase 7A local HTTP adapter implementation.
- `Ask Project`, `ask_vault`, generated natural-language answers, or LLM calls.
- Autonomous wiki publication, Vault edits, issue resolution, or decision
  updates.
- Durable context-pack storage, durable workspace storage, or profile memory.
- Decision creation, issue creation, source registration, or raw-source import.
- Hosted collaboration, user accounts, authentication, or remote sharing.
- Full frontend framework adoption unless separately designed.
- Direct storage backend access from UI code.

## 7. Source Contracts

Phase 7C reads existing application-service outputs:

- `ProjectMemoryProjection` from
  `ProjectMemoryService.summarize(requested_scope, limit=10)`;
- `OpenQuestionsProjection` from
  `IssueMemoryService.open_questions(requested_scope, limit=20)`;
- `DecisionMemoryProjection` from
  `DecisionMemoryService.list_decisions(requested_scope, topic=None,
  include_graph=False, limit=20)`;
- decision trace output from `GraphRetrievalService.decision_trace(...)`;
- canonical context pack JSON from `ContextPackBuilder`;
- optional Markdown context preview from `ContextPackRenderer`;
- result explanation records only when already available through the current MCP
  process or a future adapter. Missing explanations must be shown as
  unavailable, not synthesized.

The UI must preserve these fields when present:

- scope: `requested_scope`, `actual_scopes`, Vault IDs, content scopes, and
  `include_cross_vault`;
- memory item: `item_id`, `kind`, `claim_status`, `matched_signals`,
  `document_resource_kinds`, `title`, `summary`, `vault_id`, `path`, `status`,
  `rank`, `evidence`, `warnings`;
- evidence: `vault_id`, `document_id`, `chunk_id`, `path`, `section`, `anchor`,
  `content_hash`, `raw_sha256`, `metadata_index_revision`, `vault_revision`;
- projection: `warnings`, `store_revisions`, `freshness`, `generated_at`;
- context pack: `context_pack_schema_version`, `pack_id`, `goal`, `scope`,
  `vaults`, `store_revisions`, `budget`, `current_state`, `relevant_pages`,
  `relevant_sources`, `decisions`, `constraints`, `open_questions`,
  `warnings`, `evidence`, `generated_at`.

## 8. Decision Explorer View Model

```python
@dataclass(frozen=True)
class DecisionExplorerViewModel:
    requested_scope: dict[str, object]
    actual_scopes: tuple[dict[str, object], ...]
    topic: str | None
    generated_at: str
    vaults: tuple[DecisionVaultView, ...]
    selected_decision: DecisionItemView | None
    trace: DecisionTraceView | None
    warnings: tuple[WarningView, ...]
```

```python
@dataclass(frozen=True)
class DecisionItemView:
    item_id: str
    title: str
    summary: str
    vault_id: str
    path: str
    status: str | None
    rank: int
    claim_status: str
    claim_status_label: str
    matched_signals: tuple[str, ...]
    evidence_links: tuple[EvidenceLinkView, ...]
    warnings: tuple[WarningView, ...]
```

Rules:

- `stated`, `metadata_derived`, and `heading_candidate` must render with
  different labels.
- `heading_candidate` items must show a caution state and their item warnings.
- graph enrichment appears as a matched signal or trace panel, not as a
  replacement for `claim_status`.
- selected decision detail must include evidence chunks, resource links,
  revisions, and warnings.
- empty decisions list must show selected scope and a safe next command such as
  `Run vg index` only when a service warning recommends it.

## 9. Agent Workspace View Model

```python
@dataclass(frozen=True)
class AgentWorkspaceViewModel:
    requested_scope: dict[str, object]
    actual_scopes: tuple[dict[str, object], ...]
    goal: str | None
    generated_at: str
    project_memory: ProjectMemoryPanelView
    open_questions: OpenQuestionsPanelView
    context_pack_preview: ContextPackPreviewView | None
    durable_followups: tuple[DurableFollowupView, ...]
    warnings: tuple[WarningView, ...]
```

Panels:

- **Current State:** `ProjectMemoryVault.current_state`.
- **Decisions:** `ProjectMemoryVault.decisions`.
- **Open Questions:** `ProjectMemoryVault.open_questions` and
  `OpenQuestionsVault.questions`.
- **Constraints:** `ProjectMemoryVault.constraints`.
- **Next Priorities:** `ProjectMemoryVault.next_priorities`.
- **Stale Areas:** `ProjectMemoryVault.stale_areas`.
- **Context Pack Preview:** canonical JSON, optional Markdown rendering view,
  budget warnings, omitted-item warnings, and evidence list.
- **Durable Follow-Ups:** warning-derived suggestions such as missing evidence,
  stale projections, candidate decisions, or unresolved questions.

Durable follow-ups are suggestions only. They must not become buttons that edit
Vault files in Phase 7C.

## 10. Screen Structure

The first implementation should use two tabs or routes:

- `Timeline and Health` is owned by Phase 7B.
- `Decision Explorer` is owned by Phase 7C.
- `Agent Workspace` is owned by Phase 7C.

Decision Explorer layout:

- scope and topic controls;
- decision list grouped by Vault;
- claim-status filters;
- selected decision detail;
- decision trace panel;
- evidence and warnings panel.

Agent Workspace layout:

- scope and task goal controls;
- project memory summary panels;
- open questions panel;
- context-pack preview panel;
- evidence drawer;
- warning and durable follow-up strip.

Do not add a landing page, marketing content, chat UI, or answer composer.

## 11. Controls

Shared controls:

- active Vault by default;
- explicit Vault ID selector;
- all-Vault selector only when explicitly chosen;
- content-scope selector only if supported by the service contract;
- refresh button that reloads view data only.

Decision Explorer controls:

- optional topic filter;
- optional `include_graph` toggle for decision trace enrichment only when graph
  status is available;
- claim-status filters: stated, metadata-derived, heading candidate.

Agent Workspace controls:

- optional task goal for context-pack preview;
- max-token selector for context-pack preview if the existing builder supports
  it;
- JSON/Markdown preview toggle for the same context pack.

Forbidden controls:

- `Ask Project`;
- `Run index`;
- `Publish to Vault`;
- `Create decision`;
- `Resolve issue`;
- `Edit context pack`;
- `Save workspace`;
- remote backend migration or repair.

## 12. Data Flow

```text
Decision Explorer
  -> read scope/topic controls
  -> call decision memory service and optional decision trace provider
  -> map payloads to DecisionExplorerViewModel
  -> render grouped decisions, trace, evidence, warnings

Agent Workspace
  -> read scope/goal controls
  -> call project memory and open-question services
  -> optionally call context-pack builder for a generated preview
  -> map payloads to AgentWorkspaceViewModel
  -> render panels, context preview, evidence, warnings, follow-up suggestions
```

The future HTTP adapter may wrap these calls. The view contract must not depend
on HTTP-specific request objects, JavaScript framework state, or direct backend
imports.

## 13. Context-Pack Preview Policy

Context-pack preview is allowed because context packs are already generated
working context.

Rules:

- JSON is canonical.
- Markdown is a rendering view only.
- pack warnings, budget, omitted items, evidence, and generated timestamp must
  be visible.
- preview is regenerated on demand and is not durable.
- copying text to clipboard is a client-side convenience; it does not write
  Vault content.
- no "save pack" or "publish pack" action exists in Phase 7C.

## 14. Durable Follow-Up Policy

The UI may show follow-up suggestions derived from existing warnings and memory
items:

- stale projection: run `vg index` outside the UI;
- missing evidence: inspect source documents or improve Vault notes outside the
  UI;
- candidate decision: review and formalize in Vault through the normal workflow;
- unresolved question: use Vault's existing issue/follow-up workflow.

Follow-ups are text guidance and read-only links only. They are not commands
that mutate Vault or Vault Graph state.

## 15. Multi-Vault Policy

- Group decisions, memory panels, questions, and context-pack evidence by
  `vault_id`.
- Never merge decisions or issues by title across Vaults.
- All all-Vault views must display selected Vault IDs.
- `include_cross_vault` remains false unless an existing graph/context service
  explicitly supports it and the user opts in.
- Evidence links always show `vault_id`, path, and resource kind.

## 16. Warning And Error Policy

- Top-level warnings render in the workspace warning strip.
- Vault-level warnings render in the affected Vault group.
- Item warnings render beside the item and in the detail panel.
- `candidate_decision`, `candidate_open_question`, and
  `missing_issue_status` warnings must be visually distinct.
- Metadata unavailable is blocking for memory panels.
- Graph unavailable disables graph enrichment but does not block non-graph
  decision memory.
- Context-pack warning categories must not be hidden behind the preview toggle.

## 17. Security And Read-Only Boundary

- UI modules must not write Vault files, Vault Graph stores, browser-persisted
  durable memory, or remote services.
- Resource links must resolve through existing read-only routes or resource URI
  contracts.
- Raw file paths from payloads are display data, not paths to open directly.
- No external LLM calls are allowed in Phase 7C.
- No prompt injection handling is needed for generated answers because no
  answers are generated; evidence text should still be rendered as untrusted
  content.

## 18. Performance

- Use service limits instead of full-Vault browser scans.
- Default memory limit remains service defaults: project memory `10`, open
  questions `20`, decisions `20` unless implementation planning changes the
  call explicitly.
- Context-pack preview should use the existing context budget and warnings.
- Do not run graph traces for every decision automatically; run trace only for
  a selected topic or selected decision.
- Do not poll automatically.

## 19. Accessibility And Usability

- Claim status, warnings, and freshness must use text labels, not color alone.
- Evidence links need readable path, Vault ID, and resource kind.
- Decision and workspace panels must be keyboard navigable.
- Long evidence snippets should be collapsible without hiding warning counts.
- Generated context preview must clearly label JSON as canonical and Markdown
  as a rendering view.

## 20. Files For Later Implementation

Suggested implementation files:

```text
src/vault_graph/ui/decision_agent_view_model.py
src/vault_graph/ui/static/decision-explorer.html
src/vault_graph/ui/static/agent-workspace.html
src/vault_graph/ui/static/decision-agent.css
src/vault_graph/ui/static/decision-agent.js
tests/test_ui_decision_explorer_view_model.py
tests/test_ui_agent_workspace_view_model.py
tests/test_ui_decision_agent_read_only_boundary.py
```

If the future Phase 7A HTTP adapter chooses a different static asset structure,
keep the view-model boundaries and tests while adapting transport-specific
files.

## 21. Verification

Implementation must pass:

```bash
uv run --python 3.12 ruff check src tests
uv run --python 3.12 mypy src tests
uv run --python 3.12 pytest -q
```

Focused tests should prove:

- stated, metadata-derived, and heading-candidate decisions are visually
  distinguishable in the view model;
- decision and issue warnings are preserved at the correct level;
- project memory panels group by Vault ID and never merge same-title items
  across Vaults;
- context-pack preview preserves canonical JSON, warnings, budget, evidence,
  and generated timestamp;
- graph unavailable disables graph trace enrichment without hiding non-graph
  decision evidence;
- no UI route or view-model action invokes Vault writes, indexing, publication,
  or answer synthesis.

## 22. Review Notes

- Security/read-only: no mutation controls, no LLM calls, no direct backend
  access.
- Performance: bounded service calls and selected-decision graph trace keep the
  screen scalable.
- Testability: view-model mapping can be tested from existing Phase 6B/4 DTO
  fixtures.
- Maintainability: Decision Explorer and Agent Workspace reuse existing service
  contracts instead of introducing a new workspace data model.

## 23. Open Decisions

None for Phase 7C detailed design. Future phases must separately decide local
HTTP serving, persistent workspace state, frontend framework adoption, and
answer synthesis policy.
