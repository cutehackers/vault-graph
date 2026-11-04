## id

5

## title

Add the `vg embedding list` and `vg embedding use` CLI commands

## goal

The user can see the recommended model and the alternatives, then download the chosen model and switch to it with one command. This serves Intent 1 and Intent 3 (easy management, one recommended model).

## files

- `src/vault_graph/interface/cli/embedding_commands.py` (new)
- `src/vault_graph/interface/cli/main.py` (import and `add_typer` only)
- `tests/test_cli_embedding.py` (new)

## blockers

- 2
- 6

## acceptance

- A-8
- A-9
- A-10
- A-17
- A-28
- A-1, A-2 and A-3 as the final full run

## checks

- `uv run --python 3.12 pytest -q tests/test_cli_embedding.py`
- `uv run --python 3.12 ruff check src tests packages`
- `uv run --python 3.12 mypy src tests packages/text-embeddings/src packages/vector-search/src packages/vector-index/src`
- `uv run --python 3.12 --all-packages --all-extras pytest -q tests packages/*/tests`
- `shasum $HOME/.vault-graph/projections/active.json $HOME/.vault-graph/configs/*`, run before and after the task (A-28)

## done-when

- [ ] `use` runs the steps in this order: check the name, check that the folder is outside registered Vaults, download, write the settings file, print the next-step message. On failure it exits non-zero and leaves the settings file bytes unchanged.
- [ ] `use` stores `--models-dir` as an absolute path. Without it, `use` keeps the current folder.
- [ ] `list` shows arctic-l first as recommended and the other two as alternatives, in both text and JSON. It shows the settings path, the folder, whether each model is selected, and whether each is downloaded. It checks downloads only with `local_files_only=True` and writes nothing.
- [ ] If Graph Home has not been initialized, both commands fail with a message to run `vg init`.
- [ ] `vg --help` shows only the new `embedding` group. Every existing command is still there.
- [ ] The full CI checks pass (A-1, A-2, A-3).
