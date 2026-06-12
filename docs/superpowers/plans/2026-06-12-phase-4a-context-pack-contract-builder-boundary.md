# Phase 4A Context Pack Contract And Builder Boundary Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the Phase 4A context-pack Python contract, JSON/Markdown renderer boundary, warning conversion, evidence resolver, budget policy, and non-CLI builder boundary that Phase 4B can wire to `vg context`.

**Architecture:** Add a new `vault_graph.context` package as the deep module that owns context-pack DTOs, deterministic serialization, warning normalization, evidence resolution, budget packing, and the `ContextPackBuilder` boundary. The builder consumes existing `RetrievalService.search(...)` and `MetadataStore` interfaces only; it must not import concrete SQLite, Chroma, rustworkx, CLI, MCP, HTTP, or LLM code.

**Tech Stack:** Python 3.12, frozen dataclasses, Protocol interfaces, standard `json`, `hashlib.sha256`, `datetime.UTC`, pytest, ruff, mypy.

---

## Source Documents

Read these before implementation:

- `AGENTS.md`
- `docs/SPEC.md`
- `docs/FEATURES.md`
- `docs/DESIGN.md`
- `docs/DECISIONS.md`
- `docs/CONVENTIONS.md`
- `docs/superpowers/specs/phase-4/README.md`
- `docs/superpowers/specs/phase-4/2026-06-12-phase-4-context-pack-overview-design.md`
- `docs/superpowers/specs/phase-4/2026-06-12-phase-4a-context-pack-contract-builder-boundary-design.md`

The user prompt may mention `docs/superpowers/spec/phase-4/`; the actual repository path is `docs/superpowers/specs/phase-4/`.

## Scope Guardrails

Phase 4A implements only:

- canonical `ContextPack` JSON DTOs
- immutable scope, vault, backend, revision, item, signal, warning, evidence, budget, and request records
- `ContextPackBuilder` Protocol
- concrete `SearchContextPackBuilder` that converts `RetrievalService.search(...)` output into the Phase 4A DTO
- `ContextEvidenceResolver` Protocol
- concrete `MetadataContextEvidenceResolver` that reads through `MetadataStore`
- warning conversion from search, retrieval, and graph warning DTOs
- deterministic budget packing, excerpt truncation, and omitted-item warnings
- stable JSON serialization and `pack_id` generation
- Markdown renderer boundary that proves warnings cannot be hidden
- contract, builder, renderer, read-only, multi-vault, and import-boundary tests

Phase 4A must not implement:

- `vg context`
- MCP serving
- HTTP serving
- durable pack persistence or `ContextPackStore`
- answer synthesis
- LLM summaries
- direct imports from `vault_graph.storage.local`
- direct imports from `vault_graph.projection.rustworkx_projection`
- direct imports from Chroma, SQLite concrete stores, or rustworkx in context-pack code
- writes under registered Vault roots

Release-ready Phase 4A means Python callers can build and render a context pack through:

```python
request = ContextPackRequest(
    goal="Implement GraphRAG MVP",
    requested_scope=catalog.default_scope(),
)
pack = builder.build(request)
renderer = DefaultContextPackRenderer()
json_text = renderer.render_json(pack)
markdown_text = renderer.render_markdown(pack)
```

without any CLI command being added.

## Directory And File Structure

Create:

- `src/vault_graph/context/__init__.py`: public context package exports.
- `src/vault_graph/context/context_pack.py`: canonical DTOs, literals, constants, validation helpers, and `ContextPackRequest`.
- `src/vault_graph/context/context_pack_serialization.py`: stable conversion to JSON-compatible dictionaries, deterministic JSON rendering, and `pack_id` generation.
- `src/vault_graph/context/context_pack_warnings.py`: conversion from search, retrieval, and graph warnings into `ContextPackWarning`.
- `src/vault_graph/context/context_pack_builder.py`: `ContextPackBuilder`, `ContextRetrievalService`, `ContextEvidenceResolver`, `ResolvedContextEvidence`, `MetadataContextEvidenceResolver`, and `SearchContextPackBuilder`.
- `src/vault_graph/context/context_pack_renderer.py`: `ContextPackRenderer` and `DefaultContextPackRenderer`.
- `tests/test_context_pack_contract.py`
- `tests/test_context_pack_serialization.py`
- `tests/test_context_pack_docs_contract.py`
- `tests/test_context_pack_warnings.py`
- `tests/test_context_pack_evidence_budget.py`
- `tests/test_context_pack_builder.py`
- `tests/test_context_pack_import_boundaries.py`
- `tests/test_context_pack_read_only_boundary.py`

Modify:

- `src/vault_graph/errors.py`: add `ContextPackError`.
- `tests/test_package_import.py`: add a smoke import for `vault_graph.context` exports if the existing test already checks public packages.

Do not modify:

- `src/vault_graph/cli/main.py`
- `src/vault_graph/retrieval/retrieval_service.py`
- `src/vault_graph/storage/local/*`
- `docs/DECISIONS.md`

Only update `docs/PATCH_LOG.md` if review or verification reveals a concrete correction to this implementation plan or to design alignment.

## Component And Interface Spec

### `src/vault_graph/errors.py`

Add:

```python
class ContextPackError(VaultGraphError):
    """Raised when context pack contracts are violated."""
```

### `src/vault_graph/context/context_pack.py`

Define constants and literals:

```python
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from vault_graph.errors import ContextPackError
from vault_graph.ingestion.vault_catalog import QueryScope

CONTEXT_PACK_SCHEMA_VERSION = "context-pack-v1"
DEFAULT_CONTEXT_MAX_TOKENS = 8000
DEFAULT_CONTEXT_MAX_EVIDENCE_ITEMS = 24
DEFAULT_CONTEXT_MAX_EXCERPT_TOKENS = 320
DEFAULT_CONTEXT_RETRIEVAL_LIMIT = 10
DEFAULT_RETRIEVAL_POLICY_VERSION = "retrieval-policy-v1"

ContextPackRevisionKind = Literal["git", "snapshot", "unknown"]
ContextPackStoreRevisionKind = Literal["metadata", "keyword", "vector", "graph", "projection"]
ContextPackItemType = Literal["current_state", "page", "source", "decision", "constraint", "open_question"]
ContextPackSignalKind = Literal["keyword", "vector", "graph"]
ContextPackWarningSeverity = Literal["info", "warning", "error"]
ContextPackWarningSourceKind = Literal["retrieval", "graph", "budget", "builder"]
```

Create these frozen dataclasses exactly:

```python
@dataclass(frozen=True)
class ContextPackVault:
    vault_id: str
    display_name: str


@dataclass(frozen=True)
class ContextPackVaultRevision:
    vault_id: str
    revision: str | None
    revision_kind: ContextPackRevisionKind


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


@dataclass(frozen=True)
class ContextPackScope:
    requested: ContextPackRequestedScope
    actual_scopes: tuple[ContextPackActualScope, ...]


@dataclass(frozen=True)
class ContextPackStoreRevision:
    kind: ContextPackStoreRevisionKind
    revision: str | None
    vault_id: str | None
    scope_key: str


@dataclass(frozen=True)
class ContextPackBackendUse:
    name: str | None
    used: bool


@dataclass(frozen=True)
class ContextPackBackend:
    metadata_store: ContextPackBackendUse
    keyword_index: ContextPackBackendUse
    vector_store: ContextPackBackendUse
    graph_store: ContextPackBackendUse
    graph_projection: ContextPackBackendUse


@dataclass(frozen=True)
class ContextEvidenceRef:
    vault_id: str
    document_id: str
    chunk_id: str


@dataclass(frozen=True)
class ContextPackWarning:
    code: str
    severity: ContextPackWarningSeverity
    message: str
    affected_vault_ids: tuple[str, ...]
    evidence_refs: tuple[ContextEvidenceRef, ...] = ()
    scope_key: str | None = None
    source_code: str | None = None
    source_kind: ContextPackWarningSourceKind | None = None
    entity_id: str | None = None
    relationship_id: str | None = None
    evidence_ref_id: str | None = None
    recovery_hint: str | None = None


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


@dataclass(frozen=True)
class ContextPackSignal:
    kind: ContextPackSignalKind
    rank: int | None
    score: float | None
    explanation: str


@dataclass(frozen=True)
class ContextPackItem:
    item_id: str
    item_type: ContextPackItemType
    title: str
    summary: str
    evidence_refs: tuple[ContextEvidenceRef, ...]
    retrieval_signals: tuple[ContextPackSignal, ...]
    relationship_status: str | None
    rank: int
    warnings: tuple[ContextPackWarning, ...]


@dataclass(frozen=True)
class ContextPackBudget:
    max_tokens: int = DEFAULT_CONTEXT_MAX_TOKENS
    max_evidence_items: int = DEFAULT_CONTEXT_MAX_EVIDENCE_ITEMS
    max_excerpt_tokens: int = DEFAULT_CONTEXT_MAX_EXCERPT_TOKENS
    used_tokens: int = 0
    omitted_items: int = 0


@dataclass(frozen=True)
class ContextPackRequest:
    goal: str
    requested_scope: QueryScope
    budget: ContextPackBudget = ContextPackBudget()
    retrieval_limit: int = DEFAULT_CONTEXT_RETRIEVAL_LIMIT
    include_graph: bool = False
    include_cross_vault: bool = False


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

Validation rules:

- `ContextPackRequest.goal.strip()` must be non-empty.
- `ContextPackRequest.retrieval_limit` must be positive.
- `include_cross_vault` and `requested_scope.include_cross_vault` must match. This makes the request flag and scope flag one explicit cross-Vault state instead of two conflicting sources of truth.
- `include_cross_vault=True` is valid only when `include_graph=True`, `requested_scope.include_cross_vault=True`, and `len(requested_scope.vault_ids) > 1`.
- Phase 4A must not infer all-Vault intent from `len(requested_scope.vault_ids) > 1`. Phase 4B CLI/request construction is responsible for creating a cross-Vault `QueryScope` only from explicit all-Vault plus cross-Vault flags.
- `ContextPackBudget.max_tokens`, `max_evidence_items`, and `max_excerpt_tokens` must be positive.
- `ContextPackBudget.used_tokens` and `omitted_items` must not be negative.
- `ContextPackItem.evidence_refs` must not be empty.
- `ContextEvidence.excerpt_token_count` must not be negative.
- `ContextEvidence.truncated=True` requires an item-level or evidence-level `excerpt_truncated` warning.
- `ContextPack.context_pack_schema_version` must equal `CONTEXT_PACK_SCHEMA_VERSION`.
- `ContextPack.pack_id` may be empty only while computing the final pack identity.

Add helpers:

```python
def context_scope_from_query_scopes(
    *,
    requested_scope: QueryScope,
    actual_scopes: tuple[QueryScope, ...],
) -> ContextPackScope: ...


def scope_key(scope: QueryScope) -> str: ...
```

`scope_key(QueryScope(vault_ids=("main",), content_scopes=("wiki", "docs"), include_cross_vault=False))` must return `main:wiki,docs:local`. Cross-Vault scopes must use the suffix `cross-vault`.

Scope-key policy:

- `ContextPackActualScope.scope_key` uses the Phase 4A helper format above.
- `ContextPackStoreRevision.scope_key` preserves `SearchStoreRevision.scope_key` exactly as returned by the search/readiness layer.
- Do not normalize store revision keys into context scope keys. They identify the source store revision scope, not the rendered pack scope.

### `src/vault_graph/context/context_pack_serialization.py`

Create:

```python
from __future__ import annotations

import dataclasses
import hashlib
import json
from dataclasses import replace
from typing import Any

from vault_graph.context.context_pack import ContextPack


def context_pack_to_dict(pack: ContextPack) -> dict[str, Any]: ...


def render_context_pack_json(pack: ContextPack) -> str: ...


def context_pack_identity_dict(pack: ContextPack) -> dict[str, Any]: ...


def compute_pack_id(pack: ContextPack) -> str: ...


def with_computed_pack_id(pack: ContextPack) -> ContextPack: ...
```

Rules:

- `context_pack_to_dict` recursively converts only approved context-pack DTO classes and tuples to JSON-compatible dictionaries and lists.
- Serialization must fail closed with `ContextPackError` for unknown dataclasses, `pathlib.Path`, bytes, backend-native records, or any object outside the context-pack DTO whitelist.
- Optional fields must remain present with `None` values.
- `render_context_pack_json` uses `json.dumps(..., ensure_ascii=False, sort_keys=True, indent=2) + "\n"`.
- `context_pack_identity_dict` removes only top-level `pack_id` and `generated_at`, and reuses the same whitelisted conversion path as `context_pack_to_dict`.
- `compute_pack_id` hashes the canonical identity JSON with SHA-256 and returns the hex digest.
- `with_computed_pack_id` returns `dataclasses.replace(pack, pack_id=compute_pack_id(pack))`.

### `src/vault_graph/context/context_pack_warnings.py`

Create:

```python
from __future__ import annotations

from vault_graph.context.context_pack import ContextEvidenceRef, ContextPackWarning
from vault_graph.retrieval.graph_retrieval import GraphRetrievalWarning
from vault_graph.retrieval.retrieval_result import RetrievalWarning
from vault_graph.retrieval.search_response import SearchWarning
from vault_graph.storage.interfaces.metadata_store import EvidenceReference
```

Implement:

```python
def evidence_ref_from_metadata(reference: EvidenceReference) -> ContextEvidenceRef: ...


def context_warning_from_search(warning: SearchWarning) -> ContextPackWarning: ...


