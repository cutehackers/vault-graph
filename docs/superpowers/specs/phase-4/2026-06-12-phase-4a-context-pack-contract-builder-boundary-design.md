# Phase 4A Context Pack Contract And Builder Boundary Design

Status: Draft for implementation planning

Date: 2026-06-12

Scope: Phase 4A only

## 1. Purpose

Phase 4A defines the context pack contract before any user-facing `vg context`
implementation. The goal is to create a stable, testable boundary that Phase 4B
CLI output and Phase 5 MCP resources can reuse without changing the pack schema.

Phase 4A implements:

- canonical `ContextPack` JSON data model
- `ContextPackBuilder` application boundary
- context pack warning model
- token and chunk budget policy
- JSON and Markdown renderer boundaries
- contract tests for schema shape, evidence references, warnings, and budget
  accounting

Phase 4A must not implement:

- `vg context`
- MCP serving
- HTTP serving
- pack persistence
- LLM answer generation
- direct SQLite, Chroma, or rustworkx access from context pack code

## 2. Design Rules

| Vault Graph value | Phase 4A design rule |
| --- | --- |
| Vault is source of truth | Context packs include evidence refs and never become durable knowledge. |
| Rebuildability | Pack output records schema, policy, scope, and store revisions needed to reproduce the same retrieval boundary. |
| Evidence over fluency | Pack fields contain evidence-backed brief items and warnings, not synthesized answers. |
| Local first | The contract assumes local stores and no hosted service dependency. |
| Simplicity before scale | No `ContextPackStore` in Phase 4A. Persistence belongs to a later serving/resource layer. |

## 3. Public Contract

The canonical artifact is JSON.

Markdown is a rendering view over the JSON. Renderers may reorder sections for
readability only if they preserve every item, evidence reference, warning,
revision, and omission marker from the JSON payload.

Required top-level fields:

```python
@dataclass(frozen=True)
class ContextPack:
    context_pack_schema_version: str
    pack_id: str
    goal: str
    scope: ContextPackScope
    vaults: tuple[ContextPackVault, ...]
    vault_revisions: tuple[ContextPackVaultRevision, ...]
    backend: ContextPackBackend
    store_revisions: tuple[ContextPackStoreRevision, ...]
    retrieval_policy_version: str
    budget: ContextPackBudget
    generated_at: str
    current_state: tuple[ContextPackItem, ...]
    relevant_pages: tuple[ContextPackItem, ...]
    relevant_sources: tuple[ContextPackItem, ...]
    decisions: tuple[ContextPackItem, ...]
    constraints: tuple[ContextPackItem, ...]
    open_questions: tuple[ContextPackItem, ...]
    warnings: tuple[ContextPackWarning, ...]
    evidence: tuple[ContextEvidence, ...]
```

`context_pack_schema_version` starts as `context-pack-v1`.

`pack_id` is a SHA-256 digest of canonical pack identity JSON with `pack_id` and
`generated_at` omitted. It is a generated artifact identity, not durable
knowledge identity. Phase 4 does not persist it by default.

Vault revisions are Vault-attributed records:

```python
@dataclass(frozen=True)
class ContextPackVaultRevision:
    vault_id: str
    revision: str | None
    revision_kind: Literal["git", "snapshot", "unknown"]
```

Scope records preserve both the user's requested scope and the actual scopes
used for store reads:

```python
@dataclass(frozen=True)
class ContextPackScope:
    requested: ContextPackRequestedScope
    actual_scopes: tuple[ContextPackActualScope, ...]

@dataclass(frozen=True)
class ContextPackRequestedScope:
    vault_ids: tuple[str, ...]
    content_scopes: tuple[str, ...]
    include_cross_vault: bool

@dataclass(frozen=True)
class ContextPackActualScope:
    vault_ids: tuple[str, ...]
    content_scopes: tuple[str, ...]
    include_cross_vault: bool
    scope_key: str
```

Store revisions are scope-attributed records rather than a single object:

```python
@dataclass(frozen=True)
class ContextPackStoreRevision:
    kind: Literal["metadata", "keyword", "vector", "graph", "projection"]
    revision: str | None
    vault_id: str | None
    scope_key: str
```

This keeps multi-vault packs inspectable and prevents a stale or missing
projection in one Vault from being confused with another Vault.

Backend records describe which backends contributed to the pack. A backend with
`used=False` must not require opening that backend.

