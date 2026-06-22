# Phase 6B Project, Decision, And Issue Memory SPEC

Status: Draft for implementation planning

Date: 2026-06-18

Scope: Phase 6B

## 1. Purpose

Phase 6B adds deterministic memory projections over indexed Vault evidence. It
lets agents inspect current project state, durable decisions, and unresolved
questions without scanning the whole Vault and without turning generated output
into durable knowledge.

Phase 6B memory is projection terminology only. It is not a writable memory
database, not an LLM summary store, and not an external memory layer. Every
claim in project, decision, and issue memory must resolve back to indexed Vault
evidence.

## 2. User Value

Phase 6B should answer these operational questions:

- What is the current state of this project?
- Which decisions and constraints matter now?
- Which open questions, TODOs, blockers, or revisit triggers remain unresolved?
- Which evidence and index revisions support those memory items?
- Which parts of the projection are stale, missing, ambiguous, or degraded?

The output is structured context for humans and agents. Durable updates still
belong in Vault through the normal capture, validation, release gate, and Git
workflow.

## 3. Success Criteria

Phase 6B is complete when:

- `MetadataStore.list_documents(scope)` exposes a read-only, scope-filtered
  document listing contract for current non-tombstoned indexed documents.
- `MemorySourceReader` loads document snapshots and bounded chunk evidence only
  through `MetadataStore`; it never reads Vault files or SQLite tables directly.
- `ProjectMemoryService.summarize(...)` returns a grouped,
  evidence-linked `ProjectMemoryProjection` for the requested `QueryScope`.
- `DecisionMemoryService.list_decisions(...)` returns decision memory over
  durable decision evidence, grouped by Vault ID, and can optionally enrich a
  topic-specific view with existing graph decision-trace evidence when graph
  services are available.
- `IssueMemoryService.open_questions(...)` returns unresolved issues,
  follow-ups, TODOs, blockers, and revisit triggers with evidence and warnings.
- MCP registers `summarize_project_memory` and `get_open_questions` only after
  the backing services exist.
- `vault://{vault_id}/context/current` returns the single-Vault project memory
  projection instead of the Phase 5B backend-availability placeholder.
- outputs preserve Vault IDs, stable item IDs, evidence references, warnings,
  store revisions, freshness, actual scopes, and generated timestamps.
- multi-Vault output is grouped by `vault_id` and never merges documents,
  decisions, issues, or entities by title alone.
- no Phase 6B service writes to Vault, initializes read-only stores, persists
  memory records, imports external memory systems, or treats projection output
  as source truth.

## 4. In Scope

- MCP-free memory DTOs for project, decision, and issue projections.
- metadata-backed document listing on `MetadataStore`.
- bounded evidence loading through indexed chunks.
- deterministic document classification using path, frontmatter, headings, and
  optional graph evidence already available through existing graph services.
- project memory and open-question MCP tools.
- `context/current` MCP resource upgrade.
- prompt text updates that prefer memory tools before broad Vault scans.
- read-only, multi-Vault, stale-state, serialization, and import-boundary tests.

## 5. Out Of Scope

- LLM-written narrative summaries
- `ask_vault` answer synthesis
- autonomous wiki publication or Vault edits
- resolving issues or decisions automatically
- durable memory database or memory history
- generic writable `MemoryStore` or `Memory.create/query/upsert/link/audit` API
- Mem0, MemMachine, or MCP memory-server integration
- profile, preference, procedural, or raw episode memory
- UI explorer screens
- remote backend migration
- hosted monitoring

## 6. Files To Add Or Modify

Add:

```text
src/vault_graph/memory/memory_models.py
src/vault_graph/memory/memory_source_reader.py
src/vault_graph/memory/memory_request_context.py
src/vault_graph/memory/project_memory.py
src/vault_graph/memory/decision_memory.py
src/vault_graph/memory/issue_memory.py
src/vault_graph/mcp/mcp_memory_serialization.py
tests/test_memory_models.py
tests/test_memory_source_reader.py
tests/test_memory_request_context.py
tests/test_project_memory_service.py
tests/test_decision_memory_service.py
tests/test_issue_memory_service.py
tests/test_mcp_memory_tools.py
tests/test_mcp_current_context_resource.py
```

