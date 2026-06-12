# Phase 4B Local Context Pack Assembly And Rendering Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `vg context GOAL` so local users can render a bounded evidence-linked context pack as canonical JSON or Markdown without mutating Vault.

**Architecture:** Keep Phase 4B as a thin CLI adapter over the Phase 4A `vault_graph.context` deep module. The CLI resolves scope and output format, constructs `ContextPackRequest`, calls `SearchContextPackBuilder`, and delegates all JSON/Markdown formatting to `DefaultContextPackRenderer`.

**Tech Stack:** Python 3.12, Typer CLI, frozen dataclass DTOs, existing `RetrievalService`, existing local read-only SQLite/Chroma adapters, pytest, ruff, mypy.

---

## Scope

Phase 4B implements:

- `vg context GOAL`
- `--state`, `--vault-id`, `--all-vaults`, `--format json|markdown`, `--max-tokens`, `--limit`, `--include-graph`, `--include-cross-vault`
- CLI wiring to existing read-only retrieval and metadata evidence resolution
- JSON output from canonical `ContextPack`
- Markdown output from `DefaultContextPackRenderer`
- Phase 4B renderer sections and evidence/warning visibility
- deterministic classification and packing refinements required by the 4B design
- read-only, missing metadata, graph opt-in, and multi-vault CLI tests

Phase 4B does not implement:

- `vg ask`
- MCP serving
- HTTP serving
- context pack persistence or cache
- automatic Vault publication
- LLM-generated summaries, answers, or classifiers

## Directory And File Structure

Create:

- `tests/test_cli_context.py`
- `tests/test_context_pack_renderer.py`

Modify:

- `src/vault_graph/cli/main.py`
- `src/vault_graph/context/context_pack_builder.py`
- `src/vault_graph/context/context_pack_renderer.py`
- `tests/test_cli_surface_boundary.py`
- `tests/test_context_pack_builder.py`
- `tests/test_context_pack_serialization.py`

Do not modify:

- Vault files under registered Vault roots
- `src/vault_graph/storage/local/*` except through existing read-only constructors
- `src/vault_graph/retrieval/*` unless a test proves an existing retrieval contract defect
- `docs/DECISIONS.md` unless a user-approved decision is introduced

No open product or architecture decisions are required for this slice.

## Component And Interface Spec

### CLI Command

Add the `context` Typer command to `src/vault_graph/cli/main.py`. The public
command name is `context`; the Python function name is `context`; its parameters
are `goal`, `state`, `vault_id`, `all_vaults`, `output_format`, `max_tokens`,
`limit`, `include_graph`, and `include_cross_vault`. The complete code body is
defined in Task 4 Step 4.

Validation order:

1. `goal.strip()` must be non-empty, otherwise print `empty_goal` and exit 1.
2. `--vault-id` and `--all-vaults` are mutually exclusive, otherwise print `Use either --vault-id or --all-vaults, not both.` and exit 1.
3. `--format` must be `json` or `markdown`, otherwise print `unsupported_format` and exit 1.
4. `--max-tokens` must be at least 1000, otherwise print `context_budget_too_small` and exit 1.
5. `--limit` must be positive, otherwise print `context_limit_must_be_positive` and exit 1.
6. `--include-cross-vault` requires `--all-vaults --include-graph`, otherwise print `include_cross_vault_requires_multi_vault_graph_scope` and exit 1.

### CLI Factory Boundary

Add private factories that reuse the existing search dependency pattern while
exposing the read-only metadata store to the context evidence resolver. The
context command must load the catalog and resolve scope before calling
`_context_builder_service`; invalid `--vault-id` must not open metadata, vector,
graph, or embedding dependencies.

```python
def _read_only_search_components(
    state: Path,
    *,
    config: CatalogService,
    catalog: VaultCatalog,
    include_graph: bool = False,
) -> tuple[SQLiteMetadataStore, RetrievalService]:
    metadata_store = SQLiteMetadataStore(config.metadata_path, initialize=False)
    keyword_index = SQLiteKeywordIndex(config.metadata_path)
    vector_store = ChromaVectorStore(config.vector_path, initialize=False, read_only=True)
    text_embeddings = _search_text_embeddings(config)
    graph_candidate_provider = None
    if include_graph:
        _, _, graph_service = _graph_retrieval_service(state)
        graph_candidate_provider = GraphSearchCandidateProvider(graph_retrieval_service=graph_service)
    return (
        metadata_store,
        RetrievalService(
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
            graph_candidate_provider=graph_candidate_provider,
        ),
    )
```

Then add a wrapper for the existing search command:

```python
def _search_service_with_metadata(
    state: Path,
    *,
    include_graph: bool = False,
) -> tuple[CatalogService, VaultCatalog, SQLiteMetadataStore, RetrievalService]:
    config, catalog = _catalog(state)
    metadata_store, service = _read_only_search_components(
        state,
        config=config,
        catalog=catalog,
        include_graph=include_graph,
    )
    return config, catalog, metadata_store, service
```

Then change `_search_service` to call this helper and return the existing
3-tuple:

```python
def _search_service(
    state: Path,
    *,
    include_graph: bool = False,
) -> tuple[CatalogService, VaultCatalog, RetrievalService]:
    config, catalog, _, service = _search_service_with_metadata(state, include_graph=include_graph)
    return config, catalog, service
```

Add the context-specific factory:

```python
def _context_builder_service(
    state: Path,
    *,
    config: CatalogService,
    catalog: VaultCatalog,
    include_graph: bool = False,
) -> tuple[SearchContextPackBuilder, ContextPackRenderer]:
    metadata_store, retrieval_service = _read_only_search_components(
        state,
        config=config,
        catalog=catalog,
        include_graph=include_graph,
    )
    return (
        SearchContextPackBuilder(
            catalog=catalog,
            retrieval_service=retrieval_service,
            evidence_resolver=MetadataContextEvidenceResolver(metadata_store=metadata_store),
        ),
        DefaultContextPackRenderer(),
    )
```

`src/vault_graph/cli/main.py` may import concrete local stores because CLI is the adapter boundary. `src/vault_graph/context/*` must continue to avoid local backend imports.

### Scope Helper

Add a helper used by `vg context`:

```python
def _context_scope_for_flags(
    catalog: VaultCatalog,
    *,
    vault_id: str | None,
    all_vaults: bool,
    include_cross_vault: bool,
) -> QueryScope:
    if all_vaults:
        scope = catalog.scope_for_all_enabled()
    elif vault_id is not None:
        scope = catalog.scope_for_vault_ids([vault_id])
    else:
        scope = catalog.default_scope()
    if include_cross_vault:
        return QueryScope(
            vault_ids=scope.vault_ids,
            content_scopes=scope.content_scopes,
            include_cross_vault=True,
        )
    return scope
```

Do not reuse this helper in existing commands during Phase 4B unless a failing test requires it. Keeping the edit local reduces risk.

### Context Request Construction

Construct `ContextPackRequest` directly in the command body and wrap the
`builder.build(...)` call in `_exit_on_domain_error(...)`. Do not add a separate
pass-through build helper; the builder remains the deep module that owns pack
assembly.

```python
request = ContextPackRequest(
    goal=goal,
    requested_scope=scope,
    budget=ContextPackBudget(max_tokens=max_tokens),
    retrieval_limit=limit,
    include_graph=include_graph,
    include_cross_vault=include_cross_vault,
)
pack = _exit_on_domain_error(lambda: builder.build(request))
```

Add `ContextPackError` to `_exit_on_domain_error(...)`.

### Renderer Contract

`DefaultContextPackRenderer.render_markdown(...)` must render these headings in this order:

```markdown
# Context Pack
## Goal
## Scope
## Warnings
## Decisions
## Constraints
## Open Questions
## Current State
## Relevant Pages
## Relevant Sources
## Evidence
## Revisions
## Budget
## Backend
```

Rules:

- Always render `## Warnings`.
- Warning lines include severity, code, affected Vault IDs, message, and recovery hint when present.
- Evidence lines include `[vault_id] path#anchor` when anchor exists.
- Evidence lines include `[truncated]` when `ContextEvidence.truncated` is true.
- Markdown uses only values from `ContextPack`; it must not reconstruct or add facts.
- Existing collision-safe code fences and inline escaping remain.

### Builder Classification And Packing Refinement

Update `_item_type(...)`, `_planned_item_sort_key(...)`, and `_items_by_type(...)` in `src/vault_graph/context/context_pack_builder.py`.

Classification rules:

```python
_CONSTRAINT_TERMS = ("constraint", "principle", "invariant", "policy", "convention")
_OPEN_QUESTION_TERMS = ("question", "todo", "follow-up", "issue", "revisit")
_CURRENT_STATE_TERMS = ("current-state", "current_state")
_CURRENT_STATE_PATH_SUFFIXES = ("/status.md", "/current-state.md", "/current_state.md")


def _item_type(result: RetrievalResult) -> ContextPackItemType:
    first_evidence = result.evidence[0]
    path = first_evidence.path.lower()
    section = (first_evidence.section or "").lower()
    title = result.title.lower()
    kind = result.kind.lower()
    text = " ".join((kind, path, section, title))
    path_with_slashes = f"/{path}"
    if kind == "decision" or "/decisions/" in path_with_slashes:
        return "decision"
    if kind == "constraint" or any(term in text for term in _CONSTRAINT_TERMS):
        return "constraint"
    if kind == "open_question" or any(term in text for term in _OPEN_QUESTION_TERMS):
        return "open_question"
    if (
        kind == "current_state"
        or any(term in text for term in _CURRENT_STATE_TERMS)
        or any(path_with_slashes.endswith(suffix) for suffix in _CURRENT_STATE_PATH_SUFFIXES)
    ):
        return "current_state"
    if path.startswith("raw/"):
        return "source"
    return "page"
```

Packing sort key:

```python
def _planned_item_sort_key(item: _PlannedItem) -> tuple[int, int, int, int, str, str, str]:
    first_evidence = item.result.evidence[0]
    priority = {
        "decision": 0,
        "constraint": 1,
        "open_question": 2,
        "current_state": 3,
        "page": 4,
        "source": 5,
    }[item.item_type]
    signal_kind_count = len({signal.kind for signal in item.result.signals})
    raw_source_penalty = 1 if first_evidence.path.startswith("raw/") else 0
    return (
        priority,
        item.result.rank,
        -signal_kind_count,
        raw_source_penalty,
        item.result.vault_id,
        first_evidence.path,
        first_evidence.chunk_id,
    )
```

`_items_by_type(...)` must include:

```python
"current_state": tuple(item for item in items if item.item_type == "current_state")
```

and `SearchContextPackBuilder.build(...)` must set:

```python
current_state=items_by_type["current_state"],
```

## Data Flow

```text
vg context GOAL
  -> validate options before opening stores
  -> load VaultCatalog from --state
  -> resolve QueryScope from active Vault, --vault-id, or --all-vaults
  -> if --include-cross-vault, set QueryScope.include_cross_vault=True
  -> create read-only RetrievalService and MetadataContextEvidenceResolver
  -> create ContextPackRequest
  -> SearchContextPackBuilder.build(request)
      -> RetrievalService.search(query_text=goal, requested_scope=scope, limit=limit, output_format="json", include_graph=flag, include_cross_vault=flag)
      -> section classification
      -> evidence resolution through MetadataStore interface
      -> deterministic packing/truncation/warnings
      -> canonical ContextPack with pack_id
  -> DefaultContextPackRenderer.render_json or render_markdown
  -> write only stdout
```

No Phase 4B state transition writes to Vault or Vault Graph state. Existing read-only store constructors may inspect state files but must not create missing projections.

`--max-tokens` follows the Phase 4A public contract: it is an estimated budget
for excerpt-bearing evidence content. JSON metadata, Markdown headings, warning
text, and item summaries remain visible even when excerpts are omitted or
truncated, so rendered Markdown can contain overhead beyond `budget.used_tokens`.
The renderer must not hide warnings or revisions to force the final text under
the evidence excerpt budget.

Retrieval work remains bounded by the existing `RetrievalService` contract:
`candidate_limit = max(limit * 4, 20)` is applied per actual scope, then the
final `SearchResponse` is limited and the `SearchContextPackBuilder` caps the
requested retrieval limit to `max(max_evidence_items * 4, 10)`. Phase 4B does
not add a global all-Vault candidate allocator. Tests must avoid claiming that
all store work is globally bounded by `--limit`; the user-facing pack size is
bounded by the builder and context budget.

## Error Handling And Edge Cases

- Empty goal: CLI prints `empty_goal`, exits 1, opens no stores.
- Unsupported format: CLI prints `unsupported_format`, exits 1, opens no stores.
- `--max-tokens 999`: CLI prints `context_budget_too_small`, exits 1, opens no stores.
- `--limit 0`: CLI prints `context_limit_must_be_positive`, exits 1, opens no stores.
- `--vault-id` with `--all-vaults`: CLI prints `Use either --vault-id or --all-vaults, not both.`, exits 1.
- Unknown Vault ID: `CatalogError` is converted by `_exit_on_domain_error`, exits 1, and does not call
  `_context_builder_service` or `_graph_retrieval_service`.
- Missing metadata or keyword projection: existing `SearchError` message includes `metadata_unavailable` or `keyword_index_unavailable`, exits 1, creates no projection files.
- Vector unavailable or stale with keyword fallback: pack exits 0 and includes `search_degraded` or `stale_projection` warnings.
- Graph requested but unavailable with keyword/vector fallback: pack exits 0 and includes `graph_unavailable`.
- Plain `vg context` must not call `_graph_retrieval_service(...)`.
- `--include-cross-vault` without `--all-vaults --include-graph`: exits 1 before opening stores.
- Same document path or chunk ID across Vaults: JSON evidence refs and warning refs retain `vault_id`.

## Task 1: Strengthen Markdown Renderer For Phase 4B

**Files:**

- Create: `tests/test_context_pack_renderer.py`
- Modify: `src/vault_graph/context/context_pack_renderer.py`

- [ ] **Step 1: Write failing renderer tests**

Create `tests/test_context_pack_renderer.py`:

