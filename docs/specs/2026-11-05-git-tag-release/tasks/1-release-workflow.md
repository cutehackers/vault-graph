# Task 1: release workflow, publish.sh, PUBLISHING.md, contract test

## id

1

## title

Replace the PyPI workflows with a single `release` workflow and update `publish.sh`, `PUBLISHING.md` and the contract test

## goal

After this task, running the `release` workflow once on a `main` commit runs every check, builds and checks the wheel, and then creates tag `vX.Y.Z` and a published Release with no attached files. Nothing is uploaded to PyPI. This serves Intent 1, 2 and 3 and makes Intent 4 (the v0.3.0 release) possible after merge.

## files

- `.github/workflows/release.yml` (new, spec §4.1, includes the `origin/main` ancestor check from 질문1 옵션1)
- `.github/workflows/prepare-release.yml` (delete)
- `.github/workflows/publish-pypi.yml` (delete)
- `.github/workflows/publish-testpypi.yml` (delete)
- `publish.sh` (spec §4.3)
- `docs/PUBLISHING.md` (full rewrite, spec §4.4)
- `tests/test_release_automation_contract.py` (spec §4.8)

## blockers

none

## acceptance

A-1, A-2, A-3, A-4, A-5, A-6, A-7, and A-11 for this task's files

## checks

- `ls .github/workflows/` (expect only `ci.yml` and `release.yml`)
- `grep -riE 'pypi|uv publish|trusted-publishing|id-token|twine' .github/workflows/` (expect no output)
- `grep -iE 'pypi|prepare-release' publish.sh` (expect no output)
- `uv run --python 3.12 --all-packages --all-extras pytest -q tests/test_release_automation_contract.py`
- `uv run --python 3.12 --all-packages --all-extras pytest -q tests packages/*/tests`
- `uv run --python 3.12 ruff check src tests packages`
- `uv run --python 3.12 mypy src tests packages/text-embeddings/src packages/vector-search/src packages/vector-index/src`
- A-6 dry run (put the output in the PR description). Expect `v9.9.9` as the only tag and both lines found:

  ```sh
  T=$(mktemp -d) && for f in pyproject.toml src/vault_graph/__init__.py tests/test_package_import.py tests/test_mcp_server.py docs/PUBLISHING.md; do mkdir -p "$T/$(dirname $f)"; cp "$f" "$T/$f"; done && sed -n "/<<'PY'$/,/^PY$/p" publish.sh | sed '1d;$d' > "$T/sub.py" && (cd "$T" && python3 sub.py 9.9.9) && grep -oE 'v[0-9]+\.[0-9]+\.[0-9]+' "$T/docs/PUBLISHING.md" | sort -u && grep -F '`version`: `9.9.9`' "$T/docs/PUBLISHING.md" && grep -F './publish.sh -v 9.9.9' "$T/docs/PUBLISHING.md"
  ```

- `git diff main -- publish.sh` (the branch name `codex/release-v${VERSION}` and the version files at `publish.sh:84-93,111-117@e764c7a` are unchanged)

## done-when

- [ ] `release.yml` exists with `name: release` and only a `workflow_dispatch` trigger. Its inputs are `version`, `target_ref` (default `main`) and `release_notes` (default empty). Its only permission is `contents: write`, with concurrency group `release-${{ inputs.version }}` and the repository condition.
- [ ] Step order in `release.yml`: version check (format included), remote tag check with `git ls-remote`, `origin/main` ancestor check, Lint, Type check, Test, `verify_graph_module_wheels.py`, `uv build`, `verify_release_dist.py dist`, write `release-notes.md`, then `gh release create`. `gh release create` has no `--draft` and no `dist/*`. There is no `twine`.
- [ ] `prepare-release.yml`, `publish-pypi.yml` and `publish-testpypi.yml` are deleted.
- [ ] In `publish.sh`, line 16 says the script creates no tag and no Release. The third PUBLISHING.md substitution replaces every match. The final message shows the `release` workflow step and the `@v${VERSION}` install command plus `vg --help`. The other substitutions, the branch name and the version file list are unchanged.
- [ ] `docs/PUBLISHING.md` starts with `# Publishing\n\n## Release Quick Flow\n\n`. It has the seven spec §4.4 sections in order. The only numeric tag in it is `v0.3.0`. "Approve the `pypi`", "Trusted Publisher", "TestPyPI Flow" and "PyPI Flow" are gone.
- [ ] The contract test covers spec §4.8 items 1-5, and `test_github_generated_release_notes_are_categorized` is unchanged.
- [ ] The full pytest run, ruff and mypy pass.
- [ ] The A-6 dry-run output is saved for the PR description.
