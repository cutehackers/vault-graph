# Vault Graph

Status: Pre-release development

Vault Graph (`vg`) is long-term memory for Claude Code, built on Vaults that
vault-builder manages. Memory lives only in the Vaults. Vault Graph keeps
indexes and usage logs that it can delete and rebuild from the Vaults.

It does four things:

1. At session start it injects a short recall of the project's memory.
2. When a session ends or compacts, it hands the session to the Vault so the
   Vault stores the transcript, and it can extract facts from that session.
3. It gives the agent MCP tools to search the Vaults and to write memory
   through the Vault's own tools.
4. It can index registered code repositories so the agent sees current code
   next to the Vault decisions.

Vault Graph never creates, edits, or deletes Vault files itself and never
writes to `raw/`. Every Vault change runs a Vault command (`publish-draft`,
`review propose`, `import-source`, `sessions capture`, `sessions attach-facts`).

## Install

Claude Code users install Vault Graph with one command. Vault Graph needs
vault-builder, so the command installs both. It installs the newest release tag
of `vg`, then runs the vault-builder install command, which creates or registers
your Vaults, installs the Vault hooks (they run this `vg`), links the current
repository and registers the `vault-wiki` MCP server. Last it runs
`vg setup --agent claude --mcp --no-index`, which registers your Vaults and the
`vault-graph` MCP server. It does not index the Vaults:

```bash
curl -fsSL https://raw.githubusercontent.com/cutehackers/vault-graph/main/scripts/install.sh | bash
```

Quit Claude Code and run it in a terminal. The command stops before it changes
anything while Claude Code is running. Before it installs anything, it runs the
vault-builder setup as a dry run, so a problem vault-builder would stop on
stops the command first. Vaults made by an older vault-builder are upgraded in
the same run. Without a terminal for questions, add `--yes`
(`| bash -s -- --yes`). When uv is missing, it asks before it installs uv
(`--install-uv` installs it without asking). Start Claude Code again when
the command finishes and check the servers with `/mcp`.

The command does not index your Vaults. Index every Vault when you have time,
with Claude Code open or closed:

```bash
vg index --all-vaults
```

