# Vault Graph

English | [한국어](README-kr.md)

Status: Pre-release development

Vault Graph (`vg`) gives Claude Code a long-term memory. Your memory lives in
Vaults that vault-builder manages. Vault Graph indexes those Vaults, reminds
Claude of the right memories at the start of each session, and lets Claude
search and save memory while you work. It never edits Vault files itself. Every
change goes through the Vault's own tools.

## Install

Quit Claude Code, then run this in a terminal. It installs `vg` and
vault-builder, sets up your Vaults and hooks, and registers the MCP servers:

```bash
curl -fsSL https://raw.githubusercontent.com/cutehackers/vault-graph/main/scripts/install.sh | bash
```

Start Claude Code again and check the servers with `/mcp`. Then index your
Vaults once. The first run can take a while:

```bash
vg index --all-vaults
```

To install another tag or branch, set `VAULT_GRAPH_REF`. To remove Vault Graph,
add `--uninstall` (`| bash -s -- --uninstall`). To install only `vg`:

```bash
uv tool install --python 3.12 git+https://github.com/cutehackers/vault-graph.git@vX.Y.Z
```

For every option, Codex setup, and MCP registration, see
[docs/INSTALL.md](docs/INSTALL.md).

## Quick Start

The install command already ran setup. Run it yourself only after installing
`vg` alone:

```bash
vg setup --agent claude --mcp --dry-run
vg setup --agent claude --mcp
```

For Codex, use `vg setup --vault /path/to/vault --agent codex --mcp`. The first
indexing run may download the pinned local embedding model. Then try it:

```bash
vg ask --graph-home ~/.vault-graph "What changed recently?"
vg search --graph-home ~/.vault-graph "GraphRAG"
vg context --graph-home ~/.vault-graph "Implement GraphRAG MVP"
vg status --graph-home ~/.vault-graph
```

## What Runs Automatically

After install you do not need to run anything for these. Each step also has a
command or tool if you want to run it yourself.

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/assets/vault-graph-flow-dark.svg">
  <img src="docs/assets/vault-graph-flow-light.svg" alt="Vault Graph flow. Read: at session start, vg hook session-start reads the index of the linked Vaults and adds a memory summary to the session. During work, search_vault and ask_vault read the same index. Write: remember with basis stated goes through Vault publish-draft and a background reindex. With basis inferred it waits in the Vault review queue until a person runs review resolve. Session end: vg hook capture hands the session to the Vault, the fact worker extracts dated facts, and the Vault attaches a .facts.md file. Accepted proposals and fact files reach the index at the next index run." width="900">
</picture>

1. **When a session starts**, Vault Graph picks up Vault files that changed,
   then gives Claude a short summary of this project's memory. Pinned memories
   come first. Embeddings for new files are built in the background after that.
   - By hand: `echo '{}' | vg hook session-start`, or the MCP tool
     `summarize_project_memory`.
2. **When a session ends or Claude compacts it**, Vault Graph hands the
   conversation to the Vault, and the Vault saves it.
   - By hand: `vg session export --agent claude-code --out /path/outside/vaults --session ID --recapture`.
3. **After a session is saved**, a background worker asks Claude (or a local model, if you chose one) to pull short,
   dated facts out of the conversation. The Vault attaches those facts to the
   saved session, and search uses them to find the right part of the
   conversation. It is on by default. `vg facts off` turns it off.
   - By hand: `vg facts status` to see the queue, `vg facts worker` to process it.
   - Optional: `vg dream on` also lets a background worker propose memories from
     saved sessions. Nothing is saved until you accept a proposal in the Vault
     review queue. `vg dream status` shows what it sent.
4. **After Claude saves a memory you stated**, Vault Graph re-indexes that Vault
   in the background, so the new page shows up in search and in the next
   session's summary.
   - By hand: `vg index --vault-id ID`, or `vg index --all-vaults`.
5. **When Claude infers a memory instead of hearing it from you**, it is not
   saved yet. It waits in the Vault's review queue until you accept it. Until
   then it does not appear in search or in the session summary.
   - By hand, in the Vault folder: `python3 tools/wiki/cli.py review list --status pending`
     lists them, and
     `python3 tools/wiki/cli.py review resolve <review_path> --status accepted --resolution "<reason>"`
     accepts one.

Claude uses MCP tools for the rest: `search_vault` and `ask_vault` to look
things up, and `remember` or `update_memory` to save memory. For every feature,
tool, and file it reads or writes, see [docs/FEATURES.md](docs/FEATURES.md).

## Common Commands

| Goal | Command |
| --- | --- |
| Find setup problems | `vg doctor` |
| Index all Vaults | `vg index --all-vaults` |
| Check health | `vg status` |
| Search | `vg search "query"` |
| Ask with evidence | `vg ask "question"` |
| Fact extraction status | `vg facts status` |
| Dreaming status | `vg dream status` |
| Show embedding model | `vg embedding list --graph-home ~/.vault-graph` |
| Change model or model folder | `vg embedding use arctic-m --models-dir /path/to/models --graph-home ~/.vault-graph` |

## Embedding Model

Search uses a local embedding model. The default is `arctic-m` (about 311 MB).
`e5-small` is smaller and faster, but ranks mixed Korean and English pages less
well. Models live in `~/llm/models`. `vg embedding list` shows them and
`vg embedding use` switches. After a switch, search returns keyword results only
until re-indexing finishes. The model list is `EMBEDDING_PRESETS`. For time,
memory, and upgrade steps, see [docs/INSTALL.md](docs/INSTALL.md#embedding-model).

## Develop From Source

```bash
git clone https://github.com/cutehackers/vault-graph.git
cd vault-graph
uv sync
uv tool install --python 3.12 -e .
```

For the reusable packages, builds, and graph backends, see
[docs/DEVELOPMENT.md](docs/DEVELOPMENT.md).

## More Documentation

- [docs/INSTALL.md](docs/INSTALL.md): install options, setup, MCP registration, embedding model
- [docs/FEATURES.md](docs/FEATURES.md): every feature, command, MCP tool, resource, and prompt
- [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md): working from source and the reusable packages
- [CHANGELOG.md](CHANGELOG.md): what changed in each release
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md): source structure and composition
- [docs/DECISIONS.md](docs/DECISIONS.md): accepted decisions
- [docs/PUBLISHING.md](docs/PUBLISHING.md): release process

## License

MIT. See [`LICENSE`](LICENSE).
