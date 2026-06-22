# Phase 6B Project, Decision, And Issue Memory Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add deterministic project, decision, and open-question memory projections over indexed Vault evidence, exposed through MCP tools and the existing `vault://{vault_id}/context/current` resource.

**Architecture:** Keep Phase 6B as read-only projection work over `MetadataStore`, `IndexService.status(...)`, and optional lazy graph decision traces. `vault_graph.memory` owns MCP-free DTOs, source reading, classification, and services; `vault_graph.mcp` owns tool/resource argument parsing, serialization, resource links, and error mapping.

**Tech Stack:** Python 3.12, frozen dataclasses, existing `MetadataStore` protocol, SQLite read-only metadata store, existing `QueryScope` and MCP scope helpers, FastMCP tool/resource registration, pytest, ruff, mypy.

---

## Source Documents

Read these before implementation:

- `AGENTS.md`
- `docs/SPEC.md`
- `docs/FEATURES.md`
- `docs/DESIGN.md`
- `docs/DECISIONS.md`
- `docs/CONVENTIONS.md`
- `docs/superpowers/specs/phase-6/README.md`
- `docs/superpowers/specs/phase-6/2026-06-18-phase-6-memory-and-explorer-views-overview-design.md`
- `docs/superpowers/specs/phase-6/2026-06-18-phase-6a-result-explanation-contract-design.md`
- `docs/superpowers/specs/phase-6/2026-06-18-phase-6b-project-decision-issue-memory-design.md`
- `docs/superpowers/plans/2026-06-19-phase-6a-result-explanation-contract.md`

Current repo facts to preserve:

- `src/vault_graph/memory/result_explanation.py` already owns Phase 6A MCP-free explanation DTOs and `ExplainResultService`.
- `src/vault_graph/memory/__init__.py` uses lazy exports. Keep this package import-light and MCP-free.
- `src/vault_graph/storage/interfaces/metadata_store.py` has chunk/evidence readers but no document listing contract yet.
- `src/vault_graph/storage/local/sqlite_metadata_store.py` already has `_document_snapshot_from_row(...)`, `_path_in_content_scope(...)`, and read-only behavior when `initialize=False`.
- `src/vault_graph/mcp/mcp_tools.py` currently registers Phase 6A tools:
  `search_vault`, `build_context_pack`, `find_related`, `get_decision_trace`,
  `check_index_status`, and `explain_result`.
- `src/vault_graph/mcp/mcp_resources.py` currently returns a Phase 5B availability placeholder for `vault://{vault_id}/context/current`.
- `src/vault_graph/mcp/mcp_service_factory.py` opens stores lazily and read-only; graph services import rustworkx only when graph behavior is requested.
- `src/vault_graph/mcp/mcp_prompts.py` intentionally does not mention Phase 6B memory tools yet.
- Phase 6 memory is projection terminology only. Do not add generic writable memory APIs, external memory dependencies, hidden episode logs, profile memory, or durable memory state.

## Scope

Implement Phase 6B:

- Add `MemoryProjectionError`.
- Add `MetadataStore.list_documents(scope)` and the SQLite read-only implementation.
- Add MCP-free memory DTOs for memory items, warnings, evidence refs, backend revisions, and grouped projections.
- Add `MemorySourceReader` to load document snapshots, headings, bounded evidence, and deterministic excerpts through `MetadataStore`.
- Add deterministic project, decision, and issue/open-question memory services.
- Add optional topic-specific decision graph enrichment through a lazy `decision_trace_provider_factory`.
- Add MCP memory serialization and resource-link helpers.
- Add `summarize_project_memory(scope=None, limit=10)` and `get_open_questions(scope=None, limit=20)`.
- Upgrade `vault://{vault_id}/context/current` to return a single-Vault `ProjectMemoryProjection`.
- Update prompts so workflows prefer Phase 6B memory tools before broad search when those tools are registered.
- Add focused unit, integration, MCP, read-only, multi-Vault, import-boundary, and smoke tests.

## Non-Goals

Do not implement:

- LLM-written narrative summaries
- `ask_vault`
- automatic Vault edits, source capture, wiki publication, issue resolution, or decision acceptance
- durable memory storage, history, or database tables
- generic `MemoryStore`, `Memory.create`, `Memory.query`, `Memory.upsert`, `Memory.link`, or `Memory.audit`
- Mem0, MemMachine, MCP memory-server, profile memory, preference memory, procedural memory, or raw episode memory
- new CLI or HTTP surfaces
- `get_recent_changes` or timeline health explorer behavior from Phase 6C
- graph-only decision memory items that bypass metadata-backed evidence
- cross-Vault graph relationship grouping for memory output

## Directory And File Structure

Create:

- `src/vault_graph/memory/memory_models.py`: MCP-free memory DTOs, validation, stable item ID helper, JSON-safe scope/revision helper values only when needed by services.
- `src/vault_graph/memory/memory_source_reader.py`: read-only document snapshot, heading, bounded evidence, and excerpt loader over `MetadataStore`.
- `src/vault_graph/memory/memory_request_context.py`: per-request actual scopes, metadata status, document snapshots, and generated timestamp shared by memory services to avoid repeated scans.
- `src/vault_graph/memory/decision_memory.py`: `DecisionTraceProvider` protocol and `DecisionMemoryService`.
- `src/vault_graph/memory/issue_memory.py`: `IssueMemoryService`.
- `src/vault_graph/memory/project_memory.py`: `ProjectMemoryService` and project-level classification for current state, constraints, next priorities, and stale areas.
- `src/vault_graph/mcp/mcp_memory_serialization.py`: MCP payload, warning, resource-link, and text-safe serialization for memory projections.
- `tests/test_memory_models.py`
- `tests/test_memory_source_reader.py`
- `tests/test_memory_request_context.py`
- `tests/test_decision_memory_service.py`
- `tests/test_issue_memory_service.py`
- `tests/test_project_memory_service.py`
- `tests/test_mcp_memory_tools.py`
- `tests/test_mcp_current_context_resource.py`

Modify:

- `src/vault_graph/errors.py`: add `MemoryProjectionError`.
- `src/vault_graph/memory/__init__.py`: add lazy exports for Phase 6B DTOs and services.
- `src/vault_graph/storage/interfaces/metadata_store.py`: add `list_documents(...)`.
- `src/vault_graph/storage/local/sqlite_metadata_store.py`: implement read-only document listing.
- `src/vault_graph/mcp/__init__.py`: lazy export new MCP memory types only if existing export style requires it.
- `src/vault_graph/mcp/mcp_errors.py`: map `MemoryProjectionError`.
- `src/vault_graph/mcp/mcp_prompts.py`: mention registered Phase 6B tools and keep future tools out.
- `src/vault_graph/mcp/mcp_resources.py`: replace `context/current` placeholder with project memory resource.
- `src/vault_graph/mcp/mcp_server.py`: no new cache, but keep constructor calls compatible after tool/resource registry changes.
- `src/vault_graph/mcp/mcp_service_factory.py`: add lazy memory service construction methods.
- `src/vault_graph/mcp/mcp_tools.py`: add input DTOs, parsers, registry methods, and FastMCP handlers.
- `tests/fakes/`: add focused fake metadata/status/graph helpers only if local test modules become duplicated.
- Existing MCP/resource/server/prompt/smoke/import-boundary/read-only tests listed in later tasks.

Do not create:

- `src/vault_graph/memory/memory_store.py`
- `src/vault_graph/memory/external_memory.py`
- `src/vault_graph/memory/episode_log.py`
- `src/vault_graph/memory/profile_memory.py`
- any `data/memory/`, SQLite memory table, Chroma collection, graph table, or external adapter.

## Component And Interface Spec

### `src/vault_graph/errors.py`

Add:

```python
class MemoryProjectionError(VaultGraphError):
    """Raised when read-only memory projections cannot be assembled safely."""
```

Use this for MCP-free Phase 6B domain failures such as unavailable metadata evidence. MCP argument parsing should continue to raise existing `McpProtocolError` values through MCP validation helpers.

### `src/vault_graph/storage/interfaces/metadata_store.py`

Add to `MetadataStore`:

```python
def list_documents(self, scope: QueryScope) -> tuple[DocumentSnapshot, ...]: ...
```

Contract:

- returns current non-tombstoned documents only;
- returns `()` when the database is missing and must not create files;
- filters by `scope.vault_ids`;
- filters by `scope.content_scopes` using the same same-or-child rules as `list_chunks(...)`;
- orders by `vault_id`, `path`, then `document_id`;
- preserves all `DocumentSnapshot` fields exactly;
- does not run schema creation, migrations, tombstone writes, keyword updates, vector calls, graph calls, or status writes.

SQLite implementation in `SQLiteMetadataStore`:

```python
def list_documents(self, scope: QueryScope) -> tuple[DocumentSnapshot, ...]:
    if not scope.vault_ids:
        return ()
    if not self._database_path.exists():
        return ()
    vault_placeholders = ", ".join("?" for _ in scope.vault_ids)
    with self._connect() as connection:
        rows = connection.execute(
            f"""
            SELECT vault_id, document_id, path, kind, frontmatter_json, frontmatter_hash,
                   content_hash, raw_sha256, parser_version, last_seen_at, last_indexed_at,
                   vault_revision, index_revision
            FROM documents
            WHERE vault_id IN ({vault_placeholders})
              AND is_tombstoned = 0
            ORDER BY vault_id, path, document_id
            """,
            scope.vault_ids,
        ).fetchall()
    return tuple(
        _document_snapshot_from_row(row)
        for row in rows
        if _path_in_content_scope(path=str(row["path"]), content_scopes=scope.content_scopes)
    )
```

### `src/vault_graph/memory/memory_models.py`

Responsibilities:

- Define immutable MCP-free memory projection DTOs.
- Validate required identities, tuple immutability, evidence, warnings, rank, claim status, freshness, and JSON-safe revision fields.
- Provide a stable bounded item ID helper.
- Avoid MCP, SQLite, Chroma, graph store, FastMCP, Mem0, or MemMachine imports.

Public API:

```python
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Literal

from vault_graph.errors import MemoryProjectionError
from vault_graph.ingestion.vault_catalog import QueryScope

MemoryItemKind = Literal[
    "current_state",
    "decision",
    "open_question",
    "constraint",
    "next_priority",
    "stale_area",
]
MemoryClaimStatus = Literal["stated", "metadata_derived", "heading_candidate"]
MemoryWarningSeverity = Literal["info", "warning", "error"]
MemoryFreshness = Literal["fresh", "stale", "unavailable", "unknown"]
MemoryDocumentResourceKind = Literal["document", "page", "source", "decision", "issue"]


@dataclass(frozen=True)
class MemoryEvidenceRef:
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


@dataclass(frozen=True)
class MemoryWarning:
    code: str
    message: str
    severity: MemoryWarningSeverity
    affected_vault_ids: tuple[str, ...]
    recovery_hint: str | None = None


@dataclass(frozen=True)
class MemoryBackendRevision:
    kind: str
    revision: str | None
    vault_id: str | None
    scope_key: str


@dataclass(frozen=True)
class MemoryItem:
    item_id: str
    kind: MemoryItemKind
    claim_status: MemoryClaimStatus
    matched_signals: tuple[str, ...]
    document_resource_kinds: tuple[MemoryDocumentResourceKind, ...]
    title: str
    summary: str
    vault_id: str
    path: str
    status: str | None
    rank: int
    evidence: tuple[MemoryEvidenceRef, ...]
    warnings: tuple[MemoryWarning, ...]


@dataclass(frozen=True)
class ProjectMemoryVault:
    vault_id: str
    display_name: str
    current_state: tuple[MemoryItem, ...]
    decisions: tuple[MemoryItem, ...]
    open_questions: tuple[MemoryItem, ...]
    constraints: tuple[MemoryItem, ...]
    next_priorities: tuple[MemoryItem, ...]
    stale_areas: tuple[MemoryItem, ...]
    warnings: tuple[MemoryWarning, ...]
    store_revisions: tuple[MemoryBackendRevision, ...]
    freshness: MemoryFreshness


@dataclass(frozen=True)
class ProjectMemoryProjection:
    requested_scope: QueryScope
    actual_scopes: tuple[QueryScope, ...]
    vaults: tuple[ProjectMemoryVault, ...]
    warnings: tuple[MemoryWarning, ...]
    generated_at: str


@dataclass(frozen=True)
class DecisionMemoryVault:
    vault_id: str
    display_name: str
    decisions: tuple[MemoryItem, ...]
    warnings: tuple[MemoryWarning, ...]
    store_revisions: tuple[MemoryBackendRevision, ...]
    freshness: MemoryFreshness


@dataclass(frozen=True)
class DecisionMemoryProjection:
    requested_scope: QueryScope
    actual_scopes: tuple[QueryScope, ...]
    topic: str | None
    vaults: tuple[DecisionMemoryVault, ...]
    warnings: tuple[MemoryWarning, ...]
    generated_at: str


@dataclass(frozen=True)
class OpenQuestionsVault:
    vault_id: str
    display_name: str
    questions: tuple[MemoryItem, ...]
    warnings: tuple[MemoryWarning, ...]
    store_revisions: tuple[MemoryBackendRevision, ...]
    freshness: MemoryFreshness


@dataclass(frozen=True)
class OpenQuestionsProjection:
    requested_scope: QueryScope
    actual_scopes: tuple[QueryScope, ...]
    vaults: tuple[OpenQuestionsVault, ...]
    warnings: tuple[MemoryWarning, ...]
    generated_at: str


def stable_memory_item_id(
    *,
    kind: MemoryItemKind,
    vault_id: str,
    document_id: str,
    chunk_id: str,
    title: str,
    status: str | None,
    claim_status: MemoryClaimStatus,
) -> str: ...
```

Validation rules:

- All required string identities must be non-empty after `strip()`.
- Every sequence field must be a tuple, not a list.
- `MemoryItem.evidence` must contain at least one `MemoryEvidenceRef`.
- `MemoryItem.rank` must be positive.
- `MemoryItem.vault_id` and `MemoryItem.path` must match its first evidence ref.
- `MemoryItem.document_resource_kinds` validation checks only that the value is a non-empty tuple and includes `document`.
- Services compute `document_resource_kinds` through a shared `document_resource_kinds_for_document(document: DocumentSnapshot)` helper during classification. That helper may include `decision` or `issue` only when the backing path or canonical frontmatter satisfies the existing resource-reader classifier. Heading-only candidates must not get broken decision/issue links.
- `MemoryWarning.affected_vault_ids` must be a non-empty tuple.
- `MemoryBackendRevision.scope_key` must be non-empty; `revision` and `vault_id` may be `None`.
- projection `actual_scopes`, `vaults`, and `warnings` must be tuples.
- `stable_memory_item_id(...)` returns `memory:<kind>:<24 hex chars>`.
- ID hash input is canonical JSON with `kind`, `vault_id`, `document_id`, `chunk_id`, normalized title, normalized status, and `claim_status`.
- Phase 6B does not claim evidence-backed recency for decisions or durable changes. Timeline-based recent changes remain Phase 6C. `CurrentContextResourceReader` appends a resource-level info warning such as `recent_changes_unavailable_until_phase_6c` when `context/current` is used as current-context input and recent-change context belongs to Phase 6C.

### `src/vault_graph/memory/memory_source_reader.py`

Responsibilities:

- Centralize read-only document listing and selected-document evidence loading.
- Return headings from indexed chunks without reparsing Vault files.
- Keep item evidence bounded while allowing late matched heading chunks to be preferred.

Public API:

```python
from dataclasses import dataclass

from vault_graph.ingestion.document_normalizer import DocumentSnapshot
from vault_graph.ingestion.vault_catalog import QueryScope
from vault_graph.storage.interfaces.metadata_store import MetadataStore


@dataclass(frozen=True)
class MemoryHeadingRef:
    chunk_id: str
    section: str
    anchor: str | None


@dataclass(frozen=True)
class MemoryDocumentRead:
    document: DocumentSnapshot
    evidence: tuple[MemoryEvidenceRef, ...]
    headings: tuple[MemoryHeadingRef, ...]
    body_excerpt: str | None
    warnings: tuple[MemoryWarning, ...]


class MemorySourceReader:
    def __init__(self, *, metadata_store: MetadataStore) -> None: ...
    def list_documents(self, *, scope: QueryScope) -> tuple[DocumentSnapshot, ...]: ...
    def read_document(
        self,
        *,
        document: DocumentSnapshot,
        max_evidence_chunks: int = 3,
        preferred_chunk_ids: tuple[str, ...] = (),
    ) -> MemoryDocumentRead: ...


def document_resource_kinds_for_document(
    document: DocumentSnapshot,
) -> tuple[MemoryDocumentResourceKind, ...]: ...
```

Behavior:

- `list_documents(...)` delegates only to `MetadataStore.list_documents(...)`.
- `read_document(...)` calls `list_document_chunks(...)`, then `resolve_chunk_evidence(...)` for preferred chunk IDs first and remaining chunks in indexed order.
- `read_document(...)` lists all chunks for one selected document to return all indexed headings, but resolves at most `max_evidence_chunks` evidence refs.
- Services may call `read_document(...)` twice for a selected document when the first call discovers a late heading match outside the initial evidence cap. The second call must pass the matched heading chunk IDs as `preferred_chunk_ids`.
- Headings come from non-empty `ChunkSnapshot.section`; no Markdown reparsing.
- `body_excerpt` is the first non-empty chunk text stripped and truncated to 280 characters.
- Missing chunk evidence produces `MemoryWarning(code="unresolved_evidence", ...)`.
- No chunks produces `MemoryWarning(code="document_has_no_chunks", ...)`.
- `document_resource_kinds_for_document(...)` mirrors existing
  `MetadataResourceReader` classifiers for document/page/source/decision/issue
  resource validity and does not inspect headings.
