# Evidence-First Ask And Reasoning SPEC

Status: Implementation-ready design for planning

Date: 2026-06-25

Scope: Ask and reasoning layer

## 1. Purpose

This SPEC defines the next core Vault Graph capability:

```bash
vg ask "Why did we adopt GraphRAG?"
```

and the matching MCP tool:

```text
ask_vault(question, mode="evidence-first", scope=None)
```

The goal is to complete the first product vision: a user or agent can ask a
natural-language question and receive a concise, evidence-linked answer from
Vault-derived state without scanning the entire Vault manually.

The answer layer must preserve the Vault Graph boundary:

- Vault is the durable source of truth.
- Vault Graph answers are read-only working context.
- Every major answer claim is cited, explicitly labeled, or rejected.
- Missing evidence is reported as missing evidence, not filled with fluent
  synthesis.
- No answer, claim, trace, cache, or projection becomes durable knowledge until
  it is intentionally captured through the normal Vault workflow.

## 2. Source Contracts

This design is grounded in:

- `docs/SPEC.md`
- `docs/FEATURES.md`
- `docs/DESIGN.md`
- `docs/DECISIONS.md`
- `docs/CONVENTIONS.md`
- `docs/superpowers/specs/2026-06-09-phase-2c-evidence-first-keyword-vector-search-design.md`
- `docs/superpowers/specs/phase-3/2026-06-10-phase-3c-graph-projection-retrieval-design.md`
- `docs/superpowers/specs/phase-4/2026-06-12-phase-4b-local-context-pack-assembly-rendering-design.md`
- `docs/superpowers/specs/phase-5/2026-06-15-phase-5c-mcp-tools-prompts-agent-workflows-design.md`
- `docs/superpowers/specs/phase-6/2026-06-18-phase-6-memory-and-explorer-views-overview-design.md`
- `docs/superpowers/specs/2026-06-24-cli-todo-command-implementation-design.md`

Accepted decision:

- `2026-06-25 - Make Evidence-First Ask The Next Core Implementation`

## 3. Product Outcome

The implementation is complete when:

- `vg ask QUESTION` returns a cited answer over the active Vault.
- `vg ask --vault-id ID QUESTION` returns a cited answer scoped to one Vault.
- `vg ask --all-vaults QUESTION` preserves per-Vault identity in evidence and
  claims.
- `vg ask --include-graph QUESTION` may use graph signals and decision traces
  when indexed graph state is available.
- `vg ask --format json QUESTION` returns the canonical `AnswerResponse`.
- MCP registers `ask_vault` only after `AnswerService` exists.
- CLI and MCP both call the same `AnswerService` boundary.
- unsupported, missing, partial, stale, contested, deprecated, and inferred
  claims are visible in structured output.
- answer generation does not mutate Vault files or derived index state.
- missing vector, graph, memory, or explanation projection state degrades with
  warnings where possible.

## 4. Non-Goals

This SPEC must not implement or require:

- hosted LLM calls
- automatic model downloads during ask
- a writable memory database
- generic `Memory.create/query/upsert/link/audit`
- hidden episode logs
- profile, preference, or procedural memory
- automatic Vault publication
- automatic Vault edits, renames, rewrites, deletes, or validation
- durable answer history
- cross-Vault entity merging
- remote HTTP serving
- UI screens
- autonomous contradiction resolution

Future LLM composers may be added only behind the `AnswerComposer` contract and
must pass the same citation guard.

## 5. Design Principles

| Principle | Design rule |
| --- | --- |
| Vault source of truth | Answers cite Vault-derived evidence and never become authority. |
| Read-only | `ask` reads existing projections only; it does not index, initialize stores, or write caches except bounded MCP runtime caches already owned by MCP. |
| Evidence-first | Normal claims require evidence IDs. Unsupported or missing claims must be labeled. |
| Local-first | The default composer is deterministic and runs without internet access or hosted LLMs. |
| Simple now | First implementation uses small deterministic planning rules and bounded evidence limits. |
| Scale-compatible | All storage access stays behind existing services; future LLM, HTTP, or remote backends remain adapters. |
| Multi-vault correct | `vault_id` is preserved in every evidence ref, claim, warning, and trace step. |

## 6. User-Facing Surface

### 6.1 CLI

Add:

```bash
vg ask QUESTION
vg ask --vault-id ID QUESTION
vg ask --all-vaults QUESTION
vg ask --include-graph QUESTION
vg ask --all-vaults --include-graph --include-cross-vault QUESTION
vg ask --format json QUESTION
```

