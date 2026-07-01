# Vault Graph

Status: Active local development

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

Current source-checkout install:

```bash
git clone git@me.github.com:cutehackers/vault-graph.git
cd vault-graph
uv sync
uv run --python 3.12 vg --help
```

Optional local command install from this checkout:

```bash
uv tool install -e .
vg --help
```

PyPI registration is not required to use the current source checkout. It becomes
necessary only when Vault Graph wants to promise this public install path:

```bash
uv tool install vault-graph
```

Do not advertise the PyPI command as the primary install path until the package
has been published.

## Quick Start

Keep Vault Graph state outside your Vault:

```bash
vg init --vault /path/to/llm-wiki --state ~/.vault-graph
vg index --state ~/.vault-graph
vg status --state ~/.vault-graph
vg search --state ~/.vault-graph "GraphRAG"
vg context --state ~/.vault-graph "Implement GraphRAG MVP"
```

The first index builds local metadata, keyword, vector, and graph projections.
Vault Graph uses local storage and local embeddings by default; it does not
require hosted services for normal use.

## Common Commands

| Goal | Command |
| --- | --- |
| Register a Vault | `vg init --vault /path/to/llm-wiki --state ~/.vault-graph` |
| Add another Vault | `vg vault add work --path /path/to/other-vault --state ~/.vault-graph` |
| List Vaults | `vg vault list --state ~/.vault-graph` |
| Index the active Vault | `vg index --state ~/.vault-graph` |
| Index one Vault | `vg index --vault-id work --state ~/.vault-graph` |
| Index all Vaults | `vg index --all-vaults --state ~/.vault-graph` |
| Check health | `vg status --state ~/.vault-graph` |
| Search evidence | `vg search --state ~/.vault-graph "query"` |
| Include graph signals | `vg search --include-graph --state ~/.vault-graph "query"` |
| Ask with evidence | `vg ask --state ~/.vault-graph "question"` |
| Build a context pack | `vg context --state ~/.vault-graph "goal"` |
| Find related items | `vg related --state ~/.vault-graph GraphRAG` |
| Trace a decision | `vg decision-trace --state ~/.vault-graph GraphRAG` |

Commands that accept `--vault-id` operate on one registered Vault. Commands that
accept `--all-vaults` expand to all enabled registered Vaults. Commands without
either option use the active Vault.

## Connect An Agent Through MCP

MCP server installation and MCP server registration are different things:

- installation makes the `vg` command available
- registration tells an agent how to start `vg serve --mcp`

After indexing your Vault, register this stdio server in the agent's MCP config:

```json
{
  "mcpServers": {
    "vault-graph": {
      "command": "uv",
      "args": [
        "run",
        "--python",
        "3.12",
        "vg",
        "serve",
        "--mcp",
        "--state",
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

Vault Graph provides evidence-first working context and evidence-first answers
through `ask_vault` and `vg ask`.

## Recommended Easy Setup

The accepted onboarding target is a one-command setup flow:

```bash
vg setup --vault /path/to/llm-wiki --agent codex
```

This command:

- uses `~/.vault-graph` as the default state path when `--state` is omitted
- registers the Vault path
- runs indexing
- prepares MCP registration for the selected agent
- prints the MCP server command or writes it only to an explicit agent config path

The lower-level MCP commands should remain available for explicit control:

```bash
vg mcp register --agent codex --state ~/.vault-graph --config-path /path/to/agent-config.json
vg mcp config --agent codex --state ~/.vault-graph --print
```

These commands are implemented product features. Their implementation design
lives at
[`docs/superpowers/specs/2026-06-24-cli-todo-command-implementation-design.md`](docs/superpowers/specs/2026-06-24-cli-todo-command-implementation-design.md):

```bash
vg setup --vault /path/to/llm-wiki --agent codex
vg mcp register --agent codex --state ~/.vault-graph --config-path /path/to/agent-config.json
vg mcp config --agent codex --state ~/.vault-graph --print
vg watch
vg ask "question"
vg serve --http
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

## License

Vault Graph is distributed under the MIT License. See [`LICENSE`](LICENSE).
