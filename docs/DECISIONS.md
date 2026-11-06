# Decisions

This file records accepted product, architecture, and policy decisions for Vault
Graph.

## Writing Rule

Keep entries short. Record only the accepted decision, the reason it matters,
and the few guardrails needed to prevent drift. Put detailed plans, completion
criteria, implementation notes, and review history in `docs/SPEC.md`,
`docs/DESIGN.md`, `docs/PATCH_LOG.md`, or active plan documents.

Pending questions should be resolved with the user before implementation. If a
decision is not accepted yet, keep it in the active plan or discussion, not
here.

Implementation-only corrections that directly follow `docs/SPEC.md` and
`docs/DESIGN.md` are recorded in `docs/PATCH_LOG.md` instead.

## 2026-10-04 - Use Nolemy For Independent Package Distribution Names

**Question:** Which personal prefix should identify the independent graph packages?

**Decision:** Use `nolemy-graph-search` and `nolemy-graph-document`. The user explicitly selected `nolemy` and authorized continuing implementation.

**Reason:** Identify the publisher consistently and avoid the existing unrelated `graph-search` distribution.

**Implications:** Update wheel metadata, dependencies, lockfile, CI package selection, and installation examples. Keep `graph_search` and `graph_document` imports, repository paths, and persisted schema identifiers unchanged. Public publication remains a separate activity.

## 2026-10-04 - Separate Graph Document With Rule-Based Defaults

**Question:** Should the reusable graph document capability be managed as a separate package, and should semantic extraction be its default?

**Decision:** Specify a separate graph document package that reuses existing functionality and connects to graph_search. Keep explicit rule-based extraction as the default and document a suitable semantic extraction alternative. This scope was confirmed by the user's current request and follow-up answer.

**Reason:** Document extraction and derived graph management have a different responsibility from graph traversal. The existing rules can be reused without requiring a model for basic operation.

**Implications:** [DG-20261004](design/specs/2026-10-04-graph-document-ko.md) defines the detailed proposal and validation gates. Semantic extraction implementation, SQLite migration, production default switching, and unmeasured operating targets remain outside this accepted scope decision.

## 2026-09-07 - Eliminate Document-To-Code Binding And Adopt Stateless MCP Tri-Transport

**Question:** Should Vault Graph bind external documentation (ADRs, specs) to
code AST symbols, and how should the MCP interface align with Anthropic's
finalized stateless specification?

**Decision:** Completely sever all document-to-code bindings (eliminating Anchor
IDs, semantic doc anchoring, and documentation maintenance burdens) in favor of
self-contained code invariance (`src/`, `tests/`, `.vault-graph/invariants.yaml`).
Adopt Anthropic's finalized SEP-2575/SEP-3182 stateless MCP specification across
a Tri-Transport layer (HTTP, Stdio, CLI Bridge) with strict separation of
`params._meta` from business arguments, dynamic discovery (`server/discover`),
and 7 deep `vg_*` tools.

**Reason:** Binding prose documents to code symbols turns documentation into an
additional maintenance burden and source of entropy. A deterministic invariant
engine must enforce mechanical truth self-contained within code. Furthermore,
SEP-2575 requires stateless execution to allow concurrent multi-worktree scaling
without session affinity.

**Implications:**

- `docs/SPEC.md` removes all ADR-to-AST anchoring and vaporware claims.
- MCP tools use the standard `vg_*` namespace and accept pure domain arguments,
  extracting `client_request_id` and caller info from `params._meta`.
- The 5-step idempotency engine uses Autocommit and atomic Upsert to prevent
  failure state loss upon handler rollback.
- Root `.gitignore` tracks `.vault-graph/` governance ledgers while ignoring
  transient previews and runtime caches.
- Tier 0 structural invariants (acyclicity, deadlocks, read-only boundary) are
  strictly non-exemptible.

## 2026-09-06 - Pivot To Software Invariant Engine And Promote SPEC v5.0

**Question:** Should Vault Graph pivot from an evidence-first retrieval layer into
a deterministic Software Invariant Engine, and how should specification and
governance documents be consolidated?

**Decision:** Adopt the Software Invariant Engine identity and promote the
hardened specification suite to `docs/SPEC.md` (v5.0-pure-trinity) as the single
active product contract. Archive the previous v1.2 specification to
`docs/archive/SPEC-v1.2.md`. Enforce Tier 0-2 architectural invariants, declarative
rules (`.vault-graph/invariants.yaml`), and cross-worktree coordination while
preserving the existing 1,188 test baseline through a 3-phase adapter migration.

**Reason:** Autonomous AI coding agents cause architectural fragmentation and
semantic drift. Durable value lies in mechanical invariant enforcement, acyclicity,
and deterministic verification. Consolidating the specification into `docs/SPEC.md`
eliminates documentation fragmentation and establishes a single source of truth.

**Implications:**

- `docs/SPEC.md` is the canonical design document; `docs/archive/SPEC-v1.2.md`
  preserves the predecessor baseline for existing tests.
- Zero-write guarantees apply strictly to the static analysis engine (`O_RDONLY`);
  runtime worktree coordination uses an isolated, disk-backed SQLite WAL store
  under `~/.vault-graph/run/<repo_hash>/coordination.db`.
- Cycle detection uses global $O(V+E)$ SCC analysis and incremental reachability,
  with Git tree-hash content-addressed caching.
- Speculative distributed backends (Postgres, Neo4j, Qdrant, Web UI) are pruned
  in favor of local SQLite and rustworkx.
- Vault and answer synthesis modules transition through a 3-phase adapter
  migration without breaking existing tests.

## 2026-08-03 - Make Metadata Blobs The Single Plaintext Owner

**Question:** How should Vault Graph prevent raw, wiki, index, vector, and graph
projections from becoming duplicated knowledge stores?

**Decision:** Classify documents by authority role, connect provenance families,
persist distinct chunk plaintext only in metadata blobs, and keep keyword,
vector, and graph projections reference-only. Default knowledge search collapses
families; full rebuilds activate through an atomic projection manifest.

**Reason:** Vault is the durable authority. Derived stores must improve access
without multiplying knowledge authority or repeatedly returning the same source
lineage.

**Implications:** Explicit search modes preserve drill-down, projection hygiene
is auditable, incompatible v1 state requires a full rebuild, and Round 1 code
indexing must reuse the same authority/reference boundary.

## 2026-07-30 - Gate Expansion On Projection Deduplication

**Question:** Should Vault Graph begin code indexing immediately after accepting
the unified project-evidence direction?

**Decision:** No. First complete an Authority & Projection Hygiene gate over the
existing Vault and Vault Graph model. Separate raw evidence, canonical wiki
knowledge, operating documents, generated navigation, and audit reports; store
each derived plaintext body once; and collapse default search results by
provenance family.

**Reason:** Indexing raw, wiki, docs, and reports as co-equal content and storing
chunk plaintext in multiple projections creates token, storage, authority, and
maintenance ambiguity. Adding code before fixing that contract would multiply
the problem.

**Implications:**

- Default knowledge retrieval becomes canonical-wiki-first; raw evidence,
  operating docs, and audit reports require role-aware or explicit modes.
- FTS, vector, and graph projections reference canonical chunks instead of
  owning additional plaintext copies.
- Graph evidence resolves excerpts at read time rather than persisting them.
- Exact content hashes may share physical storage but never erase distinct
  provenance, paths, revisions, locks, or lifecycle.
- Code-index Round 1 does not start until the measurable completion gate in
  `docs/superpowers/reports/2026-07-30-vault-projection-duplication-direction-report-ko.md`
  passes.

## 2026-07-30 - Expand To A Unified Project Evidence Layer

**Question:** After completing Vault graph search, should Vault Graph remain
Vault-only, require code to be copied into Vault, delegate code indexing to an
external sidecar, or index registered source repositories as a separate
authority?

