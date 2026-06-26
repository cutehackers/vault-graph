# Evidence-First Ask And Reasoning Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `vg ask` and MCP `ask_vault(...)` so users and agents can receive concise, evidence-linked answers over indexed Vault knowledge.

**Architecture:** Add a new MCP-free `vault_graph.answer` deep module for answer DTOs, evidence planning, extractive composition, citation validation, and rendering. Keep orchestration in `vault_graph.app.answer_service`; keep CLI and MCP as thin adapters over the same `AnswerService`; reuse existing search, graph, memory, explanation, and scope services without adding writable memory, answer storage, or direct store access.

**Tech Stack:** Python 3.12, frozen dataclasses, Protocol-based service boundaries, existing `RetrievalService`, `GraphRetrievalService`, Phase 6 memory services, Typer CLI, FastMCP tool registration, pytest, ruff, mypy.

---

## Source Documents

Read these before implementation:

- `AGENTS.md`
- `docs/SPEC.md`
- `docs/FEATURES.md`
- `docs/DESIGN.md`
- `docs/DECISIONS.md`
- `docs/CONVENTIONS.md`
- `docs/superpowers/specs/2026-06-25-evidence-first-ask-and-reasoning-design.md`
- `docs/superpowers/specs/2026-06-24-cli-todo-command-implementation-design.md`
- `docs/superpowers/specs/2026-06-09-phase-2c-evidence-first-keyword-vector-search-design.md`
- `docs/superpowers/specs/phase-3/2026-06-10-phase-3c-graph-projection-retrieval-design.md`
- `docs/superpowers/specs/phase-4/2026-06-12-phase-4b-local-context-pack-assembly-rendering-design.md`
- `docs/superpowers/specs/phase-5/2026-06-15-phase-5c-mcp-tools-prompts-agent-workflows-design.md`
- `docs/superpowers/specs/phase-6/2026-06-18-phase-6-memory-and-explorer-views-overview-design.md`

Repo context inspected for this plan:

- `src/vault_graph/cli/main.py` already owns Typer commands and read-only construction helpers for search, graph, and context.
- `src/vault_graph/retrieval/retrieval_service.py` returns evidence-linked `SearchResponse` over resolved metadata evidence.
- `src/vault_graph/app/graph_retrieval_service.py` exposes `decision_trace(...)` and related graph evidence through app-level services.
- `src/vault_graph/memory/*` exposes read-only project, decision, issue, timeline, and explanation projections.
- `src/vault_graph/mcp/mcp_tools.py` already registers service-backed tools through `McpToolRegistry`.
- `src/vault_graph/mcp/mcp_service_factory.py` opens read-only services lazily and avoids eager backend imports.
- Existing tests validate CLI, MCP, read-only boundaries, import boundaries, multi-vault identity, and explanation cache behavior.

## Scope

Implement the Ask and Reasoning layer:

- Add `AnswerError`.
- Add `vault_graph.answer` DTOs and validation.
- Add deterministic `EvidencePlanner` over existing services.
- Add deterministic `ExtractiveAnswerComposer`.
- Add `CitationGuard`.
- Add text and JSON rendering for `AnswerResponse`.
- Add `AnswerService.ask(...)`.
- Add `vg ask`.
- Add MCP `ask_vault(...)`.
- Register answer evidence in the existing in-process `ResultExplanationCache` for MCP.
- Add unit, integration, CLI, MCP, import-boundary, multi-vault, and read-only tests.

## Non-Goals

Do not implement:

- hosted LLM calls
- automatic model downloads during ask
- answer persistence, `data/answers/`, answer history, or answer database tables
- writable memory APIs, hidden episode logs, profile/preference/procedural memory, Mem0, MemMachine, or external memory dependencies
- Vault file edits, publication, validation, renames, rewrites, or deletes
- indexing, schema creation, Chroma collection creation, or graph projection cache writes during ask
- HTTP or UI surfaces
- cross-Vault entity merging
- automatic contradiction resolution
- durable context-pack persistence during ask

## Directory And File Structure

Create:

- `src/vault_graph/answer/__init__.py`: lazy public exports for answer DTOs and services without importing CLI, MCP, local stores, Chroma, rustworkx, or FastMCP.
- `src/vault_graph/answer/answer_response.py`: answer response DTOs, answer status vocabularies, and validation helpers.
- `src/vault_graph/answer/answer_plan.py`: `AnswerRequest`, `EvidencePlanStep`, `AnswerPlan`, `PlannedEvidence`, request validation, and stable answer ID helper.
- `src/vault_graph/answer/evidence_planner.py`: Protocols for injected retrieval/graph/memory services, evidence planning, evidence normalization, budget enforcement, and warning conversion.
- `src/vault_graph/answer/answer_composer.py`: `AnswerComposer` Protocol and deterministic `ExtractiveAnswerComposer`.
- `src/vault_graph/answer/citation_guard.py`: final `AnswerResponse` validation and downgrade policy.
- `src/vault_graph/answer/answer_renderer.py`: text and canonical JSON rendering.
- `src/vault_graph/app/answer_service.py`: shared application boundary for CLI, MCP, and future HTTP.
- `src/vault_graph/mcp/mcp_answer_serialization.py`: MCP payload, links, warnings, and explanation records for answers.
- `tests/test_answer_response_contract.py`
- `tests/test_answer_plan_contract.py`
- `tests/test_evidence_planner.py`
- `tests/test_answer_composer.py`
- `tests/test_citation_guard.py`
- `tests/test_answer_renderer.py`
- `tests/test_answer_service.py`
- `tests/test_answer_read_only_boundary.py`
- `tests/test_answer_multi_vault.py`
- `tests/test_answer_import_boundaries.py`
- `tests/test_cli_ask.py`
- `tests/test_mcp_ask_vault.py`

Modify:

- `src/vault_graph/errors.py`: add `AnswerError`.
- `src/vault_graph/cli/main.py`: import answer service/rendering, add `_answer_service(...)`, add Typer `ask` command, add CLI validation.
- `src/vault_graph/mcp/__init__.py`: only if new answer serialization exports are needed; preserve lazy import behavior.
- `src/vault_graph/mcp/mcp_service_factory.py`: add `open_answer_service(include_graph: bool = False) -> AnswerService`.
- `src/vault_graph/mcp/mcp_tools.py`: add `ask_vault` tool name, input DTO, parser, registry method, and FastMCP registration.
- `src/vault_graph/mcp/mcp_tool_serialization.py`: no answer logic; keep shared lower-level helpers if needed.
- `tests/test_cli_surface_boundary.py`: update expected command surface.
- `tests/test_mcp_import_boundaries.py`: add answer package and answer service factory import checks.
- `tests/test_mcp_server.py`, `tests/test_mcp_stdio_smoke.py`, `tests/test_mcp_tool_read_only_boundary.py`, `tests/test_mcp_tools.py`: update tool registration and read-only expectations.

