# Changelog

Each release lists its user-visible changes, newest first. Sources: git tags,
commit history, and `docs/PATCH_LOG.md`. Dates are the tag dates.

## v0.7.0 - 2026-11-18

- Added session fact extraction: after each captured session, a background worker extracts dated facts per exchange.
- Added `vg facts on`, `vg facts off`, `vg facts status`, and `vg facts worker`. Extraction is on by default with the `claude` extractor.
- Added the `claude` extractor (logged-in `claude -p`, no tools, no MCP) and the local `llama-server` extractor.
- `vg hook capture` now queues a fact job after a written capture and starts the worker without waiting for it.
- The worker writes facts only through the Vault command `sessions attach-facts` and retries failures after 30 minutes.
- Indexed session facts as search keys that point to the original exchange.
- Added date ranges to search: `since` and `until` on `search_vault`, `ask_vault`, and `build_context_pack`.
- Added `vg search --since`, `--until`, `--when "last week"`, and `--date-strict`.
- Date ranges also match the event dates of extracted facts, and in-range results come first.
- Indexed the start and end time of each session exchange.
- Search folds exchanges of the same session into one result.
- Added optional reranking with `vg reranker use mmarco` and `vg reranker off`.
- Search tool descriptions now explain query form and `mode`, and no longer assume English Vault pages.
- Fixed the `llama-server` extractor to turn off the model's thinking step.

## v0.6.0 - 2026-11-13

- Changed the default embedding model to `arctic-m`. `e5-small` stays as the alternative.
- `remember` accepts `summary` and `aliases` and reports up to 3 similar existing pages.
- The cleanup backlog line in recall shows the median age of waiting items.
- Search folds copies of the same session exchange in one Vault into one result.
- Search attaches the replaced page as evidence for superseded pages.
- A single search no longer reloads the whole index, cutting p95 latency from 32 s to 0.3 s.
- The first session-start catch-up index builds keyword search first, then embeddings.
- Index failures now show in recall output.
- Added `vg doctor`, which prints one fix command per index, model, or MCP problem.
- Added LongMemEval benchmark tools for measuring search recall.
- Fixed indexing so v2 subagent exchanges and continued v2 copies no longer hide v1 main-conversation exchanges.

## v0.5.0 - 2026-11-08

- Added memory cleanup: `list_memory_candidates`, `mark_candidates_reviewed`, and the `curate_memory` prompt.
- Added `supersede_claim`, `restore_memory`, and `import_auto_memory` write tools.
- Limited each cleanup to 10 `inferred` proposals.
- Added `include_retired` to `search_vault` and `vg search`.
- `remember` with kind `project` writes the project brief to `wiki/projects/<project>.md`.
- `remember` records the `cwd` project on the page and adds corrections and rules to `tags`.
- Recall gained a project summary block (brief and open items, decisions, rules) with its own budget.
- Recall shows a cleanup backlog line and a reminder when 5 or more decisions follow the brief.
- Added `vg session export` and a normalized session format, `vg-session-jsonl/1`.
- `vg hook capture` passes the normalized session to the Vault and falls back to the Vault's own format when needed.
- Session files are indexed per exchange, so search returns whole exchanges with their location.
- Wiki pages are indexed as windows plus a page card. Search ranks by document and includes source pages in `knowledge` mode.
- The keyword index weights columns, adds an alias column, and boosts title matches.
- Indexing skips unchanged files, caches embeddings in the Data Home, and only re-embeds changed content.
- Lowered peak memory of a full re-index from 6.85 GB to 4.29 GB.
- Fixed session handling so a resumed session keeps one session id across v1 and v2 files.
- Fixed capture with older Vault hook launchers so session records are not lost.

## v0.4.2 - 2026-11-06

- The install command registers Vaults only. Index them with `vg index --all-vaults`.

## v0.4.1 - 2026-11-05

- The install command checks `vault-builder setup` with a dry run before installing `vg`.
- The install command stops before installing when there is no terminal and no `--yes`.
- Fixed the line order of vault-builder check output.

## v0.4.0 - 2026-11-05

- The install command also installs and sets up vault-builder.
- `vg setup` writes the running `vg` into the MCP entry instead of another `vg` on `PATH`.

## v0.3.0 - 2026-11-05

- Added `vault-map.json` support: find the project of a folder and its linked Vaults.
- Search covers all Vaults linked to the project by default and labels results with `vault_name` and `vault_role`.
- Added `vg hook session-start` for session-start recall with a token budget, plus usage records.
- Pinned memories come first in recall, in their own 400-token block.
- Added `remember`, `update_memory`, and `retire_memory`, which write through the Vault's `publish-draft`.
- `basis: inferred` writes go to the Vault review queue and return `proposed`.
- Added `vg hook capture`, which decides when the Vault's `sessions capture` runs.
- A published write starts a background index of that Vault.
- Write tools use only the Vaults linked to the `cwd` project.
- `vg status` shows `default_write_vault`.
- Default search leaves out retired pages.
- Added `vg setup --agent claude` to register the MCP server in Claude Code.
- Added `vg mcp unregister`, hook status warnings in `vg setup`, and a one-command install.
- Added `vg embedding list` and `vg embedding use`. The default model became `e5-small`.
- Releases are git tags and GitHub Releases. PyPI publishing stopped.
- Session start now updates changed files within a time limit and catches up embeddings in a detached `vg index`.
- Index generations publish under a cross-process lock, and only the current and previous generations are kept.
- Fixed: one file with bad frontmatter no longer stops setup or indexing.
- Fixed: `vault-map.json` is found through `CLAUDE_CONFIG_DIR`.
- Fixed: `vg watch` publishes nothing when nothing changed.
- Fixed: MCP read tools follow new index generations.

## v0.2.1 - 2026-10-29

- The five modules ship inside the `vault-graph` wheel as one package.

## v0.2.0 - 2026-10-28

- Moved indexing to block-window chunking and added hierarchical evidence context to search results.
- Split vector and graph code into five reusable packages (`nolemy-*`).
- Added the document graph backend, selected with `vg index --graph-backend document`.

## v0.1.4 - 2026-08-05

- Added the code index for Python and Dart: `vg code repository add`, `vg code index`, and `vg code` queries.
- Added `vg project bind` and `vg project bindings`.
- Added the `explore_project` MCP tool.
- Added `vg harness guidance preview`, `install`, and `remove`.
- Added `vg projection-audit` and search modes (`knowledge`, `evidence`, `operating`, `audit`, `all`).
- Projection bundles publish complete, and reads stop on Data Home or generation drift.
- Older pre-release Data Home layouts are detected and left untouched instead of migrated.

## v0.1.3 - 2026-07-14

- Added `vg setup --mcp` with Codex config registration and backups.

## v0.1.2 - 2026-07-14

- Release process changes only.

## v0.1.1 - 2026-07-14

- Documentation changes only.

## v0.1.0 - 2026-07-03

- First release.
- Metadata, keyword, vector, and graph indexing of Vaults: `vg init`, `vg vault`, `vg index`, `vg watch`, `vg status`.
- Evidence-first search: `vg search`, with opt-in graph signals.
- Graph commands: `vg related` and `vg decision-trace`.
- Context packs: `vg context`.
- Evidence-first answers: `vg ask`.
- Local stdio MCP server with read-only resources, tools, prompts, and result explanations.
- Project memory views: summary, open questions, and recent changes.
- `vg setup` for first-run onboarding.
