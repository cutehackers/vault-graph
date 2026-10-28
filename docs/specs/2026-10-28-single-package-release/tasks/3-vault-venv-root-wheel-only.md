# Task 3: Change `verify_graph_module_wheels.py` so the vault venv installs only the root wheel

## id

3

## title

Change `verify_graph_module_wheels.py` so the vault venv installs only the root wheel

## goal

The end-to-end smoke test runs the same install that users get from PyPI: one `vault-graph` wheel and no `nolemy-*` packages. The per-module wheel smokes stay, so module boundaries are still enforced (Intent 1 and 2, 결정3, 결정8).

## files

- `tests/verify_graph_module_wheels.py`

## blockers

- 1

## acceptance

- A-6

## checks

- `uv run --python 3.12 python tests/verify_graph_module_wheels.py`
- `grep -n install_from_local_simple_index tests/verify_graph_module_wheels.py` (must find nothing)
- `uv run --python 3.12 ruff check tests`
- `uv run --python 3.12 mypy src tests packages/text-embeddings/src packages/vector-search/src packages/vector-index/src`

## done-when

- [ ] The build of all 6 wheels, the per-wheel name, version and `Requires-Dist` checks, and the per-module venv smokes are kept.
- [ ] The vault venv installs only the root wheel file and gets external dependencies from the default index.
- [ ] The vault venv confirms that no `nolemy-*` package is installed, that all 5 modules import, and that each module's `__init__.py` appears in `importlib.metadata.files("vault-graph")`.
- [ ] The existing `VAULT_SMOKE` and `vg --help` checks still pass.
- [ ] `install_from_local_simple_index` is removed.
- [ ] The script exits 0.
