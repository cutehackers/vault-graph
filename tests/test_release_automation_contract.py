from __future__ import annotations

import re
import tomllib
from pathlib import Path

import yaml

WORKFLOWS_DIR = Path(".github/workflows")
RELEASE_WORKFLOW = WORKFLOWS_DIR / "release.yml"


def _package_version() -> str:
    version: str = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]
    return version


def test_release_workflow_creates_published_release_without_assets() -> None:
    workflow = yaml.safe_load(RELEASE_WORKFLOW.read_text(encoding="utf-8"))
    workflow_text = RELEASE_WORKFLOW.read_text(encoding="utf-8")

    assert workflow["name"] == "release"
    triggers = workflow[True]
    assert list(triggers) == ["workflow_dispatch"]
    inputs = triggers["workflow_dispatch"]["inputs"]
    assert set(inputs) == {"version", "target_ref", "release_notes"}
    assert inputs["target_ref"]["default"] == "main"
    assert inputs["release_notes"]["default"] == ""
    assert workflow["permissions"] == {"contents": "write"}
    assert workflow["concurrency"]["group"] == "release-${{ inputs.version }}"

    for required in (
        "gh release create",
        "--generate-notes",
        "release-notes.md",
        "git ls-remote",
        "verify_release_dist.py",
        "verify_graph_module_wheels.py",
    ):
        assert required in workflow_text, required
    for forbidden in ("--draft", "dist/*", "uv publish", "trusted-publishing", "id-token", "twine"):
        assert forbidden not in workflow_text, forbidden


def test_release_workflow_checks_run_before_release_creation() -> None:
    workflow = yaml.safe_load(RELEASE_WORKFLOW.read_text(encoding="utf-8"))
    (job,) = workflow["jobs"].values()
    assert job["if"] == "github.repository == 'cutehackers/vault-graph'"

    step_texts = [f"{step.get('name', '')}\n{step.get('run', '')}" for step in job["steps"]]

    def first_index(marker: str) -> int:
        for index, text in enumerate(step_texts):
            if marker in text:
                return index
        raise AssertionError(f"no step contains {marker!r}")

    ordered_markers = [
        "RELEASE_VERSION",
        "git ls-remote",
        "merge-base --is-ancestor",
        "ruff check",
        "mypy",
        "pytest",
        "verify_graph_module_wheels.py",
        "uv build",
        "verify_release_dist.py dist",
        "release-notes.md",
        "gh release create",
    ]
    indexes = [first_index(marker) for marker in ordered_markers]
    assert indexes == sorted(indexes), dict(zip(ordered_markers, indexes, strict=True))


def test_pypi_workflows_are_removed() -> None:
    for name in ("prepare-release.yml", "publish-pypi.yml", "publish-testpypi.yml"):
        assert not (WORKFLOWS_DIR / name).exists(), name
    for path in WORKFLOWS_DIR.iterdir():
        assert "pypi" not in path.read_text(encoding="utf-8").lower(), path


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
    version = _package_version()

    assert publishing.startswith("# Publishing\n\n## Release Quick Flow\n\n")
    assert "Open a release candidate PR with the version bump" in publishing[:1000]
    assert f"./publish.sh -v {version}" in publishing[:1000]
    assert f"`{version}`" in publishing[:1000]
    assert "In GitHub Actions, run `release` manually" in publishing[:1000]
    assert "leave empty for generated notes" in publishing[:1000]
    assert f"git+https://github.com/cutehackers/vault-graph.git@v{version}" in publishing[:1000]


def test_publishing_doc_numeric_tags_are_current_version() -> None:
    publishing = Path("docs/PUBLISHING.md").read_text(encoding="utf-8")
    version = _package_version()

    tags = set(re.findall(r"v[0-9]+\.[0-9]+\.[0-9]+", publishing))
    assert tags == {f"v{version}"}


def test_publish_script_points_to_release_workflow() -> None:
    script = Path("publish.sh").read_text(encoding="utf-8")

    assert "pypi" not in script.lower()
    assert "prepare-release" not in script
    assert "release workflow" in script
    assert "git+https://github.com/cutehackers/vault-graph.git@v${VERSION}" in script