Do not create:

- `src/vault_graph/answer/llm_client.py`
- `src/vault_graph/answer/answer_store.py`
- `src/vault_graph/answer/memory_store.py`
- `src/vault_graph/answer/utils.py`
- `src/vault_graph/answer/helpers.py`
- `data/answers/`
- `data/memory/`

## Component And Interface Spec

### `src/vault_graph/errors.py`

Add:

```python
class AnswerError(VaultGraphError):
    """Raised when answer planning, composition, or validation cannot safely complete."""
```

Use `AnswerError` for MCP-free answer contract failures. CLI should route it through `_exit_on_domain_error(...)`; MCP should map it through existing MCP error mapping or a focused answer mapping in `mcp_answer_serialization.py`.

### `src/vault_graph/answer/answer_response.py`

Add the exact status vocabularies from the SPEC:

```python
AnswerMode = Literal["evidence-first"]
AnswerStatus = Literal["supported", "partial", "insufficient_evidence"]
AnswerClaimStatus = Literal[
    "supported",
    "inferred",
    "partial",
    "unsupported",
    "missing",
    "contested",
    "stale",
    "deprecated",
]
AnswerWarningSeverity = Literal["info", "warning", "error"]
AnswerEvidenceSourceKind = Literal[
    "search_result",
    "graph_related",
    "decision_trace",
    "context_pack",
    "project_memory",
    "open_question",
    "recent_change",
]
```

Add frozen dataclasses:

- `AnswerSignal`
- `AnswerEvidence`
- `AnswerClaim`
- `AnswerWarning`
- `AnswerReasoningStep`
- `AnswerDraft`
- `AnswerResponse`

Validation requirements:

- All tuple fields must be immutable tuples.
- `AnswerResponse.actual_scopes` must be non-empty.
- `AnswerResponse.evidence` must have unique `evidence_id` values.
- `AnswerResponse.claims` must have unique `claim_id` values.
- All claim evidence references must exist in `AnswerResponse.evidence`.
- Claims with status `supported`, `inferred`, `partial`, `contested`, `stale`, or `deprecated` must have at least one evidence ID.
- Claims with status `unsupported` or `missing` may omit evidence but must remain visibly labeled.
- `answer_status="supported"` requires at least one supported claim and no top-level `error` warning.
- `answer_status="insufficient_evidence"` may have no evidence.

### `src/vault_graph/answer/answer_plan.py`

Add frozen dataclasses:

```python
@dataclass(frozen=True)
class AnswerRequest:
    question: str
    requested_scope: QueryScope
    mode: AnswerMode = "evidence-first"
    include_graph: bool = False
    include_cross_vault: bool = False
    retrieval_limit: int = 10
    max_evidence_tokens: int = 8000
```

```python
@dataclass(frozen=True)
class EvidencePlanStep:
    step_id: str
    kind: str
    query: str
    required: bool
    include_graph: bool = False
    include_cross_vault: bool = False
    limit: int = 10
```

```python
@dataclass(frozen=True)
class AnswerPlan:
    request: AnswerRequest
    steps: tuple[EvidencePlanStep, ...]
```

```python
@dataclass(frozen=True)
class PlannedEvidence:
    plan: AnswerPlan
    actual_scopes: tuple[QueryScope, ...]
    evidence: tuple[AnswerEvidence, ...]
    reasoning_trace: tuple[AnswerReasoningStep, ...]
    warnings: tuple[AnswerWarning, ...]
    dropped_evidence_count: int = 0
```

Validation requirements:

- `question.strip()` is required.
- `mode` must equal `"evidence-first"`.
- `retrieval_limit` must be `1..50`.
- `max_evidence_tokens` must be `1000..24000`.
- `include_cross_vault=True` requires `include_graph=True`.
- `include_cross_vault=True` requires `len(requested_scope.vault_ids) > 1`.
- `include_cross_vault` must match `requested_scope.include_cross_vault`.

Add helper:

```python
def answer_id_for(
    *,
    question: str,
    mode: AnswerMode,
    requested_scope: QueryScope,
    evidence_ids: tuple[str, ...],
    generated_at: str,
) -> str: ...
```

The ID must be a runtime identifier, not durable knowledge:

- prefix: `answer:`
- digest inputs: normalized question, mode, requested scope, evidence IDs, generated timestamp
- digest length: 24 hex chars

### `src/vault_graph/answer/evidence_planner.py`

Add Protocols:

```python
class AnswerRetrievalService(Protocol):
    def search(
        self,
        *,
        query_text: str,
        requested_scope: QueryScope,
        limit: int = 10,
        output_format: SearchOutputFormat = "text",
        include_graph: bool = False,
        include_cross_vault: bool = False,
    ) -> SearchResponse: ...
```

```python
class AnswerGraphService(Protocol):
    def decision_trace(
        self,
        *,
        topic: str,
        requested_scope: QueryScope,
        depth: int = 2,
        include_cross_vault: bool = False,
        limit: int = 10,
        output_format: GraphOutputFormat = "text",
    ) -> DecisionTraceResponse: ...
```

```python
class AnswerProjectMemoryService(Protocol):
    def summarize(self, *, requested_scope: QueryScope, limit: int = 10) -> ProjectMemoryProjection: ...
```

```python
class AnswerOpenQuestionsService(Protocol):
    def open_questions(self, *, requested_scope: QueryScope, limit: int = 20) -> OpenQuestionsProjection: ...
```

Add:

```python
class EvidencePlanner:
    def __init__(
        self,
        *,
        retrieval_service: AnswerRetrievalService,
        graph_service: AnswerGraphService | None = None,
        project_memory_service: AnswerProjectMemoryService | None = None,
        open_questions_service: AnswerOpenQuestionsService | None = None,
    ) -> None: ...

    def plan(self, request: AnswerRequest) -> AnswerPlan: ...
    def gather(self, plan: AnswerPlan) -> PlannedEvidence: ...
```

