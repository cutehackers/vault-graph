# Vault Graph User-Facing Features

Status: Active feature contract

This document lists the features and interfaces exposed to Vault Graph users. It
focuses on what a user or agent can invoke directly through CLI, MCP resources,
MCP tools, MCP prompts, Claude Code hooks, and HTTP serving.

The first sections describe the main features in one form: what it does, when
it runs, the command or tool, and what it reads and writes. The sections after
them are the full reference.

For architecture, storage contracts, indexing internals, and roadmap details,
see `docs/SPEC.md`.

The feature matrix describes the product surface. Sections below distinguish
implemented capabilities, historical slice boundaries, and explicitly deferred
adapters.

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

## Features In Detail

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

### Dreaming

- **What it does**: after a session is saved, reads session exchanges that no
  memory page cites yet and proposes memories for a person to review. It also
  checks existing pages against later exchanges on the same topic and proposes
  corrections. It never publishes anything.
- **When it runs**: it is off by default. When it is on, it runs in two ways.
  - After a capture that writes a session, a background worker runs for that
    project when all of these hold:
    1. Dreaming is on (`vg dream on`).
    2. The project's last run was more than 24 hours ago.
    3. The write Vault has fewer than 10 memory proposals waiting for review.
    4. At least 20 exchanges were never judged, or their median age is over 7
       days.
  - Once a day at `run_at` local time (default 01:00), on macOS only. One
    launchd job runs every project in `vault-map.json` whose root folder
    exists, one at a time, from that root folder. This run skips condition 2
    and keeps 1, 3 and 4, so a scheduled run starts the 24 hours for the hook
    run. If another dream run holds the lock, it waits up to 30 minutes, then
    skips that project. If the Mac was asleep at that time, launchd runs it once
    after the Mac wakes (as `man launchd.plist` describes; not yet checked on a
    real Mac). A project that fails is logged and the next one still
    runs.
- **Command**: `vg dream on` and `vg dream off` switch it. On macOS `on` also
  installs the daily launchd job and `off` removes it. If installing fails,
  dreaming stays on, the reason is printed with "hook runs still work", and the
  command ends with 1. `vg dream at HH:MM` sets the daily time and, while
  dreaming is on, installs the job again for that time. `vg dream status`
  shows the run time, whether the daily job is installed, out of date
  (`stale`), not installed, or unsupported on this platform, the last scheduled run, and also
  the settings, the last run of each project, how many dream proposals
  were accepted, rejected, or still wait, and whether a Vault reached the
  pending cap. An accept counts only when the Vault published it. An item whose
  `status` was changed by hand is listed as `unpublished` with how to fix it. `vg dream run --cwd PATH` does one run by hand, and
  `--dry-run` judges without sending anything.
- **How it judges**: it runs the logged-in Claude Code as `claude -p` with model
  `claude-sonnet-5-5`, no tools, and no MCP servers. It uses your login, not
  `ANTHROPIC_API_KEY`. The vault-graph hooks do nothing inside that child
  session.
- **What the code checks before sending a proposal**:
  1. The quote is in what you typed in that exchange.
  2. A page to change was shown for that exchange, is current, is not pinned,
     and is not the project brief.
  3. An update only adds text to a page that `remember` wrote, and keeps its
     earlier evidence lines.
  4. A claim to replace is in the page.
  5. The page did not change after the judge read it, and one run changes a
     page at most once.
- **Reads and writes**: every proposal goes through the Vault's
  `review propose` with `basis` `inferred`, at most 10 per run. You accept or
  reject each one with `vg review`. Settings are in
  `configs/dream.json` (with `run_at`), runs in `logs/dream-runs.jsonl` (each
  `run` line records its `trigger`: `hook`, `manual` or `schedule`), the daily
  run's output in `logs/dream-schedule.log`, and exchanges judged without a
  proposal in `dream/judged.jsonl`, all in the Data Home. The daily job is one
  plist in `~/Library/LaunchAgents` named `io.vault-graph.dream.<hash>.plist`. An exchange
  judged without a proposal still shows up in a manual memory cleanup.

