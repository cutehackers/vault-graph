# Phase 5A MCP Server Foundation And Stdio Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a local read-only MCP stdio foundation so agents can connect to Vault Graph through `vg serve --mcp` without giving MCP ownership of retrieval, graph, indexing, or context-pack behavior.

**Architecture:** Create `vault_graph.mcp` as a thin outer adapter around existing application services. The adapter constructs read-only dependencies from the configured Vault Graph state path, creates a FastMCP stdio server, and exposes only lifecycle/capability readiness in Phase 5A; concrete resources, tools, and prompts are added in Phase 5B/5C.

**Tech Stack:** Python 3.12, Typer CLI, official MCP Python SDK v1 (`mcp>=1.27,<2`), FastMCP stdio transport, frozen dataclasses, existing SQLite/Chroma/FastEmbed read-only constructors, pytest, ruff, mypy.

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

Implementation must preserve these current repo facts:

- `src/vault_graph/cli/main.py` already owns CLI parsing and has private read-only service helpers.
- `CatalogService` owns state-path layout and Vault boundary checks.
- `SQLiteMetadataStore(path, initialize=False)` opens SQLite with `mode=ro` and does not create missing state.
- `ChromaVectorStore(path, initialize=False, read_only=True)` avoids creating missing Chroma state.
- `FastEmbedTextEmbeddingsConfig(local_files_only=True, embedding_lazy_load=True)` avoids first-use model download during read-only search construction.
- `RustworkxGraphProjection` must remain lazily imported only for explicit graph behavior.
- `docs/DECISIONS.md` records accepted decisions only; no new user decision is required for this slice.

## Scope

Phase 5A implements:

- `mcp>=1.27,<2` dependency and updated `uv.lock`
- `src/vault_graph/mcp/` package
- FastMCP server construction for local stdio only
- `vg serve --mcp`
- read-only MCP service factory over existing catalog, metadata, keyword, vector, retrieval, and context-pack services
- shared MCP scope input DTO for later resources/tools
- shared MCP-safe error payload and exception mapping
- Codex-compatible local stdio configuration example
- tests for CLI surface, read-only startup, import boundaries, scope validation, error mapping, and config examples

Phase 5A does not implement:

- Streamable HTTP, SSE, authentication, remote hosting, or network binding
- MCP resources, resource templates, subscriptions, or context-pack resource cache
- MCP tools such as `search_vault`, `build_context_pack`, `find_related`, `get_decision_trace`, or `check_index_status`
- MCP prompts
- `ask_vault`, answer synthesis, memory projections, or autonomous Vault publication
- indexing or derived-state mutation from MCP

## Directory And File Structure

Create:

- `src/vault_graph/mcp/__init__.py`: lazy public exports for MCP DTOs and entry points.
- `src/vault_graph/mcp/mcp_server.py`: `McpServerConfig`, FastMCP construction, and stdio serving.
- `src/vault_graph/mcp/mcp_service_factory.py`: read-only application service composition for MCP handlers.
- `src/vault_graph/mcp/mcp_scope.py`: JSON scope input DTO and mapping to `QueryScope`.
- `src/vault_graph/mcp/mcp_errors.py`: MCP-safe error payloads and domain error mapping.
- `src/vault_graph/mcp/mcp_config_examples.py`: durable local stdio client configuration examples.
- `tests/test_mcp_scope.py`
- `tests/test_mcp_errors.py`
- `tests/test_mcp_service_factory.py`
- `tests/test_mcp_import_boundaries.py`
- `tests/test_cli_mcp_serve.py`
- `tests/test_mcp_config_examples.py`
- `docs/superpowers/specs/phase-5/codex-local-stdio-config.example.json`

Modify:

- `pyproject.toml`: add `mcp>=1.27,<2` to project dependencies.
- `uv.lock`: refresh with `uv lock --python 3.12`.
- `src/vault_graph/cli/main.py`: add `serve` command and stderr-oriented domain error helper for server startup.
- `tests/test_cli_surface_boundary.py`: assert the root CLI exposes `serve` and still does not expose `ask`.
- `docs/superpowers/specs/phase-5/README.md`: link the new Codex config example.

Do not modify:

- registered Vault roots or Vault files
- storage interface contracts
- retrieval ranking, graph traversal, context-pack assembly, or index reconciliation logic
- `docs/DECISIONS.md`
- `docs/PATCH_LOG.md` unless implementation review finds a concrete correction to this plan or an existing docs mismatch

## Component And Interface Spec

### `pyproject.toml`

Add the SDK dependency with a v2 guard because official MCP Python SDK v2 is alpha while v1 is the current stable line. Do not use the `mcp[cli]` extra for runtime Phase 5A; it widens the dependency surface beyond the stdio server requirement.

```toml
dependencies = [
  "PyYAML>=6.0.2",
  "chromadb>=1.5.9,<2.0",
  "fastembed>=0.8.0,<1.0",
  "huggingface-hub>=0.31,<1.0",
  "mcp>=1.27,<2",
  "rustworkx>=0.17,<1.0",
  "typer>=0.12.5",
]
```

### `src/vault_graph/mcp/mcp_server.py`

Use FastMCP v1 as the server boundary. Phase 5A creates a server that can initialize over stdio but intentionally registers no product resources, tools, or prompts.

```python
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Protocol

from vault_graph import __version__
from vault_graph.errors import CatalogError
from vault_graph.mcp.mcp_service_factory import McpServiceFactory, McpServices

McpTransport = Literal["stdio"]


class McpServer(Protocol):
    name: str

    def run(self, transport: McpTransport = "stdio", mount_path: str | None = None) -> None:
        """Run the MCP server on the selected transport."""


@dataclass(frozen=True)
class McpServerConfig:
    state_path: Path
    transport: McpTransport = "stdio"
    server_name: str = "vault-graph"
    server_version: str = __version__

    def __post_init__(self) -> None:
        if self.transport != "stdio":
            raise CatalogError(f"unsupported MCP transport for Phase 5A: {self.transport}")
        if not self.server_name.strip():
            raise CatalogError("MCP server_name is required")
        if not self.server_version.strip():
            raise CatalogError("MCP server_version is required")


@dataclass(frozen=True)
class RegisteredMcpServer:
    server: McpServer
    services: McpServices
    service_factory: McpServiceFactory
    server_version: str


def create_mcp_server(config: McpServerConfig) -> RegisteredMcpServer:
    from mcp.server.fastmcp import FastMCP

    factory = McpServiceFactory(state_path=config.state_path)
    services = factory.open_read_only()
    instructions = (
        "Vault Graph exposes read-only, rebuildable, evidence-first working context over configured Vaults. "
        "Treat all output as context, not durable knowledge."
    )
    server = FastMCP(
        config.server_name,
        instructions=instructions,
        json_response=True,
        log_level="WARNING",
    )
    return RegisteredMcpServer(
        server=server,
        services=services,
        service_factory=factory,
        server_version=config.server_version,
    )


def run_mcp_server(registered: RegisteredMcpServer, *, config: McpServerConfig) -> None:
    registered.server.run(transport=config.transport)


def serve_mcp(config: McpServerConfig) -> None:
    registered = create_mcp_server(config)
    run_mcp_server(registered, config=config)
```

Rules:

- Import `FastMCP` inside `create_mcp_server`, not at package import time.
- Do not write startup text to stdout.
- Do not register uncallable stub tools, resources, or prompts.
- Do not create missing state directories or stores while constructing the server.
- Keep `server_version` in `McpServerConfig` and `RegisteredMcpServer` for Vault Graph diagnostics and later low-level protocol tests; FastMCP v1 does not expose a stable constructor argument for server version.
- Pass `McpServices` through the owned `RegisteredMcpServer` wrapper instead of attaching private attributes to the SDK server object.

