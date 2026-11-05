# Vault Graph TODO

This file is the single backlog for deferred work, scale-up candidates, and
future adapter directions. Keep `docs/SPEC.md` focused on the active product
contract. Promote an item from this file into a focused SPEC or implementation
plan before changing code.

## Operating Rules

- Vault remains the durable source of truth.
- Vault Graph TODOs must preserve rebuildable, local-first behavior. Indexes stay
  derived data.
- Vault Graph never creates, edits, renames, or deletes Vault files directly.
  The only Vault write is `remember` running the Vault tool's publish-draft.
  Vault Graph never writes to `raw/`.
- Do not add default hosted services or hidden write paths.
- Keep future adapters behind existing deep module interfaces when possible.
- Every accepted TODO needs tests proving Vault is unchanged on every path
  other than `remember`, plus multi-vault identity, stale-state handling, and
  explicit warnings before implementation.

## Active Roadmap: Local-Graph

See [`docs/SPEC.md`](SPEC.md) §9 for the summary and
[spec 2026-10-29-local-graph-memory-layer](specs/2026-10-29-local-graph-memory-layer/spec.md)
for full contracts and acceptance criteria.

The former Software Invariant Engine roadmap (VS-1 to VS-6) is archived in
[`docs/archive/SPEC-v5.0.md`](archive/SPEC-v5.0.md) and will not be implemented.

### First Pass (1차)

- [ ] **1차-0:** Archive SPEC v5.0, write the Local-Graph SPEC, align boundary
  documents on one write rule
- [ ] **Prerequisites:** modularization remediation 1 and 5 before 1차-2,
  remediation 6 before 1차-3, the rest in parallel or after the first pass
- [ ] **1차-1:** Search parity baseline (measurement 1) before changes
- [ ] **1차-2:** Read `vault-map.json` version 2 (decision 9)
- [ ] **1차-3:** Session-start recall `vg hook session-start` (decision 10)
- [ ] **1차-4:** MCP `remember` through Vault publish-draft (decision 8) and
  README update
- [ ] **1차-5:** Korean particle stripping in a separate keyword index column
- [ ] **1차-6:** Re-run measurement 1 and record the result

### Later Passes (n차)

Promote each item to its own spec before starting.

- [ ] **n차-1:** Exclude superseded claims from default results and recall,
  weight recent memory (needs 의존4, 의존5)
- [ ] **n차-2:** Interpret memory frontmatter and add `get_profile` (needs 의존5)
- [ ] **n차-3:** Code and memory in one query, MCP `explain_symbol`, decide on
  code chunk indexing (needs first pass)
- [ ] **n차-4:** The default embedding model (`e5-small`) was chosen by a person
  (DECISIONS 2026-11-04). Still open: check `e5-small` against the previous
  MiniLM model with measurement 1
- [ ] **n차-5:** Replace polling watch with file change events (`watchfiles`)
- [ ] **n차-6:** Classify `raw/sessions/<agent>/` by source and search them in
  evidence mode (needs 의존2)
- [ ] **n차-7:** Replace `project-bindings.json` and own Vault registration with
  `vault-map.json` reading (needs 1차-2)
- [ ] **n차-8:** MCP `recall` tool and question-based recall (needs 1차-3)
- [ ] **n차-9:** Re-measure measurement 1 condition B with real collector
  output (needs 의존2)
- [ ] **n차-10:** Read-only `vg memory review` over usage records (needs 1차-3
  and two weeks of usage records)
- [ ] **n차-11:** UserPromptSubmit recall from the first prompt (needs
  measurement 1 and an extended 의존1)
- [ ] **n차-12:** Count `m:` ID mentions in `raw/sessions/` to improve usage
  counts (needs 의존2)

### Vault And vault-builder Dependencies (Not Implemented In Vault Graph)

Vault Graph does not build these. The owner implements them.

| Code | Dependency | Owner | Status |
|---|---|---|---|
| 의존1 | SessionStart hook branches to `vg hook session-start`, falls back to `recall.sh` on a non-zero exit | vault-builder (user-scope hook) | Not implemented |
| 의존2 | Session collector and `raw/sessions/` (decision 5) | Vault tools, vault-builder template | Not implemented |
| 의존3 | Vault `AGENTS.md` rule 1 exception: collector may only add new files under `raw/sessions/` (decision 11) | Vault, vault-builder | Not implemented, sent as request 1 |
| 의존4 | Cleanup skill and automatic memory confirmation rule (decision 6) | Vault tools | Not implemented |
| 의존5 | Memory frontmatter schema `vault-memory/v1` with `pin` and `memory_kind` | vault-builder, shipped in Vault tools | Not implemented |
| 의존6 | Version marker for publish-draft command and draft format | Vault tools | Command exists, version marker not implemented |
| 의존7 | Keep `vault-map.json` version 2 format | vault-builder | Implemented |