If you skip this, the first session start indexes the linked Vaults in the
background (see [Session-start recall](#session-start-recall)), and recall
returns nothing for that session.

The last lines of the install command print this command, with the full path
of `vg` when `$HOME/.local/bin` is not on your `PATH`. The first run downloads
the embedding model (`arctic-m`, about 311 MB) and embeds every Vault. Later
runs index only changed files. See [Embedding Model](#embedding-model) for the
measured time and memory.

Options after `bash -s --` go to the vault-builder install command, for example
`--repo /path/to/app --yes` to run without questions or `--dry-run` to install
nothing and show the plan. `--help` lists every option and environment variable.

The command installs the newest release tag `vX.Y.Z` of this repository over
HTTPS. The `release` workflow creates a tag only for a commit that passed every
check, so `main` is never installed by default. Set `VAULT_GRAPH_REF` to install
another tag or a branch, for example `VAULT_GRAPH_REF=main`. No SSH key is
needed. Do not install the `vault-graph` package from PyPI. It is no longer
updated and lacks commands the install command uses, such as
`vg mcp unregister`.

To remove Vault Graph, run the command with `--uninstall` (`| bash -s --
--uninstall`). It removes the `vault-graph` MCP server and `vg`, and keeps
vault-builder, your Vaults and `$HOME/.vault-graph`.

vault-builder installs and works without Vault Graph. To use only
vault-builder, run its own install command (see the vault-builder README).

### Install `vg` only

Prerequisites:

- Python 3.12+
- [`uv`](https://docs.astral.sh/uv/)

```bash
uv tool install --python 3.12 git+https://github.com/cutehackers/vault-graph.git@vX.Y.Z
vg --help
```

Replace `vX.Y.Z` with a release tag. Without `@vX.Y.Z` uv installs `main`.

Then continue with Quick Start below.

## Quick Start

The install command already runs this step for you, with `--no-index`. Run it
yourself only when you installed `vg` alone. Without `--vault`, setup reads
every Vault in `vault-map.json`. For Claude Code, use `--agent claude`:

```bash
vg setup --agent claude --mcp --dry-run
vg setup --agent claude --mcp
```

Setup uses `$HOME/.vault-graph` as the Data Home, registers each Vault, and
indexes it. `--no-index` skips indexing. Keep the Data Home outside your
Vaults. `--vault /path/to/vault` sets up one Vault instead of the whole map.

With `--agent claude`, setup adds a user-scope `mcpServers.vault-graph` entry to
`$HOME/.claude.json`. The entry starts the absolute path of your `vg` command
with `serve --mcp`, and adds `--graph-home` only when you use a Data Home other
than `$HOME/.vault-graph`. Other keys and MCP servers in the file are kept, the
old file is backed up next to it as `.claude.json.bak`, and setup refuses to
write when the file is not valid JSON. Use `--mcp-config-path` to choose another
file, `--dry-run` to see the target without writing, or `--print-mcp-config` to
print the entry and add it yourself.

For Codex, use `--agent codex`. This is the default when `--agent` is omitted.
It registers the `vault-graph` stdio MCP server in `$CODEX_HOME/config.toml` or
`$HOME/.codex/config.toml`, and backs up the old config first:

```bash
vg setup --vault /path/to/vault --agent codex --mcp
```

If one file in a Vault has frontmatter that strict YAML rejects, indexing reads
it with Vault's own frontmatter rules and prints a warning with the file path.
When setup reads several Vaults from the vault map, a Vault that fails is
reported as one `setup_failed:` line and setup continues with the next Vault.
Setup exits non-zero when any Vault failed.

If `$HOME/.vault-graph` contains an older pre-release layout, setup stops
without reading or changing it. Choose a new Data Home (or move the old
directory aside) and run setup again. The indexes are rebuilt from the Vaults.

The first indexing run may download the pinned local embedding model (see
[Embedding Model](#embedding-model)). Then use the indexed Vaults:

```bash
vg ask --graph-home ~/.vault-graph "What changed recently?"
vg search --graph-home ~/.vault-graph "GraphRAG"
vg context --graph-home ~/.vault-graph "Implement GraphRAG MVP"
vg status --graph-home ~/.vault-graph
```

Restart your agent after MCP registration so it loads the new server. Run
`vg doctor` to find index, model and MCP problems. It prints one fix command
for each and changes nothing.

## How Vault Graph Finds Your Vaults

vault-builder owns `vault-map.json`. Vault Graph reads it and never writes it.
The path is `$VAULT_GRAPH_VAULT_MAP` when set, else
`$CLAUDE_CONFIG_DIR/vault-builder/vault-map.json` when `CLAUDE_CONFIG_DIR` is
set, else `$HOME/.claude/vault-builder/vault-map.json`.

The file lists:

1. Each Vault with its folder and `role`, for example `personal` or `project`.
   Search results carry the Vault name and role.
2. Each project with the Vaults linked to it and an optional
   `default_write_vault`.
3. An optional `sharable` flag per Vault. A Vault linked to two or more projects
   without `sharable` is treated as not sharable, and session start prints a
   notice.

To find the project of a folder, Vault Graph compares, in order, the main
worktree root, the normalized `origin` remote, and the folder name. The first
step with exactly one match decides. Read tools, recall, and `vg ask`,
`vg context` and `vg search` without a Vault option use the Vaults linked to
that project. Outside a project they use the active registered Vault.

A Vault must also be registered in the Data Home (`vg setup` or `vg vault add`)
before Vault Graph indexes or searches it.

## Features

Each feature below lists what it does, when it runs, the command or MCP tool,
and what it reads and writes. "Data Home" is `$HOME/.vault-graph` unless you
pass `--graph-home`.

### Session-start recall

- **What it does**: prints a short Markdown memory bundle for the current
  project, which Claude Code adds to the session. Pinned memories come first.
- **When it runs**: automatically, from the SessionStart hook that vault-builder
  installs.
- **Command**: `vg hook session-start`. It reads the hook JSON on stdin.
  `--max-tokens` sets the token budget (default 1,500). The 9,000 character
  limit always applies. `--refresh-budget` sets how many seconds it may spend
  updating the index first (default 5, `0` skips).
- **Reads and writes**: reads `vault-map.json` and the index metadata of the
  linked Vaults. It does not run a search and does not load embeddings. It
  writes usage records and logs in the Data Home. It writes nothing in a Vault.

The bundle has these blocks, in order:

1. Pinned memories: current pages with `pin: true` from every linked Vault, in
   their own 400-token budget.
2. Project summary: the start of the project brief
   (`wiki/projects/<project>.md`) and the open items, decisions, and rules, in
   their own 500-token budget.
3. Memory list: the remaining pages, with the Vault name in each path.
4. Change notices.
5. How to open a page, how many inferred proposals wait for review, the cleanup
   backlog, a brief-update reminder, and Vaults whose index keeps failing.

Before recall, the hook indexes changed files of the linked Vaults (metadata
only). It also starts one detached `vg index` that adds embeddings after the
hook ends. Only one such process runs at a time. When no linked Vault has an
index yet, that process first builds keyword search for each Vault, then
embeddings. Exit code 3 means recall is not possible, for example because the
index is missing.

### Session capture

- **What it does**: hands the finished or compacted session to the Vault hook
  launcher, which writes the transcript into the Vault.
- **When it runs**: automatically, from the PreCompact and SessionEnd hooks that
  vault-builder installs.
- **Command**: `vg hook capture`. `--timeout` stops the launcher after the given
  seconds (default 20).
- **Reads and writes**: reads the hook's `transcript_path` and converts it to
  the `vg-session-jsonl/1` format in a temporary folder. Then it runs
  `vault_hooks.py capture --direct --normalized <file>` from the
  `vault-map.json` folder. The Vault tool chooses the Vault and writes the file.
  When conversion fails or the Vault tool is older, it runs `capture --direct`
  and the Vault writes its own format. vg does not index after capture.

Exit code 3 means the launcher was missing, failed, or ran out of time. When
`configs/session-export.json` in the Data Home names a folder, the same run also
exports the session there. `vg session export` exports past sessions by hand.

### Session fact extraction

- **What it does**: reads each captured session, extracts short facts with dates
  from each exchange, and stores them next to the session in the Vault. Search
  uses these facts to find the original exchange.
- **When it runs**: automatically after each capture that writes a session, in
  a background worker. It is on by default. Sessions captured before it was
  turned on are never queued.
- **Command**: `vg facts status` shows whether it is on, the extractor, the
  queue length, and recorded failures. `vg facts on --extractor claude|llama-server`
  turns it on and picks the extractor. `vg facts off` turns it off.
  `vg facts worker` processes the queue by hand.
- **Reads and writes**: settings in `configs/facts.json`, jobs in
  `facts/queue/`, results cached per exchange in `facts/cache/`, and failures
  in `logs/facts-failures.json`, all in the Data Home. The Vault command
  `sessions attach-facts` writes the facts into the Vault. vg writes no Vault
  file.

Extractors:

1. `claude` (default) runs the logged-in Claude Code as `claude -p` with model
   `claude-sonnet-5-5`, no tools, and no MCP servers. It uses your login, not
   `ANTHROPIC_API_KEY`. The vault-graph hooks do nothing inside that child
   session.
2. `llama-server` sends one request to a local `llama-server` at
   `http://127.0.0.1:8080/v1/chat/completions`. Set `endpoint` and `model` in
   `configs/facts.json` to change them. It sends no API key.

A failed job stays in the queue. Extractor and Vault command failures retry
after 30 minutes. A job the Vault rejects is removed. The first job ever queued
prints one notice that extraction is on.

### Memory writes

- **What it does**: adds, changes, retires, or restores memory pages in a Vault.
- **When it runs**: when the agent calls one of these MCP tools.
- **Tools**:

  | Tool | Effect |
  | --- | --- |
  | `remember` | Adds a new page: `decision` (`wiki/decisions/`), `system` (`wiki/systems/`), or the one `project` brief (`wiki/projects/<project>.md`). `pin` puts it first in recall. |
  | `update_memory` | Replaces the body of an existing page. |
  | `retire_memory` | Marks a page retired. The file stays. `replaced_by` names the page that replaces it. |
  | `supersede_claim` | Replaces one row of a page's claim table. The old row stays, marked superseded. |
  | `restore_memory` | Makes a retired, deprecated, or superseded page current again. |
  | `import_auto_memory` | Copies one Claude Code auto-memory note into the Vault under `raw/imports/claude-memory/` with the Vault's `import-source`. The note itself is not changed. |

- **Reads and writes**: every write runs a Vault command. vg never edits a Vault
  file.

All tools except `import_auto_memory` require `basis`:

1. `stated`: the user said the fact. The Vault's `publish-draft` validates it.
   The result is `published` or `rejected`.
2. `inferred`: the agent concluded it. Nothing is published. The Vault's
   `review propose` puts it in the Vault review queue (`scratch/review/`), and
   the result is `proposed` with a `review_path`. A person accepts it with the
   Vault's `review resolve`. A proposal is not in recall or search until then.

The target Vault must be linked to the `cwd` project. A new page goes to the
`vault` argument, else the project's `default_write_vault`, else the only linked
Vault. When none of these decides, the result is `vault_required` with the
candidate names, and nothing is written.

### Background reindex after a write

- **What it does**: indexes the Vault that a `published` write changed, so the
  page reaches search and recall.
- **When it runs**: automatically, right after a memory write returns
  `published`. The tool result does not wait for it. Read tools switch to the
  new index when the run finishes.
- **Command**: none. If the run cannot start, the result message asks you to run
  `vg index`.
- **Reads and writes**: writes a new index generation in the Data Home.

### Read tools

- **What it does**: searches and summarizes the Vaults linked to the project.
- **When it runs**: when the agent calls the MCP tool, or you run the CLI
  command.
- **Tools**:

  | Tool | CLI | Returns |
  | --- | --- | --- |
  | `explore_project` | - | For a coding task: current code, related tests, impact, Vault decisions, and freshness warnings. Call it first. Needs a registered, bound repository. |
  | `search_vault` | `vg search` | Ranked pages with line ranges. `mode` is `knowledge` (default), `evidence`, `operating`, `audit`, or `all`. `include_retired` shows retired pages. |
  | `ask_vault` | `vg ask` | An answer with cited evidence and claim status. |
  | `build_context_pack` | `vg context` | A token-bounded pack of evidence for a task. |
  | `get_decision_trace` | `vg decision-trace` | What led to a decision and what it replaced. |
  | `find_related` | `vg related` | Related graph entities with evidence. |
  | `get_recent_changes` | - | Pages changed since a date. |
  | `get_open_questions` | - | Open questions recorded in pages. |
  | `summarize_project_memory` | - | Current state, decisions, open questions, and next priorities. |
  | `check_index_status` | `vg status` | Index health and freshness. |
  | `explain_result` | - | Why a result was returned. |

- **Reads and writes**: read the index in the Data Home. They write nothing.

`search_vault`, `ask_vault` and `build_context_pack` accept `since` and `until`
(YYYY-MM-DD). Results in that date range come first. `vg search` also accepts
`--when "last week"` and `--date-strict`. Most tools take `cwd`, the project
folder. `scope` with `vault_ids` or `all_vaults` overrides the project's Vaults.

### Memory cleanup

- **What it does**: lists what should be saved, merged, or retired, so the agent
  can clean up memory with the user.
- **When it runs**: when the user asks to clean up memory. Session-start recall
  shows a backlog line when candidates wait. The `curate_memory` MCP prompt
  gives the agent the steps.
- **Tools**: `list_memory_candidates` returns candidates: `l1_note` (an
  auto-memory note no Vault keeps yet), `session_exchange` (a session exchange
  no page cites), `merge`, `retire`, and `brief`. Each call starts a new cleanup
  and allows at most 10 `inferred` proposals until the next call.
  `mark_candidates_reviewed` records candidates the user chose to skip.
- **Reads and writes**: candidates come from the index, usage records, and the
  Claude Code auto-memory folder. Skipped and handled candidates go to
  `memory/reviewed.jsonl` in the Data Home. Neither tool writes to a Vault. The
  memory write tools above make the actual changes.

### Code index

- **What it does**: indexes the symbols and calls of a code repository (Python
  and Dart) so `explore_project` and the `vg code` commands return current code
  next to Vault decisions.
- **When it runs**: manually. No repository is indexed until you register one.
- **Commands**:

  ```bash
  vg code repository add demo --path /path/to/repository --language python --language dart
  vg code index --repository-id demo
  vg project bind demo --vault-id default --scope wiki
  vg code impact calculate_total --repository-id demo
  ```

  `vg code search`, `symbol`, `outline`, `callers`, `callees` and `impact`
  query the index. `vg code status --verify` reports files that changed since
  indexing. `vg project bindings` lists bindings.
- **Reads and writes**: reads the repository. Writes the code index and the
  binding in the Data Home. It never writes source files and never copies
  source text into a Vault.

## Common Commands

| Goal | Command |
| --- | --- |
| Find setup problems | `vg doctor` |
| Register a Vault | `vg vault add work --path /path/to/vault` |
| List Vaults | `vg vault list` |
| Index all Vaults | `vg index --all-vaults` |
| Index one Vault | `vg index --vault-id work` |
| Rebuild from scratch | `vg index --all-vaults --full` |
| Check health | `vg status` |
| Search | `vg search "query"` |
| Search a date range | `vg search --when "last week" "query"` |
| Ask with evidence | `vg ask "question"` |
| Build a context pack | `vg context "goal"` |
| Trace a decision | `vg decision-trace TOPIC` |
| Fact extraction status | `vg facts status` |
| Show embedding model | `vg embedding list --graph-home ~/.vault-graph` |
| Change model or model folder | `vg embedding use arctic-m --models-dir /path/to/models --graph-home ~/.vault-graph` |
| Turn reranking on or off | `vg reranker use mmarco`, `vg reranker off` |
| Export sessions | `vg session export --agent claude-code --out /path/outside/vaults --all` |
| Preview harness guidance | `vg harness guidance preview --target /path/to/repository --file-name AGENTS.md` |

Every command takes `--graph-home` for a Data Home other than
`$HOME/.vault-graph`. Commands that accept `--vault-id` operate on one
registered Vault. `--all-vaults` expands to all enabled registered Vaults.

## Embedding Model

Vault Graph embeds every chunk with a local model for semantic search. The
default model is `arctic-m` (`Snowflake/snowflake-arctic-embed-m-v2.0`, int8).
It ranks pages by content when the question and the page are in different
languages, for example a Korean question over English pages. It reads up to 512
tokens per chunk and downloads about 311 MB. The first `vg setup` or `vg index`
downloads it. `vg setup --no-index` does not.

The alternative is `e5-small` (`Xenova/multilingual-e5-small`, int8, about
135 MB). It indexes faster, but in a Vault that mixes Korean and English pages
it ranks Korean pages above English pages that answer the question better. The
models are listed in `EMBEDDING_PRESETS`.

Model files live in `~/llm/models`, outside every registered Vault. The
model folder is saved in `configs/embedding.json` in the Data Home once you
change it.

```bash
vg embedding list
vg embedding use arctic-m --models-dir /path/to/models
```

`vg embedding list` shows the models, which one is selected, whether each is
already downloaded, and the model folder. It never downloads anything.
`vg embedding use arctic-m` downloads the model into the folder if it is not
there, then saves the model name and the folder. If the download fails, the
saved settings do not change. To use the smaller model, run
`vg embedding use e5-small`.

Indexing cost was measured on six Vaults on a computer with 36 GB of memory
(`docs/design/reports/2026-11-single-query-options.md` §7): a full index took
about 21 minutes with `arctic-m` and about 8 minutes with `e5-small`, and both
used up to about 5 GB of memory. Vaults with many session transcripts take
longer, because transcripts split into many small chunks.

Upgrading from a version whose default was `e5-small` or MiniLM, when
`configs/embedding.json` does not name a model:

1. The next `vg index`, or the background index at the next agent session
   start, re-embeds every chunk with `arctic-m`.
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
model on its own. To add another model, add one entry to `EMBEDDING_PRESETS` in
`src/vault_graph/interface/composition/adapters/text_embeddings.py`.

## Connect An Agent Through MCP

Installing `vg` and registering the MCP server are separate steps. Registration
tells an agent how to start `vg serve --mcp`. `vg setup --mcp` does it for you.
For explicit control:

```bash
vg mcp register --agent codex --config-path $HOME/.codex/config.toml
vg mcp config --agent codex --print
vg mcp unregister --agent claude
```

The JSON entry looks like this:

```json
{
  "mcpServers": {
    "vault-graph": {
      "command": "vg",
      "args": ["serve", "--mcp"]
    }
  }
}
```

The server exposes the tools in [Features](#features), read-only resources such
as `vault://{vault_id}/pages/{path}`, and prompts such as `curate_memory`. See
[`docs/FEATURES.md`](docs/FEATURES.md) for the full resource and prompt list.
Treat all output as working context. Re-read source lines when a warning reports
drift, and save durable conclusions with the memory write tools.

## Guarantees

- Vault Graph never edits Vault files directly. Every Vault change runs a Vault
  command.
- Inferred facts never publish without a person accepting them.
- It runs locally. Normal use needs no hosted service. The `claude` fact
  extractor runs your logged-in Claude Code.
- Results link to their evidence and carry warnings for stale, missing,
  contested, or retired material.
- Indexes can be deleted and rebuilt from the Vaults.
- Each Vault keeps its own identity, so pages with the same path in two Vaults
  do not collide.
- Index health and freshness are visible in `vg status` and `vg doctor`.

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

The last command installs all six wheels outside the workspace and verifies standalone use, the graph bridge, the text-to-vector indexing pipeline, and Vault integration. These packages are local build artifacts until separately published. Vault Graph requires the five module distributions. Concrete providers are assembled in `vault_graph.interface.composition`. See the [vector module contract](docs/design/specs/2026-10-06-vector-modules-ko.md).

To select the document graph backend for an existing Data Home:

```bash
vg index --graph-home /path/to/data-home --graph-backend document
```

The command validates and publishes a new generation. Future reads and index runs use that selection. Existing Data Homes keep the legacy backend until this explicit transition. With multiple enabled Vaults, include `--all-vaults`. Use `--dry-run` to report the intended transition without writing state.

To return to legacy storage, run the same command with `--graph-backend legacy`. Rollback rebuilds the full legacy graph and checks readiness before publication. Reads never repair an incomplete document graph or fall back to a stale legacy cache.

Switching back to the document backend rebuilds its staging cache. For an incompatible document schema, extraction profile, or checkpoint, run `vg index --graph-home /path/to/data-home --full` to rebuild explicitly. With multiple enabled Vaults, recovery requires `--all-vaults`. Recovery publishes only a validated generation and keeps the previous generation if rebuilding fails.

## More Documentation

- [`CHANGELOG.md`](CHANGELOG.md): what changed in each release
- [`docs/FEATURES.md`](docs/FEATURES.md): full list of CLI commands, MCP tools, resources, and prompts
- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md): source structure, ownership, and composition
- [`docs/SPEC.md`](docs/SPEC.md): Software Invariant Engine specification
- [`docs/DECISIONS.md`](docs/DECISIONS.md): accepted architectural and product decisions
- [`docs/TODO.md`](docs/TODO.md): roadmap and deferred work
- [`docs/PUBLISHING.md`](docs/PUBLISHING.md): release process with git tags and GitHub Releases
- [`docs/archive/`](docs/archive/): archived historical specifications

## License

Vault Graph is distributed under the MIT License. See [`LICENSE`](LICENSE).
