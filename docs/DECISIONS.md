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
