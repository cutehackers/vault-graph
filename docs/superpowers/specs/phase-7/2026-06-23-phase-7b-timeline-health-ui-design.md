# Phase 7B Timeline And Health UI SPEC

Status: Draft for implementation planning

Date: 2026-06-23

Scope: Phase 7B

## 1. Purpose

Phase 7B defines a minimal read-only browser view for the Phase 6C timeline,
freshness, backend health, MCP runtime-cache, and scale-up adapter readiness
projections.

The value is operational trust. Before a user or agent relies on Vault Graph
search, graph, context packs, project memory, or decision traces, the UI should
make it easy to see:

- what indexed document snapshots changed recently;
- which projection or backend is fresh, stale, degraded, unavailable, or schema
  incompatible;
- which warnings and recovery hints apply to the selected Vault scope;
- whether future scale-up adapters have enough logical contract readiness to be
  designed safely later.

Phase 7B is a view contract over existing Phase 6C application services. It is
not a new status service, hosted monitoring system, HTTP adapter implementation,
store inspector, migration tool, or durable memory source.

## 2. Relationship To Phase 7A And Future Ask

The current detailed-design scope intentionally skips Phase 7A. Local HTTP
serving and `vg serve --http` are future adapter work. This Phase 7B document
therefore defines the UI view model and read-only interaction contract without
requiring a concrete HTTP transport to exist first.

When a future Phase 7A HTTP adapter exists, it should serve this view model by
calling application services only. Until then, implementation planning may test
the view model directly against Python service outputs or fixtures.

`Ask Project`, `ask_vault`, answer synthesis, LLM adapter policy, and citation
guarantees are future-phase work. Phase 7B must not expose an answer box or
generated answer surface.

## 3. User Value

Phase 7B serves three narrow workflows:

1. **Freshness check:** inspect the most recent indexed document snapshot,
   vector, graph, and metadata status changes for the active Vault or explicit
   multi-Vault scope.
2. **Trust check:** see whether metadata, keyword, vector, graph, and MCP
   runtime cache state is ready enough for retrieval and context work.
3. **Scale-up readiness check:** see which logical contracts are ready for
   future Postgres, Qdrant, or Neo4j adapter design without performing
   migration or requiring those backends.

The UI should reduce terminal round-trips for humans while preserving the same
warnings and evidence that MCP tools return to agents.

## 4. Success Criteria

Phase 7B is complete when:

- a Timeline and Health view can render a `RecentChangesProjection` and
  `HealthExplorerReport` without losing Vault IDs, actual scopes, warnings,
  freshness, evidence refs, store revisions, runtime cache records, or scale-up
  readiness records;
- the default view uses the active Vault, and explicit multi-Vault scope remains
  visible in the UI;
- document-backed timeline items link to existing read-only document resources
  or equivalent evidence detail routes;
- status-backed timeline items do not masquerade as Vault documents or durable
  business events;
- every degraded, stale, unavailable, incompatible, or warning state is visible
  without requiring hover-only disclosure;
- recovery hints are displayed when the projection provides them;
- no UI interaction creates, edits, deletes, renames, indexes, migrates,
  publishes, or repairs Vault content or Vault Graph stores;
- all browser-local state is ephemeral URL/query state only in the first
  implementation; persistent browser storage is out of scope;
- tests prove that warning payloads, multi-Vault identity, empty states, and
  read-only boundaries are preserved.

## 5. In Scope

- Timeline and Health view model DTOs.
- Mapping from Phase 6C payloads to UI sections.
- Read-only controls for scope, `since`, and per-Vault limit.
- Timeline item grouping by Vault and origin.
- Backend readiness table for metadata, keyword, vector, and graph backends.
- MCP runtime-cache readiness display.
- Scale-up adapter readiness display.
- Evidence-link rendering for document-backed timeline items.
- Warning, empty, stale, and unavailable states.
- Static UI asset design suitable for a future local HTTP adapter.
- Tests for view-model mapping, warning propagation, scope handling, and
  read-only behavior.

## 6. Out Of Scope

- Phase 7A local HTTP adapter implementation.
- Hosted monitoring, subscriptions, alerts, background polling, or remote
  sharing.
- Authentication, authorization, TLS, origin policy, or network hardening.
- `Ask Project`, `ask_vault`, LLM answers, or answer synthesis.
- Decision Explorer and Agent Workspace views; those belong to Phase 7C.
- Context-pack editing, durable pack persistence, or Vault publication.
- Direct SQLite, Chroma, graph-store, status-file, or Vault-file access from UI
  modules.
- Running `vg index`, migrations, repairs, or any write operation from the UI.