- `max_evidence_chunks < 1` raises `MemoryProjectionError("invalid_memory_evidence_limit: ...")`.
- The reader must not expose `read_documents(scope)` in Phase 6B.

### `src/vault_graph/memory/memory_request_context.py`

Responsibilities:

- Build the per-request read context shared by project, decision, and issue
  services.
- Centralize metadata readiness checks so missing metadata never becomes an
  empty successful projection.
- Keep one generated timestamp and one indexed document listing per actual
  Vault scope when `ProjectMemoryService` composes decision and issue services.

Public API:

```python
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from vault_graph.app.index_service import IndexService, StatusReport
from vault_graph.ingestion.vault_catalog import QueryScope, VaultCatalog
from vault_graph.ingestion.document_normalizer import DocumentSnapshot


@dataclass(frozen=True)
class MemoryVaultDocuments:
    vault_id: str
    scope: QueryScope
    documents: tuple[DocumentSnapshot, ...]


@dataclass(frozen=True)
class MemoryRequestContext:
    requested_scope: QueryScope
    actual_scopes: tuple[QueryScope, ...]
    status_report: StatusReport
    documents_by_vault: tuple[MemoryVaultDocuments, ...]
    generated_at: str


def build_memory_request_context(
    *,
    catalog: VaultCatalog,
    source_reader: MemorySourceReader,
    status_service: IndexService,
    requested_scope: QueryScope,
    clock: Callable[[], datetime] | None = None,
) -> MemoryRequestContext: ...
```

Rules:

- Call `actual_query_scopes(catalog=catalog, scope=requested_scope)`.
- Call `status_service.status(scope=requested_scope)` before document listing.
- Raise `MemoryProjectionError("metadata_unavailable: ...")` when metadata is
  not OK or schema-incompatible.
- Call `source_reader.list_documents(scope=actual_scope)` once per actual Vault
  scope.
- Do not read chunks or graph data in the request context builder.
- `DecisionMemoryService` and `IssueMemoryService` use this helper for their
  standalone public methods. `ProjectMemoryService` builds one context and uses
  package-internal service methods that accept the context, so project memory
  does not repeat metadata/status scans.

### `src/vault_graph/memory/decision_memory.py`

Responsibilities:

- Build decision memory over durable decision evidence in metadata-selected documents.
- Optionally enrich topic-specific results with graph decision-trace signals without creating graph-only memory facts.
- Keep graph service opening lazy and explicit.

Public API:

```python
from collections.abc import Callable
from datetime import datetime
from typing import Protocol

from vault_graph.app.index_service import IndexService
from vault_graph.ingestion.vault_catalog import QueryScope, VaultCatalog
from vault_graph.retrieval.graph_retrieval import DecisionTraceResponse, GraphOutputFormat


class DecisionTraceProvider(Protocol):
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


class DecisionMemoryService:
    def __init__(
        self,
        *,
        catalog: VaultCatalog,
        source_reader: MemorySourceReader,
        status_service: IndexService,
        decision_trace_provider_factory: Callable[[], DecisionTraceProvider] | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None: ...

    def list_decisions(
        self,
        *,
        requested_scope: QueryScope,
        topic: str | None = None,
        limit: int = 20,
        include_graph: bool = False,
    ) -> DecisionMemoryProjection: ...

    def _list_decisions_from_context(
        self,
        *,
        context: MemoryRequestContext,
        topic: str | None = None,
        limit: int = 20,
        include_graph: bool = False,
    ) -> DecisionMemoryProjection: ...
```

Classification:

- `stated` when path starts `wiki/decisions/`, frontmatter `type` is `decision`, or frontmatter has `decision`.
- `metadata_derived` when document-level path/frontmatter strongly suggests decision context but is not canonical.
- `heading_candidate` when a decision heading is found inside a metadata-selected document that is not canonical.
- Decision heading terms are case-insensitive: `decision`, `alternatives`, `tradeoff`, `trade-off`, `revisit`.
- Heading-only items carry `MemoryWarning(code="candidate_decision", ...)`.
- Ambiguous group matches carry `MemoryWarning(code="ambiguous_classification", ...)`.

Candidate narrowing:

- Expand `actual_scopes = actual_query_scopes(catalog=catalog, scope=requested_scope)`.
- Build `MemoryRequestContext` for standalone `list_decisions(...)` calls.
- If `metadata_ok` is false or `metadata_schema_compatible` is false, context creation raises `MemoryProjectionError("metadata_unavailable: ...")`.
- For each actual single-Vault scope, call `source_reader.list_documents(scope=actual_scope)`.
- Document-level candidate match happens before chunk reads.
- Read at most `candidate_read_limit = min(max(limit * 10, 50), 250)` candidate documents per Vault.
- If matching document candidates exceed the cap, include `candidate_scan_truncated`.

Graph enrichment:

- Invoke `decision_trace_provider_factory` only when `topic is not None and include_graph is True`.
- Call:

```python
provider.decision_trace(
    topic=topic,
    requested_scope=requested_scope,
    depth=2,
    include_cross_vault=False,
    limit=limit,
    output_format="json",
)
```

- Do not expose `include_cross_vault` through Phase 6B memory tools.
- Do not create graph-only `MemoryItem` records in Phase 6B. If graph evidence matches an existing decision item by `(vault_id, document_id)` in evidence, append `graph_decision_trace` to `matched_signals`.
- If graph enrichment is requested but unavailable or unmatched, return the metadata-backed projection with a warning, not an empty failure, unless the graph provider raises a fatal domain error that prevents safe output.

### `src/vault_graph/memory/issue_memory.py`

Responsibilities:

- Return unresolved issues, open questions, follow-ups, TODOs, blockers, and revisit triggers.
- Exclude resolved/closed issue states conservatively.

Public API:

```python
from collections.abc import Callable
from datetime import datetime

from vault_graph.app.index_service import IndexService
from vault_graph.ingestion.vault_catalog import QueryScope, VaultCatalog


class IssueMemoryService:
    def __init__(
        self,
        *,
        catalog: VaultCatalog,
        source_reader: MemorySourceReader,
        status_service: IndexService,
        clock: Callable[[], datetime] | None = None,
    ) -> None: ...

    def open_questions(
        self,
        *,
        requested_scope: QueryScope,
        limit: int = 20,
    ) -> OpenQuestionsProjection: ...

    def _open_questions_from_context(
        self,
        *,
        context: MemoryRequestContext,
        limit: int = 20,
    ) -> OpenQuestionsProjection: ...
```

Classification:

- Active statuses: `open`, `unresolved`, `todo`, `blocked`, `revisit`.
- Excluded statuses: `closed`, `resolved`, `done`, `accepted`, `superseded`, `deprecated`, `cancelled`.
- `stated` when path starts `wiki/issues/` or frontmatter `type` is `issue`, `question`, or `follow_up`, and status is active.
- A missing status issue document is emitted only when an explicit open-question heading matched inside that metadata-selected document; include `missing_issue_status`.
- Open-question heading terms are case-insensitive: `open questions`, `question`, `follow-up`, `follow up`, `todo`, `blocker`, `revisit`.
- Heading-only TODOs inside metadata-selected documents are `heading_candidate`.
- Excluded status documents are never emitted, even if they contain old TODO headings.

### `src/vault_graph/memory/project_memory.py`

Responsibilities:

- Compose decision and issue projections.
- Add project-level current state, constraints, next priorities, and stale areas from metadata-selected documents.
- Preserve per-Vault grouping, freshness, revisions, and warnings.

Public API:

```python
from collections.abc import Callable
from datetime import datetime

from vault_graph.app.index_service import IndexService
from vault_graph.ingestion.vault_catalog import QueryScope, VaultCatalog


class ProjectMemoryService:
    def __init__(
        self,
        *,
        catalog: VaultCatalog,
        source_reader: MemorySourceReader,
        decision_service: DecisionMemoryService,
        issue_service: IssueMemoryService,
        status_service: IndexService,
        clock: Callable[[], datetime] | None = None,
    ) -> None: ...

    def summarize(
        self,
        *,
        requested_scope: QueryScope,
        limit: int = 10,
    ) -> ProjectMemoryProjection: ...
```

Project-level classification:

- `current_state`: frontmatter `type` in `project_status`, `status`, `roadmap`, `plan`, `overview`; or path contains `status`, `roadmap`, `plan`, `overview`.
- `constraint`: frontmatter contains `constraint`, `policy`, `boundary`, `invariant`; or path contains `policy`, `decision`, `convention`, `boundary`; or selected-document heading contains `constraint`, `policy`, `boundary`, `invariant`, `non-goal`.
- `next_priority`: frontmatter contains `priority`, `next`, `roadmap`, `phase`; or selected-document heading contains `next`, `priorities`, `roadmap`, `implementation order`, `todo`.
- `stale_area`: document frontmatter `status` is `stale`, `deprecated`, or `superseded`, or selected-document heading/path indicates deprecated/superseded project area.
- Backend stale, unavailable, or incompatible state must appear in `freshness` and warnings, not as `stale_area` items, unless a Vault document itself provides the stale-area evidence.
- Root-level `README.md` remains out of scope because current `QueryScope` roots do not include repository-root documents.

