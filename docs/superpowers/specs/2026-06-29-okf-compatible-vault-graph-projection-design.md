# OKF-Compatible Vault Graph Projection SPEC

Status: Deferred implementation candidate

Date: 2026-06-29

Scope: Optional future OKF compatibility, readiness, and export layer over
Vault Graph

Release position: This document is not part of the current release scope. It is
a future SPEC for a later implementation decision after the evidence-first
Vault Graph release is stable.

## 1. Purpose

This SPEC defines the recommended way to use Open Knowledge Format (OKF) to
improve Vault and Vault Graph without weakening the existing source-of-truth
boundary.

The recommended path is:

```text
Vault source of truth
  -> Vault Graph read-only indexing
  -> OKF-compatible projection/readiness/export
  -> agents, external tools, or exchange bundles
```

Do not convert Vault itself into a minimal OKF bundle. Vault is stricter than
OKF: raw sources are immutable, semantic drafts must be validated, durable wiki
claims require provenance, index/log pages carry the local wiki schema, and
release gates protect the repository. OKF should be used as an interoperability
and context-exchange projection, not as a replacement governance model.

## 2. Research Basis

Wiki pages consulted:

- `/Users/junhyounglee/vault/wiki/concepts/open-knowledge-format.md`
- `/Users/junhyounglee/vault/wiki/comparisons/open-knowledge-format-vs-rag.md`
- `/Users/junhyounglee/vault/wiki/workflows/okf-bundle-authoring.md`
- `/Users/junhyounglee/vault/wiki/systems/vault-graph.md`
- `/Users/junhyounglee/vault/wiki/workflows/read-only-rebuildable-indexing.md`
- `/Users/junhyounglee/vault/wiki/decisions/build-vault-graph-as-read-only-projection-layer.md`

Upstream OKF source consulted:

- `https://github.com/GoogleCloudPlatform/knowledge-catalog/blob/main/okf/SPEC.md`
- `https://github.com/GoogleCloudPlatform/knowledge-catalog`

Relevant OKF facts:

- OKF v0.1 is draft-stage.
- A bundle is a directory tree of Markdown files.
- Every non-reserved concept file must have YAML frontmatter with non-empty
  `type`.
- `title`, `description`, `resource`, `tags`, and `timestamp` are recommended
  optional fields.
- `index.md` and `log.md` are reserved filenames.
- Consumers must tolerate unknown types, unknown fields, missing optional
  fields, missing index files, and broken links.
- Markdown links express directed relationships; the relationship type is
  inferred from surrounding prose.

Current Vault Graph contracts consulted:

- `docs/SPEC.md`
- `docs/DESIGN.md`
- `docs/FEATURES.md`
- `docs/DECISIONS.md`
- `docs/CONVENTIONS.md`
- `docs/PATCH_LOG.md`
- current ingestion, metadata, context-pack, CLI, MCP, and answer code surfaces

## 3. Recommendation

Adopt an optional `OKFCompatibility` layer in Vault Graph.

This layer should provide three capabilities:

1. `vg okf check` reports whether a registered Vault can be projected into an
   OKF-compatible bundle and which files need metadata or link attention.
2. `vg okf export --output PATH` writes an explicit, derived OKF-compatible
   bundle outside Vault content.
3. Context packs and ask responses may include stable OKF concept IDs so agents
   can move between Vault Graph evidence and exported OKF documents.

This is the best option because it improves interoperability while preserving
all core values:

- Vault remains the durable source of truth.
- Vault Graph remains read-only over Vault.
- OKF output is rebuildable projection state.
- Existing stricter provenance and release-gate rules stay intact.
- The first implementation can reuse current frontmatter parsing, Markdown
  parsing, metadata indexing, path guards, and CLI service boundaries.

## 4. Options Considered

| Option | Summary | Decision |
| --- | --- | --- |
| Make Vault itself conform to OKF v0.1 | Rewrite or relax Vault schema so `wiki/` is directly an OKF bundle | Reject |
| Add OKF fields to every Vault page | Mutate durable wiki pages until they look more like OKF concepts | Reject |
| Use OKF only as documentation guidance | Keep current system and add prose notes only | Reject as too weak |
| Add read-only OKF projection/export in Vault Graph | Generate OKF-compatible views from indexed Vault state | Accept |

