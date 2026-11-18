# Developing Vault Graph

## Develop From Source

Clone the repository and run `vg` from the checkout:

```bash
git clone https://github.com/cutehackers/vault-graph.git
cd vault-graph
uv sync
uv run --python 3.12 vg --help
```

To put the checkout's `vg` on your `PATH` as an editable install:

```bash
uv tool install --python 3.12 -e .
vg --help
```

The install command reinstalls `vg` from a release tag with `--force` and
replaces an editable install. To keep your editable `vg`, install vault-builder
with its own install command, then point its hooks at your `vg` and register
the server yourself:

```bash
VAULT_GRAPH_BIN="$(command -v vg)" vault-builder setup
vg setup --agent claude --mcp
```


## Independent Modules

The workspace includes five reusable packages with separate wheels and public APIs:

- [`nolemy-graph-search`](../packages/graph-search/README.md) accepts node and edge IDs and provides bounded graph traversal. It has no Vault, document, database, or model dependency.
- [`nolemy-graph-document`](../packages/graph-document/README.md) accepts general document inputs and manages explicit relationships, document contributions, revisions, and evidence in a caller-selected SQLite database. It works without `nolemy-graph-search`.
- [`nolemy-text-embeddings`](../packages/text-embeddings/README.md) generates embeddings through a model provider. FastEmbed is an optional extra; the caller supplies a pinned local model or backend.
- [`nolemy-vector-search`](../packages/vector-search/README.md) stores and searches already-computed vectors with opaque metadata. Chroma writes are optional; read-only SQLite access does not load its SDK.
- [`nolemy-vector-index`](../packages/vector-index/README.md) plans and applies scope-bounded incremental indexing of prepared text. Complete snapshots and partial changes have distinct deletion semantics.

The optional `graph_document.search_bridge` connects a document snapshot to graph traversal and retains the same snapshot for evidence lookup. Vault-specific identity, scope, confidence, ranking, and MetadataStore access remain in the Vault adapters.

For local development and distribution builds:

```bash
uv sync --python 3.12
uv build --all-packages
uv run --python 3.12 python tests/verify_graph_module_wheels.py
```

The last command installs all six wheels outside the workspace and verifies standalone use, the graph bridge, the text-to-vector indexing pipeline, and Vault integration. These packages are local build artifacts until separately published. Vault Graph requires the five module distributions. Concrete providers are assembled in `vault_graph.interface.composition`. See the [vector module contract](design/specs/2026-10-06-vector-modules-ko.md).

To select the document graph backend for an existing Data Home:

```bash
vg index --graph-home /path/to/data-home --graph-backend document
```

The command validates and publishes a new generation. Future reads and index runs use that selection. Existing Data Homes keep the legacy backend until this explicit transition. With multiple enabled Vaults, include `--all-vaults`. Use `--dry-run` to report the intended transition without writing state.

To return to legacy storage, run the same command with `--graph-backend legacy`. Rollback rebuilds the full legacy graph and checks readiness before publication. Reads never repair an incomplete document graph or fall back to a stale legacy cache.

Switching back to the document backend rebuilds its staging cache. For an incompatible document schema, extraction profile, or checkpoint, run `vg index --graph-home /path/to/data-home --full` to rebuild explicitly. With multiple enabled Vaults, recovery requires `--all-vaults`. Recovery publishes only a validated generation and keeps the previous generation if rebuilding fails.

