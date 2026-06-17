# Phase 5B MCP Resources And Context Pack Resources Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add read-only MCP resource templates over indexed Vault Graph evidence, graph entities, current-context availability, and generated context packs without giving MCP ownership of Vault reading, indexing, retrieval, graph algorithms, or durable knowledge.

**Architecture:** Keep `vault_graph.mcp` as a thin adapter over Phase 5A services. All resource reads go through one URI parser, `MetadataStore`, a reusable `GraphResourceService`, status/catalog state, or a bounded in-process `ContextPackResourceCache`; every resource returns a canonical JSON envelope with evidence metadata and warnings.

**Tech Stack:** Python 3.12, official MCP Python SDK v1.27.x FastMCP resources, frozen dataclasses, SQLite metadata/graph stores opened read-only, existing context-pack JSON renderer, pytest, ruff, mypy.

---

## Source Documents

Read these before implementation:

- `AGENTS.md`
- `docs/SPEC.md`
- `docs/FEATURES.md`
- `docs/DESIGN.md`
- `docs/CONVENTIONS.md`
- `docs/superpowers/specs/phase-5/README.md`
- `docs/superpowers/specs/phase-5/2026-06-15-phase-5-mcp-server-overview-design.md`
- `docs/superpowers/specs/phase-5/2026-06-15-phase-5a-mcp-server-foundation-stdio-design.md`
- `docs/superpowers/specs/phase-5/2026-06-15-phase-5b-mcp-resources-context-pack-resources-design.md`
- `docs/superpowers/plans/2026-06-15-phase-5a-mcp-server-foundation-stdio.md`

Current repo facts to preserve:

- `src/vault_graph/mcp/mcp_server.py` already owns `McpServerConfig`, `RegisteredMcpServer`, `create_mcp_server(...)`, `run_mcp_server(...)`, and `serve_mcp(...)`.
- `src/vault_graph/mcp/mcp_service_factory.py` already opens read-only catalog, metadata, keyword, vector, retrieval, context-pack builder, and context-pack renderer services.
- `McpServiceFactory.open_read_only()` must not import `rustworkx`, create missing metadata/vector/graph/projection/model state, or write registered Vault roots.
- `McpServiceFactory.open_graph_retrieval_service()` is lazy and may import `RustworkxGraphProjection` only when graph behavior is explicitly requested.
- `mcp 1.27.2` exposes public `FastMCP.resource(...)`, `FastMCP.read_resource(...)`, `FastMCP.list_resources()`, and `FastMCP.list_resource_templates()` APIs.
- FastMCP passes percent-encoded URI template arguments to handlers unchanged. Example: `vault://main/documents/wiki%2Fspec.md` calls the handler with `path="wiki%2Fspec.md"`.
- FastMCP does not match a raw slash value in a single template segment. Example: `vault://main/documents/wiki/spec.md` does not match `vault://{vault_id}/documents/{path}`.
- `MetadataStore` currently has `document_state(...)`, `list_document_states(...)`, `list_chunks(...)`, `resolve_document(...)`, `resolve_chunk(...)`, and `resolve_chunk_evidence(...)`, but not `list_document_chunks(...)`.
- `DocumentSnapshot.kind` is currently the top-level path root from `DocumentNormalizer`.
- Context packs already have canonical JSON rendering through `DefaultContextPackRenderer.render_json(...)`.

## Scope

Implement Phase 5B:

- `vault://` URI parser, normalization, percent-encoding helpers, and validation.
- Canonical JSON resource envelope used by every resource.
- FastMCP resource-template registration for:
  - `vault://{vault_id}/documents/{path}`
  - `vault://{vault_id}/pages/{path}`
  - `vault://{vault_id}/sources/{id}`
  - `vault://{vault_id}/concepts/{name}`
  - `vault://{vault_id}/decisions/{id}`
  - `vault://{vault_id}/issues/{id}`
  - `vault://{vault_id}/timeline/recent`
  - `vault://{vault_id}/context/current`
  - `vault://{vault_id}/graph/entities/{id}`
  - `vault://context/packs/{pack_id}`
- Metadata-backed document/page/source/decision/issue resources rendered from indexed chunks only.
- `MetadataStore.list_document_chunks(vault_id, document_id)` and SQLite implementation.
- Graph entity and concept resources through a new reusable `GraphResourceService`.
- Current-context availability and timeline-unavailable resources.
- Bounded in-process context-pack resource cache shared through `RegisteredMcpServer` for Phase 5C.
- Unit, integration, MCP SDK, import-boundary, read-only, and multi-Vault tests.

## Non-Goals

Do not implement:

- resource subscriptions
- durable context-pack persistence
- full resource listing of all indexed Vault documents
- resource reads that build context packs as a side effect
- indexing from MCP
- direct Vault file reads from MCP resources
- editing, renaming, rewriting, deleting, or publishing Vault files
- binary resources
- remote HTTP resources
- LLM answer synthesis
- Phase 6 memory, issue, timeline, or project-memory projections

## Directory And File Structure

Create:

- `src/vault_graph/mcp/mcp_uri.py`: parse, normalize, encode, decode, and validate all `vault://` resource URIs.
- `src/vault_graph/mcp/mcp_resources.py`: resource DTOs, registry dispatch, current/timeline readers, and FastMCP resource-template registration.
- `src/vault_graph/mcp/metadata_resource_reader.py`: render document-like resources from indexed metadata and chunks only.
- `src/vault_graph/mcp/graph_resource_reader.py`: convert app-layer graph resource results into MCP JSON envelopes.
- `src/vault_graph/mcp/context_pack_resource_cache.py`: bounded in-process LRU cache for rendered context-pack JSON.
- `src/vault_graph/app/graph_resource_service.py`: reusable application service for graph entity/concept resource reads.
- `tests/test_mcp_uri.py`
- `tests/test_mcp_resources.py`
- `tests/test_metadata_resource_reader.py`
- `tests/test_graph_resource_reader.py`
- `tests/test_context_pack_resource_cache.py`
- `tests/test_mcp_resource_read_only_boundary.py`

Modify:

- `src/vault_graph/mcp/__init__.py`: add lazy exports for Phase 5B public DTOs/helpers without eager SDK or graph imports.
- `src/vault_graph/mcp/mcp_server.py`: expand `RegisteredMcpServer`, construct cache, and register resources during server creation.
- `src/vault_graph/mcp/mcp_service_factory.py`: add `open_graph_resource_service(...)`.
- `src/vault_graph/mcp/mcp_errors.py`: add helper constructors for expected resource errors if needed; keep existing sanitization and `McpErrorPayload`.
- `src/vault_graph/storage/interfaces/metadata_store.py`: add `list_document_chunks(...)`.
- `src/vault_graph/storage/local/sqlite_metadata_store.py`: implement `list_document_chunks(...)`.
- `tests/test_mcp_stdio_smoke.py`: assert official MCP client can list Phase 5B resource templates.

Do not modify:

- registered Vault roots or Vault files
- retrieval ranking behavior
- graph projection algorithms
- context-pack JSON schema
- `docs/DECISIONS.md`
- `docs/PATCH_LOG.md` unless implementation review finds a concrete mismatch that changes this plan or the spec

## Component And Interface Spec

### `src/vault_graph/mcp/mcp_uri.py`

Own all `vault://` parsing. Resource readers must receive `McpResourceUri`; they must not reparse URI strings or decode handler parameters.