vault-builder request document: vault-builder repository
`docs/superpowers/specs/2026-10-29-vault-graph-requests-ko.md` (not committed yet).

## Deferred Product Candidates

### Browser UI Layer

Status: pruned from core contract per 2026-09-06 decision (`docs/SPEC.md` §9.2). Local CLI & stdio MCP are canonical.

Phase 7B and Phase 7C remain optional browser UI work over existing services.
The first UI should be a small local surface over HTTP JSON endpoints, not a new
retrieval engine, answer engine, memory store, index backend, or Vault
publication workflow.

Required direction:

- use existing application services only
- preserve Vault IDs, evidence links, warnings, revisions, and freshness
- keep `127.0.0.1` as the local default
- avoid hosted UI, auth, and remote sharing until a separate security design

### OKF-Compatible Projection

Status: deferred implementation candidate.

Vault Graph may later add OKF compatibility as a projection/export layer over
Vault-derived state. OKF must not replace Vault, become a second source of
truth, or introduce a writable knowledge core.

Required direction:

- consume Vault-derived Markdown/frontmatter and graph/search/context outputs
- export portable projection records with evidence references
- keep Vault Graph as consumer/compiler, not an OKF authoring system
- keep implementation behind an explicit spec and feature flag

## Indexing And Retrieval Scale-Up

### MacBook Local Acceleration Adapter

Status: future adapter.

The default remains `FastEmbedTextEmbeddings` on local CPU. A MacBook
acceleration path should be added as a `TextEmbeddings` adapter, not by changing
`VectorIndexer`, `VectorStore`, or Chroma behavior.

Candidate adapter names:

- `CoreMLTextEmbeddings` for ONNX Runtime CoreML Execution Provider
- `AppleAcceleratedTextEmbeddings` if the adapter may choose CoreML, MLX, or
  another Apple-local runtime

Required direction:

- implement `TextEmbeddings`
- return a complete `EmbeddingModelSpec`
- keep CPU FastEmbed as the default until benchmark and deterministic-output
  evidence exists
- package acceleration as an optional extra such as `vault-graph[apple-accel]`
- fail clearly if configured acceleration is unavailable; do not silently fall
  back to CPU
- treat runtime changes as model-spec changes unless tests prove vector
  equivalence
- keep model artifacts and compiled runtime caches outside registered Vault
  roots
- report runtime/provider/cache/active-acceleration status in `vg status`

Required validation:

- supported model operators on the selected Apple runtime
- CPU versus accelerated embedding dimension, normalization, and similarity
  drift on fixed multilingual samples
- first-run compile time, warm-run throughput, memory, and battery impact
- offline behavior after model and compiled cache are present
- read-only boundary tests
- regression tests proving acceleration failure does not corrupt metadata,
  vector manifests, or existing CPU vector projections

### Non-Markdown Document Reader Adapters

Status: future adapter.

The default indexing policy remains Markdown-only. Future non-Markdown support
must use read-only document reader adapters and must not convert, rewrite,
rename, delete, or create files inside a registered Vault root.

Recommended boundary:

```text
VaultLoader
  -> DocumentReaderRegistry
      -> MarkdownDocumentReader
      -> PlainTextDocumentReader
      -> PdfDocumentReader
      -> DocxDocumentReader
  -> DocumentNormalizer
  -> MetadataStore
  -> VectorIndexer
```

Required direction:

- start with `.txt` if a non-Markdown reader is needed
- add PDF only after source-location evidence can include page numbers and text
  offsets
- add DOCX only after heading and paragraph extraction is deterministic
- keep OCR, spreadsheets, slides, images, and audio as later optional adapters
- compute `raw_sha256` from source bytes
- return reader name, reader version, parser version, extraction warnings, and
  source locators
- keep extracted caches disposable and outside registered Vault roots
- keep optional dependencies explicit with clear status diagnostics
- enforce file-size, extraction-time, symlink, and path-escape limits

Required validation:

- unsupported files do not mutate Vault and do not break Markdown indexing
- stable hashes and deterministic chunk IDs
- reader-version or extraction-option changes stale affected records
- same relative path in different Vaults does not collide
- evidence resolution returns original Vault path and format-specific locator
- missing optional dependencies produce clear status output

### Markdown Chunking Strategy Migration

Status: first production slice implemented; future readers remain separate
adapters.

Current default: `document-block-window-v2` with retrieval policy
`parent-neighbor-v1`.

Delivered boundary:

```text
source bytes
  -> DocumentReaderRegistry
  -> structural blocks with section paths and source locators
  -> document-block-window-v2 leaf chunks
  -> metadata authority and keyword/vector projections
  -> parent-neighbor-v1 query-time context
```

The legacy `heading-section-v1` shape is no longer the default. The current
planner bounds leaf chunks, keeps raw evidence separate from contextual
embedding text, and stores generic section paths and format-neutral locators.
`MarkdownDocumentReader` is enabled first; it remains the only default reader
until each optional adapter has independent dependency, locator, and recovery
tests.