def context_warning_from_retrieval(
    warning: RetrievalWarning,
    *,
    fallback_vault_id: str,
    evidence_refs: tuple[ContextEvidenceRef, ...] = (),
) -> ContextPackWarning: ...


def context_warning_from_graph(warning: GraphRetrievalWarning) -> ContextPackWarning: ...


def budget_warning(
    *,
    code: str,
    message: str,
    affected_vault_ids: tuple[str, ...],
    evidence_refs: tuple[ContextEvidenceRef, ...] = (),
    scope_key: str | None = None,
) -> ContextPackWarning: ...


def builder_warning(
    *,
    code: str,
    message: str,
    affected_vault_ids: tuple[str, ...],
    evidence_refs: tuple[ContextEvidenceRef, ...] = (),
    scope_key: str | None = None,
    recovery_hint: str | None = None,
) -> ContextPackWarning: ...
```

Warning mapping:

```python
SEARCH_WARNING_CODE_MAP = {
    "vector_query_failed": "search_degraded",
    "vector_stale": "stale_projection",
    "keyword_index_unavailable": "search_degraded",
    "vector_unavailable": "search_degraded",
    "embedding_model_unavailable": "search_degraded",
    "degraded_keyword_only": "search_degraded",
    "missing_evidence": "missing_evidence",
}

GRAPH_WARNING_CODE_MAP = {
    "graph_query_failed": "graph_unavailable",
    "graph_missing": "graph_unavailable",
    "graph_unavailable": "graph_unavailable",
    "graph_stale": "graph_stale",
    "target_not_found": "target_not_found",
    "graph_target_not_found": "target_not_found",
    "ambiguous_graph_target": "ambiguous_graph_target",
    "topic_not_durable_decision": "topic_not_durable_decision",
    "graph_empty": "graph_empty",
    "graph_target_scan_truncated": "graph_target_scan_truncated",
    "graph_relationship_read_truncated": "graph_relationship_read_truncated",
    "graph_projection_truncated": "graph_projection_truncated",
    "cross_vault_relationship_omitted": "cross_vault_relationship_omitted",
    "graph_evidence_missing": "graph_evidence_missing",
    "deprecated_relationship_omitted": "deprecated_relationship_omitted",
}
```

Preservation rules:

- Converted warnings must set `source_code` to the original code.
- Search conversions must set `source_kind="retrieval"`.
- Graph conversions must set `source_kind="graph"`.
- Budget conversions must set `source_kind="budget"`.
- Builder conversions must set `source_kind="builder"`.
- Unknown graph warning codes must preserve the same value as both `code` and `source_code`.
- `SearchWarning.document_id` and `SearchWarning.chunk_id` produce a `ContextEvidenceRef` only when both are present and `affected_vault_ids` contains exactly one Vault ID.
- Multi-vault search warnings must not guess an evidence ref. Preserve every `affected_vault_id` and leave `evidence_refs=()`.
- `RetrievalWarning` records from individual `RetrievalResult` rows must be converted to `ContextPackWarning` and attached to the corresponding `ContextPackItem.warnings`.
- If an item is omitted by budget, promote its result-level warnings to top-level context-pack warnings so warning identity is not lost.
- `SearchError` from `RetrievalService.search(...)` remains fatal and is not converted into a successful `ContextPackWarning`. This preserves existing fatal behavior for metadata and keyword projection unavailability.

### `src/vault_graph/context/context_pack_builder.py`

Create:

```python
from __future__ import annotations

import hashlib
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from typing import Protocol

from vault_graph.context.context_pack import (
    DEFAULT_RETRIEVAL_POLICY_VERSION,
    ContextEvidence,
    ContextEvidenceRef,
    ContextPack,
    ContextPackBackend,
    ContextPackBackendUse,
    ContextPackBudget,
    ContextPackItem,
    ContextPackRequest,
    ContextPackSignal,
    ContextPackStoreRevision,
    ContextPackVault,
    ContextPackVaultRevision,
    context_scope_from_query_scopes,
    scope_key,
)
from vault_graph.context.context_pack_serialization import with_computed_pack_id
from vault_graph.context.context_pack_warnings import (
    budget_warning,
    builder_warning,
    context_warning_from_retrieval,
    context_warning_from_search,
    evidence_ref_from_metadata,
)
from vault_graph.ingestion.vault_catalog import QueryScope, VaultCatalog
from vault_graph.retrieval.retrieval_result import RetrievalResult
from vault_graph.retrieval.search_response import SearchOutputFormat, SearchResponse
from vault_graph.storage.interfaces.metadata_store import MetadataStore
```

Define:

```python
class ContextPackBuilder(Protocol):
    def build(self, request: ContextPackRequest) -> ContextPack: ...


class ContextRetrievalService(Protocol):
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

Implement `MetadataContextEvidenceResolver`:

```python
class MetadataContextEvidenceResolver:
    def __init__(self, *, metadata_store: MetadataStore) -> None:
        self._metadata_store = metadata_store

    def resolve(self, ref: ContextEvidenceRef) -> ResolvedContextEvidence | None:
        chunk = self._metadata_store.resolve_chunk(vault_id=ref.vault_id, chunk_id=ref.chunk_id)
        evidence = self._metadata_store.resolve_chunk_evidence(
            vault_id=ref.vault_id,
            document_id=ref.document_id,
            chunk_id=ref.chunk_id,
        )
        if chunk is None or evidence is None:
            return None
        metadata_revision = evidence.metadata_index_revision or chunk.index_revision
        if metadata_revision is None:
            metadata_revision = "unknown"
        return ResolvedContextEvidence(
            ref=ref,
            path=evidence.path,
            section=evidence.section,
            anchor=evidence.anchor,
            content_hash=evidence.content_hash,
            raw_sha256=evidence.raw_sha256,
            metadata_index_revision=metadata_revision,
            vault_revision=evidence.vault_revision,
            text=chunk.text,
            token_count=chunk.token_count,
        )
```

Implement `SearchContextPackBuilder`:

```python
class SearchContextPackBuilder:
    def __init__(
        self,
        *,
        catalog: VaultCatalog,
        retrieval_service: ContextRetrievalService,
        evidence_resolver: ContextEvidenceResolver,
        clock: Callable[[], datetime] | None = None,
        retrieval_policy_version: str = DEFAULT_RETRIEVAL_POLICY_VERSION,
    ) -> None: ...

    def build(self, request: ContextPackRequest) -> ContextPack: ...
```

Build flow:

1. Call `ContextRetrievalService.search(...)` exactly once:

```python
response = self._retrieval_service.search(
    query_text=request.goal,
    requested_scope=request.requested_scope,
    limit=request.retrieval_limit,
    output_format="json",
    include_graph=request.include_graph,
    include_cross_vault=request.include_cross_vault,
)
```

