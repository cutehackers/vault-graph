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
- Any manual deletion guidance is limited to Vault Graph state directories, not
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
commands and a separate CLI TODO block.

**Reason:** The SPEC should not imply that `vg watch`, `vg ask`, or
`vg serve --http` are available product features.

**Implications:**

- Future commands must be marked TODO until implemented and covered by
  acceptance tests.
- `vg serve --http` remains a reserved unsupported transport until the future
  HTTP adapter is designed and built.
- Current CLI acceptance is evaluated only against implemented commands.

## 2026-06-23 - Keep Phase 7 As Read-Only Explorer UI

**Question:** Should the current Phase 7 design scope include local HTTP serving
and `Ask Project`, or focus only on optional read-only explorer views?

**Decision:** Keep the current Phase 7 detailed-design scope limited to Timeline
and Health UI, Decision Explorer, and Agent Workspace. Move local HTTP serving,
`Ask Project`, `ask_vault`, and answer synthesis to future phases.

**Reason:** Phase 7 should make existing evidence-linked projections easier to
inspect without introducing a weak search wrapper or premature LLM answer
surface. HTTP serving can be designed separately as an adapter boundary, and
`ask_vault` still needs explicit answer synthesis, LLM adapter, and citation
guarantee design.

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
