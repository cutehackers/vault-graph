# Phase 5A MCP Server Foundation And Stdio Design

Status: Draft for implementation planning

Date: 2026-06-15

Scope: Phase 5A

## 1. Purpose

Phase 5A creates the local MCP server boundary and starts it through
`vg serve --mcp`. This slice should prove that agents can connect to Vault Graph
without giving the MCP adapter direct ownership of retrieval, graph, indexing,
or context-pack behavior.

Phase 5A is intentionally small. It creates the server package, dependency,
configuration, read-only service factory, capability registration, error
mapping, and local client configuration examples. Resource contents, production
tools, and prompts are added in Phase 5B and Phase 5C.

## 2. In Scope

- Add MCP Python SDK dependency.
- Add `vault_graph.mcp` as the MCP adapter package.
- Add `vg serve --mcp`.
- Use stdio as the only Phase 5A transport.
- Build read-only application service dependencies from the configured state
  path.
- Register MCP server metadata and capability skeleton.
- Map Vault Graph domain errors into MCP-safe errors.
- Add Codex-compatible local configuration examples.
- Add tests that prove no Vault writes and no import-time backend work.

## 3. Out Of Scope

- Streamable HTTP transport.
- Authentication and remote hosting.
- Resource subscriptions.
- Durable context-pack persistence.
- `ask_vault` answer synthesis.
- Phase 6 memory projections.
- Indexing from MCP.
- MCP tools that mutate Vault Graph derived state.

## 4. Proposed Package Boundary

Phase 5 should add a dedicated MCP adapter package:

```text
src/vault_graph/mcp/
├── __init__.py
├── mcp_server.py
├── mcp_service_factory.py
├── mcp_scope.py
├── mcp_errors.py
└── mcp_config_examples.py
```

This keeps the adapter separate from `vault_graph.app`, which owns application
services, and separate from `vault_graph.cli`, which owns command-line parsing.

Phase 5A public entry points:

```python
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Protocol

McpTransport = Literal["stdio"]

@dataclass(frozen=True)
class McpServerConfig:
    state_path: Path
    transport: McpTransport = "stdio"
    server_name: str = "vault-graph"
    server_version: str = "0.1.0"

class McpServer(Protocol):
    ...

def create_mcp_server(config: McpServerConfig) -> McpServer: ...

async def serve_mcp(config: McpServerConfig) -> None: ...
```

`McpServer` is a local protocol used to keep the design independent from the
SDK's concrete server class name. The implementation plan should bind it to the
official SDK type available at implementation time.

## 5. CLI Surface

Phase 5A adds:

```bash
vg serve --mcp
vg serve --mcp --state .vault-graph
```

Rules:

- `--mcp` starts stdio transport.
- The command must not print human-readable startup text to stdout.
- Human-readable logs and startup diagnostics go to stderr.
- Configuration errors exit nonzero before the MCP event loop starts.
- The command uses read-only store construction. It must not initialize missing
  stores or create derived state.

If `vg serve --http` is already accepted by the CLI parser, it remains a future
option and must not start a partially designed HTTP server in Phase 5A.

## 6. Service Factory

Add `McpServiceFactory` as the deep boundary between MCP registration and
application services.

```python
@dataclass(frozen=True)
class McpServices:
    catalog: VaultCatalog
    metadata_store: MetadataStore
    retrieval_service: RetrievalService
    graph_retrieval_service: GraphRetrievalService | None
    context_pack_builder: ContextPackBuilder
    context_pack_renderer: ContextPackRenderer
    status_service: object

class McpServiceFactory:
    def __init__(self, *, state_path: Path) -> None: ...

    def open_read_only(self) -> McpServices: ...
```

Factory rules:

- Load `VaultCatalog` through `CatalogService`.
- Open `SQLiteMetadataStore` read-only.
- Open `ChromaVectorStore` read-only.
- Use search embeddings with `local_files_only=True`.
- Open graph services lazily only for graph tools/resources.
- Do not initialize metadata, vector, graph, cache, or model state.
- Do not run indexing or dry-run planning.
- Do not import rustworkx at package import time.

The factory may live in the MCP package even though it currently references
local adapters, because it is an outer adapter composition point. Domain
services and context builders must still depend on interfaces.