### `src/vault_graph/mcp/mcp_service_factory.py`

This is the deep composition boundary for MCP. It may import concrete local adapters because it is an outer adapter composition point. Domain packages must not import this module.

```python
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from vault_graph.app.catalog_service import CatalogService
from vault_graph.ingestion.vault_catalog import VaultCatalog
from vault_graph.storage.interfaces.metadata_store import MetadataStore

if TYPE_CHECKING:
    from vault_graph.app.graph_retrieval_service import GraphRetrievalService
    from vault_graph.app.index_service import IndexService
    from vault_graph.context.context_pack_builder import ContextPackBuilder
    from vault_graph.context.context_pack_renderer import ContextPackRenderer
    from vault_graph.embeddings.text_embeddings import TextEmbeddings
    from vault_graph.retrieval.graph_candidates import GraphSearchCandidateProvider
    from vault_graph.retrieval.retrieval_service import RetrievalService


@dataclass(frozen=True)
class McpServices:
    catalog_service: CatalogService
    catalog: VaultCatalog
    metadata_store: MetadataStore
    retrieval_service: RetrievalService
    context_pack_builder: ContextPackBuilder
    context_pack_renderer: ContextPackRenderer


class McpServiceFactory:
    def __init__(self, *, state_path: Path) -> None:
        self._state_path = state_path

    def open_read_only(self) -> McpServices:
        from vault_graph.app.search_readiness_service import ReadOnlySearchReadiness
        from vault_graph.context.context_pack_builder import MetadataContextEvidenceResolver, SearchContextPackBuilder
        from vault_graph.context.context_pack_renderer import DefaultContextPackRenderer
        from vault_graph.retrieval.retrieval_service import RetrievalService
        from vault_graph.storage.local.chroma_vector_store import ChromaVectorStore
        from vault_graph.storage.local.sqlite_keyword_index import SQLiteKeywordIndex
        from vault_graph.storage.local.sqlite_metadata_store import SQLiteMetadataStore

        catalog_service, catalog = self._catalog()
        metadata_store = SQLiteMetadataStore(catalog_service.metadata_path, initialize=False)
        keyword_index = SQLiteKeywordIndex(catalog_service.metadata_path)
        vector_store = ChromaVectorStore(catalog_service.vector_path, initialize=False, read_only=True)
        text_embeddings = self._search_text_embeddings(catalog_service)
        retrieval_service = RetrievalService(
            catalog=catalog,
            metadata_store=metadata_store,
            keyword_index=keyword_index,
            vector_store=vector_store,
            text_embeddings=text_embeddings,
            readiness=ReadOnlySearchReadiness(
                metadata_store=metadata_store,
                keyword_index=keyword_index,
                vector_store=vector_store,
                text_embeddings=text_embeddings,
            ),
        )
        return McpServices(
            catalog_service=catalog_service,
            catalog=catalog,
            metadata_store=metadata_store,
            retrieval_service=retrieval_service,
            context_pack_builder=SearchContextPackBuilder(
                catalog=catalog,
                retrieval_service=retrieval_service,
                evidence_resolver=MetadataContextEvidenceResolver(metadata_store=metadata_store),
            ),
            context_pack_renderer=DefaultContextPackRenderer(),
        )

    def open_status_service(self) -> IndexService:
        from vault_graph.app.graph_readiness_service import ReadOnlyGraphReadiness
        from vault_graph.app.index_service import IndexService
        from vault_graph.graph.graph_contracts import current_graph_extraction_spec
        from vault_graph.storage.local.chroma_vector_store import ChromaVectorStore
        from vault_graph.storage.local.graph_status_store import LocalGraphStatusStore
        from vault_graph.storage.local.sqlite_graph_store import SQLiteGraphStore
        from vault_graph.storage.local.sqlite_metadata_store import SQLiteMetadataStore
        from vault_graph.storage.local.vector_status_store import LocalVectorStatusStore

        catalog_service, catalog = self._catalog()
        metadata_store = SQLiteMetadataStore(catalog_service.metadata_path, initialize=False)
        graph_store = SQLiteGraphStore.open_read_only(catalog_service.graph_path)
        text_embeddings = self._search_text_embeddings(catalog_service)
        return IndexService(
            catalog=catalog,
            metadata_store=metadata_store,
            vector_store=ChromaVectorStore(catalog_service.vector_path, initialize=False, read_only=True),
            text_embeddings=text_embeddings,
            vector_status_store=LocalVectorStatusStore(catalog_service.vector_status_path),
            embedding_batch_size=text_embeddings.config.embedding_batch_size,
            embedding_parallelism=text_embeddings.config.embedding_parallelism,
            embedding_lazy_load=text_embeddings.config.embedding_lazy_load,
            graph_store=graph_store,
            graph_extraction_spec=current_graph_extraction_spec(),
            graph_status_store=LocalGraphStatusStore(catalog_service.graph_status_path),
            graph_readiness=ReadOnlyGraphReadiness(
                metadata_store=metadata_store,
                graph_store=graph_store,
                expected_spec=current_graph_extraction_spec(),
            ),
        )

    def open_graph_retrieval_service(self) -> GraphRetrievalService:
        from vault_graph.app.graph_readiness_service import ReadOnlyGraphReadiness
        from vault_graph.app.graph_retrieval_service import GraphRetrievalService
        from vault_graph.graph.graph_contracts import current_graph_extraction_spec
        from vault_graph.projection.rustworkx_projection import RustworkxGraphProjection
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
        return GraphRetrievalService(
            catalog=catalog,
            metadata_store=metadata_store,
            graph_store=graph_store,
            graph_readiness=readiness,
            projection=RustworkxGraphProjection(),
        )

    def open_graph_search_candidate_provider(self) -> GraphSearchCandidateProvider:
        from vault_graph.retrieval.graph_candidates import GraphSearchCandidateProvider

        return GraphSearchCandidateProvider(graph_retrieval_service=self.open_graph_retrieval_service())

    def _catalog(self) -> tuple[CatalogService, VaultCatalog]:
        config = CatalogService(state_path=self._state_path)
        catalog = config.load_catalog()
        return config, catalog

    def _search_text_embeddings(self, catalog_service: CatalogService) -> TextEmbeddings:
        from vault_graph.embeddings.fastembed_text_embeddings import FastEmbedTextEmbeddings, FastEmbedTextEmbeddingsConfig

        return FastEmbedTextEmbeddings(
            config=FastEmbedTextEmbeddingsConfig(
                cache_dir=catalog_service.embedding_cache_path,
                local_files_only=True,
            )
        )
```

Rules:

- `open_read_only()` must not call `open_status_service()` or `open_graph_retrieval_service()`.
- `open_graph_retrieval_service()` is the only Phase 5A function that imports `RustworkxGraphProjection`.
- `mcp_service_factory.py` module import must not import `RetrievalService`, `IndexService`, context-pack builder implementations, graph service classes, graph status stores, `ChromaVectorStore`, `FastEmbedTextEmbeddings`, `chromadb`, `fastembed`, `huggingface_hub`, `rustworkx`, or local graph projection adapters.
- `McpServiceFactory` must not call `IndexService.run_plan()`, `IndexService.run_apply()`, `ContextPackBuilder.build()`, or `RetrievalService.search()` during startup.
- `McpServiceFactory` may duplicate current CLI composition in Phase 5A. Do not refactor CLI helpers into a shared application factory until a later task proves the duplication is harmful.

### `src/vault_graph/mcp/mcp_scope.py`

