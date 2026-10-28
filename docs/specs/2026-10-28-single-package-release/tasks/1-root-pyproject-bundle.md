# Task 1: Root pyproject ships the 5 modules inside the `vault-graph` wheel, plus a dependency alignment test

## id

1

## title

Root pyproject ships the 5 modules inside the `vault-graph` wheel, plus a dependency alignment test

## goal

The root wheel contains all 5 module packages and requires only external dependencies, never `nolemy-*`. `uv sync` still installs the modules as editable for development. This lets PyPI receive `vault-graph` alone while modules stay strictly separated in development (Intent 1 and 2). A pytest then catches a module dependency that the root forgot to declare.

## files

- `pyproject.toml`
- `uv.lock`
- `tests/test_root_dependency_alignment.py` (new)

## blockers

none

## acceptance

- A-1
- A-2
- A-7
- A-10 applies to this task's diff.

## checks

- `uv lock --check`
- `uv sync --python 3.12`
- `uv run --python 3.12 pytest -q tests/test_root_dependency_alignment.py`
- `uv run --python 3.12 ruff check src tests packages`
- `uv run --python 3.12 mypy src tests packages/text-embeddings/src packages/vector-search/src packages/vector-index/src`
- `uv run --python 3.12 --all-packages --all-extras pytest -q tests packages/*/tests`
- `rm -rf dist && uv build && unzip -l dist/vault_graph-*.whl | grep -E '(vault_graph/|graph_search/__init__|graph_document/__init__|text_embeddings/__init__|vector_search/__init__|vector_index/__init__)'`
- `git diff --stat main -- packages src publish.sh` (must be empty)

## done-when

- [ ] `[project].dependencies` has no `nolemy-*` entries. It contains `rustworkx>=0.17,<0.18`, `fastembed>=0.8,<1` and `chromadb>=1.5.9,<2`.
- [ ] `[dependency-groups].dev` lists all 5 `nolemy-*` packages. `[tool.uv.workspace]` and `[tool.uv.sources]` are the same as at `2bc19ca`.
- [ ] `[tool.hatch.build.targets.wheel].packages` lists the 5 `packages/<dir>/src/<module>` paths. No sdist `include` is added (결정10).
- [ ] `uv.lock` is regenerated and `uv lock --check` passes.
- [ ] `tests/test_root_dependency_alignment.py` checks the 4 rules of spec 4.5 using `packaging.requirements.Requirement`. It has at least one test proving that a dependency present only on the module side is reported as a failure.
- [ ] The Lint, Type check and Test commands of the CI `verify` job pass after a fresh `uv sync`.
- [ ] `git diff --stat main -- packages src publish.sh` is empty.
