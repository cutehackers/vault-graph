# Phase 6B Project, Decision, And Issue Memory SPEC

Status: Draft for implementation planning

Date: 2026-06-18

Scope: Phase 6B

## 1. Purpose

Phase 6B adds deterministic memory projections over indexed Vault evidence:

- project memory: current state, recent decisions, open issues, constraints,
  next likely priorities, and stale areas
- decision memory: decision documents and graph decision traces grouped by
  topic, status, tradeoff, and revisit condition
- issue memory: unresolved questions, follow-ups, missing evidence, and revisit
  triggers

The goal is to help agents inspect project memory without scanning an entire
Vault and without turning generated summaries into durable knowledge.

## 2. Success Criteria

Phase 6B is complete when:

- `ProjectMemoryService.summarize(...)` returns an evidence-linked structured
  projection for a selected `QueryScope`.
- `DecisionMemoryService.list_decisions(...)` groups durable decisions and
  inferred topic traces without merging Vaults by title.
- `IssueMemoryService.open_questions(...)` returns unresolved questions and
  follow-ups with evidence and warnings.
- MCP registers `summarize_project_memory` and `get_open_questions` only after
  the backing services exist.
- `vault://{vault_id}/context/current` returns a project memory projection
  instead of only backend availability.
- outputs preserve Vault IDs, evidence references, warnings, store revisions,
  and freshness.
- no memory service writes to Vault or treats projection output as source truth.

## 3. In Scope

- `vault_graph.memory` DTOs for project, decision, and issue memory.
- metadata-backed document listing contract.
- deterministic document classification using path, frontmatter, headings, and
  graph entity type when available.
- project memory and open-question MCP tools.
- `context/current` MCP resource upgrade.
- read-only, multi-Vault, stale-state, and serialization tests.

## 4. Out Of Scope

- LLM-written narrative summaries
- `ask_vault` answer synthesis
- autonomous wiki publication
- resolving issues or decisions automatically
- durable memory database
- generic writable `MemoryStore` or `Memory.create/query/upsert/link/audit` API
- Mem0, MemMachine, or MCP memory-server integration
- profile, preference, procedural, or raw episode memory
- UI explorer screens
- remote backend migration

## 5. Files To Add Or Modify

Add:

```text
src/vault_graph/memory/memory_models.py
src/vault_graph/memory/memory_source_reader.py
src/vault_graph/memory/project_memory.py
src/vault_graph/memory/decision_memory.py
src/vault_graph/memory/issue_memory.py
src/vault_graph/mcp/mcp_memory_serialization.py
tests/test_memory_models.py
tests/test_memory_source_reader.py
tests/test_project_memory_service.py
tests/test_decision_memory_service.py
tests/test_issue_memory_service.py
tests/test_mcp_memory_tools.py
tests/test_mcp_current_context_resource.py
```

Modify:

```text
src/vault_graph/storage/interfaces/metadata_store.py
src/vault_graph/storage/local/sqlite_metadata_store.py
src/vault_graph/mcp/mcp_service_factory.py
src/vault_graph/mcp/mcp_resources.py
src/vault_graph/mcp/mcp_tools.py
src/vault_graph/mcp/mcp_server.py
src/vault_graph/mcp/__init__.py
tests/fakes/
tests/test_mcp_resources.py
tests/test_mcp_stdio_smoke.py
```

## 6. Metadata Read Contract

Phase 6B needs document-level frontmatter and timestamps without direct SQLite
queries. Add this method to `MetadataStore`:

```python
class MetadataStore(Protocol):
    def list_documents(self, scope: QueryScope) -> tuple[DocumentSnapshot, ...]: ...
```

Local implementation rules:

- return non-tombstoned documents only;
- filter by explicit `QueryScope.vault_ids` and `content_scopes`;
- order by `vault_id`, path for deterministic output;
- do not initialize schema in read-only mode;
- preserve frontmatter, content hashes, `last_seen_at`, `last_indexed_at`,
  `vault_revision`, and `index_revision`.

This method is read-only and belongs to the metadata evidence boundary. Memory
services must not query local SQLite tables directly.

## 7. Shared Memory Models

`src/vault_graph/memory/memory_models.py` owns shared MCP-free DTOs.

