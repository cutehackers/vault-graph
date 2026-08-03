# Round 2 Project Context Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` to execute this plan task-by-task. Each task requires a fresh implementer, a spec-compliance review, and a code-quality review before the next task begins.

**Goal:** Give coding agents one read-only, evidence-linked `explore_project` entry point that combines current repository code with Vault knowledge and reduces ad-hoc prompt/tool orchestration.

**Architecture:** Keep Vault and registered repositories as separate authorities. `CodeQueryService` reads the active code projection and bounded current source lines; `ProjectContextService` composes it with existing Vault retrieval/context-pack services through an explicit repository-to-Vault binding; MCP and harness files remain thin adapters. Every result carries source identity, revision/freshness, extraction status, and explicit warnings. Index/query/context/MCP services never write Vault or repository content; the harness module is the sole exception and may write only an explicitly selected instruction file under Task 4's safety contract.

**Tech Stack:** Python frozen dataclasses, existing SQLite code projection and metadata/graph/context services, Typer CLI, FastMCP, pytest, Ruff, mypy, local-only filesystem tests.

---

## Task 1: Close the Round 1 code-query and CLI boundary

**Files:**

- Create: `src/vault_graph/code_index/code_query_service.py`
- Create: `src/vault_graph/code_index/source_evidence_reader.py`
- Create: `src/vault_graph/cli/code_commands.py`
- Modify: `src/vault_graph/code_index/code_models.py` only when an existing DTO is insufficient
- Modify: `src/vault_graph/app/code_index_factory.py`
- Modify: `src/vault_graph/cli/main.py`
- Modify: `src/vault_graph/code_index/__init__.py`
- Tests: `tests/test_code_query_service.py`, `tests/test_code_query_read_only_boundary.py`, `tests/test_cli_code_index.py`, `tests/test_code_read_only_boundary.py`

- [ ] Reuse the existing frozen request/response DTOs in `src/vault_graph/code_index/code_models.py` (`CodeSymbolSearchRequest`, `CodeSymbolRequest`, `CodeFileOutlineRequest`, `CodeTraversalRequest`, `CodeImpactRequest`, and the CLI request/report DTOs); add only missing bounded fields and never create a parallel DTO family.
- [ ] Define the stable service contract: `search_symbols`, `get_symbol`, `get_file_outline`, `get_callers`, `get_callees`, and `get_impact` each accept the corresponding existing request and return its existing response type. `open_query_service(repository_id: str | None = None)` returns a service scoped to one repository or an aggregate read-only facade for all registered repositories; CLI search uses the aggregate when no ID is supplied. `get_symbol` must return an explicit `ambiguous_symbol` diagnostic when a name resolves to more than one symbol unless the request includes a stable symbol ID plus repository/path disambiguator. `get_file_outline` returns ordered symbol summaries only; expose it through `vg code outline PATH [--repository-id ID] [--format text|json]`. Traversal follows only resolved edges by default, honors `include_uncertain`, treats `direction` as callers/callees, detects cycles, and applies bounded `depth`/`limit` constants.
- [ ] Implement `CodeQueryService` over the read-only `CodeProjectionStore` contract (`search_symbols`, symbol/file lookup, `traverse`, `freshness`/active-generation readback) and `CodeFreshnessService`. Add the explicit repository/path disambiguation fields needed by `CodeSymbolRequest` (or a compatible new request version) and wire corresponding CLI options; adapters must not construct SQLite internals.
- [ ] Implement `source_evidence_reader.py` with the existing path-guard pattern. Read at most `MAX_SOURCE_LINES` current lines only after structural selection, compare the current file hash with the indexed hash before and after reading, and return `source_changed_since_index` or `source_unavailable` instead of stale text. Store no source excerpt. Evidence links use a non-executable percent-encoded `vg-source://<repository-id>/<relative-posix-path>#L<start>-L<end>` form; validate that the relative path cannot contain `..`, NUL, or a decoded absolute path. Absolute paths are redacted from evidence/error DTOs and diagnostics (repository catalog list DTOs may retain their explicit configured `root_path` field).
- [ ] Enforce repository-local traversal, depth/limit bounds, deterministic ordering, and exclusion of ambiguous/unresolved edges from confident impact. A missing/partial/stale projection must be represented in warnings and never silently treated as fresh.
- [ ] Add exactly these commands and options, preserving existing Vault commands: `vg code repository add ID --path PATH [--language LANGUAGE...]`, `list [--format text|json]`, `remove ID [--format text|json]`; `vg code index [--repository-id ID] [--full] [--dry-run] [--format text|json]`; `status [--repository-id ID] [--verify] [--format text|json]`; `search QUERY [--repository-id ID] [--kind KIND] [--limit N] [--format text|json]`; `symbol SYMBOL_OR_ID [--repository-id ID] [--path PATH] [--source] [--format text|json]`; `outline PATH [--repository-id ID] [--format text|json]`; `callers SYMBOL_OR_ID [--repository-id ID] [--path PATH] [--depth N] [--format text|json]`; `callees SYMBOL_OR_ID [--repository-id ID] [--path PATH] [--depth N] [--format text|json]`; `impact SYMBOL_OR_ID [--repository-id ID] [--path PATH] [--depth N] [--format text|json]`. Invalid input exits nonzero; unavailable/failed indexing exits nonzero; `--dry-run` and `--verify` perform no writes. `code_commands.py` remains a thin Typer adapter and imports application services, not SQLite/parser implementation details.
- [ ] Run focused tests, full tests, Ruff, mypy, build, lock, and diff checks; commit `feat: expose code query diagnostics`.