```python
from __future__ import annotations

from dataclasses import replace

from tests.test_context_pack_contract import make_pack
from vault_graph.context import (
    ContextEvidence,
    ContextEvidenceRef,
    ContextPackWarning,
    DefaultContextPackRenderer,
)


def test_markdown_renderer_uses_phase_4b_section_order() -> None:
    markdown = DefaultContextPackRenderer().render_markdown(make_pack())

    expected_order = [
        "# Context Pack",
        "## Goal",
        "## Scope",
        "## Warnings",
        "## Decisions",
        "## Constraints",
        "## Open Questions",
        "## Current State",
        "## Relevant Pages",
        "## Relevant Sources",
        "## Evidence",
        "## Revisions",
        "## Budget",
        "## Backend",
    ]
    positions = [markdown.index(heading) for heading in expected_order]
    assert positions == sorted(positions)


def test_markdown_warnings_show_scope_and_recovery_hint() -> None:
    pack = replace(
        make_pack(),
        warnings=(
            ContextPackWarning(
                code="metadata_unavailable",
                severity="warning",
                message="Metadata missing",
                affected_vault_ids=("main",),
                source_code="metadata_unavailable",
                source_kind="builder",
                recovery_hint="Run `vg index`.",
            ),
        ),
    )

    markdown = DefaultContextPackRenderer().render_markdown(pack)

    assert "[warning] `metadata_unavailable` [main]: Metadata missing" in markdown
    assert "Recovery: Run \\`vg index\\`." in markdown


def test_markdown_evidence_lines_include_vault_anchor_and_truncated_marker() -> None:
    ref = ContextEvidenceRef("main", "doc-1", "chunk-1")
    evidence = ContextEvidence(
        ref=ref,
        path="wiki/page.md",
        section="Section",
        anchor="section",
        content_hash="hash",
        raw_sha256="raw",
        metadata_index_revision="metadata-1",
        vault_revision="git-1",
        excerpt="one two three",
        excerpt_token_count=3,
        truncated=True,
        retrieval_reasons=("keyword matched",),
        warnings=(
            ContextPackWarning(
                code="excerpt_truncated",
                severity="warning",
                message="Evidence excerpt truncated.",
                affected_vault_ids=("main",),
                evidence_refs=(ref,),
                source_code="excerpt_truncated",
                source_kind="budget",
            ),
        ),
    )
    pack = replace(make_pack(), evidence=(evidence,))

    markdown = DefaultContextPackRenderer().render_markdown(pack)

    assert "[main] wiki/page.md#section [truncated]" in markdown
    assert "excerpt_truncated" in markdown


def test_markdown_renderer_escapes_vault_derived_item_and_evidence_text() -> None:
    pack = replace(
        make_pack(),
        warnings=(
            ContextPackWarning(
                code="search_degraded",
                severity="warning",
                message="# injected\n```",
                affected_vault_ids=("main",),
                source_code="search_degraded",
                source_kind="retrieval",
            ),
        ),
    )

    markdown = DefaultContextPackRenderer().render_markdown(pack)

    assert "\n# injected" not in markdown
    assert "\\# injected" in markdown
    assert markdown.count("```") % 2 == 0
```

- [ ] **Step 2: Run renderer tests to confirm failure**

Run:

```bash
uv run --python 3.12 pytest tests/test_context_pack_renderer.py -q
```

Expected: fails because the current renderer lacks `## Goal`, `## Scope`,
combined `## Revisions`, affected Vault IDs, recovery hints, and `[truncated]`
evidence markers.

- [ ] **Step 3: Update Markdown renderer**

Replace `DefaultContextPackRenderer.render_markdown(...)` in `src/vault_graph/context/context_pack_renderer.py` with an implementation that uses helper functions:

```python
def render_markdown(self, pack: ContextPack) -> str:
    lines = [
        "# Context Pack",
        "",
        "## Goal",
        _markdown_text(pack.goal),
        "",
        "## Scope",
        f"- Pack ID: {_markdown_code_span(pack.pack_id)}",
        f"- Schema: {_markdown_code_span(pack.context_pack_schema_version)}",
        f"- Generated: {_markdown_code_span(pack.generated_at)}",
        f"- Requested Vaults: {_markdown_code_span(_joined(pack.scope.requested.vault_ids))}",
        f"- Requested Content Scopes: {_markdown_code_span(_joined(pack.scope.requested.content_scopes))}",
        f"- Include Cross Vault: {_markdown_code_span(str(pack.scope.requested.include_cross_vault))}",
    ]
    if pack.scope.actual_scopes:
        lines.append("- Actual Scopes:")
        lines.extend(
            f"  - {_markdown_code_span(_actual_scope_label(scope))} "
            f"cross_vault={_markdown_code_span(str(scope.include_cross_vault))} "
            f"scope_key={_markdown_code_span(scope.scope_key)}"
            for scope in pack.scope.actual_scopes
        )
    else:
        lines.append("- Actual Scopes: None")
    lines.extend(["", "## Warnings"])
    if pack.warnings:
        lines.extend(_render_warning(warning) for warning in pack.warnings)
    else:
        lines.append("- None")
    sections = (
        ("Decisions", pack.decisions),
        ("Constraints", pack.constraints),
        ("Open Questions", pack.open_questions),
        ("Current State", pack.current_state),
        ("Relevant Pages", pack.relevant_pages),
        ("Relevant Sources", pack.relevant_sources),
    )
    for title, items in sections:
        lines.extend(["", f"## {title}"])
        if not items:
            lines.append("- None")
            continue
        for item in items:
            lines.extend(_render_item(item))
    lines.extend(["", "## Evidence"])
    if not pack.evidence:
        lines.append("- None")
    for evidence in pack.evidence:
        lines.extend(_render_evidence(evidence))
    lines.extend(["", "## Revisions", "### Vault Revisions"])
    if pack.vault_revisions:
        lines.extend(
            f"- {_markdown_code_span(revision.vault_id)}: "
            f"{_markdown_code_span(revision.revision or 'unknown')} "
            f"({_markdown_code_span(revision.revision_kind)})"
            for revision in pack.vault_revisions
        )
    else:
        lines.append("- None")
    lines.extend(["", "### Store Revisions"])
    if pack.store_revisions:
        lines.extend(
            f"- {_markdown_code_span(revision.kind)}: {_markdown_code_span(revision.revision or 'unknown')}, "
            f"vault={_markdown_code_span(revision.vault_id or 'global')}, "
            f"scope={_markdown_code_span(revision.scope_key)}"
            for revision in pack.store_revisions
        )
    else:
        lines.append("- None")
    lines.extend(
        [
            "",
            "## Budget",
            f"- max_tokens: `{pack.budget.max_tokens}`",
            f"- max_evidence_items: `{pack.budget.max_evidence_items}`",
            f"- max_excerpt_tokens: `{pack.budget.max_excerpt_tokens}`",
            f"- used_tokens: `{pack.budget.used_tokens}`",
            f"- omitted_items: `{pack.budget.omitted_items}`",
            "",
            "## Backend",
            _render_backend_use("metadata_store", pack.backend.metadata_store.name, pack.backend.metadata_store.used),
            _render_backend_use("keyword_index", pack.backend.keyword_index.name, pack.backend.keyword_index.used),
            _render_backend_use("vector_store", pack.backend.vector_store.name, pack.backend.vector_store.used),
            _render_backend_use("graph_store", pack.backend.graph_store.name, pack.backend.graph_store.used),
            _render_backend_use(
                "graph_projection",
                pack.backend.graph_projection.name,
                pack.backend.graph_projection.used,
            ),
        ]
    )
    return "\n".join(lines) + "\n"
```

Add helper functions in the same module:

```python
def _render_warning(warning: ContextPackWarning) -> str:
    vaults = ",".join(warning.affected_vault_ids) if warning.affected_vault_ids else "unknown"
    rendered = (
        f"- [{warning.severity}] {_markdown_code_span(warning.code)} "
        f"[{_markdown_text(vaults)}]: {_markdown_text(warning.message)}"
    )
    if warning.recovery_hint:
        rendered += f" Recovery: {_markdown_text(warning.recovery_hint)}"
    return rendered


def _render_evidence(evidence: ContextEvidence) -> list[str]:
    ref = evidence.ref
    location = _evidence_location(evidence)
    truncated = " [truncated]" if evidence.truncated else ""
    lines = [
        f"- {_markdown_code_span(_evidence_ref_label(ref))} {location}{truncated} "
        f"({evidence.excerpt_token_count} tokens)"
    ]
    if evidence.warnings:
        for warning in evidence.warnings:
            lines.append(f"  - {_render_warning(warning).removeprefix('- ')}")
    if evidence.excerpt:
        fence = _markdown_fence(evidence.excerpt)
        lines.append("")
        lines.append(f"  {fence}text")
        lines.extend(f"  {line}" for line in evidence.excerpt.splitlines())
        lines.append(f"  {fence}")
    return lines


def _evidence_location(evidence: ContextEvidence) -> str:
    suffix = evidence.anchor or evidence.section
    rendered = f"[{_markdown_text(evidence.ref.vault_id)}] {_markdown_text(evidence.path)}"
    if suffix:
        rendered += f"#{_markdown_text(suffix)}"
    return rendered


def _actual_scope_label(scope: ContextPackActualScope) -> str:
    return f"{','.join(scope.vault_ids)}:{','.join(scope.content_scopes)}"


def _render_item(item: ContextPackItem) -> list[str]:
    lines = [
        f"- **{_markdown_text(item.title)}**",
        f"  - Summary: {_markdown_text(item.summary)}",
        "  - Evidence: "
        + ", ".join(_markdown_code_span(_evidence_ref_label(ref)) for ref in item.evidence_refs),
    ]
    if item.warnings:
        lines.append("  - Warnings:")
        lines.extend(f"    - {_render_warning(warning).removeprefix('- ')}" for warning in item.warnings)
    return lines


def _render_backend_use(name: str, backend_name: str | None, used: bool) -> str:
    return (
        f"- {name}: {_markdown_code_span(backend_name or 'none')}, "
        f"used={_markdown_code_span(str(used))}"
    )


def _evidence_ref_label(ref: ContextEvidenceRef) -> str:
    return f"{ref.vault_id}:{ref.document_id}:{ref.chunk_id}"


def _joined(values: tuple[str, ...]) -> str:
    return ", ".join(values)


def _markdown_code_span(value: str) -> str:
    safe = value.replace("\n", " ")
    longest = 0
    current = 0
    for character in safe:
        if character == "`":
            current += 1
            longest = max(longest, current)
        else:
            current = 0
    fence = "`" * max(1, longest + 1)
    return f"{fence}{safe}{fence}"