```python
@dataclass(frozen=True)
class ContextPackBackend:
    metadata_store: ContextPackBackendUse
    keyword_index: ContextPackBackendUse
    vector_store: ContextPackBackendUse
    graph_store: ContextPackBackendUse
    graph_projection: ContextPackBackendUse

@dataclass(frozen=True)
class ContextPackBackendUse:
    name: str | None
    used: bool
```

Default keyword/vector context packs set `graph_store.used=False` and
`graph_projection.used=False`. They do not include `graph` or `projection`
store revision rows. Graph backend names and graph revisions appear only when
`include_graph=True`.

## 4. Evidence Authority

The canonical evidence reference remains:

```python
@dataclass(frozen=True)
class ContextEvidenceRef:
    vault_id: str
    document_id: str
    chunk_id: str
```

Every normal item that makes a factual claim must include at least one
`ContextEvidenceRef`.

Evidence details are resolved from `MetadataStore` and represented once in the
top-level `evidence` list:

```python
@dataclass(frozen=True)
class ContextEvidence:
    ref: ContextEvidenceRef
    path: str
    section: str | None
    anchor: str | None
    content_hash: str
    raw_sha256: str | None
    metadata_index_revision: str
    vault_revision: str | None
    excerpt: str
    excerpt_token_count: int
    truncated: bool
    retrieval_reasons: tuple[str, ...]
    warnings: tuple[ContextPackWarning, ...]
```

Pack items reference evidence by `(vault_id, document_id, chunk_id)` instead of
duplicating evidence text.

The builder creates `ContextEvidence` from a raw resolved evidence snapshot plus
retrieval and budget decisions. The resolver must not fill builder-owned fields
such as `retrieval_reasons`, `warnings`, `excerpt`, or `truncated`.

## 5. Item Model

`ContextPackItem` is a section-neutral brief item. Section placement explains
how the builder classified it.

```python
@dataclass(frozen=True)
class ContextPackItem:
    item_id: str
    item_type: Literal[
        "current_state",
        "page",
        "source",
        "decision",
        "constraint",
        "open_question",
    ]
    title: str
    summary: str
    evidence_refs: tuple[ContextEvidenceRef, ...]
    retrieval_signals: tuple[ContextPackSignal, ...]
    relationship_status: str | None
    rank: int
    warnings: tuple[ContextPackWarning, ...]
```

`summary` must be extractive or template-based in Phase 4A/4B. It must not be an
LLM-generated answer.

## 6. Signal Model

Signals preserve why an item entered the pack.

```python
@dataclass(frozen=True)
class ContextPackSignal:
    kind: Literal["keyword", "vector", "graph"]
    rank: int | None
    score: float | None
    explanation: str
```

Backend-native scores are not compared directly. The builder consumes the
ranked `SearchResponse` produced by `RetrievalService`.

## 7. Warning Model

Warnings are first-class records.

```python
@dataclass(frozen=True)
class ContextPackWarning:
    code: str
    severity: Literal["info", "warning", "error"]
    message: str
    affected_vault_ids: tuple[str, ...]
    evidence_refs: tuple[ContextEvidenceRef, ...]
    scope_key: str | None
    source_code: str | None
    source_kind: Literal["retrieval", "graph", "budget", "builder"] | None
    entity_id: str | None
    relationship_id: str | None
    evidence_ref_id: str | None
    recovery_hint: str | None
```

Required warning codes:

| Code | When |
| --- | --- |
| `metadata_unavailable` | required metadata projection cannot be opened |
| `search_degraded` | retrieval returned results with degraded keyword/vector behavior |
| `graph_unavailable` | graph was requested but graph state is missing or incompatible |
| `target_not_found` | graph target could not be resolved |
| `ambiguous_graph_target` | graph target matched multiple equal-rank entities |
| `topic_not_durable_decision` | decision trace target is a topic, not a durable `Decision` entity |
| `graph_stale` | graph readiness or retrieval reported stale graph state |
| `graph_empty` | graph lookup found no related graph records |
| `graph_target_scan_truncated` | target scan exceeded bounded lookup limits |
| `graph_relationship_read_truncated` | relationship read exceeded bounded lookup limits |
| `graph_projection_truncated` | graph traversal exceeded the Phase 3C projection budget |
| `cross_vault_relationship_omitted` | cross-Vault graph relationships were omitted because cross-Vault mode was not explicit |
| `graph_evidence_missing` | graph relationship evidence could not be resolved |
| `deprecated_relationship_omitted` | deprecated relationships were omitted from graph results |
| `missing_evidence` | a candidate references evidence that `MetadataStore` cannot resolve |
| `stale_projection` | metadata, vector, or graph revision is stale for the requested scope |
| `contested_relationship` | graph relationship status is contested |
| `deprecated_relationship` | graph relationship status is deprecated |
| `budget_omitted` | a section or item was omitted to fit the budget |
| `excerpt_truncated` | an evidence excerpt was shortened |
| `unsupported_scope` | requested scope cannot be represented by the current pack builder |

