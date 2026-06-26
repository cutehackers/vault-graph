# CLI TODO Command Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the documented CLI TODO surfaces that make Vault Graph easier to install, register with agents, keep indexed, and serve locally without weakening the read-only Vault boundary.

**Architecture:** Keep protocol adapters thin. Move reusable service construction into app-level factories, keep MCP config registration in the MCP package, keep setup/watch orchestration in app services, and keep HTTP as a read-only adapter over existing application services. `vg ask` and MCP `ask_vault(...)` are implemented by the companion Ask plan and are referenced here only as a CLI TODO dependency to avoid duplicating answer contracts.

**Tech Stack:** Python 3.12, Typer, frozen dataclasses, Protocol-based service seams, existing `IndexService`, existing read-only retrieval/graph/context/memory services, FastAPI and Uvicorn for the HTTP adapter, pytest, ruff, mypy.

---

## Source Documents

Read these before implementation:

- `AGENTS.md`
- `docs/SPEC.md`
- `docs/FEATURES.md`
- `docs/DESIGN.md`
- `docs/DECISIONS.md`
- `docs/CONVENTIONS.md`
- `README.md`
- `docs/superpowers/specs/2026-06-24-cli-todo-command-implementation-design.md`
- `docs/superpowers/specs/2026-06-25-evidence-first-ask-and-reasoning-design.md`
- `docs/superpowers/plans/2026-06-26-evidence-first-ask-and-reasoning.md`

Repo context inspected for this plan:

- `src/vault_graph/cli/main.py` currently exposes `init`, `index`, `context`, `search`, `related`, `decision-trace`, `status`, `serve`, and `vault`.
- `src/vault_graph/cli/main.py` currently rejects `vg serve --http` with `http_transport_not_supported_in_phase_5a`.
- `src/vault_graph/cli/main.py` currently owns private service-construction helpers for writable indexing and read-only retrieval.
- `src/vault_graph/mcp/mcp_config_examples.py` contains a source-checkout Codex stdio example using `uv run --python 3.12 vg ...`; this should remain a documented example, not the registrar's installed-command payload.
- `src/vault_graph/mcp/mcp_service_factory.py` already opens read-only services for MCP and should keep lazy imports.
- `tests/test_cli_surface_boundary.py` currently asserts `ask` is not present.
- `tests/test_cli_mcp_serve.py` currently asserts `serve --http` is reserved and unsupported.
- Existing tests cover read-only boundaries, multi-vault identity, search/context/graph CLI behavior, MCP tool registration, and MCP service factory import boundaries.

## Scope

Implement or coordinate these documented command surfaces:

- `vg mcp config --agent codex --state PATH --print`
- `vg mcp register --agent codex --state PATH --config-path PATH [--dry-run]`
- `vg setup --vault PATH [--state PATH] [--vault-id ID] [--agent codex] [--mcp-config-path PATH] [--print-mcp-config] [--dry-run]`
- `vg watch [--state PATH] [--vault-id ID | --all-vaults] [--interval SECONDS] [--full]`
- `vg serve --http [--state PATH] [--host 127.0.0.1] [--port 8765]`
- `vg ask ...` only through the companion Ask plan; this plan updates CLI TODO acceptance so `vg ask` no longer stays hidden after that plan lands.

## Non-Goals

Do not implement:

- hosted or remote HTTP serving
- authentication or remote sharing
- default-path discovery for Codex config writes
- implicit writes to user-level agent config files
- native filesystem watchers
- PyPI publication
- answer internals, answer DTOs, or citation logic in this plan
- writable memory APIs, answer persistence, or durable context-pack storage
- any Vault file edit, rename, rewrite, deletion, publication, validation, or Git metadata write

## Directory And File Structure

Create:

- `src/vault_graph/app/local_index_service_factory.py`
  - Owns local writable/read-only `IndexService` construction for CLI setup/watch/index/status.
- `src/vault_graph/app/read_only_service_factory.py`
  - Owns reusable read-only retrieval, graph, context, status, and memory service construction for MCP and HTTP.
- `src/vault_graph/app/setup_service.py`
  - Owns one-command setup orchestration.
- `src/vault_graph/app/watch_service.py`
  - Owns polling-based repeated indexing.
- `src/vault_graph/mcp/mcp_config_registration.py`
  - Owns Codex MCP config rendering and explicit config-file registration.
- `src/vault_graph/http/__init__.py`
- `src/vault_graph/http/http_errors.py`
- `src/vault_graph/http/http_serialization.py`
- `src/vault_graph/http/http_server.py`
- `src/vault_graph/http/http_service_factory.py`
- `tests/test_local_index_service_factory.py`
- `tests/test_read_only_service_factory.py`
- `tests/test_mcp_config_registration.py`
- `tests/test_cli_mcp_config.py`
- `tests/test_cli_mcp_register.py`
- `tests/test_setup_service.py`
- `tests/test_cli_setup.py`
- `tests/test_watch_service.py`
- `tests/test_cli_watch.py`
- `tests/test_http_errors.py`
- `tests/test_http_serialization.py`
- `tests/test_http_server.py`
- `tests/test_cli_http_serve.py`
- `tests/test_http_read_only_boundary.py`

Modify:

- `pyproject.toml`
  - Add HTTP dependencies only when starting the HTTP slice: `fastapi>=0.115,<1` and `uvicorn>=0.30,<1`.
- `src/vault_graph/cli/main.py`
  - Add `mcp` Typer sub-app, setup command, watch command, HTTP serve options, and factory delegation.
- `src/vault_graph/mcp/mcp_service_factory.py`
  - Delegate service construction to `ReadOnlyServiceFactory` while preserving the existing public `McpServiceFactory` methods.
- `tests/test_cli_surface_boundary.py`
  - Update command surface expectations as each slice lands.
- `tests/test_cli_mcp_serve.py`
  - Keep `--mcp --http` invalid; update `--http` once HTTP lands.
- `tests/test_mcp_service_factory.py`
  - Preserve lazy-import and read-only behavior after factory extraction.
- `tests/test_mcp_import_boundaries.py`
  - Guard that HTTP does not import MCP and MCP does not import HTTP.
- `README.md`, `docs/SPEC.md`, and `docs/FEATURES.md`
  - Move commands out of TODO only after their acceptance tests pass.