Modify:

```text
src/vault_graph/errors.py
src/vault_graph/memory/__init__.py
src/vault_graph/storage/interfaces/metadata_store.py
src/vault_graph/storage/local/sqlite_metadata_store.py
src/vault_graph/mcp/__init__.py
src/vault_graph/mcp/mcp_errors.py
src/vault_graph/mcp/mcp_prompts.py
src/vault_graph/mcp/mcp_resources.py
src/vault_graph/mcp/mcp_server.py
src/vault_graph/mcp/mcp_service_factory.py
src/vault_graph/mcp/mcp_tools.py
tests/fakes/
tests/test_mcp_errors.py
tests/test_mcp_prompts.py
tests/test_mcp_resource_read_only_boundary.py
tests/test_mcp_resources.py
tests/test_mcp_server.py
tests/test_mcp_service_factory.py
tests/test_mcp_stdio_smoke.py
```

Do not add persistence files under `data/memory/`. Phase 6B projections are
computed from existing derived indexes at request time.

## 7. Existing Dependencies

Phase 6B builds on current code contracts:

- `DocumentSnapshot` and `ChunkSnapshot` from
  `vault_graph.ingestion.document_normalizer`
- `QueryScope`, `VaultCatalog`, and `actual_query_scopes(...)`
- `MetadataStore.list_document_chunks(...)` and
  `MetadataStore.resolve_chunk_evidence(...)`
- `IndexService.status(...)` for freshness and backend degradation
- `GraphRetrievalService.decision_trace(...)` only as an optional enrichment
  path for topic-specific decision memory
- Phase 6A `vault_graph.memory` package and MCP read-only adapter style

MCP and resource layers must depend on memory application services. They must
not duplicate classification, query SQLite directly, or read Vault files.

## 8. Metadata Read Contract

Phase 6B needs document-level frontmatter, path, timestamps, hashes, and index
revision data without direct SQLite queries. Add this method to
`MetadataStore`:

```python
class MetadataStore(Protocol):
    def list_documents(self, scope: QueryScope) -> tuple[DocumentSnapshot, ...]: ...
```

Local implementation rules:

- return current non-tombstoned documents only;
- return `()` when the metadata database is missing instead of initializing it;
- filter by `scope.vault_ids`;
- filter by `scope.content_scopes` using the same content-scope narrowing rules
  used by chunk listing;
- order by `vault_id`, `path`, then `document_id`;
- preserve all current `DocumentSnapshot` fields exactly:
  `vault_id`, `document_id`, `path`, `kind`, `frontmatter`,
  `frontmatter_hash`, `content_hash`, `raw_sha256`, `parser_version`,
  `last_seen_at`, `last_indexed_at`, `vault_revision`, and `index_revision`;
- do not create schema, run migrations, update tombstones, or mutate keyword,
  vector, graph, or status state.

This method is part of the metadata evidence boundary. Memory services must not
depend on local SQLite table names, row IDs, or private store fields.

## 9. Shared Memory Models

`src/vault_graph/memory/memory_models.py` owns shared MCP-free DTOs.

```python
from dataclasses import dataclass
from typing import Literal

MemoryItemKind = Literal[
    "current_state",
    "decision",
    "open_question",
    "constraint",
    "next_priority",
    "stale_area",
]
MemoryClaimStatus = Literal[
    "stated",
    "metadata_derived",
    "heading_candidate",
]
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
```

Decision and issue projections use the same grouping pattern:

```python
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
```

Model rules:

- constructors validate required strings and tuple immutability like existing
  retrieval and context-pack DTOs.
- `MemoryItem.evidence` must contain at least one chunk evidence reference.
  Documents with no resolved chunk evidence create warnings and are not emitted
  as factual memory items.
- `MemoryItem.summary` is a deterministic excerpt or metadata-derived phrase.
  It must not be an LLM-written conclusion.
- `MemoryItem.document_resource_kinds` lists the existing MCP document resource
  views that are valid for the backing document. It must always include
  `document`; it may include `page`, `source`, `decision`, or `issue` only when
  the backing path or canonical frontmatter satisfies the corresponding
  existing resource-reader classifier. Heading-only candidates must not receive
  `decision` or `issue` resource kinds unless the document path or frontmatter
  also supports that resource.