## Task 2: Build the MCP-free project context service

**Files:**

- Create: `src/vault_graph/project_context/project_context_models.py`
- Create: `src/vault_graph/project_context/project_context_service.py`
- Create: `src/vault_graph/project_context/project_binding.py`
- Create: `src/vault_graph/project_context/project_binding_catalog.py`
- Create: `src/vault_graph/project_context/__init__.py`
- Modify: `src/vault_graph/app/code_index_factory.py`
- Modify: `src/vault_graph/app/read_only_service_factory.py` only if composition requires it
- Create: `src/vault_graph/cli/project_commands.py`
- Modify: `src/vault_graph/cli/main.py`
- Tests: `tests/test_project_context_service.py`, `tests/test_project_context_read_only_boundary.py`, `tests/test_project_context_scope.py`, `tests/test_project_context_import_boundaries.py`, `tests/test_project_context_models.py`, `tests/test_project_binding_catalog.py`, `tests/test_cli_project_binding.py`

- [ ] Define immutable task/scope/budget/evidence/revision/warning DTOs and a `ProjectBinding` catalog. The binding is explicit configuration keyed by registered `repository_id` (safe Graph state, never Vault or repository content) and contains one or more explicit `vault_ids` plus optional content scopes. Implement a load/save/validate round-trip service at the Graph state path, an explicit `vg project bind REPOSITORY_ID --vault-id ID [--scope SCOPE]...` setup path, and no implicit write during query/MCP. There is no “active Vault” inference. Missing binding, unregistered path, and ambiguous/multi-binding cases fail with a redacted recovery hint; multi-Vault bindings are allowed only when explicitly listed and are reported as separate authorities.
- [ ] Define injected stable protocols for Vault retrieval, context-pack, graph relation lookup, and Vault freshness/status. Adapt existing concrete services behind those protocols; do not make `ProjectContextService` depend on concrete storage or MCP classes. Map statuses to (`fresh`, `stale`, `syncing`, `partial`, `unavailable`, `unknown`) with deterministic precedence `unavailable > partial > syncing > unknown > stale > fresh`; combined context is never `fresh` unless code and every selected Vault authority are fresh.
- [ ] Resolve `project_path` by canonical path against the repository catalog, then require the explicit binding. A caller may supply `repository_id` only when it is registered; never search other repositories or Vaults to guess a match. If both `project_path` and `repository_id` are omitted, select the sole registered repository that has an explicit binding; if zero or more than one qualify, return `scope_required` with a redacted list of acceptable repository IDs.
- [ ] Store bindings at a Graph-owned state path (for example `<graph-state>/project-bindings.json`) with a versioned JSON schema, atomic writes, and no Vault/repository writes. Register `project_commands.py` as `vg project bind REPOSITORY_ID --vault-id ID [--scope SCOPE]... [--format text|json]` and `vg project bindings [--format text|json]`; test command registration, validation, round-trip, duplicate replacement, and state-only fingerprints.
- [ ] Compose `CodeQueryService` with the injected retrieval/context-pack/graph services. Select bounded code evidence, live source-line links, related tests, impact, and relevant Vault decisions/design constraints without duplicating search algorithms. Cross-authority links are emitted only when extracted from a stable identifier or explicitly configured mapping; otherwise use `inferred`, `ambiguous`, or `unresolved` with the reason.
- [ ] Enforce an explicit output budget (`max_tokens` upper bound and deterministic evidence truncation), stable ordering, no stored source excerpts, and graceful missing-code-index fallback that still returns Vault evidence and a warning. Prove no Vault/repository writes; commit `feat: compose project context evidence`.

