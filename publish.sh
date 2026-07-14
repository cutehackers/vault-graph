#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage: ./publish.sh -v 0.1.2

Prepare a release candidate PR:
  - create or reuse codex/release-v<VERSION>
  - update package version files
  - refresh uv.lock
  - commit the version bump
  - push the branch
  - open a GitHub PR

This script does not publish to PyPI and does not create a GitHub Release.
EOF
}

VERSION=""

while getopts ":v:h" opt; do
  case "${opt}" in
    v)
      VERSION="${OPTARG}"
      ;;
    h)
      usage
      exit 0
      ;;
    *)
      usage
      exit 2
      ;;
  esac
done

if [ -z "${VERSION}" ]; then
  usage
  exit 2
fi

if [[ ! "${VERSION}" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
  echo "Version must be SemVer without a v prefix, for example 0.1.2." >&2
  exit 2
fi

if [ -n "$(git status --porcelain)" ]; then
  echo "Working tree is dirty. Commit, stash, or discard changes before preparing a release PR." >&2
  exit 1
fi

if ! command -v uv >/dev/null 2>&1; then
  echo "uv is required." >&2
  exit 1
fi

if ! command -v gh >/dev/null 2>&1; then
  echo "GitHub CLI is required." >&2
  exit 1
fi

ROOT="$(git rev-parse --show-toplevel)"
cd "${ROOT}"

BRANCH="codex/release-v${VERSION}"
CURRENT_BRANCH="$(git branch --show-current)"

if [ "${CURRENT_BRANCH}" = "main" ]; then
  git switch -c "${BRANCH}"
else
  BRANCH="${CURRENT_BRANCH}"
fi

uv run --python 3.12 python - "${VERSION}" <<'PY'
from __future__ import annotations

import re
import sys
from pathlib import Path

version = sys.argv[1]

replacements = {
    Path("pyproject.toml"): (r'version = "[^"]+"', f'version = "{version}"'),
    Path("src/vault_graph/__init__.py"): (r'__version__ = "[^"]+"', f'__version__ = "{version}"'),
    Path("tests/test_package_import.py"): (r'assert __version__ == "[^"]+"', f'assert __version__ == "{version}"'),
    Path("tests/test_mcp_server.py"): (
        r'assert registered\.server_version == "[^"]+"',
        f'assert registered.server_version == "{version}"',
    ),
    Path("docs/PUBLISHING.md"): (r"`version`: `[^`]+`", f"`version`: `{version}`"),
}

for path, (pattern, replacement) in replacements.items():
    text = path.read_text(encoding="utf-8")
    next_text, count = re.subn(pattern, replacement, text, count=1)
    if count != 1:
        raise SystemExit(f"Failed to update {path}")
    path.write_text(next_text, encoding="utf-8")

publishing_path = Path("docs/PUBLISHING.md")
publishing = publishing_path.read_text(encoding="utf-8")
publishing = re.sub(r"\./publish\.sh -v [0-9]+\.[0-9]+\.[0-9]+", f"./publish.sh -v {version}", publishing, count=1)
publishing = re.sub(r"v[0-9]+\.[0-9]+\.[0-9]+", f"v{version}", publishing, count=1)
publishing_path.write_text(publishing, encoding="utf-8")
PY

uv lock

git add \
  pyproject.toml \
  src/vault_graph/__init__.py \
  tests/test_package_import.py \
  tests/test_mcp_server.py \
  docs/PUBLISHING.md \
  uv.lock

git commit -m "chore: prepare release v${VERSION}"
git push -u origin "${BRANCH}"

gh pr create \
  --base main \
  --head "${BRANCH}" \
  --title "Release v${VERSION}" \
  --body "Prepare vault-graph v${VERSION} release candidate."

cat <<EOF
Release candidate PR is ready for v${VERSION}.

After merge:
1. Run the prepare-release workflow with version ${VERSION}.
2. Review and publish the generated draft GitHub Release.
3. Approve the pypi environment deployment.
EOF
