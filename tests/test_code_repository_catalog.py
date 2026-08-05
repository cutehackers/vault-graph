from __future__ import annotations

from pathlib import Path

import pytest

from vault_graph.app.catalog_service import CatalogService
from vault_graph.app.graph_home import DEFAULT_GRAPH_HOME
from vault_graph.code_index.code_models import CodeRepositoryEntry
from vault_graph.code_index.repository_catalog import (
    CodeRepositoryCatalogService,
    repository_policy_revision,
)
from vault_graph.errors import CatalogError


def _vault_and_service(tmp_path: Path) -> tuple[Path, CodeRepositoryCatalogService]:
    vault_root = tmp_path / "vault"
    vault_root.mkdir()
    graph_home_path = tmp_path / "state"
    catalog_service = CatalogService(graph_home_path=graph_home_path)
    catalog_service.create_default_catalog(vault_root=vault_root)
    return vault_root, CodeRepositoryCatalogService(catalog_service=catalog_service)


def _entry(root: Path, repository_id: str = "demo", **overrides: object) -> CodeRepositoryEntry:
    values: dict[str, object] = {
        "repository_id": repository_id,
        "root_path": root,
        "display_name": "Demo",
        "enabled": True,
        "include_globs": ("src/**",),
        "exclude_globs": (".git/**",),
        "languages": ("python",),
        "state_namespace": f"code/{repository_id}",
        "git_revision_policy": "head-and-working-tree",
        "watch": False,
    }
    values.update(overrides)
    return CodeRepositoryEntry(**values)  # type: ignore[arg-type]


def test_catalog_service_defaults_to_canonical_graph_home() -> None:
    service = CodeRepositoryCatalogService()

    assert service.graph_home_path == DEFAULT_GRAPH_HOME


def test_catalog_yaml_round_trip_normalizes_roots_and_preserves_order(tmp_path: Path) -> None:
    _, service = _vault_and_service(tmp_path)
    first = tmp_path / "repo-a"
    second = tmp_path / "repo-b"
    first.mkdir()
    second.mkdir()

    service.add(_entry(first, "first"))
    service.add(_entry(second, "second", languages=("dart",), include_globs=("lib/**",)))

    loaded = CodeRepositoryCatalogService(catalog_service=service.catalog_service).load()

    assert [entry.repository_id for entry in loaded.entries()] == ["first", "second"]
    assert loaded.resolve("first").root_path == first.resolve()
    assert loaded.resolve("second").languages == ("dart",)
    assert service.config_path == tmp_path / "state" / "configs" / "repositories.yaml"
    assert service.config_path.exists()


def test_catalog_hashes_scan_policy_deterministically(tmp_path: Path) -> None:
    _, service = _vault_and_service(tmp_path)
    repo = tmp_path / "repo"
    repo.mkdir()
    first = _entry(repo)
    second = _entry(repo, include_globs=("tests/**",))

    assert repository_policy_revision(first) == repository_policy_revision(first)
    assert repository_policy_revision(first) != repository_policy_revision(second)
    service.add(first)


def test_catalog_rejects_missing_root(tmp_path: Path) -> None:
    _, service = _vault_and_service(tmp_path)

    with pytest.raises(CatalogError, match="does not exist"):
        service.add(_entry(tmp_path / "missing"))


def test_catalog_rejects_duplicate_id_and_canonical_root(tmp_path: Path) -> None:
    _, service = _vault_and_service(tmp_path)
    first = tmp_path / "repo"
    first.mkdir()
    service.add(_entry(first))

    with pytest.raises(CatalogError, match="duplicate repository_id"):
        service.add(_entry(tmp_path / "other"))

    alias = tmp_path / "alias"
    alias.symlink_to(first, target_is_directory=True)
    with pytest.raises(CatalogError, match="canonical root"):
        service.add(_entry(alias, repository_id="alias"))


def test_catalog_rejects_parent_child_overlap(tmp_path: Path) -> None:
    _, service = _vault_and_service(tmp_path)
    parent = tmp_path / "parent"
    child = parent / "child"
    child.mkdir(parents=True)
    service.add(_entry(parent, "parent"))

    with pytest.raises(CatalogError, match="overlap"):
        service.add(_entry(child, "child"))


def test_catalog_rejects_duplicate_state_namespace(tmp_path: Path) -> None:
    _, service = _vault_and_service(tmp_path)
    first = tmp_path / "repo-a"
    second = tmp_path / "repo-b"
    first.mkdir()
    second.mkdir()
    service.add(_entry(first, "first", state_namespace="code/shared"))

    with pytest.raises(CatalogError, match="duplicate state_namespace"):
        service.add(_entry(second, "second", state_namespace="code/shared"))


@pytest.mark.parametrize("glob", [".", "../outside/**", "src/../outside/**", "/tmp/**"])
def test_catalog_rejects_empty_absolute_or_traversal_globs(tmp_path: Path, glob: str) -> None:
    _, service = _vault_and_service(tmp_path)
    repo = tmp_path / "repo"
    repo.mkdir()

    with pytest.raises(CatalogError, match="glob"):
        service.add(_entry(repo, include_globs=(glob,)))


def test_catalog_rejects_empty_glob_loaded_from_yaml(tmp_path: Path) -> None:
    _, service = _vault_and_service(tmp_path)
    repo = tmp_path / "repo"
    repo.mkdir()
    service.config_path.parent.mkdir(parents=True, exist_ok=True)
    service.config_path.write_text(
        "repositories:\n"
        "  - repository_id: demo\n"
        f"    root_path: {repo}\n"
        "    include_globs: ['']\n"
        "    exclude_globs: []\n"
        "    languages: [python]\n"
        "    state_namespace: code/demo\n"
        "    git_revision_policy: head-and-working-tree\n"
        "    watch: false\n",
        encoding="utf-8",
    )

    with pytest.raises(CatalogError, match="repository entry"):
        service.load()


def test_catalog_wraps_malformed_utf8_as_catalog_error(tmp_path: Path) -> None:
    _, service = _vault_and_service(tmp_path)
    service.config_path.parent.mkdir(parents=True, exist_ok=True)
    service.config_path.write_bytes(b"repositories:\n  - \xff\n")

    with pytest.raises(CatalogError, match="cannot read code repository catalog"):
        service.load()


def test_catalog_rejects_symlink_glob_escape(tmp_path: Path) -> None:
    _, service = _vault_and_service(tmp_path)
    repo = tmp_path / "repo"
    outside = tmp_path / "outside"
    repo.mkdir()
    outside.mkdir()
    (repo / "linked").symlink_to(outside, target_is_directory=True)

    with pytest.raises(CatalogError, match="symlink"):
        service.add(_entry(repo, include_globs=("linked/**",)))


def test_catalog_rejects_unsupported_language(tmp_path: Path) -> None:
    _, service = _vault_and_service(tmp_path)
    repo = tmp_path / "repo"
    repo.mkdir()

    with pytest.raises(CatalogError, match="unsupported language"):
        service.add(_entry(repo, languages=("rust",)))