### `src/vault_graph/mcp/mcp_memory_serialization.py`

Responsibilities:

- Convert memory projections to JSON-safe MCP payloads.
- Convert memory warnings to `McpErrorPayload`.
- Build evidence-backed resource links without inventing memory resource URIs.
- Keep text mirrors tied to structured payload through existing `_tool_body(...)`.

Public API:

```python
from __future__ import annotations

from typing import TYPE_CHECKING

from vault_graph.mcp.mcp_errors import McpErrorPayload
from vault_graph.memory.memory_models import (
    MemoryEvidenceRef,
    MemoryWarning,
    OpenQuestionsProjection,
    ProjectMemoryProjection,
)

if TYPE_CHECKING:
    from vault_graph.mcp.mcp_tools import McpResourceLink


def project_memory_projection_to_payload(projection: ProjectMemoryProjection) -> dict[str, object]: ...
def open_questions_projection_to_payload(projection: OpenQuestionsProjection) -> dict[str, object]: ...
def memory_warning_to_mcp_error(warning: MemoryWarning) -> McpErrorPayload: ...
def resource_links_for_memory_projection(
    projection: ProjectMemoryProjection | OpenQuestionsProjection,
) -> tuple[McpResourceLink, ...]: ...
```

Import-cycle rule:

- `mcp_tools.py` and `mcp_resources.py` must import `mcp_memory_serialization`
  inside registry/resource methods, not at module import time.
- `mcp_memory_serialization.py` must not import `McpResourceLink` from
  `mcp_tools.py` at runtime module import. Use `from __future__ import
  annotations`, `TYPE_CHECKING` for annotations, and a small local import inside
  the helper that constructs links.
- `mcp_memory_serialization.py` must define its own small
  `query_scope_to_dict(...)` helper or import one from a future neutral module.
  It must not import `query_scope_to_dict(...)` from
  `mcp_tool_serialization.py`, because that module currently imports
  `McpResourceLink` from `mcp_tools.py` at runtime.
- Add an import-boundary test that imports `vault_graph.mcp.mcp_tools`,
  `vault_graph.mcp.mcp_resources`, and `vault_graph.mcp.mcp_memory_serialization`
  in a fresh interpreter and fails on circular-import errors.

Resource-link rules:

- Every evidence-backed item with `document` in `document_resource_kinds` links to `vault://{vault_id}/documents/{path}`.
- Items with `page` in `document_resource_kinds` link to `vault://{vault_id}/pages/{path}`.
- Items with `source` in `document_resource_kinds` link to `vault://{vault_id}/sources/{document_id}`.
- Decision items with `decision` in `document_resource_kinds` link to `vault://{vault_id}/decisions/{document_id}`.
- Open-question items with `issue` in `document_resource_kinds` link to `vault://{vault_id}/issues/{document_id}`.
- No `vault://.../memory/...` URI is introduced.

### `src/vault_graph/mcp/mcp_service_factory.py`

Add lazy construction methods:

```python
class McpServiceFactory:
    def open_memory_source_reader(self) -> MemorySourceReader: ...
    def open_decision_memory_service(self) -> DecisionMemoryService: ...
    def open_issue_memory_service(self) -> IssueMemoryService: ...
    def open_project_memory_service(self) -> ProjectMemoryService: ...
```

Rules:

- Open `SQLiteMetadataStore(catalog_service.metadata_path, initialize=False)`.
- Reuse `open_status_service()` for `IndexService`.
- Pass `decision_trace_provider_factory=self.open_graph_retrieval_service`, not a concrete graph service.
- Do not store memory service instances on `McpServices` in Phase 6B.
- Do not create memory-specific state directories.
- Do not import `rustworkx` or `vault_graph.projection.rustworkx_projection` until topic-specific graph enrichment calls the provider factory.

### `src/vault_graph/mcp/mcp_tools.py`

Update tool literal:

```python
McpToolName = Literal[
    "search_vault",
    "build_context_pack",
    "find_related",
    "get_decision_trace",
    "check_index_status",
    "explain_result",
    "summarize_project_memory",
    "get_open_questions",
]
```

Add input DTOs:

```python
@dataclass(frozen=True)
class SummarizeProjectMemoryInput:
    scope: McpScopeInput | None = None
    limit: int = 10


@dataclass(frozen=True)
class GetOpenQuestionsInput:
    scope: McpScopeInput | None = None
    limit: int = 20
```

Add parsers:

```python
def parse_summarize_project_memory_input(
    *,
    scope: dict[str, object] | None = None,
    limit: int = 10,
) -> SummarizeProjectMemoryInput: ...


def parse_get_open_questions_input(
    *,
    scope: dict[str, object] | None = None,
    limit: int = 20,
) -> GetOpenQuestionsInput: ...
```

Registry methods:

```python
def summarize_project_memory(self, request: SummarizeProjectMemoryInput) -> McpToolBody: ...
def get_open_questions(self, request: GetOpenQuestionsInput) -> McpToolBody: ...
```

Behavior:

- Use `_limit(...)` for `limit` so invalid values return existing `invalid_tool_arguments` / `invalid_parameter`.
- Resolve scope with `_scope_for_tool(request.scope, catalog=self._services.catalog)`.
- `include_cross_vault` is not an input argument. If callers pass `scope.include_cross_vault=True`, existing MCP scope parsing rejects it because `allow_graph_cross_vault=False`.
- `summarize_project_memory` opens `self._service_factory.open_project_memory_service()`.
- `get_open_questions` opens `self._service_factory.open_issue_memory_service()`.
- Convert projections through `mcp_memory_serialization`.
- Tool body `text` remains `tool_text_mirror(payload)`.

FastMCP registration:

```python
@server.tool("summarize_project_memory", structured_output=True)
def summarize_project_memory(
    scope: dict[str, object] | None = None,
    limit: int = 10,
) -> dict[str, object]: ...


@server.tool("get_open_questions", structured_output=True)
def get_open_questions(
    scope: dict[str, object] | None = None,
    limit: int = 20,
) -> dict[str, object]: ...
```

### `src/vault_graph/mcp/mcp_resources.py`

Upgrade `CurrentContextResourceReader.read_current_context(...)`:

- Build `requested_scope = self._catalog.scope_for_vault_ids((vault_id,))`.
- Call `self._service_factory.open_project_memory_service().summarize(requested_scope=requested_scope, limit=10)`.
- Serialize with `project_memory_projection_to_payload(...)`.
- Return `McpResourceBody(content_mime_type="application/json", text=json.dumps(payload, ...), metadata=payload, warnings=...)`.
- Use `memory_warning_to_mcp_error(...)` for payload warnings.
- Append `recent_changes_unavailable_until_phase_6c` to the resource payload
  and resource warnings until Phase 6C provides `timeline/recent`.
- Catch `MemoryProjectionError` inside `read_current_context(...)` and raise
  `McpProtocolError` directly so the resource preserves
  `affected_vault_ids=(vault_id,)` and recovery hint
  `Run vg index, then vg status for the selected Vault.` Do not rely on the
  generic `McpResourceRegistry.read(...)` exception mapper for this resource.
- Keep `vault://{vault_id}/timeline/recent` unavailable until Phase 6C.

## State Management And Data Flow

MCP memory tool flow:

```text
summarize_project_memory / get_open_questions
  -> parse bounded MCP arguments
  -> scope_from_mcp_input(...)
  -> McpServiceFactory opens read-only metadata store and status service
  -> MemorySourceReader.list_documents(scope)
  -> services classify document-level metadata first
  -> services read bounded chunks only for selected candidates
  -> services resolve evidence through MetadataStore
  -> MCP serialization builds payload, warnings, resource links, and JSON text mirror
```

`context/current` resource flow:

```text
vault://{vault_id}/context/current
  -> parse enabled single-Vault URI
  -> catalog.scope_for_vault_ids((vault_id,))
  -> ProjectMemoryService.summarize(...)
  -> application/json resource body with the same payload shape as summarize_project_memory
```

Decision graph enrichment flow:

```text
DecisionMemoryService.list_decisions(topic=..., include_graph=True)
  -> build metadata-backed decision items first
  -> lazily open GraphRetrievalService through provider factory
  -> decision_trace(output_format="json", depth=2)
  -> append graph_decision_trace to matched_signals for matching evidence documents
  -> return warnings for graph unavailable or unmatched trace evidence
```

State guarantees:

- No Phase 6B memory service writes to Vault.
- No Phase 6B memory service creates memory storage.
- Missing metadata is a structured execution error, not an empty successful memory result.
- Empty initialized metadata is a successful empty projection with `no_memory_items_found`.
- All output groups carry Vault IDs and never merge by title/path alone.
- Deleting derived stores only removes projection inputs; rerunning `vg index` recreates the evidence basis.