**Decision:** Expand Vault Graph into a local-first, read-only, rebuildable
project evidence and reasoning layer. Vault remains authoritative for durable
project knowledge. Each registered source repository remains authoritative for
its current executable code. Vault Graph may index both but must edit neither.

**Reason:** Coding agents need current code structure and durable project
decisions together. Copying code into Vault creates a stale second source, while
a mandatory external sidecar splits setup, freshness, provenance, and retrieval
contracts.

**Implications:**

- Round 1 builds a separate deterministic code projection, beginning with
  Python and Dart, instead of extending Markdown ingestion with code parsing.
- Round 2 adds a high-level project exploration service and MCP tool that
  combines code evidence, Vault evidence, impact, tests, and freshness.
- Vault documents and repository symbols with the same concept remain separate
  evidence records connected by typed relationships.
- Derived storage may deduplicate content physically, but it must preserve
  source kind, source ID, path, revision, and evidence location.
- Duplicate or overlapping repository registrations must be rejected.
- The detailed direction and two-round completion criteria live in
  `docs/superpowers/reports/2026-07-30-code-index-agent-context-direction-report-ko.md`.

## 2026-07-14 - Allow Explicit Easy Codex MCP Registration

**Question:** Should `vg setup` auto-register the Vault Graph MCP server for
Codex?

**Decision:** Yes, but only when the user passes `--mcp`. `vg setup --mcp`
registers the `vault-graph` stdio server in `$CODEX_HOME/config.toml` or
`~/.codex/config.toml`, and explicit `--mcp-config-path` remains available.

**Reason:** MCP must be easy enough for normal onboarding, while hidden writes
outside Vault Graph Data Home remain unacceptable.

**Implications:**

- `vg setup --vault PATH --agent codex --mcp` is the preferred easy path.
- Existing Codex config must be backed up before the `vault-graph` server entry
  changes.
- Unrelated Codex config entries must be preserved.
- Manual `vg mcp config` and `vg mcp register --config-path` commands remain
  available for explicit control.

## 2026-06-29 - Use Trusted Publishing With Release Approval

**Question:** How should Vault Graph publish public PyPI packages safely?

**Decision:** Publish through GitHub Actions, PyPI Trusted Publishing, and
GitHub environment approval. Pull requests and pushes run verification only.
TestPyPI publishing is manual. Production PyPI publishing runs only from a
published GitHub Release and waits at the `pypi` environment gate.

**Reason:** Public package files are difficult to recover from after mistakes,
and release credentials should not live on local machines or in repository
secrets.

**Implications:**

- Local `uv publish` is not the normal release path.
- GitHub workflows must grant `id-token: write` only to publish jobs.
- `pypi` requires a required reviewer before upload.
- README may promote `uv tool install vault-graph` only after PyPI publication
  is complete and verified.

## 2026-06-29 - Use MIT License For Public Distribution

**Question:** Which open-source license should Vault Graph use before public
PyPI distribution?

**Decision:** Use the MIT License for Vault Graph.

**Reason:** MIT keeps the project simple to adopt, compatible with common
developer tooling, and aligned with the goal of making Vault Graph easy to
install, inspect, and extend.

**Implications:**

- The source distribution and wheel include a `LICENSE` file.
- `pyproject.toml` declares MIT package metadata before PyPI publication.
- Future public packaging docs should describe Vault Graph as MIT-licensed.

## 2026-06-25 - Make Evidence-First Ask The Next Core Implementation

**Question:** After the first product implementation, should Vault Graph keep
`ask_vault` as future work or make cited question answering the next core
implementation target?

**Decision:** Make evidence-first ask and reasoning the next implementation
target. Implement `vg ask` and `ask_vault` as service-backed answer planning,
answer composition, and citation validation over existing Vault-derived search,
graph, context-pack, decision-trace, and memory projection services.

**Reason:** The first implementation can find, explain, and package Vault
context, but users still need a direct way to ask questions and receive
reasoned answers grounded in original Vault evidence.

**Implications:**

- `ask_vault` is not an external memory system and must not add a writable
  `MemoryStore`, hidden episode log, profile memory, preference memory, or
  procedural memory.
- Every major answer claim must be cited, explicitly labeled as inferred or
  partial, or rejected as insufficiently supported.
- The default implementation must preserve read-only, rebuildable, local-first,
  and evidence-first behavior.
- Optional LLM-backed composition may be added only behind the same
  `AnswerComposer` contract and citation guard.
- External memory systems remain adapter/export targets, not Vault Graph core.

## 2026-06-24 - Use Setup And MCP Registration As Onboarding Target

**Question:** Does Vault Graph need PyPI before documenting easy install and
agent setup?

**Decision:** Not for the current source-checkout workflow. Keep source checkout
and `uv tool install -e .` as the current install paths. Treat PyPI as required
only before promising `uv tool install vault-graph` as the public install path.
Use `vg setup --vault PATH --agent AGENT` as the source-checkout happy path, and
separate it from lower-level MCP registration commands.

**Reason:** Users need a simple local path now without depending on an
unpublished PyPI package, and MCP server installation must remain distinct from
agent MCP registration.

**Implications:**

- README must distinguish current source-checkout install paths from the future
  public PyPI install path.
- `vg setup` defaults omitted `--graph-home` to `~/.vault-graph`.
- MCP registration commands configure agents to run `vg serve --mcp`; they must
  not describe MCP registration as MCP server installation.
- PyPI publication can be handled as a release task, not as a blocker for local
  source-checkout usage.

## 2026-06-24 - Use Documented Index-State Rebuild Before Reset CLI

**Question:** Should Vault Graph add a user-facing `vg reset-index` command
before public release?

**Decision:** Not now. Document and test deletion of Vault Graph internal index
state followed by `vg index` / `vg index --vault-id`. Add `vg reset-index` only
after a real user-facing gap appears.

**Reason:** The smallest safe surface preserves the rebuildable-state value
without adding a destructive command prematurely.

**Implications:**

- Acceptance must prove metadata, keyword, vector, and graph state rebuild from
  Vault while Vault file hashes stay unchanged.
- Any manual deletion guidance is limited to Vault Graph Data Home directories, not
  registered Vault roots or Vault content.
- A future reset command must call an application service with path-safety
  checks, not delete backend files directly.

## 2026-06-24 - Use Deterministic Offline Smoke As Local-First Acceptance

**Question:** What is sufficient proof that local-first search works without
internet access?

**Decision:** Use a deterministic offline smoke test that disables or fakes
network/download paths and proves visible keyword-only degradation. Keep real
cached-model plus OS-level network-blocking checks as optional manual release
checks.

**Reason:** CI should verify the local-only boundary without depending on a
specific laptop cache, hosted service, or network state.

**Implications:**

- Offline acceptance must show the embedding model is unavailable locally,
  vector embedding is not attempted, keyword results still return, and warnings
  are visible.
- Tests must not download model artifacts or mutate embedding caches.
- The default embedding implementation remains local-first and may still use a
  cached model when available.

## 2026-06-24 - Split Implemented And Future CLI Documentation

**Question:** How should `docs/SPEC.md` present CLI commands after the first
implementation is complete?

**Decision:** Replace the old "Initial CLI" wording with implemented CLI
commands and a separate future-command block.

**Current note:** `vg watch`, `vg ask`, `vg setup`, MCP registration commands,
and `vg serve --http` are now implemented. This decision remains the
documentation rule for separating implemented commands from future commands; it
is no longer an availability statement about those commands.

**Reason:** The SPEC should expose only commands that are implemented and
covered by acceptance tests, while keeping later command ideas visibly separate.

**Implications:**

- Future commands must be marked TODO until implemented and covered by
  acceptance tests.
- Current CLI acceptance is evaluated against implemented commands only.

## 2026-06-23 - Keep Phase 7 As Read-Only Explorer UI

**Question:** Should the current Phase 7 design scope include local HTTP serving
and `Ask Project`, or focus only on optional read-only explorer views?