```python
from __future__ import annotations

from dataclasses import dataclass

from vault_graph.errors import CatalogError
from vault_graph.ingestion.query_scope_resolution import actual_query_scopes
from vault_graph.ingestion.vault_catalog import QueryScope, VaultCatalog, VaultCatalogEntry


@dataclass(frozen=True)
class McpScopeInput:
    vault_ids: tuple[str, ...] | None = None
    all_vaults: bool = False
    content_scopes: tuple[str, ...] | None = None
    include_cross_vault: bool = False


def scope_from_mcp_input(
    scope_input: McpScopeInput | None,
    *,
    catalog: VaultCatalog,
    allow_graph_cross_vault: bool = False,
) -> QueryScope:
    if scope_input is None:
        base_scope = catalog.default_scope()
        selected_entries = tuple(catalog.resolve(vault_id) for vault_id in base_scope.vault_ids)
        _reject_disabled_entries(selected_entries)
        return base_scope
    if scope_input.all_vaults and scope_input.vault_ids:
        raise CatalogError("Use either all_vaults or vault_ids, not both.")
    if scope_input.all_vaults:
        base_scope = catalog.scope_for_all_enabled()
    elif scope_input.vault_ids:
        selected_entries = tuple(catalog.resolve(vault_id) for vault_id in scope_input.vault_ids)
        _reject_disabled_entries(selected_entries)
        base_scope = catalog.scope_for_vault_ids(scope_input.vault_ids)
    else:
        base_scope = catalog.default_scope()
        selected_entries = tuple(catalog.resolve(vault_id) for vault_id in base_scope.vault_ids)
        _reject_disabled_entries(selected_entries)
    if scope_input.include_cross_vault and not allow_graph_cross_vault:
        raise CatalogError("include_cross_vault is allowed only for explicit graph behavior")
    content_scopes = base_scope.content_scopes
    if scope_input.content_scopes is not None:
        narrowed_scope = QueryScope(
            vault_ids=base_scope.vault_ids,
            content_scopes=scope_input.content_scopes,
            include_cross_vault=scope_input.include_cross_vault,
        )
        _validate_content_scope_narrowing(catalog=catalog, requested_scope=narrowed_scope)
        content_scopes = scope_input.content_scopes
    return QueryScope(
        vault_ids=base_scope.vault_ids,
        content_scopes=content_scopes,
        include_cross_vault=scope_input.include_cross_vault,
    )


def _reject_disabled_entries(entries: tuple[VaultCatalogEntry, ...]) -> None:
    for entry in entries:
        if not entry.enabled:
            raise CatalogError(f"disabled vault_id: {entry.vault_id}")


def _validate_content_scope_narrowing(*, catalog: VaultCatalog, requested_scope: QueryScope) -> None:
    if not requested_scope.content_scopes:
        raise CatalogError("content_scopes cannot be empty")
    actual_by_vault = {
        actual_scope.vault_ids[0]: actual_scope
        for actual_scope in actual_query_scopes(catalog=catalog, scope=requested_scope)
    }
    for vault_id in requested_scope.vault_ids:
        actual_scope = actual_by_vault.get(vault_id)
        if actual_scope is None or actual_scope.content_scopes != requested_scope.content_scopes:
            requested = ", ".join(requested_scope.content_scopes)
            raise CatalogError(f"content scope {requested} is not enabled for vault_id: {vault_id}")
```

Mapping rules:

- `None` uses the active Vault.
- `all_vaults=True` expands to enabled Vault IDs only.
- `vault_ids` rejects unknown or disabled Vault IDs.
- `all_vaults` and `vault_ids` are mutually exclusive.
- `content_scopes` narrows only when each selected Vault enables that scope, using the existing `actual_query_scopes(...)` helper as the authority for scope compatibility.
- `include_cross_vault=True` requires `allow_graph_cross_vault=True`.

### `src/vault_graph/mcp/mcp_errors.py`

```python
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from vault_graph.errors import (
    CatalogError,
    ContextPackError,
    GraphStoreError,
    KeywordIndexError,
    ReadOnlyBoundaryError,
    SearchError,
    TextEmbeddingsError,
    VaultGraphError,
    VectorStoreError,
)

McpErrorSeverity = Literal["info", "warning", "error"]
McpProtocolErrorKind = Literal["invalid_parameter", "not_found", "execution", "internal"]
ABSOLUTE_PATH_RE = re.compile(r"(?P<path>(?:/[^\s:;,)\]]+)+|[A-Za-z]:\\[^\s:;,)\]]+)")


@dataclass(frozen=True)
class McpErrorPayload:
    code: str
    message: str
    severity: McpErrorSeverity
    affected_vault_ids: tuple[str, ...]
    recovery_hint: str | None = None


class McpProtocolError(Exception):
    def __init__(self, *, kind: McpProtocolErrorKind, payload: McpErrorPayload) -> None:
        super().__init__(payload.message)
        self.kind = kind
        self.payload = payload


def map_exception_to_mcp_error(
    exc: Exception,
    *,
    affected_vault_ids: tuple[str, ...] = (),
    user_state_path: Path | None = None,
) -> McpProtocolError:
    if isinstance(exc, CatalogError):
        return _error(
            "invalid_parameter",
            "catalog_error",
            _sanitize_error_message(str(exc), user_state_path=user_state_path),
            affected_vault_ids,
        )
    if isinstance(exc, ReadOnlyBoundaryError):
        return _error(
            "execution",
            "read_only_boundary_error",
            _sanitize_error_message(str(exc), user_state_path=user_state_path),
            affected_vault_ids,
        )
    if isinstance(exc, (KeywordIndexError, VectorStoreError, GraphStoreError, TextEmbeddingsError)):
        return _error(
            "execution",
            _code_for_domain_error(exc),
            _sanitize_error_message(str(exc), user_state_path=user_state_path),
            affected_vault_ids,
        )
    if isinstance(exc, (SearchError, ContextPackError)):
        return _error(
            "execution",
            _code_for_domain_error(exc),
            _sanitize_error_message(str(exc), user_state_path=user_state_path),
            affected_vault_ids,
        )
    if isinstance(exc, VaultGraphError):
        return _error(
            "execution",
            _code_for_domain_error(exc),
            _sanitize_error_message(str(exc), user_state_path=user_state_path),
            affected_vault_ids,
        )
    return _error(
        "internal",
        "internal_error",
        _sanitize_internal_message(exc, user_state_path=user_state_path),
        affected_vault_ids,
        recovery_hint="Check stderr logs and rerun the command with the same --state path.",
    )


def _error(
    kind: McpProtocolErrorKind,
    code: str,
    message: str,
    affected_vault_ids: tuple[str, ...],
    recovery_hint: str | None = None,
) -> McpProtocolError:
    return McpProtocolError(
        kind=kind,
        payload=McpErrorPayload(
            code=code,
            message=message,
            severity="error",
            affected_vault_ids=affected_vault_ids,
            recovery_hint=recovery_hint,
        ),
    )


def _code_for_domain_error(exc: Exception) -> str:
    name = exc.__class__.__name__
    chars: list[str] = []
    for index, char in enumerate(name):
        if char.isupper() and index > 0:
            chars.append("_")
        chars.append(char.lower())
    return "".join(chars)


def _sanitize_internal_message(exc: Exception, *, user_state_path: Path | None) -> str:
    text = str(exc)
    sanitized = _sanitize_error_message(text, user_state_path=user_state_path)
    return sanitized if sanitized != text else "unexpected MCP server error"


def _sanitize_error_message(message: str, *, user_state_path: Path | None) -> str:
    allowed_state = str(user_state_path.expanduser().resolve()) if user_state_path is not None else None

    def replace(match: re.Match[str]) -> str:
        path = match.group("path")
        if allowed_state is not None and (path == allowed_state or path.startswith(f"{allowed_state}/")):
            return path
        return "<redacted-path>"

    return ABSOLUTE_PATH_RE.sub(replace, message)
```

