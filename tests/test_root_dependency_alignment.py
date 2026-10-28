"""The root `vault-graph` wheel bundles the 5 modules, so it must declare their external dependencies itself."""

import tomllib
from pathlib import Path
from typing import Any

from packaging.requirements import Requirement

REPO_ROOT = Path(__file__).resolve().parents[1]

# Module directory -> extras the root used to enable when it depended on `nolemy-*`.
MODULE_EXTRAS: dict[str, tuple[str, ...]] = {
    "graph-search": (),
    "graph-document": ("search",),
    "text-embeddings": ("fastembed",),
    "vector-search": ("chroma",),
    "vector-index": (),
}

INTERNAL_PREFIX = "nolemy-"
MODULE_DISTRIBUTIONS = {f"{INTERNAL_PREFIX}{name}" for name in MODULE_EXTRAS}


def _load(path: Path) -> dict[str, Any]:
    return tomllib.loads(path.read_text(encoding="utf-8"))


def _is_internal(requirement: Requirement) -> bool:
    return requirement.name.startswith(INTERNAL_PREFIX)


def required_external_dependencies(modules: dict[str, dict[str, Any]]) -> list[Requirement]:
    """Rule 1: module dependencies plus formerly enabled extras, without internal `nolemy-*` requirements."""
    required: list[Requirement] = []
    for directory, extras in MODULE_EXTRAS.items():
        project = modules[directory]["project"]
        raw = list(project.get("dependencies", []))
        optional = project.get("optional-dependencies", {})
        for extra in extras:
            raw.extend(optional[extra])
        for item in raw:
            requirement = Requirement(item)
            if not _is_internal(requirement) and requirement not in required:
                required.append(requirement)
    return required


def find_alignment_errors(root: dict[str, Any], modules: dict[str, dict[str, Any]]) -> list[str]:
    """Return one message per violated rule of spec 4.5. An empty list means the root is aligned."""
    errors: list[str] = []
    root_dependencies = [Requirement(item) for item in root["project"].get("dependencies", [])]

    for requirement in required_external_dependencies(modules):
        if requirement not in root_dependencies:
            errors.append(f"root [project].dependencies is missing module requirement {requirement}")

    for requirement in root_dependencies:
        if _is_internal(requirement):
            errors.append(f"root [project].dependencies must not require internal module {requirement}")

    dev_names = {
        Requirement(item).name
        for item in root.get("dependency-groups", {}).get("dev", [])
        if isinstance(item, str)
    }
    for name in sorted(MODULE_DISTRIBUTIONS - dev_names):
        errors.append(f"root [dependency-groups].dev is missing {name}")

    return errors


def _load_repository() -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    root = _load(REPO_ROOT / "pyproject.toml")
    modules = {name: _load(REPO_ROOT / "packages" / name / "pyproject.toml") for name in MODULE_EXTRAS}
    return root, modules


def test_root_pyproject_is_aligned_with_module_dependencies() -> None:
    root, modules = _load_repository()

    assert find_alignment_errors(root, modules) == []


def test_dependency_present_only_on_module_side_is_reported() -> None:
    root, modules = _load_repository()
    modules["vector-search"]["project"]["dependencies"] = ["numpy>=2,<3"]

    errors = find_alignment_errors(root, modules)

    assert errors == ["root [project].dependencies is missing module requirement numpy<3,>=2"]


def test_module_extra_dependency_missing_from_root_is_reported() -> None:
    root, modules = _load_repository()
    root["project"]["dependencies"] = [
        item for item in root["project"]["dependencies"] if Requirement(item).name != "chromadb"
    ]

    errors = find_alignment_errors(root, modules)

    assert errors == ["root [project].dependencies is missing module requirement chromadb<2,>=1.5.9"]


def test_root_specifier_different_from_module_is_reported() -> None:
    root, modules = _load_repository()
    root["project"]["dependencies"] = [
        "rustworkx>=0.17" if Requirement(item).name == "rustworkx" else item
        for item in root["project"]["dependencies"]
    ]

    errors = find_alignment_errors(root, modules)

    assert errors == ["root [project].dependencies is missing module requirement rustworkx<0.18,>=0.17"]


def test_internal_module_requirement_in_root_dependencies_is_reported() -> None:
    root, modules = _load_repository()
    root["project"]["dependencies"] = [*root["project"]["dependencies"], "nolemy-vector-index==0.1.0"]

    errors = find_alignment_errors(root, modules)

    assert errors == ["root [project].dependencies must not require internal module nolemy-vector-index==0.1.0"]


def test_missing_module_in_dev_group_is_reported() -> None:
    root, modules = _load_repository()
    root["dependency-groups"]["dev"] = [
        item for item in root["dependency-groups"]["dev"] if Requirement(item).name != "nolemy-graph-document"
    ]

    errors = find_alignment_errors(root, modules)

    assert errors == ["root [dependency-groups].dev is missing nolemy-graph-document"]


def test_internal_module_requirements_are_excluded_from_comparison() -> None:
    _, modules = _load_repository()

    names = {requirement.name for requirement in required_external_dependencies(modules)}

    assert names == {"rustworkx", "fastembed", "chromadb"}
