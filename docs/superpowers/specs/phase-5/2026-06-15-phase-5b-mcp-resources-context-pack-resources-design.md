# Phase 5B MCP Resources And Context Pack Resource SPEC

Status: Implementation-ready design for planning

Date: 2026-06-15

Last updated: 2026-06-17

Scope: Phase 5B

## 1. Purpose

Phase 5B exposes read-only MCP resources over indexed Vault Graph state and
generated context packs. Resources let agents request precise evidence by URI
instead of scanning an entire Vault or treating search text as durable
knowledge.

The slice extends the completed Phase 5A stdio foundation. It must reuse
`McpServiceFactory`, `McpErrorPayload`, and `McpScopeInput`; it must not create
a second MCP runtime, retrieval layer, graph layer, context-pack builder, or
Vault reader.

Resources are working context. They do not publish durable knowledge and do not
make generated context packs authoritative.

## 2. Success Criteria

Phase 5B is complete when:

- `vg serve --mcp` lists MCP resource templates through the official MCP client.
- resource reads are backed by `MetadataStore`, graph services, status services,
  or the in-process context-pack cache, never by direct Vault file reads.
- every Vault-derived resource URI preserves `vault_id`.
- identical logical paths in different Vaults resolve to distinct resources.
- invalid or unsafe URIs fail closed before any store lookup.
- generated context pack resources are readable only while present in the
  bounded in-process cache.
- reading resources does not create metadata, vector, graph, cache, model, or
  Vault files.
- all resource bodies include a normalized URI, evidence metadata, warnings, and
  recovery hints where relevant.

## 3. In Scope

- FastMCP resource-template registration on the Phase 5A server.
- URI parsing, normalization, encoding helpers, and validation for `vault://`.
- Metadata-backed resources for documents, pages, sources, decisions, and
  issues.
- Graph-backed resources for graph entities and concept-name lookups when graph
  state is available.
- Current-context availability resource backed by existing catalog and status
  state.
- Timeline resource template with a clear unavailable response until a timeline
  service exists.
- Bounded in-process cache for `vault://context/packs/{pack_id}`.
- Resource-specific errors and warnings using `McpErrorPayload`.
- Tests for read-only behavior, URI safety, FastMCP compatibility, and
  multi-Vault identity.

## 4. Out Of Scope

- resource subscriptions and list-changed notifications
- full listing of every indexed document by default
- durable context-pack persistence
- context-pack building as a resource read side effect
- indexing from MCP
- editing, renaming, deleting, or publishing Vault files
- binary resources
- remote HTTP resources
- LLM answer synthesis
- Phase 6 memory, issue, timeline, or project-memory projections

## 5. Phase 5A Dependency Contract

Phase 5B must build on the current Phase 5A files:

```text
src/vault_graph/mcp/
├── mcp_server.py
├── mcp_service_factory.py
├── mcp_scope.py
├── mcp_errors.py
└── mcp_config_examples.py
```

Required reuse:

- `create_mcp_server(config)` remains the single server construction entry
  point.
- `RegisteredMcpServer` owns runtime objects that must be shared by Phase 5C,
  including the context-pack resource cache.
- `McpServiceFactory.open_read_only()` opens base services without indexing or
  creating missing stores.
- `McpServiceFactory.open_graph_retrieval_service()` remains lazy and imports
  rustworkx only for graph resources or graph tools.
- `McpErrorPayload` is the structured warning/error shape used by resources and
  tools.

## 6. Files To Add Or Modify

Add:

```text
src/vault_graph/mcp/mcp_uri.py
src/vault_graph/mcp/mcp_resources.py
src/vault_graph/mcp/metadata_resource_reader.py
src/vault_graph/mcp/graph_resource_reader.py
src/vault_graph/mcp/context_pack_resource_cache.py
src/vault_graph/app/graph_resource_service.py
```

Modify:

```text
src/vault_graph/mcp/__init__.py
src/vault_graph/mcp/mcp_server.py
src/vault_graph/mcp/mcp_service_factory.py
src/vault_graph/storage/interfaces/metadata_store.py
src/vault_graph/storage/local/sqlite_metadata_store.py
tests/test_mcp_stdio_smoke.py
```

Add tests:

```text
tests/test_mcp_uri.py
tests/test_mcp_resources.py
tests/test_metadata_resource_reader.py
tests/test_graph_resource_reader.py
tests/test_context_pack_resource_cache.py
tests/test_mcp_resource_read_only_boundary.py
```

## 7. Resource URI Contract

Phase 5B registers these URI templates:

```text
vault://{vault_id}/documents/{path}
vault://{vault_id}/pages/{path}
vault://{vault_id}/sources/{id}
vault://{vault_id}/concepts/{name}
vault://{vault_id}/decisions/{id}
vault://{vault_id}/issues/{id}
vault://{vault_id}/timeline/recent
vault://{vault_id}/context/current
vault://{vault_id}/graph/entities/{id}
vault://context/packs/{pack_id}
```

FastMCP template parameters do not match slash-containing path values. For
Phase 5B, `{path}`, `{id}`, `{name}`, and `{pack_id}` are single URI-template
segments. If a logical value contains `/`, it must be percent-encoded with
`quote(value, safe="")`.

Examples:

```text
logical path: wiki/spec.md
resource URI: vault://main/documents/wiki%2Fspec.md

logical concept name: Graph RAG
resource URI: vault://main/concepts/Graph%20RAG
```

Rules:

- `vault://{vault_id}/...` resources must include a known, enabled Vault ID.
- `vault://context/packs/{pack_id}` is generated and is not tied to one Vault in
  the URI because the pack body records requested and actual scopes.
- normalized resource URIs always use percent-encoded single-segment values.
- decoded paths are Vault-relative logical paths, never absolute filesystem
  paths.
- the parser rejects unknown schemes, unknown resource kinds, missing Vault IDs,
  unknown Vault IDs, disabled Vaults, absolute paths, raw slash in a template
  value, `..`, `.`, empty segments, encoded traversal, encoded slash where the
  resource kind expects an opaque ID, and empty IDs.
- the parser must not call stores or touch the filesystem.
- resource output includes both the normalized URI and decoded logical value in
  metadata.

## 8. URI Parser Contract

`src/vault_graph/mcp/mcp_uri.py` owns all `vault://` parsing. Resource readers
must receive a parsed object instead of reparsing strings.

```python
from dataclasses import dataclass
from typing import Literal

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

Validation details:

- use `urllib.parse.urlsplit`, `quote`, and `unquote`; do not hand-split query
  strings or decode by replacement.
- reject non-empty query strings or fragments.
- reject path values when decoding changes `%2e`, `%2E`, `%2f`, or `%2F` into a
  traversal or raw slash that the resource kind does not allow.
- allow decoded slash only for `document` and `page` path resources.
- require `path.endswith(".md")` for `document` and `page` resources because
  Phase 5B indexes Markdown only.
- require page paths to stay under `wiki/`.
- for path resources, require the decoded path to be inside the selected Vault
  entry's `content_scopes` by same-or-child matching.
- for opaque-ID resources, defer content-scope and classification validation to
  the reader after the indexed document or graph record is resolved.
- return `McpProtocolError(kind="invalid_parameter")` with
  `invalid_resource_uri`, `unknown_vault_id`, or `vault_disabled` payload codes.

## 9. Resource Body Contract

Phase 5B uses a canonical JSON envelope for every FastMCP resource body.

FastMCP high-level resources support static template metadata, but they do not
provide a stable way to attach dynamic `_meta` per resource read. A JSON envelope
keeps evidence metadata and warnings first-class without depending on SDK
private attributes. Future lower-level MCP serving may map the same fields into
native MCP `_meta` without changing reader contracts.

```python
from dataclasses import dataclass
from typing import Literal

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
```

The registered FastMCP MIME type for Phase 5B resources is
`application/json`. `content_mime_type` tells clients whether `text` should be
treated as Markdown or JSON.

Envelope fields:

- `uri`: normalized URI resolved by `mcp_uri.py`
- `content_mime_type`: logical content type for `text`
- `text`: Markdown or JSON string produced by the reader
- `metadata`: structured evidence, revision, scope, and decoded logical values
- `warnings`: structured `McpErrorPayload` values

Document-like resources put content in `text` as Markdown. JSON-like resources
put a stable JSON string in `text`. Dynamic facts, evidence, hashes, revisions,
and warnings belong in `metadata` and `warnings`, not hidden inside Markdown
prose.

## 10. Resource Registry And FastMCP Registration

`src/vault_graph/mcp/mcp_resources.py` owns template registration and dispatch.

```python
from collections.abc import Callable
from typing import Protocol

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

