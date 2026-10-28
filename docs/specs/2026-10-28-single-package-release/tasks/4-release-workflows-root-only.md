# Task 4: Release workflows build only the root package and run `verify_release_dist.py` before upload

## id

4

## title

Release workflows build only the root package and run `verify_release_dist.py` before upload

## goal

`publish-pypi`, `publish-testpypi` and `prepare-release` build and upload only the `vault-graph` wheel and sdist, after checking them. The CI `verify` job catches the same problems on every PR. This removes the step that failed in run 40661532945 (Intent 2).

## files

Sensitive path (`.github/**`).

- `.github/workflows/publish-pypi.yml`
- `.github/workflows/publish-testpypi.yml`
- `.github/workflows/prepare-release.yml`
- `.github/workflows/ci.yml`

## blockers

- 2

## acceptance

- A-8
- A-9

## checks

- `grep -nE -- 'uv build --all-packages|dist/nolemy_' .github/workflows/publish-pypi.yml .github/workflows/publish-testpypi.yml .github/workflows/prepare-release.yml` (must find nothing)
- `grep -n -B2 'verify_release_dist.py dist' .github/workflows/*.yml` (the step must follow `Check distributions` and come before upload or Release creation)
- `git diff main -- .github/workflows/ci.yml` (only an addition to the `verify` job)
- `uv run --python 3.12 --with pyyaml python -c "import yaml,sys;[yaml.safe_load(open(f)) for f in sys.argv[1:]]" .github/workflows/*.yml`

## done-when

- [ ] In `publish-pypi.yml` and `publish-testpypi.yml`, `uv build --all-packages` is replaced by `uv build`, a `verify_release_dist.py dist` step follows `Check distributions`, and the `dist/nolemy_*` upload step is deleted.
- [ ] `prepare-release.yml` uses `uv build` and runs the verify step before the draft Release is created.
- [ ] The `ci.yml` `verify` job has the verify step after `Check distributions`. The `graph-search-runtime-compatibility` and `independent-modules` jobs are unchanged.
- [ ] The names and commands of existing `Verify ...` steps are unchanged.
- [ ] All PR CI jobs pass (A-9 is confirmed on the PR).