**Decision:** Keep the current Phase 7 detailed-design scope limited to Timeline
and Health UI, Decision Explorer, and Agent Workspace. Move local HTTP serving
and `Ask Project` out of Phase 7. At the time of this decision, `ask_vault` and
answer synthesis were also outside the Phase 7 UI scope.

**Current note:** This remains the UI scope decision. The `ask_vault` timing was
superseded by `2026-06-25 - Make Evidence-First Ask The Next Core
Implementation`.

**Reason:** Phase 7 should make existing evidence-linked projections easier to
inspect without introducing a weak search wrapper or an independent answer
engine. HTTP serving and evidence-first ask are handled by separate adapter and
answer-layer contracts.

**Implications:**

- Phase 7 UI surfaces existing CLI/MCP-backed application services visually.
- The UI must remain read-only, local-first, evidence-first, and Vault-scoped.
- UI view contracts must not query storage backends directly or create a new
  durable knowledge source.
- Future HTTP serving must remain an adapter over application services.
- Future answer generation requires a separate accepted design.

## 2026-06-19 - Keep External Memory Systems As Future Adapters

**Question:** Should Vault Graph adopt Mem0, MemMachine, or a similar external
memory layer as part of the Phase 6 core?

**Decision:** No. Keep Phase 6 memory as read-only, evidence-linked projections
over Vault-derived state. Record Mem0, MemMachine, and MCP memory servers as
future adapter or export targets only.

**Reason:** Vault must remain the durable source of truth. A writable memory
core would create a second authority and make project knowledge harder to audit
or rebuild.

**Implications:**

- Phase 6 must not add generic `MemoryStore`, `Memory.create`,
  `Memory.query`, `Memory.upsert`, `Memory.link`, `Memory.audit`, hidden
  episode logs, profile memory databases, preference memory databases, or
  procedural memory databases.
- Future external memory integration must consume exported projections and must
  not write Vault content or Vault Graph stores.
- Agent-generated memories become durable only after they enter Vault through
  the normal validation and Git workflow.

## 2026-06-12 - Use JSON-Canonical Opt-In Graph Context Packs

**Question:** What should Phase 4 context packs treat as canonical, and should
graph expansion be automatic?

**Decision:** Use canonical JSON context packs with Markdown as a rendering
view. Keep evidence chunks as the authority unit, make stale/conflict/budget
warnings first-class, use an 8,000-token default context budget, and keep graph
signals opt-in.

**Reason:** This preserves Vault Graph's evidence-first, read-only, rebuildable
value while keeping Phase 4 simple enough for MCP and HTTP to reuse later.

**Implications:**

- `vg context "goal"` uses keyword/vector retrieval by default.
- Graph and cross-Vault graph signals require explicit flags.
- Context packs are generated working context, not durable Vault knowledge.

## 2026-06-10 - Use Actual Scope Terminology During Pre-Release Development

**Question:** How should Vault Graph handle the scope terminology rename to
`actual_*` before public release?

**Decision:** Use `actual_*` as the only project terminology. Do not add
backward compatibility aliases, dual CLI/JSON keys, SQLite migrations, or graph
schema version bumps solely for the old scope names.

**Reason:** Vault Graph is still in pre-release development, and all derived
projection state is rebuildable. Keeping one name avoids carrying compatibility
complexity before any public contract exists.

**Implications:**

- CLI text, CLI JSON, Python contracts, docs, and SQLite graph columns use
  `actual_*` only.
- Existing local development graph DBs created with old names may be deleted and
  rebuilt.
- Compatibility work starts only after a public release or an accepted migration
  policy.

## 2026-06-10 - Keep Phase 3 Detailed Designs In Slice Documents

**Question:** How should Phase 3 stay detailed enough for implementation without
making `docs/SPEC.md` too long?

**Decision:** Keep the Phase 3 section of `docs/SPEC.md` as a concise top-level
contract and place the Phase 3 overview plus detailed slice designs under
`docs/superpowers/specs/phase-3/`.

**Reason:** This matches the Phase 2 slice style while keeping implementation
details easy to find and preventing the top-level SPEC from becoming a second
implementation plan.

**Implications:**

- Each Phase 3 slice gets a focused design document before its implementation.
- `docs/SPEC.md` links to slice documents instead of duplicating long data
  models and interface details.
- `docs/PATCH_LOG.md` records consistency corrections made during reviews.

## 2026-06-09 - Use Evidence Chunk As The Phase 2C Search Unit

**Question:** What should Phase 2C return as the canonical search result?

**Decision:** Return evidence chunks resolved through `MetadataStore`. Document,
page, source, and section results are grouping or rendering views over chunk
evidence, not separate canonical retrieval identities.

**Reason:** This best protects Vault Graph's value: search stays inspectable,
read-only, rebuildable, multi-vault-safe, and ready for later graph signals.

**Implications:**

- Keyword and vector stores return candidates only.
- `RetrievalService` owns merge, rank fusion, warnings, and evidence
  resolution.
- All-vault search expands into per-Vault actual scopes before candidate
  lookup.
- The local keyword index is a metadata subprojection updated with the metadata
  revision and exposed through a read-only candidate interface.
- `vg search` reads existing projections only and degrades visibly to
  keyword-only when vector search is unavailable.

## 2026-06-08 - Use Chroma-Backed Scope-Local Vector Reconcile

**Question:** How should Phase 2B turn metadata chunks into a sustainable local
vector projection?

**Decision:** Use Chroma as the default installed local `VectorStore`, update it
through scope-local reconcile during `vg index`, and keep `EmbeddingModelSpec`
as the model compatibility boundary.

**Reason:** This keeps the default workflow simple for users while preserving
Vault Graph's core rule: derived projections are rebuildable from Vault and
recoverable after partial failure.

**Implications:**

- `vg index` updates metadata and vector projections by default.
- Vector state is reconciled from live `MetadataStore` chunks plus the vector
  manifest, not patched from ad hoc changed-path assumptions.
- Chroma collections are keyed by `EmbeddingModelSpec`; Vault selection remains
  `vault_id` and `content_scope` filter metadata.
- Metadata and vector stores do not require a cross-store transaction. Vector
  failure is reported as stale or unavailable and recovered by the next index.

## 2026-06-08 - Use FastEmbed Multilingual MiniLM As Default Local Embeddings

**Question:** Which production local embedding implementation and model should
Phase 2B use by default?

**Decision:** Use `FastEmbedTextEmbeddings` with
`sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` as the default
local embedding implementation and model, pinned to FastEmbed artifact revision
`faf4aa4225822f3bc6376869cb1164e8e3feedd0`. The source model provenance
revision is `e8f8c211226b894fcb81acc59f3b34ba3efd5f42`.

**Current note:** The default model was replaced by `2026-11-04 - Default To
Arctic-L And Let Users Pick An Embedding Preset`, and then by `2026-11-04 -
Default To E5-Small After Measuring Arctic-L`. `2026-11-04 - Keep One Embedding
Model` removed the `minilm` preset. The guardrails below still apply to
`e5-small`.

**Reason:** Vault Graph must stay local-first and useful for mixed Korean and
English Vault content. A small 384-dimensional multilingual model keeps the
default simple while preserving the `TextEmbeddings` and `EmbeddingModelSpec`
replacement boundary.

**Implications:**

- The default does not require a hosted API.
- Model artifacts are cached outside registered Vault roots.
- Missing model artifacts may be downloaded on first use, but Vault Graph must
  not silently fall back to another model.
- FastEmbed artifact revision, dimensions, or spec changes make the vector
  projection stale.

## 2026-06-08 - Use Evidence-First Graph-Ready Hybrid Retrieval

**Question:** Should Phase 2 optimize around vector search alone, graph search
alone, answer-first generation, or a hybrid retrieval contract?

**Decision:** Use evidence-first graph-ready hybrid retrieval. Phase 2 implements
keyword plus vector retrieval and keeps graph signals as a later input that joins
the same result contract after `GraphStore` exists.