Do not create:

- `src/vault_graph/app/manager.py`
- `src/vault_graph/app/utils.py`
- `src/vault_graph/http/helpers.py`
- `src/vault_graph/http/http_store.py`
- any `watchdog` dependency
- any persisted answer, memory, or HTTP session store

## Component And Interface Spec

### `src/vault_graph/app/local_index_service_factory.py`

Add:

```python
from dataclasses import dataclass
from pathlib import Path

from vault_graph.app.catalog_service import CatalogService
from vault_graph.app.index_service import IndexService
from vault_graph.ingestion.vault_catalog import VaultCatalog


@dataclass(frozen=True)
class LocalIndexServiceBundle:
    catalog_service: CatalogService
    catalog: VaultCatalog
    index_service: IndexService

    def close(self) -> None:
        self.index_service.close()


class LocalIndexServiceFactory:
    def open(self, *, state_path: Path, initialize_store: bool) -> LocalIndexServiceBundle:
        ...
```

Behavior:

- Move the current `src/vault_graph/cli/main.py::_service(...)` construction into this factory.
- Preserve path safety checks when `initialize_store=True`.
- Use writable graph store only when `initialize_store=True`.
- Use read-only graph/vector/metadata constructors when `initialize_store=False`.
- Keep `FastEmbedTextEmbeddingsConfig(local_files_only=True)` for read-only search behavior elsewhere; indexing may still use the existing writable embedding config.
- Do not import Typer, MCP, HTTP, or CLI modules.

### `src/vault_graph/app/read_only_service_factory.py`

Add:

```python
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from vault_graph.app.catalog_service import CatalogService
from vault_graph.ingestion.vault_catalog import VaultCatalog
from vault_graph.storage.interfaces.metadata_store import MetadataStore

if TYPE_CHECKING:
    from vault_graph.app.graph_resource_service import GraphResourceService
    from vault_graph.app.graph_retrieval_service import GraphRetrievalService
    from vault_graph.app.index_service import IndexService
    from vault_graph.context.context_pack_builder import ContextPackBuilder
    from vault_graph.context.context_pack_renderer import ContextPackRenderer
    from vault_graph.memory.decision_memory import DecisionMemoryService
    from vault_graph.memory.health_explorer import HealthExplorerService
    from vault_graph.memory.issue_memory import IssueMemoryService
    from vault_graph.memory.memory_source_reader import MemorySourceReader
    from vault_graph.memory.project_memory import ProjectMemoryService
    from vault_graph.memory.timeline_memory import TimelineMemoryService
    from vault_graph.retrieval.graph_candidates import GraphSearchCandidateProvider
    from vault_graph.retrieval.retrieval_service import RetrievalService


@dataclass(frozen=True)
class ReadOnlyServices:
    catalog_service: CatalogService
    catalog: VaultCatalog
    metadata_store: MetadataStore
    retrieval_service: "RetrievalService"
    context_pack_builder: "ContextPackBuilder"
    context_pack_renderer: "ContextPackRenderer"


class ReadOnlyServiceFactory:
    def __init__(self, *, state_path: Path) -> None: ...
    def open_read_only(self) -> ReadOnlyServices: ...
    def open_retrieval_service(self, *, include_graph: bool = False) -> "RetrievalService": ...
    def open_context_pack_builder(self, *, include_graph: bool = False) -> "ContextPackBuilder": ...
    def open_status_service(self) -> "IndexService": ...
    def open_graph_retrieval_service(self) -> "GraphRetrievalService": ...
    def open_graph_resource_service(self) -> "GraphResourceService": ...
    def open_graph_search_candidate_provider(self) -> "GraphSearchCandidateProvider": ...
    def open_memory_source_reader(self) -> "MemorySourceReader": ...
    def open_decision_memory_service(self) -> "DecisionMemoryService": ...
    def open_issue_memory_service(self) -> "IssueMemoryService": ...
    def open_project_memory_service(self) -> "ProjectMemoryService": ...
    def open_timeline_memory_service(self) -> "TimelineMemoryService": ...
    def open_health_explorer_service(self) -> "HealthExplorerService": ...
```

Implementation rule:

- Extract the current `McpServiceFactory` implementation into this app-level class first.
- Keep imports lazy inside methods exactly as `McpServiceFactory` does today.
- Then update `McpServiceFactory` to wrap `ReadOnlyServiceFactory` and keep its current method names.
- HTTP must depend on this app-level factory, not on `vault_graph.mcp`.

### `src/vault_graph/mcp/mcp_config_registration.py`

Add:

```python
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

McpAgent = Literal["codex"]


@dataclass(frozen=True)
class McpConfigRequest:
    agent: McpAgent
    state_path: Path
    server_name: str = "vault-graph"


@dataclass(frozen=True)
class McpRegistrationRequest:
    agent: McpAgent
    state_path: Path
    config_path: Path
    dry_run: bool = False
    server_name: str = "vault-graph"


@dataclass(frozen=True)
class McpRegistrationReport:
    agent: McpAgent
    config_path: Path
    backup_path: Path | None
    server_name: str
    command: str
    args: tuple[str, ...]
    dry_run: bool
    changed: bool
    rendered_config: str


class McpConfigRenderer:
    def render_dict(self, request: McpConfigRequest) -> dict[str, object]: ...
    def render(self, request: McpConfigRequest) -> str: ...


class McpConfigRegistrar:
    def __init__(self, *, backup_suffix: Callable[[], str] | None = None) -> None: ...
    def register(self, request: McpRegistrationRequest) -> McpRegistrationReport: ...
```

Rendering rules:

- Resolve `state_path` with `expanduser().resolve()`.
- Render installed-command payload:

```json
{
  "mcpServers": {
    "vault-graph": {
      "command": "vg",
      "args": ["serve", "--mcp", "--state", "<resolved-state-path>"]
    }
  }
}
```

- Keep `src/vault_graph/mcp/mcp_config_examples.py` unchanged unless docs explicitly need a source-checkout example update.

Registration rules:

- Support `agent="codex"` only.
- `vg mcp config` prints and never writes.
- `vg mcp register` writes only `config_path`.
- Reject missing config parent with `mcp_config_parent_missing`.
- Parse existing JSON as JSON and preserve unrelated entries.
- Reject invalid JSON with `mcp_config_invalid_json`.
- If existing `mcpServers.vault-graph` already matches, set `changed=False` and do not write a backup.
- If existing `mcpServers.vault-graph` differs, write backup before replacing that entry.
- Use backup path `<config_path.name>.bak-<suffix>` in the same directory.
- `--dry-run` reports the same rendered payload and planned backup path but writes nothing.

### `src/vault_graph/app/setup_service.py`

Add:

```python
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from vault_graph.mcp.mcp_config_registration import McpRegistrationReport

SetupAgent = Literal["codex"]


@dataclass(frozen=True)
class SetupRequest:
    vault_root: Path
    state_path: Path
    vault_id: str = "default"
    agent: SetupAgent | None = None
    mcp_config_path: Path | None = None
    print_mcp_config: bool = False
    dry_run: bool = False


@dataclass(frozen=True)
class SetupReport:
    vault_id: str
    vault_root: Path
    state_path: Path
    catalog_created: bool
    catalog_changed: bool
    index_exit_code: int | None
    index_summary: dict[str, object] | None
    mcp_config: str | None
    mcp_registration: McpRegistrationReport | None
    warnings: tuple[str, ...]


class SetupService:
    def run(self, request: SetupRequest) -> SetupReport: ...
```

Setup flow:

1. Resolve `vault_root` and `state_path`.
2. Reject `state_path` inside `vault_root` with the existing read-only boundary guard.
3. If `dry_run=True`, validate paths and return a plan without creating state, catalogs, indexes, caches, or agent config.
4. If no catalog exists, create a catalog with `vault_id`.
5. If a catalog exists and `vault_id` points to the same root, treat setup as idempotent.
6. If a catalog exists and `vault_id` points elsewhere, fail with `setup_vault_id_conflict`.
7. If a catalog exists and `vault_id` is missing, fail with `setup_vault_id_missing`; recovery hint should suggest `vg vault add`.
8. Run `IndexService.run_apply(scope=catalog.scope_for_vault_ids([vault_id]), full=False)`.
9. If `agent` is omitted, stop after indexing.
10. If `agent` is set and `mcp_config_path` is set, call `McpConfigRegistrar`.
11. If `agent` is set and `print_mcp_config=True`, include rendered config in output.
12. If `agent` is set with neither `mcp_config_path` nor `print_mcp_config`, include rendered config and add warning `mcp_config_not_written`.

### `src/vault_graph/app/watch_service.py`

Add:

```python
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from vault_graph.app.index_service import IndexRunReport
from vault_graph.app.local_index_service_factory import LocalIndexServiceFactory
from vault_graph.ingestion.vault_catalog import QueryScope


@dataclass(frozen=True)
class WatchRequest:
    scope: QueryScope
    interval_seconds: float = 2.0
    full: bool = False


@dataclass(frozen=True)
class WatchIterationReport:
    iteration: int
    index_exit_code: int
    changed: int
    deleted: int
    vector_failed: bool
    graph_failed: bool


class WatchService:
    def __init__(
        self,
        *,
        state_path: Path,
        index_factory: LocalIndexServiceFactory | None = None,
    ) -> None: ...

    def run(
        self,
        request: WatchRequest,
        *,
        stop_requested: Callable[[], bool],
        on_iteration: Callable[[WatchIterationReport], None],
        sleep: Callable[[float], None],
    ) -> int: ...
```

Behavior:

- Use `LocalIndexServiceFactory.open(initialize_store=True)`.
- The CLI constructs `WatchService(state_path=state)` after resolving scope from
  the catalog.
- Call `IndexService.run_apply(scope=request.scope, full=request.full)` each iteration.
- Convert each `IndexRunReport` into `WatchIterationReport`.
- Continue after recoverable vector/graph failures and return the last nonzero code only if all iterations failed before a clean interruption.
- Return `0` on `KeyboardInterrupt` after at least one iteration.
- Return nonzero for configuration/store errors before the first iteration.
- Never inspect Vault Git metadata and never write outside Vault Graph state.

### `src/vault_graph/http/*`

Add `HttpServerConfig`:

```python
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class HttpServerConfig:
    state_path: Path
    host: str = "127.0.0.1"
    port: int = 8765

    def __post_init__(self) -> None: ...
```

Rules:

- Resolve `state_path`.
- Reject `host != "127.0.0.1"` with `remote_http_not_supported`.
- Reject invalid ports outside `1..65535`.
- Do not add CORS middleware.

Add:

```python
def create_http_app(config: HttpServerConfig) -> object: ...
def run_http_server(config: HttpServerConfig) -> None: ...
```

Routes:

- `GET /health`
  - Returns `{"ok": true, "service": "vault-graph", "transport": "http"}` if config and catalog load.
- `GET /status`
  - Calls `ReadOnlyServiceFactory.open_status_service().status(...)`.
- `POST /search`
  - Request: `{"query": str, "scope": object | null, "limit": int, "include_graph": bool, "include_cross_vault": bool}`
  - Calls `RetrievalService.search(...)`.
- `POST /context`
  - Request mirrors MCP `build_context_pack`.
- `POST /related`
  - Request mirrors MCP `find_related`.
- `POST /decision-trace`
  - Request mirrors MCP `get_decision_trace`.
- `GET /memory/project`
- `GET /memory/open-questions`
- `GET /memory/recent-changes`
- `POST /explain-result`
- `POST /ask`
  - Add only after companion Ask plan creates `AnswerService`.
  - Until then, do not expose `/ask`.

HTTP error payload:

```json
{
  "error": {
    "code": "catalog_error",
    "message": "...",
    "recovery_hint": "..."
  }
}
```

HTTP adapter rules:

- JSON only.
- No filesystem browsing routes.
- No full-Vault dump routes.
- No indexing route.
- No writes to Vault Graph derived state.
- No writes to Vault content.
- No dependency from `vault_graph.http` to `vault_graph.mcp`.

## State Management And Data Flow

### MCP Config

```text
CLI args
  -> McpConfigRequest or McpRegistrationRequest
  -> McpConfigRenderer or McpConfigRegistrar
  -> printed JSON or explicit config_path write
```

Writes:

- `vg mcp config`: none
- `vg mcp register`: only `--config-path`

Forbidden:

- registered Vault roots
- Vault Graph indexes
- implicit user-level config discovery