Why the rejected options fail:

- Direct conversion conflicts with Vault's reserved `index.md` and `log.md`
  pages, which intentionally carry Vault frontmatter and quality metadata.
- Mutating durable wiki pages for OKF compatibility risks downgrading
  provenance-first validation to a weaker minimal schema.
- Documentation-only guidance does not give agents or external tools a portable
  artifact.

## 5. Product Outcome

The implementation is complete when:

- `vg okf check` reads indexed Vault state and reports OKF projection readiness.
- `vg okf check --format json` returns a stable readiness DTO.
- `vg okf export --output PATH` writes an OKF-compatible bundle to an explicit
  output path that is not inside the registered Vault root unless the user
  explicitly selects a safe derived-output path.
- generated concept files contain valid OKF frontmatter.
- generated `index.md` and `log.md` files follow OKF reserved-file rules.
- Vault's `raw/`, `wiki/`, `docs/`, `scratch/`, and Git metadata are not
  mutated.
- multi-Vault output preserves `vault_id` and never merges concepts from
  different Vaults by title alone.
- context packs and ask output can expose `okf_concept_id` fields when the OKF
  projection is available.

## 6. Non-Goals

This SPEC must not implement or require:

- automatic Vault publication
- direct edits to Vault pages
- direct edits to raw sources
- weakening Vault provenance validation
- treating OKF output as durable Vault knowledge
- hosted services or network calls
- a central OKF type registry
- cross-Vault concept merging
- external memory storage
- UI screens
- automatic contradiction resolution

## 7. User-Facing Surface

### 7.1 CLI Commands

Add a new CLI group:

```bash
vg okf check
vg okf check --vault-id ID
vg okf check --all-vaults
vg okf check --format text
vg okf check --format json
vg okf export --output /path/to/bundle
vg okf export --vault-id ID --output /path/to/bundle
vg okf export --all-vaults --output /path/to/bundle
vg okf export --dry-run --output /path/to/bundle
```

Defaults:

- active Vault scope
- `--format text`
- no graph requirement
- no network
- no Vault writes

Validation:

- `--vault-id` and `--all-vaults` are mutually exclusive.
- `--output` is required for export.
- export refuses to overwrite a non-empty directory unless `--force` is added in
  a later slice.
- export refuses registered Vault roots and Vault content paths by default.
- `--dry-run` prints the manifest and warnings without writing files.

### 7.2 Future MCP Surface

MCP should not be part of the first implementation. After CLI check/export is
stable, MCP can expose read-only resources:

```text
vault://{vault_id}/okf/manifest
vault://{vault_id}/okf/concepts/{concept_id}
```

These resources must be generated from application services, not from direct
store queries inside `vault_graph.mcp`.

## 8. OKF Profile For Vault Projection

Vault Graph should generate an OKF profile rather than pretending the source
Vault directory is already a raw OKF bundle.

Profile name:

```text
vault-graph-okf-profile-v1
```

Concept ID rule:

```text
concept_id = vault_id + "/" + vault_relative_path_without_md
```

Examples:

```text
default/wiki/concepts/open-knowledge-format
default/wiki/sources/okf-research-report-20260629
default/docs/SPEC
```

Reserved-file rule:

- source `wiki/index.md` becomes generated navigation, not an OKF concept;
- source `wiki/log.md` becomes generated history, not an OKF concept;
- any source `index.md` or `log.md` under a non-Vault wiki directory is treated
  as a reserved-file warning unless the projection has a specific mapping rule;
- reserved source files are still visible in readiness output so users know why
  they were excluded from concept export.

Frontmatter mapping:

| OKF field | Vault Graph source |
| --- | --- |
| `type` | mapped from Vault `type`, or derived from path kind; never empty |
| `title` | Vault `title`, first heading, or filename-derived title |
| `description` | Vault `summary`, OKF `description`, or first non-empty body sentence |
| `resource` | stable `vault://{vault_id}/{path}` URI |
| `tags` | Vault `tags` plus projection tags such as `vault`, `wiki`, `source` |
| `timestamp` | Vault `updated`, `created`, or indexed timestamp |