2. Convert `response.requested_scope` and `response.actual_scopes` to `ContextPackScope`.
3. Convert catalog entries referenced by `response.actual_scopes` to `ContextPackVault`.
4. Convert `response.store_revisions` to `ContextPackStoreRevision`, preserving `kind`, `revision`, `vault_id`, and `scope_key`.
5. Build `ContextPackBackend` from response evidence:
   - metadata store: `name="metadata"`, `used=True`
   - keyword index: use the first keyword signal backend when present, otherwise `name="keyword"`, `used=True`
   - vector store: use the first vector signal backend when present, otherwise `name="vector"` when a vector revision exists; `used=True` only when a vector signal or vector store revision exists
   - graph store: use the first graph signal backend when present, otherwise `name="graph"` when a graph revision exists; `used=True` only when `request.include_graph=True` and a graph signal or graph store revision exists
   - graph projection: `name="projection"` and `used=True` only when `request.include_graph=True` and a projection store revision exists
6. Convert top-level `SearchWarning` records to `ContextPackWarning`.
7. Convert each `RetrievalResult.warnings` record to item-level `ContextPackWarning`.
8. Pre-plan ranked items from `RetrievalResult` rows without resolving chunk text yet.
9. Deduplicate candidate evidence refs by `(vault_id, document_id, chunk_id)` before resolver calls.
10. Resolve evidence refs in ranked order only until `max_evidence_items` or `max_tokens` is reached.
11. Cache resolved evidence inside one build so duplicate refs call the resolver at most once.
12. Convert each kept `RetrievalResult` into one `ContextPackItem`.
13. Omit an item when none of its evidence can be resolved; add a `missing_evidence` builder warning with affected Vault IDs and the unresolved refs.
14. Enforce `max_evidence_items`, `max_tokens`, and `max_excerpt_tokens`.
15. Produce `ContextEvidence` once per `(vault_id, document_id, chunk_id)`.
16. Compute `ContextPackBudget.used_tokens` and `omitted_items`.
17. Set `generated_at` from the injected clock or `datetime.now(UTC)`.
18. Create the pack with `pack_id=""`, then return `with_computed_pack_id(pack)`.

Classification:

```python
def _item_type(result: RetrievalResult) -> ContextPackItemType:
    if result.kind == "decision":
        return "decision"
    if result.kind == "constraint":
        return "constraint"
    if result.kind == "open_question":
        return "open_question"
    if result.evidence and result.evidence[0].path.startswith("raw/"):
        return "source"
    return "page"
```

Place items by type:

- `decision` -> `decisions`
- `constraint` -> `constraints`
- `open_question` -> `open_questions`
- `source` -> `relevant_sources`
- `page` -> `relevant_pages`
- `current_state` is empty in Phase 4A because current-state synthesis belongs to later context-pack enrichment

Signal conversion:

```python
ContextPackSignal(
    kind=signal.kind,
    rank=signal.rank,
    score=signal.score,
    explanation=signal.explanation,
)
```

Item IDs:

```python
def _item_id(result: RetrievalResult, item_type: str) -> str:
    identity = "|".join(
        [item_type, result.result_id]
        + [f"{ref.vault_id}:{ref.document_id}:{ref.chunk_id}" for ref in result.evidence]
    )
    return hashlib.sha256(identity.encode("utf-8")).hexdigest()
```

Budget behavior:

- Iterate response results in rank order.
- Treat the first unresolved evidence ref on an item as a warning but keep the item if at least one evidence ref resolves.
- If `len(evidence_by_ref) == max_evidence_items`, omit remaining items and add one aggregate `budget_omitted` warning for the evidence-item limit.
- If adding an evidence excerpt would exceed `max_tokens`, omit that item and add one aggregate `budget_omitted` warning for token-budget omissions.
- If resolved evidence `token_count > max_excerpt_tokens`, truncate `text` to `max_excerpt_tokens` whitespace-delimited tokens and add `excerpt_truncated` to both evidence warnings and pack warnings.
- `used_tokens` is the sum of included `ContextEvidence.excerpt_token_count`.
- `omitted_items` is the total number of omitted ranked results across evidence-count and token-budget omissions.
- `budget_omitted` warnings must summarize omission counts; do not create one warning per omitted result.
- `ContextPackRequest.retrieval_limit` must be capped by `max(max_evidence_items * 4, DEFAULT_CONTEXT_RETRIEVAL_LIMIT)` before calling retrieval. This bounds candidate and warning work while preserving enough candidates for budget packing.
- `ContextEvidence.path` must be Vault-relative. Reject absolute paths and paths containing `..` by dropping the affected evidence and adding `invalid_evidence_path` as a builder warning.
- Required pack metadata, warnings, backend records, scope, and revisions are never omitted.

Vault revision behavior:

- For each Vault in the response actual scopes, use the first non-empty `vault_revision` from included `ContextEvidence`.
- If no included evidence has a Vault revision for that Vault, set `revision=None` and `revision_kind="unknown"`.
- If a revision exists and the catalog entry uses `git_revision_policy="head"`, set `revision_kind="git"`.
- If a revision exists but the catalog entry does not indicate Git provenance, set `revision_kind="unknown"` instead of guessing.

### `src/vault_graph/context/context_pack_renderer.py`

Create:

```python
from __future__ import annotations

from typing import Protocol

from vault_graph.context.context_pack import ContextPack
from vault_graph.context.context_pack_serialization import render_context_pack_json


class ContextPackRenderer(Protocol):
    def render_json(self, pack: ContextPack) -> str: ...
    def render_markdown(self, pack: ContextPack) -> str: ...


class DefaultContextPackRenderer:
    def render_json(self, pack: ContextPack) -> str:
        return render_context_pack_json(pack)

    def render_markdown(self, pack: ContextPack) -> str: ...
```

Markdown renderer rules:

- Render `# Context Pack: {goal}`.
- Render pack ID, schema version, generated timestamp, and requested Vault IDs.
- Render a `## Warnings` section always. If there are no warnings, render `- None`.
- Render every top-level warning as `- [{severity}] {code}: {message}`.
- Render sections in this order: decisions, constraints, open questions, current state, relevant pages, relevant sources.
- Render every item title, summary, evidence refs, and item warnings.
- Render `## Evidence` with every evidence ref and path.
- Do not perform any classification, evidence selection, truncation, or warning filtering in the renderer.
- Escape or fence untrusted Vault-derived text before placing it in Markdown: goal, title, summary, warning message, evidence path, evidence ref text, and excerpt text.
- Use deterministic escaping, not ad hoc replacement at call sites. The renderer should own a private `_markdown_text(value: str) -> str` helper and apply it to every untrusted inline value.

### `src/vault_graph/context/__init__.py`

Export all public DTOs, builders, resolver contracts, and renderers:

```python
from vault_graph.context.context_pack import ...
from vault_graph.context.context_pack_builder import ...
from vault_graph.context.context_pack_renderer import ...
from vault_graph.context.context_pack_serialization import ...
from vault_graph.context.context_pack_warnings import ...

__all__ = [...]
```