## Error Handling And Edge Cases

- Invalid tool `limit` type or range:
  - parser raises existing `invalid_tool_arguments` with `kind="invalid_parameter"`.
- Unknown or disabled Vault ID:
  - existing catalog/scope handling raises validation error.
- `scope.include_cross_vault=True` for memory tools:
  - rejected because cross-Vault relationship expansion is graph-only.
- Missing metadata database:
  - `IndexService.status(...)` reports metadata unavailable; memory service raises `MemoryProjectionError("metadata_unavailable: ...")`.
- Metadata database exists but has no matching documents:
  - return empty per-Vault groups plus `no_memory_items_found`.
- Stale metadata:
  - return projection with `freshness="stale"` and warning.
- Missing vector backend:
  - warning only if status exposes it; vector state is not required for Phase 6B memory.
- Missing graph backend:
  - warning only for explicit topic-specific graph enrichment.
- Document has no chunks:
  - warning; do not emit factual item for that document.
- Chunk evidence cannot resolve:
  - warning; item emitted only if at least one evidence ref remains.
- Candidate cap exceeded:
  - include `candidate_scan_truncated` warning with affected Vault ID.
- Heading match appears after first three chunks:
  - service re-reads selected document with matched heading chunk IDs as `preferred_chunk_ids`.
- Resolved/closed issue contains TODO heading:
  - excluded from open-question output.
- Same document matches multiple groups:
  - emit item in each relevant group and attach `ambiguous_classification`.
- Multi-Vault documents share title/path/status:
  - item IDs include `vault_id` and primary evidence chunk; output remains grouped by Vault.

## Implementation Tasks

### Task 1: Metadata Document Listing Contract

**Files:**

- Modify: `src/vault_graph/storage/interfaces/metadata_store.py`
- Modify: `src/vault_graph/storage/local/sqlite_metadata_store.py`
- Modify: `tests/test_sqlite_metadata_store.py`

- [ ] **Step 1: Write failing list-document tests**

Add tests:

```python
def test_list_documents_returns_non_tombstoned_documents_for_scope(tmp_path: Path) -> None: ...
def test_list_documents_preserves_document_snapshot_fields(tmp_path: Path) -> None: ...
def test_list_documents_filters_by_vault_id_and_content_scope(tmp_path: Path) -> None: ...
def test_list_documents_orders_by_vault_path_and_document_id(tmp_path: Path) -> None: ...
def test_list_documents_returns_empty_for_missing_database_without_creating_file(tmp_path: Path) -> None: ...
```

Run:

```bash
uv run --python 3.12 pytest tests/test_sqlite_metadata_store.py -q
```

Expected: fail because `SQLiteMetadataStore.list_documents(...)` is missing.

- [ ] **Step 2: Add protocol method and SQLite implementation**

Implement the `MetadataStore.list_documents(scope)` contract exactly from the component spec.

- [ ] **Step 3: Verify Task 1**

Run:

```bash
uv run --python 3.12 pytest tests/test_sqlite_metadata_store.py tests/test_metadata_chunk_listing.py -q
```

Expected: pass.

- [ ] **Step 4: Commit Task 1**

```bash
git add src/vault_graph/storage/interfaces/metadata_store.py src/vault_graph/storage/local/sqlite_metadata_store.py tests/test_sqlite_metadata_store.py
git commit -m "feat(metadata): list indexed documents by scope"
```

### Task 2: Memory Models, Error, And Lazy Package Exports

**Files:**

- Modify: `src/vault_graph/errors.py`
- Modify: `src/vault_graph/memory/__init__.py`
- Modify: `src/vault_graph/mcp/mcp_errors.py`
- Create: `src/vault_graph/memory/memory_models.py`
- Create: `tests/test_memory_models.py`
- Modify: `tests/test_mcp_errors.py`
- Modify: `tests/test_mcp_import_boundaries.py`

- [ ] **Step 1: Write failing model validation tests**

Add tests:

```python
def test_memory_item_requires_evidence_and_positive_rank() -> None: ...
def test_memory_warning_requires_affected_vault_ids_tuple() -> None: ...
def test_memory_projection_requires_tuple_fields() -> None: ...
def test_stable_memory_item_id_includes_vault_primary_chunk_status_and_claim_status() -> None: ...
def test_memory_backend_revision_allows_missing_revision_but_requires_scope_key() -> None: ...
def test_memory_item_requires_document_resource_kind() -> None: ...
```

Run:

```bash
uv run --python 3.12 pytest tests/test_memory_models.py -q
```

Expected: fail because `memory_models.py` does not exist.

- [ ] **Step 2: Add MCP error mapping test**

In `tests/test_mcp_errors.py`, add:

```python
def test_memory_projection_error_maps_to_execution_error() -> None:
    error = map_exception_to_mcp_error(MemoryProjectionError("metadata_unavailable: not initialized"))

    assert error.kind == "execution"
    assert error.payload.code == "metadata_unavailable"


def test_invalid_memory_limit_prefix_is_preserved() -> None:
    error = map_exception_to_mcp_error(MemoryProjectionError("invalid_memory_limit: limit must be 1..50"))

    assert error.kind == "execution"
    assert error.payload.code == "invalid_memory_limit"
```

Expected: fail until the error and mapping are added.

- [ ] **Step 3: Add import-boundary test**

Extend `tests/test_mcp_import_boundaries.py` or add a dedicated test:

```python
def test_memory_models_import_is_backend_and_external_memory_free() -> None: ...
def test_memory_item_lazy_export_does_not_import_services_or_backends() -> None: ...
```

It must fail if importing `vault_graph.memory.memory_models` imports `mcp`, `chromadb`, `fastembed`, `rustworkx`, `mem0`, or `memmachine`.

- [ ] **Step 4: Implement `MemoryProjectionError`, DTOs, validation, and stable ID helper**

Keep validation in `__post_init__` methods and raise `MemoryProjectionError` for contract violations.

- [ ] **Step 5: Update lazy memory exports without broad module imports**

Add Phase 6B DTOs and services to `src/vault_graph/memory/__init__.py` using
separate symbol-to-module branches. Importing `MemoryItem` must import only
`memory_models.py`; it must not import `decision_memory.py`, `issue_memory.py`,
`project_memory.py`, `IndexService`, graph modules, MCP modules, Chroma, or
FastEmbed. Add tests for both `import vault_graph.memory` and
`from vault_graph.memory import MemoryItem`.

- [ ] **Step 6: Update MCP error mapping**

Add `MemoryProjectionError` handling. `_code_for_domain_error(...)` must recognize:

```python
"metadata_unavailable",
"memory_projection_unavailable",
"memory_evidence_unresolved",
"invalid_memory_evidence_limit",
"invalid_memory_limit",
```

Map all to `kind="execution"` unless the message is an argument validation already handled by MCP parsers.

- [ ] **Step 7: Verify Task 2**

Run:

```bash
uv run --python 3.12 pytest tests/test_memory_models.py tests/test_mcp_errors.py tests/test_mcp_import_boundaries.py -q
```

Expected: pass.

- [ ] **Step 8: Commit Task 2**

```bash
git add src/vault_graph/errors.py src/vault_graph/memory/__init__.py src/vault_graph/memory/memory_models.py src/vault_graph/mcp/mcp_errors.py tests/test_memory_models.py tests/test_mcp_errors.py tests/test_mcp_import_boundaries.py
git commit -m "feat(memory): add projection models"
```

### Task 3: Memory Source Reader

**Files:**

- Create: `src/vault_graph/memory/memory_source_reader.py`
- Create: `src/vault_graph/memory/memory_request_context.py`
- Create: `tests/test_memory_source_reader.py`
- Create: `tests/test_memory_request_context.py`

- [ ] **Step 1: Write failing source-reader tests**

Add a local fake `MetadataStore` with call recording and tests:

```python
def test_list_documents_delegates_to_metadata_store() -> None: ...
def test_read_document_loads_bounded_evidence_and_all_headings() -> None: ...
def test_read_document_prefers_matched_heading_chunk_ids() -> None: ...
def test_read_document_warns_for_unresolved_evidence() -> None: ...
def test_read_document_warns_for_document_with_no_chunks() -> None: ...
def test_read_document_body_excerpt_is_deterministic_and_capped() -> None: ...
def test_read_document_rejects_non_positive_evidence_limit() -> None: ...
def test_source_reader_has_no_scope_level_read_documents_method() -> None: ...
def test_document_resource_kinds_for_document_matches_existing_resource_classifiers() -> None: ...
```

Run:

```bash
uv run --python 3.12 pytest tests/test_memory_source_reader.py -q
```

Expected: fail because `MemorySourceReader` does not exist.

- [ ] **Step 2: Implement source reader**

Implement `MemoryHeadingRef`, `MemoryDocumentRead`, and `MemorySourceReader`.

