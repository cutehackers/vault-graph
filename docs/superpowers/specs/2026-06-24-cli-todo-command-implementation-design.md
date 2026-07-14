# CLI Command Implementation SPEC

Status: Active implementation design

Date: 2026-06-24

Scope: Unimplemented CLI targets from `docs/SPEC.md` section 17 and
`README.md`. `vg ask` is the next core product implementation target; the other
commands remain setup, watch, MCP registration, and HTTP adapter targets. The
canonical answer-layer contract for `vg ask` and MCP `ask_vault` lives in
`docs/superpowers/specs/2026-06-25-evidence-first-ask-and-reasoning-design.md`.

## 1. Purpose

This SPEC turns the currently documented unimplemented command targets into an
implementation-ready design.

Next core target:

```bash
vg ask "question"
```

Remaining command targets:

```bash
vg setup --vault /path/to/vault --agent codex --mcp
vg mcp register --agent codex --state ~/.vault-graph --config-path /path/to/agent-config.json
vg mcp config --agent codex --state ~/.vault-graph --print
vg watch
vg serve --http
```

The goal is not to expand product scope. The goal is to make the already
reserved user-facing commands implementable without weakening Vault Graph's core
values: Vault stays the source of truth, Vault Graph state is derived and
rebuildable, outputs are evidence-first, and all adapters stay read-only over
Vault content.

## 2. Current State

Current CLI commands are:

```text
init
index
context
search
related
decision-trace
status
serve
vault
```

`vg serve --http` is accepted by the parser but exits with
`http_transport_not_supported_in_phase_5a`. It is therefore a reserved transport,
not an implemented feature.

The missing command surfaces are:

- `vg setup`
- `vg mcp config`
- `vg mcp register`
- `vg watch`
- `vg ask`
- the real read-only behavior behind `vg serve --http`

## 3. Design Principles

- Keep setup convenient without hiding what it does. A successful setup must
  print the Vault ID, Vault path, state path, index result, and MCP registration
  result.
- Keep installation separate from MCP registration. Installing Vault Graph makes
  `vg` available; MCP registration writes or prints an agent config that starts
  `vg serve --mcp`.
- Keep external config writes explicit. Agent config registration may write
  outside the Vault Graph state directory only when the user provides a config
  path or an agent adapter has a tested safe target. All such writes need a
  backup or dry-run path.
- Keep `watch` boring. The first implementation should use periodic incremental
  indexing through `IndexService`; a native filesystem watcher can be added later
  behind the same service boundary.
- Keep `ask` evidence-first. The first implementation should use an extractive
  answer composer over retrieved evidence and context-pack evidence. Hosted LLM
  answer generation is not required for the default workflow.
- Keep HTTP as an adapter. HTTP routes must call application services and reuse
  CLI/MCP serializers where practical; they must not query stores directly.

## 4. Implementation Slices

| Slice | Command Surface | Goal | Dependencies |
| --- | --- | --- | --- |
| CLI-A | `vg mcp config`, `vg mcp register` | Make agent MCP configuration reproducible and safe | existing MCP config example |
| CLI-B | `vg setup` | One-command local onboarding over init, index, and optional MCP registration | CLI-A, current `init` and `index` services |
| CLI-C | `vg watch` | Periodic incremental indexing for registered Vault scopes | current `IndexService` |
| CLI-D | `vg serve --http` | Local read-only JSON adapter over existing application services | current retrieval, graph, context, memory services |
| CLI-E | `vg ask` | Evidence-first answer rendering with citations and warnings | current retrieval, context, explanation services |

The recommended implementation order is now CLI-E first, then CLI-A, CLI-B,
CLI-C, and CLI-D. `vg ask` is the product-value slice; setup, watch, and HTTP
improve onboarding and adapters around the existing services. The answer DTO
should be shared by CLI, MCP, and HTTP when those adapters expose ask behavior.

## 5. Directory And File Structure

Add:

```text
src/vault_graph/app/setup_service.py
src/vault_graph/app/watch_service.py
src/vault_graph/answer/__init__.py
src/vault_graph/answer/answer_contracts.py
src/vault_graph/answer/answer_service.py
src/vault_graph/answer/extractive_answer_composer.py
src/vault_graph/http/__init__.py
src/vault_graph/http/http_errors.py
src/vault_graph/http/http_serialization.py
src/vault_graph/http/http_server.py
src/vault_graph/http/http_service_factory.py
src/vault_graph/mcp/mcp_config_registration.py
tests/test_cli_setup.py
tests/test_cli_mcp_config.py
tests/test_cli_mcp_register.py
tests/test_cli_watch.py
tests/test_cli_ask.py
tests/test_cli_http_serve.py
tests/test_answer_service.py
tests/test_answer_read_only_boundary.py
tests/test_http_server.py
tests/test_http_read_only_boundary.py
```

Modify:

```text
pyproject.toml
src/vault_graph/cli/main.py
src/vault_graph/mcp/mcp_config_examples.py
tests/test_cli_mcp_serve.py
tests/test_cli_surface_boundary.py
tests/test_mcp_config_examples.py
docs/FEATURES.md
docs/SPEC.md
README.md
```

Dependency changes:

- Do not add a filesystem watcher dependency for CLI-C. Use the standard
  library plus `IndexService` polling first.
- Add HTTP dependencies only for CLI-D. Use `fastapi>=0.115,<1` and
  `uvicorn>=0.30,<1` unless the implementation plan finds an already accepted
  project dependency with equivalent modern support.

## 6. CLI-A: MCP Config And Registration

### 6.1 CLI Surface

```bash
vg mcp config --agent codex --state ~/.vault-graph --print
vg mcp register --agent codex --state ~/.vault-graph --config-path /path/to/agent-config.json
vg mcp register --agent codex --state ~/.vault-graph --config-path /path/to/agent-config.json --dry-run
```

`--agent` initially supports only `codex`. Unsupported agents return
`unsupported_agent` and list supported agents.

`vg mcp config` prints only. It never writes files.

`vg mcp register` writes only the selected agent configuration file. It must not
write to Vault, Vault Graph indexes, or arbitrary paths discovered implicitly.

### 6.2 Service Boundary

`src/vault_graph/mcp/mcp_config_registration.py` owns this boundary.

```python
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

class McpConfigRenderer:
    def render(self, request: McpConfigRequest) -> str: ...

class McpConfigRegistrar:
    def register(self, request: McpRegistrationRequest) -> McpRegistrationReport: ...
```

### 6.3 Registration Rules

- Expand and resolve `state_path` before rendering config.
- The rendered server command is the local stdio command:

  ```bash
  vg serve --mcp --state <resolved-state-path>
  ```

- The current source-checkout README example may still use `uv run --python
  3.12 vg ...` for users running from a checkout. Registered agent config uses
  the installed `vg` command.
- `vg setup --mcp` may auto-register Codex at `$CODEX_HOME/config.toml` or
  `~/.codex/config.toml`. This is allowed only behind the explicit `--mcp` flag.
- Existing JSON config files must be parsed as structured JSON. Existing Codex
  TOML config files must be parsed as valid TOML before updating the bounded
  `[mcp_servers.vault-graph]` section.
- Preserve unrelated agent config entries.
- If the target server entry already matches the rendered payload, report
  `changed=False`.
- If the target server entry exists with different content, write a backup
  beside the config file before replacing only the `vault-graph` server entry.
- If `--dry-run` is set, print the planned payload and backup path but write
  nothing.
- If the parent directory does not exist, fail with
  `mcp_config_parent_missing`.
- If JSON or TOML parsing fails, fail with `mcp_config_invalid_json` or
  `mcp_config_invalid_toml` and write nothing.

## 7. CLI-B: Setup

### 7.1 CLI Surface

```bash
vg setup --vault /path/to/vault
vg setup --vault /path/to/vault --state ~/.vault-graph
vg setup --vault /path/to/vault --vault-id main
vg setup --vault /path/to/vault --agent codex --mcp
vg setup --vault /path/to/vault --agent codex --mcp-config-path /path/to/agent-config.json
vg setup --vault /path/to/vault --agent codex --print-mcp-config
vg setup --vault /path/to/vault --dry-run
```

For `vg setup`, omitted `--state` defaults to `~/.vault-graph`. Existing
commands keep their current `.vault-graph` default unless separately changed.

### 7.2 Service Boundary

`src/vault_graph/app/setup_service.py` owns setup orchestration so the CLI stays
thin.

