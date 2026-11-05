# Vault Graph

Status: Pre-release development

Vault Graph is a long-term memory tool for Claude Code built on Vault. Memory
lives only in Vault. Vault Graph keeps rebuildable derived data (indexes and
usage logs), not a source of knowledge.

It searches every Vault linked to the current project in one ranked list and
labels each result with its Vault name and role. At session start it injects a
short recall within a token budget, pinned memories first. Humans and agents
can also trace decisions, inspect project memory, and build task-specific
context packs.

Vault Graph never creates, edits, or deletes Vault files itself and never writes
to `raw/`. Three MCP tools write memory, always through Vault's own tools:
`remember` adds a page, `update_memory` replaces a page body, and
`retire_memory` retires a page. Each requires `basis`. A `stated` fact runs
Vault's `publish-draft` and is published once it passes Vault validation. An
`inferred` fact runs Vault's `review propose` and returns `proposed` with a
`review_path`. It reaches recall and search only after a person accepts it
with Vault's `review resolve`. Session transcripts are written by Vault's
`sessions capture`. `vg hook capture` only decides when it runs.

## Install

Claude Code users start with the vault-builder install command. It installs
`vg`, creates or registers your Vaults, installs the Vault hooks, links the
current repository, registers the `vault-graph` MCP server in Claude Code, and
runs the first index:

```bash
curl -fsSL https://raw.githubusercontent.com/cutehackers/vault-builder/main/scripts/install.sh | bash
```

Quit Claude Code before you run it. The command stops before it writes
`~/.claude.json` while Claude Code is running. The first index downloads the
embedding model (about 135 MB) and embeds every Vault, so the command can run
for several minutes. On six Vaults with 26,209 chunks it took about 14 minutes
and up to about 21 GB of memory. Start Claude Code again when the command
finishes and check the servers with `/mcp`. The command installs both
vault-builder and Vault Graph by default. Add `--without-vault-graph` (`| bash
-s -- --without-vault-graph`) to install vault-builder only. See the
vault-builder README for its other options.

The install command installs the `main` branch of Vault Graph from this public
GitHub repository over HTTPS. No SSH key is needed. To install a specific
release, add its tag to the repository address as `@vX.Y.Z`. Do not install the
`vault-graph` package from PyPI. It is no longer updated and lacks commands the
install command uses, such as `vg mcp unregister`.

### Install `vg` only

Prerequisites:

- Python 3.12+
- [`uv`](https://docs.astral.sh/uv/)

```bash
uv tool install --python 3.12 git+https://github.com/cutehackers/vault-graph.git
vg --help
```

To install a release tag instead of `main`, use
`uv tool install --python 3.12 git+https://github.com/cutehackers/vault-graph.git@vX.Y.Z`.

Then continue with Quick Start below.

## Quick Start

The vault-builder install command already runs this step for you. Run it
yourself only when you installed `vg` alone. For Claude Code, use
`--agent claude`:

```bash
vg setup --vault /path/to/vault --agent claude --mcp --dry-run
vg setup --vault /path/to/vault --agent claude --mcp
```

By default, setup uses `~/.vault-graph` for local Data Home, registers the Vault,
and runs indexing. Keep this Data Home directory outside your Vault.

With `--agent claude`, setup adds a user-scope `mcpServers.vault-graph` entry to
`~/.claude.json`. The entry starts the absolute path of your `vg` command with
`serve --mcp`, and adds `--graph-home` only when you use a Data Home other than
`~/.vault-graph`. Other keys and MCP servers in the file are kept, the old file
is backed up next to it as `~/.claude.json.bak`, and setup refuses to write when
the file is not valid JSON. Use `--mcp-config-path` to choose another file,
`--dry-run` to see the target without writing, or `--print-mcp-config` to print
the entry and add it yourself.

For Codex, use `--agent codex`. This is also the default when `--agent` is
omitted:

```bash
vg setup --vault /path/to/vault --agent codex --mcp
```

This registers the `vault-graph` stdio MCP server in the Codex config at
`$CODEX_HOME/config.toml` or `~/.codex/config.toml`. Existing Codex config is
backed up before the `vault-graph` server entry is changed.

If one file in a Vault has frontmatter that strict YAML rejects, indexing reads
it with Vault's own frontmatter rules and prints a warning with the file path.
When setup reads several Vaults from the vault map, a Vault that fails is
reported as one `setup_failed:` line and setup continues with the next Vault.
Setup exits non-zero when any Vault failed.

Vault Graph is currently pre-release. If `~/.vault-graph` contains an older
pre-release layout, setup stops without reading or changing it. Choose a new
Data Home (or move the rebuildable old directory aside) and run setup again;
the projections will be rebuilt from Vault. Vault files are never migrated or
modified.

Then use the indexed Vault:

```bash
vg ask --graph-home ~/.vault-graph "What changed recently?"
vg search --graph-home ~/.vault-graph "GraphRAG"
vg search --graph-home ~/.vault-graph --mode evidence "GraphRAG"
vg projection-audit --graph-home ~/.vault-graph --format json
vg context --graph-home ~/.vault-graph "Implement GraphRAG MVP"
vg status --graph-home ~/.vault-graph
```

To add current source-code evidence to an agent task, register the repository
and bind it explicitly to the Vault that owns durable project knowledge:

```bash
vg code repository add demo --path /path/to/repository --language python --language dart --graph-home ~/.vault-graph
vg code index --repository-id demo --graph-home ~/.vault-graph
vg project bind demo --vault-id default --scope wiki --graph-home ~/.vault-graph
vg code impact calculate_total --repository-id demo --graph-home ~/.vault-graph
```

Repository code remains authoritative for current behavior; Vault remains
authoritative for durable decisions. The code index is a local, rebuildable,
read-only projection and does not write source files or copy source bodies into
Vault.

Vault Graph builds local metadata, keyword, vector, and graph projections. It
uses local storage and local embeddings by default; it does not require hosted
services for normal use. The first indexing run may download the pinned local
embedding model (`e5-small`, about 135 MB) and cache it outside your Vault, in
`~/llm/models` by default. See [Embedding Model](#embedding-model). Restart
your agent after MCP registration so it can load the new server.

## Common Commands

| Goal | Command |
| --- | --- |
| Register a Vault | `vg init --vault /path/to/vault --graph-home ~/.vault-graph` |
| Add another Vault | `vg vault add work --path /path/to/other-vault --graph-home ~/.vault-graph` |
| List Vaults | `vg vault list --graph-home ~/.vault-graph` |
| Index the active Vault | `vg index --graph-home ~/.vault-graph` |
| Index one Vault | `vg index --vault-id work --graph-home ~/.vault-graph` |
| Index all Vaults | `vg index --all-vaults --graph-home ~/.vault-graph` |
| Check health | `vg status --graph-home ~/.vault-graph` |
| Show embedding model | `vg embedding list --graph-home ~/.vault-graph` |
| Change model folder | `vg embedding use e5-small --models-dir /path/to/models --graph-home ~/.vault-graph` |
| Search evidence | `vg search --graph-home ~/.vault-graph "query"` |
| Expand raw/source evidence | `vg search --mode evidence --graph-home ~/.vault-graph "query"` |
| Audit projection duplication | `vg projection-audit --graph-home ~/.vault-graph` |
| Include graph signals | `vg search --include-graph --graph-home ~/.vault-graph "query"` |
| Ask with evidence | `vg ask --graph-home ~/.vault-graph "question"` |
| Build a context pack | `vg context --graph-home ~/.vault-graph "goal"` |
| Find related items | `vg related --graph-home ~/.vault-graph GraphRAG` |
| Trace a decision | `vg decision-trace --graph-home ~/.vault-graph GraphRAG` |
| Register a code repository | `vg code repository add demo --path /path/to/repository --language python --language dart --graph-home ~/.vault-graph` |
| Build/update a code projection | `vg code index --repository-id demo --graph-home ~/.vault-graph` |
| Inspect code impact | `vg code impact SYMBOL --repository-id demo --graph-home ~/.vault-graph` |
| Bind repository to Vault | `vg project bind demo --vault-id default --scope wiki --graph-home ~/.vault-graph` |
| Preview harness guidance | `vg harness guidance preview --target /path/to/repository --file-name AGENTS.md --graph-home ~/.vault-graph` |

Commands that accept `--vault-id` operate on one registered Vault. Commands that
accept `--all-vaults` expand to all enabled registered Vaults. Commands without
either option use the active Vault.

## Embedding Model

Vault Graph embeds every chunk with a local model for semantic search. It uses
one model, `e5-small` (`Xenova/multilingual-e5-small`, int8). The model suits
Korean and English coding agent session transcripts, reads up to 512 tokens per
chunk, and downloads about 135 MB. You do not need to set anything up: the
first `vg setup` or `vg index` downloads it.

Model files live in `~/llm/models`, outside every registered Vault. The model
folder is saved in `configs/embedding.json` under your Data Home
(`~/.vault-graph/configs/embedding.json` by default) once you change it.

```bash
vg embedding list --graph-home ~/.vault-graph
vg embedding use e5-small --models-dir /path/to/models --graph-home ~/.vault-graph
```

`vg embedding list` shows the model, whether it is already downloaded, and the
model folder. It never downloads anything. `vg embedding use e5-small` downloads
the model into the folder if it is not there, then saves the folder. If the
download fails, the saved settings do not change.

Re-indexing cost was measured on six Vaults with 26,209 chunks on a computer
with 36 GB of memory: a full re-index took about 14 minutes, used up to about
21 GB of memory without swapping, and the whole index folder was about 496 MB.

Upgrading from a version that used MiniLM:

1. The next `vg index`, or the background index at the next agent session
   start, re-embeds every chunk with `e5-small`.
2. Search returns keyword results only until re-indexing finishes for that
   Vault, with a `vector_stale` warning. Vaults that finish first get semantic
   search back first.
3. After a successful re-index, `vg index` removes the old model's empty vector
   collections and prints `removed_vector_collections: N`. The previous index
   generation keeps its copy until the next index replaces it, so disk space
   comes back one index later. When you re-index only some Vaults with
   `--vault-id`, the old collection stays until every Vault is re-indexed.
4. A running MCP server does not need a restart. It reads the new model when
   the re-index publishes a new index.

If `configs/embedding.json` names an unknown model or is not valid, commands
that need the model stop with an error. Vault Graph never switches to another
model on its own. To add another model later, add one entry to
`EMBEDDING_PRESETS` in
`src/vault_graph/interface/composition/adapters/text_embeddings.py`.

## Connect An Agent Through MCP

MCP server installation and MCP server registration are different things:

- installation makes the `vg` command available
- registration tells an agent how to start `vg serve --mcp`

For Codex, the easiest supported path is:

```bash
vg setup --vault /path/to/vault --agent codex --mcp
```

For explicit control, render or register the stdio server manually:

```json
{
  "mcpServers": {
    "vault-graph": {
      "command": "vg",
      "args": [
        "serve",
        "--mcp",
        "--graph-home",
        "/path/to/.vault-graph"
      ]
    }
  }
}
```

The current Codex-style example lives at
[`docs/superpowers/specs/phase-5/codex-local-stdio-config.example.json`](docs/superpowers/specs/phase-5/codex-local-stdio-config.example.json).

Once connected, the agent can use these MCP tools:

- `search_vault`
- `build_context_pack`
- `find_related`
- `get_decision_trace`
- `check_index_status`
- `explain_result`
- `summarize_project_memory`
- `get_open_questions`
- `get_recent_changes`
- `ask_vault`
- `explore_project`

For a coding task, call `explore_project` first with the task and a registered
`repository_id` (or a registered `project_path`). It returns bounded current
code evidence, related tests and impact, selected Vault decisions, revisions,
and freshness warnings in one read-only response. If only one repository has an
explicit Vault binding, the repository scope may be omitted; otherwise MCP
returns a recovery hint instead of guessing.

`explore_project` output is working evidence. Re-read source lines if a warning
reports drift, and publish durable conclusions through Vault's normal workflow.
When MCP is unavailable, use the `vg code search`, `vg code symbol`, `vg code
outline`, `vg code callers`, `vg code callees`, and `vg code impact` commands.

Vault Graph provides evidence-first working context and evidence-first answers
through `ask_vault` and `vg ask`.

For explicit MCP control:

```bash
vg mcp register --agent codex --graph-home ~/.vault-graph --config-path /path/to/agent-config.json
vg mcp register --agent codex --graph-home ~/.vault-graph --config-path ~/.codex/config.toml
vg mcp config --agent codex --graph-home ~/.vault-graph --print
```

## Guarantees

Vault Graph user-facing features preserve these guarantees:

- read-only access to Vault
- local-first operation without mandatory hosted services
- evidence-first retrieval, context packs, and answers
- clear separation between stated facts and inferred links
- warnings for stale, missing, contested, or deprecated material
- reproducible indexes that can be deleted and rebuilt from Vault
- Vault-scoped identity for multiple registered Vault roots
- visible backend health and index freshness status
- durable knowledge publication only through Vault

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

The vault-builder install command reinstalls `vg` from the git URL with
`--force` and replaces an editable install. Pass `--without-vault-graph` to it
to keep your editable `vg`.

## Independent Modules

The workspace includes five reusable packages with separate wheels and public APIs:

- [`nolemy-graph-search`](packages/graph-search/README.md) accepts node and edge IDs and provides bounded graph traversal. It has no Vault, document, database, or model dependency.
- [`nolemy-graph-document`](packages/graph-document/README.md) accepts general document inputs and manages explicit relationships, document contributions, revisions, and evidence in a caller-selected SQLite database. It works without `nolemy-graph-search`.

- [`nolemy-text-embeddings`](packages/text-embeddings/README.md) generates embeddings through a model provider. FastEmbed is an optional extra; the caller supplies a pinned local model or backend.
- [`nolemy-vector-search`](packages/vector-search/README.md) stores and searches already-computed vectors with opaque metadata. Chroma writes are optional; read-only SQLite access does not load its SDK.
- [`nolemy-vector-index`](packages/vector-index/README.md) plans and applies scope-bounded incremental indexing of prepared text. Complete snapshots and partial changes have distinct deletion semantics.

The optional `graph_document.search_bridge` connects a document snapshot to graph traversal and retains the same snapshot for evidence lookup. Vault-specific identity, scope, confidence, ranking, and MetadataStore access remain in the Vault adapters.

For local development and distribution builds:

```bash
uv sync --python 3.12
uv build --all-packages
uv run --python 3.12 python tests/verify_graph_module_wheels.py
```

The last command installs all six wheels outside the workspace and verifies standalone use, the graph bridge, the text-to-vector indexing pipeline, and Vault integration. These packages are local build artifacts until separately published. Vault Graph requires the five module distributions. Vault-specific text preparation, scope, identity, evidence, status, and publication remain in the Vault Graph functional groups. Concrete providers are assembled in `vault_graph.interface.composition`. Previous import paths such as `vault_graph.vault_adapter` were removed. Import from the functional groups instead. See the [vector module contract](docs/design/specs/2026-10-06-vector-modules-ko.md).

To select the document graph backend for an existing Data Home:

```bash
vg index --graph-home /path/to/data-home --graph-backend document
```

The command validates and publishes a new generation. Future reads and index runs use that selection. Existing Data Homes retain the legacy backend until this explicit transition. With multiple enabled Vaults, include `--all-vaults`. Use `--dry-run` to report the intended transition without writing state.

To return to legacy storage, run the same command with `--graph-backend legacy`. Rollback rebuilds the full legacy graph and checks readiness before publication, including source changes made after transition. Reads never repair an incomplete document graph or fall back to a stale legacy cache.

Switching back to the document backend rebuilds its staging cache. For an incompatible document schema, extraction profile, or checkpoint, run `vg index --graph-home /path/to/data-home --full` to rebuild explicitly. With multiple enabled Vaults, recovery requires `--all-vaults`. Recovery publishes only a validated generation and preserves the previous generation if rebuilding fails.

## More Documentation

- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md): current source structure, ownership, composition, and import compatibility
- [`docs/SPEC.md`](docs/SPEC.md): Software Invariant Engine specification and architecture (v5.0)
- [`docs/DECISIONS.md`](docs/DECISIONS.md): accepted architectural and product decisions (ADR)
- [`docs/FEATURES.md`](docs/FEATURES.md): user-facing feature catalog (Phase 1 coexistence)
- [`docs/TODO.md`](docs/TODO.md): active Invariant Engine roadmap and deferred work
- [`docs/PUBLISHING.md`](docs/PUBLISHING.md): release process with git tags and GitHub Releases, and its permissions
- [`docs/archive/`](docs/archive/): archived historical specifications (`SPEC-v1.2.md`, `DESIGN-v1.2.md`)

## License

Vault Graph is distributed under the MIT License. See [`LICENSE`](LICENSE).
