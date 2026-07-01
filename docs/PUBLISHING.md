# Publishing

Vault Graph uses GitHub Actions and PyPI Trusted Publishing for public package
distribution. Do not publish release artifacts from a local machine.

## Safety Model

- Pull requests run verification only.
- Pushes to `main` run verification only.
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
3. Create and publish a GitHub Release such as `v0.1.0`.
4. Wait for the `publish-pypi` workflow to reach the `pypi` environment gate.
5. Review the release artifact, version, README, and workflow run.
6. Approve the `pypi` environment.
7. Verify public install:

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