**Reason:** Vault Graph's core value is not fluent answer generation or opaque
semantic matching. Its value is read-only, rebuildable, evidence-linked access
to Vault. `VectorStore` should provide semantic candidates, `GraphStore` should
provide relationship candidates, and the retrieval layer should own candidate
fusion, ranking explanations, warnings, and evidence resolution.

**Implications:**

- `VectorStore` returns semantic candidates; it does not own hybrid policy,
  evidence authority, graph relationships, or durable wiki publication.
- `MetadataStore` resolves document and chunk evidence before results are
  rendered.
- `RetrievalService` or `HybridRetriever` owns fusion, ranking explanations,
  warnings, and final result assembly.
- Phase 2 is split into 2A retrieval contract, 2B vector indexing, and 2C
  keyword/vector search. Graph expansion, `vg ask`, context packs, and MCP/HTTP
  serving remain later phases.

## 2026-06-05 - Keep Python Package Namespace

**Question:** Should the implementation use `src/vault_graph/...` or put modules
directly under `src/`?

**Decision:** Keep `src/vault_graph/...`.

**Reason:** `src/` is the source root, while `vault_graph` is the product package
namespace. Keeping the namespace avoids generic import names such as
`ingestion`, `storage`, `indexing`, and `cli`, and preserves a clearer package
boundary for testing, installation, and future scale-up.

## 2026-08-04 - Name The Derived Data Root Vault Graph Data Home

**Question:** What user-facing term should describe the local, rebuildable root
that contains Vault Graph catalogs, projection generations, manifests, and
diagnostics?

**Decision:** Use **Vault Graph Data Home** as the canonical user-facing and
architecture term. Use `--graph-home PATH` as the only explicit CLI override;
do not retain a `--state` alias. Keep `~/.vault-graph` as the default path.

**Reason:** `state` is ambiguous to users and suggests transient runtime state.
Data Home describes the actual boundary: Vault Graph-owned derived data that is
rebuildable and must never replace Vault or a registered repository as a source
of truth.

**Implications:**

- New specifications, CLI help, MCP registration, and onboarding use Vault
  Graph Data Home and `--graph-home`.
- Internal names use `GraphHomeResolver` and Data Home manifest terminology.
- Existing project-local `.vault-graph` data is never discovered, read, or
  merged implicitly. Before the first release, choose a new `--graph-home`
  path and rebuild from Vault instead of migrating it.
- The implementation must remove `--state` from the supported public surface.

## 2026-08-04 - Rebuild Pre-Release Legacy Data Instead Of Shipping Migration

**Question:** Should the first Vault Graph release include a user-facing legacy
Data Home migration command?

**Decision:** No. Before the first public release, known legacy Data Home
layouts are detected and rejected without being read, copied, or merged. The
canonical recovery path is to choose a new `--graph-home` (or move the
rebuildable old directory aside) and run `vg setup` to rebuild projections from
Vault. New-user onboarding through `vg setup --vault PATH --agent codex --mcp`
is required for the release.

**Reason:** Vault Graph has no released compatibility contract yet, and its
Data Home contains rebuildable derived data rather than an authority. Shipping
migration now would add schema, catalog-conflict, and duplicate-projection
complexity before it is needed. Fail-closed detection still protects users
from accidentally opening two Data Homes or treating an old projection as a
source of truth.

**Implications:**

- `legacy_data_home_detected` is a recovery state, not a migration workflow.
- `setup`, `status`, MCP, and HTTP expose deterministic setup/rebuild hints.
- No `vg data-home migrate` or automatic adoption command is part of the first
  release; compatibility can be reconsidered after real release evidence.
- Historical design artifacts are not rewritten to fabricate a migration
  history; current code and canonical docs use the guard-and-rebuild policy.

## 2026-10-06 - Independent Embedding And Vector Modules

**Question:** Should embedding, vector search/storage, and incremental vector indexing become reusable modules while Vault policy remains separate?

**Decision:** Implement `nolemy-text-embeddings`, `nolemy-vector-search`, and `nolemy-vector-index` with domain-neutral public contracts. Keep Vault input preparation, identity/scope mapping, evidence, offline policy, status, and generation publication in `vault_graph.vault_adapter`. Preserve existing import paths and stored vector identities.

**Reason:** The user approved independent functional modules that can be used without Vault and requested complete integration with the existing system.

**Implications:**

- Generic packages do not import Vault or graph packages or interpret Vault metadata.
- Complete snapshots and partial changes have distinct deletion authority over explicit logical collections.
- Generic write operations do not promise rollback. Vault retains private staged writes and generation activation.
- Contracts and completion checks are defined in [the vector module specification](design/specs/2026-10-06-vector-modules-ko.md).

<a id="sel-20261015-scope"></a>
## 2026-10-15 - Group Bidirectional Search Evidence Linking Inside Vault Graph

**Question:** Should Vault Graph group search-target/evidence mapping and include reverse lookup from a document/chunk to its graph owners?

**Decision:** Specify one Vault-internal bidirectional linking capability. The user requested the internal capability, asked what reverse lookup means, and then explicitly answered ‘추가하라. 모듈구조를 생각해서 구현하는게 좋곘어.’ Keep generic packages independent and preserve current public search behavior. This accepts feature scope, not all detailed API choices or implementation slices.

**Reason:** A chunk can support multiple graph nodes/relationships and one owner can have multiple evidence chunks. Reusing existing identities and references avoids requiring generic vector/graph packages to interpret Vault. The considered alternative was consolidating only the existing forward resolution; the user selected inclusion of reverse lookup.

**Implications:** [SEL-20261015](design/specs/2026-10-15-search-evidence-linking-ko.md) defines the proposed API and validation. Owner and evidence Vaults remain distinct. Existing warning, rank, revision, read-only, and storage contracts remain unchanged. A new persistent mapping database, automatic vector-seeded graph expansion, and new external commands are excluded. GOAL-01/02 and INV-01–03 are affected. Detailed API proposal P-01 and technical assumptions remain in the parent contract; no old contract is retired.

<a id="vg-mod-20261015-implementation"></a>
## 2026-10-15 - Implement Functional Boundaries And Evidence Linking

**Question:** Should the reviewed modular architecture and bidirectional evidence-linking proposals now be implemented, and should remaining Vault capabilities become additional distributions?

**Decision:** Implement [VG-MOD-20261015](design/specs/2026-10-15-vault-graph-modular-architecture-ko.md), its ordered plan, and the SEL internal API. The user's explicit instruction to read and implement the specification and plan accepts Q-01/Q-02 and SEL P-01. Retain five reusable distributions and keep Vault-specific capabilities internal. Reuse cohesive implementations and move only the policies that need a clear owner. No durable slice contracts were created or implicitly approved.

**Reason:** The goal is predictable functional ownership and changeability. Additional distributions or a wholesale directory rewrite would add compatibility work without a demonstrated consumer.

**Implications:** Preserve source content, public responses, existing imports, schemas and generation recovery. New internal reverse lookup remains explicit and bounded. Implementation and outcome review, whole-suite/static checks, independent wheel installation, applicable performance checks and a current module diagram are required. Evidence is recorded in [the implementation report](design/reports/2026-10-15-modularization-completion-ko.md). This accepts implementation scope and design, not a claim of deployed readiness.

<a id="vg-mod-20261015-grouped-layout"></a>
## 2026-10-15 - Apply Approved Functional Groups To Source Directories

**Question:** Should the selected functional groups remain documentation labels or become the physical source structure?

**Decision:** Apply the user-approved grouped directories inside `vault_graph`: `indexing/{ingestion,extraction,publication}`, `retrieval/{search,graph,evidence,explanation}`, `context/{pack,memory,answer}`, `project/{code,context}`, `operation/{scope,readiness,diagnostics,runtime,integration}`, and `interface/{cli,mcp,http,composition}`. Keep `storage/interfaces` and `storage/local`, preserving existing stored representations. Treat `engine` as a logical category for the five unchanged distributions under `packages/`, without creating an engine directory.

