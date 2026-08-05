from __future__ import annotations

from pathlib import Path

import pytest

from vault_graph.app.catalog_service import CatalogService
from vault_graph.code_index.code_models import CodeRepositoryEntry
from vault_graph.code_index.repository_catalog import CodeRepositoryCatalogService
from vault_graph.errors import CatalogError, ReadOnlyBoundaryError


def _entry(root: Path) -> CodeRepositoryEntry:
    return CodeRepositoryEntry(
        repository_id="demo",
        root_path=root,
        display_name="Demo",
        enabled=True,
        include_globs=("**/*.py",),
        exclude_globs=(".git/**",),
        languages=("python",),
        state_namespace="code/demo",
        git_revision_policy="head-and-working-tree",
        watch=False,
    )


def test_code_repository_root_equal_or_inside_vault_is_rejected(tmp_path: Path) -> None:
    vault_root = tmp_path / "vault"
    vault_root.mkdir()
    graph_home_path = tmp_path / "state"
    catalog_service = CatalogService(graph_home_path=graph_home_path)
    catalog_service.create_default_catalog(vault_root=vault_root)
    service = CodeRepositoryCatalogService(catalog_service=catalog_service)

    with pytest.raises((CatalogError, ReadOnlyBoundaryError), match="Vault"):
        service.add(_entry(vault_root))

    nested = vault_root / "nested-repository"
    nested.mkdir()
    with pytest.raises((CatalogError, ReadOnlyBoundaryError), match="Vault"):
        service.add(_entry(nested))


def test_code_repository_root_equal_or_inside_graph_state_is_rejected(tmp_path: Path) -> None:
    vault_root = tmp_path / "vault"
    vault_root.mkdir()
    graph_home_path = tmp_path / "state"
    catalog_service = CatalogService(graph_home_path=graph_home_path)
    catalog_service.create_default_catalog(vault_root=vault_root)
    service = CodeRepositoryCatalogService(catalog_service=catalog_service)

    graph_home_path.mkdir(parents=True, exist_ok=True)
    with pytest.raises(CatalogError, match="Graph Data Home"):
        service.add(_entry(graph_home_path))

    nested = graph_home_path / "nested-repository"
    nested.mkdir()
    with pytest.raises(CatalogError, match="Graph Data Home"):
        service.add(_entry(nested))


def test_code_repository_root_containing_graph_state_is_rejected(tmp_path: Path) -> None:
    vault_root = tmp_path / "vault"
    vault_root.mkdir()
    repository_root = tmp_path / "repository"
    repository_root.mkdir()
    graph_home_path = repository_root / "state"
    catalog_service = CatalogService(graph_home_path=graph_home_path)
    catalog_service.create_default_catalog(vault_root=vault_root)
    service = CodeRepositoryCatalogService(catalog_service=catalog_service)

    with pytest.raises(CatalogError, match="Graph Data Home"):
        service.add(_entry(repository_root))


def test_catalog_mutations_never_modify_or_delete_repository_files(tmp_path: Path) -> None:
    vault_root = tmp_path / "vault"
    vault_root.mkdir()
    graph_home_path = tmp_path / "state"
    catalog_service = CatalogService(graph_home_path=graph_home_path)
    catalog_service.create_default_catalog(vault_root=vault_root)
    repository_root = tmp_path / "repository"
    repository_root.mkdir()
    source = repository_root / "main.py"
    source.write_text("print('stable')\n", encoding="utf-8")
    before = source.read_bytes()
    service = CodeRepositoryCatalogService(catalog_service=catalog_service)

    service.add(_entry(repository_root))
    service.remove("demo")

    assert source.exists()
    assert source.read_bytes() == before
    assert repository_root.exists()
    assert catalog_service.code_config_path == graph_home_path / "configs" / "repositories.yaml"
    assert not (vault_root / "repositories.yaml").exists()


def test_code_catalog_rejects_config_symlink_into_vault(tmp_path: Path) -> None:
    vault_root = tmp_path / "vault"
    (vault_root / "docs").mkdir(parents=True)
    graph_home_path = tmp_path / "state"
    catalog_service = CatalogService(graph_home_path=graph_home_path)
    catalog_service.create_default_catalog(vault_root=vault_root)
    config_path = catalog_service.code_config_path
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.symlink_to(vault_root / "docs" / "repositories.yaml")

    service = CodeRepositoryCatalogService(catalog_service=catalog_service)

    with pytest.raises(ReadOnlyBoundaryError, match="Data Home"):
        service.load()