```python
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from vault_graph.ingestion.vault_catalog import VaultCatalog

McpResourceKind = Literal[
    "document",
    "page",
    "source",
    "concept",
    "decision",
    "issue",
    "timeline_recent",
    "context_current",
    "graph_entity",
    "context_pack",
]


@dataclass(frozen=True)
class McpResourceUri:
    raw_uri: str
    normalized_uri: str
    kind: McpResourceKind
    vault_id: str | None
    value: str | None


def encode_resource_segment(value: str) -> str: ...
def decode_resource_segment(value: str, *, allow_slash: bool) -> str: ...
def parse_mcp_resource_uri(uri: str, *, catalog: VaultCatalog) -> McpResourceUri: ...
```

Parser rules:

- Use `urllib.parse.urlsplit`, `quote`, and `unquote`.
- Reject any query string or fragment.
- Treat `urlsplit(uri).netloc` as `vault_id`, except `netloc == "context"` for `vault://context/packs/{pack_id}`.
- For `vault://{vault_id}/documents/{path}`, require path parts exactly `["documents", "{path}"]`.
- For `vault://{vault_id}/pages/{path}`, require path parts exactly `["pages", "{path}"]`.
- For `vault://{vault_id}/sources/{id}`, `decisions/{id}`, `issues/{id}`, and `concepts/{name}`, require exactly two path parts.
- For `vault://{vault_id}/graph/entities/{id}`, require exactly three path parts.
- For `vault://{vault_id}/timeline/recent` and `context/current`, require no value.
- For `vault://context/packs/{pack_id}`, require exactly `["packs", "{pack_id}"]`.
- Reject raw slash values by rejecting path part counts other than the exact template count.
- Reject empty values after decode and before normalization.
- Reject decoded `.` and `..` path segments for every value.
- Reject absolute decoded paths for every value.
- Allow decoded slash only for `document` and `page`.
- Reject encoded slash for all opaque values: source ID, concept name, decision ID, issue ID, graph entity ID, pack ID.
- Require decoded document/page path to end with `.md`.
- Require decoded page path to start with `wiki/`.
- For document/page resources, require the decoded path to be under the selected Vault entry's enabled content scopes using same-or-child matching.
- Resolve and reject unknown or disabled Vault IDs before returning.
- Do not call any store, graph service, context builder, loader, filesystem read, or filesystem write.

Error mapping:

- Invalid scheme, path shape, empty value, traversal, raw slash, query, fragment, non-Markdown path, page outside `wiki/`, and scope mismatch: `McpProtocolError(kind="invalid_parameter", payload.code="invalid_resource_uri")`.
- Unknown Vault ID: `McpProtocolError(kind="invalid_parameter", payload.code="unknown_vault_id")`.
- Disabled Vault ID: `McpProtocolError(kind="invalid_parameter", payload.code="vault_disabled")`.

Implementation helper detail:

```python
def _same_or_child(path: str, parent: str) -> bool:
    return path == parent or path.startswith(f"{parent}/")
```

Normalize resource URIs by re-encoding the decoded value with `quote(value, safe="")`. For document/page resources this means decoded slash becomes `%2F` in the normalized URI.

### `src/vault_graph/mcp/mcp_resources.py`

Own resource DTOs, registry dispatch, current/timeline resource rendering, and FastMCP registration.

```python
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal, Protocol

from vault_graph.mcp.mcp_errors import McpErrorPayload

McpResourceContentMime = Literal["text/markdown", "application/json"]


@dataclass(frozen=True)
class McpResourceRequest:
    uri: str


@dataclass(frozen=True)
class McpResourceBody:
    uri: str
    content_mime_type: McpResourceContentMime
    text: str
    metadata: dict[str, object]
    warnings: tuple[McpErrorPayload, ...] = ()

    def to_json_dict(self) -> dict[str, object]: ...


class McpResourceServer(Protocol):
    def resource(
        self,
        uri: str,
        *,
        name: str | None = None,
        title: str | None = None,
        description: str | None = None,
        mime_type: str | None = None,
        meta: dict[str, object] | None = None,
    ) -> Callable[[Callable[..., object]], Callable[..., object]]: ...


class GraphResourceReaderFactory(Protocol):
    def get(self) -> GraphResourceReader: ...


class McpResourceRegistry:
    def __init__(
        self,
        *,
        catalog: VaultCatalog,
        metadata_reader: MetadataResourceReader,
        graph_reader_factory: GraphResourceReaderFactory,
        context_pack_cache: ContextPackResourceCache,
        current_context_reader: CurrentContextResourceReader,
    ) -> None: ...

    def read(self, request: McpResourceRequest) -> McpResourceBody: ...
    def read_json(self, request: McpResourceRequest) -> str: ...


class CurrentContextResourceReader:
    def __init__(
        self,
        *,
        catalog: VaultCatalog,
        service_factory: McpServiceFactory,
        context_pack_cache: ContextPackResourceCache,
    ) -> None: ...

    def read_current_context(self, uri: McpResourceUri) -> McpResourceBody: ...
    def read_recent_timeline(self, uri: McpResourceUri) -> McpResourceBody: ...


def register_mcp_resources(
    server: McpResourceServer,
    *,
    services: McpServices,
    service_factory: McpServiceFactory,
    context_pack_cache: ContextPackResourceCache,
) -> McpResourceRegistry: ...
```

`McpResourceBody.to_json_dict()` must return JSON-safe values only:

- `uri`
- `content_mime_type`
- `text`
- `metadata`
- `warnings`, as a list of dictionaries with `code`, `message`, `severity`, `affected_vault_ids`, and `recovery_hint`

`McpResourceRegistry.read(...)` dispatch table:

- `document` -> `metadata_reader.read_document(uri)`
- `page` -> `metadata_reader.read_page(uri)`
- `source` -> `metadata_reader.read_source(uri)`
- `decision` -> `metadata_reader.read_decision(uri)`
- `issue` -> `metadata_reader.read_issue(uri)`
- `graph_entity` -> `graph_reader_factory.get().read_entity(uri)`
- `concept` -> `graph_reader_factory.get().read_concept(uri)`
- `context_current` -> `current_context_reader.read_current_context(uri)`
- `timeline_recent` -> `current_context_reader.read_recent_timeline(uri)`
- `context_pack` -> cache lookup and body rendering

`McpResourceRegistry.read_json(...)` must serialize with:

```python
json.dumps(body.to_json_dict(), sort_keys=True, ensure_ascii=False, indent=2) + "\n"
```

Expected resource failures should raise `McpProtocolError`. Unexpected domain exceptions should go through `map_exception_to_mcp_error(...)` with the request's affected Vault IDs when available. Do not swallow errors by returning Markdown-only warnings.

FastMCP registration rules:

- Register templates only with `server.resource(...)`.
- Use `mime_type="application/json"` for every resource template.
- Do not inspect or mutate private FastMCP fields.
- Do not scan metadata to list every document during startup.
- Handler parameters are encoded. Rebuild the URI from the encoded handler arguments and call `registry.read_json(...)`.

Template handler shape:

```python
@server.resource("vault://{vault_id}/documents/{path}", mime_type="application/json")
def read_document_resource(vault_id: str, path: str) -> str:
    return registry.read_json(McpResourceRequest(uri=f"vault://{vault_id}/documents/{path}"))
```