```

Import `ContextEvidence`, `ContextEvidenceRef`, `ContextPackActualScope`,
`ContextPackItem`, and `ContextPackWarning` at the top of the renderer module.
Replace the existing `_render_item(...)` with the version above so top-level,
item-level, and evidence-level warnings all use the same warning-line helper.

- [ ] **Step 4: Run renderer tests**

Run:

```bash
uv run --python 3.12 pytest tests/test_context_pack_renderer.py tests/test_context_pack_serialization.py -q
```

Expected: all selected tests pass. `tests/test_context_pack_serialization.py`
still contains the Phase 4A CLI boundary assertion at this point.

- [ ] **Step 5: Commit renderer work**

```bash
git add src/vault_graph/context/context_pack_renderer.py tests/test_context_pack_renderer.py
git commit -m "feat(context): render phase 4b markdown context packs"
```

## Task 2: Refine Builder Classification And Packing

**Files:**

- Modify: `src/vault_graph/context/context_pack_builder.py`
- Modify: `tests/test_context_pack_builder.py`

- [ ] **Step 1: Add failing builder tests**

Append these tests to `tests/test_context_pack_builder.py`:

```python
def test_builder_classifies_decisions_constraints_questions_current_state_and_sources(tmp_path: Path) -> None:
    decision_ref = ContextEvidenceRef("main", "doc-decision", "chunk-decision")
    constraint_ref = ContextEvidenceRef("main", "doc-constraint", "chunk-constraint")
    question_ref = ContextEvidenceRef("main", "doc-question", "chunk-question")
    state_ref = ContextEvidenceRef("main", "doc-state", "chunk-state")
    source_ref = ContextEvidenceRef("main", "doc-source", "chunk-source")
    results = (
        make_result(rank=1, document_id="doc-decision", chunk_id="chunk-decision", path="wiki/decisions/choice.md"),
        make_result(rank=2, document_id="doc-constraint", chunk_id="chunk-constraint", path="docs/policy.md"),
        make_result(rank=3, document_id="doc-question", chunk_id="chunk-question", path="wiki/follow-up.md"),
        make_result(
            rank=4,
            document_id="doc-state",
            chunk_id="chunk-state",
            kind="current_state",
            path="wiki/status.md",
        ),
        make_result(rank=5, document_id="doc-source", chunk_id="chunk-source", path="raw/source.md"),
    )
    resolver = StaticResolver(
        {
            decision_ref: make_resolved(decision_ref, path="wiki/decisions/choice.md"),
            constraint_ref: make_resolved(constraint_ref, path="docs/policy.md"),
            question_ref: make_resolved(question_ref, path="wiki/follow-up.md"),
            state_ref: make_resolved(state_ref, path="wiki/status.md"),
            source_ref: make_resolved(source_ref, path="raw/source.md"),
        }
    )
    pack = make_builder(
        tmp_path=tmp_path,
        response=make_search_response(results=results),
        resolver=resolver,
    ).build(ContextPackRequest(goal="Build context", requested_scope=QueryScope(vault_ids=("main",))))

    assert [item.item_type for item in pack.decisions] == ["decision"]
    assert [item.item_type for item in pack.constraints] == ["constraint"]
    assert [item.item_type for item in pack.open_questions] == ["open_question"]
    assert [item.item_type for item in pack.current_state] == ["current_state"]
    assert [item.item_type for item in pack.relevant_sources] == ["source"]


def test_builder_tie_breaks_by_signal_count_then_path(tmp_path: Path) -> None:
    first_ref = ContextEvidenceRef("main", "doc-first", "chunk-first")
    second_ref = ContextEvidenceRef("main", "doc-second", "chunk-second")
    first = make_result(
        rank=1,
        document_id="doc-first",
        chunk_id="chunk-first",
        path="wiki/b.md",
        signals=(
            RetrievalSignal(
                kind="keyword",
                source_id="keyword:first",
                rank=1,
                score=1.0,
                backend="sqlite-fts5",
                index_revision="keyword-1",
                explanation="keyword matched",
            ),
        ),
    )
    second = make_result(
        rank=1,
        document_id="doc-second",
        chunk_id="chunk-second",
        path="wiki/a.md",
        signals=(
            RetrievalSignal(
                kind="keyword",
                source_id="keyword:second",
                rank=1,
                score=1.0,
                backend="sqlite-fts5",
                index_revision="keyword-1",
                explanation="keyword matched",
            ),
            RetrievalSignal(
                kind="vector",
                source_id="vector:second",
                rank=2,
                score=0.9,
                backend="chroma",
                index_revision="vector-1",
                explanation="vector matched",
            ),
        ),
    )
    pack = make_builder(
        tmp_path=tmp_path,
        response=make_search_response(results=(first, second)),
        resolver=StaticResolver(
            {
                first_ref: make_resolved(first_ref, path="wiki/b.md"),
                second_ref: make_resolved(second_ref, path="wiki/a.md"),
            }
        ),
    ).build(ContextPackRequest(goal="Build context", requested_scope=QueryScope(vault_ids=("main",))))

    assert [item.evidence_refs[0].chunk_id for item in pack.relevant_pages] == ["chunk-second", "chunk-first"]


def test_builder_caps_large_retrieval_limit_by_evidence_budget(tmp_path: Path) -> None:
    ref = ContextEvidenceRef("main", "doc-1", "chunk-1")
    retrieval = RecordingRetrievalService(make_search_response())
    builder = SearchContextPackBuilder(
        catalog=make_catalog(tmp_path),
        retrieval_service=cast(ContextRetrievalService, retrieval),
        evidence_resolver=StaticResolver({ref: make_resolved(ref)}),
        clock=fixed_clock,
    )

    builder.build(
        ContextPackRequest(
            goal="Build context",
            requested_scope=QueryScope(vault_ids=("main",)),
            retrieval_limit=10_000,
            budget=ContextPackBudget(max_evidence_items=24),
        )
    )

    assert retrieval.calls[0]["limit"] == 96