- `claim_status` labels how the item was identified:
  - `stated`: canonical Vault evidence such as frontmatter type/status or a
    canonical decision/issue path states the classification directly;
  - `metadata_derived`: path, document kind, or non-canonical frontmatter
    suggests the classification;
  - `heading_candidate`: a heading suggests the classification but the document
    does not state it as canonical metadata.
- text mirrors and MCP payloads must preserve `claim_status` and
  `matched_signals` so heuristic candidates do not look like stated Vault facts.
- graph enrichment is represented in `matched_signals` such as
  `graph_decision_trace`; it does not override the item's original
  `claim_status`.
- `item_id` is a bounded stable handle derived from canonical fields:
  `memory:<kind>:<24 hex chars>`, where the hash input includes `kind`,
  `vault_id`, `document_id`, the primary evidence `chunk_id`, normalized title,
  normalized `status`, and `claim_status`.
- `rank` starts at `1` within each Vault group and item kind.
- top-level warnings describe scope or backend problems; Vault-group warnings
  describe Vault-specific gaps; item warnings describe item-specific ambiguity.
- Phase 6B does not claim evidence-backed recency for decisions or durable
  changes. Timeline-based recent changes belong to Phase 6C. Project memory may
  be used by `context/current`; that resource may append a
  `recent_changes_unavailable_until_phase_6c` info warning until Phase 6C
  provides timeline-backed recent changes.

## 10. Source Reader

`MemorySourceReader` centralizes document and evidence loading:

```python
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
```

Rules:

- `list_documents(...)` delegates to `MetadataStore.list_documents(...)`.
- `read_document(...)` delegates to
  `MetadataStore.list_document_chunks(vault_id=..., document_id=...)` and then
  `resolve_chunk_evidence(...)`.
- `MemorySourceReader` does not expose a scope-level `read_documents(...)`
  method in Phase 6B. Services own candidate narrowing and call
  `read_document(...)` only for selected document snapshots.
- chunk order follows `list_document_chunks(...)`, which preserves indexed
  document order.
- all chunk headings for a selected document are inspected and returned as
  `MemoryHeadingRef` records. Heading inspection is separate from evidence
  payload size.
- evidence is capped by `max_evidence_chunks` to keep payloads bounded.
- `preferred_chunk_ids` are resolved first, then remaining document-order chunks
  fill the evidence cap. Services use this to prefer chunks whose headings
  matched `Decision`, `TODO`, `Blocker`, `Revisit`, or similar rules even when
  those chunks appear after the first three document chunks.
- `headings` comes from resolved chunks' `section` values, not from reparsing
  Vault files.
- `body_excerpt` is the first non-empty chunk text trimmed to a deterministic
  maximum of 280 characters.
- unresolved chunk evidence creates `unresolved_evidence` warnings.
- documents with no chunks create `document_has_no_chunks` warnings.
- read methods do not run indexing, initialize stores, access Vault paths, or
  synthesize evidence.

`MemoryRequestContext` is a small per-request read context used by memory
services:

```python
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
```

Context rules:

- context creation resolves actual scopes, checks `IndexService.status(...)`,
  and lists document snapshots once per actual Vault scope;
- metadata-unavailable or schema-incompatible status raises
  `MemoryProjectionError("metadata_unavailable: ...")`;
- context creation does not read chunks, graph data, or Vault files;
- `ProjectMemoryService` builds one context and uses package-internal
  decision/issue service methods that consume that context, so project memory
  does not repeat metadata/status scans.

## 11. Candidate Narrowing Policy

"Without scanning the whole Vault" means Phase 6B does not read Vault source
files at request time. It may scan indexed metadata rows for the selected
`QueryScope`.

Services must still narrow candidates before chunk evidence reads:

1. list document snapshots through `MetadataStore.list_documents(...)`;
2. classify path, document kind, frontmatter type/status, and revision metadata
   first;
3. select a deterministic per-Vault candidate set before reading chunks from
   documents matched by path, document kind, frontmatter, revision metadata, or
   other document-level indexed fields;
4. read chunks only for selected candidates;
5. inspect all headings for selected candidates, while keeping evidence and
   excerpts capped;
6. return `candidate_scan_truncated` warnings when the candidate set exceeds the
   read cap.

