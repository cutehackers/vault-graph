## id

4

## title

Update README, ARCHITECTURE, DECISIONS, SPEC and TODO for embedding model selection

## goal

The user can learn about this feature and manage it from the README alone: the recommended model, the alternatives, the model folder, how to switch, and how search behaves during re-indexing. This serves Intent 1 and Intent 3.

## files

- `README.md`
- `docs/ARCHITECTURE.md`
- `docs/DECISIONS.md`
- `docs/SPEC.md`
- `docs/TODO.md`
- `tests/test_readme_onboarding_contract.py`

## blockers

none

## acceptance

- A-18
- A-19

## checks

- `uv run --python 3.12 pytest -q tests/test_readme_onboarding_contract.py`
- `rg -n 'vg embedding' README.md docs/ARCHITECTURE.md`

## done-when

- [ ] README has an "Embedding model" section that presents arctic-l first as the recommended model, followed by a short table of the two alternatives. The section covers the folder, `list`/`use`, keyword-only results until re-indexing finishes, first re-index time and storage growth, and old-collection cleanup. It also gives the install order and adds both commands to the "Common Commands" table.
- [ ] The task reads the code to check whether a running MCP server reads the settings file again when it reopens (spec 7.6). If it does not, README tells users to restart the MCP server after switching models.
- [ ] ARCHITECTURE §4 describes `vg embedding use` and the cleanup before publish, and §2 gives the preset and settings-file locations.
- [ ] DECISIONS has a new decision that replaces the 2026-06-08 MiniLM decision without deleting it.
- [ ] SPEC.md :84 and :366 and TODO.md :54 now say the model was chosen by a person and the measurement-1 comparison is still open.
- [ ] The existing check at `test_readme_onboarding_contract.py:26` still passes.
