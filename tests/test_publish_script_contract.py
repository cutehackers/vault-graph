from __future__ import annotations

import stat
import tomllib
from pathlib import Path


def test_publish_script_prepares_release_candidate_pr_only() -> None:
    script_path = Path("publish.sh")
    script = script_path.read_text(encoding="utf-8")
    mode = script_path.stat().st_mode

    assert mode & stat.S_IXUSR
    assert "Usage: ./publish.sh -v 0.1.2" in script
    assert "git status --porcelain" in script
    assert "pyproject.toml" in script
    assert "src/vault_graph/__init__.py" in script
    assert "re.sub(r\"\\./publish\\.sh -v " in script
    assert 'uv run --python 3.12 python - "${VERSION}"' in script
    assert not any(line.startswith('python - "${VERSION}"') for line in script.splitlines())
    assert "uv lock" in script
    assert "git commit" in script
    assert "git push" in script
    assert "gh pr create" in script
    assert "uv publish" not in script
    assert "gh release create" not in script


def test_publishing_doc_uses_publish_script_for_release_candidate_pr() -> None:
    publishing = Path("docs/PUBLISHING.md").read_text(encoding="utf-8")
    version = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]

    assert f"./publish.sh -v {version}" in publishing[:1000]
    assert "Open a release candidate PR" in publishing[:1000]