### Reviewing memory proposals

- **What it does**: shows the memory proposals that wait in the review queues
  of the project's linked Vaults, and accepts or rejects them. Proposals come
  from dreaming and from MCP writes with `basis` `inferred`.
- **When it runs**: only when a person runs `vg review` in the project folder.
  No MCP tool, hook, or background worker accepts or rejects a proposal.
- **Command**:
  1. `vg review` shows each waiting proposal with its Vault, target page,
     summary, the text it changes, and its evidence, then asks accept, reject,
     skip, or quit. A skipped proposal comes back next time. It asks only in a
     terminal. Anywhere else it prints the list.
  2. `vg review list` lists the waiting proposals, accepts that were never
     published, and how many other review items wait.
  3. `vg review show ID` shows one proposal.
  4. `vg review accept ID` accepts one. `vg review reject ID --reason TEXT`
     rejects one.
- **Reads and writes**: it reads the Vault review queue (`scratch/review/`).
  Accept and reject run the Vault's `review resolve`. vg never edits a Vault
  file. After an accept the Vault publishes the page, and vg indexes that Vault
  in the background.
- **Limits**: it handles memory proposals only. The proposal text cannot be
  edited here: reject it and propose again. vg cannot stop an agent that types
  `vg review accept` in a shell. If you set an item's `status` to `accepted`
  by hand, nothing is published. Set `status` back to `pending` and
  `resolution` to an empty value in the item file, then accept it with
  `vg review`.

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
   the result is `proposed` with a `review_path`. A person accepts it with
   `vg review` in the project folder. A proposal is not in recall or search
   until then.

`remember`, `update_memory`, and `supersede_claim` take an optional `quote`.
When `basis` is `stated` and the evidence names a session file
(`raw/sessions/...md`), `quote` is required: your own words, copied exactly from
the exchange. The evidence must name the exchange with its line range
(`<path> L<a>-L<b>`). The tool checks that the words are in what you typed
there and returns `rejected` when they are not, or when the line range is
missing. A prompt given to a subagent never counts as your words.

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

## Product Boundary

Vault Graph is a rebuildable access layer over Vault. Vault holds all durable
knowledge. Vault Graph holds indexes, usage records, and settings in its Data
Home (`$HOME/.vault-graph` by default).

`vg search` defaults to `--mode knowledge`. `evidence`, `operating`, `audit`,
and `all` search other page groups. `vg projection-audit` reports plaintext
duplication, dangling index references, and component revisions.

It can:

- read Vault content and index it locally
- search, explain, and answer from Vault evidence
- build evidence-linked context for humans and agents
- inject a session-start recall through a Claude Code hook
- hand finished sessions to the Vault and extract facts from them
- write memory, but only by running the Vault's own commands

It does not:

- create, edit, or delete Vault files itself
- write to `raw/`
- publish an inferred fact without a person accepting it in the Vault review
  queue
- resolve contradictions automatically
- replace Vault as the source of truth

## Feature Matrix

This matrix includes implemented user-facing capabilities covered by CLI, MCP,
or local HTTP acceptance tests.