The current implementation:

- parses structural Markdown blocks
- groups adjacent blocks within a deterministic token budget
- preserves code fences and tables unless deterministic oversized splitting is
  required
- includes compact heading breadcrumbs only in embedding input
- keeps evidence rendering tied to original Vault paths, headings, anchors,
  locators, and hashes
- tombstones old-version vectors only inside the selected `QueryScope`

Future adapter work:

- add PlainText, PDF, and DOCX readers behind the same extraction contract
- add format-specific locator and optional-dependency recovery tests
- benchmark and tune budgets only after retrieval evidence justifies it

Required validation:

- deterministic chunk IDs for unchanged Markdown
- stable chunk IDs for unrelated edits
- large sections split under `max_tokens`
- small sections receive heading breadcrumb context
- chunker-version changes stale affected metadata and vector records
- parent/neighbor expansion respects `QueryScope`
- retrieval-policy changes do not stale vectors when chunk text is unchanged
- no Vault file mutation

### Backend Scale-Up

Status: pruned from core contract per 2026-09-06 decision (`docs/SPEC.md` §9.2).

Postgres, Qdrant, and Neo4j backends are formally pruned to maintain a zero-infrastructure, local-first single-process architecture (SQLite WAL and rustworkx).

## Serving, Security, And Agent Adapters

### Remote HTTP And Authentication

Status: future security design.

Current HTTP serving is local-only and read-only. Remote serving, authentication,
TLS, origin policy, and hosted deployment require a separate security design.

Required direction:

- keep `127.0.0.1` as the default bind address
- document threat model before exposing remote access
- preserve read-only behavior
- avoid store-direct HTTP endpoints
- keep HTTP as an adapter over application services

### LLM-Backed Answer Composer

Status: future answer adapter.

The default answer composer remains deterministic and extractive. An LLM-backed
composer may be added only behind `AnswerComposer`.

Required direction:

- preserve `CitationGuard`
- label unsupported claims as partial or insufficient evidence
- never write answer content into Vault Graph indexes as authority
- keep hosted model usage optional and explicit
- preserve deterministic fallback behavior

### External Memory Layer Adapter And Export Target

Status: future adapter/export target.

External memory systems such as Mem0, MemMachine, or MCP memory servers may be
useful later for personalization, cross-session recall, or shared memory between
agent runtimes. They must consume projection exports; they must not become a
Vault Graph core store.

Required direction:

- Vault remains the durable source of truth
- Vault Graph memory projections remain read-only, disposable, and rebuildable
- no external adapter may write, rename, rewrite, delete, publish, or validate
  Vault content
- no generated memory may become a fact unless captured in Vault and re-indexed
- outbound records include `vault_id`, evidence refs, store revisions,
  generated timestamps, freshness, warnings, and export schema version
- profile, preference, procedural, and raw episode memories stay outside Vault
  Graph core unless represented as durable Vault notes

Recommended future adapter shape:

```python
class MemoryProjectionExporter(Protocol):
    def export_project_memory(
        self,
        projection: ProjectMemoryProjection,
    ) -> tuple[MemoryExportRecord, ...]: ...

    def export_recent_changes(
        self,
        projection: RecentChangesProjection,
    ) -> tuple[MemoryExportRecord, ...]: ...
```

Required validation:

- exported records are reproducible from the same Vault-derived state
- deleting the external adapter loses no Vault Graph truth
- no external memory dependency is imported by default
- adapter failures do not break search, context packs, graph, or memory
  projections
- cross-Vault exports preserve Vault IDs and never merge by title alone

## CLI And Operations

### Reset Index Command

Status: future ergonomic CLI.

`vg reset-index` is not required for the current release. Users can delete
Vault Graph internal state and run `vg index` again. Add a command only after a
real user-facing gap appears.

Required direction:

- call an application service, not ad hoc path deletion
- enforce path safety so only Vault Graph state is removed
- never delete Vault content
- explain the equivalent manual recovery path in command output

### Release And Publishing Operations

Status: ongoing operations.

A release is one git tag `vX.Y.Z` and its published GitHub Release. Users
install a release with `git+https://github.com/cutehackers/vault-graph.git@vX.Y.Z`.
Vault Graph no longer publishes to PyPI or TestPyPI. See `docs/PUBLISHING.md`.

Required direction:

- PR and push run verification only
- only the manual `release` workflow creates tags and GitHub Releases
- `release` creates no tag until every check passes, and it releases only
  commits already on `origin/main`
- GitHub Releases have no attached files
- no PyPI or TestPyPI upload

Left for a person:

- decide whether to keep, yank, or delete the `vault-graph` project on PyPI
  (0.2.1 is the last upload)
- delete the `pypi` and `testpypi` GitHub environments
- delete the Trusted Publishers on PyPI and TestPyPI