Additional producer-defined fields:

```yaml
vault_id: default
vault_path: wiki/concepts/open-knowledge-format.md
vault_document_id: "..."
vault_content_hash: "..."
vault_raw_sha256: "..."
vault_frontmatter_hash: "..."
vault_graph_index_revision: "..."
vault_quality:
  provenance: claim
  contradictions: none
  review_required: false
```

These fields preserve Vault-specific auditability while staying valid OKF
extensions.

## 9. Data Contracts

Add:

```text
src/vault_graph/okf/__init__.py
src/vault_graph/okf/okf_models.py
src/vault_graph/okf/okf_profile.py
src/vault_graph/okf/okf_readiness.py
src/vault_graph/okf/okf_exporter.py
src/vault_graph/okf/okf_renderer.py
src/vault_graph/app/okf_projection_service.py
tests/test_okf_profile.py
tests/test_okf_readiness.py
tests/test_okf_exporter.py
tests/test_okf_renderer.py
tests/test_okf_projection_service.py
tests/test_cli_okf.py
tests/test_okf_read_only_boundary.py
tests/test_okf_multi_vault.py
```

Core DTOs:

```python
from dataclasses import dataclass
from typing import Literal

OkfWarningSeverity = Literal["info", "warning", "error"]

@dataclass(frozen=True)
class OkfConceptId:
    vault_id: str
    concept_id: str
    source_path: str

@dataclass(frozen=True)
class OkfConceptProjection:
    identity: OkfConceptId
    type: str
    title: str | None
    description: str | None
    resource: str | None
    tags: tuple[str, ...]
    timestamp: str | None
    extra_frontmatter: dict[str, object]
    body: str
    source_document_id: str
    source_content_hash: str
    source_raw_sha256: str | None
    metadata_index_revision: str | None

@dataclass(frozen=True)
class OkfProjectionWarning:
    code: str
    severity: OkfWarningSeverity
    message: str
    vault_id: str
    source_path: str | None = None
    concept_id: str | None = None

@dataclass(frozen=True)
class OkfReadinessReport:
    profile_version: str
    okf_version: str
    vault_ids: tuple[str, ...]
    concept_count: int
    skipped_reserved_files: tuple[str, ...]
    warnings: tuple[OkfProjectionWarning, ...]

@dataclass(frozen=True)
class OkfBundleManifest:
    profile_version: str
    okf_version: str
    generated_at: str
    vault_ids: tuple[str, ...]
    concepts: tuple[OkfConceptProjection, ...]
    warnings: tuple[OkfProjectionWarning, ...]
```

Implementation detail:

- `dict[str, object]` in `extra_frontmatter` must be JSON/YAML-serializable.
- If a value is not serializable, readiness reports an error and export skips or
  stringifies only under an explicit, tested policy.

## 10. Service Boundary

`OkfProjectionService` is the deep module.

```python
@dataclass(frozen=True)
class OkfProjectionRequest:
    scope: QueryScope
    include_docs: bool = True
    include_wiki: bool = True
    include_raw_references: bool = False

class OkfProjectionService:
    def check(self, request: OkfProjectionRequest) -> OkfReadinessReport: ...
    def manifest(self, request: OkfProjectionRequest) -> OkfBundleManifest: ...
```

Responsibilities:

- read indexed documents through `MetadataStore`;
- apply the Vault OKF profile mapping;
- build deterministic concept IDs;
- detect reserved filename conflicts;
- detect missing required `type` projections;
- preserve Vault-specific evidence fields;
- return warnings instead of mutating Vault.

Must not own:

- CLI parsing;
- MCP serialization;
- direct filesystem export writes;
- direct SQLite queries;
- Vault file reads when indexed metadata is sufficient;
- Vault publication or validation.

`OkfExporter` owns explicit output writes. It writes only generated files under
the user-selected output directory.

## 11. Export Layout

For one Vault:

```text
okf-bundle/
├── index.md
├── log.md
├── manifest.json
└── default/
    ├── wiki/
    │   ├── concepts/
    │   │   └── open-knowledge-format.md
    │   ├── comparisons/
    │   └── workflows/
    └── docs/
        └── SPEC.md
```

For multiple Vaults:

```text
okf-bundle/
├── index.md
├── log.md
├── manifest.json
├── main/
│   └── ...
└── research/
    └── ...
```

Generated `index.md`:

- root `index.md` may include `okf_version: "0.1"` frontmatter;
- directory-level indexes must omit frontmatter;
- entries include concept title and description when available;
- entries link to generated concept files, not original Vault files.

Generated `log.md`:

- newest-first date headings;
- one entry per export operation;
- includes source Vault IDs, index revisions, and warning count;
- does not copy Vault's full `wiki/log.md` verbatim.

Generated `manifest.json`:

- machine-readable projection manifest;
- includes Vault IDs, index revisions, concept count, warnings, and source
  hashes;
- is a Vault Graph export artifact, not an OKF concept.

## 12. Readiness Rules

Errors:

- a non-reserved exported concept cannot produce non-empty `type`;
- generated concept path collides with `index.md` or `log.md`;
- output path is unsafe;
- frontmatter cannot be rendered as parseable YAML;
- export would mutate a registered Vault root or configured state store.

Warnings:

- missing `title`;
- missing `description`;
- broken internal Markdown link;
- source file is skipped because it is a reserved OKF filename;
- source page has provenance warnings in Vault frontmatter;
- source page is stale or has source drift according to indexed metadata;
- concept body is empty;
- concept has unknown type mapping.

OKF consumers tolerate broken links and unknown fields, but Vault Graph should
still report them because Vault's quality bar is higher than OKF's minimum
conformance.

## 13. Context Pack And Ask Integration

Add optional fields to rendered outputs only after the projection service exists:

```json
{
  "okf": {
    "profile_version": "vault-graph-okf-profile-v1",
    "concept_id": "default/wiki/concepts/open-knowledge-format",
    "resource": "vault://default/wiki/concepts/open-knowledge-format.md"
  }
}
```

Rules:

- canonical context-pack DTOs remain evidence-first Vault Graph DTOs;
- OKF fields are interoperability hints, not authority fields;
- existing `ContextEvidenceRef` and answer evidence IDs remain the authority for
  citation;
- if OKF projection is unavailable, context packs and answers degrade by
  omitting OKF hints.

## 14. Vault Improvements Enabled

The OKF projection improves Vault without changing Vault's durable schema:

- highlights pages that lack agent-friendly descriptions;
- surfaces inconsistent type vocabulary before export;
- reports broken links in a portable bundle view;
- creates a portable context bundle for external agents;
- keeps provenance and quality metadata available through OKF extension fields;
- gives humans a concrete interoperability artifact without relaxing release
  gates.

Recommended future Vault-side follow-up, outside this SPEC:

- document the local `vault-graph-okf-profile-v1` mapping in Vault docs after
  implementation proves useful;
- optionally add a Vault wiki page that records OKF as an exchange profile, not
  as the source-of-truth schema.

## 15. Vault Graph Improvements Enabled

The OKF layer improves Vault Graph by making document identity and concept
navigation more explicit:

- stable `okf_concept_id` gives agents a readable ID alongside hash-based
  document and chunk IDs;
- `type`, `title`, `description`, `resource`, `tags`, and `timestamp` become
  normalized retrieval/display fields;
- generated indexes provide progressive disclosure for external tools;
- export manifests make projection freshness easier to inspect;
- context packs and ask answers can reference portable concept IDs while keeping
  Vault evidence IDs authoritative.

## 16. Implementation Slices

### OKF-A: Projection DTOs And Profile Mapping

Implement `vault_graph.okf` DTOs and pure mapping functions.

Acceptance:

- maps Vault wiki pages into OKF concept projections;
- excludes reserved source files as concepts;
- derives non-empty `type` for every exported concept;
- preserves unknown Vault metadata under extension fields;
- includes deterministic multi-Vault concept IDs.

### OKF-B: Readiness Service And CLI Check

Implement `OkfProjectionService.check(...)` and `vg okf check`.

Acceptance:

- reads through `MetadataStore.list_documents(scope)`;
- emits JSON and text reports;
- reports reserved filename skips and missing metadata;
- performs no filesystem writes;
- passes read-only boundary tests.

### OKF-C: Exporter And CLI Export

Implement explicit output export.