| Feature | CLI | MCP Tool | MCP Resource | Output |
| --- | --- | --- | --- | --- |
| First-run onboarding | `vg setup --vault PATH --agent codex --mcp` | - | - | One Data Home, Vault registration, baseline index, MCP config, readiness and recovery hints |
| Initialize Vault Graph | `vg init --vault /path/to/vault` | - | - | Default Vault path and Data Home setup |
| Register Vault | `vg vault add ID --path /path/to/vault`, `vg vault list` | - | - | Vault catalog entries |
| Index Vault | `vg index`, `vg index --vault-id ID`, `vg index --all-vaults`, `vg index --full`, `vg index --dry-run` | - | - | Index revision, change plan, warnings |
| Watch Vault | `vg watch` | - | - | Continuous index refresh |
| Check Status | `vg status` | `check_index_status(scope=None)` | - | Vault IDs/paths, backend health, schema compatibility, freshness, warnings |
| Ask Vault | `vg ask "question"` | `ask_vault(question, mode="evidence-first", scope=None)` | - | Answer, claims, evidence, reasoning trace, warnings |
| Search Vault | `vg search "query"` | `search_vault(query, scope=None, limit=10, mode="knowledge", include_retired=False, since=None, until=None, cwd=None)` | document/page/source resources | Ranked evidence-linked results |
| Find Related Items | `vg related TARGET` | `find_related(target, scope=None, depth=1, kinds=None)` | `vault://{vault_id}/graph/entities/{id}` | Related entities, paths, evidence |
| Trace Decision | `vg decision-trace TOPIC` | `get_decision_trace(decision_or_topic, scope=None)` | `vault://{vault_id}/decisions/{id}` | Decision, context, alternatives, tradeoffs |
| Build Context Pack | `vg context "goal"` | `build_context_pack(goal, scope=None, max_tokens=None)` | `vault://context/packs/{id}` | JSON or Markdown agent brief |
| Summarize Project Memory | - | `summarize_project_memory(scope=None, limit=10)` | `vault://{vault_id}/context/current` | Current state, decision highlights, open issues |
| Get Open Questions | - | `get_open_questions(scope=None, limit=20)` | `vault://{vault_id}/issues/{id}` | Open questions and unresolved follow-ups |
| Get Recent Changes | - | `get_recent_changes(since=None, scope=None, limit=20)` | `vault://{vault_id}/timeline/recent` | Recent indexed document snapshot and projection changes |
| Explain Result | - | `explain_result(result_id)` | - | Retrieval reason, evidence, scores, warnings |
| Register Code Repository | `vg code repository add ID --path PATH --language LANGUAGE` | - | - | Read-only repository catalog entry |
| Index And Query Code | `vg code index`, `vg code search`, `vg code symbol`, `vg code outline`, `vg code callers`, `vg code callees`, `vg code impact` | - | `vg-source://{repository_id}/{path}#L{start}-L{end}` | Bounded symbols, source links, traversal, freshness warnings |
| Bind Project Authorities | `vg project bind REPOSITORY_ID --vault-id ID`, `vg project bindings` | - | - | Explicit Graph-owned repository-to-Vault selection |
| Explore Project | - | `explore_project(task, project_path=None, repository_id=None, max_tokens=None, depth=2, limit=20)` | repository and Vault evidence links | Bounded code, tests, impact, Vault evidence, revisions, freshness, warnings |
| Install Harness Guidance | `vg harness guidance preview/install/remove` | - | - | Explicit marker-fenced `AGENTS.md` or `CLAUDE.md` guidance outside Vault |
| Session-start recall | `vg hook session-start` (SessionStart hook) | - | - | Markdown memory bundle: pinned pages, project summary, memory list, notices |
| Session capture | `vg hook capture` (PreCompact and SessionEnd hooks) | - | - | Normalized session handed to the Vault hook launcher |
| Session fact extraction | `vg facts on`, `vg facts off`, `vg facts status`, `vg facts worker` | - | - | Facts per session exchange, written by the Vault's `sessions attach-facts` |
| Dreaming | `vg dream on`, `vg dream off`, `vg dream at`, `vg dream status`, `vg dream run` | - | - | `inferred` memory proposals in the Vault review queue |
| Review memory proposals | `vg review`, `vg review list`, `vg review show ID`, `vg review accept ID`, `vg review reject ID --reason TEXT` | - | - | Waiting proposals with the text they change, then `accepted` or `rejected` by the Vault's `review resolve` |
| Export sessions | `vg session export --agent claude-code --out PATH` | - | - | Raw copies and normalized session files outside every Vault |
| Write memory | - | `remember`, `update_memory`, `retire_memory`, `supersede_claim`, `restore_memory`, `import_auto_memory` | - | `published`, `proposed` (review queue), `rejected`, or `vault_required` |
| Clean up memory | - | `list_memory_candidates`, `mark_candidates_reviewed`, prompt `curate_memory` | - | Cleanup candidates with comparison pages and keys |
| Diagnose setup | `vg doctor` | - | - | One fix command per index, model, or MCP problem |
| Manage models | `vg embedding list/use`, `vg reranker use/off` | - | - | Selected embedding and rerank models |
| Serve MCP | `vg serve --mcp` | - | all MCP resources | MCP server for agents |
| Serve HTTP | `vg serve --http` | - | - | HTTP access surface |