## Task 3: Add the `explore_project` MCP surface

**Files:**

- Modify: `src/vault_graph/mcp/mcp_tools.py`
- Modify: `src/vault_graph/mcp/mcp_tool_serialization.py`
- Modify: `src/vault_graph/mcp/mcp_server.py`
- Modify: `src/vault_graph/mcp/mcp_service_factory.py`
- Modify: `src/vault_graph/mcp/mcp_prompts.py`
- Modify: `src/vault_graph/mcp/__init__.py`
- Tests: `tests/test_mcp_explore_project.py`, `tests/test_mcp_explore_project_read_only_boundary.py`, `tests/test_mcp_tools.py`, `tests/test_mcp_server.py`, `tests/test_mcp_stdio_smoke.py`, `tests/test_mcp_import_boundaries.py`

- [ ] Add `ExploreProjectInput(task, project_path=None, repository_id=None, max_tokens=None, depth=2, limit=20)` and `parse_explore_project_input` using existing MCP error/scope conventions. Reject blank/overlong tasks, absolute-path leakage in errors, depth/limit outside bounded constants, and simultaneous conflicting `project_path`/`repository_id` scopes. When both scope fields are omitted, delegate to the Task 2 sole-bound-repository rule; return `scope_required` for zero or multiple bound repositories rather than guessing.
- [ ] Update `McpToolName`/the Literal, registry, parser, serializer, server, service factory, package exports, and exact existing registration tests to add exactly one `explore_project` tool. The adapter calls only `ProjectContextService`; it never opens SQLite or reads repository paths. Code-index startup is lazy: a missing/unavailable code catalog returns a structured fallback from the service and does not break non-code MCP tools.
- [ ] Extend `McpResourceLink` compatibly with optional repository evidence URI fields while retaining Vault links. Serialize evidence, source links, revisions, freshness, impact, tests, warnings, and recovery hints as structured JSON plus a concise text mirror; never embed source bodies or absolute paths.
- [ ] Add MCP initialization guidance that makes `explore_project` the default coding entry point while preserving the durable-Vault publication rule. Run import-laziness tests and the enabled stdio smoke gate (`VG_RUN_MCP_STDIO_SMOKE=1 uv run pytest tests/test_mcp_stdio_smoke.py -q`). If the required `mcp` runtime is absent, record the exact dependency, command, and skip reason in the verification report; otherwise a failure is blocking. Commit `feat: expose project exploration through mcp`.

## Task 4: Add explicit coding-harness instruction management

**Files:**

- Create: `src/vault_graph/harness/harness_guidance.py`
- Create: `src/vault_graph/harness/__init__.py`
- Create: `src/vault_graph/cli/harness_commands.py`
- Modify: `src/vault_graph/app/setup_service.py`
- Modify: `src/vault_graph/cli/main.py`
- Modify: `src/vault_graph/mcp/mcp_prompts.py` only for shared marker text
- Tests: `tests/test_harness_guidance.py`, `tests/test_harness_guidance_read_only.py`, `tests/test_setup_harness_guidance.py`

- [ ] Implement marker-fenced, idempotent guidance installation/removal for supported `AGENTS.md`/`CLAUDE.md` targets. Register exact commands `vg harness guidance install --target PATH --file-name AGENTS.md|CLAUDE.md [--backup PATH] [--preview]`, `vg harness guidance remove --target PATH --file-name AGENTS.md|CLAUDE.md [--preview]`, and `vg harness guidance preview --target PATH --file-name AGENTS.md|CLAUDE.md`; there is no overwrite flag and backup collisions are always rejected. Default/MCP startup performs no write. Resolve and canonicalize the target and backup paths, reject symlink targets/backups and paths inside Vault, and atomically write a same-directory temporary file followed by `os.replace`. Preserve unrelated edits; on removal restore only the marker block and leave user changes intact. Back up the original before mutation and make tamper/missing-marker states explicit errors.
- [ ] Guidance must say to call `explore_project` first, treat output as working evidence, re-read changed source lines, and publish durable knowledge only through Vault's workflow. It must not contain hidden prompt injection or claim code projection authority. When MCP is unavailable, include a safe fallback to the equivalent `vg code ...` CLI commands; all guidance text is static trusted text.
- [ ] Add `harness_commands.py` registration in `cli/main.py` and setup-service integration, preserving unrelated file content and proving no-write behavior for preview and default MCP startup; never target Vault or a repository unless the user explicitly chooses its instruction file. Commit `feat: install explicit coding harness guidance`.