Options:

```text
--state PATH
--vault-id ID
--all-vaults
--format text|json
--include-graph
--include-cross-vault
--limit N
--max-evidence-tokens N
```

Defaults:

- `--state .vault-graph`
- active Vault scope
- `--format text`
- `--limit 10`
- `--max-evidence-tokens 8000`
- graph disabled unless `--include-graph` is set
- cross-Vault relationships disabled unless explicitly requested

Validation:

- `--vault-id` and `--all-vaults` are mutually exclusive.
- `--include-cross-vault` requires `--all-vaults --include-graph`.
- `--limit` must be positive.
- `--max-evidence-tokens` must be at least `1000`.
- empty questions return `empty_question`.
- unsupported formats return `unsupported_format`.

Text output must include:

- answer status
- answer
- claim list with status and evidence IDs
- evidence list with Vault-relative paths
- warnings
- reasoning trace summary
- suggested durable follow-up when present

JSON output is the canonical `AnswerResponse`.

### 6.2 MCP Tool

Add tool name:

```text
ask_vault
```

Input:

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

Rules:

- only `mode="evidence-first"` is supported in this slice;
- `scope=None` uses the active Vault;
- cross-Vault answering requires explicit scope or all-Vault selection;
- MCP maps the input to `AnswerRequest` and calls `AnswerService.ask`;
- MCP returns the existing `McpToolBody` envelope with the answer payload,
  resource links, warnings, and a text mirror;
- the text mirror must contain no facts absent from structured output;
- answer evidence may be registered in `ResultExplanationCache` so
  `explain_result` can explain evidence items returned by `ask_vault` in the
  same MCP process.

## 7. Directory And File Structure

Add:

```text
src/vault_graph/answer/__init__.py
src/vault_graph/answer/answer_plan.py
src/vault_graph/answer/answer_response.py
src/vault_graph/answer/evidence_planner.py
src/vault_graph/answer/answer_composer.py
src/vault_graph/answer/citation_guard.py
src/vault_graph/answer/answer_renderer.py
src/vault_graph/app/answer_service.py
src/vault_graph/mcp/mcp_answer_serialization.py
tests/test_answer_response_contract.py
tests/test_evidence_planner.py
tests/test_answer_composer.py
tests/test_citation_guard.py
tests/test_answer_service.py
tests/test_answer_read_only_boundary.py
tests/test_answer_multi_vault.py
tests/test_answer_import_boundaries.py
tests/test_cli_ask.py
tests/test_mcp_ask_vault.py
```

Modify:

```text
src/vault_graph/errors.py
src/vault_graph/cli/main.py
src/vault_graph/mcp/__init__.py
src/vault_graph/mcp/mcp_service_factory.py
src/vault_graph/mcp/mcp_tools.py
src/vault_graph/mcp/mcp_tool_serialization.py
tests/test_cli_surface_boundary.py
tests/test_mcp_import_boundaries.py
tests/test_mcp_server.py
tests/test_mcp_stdio_smoke.py
tests/test_mcp_tool_read_only_boundary.py
tests/test_mcp_tools.py
```

Do not add `data/answers/`, `data/memory/`, answer databases, durable answer
logs, or new external dependencies.

## 8. Package Responsibilities

| Package | Owns | Must not own |
| --- | --- | --- |
| `vault_graph.answer` | answer DTOs, planning records, evidence grouping, deterministic composition, citation validation, text rendering | CLI parsing, MCP registration, direct SQLite/Chroma/rustworkx access, Vault file reads |
| `vault_graph.app.answer_service` | application-service orchestration shared by CLI, MCP, and later HTTP | protocol-specific output, durable storage, indexing |
| `vault_graph.cli` | CLI arguments, scope flags, text/JSON output | answer planning, evidence grouping, citation policy |
| `vault_graph.mcp` | MCP input parsing, tool registration, serialization, resource links, runtime explanation cache insertion | answer algorithms, retrieval algorithms, memory algorithms |
| existing retrieval/graph/context/memory services | evidence retrieval and projections | answer prose or final claim policy |

## 9. Core Data Contracts

`src/vault_graph/answer/answer_response.py` owns MCP-free response DTOs.