## Search Scope

Without a Vault option or `scope`, the read tools and `vg search`, `vg ask`
and `vg context` use the Vaults linked to the current project in
`vault-map.json`. MCP tools take the project folder as `cwd`. Outside a project
they use the active registered Vault. `--vault-id`, `--all-vaults`, or `scope`
with `vault_ids` or `all_vaults` override this choice.

Graph signals are opt-in: use `vg related`, `vg decision-trace`, or
`--include-graph`. Context packs are working briefs, not answers and not durable
Vault knowledge.

`explore_project` is the preferred coding entry point. It requires a registered
repository and an explicit Graph-owned binding to one or more Vaults. It never
guesses an active Vault. When code indexing is unavailable, it returns a
Vault-only result with a visible warning rather than stale code.

The history of each slice is in `CHANGELOG.md` and `docs/PATCH_LOG.md`.

## Code And Project Context Features

Code projection is read-only and rebuildable. Register a repository, index it,
and bind it explicitly to the Vault authority that carries its durable project
knowledge:

```bash
vg code repository add demo --path /path/to/repository --language python --language dart
vg code index --repository-id demo
vg project bind demo --vault-id main --scope wiki
vg code impact calculate_total --repository-id demo
```

Code links identify bounded current lines through `vg-source://` URIs. They do
not embed source bodies in stored projections or MCP output. `vg code status
--verify` reports drift; stale, partial, or unavailable results remain visible
as warnings.

For an agent connected through MCP, call `explore_project` first. It combines
current code structure, impact and related tests with bounded relevant Vault
evidence. The response remains working evidence: confirm changed source lines
before editing, and publish durable conclusions only through the Vault workflow.

Harness guidance is an explicit opt-in command. It only changes the selected
non-Vault `AGENTS.md` or `CLAUDE.md`, previews before mutation when requested,
backs up the original before a write, and can remove only its own marker block.

## Evidence-First Ask And Reasoning

`vg ask` and `ask_vault` are current core product capabilities. They make
Vault Graph useful when a user wants a reasoned answer rather than a search
result list or a context pack.

The user-facing value is:

- ask a natural-language question against one Vault or an explicit Vault scope
- receive a concise answer grounded in original Vault evidence
- see which claims are directly supported, inferred, partial, unsupported, or
  missing
- inspect the evidence and reasoning trace behind the answer
- receive warnings for stale, missing, contested, deprecated, or conflicting
  evidence
- receive safe durable follow-up guidance when new knowledge should be captured
  through Vault's normal workflow

The implementation value is:

- reuse existing search, graph, decision-trace, context-pack, explanation, and
  memory projection services
- keep `AnswerService` as the deep application boundary for CLI, MCP, and later
  HTTP adapters
- keep `EvidencePlanner` responsible for selecting evidence-gathering steps
- keep `AnswerComposer` responsible for composing the answer from resolved
  evidence
- keep `CitationGuard` responsible for preventing unsupported claims from
  appearing as normal answer facts
- avoid introducing a writable memory database or a second source of truth

## CLI Features

### First-run onboarding

The supported first-run path is:

```bash
vg setup --vault /path/to/vault --agent codex --mcp
vg status
```

`setup` creates the canonical `~/.vault-graph` Data Home (or the explicit
`--graph-home` path), registers the Vault, publishes the baseline projection,
and writes the normalized absolute MCP configuration path. Re-running setup for
the same Vault ID and root is idempotent: it updates the existing catalog entry
and generation instead of creating another Data Home. `--dry-run` performs the
same preflight without writing the Data Home, Vault, or agent configuration.