Keep `__all__` explicit.

## State Management And Data Flow

Phase 4A has no durable state.

Runtime flow:

```text
ContextPackRequest
  -> ContextPackRequest validation
  -> SearchContextPackBuilder.build
  -> RetrievalService.search(goal, scope, retrieval_limit, graph flags)
  -> SearchResponse
  -> warning conversion
  -> RetrievalResult to ContextPackItem conversion
  -> ContextEvidenceResolver.resolve(ref)
  -> budget packing and excerpt truncation
  -> ContextPack with pack_id=""
  -> with_computed_pack_id
  -> DefaultContextPackRenderer.render_json(...) or render_markdown(...)
```

State transitions:

- Request state is immutable after construction.
- Search state remains owned by `RetrievalService`.
- Evidence authority remains in `MetadataStore`; `ContextEvidence` is a resolved snapshot for rendering only.
- Pack identity is derived after assembly and excludes `generated_at`.
- No pack is written to disk.
- No Vault file is created, edited, renamed, or deleted.

## Error Handling And Edge Cases

Fatal `ContextPackError`:

- empty `goal`
- invalid budget values
- invalid `retrieval_limit`
- `include_cross_vault=True` without graph mode
- `include_cross_vault=True` when `requested_scope.include_cross_vault` is not already true
- `requested_scope.include_cross_vault=True` when `include_cross_vault` is false
- `include_cross_vault=True` with only one requested Vault ID
- normal `ContextPackItem` without evidence refs
- invalid schema version
- unsupported warning severity

Propagated fatal `SearchError`:

- metadata store unavailable
- keyword index unavailable when no search can be produced
- invalid `QueryScope`

Non-fatal `ContextPackWarning`:

- vector unavailable with keyword fallback -> `search_degraded`
- graph unavailable when explicitly requested -> `graph_unavailable`
- stale store revision -> `stale_projection`
- missing evidence for one candidate -> `missing_evidence`
- excerpt truncation -> `excerpt_truncated`
- item omitted by budget -> `budget_omitted`
- unknown graph warning -> original graph code preserved

Edge cases:

- Zero search results returns a valid pack with empty item and evidence sections.
- Multi-vault packs keep evidence refs distinct by `(vault_id, document_id, chunk_id)`.
- Same `chunk_id` in two Vaults must render as two evidence records when Vault IDs differ.
- Duplicate evidence refs in one pack render once in top-level `evidence`.
- `generated_at` changes must not change `pack_id`.
- Graph store/projection backend `used` stays `False` unless graph mode is explicit and graph contributed signals or revisions.
- Markdown rendering must include warnings even when all normal sections are empty.

## Tasks

### Task 1: Context Pack DTO Contract

**Files:**

- Modify: `src/vault_graph/errors.py`
- Create: `src/vault_graph/context/__init__.py`
- Create: `src/vault_graph/context/context_pack.py`
- Test: `tests/test_context_pack_contract.py`

- [ ] **Step 1: Write failing DTO contract tests**

Add tests that construct a minimal valid `ContextPack` and assert:

```python
def test_context_pack_includes_required_top_level_fields() -> None:
    pack = make_pack()

    assert pack.context_pack_schema_version == "context-pack-v1"
    assert pack.scope.requested.vault_ids == ("main",)
    assert pack.backend.graph_store.used is False
    assert pack.budget.max_tokens == 8000
    assert pack.warnings == ()
    assert pack.evidence == ()
```

Also add tests:

```python
def test_item_requires_evidence_refs() -> None:
    with pytest.raises(ContextPackError, match="evidence_refs are required"):
        ContextPackItem(
            item_id="item-1",
            item_type="page",
            title="Page",
            summary="Summary",
            evidence_refs=(),
            retrieval_signals=(),
            relationship_status=None,
            rank=1,
            warnings=(),
        )


def test_context_pack_request_rejects_cross_vault_without_graph() -> None:
    with pytest.raises(ContextPackError, match="include_cross_vault requires include_graph"):
        ContextPackRequest(
            goal="Build",
            requested_scope=QueryScope(vault_ids=("first", "second"), include_cross_vault=True),
            include_graph=False,
            include_cross_vault=True,
        )
```

Also test:

- `ContextPackRequest(..., requested_scope=QueryScope(..., include_cross_vault=True), include_graph=True, include_cross_vault=False)` is rejected as mismatched cross-Vault state.
- `ContextPackRequest(..., requested_scope=QueryScope(vault_ids=("main",), include_cross_vault=True), include_graph=True, include_cross_vault=True)` is rejected because cross-Vault graph mode requires multiple requested Vault IDs.

- [ ] **Step 2: Run tests to verify failure**

Run:

```bash
uv run --python 3.12 pytest tests/test_context_pack_contract.py -q
```

Expected: FAIL because `vault_graph.context` and `ContextPackError` do not exist.

- [ ] **Step 3: Implement DTOs and validation**

Add `ContextPackError`, create the `vault_graph.context` package, and implement the dataclasses and helpers listed in the Component And Interface Spec.

- [ ] **Step 4: Run DTO tests**

Run:

```bash
uv run --python 3.12 pytest tests/test_context_pack_contract.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/vault_graph/errors.py src/vault_graph/context/__init__.py src/vault_graph/context/context_pack.py tests/test_context_pack_contract.py
git commit -m "feat(context): add context pack contract"
```

### Task 2: Stable Serialization And Pack Identity

**Files:**

- Create: `src/vault_graph/context/context_pack_serialization.py`
- Modify: `src/vault_graph/context/__init__.py`
- Test: `tests/test_context_pack_serialization.py`
- Test: `tests/test_context_pack_docs_contract.py`

- [ ] **Step 1: Write failing serialization tests**

Add tests:

```python
def test_context_pack_json_keeps_null_optional_fields_and_sorted_keys() -> None:
    pack = make_pack_with_warning()
    rendered = render_context_pack_json(pack)
    payload = json.loads(rendered)

    assert rendered.endswith("\n")
    assert payload["backend"]["graph_store"]["name"] is None
    assert payload["warnings"][0]["scope_key"] is None
    assert list(payload.keys()) == sorted(payload.keys())


def test_pack_id_excludes_generated_at() -> None:
    first = with_computed_pack_id(make_pack(generated_at="2026-06-12T00:00:00+00:00"))
    second = with_computed_pack_id(make_pack(generated_at="2026-06-12T01:00:00+00:00"))

    assert first.pack_id == second.pack_id
    assert len(first.pack_id) == 64
```

- [ ] **Step 2: Write failing docs contract tests**

Create `tests/test_context_pack_docs_contract.py` and add:

```python
def test_spec_and_features_context_pack_examples_match_dto_top_level_fields() -> None:
    dto_fields = set(ContextPack.__dataclass_fields__)
    spec_payload = _first_json_object_after_heading(Path("docs/SPEC.md"), "Minimum JSON shape")
    features_payload = _first_json_object_after_heading(Path("docs/FEATURES.md"), "Minimum JSON shape")

    assert set(spec_payload) == dto_fields
    assert set(features_payload) == dto_fields
    assert spec_payload["context_pack_schema_version"] == CONTEXT_PACK_SCHEMA_VERSION
    assert features_payload["context_pack_schema_version"] == CONTEXT_PACK_SCHEMA_VERSION
```

Add nested schema assertions:

```python
def test_documented_context_pack_nested_shapes_match_dto_serialization() -> None:
    rendered_payload = json.loads(render_context_pack_json(with_computed_pack_id(make_pack())))
    spec_payload = _first_json_object_after_heading(Path("docs/SPEC.md"), "Minimum JSON shape")

    assert set(spec_payload["scope"]) == set(rendered_payload["scope"])
    assert set(spec_payload["scope"]["requested"]) == set(rendered_payload["scope"]["requested"])
    assert set(spec_payload["scope"]["actual_scopes"][0]) == set(rendered_payload["scope"]["actual_scopes"][0])
    assert set(spec_payload["backend"]) == set(rendered_payload["backend"])
    assert set(spec_payload["backend"]["metadata_store"]) == set(rendered_payload["backend"]["metadata_store"])
    assert set(spec_payload["budget"]) == set(rendered_payload["budget"])
    assert set(spec_payload["store_revisions"][0]) == set(rendered_payload["store_revisions"][0])
```

Implement `_first_json_object_after_heading(...)` with a brace-depth scan over
the fenced JSON block following the heading. This keeps the test independent of
line numbers.

- [ ] **Step 3: Run tests to verify failure**

```bash
uv run --python 3.12 pytest tests/test_context_pack_serialization.py tests/test_context_pack_docs_contract.py -q
```

Expected: FAIL because serialization helpers do not exist.

- [ ] **Step 4: Implement serialization helpers**

Implement `context_pack_to_dict`, `render_context_pack_json`, `context_pack_identity_dict`, `compute_pack_id`, and `with_computed_pack_id` as specified above.

- [ ] **Step 5: Run serialization tests**

```bash
uv run --python 3.12 pytest tests/test_context_pack_serialization.py tests/test_context_pack_docs_contract.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/vault_graph/context/context_pack_serialization.py src/vault_graph/context/__init__.py tests/test_context_pack_serialization.py tests/test_context_pack_docs_contract.py
git commit -m "feat(context): add stable context pack serialization"
```

### Task 3: Warning Conversion

**Files:**

- Create: `src/vault_graph/context/context_pack_warnings.py`
- Modify: `src/vault_graph/context/__init__.py`
- Test: `tests/test_context_pack_warnings.py`

- [ ] **Step 1: Write failing warning conversion tests**

Add tests:

```python
def test_vector_query_failed_becomes_search_degraded_with_source_code() -> None:
    warning = context_warning_from_search(
        SearchWarning(
            code="vector_query_failed",
            message="Vector failed",
            severity="warning",
            affected_vault_ids=("main",),
        )
    )

    assert warning.code == "search_degraded"
    assert warning.source_code == "vector_query_failed"
    assert warning.source_kind == "retrieval"
    assert warning.affected_vault_ids == ("main",)


def test_unknown_graph_warning_preserves_identity() -> None:
    warning = context_warning_from_graph(
        GraphRetrievalWarning(
            code="new_graph_warning",
            message="New warning",
            severity="warning",
            affected_vault_ids=("main",),
        )
    )

    assert warning.code == "new_graph_warning"
    assert warning.source_code == "new_graph_warning"
    assert warning.source_kind == "graph"
```

Also add parameterized tests for every required `GRAPH_WARNING_CODE_MAP` entry:

```python
@pytest.mark.parametrize(
    ("source_code", "context_code"),
    sorted(GRAPH_WARNING_CODE_MAP.items()),
)
def test_graph_warning_mapping_preserves_source_identity(source_code: str, context_code: str) -> None:
    warning = context_warning_from_graph(
        GraphRetrievalWarning(
            code=source_code,
            message="Graph warning",
            severity="warning",
            affected_vault_ids=("main",),
            scope_key="main:wiki:cross",
            entity_id="entity-1",
            relationship_id="relationship-1",
            evidence_ref_id="evidence-1",
        )
    )

    assert warning.code == context_code
    assert warning.source_code == source_code
    assert warning.source_kind == "graph"
    assert warning.scope_key == "main:wiki:cross"
    assert warning.entity_id == "entity-1"
    assert warning.relationship_id == "relationship-1"
    assert warning.evidence_ref_id == "evidence-1"
```

Also test:

- every `SEARCH_WARNING_CODE_MAP` entry preserves `source_code`, `source_kind`, `scope_key`, and affected Vault IDs
- `SearchWarning` with one affected Vault plus `document_id` and `chunk_id` produces one `ContextEvidenceRef`
- `SearchWarning` with multiple affected Vaults plus `document_id` and `chunk_id` produces no evidence ref
- `budget_warning(...)` sets `source_kind="budget"`
- `builder_warning(...)` sets `source_kind="builder"` and preserves `recovery_hint`

- [ ] **Step 2: Run tests to verify failure**

```bash
uv run --python 3.12 pytest tests/test_context_pack_warnings.py -q
```

Expected: FAIL because warning conversion helpers do not exist.

- [ ] **Step 3: Implement warning conversion**

Implement the exact mapping and preservation rules from the Component And Interface Spec.

- [ ] **Step 4: Run warning tests**

```bash
uv run --python 3.12 pytest tests/test_context_pack_warnings.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/vault_graph/context/context_pack_warnings.py src/vault_graph/context/__init__.py tests/test_context_pack_warnings.py
git commit -m "feat(context): normalize context pack warnings"
```

### Task 4: Evidence Resolver And Budget Policy

**Files:**

- Create: `src/vault_graph/context/context_pack_builder.py`
- Modify: `src/vault_graph/context/__init__.py`
- Test: `tests/test_context_pack_evidence_budget.py`

- [ ] **Step 1: Write failing evidence and budget tests**

Add an interface-only fake store test:

```python
class RecordingMetadataStore:
    def __init__(self, *, chunk: ChunkSnapshot, evidence: EvidenceReference) -> None:
        self.chunk = chunk
        self.evidence = evidence
        self.calls: list[tuple[str, str, str | None]] = []

    def resolve_chunk(self, *, vault_id: str, chunk_id: str) -> ChunkSnapshot | None:
        self.calls.append(("resolve_chunk", vault_id, chunk_id))
        return self.chunk

    def resolve_chunk_evidence(
        self, *, vault_id: str, document_id: str, chunk_id: str
    ) -> EvidenceReference | None:
        self.calls.append(("resolve_chunk_evidence", vault_id, chunk_id))
        return self.evidence


def test_metadata_context_evidence_resolver_reads_metadata_store_protocol() -> None:
    chunk = make_chunk_snapshot(text="one two three", token_count=3)
    evidence = make_evidence_reference(metadata_index_revision="metadata-1")
    store = RecordingMetadataStore(chunk=chunk, evidence=evidence)
    resolver = MetadataContextEvidenceResolver(metadata_store=store)  # type: ignore[arg-type]

    resolved = resolver.resolve(ContextEvidenceRef("main", evidence.document_id, evidence.chunk_id))

    assert resolved is not None
    assert resolved.path == "wiki/page.md"
    assert resolved.text == "one two three"
    assert resolved.token_count == 3
    assert resolved.metadata_index_revision == "metadata-1"
    assert [call[0] for call in store.calls] == ["resolve_chunk", "resolve_chunk_evidence"]
```

Also add an integration smoke test using `SQLiteMetadataStore`, `make_document`, and `make_chunk` from `tests/test_sqlite_metadata_store.py`.

Add resolver and budget validation tests for:

- `MetadataContextEvidenceResolver.resolve(...)` returns `None` when `resolve_chunk(...)` returns `None`
- `MetadataContextEvidenceResolver.resolve(...)` returns `None` when `resolve_chunk_evidence(...)` returns `None`
- `ContextPackBudget(max_tokens=0)` raises `ContextPackError`
- `ContextPackBudget(max_evidence_items=0)` raises `ContextPackError`
- `ContextPackBudget(max_excerpt_tokens=0)` raises `ContextPackError`

- [ ] **Step 2: Run tests to verify failure**

```bash
uv run --python 3.12 pytest tests/test_context_pack_evidence_budget.py -q
```

Expected: FAIL because resolver and builder code do not exist.

- [ ] **Step 3: Implement resolver, budget helpers, and minimal builder internals**

Implement `ContextPackBuilder`, `ContextRetrievalService`, `ContextEvidenceResolver`, `ResolvedContextEvidence`, `MetadataContextEvidenceResolver`, and the private budget helpers inside `context_pack_builder.py`.

Private helpers to implement:

```python
def _truncate_excerpt(*, text: str, max_tokens: int) -> tuple[str, int, bool]: ...
def _context_evidence_from_resolved(...) -> ContextEvidence: ...
def _budget_omitted_warning(...) -> ContextPackWarning: ...
def _excerpt_truncated_warning(...) -> ContextPackWarning: ...
```

- [ ] **Step 4: Run evidence and budget tests**

```bash
uv run --python 3.12 pytest tests/test_context_pack_evidence_budget.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/vault_graph/context/context_pack_builder.py src/vault_graph/context/__init__.py tests/test_context_pack_evidence_budget.py
git commit -m "feat(context): resolve evidence and enforce pack budgets"
```

### Task 5: SearchContextPackBuilder Boundary

**Files:**

- Modify: `src/vault_graph/context/context_pack_builder.py`
- Test: `tests/test_context_pack_builder.py`

- [ ] **Step 1: Write failing builder tests**

Add tests using existing fixtures from `tests/test_retrieval_service_search.py` where practical.

Test retrieval limit pass-through:

```python
class RecordingRetrievalService:
    def __init__(self, response: SearchResponse) -> None:
        self.response = response
        self.calls: list[dict[str, object]] = []

    def search(self, **kwargs: object) -> SearchResponse:
        self.calls.append(kwargs)
        return self.response


def test_builder_passes_retrieval_limit_and_graph_flags() -> None:
    retrieval = RecordingRetrievalService(make_search_response())
    builder = SearchContextPackBuilder(
        catalog=make_catalog(),
        retrieval_service=retrieval,  # type: ignore[arg-type]
        evidence_resolver=StaticResolver(),
        clock=fixed_clock,
    )

    builder.build(
        ContextPackRequest(
            goal="Build context",
            requested_scope=QueryScope(vault_ids=("main",)),
            retrieval_limit=7,
            include_graph=False,
        )
    )

    assert retrieval.calls[0]["limit"] == 7
    assert retrieval.calls[0]["include_graph"] is False
    assert retrieval.calls[0]["include_cross_vault"] is False
```

Add tests:

- `include_graph=False` does not require or invoke graph dependencies by using existing `RetrievalService` with `FailingGraphCandidateProvider`.
- `include_graph=True` preserves realistic graph-mode `SearchWarning(code="graph_stale", source scope...)` records as `ContextPack.warnings` with `code="graph_stale"` and `source_code="graph_stale"`.
- `RetrievalResult.warnings` becomes `ContextPackItem.warnings` and is visible in Markdown through `DefaultContextPackRenderer`.
- truncating a 400-token chunk to `max_excerpt_tokens=3` sets `pack.budget.used_tokens == 3`, creates an evidence-level `excerpt_truncated` warning, and creates a top-level `excerpt_truncated` warning.
- omitting the second result when `max_evidence_items=1` sets `pack.budget.omitted_items == 1` and creates one aggregate `budget_omitted` warning.
- keeping same `chunk_id` from two Vault IDs as two separate evidence refs.
- duplicate evidence refs in separate results call the resolver once and render one top-level evidence record.
- invalid evidence paths such as `/Users/me/vault/wiki/page.md` and `../outside.md` are dropped with `invalid_evidence_path`.
- default keyword/vector pack has no graph or projection store revision rows.
- store revisions include `keyword` for default packs.
- every normal item references at least one evidence ref.
- pack with zero results is valid and contains search warnings.

- [ ] **Step 2: Run tests to verify failure**

```bash
uv run --python 3.12 pytest tests/test_context_pack_builder.py -q
```

Expected: FAIL because `SearchContextPackBuilder` is incomplete.

- [ ] **Step 3: Implement `SearchContextPackBuilder.build`**

Implement the build flow exactly as specified in Component And Interface Spec. Keep classification template-based and deterministic. Do not add LLM summaries or durable persistence.

- [ ] **Step 4: Run builder tests**

```bash
uv run --python 3.12 pytest tests/test_context_pack_builder.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/vault_graph/context/context_pack_builder.py tests/test_context_pack_builder.py
git commit -m "feat(context): build context packs from retrieval results"
```

### Task 6: Renderer Boundary

**Files:**

- Create: `src/vault_graph/context/context_pack_renderer.py`
- Modify: `src/vault_graph/context/__init__.py`
- Test: `tests/test_context_pack_serialization.py`

- [ ] **Step 1: Add failing renderer tests**

Add tests:

```python
def test_json_renderer_uses_canonical_json() -> None:
    pack = make_pack_with_warning()
    renderer: ContextPackRenderer = DefaultContextPackRenderer()

    assert renderer.render_json(pack) == render_context_pack_json(pack)


def test_markdown_renderer_cannot_hide_top_level_warnings() -> None:
    pack = make_pack_with_warning(code="graph_unavailable", message="Graph missing")
    renderer: ContextPackRenderer = DefaultContextPackRenderer()
    markdown = renderer.render_markdown(pack)

    assert "## Warnings" in markdown
    assert "graph_unavailable" in markdown
    assert "Graph missing" in markdown
```