Default bounds:

- `candidate_read_limit = min(max(limit * 10, 50), 250)` per Vault and per
  service call.
- `max_evidence_chunks = 3` per emitted memory item.

The implementation may tune these constants later, but Phase 6B must keep the
same behavior: metadata-first narrowing, bounded chunk reads, deterministic
ordering, and visible truncation warnings.

Heading-only matches are intentionally limited to metadata-selected documents in
Phase 6B. The service must not scan chunks for every document in a large scope
just to discover arbitrary TODO headings. If this misses an otherwise
unclassified TODO, the user can narrow the scope or rely on later search/context
flows; Phase 6B favors bounded, explainable projection over unbounded heading
mining.

## 12. Classification Policy

Classification is deterministic, conservative, and case-insensitive for path
segments, frontmatter string values, and heading matches.

Heading rules refine only metadata-selected documents. A document becomes
metadata-selected through path, document kind, frontmatter, revision metadata, or
another document-level indexed field. Phase 6B does not scan headings across
otherwise unclassified documents.

Decision candidates:

- path starts with `wiki/decisions/`;
- frontmatter `type` equals `decision`;
- frontmatter `decision` is present;
- heading contains `Decision`, `Alternatives`, `Tradeoff`, or `Revisit` inside
  a metadata-selected document;
- optional graph decision-trace enrichment identifies a decision entity.

Decision classification rules:

- `stated` decisions require a canonical decision path, frontmatter
  `type: decision`, or explicit decision frontmatter.
- heading-only decision matches are `heading_candidate` items with a
  `candidate_decision` warning. They are useful context but must not be labeled
  as durable decisions in text mirrors.
- graph-enriched decision context keeps the underlying item's original
  `claim_status` unless the graph evidence adds relationship context, in which
  case `matched_signals` includes `graph_decision_trace`.

Open-question candidates:

- path starts with `wiki/issues/` and the document has an active or unresolved
  status;
- frontmatter `type` equals `issue`, `question`, or `follow_up` and the
  document has an active or unresolved status;
- frontmatter `status` is `open`, `unresolved`, `todo`, `blocked`, or
  `revisit`;
- heading contains `Open Questions`, `Question`, `Follow-up`, `TODO`,
  `Blocker`, or `Revisit` inside a metadata-selected document.

Open-question exclusion rules:

- frontmatter `status` values `closed`, `resolved`, `done`, `accepted`,
  `superseded`, `deprecated`, and `cancelled` are excluded from
  `open_question` output.
- issue documents with missing status are emitted only when an explicit
  open-question heading matched inside that metadata-selected document; they
  carry `missing_issue_status`.
- issue documents with missing status and no explicit open-question heading are
  not emitted as open facts.

Current-state candidates:

- frontmatter `type` is `project_status`, `status`, `roadmap`, `plan`, or
  `overview`;
- path contains `status`, `roadmap`, `plan`, or `overview`;
- project documents such as `docs/SPEC.md` or `docs/FEATURES.md` only when they
  are inside the selected Vault scope.
- root-level `README.md` is intentionally excluded in Phase 6B because current
  `QueryScope` roots do not include repository-root documents.

Constraint candidates:

- frontmatter contains `constraint`, `policy`, `boundary`, or `invariant`;
- path contains `policy`, `decision`, `convention`, or `boundary`;
- heading contains `Constraint`, `Policy`, `Boundary`, `Invariant`, or
  `Non-goal`.

Next-priority candidates:

- frontmatter contains `priority`, `next`, `roadmap`, or `phase`;
- heading contains `Next`, `Priorities`, `Roadmap`, `Implementation Order`, or
  `TODO` inside a metadata-selected document.

Stale-area candidates:

- document frontmatter `status` is `stale`, `deprecated`, or `superseded`;
- path or headings indicate deprecated or superseded project areas.

Backend stale, unavailable, or incompatible state belongs to `freshness` and
warnings, not to `stale_area` `MemoryItem` records, unless a Vault document
itself provides evidence for the stale area.

Ambiguous classification:

- The same document may appear in multiple groups when it matches multiple
  rules.
- Each ambiguous item carries `ambiguous_classification` with the matched
  groups.