```python
from dataclasses import dataclass
from typing import Literal

from vault_graph.ingestion.vault_catalog import QueryScope

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

@dataclass(frozen=True)
class AnswerSignal:
    kind: str
    source_id: str | None
    rank: int | None
    score: float | None
    backend: str | None
    index_revision: str | None
    explanation: str

@dataclass(frozen=True)
class AnswerEvidence:
    evidence_id: str
    source_kind: AnswerEvidenceSourceKind
    vault_id: str
    document_id: str
    chunk_id: str
    path: str
    section: str | None
    anchor: str | None
    content_hash: str
    raw_sha256: str | None
    metadata_index_revision: str | None
    vault_revision: str | None
    retrieval_reason: str
    excerpt: str
    signals: tuple[AnswerSignal, ...]
    relationship_status: str | None = None
    result_id: str | None = None

@dataclass(frozen=True)
class AnswerClaim:
    claim_id: str
    text: str
    status: AnswerClaimStatus
    evidence_ids: tuple[str, ...]
    warning_codes: tuple[str, ...] = ()

@dataclass(frozen=True)
class AnswerWarning:
    code: str
    message: str
    severity: AnswerWarningSeverity
    affected_vault_ids: tuple[str, ...]
    recovery_hint: str | None = None
    evidence_ids: tuple[str, ...] = ()

@dataclass(frozen=True)
class AnswerReasoningStep:
    step_id: str
    kind: str
    service: str
    status: str
    query: str | None
    result_count: int
    kept_evidence_ids: tuple[str, ...]
    dropped_count: int = 0
    warning_codes: tuple[str, ...] = ()

@dataclass(frozen=True)
class AnswerDraft:
    answer_status: AnswerStatus
    answer: str
    claims: tuple[AnswerClaim, ...]
    warnings: tuple[AnswerWarning, ...]
    suggested_follow_up: str | None

@dataclass(frozen=True)
class AnswerResponse:
    answer_id: str
    question: str
    mode: AnswerMode
    requested_scope: QueryScope
    actual_scopes: tuple[QueryScope, ...]
    answer_status: AnswerStatus
    answer: str
    claims: tuple[AnswerClaim, ...]
    evidence: tuple[AnswerEvidence, ...]
    reasoning_trace: tuple[AnswerReasoningStep, ...]
    warnings: tuple[AnswerWarning, ...]
    suggested_follow_up: str | None
    generated_at: str
```

Validation rules:

- `answer_id`, `question`, `answer`, and `generated_at` are required.
- `actual_scopes` must be immutable and non-empty.
- `evidence_id` values are unique inside one response.
- `claim_id` values are unique inside one response.
- every `claim.evidence_ids` entry must refer to response evidence.
- claims with status `supported`, `inferred`, `partial`, `contested`, `stale`,
  or `deprecated` must carry at least one evidence ID.
- claims with status `unsupported` or `missing` may have no evidence, but must
  not be rendered as normal answer facts.
- `answer_status="supported"` requires at least one supported claim and no
  top-level error warning.
- `answer_status="insufficient_evidence"` is valid with no evidence.

## 10. Request And Plan Contracts

`src/vault_graph/answer/answer_plan.py` owns request and planning DTOs.

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

@dataclass(frozen=True)
class EvidencePlanStep:
    step_id: str
    kind: str
    query: str
    required: bool
    include_graph: bool = False
    include_cross_vault: bool = False
    limit: int = 10

@dataclass(frozen=True)
class AnswerPlan:
    request: AnswerRequest
    steps: tuple[EvidencePlanStep, ...]

@dataclass(frozen=True)
class PlannedEvidence:
    plan: AnswerPlan
    actual_scopes: tuple[QueryScope, ...]
    evidence: tuple[AnswerEvidence, ...]
    reasoning_trace: tuple[AnswerReasoningStep, ...]
    warnings: tuple[AnswerWarning, ...]
    dropped_evidence_count: int = 0