## 7. Source Contracts

Phase 7B reads only existing service-level payloads:

- `RecentChangesProjection` from
  `TimelineMemoryService.recent_changes(requested_scope, since=None, limit=20)`.
- `HealthExplorerReport` from
  `HealthExplorerService.inspect(requested_scope, runtime_caches=...)`.
- MCP serialization shape from
  `recent_changes_projection_to_payload(...)` and
  `health_explorer_report_to_payload(...)`.

Required fields to preserve:

- top level: `requested_scope`, `actual_scopes`, `warnings`, `generated_at`;
- timeline: `since`, `limit`, `vaults`, `items`, `origin`, `occurred_at`,
  `sort_key`, `evidence`, `store_revisions`, `freshness`;
- timeline evidence: `source_kind`, `vault_id`, `document_id`, `chunk_id`,
  `path`, `content_hash`, `raw_sha256`, `metadata_index_revision`,
  `vault_revision`, `backend_kind`, `backend_revision`, `scope_key`;
- health: `backends`, `runtime_caches`, `scale_up_adapters`;
- backend readiness: `backend_kind`, `backend_name`, `vault_id`, `scope_key`,
  `status`, `schema_compatible`, `freshness`, `revision`, `last_success_at`,
  `last_error_at`, `message`, `recovery_hint`;
- runtime caches: `cache_name`, `current_entries`, `max_entries`, `status`,
  `oldest_cached_at`, `newest_cached_at`, `message`;
- scale-up readiness: `adapter_kind`, `target_backend`, `configured`,
  `contract_ready`, `migration_required`, `depends_on_backend_kind`, `message`,
  `recovery_hint`.

The UI must treat these payloads as canonical. It may group, sort, filter, or
collapse them for display, but it must not invent new facts or hide warnings.

## 8. View Model

Add a UI-specific model layer only if implementation needs it. It should be a
pure mapping layer with no store access:

```python
@dataclass(frozen=True)
class TimelineHealthViewModel:
    requested_scope: dict[str, object]
    actual_scopes: tuple[dict[str, object], ...]
    selected_vault_ids: tuple[str, ...]
    generated_at: str
    since: str | None
    limit: int
    vaults: tuple[TimelineHealthVaultView, ...]
    backend_rows: tuple[BackendHealthRowView, ...]
    runtime_cache_rows: tuple[RuntimeCacheRowView, ...]
    scale_up_rows: tuple[ScaleUpReadinessRowView, ...]
    warnings: tuple[WarningView, ...]
```

```python
@dataclass(frozen=True)
class TimelineHealthVaultView:
    vault_id: str
    display_name: str
    freshness: str
    item_count: int
    items: tuple[TimelineItemView, ...]
    warnings: tuple[WarningView, ...]
    store_revisions: tuple[RevisionView, ...]
```

```python
@dataclass(frozen=True)
class TimelineItemView:
    item_id: str
    origin: str
    origin_label: str
    title: str
    summary: str
    vault_id: str
    occurred_at: str | None
    sort_key: str
    evidence_links: tuple[EvidenceLinkView, ...]
    status_evidence: tuple[TimelineStatusEvidenceView, ...]
    warnings: tuple[WarningView, ...]
```

Mapping rules:

- `origin_label` is a presentation label only; keep raw `origin` available for
  tests and accessibility text.
- `document_snapshot_change` items render document evidence links first.
- `index_change` and `projection_change` items render backend/status evidence,
  not document links.
- `warning` items render as timeline items and warning banners.
- timestamps are displayed exactly enough to preserve timezone information; the
  UI may format for readability but must keep the original value available in a
  detail panel.
- items with `occurred_at=None` are visibly marked `No timestamp`.

## 9. Screen Structure

The first implementation should be one dense operations screen:

- top scope bar: selected Vault IDs, content scopes, generated timestamp;
- warning strip: top-level errors and warnings;
- freshness summary: counts by `fresh`, `stale`, `degraded`, `unavailable`,
  `unknown`;
- timeline column: grouped by Vault, then sorted according to projection order;
- health column: backend readiness table and runtime caches;
- scale-up panel: adapter readiness for Postgres, Qdrant, and Neo4j targets;
- detail drawer: selected timeline item, backend row, or warning.

This screen should feel like an operational tool. Do not add a landing page,
marketing hero, explanatory feature cards, or decorative visual layout.

## 10. Controls

Initial controls:

- Vault scope selector:
  - active Vault by default;
  - explicit one-Vault selection;
  - all enabled Vaults only when explicitly selected.
- `since` input:
  - empty means no filter;
  - ISO-8601 string when provided;
  - invalid input shows a validation error before requesting data.