- Ambiguity is visible; the classifier must not silently pick one group.

Ranking:

1. exact frontmatter type/status matches
2. path-root matches
3. heading matches
4. optional graph-enriched decision trace matches
5. fallback path-name matches

Within the same rank tier, order by `vault_id`, normalized path, then stable
`item_id`.

## 13. Services

Services are MCP-free and read-only. All services expand requested scopes
through `actual_query_scopes(catalog=catalog, scope=requested_scope)` before
reading stores.

Project memory:

```python
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

Decision memory:

```python
from vault_graph.retrieval.graph_retrieval import GraphOutputFormat

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

Issue memory:

```python
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

Service rules:

- services call `IndexService.status(...)` before document listing. If metadata
  health is unavailable or schema-incompatible, the service raises
  `MemoryProjectionError("metadata_unavailable: ...")` instead of treating an
  empty low-level store result as an empty project.
- standalone decision and issue service calls build their own
  `MemoryRequestContext`; project memory builds one context and passes it to
  package-internal decision and issue service methods.
- `limit` must be `1..50`; higher MCP limits are validation errors.
- limits apply per Vault group and per primary group. For
  `ProjectMemoryService`, each group gets at most `limit` items.
- `ProjectMemoryService` composes decision and issue service results instead of
  duplicating decision/open-question classification.
- `DecisionMemoryService` prefers durable decision documents.
- Graph trace enrichment is additive and may only use existing read-only graph
  services through `decision_trace_provider_factory`.
- `decision_trace_provider_factory` is invoked only when `topic is not None` and
  `include_graph=True`; project-memory summaries must not open graph services
  as a side effect.
- The factory returns the concrete `GraphRetrievalService`; no adapter is needed
  because it satisfies `DecisionTraceProvider`.
- Decision enrichment calls the provider with `output_format="json"` explicitly
  and keeps the default graph `depth=2` unless a later slice designs a public
  depth control.
- If graph enrichment is unavailable, decision memory still returns durable
  metadata-backed decisions with a warning.
- Store revisions are built from document `index_revision` values and status
  service revision fields. Missing revisions are represented as `None`, not
  invented strings.
- Stale or unavailable backends create warnings and freshness fields. They do
  not disappear from text mirrors.

## 14. MCP Tools And Resources

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

MCP tool registration rules:

- `McpToolName` appends `summarize_project_memory` and `get_open_questions`.
- `tests/test_mcp_stdio_smoke.py` updates the exact expected tool list.
- tools resolve scope through `scope_from_mcp_input(...)`.
- tools support active-Vault default, explicit `vault_ids`, and `all_vaults`.
- `include_cross_vault` remains graph-only and is not accepted by these memory
  tools.
- `DecisionMemoryService.list_decisions(...)` is not exposed as a new MCP tool
  in Phase 6B. Existing `get_decision_trace` remains the graph-specific
  decision-tracing surface. Decision memory feeds project memory internally and
  remains available for a future explicit tool if needed.

Serialization:

```python
def project_memory_projection_to_payload(
    projection: ProjectMemoryProjection,
) -> dict[str, object]: ...

def open_questions_projection_to_payload(
    projection: OpenQuestionsProjection,
) -> dict[str, object]: ...

def resource_links_for_memory_projection(
    projection: ProjectMemoryProjection | OpenQuestionsProjection,
) -> tuple[McpResourceLink, ...]: ...
```

Resource-link rules:

- every evidence-backed item links to the underlying document or page resource;
- resource serializers use `MemoryItem.document_resource_kinds` to decide which
  existing resource links are valid;
- `open_question` items with `issue` in `document_resource_kinds` link to the
  existing `vault://{vault_id}/issues/{document_id}` resource;
- decision items with `decision` in `document_resource_kinds` link to the
  existing `vault://{vault_id}/decisions/{document_id}` resource;
- memory tools must not create new writable memory resource URIs.

Output envelope follows existing MCP tool bodies:

```json
{
  "tool_name": "summarize_project_memory",
  "payload": {
    "requested_scope": {},
    "actual_scopes": [],
    "vaults": [],
    "warnings": [],
    "generated_at": "..."
  },
  "resource_links": [],
  "warnings": [],
  "text": "{...}"
}
```

Resource upgrade:

```text
vault://{vault_id}/context/current
```

Resource rules:

- the resource returns `ProjectMemoryProjection` for exactly one Vault;
- resource scope is `catalog.scope_for_vault_ids((vault_id,))`;
- all-Vault summaries remain tool-only because the URI carries one Vault ID;
- the resource keeps `application/json`;
- if project memory is unavailable, return an MCP resource error with a safe
  `Run vg index` or `Run vg status` recovery hint.

Prompt updates:

- `generate_codex_brief` and `prepare_implementation_context` should call
  `summarize_project_memory` before broad search when Phase 6B tools exist.
- risk and wiki-update prompts should call `get_open_questions` when unresolved
  follow-up context matters.
- prompts must keep the read-only Vault boundary and must not suggest
  publication through Vault Graph.

## 15. Service Factory Handoff

`McpServiceFactory` adds lazy read-only construction methods:

```python
class McpServiceFactory:
    def open_memory_source_reader(self) -> MemorySourceReader: ...
    def open_decision_memory_service(self) -> DecisionMemoryService: ...
    def open_issue_memory_service(self) -> IssueMemoryService: ...
    def open_project_memory_service(self) -> ProjectMemoryService: ...
```

Rules:

- each method opens stores with `initialize=False` and existing read-only flags;
- graph retrieval is passed as a factory and opened lazily only when
  `DecisionMemoryService.list_decisions(..., topic=..., include_graph=True)`
  requests topic-specific graph enrichment;
- memory services do not become fields on `McpServices` unless repeated
  construction becomes a measured problem;
- no method creates memory-specific storage directories.

## 16. Error And Degradation Policy

Add `MemoryProjectionError` in `src/vault_graph/errors.py`.

MCP error mapping:

- invalid MCP tool limits use the existing `invalid_tool_arguments` code and
  `invalid_parameter` kind from `mcp_tools._limit(...)`.
- `memory_projection_unavailable` -> `execution`
- `metadata_unavailable` -> `execution`
- `memory_evidence_unresolved` -> `execution` only when no evidence-backed
  item can be returned for the requested projection
- `invalid_memory_limit` -> `execution` for direct service calls; MCP tool
  calls should reject invalid limits earlier with `invalid_tool_arguments`

Behavior rules:

- invalid scope or unknown Vault ID: validation error;
- disabled Vault ID: validation error from existing scope handling;
- missing metadata backend: execution error with `Run vg index`;
- metadata backend present but empty: successful empty projection plus
  `no_memory_items_found`;
- stale metadata: successful projection with freshness `stale` and warnings;
- missing vector backend: warning only;
- missing graph backend: warning only unless graph enrichment was explicitly
  requested by a topic-specific decision-memory call;
- no matching memory items: successful empty projection plus
  `no_memory_items_found`;
- text mirrors must not omit warnings that are present in structured payloads.

## 17. Multi-Vault Policy

- default tools use the active Vault.
- explicit `all_vaults` expands to enabled Vault entries before service calls.
- projections contain one Vault group per actual Vault scope.
- stable item IDs include `vault_id` and never merge by title, path, or entity
  name alone.
- warnings carry affected Vault IDs.
- resource URIs are single-Vault only.
- cross-Vault graph relationship grouping remains out of scope for Phase 6B.

## 18. Read-Only And Rebuildability

- Phase 6B writes no Vault files and no derived memory files.
- Projection output is rebuilt from current `MetadataStore`, optional graph
  service output, and status service state.
- Deleting metadata/vector/graph stores removes only derived state; rerunning
  `vg index` recreates the evidence basis.
- External memory systems may later export these projections, but they must not
  become sources for Phase 6B facts.

## 19. Tests

Required tests:

- `MetadataStore.list_documents(...)` returns non-tombstoned documents,
  preserves `DocumentSnapshot` fields, filters by `QueryScope`, orders
  deterministically, and does not initialize missing databases.
- `MemorySourceReader` loads bounded evidence from chunks, preserves chunk
  order, warns on unresolved evidence, and never reads Vault files.
- `MemoryRequestContext` checks metadata status before listing documents, lists
  documents once per actual Vault scope, and uses one generated timestamp.