def test_builder_keeps_durable_page_before_raw_source_and_lexical_tie_break(tmp_path: Path) -> None:
    page_ref = ContextEvidenceRef("main", "doc-page", "chunk-page")
    raw_ref = ContextEvidenceRef("main", "doc-raw", "chunk-raw")
    alpha_ref = ContextEvidenceRef("main", "doc-alpha", "chunk-alpha")
    beta_ref = ContextEvidenceRef("main", "doc-beta", "chunk-beta")
    page = make_result(rank=1, document_id="doc-page", chunk_id="chunk-page", path="wiki/page.md")
    raw = make_result(rank=1, document_id="doc-raw", chunk_id="chunk-raw", path="raw/source.md")
    alpha = make_result(rank=1, document_id="doc-alpha", chunk_id="chunk-alpha", path="wiki/a.md")
    beta = make_result(rank=1, document_id="doc-beta", chunk_id="chunk-beta", path="wiki/b.md")

    pack = make_builder(
        tmp_path=tmp_path,
        response=make_search_response(results=(raw, beta, page, alpha)),
        resolver=StaticResolver(
            {
                page_ref: make_resolved(page_ref, path="wiki/page.md"),
                raw_ref: make_resolved(raw_ref, path="raw/source.md"),
                alpha_ref: make_resolved(alpha_ref, path="wiki/a.md"),
                beta_ref: make_resolved(beta_ref, path="wiki/b.md"),
            }
        ),
    ).build(ContextPackRequest(goal="Build context", requested_scope=QueryScope(vault_ids=("main",))))

    assert [evidence.path for evidence in pack.evidence] == [
        "wiki/a.md",
        "wiki/b.md",
        "wiki/page.md",
        "raw/source.md",
    ]
```

- [ ] **Step 2: Run builder tests to confirm failure**

Run:

```bash
uv run --python 3.12 pytest tests/test_context_pack_builder.py -q
```

Expected: fails because `current_state` is never filled and current classification/sort rules are Phase 4A minimal rules.

- [ ] **Step 3: Implement classification and sort refinements**

In `src/vault_graph/context/context_pack_builder.py`, add constants near `_planned_item_sort_key(...)`:

```python
_CONSTRAINT_TERMS = ("constraint", "principle", "invariant", "policy", "convention")
_OPEN_QUESTION_TERMS = ("question", "todo", "follow-up", "issue", "revisit")
_CURRENT_STATE_TERMS = ("current-state", "current_state")
_CURRENT_STATE_PATH_SUFFIXES = ("/status.md", "/current-state.md", "/current_state.md")
```

Replace `_planned_item_sort_key`, `_item_type`, and `_items_by_type` with the
exact code blocks named `Classification rules` and `Packing sort key` in this
document. Change `current_state=()` in `SearchContextPackBuilder.build(...)` to
`current_state=items_by_type["current_state"]`.

- [ ] **Step 4: Run builder tests**

Run:

```bash
uv run --python 3.12 pytest tests/test_context_pack_builder.py tests/test_context_pack_evidence_budget.py -q
```

Expected: all selected tests pass.

- [ ] **Step 5: Commit builder work**

```bash
git add src/vault_graph/context/context_pack_builder.py tests/test_context_pack_builder.py
git commit -m "feat(context): refine context pack section classification"
```

## Task 3: Add CLI Context Tests

**Files:**

- Create: `tests/test_cli_context.py`
- Modify: `tests/test_cli_surface_boundary.py`
- Modify: `tests/test_context_pack_serialization.py`

- [ ] **Step 1: Update CLI surface test**

Replace `test_cli_surface_exposes_search_but_not_answer_or_context_commands` in `tests/test_cli_surface_boundary.py` with:

```python
def test_cli_surface_exposes_context_but_not_answer_command() -> None:
    result = runner.invoke(app, ["--help"])

    assert result.exit_code == 0
    assert "search" in result.output
    assert "related" in result.output
    assert "decision-trace" in result.output
    assert "context" in result.output
    assert "ask" not in result.output
```

- [ ] **Step 2: Create CLI context tests**

Create `tests/test_cli_context.py`:

```python
from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

from pytest import MonkeyPatch
from typer.testing import CliRunner

from tests.test_cli_search import _deterministic_text_embeddings, write_page
from tests.test_context_pack_contract import make_pack, make_pack_with_warning
from tests.test_read_only_boundary import file_bytes
from vault_graph.cli.main import app
from vault_graph.context import (
    ContextEvidence,
    ContextEvidenceRef,
    ContextPack,
    ContextPackActualScope,
    ContextPackRequest,
    ContextPackRequestedScope,
    ContextPackRenderer,
    ContextPackScope,
    ContextPackStoreRevision,
    ContextPackVault,
    ContextPackVaultRevision,
    ContextPackWarning,
    DefaultContextPackRenderer,
)
from vault_graph.ingestion.vault_catalog import QueryScope, VaultCatalog, VaultCatalogEntry

runner = CliRunner()


class _RecordingContextPackBuilder:
    def __init__(self, pack: ContextPack) -> None:
        self.pack = pack
        self.calls: list[ContextPackRequest] = []
        self.include_graph_from_factory: bool | None = None

    def build(self, request: ContextPackRequest) -> ContextPack:
        self.calls.append(request)
        return self.pack


def _catalog(tmp_path: Path, vault_ids: tuple[str, ...] = ("default", "second")) -> VaultCatalog:
    entries = []
    for vault_id in vault_ids:
        root = tmp_path / vault_id
        root.mkdir(exist_ok=True)
        entries.append(VaultCatalogEntry.from_root(vault_id=vault_id, root_path=root, content_scopes=("wiki", "docs")))
    return VaultCatalog.from_entries(entries=entries, active_vault_id=vault_ids[0])


def state_tree(path: Path) -> tuple[str, ...]:
    if not path.exists():
        return ()
    return tuple(sorted(str(child.relative_to(path)) for child in path.rglob("*")))


def make_multi_vault_pack() -> ContextPack:
    first_ref = ContextEvidenceRef("default", "doc-shared", "chunk-shared")
    second_ref = ContextEvidenceRef("second", "doc-shared", "chunk-shared")
    first_evidence = ContextEvidence(
        ref=first_ref,
        path="wiki/shared.md",
        section="Shared",
        anchor="shared",
        content_hash="hash-default",
        raw_sha256="raw-default",
        metadata_index_revision="metadata-default",
        vault_revision="git-default",
        excerpt="default evidence",
        excerpt_token_count=2,
        truncated=False,
        retrieval_reasons=("keyword matched",),
        warnings=(),
    )
    second_evidence = ContextEvidence(
        ref=second_ref,
        path="wiki/shared.md",
        section="Shared",
        anchor="shared",
        content_hash="hash-second",
        raw_sha256="raw-second",
        metadata_index_revision="metadata-second",
        vault_revision="git-second",
        excerpt="second evidence",
        excerpt_token_count=2,
        truncated=False,
        retrieval_reasons=("vector matched",),
        warnings=(),
    )
    return replace(
        make_pack(),
        scope=ContextPackScope(
            requested=ContextPackRequestedScope(
                vault_ids=("default", "second"),
                content_scopes=("wiki", "docs"),
                include_cross_vault=False,
            ),
            actual_scopes=(
                ContextPackActualScope(
                    vault_ids=("default",),
                    content_scopes=("wiki", "docs"),
                    include_cross_vault=False,
                    scope_key="default:wiki,docs:local",
                ),
                ContextPackActualScope(
                    vault_ids=("second",),
                    content_scopes=("wiki", "docs"),
                    include_cross_vault=False,
                    scope_key="second:wiki,docs:local",
                ),
            ),
        ),
        vaults=(
            ContextPackVault(vault_id="default", display_name="default"),
            ContextPackVault(vault_id="second", display_name="second"),
        ),
        vault_revisions=(
            ContextPackVaultRevision(vault_id="default", revision="git-default", revision_kind="git"),
            ContextPackVaultRevision(vault_id="second", revision="git-second", revision_kind="git"),
        ),
        store_revisions=(
            ContextPackStoreRevision(
                kind="metadata",
                revision="metadata-default",
                vault_id="default",
                scope_key="default:wiki,docs:local",
            ),
            ContextPackStoreRevision(
                kind="metadata",
                revision="metadata-second",
                vault_id="second",
                scope_key="second:wiki,docs:local",
            ),
        ),
        warnings=(
            ContextPackWarning(
                code="stale_projection",
                severity="warning",
                message="Second Vault vector projection is stale.",
                affected_vault_ids=("second",),
                evidence_refs=(second_ref,),
                scope_key="second:wiki,docs:local",
                source_code="vector_stale",
                source_kind="retrieval",
            ),
        ),
        evidence=(first_evidence, second_evidence),
    )