Acceptance:

- writes an OKF-compatible bundle under `--output`;
- writes generated `index.md`, `log.md`, and `manifest.json`;
- refuses unsafe output paths;
- supports dry-run without writes;
- does not mutate Vault or Vault Graph state.

### OKF-D: Context/Ask Interoperability Hints

Expose optional OKF IDs in context-pack and answer renderers.

Acceptance:

- existing canonical evidence refs remain unchanged;
- OKF fields are omitted when no projection is available;
- tests prove no answer claim depends on OKF projection as source truth.

### OKF-E: MCP Resources

Add optional MCP resources over `OkfProjectionService`.

Acceptance:

- resources are read-only;
- resource URIs preserve Vault ID and concept ID;
- MCP does not perform export writes.

## 17. Verification Plan

Focused tests:

```bash
uv run --python 3.12 pytest \
  tests/test_okf_profile.py \
  tests/test_okf_readiness.py \
  tests/test_okf_exporter.py \
  tests/test_okf_renderer.py \
  tests/test_okf_projection_service.py \
  tests/test_cli_okf.py \
  tests/test_okf_read_only_boundary.py \
  tests/test_okf_multi_vault.py -q
```

Regression tests:

```bash
uv run --python 3.12 pytest tests/test_document_normalizer.py tests/test_vault_loader.py tests/test_context_pack_serialization.py -q
uv run --python 3.12 pytest tests/test_cli_surface_boundary.py tests/test_mcp_import_boundaries.py -q
uv run --python 3.12 ruff check src tests
uv run --python 3.12 mypy src tests
uv run --python 3.12 pytest -q
```

Manual smoke:

```bash
tmpdir="$(mktemp -d)"
uv run --python 3.12 vg init --vault /Users/junhyounglee/vault --state "$tmpdir/state"
uv run --python 3.12 vg index --state "$tmpdir/state"
uv run --python 3.12 vg okf check --state "$tmpdir/state"
uv run --python 3.12 vg okf export --state "$tmpdir/state" --output "$tmpdir/okf-bundle"
find "$tmpdir/okf-bundle" -maxdepth 3 -type f | sort | head
```

Safety checks:

```bash
git -C /Users/junhyounglee/vault diff --exit-code
git diff --check
```

## 18. Risks And Mitigations

| Risk | Mitigation |
| --- | --- |
| Agents treat exported OKF as durable truth | Label output as projection, include Vault evidence hashes, and keep Vault evidence IDs authoritative |
| Minimal OKF type values reduce local schema rigor | Use a local profile and preserve Vault `quality` metadata as extension fields |
| Reserved `index.md` / `log.md` conflict with Vault pages | Generate OKF reserved files separately and exclude source reserved files as concepts |
| Output path accidentally points into Vault | Reuse path-guard policy and reject registered Vault roots by default |
| Multi-Vault concept IDs collide | Prefix concept IDs with `vault_id` |
| Export introduces stale artifacts | Include metadata index revisions and generated timestamps in manifest and log |

## 19. Open Decisions

### Decision 1: Should OKF export include raw source wrappers?

Recommendation: not in the first implementation.

Reason: raw sources may lack OKF frontmatter and should remain immutable. Source
pages already summarize and cite raw material. Add `include_raw_references`
later only if external OKF consumers need first-class reference concepts.

### Decision 2: Should `vg okf export` allow output inside Vault `scratch/`?

Recommendation: start with no.

Reason: the safest default is to keep export artifacts outside Vault. If a user
wants a durable export inside Vault, that should be a separate Vault workflow
with explicit source/draft/log handling.

### Decision 3: Should OKF warnings fail export?

Recommendation: errors fail export; warnings do not.

Reason: OKF is intentionally permissive, but Vault Graph should still surface
quality gaps. This keeps interoperability useful while preserving visibility.

## 20. Handoff Summary

Implement `OKFCompatibility` as a read-only projection and explicit export layer
over current Vault Graph metadata. Do not mutate Vault. Do not downgrade Vault's
compiled-wiki governance. Treat OKF as a portable, agent-friendly exchange view
with stable concept IDs and generated navigation, while keeping Vault evidence
IDs, hashes, provenance, and release gates authoritative.