Rules:

- Domain validation errors map to invalid parameters or structured execution errors.
- Domain and internal error messages must redact arbitrary absolute paths.
- A user-provided `--state` path may appear in diagnostics because the user explicitly provided it; unrelated absolute paths in the same message must still be redacted.
- Error payloads are the structured contract used by Phase 5B resources and Phase 5C tools.
- Phase 5A does not convert warning DTOs because it registers no concrete handlers. Phase 5B and Phase 5C handlers must pass original warning codes into `McpErrorPayload.code` or their structured result warning fields without renaming them.

### `src/vault_graph/mcp/mcp_config_examples.py`

```python
from __future__ import annotations

import json
from typing import TypedDict


class CodexMcpServerConfig(TypedDict):
    command: str
    args: list[str]


class CodexMcpConfig(TypedDict):
    mcpServers: dict[str, CodexMcpServerConfig]


CODEX_STDIO_CONFIG_EXAMPLE: CodexMcpConfig = {
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
                "/path/to/.vault-graph",
            ],
        }
    }
}


def codex_stdio_config_json() -> str:
    return json.dumps(CODEX_STDIO_CONFIG_EXAMPLE, sort_keys=True, indent=2) + "\n"
```

### `src/vault_graph/mcp/__init__.py`

Use lazy exports so `import vault_graph.mcp` does not import the MCP SDK, Chroma, rustworkx, or storage backends.

```python
from __future__ import annotations

from typing import Any

__all__ = [
    "McpErrorPayload",
    "McpProtocolError",
    "McpScopeInput",
    "McpServerConfig",
    "McpServiceFactory",
    "McpServices",
    "RegisteredMcpServer",
    "codex_stdio_config_json",
    "create_mcp_server",
    "map_exception_to_mcp_error",
    "run_mcp_server",
    "scope_from_mcp_input",
    "serve_mcp",
]


def __getattr__(name: str) -> Any:
    if name in {"McpServerConfig", "RegisteredMcpServer", "create_mcp_server", "run_mcp_server", "serve_mcp"}:
        from vault_graph.mcp.mcp_server import (
            McpServerConfig,
            RegisteredMcpServer,
            create_mcp_server,
            run_mcp_server,
            serve_mcp,
        )

        return {
            "McpServerConfig": McpServerConfig,
            "RegisteredMcpServer": RegisteredMcpServer,
            "create_mcp_server": create_mcp_server,
            "run_mcp_server": run_mcp_server,
            "serve_mcp": serve_mcp,
        }[name]
    if name in {"McpServiceFactory", "McpServices"}:
        from vault_graph.mcp.mcp_service_factory import McpServiceFactory, McpServices

        return {"McpServiceFactory": McpServiceFactory, "McpServices": McpServices}[name]
    if name in {"McpScopeInput", "scope_from_mcp_input"}:
        from vault_graph.mcp.mcp_scope import McpScopeInput, scope_from_mcp_input

        return {"McpScopeInput": McpScopeInput, "scope_from_mcp_input": scope_from_mcp_input}[name]
    if name in {"McpErrorPayload", "McpProtocolError", "map_exception_to_mcp_error"}:
        from vault_graph.mcp.mcp_errors import McpErrorPayload, McpProtocolError, map_exception_to_mcp_error

        return {
            "McpErrorPayload": McpErrorPayload,
            "McpProtocolError": McpProtocolError,
            "map_exception_to_mcp_error": map_exception_to_mcp_error,
        }[name]
    if name == "codex_stdio_config_json":
        from vault_graph.mcp.mcp_config_examples import codex_stdio_config_json

        return codex_stdio_config_json
    raise AttributeError(name)


def __dir__() -> list[str]:
    return sorted(__all__)
```

### `src/vault_graph/cli/main.py`

Add a `serve` command. Keep the MCP import inside the command body so ordinary CLI imports and help do not load the MCP SDK.

```python
@app.command()
def serve(
    state: Path = typer.Option(Path(".vault-graph"), "--state", help="Vault Graph state path."),
    mcp: bool = typer.Option(False, "--mcp", help="Start the local stdio MCP server."),
    http: bool = typer.Option(False, "--http", help="Reserved for a future HTTP server."),
) -> None:
    if mcp and http:
        typer.echo("Use either --mcp or --http, not both.", err=True)
        raise typer.Exit(1)
    if http:
        typer.echo("http_transport_not_supported_in_phase_5a", err=True)
        raise typer.Exit(1)
    if not mcp:
        typer.echo("select one server transport: --mcp", err=True)
        raise typer.Exit(1)
    from vault_graph.mcp.mcp_server import McpServerConfig, create_mcp_server, run_mcp_server

    config = _exit_on_domain_error_stderr(lambda: McpServerConfig(state_path=state))
    registered = _exit_on_domain_error_stderr(lambda: create_mcp_server(config))
    _exit_on_domain_error_stderr(lambda: run_mcp_server(registered, config=config))
```

Add this helper near `_exit_on_domain_error`:

```python
def _exit_on_domain_error_stderr[T](operation: Callable[[], T]) -> T:
    try:
        return operation()
    except (
        CatalogError,
        ContextPackError,
        GraphIndexingError,
        GraphStoreError,
        KeywordIndexError,
        ReadOnlyBoundaryError,
        SearchError,
        TextEmbeddingsError,
        VectorStoreError,
    ) as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(1) from exc
```

Rules:

- `vg serve --mcp --help` may print help to stdout.
- `vg serve --mcp` itself must print no human startup text to stdout.
- Startup domain errors go to stderr.
- `vg serve --http` fails explicitly instead of starting a partial HTTP server.

## State Management And Data Flow

Startup flow:

```text
vg serve --mcp --state PATH
  -> parse CLI flags
  -> construct McpServerConfig
  -> create_mcp_server(config)
  -> McpServiceFactory.open_read_only()
  -> CatalogService.load_catalog()
  -> open read-only MetadataStore, KeywordIndex, VectorStore, TextEmbeddings
  -> construct RetrievalService and SearchContextPackBuilder
  -> FastMCP.run(transport="stdio")
```

Runtime state rules:

- Phase 5A does not create metadata, vector, graph, projection, model cache, or context-pack cache state.
- The MCP server keeps service objects in process memory only.
- Missing indexes produce startup failure only if the read-only constructor raises during service creation; missing queryable state remains a Phase 5B/5C handler concern.
- No MCP argument can provide a raw Vault path or arbitrary filesystem root.
- Later handlers must reuse `McpServiceFactory` and `scope_from_mcp_input` instead of opening stores directly.

## Error Handling And Edge Cases

Required behavior:

- Missing catalog at `--state` exits before stdio startup with nonzero exit and stderr message.
- State path inside a registered Vault is rejected by `CatalogService.load_catalog()`.
- Unsupported transport is rejected by `McpServerConfig`.
- `--http` returns `http_transport_not_supported_in_phase_5a`.
- `--mcp --http` returns `Use either --mcp or --http, not both.`
- `McpScopeInput(all_vaults=True, vault_ids=("default",))` raises `CatalogError`.
- `McpScopeInput(vault_ids=("disabled",))` raises `CatalogError`.
- `McpScopeInput(include_cross_vault=True)` raises unless the caller passes `allow_graph_cross_vault=True`.
- Unexpected exceptions map to `internal_error` without leaking arbitrary absolute paths.

## Tasks

### Task 1: Add MCP Dependency And Config Example