```

Request validation:

- `question.strip()` is required.
- `mode` must be `evidence-first`.
- `retrieval_limit` must be positive and capped at `50`.
- `max_evidence_tokens` must be at least `1000` and capped at `24000`.
- `include_cross_vault` is valid only when `include_graph=True` and the
  requested scope contains multiple Vault IDs.

Planner rules:

- Always create one required `search` step.
- Use `RetrievalService.search(..., output_format="json")` for search steps.
- Pass `include_graph=True` only when the request explicitly asks for graph
  evidence.
- Add optional `decision_trace` planning only when graph is requested and the
  question looks decision-oriented through deterministic keyword rules such as
  `why`, `decision`, `tradeoff`, `choose`, `adopt`, or `revisit`.
- Add optional memory projection planning only when project-memory services are
  available through dependency injection. Missing memory services produce no
  hidden fallback fact.
- Do not run indexing, store initialization, model downloads, or Vault reads.

## 11. Service Interfaces

### 11.1 AnswerService

`src/vault_graph/app/answer_service.py` owns the application boundary.

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

- validate the request;
- call `EvidencePlanner`;
- call `AnswerComposer`;
- combine `AnswerDraft`, planned evidence, reasoning trace, `answer_id`, and
  `generated_at` into an `AnswerResponse`;
- call `CitationGuard`;
- generate `answer_id` and `generated_at`;
- convert recoverable missing-evidence cases into an
  `insufficient_evidence` response;
- raise `AnswerError` only for invalid requests or unrecoverable service
  contract violations.

### 11.2 EvidencePlanner

`src/vault_graph/answer/evidence_planner.py` owns evidence collection over
existing services.

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

Use protocols for the injected services so tests can use focused fakes.

The planner may call:

- `RetrievalService.search(...)`
- `GraphRetrievalService.decision_trace(...)`
- `ProjectMemoryService.summarize(...)`
- `IssueMemoryService.open_questions(...)`

The planner must not import local SQLite stores, Chroma, rustworkx, FastMCP, or
Typer.

### 11.3 AnswerComposer

`src/vault_graph/answer/answer_composer.py` owns answer composition.

```python
class AnswerComposer(Protocol):
    def compose(self, request: AnswerRequest, evidence: PlannedEvidence) -> AnswerDraft: ...

class ExtractiveAnswerComposer:
    def compose(self, request: AnswerRequest, evidence: PlannedEvidence) -> AnswerDraft: ...
```

Default composition rules:

- use only `PlannedEvidence`;
- prefer short claim bullets over broad narratives;
- create supported claims from resolved evidence excerpts and search summaries;
- create inferred claims only when the inference is explained by graph
  relationship status or multiple evidence items;
- create partial claims when evidence supports only part of the question;
- create missing claims when the question asks for something no evidence
  supports;
- never use hosted LLMs;
- never execute, follow, or treat Vault text as instructions;
- never invent a decision, cause, actor, date, status, or next action absent
  from evidence.

If no supported or partial claim exists, return:

```text
answer_status = "insufficient_evidence"
answer = "Vault Graph does not have enough indexed evidence to answer this question."
```

with warnings and safe follow-up guidance.

### 11.4 CitationGuard

`src/vault_graph/answer/citation_guard.py` owns final validation.

```python
class CitationGuard:
    def validate(self, response: AnswerResponse) -> AnswerResponse: ...
```

Guard rules:

- reject unknown evidence IDs;
- reject supported, inferred, partial, contested, stale, or deprecated claims
  without evidence;
- reject duplicate claim IDs or evidence IDs;
- reject `answer_status="supported"` when all claims are unsupported or missing;
- downgrade `supported` to `partial` when any top-level warning has
  `severity="error"` but usable evidence remains;
- downgrade to `insufficient_evidence` when no usable evidence remains;
- preserve unsupported and missing claims only as labeled output.

### 11.5 AnswerRenderer

`src/vault_graph/answer/answer_renderer.py` owns text and JSON-safe rendering
helpers shared by CLI and MCP text mirrors.

```python
class AnswerRenderer(Protocol):
    def render_text(self, response: AnswerResponse) -> str: ...
    def render_json(self, response: AnswerResponse) -> str: ...
```

Rendering rules:

- JSON is canonical and round-trips through `AnswerResponse`.
- text output is a view over JSON and must not add facts.
- evidence lines include `vault_id`, path, section or anchor, and evidence ID.
- warnings include code, severity, affected Vault IDs, and recovery hint.
- unsupported or missing claims are visibly labeled.

## 12. Data Flow

```text
CLI or MCP request
  -> resolve QueryScope
  -> AnswerRequest
  -> AnswerService.ask(request)
     -> EvidencePlanner.plan(request)
     -> EvidencePlanner.gather(plan)
        -> RetrievalService.search(...)
        -> optional GraphRetrievalService.decision_trace(...)
        -> optional ProjectMemoryService.summarize(...)
        -> optional IssueMemoryService.open_questions(...)
        -> normalize evidence into AnswerEvidence records
        -> group by (vault_id, document_id, chunk_id)
        -> enforce max_evidence_tokens
     -> ExtractiveAnswerComposer.compose(...)
     -> AnswerService attaches evidence, trace, answer_id, and generated_at
     -> CitationGuard.validate(...)
     -> AnswerResponse
  -> CLI renderer or MCP serializer
