# Publishing

## Release Quick Flow

1. Open a release candidate PR that bumps the package version, for example
   `0.1.2`.
2. Review and merge the release candidate PR into `main`.
3. In GitHub Actions, run `prepare-release` manually:
   - `version`: `0.1.2`
   - `target_ref`: `main`
   - `release_notes`: leave empty for generated notes, or write a manual override
4. Open the generated draft GitHub Release `v0.1.2`.
5. Review the release notes and attached `dist/*` artifacts.
6. Publish the draft GitHub Release.
7. Open the `publish-pypi` workflow run.
8. Approve the `pypi` environment deployment.
9. After the workflow succeeds, verify the public install:

```bash
uv tool uninstall vault-graph || true
uv tool install vault-graph
vg --help
vg setup --help
vg ask --help
```

Vault Graph uses GitHub Actions and PyPI Trusted Publishing for public package
distribution. Do not publish release artifacts from a local machine.

## Safety Model

- Pull requests run verification only.
- Pushes to `main` run verification only.
- Release preparation is manual and creates a draft GitHub Release only.
- Empty release notes use GitHub generated release notes for the draft.
- TestPyPI publishing is manual through `workflow_dispatch`.
- PyPI publishing runs only when a GitHub Release is published.
- PyPI upload jobs require GitHub environment approval.
- PyPI and TestPyPI use OIDC Trusted Publishing, not API tokens or GitHub
  secrets.

## Required GitHub Settings

Create these environments in the GitHub repository:

- `testpypi`
- `pypi`

For `pypi`, configure required reviewers. This keeps the upload job paused after
a GitHub Release is published until an authorized maintainer approves it.

Recommended repository protections:

- protect `main`
- require CI before merge
- restrict who can publish releases
- keep Actions permissions at read-only by default

## Required PyPI Settings

Register Trusted Publishers for both TestPyPI and PyPI.

TestPyPI:

- project name: `vault-graph`
- owner: `cutehackers`
- repository: `vault-graph`
- workflow: `publish-testpypi.yml`
- environment: `testpypi`

PyPI:

- project name: `vault-graph`
- owner: `cutehackers`
- repository: `vault-graph`
- workflow: `publish-pypi.yml`
- environment: `pypi`

If the project does not exist yet, use PyPI's pending publisher flow.

## Release Verification

Before publishing a release, run:

```bash
uv run --python 3.12 ruff check src tests
uv run --python 3.12 mypy src tests
uv run --python 3.12 pytest -q

rm -rf dist
uv build
uv run --python 3.12 --with twine python -m twine check dist/*
```

## TestPyPI Flow

Use TestPyPI before the first public release and before risky packaging changes.
Use a version that has not already been uploaded to TestPyPI.

1. Push the release candidate commit to `main`.
2. Confirm the `ci` workflow passed.
3. Run the `publish-testpypi` workflow manually.
4. Approve the `testpypi` environment if approval is enabled.
5. Install and smoke-test the package from TestPyPI.

TestPyPI does not mirror all dependencies. If dependency resolution fails during
manual installation, use PyPI as an extra index for dependencies.

## PyPI Flow

1. Confirm TestPyPI validation is acceptable.
2. Confirm README installation instructions match the public PyPI state.
3. Run the `prepare-release` workflow to create a draft GitHub Release such as
   `vX.Y.Z`.
4. Review and publish the draft GitHub Release.
5. Wait for the `publish-pypi` workflow to reach the `pypi` environment gate.
6. Review the release artifact, version, README, and workflow run.
7. Approve the `pypi` environment.
8. Verify public install:

```bash
uv tool uninstall vault-graph || true
uv tool install vault-graph
vg --help
vg setup --help
vg ask --help
```

## Non-Goals

- Do not publish on plain `push`.
- Do not publish on tag push alone.
- Do not store PyPI API tokens in GitHub Secrets.
- Do not rebuild or mutate Vault content during package publication.