**Files:**

- Modify: `pyproject.toml`
- Modify: `uv.lock`
- Create: `docs/superpowers/specs/phase-5/codex-local-stdio-config.example.json`
- Modify: `docs/superpowers/specs/phase-5/README.md`
- Test: `tests/test_mcp_config_examples.py`

- [ ] **Step 1: Write failing config-example tests**

```python
from __future__ import annotations

import json
from pathlib import Path

from vault_graph.mcp.mcp_config_examples import CODEX_STDIO_CONFIG_EXAMPLE, codex_stdio_config_json


def test_codex_stdio_config_example_uses_only_local_stdio() -> None:
    payload = CODEX_STDIO_CONFIG_EXAMPLE
    server = payload["mcpServers"]["vault-graph"]

    assert server["command"] == "uv"
    assert server["args"] == [
        "run",
        "--python",
        "3.12",
        "vg",
        "serve",
        "--mcp",
        "--state",
        "/path/to/.vault-graph",
    ]
    assert "url" not in server
    assert "headers" not in server


def test_codex_stdio_config_json_matches_documented_example() -> None:
    rendered = codex_stdio_config_json()
    parsed = json.loads(rendered)
    docs_example = json.loads(
        Path("docs/superpowers/specs/phase-5/codex-local-stdio-config.example.json").read_text(encoding="utf-8")
    )

    assert parsed == docs_example
    assert str(Path.home()) not in rendered
    assert str(Path.cwd()) not in rendered
    assert "/path/to/.vault-graph" in rendered
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
uv run --python 3.12 pytest tests/test_mcp_config_examples.py -q
```

Expected: FAIL because `vault_graph.mcp.mcp_config_examples` and the JSON example do not exist.

- [ ] **Step 3: Add dependency and config example**

Add `mcp>=1.27,<2` to `pyproject.toml`, then run:

```bash
uv lock --python 3.12
```

Create `src/vault_graph/mcp/__init__.py` with this temporary content:

```python
from __future__ import annotations

__all__: list[str] = []
```

Create `src/vault_graph/mcp/mcp_config_examples.py` using the code in the Component And Interface Spec.

Create `docs/superpowers/specs/phase-5/codex-local-stdio-config.example.json`:

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

Add this row to the Phase 5 README document table:

```markdown
| `codex-local-stdio-config.example.json` | Local Codex MCP stdio configuration example for `vg serve --mcp` |
```

- [ ] **Step 4: Run tests to verify they pass**

Run:

```bash
uv run --python 3.12 pytest tests/test_mcp_config_examples.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml uv.lock src/vault_graph/mcp/__init__.py src/vault_graph/mcp/mcp_config_examples.py docs/superpowers/specs/phase-5/codex-local-stdio-config.example.json docs/superpowers/specs/phase-5/README.md tests/test_mcp_config_examples.py
git commit -m "feat(mcp): add local stdio config example"
```

### Task 2: Add MCP Scope And Error Contracts

**Files:**

- Modify: `src/vault_graph/mcp/__init__.py`
- Create: `src/vault_graph/mcp/mcp_scope.py`
- Create: `src/vault_graph/mcp/mcp_errors.py`
- Test: `tests/test_mcp_scope.py`
- Test: `tests/test_mcp_errors.py`

- [ ] **Step 1: Write failing scope tests**

```python
from __future__ import annotations

from pathlib import Path

import pytest

from vault_graph.errors import CatalogError
from vault_graph.ingestion.vault_catalog import VaultCatalog, VaultCatalogEntry
from vault_graph.mcp.mcp_scope import McpScopeInput, scope_from_mcp_input


def _catalog(tmp_path: Path) -> VaultCatalog:
    first = tmp_path / "first"
    second = tmp_path / "second"
    disabled = tmp_path / "disabled"
    for root in (first, second, disabled):
        root.mkdir()
    return VaultCatalog.from_entries(
        entries=[
            VaultCatalogEntry.from_root(vault_id="default", root_path=first, content_scopes=("wiki", "docs")),
            VaultCatalogEntry.from_root(vault_id="work", root_path=second, content_scopes=("wiki",)),
            VaultCatalogEntry.from_root(vault_id="off", root_path=disabled, enabled=False),
        ],
        active_vault_id="default",
    )


def test_none_scope_uses_active_vault(tmp_path: Path) -> None:
    scope = scope_from_mcp_input(None, catalog=_catalog(tmp_path))

    assert scope.vault_ids == ("default",)
    assert scope.content_scopes == ("wiki", "docs")
    assert scope.include_cross_vault is False


def test_all_vaults_expands_enabled_vaults(tmp_path: Path) -> None:
    scope = scope_from_mcp_input(McpScopeInput(all_vaults=True), catalog=_catalog(tmp_path))

    assert scope.vault_ids == ("default", "work")
    assert scope.include_cross_vault is False


def test_scope_rejects_ambiguous_vault_selection(tmp_path: Path) -> None:
    with pytest.raises(CatalogError, match="either all_vaults or vault_ids"):
        scope_from_mcp_input(McpScopeInput(vault_ids=("default",), all_vaults=True), catalog=_catalog(tmp_path))


def test_scope_rejects_disabled_vault_id(tmp_path: Path) -> None:
    with pytest.raises(CatalogError, match="disabled vault_id: off"):
        scope_from_mcp_input(McpScopeInput(vault_ids=("off",)), catalog=_catalog(tmp_path))


def test_scope_rejects_cross_vault_without_graph_permission(tmp_path: Path) -> None:
    with pytest.raises(CatalogError, match="explicit graph behavior"):
        scope_from_mcp_input(
            McpScopeInput(all_vaults=True, include_cross_vault=True),
            catalog=_catalog(tmp_path),
        )


def test_scope_allows_cross_vault_for_explicit_graph_behavior(tmp_path: Path) -> None:
    scope = scope_from_mcp_input(
        McpScopeInput(all_vaults=True, include_cross_vault=True),
        catalog=_catalog(tmp_path),
        allow_graph_cross_vault=True,
    )

    assert scope.include_cross_vault is True


def test_scope_content_scopes_must_narrow_every_selected_vault(tmp_path: Path) -> None:
    with pytest.raises(CatalogError, match="not enabled for vault_id: work"):
        scope_from_mcp_input(
            McpScopeInput(vault_ids=("default", "work"), content_scopes=("docs",)),
            catalog=_catalog(tmp_path),
        )


def test_scope_content_scopes_can_narrow_shared_scope(tmp_path: Path) -> None:
    scope = scope_from_mcp_input(
        McpScopeInput(vault_ids=("default", "work"), content_scopes=("wiki",)),
        catalog=_catalog(tmp_path),
    )

    assert scope.vault_ids == ("default", "work")
    assert scope.content_scopes == ("wiki",)
```

- [ ] **Step 2: Write failing error mapping tests**