```

Read paths:

- catalog config
- metadata store through existing retrieval and memory services
- keyword projection through retrieval service
- vector projection through retrieval service
- graph store only when graph is requested
- MCP runtime explanation cache only for current-process explainability

Write paths:

- CLI ask: no writes
- MCP ask: may write bounded in-process `ResultExplanationCache` entries only

Forbidden writes:

- Vault files
- metadata database
- keyword index
- vector store
- graph store
- projection cache
- model cache
- durable answer cache
- external memory system

## 13. Evidence Normalization

The planner converts existing service outputs into `AnswerEvidence`.

Search results:

- source kind: `search_result`
- evidence from `RetrievalResult.evidence`
- excerpt from `RetrievalResult.summary` or resolved excerpt already returned
  by retrieval
- signals from `RetrievalResult.signals`
- relationship status from `RetrievalResult.relationship_status`

Decision trace steps:

- source kind: `decision_trace`
- evidence from step evidence
- retrieval reason uses the trace role and relationship path
- contested or deprecated relationships become claim statuses or warnings

Project memory and open questions:

- source kind: `project_memory` or `open_question`
- evidence from `MemoryEvidenceRef`
- claim status starts from the memory item claim status and is mapped to
  `supported`, `partial`, or `missing` conservatively

Context packs:

- context packs are not required for the first composer;
- if reused later as a budget normalizer, context-pack evidence must be
  transformed back into `AnswerEvidence`;
- context packs must not be persisted just because `ask` ran.

Deduplication key:

```text
(vault_id, document_id, chunk_id, source_kind)
```

Evidence IDs:

```text
ev_<rank>_<short_hash(vault_id, document_id, chunk_id, source_kind)>
```

## 14. Degraded And Edge Cases

| Case | Behavior |
| --- | --- |
| Empty question | validation error `empty_question`; CLI exits nonzero; MCP returns validation error |
| Unknown Vault ID | validation error from catalog scope resolution |
| Metadata or keyword unavailable | fail as service error with recovery hint `Run vg index` |
| Healthy index but no evidence | valid `insufficient_evidence` answer |
| Vector unavailable | keyword-only evidence plus warning |
| Graph requested but unavailable | answer from non-graph evidence when possible plus graph warning |
| Cross-Vault graph requested without all-Vault scope | validation error |
| Stale vector or graph state | use only fresh evidence where possible; otherwise warn and downgrade |
| Missing evidence after candidate resolution | drop evidence and warn |
| Conflicting evidence | keep conflicting claims labeled `contested` or return `partial` |
| Deprecated relationship | do not use as supported fact; label `deprecated` if shown |
| Evidence budget exhausted | omit lower-ranked evidence and warn |
| Unsupported requested fact | return missing or unsupported claim, not invented answer prose |

## 15. CLI Implementation Notes

`src/vault_graph/cli/main.py` adds an `ask` command after `context` or after
`search` for discoverability.

The CLI may follow current helper patterns:

```python
def _answer_service(state: Path, *, include_graph: bool) -> tuple[CatalogService, VaultCatalog, AnswerService]:
    ...
```

The helper must instantiate `AnswerService` over read-only service components
only. It must not import MCP modules.

Text rendering:

```text
status: partial
answer:
  ...
claims:
  C1 supported ev_...
evidence:
  ev_... [main] wiki/decisions/graphrag.md#why
warnings:
  stale_graph ...
reasoning:
  search kept 5 of 8
follow_up:
  ...
```

JSON rendering must use `AnswerRenderer.render_json` or an equivalent
serializer over `AnswerResponse`.

## 16. MCP Implementation Notes

Modify `McpToolName` to include `ask_vault`.

Add parsing:

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

Add registry method:

```python
def ask_vault(self, request: AskVaultInput) -> McpToolBody: ...
```

Factory:

```python
class McpServiceFactory:
    def open_answer_service(self, *, include_graph: bool = False) -> AnswerService: ...
