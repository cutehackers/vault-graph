# Installing Vault Graph

This page has the full install and setup details. The README has the short version.

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
background (see the session-start recall in [FEATURES.md](FEATURES.md#session-start-recall)), and recall
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

Then run setup (next section).


## Setup

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

The server exposes the tools in [FEATURES.md](FEATURES.md#features-in-detail), read-only resources such
as `vault://{vault_id}/pages/{path}`, and prompts such as `curate_memory`. See
[FEATURES.md](FEATURES.md) for the full resource and prompt list.
Treat all output as working context. Re-read source lines when a warning reports
drift, and save durable conclusions with the memory write tools.


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