```python
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

SetupAgent = Literal["codex"]

@dataclass(frozen=True)
class SetupRequest:
    vault_root: Path
    state_path: Path
    vault_id: str = "default"
    agent: SetupAgent | None = None
    register_mcp: bool = False
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

### 7.3 Setup Flow

1. Resolve `vault_root` and `state_path`.
2. Reject a `state_path` inside the registered Vault root.
3. If `dry_run=True`, validate inputs and produce a plan without creating state,
   indexes, cache directories, or agent config.
4. Create or load the catalog.
5. If no catalog exists, create a catalog with the requested `vault_id`.
6. If a catalog exists and the same `vault_id` points to the same Vault root,
   treat setup as idempotent.
7. If a catalog exists and the requested `vault_id` points elsewhere, fail with
   `setup_vault_id_conflict`. Do not silently replace a Vault root.
8. Run index apply for the selected Vault.
9. If `agent` is omitted, stop after indexing.
10. If `agent` is present and `register_mcp` is true without
    `mcp_config_path`, resolve the Codex config path to
    `$CODEX_HOME/config.toml` or `~/.codex/config.toml`.
11. If `agent` is present and an explicit or resolved MCP config path is
    present, call `McpConfigRegistrar`.
12. If `agent` is present and `print_mcp_config=True`, include the rendered MCP
    config in output.
13. If `agent` is present with neither MCP registration path nor
    `print_mcp_config`, print the MCP config and add a warning that no agent
    config file was written.

This preserves the easy setup path while avoiding hidden writes: automatic Codex
registration happens only when the user passes `--mcp`.

## 8. CLI-C: Watch

### 8.1 CLI Surface

```bash
vg watch
vg watch --state ~/.vault-graph
vg watch --vault-id main
vg watch --all-vaults
vg watch --interval 2.0
vg watch --full
```

### 8.2 Service Boundary

`src/vault_graph/app/watch_service.py` owns watch behavior.

```python
from dataclasses import dataclass
from typing import Callable

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
    def run(
        self,
        request: WatchRequest,
        *,
        stop_requested: Callable[[], bool],
        on_iteration: Callable[[WatchIterationReport], None],
    ) -> int: ...
```

### 8.3 Watch Rules

- Use the same scope flags as `vg index`.
- Run `IndexService.run_apply(...)` repeatedly.
- Sleep `interval_seconds` between iterations.
- Exit cleanly on `KeyboardInterrupt`.
- Continue after recoverable vector or graph failures, print warnings, and keep
  the last nonzero status visible.
- Return nonzero only when the watch loop fails before the first iteration or is
  interrupted by an unrecoverable configuration/store error.
- Do not watch or mutate Vault Git metadata.
- Do not write outside the state path.

The first implementation intentionally avoids native filesystem events. This
keeps the command portable, testable, and aligned with the rebuildable indexing
model. A later implementation can replace the polling trigger without changing
`WatchService`.

## 9. CLI-D: HTTP Serving

### 9.1 CLI Surface

```bash
vg serve --http
vg serve --http --state ~/.vault-graph
vg serve --http --host 127.0.0.1 --port 8765
```

Default host must be `127.0.0.1`. Binding to `0.0.0.0` must fail unless a future
authentication and remote-hosting design is accepted.

### 9.2 Package Boundary

`src/vault_graph/http/` is an adapter package like `src/vault_graph/mcp/`.

```python
from dataclasses import dataclass
from pathlib import Path

@dataclass(frozen=True)
class HttpServerConfig:
    state_path: Path
    host: str = "127.0.0.1"
    port: int = 8765