Vault Graph is pre-release. If setup detects a known legacy Data Home layout, it
returns `legacy_data_home_detected` and does not read, merge, copy, or modify
the old derived files. Choose a new `--graph-home` (or move the rebuildable
directory aside) and rerun setup to rebuild from Vault. There is no migration
command in the first release.

### Initialize

```bash
vg init --vault /path/to/vault
vg init --vault-id main --vault /path/to/vault
vg vault add work --path /path/to/other-vault
vg vault list
```

Configures one or more Vault roots and the Vault Graph Data Home location. If no
Vault ID is provided, `vg init --vault /path/to/vault` creates the active entry
with `vault_id: default`. Commands should be explicit about which Vault ID,
Vault path, and Vault Graph Data Home path they use.

Commands that support Vault selection use the active Vault by default.
`--vault-id ID` selects one Vault. `--all-vaults` expands to all enabled Vault
IDs and must make that selection visible in output.

### Index

```bash
vg index
vg index --vault-id main
vg index --all-vaults
vg index --full
vg index --dry-run
```

Builds or refreshes Vault-derived indexes.

User-visible behavior:

- detects changed, stale, and deleted files
- supports incremental and full rebuilds
- updates metadata first and then reconciles the local vector
  projection for the selected scope
- uses the active Vault by default
- supports `--vault-id ID` for one Vault and `--all-vaults` for all enabled
  Vaults
- reports index revision information
- reports vector upserts, tombstones, unchanged records, stale
  records, model spec, backend health, and recoverable vector failures
- in dry-run output, reports configured `embedding_batch_size`,
  parallelism, lazy loading, and planned embedding count without loading the
  model
- returns a nonzero exit if metadata succeeds but vector reconcile
  fails, while preserving the applied metadata revision in output and status
- reports graph entity upserts, relationship upserts, evidence
  reference upserts, tombstones, stale graph records, affected Vault IDs,
  `GraphExtractionSpec`, graph revision metadata, and projection cache
  invalidations
- returns a nonzero exit if metadata/vector work succeeds but graph
  reconcile fails, while preserving completed earlier projection state in output
  and status
- reports vector and graph indexing failures independently when
  both are enabled
- reports warnings for source drift, duplicates, stale data, or missing evidence
- supports dry-run planning before index mutation

Indexing must not mutate Vault files.

### Watch

```bash
vg watch
```

Watches Vault for changes and keeps Vault Graph indexes fresh.

### Status

```bash
vg status
vg status --vault-id main
vg status --all-vaults
```

Reports operational status.

The status surface should show:

- configured Vault IDs and paths
- configured Vault Graph Data Home path
- backend health
- schema compatibility
- index revision freshness
- Chroma vector backend health, schema compatibility, active
  `EmbeddingModelSpec`, vector revision, stale count, status scope, and last
  vector failure
- default local embedding model, model revision, model cache
  availability, throughput tuning, and model-unavailable errors
- graph backend health, graph schema compatibility,
  `GraphExtractionSpec`, graph revisions by Vault/actual scope, stale graph
  record counts, tombstone counts, last graph failure, and graph projection cache
  freshness
- active generation identity, projection bundle validity, enabled component
  capabilities, common source-snapshot identity, and component revisions
- projection recovery hints when no active bundle exists or a publication failed
- stale or invalid vector/graph cache warnings

By default, freshness fields use the active Vault. `--vault-id ID` reports one
Vault, and `--all-vaults` reports all enabled Vaults with explicit Vault IDs in
the output.

### Ask

```bash
vg ask "Why did we adopt GraphRAG?"
vg ask --vault-id main "Why did we adopt GraphRAG?"
```

Asks a natural-language question against Vault-derived knowledge. This is the
implemented answer workflow over the existing evidence-first services.

The command calls the same `AnswerService` used by MCP and later HTTP
adapters. It must not read stores directly, mutate Vault files, run indexing,
download models, or create a writable memory layer.

The answer should separate:

- answer
- claim status: supported, partial, inferred, unsupported, or missing
- evidence
- inferred links
- reasoning trace
- warnings
- suggested durable follow-up

Expected behavior:

- uses the Vaults linked to the current project by default, else the active
  Vault
- supports `--vault-id` and `--all-vaults` for scoped answering
- uses existing search, graph, decision-trace, context-pack, and memory
  projection services where available
- cites every major answer claim or labels it as unsupported or partial
- returns `insufficient_evidence` instead of inventing missing facts
- carries `vault_id`, document/chunk identity, store revisions, and freshness
  status in evidence metadata
- suggests a safe Vault workflow or indexing command when the answer exposes
  missing evidence, stale projections, or useful publication candidates

### Related

```bash
vg related GraphRAG
vg related --vault-id main GraphRAG
vg related --all-vaults GraphRAG
```

Finds items related to a concept, project, decision, issue, system, workflow, or
other indexed entity.

Results should include evidence paths and distinguish stated relationships from
inferred, contested, deprecated, or stale relationships.

### Context

```bash
vg context "Implement GraphRAG MVP"
vg context --vault-id main "Implement GraphRAG MVP"
vg context --all-vaults "Implement GraphRAG MVP"
vg context --include-graph "Implement GraphRAG MVP"
vg context --format json "Implement GraphRAG MVP"
vg context --format markdown "Implement GraphRAG MVP"
vg context --max-tokens 8000 "Implement GraphRAG MVP"
```

Builds a scoped context pack for a concrete task.

The output should be small enough for an agent to read directly and rich enough
to avoid a full Vault scan.

Context behavior:

- JSON is the canonical artifact
- Markdown is a rendering view over the JSON artifact
- evidence chunks remain the authority unit
- stale, missing, contested, deprecated, truncated, and omitted material appears
  as warnings
- `--include-graph` is required for graph signals
- `--include-cross-vault` requires `--all-vaults --include-graph`
- graph backend and graph revision fields are not used by default context packs

### Decision Trace

```bash
vg decision-trace GraphRAG
vg decision-trace --vault-id main GraphRAG
vg decision-trace --all-vaults GraphRAG
```

Explains a decision or topic through durable decision pages, related evidence,
source pages, concepts, tradeoffs, and revisit conditions.

### Serve

```bash
vg serve --mcp
vg serve --http
```

Starts a server interface for agents or custom clients.

## MCP Resources

Vault Graph exposes read-only MCP resources for documents, pages, generated
context, timeline data, and graph entities.

Initial resource URIs:

```text
vault://{vault_id}/documents/{path}
vault://{vault_id}/pages/{path}
vault://{vault_id}/sources/{id}
vault://{vault_id}/concepts/{name}
vault://{vault_id}/decisions/{id}
vault://{vault_id}/issues/{id}
vault://{vault_id}/timeline/recent
vault://{vault_id}/context/current
vault://context/packs/{id}
vault://{vault_id}/graph/entities/{id}
```

Resource responses should include evidence metadata when relevant, such as Vault
ID, Vault path, wiki path, section or anchor, content hash, raw SHA-256,
retrieval reason, confidence, warning, vault revision, and index revision.
`vault://context/packs/{id}` is a generated artifact URI. The pack body records
the `QueryScope` used when it was created.

## MCP Tools

The feature matrix lists the product surface. MCP registers only tools backed by
existing application services.

The memory write tools (`remember`, `update_memory`, `retire_memory`,
`supersede_claim`, `restore_memory`, `import_auto_memory`) and the cleanup tools
(`list_memory_candidates`, `mark_candidates_reviewed`) are described above
under Memory writes and Memory cleanup. Their full argument lists are in
the tool descriptions the server sends to the agent
(`src/vault_graph/interface/mcp/mcp_memory_tools.py` and `mcp_tools.py`).

### `search_vault(query, scope=None, limit=10, mode="knowledge")`

Searches Vault-derived indexes and returns ranked, evidence-linked results.
The optional `scope` is a `QueryScope`. Without it, search uses the Vaults
linked to the `cwd` project (see Search Scope). Results carry `vault_name` and
`vault_role`. `include_retired` adds retired pages with their retire reason.
`since` and `until` (YYYY-MM-DD) put results in that date range first.