- limit selector:
  - allowed range `1..50`;
  - default `20`;
  - label must say it applies per Vault group.
- refresh button:
  - reloads view data only;
  - must not run indexing or repairs.

The UI must not expose controls for `vg index`, migration, store deletion,
remote backend setup, or Vault publication in Phase 7B.

## 11. Data Flow

```text
Timeline and Health screen
  -> read UI query state
  -> request TimelineHealthViewData from an adapter boundary
  -> adapter calls TimelineMemoryService and HealthExplorerService
  -> map service payloads into view model
  -> render warnings, scope, evidence, timeline, backend rows, runtime caches
```

The adapter boundary may later be HTTP, but Phase 7B must keep the view contract
independent of transport. UI code must not import local store backends.

## 12. Error And Empty States

- Unknown or disabled Vault ID: show a blocking error with the selected Vault
  ID and recovery hint.
- Metadata unavailable or schema incompatible: show a blocking timeline error;
  health rows may still render if the service payload exists.
- Vector unavailable: show degraded health and warning items; timeline remains
  usable if metadata exists.
- Graph unavailable: show degraded health and projection warnings; do not hide
  document timeline items.
- Empty recent changes: show an empty timeline state with selected scope and
  freshness.
- No timestamp: render item after timestamped items and mark it explicitly.
- Invalid `since` or limit: validate before service invocation.

## 13. Multi-Vault Policy

- Never merge timeline items by path, title, timestamp, backend kind, or
  adapter kind across Vaults.
- Every group, row, detail panel, and evidence link displays `vault_id`.
- All-Vault views group timeline items by Vault.
- Backend rows with `vault_id=None` must explain whether the row represents an
  aggregate or a request-scope status.
- Cross-Vault graph traversal is not a Phase 7B concept.

## 14. Security And Read-Only Boundary

- UI assets and view-model code must not write Vault content.
- UI code must not open arbitrary file paths from payload fields.
- Evidence links must resolve through existing read-only resource routes or
  resource URI contracts.
- If future HTTP serves this view, it must bind locally by default and avoid
  remote exposure until a security design exists.
- Do not serialize cached context-pack bodies or explanation records inside
  health output; show counts and readiness only.

## 15. Performance

- Render only the bounded projection returned by services; do not request full
  Vault dumps.
- The default limit remains `20` per Vault.
- Do not poll automatically in the first implementation.
- Keep DOM rendering incremental enough for 50 items per Vault and several
  Vaults; beyond that, prefer server-side limit controls over client-only
  virtualization.
- Do not compute derived health by scanning documents in the browser.

## 16. Accessibility And Usability

- Warnings must be visible in text, not color alone.
- Backend statuses must use text labels plus icons or badges.
- Timeline items must have stable headings and keyboard-selectable detail
  panels.
- Evidence links must include path, Vault ID, and resource kind.
- The screen should be usable on a laptop without horizontal scrolling for the
  main timeline list; detail panels may use constrained tables.

## 17. Files For Later Implementation

Suggested implementation files:

```text
src/vault_graph/ui/__init__.py
src/vault_graph/ui/timeline_health_view_model.py
src/vault_graph/ui/static/timeline-health.html
src/vault_graph/ui/static/timeline-health.css
src/vault_graph/ui/static/timeline-health.js
tests/test_ui_timeline_health_view_model.py
tests/test_ui_read_only_boundary.py
```

If the future Phase 7A HTTP adapter uses different static-asset packaging, keep
the view-model and tests while moving only transport-specific files.

## 18. Verification

Implementation must pass:

```bash
uv run --python 3.12 ruff check src tests
uv run --python 3.12 mypy src tests
uv run --python 3.12 pytest -q
```

Focused tests should prove:

- timeline warnings remain visible at top-level, Vault-level, and item-level;
- health warnings remain visible and include recovery hints;
- document-backed timeline items produce evidence links with `vault_id`;
- status-backed items do not produce document links;
- multi-Vault items remain grouped by Vault ID;
- refresh does not call indexing or write APIs;
- empty and unavailable states render without dropping scope information.

## 19. Review Notes

- Security/read-only: the design exposes no write controls and requires future
  HTTP to stay local-first.
- Performance: bounded service projections are reused; no full-Vault browser
  scan is introduced.
- Testability: mapping functions can be tested with Phase 6C DTO fixtures.
- Maintainability: the UI is a thin view over Phase 6C contracts and does not
  duplicate projection logic.

## 20. Open Decisions

None for Phase 7B detailed design. Future Phase 7A must separately decide the
local HTTP stack, bind policy, static asset packaging, and browser launch
behavior.