**Reason:** The user explicitly approved the names and physical grouping so that source location follows the accepted ownership map. This extends the earlier limited-move decision without changing functional scope or package contracts.

**Implications:** [ARCHITECTURE.md](ARCHITECTURE.md) is the current source-structure reference. Retain legacy public imports through same-module compatibility facades and preserve leaf package APIs. New dependencies use consumer ports with concrete composition under `interface/composition`; the documented lazy constructor defaults remain limited compatibility exceptions. Preserve source immutability, rebuildable projections, normal read-only queries, explicit setup/configuration writer boundaries, and the five domain-neutral packages' prohibition on importing `vault_graph`. Record fresh relocation checks only after execution and retain earlier verification evidence as historical results.

## 2026-10-28 - Publish Only Vault Graph And Defer Module Distributions

**Question:** After the v0.2.0 PyPI upload failed on the first `nolemy-*` wheel, should the five modules be published as separate PyPI projects?

**Decision:** No. The user approved publishing only `vault-graph`, with the five module import packages bundled in its wheel and their external dependencies declared directly. `nolemy-*` move to the root development dependency group. The fix ships as 0.2.1 after a TestPyPI check. Separate module publishing to PyPI is deferred.

**Reason:** Trusted Publishing cannot create a PyPI project that does not exist yet, and each module would need its own project setup. One distribution restores the install path used through 0.1.4 while CI keeps enforcing module boundaries.

**Implications:** [Spec 2026-10-28-single-package-release](specs/2026-10-28-single-package-release/spec.md) defines the build and verification changes. No module Trusted Publisher is registered. Module `pyproject.toml` files, `nolemy-*` names, and version 0.1.0 stay unchanged so separate publishing can be enabled later. The 2026-10-04 naming decision still applies. The bundled top-level import names may collide with other distributions, and this change does not address that risk.

## 2026-10-30 - Archive SPEC v5.0 And Make Local-Graph The Active Contract

**Question:** Which product contract is active: the Software Invariant Engine (SPEC v5.0) or a local search and recall layer over Vault (design page decision 4)?

**Decision:** Option 1. Move SPEC v5.0 to `docs/archive/SPEC-v5.0.md` unchanged and make the Local-Graph [`docs/SPEC.md`](SPEC.md) the only active contract. The user chose this option and approved the spec on 2026-10-30.

**Reason:** The code and README already describe a search layer. None of VS-1 to VS-6 was implemented, and v5.0 goal 4 ("remove the contact point between documents and code") conflicts with value 3 (code and decision records queried together).

**Implications:** [Spec 2026-10-29-local-graph-memory-layer](specs/2026-10-29-local-graph-memory-layer/spec.md) defines the first pass, later passes, and Vault-side dependencies. The context pack JSON contract and the five independent module contracts move into the new SPEC unchanged. Older documents that link `docs/SPEC.md` sections are not edited; readers use the archived copies.

## 2026-10-30 - Adopt Automatic Memory Confirmation As A Vault-Owned Policy

**Question:** How should automatically extracted memory become confirmed knowledge (design page decision 6)?

**Decision:** Adopt the recommendation. Episodes and facts the user stated directly (stated) are confirmed when they pass validation. Facts an LLM inferred (inferred) go through the review queue. This is a policy that Vault owns and executes through its cleanup skill (dependency 4), not a Vault Graph feature. The user chose this in spec question 8.

**Reason:** Confirming everything automatically is fast but accumulates wrong facts. The review queue keeps inferred facts out of recall until a person approves them.

**Implications:** Vault Graph does not index `scratch/review/`, and the first-pass `remember` handles stated content only. vault-builder request 7 is updated to this decided policy. Implementation stays with Vault tools.

## 2026-10-30 - Vault Graph Does Not Call An LLM

**Question:** Should Vault Graph call an LLM to compose answers, summaries, or extracted facts (design page decision 7)?

**Decision:** No. Vault Graph returns evidence and sources only, and the calling agent does the reasoning. The user confirmed this in spec question 7.

**Reason:** The Local principle means no hosted service, API key, or cost, and results stay reproducible.

**Implications:** `remember` builds its draft only from the fields the agent passes. No LLM client import or dependency is added to `src` or `pyproject.toml`. The "LLM-Backed Answer Composer" TODO candidate stays deferred.

## 2026-10-30 - Write To Vault Only Through Remember And Publish-Draft

**Question:** Should Vault Graph offer a write path to Vault, and if so how (design page decision 8)?

**Decision:** Add an MCP tool `remember` that runs the Vault tool's publish-draft. Vault Graph never creates, edits, renames, or deletes Vault files directly and never writes to `raw/`. The boundary rule changes from "read-only" to "the only Vault write is `remember` running publish-draft". The user adopted this and also redefined VG-MOD INV-01, INV-02, and INV-04 (spec questions 3, 4, 9).

**Reason:** Agents need to know one MCP server, and every write passes the same validation as the llm-wiki MCP. One reviewer recommended removing `remember`; the user did not accept that.

**Implications:** `AGENTS.md`, `docs/TODO.md`, `docs/ARCHITECTURE.md` §4, and VG-MOD INV-01/02/04 state the same rule. The draft is built in a temporary directory outside Vault and Graph Home and deleted afterwards. The target Vault is chosen only from an explicit argument or a single linked Vault. A failed publish-draft is reported, not retried or redirected. Other MCP tools, query, index, and watch never run publish-draft.

## 2026-10-30 - Read Project And Vault Links Only From vault-map.json

**Question:** Where should the link between a project and its Vaults be owned (design page decision 9)?

**Decision:** `vault-map.json`, which vault-builder installs in the user scope and edits through install, link, and unlink, is the single source. Vault Graph only reads it. The user adopted this.

**Reason:** Vault Graph's own `project-bindings.json` and Vault registration duplicate the same information.

**Implications:** The first pass reads `vault-map.json` version 2 and falls back to `project-bindings.json` only when the project is missing. Removing `project-bindings.json` and own registration is later pass n차-7. Project lookup follows the llm-wiki router rule, which the router owns.

## 2026-10-30 - Prefer Vault Graph Recall At Session Start With recall.sh Fallback

**Question:** How should Vault Graph recall relate to vault-builder's `recall.sh` (design page decision 10)?

**Decision:** The SessionStart hook uses Vault Graph recall when Vault Graph is installed and `recall.sh` otherwise. Vault Graph adds `vg hook session-start`. Exit code 0 means handled (output may be empty) and 3 means recall is not possible. The user adopted this.

**Reason:** Session start is where an agent first notices memory, and Vault must keep working without Vault Graph.

**Implications:** The hook branch itself is dependency 1, owned by vault-builder and not implemented yet. Recall does not run keyword or vector search, and appends usage records only under Graph Home `usage/`.

## 2026-10-30 - Allow Session Files In raw/sessions As A Vault-Owned Rule Exception

**Question:** May a session collector add files under Vault `raw/` despite Vault `AGENTS.md` rule 1 (design page decision 11)?

**Decision:** Yes, as an exception owned by Vault and vault-builder: the collector may only add new files under `raw/sessions/`. Editing or deleting existing files stays forbidden. The user adopted this. Vault Graph has no work for this decision.

**Reason:** The collector cannot go through publish-draft because publish-draft cannot write outside `wiki/`.

**Implications:** The rule change is sent to vault-builder as request 1 and tracked as dependency 3 (not implemented). This exception does not apply to Vault Graph, which never writes to `raw/`.

## 2026-11-02 - Redefine Vault Graph As A Long-Term Memory Tool Over Multiple Vaults

**Question:** Is Vault Graph still a read-only search layer, and how should it handle several Vaults of different types?