Warnings tied to a Vault must include `affected_vault_ids`. Warnings tied to
evidence should also include `evidence_refs`.

Warning conversion preserves original warning identity:

| Source warning | Context pack code | Preservation rule |
| --- | --- | --- |
| `vector_query_failed` | `search_degraded` | keep `source_code="vector_query_failed"` |
| `vector_stale` | `stale_projection` | keep affected Vault IDs and evidence refs when available |
| `keyword_index_unavailable` | `search_degraded` | applies only if retrieval returns it as a warning; fatal `SearchError` remains fatal |
| `graph_query_failed` | `graph_unavailable` | keep `source_code="graph_query_failed"` |
| `graph_missing` | `graph_unavailable` | keep graph recovery hint |
| `graph_stale` | `graph_stale` | preserve source code and scope key |
| `target_not_found` or `graph_target_not_found` | `target_not_found` | preserve target lookup identity |
| `ambiguous_graph_target` | `ambiguous_graph_target` | preserve candidates when renderer supports them; otherwise preserve source code |
| `topic_not_durable_decision` | `topic_not_durable_decision` | preserve entity ID when provided |
| `graph_empty` | `graph_empty` | preserve source code for missing or empty graph state; message and recovery hint disambiguate |
| `graph_target_scan_truncated` | `graph_target_scan_truncated` | preserve bounded scan warning |
| `graph_relationship_read_truncated` | `graph_relationship_read_truncated` | preserve bounded relationship read warning |
| `graph_projection_truncated` | `graph_projection_truncated` | preserve projection warning identity |
| `cross_vault_relationship_omitted` | `cross_vault_relationship_omitted` | preserve omitted cross-Vault attribution |
| `graph_evidence_missing` | `graph_evidence_missing` | preserve relationship or evidence IDs when provided |
| `deprecated_relationship_omitted` | `deprecated_relationship_omitted` | preserve omitted deprecated relationship identity |

Any graph warning not listed here must still become a `ContextPackWarning` with
the original graph warning code as both `code` and `source_code`, unless a later
accepted design explicitly normalizes it. This prevents Phase 4 from losing
Phase 3C warning identity as graph retrieval evolves.

## 8. Budget Policy

Public `max_tokens` means estimated context tokens for excerpt-bearing content.
It is based on `ChunkSnapshot.token_count` and deterministic truncation, not a
model-specific tokenizer.

Default Phase 4 budget:

```python
@dataclass(frozen=True)
class ContextPackBudget:
    max_tokens: int = 8000
    max_evidence_items: int = 24
    max_excerpt_tokens: int = 320
    used_tokens: int = 0
    omitted_items: int = 0
```

Budget rules:

1. Required metadata, scope, backend, revisions, and warnings are never omitted.
2. Evidence metadata is preserved even when excerpts are truncated.
3. Normal items are packed in deterministic priority order.
4. If an item does not fit, omit it and add `budget_omitted`.
5. If an excerpt is too large, truncate it at a deterministic word boundary and
   add `excerpt_truncated`.
6. Duplicate evidence refs are represented once in top-level `evidence`.
7. The builder stops after `max_evidence_items` normal evidence entries.

Default priority order:

1. warnings and recovery hints
2. durable decisions
3. constraints
4. open questions
5. current state
6. relevant pages
7. relevant sources
8. optional graph-related evidence

The order intentionally favors durable project memory over raw supporting
material. It can be revised later through `retrieval_policy_version`.

## 9. Graph Policy

Graph signals are opt-in.

Phase 4A request options:

```python
@dataclass(frozen=True)
class ContextPackRequest:
    goal: str
    requested_scope: QueryScope
    budget: ContextPackBudget
    retrieval_limit: int = 10
    include_graph: bool = False
    include_cross_vault: bool = False
```

Rules:

- `include_graph=False` uses keyword/vector retrieval only.
- `include_graph=True` may add graph signals through the same
  `RetrievalService` graph candidate provider introduced in Phase 3C.
- `include_cross_vault=True` is valid only when `include_graph=True`, the
  requested scope already has `include_cross_vault=True`, and the requested
  scope includes multiple Vault IDs.
- `ContextPackRequest.include_cross_vault` and
  `ContextPackRequest.requested_scope.include_cross_vault` must match so the
  builder has one explicit cross-Vault state.