```python
from __future__ import annotations

from pathlib import Path

from vault_graph.errors import CatalogError, VectorStoreError
from vault_graph.mcp.mcp_errors import McpProtocolError, map_exception_to_mcp_error


def test_catalog_error_maps_to_invalid_parameter() -> None:
    error = map_exception_to_mcp_error(CatalogError("unknown vault_id: work"))

    assert isinstance(error, McpProtocolError)
    assert error.kind == "invalid_parameter"
    assert error.payload.code == "catalog_error"
    assert error.payload.message == "unknown vault_id: work"
    assert error.payload.severity == "error"


def test_backend_error_maps_to_execution_error() -> None:
    error = map_exception_to_mcp_error(VectorStoreError("vector search unavailable: not initialized"))

    assert error.kind == "execution"
    assert error.payload.code == "vector_store_error"
    assert error.payload.message == "vector search unavailable: not initialized"


def test_domain_error_redacts_absolute_paths(tmp_path: Path) -> None:
    vault_file = tmp_path / "vault" / "wiki" / "page.md"
    error = map_exception_to_mcp_error(CatalogError(f"vault root does not exist: {vault_file}"))

    assert str(vault_file) not in error.payload.message
    assert "<redacted-path>" in error.payload.message


def test_internal_error_does_not_leak_arbitrary_absolute_path(tmp_path: Path) -> None:
    secret_path = tmp_path / "vault" / "wiki" / "page.md"
    error = map_exception_to_mcp_error(RuntimeError(f"failed at {secret_path}"))

    assert error.kind == "internal"
    assert error.payload.code == "internal_error"
    assert str(secret_path) not in error.payload.message


def test_internal_error_may_include_user_state_path(tmp_path: Path) -> None:
    state_path = tmp_path / "state"
    secret_path = tmp_path / "vault" / "wiki" / "page.md"
    error = map_exception_to_mcp_error(
        RuntimeError(f"failed at {state_path}; checked {secret_path}"),
        user_state_path=state_path,
    )

    assert str(state_path) in error.payload.message
    assert str(secret_path) not in error.payload.message
    assert "<redacted-path>" in error.payload.message
```

- [ ] **Step 3: Run tests to verify they fail**

Run:

```bash
uv run --python 3.12 pytest tests/test_mcp_scope.py tests/test_mcp_errors.py -q
```

Expected: FAIL because the MCP package, scope DTO, and error mapper do not exist.

- [ ] **Step 4: Implement scope, error, and lazy package exports**

Create `src/vault_graph/mcp/mcp_scope.py` and `src/vault_graph/mcp/mcp_errors.py`. Replace the temporary `src/vault_graph/mcp/__init__.py` content with the lazy export implementation from the Component And Interface Spec.

- [ ] **Step 5: Run tests to verify they pass**

Run:

```bash
uv run --python 3.12 pytest tests/test_mcp_scope.py tests/test_mcp_errors.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/vault_graph/mcp/__init__.py src/vault_graph/mcp/mcp_scope.py src/vault_graph/mcp/mcp_errors.py tests/test_mcp_scope.py tests/test_mcp_errors.py
git commit -m "feat(mcp): add scope and error contracts"
```

### Task 3: Add Read-Only MCP Service Factory

**Files:**

- Create: `src/vault_graph/mcp/mcp_service_factory.py`
- Test: `tests/test_mcp_service_factory.py`
- Test: `tests/test_mcp_import_boundaries.py`

- [ ] **Step 1: Write failing service factory tests**

```python
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from tests.test_read_only_boundary import file_bytes
from vault_graph.cli.main import app
from typer.testing import CliRunner

runner = CliRunner()


def test_mcp_factory_opens_read_only_services_without_creating_missing_state(tmp_path: Path) -> None:
    from vault_graph.mcp.mcp_service_factory import McpServiceFactory

    vault_root = tmp_path / "vault"
    (vault_root / "wiki").mkdir(parents=True)
    (vault_root / "wiki" / "page.md").write_text("# Page\nBody\n", encoding="utf-8")
    state_path = tmp_path / "state"
    assert runner.invoke(app, ["init", "--vault", str(vault_root), "--state", str(state_path)]).exit_code == 0
    before = file_bytes(vault_root)

    services = McpServiceFactory(state_path=state_path).open_read_only()

    assert services.catalog.active_vault_id == "default"
    assert services.retrieval_service is not None
    assert services.context_pack_builder is not None
    assert file_bytes(vault_root) == before
    assert not (state_path / "metadata").exists()
    assert not (state_path / "vector").exists()
    assert not (state_path / "graph").exists()
    assert not (state_path / "projection_cache").exists()


def test_mcp_factory_missing_catalog_fails_without_creating_state(tmp_path: Path) -> None:
    from vault_graph.errors import CatalogError
    from vault_graph.mcp.mcp_service_factory import McpServiceFactory

    state_path = tmp_path / "missing-state"

    with pytest.raises(CatalogError):
        McpServiceFactory(state_path=state_path).open_read_only()

    assert not state_path.exists()


def test_mcp_factory_uses_read_only_store_constructors(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from vault_graph.mcp.mcp_service_factory import McpServiceFactory

    vault_root = tmp_path / "vault"
    vault_root.mkdir()
    state_path = tmp_path / "state"
    assert runner.invoke(app, ["init", "--vault", str(vault_root), "--state", str(state_path)]).exit_code == 0
    calls: dict[str, object] = {}

    class FakeMetadataStore:
        def __init__(self, path: Path, *, initialize: bool = False) -> None:
            calls["metadata"] = (path, initialize)

    class FakeKeywordIndex:
        def __init__(self, path: Path) -> None:
            calls["keyword"] = path

    class FakeVectorStore:
        def __init__(self, path: Path, *, initialize: bool = False, read_only: bool = False) -> None:
            calls["vector"] = (path, initialize, read_only)

    monkeypatch.setattr("vault_graph.storage.local.sqlite_metadata_store.SQLiteMetadataStore", FakeMetadataStore)
    monkeypatch.setattr("vault_graph.storage.local.sqlite_keyword_index.SQLiteKeywordIndex", FakeKeywordIndex)
    monkeypatch.setattr("vault_graph.storage.local.chroma_vector_store.ChromaVectorStore", FakeVectorStore)

    McpServiceFactory(state_path=state_path).open_read_only()

    assert calls["metadata"] == (state_path / "metadata" / "metadata.sqlite3", False)
    assert calls["keyword"] == state_path / "metadata" / "metadata.sqlite3"
    assert calls["vector"] == (state_path / "vector" / "chroma", False, True)


def test_mcp_factory_open_read_only_does_not_import_rustworkx_projection() -> None:
    code = """
from pathlib import Path
import sys
from vault_graph.mcp.mcp_service_factory import McpServiceFactory
try:
    McpServiceFactory(state_path=Path('/definitely/missing/state')).open_read_only()
except Exception:
    pass
for name in ('vault_graph.projection.rustworkx_projection', 'rustworkx'):
    if name in sys.modules:
        raise SystemExit(name)
"""
    completed = subprocess.run([sys.executable, "-c", code], check=False, capture_output=True, text=True)

    assert completed.returncode == 0, completed.stderr or completed.stdout


def test_mcp_factory_open_read_only_does_not_import_runtime_clients(tmp_path: Path) -> None:
    code = f"""
from pathlib import Path
import sys
from typer.testing import CliRunner
from vault_graph.cli.main import app
from vault_graph.mcp.mcp_service_factory import McpServiceFactory

vault_root = Path({str(tmp_path / "vault")!r})
vault_root.mkdir()
state_path = Path({str(tmp_path / "state")!r})
runner = CliRunner()
runner.invoke(app, ["init", "--vault", str(vault_root), "--state", str(state_path)])
McpServiceFactory(state_path=state_path).open_read_only()
for name in ("chromadb", "fastembed", "huggingface_hub", "rustworkx"):
    if name in sys.modules:
        raise SystemExit(name)
"""
    completed = subprocess.run([sys.executable, "-c", code], check=False, capture_output=True, text=True)

    assert completed.returncode == 0, completed.stderr or completed.stdout


def test_mcp_factory_graph_service_imports_rustworkx_only_when_requested(tmp_path: Path) -> None:
    code = f"""
from pathlib import Path
import sys
from typer.testing import CliRunner
from vault_graph.cli.main import app
from vault_graph.mcp.mcp_service_factory import McpServiceFactory

vault_root = Path({str(tmp_path / "vault")!r})
(vault_root / "wiki").mkdir(parents=True)
(vault_root / "wiki" / "page.md").write_text("# Page\\nBody\\n", encoding="utf-8")
state_path = Path({str(tmp_path / "state")!r})
runner = CliRunner()
runner.invoke(app, ["init", "--vault", str(vault_root), "--state", str(state_path)])
factory = McpServiceFactory(state_path=state_path)
factory.open_read_only()
if "vault_graph.projection.rustworkx_projection" in sys.modules:
    raise SystemExit("eager")
try:
    factory.open_graph_retrieval_service()
except Exception:
    pass
if "vault_graph.projection.rustworkx_projection" not in sys.modules:
    raise SystemExit("missing")
"""
    completed = subprocess.run([sys.executable, "-c", code], check=False, capture_output=True, text=True)

    assert completed.returncode == 0, completed.stderr or completed.stdout
```