def register_mcp_resources(
    server: McpResourceServer,
    *,
    services: McpServices,
    service_factory: McpServiceFactory,
    context_pack_cache: ContextPackResourceCache,
) -> McpResourceRegistry: ...
```

Registration rules:

- register templates only through the public `FastMCP.resource(...)` decorator.
- do not access private SDK attributes.
- each template handler reconstructs the URI string from template arguments and
  delegates to `McpResourceRegistry.read(...)`.
- template handlers return `json.dumps(body.to_json_dict(), sort_keys=True,
  ensure_ascii=False, indent=2) + "\n"`.
- the registry catches domain exceptions and converts them through
  `map_exception_to_mcp_error(...)` before exposing a protocol error.
- `list_resources()` should remain small; Phase 5B relies on
  `list_resource_templates()` and direct resource reads instead of listing every
  document.

`mcp_server.py` changes:

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

`create_mcp_server(...)` constructs the cache, registers resources, and returns
the expanded wrapper. It must keep MCP SDK imports lazy.

## 11. Metadata Store Extension

Phase 5B should add a focused read method instead of making resource readers
filter every chunk in a Vault.

```python
class MetadataStore(Protocol):
    def list_document_chunks(
        self,
        *,
        vault_id: str,
        document_id: str,
    ) -> tuple[ChunkSnapshot, ...]: ...
```

`SQLiteMetadataStore.list_document_chunks(...)` must:

- use `vault_id` and `document_id` filters.
- return chunks ordered by indexed document order, preserving heading-section
  order from `heading-section-v1`.
- return an empty tuple for unknown or tombstoned documents.
- perform no writes and no implicit schema initialization.

This method is a Phase 5B requirement, not a temporary optimization. It keeps
resource rendering behind a small store interface and avoids repeated
scope-wide scans as Vaults grow.

## 12. Metadata Resource Reader

`src/vault_graph/mcp/metadata_resource_reader.py` renders document-like
resources from indexed metadata only.

```python
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

Identity rules:

- `documents/{path}` and `pages/{path}` resolve by decoded logical path through
  `MetadataStore.document_state(vault_id, path)`.
- `sources/{id}`, `decisions/{id}`, and `issues/{id}` resolve by
  `document_id`; tools may return these links after search or context-pack
  assembly.
- `resolve_document(document_id)` results must match the URI `vault_id`; a
  mismatch is `resource_not_found`.
- source, decision, and issue readers verify the resolved document classification
  before rendering:
  - source: `raw/`, `docs/`, or `scratch/reports/` path, or frontmatter
    `type: source`
  - decision: `wiki/decisions/` path or frontmatter `type: decision`
  - issue: `wiki/issues/` path or frontmatter `type: issue`
- a classification mismatch returns `resource_not_found`; it must not render an
  unrelated document under a misleading resource kind.

Rendering rules:

- render chunks in `list_document_chunks(...)` order.
- preserve original chunk text; do not re-read the Vault file.
- add heading separators only when needed to keep adjacent chunks readable.
- do not inject hidden prompt instructions into resource content.
- put document metadata in the JSON envelope:
  - `vault_id`
  - `document_id`
  - decoded logical path
  - document kind
  - frontmatter hash
  - content hash
  - raw SHA-256
  - parser version
  - chunker version
  - metadata index revision
  - Vault revision
  - chunk count
  - evidence refs
- warn with `missing_evidence` when a document has metadata but no current
  chunks.
- return `resource_not_found` for missing or tombstoned documents.
- return `stale_index` as a warning when store health or document/chunk
  revisions show stale metadata.

## 13. Graph Resource Service And Reader

Graph resources need graph state, graph readiness, and metadata evidence. Keep
that logic behind an application service so future HTTP serving can reuse it.

Add `src/vault_graph/app/graph_resource_service.py`:

```python
@dataclass(frozen=True)
class GraphResourceWarning:
    code: str
    message: str
    severity: str
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

`McpServiceFactory` adds:

```python
def open_graph_resource_service(self) -> GraphResourceService: ...
```

Graph rules:

- opening graph resources is lazy; importing `vault_graph.mcp` and
  `open_read_only()` must not import rustworkx.
- `get_entity(...)` checks graph readiness for the selected Vault before
  reading.
- `find_concept(...)` searches active graph entities by normalized concept name
  within the selected Vault only.
- no graph concept match returns `resource_not_found`; multiple active exact
  concept matches return `ambiguous_resource` so the caller can use a graph
  entity URI instead.
- graph entity output includes relationship status labels:
  `stated`, `inferred`, `contested`, and `deprecated`.
- cross-Vault evidence refs preserve `evidence_vault_id`, `owner_vault_id`, and
  relationship source/target Vault IDs.
- unavailable graph state returns `graph_unavailable` or `resource_not_available`
  instead of silently degrading to metadata text.

`src/vault_graph/mcp/graph_resource_reader.py` turns service results into
`McpResourceBody`.

```python
class GraphResourceReader:
    def __init__(self, *, graph_resource_service: GraphResourceService) -> None: ...

    def read_entity(self, uri: McpResourceUri) -> McpResourceBody: ...
    def read_concept(self, uri: McpResourceUri) -> McpResourceBody: ...