- heading classification inside metadata-selected documents inspects headings
  beyond the first three chunks and prefers matched heading chunks inside the
  bounded evidence set.
- memory DTOs reject blank IDs, mutable sequences, missing evidence, invalid
  `rank` values, and warnings without affected Vault IDs.
- classification covers path, frontmatter, headings, status values, ambiguous
  matches, and no-match behavior.
- open-question classification excludes resolved/closed/done issues and warns
  when missing status is used only as a heading candidate.
- large scopes use metadata-first candidate narrowing, enforce
  `candidate_read_limit`, and emit `candidate_scan_truncated` warnings.
- project memory groups current state, decisions, open questions, constraints,
  priorities, and stale areas deterministically.
- decision memory prefers durable decision documents and adds graph-derived
  warnings/enrichment only when graph service is injected.
- open questions include issue docs, TODO headings, blockers, follow-ups, and
  revisit triggers.
- multi-Vault documents with identical paths, titles, and statuses do not
  collide.
- MCP tools serialize structured memory projections, resource links, warnings,
  and text mirrors.
- `get_open_questions` returns existing issue resource links for issue-backed
  open questions and does not invent memory-resource URIs.
- memory resource links use `document_resource_kinds` so frontmatter-backed
  decision/issue documents get valid existing resource links while heading-only
  candidates do not get broken decision/issue links.
- MCP tool validation rejects non-integer or out-of-range limits with existing
  `invalid_tool_arguments` errors.
- `context/current` returns a single-Vault project memory projection.
- read-only boundary tests assert no Vault file mutation and no read-only store
  initialization.
- import or boundary tests assert Phase 6B does not introduce writable
  `MemoryStore`, external memory dependencies, raw episode logs, or profile
  memory tables.
- prompt tests assert Phase 6B prompt lines mention only registered tools.

Verification commands:

```bash
uv run --python 3.12 pytest tests/test_memory_models.py tests/test_memory_source_reader.py -q
uv run --python 3.12 pytest tests/test_project_memory_service.py tests/test_decision_memory_service.py tests/test_issue_memory_service.py -q
uv run --python 3.12 pytest tests/test_mcp_memory_tools.py tests/test_mcp_current_context_resource.py tests/test_mcp_resources.py -q
VG_RUN_MCP_STDIO_SMOKE=1 uv run --python 3.12 pytest tests/test_mcp_stdio_smoke.py -q
uv run --python 3.12 ruff check src tests
uv run --python 3.12 mypy src tests
```

## 20. Implementation Handoff

Implement Phase 6B in this order:

1. Add `MemoryProjectionError`, memory DTOs, and focused model tests.
2. Add `MetadataStore.list_documents(...)` to the protocol and local SQLite
   implementation with contract tests.
3. Add `MemorySourceReader`, `MemoryRequestContext`, and evidence/context tests.
4. Add `DecisionMemoryService` and `IssueMemoryService`.
5. Add `ProjectMemoryService` that composes decision and issue projections.
6. Add MCP memory serialization and service-factory open methods.
7. Add `summarize_project_memory`, `get_open_questions`, prompt updates, and
   stdio tool-list tests.
8. Upgrade `vault://{vault_id}/context/current`.
9. Run read-only/import-boundary tests and full verification.

## 21. Risks And Mitigations

- **Risk:** deterministic memory can look less fluent than an LLM summary.
  **Mitigation:** preserve structured groups and evidence first; answer
  synthesis remains out of scope.
- **Risk:** broad document classification creates noisy memory.
  **Mitigation:** keep classifiers conservative, bound results per Vault, rank
  deterministic evidence, and warn on ambiguous items.
- **Risk:** document listing widens `MetadataStore`.
  **Mitigation:** make it read-only, scope-filtered, and contract-tested across
  local and future scale-up backends.
- **Risk:** "memory" naming encourages a generic writable layer.
  **Mitigation:** expose specific read services only and add boundary tests that
  reject writable memory-store or external memory dependencies.
- **Risk:** all-Vault memory output hides source ownership.
  **Mitigation:** group by Vault ID and require Vault IDs in item IDs, warnings,
  evidence refs, store revisions, and resource links.

## 22. Open Decisions

None for Phase 6B. LLM-written project summaries, durable memory history, and
external memory adapters remain out of scope.
