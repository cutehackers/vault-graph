from __future__ import annotations

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
    assert "uv publish" not in workflow_text
    assert "trusted-publishing" not in workflow_text


def test_publishing_doc_starts_with_release_quick_flow() -> None:
    publishing = Path("docs/PUBLISHING.md").read_text(encoding="utf-8")

    assert publishing.startswith("# Publishing\n\n## Release Quick Flow\n\n")
    assert "In GitHub Actions, run `prepare-release` manually" in publishing[:1000]
    assert "Publish the draft GitHub Release" in publishing[:1000]
    assert "Approve the `pypi` environment deployment" in publishing[:1000]