```

The reader returns `content_mime_type="application/json"` and a stable JSON
string containing:

- entity identity, type, name, aliases, canonical path, confidence, status, and
  graph index revision
- evidence refs and resolved metadata evidence
- relationship summaries grouped by status
- graph extraction spec version and digest
- graph/store/projection revisions when available
- warnings

## 14. Current Context And Timeline Resources

`src/vault_graph/mcp/mcp_resources.py` may keep current context rendering inside
the registry module or split it into a small reader. If split, use this shape:

```python
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
```

`vault://{vault_id}/context/current` is an availability resource, not a memory
summary. It may include:

- selected Vault ID and display name
- enabled content scopes
- active Vault marker
- metadata/vector/graph health status available through existing services
- context-pack cache size and max entries
- warnings for missing, stale, or unavailable projections

It must not summarize project memory, synthesize a current-state narrative, or
scan Vault files.

`vault://{vault_id}/timeline/recent` remains a template in the URI contract, but
Phase 5B returns `resource_not_available` until a timeline projection service
exists. This keeps the resource vocabulary stable without inventing summaries.

## 15. Context Pack Resource Cache

Phase 4 intentionally avoided durable pack persistence. Phase 5B keeps that
choice.

`src/vault_graph/mcp/context_pack_resource_cache.py`:

```python
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

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

Cache policy:

- in-process only
- bounded by count, default `32` packs
- evicts least-recently-used packs
- writes no files
- stores rendered canonical JSON only
- does not change `ContextPack` JSON schema
- returns `resource_not_found` for missing pack IDs with recovery hint:
  call `build_context_pack` again

Phase 5B registers `vault://context/packs/{pack_id}` and implements reads from
this cache. Phase 5C `build_context_pack` must use the same cache instance from
`RegisteredMcpServer`, return structured pack JSON, and include the resource URI
for follow-up reads.

## 16. Error And Warning Policy

Resource error payload codes:

- `invalid_resource_uri`
- `unknown_vault_id`
- `vault_disabled`
- `resource_not_found`
- `resource_not_available`
- `ambiguous_resource`
- `metadata_unavailable`
- `graph_unavailable`
- `stale_index`
- `missing_evidence`
- `read_only_boundary_error`

Policy:

- invalid URI, unknown Vault, disabled Vault, and unsupported resource kind are
  invalid-parameter errors.
- missing documents, missing graph entities, and missing cached packs are
  not-found errors.
- missing backends, unhealthy stores, and stale projections are execution errors
  or warnings depending on whether a partial resource can still be returned.
- local absolute paths must be redacted through `mcp_errors.py` unless the path
  is the explicit user-provided `--state` path.
- warnings are included in the JSON envelope `warnings` field; they must not be
  hidden only in Markdown text.

## 17. Security And Read-Only Requirements

- resource reads never execute shell commands.
- resource reads never accept raw filesystem roots.
- resource reads never call `VaultLoader`.
- resource reads never write registered Vault roots.
- resource reads never create missing Vault Graph state directories.
- URI parsing rejects absolute paths and traversal before store calls.
- decoded logical paths are checked against the selected Vault entry's enabled
  content scopes.
- FastMCP stdout remains protocol-only; diagnostics go to stderr.
- all tests that inspect filesystem side effects compare Vault and state bytes
  before and after resource reads.

## 18. Multi-Vault Requirements

- every Vault-derived resource URI includes `vault_id`.
- `vault://context/packs/{pack_id}` stores requested and actual scopes in the
  context-pack JSON body.
- identical decoded paths in two Vaults must resolve through separate
  `document_id` values and separate metadata evidence.
- warnings include `affected_vault_ids`.
- graph relationships preserve source, target, owner, and evidence Vault IDs.
- current context is per Vault; all-Vault summaries are out of scope for 5B.

## 19. Resource Listing Policy

Do not list every indexed document by default. A large Vault may contain
thousands of indexed files, and broad listing would encourage whole-Vault
scans.

Phase 5B should:

- expose resource templates through `list_resource_templates()`.
- keep `list_resources()` empty or limited to a very small generated set.
- let Phase 5C tools return precise resource links for follow-up reads.
- never create a full resource list by scanning `MetadataStore` during server
  startup.