## Task 5: Measure prompt and call reduction and close the Round 2 gate

**Files:**

- Create: `tests/fixtures/project_context/` representative Python/Dart/Vault fixture
- Create: `tests/benchmarks/test_project_context_benchmark.py`
- Create: `docs/superpowers/reports/2026-08-03-round-2-project-context-verification-ko.md`
- Modify: `docs/SPEC.md`, `docs/DESIGN.md`, `docs/FEATURES.md`, `README.md`, `docs/DECISIONS.md` only for accepted identity/contract updates
- Tests: `tests/test_project_context_import_boundaries.py`, `tests/test_project_context_models.py`, `tests/test_project_context_serialization.py`

- [ ] Measure deterministic scripted baseline multi-tool flows and the one-call `explore_project` flow (no LLM/network) for structure explanation, bug-scope investigation, impact analysis, and design/implementation consistency. The fixture must include a registered code catalog, an explicit repository↔Vault binding, Python/Dart symbols, tests, a stale/partial case, and Vault decisions. Record tool calls, response-token estimates, fallback reads, expected evidence IDs, relevant-evidence recall, and stale-result misses.
- [ ] Acceptance thresholds are explicit: `explore_project` uses fewer application-tool calls than each baseline scenario; prompt instruction tokens are lower than baseline; relevant-evidence recall is ≥ baseline; stale-result misses are exactly zero; output remains within `max_tokens`/depth/limit bounds; Vault and repository fingerprints are unchanged; missing-code-index fallback is deterministic.
- [ ] Run the full verification gate: `uv run pytest -q`, `uv run ruff check .`, changed-file `uv run ruff format --check`, `uv run mypy src` plus changed tests, `uv build`, `uv lock --check`, `git diff --check`, and `VG_RUN_MCP_STDIO_SMOKE=1 uv run pytest tests/test_mcp_stdio_smoke.py -q`. Document the exact command, whether the gate ran, and any dependency-based skip reason; a runnable gate failure is blocking.
- [ ] Have a final independent reviewer audit every Round 2 completion criterion and write the Korean verification report. Commit `test: verify project context and harness gate`.

## Completion criteria

- A single `explore_project` call returns bounded current code evidence, related tests/impact, relevant Vault evidence, provenance, revisions, and freshness warnings.
- Existing MCP tools remain compatible; MCP adapters call application services and never open stores directly.
- Code, Vault, and harness guidance preserve read-only/rebuildable authority boundaries.
- Explicit guidance installation/removal is reversible and does not mutate Vault or repositories by default.
- Benchmark evidence shows fewer orchestration calls and less prompt instruction without lower evidence recall or hidden staleness.

## Open Decisions (recommendations for implementation)

1. **Repository↔Vault binding format:** use a small Graph-owned TOML/JSON catalog entry keyed by `repository_id`, with explicit `vault_ids` and optional content scopes, loaded/saved by `ProjectBindingCatalogService` and created through the explicit `vg project bind` path. Recommendation: allow one-to-many bindings but return authority-separated evidence and reject an empty list; never infer a Vault from cwd, recency, or an “active” setting.
2. **Project path resolution:** canonicalize the caller path and match exactly one registered repository root (a child path is allowed); reject none or more than one match with a redacted recovery hint. Recommendation: require `repository_id` when the path is outside the catalog.
3. **Evidence bounds:** default `depth=2`, `limit=20`, `max_tokens=4000`; hard caps are service constants shared by CLI and MCP. Recommendation: truncate deterministically by authority, then by stable evidence ID.
4. **Harness targets:** only an explicitly selected project instruction file may be changed. Recommendation: support `AGENTS.md` and `CLAUDE.md`, never Vault files, and never write on MCP startup.

These are active-plan decisions, not accepted product decisions. After implementation and user acceptance, record only the accepted choices in `docs/DECISIONS.md` using the repository's existing style.