def create_http_app(config: HttpServerConfig) -> object: ...
def run_http_server(config: HttpServerConfig) -> None: ...
```

The concrete app type may be FastAPI's `FastAPI`, but the CLI should depend only
on `create_http_app(...)` / `run_http_server(...)`.

### 9.3 Initial Routes

Expose routes only for services that already exist when CLI-D is implemented:

```text
GET  /health
GET  /status
POST /search
POST /context
POST /related
POST /decision-trace
GET  /memory/project
GET  /memory/open-questions
GET  /memory/recent-changes
POST /explain-result
POST /ask        # only after AnswerService exists
```

Route rules:

- Responses are JSON only.
- Request scope uses the same `QueryScope` shape as MCP.
- The adapter opens read-only stores for read routes.
- The adapter must not initialize missing stores or run indexing.
- Errors use stable JSON payloads:

  ```json
  {
    "error": {
      "code": "stale_index",
      "message": "...",
      "recovery_hint": "Run vg index --state ..."
    }
  }
  ```

- HTTP must not expose filesystem browsing or full-Vault dumps.
- CORS is disabled by default.
- No route may mutate Vault content or Vault Graph derived state.

## 10. CLI-E: Ask

### 10.1 CLI Surface

```bash
vg ask "Why did we adopt GraphRAG?"
vg ask --vault-id main "Why did we adopt GraphRAG?"
vg ask --all-vaults "What changed in the indexing design?"
vg ask --include-graph "Why did we keep graph expansion opt-in?"
vg ask --format json "question"
```

Default output is text. JSON output exposes the canonical answer contract.

### 10.2 Answer Package Boundary

`src/vault_graph/answer/` owns MCP-free and HTTP-free answer behavior. Do not
define a second answer DTO in the CLI layer. Use the canonical contracts from
`docs/superpowers/specs/2026-06-25-evidence-first-ask-and-reasoning-design.md`:

- `AnswerRequest`
- `AnswerResponse`
- `AnswerService.ask(...)`
- `EvidencePlanner`
- `AnswerComposer`
- `CitationGuard`
- `AnswerRenderer`

### 10.3 Default Composer

The first composer is `ExtractiveAnswerComposer`.

Rules:

- It must not call hosted LLMs.
- It must not invent facts absent from evidence.
- It may quote or paraphrase short evidence snippets already returned by
  retrieval/context-pack evidence.
- If evidence is weak or conflicting, it returns `answer_status="partial"` or
  `answer_status="insufficient_evidence"` with warnings.
- It separates inferred links from stated facts.
- It always includes a suggested durable follow-up when a human should update
  Vault through the Vault workflow.

Future LLM-backed composers must implement `AnswerComposer`, be opt-in, preserve
the same `AnswerResponse`, and pass the same citation tests. They are not
required for this CLI TODO implementation.

## 11. State Management And Data Flow

### Setup

```text
CLI args
  -> SetupRequest
  -> SetupService
  -> CatalogService create/load
  -> IndexService.run_apply
  -> optional McpConfigRenderer or McpConfigRegistrar
  -> SetupReport
  -> CLI text/json rendering
```

Writes:

- Vault Graph state and indexes under `state_path`
- optional agent config file selected by `--mcp-config-path`

Forbidden writes:

- registered Vault root
- Vault `raw/`, `wiki/`, `docs/`, `scratch/`
- Vault Git metadata
- implicit user config files not passed to the command

### Watch

```text
CLI scope flags
  -> WatchRequest
  -> WatchService loop
  -> IndexService.run_apply
  -> WatchIterationReport
  -> CLI iteration output
```

### Ask

```text
CLI question and scope flags
  -> AnswerRequest
  -> AnswerService.ask
  -> EvidencePlanner
  -> existing retrieval / graph / memory services
  -> AnswerComposer
  -> CitationGuard
  -> AnswerResponse
  -> CLI text/json rendering
```

### HTTP

```text
HTTP request JSON
  -> request DTO and QueryScope mapping
  -> existing application service
  -> shared serializer
  -> JSON response