```python
from dataclasses import dataclass
from typing import Literal

MemoryItemKind = Literal[
    "current_state",
    "decision",
    "issue",
    "constraint",
    "next_priority",
    "stale_area",
]

MemoryWarningSeverity = Literal["info", "warning", "error"]

@dataclass(frozen=True)
class MemoryEvidenceRef:
    vault_id: str
    document_id: str
    chunk_id: str | None
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
class MemoryItem:
    item_id: str
    kind: MemoryItemKind
    title: str
    summary: str
    vault_id: str
    path: str
    status: str | None
    rank: int
    evidence: tuple[MemoryEvidenceRef, ...]
    warnings: tuple[MemoryWarning, ...]

@dataclass(frozen=True)
class ProjectMemoryProjection:
    requested_scope: QueryScope
    actual_scopes: tuple[QueryScope, ...]
    current_state: tuple[MemoryItem, ...]
    recent_decisions: tuple[MemoryItem, ...]
    open_questions: tuple[MemoryItem, ...]
    constraints: tuple[MemoryItem, ...]
    next_priorities: tuple[MemoryItem, ...]
    stale_areas: tuple[MemoryItem, ...]
    warnings: tuple[MemoryWarning, ...]
    store_revisions: tuple[dict[str, object], ...]
    generated_at: str
```

Model rules:

- `MemoryItem.summary` is an excerpt or deterministic metadata summary, not an
  LLM-written conclusion.
- `MemoryItem` requires at least one evidence reference.
- `item_id` is stable for the same `(kind, vault_id, document_id, path, status)`.
- projection groups may be empty, but gaps that affect confidence create
  top-level warnings.

## 8. Source Reader

`MemorySourceReader` centralizes document and evidence loading:

```python
@dataclass(frozen=True)
class MemoryDocumentRead:
    document: DocumentSnapshot
    evidence: tuple[MemoryEvidenceRef, ...]
    warnings: tuple[MemoryWarning, ...]

class MemorySourceReader:
    def __init__(self, *, metadata_store: MetadataStore) -> None: ...
    def list_documents(self, *, scope: QueryScope) -> tuple[DocumentSnapshot, ...]: ...
    def read_document(self, *, document: DocumentSnapshot, max_chunks: int = 3) -> MemoryDocumentRead: ...
    def read_documents(self, *, scope: QueryScope, max_chunks_per_document: int = 3) -> tuple[MemoryDocumentRead, ...]: ...
```

Rules:

- never read Vault files directly;
- use metadata store evidence resolution;
- return `MemoryDocumentRead.warnings` for documents without chunks or unresolved
  evidence;
- cap evidence per document to keep memory payloads bounded.

## 9. No Generic Writable Memory API

Phase 6B exposes specific read services, not a general memory facade. The
implementation must not add:

- `MemoryStore`, `Memory.create`, `Memory.query`, `Memory.upsert`,
  `Memory.link`, or `Memory.audit`;
- writable project memory records;
- raw episode logs or session transcript storage;
- profile, preference, or procedural memory tables;
- direct Mem0, MemMachine, or MCP memory-server dependencies.

Future external memory adapters may export `ProjectMemoryProjection`,
`DecisionMemoryProjection`, or `OpenQuestionsProjection`, but they must consume
those DTOs as outbound evidence-linked projections. They must not write back to
Vault Graph stores or turn agent-generated memory into source truth.

## 10. Classification Policy

Classification is deterministic and conservative.

Decision candidates:

- path starts with `wiki/decisions/`
- frontmatter `type: decision`
- graph entity type `Decision` when graph service is explicitly available

Issue or open-question candidates:

- path starts with `wiki/issues/`
- frontmatter `type: issue`
- frontmatter `status` in `open`, `unresolved`, `todo`, `blocked`
- headings containing `Open Questions`, `Follow-up`, `TODO`, or `Revisit`

Current-state candidates:

- frontmatter `type` in `project_status`, `status`, `roadmap`
- path contains `status`, `roadmap`, `plan`, or `overview`
- root project documents such as `README.md`, `docs/SPEC.md`, `docs/FEATURES.md`
  only when inside the selected Vault scope

Next-priority candidates:

- frontmatter `priority`, `next`, or `roadmap`
- headings containing `Next`, `Priorities`, `Roadmap`, or `Implementation Order`

If classification is ambiguous, the item can appear in multiple groups with the
same evidence and an `ambiguous_classification` warning.

## 11. Services

Project memory:

```python
class ProjectMemoryService:
    def __init__(
        self,
        *,
        catalog: VaultCatalog,
        source_reader: MemorySourceReader,
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

Decision memory:

```python
@dataclass(frozen=True)
class DecisionMemoryProjection:
    requested_scope: QueryScope
    actual_scopes: tuple[QueryScope, ...]
    decisions: tuple[MemoryItem, ...]
    warnings: tuple[MemoryWarning, ...]
    store_revisions: tuple[dict[str, object], ...]
    generated_at: str

class DecisionMemoryService:
    def list_decisions(
        self,
        *,
        requested_scope: QueryScope,
        topic: str | None = None,
        limit: int = 20,
    ) -> DecisionMemoryProjection: ...
```

Issue memory:

```python
@dataclass(frozen=True)
class OpenQuestionsProjection:
    requested_scope: QueryScope
    actual_scopes: tuple[QueryScope, ...]
    questions: tuple[MemoryItem, ...]
    warnings: tuple[MemoryWarning, ...]
    store_revisions: tuple[dict[str, object], ...]
    generated_at: str

class IssueMemoryService:
    def open_questions(
        self,
        *,
        requested_scope: QueryScope,
        limit: int = 20,
    ) -> OpenQuestionsProjection: ...
```

Services must expand requested scopes through `actual_query_scopes(...)` before
reading stores.

## 12. MCP Tools And Resources

Add tools:

```text
summarize_project_memory(scope=None, limit=10)
get_open_questions(scope=None, limit=20)
```

MCP input DTOs:

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

Resource upgrade:

```text
vault://{vault_id}/context/current
```

This resource returns `ProjectMemoryProjection` for the selected single Vault.
All-Vault summaries remain tool-only because resource URIs carry one Vault ID.

## 13. Error And Degradation Policy

- invalid scope or unknown Vault ID: validation error
- missing metadata backend: execution error with `Run vg index`
- stale metadata: warning plus freshness fields
- missing vector backend: warning only; memory can still use metadata evidence
- missing graph backend: warning only unless the caller requested graph-derived
  decision grouping
- no matching memory items: successful empty projection plus
  `no_memory_items_found` warning

## 14. Multi-Vault Policy

- default tools use the active Vault.
- explicit all-Vault scope groups output by `vault_id`.
- item IDs include `vault_id` and never merge by title alone.
- warnings carry affected Vault IDs.
- cross-Vault graph relationship grouping remains out of scope for Phase 6B
  unless explicitly requested by a future graph memory slice.

## 15. Tests

Required tests:

- `MetadataStore.list_documents(...)` contract and local implementation.
- classification by path, frontmatter, and headings.
- project memory groups evidence and warnings deterministically.
- open questions include issue docs and follow-up headings.
- decision memory prefers durable decision docs.
- multi-Vault documents with identical paths do not collide.
- MCP tools serialize structured memory projections.
- `context/current` returns project memory for one Vault.
- read-only boundary tests assert no Vault file mutations.
- import or boundary tests assert Phase 6B does not introduce a writable
  `MemoryStore` or external memory dependency.

Verification commands:

```bash
uv run --python 3.12 pytest tests/test_memory_models.py tests/test_memory_source_reader.py -q
uv run --python 3.12 pytest tests/test_project_memory_service.py tests/test_decision_memory_service.py tests/test_issue_memory_service.py -q
uv run --python 3.12 pytest tests/test_mcp_memory_tools.py tests/test_mcp_current_context_resource.py tests/test_mcp_resources.py -q
uv run --python 3.12 ruff check src tests
uv run --python 3.12 mypy src tests
```

## 16. Risks And Mitigations

- **Risk:** deterministic memory can look less fluent than an LLM summary.
  **Mitigation:** preserve structured groups and evidence first; answer
  synthesis remains a later phase.
- **Risk:** broad document classification creates noisy memory.
  **Mitigation:** keep classifiers conservative, bounded by limit, and warning
  on ambiguous items.
- **Risk:** adding document listing widens `MetadataStore`.
  **Mitigation:** make it read-only, scope-filtered, and contract-tested across
  local and future scale-up backends.
- **Risk:** "memory" naming makes developers add a generic writable memory
  layer.
  **Mitigation:** keep only specific read services and add boundary tests that
  reject writable memory-store or external memory dependencies.

## 17. Open Decisions

None for Phase 6B. LLM-written project summaries remain out of scope.