- If graph is requested and unavailable, the pack may still succeed with
  keyword/vector evidence plus `graph_unavailable`.
- `retrieval_limit` is passed to `RetrievalService.search(...)` before section
  classification.

## 10. Builder Boundary

`ContextPackBuilder` is an application service.

The implementation package is `vault_graph.context`. This keeps context-pack
DTOs, warning conversion, budget packing, serialization, and rendering out of
the lower-level retrieval package while still depending on retrieval services
through a narrow boundary.

```python
class ContextPackBuilder(Protocol):
    def build(self, request: ContextPackRequest) -> ContextPack: ...
```

Dependencies:

- `VaultCatalog`
- `RetrievalService`
- `ContextEvidenceResolver`
- clock function for `generated_at`

Evidence resolver boundary:

```python
class ContextEvidenceResolver(Protocol):
    def resolve(self, ref: ContextEvidenceRef) -> ResolvedContextEvidence | None: ...

@dataclass(frozen=True)
class ResolvedContextEvidence:
    ref: ContextEvidenceRef
    path: str
    section: str | None
    anchor: str | None
    content_hash: str
    raw_sha256: str | None
    metadata_index_revision: str
    vault_revision: str | None
    text: str
    token_count: int
```

The local resolver may use `MetadataStore.resolve_chunk(...)` and
`MetadataStore.resolve_chunk_evidence(...)` through the `MetadataStore`
interface. It must not depend on `SQLiteMetadataStore`.

`ContextPackBuilder` converts `ResolvedContextEvidence` into `ContextEvidence`
by applying excerpt truncation, token accounting, retrieval reasons, and
evidence-level warnings.

Renderer boundary:

```python
class ContextPackRenderer(Protocol):
    def render_json(self, pack: ContextPack) -> str: ...
    def render_markdown(self, pack: ContextPack) -> str: ...
```

Renderers may serialize and format only. They must not select evidence, change
budget decisions, or suppress warnings.

Forbidden dependencies:

- `SQLiteMetadataStore`
- `SQLiteGraphStore`
- `ChromaVectorStore`
- `RustworkxGraphProjection`
- filesystem writes under registered Vault roots
- LLM clients

## 11. JSON Serialization

JSON output must be stable:

- sorted object keys where practical
- deterministic tuple/list ordering
- ISO-8601 `generated_at`
- explicit `null` for optional fields that are part of the schema
- no backend-specific raw records

The JSON serializer is the contract test target. Markdown tests should compare
against the JSON-derived data, not independently reconstructed content.

## 12. Error Handling

Fatal errors:

- empty `goal`
- invalid `QueryScope`
- invalid budget values
- unsupported output format
- metadata store unavailable before any evidence can be resolved

Non-fatal warnings:

- vector unavailable with keyword fallback
- graph unavailable when explicitly requested
- stale store revisions
- missing evidence for individual candidates
- truncation and omission
- contested or deprecated relationship status

Fatal errors should produce nonzero CLI exits in Phase 4B. Non-fatal warnings
remain in `ContextPack.warnings`.

## 13. Tests Required Before Implementation

Phase 4A implementation must include tests for:

- JSON contract includes every required top-level field.
- `docs/SPEC.md`, `docs/FEATURES.md`, and Phase 4A DTOs agree on one
  canonical schema.
- Every normal item references at least one evidence chunk.
- Evidence refs are Vault-scoped and do not collide across Vaults.
- Store revisions include `keyword` for default keyword/vector packs.
- Graph and projection revisions are absent unless graph mode is explicit.
- Markdown renderer cannot hide top-level warnings.
- Renderer tests use `ContextPackRenderer`; CLI must not format pack sections
  directly.
- Evidence resolver tests prove excerpts and token counts come from
  `MetadataStore` interfaces.
- Budget omission and truncation produce warnings.
- Budget output includes `used_tokens` and `omitted_items`.
- `ContextPackRequest.retrieval_limit` is passed to retrieval.
- `include_graph=False` does not open graph retrieval dependencies.
- `include_graph=True` preserves graph warnings in context pack output.
- Source warning codes are preserved during context warning conversion.
- Builder depends on retrieval and storage interfaces, not local backend
  implementations.
- Context pack code does not write Vault files.

## 14. Handoff To Phase 4B

Phase 4B may implement `vg context` only after Phase 4A contract tests are
stable. The CLI should call `ContextPackBuilder.build(...)` and render either
canonical JSON or Markdown. It must not assemble sections directly in CLI code.