```

## 12. Error Handling And Edge Cases

### Shared CLI Errors

- `unknown_vault_id`: unknown `--vault-id`
- `conflicting_scope_flags`: both `--vault-id` and `--all-vaults`
- `state_inside_vault`: state path resolves inside registered Vault root
- `catalog_missing`: command requires initialized state
- `unsupported_format`: output format is not `text` or `json`
- `backend_unhealthy`: required local backend cannot be read
- `schema_incompatible`: local state must be rebuilt or migrated

### Setup Errors

- Existing `vault_id` points to a different root: fail without mutation.
- Index partially fails: print index summary and exit nonzero. Keep completed
  metadata/vector/graph status visible.
- MCP registration fails after indexing succeeds: exit nonzero, print that
  Vault setup and indexing succeeded, and include the config payload for manual
  registration.

### MCP Registration Errors

- Missing config parent: fail before writes.
- Invalid JSON: fail before writes.
- Existing server entry differs: write backup before replacement.
- Dry-run: no writes, even if target file exists.

### Watch Errors

- Configuration errors before first iteration return nonzero.
- Recoverable indexing failures are reported per iteration.
- Keyboard interrupt exits cleanly and prints last successful revision when
  available.

### Ask Errors

- Empty question returns `empty_question`.
- No indexed evidence returns an insufficient-evidence answer, not a fluent
  unsupported answer.
- Vector unavailable degrades to keyword evidence with visible warnings.
- Graph unavailable while `--include-graph` is set returns graph warnings but
  may still answer from keyword/vector evidence.

### HTTP Errors

- Host other than `127.0.0.1` returns `remote_http_not_supported`.
- Missing state returns `catalog_missing`.
- HTTP route errors use the shared JSON error payload and do not leak tracebacks
  by default.

## 13. Test Plan

Required focused tests:

- `test_cli_surface_boundary.py`
  - `vg ask` appears only after the answer service slice lands.
  - `setup`, `mcp`, and `watch` appear only after their implementation slices
    land.
  - `serve --http` no longer returns the reserved Phase 5A error after CLI-D.
- `test_cli_mcp_config.py`
  - prints Codex stdio config using resolved state path.
  - does not write files.
- `test_cli_mcp_register.py`
  - writes only the requested config path.
  - preserves unrelated config entries.
  - creates backup before replacing an existing `vault-graph` server entry.
  - dry-run writes nothing.
- `test_cli_setup.py`
  - default state is `~/.vault-graph` for setup.
  - creates catalog and applies index.
  - is idempotent for the same Vault root.
  - rejects state path inside Vault.
  - prints MCP config when no config path is provided.
- `test_cli_watch.py`
  - calls indexing repeatedly until stop callback.
  - handles recoverable vector/graph failures.
  - does not mutate Vault files.
- `test_answer_service.py`
  - returns supported, partial, and insufficient-evidence answers.
  - evidence references include Vault ID, document ID, chunk ID, path, and
    content hash.
  - no answer includes facts absent from provided evidence fixtures.
- `test_answer_read_only_boundary.py`
  - `vg ask` does not mutate Vault or derived state.
- `test_cli_http_serve.py`
  - `--http` starts the HTTP adapter through `run_http_server`.
  - `--mcp --http` remains invalid.
  - non-local host is rejected.
- `test_http_server.py`
  - status/search/context/related/decision-trace/memory routes call services.
  - errors are stable JSON payloads.
- `test_http_read_only_boundary.py`
  - HTTP requests do not mutate Vault or initialize missing stores.

Verification commands:

```bash
uv run --python 3.12 ruff check src tests
uv run --python 3.12 mypy src tests
uv run --python 3.12 pytest
VG_RUN_MCP_STDIO_SMOKE=1 uv run --python 3.12 pytest tests/test_mcp_stdio_smoke.py -q
```

## 14. Documentation Updates

When each slice is implemented:

- Move the implemented command from README `CLI TODO` into `Common Commands`
  only after acceptance tests pass.
- Move the implemented command from `docs/SPEC.md` CLI TODO into the implemented
  CLI block only after acceptance tests pass.
- Update `docs/FEATURES.md` so feature tables distinguish implemented command
  surfaces from future roadmap surfaces.
- Do not add `docs/DECISIONS.md` entries unless a new accepted product or policy
  decision is made.
- Do not add `docs/PATCH_LOG.md` entries unless review or verification finds a
  mismatch, defect, or risk that changes the plan/spec.

## 15. Open Decisions

None. This SPEC follows the accepted 2026-06-24 decision to use setup and MCP
registration as the onboarding target while keeping PyPI publication separate
from current source-checkout usage.

If a future implementation wants `vg mcp register --agent codex` to discover and
write a default Codex config path without `--config-path`, that is a separate
policy decision because it writes outside the Vault Graph state directory.

## 16. Self-Review Notes

- Security: no Vault writes; no hidden user-config writes; HTTP binds only to
  localhost.
- Performance: `watch` reuses incremental indexing; native filesystem events
  are deferred until polling proves insufficient.
- Testability: each command has an application-service boundary and deterministic
  tests that can run without live services.
- Maintainability: adapters stay thin; answer behavior is isolated from CLI,
  MCP, and HTTP surfaces.
- Core value fit: all new outputs remain working context, derived from indexed
  Vault evidence, and safe to delete/rebuild.
