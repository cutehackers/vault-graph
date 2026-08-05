# Vault Graph

Status: Pre-release development

Vault Graph is a read-only, rebuildable knowledge access layer over Vault.

It helps humans and agents search Vault, trace decisions, inspect project
memory, and build task-specific context packs without turning retrieval output
into durable knowledge.

Vault remains the source of truth. Vault Graph reads, indexes, retrieves, and
explains Vault-derived context. It does not publish wiki pages, mutate raw
sources, edit Vault documents, or replace Vault's validation workflow.

## Install

Prerequisites:

- Python 3.12+
- [`uv`](https://docs.astral.sh/uv/)

Install the current pre-release from a source checkout:

```bash
git clone git@me.github.com:cutehackers/vault-graph.git
cd vault-graph
uv sync
uv run --python 3.12 vg --help
```

Optional editable command install from the source checkout:

```bash
uv tool install -e .
vg --help
```

The public PyPI install path is deferred until the first release:

```bash
uv tool install vault-graph
vg --help
```

## Quick Start

Run one setup command after installation:

```bash
vg setup --vault /path/to/llm-wiki --agent codex --mcp
```

By default, setup uses `~/.vault-graph` for local Data Home, registers the Vault,
runs indexing, and registers the `vault-graph` stdio MCP server in the Codex
config at `$CODEX_HOME/config.toml` or `~/.codex/config.toml`. Existing Codex
config is backed up before the `vault-graph` server entry is changed. Keep this
Data Home directory outside your Vault.

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
embedding model and cache it outside your Vault. Restart your agent after MCP
registration so it can load the new server.

## Common Commands

| Goal | Command |
| --- | --- |
| Register a Vault | `vg init --vault /path/to/llm-wiki --graph-home ~/.vault-graph` |
| Add another Vault | `vg vault add work --path /path/to/other-vault --graph-home ~/.vault-graph` |
| List Vaults | `vg vault list --graph-home ~/.vault-graph` |
| Index the active Vault | `vg index --graph-home ~/.vault-graph` |
| Index one Vault | `vg index --vault-id work --graph-home ~/.vault-graph` |
| Index all Vaults | `vg index --all-vaults --graph-home ~/.vault-graph` |
| Check health | `vg status --graph-home ~/.vault-graph` |
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

## Connect An Agent Through MCP

MCP server installation and MCP server registration are different things:

- installation makes the `vg` command available
- registration tells an agent how to start `vg serve --mcp`

For Codex, the easiest supported path is:

```bash
vg setup --vault /path/to/llm-wiki --agent codex --mcp
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

## More Documentation

- [`docs/FEATURES.md`](docs/FEATURES.md): user-facing feature catalog
- [`docs/SPEC.md`](docs/SPEC.md): product specification and architecture
- [`docs/DESIGN.md`](docs/DESIGN.md): design goals and boundaries
- [`docs/PUBLISHING.md`](docs/PUBLISHING.md): PyPI release workflow and permissions
- [`docs/TODO.md`](docs/TODO.md): explicit deferred work and scale-up backlog

## License

Vault Graph is distributed under the MIT License. See [`LICENSE`](LICENSE).