## 20. Implementation Flow

Server startup:

```text
vg serve --mcp --state PATH
  -> create_mcp_server(config)
  -> McpServiceFactory.open_read_only()
  -> create ContextPackResourceCache(max_entries=32)
  -> register_mcp_resources(...)
  -> run stdio transport
```

Document read:

```text
read vault://main/documents/wiki%2Fspec.md
  -> parse_mcp_resource_uri(...)
  -> resolve enabled VaultCatalog entry
  -> MetadataStore.document_state("main", "wiki/spec.md")
  -> reject tombstone or missing state
  -> MetadataStore.resolve_document(document_id)
  -> MetadataStore.list_document_chunks(vault_id="main", document_id=...)
  -> render chunk text in order
  -> return JSON envelope with Markdown text and metadata
```

Graph entity read:

```text
read vault://main/graph/entities/{entity_id}
  -> parse_mcp_resource_uri(...)
  -> lazily open GraphResourceService
  -> check graph readiness for main
  -> resolve entity, relationships, and evidence
  -> return JSON envelope with graph JSON text and warnings
```

Context pack read:

```text
read vault://context/packs/{pack_id}
  -> parse_mcp_resource_uri(...)
  -> ContextPackResourceCache.get(pack_id)
  -> return cached canonical pack JSON
  -> if missing, return resource_not_found with build_context_pack recovery hint
```

## 21. Test Plan

Required focused tests:

- `test_mcp_uri.py`
  - accepts encoded logical paths and normalizes them.
  - rejects raw slash path template values where FastMCP cannot match.
  - rejects unknown schemes, query strings, fragments, absolute paths,
    traversal, encoded traversal, unknown Vault IDs, disabled Vaults, and empty
    IDs.
  - allows decoded slash only for document/page paths.
- `test_mcp_resources.py`
  - registers all expected FastMCP templates with `application/json` MIME type.
  - `list_resources()` does not enumerate all documents.
  - direct FastMCP `read_resource(...)` returns the JSON envelope.
  - no private FastMCP attributes are used.
- `test_metadata_resource_reader.py`
  - document and page resources read indexed metadata only.
  - source, decision, and issue resources validate classification.
  - chunk order, hashes, revisions, and evidence metadata are preserved.
  - tombstoned or missing documents return not found.
  - the same path in two Vaults resolves to different resources.
- `test_graph_resource_reader.py`
  - graph resources open graph dependencies lazily.
  - missing graph state returns `graph_unavailable`.
  - entity resources preserve evidence Vault IDs and relationship statuses.
  - concept lookups resolve only within the requested Vault.
- `test_context_pack_resource_cache.py`
  - `put` and `get` return rendered canonical JSON.
  - LRU eviction removes the least-recently-used pack.
  - missing pack IDs return not found with regeneration hint.
  - cache does not write files.
- `test_mcp_resource_read_only_boundary.py`
  - resource reads do not mutate registered Vault roots.
  - resource reads do not create metadata/vector/graph/cache/model state.
  - invalid resource reads fail before store lookup.
- update `test_mcp_stdio_smoke.py`
  - official MCP client sees resource templates after startup.
  - stdout contains only protocol messages.

Required final verification:

```bash
uv run --python 3.12 pytest tests/test_mcp_uri.py tests/test_mcp_resources.py tests/test_metadata_resource_reader.py tests/test_graph_resource_reader.py tests/test_context_pack_resource_cache.py tests/test_mcp_resource_read_only_boundary.py tests/test_mcp_stdio_smoke.py -q
uv run --python 3.12 pytest -q
uv run --python 3.12 ruff check src tests
uv run --python 3.12 mypy src tests
git diff --check
```

## 22. Handoff To Phase 5C

Phase 5C tools should return resource links created by Phase 5B where useful:

- `search_vault(...)` returns document/page/source resource links for evidence.
- `find_related(...)` returns graph entity resource links.
- `get_decision_trace(...)` returns decision and graph entity resource links.
- `build_context_pack(...)` stores the rendered pack in
  `ContextPackResourceCache` and returns `vault://context/packs/{pack_id}`.

Phase 5C must not create a second context-pack cache or a separate URI format.

## 23. Open Decisions

None. The design uses existing accepted project decisions:

- Vault remains the source of truth.
- MCP is a read-only adapter over application services.
- context packs are generated working context, not durable knowledge.
- generated context-pack resources remain in-process until a later durable pack
  store is explicitly designed.