- [ ] **Step 2: Write failing package import boundary test**

```python
from __future__ import annotations

import subprocess
import sys


def test_mcp_package_import_is_lazy() -> None:
    code = """
import sys
import vault_graph.mcp
for name in (
    'mcp',
    'mcp.server.fastmcp',
    'chromadb',
    'fastembed',
    'vault_graph.context.context_pack_builder',
    'vault_graph.retrieval.retrieval_service',
    'vault_graph.storage.local.chroma_vector_store',
    'vault_graph.projection.rustworkx_projection',
    'rustworkx',
):
    if name in sys.modules:
        raise SystemExit(name)
"""
    completed = subprocess.run([sys.executable, "-c", code], check=False, capture_output=True, text=True)

    assert completed.returncode == 0, completed.stderr or completed.stdout


def test_mcp_service_factory_module_import_is_lightweight() -> None:
    code = """
import sys
import vault_graph.mcp.mcp_service_factory
for name in (
    'vault_graph.retrieval.retrieval_service',
    'vault_graph.context.context_pack_builder',
    'vault_graph.app.index_service',
    'vault_graph.app.graph_retrieval_service',
    'vault_graph.storage.local.chroma_vector_store',
    'vault_graph.projection.rustworkx_projection',
    'chromadb',
    'fastembed',
    'huggingface_hub',
    'rustworkx',
):
    if name in sys.modules:
        raise SystemExit(name)
"""
    completed = subprocess.run([sys.executable, "-c", code], check=False, capture_output=True, text=True)

    assert completed.returncode == 0, completed.stderr or completed.stdout
```

- [ ] **Step 3: Run tests to verify they fail**

Run:

```bash
uv run --python 3.12 pytest tests/test_mcp_service_factory.py tests/test_mcp_import_boundaries.py -q
```

Expected: FAIL because `mcp_service_factory.py` does not exist.

- [ ] **Step 4: Implement service factory**

Create `src/vault_graph/mcp/mcp_service_factory.py` using the Component And Interface Spec.

- [ ] **Step 5: Run focused tests**

Run:

```bash
uv run --python 3.12 pytest tests/test_mcp_service_factory.py tests/test_mcp_import_boundaries.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/vault_graph/mcp/mcp_service_factory.py tests/test_mcp_service_factory.py tests/test_mcp_import_boundaries.py
git commit -m "feat(mcp): add read-only service factory"
```

### Task 4: Add FastMCP Server Construction

**Files:**

- Create: `src/vault_graph/mcp/mcp_server.py`
- Test: `tests/test_mcp_server.py`

- [ ] **Step 1: Write failing server construction tests**

```python
from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from vault_graph.cli.main import app
from vault_graph.errors import CatalogError
from vault_graph.mcp.mcp_server import McpServerConfig, create_mcp_server

runner = CliRunner()


def test_mcp_server_config_accepts_stdio_only(tmp_path: Path) -> None:
    config = McpServerConfig(state_path=tmp_path / "state")

    assert config.transport == "stdio"
    assert config.server_name == "vault-graph"


def test_mcp_server_config_rejects_non_stdio_transport(tmp_path: Path) -> None:
    with pytest.raises(CatalogError, match="unsupported MCP transport"):
        McpServerConfig(state_path=tmp_path / "state", transport="streamable-http")  # type: ignore[arg-type]


def test_create_mcp_server_loads_services_before_stdio_run(tmp_path: Path) -> None:
    vault_root = tmp_path / "vault"
    vault_root.mkdir()
    state_path = tmp_path / "state"
    assert runner.invoke(app, ["init", "--vault", str(vault_root), "--state", str(state_path)]).exit_code == 0

    registered = create_mcp_server(McpServerConfig(state_path=state_path))

    assert registered.server.name == "vault-graph"
    assert registered.services.catalog.active_vault_id == "default"
    assert registered.server_version == "0.1.0"


def test_create_mcp_server_missing_catalog_fails_before_server_object(tmp_path: Path) -> None:
    with pytest.raises(CatalogError):
        create_mcp_server(McpServerConfig(state_path=tmp_path / "missing-state"))
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
uv run --python 3.12 pytest tests/test_mcp_server.py -q
```

Expected: FAIL because `mcp_server.py` does not exist.

- [ ] **Step 3: Implement server construction**

Create `src/vault_graph/mcp/mcp_server.py` using the Component And Interface Spec.

- [ ] **Step 4: Run tests to verify they pass**

Run:

```bash
uv run --python 3.12 pytest tests/test_mcp_server.py tests/test_mcp_service_factory.py tests/test_mcp_import_boundaries.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/vault_graph/mcp/mcp_server.py tests/test_mcp_server.py
git commit -m "feat(mcp): add stdio server construction"
```

### Task 5: Add `vg serve --mcp`

**Files:**

- Modify: `src/vault_graph/cli/main.py`
- Modify: `tests/test_cli_surface_boundary.py`
- Test: `tests/test_cli_mcp_serve.py`

- [ ] **Step 1: Write failing CLI tests**

```python
from __future__ import annotations

from pathlib import Path

from pytest import MonkeyPatch
from typer.testing import CliRunner

from vault_graph.cli.main import app

runner = CliRunner()


def test_cli_surface_exposes_serve_command() -> None:
    result = runner.invoke(app, ["--help"])

    assert result.exit_code == 0
    assert "serve" in result.output
    assert "ask" not in result.output


def test_serve_help_exposes_mcp_without_starting_server() -> None:
    result = runner.invoke(app, ["serve", "--help"])

    assert result.exit_code == 0
    assert "--mcp" in result.output
    assert "--state" in result.output


def test_serve_requires_selected_transport(tmp_path: Path) -> None:
    result = runner.invoke(app, ["serve", "--state", str(tmp_path / "state")])

    assert result.exit_code == 1
    assert "select one server transport: --mcp" in result.stderr


def test_serve_rejects_http_transport(tmp_path: Path) -> None:
    result = runner.invoke(app, ["serve", "--http", "--state", str(tmp_path / "state")])

    assert result.exit_code == 1
    assert "http_transport_not_supported_in_phase_5a" in result.stderr


def test_serve_rejects_multiple_transports(tmp_path: Path) -> None:
    result = runner.invoke(app, ["serve", "--mcp", "--http", "--state", str(tmp_path / "state")])

    assert result.exit_code == 1
    assert "Use either --mcp or --http, not both." in result.stderr


def test_serve_mcp_missing_catalog_exits_before_stdio_start(tmp_path: Path, monkeypatch: MonkeyPatch) -> None:
    called = False

    def fake_run(_: object, *, config: object) -> None:
        nonlocal called
        called = True

    monkeypatch.setattr("vault_graph.mcp.mcp_server.run_mcp_server", fake_run)

    result = runner.invoke(app, ["serve", "--mcp", "--state", str(tmp_path / "missing-state")])

    assert result.exit_code == 1
    assert called is False
    assert "VaultCatalog config does not exist" in result.stderr
    assert result.stdout == ""


def test_serve_mcp_delegates_without_stdout_startup_text(tmp_path: Path, monkeypatch: MonkeyPatch) -> None:
    vault_root = tmp_path / "vault"
    vault_root.mkdir()
    state_path = tmp_path / "state"
    assert runner.invoke(app, ["init", "--vault", str(vault_root), "--state", str(state_path)]).exit_code == 0
    seen_state: Path | None = None

    def fake_run(_: object, *, config: object) -> None:
        nonlocal seen_state
        seen_state = config.state_path  # type: ignore[attr-defined]

    monkeypatch.setattr("vault_graph.mcp.mcp_server.run_mcp_server", fake_run)

    result = runner.invoke(app, ["serve", "--mcp", "--state", str(state_path)])

    assert result.exit_code == 0
    assert seen_state == state_path.expanduser().resolve()
    assert result.stdout == ""
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
uv run --python 3.12 pytest tests/test_cli_mcp_serve.py tests/test_cli_surface_boundary.py -q
```