Planning rules:

- Always add one required `search` step.
- Use `RetrievalService.search(..., output_format="json")`.
- Pass graph flags to search only when explicitly requested.
- Add an optional `decision_trace` step only when `include_graph=True`, `graph_service is not None`, and the question contains deterministic decision terms:
  `why`, `decision`, `tradeoff`, `trade-off`, `choose`, `chosen`, `adopt`, `adopted`, `revisit`, `because`.
- Add optional `project_memory` when `project_memory_service is not None`.
- Add optional `open_question` when `open_questions_service is not None`.
- Do not call context-pack builder in this first implementation. The response DTO keeps `context_pack` as a supported `source_kind`, but ask must not build or persist a context pack just to answer.

Evidence normalization rules:

- Search result evidence:
  - `source_kind="search_result"`
  - `result_id=result.result_id`
  - `excerpt=result.summary`
  - `retrieval_reason` is a comma-separated signal kind list such as `keyword`, `vector`, `graph`, or `keyword,vector`
  - `relationship_status=result.relationship_status`
- Decision trace evidence:
  - `source_kind="decision_trace"`
  - `result_id="decision_trace:<digest>"`
  - `excerpt=step.explanation`
  - `relationship_status=step.relationship_status`
  - graph warnings map to answer warnings
- Project memory evidence:
  - `source_kind="project_memory"`
  - `excerpt=item.summary`
  - memory claim status maps conservatively:
    - `stated` -> `supported`
    - `metadata_derived` -> `partial`
    - `heading_candidate` -> `partial` with warning
- Open question evidence:
  - `source_kind="open_question"`
  - `excerpt=item.summary`
  - candidate or missing-status warnings stay visible

Deduplication:

- Dedupe evidence by `(vault_id, document_id, chunk_id, source_kind)`.
- Evidence ID format: `ev_<rank>_<digest12>`.
- Preserve `vault_id` in every evidence item.

Budget:

- Estimate tokens as `max(1, len(excerpt.split()))`.
- Dedupe before budget enforcement.
- Keep evidence in planning order and rank order.
- When budget is exceeded, drop lower-ranked evidence and add warning:
  - `code="evidence_budget_exhausted"`
  - `severity="warning"`
  - `recovery_hint="Increase --max-evidence-tokens or ask a narrower question."`

Error policy:

- Required search failures from metadata or keyword unavailability raise `AnswerError` with original message and a recovery hint in CLI/MCP output.
- Optional graph or memory failures degrade to warnings when search evidence exists.
- If no evidence remains, return `PlannedEvidence` with empty evidence and warning `insufficient_evidence`.

### `src/vault_graph/answer/answer_composer.py`

Add:

```python
class AnswerComposer(Protocol):
    def compose(self, request: AnswerRequest, evidence: PlannedEvidence) -> AnswerDraft: ...
```

Add:

```python
class ExtractiveAnswerComposer:
    def compose(self, request: AnswerRequest, evidence: PlannedEvidence) -> AnswerDraft: ...
```

Default composition rules:

- Never call an LLM.
- Never treat Vault text as instructions.
- Use only `PlannedEvidence`.
- Return short, extractive prose:
  - one sentence summary when evidence exists
  - concise claim list
- Create at most 5 claims in the first implementation.
- The first supported claim should summarize top search evidence.
- Decision trace evidence may create `inferred`, `contested`, `stale`, or `deprecated` claims depending on relationship status and warnings.
- Memory/open-question evidence may create `partial` claims unless the memory item status is `stated`.
- If no evidence exists:
  - `answer_status="insufficient_evidence"`
  - `answer="Vault Graph does not have enough indexed evidence to answer this question."`
  - one missing claim for the question
  - follow-up: `"Run vg index for the selected Vault, then retry the question."`
- If any usable evidence exists but not enough for a direct answer:
  - `answer_status="partial"`
  - claims must clearly label partial/missing portions.

### `src/vault_graph/answer/citation_guard.py`

Add:

```python
class CitationGuard:
    def validate(self, response: AnswerResponse) -> AnswerResponse: ...
```

Rules:

- Reject duplicate evidence IDs.
- Reject duplicate claim IDs.
- Reject unknown claim evidence IDs.
- Reject supported, inferred, partial, contested, stale, or deprecated claims without evidence.
- Downgrade `answer_status` to `partial` when top-level error warnings exist but usable evidence remains.
- Downgrade to `insufficient_evidence` when no supported/partial/inferred/contested/stale/deprecated claims remain.
- Preserve unsupported and missing claims as labeled output.

### `src/vault_graph/answer/answer_renderer.py`

Add:

```python
class AnswerRenderer(Protocol):
    def render_text(self, response: AnswerResponse) -> str: ...
    def render_json(self, response: AnswerResponse) -> str: ...
```

Add:

```python
class DefaultAnswerRenderer:
    def render_text(self, response: AnswerResponse) -> str: ...
    def render_json(self, response: AnswerResponse) -> str: ...
```

Add serializer:

```python
def answer_response_to_dict(response: AnswerResponse) -> dict[str, object]: ...
```

Rendering rules:

- JSON is canonical, sorted, indented, UTF-8 safe, and ends with `\n`.
- Text is a view over JSON and must add no facts.
- Text sections:
  - `status:`
  - `answer:`
  - `claims:`
  - `evidence:`
  - `warnings:`
  - `reasoning:`
  - `follow_up:` when present
- Evidence line format:
  - `ev_... [vault_id] path#section`
- Never print absolute Vault root paths.

### `src/vault_graph/app/answer_service.py`

Add:

```python
class AnswerService:
    def __init__(
        self,
        *,
        planner: EvidencePlanner,
        composer: AnswerComposer,
        citation_guard: CitationGuard,
        clock: Callable[[], datetime] | None = None,
    ) -> None: ...

    def ask(self, request: AnswerRequest) -> AnswerResponse: ...
```

Responsibilities:

- Validate `AnswerRequest` through its dataclass contract.
- Call `planner.plan(request)`.
- Call `planner.gather(plan)`.
- Call `composer.compose(request, planned_evidence)`.
- Generate `generated_at` using the injected clock or UTC now.
- Generate `answer_id` with `answer_id_for(...)`.
- Assemble `AnswerResponse`.
- Run `CitationGuard.validate(...)`.
- Return `AnswerResponse`.

`AnswerService` must not:

- import Typer or MCP
- import local SQLite/Chroma/rustworkx adapters
- read Vault files directly
- write any state
- run indexing

## State Management And Data Flow

```text
CLI or MCP adapter
  -> resolve QueryScope with existing catalog/scope helpers
  -> AnswerRequest
  -> AnswerService.ask(request)
     -> EvidencePlanner.plan(request)
     -> EvidencePlanner.gather(plan)
        -> RetrievalService.search(...)
        -> optional GraphRetrievalService.decision_trace(...)
        -> optional ProjectMemoryService.summarize(...)
        -> optional IssueMemoryService.open_questions(...)
        -> normalize to AnswerEvidence
        -> dedupe by (vault_id, document_id, chunk_id, source_kind)
        -> enforce max_evidence_tokens
     -> ExtractiveAnswerComposer.compose(...)
     -> AnswerService attaches id, timestamp, evidence, and trace
     -> CitationGuard.validate(...)
     -> AnswerResponse
  -> CLI DefaultAnswerRenderer or MCP mcp_answer_serialization
```

Allowed reads:

- Vault catalog config through `CatalogService`.
- Metadata, keyword, vector, graph, and memory projections through existing application services.
- MCP `ResultExplanationCache` for current-process explainability only.

Allowed writes:

- CLI ask: none.
- MCP ask: bounded in-process `ResultExplanationCache.put_many(...)` only.

Forbidden writes:

- Vault files.
- Metadata SQLite.
- Keyword projection.
- Chroma/vector store.
- Graph store.
- Vector or graph status files.
- Projection cache.
- Embedding/model cache.
- Durable answer cache.
- Memory state directory.
- External memory system.

## Implementation Tasks

### Task 1: Add Answer Error And Response DTO Contracts

**Files:**

- Modify: `src/vault_graph/errors.py`
- Create: `src/vault_graph/answer/__init__.py`
- Create: `src/vault_graph/answer/answer_response.py`
- Test: `tests/test_answer_response_contract.py`
- Test: `tests/test_answer_import_boundaries.py`

- [ ] **Step 1: Write failing DTO validation tests**

Add tests:

```python
def test_answer_response_rejects_supported_claim_without_evidence() -> None: ...
def test_answer_response_rejects_unknown_claim_evidence_id() -> None: ...
def test_answer_response_requires_non_empty_actual_scopes() -> None: ...
def test_supported_answer_requires_supported_claim() -> None: ...
def test_insufficient_evidence_allows_empty_evidence() -> None: ...
```

Run:

```bash
uv run --python 3.12 pytest tests/test_answer_response_contract.py -q
```

Expected: FAIL because `vault_graph.answer` does not exist.

- [ ] **Step 2: Implement `AnswerError` and DTOs**

Implement all dataclasses and `__post_init__` validation from the component spec. Use small private helpers such as `_require_non_empty(...)`, `_require_tuple(...)`, `_unique_field(...)`, and `_evidence_id_set(...)`.

- [ ] **Step 3: Add lazy package exports**

`src/vault_graph/answer/__init__.py` must use `__getattr__` lazy exports, matching the style of `vault_graph.memory` where possible.

Public names:

- `AnswerRequest`
- `AnswerPlan`
- `PlannedEvidence`
- `AnswerResponse`
- `AnswerDraft`
- `AnswerEvidence`
- `AnswerClaim`
- `AnswerWarning`
- `AnswerReasoningStep`
- `EvidencePlanner`
- `ExtractiveAnswerComposer`
- `CitationGuard`
- `DefaultAnswerRenderer`

- [ ] **Step 4: Add import-boundary tests**

In `tests/test_answer_import_boundaries.py`, verify:

- importing `vault_graph.answer` does not import `typer`, `mcp`, `chromadb`, `fastembed`, `rustworkx`, or `vault_graph.storage.local.*`
- answer package files do not import `vault_graph.cli`
- answer package files do not import `vault_graph.mcp`
- answer package files do not import local store implementations

Run:

```bash
uv run --python 3.12 pytest tests/test_answer_response_contract.py tests/test_answer_import_boundaries.py -q
```

Expected: PASS.

### Task 2: Add Answer Request, Plan, And Runtime ID Contracts

**Files:**

- Create: `src/vault_graph/answer/answer_plan.py`
- Test: `tests/test_answer_plan_contract.py`

- [ ] **Step 1: Write failing request validation tests**

Add tests:

```python
def test_answer_request_rejects_empty_question() -> None: ...
def test_answer_request_rejects_unsupported_mode() -> None: ...
def test_answer_request_caps_retrieval_limit() -> None: ...
def test_answer_request_caps_evidence_budget() -> None: ...
def test_cross_vault_requires_graph_and_multi_vault_scope() -> None: ...
def test_answer_id_is_runtime_scoped_and_stable_for_same_inputs() -> None: ...
```

Run:

```bash
uv run --python 3.12 pytest tests/test_answer_plan_contract.py -q
```

Expected: FAIL because `answer_plan.py` does not exist.

- [ ] **Step 2: Implement planning DTOs**

Implement `AnswerRequest`, `EvidencePlanStep`, `AnswerPlan`, `PlannedEvidence`, and `answer_id_for(...)`.

- [ ] **Step 3: Verify**

Run:

```bash
uv run --python 3.12 pytest tests/test_answer_plan_contract.py tests/test_answer_response_contract.py -q
```

Expected: PASS.

### Task 3: Add CitationGuard

**Files:**

- Create: `src/vault_graph/answer/citation_guard.py`
- Test: `tests/test_citation_guard.py`

- [ ] **Step 1: Write failing guard tests**

Add tests:

```python
def test_guard_rejects_unknown_evidence_id() -> None: ...
def test_guard_rejects_supported_claim_without_evidence() -> None: ...
def test_guard_downgrades_supported_response_with_error_warning_to_partial() -> None: ...
def test_guard_downgrades_no_usable_evidence_to_insufficient_evidence() -> None: ...
def test_guard_preserves_missing_claim_as_labeled_output() -> None: ...
```

Run:

```bash
uv run --python 3.12 pytest tests/test_citation_guard.py -q
```

Expected: FAIL because `CitationGuard` does not exist.

- [ ] **Step 2: Implement guard**

Implement the validation and downgrade rules. Keep it pure: no filesystem, no service calls, no clock.

- [ ] **Step 3: Verify**

Run:

```bash
uv run --python 3.12 pytest tests/test_citation_guard.py tests/test_answer_response_contract.py -q
```

Expected: PASS.

### Task 4: Add EvidencePlanner Search Normalization

**Files:**

- Create: `src/vault_graph/answer/evidence_planner.py`
- Test: `tests/test_evidence_planner.py`

- [ ] **Step 1: Write failing search planner tests**

Add tests using a recording fake retrieval service returning `SearchResponse` fixtures:

```python
def test_planner_always_plans_required_search_step() -> None: ...
def test_gather_calls_retrieval_service_with_json_output() -> None: ...
def test_search_result_maps_to_answer_evidence() -> None: ...
def test_search_warnings_map_to_answer_warnings() -> None: ...
def test_missing_search_evidence_returns_insufficient_evidence_warning() -> None: ...
def test_evidence_budget_drops_lower_ranked_evidence_with_warning() -> None: ...
```

Run:

```bash
uv run --python 3.12 pytest tests/test_evidence_planner.py -q
```

Expected: FAIL because planner does not exist.

- [ ] **Step 2: Implement Protocols and `EvidencePlanner.plan(...)`**

Implement protocols and planning rules. The first plan must include:

```python
EvidencePlanStep(
    step_id="search:1",
    kind="search",
    query=request.question.strip(),
    required=True,
    include_graph=request.include_graph,
    include_cross_vault=request.include_cross_vault,
    limit=request.retrieval_limit,
)
```

- [ ] **Step 3: Implement search evidence normalization**

Map `SearchResponse.results[*].evidence[*]` and `RetrievalSignal` to `AnswerEvidence` and `AnswerSignal`.

Keep `actual_scopes=response.actual_scopes`.

Reasoning step:

```python
AnswerReasoningStep(
    step_id="search:1",
    kind="search",
    service="RetrievalService.search",
    status="ok" or "warning",
    query=request.question.strip(),
    result_count=response.result_count,
    kept_evidence_ids=(...),
    dropped_count=response.dropped_candidate_count,
    warning_codes=(...),
)
```

- [ ] **Step 4: Verify**

Run:

```bash
uv run --python 3.12 pytest tests/test_evidence_planner.py -q
```

Expected: PASS for search-only cases.

### Task 5: Add Optional Graph And Memory Planning

**Files:**

- Modify: `src/vault_graph/answer/evidence_planner.py`
- Test: `tests/test_evidence_planner.py`
- Test: `tests/test_answer_multi_vault.py`

- [ ] **Step 1: Write failing graph and memory tests**

Add tests:

```python
def test_decision_trace_only_planned_when_graph_requested_and_question_is_decision_oriented() -> None: ...
def test_graph_unavailable_degrades_to_warning_when_search_evidence_exists() -> None: ...
def test_decision_trace_evidence_preserves_relationship_status() -> None: ...
def test_project_memory_evidence_maps_to_partial_claim_source() -> None: ...
def test_open_question_evidence_source_is_preserved() -> None: ...
def test_multi_vault_evidence_preserves_vault_ids() -> None: ...
```

Run:

```bash
uv run --python 3.12 pytest tests/test_evidence_planner.py tests/test_answer_multi_vault.py -q
```

Expected: FAIL until optional sources are implemented.

- [ ] **Step 2: Implement graph normalization**

Call:

```python
graph_service.decision_trace(
    topic=request.question.strip(),
    requested_scope=request.requested_scope,
    include_cross_vault=request.include_cross_vault,
    limit=min(request.retrieval_limit, 10),
    output_format="json",
)
```

Convert `DecisionTraceResponse.steps[*].evidence[*]` into `AnswerEvidence(source_kind="decision_trace")`.

Map `GraphRetrievalWarning` to `AnswerWarning`.

- [ ] **Step 3: Implement memory normalization**

Call project memory and open-question services with bounded limits:

```python
project_memory_service.summarize(requested_scope=request.requested_scope, limit=min(request.retrieval_limit, 10))
open_questions_service.open_questions(requested_scope=request.requested_scope, limit=min(request.retrieval_limit, 20))
```

Convert `MemoryEvidenceRef` to `AnswerEvidence`.

Map `MemoryWarning` to `AnswerWarning`.

- [ ] **Step 4: Dedupe and budget after all sources**

Apply dedupe and `max_evidence_tokens` after all source normalization. Preserve first occurrence order.

- [ ] **Step 5: Verify**

Run:

```bash
uv run --python 3.12 pytest tests/test_evidence_planner.py tests/test_answer_multi_vault.py -q
```

Expected: PASS.

### Task 6: Add ExtractiveAnswerComposer

**Files:**

- Create: `src/vault_graph/answer/answer_composer.py`
- Test: `tests/test_answer_composer.py`

- [ ] **Step 1: Write failing composer tests**

Add tests:

```python
def test_composer_returns_supported_answer_from_search_evidence() -> None: ...
def test_composer_returns_partial_answer_when_warnings_exist() -> None: ...
def test_composer_returns_insufficient_evidence_without_evidence() -> None: ...
def test_composer_never_creates_claim_without_evidence_except_missing_or_unsupported() -> None: ...
def test_composer_marks_contested_and_deprecated_relationships_visibly() -> None: ...
def test_composer_limits_claim_count() -> None: ...
```

Run:

```bash
uv run --python 3.12 pytest tests/test_answer_composer.py -q
```

Expected: FAIL because composer does not exist.

- [ ] **Step 2: Implement composer**

Implement deterministic extraction:

- Use the first 3 to 5 evidence excerpts.
- Supported claim text format: `Evidence from <path> indicates: <excerpt>`
- Partial claim text format: `Vault Graph found partial evidence in <path>: <excerpt>`
- Missing claim text format: `No indexed evidence directly answers: <question>`
- Answer text:
  - supported: `Vault Graph found indexed evidence that answers the question.`
  - partial: `Vault Graph found partial evidence; review the labeled claims and warnings.`
  - insufficient: exact string from SPEC.

No answer text may mention facts not present in evidence excerpt, path, status, or warnings.

- [ ] **Step 3: Verify**

Run:

```bash
uv run --python 3.12 pytest tests/test_answer_composer.py tests/test_citation_guard.py -q
```

Expected: PASS.

### Task 7: Add AnswerService Orchestration

**Files:**

