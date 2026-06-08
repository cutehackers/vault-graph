# Decisions

This file records accepted product, architecture, and policy decisions for Vault
Graph.

Pending questions should be resolved with the user before implementation. If a
decision is not accepted yet, keep it in the active plan or discussion, not
here.

Implementation-only corrections that directly follow `docs/SPEC.md` and
`docs/DESIGN.md` are recorded in `docs/PATCH_LOG.md` instead.

## 2026-06-05 - Keep Python Package Namespace

**Question:** Should the implementation use `src/vault_graph/...` or put modules
directly under `src/`?

**Decision:** Keep `src/vault_graph/...`.

**Reason:** `src/` is the source root, while `vault_graph` is the product package
namespace. Keeping the namespace avoids generic import names such as
`ingestion`, `storage`, `indexing`, and `cli`, and preserves a clearer package
boundary for testing, installation, and future scale-up.