class _SentinelRenderer:
    def __init__(self) -> None:
        self.json_pack: ContextPack | None = None
        self.markdown_pack: ContextPack | None = None

    def render_json(self, pack: ContextPack) -> str:
        self.json_pack = pack
        return "{\"sentinel\":\"json\"}\n"

    def render_markdown(self, pack: ContextPack) -> str:
        self.markdown_pack = pack
        return "SENTINEL MARKDOWN\n"


def _install_fake_context(
    *,
    monkeypatch: MonkeyPatch,
    tmp_path: Path,
    builder: _RecordingContextPackBuilder,
    renderer: ContextPackRenderer | None = None,
) -> VaultCatalog:
    catalog = _catalog(tmp_path)

    def fake_catalog(_: Path) -> tuple[object, VaultCatalog]:
        return object(), catalog

    def fake_context_builder_service(
        _: Path,
        *,
        config: object,
        catalog: VaultCatalog,
        include_graph: bool = False,
    ) -> tuple[_RecordingContextPackBuilder, ContextPackRenderer]:
        builder.include_graph_from_factory = include_graph
        return builder, renderer or DefaultContextPackRenderer()

    monkeypatch.setattr("vault_graph.cli.main._catalog", fake_catalog)
    monkeypatch.setattr("vault_graph.cli.main._context_builder_service", fake_context_builder_service)
    return catalog