- Create: `src/vault_graph/app/answer_service.py`
- Test: `tests/test_answer_service.py`
- Test: `tests/test_answer_read_only_boundary.py`

- [ ] **Step 1: Write failing service tests**

Add tests:

```python
def test_answer_service_calls_planner_composer_and_guard() -> None: ...
def test_answer_service_attaches_answer_id_and_generated_at() -> None: ...
def test_answer_service_preserves_planned_evidence_and_trace() -> None: ...
def test_answer_service_returns_insufficient_evidence_response() -> None: ...
def test_answer_service_does_not_write_files() -> None: ...
```

Use fakes for planner/composer/guard; use a fixed clock.

Run:

```bash
uv run --python 3.12 pytest tests/test_answer_service.py tests/test_answer_read_only_boundary.py -q
```

Expected: FAIL because `AnswerService` does not exist.

- [ ] **Step 2: Implement service**

Assemble `AnswerResponse` from `AnswerDraft` and `PlannedEvidence`.

Generated timestamp:

```python
generated_at = _utc_isoformat(self._clock())
```

Do not catch `AnswerError`. Let adapters map it.

- [ ] **Step 3: Verify**

Run:

```bash
uv run --python 3.12 pytest tests/test_answer_service.py tests/test_answer_read_only_boundary.py -q
```

Expected: PASS.

### Task 8: Add AnswerRenderer And JSON Serialization

**Files:**

- Create: `src/vault_graph/answer/answer_renderer.py`
- Test: `tests/test_answer_renderer.py`

- [ ] **Step 1: Write failing renderer tests**

Add tests:

```python
def test_render_json_round_trips_answer_response_shape() -> None: ...
def test_render_text_includes_status_claims_evidence_warnings_and_reasoning() -> None: ...
def test_render_text_labels_missing_claims() -> None: ...
def test_render_text_does_not_include_absolute_vault_paths() -> None: ...
def test_render_json_rejects_non_finite_float_scores() -> None: ...
```

Run:

```bash
uv run --python 3.12 pytest tests/test_answer_renderer.py -q
```

Expected: FAIL.

- [ ] **Step 2: Implement renderer**

Follow `context_pack_serialization.py` style:

- support only known answer dataclasses, tuples, strings, ints, floats, bools, and `None`
- serialize `QueryScope` through `query_scope_to_dict`-equivalent local helper
- reject `Path`, bytes, dicts in dataclass fields, sets, and non-finite floats

- [ ] **Step 3: Verify**

Run:

```bash
uv run --python 3.12 pytest tests/test_answer_renderer.py -q
```

Expected: PASS.

### Task 9: Add CLI `vg ask`

**Files:**

- Modify: `src/vault_graph/cli/main.py`
- Test: `tests/test_cli_ask.py`
- Modify: `tests/test_cli_surface_boundary.py`

- [ ] **Step 1: Write failing CLI tests**

Add tests:

```python
def test_cli_ask_uses_active_vault_by_default() -> None: ...
def test_cli_ask_json_uses_answer_response_contract() -> None: ...
def test_cli_ask_scope_flags_are_mutually_exclusive() -> None: ...
def test_cli_ask_include_cross_vault_requires_all_vaults_and_graph() -> None: ...
def test_cli_ask_rejects_empty_question() -> None: ...
def test_cli_ask_rejects_unsupported_format() -> None: ...
def test_cli_ask_does_not_open_graph_when_graph_flag_is_false() -> None: ...
def test_cli_ask_include_graph_opens_graph_service() -> None: ...
def test_cli_ask_does_not_mutate_vault_or_create_answer_state() -> None: ...
def test_vg_help_lists_ask_command() -> None: ...
```

Run:

```bash
uv run --python 3.12 pytest tests/test_cli_ask.py tests/test_cli_surface_boundary.py -q
```

Expected: FAIL because command does not exist.

- [ ] **Step 2: Add `_answer_scope_for_flags(...)`**

Use the same policy as context/search:

- `--vault-id` and `--all-vaults` are mutually exclusive.
- `--include-cross-vault` requires `--all-vaults --include-graph`.
- When `include_cross_vault=True`, return a `QueryScope` with `include_cross_vault=True`.

- [ ] **Step 3: Add `_answer_service(...)` helper**

Signature:

```python
def _answer_service(
    state: Path,
    *,
    include_graph: bool = False,
) -> tuple[CatalogService, VaultCatalog, AnswerService]:
    ...
```

Construction rules:

- Use `_read_only_search_components(...)` to build read-only retrieval.
- Open graph service only when `include_graph=True`.
- Construct Phase 6 memory services read-only using existing memory source/status services only if doing so does not create state paths.
- Use `ExtractiveAnswerComposer`, `CitationGuard`, `EvidencePlanner`, and `AnswerService`.
- Do not import MCP modules.

- [ ] **Step 4: Add Typer command**

Signature:

```python
@app.command()
def ask(
    question: str = typer.Argument(..., help="Natural-language question."),
    state: Path = typer.Option(Path(".vault-graph"), "--state", help="Vault Graph state path."),
    vault_id: str | None = typer.Option(None, "--vault-id", help="Ask one registered Vault ID."),
    all_vaults: bool = typer.Option(False, "--all-vaults", help="Ask all enabled registered Vaults."),
    output_format: str = typer.Option("text", "--format", help="Output format: text or json."),
    include_graph: bool = typer.Option(False, "--include-graph", help="Include explicit graph and decision-trace signals."),
    include_cross_vault: bool = typer.Option(False, "--include-cross-vault", help="Include explicit cross-Vault graph relationships."),
    limit: int = typer.Option(10, "--limit", help="Maximum retrieval evidence before answering."),
    max_evidence_tokens: int = typer.Option(8000, "--max-evidence-tokens", help="Estimated answer evidence token budget."),
) -> None:
    ...
```

Validation messages:

- empty question: `empty_question`
- unsupported format: `unsupported_format`
- limit <= 0: `answer_limit_must_be_positive`
- max evidence tokens < 1000: `answer_evidence_budget_too_small`
- cross-vault misuse: `include_cross_vault_requires_multi_vault_graph_scope`

- [ ] **Step 5: Render output**

- `--format json`: `DefaultAnswerRenderer.render_json(response)`
- text: `DefaultAnswerRenderer.render_text(response)`

Use `nl=False` because renderer returns trailing newline.

- [ ] **Step 6: Verify**

Run:

```bash
uv run --python 3.12 pytest tests/test_cli_ask.py tests/test_cli_surface_boundary.py -q
uv run --python 3.12 vg --help
uv run --python 3.12 vg ask --help
```

Expected: PASS; `vg --help` lists `ask`; `vg ask --help` shows answer flags.

### Task 10: Add MCP Answer Serialization

**Files:**

- Create: `src/vault_graph/mcp/mcp_answer_serialization.py`
- Test: `tests/test_mcp_ask_vault.py`
- Modify: `tests/test_mcp_import_boundaries.py`

- [ ] **Step 1: Write failing MCP serialization tests**

Add tests:

```python
def test_answer_response_to_payload_matches_answer_json_contract() -> None: ...
def test_resource_links_for_answer_include_evidence_links() -> None: ...
def test_explanation_records_for_answer_register_evidence_items() -> None: ...
def test_mcp_warning_from_answer_preserves_recovery_hint() -> None: ...
def test_mcp_answer_serialization_imports_no_fastmcp_or_backends() -> None: ...
```

Run:

```bash
uv run --python 3.12 pytest tests/test_mcp_ask_vault.py tests/test_mcp_import_boundaries.py -q
```

Expected: FAIL until serialization exists.

- [ ] **Step 2: Implement serializer**

Functions:

```python
def answer_response_to_payload(response: AnswerResponse) -> dict[str, object]: ...
def resource_links_for_answer(response: AnswerResponse) -> tuple[McpResourceLink, ...]: ...
def explanation_records_for_answer(response: AnswerResponse) -> tuple[ExplanationRecord, ...]: ...
def mcp_warning_from_answer(warning: AnswerWarning) -> McpErrorPayload: ...
```

Resource links:

- Use the same URI policy as search serialization:
  - `vault://{vault_id}/documents/{encoded_path}`
  - page/source/decision/issue links based on path prefix
- Reuse lower-level helpers only if doing so does not introduce circular imports. If helpers are private, duplicate a tiny local `_links_for_answer_evidence(...)` instead of exposing broad generic helpers.

Explanation records:

- `result_id=evidence.result_id or evidence.evidence_id`
- `source_kind=evidence.source_kind`
- `title=evidence.path`
- `summary=evidence.excerpt`
- `vault_id=evidence.vault_id`
- evidence refs from answer evidence fields
- signals from `AnswerSignal`
- relationship status from `AnswerEvidence.relationship_status`
- warnings matching evidence IDs

- [ ] **Step 3: Verify**

Run:

```bash
uv run --python 3.12 pytest tests/test_mcp_ask_vault.py tests/test_mcp_import_boundaries.py -q
```

Expected: serialization tests pass.

### Task 11: Add MCP `ask_vault`

**Files:**

- Modify: `src/vault_graph/mcp/mcp_service_factory.py`
- Modify: `src/vault_graph/mcp/mcp_tools.py`
- Modify: `src/vault_graph/mcp/mcp_tool_serialization.py` only if shared helpers are needed
- Test: `tests/test_mcp_ask_vault.py`
- Modify: `tests/test_mcp_tools.py`
- Modify: `tests/test_mcp_server.py`
- Modify: `tests/test_mcp_stdio_smoke.py`
- Modify: `tests/test_mcp_tool_read_only_boundary.py`

- [ ] **Step 1: Write failing registry tests**

Add tests:

```python
def test_register_mcp_tools_registers_ask_vault() -> None: ...
def test_parse_ask_vault_input_defaults_to_evidence_first() -> None: ...
def test_parse_ask_vault_rejects_unsupported_mode() -> None: ...
def test_ask_vault_calls_answer_service() -> None: ...
def test_ask_vault_with_graph_opens_graph_answer_service() -> None: ...
def test_ask_vault_registers_explanation_records() -> None: ...
def test_ask_vault_does_not_mutate_vault_or_create_answer_state() -> None: ...
```

Run:

```bash
uv run --python 3.12 pytest tests/test_mcp_ask_vault.py tests/test_mcp_tools.py -q
```

Expected: FAIL until MCP tool exists.

- [ ] **Step 2: Add `AskVaultInput`**

In `mcp_tools.py`:

```python
@dataclass(frozen=True)
class AskVaultInput:
    question: str
    mode: str = "evidence-first"
    scope: McpScopeInput | None = None
    limit: int = 10
    include_graph: bool = False
    include_cross_vault: bool = False
    max_evidence_tokens: int = 8000
```

Update:

```python
McpToolName = Literal[
    "ask_vault",
    "search_vault",
    ...
]
```

Place `ask_vault` first in `tool_names` because it is now the main product workflow. Keep tests explicit.

- [ ] **Step 3: Add parser and validation**

Add:

```python
def parse_ask_vault_input(
    *,
    question: str,
    mode: str = "evidence-first",
    scope: dict[str, object] | None = None,
    limit: int = 10,
    include_graph: bool = False,
    include_cross_vault: bool = False,
    max_evidence_tokens: int = 8000,
) -> AskVaultInput: ...
```

Validation:

- `question` required
- `mode == "evidence-first"`
- `limit` uses existing `_limit(...)`
- `max_evidence_tokens` must be int `1000..24000`
- `include_cross_vault` requires `include_graph`
- `scope.include_cross_vault` must match top-level `include_cross_vault`

- [ ] **Step 4: Add `McpServiceFactory.open_answer_service(...)`**

Signature:

```python
def open_answer_service(self, *, include_graph: bool = False) -> AnswerService: ...
```

Construction:

- Build retrieval through `_open_retrieval_components()` and `_build_retrieval_service(...)`.
- Graph service only when `include_graph=True`.
- Memory services through existing `open_project_memory_service()` and `open_issue_memory_service()`.
- Composer, guard, planner are deterministic default implementations.
- Keep imports inside the method to preserve lazy factory import tests.

- [ ] **Step 5: Add registry method**

In `McpToolRegistry`:

```python
def ask_vault(self, request: AskVaultInput) -> McpToolBody: ...
```

Flow:

- validate input
- resolve selected scope with `_scope_for_tool(...)`
- validate graph cross-vault width
- build `AnswerRequest`
- call `self._service_factory.open_answer_service(include_graph=request.include_graph).ask(answer_request)`
- serialize with `mcp_answer_serialization`
- put explanation records into `ResultExplanationCache`
- return `_tool_body(tool_name="ask_vault", ...)`

- [ ] **Step 6: Add FastMCP registration**

