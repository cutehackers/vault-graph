# Phase 5B MCP Resources And Context Pack Resource Design

Status: Draft for implementation planning

Date: 2026-06-15

Scope: Phase 5B

## 1. Purpose

Phase 5B exposes read-only MCP resources over indexed Vault content and generated
context packs. Resources let agents request precise context by URI instead of
asking for full-Vault scans or opaque search output.

Resources remain working context. They do not publish durable knowledge and do
not make generated context packs authoritative.

## 2. In Scope

- Resource templates for Vault documents, pages, sources, decisions, issues,
  recent timeline, current context, graph entities, and context packs.
- URI parsing and validation for the `vault://` scheme.
- Metadata-backed document/page/source content rendering.
- Graph-entity resource rendering through graph retrieval services.
- Generated context-pack resource cache for `vault://context/packs/{pack_id}`.
- Resource errors and warnings with recovery hints.
- Resource tests for read-only and multi-vault behavior.

## 3. Out Of Scope

- Resource subscriptions and list-changed notifications.
- Full listing of every Vault document by default.
- Durable context-pack persistence.
- Editing, renaming, deleting, or publishing Vault files.
- Binary resources.
- Remote HTTP resources.

## 4. Resource URI Contract

Phase 5B supports these resource templates:

```text
vault://{vault_id}/documents/{path}
vault://{vault_id}/pages/{path}
vault://{vault_id}/sources/{id}
vault://{vault_id}/decisions/{id}
vault://{vault_id}/issues/{id}
vault://{vault_id}/timeline/recent
vault://{vault_id}/context/current
vault://{vault_id}/graph/entities/{id}
vault://context/packs/{pack_id}
```

Rules:

- Every Vault-derived URI includes `vault_id`.
- `vault://context/packs/{pack_id}` is generated and not tied to one Vault in
  the URI because the pack body records its requested and actual scopes.
- Path-like values are Vault-relative logical paths, never absolute filesystem
  paths.
- URI parsing must reject unknown schemes, unknown resource kinds, missing
  Vault IDs, unknown Vault IDs, disabled Vaults, absolute paths, `..`, encoded
  traversal, and empty IDs.
- Resource output must include the normalized URI it resolved.

## 5. Resource Package Additions

Phase 5B extends the MCP package:

```text
src/vault_graph/mcp/
├── mcp_resources.py
├── mcp_uri.py
├── metadata_resource_reader.py
├── graph_resource_reader.py
└── context_pack_resource_cache.py
```

Public contracts:

```python
@dataclass(frozen=True)
class McpResourceRequest:
    uri: str

@dataclass(frozen=True)
class McpResourceBody:
    uri: str
    mime_type: str
    text: str
    metadata: dict[str, object]
    warnings: tuple[McpErrorPayload, ...]

class McpResourceRegistry:
    def list_templates(self) -> tuple[object, ...]: ...
    def read(self, request: McpResourceRequest) -> McpResourceBody: ...
```

`object` in `list_templates` stands for the MCP SDK resource-template type used
by the implementation.

## 6. Metadata Resource Reader

Metadata-backed resources should render from indexed metadata, not from direct
filesystem reads, so resource output is consistent with search and context-pack
evidence.

Recommended store contract extension:

```python
class MetadataStore(Protocol):
    def list_document_chunks(
        self,
        *,
        vault_id: str,
        document_id: str,
    ) -> tuple[ChunkSnapshot, ...]: ...
```

Resource flow:

```text
vault://main/documents/wiki/spec.md
  -> validate URI and Vault ID
  -> MetadataStore.document_state(vault_id, path)
  -> MetadataStore.resolve_document(document_id)
  -> MetadataStore.list_document_chunks(vault_id, document_id)
  -> render chunks in document order
  -> include evidence metadata, hashes, revisions, and warnings
```

If the implementation plan avoids the interface extension for Phase 5B, it may
filter `MetadataStore.list_chunks(scope)` by `document_id` as a temporary local
path, but the plan must record this as a bounded MVP trade-off and add the
target store method before scale-up adapters.