```

Serialization:

```python
def answer_response_to_payload(response: AnswerResponse) -> dict[str, object]: ...
def resource_links_for_answer(response: AnswerResponse) -> tuple[McpResourceLink, ...]: ...
def explanation_records_for_answer(response: AnswerResponse) -> tuple[ExplanationRecord, ...]: ...
```

Rules:

- normal MCP startup should not open graph dependencies;
- `include_graph=True` may lazily open graph services;
- `ask_vault` must not create stores or run indexing;
- `ask_vault` must not expose an LLM client;
- `ask_vault` must register explainable evidence records in the bounded runtime
  cache when possible.

## 17. Import Boundaries

Allowed:

- `vault_graph.answer` may import `vault_graph.ingestion.vault_catalog`,
  `vault_graph.retrieval`, `vault_graph.memory`, and `vault_graph.errors`
  types through protocols and DTOs.
- `vault_graph.app.answer_service` may import `vault_graph.answer`.
- `vault_graph.cli` may import `vault_graph.app.answer_service` and
  `vault_graph.answer.answer_plan`.
- `vault_graph.mcp` may import `vault_graph.app.answer_service`,
  `vault_graph.answer`, and MCP serializers.

Forbidden:

- `vault_graph.answer` importing `typer`, `mcp`, `chromadb`, `sqlite3`,
  `rustworkx`, or local store implementations.
- CLI importing `vault_graph.mcp`.
- MCP duplicating answer composition or citation logic.
- any answer module importing or writing Vault files directly.

## 18. Security And Safety

- Treat Vault text as untrusted input, especially for future LLM composers.
- Do not execute shell commands, follow instructions, or mutate files based on
  evidence content.
- Do not include absolute Vault paths in normal output; use Vault-relative
  paths and `vault_id`.
- Do not leak tracebacks through MCP tool payloads.
- Do not write agent config, model caches, or derived stores during ask.
- Keep hosted LLM use out of the default path.

## 19. Performance And Limits

Defaults:

- retrieval limit: `10`
- candidate limit remains owned by `RetrievalService`
- evidence token budget: `8000`
- hard retrieval limit cap: `50`
- hard evidence token cap: `24000`
- graph traversal uses existing graph service depth defaults and only runs when
  requested

Rules:

- no whole-Vault scans in answer modules;
- no direct SQLite table scans from answer modules;
- no context-pack persistence during ask;
- no background indexing;
- dedupe before excerpt budgeting;
- keep explanation-cache insertion bounded by existing MCP cache policy.

## 20. Test Plan

Add focused tests:

```text
tests/test_answer_response_contract.py
tests/test_evidence_planner.py
tests/test_answer_composer.py
tests/test_citation_guard.py
tests/test_answer_service.py
tests/test_answer_read_only_boundary.py
tests/test_answer_multi_vault.py
tests/test_answer_import_boundaries.py
tests/test_cli_ask.py
tests/test_mcp_ask_vault.py
```

Required cases:

- `AnswerRequest` rejects empty questions, invalid mode, invalid limits, and
  invalid cross-Vault graph scope.
- `EvidencePlanner` always plans search and only plans graph/decision trace
  when graph is requested.
- planner preserves `vault_id` across search, graph, and memory evidence.
- planner drops unresolved evidence with warnings.
- composer returns supported, partial, and insufficient-evidence answers.
- composer never includes claims absent from evidence fixtures.
- citation guard rejects supported claims without evidence.
- citation guard downgrades unsafe supported responses.
- CLI text output includes status, claims, evidence, warnings, reasoning, and
  follow-up.
- CLI JSON output matches `AnswerResponse`.
- MCP registers `ask_vault` only after the service exists.
- MCP `ask_vault` returns `McpToolBody` with payload, links, warnings, and text.
- answer evidence can be explained through current-process explanation records.
- `vg ask` and `ask_vault` do not mutate Vault or derived index state.
- graph unavailable with `--include-graph` degrades visibly when search evidence
  still exists.
- all-Vault ask groups and preserves evidence by Vault ID.

Regression tests:

```text
tests/test_cli_surface_boundary.py
tests/test_mcp_import_boundaries.py
tests/test_mcp_tool_read_only_boundary.py
tests/test_mcp_stdio_smoke.py
tests/test_search_read_only_boundary.py
tests/test_context_pack_read_only_boundary.py
tests/test_multi_vault_search.py
tests/test_multi_vault_graph_retrieval.py
tests/test_mcp_result_explanation_cache.py
```

Verification commands:

```bash
uv run --python 3.12 pytest
uv run --python 3.12 ruff check .
uv run --python 3.12 mypy src tests
uv run --python 3.12 vg --help
uv run --python 3.12 vg ask --help
```

## 21. Implementation Slices

### Slice A: Answer DTOs And Citation Guard

Files:

- `src/vault_graph/answer/answer_response.py`
- `src/vault_graph/answer/answer_plan.py`
- `src/vault_graph/answer/citation_guard.py`
- `src/vault_graph/errors.py`

Tests:

- `test_answer_response_contract.py`
- `test_citation_guard.py`

Exit criteria:

- answer DTO validation is deterministic;
- invalid claims are rejected or downgraded;
- no protocol adapter code is imported.

### Slice B: Evidence Planner And Extractive Composer

Files:

- `src/vault_graph/answer/evidence_planner.py`
- `src/vault_graph/answer/answer_composer.py`

Tests:

- `test_evidence_planner.py`
- `test_answer_composer.py`
- `test_answer_multi_vault.py`

Exit criteria:

- planner gathers search evidence through `RetrievalService`;
- optional graph and memory service protocols are dependency-injected;
- composer produces supported, partial, and insufficient-evidence responses.

### Slice C: AnswerService And Renderers

Files:

- `src/vault_graph/app/answer_service.py`
- `src/vault_graph/answer/answer_renderer.py`
- `src/vault_graph/answer/__init__.py`

Tests:

- `test_answer_service.py`
- `test_answer_read_only_boundary.py`
- `test_answer_import_boundaries.py`

Exit criteria:

- service orchestrates planner, composer, and guard;
- read-only boundary is proven;
- text and JSON rendering add no new facts.

### Slice D: CLI `vg ask`

Files:

- `src/vault_graph/cli/main.py`
- `tests/test_cli_ask.py`
- `tests/test_cli_surface_boundary.py`

Exit criteria:

- `vg ask` appears in `vg --help`;
- CLI validates scope and format flags;
- text and JSON outputs match the answer contract;
- command does not mutate Vault or derived state.

### Slice E: MCP `ask_vault`

Files:

- `src/vault_graph/mcp/mcp_service_factory.py`
- `src/vault_graph/mcp/mcp_tools.py`
- `src/vault_graph/mcp/mcp_answer_serialization.py`
- `src/vault_graph/mcp/mcp_tool_serialization.py`
- `tests/test_mcp_ask_vault.py`
- MCP smoke and read-only tests

Exit criteria:

- `ask_vault` is registered with structured output;
- MCP calls the same `AnswerService`;
- result explanation cache can explain returned evidence;
- MCP output preserves warnings, links, and Vault IDs.

## 22. Acceptance Criteria

The feature is accepted when a local indexed Vault can run:

```bash
vg ask "Why did we adopt GraphRAG?"
vg ask --format json "Why did we adopt GraphRAG?"
vg ask --include-graph "Why did we keep graph expansion opt-in?"
vg serve --mcp
```

and agents can call:

```text
ask_vault(question="Why did we adopt GraphRAG?")
```

with all of the following true:

- answers cite Vault-derived evidence;
- unsupported or missing claims are labeled;
- answer status is stable and machine-readable;
- evidence paths are Vault-relative and include `vault_id`;
- reasoning trace explains which services were used;
- stale or unavailable projections are visible as warnings;
- no Vault content or derived index state changes during ask;
- the answer is useful as working context but not durable knowledge.

## 23. Self-Review Notes

Security:

- Default path is local and deterministic.
- Future LLM adapters are explicitly behind `AnswerComposer` and citation guard.
- Vault text is evidence, not executable instruction.

Performance:

- Answer planning uses bounded retrieval and evidence budgets.
- Graph and memory enrichments are optional and dependency-injected.
- No full-Vault scans or background indexing are introduced.

Testability:

- Planner uses protocols and can be tested with fakes.
- Composer and guard are pure and deterministic.
- CLI and MCP are adapter tests over the same service contract.

Maintainability:

- The answer layer is a deep module.
- CLI and MCP do not duplicate answer policy.
- The response vocabulary matches SPEC and FEATURES: answer, claims, evidence,
  reasoning trace, warnings, and durable follow-up.

Open decisions:

- None. The design follows accepted project decisions and leaves hosted LLM
  composers, external memory adapters, HTTP serving, and UI as separate future
  design work.