### Setup

```text
CLI args
  -> SetupRequest
  -> SetupService
  -> CatalogService create/load
  -> LocalIndexServiceFactory.open(initialize_store=True)
  -> IndexService.run_apply
  -> optional McpConfigRenderer or McpConfigRegistrar
  -> SetupReport
  -> CLI text rendering
```

Writes:

- Vault Graph state under `state_path`
- optional explicit `--mcp-config-path`

Forbidden:

- Vault files
- Vault Git metadata
- hidden agent config path writes

### Watch

```text
CLI scope flags
  -> QueryScope
  -> WatchRequest
  -> WatchService.run
  -> IndexService.run_apply per iteration
  -> WatchIterationReport
  -> CLI iteration output
```

Writes:

- Vault Graph derived state under `state_path`

Forbidden:

- Vault files
- external config files

### HTTP

```text
HTTP request JSON
  -> request parser
  -> QueryScope mapping
  -> ReadOnlyServiceFactory
  -> existing app service
  -> HTTP serializer
  -> JSON response
```

Writes:

- none for initial HTTP routes

Forbidden:

- indexing
- durable context-pack or answer storage
- Vault writes

## Implementation Steps

### Task 0: Sync With Ask Plan

**Files:**

- Read: `docs/superpowers/plans/2026-06-26-evidence-first-ask-and-reasoning.md`
- Modify later: `tests/test_cli_surface_boundary.py`

- [ ] **Step 1: Confirm companion plan exists**

Run: `test -f docs/superpowers/plans/2026-06-26-evidence-first-ask-and-reasoning.md`

Expected: exit code `0`.

- [ ] **Step 2: Do not duplicate answer internals**

Implementation rule: this plan must not create alternate `AnswerResponse`, `AnswerService`, `CitationGuard`, or `ask_vault` contracts. Execute the companion Ask plan for those symbols.

- [ ] **Step 3: Commit only after a real code slice**

Do not commit Task 0 by itself.

### Task 1: Extract Local Index Service Construction

**Files:**

- Create: `src/vault_graph/app/local_index_service_factory.py`
- Modify: `src/vault_graph/cli/main.py`
- Test: `tests/test_local_index_service_factory.py`

- [ ] **Step 1: Write failing factory tests**

Add tests:

- `test_local_index_factory_initializes_writable_state_safely`
- `test_local_index_factory_rejects_state_inside_vault`
- `test_local_index_factory_read_only_mode_does_not_create_missing_state`

Run: `uv run --python 3.12 pytest tests/test_local_index_service_factory.py -q`

Expected: FAIL because module does not exist.

- [ ] **Step 2: Implement `LocalIndexServiceFactory`**

Move the current CLI `_service(...)` construction into `LocalIndexServiceFactory.open(...)`. Keep the current CLI helper as a thin wrapper:

```python
def _service(state: Path, *, initialize_store: bool) -> tuple[CatalogService, VaultCatalog, IndexService]:
    bundle = LocalIndexServiceFactory().open(state_path=state, initialize_store=initialize_store)
    return bundle.catalog_service, bundle.catalog, bundle.index_service
```

- [ ] **Step 3: Verify no CLI behavior changed**

Run: `uv run --python 3.12 pytest tests/test_cli_catalog_metadata.py tests/test_cli_vector_indexing.py tests/test_cli_graph_indexing.py tests/test_cli_graph_status.py -q`

Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add src/vault_graph/app/local_index_service_factory.py src/vault_graph/cli/main.py tests/test_local_index_service_factory.py
git commit -m "refactor(cli): extract local index service factory"
```

### Task 2: Extract Read-Only Service Construction

**Files:**

- Create: `src/vault_graph/app/read_only_service_factory.py`
- Modify: `src/vault_graph/mcp/mcp_service_factory.py`
- Test: `tests/test_read_only_service_factory.py`
- Test: `tests/test_mcp_service_factory.py`

- [ ] **Step 1: Write failing read-only factory tests**

Add tests:

- `test_read_only_factory_opens_search_without_creating_state`
- `test_read_only_factory_keeps_graph_provider_lazy`
- `test_read_only_factory_opens_memory_services_without_memory_state`

Run: `uv run --python 3.12 pytest tests/test_read_only_service_factory.py -q`

Expected: FAIL because module does not exist.

- [ ] **Step 2: Move `McpServiceFactory` internals**

Move the construction logic from `McpServiceFactory` into `ReadOnlyServiceFactory`. Then make `McpServiceFactory` delegate to a private `ReadOnlyServiceFactory` instance.

Preserve public names:

- `open_read_only`
- `open_retrieval_service`
- `open_context_pack_builder`
- `open_status_service`
- `open_graph_retrieval_service`
- `open_graph_resource_service`
- `open_graph_search_candidate_provider`
- `open_memory_source_reader`
- `open_decision_memory_service`
- `open_issue_memory_service`
- `open_project_memory_service`
- `open_timeline_memory_service`
- `open_health_explorer_service`

- [ ] **Step 3: Verify MCP did not gain eager imports**

Run: `uv run --python 3.12 pytest tests/test_mcp_service_factory.py tests/test_mcp_import_boundaries.py -q`

Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add src/vault_graph/app/read_only_service_factory.py src/vault_graph/mcp/mcp_service_factory.py tests/test_read_only_service_factory.py tests/test_mcp_service_factory.py tests/test_mcp_import_boundaries.py
git commit -m "refactor(app): share read-only service factory"
```

### Task 3: Add MCP Config Rendering And Registration

**Files:**

- Create: `src/vault_graph/mcp/mcp_config_registration.py`
- Test: `tests/test_mcp_config_registration.py`

- [ ] **Step 1: Write failing renderer tests**

Add tests:

- `test_mcp_config_renderer_outputs_installed_vg_command`
- `test_mcp_config_renderer_resolves_state_path`
- `test_mcp_config_renderer_rejects_unsupported_agent`

Run: `uv run --python 3.12 pytest tests/test_mcp_config_registration.py -q`

Expected: FAIL because module does not exist.

- [ ] **Step 2: Implement renderer**

Implement `McpConfigRequest`, `McpConfigRenderer.render_dict(...)`, and `McpConfigRenderer.render(...)`.

- [ ] **Step 3: Write failing registrar tests**

Add tests:

- `test_mcp_config_register_writes_requested_config_path_only`
- `test_mcp_config_register_preserves_unrelated_servers`
- `test_mcp_config_register_is_idempotent_when_entry_matches`
- `test_mcp_config_register_backs_up_before_replacing_existing_entry`
- `test_mcp_config_register_dry_run_writes_nothing`
- `test_mcp_config_register_rejects_missing_parent`
- `test_mcp_config_register_rejects_invalid_json_without_write`

Run: `uv run --python 3.12 pytest tests/test_mcp_config_registration.py -q`

Expected: FAIL on registrar symbols.

- [ ] **Step 4: Implement registrar**

Implement structured JSON loading and writing. Use atomic write through a temporary file in the target directory followed by `Path.replace(...)`.

- [ ] **Step 5: Verify**

Run: `uv run --python 3.12 pytest tests/test_mcp_config_registration.py tests/test_mcp_config_examples.py -q`

Expected: PASS. Existing source-checkout example tests must still pass.

- [ ] **Step 6: Commit**

```bash
git add src/vault_graph/mcp/mcp_config_registration.py tests/test_mcp_config_registration.py
git commit -m "feat(mcp): add explicit config registration"
```

### Task 4: Add `vg mcp config` And `vg mcp register`

**Files:**

- Modify: `src/vault_graph/cli/main.py`
- Test: `tests/test_cli_mcp_config.py`
- Test: `tests/test_cli_mcp_register.py`
- Test: `tests/test_cli_surface_boundary.py`

- [ ] **Step 1: Write failing CLI tests**

Add tests:

- `test_cli_mcp_config_prints_codex_stdio_config`
- `test_cli_mcp_config_does_not_write_files`
- `test_cli_mcp_register_writes_explicit_config_path`
- `test_cli_mcp_register_dry_run_writes_nothing`
- `test_cli_mcp_register_reports_backup_path_when_replacing`
- `test_cli_mcp_register_rejects_unsupported_agent`

Run: `uv run --python 3.12 pytest tests/test_cli_mcp_config.py tests/test_cli_mcp_register.py -q`

Expected: FAIL because `mcp` Typer sub-app does not exist.

- [ ] **Step 2: Add Typer sub-app**

Add near the existing `vault_app`:

```python
mcp_app = typer.Typer(no_args_is_help=True)
app.add_typer(mcp_app, name="mcp")
```

Add commands:

```python
@mcp_app.command("config")
def mcp_config(...): ...

@mcp_app.command("register")
def mcp_register(...): ...
```

`--print` is required for `mcp config` in this first implementation. If omitted, print `mcp_config_requires_print` and exit `1`.

- [ ] **Step 3: Render outputs**

Text output requirements:

- `mcp config`: print JSON only to stdout.
- `mcp register`: print `agent`, `config_path`, `server_name`, `changed`, and `backup_path` when present.
- Domain errors print to stdout like current non-server CLI commands.

- [ ] **Step 4: Verify**

Run: `uv run --python 3.12 pytest tests/test_cli_mcp_config.py tests/test_cli_mcp_register.py tests/test_cli_surface_boundary.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/vault_graph/cli/main.py tests/test_cli_mcp_config.py tests/test_cli_mcp_register.py tests/test_cli_surface_boundary.py
git commit -m "feat(cli): add mcp config commands"
```

### Task 5: Add Setup Service

**Files:**

- Create: `src/vault_graph/app/setup_service.py`
- Test: `tests/test_setup_service.py`

- [ ] **Step 1: Write failing setup service tests**

Add tests:

- `test_setup_dry_run_writes_nothing`
- `test_setup_creates_catalog_and_runs_index`
- `test_setup_is_idempotent_for_same_vault_root`
- `test_setup_rejects_state_inside_vault`
- `test_setup_rejects_existing_vault_id_conflict`
- `test_setup_rejects_missing_vault_id_in_existing_catalog`
- `test_setup_with_agent_prints_config_when_no_config_path`
- `test_setup_with_agent_registers_explicit_config_path`

Run: `uv run --python 3.12 pytest tests/test_setup_service.py -q`

Expected: FAIL because `setup_service.py` does not exist.

- [ ] **Step 2: Implement `SetupService`**

Use `CatalogService`, `LocalIndexServiceFactory`, `McpConfigRenderer`, and `McpConfigRegistrar`. Keep constructor defaults simple:

```python
class SetupService:
    def __init__(
        self,
        *,
        index_factory: LocalIndexServiceFactory | None = None,
        config_renderer: McpConfigRenderer | None = None,
        config_registrar: McpConfigRegistrar | None = None,
    ) -> None: ...
```

- [ ] **Step 3: Verify**

