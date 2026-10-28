# Task 2: Add `tests/verify_release_dist.py` to check the built `dist/` before upload

## id

2

## title

Add `tests/verify_release_dist.py` to check the built `dist/` before upload

## goal

Before any upload or Release step, the workflows can reject a `dist/` that contains `nolemy_*` files, lacks a module, or requires `nolemy-*`. This keeps the "only `vault-graph` on PyPI" promise (Intent 2, 결정2, 결정6).

## files

- `tests/verify_release_dist.py` (new)

## blockers

- 1

## acceptance

- A-3
- A-4
- A-5

## checks

- `rm -rf dist && uv build && uv run --python 3.12 python tests/verify_release_dist.py dist`
- `uv build --wheel dist/vault_graph-*.tar.gz --out-dir <scratch dir>`, then compare the file lists of the two wheels from `unzip -Z1`
- A-5 negative cases, run against copies of `dist/` in a scratch dir. Each must exit with a non-zero code.
  - (a) add a `nolemy_*` wheel
  - (b) remove one module from the wheel
  - (c) add a `Requires-Dist: nolemy-...` line to METADATA
- `uv run --python 3.12 ruff check tests`
- `uv run --python 3.12 mypy src tests packages/text-embeddings/src packages/vector-search/src packages/vector-index/src`

## done-when

- [ ] `def main(dist_dir: Path) -> None` exists, and `python tests/verify_release_dist.py dist` runs it.
- [ ] It checks the 4 rules of spec 4.2: exactly 1 wheel and 1 sdist of `vault_graph` at the root `pyproject.toml` version, with no `nolemy_*` files; the wheel contains `vault_graph/` and the 5 module `__init__.py` files; METADATA has no `nolemy-` requirement; the sdist contains the 5 `packages/<dir>/src/<module>/__init__.py` files.
- [ ] Every failure message names the missing or unexpected item.
- [ ] The script passes on the real `uv build` output.
- [ ] The wheel rebuilt from the sdist has the same file list as the original wheel (A-4).
- [ ] Negative cases (a), (b) and (c) each exit non-zero. The commands and their output are saved for the PR description.