## 7. Resource Rendering

MIME types:

- Markdown-like document/page/source/decision/issue resources:
  `text/markdown`
- JSON-like timeline/current context/graph entity/context pack resources:
  `application/json`

Document rendering:

- Preserve headings and chunk order from indexed chunks.
- Include a small metadata header in JSON metadata, not by injecting new facts
  into Markdown text.
- Do not include hidden prompt instructions inside resource content.
- Attach warnings for stale metadata, missing chunks, tombstoned documents, or
  unavailable backend state.

Graph entity rendering:

- Resolve through graph services and evidence refs.
- Include relationship status labels: `stated`, `inferred`, `contested`, or
  `deprecated`.
- Include evidence Vault IDs for cross-Vault relationships.
- Return a structured warning when graph state is unavailable or stale.

Current context and timeline resources:

- Phase 5B may expose `vault://{vault_id}/context/current` and
  `vault://{vault_id}/timeline/recent` only if backed by existing indexed
  metadata and status. Rich memory projections remain Phase 6.
- If Phase 6 services do not exist, these resources return a clear
  `resource_not_available` error rather than inventing summaries.

## 8. Context Pack Resource Cache

Phase 4 intentionally avoided durable pack persistence. Phase 5B keeps that
choice.

```python
@dataclass(frozen=True)
class CachedContextPack:
    pack_id: str
    pack_json: str
    generated_at: str
    requested_scope_key: str
    actual_scope_keys: tuple[str, ...]

class ContextPackResourceCache:
    def put(self, pack: ContextPack, *, rendered_json: str) -> str: ...
    def get(self, pack_id: str) -> CachedContextPack | None: ...
```

Cache policy:

- In-process only.
- Bounded by count, default `32` packs.
- Evicts least-recently-used packs.
- Does not write to Vault Graph state.
- Does not change `ContextPack` JSON schema.
- Missing cache entries return not found with recovery hint:
  call `build_context_pack` again.

The `build_context_pack` MCP tool in Phase 5C should return both structured pack
JSON and a resource link to `vault://context/packs/{pack_id}` after placing the
pack in this cache.

## 9. Resource Listing Policy

Do not list every indexed document by default. A large Vault could produce
thousands of resources and make discovery slow.

Phase 5B should:

- expose resource templates
- optionally list a small set of high-value generated resources, such as the
  current active Vault context resource if available
- let tools return resource links for precise follow-up reads

## 10. Error And Warning Policy

Resource errors:

- `invalid_resource_uri`
- `unknown_vault_id`
- `vault_disabled`
- `resource_not_found`
- `resource_not_available`
- `metadata_unavailable`
- `graph_unavailable`
- `stale_index`
- `missing_evidence`

Warnings are returned in resource metadata and, when the MCP SDK supports it,
as structured annotations. Do not hide warnings in Markdown prose only.

## 11. Tests Required Before Implementation

Phase 5B implementation must include tests for:

- each resource template is registered with the expected URI pattern.
- URI parser rejects absolute paths, `..`, encoded traversal, unknown schemes,
  and unknown Vault IDs.
- document/page/source resources read indexed metadata only and preserve
  `vault_id`, path, content hash, and revision metadata.
- same relative path in two Vaults resolves to different resources.
- tombstoned or missing documents do not render as fresh resources.
- graph entity resources require graph state and preserve relationship evidence
  Vault IDs.
- generated context pack resources are available after `build_context_pack` and
  disappear with a clear not-found error after cache eviction or restart.
- reading resources does not create metadata/vector/graph/cache files.
- no resource handler writes to registered Vault roots.

## 12. Handoff To Phase 5C

Phase 5C tools should return resource links created by Phase 5B where useful.
For example, `build_context_pack` returns `vault://context/packs/{pack_id}`, and
graph tools may return `vault://{vault_id}/graph/entities/{id}` links.
