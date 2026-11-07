# Publishing

## Release Quick Flow

1. Open a release candidate PR with the version bump:
   `./publish.sh -v 0.5.0`
   Run this from a clean `main` checkout or release worktree.
2. Review and merge the release candidate PR into `main`.
3. In GitHub Actions, run `release` manually:
   - `version`: `0.5.0`
   - `target_ref`: `main`
   - `release_notes`: leave empty for generated notes, or write a manual override
4. Confirm the GitHub Release `v0.5.0` and its tag exist.
5. Verify the tagged install:

```bash
uv tool install --force --python 3.12 git+https://github.com/cutehackers/vault-graph.git@v0.5.0
vg --help
vg setup --help
vg ask --help
```

## Safety Model

- Pull requests and pushes to `main` run checks only.
- Only the manual `release` workflow creates tags and GitHub Releases.
- The tag is created only after every check in the `release` workflow passes.
  If any check fails, no tag and no Release are created.
- The workflow stops if the tag already exists on the remote.
- The workflow stops if the target commit is not on `main`.
- The workflow uses no API tokens or GitHub secrets beyond the default
  `GITHUB_TOKEN`.

## Install Channels

- `scripts/install.sh` (the README install command) installs the newest
  `vX.Y.Z` tag, read with `git ls-remote --tags`, so a new release reaches new
  installs as soon as its tag exists. `VAULT_GRAPH_REF` picks another tag or a
  branch. The command then runs the vault-builder install command with
  `VAULT_GRAPH_BIN` set to the installed `vg`, and runs `vg setup`.
- `git+https://github.com/cutehackers/vault-graph.git@vX.Y.Z` installs a
  released version.
- `git+https://github.com/cutehackers/vault-graph.git` without a ref installs
  `main`. No install command uses this form.
- vault-builder does not install vault-graph.
- The `vault-graph` package on PyPI stopped at 0.2.1 and is no longer updated.

## What The Release Builds

The GitHub Release has no attached files. The `release` workflow still builds
with `uv build` and runs `tests/verify_release_dist.py dist`, because a git
install builds the same wheel from the same source.

The `vault-graph` wheel bundles the five repository modules (`graph_search`,
`graph_document`, `text_embeddings`, `vector_search`, `vector_index`) and
declares their external dependencies directly, so it does not require any
`nolemy-*` distribution.

The `nolemy-*` module wheels are built only for checks in the `release`
workflow (`tests/verify_graph_module_wheels.py`). Pull request CI runs only
lint, type check and tests. See the 2026-10-28 entry in
[DECISIONS.md](DECISIONS.md).

## Required GitHub Settings

- protect `main`
- require CI before merge
- keep Actions permissions at read-only by default

Anyone with write access to the repository can run the `release` workflow.

## Release Verification

Before running the `release` workflow, run:

```bash
uv run --python 3.12 ruff check src tests
uv run --python 3.12 mypy src tests
uv run --python 3.12 pytest -q

rm -rf dist
uv build
```

## Non-Goals

- Do not release on plain `push` or on tag push.
- Do not push release tags from a local machine.
- Do not attach files to GitHub Releases.
- Do not upload to PyPI or TestPyPI.
- Do not create or change Vault content during a release.