def test_cli_context_json_uses_context_pack_contract(tmp_path: Path, monkeypatch: MonkeyPatch) -> None:
    builder = _RecordingContextPackBuilder(make_pack_with_warning())
    _install_fake_context(monkeypatch=monkeypatch, tmp_path=tmp_path, builder=builder)

    result = runner.invoke(app, ["context", "--state", str(tmp_path / "state"), "--format", "json", "Build context"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["context_pack_schema_version"] == "context-pack-v1"
    assert payload["warnings"][0]["code"] == "graph_unavailable"
    assert builder.calls[0].goal == "Build context"
    assert builder.calls[0].budget.max_tokens == 8000
    assert builder.calls[0].retrieval_limit == 10
    assert builder.calls[0].include_graph is False


def test_cli_context_uses_injected_renderer_for_markdown_and_preserves_warnings(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    builder = _RecordingContextPackBuilder(make_pack_with_warning(code="search_degraded", message="Vector unavailable"))
    renderer = _SentinelRenderer()
    _install_fake_context(monkeypatch=monkeypatch, tmp_path=tmp_path, builder=builder, renderer=renderer)

    result = runner.invoke(app, ["context", "--state", str(tmp_path / "state"), "Build context"])

    assert result.exit_code == 0
    assert result.stdout == "SENTINEL MARKDOWN\n"
    assert renderer.markdown_pack is builder.pack
    assert renderer.markdown_pack.warnings[0].code == "search_degraded"


def test_cli_context_uses_injected_renderer_for_json(tmp_path: Path, monkeypatch: MonkeyPatch) -> None:
    builder = _RecordingContextPackBuilder(make_pack())
    renderer = _SentinelRenderer()
    _install_fake_context(monkeypatch=monkeypatch, tmp_path=tmp_path, builder=builder, renderer=renderer)

    result = runner.invoke(app, ["context", "--state", str(tmp_path / "state"), "--format", "json", "Build context"])

    assert result.exit_code == 0
    assert result.stdout == "{\"sentinel\":\"json\"}\n"
    assert renderer.json_pack is builder.pack


def test_cli_context_passes_limit_budget_and_graph_flags(tmp_path: Path, monkeypatch: MonkeyPatch) -> None:
    builder = _RecordingContextPackBuilder(make_pack())
    _install_fake_context(monkeypatch=monkeypatch, tmp_path=tmp_path, builder=builder)

    result = runner.invoke(
        app,
        [
            "context",
            "--state",
            str(tmp_path / "state"),
            "--all-vaults",
            "--include-graph",
            "--include-cross-vault",
            "--max-tokens",
            "1200",
            "--limit",
            "7",
            "Build context",
        ],
    )

    assert result.exit_code == 0
    request = builder.calls[0]
    assert builder.include_graph_from_factory is True
    assert request.budget.max_tokens == 1200
    assert request.retrieval_limit == 7
    assert request.include_graph is True
    assert request.include_cross_vault is True
    assert request.requested_scope.vault_ids == ("default", "second")
    assert request.requested_scope.include_cross_vault is True


def test_cli_context_validates_options_before_opening_stores(tmp_path: Path, monkeypatch: MonkeyPatch) -> None:
    def fail_factory(*_: object, **__: object) -> object:
        raise AssertionError("invalid options must not open context stores")

    monkeypatch.setattr("vault_graph.cli.main._context_builder_service", fail_factory)

    invalid_format = runner.invoke(
        app,
        ["context", "--state", str(tmp_path / "state"), "--format", "xml", "Build"],
    )
    assert invalid_format.exit_code == 1
    assert "unsupported_format" in invalid_format.stdout
    assert "empty_goal" in runner.invoke(app, ["context", "--state", str(tmp_path / "state"), "   "]).stdout
    assert "context_budget_too_small" in runner.invoke(
        app, ["context", "--state", str(tmp_path / "state"), "--max-tokens", "999", "Build"]
    ).stdout
    assert "context_limit_must_be_positive" in runner.invoke(
        app, ["context", "--state", str(tmp_path / "state"), "--limit", "0", "Build"]
    ).stdout


def test_cli_context_rejects_invalid_scope_flag_combinations(tmp_path: Path) -> None:
    both_scope_flags = runner.invoke(
        app,
        ["context", "--state", str(tmp_path / "state"), "--vault-id", "default", "--all-vaults", "Build"],
    )
    cross_without_graph = runner.invoke(
        app,
        ["context", "--state", str(tmp_path / "state"), "--all-vaults", "--include-cross-vault", "Build"],
    )
    cross_without_all_vaults = runner.invoke(
        app,
        ["context", "--state", str(tmp_path / "state"), "--include-graph", "--include-cross-vault", "Build"],
    )

    assert both_scope_flags.exit_code == 1
    assert "Use either --vault-id or --all-vaults" in both_scope_flags.stdout
    assert cross_without_graph.exit_code == 1
    assert "include_cross_vault_requires_multi_vault_graph_scope" in cross_without_graph.stdout
    assert cross_without_all_vaults.exit_code == 1
    assert "include_cross_vault_requires_multi_vault_graph_scope" in cross_without_all_vaults.stdout


def test_cli_context_unknown_vault_does_not_open_builder_or_graph(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    vault_root = tmp_path / "vault"
    vault_root.mkdir()
    state_path = tmp_path / "state"
    runner.invoke(app, ["init", "--vault", str(vault_root), "--state", str(state_path)])

    def fail_context_builder(*_: object, **__: object) -> object:
        raise AssertionError("unknown vault must not open context builder dependencies")

    def fail_graph_open(_: object) -> object:
        raise AssertionError("unknown vault must not open graph retrieval state")

    monkeypatch.setattr("vault_graph.cli.main._context_builder_service", fail_context_builder)
    monkeypatch.setattr("vault_graph.cli.main._graph_retrieval_service", fail_graph_open)

    result = runner.invoke(
        app,
        ["context", "--state", str(state_path), "--vault-id", "missing", "--include-graph", "Build"],
    )

    assert result.exit_code == 1
    assert "unknown vault_id: missing" in result.stdout


def test_cli_context_without_include_graph_does_not_open_graph_state(tmp_path: Path, monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setattr("vault_graph.cli.main._text_embeddings", _deterministic_text_embeddings)
    monkeypatch.setattr("vault_graph.cli.main._search_text_embeddings", _deterministic_text_embeddings)

    def fail_graph_open(_: object) -> None:
        raise AssertionError("plain context must not open graph retrieval state")

    monkeypatch.setattr("vault_graph.cli.main._graph_retrieval_service", fail_graph_open)
    vault_root = tmp_path / "vault"
    write_page(vault_root, "wiki/page.md", "# Page\nGraphRAG evidence\n")
    state_path = tmp_path / "state"
    runner.invoke(app, ["init", "--vault", str(vault_root), "--state", str(state_path)])
    runner.invoke(app, ["index", "--state", str(state_path)])
    before = file_bytes(vault_root)

    result = runner.invoke(app, ["context", "--state", str(state_path), "GraphRAG"])

    assert result.exit_code == 0
    assert "wiki/page.md" in result.stdout
    assert file_bytes(vault_root) == before


def test_cli_context_missing_metadata_exits_nonzero_without_creating_projection_files(tmp_path: Path) -> None:
    vault_root = tmp_path / "vault"
    write_page(vault_root, "wiki/page.md", "# Page\nGraphRAG evidence\n")
    state_path = tmp_path / "state"
    runner.invoke(app, ["init", "--vault", str(vault_root), "--state", str(state_path)])
    before_state = state_tree(state_path)

    result = runner.invoke(app, ["context", "--state", str(state_path), "GraphRAG"])

    assert result.exit_code == 1
    assert "metadata_unavailable" in result.stdout or "keyword_index_unavailable" in result.stdout
    assert state_tree(state_path) == before_state
    assert not (state_path / "metadata" / "metadata.sqlite3").exists()
    assert not (state_path / "vector").exists()
    assert not (state_path / "graph").exists()
    assert not (state_path / "projection_cache").exists()
    assert not (state_path / "data" / "projection_cache").exists()


def test_cli_context_all_vaults_preserves_requested_vault_ids(tmp_path: Path, monkeypatch: MonkeyPatch) -> None:
    builder = _RecordingContextPackBuilder(make_pack())
    _install_fake_context(monkeypatch=monkeypatch, tmp_path=tmp_path, builder=builder)

    result = runner.invoke(
        app,
        ["context", "--state", str(tmp_path / "state"), "--all-vaults", "--format", "json", "Build"],
    )

    assert result.exit_code == 0
    assert builder.calls[0].requested_scope.vault_ids == ("default", "second")


def test_cli_context_all_vaults_preserves_evidence_warning_and_revision_vault_ids(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    builder = _RecordingContextPackBuilder(make_multi_vault_pack())
    _install_fake_context(monkeypatch=monkeypatch, tmp_path=tmp_path, builder=builder)

    result = runner.invoke(
        app,
        ["context", "--state", str(tmp_path / "state"), "--all-vaults", "--format", "json", "Build"],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert [item["vault_id"] for item in payload["vaults"]] == ["default", "second"]
    assert [item["ref"]["vault_id"] for item in payload["evidence"]] == ["default", "second"]
    assert payload["warnings"][0]["affected_vault_ids"] == ["second"]
    assert payload["warnings"][0]["evidence_refs"][0]["vault_id"] == "second"
    assert [item["vault_id"] for item in payload["vault_revisions"]] == ["default", "second"]
    assert [item["vault_id"] for item in payload["store_revisions"]] == ["default", "second"]
    markdown = DefaultContextPackRenderer().render_markdown(builder.pack)
    assert "[second] wiki/shared.md#shared" in markdown
    assert "second:wiki,docs:local" in markdown
    assert "stale_projection" in markdown
```

- [ ] **Step 3: Remove the Phase 4A-only CLI context boundary test**

Delete `test_cli_does_not_format_context_pack_sections_in_phase_4a` from
`tests/test_context_pack_serialization.py`. Phase 4B intentionally imports the
context renderer in the CLI adapter, and renderer delegation is now proven by
`test_cli_context_uses_injected_renderer_for_markdown_and_preserves_warnings`
and `test_cli_context_uses_injected_renderer_for_json`.

- [ ] **Step 4: Run CLI context tests to confirm failure**

Run:

```bash
uv run --python 3.12 pytest tests/test_cli_context.py tests/test_cli_surface_boundary.py tests/test_context_pack_serialization.py -q
```

Expected: fails because `vg context` and `_context_builder_service` do not exist.

- [ ] **Step 5: Keep red tests unstaged until Task 4 is green**

Do not create a commit after this step. Stage and commit `tests/test_cli_context.py`
`tests/test_cli_surface_boundary.py`, and `tests/test_context_pack_serialization.py`
in Task 4 Step 7 after the command implementation passes.

## Task 4: Implement `vg context`

**Files:**

- Modify: `src/vault_graph/cli/main.py`

- [ ] **Step 1: Add imports**

Add imports to `src/vault_graph/cli/main.py`:

```python
from vault_graph.context import (
    DEFAULT_CONTEXT_MAX_TOKENS,
    DEFAULT_CONTEXT_RETRIEVAL_LIMIT,
    ContextPackBudget,
    ContextPackRenderer,
    ContextPackRequest,
    DefaultContextPackRenderer,
    MetadataContextEvidenceResolver,
    SearchContextPackBuilder,
)
```

Add `ContextPackError` to the `vault_graph.errors` import list.

- [ ] **Step 2: Refactor search factories**

Add `_read_only_search_components` and `_search_service_with_metadata` exactly
as specified in the Component And Interface Spec. Replace the body of
`_search_service` with the wrapper body specified there.

- [ ] **Step 3: Add context factory and helpers**

Add `_context_builder_service` and `_context_scope_for_flags` exactly as
specified in the Component And Interface Spec.

- [ ] **Step 4: Add command implementation**

Add the `context(...)` command below `search(...)` or immediately before it:

```python
@app.command("context")
def context(
    goal: str = typer.Argument(..., help="Concrete task or goal."),
    state: Path = typer.Option(Path(".vault-graph"), "--state", help="Vault Graph state path."),
    vault_id: str | None = typer.Option(None, "--vault-id", help="Build context for one registered Vault ID."),
    all_vaults: bool = typer.Option(False, "--all-vaults", help="Build context for all enabled registered Vaults."),
    output_format: str = typer.Option("markdown", "--format", help="Output format: json or markdown."),
    max_tokens: int = typer.Option(DEFAULT_CONTEXT_MAX_TOKENS, "--max-tokens", help="Estimated context token budget."),
    limit: int = typer.Option(DEFAULT_CONTEXT_RETRIEVAL_LIMIT, "--limit", help="Retrieval results before packing."),
    include_graph: bool = typer.Option(False, "--include-graph", help="Include explicit graph retrieval signals."),
    include_cross_vault: bool = typer.Option(
        False,
        "--include-cross-vault",
        help="Include explicit cross-Vault graph relationships.",
    ),
) -> None:
    if not goal.strip():
        typer.echo("empty_goal")
        raise typer.Exit(1)
    if all_vaults and vault_id:
        typer.echo("Use either --vault-id or --all-vaults, not both.")
        raise typer.Exit(1)
    if output_format not in {"json", "markdown"}:
        typer.echo("unsupported_format")
        raise typer.Exit(1)
    if max_tokens < 1000:
        typer.echo("context_budget_too_small")
        raise typer.Exit(1)
    if limit <= 0:
        typer.echo("context_limit_must_be_positive")
        raise typer.Exit(1)
    if include_cross_vault and not (include_graph and all_vaults):
        typer.echo("include_cross_vault_requires_multi_vault_graph_scope")
        raise typer.Exit(1)
    config, catalog = _exit_on_domain_error(lambda: _catalog(state))
    scope = _exit_on_domain_error(
        lambda: _context_scope_for_flags(
            catalog,
            vault_id=vault_id,
            all_vaults=all_vaults,
            include_cross_vault=include_cross_vault,
        )
    )
    builder, renderer = _exit_on_domain_error(
        lambda: _context_builder_service(
            state,
            config=config,
            catalog=catalog,
            include_graph=include_graph,
        )
    )
    request = ContextPackRequest(
        goal=goal,
        requested_scope=scope,
        budget=ContextPackBudget(max_tokens=max_tokens),
        retrieval_limit=limit,
        include_graph=include_graph,
        include_cross_vault=include_cross_vault,
    )
    pack = _exit_on_domain_error(lambda: builder.build(request))
    if output_format == "json":
        typer.echo(renderer.render_json(pack), nl=False)
    else:
        typer.echo(renderer.render_markdown(pack), nl=False)
```

- [ ] **Step 5: Update domain error conversion**

Add `ContextPackError` to `_exit_on_domain_error(...)`:

```python
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
```

- [ ] **Step 6: Run CLI context tests**

Run:

```bash
uv run --python 3.12 pytest tests/test_cli_context.py tests/test_cli_search.py tests/test_cli_surface_boundary.py tests/test_context_pack_serialization.py -q
```

Expected: all selected tests pass.

- [ ] **Step 7: Commit CLI work**

```bash
git add src/vault_graph/cli/main.py tests/test_cli_context.py tests/test_cli_surface_boundary.py tests/test_context_pack_serialization.py
git commit -m "feat(cli): add local context pack command"
```

## Task 5: Add Boundary And Integration Coverage

**Files:**

- Modify: `tests/test_context_pack_import_boundaries.py`
- Modify: `tests/test_cli_context.py`

- [ ] **Step 1: Add import-boundary assertion for CLI context**

Append to `tests/test_context_pack_import_boundaries.py`:

```python
def test_cli_import_with_context_command_does_not_load_rustworkx_projection_adapter() -> None:
    code = """
import sys
import vault_graph.cli.main
for name in (
    'vault_graph.projection.rustworkx_projection',
    'rustworkx',
):
    if name in sys.modules:
        raise SystemExit(name)
"""
    completed = subprocess.run([sys.executable, "-c", code], check=False, capture_output=True, text=True)

    assert completed.returncode == 0, completed.stderr or completed.stdout
```

- [ ] **Step 2: Add graph requested warning integration test**

Append to `tests/test_cli_context.py`:

```python
def test_cli_context_include_graph_preserves_graph_unavailable_warning(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    monkeypatch.setattr("vault_graph.cli.main._text_embeddings", _deterministic_text_embeddings)
    monkeypatch.setattr("vault_graph.cli.main._search_text_embeddings", _deterministic_text_embeddings)

    class _UnavailableGraphSearchSource:
        def graph_candidates_for_search(self, **_: object) -> object:
            from vault_graph.errors import SearchError

            raise SearchError("graph_missing")

    def graph_factory(_: Path) -> tuple[object, VaultCatalog, _UnavailableGraphSearchSource]:
        catalog = VaultCatalog.from_entries(
            entries=(VaultCatalogEntry.from_root(vault_id="default", root_path=vault_root),),
            active_vault_id="default",
        )
        return object(), catalog, _UnavailableGraphSearchSource()

    vault_root = tmp_path / "vault"
    write_page(vault_root, "wiki/page.md", "# Page\nGraphRAG evidence\n")
    state_path = tmp_path / "state"
    runner.invoke(app, ["init", "--vault", str(vault_root), "--state", str(state_path)])
    runner.invoke(app, ["index", "--state", str(state_path)])
    before_vault = file_bytes(vault_root)
    before_state = state_tree(state_path)
    monkeypatch.setattr("vault_graph.cli.main._graph_retrieval_service", graph_factory)

    result = runner.invoke(
        app,
        ["context", "--state", str(state_path), "--include-graph", "--format", "json", "GraphRAG"],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert any(warning["code"] == "graph_unavailable" for warning in payload["warnings"])
    assert payload["backend"]["graph_store"]["used"] is False
    assert file_bytes(vault_root) == before_vault
    assert state_tree(state_path) == before_state


def test_cli_context_all_vaults_does_not_modify_registered_vault_files(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"
    write_page(first, "wiki/page.md", "# First\nGraphRAG evidence\n")
    write_page(second, "wiki/page.md", "# Second\nGraphRAG evidence\n")
    state_path = tmp_path / "state"
    runner.invoke(app, ["init", "--vault", str(first), "--state", str(state_path)])
    runner.invoke(app, ["vault", "add", "second", "--path", str(second), "--state", str(state_path)])
    before_first = file_bytes(first)
    before_second = file_bytes(second)
    builder = _RecordingContextPackBuilder(make_multi_vault_pack())

    def fake_context_builder_service(
        _: Path,
        *,
        config: object,
        catalog: VaultCatalog,
        include_graph: bool = False,
    ) -> tuple[_RecordingContextPackBuilder, ContextPackRenderer]:
        return builder, DefaultContextPackRenderer()

    monkeypatch.setattr("vault_graph.cli.main._context_builder_service", fake_context_builder_service)

    result = runner.invoke(app, ["context", "--state", str(state_path), "--all-vaults", "GraphRAG"])

    assert result.exit_code == 0
    assert builder.calls[0].requested_scope.vault_ids == ("default", "second")
    assert file_bytes(first) == before_first
    assert file_bytes(second) == before_second
```

- [ ] **Step 3: Run boundary and integration tests**

Run:

```bash
uv run --python 3.12 pytest tests/test_cli_context.py tests/test_context_pack_import_boundaries.py tests/test_retrieval_import_boundaries.py -q
```

Expected: all selected tests pass and CLI import still does not load rustworkx.

- [ ] **Step 4: Commit boundary coverage**

```bash
git add tests/test_cli_context.py tests/test_context_pack_import_boundaries.py
git commit -m "test(context): cover cli context read-only boundaries"
```

## Task 6: Full Verification

**Files:**

- No required file changes.

- [ ] **Step 1: Run focused Phase 4B tests**

```bash
uv run --python 3.12 pytest tests/test_cli_context.py tests/test_cli_search.py tests/test_cli_surface_boundary.py tests/test_context_pack_renderer.py tests/test_context_pack_builder.py tests/test_context_pack_serialization.py tests/test_context_pack_import_boundaries.py -q
```

Expected: all selected tests pass.

- [ ] **Step 2: Run full test suite**

```bash
uv run --python 3.12 pytest -q
```

Expected: all tests pass.

- [ ] **Step 3: Run lint**

```bash
uv run --python 3.12 ruff check src tests
```

Expected: `All checks passed!`

- [ ] **Step 4: Run static typing**

```bash
uv run --python 3.12 mypy src tests
```

Expected: `Success: no issues found`.

- [ ] **Step 5: Run whitespace check**

```bash
git diff --check
```

Expected: no output and exit code 0.

- [ ] **Step 6: Confirm no uncommitted implementation changes remain**

Run:

```bash
git status --short
```

Expected: no output.

## Review Checklist For Implementers

Security:

- Invalid options exit before opening stores.
- Evidence paths remain Vault-relative and are validated by the builder.
- Markdown escapes Vault-derived text and uses collision-safe fences.
- The command writes only to stdout.

Performance:

- `--limit` is passed to `ContextPackRequest.retrieval_limit`.
- The builder cap still prevents excessive retrieval fanout.
- Evidence resolution remains deduped by `(vault_id, document_id, chunk_id)`.
- Plain context does not open graph retrieval state.

Testability:

- CLI behavior is tested with fake builders for argument wiring.
- End-to-end local behavior is tested with temp Vaults and deterministic embeddings.
- Renderer tests assert Markdown as a view over JSON DTO fields.
- Import-boundary tests prevent accidental concrete backend imports in `vault_graph.context`.

Maintainability:

- CLI owns only argument parsing, scope selection, factory wiring, and output selection.
- `vault_graph.context` owns pack assembly and rendering.
- No new store interface or pack persistence layer is introduced.
- Existing Phase 4A contracts remain the canonical JSON authority.