## 7. Scope Input DTO

MCP tools need JSON arguments. Phase 5A defines one scope input shape reused by
Phase 5B and Phase 5C:

```python
@dataclass(frozen=True)
class McpScopeInput:
    vault_ids: tuple[str, ...] | None = None
    all_vaults: bool = False
    content_scopes: tuple[str, ...] | None = None
    include_cross_vault: bool = False
```

Mapping rules:

- `None` maps to `catalog.default_scope()`.
- `all_vaults=true` maps to `catalog.scope_for_all_enabled()`.
- `vault_ids` maps to `catalog.scope_for_vault_ids(...)`.
- `all_vaults` and `vault_ids` are mutually exclusive.
- Unknown or disabled Vault IDs are invalid arguments.
- `content_scopes` may narrow the selected Vault scope but must not widen a
  Vault beyond its configured enabled content scopes.
- `include_cross_vault` is allowed only for explicit graph behavior.

## 8. Error Mapping

Add a small error payload used by tools and resources:

```python
@dataclass(frozen=True)
class McpErrorPayload:
    code: str
    message: str
    severity: str
    affected_vault_ids: tuple[str, ...]
    recovery_hint: str | None = None
```

Mapping policy:

- `CatalogError`, invalid scope, invalid resource URI, and invalid tool
  arguments map to invalid-parameter errors.
- Missing resources map to not-found errors.
- Backend health and schema compatibility failures map to structured execution
  errors when a tool/resource can still return an MCP result.
- Unexpected exceptions map to internal errors without exposing local absolute
  paths unless the path is already an explicit user-provided state path.

All errors that can be represented as Vault Graph warnings should preserve the
original warning code in structured output.

## 9. Capability Registration

Phase 5A registers the server with:

- resources capability present but no broad resource listing
- tools capability present with at most `check_index_status` smoke coverage if
  the implementation plan chooses a minimal tool
- prompts capability present only after Phase 5C

If the SDK requires explicit functions at server creation time, register empty
capability skeletons only where the SDK supports them safely. Otherwise, defer
capability registration until each slice adds concrete handlers. Do not list
tools or prompts that are not actually callable.

## 10. Codex-Compatible Local Config Examples

Add documentation examples under the Phase 5 docs or root docs, not under Vault:

```json
{
  "mcpServers": {
    "vault-graph": {
      "command": "uv",
      "args": [
        "run",
        "--python",
        "3.12",
        "vg",
        "serve",
        "--mcp",
        "--state",
        "/path/to/.vault-graph"
      ]
    }
  }
}
```

Rules:

- Use example paths in durable docs.
- Do not document the user's real home directory.
- Keep examples local stdio only in Phase 5A.
- Do not include OAuth, API keys, or remote server examples.

## 11. Security And Read-Only Requirements

- The stdio server writes only MCP protocol messages to stdout.
- The server never executes shell commands from MCP arguments.
- The server accepts only configured state path and structured tool arguments.
- The server never accepts a raw filesystem root from a tool call.
- All store reads are scoped through `VaultCatalog` and `QueryScope`.
- Path and URI parsing must reject absolute paths, `..`, encoded traversal, and
  unknown URI schemes.
- MCP startup must not create metadata, vector, graph, projection, model cache,
  or Vault files.

## 12. Tests Required Before Implementation

Phase 5A implementation must include tests for:

- `vg serve --mcp --help` exposes the command without starting the server.
- invalid `--state` or missing catalog exits before stdio server startup.
- server construction loads catalog and opens stores read-only.
- startup does not create metadata, vector, graph, cache, or Vault files.
- package import does not import rustworkx, Chroma runtime clients, or open
  stores eagerly.
- stdio command path does not write non-protocol startup text to stdout.
- `McpScopeInput` rejects ambiguous or unknown Vault scope.
- error mapping preserves domain warning/error codes.
- Codex config examples contain example paths, not user-local real paths.

## 13. Handoff To Phase 5B

Phase 5B may add resources only after Phase 5A proves that MCP server startup is
local, read-only, and adapter-only. Resource handlers should use the Phase 5A
service factory and scope parser rather than opening their own stores.