Evidence ordering algorithm:

```python
chunks = self._metadata_store.list_document_chunks(...)
preferred = tuple(chunk for chunk in chunks if chunk.chunk_id in preferred_chunk_ids)
remaining = tuple(chunk for chunk in chunks if chunk.chunk_id not in preferred_chunk_ids)
selected = (*preferred, *remaining)[:max_evidence_chunks]
```

Use `resolve_chunk_evidence(...)` for each selected chunk and convert successful refs to `MemoryEvidenceRef`.

- [ ] **Step 3: Write and implement request-context tests**

Add tests:

```python
def test_build_memory_request_context_checks_status_before_listing_documents() -> None: ...
def test_build_memory_request_context_raises_metadata_unavailable_when_status_is_unhealthy() -> None: ...
def test_build_memory_request_context_lists_documents_once_per_actual_scope() -> None: ...
def test_build_memory_request_context_uses_one_generated_timestamp() -> None: ...
```

Implement `MemoryVaultDocuments`, `MemoryRequestContext`, and
`build_memory_request_context(...)`.

- [ ] **Step 4: Verify Task 3**

Run:

```bash
uv run --python 3.12 pytest tests/test_memory_source_reader.py tests/test_memory_request_context.py -q
```

Expected: pass.

- [ ] **Step 5: Commit Task 3**

```bash
git add src/vault_graph/memory/memory_source_reader.py src/vault_graph/memory/memory_request_context.py tests/test_memory_source_reader.py tests/test_memory_request_context.py
git commit -m "feat(memory): read bounded evidence from metadata"
```

### Task 4: Decision And Issue Memory Services

**Files:**

- Create: `src/vault_graph/memory/decision_memory.py`
- Create: `src/vault_graph/memory/issue_memory.py`
- Create: `tests/test_decision_memory_service.py`
- Create: `tests/test_issue_memory_service.py`

- [ ] **Step 1: Write failing decision service tests**

Add tests:

```python
def test_decision_service_returns_canonical_decision_path_as_stated() -> None: ...
def test_decision_service_returns_frontmatter_decision_as_stated() -> None: ...
def test_decision_service_marks_heading_only_decision_as_candidate() -> None: ...
def test_decision_service_does_not_scan_headings_for_unselected_documents() -> None: ...
def test_decision_service_prefers_late_heading_evidence_chunk() -> None: ...
def test_decision_service_enforces_candidate_read_limit_with_warning() -> None: ...
def test_decision_service_groups_identical_titles_by_vault_without_id_collision() -> None: ...
def test_decision_service_raises_metadata_unavailable_before_document_listing() -> None: ...
def test_decision_service_opens_graph_provider_only_for_topic_graph_enrichment() -> None: ...
def test_decision_service_adds_graph_signal_to_matching_metadata_backed_item() -> None: ...
def test_decision_service_warns_when_graph_enrichment_unavailable() -> None: ...
```

Run:

```bash
uv run --python 3.12 pytest tests/test_decision_memory_service.py -q
```

Expected: fail because service does not exist.

- [ ] **Step 2: Write failing issue service tests**

Add tests:

```python
def test_issue_service_returns_open_issue_path_with_active_status() -> None: ...
def test_issue_service_returns_frontmatter_question_with_active_status() -> None: ...
def test_issue_service_excludes_closed_resolved_done_and_accepted_statuses() -> None: ...
def test_issue_service_missing_status_requires_explicit_open_heading_warning() -> None: ...
def test_issue_service_heading_todo_inside_metadata_selected_document_is_candidate() -> None: ...
def test_issue_service_does_not_scan_todo_headings_for_unselected_documents() -> None: ...
def test_issue_service_prefers_late_todo_heading_evidence_chunk() -> None: ...
def test_issue_service_enforces_candidate_read_limit_with_warning() -> None: ...
def test_issue_service_groups_identical_issues_by_vault_without_id_collision() -> None: ...
```

Run:

```bash
uv run --python 3.12 pytest tests/test_issue_memory_service.py -q
```

Expected: fail.

- [ ] **Step 3: Implement shared private patterns inside each service**

Do not add a generic helper module unless duplication becomes unmaintainable. Use private functions in each service for:

- `_normalize_text(value: object) -> str`
- `_frontmatter_value(document, key) -> str`
- `_status(document) -> str | None`
- `_candidate_read_limit(limit: int) -> int`
- `_validate_limit(limit: int) -> None`
- `_freshness_from_status(report) -> MemoryFreshness`
- `_store_revisions_from_documents(...) -> tuple[MemoryBackendRevision, ...]`
- `_warning(...) -> MemoryWarning`
- `_rank_items(...) -> tuple[MemoryItem, ...]`

Keep the public surface small: only the service class and `DecisionTraceProvider` protocol are exported.

- [ ] **Step 4: Implement decision service**

Implementation order:

1. Validate `limit` is `1..50`; raise `MemoryProjectionError("invalid_memory_limit: ...")` for service-level calls. MCP calls still use `_limit(...)` before service invocation.
2. Resolve actual scopes.
3. Call `status_service.status(scope=requested_scope)` and check metadata readiness.
4. List documents per actual scope.
5. Build document-level decision candidates.
6. Read selected candidates with `MemorySourceReader`.
7. If heading matches a chunk outside selected evidence, re-read with `preferred_chunk_ids`.
8. Create `MemoryItem(kind="decision", ...)` only when at least one evidence ref exists.
9. Apply graph enrichment only after metadata-backed items exist and only when requested.
10. Return `DecisionMemoryProjection`.

- [ ] **Step 5: Implement issue service**

Follow the same service skeleton as decision memory, using open-question status and exclusion rules.

- [ ] **Step 6: Verify Task 4**

Run:

```bash
uv run --python 3.12 pytest tests/test_decision_memory_service.py tests/test_issue_memory_service.py -q
```

Expected: pass.

- [ ] **Step 7: Commit Task 4**

```bash
git add src/vault_graph/memory/decision_memory.py src/vault_graph/memory/issue_memory.py tests/test_decision_memory_service.py tests/test_issue_memory_service.py
git commit -m "feat(memory): add decision and issue projections"
```

### Task 5: Project Memory Service

**Files:**

- Create: `src/vault_graph/memory/project_memory.py`
- Create: `tests/test_project_memory_service.py`

- [ ] **Step 1: Write failing project service tests**

Add tests:

```python
def test_project_memory_composes_decisions_and_open_questions() -> None: ...
def test_project_memory_reuses_one_request_context_for_decisions_and_open_questions() -> None: ...
def test_project_memory_groups_current_state_constraints_priorities_and_stale_areas() -> None: ...
def test_project_memory_does_not_emit_backend_stale_as_stale_area_item() -> None: ...
def test_project_memory_emits_backend_warnings_and_freshness() -> None: ...
def test_project_memory_empty_metadata_returns_no_memory_items_warning() -> None: ...
def test_project_memory_keeps_per_group_limit_per_vault() -> None: ...
def test_project_memory_multi_vault_output_stays_grouped_by_vault_id() -> None: ...
def test_project_memory_does_not_open_graph_service_as_side_effect() -> None: ...
def test_project_memory_excludes_root_readme_from_current_state() -> None: ...
```

Run:

```bash
uv run --python 3.12 pytest tests/test_project_memory_service.py -q
```

Expected: fail.

- [ ] **Step 2: Implement project service**

Implementation order:

1. Validate `limit` is `1..50`.
2. Build one `MemoryRequestContext`.
3. Use `decision_service._list_decisions_from_context(..., include_graph=False, limit=limit)`.
4. Use `issue_service._open_questions_from_context(..., limit=limit)`.
5. Classify project-level candidate docs from metadata before chunk reads.
6. Read bounded evidence for project-level candidates.
7. Build one `ProjectMemoryVault` per actual Vault scope.
8. Merge warnings from status, decision projection, issue projection, and project-level classification.
9. Apply `rank` starting at `1` within each Vault group and item kind.

The project service must not duplicate decision/open-question classification; it should compose those services and own only project-level groups.

- [ ] **Step 3: Verify Task 5**

Run:

```bash
uv run --python 3.12 pytest tests/test_project_memory_service.py tests/test_decision_memory_service.py tests/test_issue_memory_service.py -q
```

Expected: pass.

- [ ] **Step 4: Commit Task 5**

```bash
git add src/vault_graph/memory/project_memory.py tests/test_project_memory_service.py
git commit -m "feat(memory): summarize project memory"
```

### Task 6: MCP Memory Serialization

**Files:**

- Create: `src/vault_graph/mcp/mcp_memory_serialization.py`
- Create: `tests/test_mcp_memory_tools.py`

- [ ] **Step 1: Write failing serialization tests**

Add tests:

```python
def test_project_memory_projection_payload_preserves_claim_status_signals_evidence_and_warnings() -> None: ...
def test_open_questions_projection_payload_preserves_vault_groups() -> None: ...
def test_memory_resource_links_include_document_page_decision_and_issue_links() -> None: ...
def test_memory_resource_links_use_document_resource_kinds_for_frontmatter_decisions_and_issues() -> None: ...
def test_memory_resource_links_do_not_link_heading_only_candidates_as_decisions_or_issues() -> None: ...
def test_memory_resource_links_do_not_create_memory_uris() -> None: ...
def test_memory_warning_maps_to_mcp_error_payload() -> None: ...
def test_memory_text_mirror_contains_no_fields_outside_structured_payload(tmp_path: Path) -> None: ...
```

Run:

```bash
uv run --python 3.12 pytest tests/test_mcp_memory_tools.py -q
```

Expected: fail because serialization module does not exist.

- [ ] **Step 2: Implement serialization helpers**

Keep this module MCP-specific and free of classification logic. Convert all tuple values to lists in payloads. Implement a local `query_scope_to_dict(...)` equivalent instead of importing from `mcp_tool_serialization.py`.

- [ ] **Step 3: Verify Task 6**

Run:

```bash
uv run --python 3.12 pytest tests/test_mcp_memory_tools.py -q
```

Expected: pass.

- [ ] **Step 4: Commit Task 6**

```bash
git add src/vault_graph/mcp/mcp_memory_serialization.py tests/test_mcp_memory_tools.py
git commit -m "feat(mcp): serialize memory projections"
```

### Task 7: MCP Service Factory Handoff

**Files:**

- Modify: `src/vault_graph/mcp/mcp_service_factory.py`
- Modify: `tests/test_mcp_service_factory.py`

- [ ] **Step 1: Write failing factory tests**

Add tests:

```python
def test_mcp_factory_opens_memory_source_reader_with_read_only_metadata_store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None: ...
def test_mcp_factory_opens_project_memory_service_without_creating_memory_state(tmp_path: Path) -> None: ...
def test_mcp_factory_memory_services_do_not_import_rustworkx_until_graph_enrichment(tmp_path: Path) -> None: ...
def test_mcp_factory_decision_memory_graph_provider_is_lazy(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None: ...
```

Run:

```bash
uv run --python 3.12 pytest tests/test_mcp_service_factory.py -q
```

Expected: fail until factory methods exist.

- [ ] **Step 2: Implement factory methods**

Use local imports inside methods. Do not add memory services to `McpServices`.

Factory construction pattern:

```python
def open_memory_source_reader(self) -> MemorySourceReader:
    from vault_graph.memory.memory_source_reader import MemorySourceReader
    from vault_graph.storage.local.sqlite_metadata_store import SQLiteMetadataStore

    catalog_service, _ = self._catalog()
    return MemorySourceReader(
        metadata_store=SQLiteMetadataStore(catalog_service.metadata_path, initialize=False)
    )
```

For service methods, call `_catalog()` once, create a matching source reader over read-only metadata, create `status_service = self.open_status_service()`, and pass dependencies. The decision service receives `decision_trace_provider_factory=self.open_graph_retrieval_service`.

- [ ] **Step 3: Verify Task 7**

Run:

```bash
uv run --python 3.12 pytest tests/test_mcp_service_factory.py tests/test_mcp_import_boundaries.py -q
```

Expected: pass.

- [ ] **Step 4: Commit Task 7**

```bash
git add src/vault_graph/mcp/mcp_service_factory.py tests/test_mcp_service_factory.py
git commit -m "feat(mcp): open memory services lazily"
```

### Task 8: MCP Memory Tools

**Files:**

- Modify: `src/vault_graph/mcp/mcp_tools.py`
- Modify: `src/vault_graph/mcp/__init__.py`
- Modify: `tests/test_mcp_tools.py`
- Modify: `tests/test_mcp_memory_tools.py`
- Modify: `tests/test_mcp_stdio_smoke.py`
- Modify: `tests/test_mcp_tool_read_only_boundary.py`

- [ ] **Step 1: Write failing MCP tool tests**

Add or extend tests:

```python
def test_register_mcp_tools_registers_exact_phase_6b_tools(tmp_path: Path) -> None: ...
def test_summarize_project_memory_uses_project_memory_service(tmp_path: Path) -> None: ...
def test_get_open_questions_uses_issue_memory_service(tmp_path: Path) -> None: ...
def test_memory_tools_support_active_vault_explicit_vault_ids_and_all_vaults(tmp_path: Path) -> None: ...
def test_memory_tools_reject_include_cross_vault_scope(tmp_path: Path) -> None: ...
def test_memory_tool_validation_rejects_bad_limits(tmp_path: Path) -> None: ...
def test_memory_tool_errors_map_memory_projection_error(tmp_path: Path) -> None: ...
def test_memory_tools_do_not_mutate_vault_bytes(tmp_path: Path) -> None: ...
def test_mcp_memory_serialization_import_has_no_cycle() -> None: ...
```

Update smoke expected tool set to include:

```python
"summarize_project_memory",
"get_open_questions",
```

Run:

```bash
uv run --python 3.12 pytest tests/test_mcp_tools.py tests/test_mcp_memory_tools.py tests/test_mcp_tool_read_only_boundary.py -q
```

Expected: fail until tools exist.

- [ ] **Step 2: Add input DTOs, parsers, registry methods, and FastMCP handlers**

Keep tool names appended after `explain_result` to preserve existing order plus additive Phase 6B tools:

```python
self.tool_names = (
    "search_vault",
    "build_context_pack",
    "find_related",
    "get_decision_trace",
    "check_index_status",
    "explain_result",
    "summarize_project_memory",
    "get_open_questions",
)
```

- [ ] **Step 3: Verify Task 8**

Run:

```bash
uv run --python 3.12 pytest tests/test_mcp_tools.py tests/test_mcp_memory_tools.py tests/test_mcp_tool_read_only_boundary.py -q
```

Expected: pass.

- [ ] **Step 4: Commit Task 8**

```bash
git add src/vault_graph/mcp/mcp_tools.py src/vault_graph/mcp/__init__.py tests/test_mcp_tools.py tests/test_mcp_memory_tools.py tests/test_mcp_stdio_smoke.py tests/test_mcp_tool_read_only_boundary.py
git commit -m "feat(mcp): add project memory tools"
```

### Task 9: `context/current` Resource Upgrade

**Files:**

- Modify: `src/vault_graph/mcp/mcp_resources.py`
- Create: `tests/test_mcp_current_context_resource.py`
- Modify: `tests/test_mcp_resources.py`
- Modify: `tests/test_mcp_resource_read_only_boundary.py`

- [ ] **Step 1: Write failing current-context resource tests**

Add tests:

```python
def test_current_context_resource_returns_single_vault_project_memory_projection(tmp_path: Path) -> None: ...
def test_current_context_resource_does_not_return_all_vault_summary(tmp_path: Path) -> None: ...
def test_current_context_resource_maps_memory_projection_error_with_recovery_hint(tmp_path: Path) -> None: ...
def test_current_context_resource_preserves_memory_warnings_in_body_and_metadata(tmp_path: Path) -> None: ...
def test_current_context_resource_does_not_mutate_vault_bytes(tmp_path: Path) -> None: ...
```

Update `tests/test_mcp_resources.py::test_current_context_resource_is_per_vault_not_all_vault_summary` so it asserts the new projection payload, not the old placeholder.

Run:

```bash
uv run --python 3.12 pytest tests/test_mcp_current_context_resource.py tests/test_mcp_resources.py tests/test_mcp_resource_read_only_boundary.py -q
```

Expected: fail until resource uses `ProjectMemoryService`.

- [ ] **Step 2: Implement resource upgrade**

Replace the placeholder metadata-health payload in `CurrentContextResourceReader.read_current_context(...)` with a serialized `ProjectMemoryProjection`.

Keep these resource invariants:

- URI is single-Vault.
- MIME type is `application/json`.
- all-Vault summaries remain tool-only.
- resource errors do not write state and include safe `vg index` / `vg status` guidance.

- [ ] **Step 3: Verify Task 9**

Run:

```bash
uv run --python 3.12 pytest tests/test_mcp_current_context_resource.py tests/test_mcp_resources.py tests/test_mcp_resource_read_only_boundary.py -q
```

Expected: pass.

- [ ] **Step 4: Commit Task 9**

```bash
git add src/vault_graph/mcp/mcp_resources.py tests/test_mcp_current_context_resource.py tests/test_mcp_resources.py tests/test_mcp_resource_read_only_boundary.py
git commit -m "feat(mcp): expose current project memory resource"
```

### Task 10: Prompt Updates, Boundary Guards, And Full Verification

**Files:**

- Modify: `src/vault_graph/mcp/mcp_prompts.py`
- Modify: `tests/test_mcp_prompts.py`
- Modify: `tests/test_mcp_import_boundaries.py`
- Modify: `tests/test_naming_conventions.py` only if new wording accidentally violates existing naming rules.

- [ ] **Step 1: Write failing prompt tests**