**Decision:** Vault Graph is a long-term memory tool for Claude Code built on Vault. `docs/SPEC.md` §0 records the intent. Vault is the only memory store. Vault Graph may add, update, and retire memory pages, always through Vault's own tools. Session transcripts are saved by Vault's `sessions capture`, and Vault Graph may decide when to run it. Vault Graph keeps only rebuildable data, and usage data moves into Vault once it affects ranking or cleanup. For multiple Vaults the user adopted the recommended defaults, modeled on OpenWiki workspaces:
- Decision 12: write to the explicit `vault`, else the project's default write Vault, else return `vault_required`. There is no routing by memory kind.
- Decision 13: search all linked Vaults into one ranked list, tagging each result with its Vault name and type.
- Decision 14: session-start recall puts pinned memories first, then fills the budget from one ranked list with no per-Vault share.
- Decision 15: a Vault type is a label in `vault-map.json`, and code never branches on a type name.

**Reason:** Claude Code's built-in memory is flat files loaded in full, and its transcripts expire after 30 days. Memory naturally splits into personal, project, and team Vaults. Guessing a write target can leak a private memory into a shared Vault.

**Implications:** This replaces "read-only" wording. Principles 4 and 5 in `docs/SPEC.md` now allow writes through Vault tools and capture orchestration, but never direct file writes. Not implemented yet:
- update and retire (dependencies 4 and 5)
- the team type and the default write Vault field in `vault-map.json` (request 5 extension)
- capture orchestration (dependency 1)

## 2026-11-02 - Leave Retired Pages Out Of Default Search As An INV-05 Exception

**Current note:** `2026-11-06 - Find Retired Memories With include_retired And Restore Them` added the option to include retired pages. Default search is unchanged.

**Question:** Should default search still return pages whose frontmatter status is `retired` (spec `docs/specs/2026-11-02-vault-long-term-memory/spec.md` decision S14, question 3)?

**Decision:** No. Default search drops results from pages with status `retired`. Pages with status `deprecated` stay in results as before. This is an accepted exception to VG-MOD INV-05, which otherwise keeps search scores and order unchanged.

**Reason:** A retired page has no replacement and its content is no longer true. If search returns it, the agent cannot tell that the content is withdrawn. A `deprecated` page points to its replacement through `superseded_by`, so it still helps.

**Implications:** The filter runs in the search step (M05) through the metadata store's document frontmatter, before ranking and before `limit` is applied, so a retired page does not take a result slot. Scores and order of the remaining results do not change. There is no option yet to include retired pages in search.

## 2026-11-03 - Run Only Lint, Type Check And Tests In Pull Request CI

**Question:** Pull request CI ran eight jobs: two rustworkx runtime checks, five per-module jobs (lint, mypy, tests, build, twine), and a `verify` job that also built and checked the release wheels. Is that needed on every pull request?

**Decision:** No. `ci.yml` keeps one `verify` job with `ruff`, `mypy` and `pytest` over `tests` and `packages/*/tests`. The user decided this. It replaces decision 3 of `docs/specs/2026-10-28-single-package-release/spec.md`, which kept the per-module jobs.

**Reason:** The `verify` job already runs every module's tests. The wheel, build and release distribution checks run again in `publish-pypi.yml` and `publish-testpypi.yml` before upload.

**Implications:** A module that starts importing a `vault-graph` dependency, or a break on the minimum rustworkx version, now shows up only in the release workflows, not on the pull request.

## 2026-11-04 - Default To Arctic-L And Let Users Pick An Embedding Preset

**Current note:** The default model was replaced by `2026-11-04 - Default To E5-Small After Measuring Arctic-L`. `2026-11-04 - Keep One Embedding Model` then removed the `arctic-l` and `minilm` presets. The preset list, settings file and commands below still apply.

**Question:** The embedding model was one hard-coded constant (multilingual MiniLM, 128 tokens per chunk). Users search Korean-heavy coding agent session transcripts and could not change the model. Which model should be the default, and how should users switch (spec `docs/specs/2026-11-04-embedding-model-selection/spec.md`)?

**Decision:** The user chose `arctic-l` (`Snowflake/snowflake-arctic-embed-l-v2.0`, int8 ONNX, 1024 dimensions, up to 8192 tokens) as the default and recommended model. Models are named presets in `EMBEDDING_PRESETS` (`interface/composition/adapters/text_embeddings.py`), each pinned to a fixed revision. The first list has `arctic-l` (recommended), `e5-small` (smaller and faster alternative) and `minilm` (the previous default, kept for rollback). `vg embedding use NAME` downloads the model into the model folder (default `~/llm/models`) and then writes `<graph-home>/configs/embedding.json`. `vg embedding list` shows the presets, the selection and the folder. A Graph Home without that file uses `arctic-l`. This replaces the default in `2026-06-08 - Use FastEmbed Multilingual MiniLM As Default Local Embeddings`.

**Reason:** On a public Korean retrieval table `arctic-l` scores 0.724 against MiniLM's 0.410, it is Apache-2.0, and it downloads about 570 MB. The user accepted the cost: the first full re-index can take up to about 48 minutes and the vector store grows about 2.7 times. These figures are estimates and are not yet measured on the user's Vaults.

**Implications:**

- Switching models only changes the spec. Existing vectors become stale, and the next `vg index` or session-start background index re-embeds them. Until then, search in each Vault returns keyword results only.
- A successful index removes empty `vault_graph_` vector collections of other specs from the new generation before publishing it. Read paths never remove collections.
- A broken settings file or an unknown preset name stops commands that use the model. Vault Graph still never falls back to another model silently.
- The `minilm` preset keeps the old spec, so a Graph Home that selects it before re-embedding with another model reuses its existing MiniLM vectors.
- Measurement 1 (`docs/SPEC.md` n-4) still has to compare the models on the user's own data.

## 2026-11-04 - Default To E5-Small After Measuring Arctic-L

**Current note:** `2026-11-04 - Keep One Embedding Model` removed `arctic-l` and `minilm` from the list.

**Question:** The previous decision made `arctic-l` the default on estimated costs. A measured full re-index on the user's six Vaults (26,209 chunks, a computer with 36 GB of memory) did not finish in 1 hour 55 minutes and used about 40 GB of memory, which made the computer swap. Should `arctic-l` stay the default (spec `docs/specs/2026-11-04-embedding-model-selection/spec.md`, 결정13)?

**Decision:** The user chose `e5-small` (`Xenova/multilingual-e5-small`, int8 ONNX, 384 dimensions, up to 512 tokens) as the default and recommended model. `arctic-l` stays as an alternative. A Graph Home without `configs/embedding.json` uses `e5-small`. This replaces the default model in `2026-11-04 - Default To Arctic-L And Let Users Pick An Embedding Preset`. The preset list, the settings file and the commands from that decision stay.

**Reason:** A Graph Home without a settings file starts a background full re-index at the first session after an upgrade. With `arctic-l` that run takes hours and uses more memory than the computer has. `e5-small` supports Korean, reads 512 tokens per chunk against MiniLM's 128, and downloads about 135 MB. The earlier estimate of about 48 minutes was wrong. The storage growth of about 2.7 times was not measured.

**Implications:**

- `README.md` lists `arctic-l` as an alternative with its measured cost.
- Measurement 1 (`docs/SPEC.md` n-4) still has to compare the models on the user's own data.

## 2026-11-04 - Keep One Embedding Model

**Question:** After `e5-small` became the default, the list still had `arctic-l` and `minilm`. Should users keep choosing among three models (spec `docs/specs/2026-11-04-embedding-model-selection/spec.md`, 결정14)?

**Decision:** The user chose to keep one model, `e5-small`. The `arctic-l` and `minilm` presets are removed. `EMBEDDING_PRESETS`, `configs/embedding.json`, `vg embedding list` and `vg embedding use` stay, so adding a model later is one new entry in `EMBEDDING_PRESETS`.

**Reason:** On the public Korean table `arctic-l` scores only 0.05 above `e5-small`, and it could not finish a full re-index on the user's computer. The user wants one model now and more models only when needed.

**Implications:**