Use the same pattern for all templates. For `timeline/recent` and `context/current`, handlers take only `vault_id`. For `context/packs/{pack_id}`, handler takes only `pack_id` and builds `vault://context/packs/{pack_id}`.

`CurrentContextResourceReader.read_current_context(...)` returns JSON text with:

- `vault_id`
- `display_name`
- `active`
- `content_scopes`
- `state_namespace`
- `metadata_health`
- `search_health`
- `graph_health`
- `context_pack_cache`
- `warnings`

This method may call `service_factory.open_status_service()` inside the read, not during server startup. If status/graph health is unavailable, return partial current context with warning payloads instead of synthesizing a memory summary.

`CurrentContextResourceReader.read_recent_timeline(...)` always raises `McpProtocolError(kind="execution", payload.code="resource_not_available")` in Phase 5B with recovery hint `"Timeline projection resources are planned for Phase 6."`

### `src/vault_graph/mcp/context_pack_resource_cache.py`

Own only in-process resource cache behavior.

```python
from __future__ import annotations

from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime

from vault_graph.context.context_pack import ContextPack


@dataclass(frozen=True)
class CachedContextPack:
    pack_id: str
    pack_json: str
    generated_at: str
    requested_scope_key: str
    actual_scope_keys: tuple[str, ...]
    cached_at: str


class ContextPackResourceCache:
    def __init__(
        self,
        *,
        max_entries: int = 32,
        clock: Callable[[], datetime] | None = None,
    ) -> None: ...

    @property
    def max_entries(self) -> int: ...

    def put(self, pack: ContextPack, *, rendered_json: str) -> CachedContextPack: ...
    def get(self, pack_id: str) -> CachedContextPack | None: ...
    def __len__(self) -> int: ...
```

Cache rules:

- Reject `max_entries <= 0` with `ContextPackError`.
- Reject empty `pack.pack_id`.
- Store `rendered_json` exactly as provided by the existing renderer.
- Set `requested_scope_key` as:
  - `",".join(pack.scope.requested.vault_ids) + ":" + ",".join(pack.scope.requested.content_scopes) + f":cross={pack.scope.requested.include_cross_vault}"`
- Set `actual_scope_keys` from `scope.scope_key` for each `pack.scope.actual_scopes`.
- Set `cached_at` from `clock()` in UTC ISO format.
- Use `OrderedDict[str, CachedContextPack]` and move entries to the end on `get`.
- Evict least-recently-used entries while `len(cache) > max_entries`.
- Do not write files.
- Do not mutate the `ContextPack`.

When `McpResourceRegistry` reads a missing pack ID, raise `resource_not_found` with recovery hint `"Call build_context_pack again to regenerate this in-process resource."`

### `src/vault_graph/storage/interfaces/metadata_store.py`

Add the focused chunk read method to the `MetadataStore` protocol:

```python
class MetadataStore(Protocol):
    ...
    def list_document_chunks(
        self,
        *,
        vault_id: str,
        document_id: str,
    ) -> tuple[ChunkSnapshot, ...]: ...
```

Contract:

- Return current non-tombstoned chunks only.
- Filter by both `vault_id` and `document_id`.
- Return `()` if the document is unknown, tombstoned, or has no current chunks.
- Return chunks in indexed document order. The current `metadata-v1` schema has
  no explicit chunk ordinal, so Phase 5B must use SQLite `c.rowid` for this
  document-specific query because `apply_metadata_revision(...)` deletes then
  reinserts a document's chunks in normalizer order.
- Perform no writes and no implicit schema initialization.

### `src/vault_graph/storage/local/sqlite_metadata_store.py`

Implement:

```python
def list_document_chunks(
    self,
    *,
    vault_id: str,
    document_id: str,
) -> tuple[ChunkSnapshot, ...]:
    if not self._database_path.exists():
        return ()
    with self._connect() as connection:
        rows = connection.execute(
            """
            SELECT c.vault_id, c.chunk_id, c.document_id, c.path, c.section, c.anchor,
                   c.text, c.token_count, c.content_hash, c.chunker_version, c.index_revision
            FROM chunks c
            INNER JOIN documents d
              ON d.vault_id = c.vault_id
             AND d.document_id = c.document_id
             AND d.path = c.path
            WHERE c.vault_id = ?
              AND c.document_id = ?
              AND d.is_tombstoned = 0
            ORDER BY c.rowid
            """,
            (vault_id, document_id),
        ).fetchall()
    return tuple(_chunk_snapshot_from_row(row) for row in rows)
```

Do not use `ORDER BY chunk_id` for this method. `chunk_id` is a stable hash and
does not preserve `heading-section-v1` document order.

### `src/vault_graph/mcp/metadata_resource_reader.py`

Render document-like resources from indexed metadata only.

```python
from __future__ import annotations

from dataclasses import dataclass

from vault_graph.ingestion.document_normalizer import ChunkSnapshot, DocumentSnapshot
from vault_graph.ingestion.vault_catalog import VaultCatalog
from vault_graph.mcp.mcp_resources import McpResourceBody
from vault_graph.mcp.mcp_uri import McpResourceUri
from vault_graph.storage.interfaces.metadata_store import EvidenceReference, MetadataStore


@dataclass(frozen=True)
class MetadataResourceRead:
    document: DocumentSnapshot
    chunks: tuple[ChunkSnapshot, ...]
    evidence: tuple[EvidenceReference, ...]
    warnings: tuple[McpErrorPayload, ...]


class MetadataResourceReader:
    def __init__(self, *, catalog: VaultCatalog, metadata_store: MetadataStore) -> None: ...

    def read_document(self, uri: McpResourceUri) -> McpResourceBody: ...
    def read_page(self, uri: McpResourceUri) -> McpResourceBody: ...
    def read_source(self, uri: McpResourceUri) -> McpResourceBody: ...
    def read_decision(self, uri: McpResourceUri) -> McpResourceBody: ...
    def read_issue(self, uri: McpResourceUri) -> McpResourceBody: ...
```

Resolution rules:

- `read_document(...)` and `read_page(...)` use `uri.value` as decoded logical path.
- `read_source(...)`, `read_decision(...)`, and `read_issue(...)` use `uri.value` as `document_id`.
- Path resources call `metadata_store.document_state(vault_id, path)` first.
- If `DocumentState.document_id is None` or `is_tombstoned is True`, raise `resource_not_found`.
- Resolve the document with `metadata_store.resolve_document(document_id)`.
- Reject missing document or `document.vault_id != uri.vault_id` as `resource_not_found`.
- Fetch chunks with `metadata_store.list_document_chunks(vault_id=uri.vault_id, document_id=document.document_id)`.
- Build evidence by calling `resolve_chunk_evidence(...)` for each chunk. Missing evidence refs produce `missing_evidence` warnings.
- Do not call `VaultLoader`, `Path.read_text`, or any direct Vault filesystem read.

Classification rules:

- `read_page(...)`: require `document.path.startswith("wiki/")`.
- `read_source(...)`: require path under `raw/`, `docs/`, or `scratch/reports/`, or `document.frontmatter.get("type") == "source"`.
- `read_decision(...)`: require path under `wiki/decisions/` or `document.frontmatter.get("type") == "decision"`.
- `read_issue(...)`: require path under `wiki/issues/` or `document.frontmatter.get("type") == "issue"`.
- Classification mismatch raises `resource_not_found`, not a misleading partial resource.

Rendering rules:

- Preserve each chunk's `text`.
- Join chunks with `"\n\n"` unless the adjacent text already has a blank line boundary.
- Do not add facts, summaries, hidden instructions, or prompt text.
- `content_mime_type="text/markdown"` for document/page/source/decision/issue resources.
- `metadata` must include:
  - `vault_id`
  - `document_id`
  - `path`
  - `resource_kind`
  - `document_kind`
  - `frontmatter_hash`
  - `content_hash`
  - `raw_sha256`
  - `parser_version`
  - `chunker_version`
  - `metadata_index_revision`
  - `vault_revision`
  - `chunk_count`
  - `evidence_refs`
- If a document exists but has no chunks, return an empty Markdown `text` with `missing_evidence` warning.
- If `metadata_store.health()` is unavailable or schema incompatible, raise `metadata_unavailable` unless a partial indexed document can be returned with a warning.

### `src/vault_graph/app/graph_resource_service.py`

Add a reusable app-layer service for graph resource reads. MCP readers should not contain graph readiness or graph-store query policy.

```python
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from vault_graph.app.graph_retrieval_service import GraphReadinessChecker
from vault_graph.graph.graph_contracts import EntityRecord, RelationshipRecord
from vault_graph.retrieval.graph_retrieval import GraphRetrievalRevision
from vault_graph.storage.interfaces.graph_store import GraphStore
from vault_graph.storage.interfaces.metadata_store import EvidenceReference, MetadataStore

GraphResourceWarningSeverity = Literal["info", "warning", "error"]


@dataclass(frozen=True)
class GraphResourceWarning:
    code: str
    message: str
    severity: GraphResourceWarningSeverity
    affected_vault_ids: tuple[str, ...]
    recovery_hint: str | None = None


@dataclass(frozen=True)
class GraphEntityResource:
    entity: EntityRecord
    evidence: tuple[EvidenceReference, ...]
    related_relationships: tuple[RelationshipRecord, ...]
    warnings: tuple[GraphResourceWarning, ...]
    store_revisions: tuple[GraphRetrievalRevision, ...]


class GraphResourceService:
    def __init__(
        self,
        *,
        catalog: VaultCatalog,
        metadata_store: MetadataStore,
        graph_store: GraphStore,
        graph_readiness: GraphReadinessChecker,
    ) -> None: ...

    def get_entity(
        self,
        *,
        vault_id: str,
        entity_id: str,
    ) -> GraphEntityResource: ...

    def find_concept(
        self,
        *,
        vault_id: str,
        name: str,
    ) -> GraphEntityResource: ...
```

Service rules:

- Build requested scope as `catalog.scope_for_vault_ids((vault_id,))`.
- Reject disabled Vault entries with `CatalogError("disabled vault_id: ...")`.
- Compute per-Vault actual scopes with `actual_query_scopes(...)`.
- Call `graph_readiness.check(...)`.
- If readiness freshness is `incompatible` or `unavailable`, raise `GraphStoreError(f"graph_{readiness.freshness}: {readiness.recovery_hint}")`.
- Treat freshness `missing`, `empty`, or `stale` as warnings. If there is no fresh scope, raise `GraphStoreError("graph_unavailable: ...")` for entity/concept resources because Phase 5B must not silently degrade to metadata text.
- `get_entity(...)` calls `graph_store.get_entity(vault_id=vault_id, entity_id=entity_id)` and requires active status.
- `find_concept(...)` calls `graph_store.find_entities(GraphEntityQuery(text=name, actual_scopes=fresh_scopes, limit=20))`.
- For concept lookup, exact matches are `entity.normalized_name == normalized_name(name)` or `name in entity.aliases` after applying the same normalization policy used by graph indexing. If no shared normalizer exists, add a local private `_normalize_concept_name(value: str) -> str` using lowercase and whitespace collapse only.
- No exact concept match raises `resource_not_found`.
- More than one exact active concept match raises `ambiguous_resource`.
- Related relationships come from `graph_store.relationships_for_entities(...)` with:
  - seed identity for the entity
  - `direction="both"`
  - `statuses=("stated", "inferred", "contested", "deprecated")`
  - `include_cross_vault=False`
  - `limit=200`
- Evidence is resolved from entity and relationship `GraphEvidenceRef` values through `metadata_store.resolve_chunk_evidence(...)`.
- Missing graph evidence produces `missing_evidence` warnings and does not fabricate evidence text.
- Store revisions include graph readiness rows and metadata revisions from resolved evidence.

Keep this service free of MCP imports. It may use `GraphResourceWarning`, but not `McpErrorPayload`.

### `src/vault_graph/mcp/graph_resource_reader.py`

Convert `GraphResourceService` output into the canonical MCP envelope.

```python
from __future__ import annotations

from vault_graph.app.graph_resource_service import GraphEntityResource, GraphResourceService
from vault_graph.mcp.mcp_resources import McpResourceBody
from vault_graph.mcp.mcp_uri import McpResourceUri


class GraphResourceReader:
    def __init__(self, *, graph_resource_service: GraphResourceService) -> None: ...

    def read_entity(self, uri: McpResourceUri) -> McpResourceBody: ...
    def read_concept(self, uri: McpResourceUri) -> McpResourceBody: ...
```

Output rules:

- `content_mime_type="application/json"`.
- `text` is stable JSON string with `sort_keys=True`, `ensure_ascii=False`, `indent=2`, and a final newline.
- JSON text includes:
  - `entity`
  - `evidence`
  - `relationships_by_status`
  - `store_revisions`
  - `warnings`
- `metadata` includes:
  - `vault_id`
  - `entity_id`
  - `resource_kind`
  - `graph_extraction_spec_version`
  - `graph_extraction_spec_digest`
  - `graph_index_revision`
  - `relationship_count`
  - `evidence_count`
- Convert `GraphResourceWarning` to `McpErrorPayload`.
- Preserve relationship `source_vault_id`, `target_vault_id`, `evidence_vault_id`, and `owner_vault_id` in JSON.

### `src/vault_graph/mcp/mcp_service_factory.py`

Add lazy graph resource service construction:

```python
def open_graph_resource_service(self) -> GraphResourceService:
    from vault_graph.app.graph_readiness_service import ReadOnlyGraphReadiness
    from vault_graph.app.graph_resource_service import GraphResourceService
    from vault_graph.graph.graph_contracts import current_graph_extraction_spec
    from vault_graph.storage.local.sqlite_graph_store import SQLiteGraphStore
    from vault_graph.storage.local.sqlite_metadata_store import SQLiteMetadataStore

    catalog_service, catalog = self._catalog()
    metadata_store = SQLiteMetadataStore(catalog_service.metadata_path, initialize=False)
    graph_store = SQLiteGraphStore.open_read_only(catalog_service.graph_path)
    readiness = ReadOnlyGraphReadiness(
        metadata_store=metadata_store,
        graph_store=graph_store,
        expected_spec=current_graph_extraction_spec(),
    )
    return GraphResourceService(
        catalog=catalog,
        metadata_store=metadata_store,
        graph_store=graph_store,
        graph_readiness=readiness,
    )
```

Do not import `RustworkxGraphProjection` in this method. Graph resource reads do not need projection building.

### `src/vault_graph/mcp/mcp_server.py`

Expand the server wrapper:

```python
@dataclass(frozen=True)
class RegisteredMcpServer:
    server: McpServer
    services: McpServices
    service_factory: McpServiceFactory
    server_version: str
    context_pack_cache: ContextPackResourceCache
    resource_registry: McpResourceRegistry
```

Update `create_mcp_server(...)`:

```python
def create_mcp_server(config: McpServerConfig) -> RegisteredMcpServer:
    from mcp.server.fastmcp import FastMCP

    from vault_graph.mcp.context_pack_resource_cache import ContextPackResourceCache
    from vault_graph.mcp.mcp_resources import register_mcp_resources

    factory = McpServiceFactory(state_path=config.state_path)
    services = factory.open_read_only()
    server = FastMCP(...)
    context_pack_cache = ContextPackResourceCache(max_entries=32)
    resource_registry = register_mcp_resources(
        server,
        services=services,
        service_factory=factory,
        context_pack_cache=context_pack_cache,
    )
    return RegisteredMcpServer(
        server=server,
        services=services,
        service_factory=factory,
        server_version=config.server_version,
        context_pack_cache=context_pack_cache,
        resource_registry=resource_registry,
    )
```

Rules:

- Keep `FastMCP` import lazy.
- Keep Phase 5A stdio behavior unchanged.
- Startup must not open graph resource service, status service, or context-pack builder work beyond existing read-only service construction.
- Startup must not list documents or scan metadata.

### `src/vault_graph/mcp/__init__.py`

Add lazy exports:

- `McpResourceUri`
- `parse_mcp_resource_uri`
- `encode_resource_segment`
- `decode_resource_segment`
- `McpResourceRequest`
- `McpResourceBody`
- `McpResourceRegistry`
- `ContextPackResourceCache`
- `CachedContextPack`

Keep exports lazy through `__getattr__`. Importing `vault_graph.mcp` must not import `mcp.server.fastmcp`, `chromadb`, `fastembed`, `huggingface_hub`, `rustworkx`, or graph projection modules.

## State Management And Data Flow

### Server Startup

```text
vg serve --mcp --state PATH
  -> create_mcp_server(config)
  -> McpServiceFactory.open_read_only()
  -> ContextPackResourceCache(max_entries=32)
  -> register_mcp_resources(...)
  -> run stdio transport
```

State changes allowed: none.

### Document Resource Read

```text
read vault://main/documents/wiki%2Fspec.md
  -> FastMCP handler receives vault_id="main", path="wiki%2Fspec.md"
  -> handler rebuilds vault://main/documents/wiki%2Fspec.md
  -> McpResourceRegistry.read(...)
  -> parse_mcp_resource_uri(...)
  -> MetadataResourceReader.read_document(...)
  -> MetadataStore.document_state("main", "wiki/spec.md")
  -> MetadataStore.resolve_document(document_id)
  -> MetadataStore.list_document_chunks(vault_id="main", document_id=document_id)
  -> MetadataStore.resolve_chunk_evidence(...) for each chunk
  -> JSON envelope with Markdown text, metadata, and warnings
```

State changes allowed: none.

### Graph Entity Resource Read

```text
read vault://main/graph/entities/{entity_id}
  -> parse_mcp_resource_uri(...)
  -> lazy GraphResourceReaderFactory.get()
  -> McpServiceFactory.open_graph_resource_service()
  -> GraphResourceService.get_entity(...)
  -> graph readiness check for selected Vault
  -> graph store entity and relationship reads
  -> metadata evidence resolution
  -> JSON envelope with graph JSON text and warnings
```

State changes allowed: none.

### Context Pack Resource Read

```text
read vault://context/packs/{pack_id}
  -> parse_mcp_resource_uri(...)
  -> ContextPackResourceCache.get(pack_id)
  -> JSON envelope with cached pack_json
  -> if missing, resource_not_found with build_context_pack recovery hint
```

State changes allowed: LRU order inside process memory only. No files.

## Implementation Tasks

### Task 1: URI Parser And Resource Error Helpers

**Files:**

- Create: `src/vault_graph/mcp/mcp_uri.py`
- Modify: `src/vault_graph/mcp/mcp_errors.py`
- Test: `tests/test_mcp_uri.py`

- [ ] **Step 1: Write failing URI parser tests**

Cover:

- encoded document path normalizes to `vault://main/documents/wiki%2Fspec.md` and value `wiki/spec.md`.
- encoded page path under `wiki/` is accepted.
- raw slash document path `vault://main/documents/wiki/spec.md` is rejected before store lookup.
- query and fragment are rejected.
- unknown scheme is rejected.
- absolute paths and traversal are rejected, including `%2e%2e`.
- encoded slash is rejected for opaque IDs.
- non-Markdown document/page paths are rejected.
- page path outside `wiki/` is rejected.
- unknown Vault ID maps to `unknown_vault_id`.
- disabled Vault ID maps to `vault_disabled`.
- `vault://context/packs/pack-1` parses with `vault_id is None`.

Run:

```bash
uv run --python 3.12 pytest tests/test_mcp_uri.py -q
```

Expected: fail because `vault_graph.mcp.mcp_uri` does not exist.

- [ ] **Step 2: Implement `mcp_uri.py` minimally**

Implement the dataclass, helpers, parser, and private validation functions. Use only catalog data and pure URI parsing.

- [ ] **Step 3: Add resource error helper functions only if tests need them**

If repeated error construction is noisy, add private helpers in `mcp_errors.py`:

```python
def resource_error(
    *,
    kind: McpProtocolErrorKind,
    code: str,
    message: str,
    affected_vault_ids: tuple[str, ...] = (),
    recovery_hint: str | None = None,
) -> McpProtocolError: ...
```

Keep the existing public `map_exception_to_mcp_error(...)` behavior unchanged.

- [ ] **Step 4: Run URI parser tests**

Run:

```bash
uv run --python 3.12 pytest tests/test_mcp_uri.py -q
```

Expected: pass.

- [ ] **Step 5: Commit**

```bash
git add src/vault_graph/mcp/mcp_uri.py src/vault_graph/mcp/mcp_errors.py tests/test_mcp_uri.py
git commit -m "feat(mcp): add resource uri parser"
```

### Task 2: Resource Envelope, Cache, Registry Skeleton, And FastMCP Templates

**Files:**

- Create: `src/vault_graph/mcp/mcp_resources.py`
- Create: `src/vault_graph/mcp/context_pack_resource_cache.py`
- Modify: `src/vault_graph/mcp/mcp_server.py`
- Modify: `src/vault_graph/mcp/__init__.py`
- Test: `tests/test_context_pack_resource_cache.py`
- Test: `tests/test_mcp_resources.py`
- Test: `tests/test_mcp_server.py`

- [ ] **Step 1: Write failing cache tests**

Cover:

- `put` returns `CachedContextPack` using existing `ContextPack.pack_id`.
- `get` returns exact rendered JSON.
- `get` moves an entry to most-recently-used.
- inserting over `max_entries` evicts the least-recently-used pack.
- `max_entries <= 0` raises `ContextPackError`.
- cache length is in-memory only and no files are created under a temporary state path.

Run:

```bash
uv run --python 3.12 pytest tests/test_context_pack_resource_cache.py -q
```

Expected: fail because cache module does not exist.

- [ ] **Step 2: Implement cache**

Use `OrderedDict` and the contract above. Reuse fixture helpers from existing context-pack tests where possible.

- [ ] **Step 3: Write failing resource registry/template tests**

Cover:

- `create_mcp_server(...)` returns `RegisteredMcpServer` with `context_pack_cache` and `resource_registry`.
- `registered.server.list_resource_templates()` includes exactly the 10 Phase 5B templates.
- each template has `mime_type == "application/json"`.
- `registered.server.list_resources()` is empty for a normal initialized catalog.
- direct `registered.resource_registry.read(...)` dispatches context pack cache reads.
- missing context pack raises `resource_not_found`.
- no private FastMCP fields are accessed; enforce by testing behavior through public `list_resource_templates()` and `read_resource()`.

Run:

```bash
uv run --python 3.12 pytest tests/test_mcp_resources.py tests/test_mcp_server.py -q
```

Expected: fail because registry and server wrapper are not expanded.

- [ ] **Step 4: Implement `McpResourceBody`, `McpResourceRegistry`, `CurrentContextResourceReader`, and registration skeleton**

In this task, metadata and graph readers can be placeholder injected fakes in tests. Do not implement real document/graph reads yet.

Requirements:

- `McpResourceBody.to_json_dict()` returns JSON-safe values.
- `register_mcp_resources(...)` creates readers and registers every FastMCP template.
- Current-context reader may return catalog/cache fields with backend warnings; do not scan Vault files.
- Timeline reader raises `resource_not_available`.
- Context pack cache reads return:
  - `content_mime_type="application/json"`
  - `text=CachedContextPack.pack_json`
  - metadata with `pack_id`, `generated_at`, `requested_scope_key`, `actual_scope_keys`, and `cached_at`

- [ ] **Step 5: Update `mcp_server.py`**

Expand `RegisteredMcpServer` and wire the cache/registry during `create_mcp_server(...)`.

- [ ] **Step 6: Update lazy exports**

Add Phase 5B exports in `src/vault_graph/mcp/__init__.py` without eager imports.

- [ ] **Step 7: Run focused tests**

Run:

```bash
uv run --python 3.12 pytest tests/test_context_pack_resource_cache.py tests/test_mcp_resources.py tests/test_mcp_server.py -q
```

Expected: pass.

- [ ] **Step 8: Run import-boundary tests**

Run:

```bash
uv run --python 3.12 pytest tests/test_mcp_import_boundaries.py tests/test_mcp_service_factory.py -q
```

Expected: pass, proving new exports and registration do not import runtime clients or graph projection eagerly.

- [ ] **Step 9: Commit**

```bash
git add src/vault_graph/mcp/mcp_resources.py src/vault_graph/mcp/context_pack_resource_cache.py src/vault_graph/mcp/mcp_server.py src/vault_graph/mcp/__init__.py tests/test_context_pack_resource_cache.py tests/test_mcp_resources.py tests/test_mcp_server.py
git commit -m "feat(mcp): register resource templates"
```

### Task 3: Metadata Store Document Chunk Read

**Files:**

- Modify: `src/vault_graph/storage/interfaces/metadata_store.py`
- Modify: `src/vault_graph/storage/local/sqlite_metadata_store.py`
- Test: `tests/test_sqlite_metadata_store.py`

- [ ] **Step 1: Write failing metadata-store tests**

Cover:

- `list_document_chunks(vault_id, document_id)` returns only chunks for that document.
- same `document_id` in a different Vault cannot leak because `vault_id` is filtered.
- tombstoned document returns `()`.
- missing database returns `()` and does not create a database.
- returned chunks preserve normalizer insertion order even when `chunk_id`
  lexical order differs from document order.

Run:

```bash
uv run --python 3.12 pytest tests/test_sqlite_metadata_store.py -q
```

Expected: fail until method exists.

- [ ] **Step 2: Add protocol method**

Add `list_document_chunks(...)` to `MetadataStore`.

- [ ] **Step 3: Implement SQLite method**

Use a single SELECT with an inner join to `documents` and `d.is_tombstoned = 0`. Avoid migrations.

- [ ] **Step 4: Run metadata store tests**

Run:

```bash
uv run --python 3.12 pytest tests/test_sqlite_metadata_store.py -q
```

Expected: pass.

- [ ] **Step 5: Commit**

```bash
git add src/vault_graph/storage/interfaces/metadata_store.py src/vault_graph/storage/local/sqlite_metadata_store.py tests/test_sqlite_metadata_store.py
git commit -m "feat(metadata): read chunks by document"
```

### Task 4: Metadata Resource Reader

**Files:**

- Create: `src/vault_graph/mcp/metadata_resource_reader.py`
- Modify: `src/vault_graph/mcp/mcp_resources.py`
- Test: `tests/test_metadata_resource_reader.py`
- Test: `tests/test_mcp_resources.py`

- [ ] **Step 1: Write failing metadata resource tests**

Cover:

- document resource uses `document_state`, `resolve_document`, and `list_document_chunks`; it does not read the Vault file after indexing.
- page resource requires `wiki/`.
- source resource accepts `raw/`, `docs/`, `scratch/reports/`, or frontmatter `type: source`.
- decision resource accepts `wiki/decisions/` or frontmatter `type: decision`.
- issue resource accepts `wiki/issues/` or frontmatter `type: issue`.
- classification mismatch returns `resource_not_found`.
- tombstoned or missing document returns `resource_not_found`.
- document from a different Vault returns `resource_not_found`.
- metadata envelope contains hashes, revisions, chunk count, and evidence refs.
- no chunks returns empty Markdown text plus `missing_evidence` warning.
- same logical path in two Vaults resolves to different documents and evidence.

Run:

```bash
uv run --python 3.12 pytest tests/test_metadata_resource_reader.py -q
```

Expected: fail because reader does not exist.

- [ ] **Step 2: Implement `MetadataResourceReader`**

Use the contract above. Keep helpers private and small:

- `_read_by_path(...)`
- `_read_by_document_id(...)`
- `_render_markdown(chunks: tuple[ChunkSnapshot, ...]) -> str`
- `_document_metadata(...) -> dict[str, object]`
- `_evidence_dict(...) -> dict[str, object]`
- `_warning(...) -> McpErrorPayload`
- `_raise_not_found(...) -> None`

- [ ] **Step 3: Wire real reader into registry**

`register_mcp_resources(...)` should construct:

```python
metadata_reader = MetadataResourceReader(
    catalog=services.catalog,
    metadata_store=services.metadata_store,
)
```

and dispatch metadata resource kinds to the reader.

- [ ] **Step 4: Run focused tests**

Run:

```bash
uv run --python 3.12 pytest tests/test_metadata_resource_reader.py tests/test_mcp_resources.py -q
```

Expected: pass.

- [ ] **Step 5: Commit**

```bash
git add src/vault_graph/mcp/metadata_resource_reader.py src/vault_graph/mcp/mcp_resources.py tests/test_metadata_resource_reader.py tests/test_mcp_resources.py
git commit -m "feat(mcp): read metadata resources"
```

### Task 5: Graph Resource Service

**Files:**

- Create: `src/vault_graph/app/graph_resource_service.py`
- Modify: `src/vault_graph/mcp/mcp_service_factory.py`
- Test: `tests/test_graph_resource_reader.py`
- Test: `tests/test_mcp_service_factory.py`

- [ ] **Step 1: Write failing graph service tests**

Use fakes for `GraphStore`, `MetadataStore`, and `GraphReadinessChecker`.

Cover:

- `get_entity(...)` checks graph readiness before reading entity details.
- missing graph state maps to graph-unavailable behavior.
- stale graph state produces warnings, not silent success without warnings.
- missing entity returns `resource_not_found`.
- tombstoned entity returns `resource_not_found`.
- `find_concept(...)` resolves one exact active concept inside the requested Vault.
- no exact concept match returns `resource_not_found`.
- multiple exact concept matches return `ambiguous_resource`.
- related relationships include `stated`, `inferred`, `contested`, and `deprecated`.
- evidence resolution preserves evidence Vault IDs.
- missing evidence creates `missing_evidence` warning.

Run:

```bash
uv run --python 3.12 pytest tests/test_graph_resource_reader.py -q
```

Expected: fail because service does not exist.

- [ ] **Step 2: Implement `GraphResourceService`**

Keep MCP-free. Prefer app/domain errors:

- `CatalogError` for invalid Vault selection.
- `GraphStoreError("resource_not_found: ...")` for missing entity/concept.
- `GraphStoreError("ambiguous_resource: ...")` for ambiguous concepts.
- `GraphStoreError("graph_unavailable: ...")` for unavailable graph state.

Do not import `vault_graph.mcp`.

- [ ] **Step 3: Add `McpServiceFactory.open_graph_resource_service()`**

Use the service-factory contract above. Verify it does not import `RustworkxGraphProjection`.

- [ ] **Step 4: Extend service factory import-boundary tests**

Add a test similar to `test_mcp_factory_graph_service_imports_rustworkx_only_when_requested`, but for `open_graph_resource_service()`:

- after `factory.open_read_only()`, `vault_graph.projection.rustworkx_projection` is not in `sys.modules`.
- after `factory.open_graph_resource_service()`, it is still not in `sys.modules`.

- [ ] **Step 5: Run focused tests**

Run:

```bash
uv run --python 3.12 pytest tests/test_graph_resource_reader.py tests/test_mcp_service_factory.py -q
```

Expected: pass for service-level cases and import boundary.

- [ ] **Step 6: Commit**

```bash
git add src/vault_graph/app/graph_resource_service.py src/vault_graph/mcp/mcp_service_factory.py tests/test_graph_resource_reader.py tests/test_mcp_service_factory.py
git commit -m "feat(graph): add resource read service"
```

### Task 6: Graph Resource Reader And MCP Dispatch

**Files:**

- Create: `src/vault_graph/mcp/graph_resource_reader.py`
- Modify: `src/vault_graph/mcp/mcp_resources.py`
- Modify: `src/vault_graph/mcp/mcp_errors.py`
- Test: `tests/test_graph_resource_reader.py`
- Test: `tests/test_mcp_resources.py`

- [ ] **Step 1: Write failing graph reader tests**

Cover:

- entity resource returns canonical JSON envelope.
- concept resource calls `find_concept(...)`.
- graph warnings become `McpErrorPayload`.
- graph output groups relationships by status.
- graph output preserves source/target/evidence/owner Vault IDs.
- `GraphStoreError("graph_unavailable: ...")` maps to `graph_unavailable`.
- `GraphStoreError("ambiguous_resource: ...")` maps to `ambiguous_resource`.
- not-found graph resources map to `resource_not_found`.

Run:

```bash
uv run --python 3.12 pytest tests/test_graph_resource_reader.py -q
```

Expected: fail until reader exists and maps errors.

- [ ] **Step 2: Implement `GraphResourceReader`**

Add private conversion helpers:

- `_entity_to_dict(entity: EntityRecord) -> dict[str, object]`
- `_relationship_to_dict(relationship: RelationshipRecord) -> dict[str, object]`
- `_evidence_to_dict(evidence: EvidenceReference) -> dict[str, object]`
- `_revision_to_dict(revision: GraphRetrievalRevision) -> dict[str, object]`
- `_warning_to_mcp(warning: GraphResourceWarning) -> McpErrorPayload`

- [ ] **Step 3: Implement lazy graph reader factory in `mcp_resources.py`**

Shape:

```python
class LazyGraphResourceReaderFactory:
    def __init__(self, *, service_factory: McpServiceFactory) -> None:
        self._service_factory = service_factory
        self._reader: GraphResourceReader | None = None

    def get(self) -> GraphResourceReader:
        if self._reader is None:
            self._reader = GraphResourceReader(
                graph_resource_service=self._service_factory.open_graph_resource_service()
            )
        return self._reader
```

- [ ] **Step 4: Wire graph dispatch**

`McpResourceRegistry.read(...)` dispatches `graph_entity` and `concept` through the lazy factory.

- [ ] **Step 5: Run focused tests**

Run:

```bash
uv run --python 3.12 pytest tests/test_graph_resource_reader.py tests/test_mcp_resources.py tests/test_mcp_import_boundaries.py -q
```

Expected: pass.

- [ ] **Step 6: Commit**

```bash
git add src/vault_graph/mcp/graph_resource_reader.py src/vault_graph/mcp/mcp_resources.py src/vault_graph/mcp/mcp_errors.py tests/test_graph_resource_reader.py tests/test_mcp_resources.py
git commit -m "feat(mcp): read graph resources"
```

### Task 7: Read-Only Boundary And Multi-Vault Resource Tests

**Files:**

- Create: `tests/test_mcp_resource_read_only_boundary.py`
- Modify: `tests/test_mcp_resources.py`
- Modify: `tests/test_metadata_resource_reader.py`

- [ ] **Step 1: Write read-only boundary tests**

Cover:

- successful document resource read does not mutate Vault bytes.
- missing document resource read does not mutate Vault bytes.
- invalid URI read fails before metadata store lookup.
- resource reads do not create `metadata`, `vector`, `graph`, `projection_cache`, or model cache directories when missing.
- resource reads never call `VaultLoader`; enforce with monkeypatch that raises if imported/called.

Run:

```bash
uv run --python 3.12 pytest tests/test_mcp_resource_read_only_boundary.py -q
```

Expected: pass if earlier tasks preserved boundaries; otherwise fix.

- [ ] **Step 2: Add multi-Vault resource tests**

Cover:

- two Vaults with `wiki/spec.md` produce two distinct resource URIs and document IDs.
- reading `vault://main/documents/wiki%2Fspec.md` never returns `work` Vault metadata.
- warnings include `affected_vault_ids` where relevant.
- context/current is per Vault and does not aggregate all Vaults.

Run:

```bash
uv run --python 3.12 pytest tests/test_metadata_resource_reader.py tests/test_mcp_resources.py -q
```

Expected: pass.

- [ ] **Step 3: Commit**

```bash
git add tests/test_mcp_resource_read_only_boundary.py tests/test_mcp_resources.py tests/test_metadata_resource_reader.py
git commit -m "test(mcp): cover resource read boundaries"
```

### Task 8: Official MCP Stdio Smoke And Full Verification

**Files:**

- Modify: `tests/test_mcp_stdio_smoke.py`

- [ ] **Step 1: Update official MCP client smoke test**

Keep the environment gate `VG_RUN_MCP_STDIO_SMOKE=1`.

Add assertions:

```python
templates = await session.list_resource_templates()
template_uris = {str(template.uriTemplate) for template in templates.resourceTemplates}
assert "vault://{vault_id}/documents/{path}" in template_uris
assert "vault://context/packs/{pack_id}" in template_uris
```

Keep existing assertions:

- `tools.tools == []` until Phase 5C.
- `resources.resources == []` or only a tiny generated set.
- `prompts.prompts == []` until Phase 5C.

- [ ] **Step 2: Run focused MCP tests**

Run:

```bash
uv run --python 3.12 pytest tests/test_mcp_uri.py tests/test_mcp_resources.py tests/test_metadata_resource_reader.py tests/test_graph_resource_reader.py tests/test_context_pack_resource_cache.py tests/test_mcp_resource_read_only_boundary.py tests/test_mcp_server.py tests/test_mcp_service_factory.py tests/test_mcp_import_boundaries.py -q
```

Expected: pass.

- [ ] **Step 3: Run official stdio smoke when local environment permits**

Run:

```bash
VG_RUN_MCP_STDIO_SMOKE=1 uv run --python 3.12 pytest tests/test_mcp_stdio_smoke.py -q
```

Expected: pass. If it cannot run in the environment, record the exact reason and run the non-gated MCP resource tests instead.

- [ ] **Step 4: Run full project verification**

Run:

```bash
uv run --python 3.12 pytest -q
uv run --python 3.12 ruff check src tests
uv run --python 3.12 mypy src tests
git diff --check
```

Expected:

- pytest passes with no new failures.
- ruff exits 0.
- mypy exits 0.
- `git diff --check` exits 0.

- [ ] **Step 5: Commit**

```bash
git add tests/test_mcp_stdio_smoke.py
git commit -m "test(mcp): smoke resource templates"
```

## Error Handling And Edge Cases

URI errors:

- malformed URI -> `invalid_resource_uri`
- unsupported scheme -> `invalid_resource_uri`
- query or fragment -> `invalid_resource_uri`
- unknown resource kind -> `invalid_resource_uri`
- raw slash template value -> FastMCP no match or parser `invalid_resource_uri`
- encoded traversal -> `invalid_resource_uri`
- non-Markdown path -> `invalid_resource_uri`
- page outside `wiki/` -> `invalid_resource_uri`
- unknown Vault -> `unknown_vault_id`
- disabled Vault -> `vault_disabled`

Metadata errors:

- missing database -> missing resource or `metadata_unavailable` depending on read path
- schema incompatible -> `metadata_unavailable`
- missing/tombstoned document -> `resource_not_found`
- document ID from another Vault -> `resource_not_found`
- classification mismatch -> `resource_not_found`
- document exists with no chunks -> resource body with `missing_evidence` warning

Graph errors:

- graph store missing/unavailable/incompatible -> `graph_unavailable`
- graph stale -> warning if evidence can still be returned; otherwise `graph_unavailable`
- missing entity/concept -> `resource_not_found`
- ambiguous concept -> `ambiguous_resource`
- missing graph evidence -> `missing_evidence` warning

Context pack cache errors:

- missing pack ID -> `resource_not_found`
- cache evicted or server restarted -> `resource_not_found` with regeneration hint
- invalid max entries -> `ContextPackError`

Read-only failures:

- any attempted Vault write -> test failure and `read_only_boundary_error`
- missing state creation during resource read -> test failure
- direct `VaultLoader` usage in resource read -> test failure

## Validation Review

Security/read-only:

- URI parsing rejects absolute paths, traversal, raw slash mismatches, unknown schemes, query strings, fragments, and disabled Vault IDs before store lookup.
- Resource readers never call `VaultLoader` or direct filesystem reads.
- MCP stdio stdout remains protocol-only because registration happens during server construction without startup prints.
- Error sanitization remains in `mcp_errors.py`; local absolute paths are not exposed except the explicit `--state` path.

Performance/scalability:

- Resource startup registers templates only; it does not list every document.
- `MetadataStore.list_document_chunks(...)` avoids filtering a whole Vault for one document.
- Graph resource service opens lazily and does not import rustworkx projection.
- Context pack cache is bounded by count and keeps only rendered JSON in memory.

Testability:

- URI parser is pure and unit-testable.
- Metadata resource reader can be tested with fake metadata stores.
- Graph resource service is MCP-free and can be tested with fake graph/readiness stores.
- FastMCP behavior is tested through public `list_resource_templates()` and `read_resource()`.
- Read-only tests compare filesystem bytes before and after resource reads.

Maintainability/deep modules:

- `mcp_uri.py` hides URI parsing details behind one stable object.
- `metadata_resource_reader.py` owns document rendering and classification.
- `GraphResourceService` owns graph readiness and store reads for resource use; MCP only adapts it.
- `ContextPackResourceCache` owns cache policy; `ContextPackBuilder` remains the pack assembly module.
- No generic `utils`, `helpers`, or `manager` modules are introduced.

Agent ergonomics:

- All resources return a stable JSON envelope.
- Resource links preserve Vault IDs and can be returned by Phase 5C tools.
- Warnings and recovery hints are structured, not hidden in prose.
- `list_resources()` stays small so agents do not start broad Vault scans.

## Risks And Mitigations

- **Risk:** FastMCP wraps handler exceptions as SDK resource errors, which may hide custom exception types from external clients.
  **Mitigation:** Keep direct `McpResourceRegistry.read(...)` tests for structured payloads and smoke-test external client behavior for template listing. Preserve structured error payload messages when raising `McpProtocolError`.

- **Risk:** Existing chunk ordering does not store an explicit ordinal.
  **Mitigation:** Use the current `list_chunks(...)` ordering style for Phase 5B and do not add a migration. If later chunk ordering needs stronger guarantees, design it as a metadata schema migration.

- **Risk:** Concept matching could drift from graph indexing normalization.
  **Mitigation:** Reuse an existing graph identity normalizer if present. If not, implement the smallest local normalization and cover it with tests; do not introduce cross-Vault entity merging.

- **Risk:** Current-context availability could grow into memory summary behavior.
  **Mitigation:** Limit it to catalog, status, health, and cache fields. Timeline and memory summaries remain unavailable until Phase 6 services exist.

- **Risk:** Context pack resource cache could be mistaken for durable persistence.
  **Mitigation:** Keep it in-process only, expose regeneration hints, and do not write pack JSON to disk.

## Open Decisions

None.

This plan follows accepted project decisions:

- Vault remains the source of truth.
- Vault Graph resources are read-only, rebuildable working context.
- MCP is an adapter over application services.
- Context pack resources are in-process generated artifacts until a durable pack store is explicitly designed later.

## Required Final Verification

Before declaring Phase 5B implementation complete, run:

```bash
uv run --python 3.12 pytest tests/test_mcp_uri.py tests/test_mcp_resources.py tests/test_metadata_resource_reader.py tests/test_graph_resource_reader.py tests/test_context_pack_resource_cache.py tests/test_mcp_resource_read_only_boundary.py tests/test_mcp_stdio_smoke.py -q
uv run --python 3.12 pytest -q
uv run --python 3.12 ruff check src tests
uv run --python 3.12 mypy src tests
git diff --check
```

Run the official stdio smoke test with:

```bash
VG_RUN_MCP_STDIO_SMOKE=1 uv run --python 3.12 pytest tests/test_mcp_stdio_smoke.py -q
```

Expected final signal:

- official MCP client lists Phase 5B resource templates.
- `list_resources()` does not enumerate the full Vault.
- resource reads are JSON envelopes with normalized URI, metadata, and warnings.
- no resource read mutates Vault files or creates missing derived-state directories.
- all tests, lint, type check, and diff whitespace checks pass.