Update prompt expectations:

```python
def test_prompt_text_mentions_registered_phase_6b_memory_tools() -> None: ...
def test_prompt_text_still_omits_unregistered_future_tools() -> None: ...
```

Required prompt behavior:

- `generate_codex_brief` and `prepare_implementation_context` mention `summarize_project_memory`.
- risk and wiki-update prompts mention `get_open_questions`.
- prompts still do not mention `ask_vault` or `get_recent_changes`.
- prompts keep read-only Vault publication boundary.

- [ ] **Step 2: Add/import boundary guard for forbidden memory drift**

Add a test that scans `src/vault_graph/memory` and MCP memory files for forbidden identifiers:

```python
FORBIDDEN_MEMORY_SURFACES = (
    "MemoryStore",
    "Memory.create",
    "Memory.query",
    "Memory.upsert",
    "Memory.link",
    "Memory.audit",
    "episode_log",
    "profile_memory",
    "mem0",
    "memmachine",
)
```

This can live in `tests/test_mcp_import_boundaries.py` or a new memory boundary test if cleaner.

- [ ] **Step 3: Verify prompts and boundaries**

Run:

```bash
uv run --python 3.12 pytest tests/test_mcp_prompts.py tests/test_mcp_import_boundaries.py tests/test_naming_conventions.py -q
```

Expected: pass.

- [ ] **Step 4: Run focused Phase 6B suites**

```bash
uv run --python 3.12 pytest tests/test_memory_models.py tests/test_memory_source_reader.py -q
uv run --python 3.12 pytest tests/test_decision_memory_service.py tests/test_issue_memory_service.py tests/test_project_memory_service.py -q
uv run --python 3.12 pytest tests/test_mcp_memory_tools.py tests/test_mcp_current_context_resource.py -q
```

Expected: pass.

- [ ] **Step 5: Run MCP regression suites**

```bash
uv run --python 3.12 pytest tests/test_mcp_tools.py tests/test_mcp_resources.py tests/test_mcp_server.py tests/test_mcp_service_factory.py tests/test_mcp_prompts.py tests/test_mcp_tool_read_only_boundary.py tests/test_mcp_resource_read_only_boundary.py -q
```

Expected: pass.

- [ ] **Step 6: Run official MCP stdio smoke**

```bash
VG_RUN_MCP_STDIO_SMOKE=1 uv run --python 3.12 pytest tests/test_mcp_stdio_smoke.py -q
```

Expected: pass and list exactly the Phase 6B tool set.

- [ ] **Step 7: Run full repository verification**

```bash
uv run --python 3.12 pytest -q
uv run --python 3.12 ruff check src tests
uv run --python 3.12 mypy src tests
git diff --check
```

Expected: all pass with no output from `git diff --check`.

- [ ] **Step 8: Commit Task 10**

Only commit if Task 10 changed files:

```bash
git add src tests
git commit -m "test(memory): verify phase 6b boundaries"
```

## Test Matrix

| Behavior | Test File |
| --- | --- |
| metadata document listing contract | `tests/test_sqlite_metadata_store.py` |
| memory DTO validation and stable IDs | `tests/test_memory_models.py` |
| source reader bounded evidence and headings | `tests/test_memory_source_reader.py` |
| decision classification and graph enrichment | `tests/test_decision_memory_service.py` |
| issue/open-question classification | `tests/test_issue_memory_service.py` |
| project memory composition | `tests/test_project_memory_service.py` |
| MCP memory payloads and resource links | `tests/test_mcp_memory_tools.py` |
| MCP memory tool registration and validation | `tests/test_mcp_tools.py`, `tests/test_mcp_memory_tools.py` |
| `context/current` resource upgrade | `tests/test_mcp_current_context_resource.py`, `tests/test_mcp_resources.py` |
| read-only Vault boundary | `tests/test_mcp_tool_read_only_boundary.py`, `tests/test_mcp_resource_read_only_boundary.py` |
| service factory laziness | `tests/test_mcp_service_factory.py`, `tests/test_mcp_import_boundaries.py` |
| prompt mentions only registered tools | `tests/test_mcp_prompts.py` |
| official MCP SDK compatibility | `tests/test_mcp_stdio_smoke.py` |
| no generic writable memory/external dependency | `tests/test_mcp_import_boundaries.py` |

## Verification Commands

Run before considering implementation complete:

```bash
uv run --python 3.12 pytest tests/test_memory_models.py tests/test_memory_source_reader.py -q
uv run --python 3.12 pytest tests/test_decision_memory_service.py tests/test_issue_memory_service.py tests/test_project_memory_service.py -q
uv run --python 3.12 pytest tests/test_mcp_memory_tools.py tests/test_mcp_current_context_resource.py tests/test_mcp_tools.py tests/test_mcp_resources.py -q
uv run --python 3.12 pytest tests/test_mcp_server.py tests/test_mcp_service_factory.py tests/test_mcp_prompts.py tests/test_mcp_tool_read_only_boundary.py tests/test_mcp_resource_read_only_boundary.py -q
VG_RUN_MCP_STDIO_SMOKE=1 uv run --python 3.12 pytest tests/test_mcp_stdio_smoke.py -q
uv run --python 3.12 pytest -q
uv run --python 3.12 ruff check src tests
uv run --python 3.12 mypy src tests
git diff --check
```

## Risks And Mitigations

- **Risk:** memory terminology drifts into a writable memory layer.
  **Mitigation:** add only specific read services; import/boundary tests reject generic memory stores, episode logs, profile memory, and external memory dependencies.
- **Risk:** deterministic memory looks like unsupported synthesis.
  **Mitigation:** require evidence on every `MemoryItem`, preserve `claim_status` and `matched_signals`, and keep summaries deterministic excerpts or metadata-derived phrases.
- **Risk:** broad scopes cause unbounded chunk reads.
  **Mitigation:** metadata-first narrowing, per-Vault candidate caps, max three evidence chunks per item, and visible truncation warnings.
- **Risk:** open-question projection includes already resolved work.
  **Mitigation:** status exclusion list is tested; missing status requires explicit open-question heading and warning.
- **Risk:** optional graph enrichment opens heavy graph dependencies during ordinary memory summaries.
  **Mitigation:** graph provider factory is called only for topic-specific `include_graph=True`; project memory never requests graph enrichment.
- **Risk:** all-Vault output hides source ownership.
  **Mitigation:** output groups by Vault ID; stable IDs, warnings, evidence refs, and resource links include Vault IDs.
- **Risk:** `context/current` resource becomes a full-Vault dump.
  **Mitigation:** resource URI remains single-Vault; all-Vault memory remains tool-only and bounded by per-group limits.

## Validation Review

Security and read-only safety:

- Memory services read only `MetadataStore`, `IndexService.status(...)`, and optional graph retrieval DTOs.
- No service opens Vault files, calls `VaultLoader`, or runs `IndexService.apply(...)` / `run_apply(...)`.
- MCP tools/resources use application services instead of direct SQLite or Vault file access.
- Read-only tests compare Vault bytes before and after memory tool/resource calls.

Performance and scalability:

- Candidate narrowing happens at indexed metadata level before chunk/evidence reads.
- Per-Vault candidate cap is bounded by `min(max(limit * 10, 50), 250)`.
- Each emitted item carries at most three evidence refs.
- Graph enrichment is lazy and topic-specific.
- Future scale-up backends need only implement the same `MetadataStore.list_documents(...)` contract.

Testability:

- DTOs, source reader, each memory service, MCP serialization, tools, resources, prompts, factory laziness, and read-only boundaries have focused tests.
- Services can be tested with fake metadata/status/graph providers without FastMCP.
- Official stdio smoke remains the final MCP SDK compatibility check.

Maintainability and deep-module boundaries:

- `memory_models.py` owns DTO validity and stable IDs.
- `memory_source_reader.py` owns evidence loading and warnings for selected documents.
- `decision_memory.py`, `issue_memory.py`, and `project_memory.py` own domain-specific classification and service flow.
- `mcp_memory_serialization.py` owns MCP payload/resource-link conversion.
- `mcp_tools.py` and `mcp_resources.py` stay adapter modules and do not duplicate memory classification.

Agent ergonomics:

- Agents can call `summarize_project_memory` before broad search.
- Agents can call `get_open_questions` when unresolved follow-up context matters.
- Agents can inspect `claim_status`, `matched_signals`, warnings, evidence refs, and resource links instead of trusting fluent summaries.
- `context/current` becomes a useful single-Vault resource without changing URI templates.

## Open Decisions

None. The Phase 6B SPEC fixes the policy choices: deterministic projection only, metadata-first bounded candidate narrowing, Chroma/vector not required, lazy optional graph enrichment, no external writable memory layer, and no new durable memory store.

## Patch Log Impact

No `docs/PATCH_LOG.md` entry is required for implementing this plan as written. Add an entry only if review or verification changes this plan, a SPEC, or implementation behavior because a concrete mismatch, defect, or risk is found.