This MCP tool uses the same search service as `vg search`:

```bash
vg search "GraphRAG"
vg search --vault-id main "GraphRAG"
vg search --all-vaults "GraphRAG"
vg search --when "last week" "GraphRAG"
```

Search combines keyword and vector candidates, ranks by document, and can rerank
when `vg reranker use` turned reranking on. Graph candidates join only with
`include_graph`. Each result is an evidence chunk resolved through
`MetadataStore`. The groups below are rendering views over chunk evidence, not
separate retrieval identities.

Expected rendering groups:

- matching documents
- matching wiki pages
- matching sources
- matching chunks
- matching entities after graph indexing exists
- warnings for stale or missing evidence

Each normal result preserves `vault_id`, `document_id`, `chunk_id`, path,
section or anchor, retrieval signals, result warnings, and store revision
metadata. Query-wide degraded conditions, such as vector search unavailable,
appear as top-level warnings.

### `ask_vault(question, mode="evidence-first", scope=None)`

Answers a natural-language question with cited evidence.

The default mode prefers inspectable evidence over fluent unsupported synthesis.
The optional `scope` is a `QueryScope`. Without it, the Vaults linked to the
`cwd` project are used (see Search Scope).

Expected response fields:

- `answer_id`
- `question`
- `scope`
- `answer`
- `answer_status`: `supported`, `partial`, or `insufficient_evidence`
- `claims`
- `evidence`
- `reasoning_trace`
- `warnings`
- `suggested_follow_up`
- `generated_at`

`ask_vault` does not own memory storage. It composes existing read-only
services and returns a cited answer plus reasoning trace. If a later LLM-backed
composer is added, it must sit behind the same answer contract and pass the same
citation guard.

### `find_related(target, scope=None, depth=1, kinds=None)`

Finds related entities through graph traversal, wiki links, decision maps,
timeline maps, or hybrid retrieval.

The response should distinguish stated, inferred, contested, and deprecated
relationships. Cross-Vault traversal requires explicit `vault_ids` in
`QueryScope`.

### `get_decision_trace(decision_or_topic, scope=None)`

Returns a decision trace for a decision ID, topic, or search phrase.

The response should include:

- decision
- context
- alternatives
- tradeoffs
- evidence
- related documents
- related follow-up questions
- revisit conditions

### `build_context_pack(goal, scope=None, max_tokens=None)`

Builds a structured brief for a human or agent.

Required fields:

- `goal`
- `context_pack_schema_version`
- `pack_id`
- `scope`
- `vaults`
- `vault_revisions`
- `backend`
- `store_revisions`
- `retrieval_policy_version`
- `budget`
- `current_state`
- `relevant_pages`
- `relevant_sources`
- `decisions`
- `constraints`
- `open_questions`
- `warnings`
- `evidence`
- `generated_at`

### `summarize_project_memory(scope=None, limit=10)`

Summarizes the current project memory projection.

The response should include:

- current goal
- decision highlights with evidence
- recent-change handoff to `get_recent_changes`
- open issues
- next likely priorities
- evidence links
- warnings or stale areas

### `get_open_questions(scope=None, limit=20)`

Returns unresolved questions, incomplete follow-ups, missing evidence warnings,
or items that should be revisited.

### `get_recent_changes(since=None, scope=None, limit=20)`

Returns recent indexed document snapshot and projection changes from
Vault-derived metadata and revision state.

The response should identify whether each item is an indexed document snapshot
change, an indexed projection change, or a warning. `limit` defaults to `20`,
is validated as `1..50`, and applies per Vault group.

### `explain_result(result_id)`

Explains why a search, answer, context-pack item, or graph result was returned.

The explanation should include retrieval reason, evidence path, relationship
status, confidence, scores when available, and warnings.

### `check_index_status(scope=None)`

Reports index and backend status for agents. `scope=None` uses the active
Vault; explicit scope selects one or more Vaults.

The response should include backend name, schema version, index revision,
freshness, projection cache status, and health warnings.