- A Graph Home that still has MiniLM vectors cannot keep them by selecting `minilm`. The next index re-embeds them with `e5-small`.
- `vg embedding use e5-small --models-dir PATH` is how a user moves the model folder.
- Measurement 1 (`docs/SPEC.md` n-4) still has to check `e5-small` on the user's own data.

## 2026-11-05 - Release With Git Tags And GitHub Releases Only

**Question:** Every install path uses git: the vault-builder install command and the README both install `git+https://github.com/cutehackers/vault-graph.git`. Release still went through a draft GitHub Release, `pypi` environment approval and a PyPI upload, so v0.3.0 had no tag or Release. Is PyPI still needed (spec `docs/specs/2026-11-05-git-tag-release/spec.md`)?

**Decision:** No. The user approved removing PyPI and TestPyPI publishing. The manual `release` workflow (`.github/workflows/release.yml`) runs the version, tag, lint, type, test and wheel checks, then creates the tag `vX.Y.Z` and a published GitHub Release with no attached files. It fails without creating anything when a check fails or the target commit is not on `origin/main`.

**Reason:** No supported install path reads PyPI. The last PyPI release, 0.2.1, lacks commands the install command uses, such as `vg mcp unregister`. The PyPI upload and its approval step only delayed releases.

**Implications:**

- This replaces `2026-06-29 - Use Trusted Publishing With Release Approval` in full.
- It replaces the PyPI implications of `2026-06-24 - Use Setup And MCP Registration As Onboarding Target`. README now installs from git and tells users not to use the PyPI package.
- It replaces the PyPI upload part of `2026-10-28 - Publish Only Vault Graph And Defer Module Distributions`. Bundling the five modules in the `vault-graph` wheel stays.
- It replaces the reason in `2026-11-03 - Run Only Lint, Type Check And Tests In Pull Request CI` that wheel checks run again in `publish-pypi.yml` and `publish-testpypi.yml`. They now run in `release.yml`. The user kept `ci.yml` unchanged, so wheel problems on `main` still show up only at release time.
- `2026-06-29 - Use MIT License For Public Distribution` still stands.
- Making vault-builder install a release tag instead of `main` is a later, separate change.
- A person decides what to do with the PyPI project and deletes the `pypi` and `testpypi` environments and the Trusted Publishers.

## 2026-11-05 - Vault Graph Installs vault-builder, Not The Other Way Around

**Question:** The vault-builder install command installed `vg` from `main`, registered the `vault-graph` MCP server and ran the first index. vault-builder works without Vault Graph, and Vault Graph needs vault-builder. Which side owns the Vault Graph install?

**Decision:** Vault Graph. The user decided that vault-builder has no Vault Graph dependency and that Vault Graph owns installing and setting up both. `scripts/install.sh` installs the newest release tag of `vg`, runs the vault-builder install command with `VAULT_GRAPH_BIN` set to that `vg` (so the vault-builder hooks run it), then runs `vg setup --agent claude --mcp`. `--uninstall` removes the `vault-graph` MCP entry and `vg` and keeps vault-builder.

**Reason:** The dependency runs one way. An install that starts from vault-builder had to know Vault Graph's repository, ref, Python version and setup command, and every Vault Graph release could break a vault-builder install. Installing a release tag instead of `main` also keeps unchecked commits away from new installs.

**Implications:**

- This resolves "Making vault-builder install a release tag instead of `main` is a later, separate change" in `2026-11-05 - Release With Git Tags And GitHub Releases Only`: vault-builder installs no Vault Graph at all.
- The README install command is the Vault Graph one. vault-builder alone is installed with its own command.
- `vg setup` hook warnings name `VAULT_GRAPH_BIN=<this vg> vault-builder setup` as the fix, because `vault-builder setup` no longer installs `vg`.
- vault-builder must ship its change (no `vg` install, `--without-vault-graph` removed) before this install command is used. Otherwise vault-builder setup installs `vg` from `main` a second time.

## 2026-11-06 - Export Agent Sessions Through Per-Agent Adapters To A Common Format

**Question:** Claude Code deletes session transcripts after 30 days, and Vault session files are markdown written from them. Should Vault Graph keep the transcripts, and in what format (spec `docs/specs/2026-11-05-session-memory-indexing/spec.md`, §9.1 questions 1 and 2)?

**Decision:** The user decided that `vg session export` writes the source copy and a normalized file to a user-chosen path outside every Vault, and that one adapter per agent converts to a common format. The Claude Code adapter is implemented; the Codex adapter has a contract only (backlog B-1). With the final spec approval the user also accepted decisions 7, 8, 9 and 18: the common format has two layers, the machine format `vg-session-jsonl/1` outside the Vault and the `vault-session/v2` markdown that the Vault tool renders from it (`sessions capture --normalized`, request S10). Human turns, tool targets and success come from source record fields, not text heuristics. The adapter code is the new feature area M19 `operation/sessions/`, which imports only M01.

**Reason:** JSONL loses the least and parses easily, while the markdown keeps the current reader, FTS and line locators. The Vault tool keeps owning the markdown format, so sessions captured without Vault Graph look the same. Vault Graph still never writes Vault files.

**Implications:** `vg hook capture` now decides which normalized file it passes as well as when it runs (boundary sentence 5). With Graph Home `configs/session-export.json` every capture also exports. The format is fixed in `docs/contracts/vg-session-jsonl-v1.md`. `docs/SPEC.md` §9.2 B-1 holds the Codex work.

## 2026-11-06 - Chunk Session Files By Exchange

**Question:** Session files were cut by the general block chunker, so tool-only turns filled results and one exchange spread over many chunks. How should session files be chunked and returned (spec `docs/specs/2026-11-05-session-memory-indexing/spec.md`, §5.2, §9.3 question 11)?

**Decision:** Accepted with the final spec approval (decisions 10 to 17, 41 and 42). Session files are cut into non-overlapping windows of at most 160 whitespace tokens inside one exchange (`session-exchange-v2`, and `session-exchange-v1` for old files). A v2 chunk id comes from session id, exchange id, agent scope and window number, not the file path. Exchange meta (files, commands, tools, errors, outcome) goes only to the keyword row's `frontmatter` column. Search finds windows and returns one result per exchange with the whole exchange line range. The chunker owns its embedding input. Subagent exchanges are chunked separately with the same score. The user decided that when v1 and v2 files of one session overlap, Vault Graph leaves the overlapping v1 exchanges out of the index only and does not touch Vault files (question 11). Part numbers and cursors stay with the Vault tool, and incremental runs re-plan every file of one session group and provenance family.

**Reason:** A question and its answer land in one result, keyword hits on tool names disappear, and chunk ids survive renderer and model changes. Re-planning whole groups keeps incremental results equal to a full run.

**Implications:** Session evidence ids changed once, so session citations in answers made before the switch do not reopen. Session recall is measured per exchange (`tests/benchmarks/measure_session_recall.py`); measurement 1 is only a regression check. Implementation changes to the spec text are in `docs/PATCH_LOG.md` `2026-11-06 - Align Session Memory Implementation With Spec Text`.

## 2026-11-06 - Fix The Five Indexing Slowdowns At Their Causes

**Question:** Indexing re-embedded whole documents, repeated failed background runs and used up to 21 GB of memory. Should Vault Graph speed it up, and should the embedding model change (spec `docs/specs/2026-11-05-session-memory-indexing/spec.md`, §5.1, §5.3, §9.1 question 5)?

**Decision:** The user decided to fix all five causes at their source, to fix the background failure first, and to keep `e5-small` (model choice is outside this spec). With the final spec approval the user accepted decisions 19 to 23: compare the embedding key and the metadata fingerprint separately and update metadata only when only it changed; keep the vector list table inside the generation and the embedding cache outside it; hold back vector retries for the same error for 1, 2, 4 up to 24 hours without blocking metadata and graph; cut embedding batches by a token budget (default 16,384); update the graph per changed document as the last code step.

