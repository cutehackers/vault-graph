from __future__ import annotations

import tomllib
from pathlib import Path

import yaml


def test_prepare_release_workflow_creates_draft_release_only() -> None:
    workflow_path = Path(".github/workflows/prepare-release.yml")
    workflow = yaml.safe_load(workflow_path.read_text(encoding="utf-8"))
    workflow_text = workflow_path.read_text(encoding="utf-8")

    assert workflow["name"] == "prepare-release"
    assert "workflow_dispatch" in workflow[True]
    assert workflow["permissions"] == {"contents": "write"}
    assert "gh release create" in workflow_text
    assert "--draft" in workflow_text
    assert "--generate-notes" in workflow_text
    assert "release-notes.md" in workflow_text
    assert "uv publish" not in workflow_text
    assert "trusted-publishing" not in workflow_text


def test_github_generated_release_notes_are_categorized() -> None:
    release_config_path = Path(".github/release.yml")
    release_config = yaml.safe_load(release_config_path.read_text(encoding="utf-8"))

    categories = release_config["changelog"]["categories"]
    category_titles = {category["title"] for category in categories}

    assert "Features" in category_titles
    assert "Fixes" in category_titles
    assert "Documentation" in category_titles
    assert "CI and Release" in category_titles
    assert categories[-1]["labels"] == ["*"]


def test_publishing_doc_starts_with_release_quick_flow() -> None:
    publishing = Path("docs/PUBLISHING.md").read_text(encoding="utf-8")
    version = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]

    assert publishing.startswith("# Publishing\n\n## Release Quick Flow\n\n")
    assert "Open a release candidate PR with the version bump" in publishing[:1000]
    assert f"./publish.sh -v {version}" in publishing[:1000]
    assert f"`{version}`" in publishing[:1000]
    assert "In GitHub Actions, run `prepare-release` manually" in publishing[:1000]
    assert "leave empty for generated notes" in publishing[:1000]
    assert "Publish the draft GitHub Release" in publishing[:1000]
    assert "Approve the `pypi` environment deployment" in publishing[:1000]