Add:

```python
@server.tool("ask_vault", structured_output=True)
def ask_vault(...): ...
```

Place before `search_vault` registration.

- [ ] **Step 7: Verify MCP**

Run:

```bash
uv run --python 3.12 pytest tests/test_mcp_ask_vault.py tests/test_mcp_tools.py tests/test_mcp_server.py tests/test_mcp_stdio_smoke.py tests/test_mcp_tool_read_only_boundary.py -q
```

Expected: PASS.

### Task 12: Full Boundary, Quality, And Regression Verification

**Files:**

- Modify any failing tests only where the expected surface genuinely changed from "ask not registered" to "ask registered".

- [ ] **Step 1: Run answer-focused test set**

```bash
uv run --python 3.12 pytest \
  tests/test_answer_response_contract.py \
  tests/test_answer_plan_contract.py \
  tests/test_evidence_planner.py \
  tests/test_answer_composer.py \
  tests/test_citation_guard.py \
  tests/test_answer_renderer.py \
  tests/test_answer_service.py \
  tests/test_answer_read_only_boundary.py \
  tests/test_answer_multi_vault.py \
  tests/test_answer_import_boundaries.py \
  tests/test_cli_ask.py \
  tests/test_mcp_ask_vault.py \
  -q
```

Expected: PASS.

- [ ] **Step 2: Run related regression tests**

```bash
uv run --python 3.12 pytest \
  tests/test_cli_search.py \
  tests/test_cli_context.py \
  tests/test_cli_related.py \
  tests/test_cli_decision_trace.py \
  tests/test_mcp_tools.py \
  tests/test_mcp_tool_serialization.py \
  tests/test_mcp_result_explanation_cache.py \
  tests/test_mcp_tool_read_only_boundary.py \
  tests/test_mcp_import_boundaries.py \
  tests/test_multi_vault_search.py \
  tests/test_multi_vault_graph_retrieval.py \
  tests/test_search_read_only_boundary.py \
  tests/test_context_pack_read_only_boundary.py \
  -q
```

Expected: PASS.

- [ ] **Step 3: Run full project checks**

```bash
uv run --python 3.12 pytest
uv run --python 3.12 ruff check .
uv run --python 3.12 mypy src tests
uv run --python 3.12 vg --help
uv run --python 3.12 vg ask --help
```

Expected:

- all tests pass
- ruff reports no issues
- mypy reports no issues
- `vg --help` includes `ask`
- `vg ask --help` lists scope, format, graph, limit, and evidence budget flags

## Errors And Edge Cases

| Case | Implementation behavior |
| --- | --- |
| Empty CLI question | Print `empty_question`, exit 1 |
| Empty MCP question | Raise `invalid_tool_arguments` |
| Unsupported ask mode | MCP validation error; CLI has no mode flag in this slice |
| `--vault-id` with `--all-vaults` | Print existing mutual-exclusion message, exit 1 |
| Unknown Vault ID | Catalog error through existing adapter mapping |
| `--include-cross-vault` without graph/all-Vault | Validation error `include_cross_vault_requires_multi_vault_graph_scope` |
| `limit <= 0` | CLI `answer_limit_must_be_positive`; MCP invalid arguments |
| `limit > 50` | `AnswerRequest` or MCP invalid arguments |
| `max_evidence_tokens < 1000` | CLI `answer_evidence_budget_too_small`; MCP invalid arguments |
| `max_evidence_tokens > 24000` | `AnswerRequest` or MCP invalid arguments |
| Metadata or keyword unavailable | Raise `AnswerError` with `Run vg index` recovery text |
| Vector unavailable | Search warning maps to answer warning; answer may be partial |
| Graph requested but unavailable | Graph warning, search evidence still used when available |
| Memory projection unavailable | Warning if search evidence exists; no hidden fallback facts |
| No evidence | Valid `insufficient_evidence` response |
| Conflicting/contested graph evidence | Claims labeled `contested` or answer downgraded to `partial` |
| Deprecated graph relationship | Not used as supported fact; shown as `deprecated` claim if included |
| Evidence budget exhausted | Lower-ranked evidence dropped with warning |
| Missing evidence after candidate resolution | Drop evidence and warn |
| Absolute path in evidence | Reject or omit in renderer tests; output must stay Vault-relative |

## Risks And Mitigations

- Risk: deterministic composer may feel less fluent than LLM answers.
  - Mitigation: keep this slice extractive and correct; future LLM composers can sit behind `AnswerComposer` after citation guarantees are proven.
- Risk: answer planner becomes a second retrieval engine.
  - Mitigation: it only calls existing services and normalizes outputs; no store access or ranking backend imports.
- Risk: MCP and CLI output drift.
  - Mitigation: both call `AnswerService`; JSON is rendered from `AnswerResponse`; MCP payload uses the same response fields.
- Risk: memory projection calls add cost.
  - Mitigation: bounded limits, no writes, no direct scans outside existing memory services, optional dependency injection.
- Risk: graph dependencies load for plain ask.
  - Mitigation: tests assert plain ask does not open graph service or load rustworkx projection.
- Risk: answer claims become unsupported prose.
  - Mitigation: `CitationGuard` rejects or downgrades unsupported normal claims.

## Validation Review

Subagent note: actual subagent spawning was not used while writing this plan because current tool policy permits spawning only when the user explicitly requests subagents or delegation. The same review angles required by `vg-plan` were applied inline and reflected in the tasks above.

- Security/read-only: Plan forbids Vault writes, answer storage, indexing, model downloads, and durable memory. Tests cover Vault byte immutability and missing state path creation.
- Performance/scalability: Plan keeps bounded retrieval limits, evidence budgets, graph opt-in behavior, lazy graph imports, and no whole-Vault answer scans.
- Testability: DTOs, planner, composer, guard, renderer, service, CLI, and MCP each have focused tests with fake services and fixed clocks.
- Maintainability/deep modules: Answer policy lives in `vault_graph.answer`; app orchestration lives in `app.answer_service`; CLI/MCP stay adapters.
- Agent ergonomics: `vg ask` and `ask_vault` expose answer, claims, evidence, reasoning trace, warnings, and follow-up in one stable contract.

## Open Decisions

None. The implementation follows accepted project direction: evidence-first ask is the next core implementation, deterministic extractive composition is the default, and future hosted LLM/external memory/HTTP/UI work remains outside this slice.