## MCP Prompts

Vault Graph provides prompts for repeatable agent workflows.

Initial prompts:

- `generate_codex_brief`
- `prepare_implementation_context`
- `review_architecture_decision`
- `summarize_feature_history`
- `analyze_project_risk`
- `prepare_wiki_update_context`
- `trace_decision_history`
- `curate_memory`: the steps for a memory cleanup with `list_memory_candidates`
  and the memory write tools

Prompts must instruct agents to treat Vault Graph output as working context.
Durable publication still runs through Vault's own commands.

## Context Pack Output

A context pack is a structured artifact generated from Vault Graph retrieval.
JSON is canonical. Markdown is a rendering view over the same JSON payload.

Minimum JSON shape:

```json
{
  "context_pack_schema_version": "context-pack-v1",
  "pack_id": "sha256-of-canonical-pack-identity",
  "goal": "Implement GraphRAG MVP",
  "scope": {
    "requested": {
      "vault_ids": ["main"],
      "content_scopes": ["wiki", "docs"],
      "include_cross_vault": false
    },
    "actual_scopes": [
      {
        "vault_ids": ["main"],
        "content_scopes": ["wiki", "docs"],
        "include_cross_vault": false,
        "scope_key": "main:wiki,docs:local"
      }
    ]
  },
  "vaults": [
    {
      "vault_id": "main",
      "display_name": "Main Vault"
    }
  ],
  "vault_revisions": [
    {
      "vault_id": "main",
      "revision": "git-sha-or-file-snapshot-id",
      "revision_kind": "git"
    }
  ],
  "backend": {
    "metadata_store": {
      "name": "sqlite",
      "used": true
    },
    "keyword_index": {
      "name": "sqlite-fts5",
      "used": true
    },
    "vector_store": {
      "name": "chroma",
      "used": true
    },
    "graph_store": {
      "name": null,
      "used": false
    },
    "graph_projection": {
      "name": null,
      "used": false
    }
  },
  "retrieval_policy_version": "retrieval-policy-v1",
  "budget": {
    "max_tokens": 8000,
    "max_evidence_items": 24,
    "max_excerpt_tokens": 320,
    "used_tokens": 0,
    "omitted_items": 0
  },
  "store_revisions": [
    {
      "kind": "metadata",
      "revision": "metadata-revision-id",
      "vault_id": "main",
      "scope_key": "main:wiki,docs:local"
    },
    {
      "kind": "keyword",
      "revision": "keyword-revision-id",
      "vault_id": "main",
      "scope_key": "main:wiki,docs:local"
    },
    {
      "kind": "vector",
      "revision": "vector-revision-id",
      "vault_id": "main",
      "scope_key": "main:wiki,docs:local"
    }
  ],
  "generated_at": "2026-06-04T00:00:00+09:00",
  "current_state": [],
  "relevant_pages": [],
  "relevant_sources": [],
  "decisions": [],
  "constraints": [],
  "open_questions": [],
  "warnings": [],
  "evidence": []
}
```

## Optional UI Features

The optional UI can expose the same capabilities visually.

Planned views:

- Timeline and Health View
- Decision Explorer
- Agent Workspace

These views should not create a second source of truth. They should display
Vault-derived context, evidence, warnings, and durable follow-up suggestions.
Local HTTP serving remains a separate adapter task and is not required to define
the Phase 7B and 7C view contracts. If the UI later surfaces ask results, it
must call `AnswerService` and render the existing answer, evidence, warnings,
and claim-status contract instead of creating an independent answer engine.

## User-Visible Guarantees

Vault Graph should preserve these guarantees for every user-facing feature:

- no direct edits to Vault files: every Vault change runs a Vault command
- local-first operation without mandatory hosted services
- evidence-first responses
- clear separation between stated facts and inferred links
- visible warnings for stale, missing, contested, or deprecated material
- reproducible indexes that can be deleted and rebuilt from Vault
- Vault-scoped identity so registered Vaults with matching relative paths do not
  collide
- explicit backend health and index freshness status
- durable knowledge publication only through Vault