Also test that every evidence ref appears in Markdown, Vault-derived headings are escaped instead of creating new Markdown sections, and `src/vault_graph/cli/main.py` does not contain context-pack section formatting helpers in Phase 4A.

- [ ] **Step 2: Run tests to verify failure**

```bash
uv run --python 3.12 pytest tests/test_context_pack_serialization.py -q
```

Expected: FAIL because renderers do not exist.

- [ ] **Step 3: Implement renderers**

Implement `ContextPackRenderer` and `DefaultContextPackRenderer` using only `ContextPack` DTO data. Do not call retrieval, metadata stores, graph stores, or filesystem APIs from renderers.

- [ ] **Step 4: Run renderer tests**

```bash
uv run --python 3.12 pytest tests/test_context_pack_serialization.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/vault_graph/context/context_pack_renderer.py src/vault_graph/context/__init__.py tests/test_context_pack_serialization.py
git commit -m "feat(context): add context pack renderers"
```

### Task 7: Import Boundary And Read-Only Tests

**Files:**

- Create: `tests/test_context_pack_import_boundaries.py`
- Create: `tests/test_context_pack_read_only_boundary.py`
- Modify: `tests/test_package_import.py`

- [ ] **Step 1: Write import-boundary tests**

Add:

```python
import ast
from pathlib import Path


def test_context_package_does_not_import_local_backends_or_llms() -> None:
    forbidden_prefixes = (
        "vault_graph.storage.local",
        "vault_graph.cli",
        "vault_graph.projection.rustworkx_projection",
        "rustworkx",
        "chromadb",
        "openai",
        "anthropic",
    )
    imported_modules: set[str] = set()
    for path in Path("src/vault_graph/context").glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported_modules.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported_modules.add(node.module)

    assert not [
        module
        for module in imported_modules
        if any(module == forbidden or module.startswith(f"{forbidden}.") for forbidden in forbidden_prefixes)
    ]
```

Add a subprocess import test proving `import vault_graph.context` does not import `vault_graph.cli.main`, `vault_graph.storage.local.sqlite_metadata_store`, `vault_graph.storage.local.chroma_vector_store`, `vault_graph.retrieval.graph_retrieval`, `vault_graph.retrieval.graph_candidates`, or `vault_graph.projection.rustworkx_projection`.

- [ ] **Step 2: Write read-only test**

Add:

```python
def test_context_pack_builder_does_not_modify_vault_files(tmp_path: Path) -> None:
    vault_root = tmp_path / "vault"
    for relative_path in (
        "wiki/page.md",
        "docs/spec.md",
        "raw/source.md",
        "scratch/reports/report.md",
        "wiki/nested/decision.md",
    ):
        path = vault_root / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"# {relative_path}\nBody\n", encoding="utf-8")
    before = file_bytes(vault_root)

    builder = make_builder_for_existing_metadata(tmp_path, vault_root)
    builder.build(ContextPackRequest(goal="Body", requested_scope=builder_catalog.default_scope()))

    assert file_bytes(vault_root) == before
```

Use the existing `file_bytes` helper shape from `tests/test_read_only_boundary.py`. The helper builder may use `SQLiteMetadataStore` in the test fixture, but production `src/vault_graph/context` code must use only `MetadataStore`.

- [ ] **Step 3: Run boundary tests**

```bash
uv run --python 3.12 pytest tests/test_context_pack_import_boundaries.py tests/test_context_pack_read_only_boundary.py tests/test_package_import.py -q
```

Expected: PASS after implementation.

- [ ] **Step 4: Commit**

```bash
git add tests/test_context_pack_import_boundaries.py tests/test_context_pack_read_only_boundary.py tests/test_package_import.py
git commit -m "test(context): harden context pack boundaries"
```

### Task 8: Full Verification

**Files:**

- No code changes expected.

- [ ] **Step 1: Run focused context tests**

```bash
uv run --python 3.12 pytest \
  tests/test_context_pack_contract.py \
  tests/test_context_pack_serialization.py \
  tests/test_context_pack_warnings.py \
  tests/test_context_pack_evidence_budget.py \
  tests/test_context_pack_builder.py \
  tests/test_context_pack_import_boundaries.py \
  tests/test_context_pack_read_only_boundary.py \
  -q
```

Expected: all focused context tests pass.

- [ ] **Step 2: Run search and graph regression tests**

```bash
uv run --python 3.12 pytest \
  tests/test_retrieval_service_search.py \
  tests/test_search_response_contract.py \
  tests/test_search_include_graph.py \
  tests/test_graph_retrieval_service.py \
  tests/test_multi_vault_graph_retrieval.py \
  -q
```

Expected: existing retrieval and graph behavior remains unchanged.

- [ ] **Step 3: Run full verification**

```bash
uv run --python 3.12 pytest -q
uv run --python 3.12 ruff check src tests
uv run --python 3.12 mypy src tests
git diff --check
```

Expected:

- pytest passes
- ruff reports `All checks passed!`
- mypy reports `Success: no issues found`
- `git diff --check` exits 0

- [ ] **Step 4: Final commit if any verification-only fixes were needed**

```bash
git add src/vault_graph/context tests src/vault_graph/errors.py
git commit -m "test(context): verify phase 4a context pack contract"
```

Skip this commit if Task 8 made no file changes.

## Multi-Angle Review Results

- Security: tightened multi-vault warning attribution so evidence refs are created only for single-vault warnings; required result-level warnings to survive as item warnings; added Vault-relative path validation, Markdown escaping, and fail-closed DTO serialization.
- Performance: changed the builder flow to dedupe evidence refs before resolver calls, resolve only within budget, aggregate `budget_omitted` warnings, cap retrieval work from the evidence budget, and avoid eager graph imports from `vault_graph.retrieval`.
- Testability: added docs/DTO schema parity tests, nested JSON shape checks, parameterized warning mapping tests, fake `MetadataStore` resolver tests, exact budget accounting assertions, renderer abstraction checks, and broader read-only fixtures.
- Clean Code / Maintainability: made `vault_graph.context` an explicit package boundary in `docs/SPEC.md` and `docs/DESIGN.md`; replaced the concrete retrieval dependency with `ContextRetrievalService`; clarified scope-key policy; replaced unsupported renderer methods with one `DefaultContextPackRenderer`.

## Open Decisions

No user decision is required for Phase 4A at plan time. The plan follows accepted Phase 4 decisions: JSON is canonical, graph signals are opt-in, packs are not persisted, and `docs/DECISIONS.md` records only accepted decisions.

## Handoff

Recommended execution mode: Subagent-Driven. Dispatch one implementation subagent per task or small task group, with a review checkpoint after each commit.