Run: `uv run --python 3.12 pytest tests/test_setup_service.py tests/test_read_only_boundary.py -q`

Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add src/vault_graph/app/setup_service.py tests/test_setup_service.py
git commit -m "feat(app): add setup orchestration service"
```

### Task 6: Add `vg setup`

**Files:**

- Modify: `src/vault_graph/cli/main.py`
- Test: `tests/test_cli_setup.py`
- Test: `tests/test_cli_surface_boundary.py`

- [ ] **Step 1: Write failing CLI setup tests**

Add tests:

- `test_cli_setup_defaults_state_to_home_vault_graph`
- `test_cli_setup_runs_index_and_prints_summary`
- `test_cli_setup_dry_run_does_not_create_state`
- `test_cli_setup_rejects_state_inside_vault`
- `test_cli_setup_with_agent_prints_mcp_config_when_no_config_path`
- `test_cli_setup_with_agent_writes_explicit_mcp_config_path`

Run: `uv run --python 3.12 pytest tests/test_cli_setup.py -q`

Expected: FAIL because command does not exist.

- [ ] **Step 2: Add command**

Add:

```python
@app.command()
def setup(
    vault: Path = typer.Option(..., "--vault", help="Vault repository root."),
    state: Path = typer.Option(Path("~/.vault-graph"), "--state", help="Vault Graph state path."),
    vault_id: str = typer.Option("default", "--vault-id", help="Registered Vault ID."),
    agent: str | None = typer.Option(None, "--agent", help="Agent config target. Supported: codex."),
    mcp_config_path: Path | None = typer.Option(None, "--mcp-config-path", help="Explicit agent MCP config path."),
    print_mcp_config: bool = typer.Option(False, "--print-mcp-config", help="Print MCP config JSON."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Validate and print plan without writes."),
) -> None:
    ...
```

- [ ] **Step 3: Render setup report**

Text output must include:

- `vault_id`
- `vault_path`
- `state`
- `catalog_created`
- `catalog_changed`
- `index_exit_code`
- metadata changed/unchanged/deleted counts when indexing ran
- MCP config JSON when requested or implied by `--agent`
- warnings

- [ ] **Step 4: Verify**

Run: `uv run --python 3.12 pytest tests/test_cli_setup.py tests/test_cli_surface_boundary.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/vault_graph/cli/main.py tests/test_cli_setup.py tests/test_cli_surface_boundary.py
git commit -m "feat(cli): add one-command setup"
```

### Task 7: Add Watch Service

**Files:**

- Create: `src/vault_graph/app/watch_service.py`
- Test: `tests/test_watch_service.py`

- [ ] **Step 1: Write failing watch service tests**

Add tests:

- `test_watch_runs_repeated_incremental_index_until_stopped`
- `test_watch_reports_vector_and_graph_failures_without_crashing`
- `test_watch_returns_nonzero_when_first_iteration_cannot_start`
- `test_watch_returns_zero_on_keyboard_interrupt_after_iteration`

Run: `uv run --python 3.12 pytest tests/test_watch_service.py -q`

Expected: FAIL because module does not exist.

- [ ] **Step 2: Implement `WatchService`**

Use injected `sleep` and `stop_requested` for deterministic tests. Convert `IndexRunReport` to `WatchIterationReport` without exposing full index internals to CLI.

- [ ] **Step 3: Verify**

Run: `uv run --python 3.12 pytest tests/test_watch_service.py -q`

Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add src/vault_graph/app/watch_service.py tests/test_watch_service.py
git commit -m "feat(app): add polling watch service"
```

### Task 8: Add `vg watch`

**Files:**

- Modify: `src/vault_graph/cli/main.py`
- Test: `tests/test_cli_watch.py`
- Test: `tests/test_cli_surface_boundary.py`

- [ ] **Step 1: Write failing CLI watch tests**

Add tests:

- `test_cli_watch_rejects_conflicting_scope_flags`
- `test_cli_watch_rejects_nonpositive_interval`
- `test_cli_watch_uses_active_vault_by_default`
- `test_cli_watch_uses_all_vaults_when_requested`
- `test_cli_watch_prints_iteration_report`
- `test_cli_watch_does_not_mutate_vault_files`

Run: `uv run --python 3.12 pytest tests/test_cli_watch.py -q`

Expected: FAIL because command does not exist.

- [ ] **Step 2: Add command**

Add:

```python
@app.command()
def watch(
    state: Path = typer.Option(Path(".vault-graph"), "--state", help="Vault Graph state path."),
    vault_id: str | None = typer.Option(None, "--vault-id", help="Watch one registered Vault ID."),
    all_vaults: bool = typer.Option(False, "--all-vaults", help="Watch all enabled registered Vaults."),
    interval: float = typer.Option(2.0, "--interval", help="Polling interval in seconds."),
    full: bool = typer.Option(False, "--full", help="Run full rebuild each iteration."),
) -> None:
    ...
```

Use existing scope flag behavior from `index`.

- [ ] **Step 3: Verify**

Run: `uv run --python 3.12 pytest tests/test_cli_watch.py tests/test_read_only_boundary.py -q`

Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add src/vault_graph/cli/main.py tests/test_cli_watch.py tests/test_cli_surface_boundary.py
git commit -m "feat(cli): add watch command"
```

### Task 9: Add HTTP Dependencies, Config, And Error Mapping

**Files:**

- Modify: `pyproject.toml`
- Create: `src/vault_graph/http/__init__.py`
- Create: `src/vault_graph/http/http_errors.py`
- Create: `src/vault_graph/http/http_server.py`
- Test: `tests/test_http_errors.py`

- [ ] **Step 1: Write failing HTTP config tests**

Add tests:

- `test_http_config_defaults_to_localhost`
- `test_http_config_rejects_remote_host`
- `test_http_config_rejects_invalid_port`
- `test_http_error_mapping_sanitizes_domain_errors`

Run: `uv run --python 3.12 pytest tests/test_http_errors.py -q`

Expected: FAIL because HTTP package does not exist.

- [ ] **Step 2: Add dependencies**

Add to `[project].dependencies`:

```toml
"fastapi>=0.115,<1",
"uvicorn>=0.30,<1",
```

- [ ] **Step 3: Implement config and errors**

Add `HttpServerConfig`, `HttpErrorPayload`, `HttpRequestError`, and `map_exception_to_http_error(...)`.

- [ ] **Step 4: Verify**

Run: `uv run --python 3.12 pytest tests/test_http_errors.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml src/vault_graph/http/__init__.py src/vault_graph/http/http_errors.py src/vault_graph/http/http_server.py tests/test_http_errors.py
git commit -m "feat(http): add local server config"
```

### Task 10: Add HTTP Serialization And Service Factory

**Files:**

- Create: `src/vault_graph/http/http_serialization.py`
- Create: `src/vault_graph/http/http_service_factory.py`
- Test: `tests/test_http_serialization.py`

- [ ] **Step 1: Write failing serialization tests**

Add tests:

- `test_http_search_payload_preserves_evidence_fields`
- `test_http_status_payload_preserves_selected_scope`
- `test_http_memory_payload_preserves_warnings`
- `test_http_error_payload_has_stable_shape`

Run: `uv run --python 3.12 pytest tests/test_http_serialization.py -q`

Expected: FAIL because serialization module does not exist.

- [ ] **Step 2: Implement serialization**

Serialize domain objects to JSON-compatible dictionaries. Do not import from `vault_graph.mcp`.

- [ ] **Step 3: Implement service factory wrapper**

`HttpServiceFactory` should hold a `ReadOnlyServiceFactory` and expose only route-needed service methods. It must not provide indexing.

Required signature:

```python
class HttpServiceFactory:
    def __init__(
        self,
        *,
        state_path: Path,
        read_only_factory: ReadOnlyServiceFactory | None = None,
    ) -> None: ...

    def open_read_only(self) -> ReadOnlyServices: ...
    def open_retrieval_service(self, *, include_graph: bool = False) -> RetrievalService: ...
    def open_context_pack_builder(self, *, include_graph: bool = False) -> ContextPackBuilder: ...
    def open_status_service(self) -> IndexService: ...
    def open_graph_retrieval_service(self) -> GraphRetrievalService: ...
    def open_project_memory_service(self) -> ProjectMemoryService: ...
    def open_issue_memory_service(self) -> IssueMemoryService: ...
    def open_timeline_memory_service(self) -> TimelineMemoryService: ...
```

- [ ] **Step 4: Verify import boundary**

Run: `uv run --python 3.12 pytest tests/test_http_serialization.py tests/test_mcp_import_boundaries.py -q`

Expected: PASS and no HTTP-to-MCP dependency.

- [ ] **Step 5: Commit**

```bash
git add src/vault_graph/http/http_serialization.py src/vault_graph/http/http_service_factory.py tests/test_http_serialization.py tests/test_mcp_import_boundaries.py
git commit -m "feat(http): add read-only serialization"
```

### Task 11: Add HTTP App Routes

**Files:**

- Modify: `src/vault_graph/http/http_server.py`
- Test: `tests/test_http_server.py`
- Test: `tests/test_http_read_only_boundary.py`

- [ ] **Step 1: Write failing route tests**

Add tests:

- `test_http_health_loads_catalog`
- `test_http_status_calls_status_service`
- `test_http_search_calls_retrieval_service`
- `test_http_context_calls_context_pack_builder`
- `test_http_related_calls_graph_service`
- `test_http_decision_trace_calls_graph_service`
- `test_http_memory_routes_call_memory_services`
- `test_http_explain_result_uses_explanation_service`
- `test_http_routes_return_stable_error_payload`
- `test_http_requests_do_not_mutate_vault_or_create_missing_state`

Run: `uv run --python 3.12 pytest tests/test_http_server.py tests/test_http_read_only_boundary.py -q`

Expected: FAIL because routes are not implemented.

- [ ] **Step 2: Implement FastAPI app**

Use `fastapi.FastAPI`. Add routes listed in the component spec. Use request dictionaries or small local dataclasses; avoid Pydantic models unless they materially simplify validation.

- [ ] **Step 3: Add `/ask` only if answer service exists**

If the companion Ask plan has already created `AnswerService`, add `POST /ask`. If not, leave `/ask` absent and document it as blocked by Task 0 dependency. Do not implement a placeholder route that returns fake answers.

- [ ] **Step 4: Verify**

Run: `uv run --python 3.12 pytest tests/test_http_server.py tests/test_http_read_only_boundary.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/vault_graph/http/http_server.py tests/test_http_server.py tests/test_http_read_only_boundary.py
git commit -m "feat(http): add read-only local routes"
```

### Task 12: Wire `vg serve --http`

**Files:**

- Modify: `src/vault_graph/cli/main.py`
- Modify: `tests/test_cli_mcp_serve.py`
- Create: `tests/test_cli_http_serve.py`

- [ ] **Step 1: Write failing CLI HTTP tests**

Add tests:

- `test_serve_http_delegates_to_run_http_server`
- `test_serve_http_defaults_to_localhost`
- `test_serve_http_rejects_remote_host`
- `test_serve_rejects_multiple_transports`
- `test_serve_requires_selected_transport_mentions_mcp_or_http`

Run: `uv run --python 3.12 pytest tests/test_cli_http_serve.py tests/test_cli_mcp_serve.py -q`

Expected: FAIL because `serve --http` still returns `http_transport_not_supported_in_phase_5a`.

- [ ] **Step 2: Update CLI serve command**

Add options:

```python
host: str = typer.Option("127.0.0.1", "--host", help="HTTP bind host."),
port: int = typer.Option(8765, "--port", help="HTTP bind port."),
```

Behavior:

- `--mcp --http` remains invalid.
- `--http` creates `HttpServerConfig` and calls `run_http_server`.
- no selected transport prints `select one server transport: --mcp or --http`.
- server startup errors print to stderr.

- [ ] **Step 3: Verify**

Run: `uv run --python 3.12 pytest tests/test_cli_http_serve.py tests/test_cli_mcp_serve.py -q`

Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add src/vault_graph/cli/main.py tests/test_cli_http_serve.py tests/test_cli_mcp_serve.py
git commit -m "feat(cli): enable local http serving"
```

### Task 13: Update CLI Surface After Ask Lands

**Files:**

- Modify: `tests/test_cli_surface_boundary.py`
- Modify: `tests/test_mcp_tools.py`
- Modify: `README.md`
- Modify: `docs/SPEC.md`
- Modify: `docs/FEATURES.md`

- [ ] **Step 1: Execute companion Ask implementation plan first**

Run the plan at `docs/superpowers/plans/2026-06-26-evidence-first-ask-and-reasoning.md` through its verification gate.

Required signals:

- `uv run --python 3.12 vg --help` shows `ask`.
- MCP tool registry includes `ask_vault`.
- Answer tests pass.

- [ ] **Step 2: Update CLI/MCP surface tests**

Update:

- `test_cli_surface_exposes_context_but_not_answer_command` should become `test_cli_surface_exposes_ask_and_setup_commands`.
- `test_register_mcp_tools_registers_exact_phase_6c_tools` should be renamed and include `ask_vault`.

- [ ] **Step 3: Update docs**

Move implemented commands out of README/SPEC/FEATURES TODO sections only after their tests pass:

- `vg ask`
- `vg mcp config`
- `vg mcp register`
- `vg setup`
- `vg watch`
- `vg serve --http`

If a command has not landed yet, keep it in TODO.

- [ ] **Step 4: Verify docs and command help**

Run:

```bash
git diff --check
uv run --python 3.12 vg --help
uv run --python 3.12 vg mcp --help
uv run --python 3.12 vg serve --help
rg -n "CLI TODO|not current commands|http_transport_not_supported_in_phase_5a|ask is not present" README.md docs/SPEC.md docs/FEATURES.md tests
```

Expected:

- diff check passes.
- help output includes implemented commands.
- remaining TODO wording matches only commands not yet implemented.

- [ ] **Step 5: Commit**

```bash
git add README.md docs/SPEC.md docs/FEATURES.md tests/test_cli_surface_boundary.py tests/test_mcp_tools.py
git commit -m "docs(cli): mark implemented command surfaces"
```

### Task 14: Full Release Verification

**Files:**

- No new source files unless verification finds a defect.

- [ ] **Step 1: Run full static checks**

Run:

```bash
uv run --python 3.12 ruff check src tests
uv run --python 3.12 mypy src tests
```

Expected: PASS.

- [ ] **Step 2: Run full tests**

Run:

```bash
uv run --python 3.12 pytest
VG_RUN_MCP_STDIO_SMOKE=1 uv run --python 3.12 pytest tests/test_mcp_stdio_smoke.py -q
```

Expected: PASS.

- [ ] **Step 3: Run command smoke checks**

Run:

```bash
uv run --python 3.12 vg --help
uv run --python 3.12 vg mcp --help
uv run --python 3.12 vg setup --help
uv run --python 3.12 vg watch --help
uv run --python 3.12 vg serve --help
```

Expected: each command exits `0` and prints help.

- [ ] **Step 4: Run read-only smoke over fixture Vault**

Create a temporary fixture Vault, run setup/index/search/context/status, and assert file hashes under the Vault root are unchanged.

Expected: Vault files unchanged; only Vault Graph state and optional explicit config path changed.

- [ ] **Step 5: Commit fixes or finish**

If verification required code changes, commit them:

```bash
git add <changed-files>
git commit -m "test(cli): cover todo command release gates"
```

## Error Handling And Edge Cases

Shared CLI:

- `conflicting_scope_flags`: `--vault-id` and `--all-vaults` together.
- `unsupported_format`: unsupported text/json format.
- `catalog_missing`: commands requiring initialized state fail without creating state.
- `state_inside_vault`: any write-capable command rejects state path inside a registered Vault.
- `unknown_vault_id`: scope resolution fails through `VaultCatalog`.

MCP config:

- `unsupported_agent`: only `codex` is supported.
- `mcp_config_parent_missing`: parent directory missing.
- `mcp_config_invalid_json`: existing config cannot be parsed.
- `mcp_config_not_changed`: existing entry already matches; report `changed=False`.
- `dry_run`: no writes, no backup.

Setup:

- `setup_vault_id_conflict`: existing `vault_id` points elsewhere.
- `setup_vault_id_missing`: existing catalog lacks requested ID.
- Index failure after setup: report setup/index split clearly and exit nonzero.
- MCP registration failure after successful indexing: report indexing succeeded and registration failed; do not roll back state.

Watch:

- Nonpositive interval returns exit `1`.
- First iteration configuration/store failure returns exit `1`.
- Recoverable vector/graph failures are warnings with visible nonzero iteration status.
- Keyboard interrupt exits cleanly after printing last iteration.

HTTP:

- `remote_http_not_supported`: host other than `127.0.0.1`.
- Invalid port fails before starting server.
- Missing catalog returns JSON error, not traceback.
- No route writes derived state or Vault content.

## Tests

Focused test commands per slice:

```bash
uv run --python 3.12 pytest tests/test_mcp_config_registration.py -q
uv run --python 3.12 pytest tests/test_cli_mcp_config.py tests/test_cli_mcp_register.py -q
uv run --python 3.12 pytest tests/test_setup_service.py tests/test_cli_setup.py -q
uv run --python 3.12 pytest tests/test_watch_service.py tests/test_cli_watch.py -q
uv run --python 3.12 pytest tests/test_http_errors.py tests/test_http_serialization.py tests/test_http_server.py tests/test_cli_http_serve.py -q
uv run --python 3.12 pytest tests/test_read_only_boundary.py tests/test_http_read_only_boundary.py -q
```

Full gate:

```bash
uv run --python 3.12 ruff check src tests
uv run --python 3.12 mypy src tests
uv run --python 3.12 pytest
VG_RUN_MCP_STDIO_SMOKE=1 uv run --python 3.12 pytest tests/test_mcp_stdio_smoke.py -q
```

## Risks And Mitigations

- Risk: `vg setup --agent` could feel like it secretly edits agent config.
  Mitigation: write only when `--mcp-config-path` is explicit; otherwise print config and warning.
- Risk: HTTP duplicates MCP serialization and drifts.
  Mitigation: keep HTTP serialization small, route-owned, and covered by contract tests; avoid importing MCP from HTTP.
- Risk: HTTP serving broadens exposure.
  Mitigation: localhost only, no CORS, no auth bypass, no filesystem routes.
- Risk: `watch` becomes complex and platform-specific.
  Mitigation: start with polling through `IndexService`; defer native watchers.
- Risk: app-level factory extraction changes MCP import behavior.
  Mitigation: preserve existing lazy import tests and add app factory tests before behavior changes.
- Risk: command documentation marks features implemented too early.
  Mitigation: move README/SPEC/FEATURES entries only after slice acceptance tests pass.

## Validation Review

Subagent spawning was not used for this plan because the current tool policy permits spawning only when the user explicitly requests subagents or delegation. The same review angles were applied inline and defects were folded into the plan.

- Security/read-only: Plan keeps Vault writes forbidden, makes agent config writes explicit, rejects remote HTTP bind hosts, and uses existing path guards for state writes.
- Performance/scalability: Setup reuses incremental indexing; watch uses polling over `IndexService`; HTTP routes are read-only and do not trigger indexing or model downloads.
- Testability: Each command has a service boundary and deterministic tests with fake factories, injected sleeps, and explicit CLI runners.
- Maintainability/deep modules: Shared service construction moves out of CLI/MCP adapters; setup/watch are app services; HTTP remains an adapter; answer internals remain in the companion answer module.
- Agent ergonomics: `vg setup`, `vg mcp config`, and `vg mcp register` make MCP use reproducible without hiding installation vs registration.

## Open Decisions

None. The plan follows accepted decisions in `docs/DECISIONS.md`: use setup and explicit MCP registration as the onboarding target, keep PyPI separate from current source-checkout usage, and make evidence-first ask the next core implementation target.

## Patch And Decision Logs

No `docs/PATCH_LOG.md` or `docs/DECISIONS.md` update is required for writing this plan. Add a patch log entry only if implementation review finds a mismatch, defect, or risk that changes this plan or the source SPEC. Add a decision entry only after the user accepts a new product, architecture, or policy decision.