Expected: FAIL because `serve` command does not exist.

- [ ] **Step 3: Add `serve` command and stderr helper**

Modify `src/vault_graph/cli/main.py` using the CLI Component And Interface Spec. Place `serve` after `status` or near other top-level commands; do not move unrelated command bodies.

- [ ] **Step 4: Run focused CLI tests**

Run:

```bash
uv run --python 3.12 pytest tests/test_cli_mcp_serve.py tests/test_cli_surface_boundary.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/vault_graph/cli/main.py tests/test_cli_mcp_serve.py tests/test_cli_surface_boundary.py
git commit -m "feat(cli): add mcp serve command"
```

### Task 6: Add End-To-End MCP Stdio Smoke Verification

**Files:**

- Test: `tests/test_mcp_stdio_smoke.py`

- [ ] **Step 1: Write failing stdio smoke test**

```python
from __future__ import annotations

import os
from pathlib import Path

import pytest
from typer.testing import CliRunner

from vault_graph.cli.main import app

runner = CliRunner()


@pytest.mark.skipif(os.environ.get("VG_RUN_MCP_STDIO_SMOKE") != "1", reason="set VG_RUN_MCP_STDIO_SMOKE=1")
def test_mcp_stdio_initializes_with_official_client(tmp_path: Path) -> None:
    import anyio
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    vault_root = tmp_path / "vault"
    vault_root.mkdir()
    state_path = tmp_path / "state"
    assert runner.invoke(app, ["init", "--vault", str(vault_root), "--state", str(state_path)]).exit_code == 0

    async def run_client() -> None:
        params = StdioServerParameters(
            command="uv",
            args=[
                "run",
                "--python",
                "3.12",
                "vg",
                "serve",
                "--mcp",
                "--state",
                str(state_path),
            ],
        )
        with anyio.fail_after(15):
            async with stdio_client(params) as (read_stream, write_stream):
                async with ClientSession(read_stream, write_stream) as session:
                    await session.initialize()
                    tools = await session.list_tools()
                    resources = await session.list_resources()
                    prompts = await session.list_prompts()
                    assert tools.tools == []
                    assert resources.resources == []
                    assert prompts.prompts == []

    anyio.run(run_client)
```

- [ ] **Step 2: Run default suite behavior**

Run:

```bash
uv run --python 3.12 pytest tests/test_mcp_stdio_smoke.py -q
```

Expected: SKIPPED with reason `set VG_RUN_MCP_STDIO_SMOKE=1`.

- [ ] **Step 3: Run opt-in smoke test**

Run:

```bash
VG_RUN_MCP_STDIO_SMOKE=1 uv run --python 3.12 pytest tests/test_mcp_stdio_smoke.py -q
```

Expected: PASS. If the MCP SDK client hangs, do not increase timeouts first; inspect stdout contamination, stderr logging, and server startup errors.

- [ ] **Step 4: Commit**

```bash
git add tests/test_mcp_stdio_smoke.py
git commit -m "test(mcp): add opt-in stdio smoke coverage"
```

### Task 7: Full Verification And Documentation Check

**Files:**

- No new production files unless verification exposes a defect.

- [ ] **Step 1: Run Phase 5A focused tests**

```bash
uv run --python 3.12 pytest \
  tests/test_mcp_config_examples.py \
  tests/test_mcp_scope.py \
  tests/test_mcp_errors.py \
  tests/test_mcp_service_factory.py \
  tests/test_mcp_import_boundaries.py \
  tests/test_mcp_server.py \
  tests/test_cli_mcp_serve.py \
  tests/test_cli_surface_boundary.py \
  tests/test_mcp_stdio_smoke.py \
  -q
```

Expected: PASS with one skipped smoke test unless `VG_RUN_MCP_STDIO_SMOKE=1` is set.

- [ ] **Step 2: Run required MCP stdio smoke test**

```bash
VG_RUN_MCP_STDIO_SMOKE=1 uv run --python 3.12 pytest tests/test_mcp_stdio_smoke.py -q
```

Expected: PASS. This command is required before marking Phase 5A complete because the default suite skips the official MCP client initialization check.

- [ ] **Step 3: Run existing boundary and context-pack regression tests**

```bash
uv run --python 3.12 pytest \
  tests/test_read_only_boundary.py \
  tests/test_search_read_only_boundary.py \
  tests/test_context_pack_import_boundaries.py \
  tests/test_retrieval_import_boundaries.py \
  tests/test_cli_search.py \
  tests/test_cli_context.py \
  tests/test_cli_related.py \
  tests/test_cli_decision_trace.py \
  -q
```

Expected: PASS.

- [ ] **Step 4: Run full quality gates**

```bash
uv run --python 3.12 pytest -q
uv run --python 3.12 ruff check src tests
uv run --python 3.12 mypy src tests
git diff --check
```

Expected: all commands PASS.

- [ ] **Step 5: Inspect final changed files**

```bash
git status --short
git diff --stat
```

Expected: only Phase 5A files listed in this plan are changed.

- [ ] **Step 6: Commit final verification fixes if any**

If verification required fixes after Task 6, commit those fixes:

```bash
git add <fixed-files>
git commit -m "fix(mcp): harden stdio foundation"
```

## Multi-Angle Review Checklist

Run this review after Task 7 and before merging:

- Security: no Vault writes, no raw filesystem arguments from MCP, no stdout logs during stdio, no arbitrary absolute path leaks in internal errors, no remote transport.
- Performance: no eager Chroma client, FastEmbed backend, model download, rustworkx import, indexing, or context-pack build during startup.
- Testability: service factory has unit tests, CLI command can be tested without starting a long-running server, opt-in stdio smoke verifies real MCP initialization.
- Maintainability: MCP package is an adapter only; CLI and MCP do not share hidden mutable state; resource/tool/prompt work has clear handoff points for Phase 5B/5C.

## Open Decisions

None.

Implementation-level choices fixed by this plan:

- Use official `mcp>=1.27,<2` because v1 is stable, v2 is alpha, and the runtime server does not need the SDK CLI extra.
- Use FastMCP for the Phase 5A server boundary.
- Register no Phase 5A resources, tools, or prompts until the concrete Phase 5B/5C handlers exist.
- Keep Streamable HTTP and authentication out of Phase 5A.

## References

- Official MCP Python SDK: https://github.com/modelcontextprotocol/python-sdk
- MCP specification: https://modelcontextprotocol.io/specification/2025-06-18