**Reason:** Vector values do not depend on revision or role metadata. A generation must roll back with its table, but computed vectors should survive a rebuilt generation. An error that does not clear by itself must not rewrite a generation at every session start.

**Implications:** Graph Home gains `cache/embeddings.sqlite3` and `logs/vector-index-failures.json` (`docs/SPEC.md` §4). The ONNX memory arena stays on by default because turning it off was 23% slower (`docs/design/reports/2026-11-embedding-memory.md`). After the session chunkers landed, a full re-index of every Vault peaked at 6.85 GB with the assumed 16,384 budget, so the measured default became 8,192 (4.29 GB at the same speed); see `docs/PATCH_LOG.md` `2026-11-06 - Lower The Default Embedding Token Budget To 8,192`.

## 2026-11-06 - Move L1, L2 And L3 Memory Management To Vault Graph

**Question:** Memory cleanup was split between Claude Code auto-memory (L1), Vault pages (L2), vault-builder skills and Vault Graph recall. Who should manage memory (spec `docs/specs/2026-11-05-session-memory-indexing/spec.md`, §5.4, §9.1 questions 3 and 6)?

**Decision:** The user decided to move L1, L2 and L3 management to Vault Graph and to keep Vault as the store (ingest, update, query and validation), with no split of duties. Vault Graph reads the L1 folder. With the final spec approval the user accepted decisions 27 to 29, 31, 34 and 35: Vault Graph builds the cleanup bundle deterministically, the agent in the session decides what to add, update, retire or skip, and the Vault tool validates and stores. `basis: stated` only when the evidence quotes the user's own words, and at most 10 `inferred` proposals per cleanup. Retirement is only suggested, never automatic. The user starts a cleanup (`curate_memory`); hooks never clean up. The vault-builder judgment pieces (`memory-cleanup`, the `maps build` project summary, `recall.sh`, `/project-memory`) are frozen and removed in the last step after a person confirms.

**Reason:** Vault Graph calls no LLM and never writes `raw/`, so the judgment stays with the strongest available judge, the agent, while the rules no longer live in vault-builder.

**Implications:** New MCP tools `list_memory_candidates`, `mark_candidates_reviewed`, `import_auto_memory`, `supersede_claim` and `restore_memory` bring the count to 19 (`docs/SPEC.md` §5). A session-start line shows the cleanup backlog. Targets such as the 10-proposal cap and the 180-day age limit for session candidates are checked again in each measurement.

## 2026-11-06 - Scope Recall By Project Links And A Per-Vault Sharable Flag

**Question:** Pages without a `project` field reached the recall of every project linked to their Vault. How should recall decide which pages belong to a project (spec `docs/specs/2026-11-05-session-memory-indexing/spec.md`, §9.1 question 4, §9.3 question 15, review 1)?

**Decision:** The user decided on a per-Vault setting and named it `sharable` (`vault-map.json` `vaults.<name>.sharable`). True puts the Vault's pages without `project` in the session-start memory of every linked project; false leaves them out. A missing field counts as false, and `vg status` and session start show one setup line. Search ignores the setting. With the final spec approval the user accepted decision 40: a page without `project` in a Vault linked to only one project belongs to that project; `sharable` applies only to Vaults linked to two or more projects.

**Reason:** The link data already sits in `vault-map.json`, so no Vault write is needed. Without the one-project rule, project Vaults whose pages lack `project` would recall nothing.

**Implications:** One rule function `page_in_project` serves recall, L3 lists and the cleanup bundle (`docs/SPEC.md` §6-4). `remember` now writes `project` from `cwd`. vault-builder owns the field and its set command (request S4).

## 2026-11-06 - Use Usage And Skip Records Only For Cleanup Suggestions

**Question:** Should recall ranking use when a memory was last opened, and may Graph Home records influence cleanup (spec `docs/specs/2026-11-05-session-memory-indexing/spec.md`, §9.3 question 14)?

**Decision:** The user decided that recall ranking does not use usage records. Usage records and cleanup skip records stay in Graph Home and are used only to pick, order and show cleanup candidates. Whether to write a memory stays with the agent and Vault validation. `docs/SPEC.md` §0 rule 5 records this exception. With the final spec approval the user accepted decision 44: a write tool that receives `candidate_key` records the candidate when the result is `published` or `proposed`, session evidence counts per exchange location, and session candidates older than 180 days are not suggested.

**Reason:** Deleting Graph Home must not change recall. In cleanup it only means seeing an already skipped candidate once more.

**Implications:** Records go to Graph Home `memory/reviewed.jsonl`. A proposal waiting for review does not come back in the next cleanup.

## 2026-11-06 - Keep L3 Lists Computed And The Brief As A Vault Page

**Question:** Where should the project-level summary (L3) live: computed by Vault Graph, or written to the Vault (spec `docs/specs/2026-11-05-session-memory-indexing/spec.md`, §9.3 questions 10 and 13)?

**Decision:** The user left question 10 to the spec, and approved the result. L3 is mixed: the lists of open work, current decisions and corrections or rules are computed from the index at recall and query time and never stored. The brief is one Vault page per project at `wiki/projects/<project>.md` with the new type `project` (user, question 13), written by the agent through `remember(kind="project")` and then `update_memory`. Vault Graph decides when it is stale: 5 or more decisions after the brief. With the final spec approval the user accepted decisions 30 and 33: superseded claim rows are left out of recall and L3 lists, and the 1,500-token recall splits into 400 pinned, 500 L3, 180 notices and the rest for other memories.

**Reason:** Lists can be computed again, and the approved boundary forbids writing machine-made content to a Vault. Only judged knowledge goes to the Vault.

**Implications:** `remember` accepts `kind` `project` (`docs/SPEC.md` §5). The Vault schema change is vault-builder request S9.

## 2026-11-06 - Change The Boundary Sentences For Memory Management

**Question:** Memory management needs Vault Graph to copy auto-memory notes into a Vault, run read-only Vault commands while indexing and choose the normalized session file. The boundary sentences did not allow that (spec `docs/specs/2026-11-05-session-memory-indexing/spec.md`, §4.4.8, §9.3 question 9, §9.4 question 17).

**Decision:** The user approved the seven sentences (question 9) and the three matching sentences in `docs/SPEC.md` §0 rules 2 and 3 and principle 5 (question 17): write path 4 `import-source`, read-only Vault commands during indexing, reading the L1 folder, no machine-made content in a Vault, the capture path choosing the normalized file, the principle 1 addition that the agent decides what to remember, and "Vault works without Vault Graph as a store".

**Reason:** Within one document, boundary rules that disagree make the next implementer follow the narrower one.

**Implications:** The sentences are in `AGENTS.md` Project Boundary and `docs/SPEC.md` (commit `4fc6280`). `docs/ARCHITECTURE.md` §4 lists the four write paths.

## 2026-11-06 - Find Retired Memories With include_retired And Restore Them

**Question:** Retirement only changes frontmatter, but default search always hid retired pages and nothing could undo a retirement. An agent could then save the same fact again. How should retired memories be found and restored (spec `docs/specs/2026-11-05-session-memory-indexing/spec.md`, §4.4.13, review 6, question 16)?

**Decision:** The user confirmed the recommended answer to question 16 with the final spec approval (decision 45). `search_vault` and `vg search` take the optional `include_retired` (default false), and results then carry `status`, `retired_reason`, `retired_at` and `superseded_by`. The cleanup comparison material includes retired pages. The new write tool `restore_memory` sets `status: active` through the existing Vault `patch-page` and keeps the retirement fields as history. With the same approval the user accepted decision 43: the new write tool `supersede_claim` replaces one claim row through the existing `patch-page` `supersede-claim` edit.

**Reason:** A retirement that cannot be undone or seen leads to duplicates. Both tools reuse validated Vault formats, so no new Vault feature is needed.

**Implications:** Default search still leaves out only `retired` pages, as in `2026-11-02 - Leave Retired Pages Out Of Default Search As An INV-05 Exception`. Recall and L3 lists never use the option.
