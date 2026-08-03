from __future__ import annotations

import json
from pathlib import Path

import pytest

from vault_graph.app.catalog_service import CatalogService
from vault_graph.code_index.code_models import CodeRepositoryEntry
from vault_graph.ingestion.vault_catalog import VaultCatalog, VaultCatalogEntry
from vault_graph.project_context.project_binding import ProjectBinding
from vault_graph.project_context.project_binding_catalog import ProjectBindingCatalogService


class _Repositories:
    def __init__(self, entry: CodeRepositoryEntry) -> None:
        self._entry = entry

    def entries(self) -> tuple[CodeRepositoryEntry, ...]:
        return (self._entry,)

    def resolve(self, repository_id: str) -> CodeRepositoryEntry:
        if repository_id != self._entry.repository_id:
            raise ValueError(f"unknown repository_id: {repository_id}")
        return self._entry


def _service(tmp_path: Path) -> tuple[ProjectBindingCatalogService, Path]:
    vault_root = tmp_path / "vault"
    repository_root = tmp_path / "repository"
    vault_root.mkdir()
    repository_root.mkdir()
    catalog = VaultCatalog.from_entries(
        entries=(VaultCatalogEntry.from_root(vault_id="main", root_path=vault_root),),
        active_vault_id="main",
    )
    state_path = tmp_path / "state"
    catalog_service = CatalogService(state_path=state_path)
    catalog_service.save_catalog(catalog)
    repository = CodeRepositoryEntry(
        repository_id="demo",
        root_path=repository_root,
        display_name="Demo",
        enabled=True,
        include_globs=("**/*.py",),
        exclude_globs=(),
        languages=("python",),
        state_namespace="code/demo",
        git_revision_policy="head",
        watch=False,
    )
    return (
        ProjectBindingCatalogService(
            catalog_service=catalog_service,
            repository_catalog=_Repositories(repository),
            vault_catalog=catalog,
        ),
        state_path,
    )


def test_project_binding_catalog_round_trips_versioned_state(tmp_path: Path) -> None:
    service, state_path = _service(tmp_path)

    catalog = service.bind(ProjectBinding(repository_id="demo", vault_ids=("main",), content_scopes=("wiki",)))

    assert catalog.resolve("demo").vault_ids == ("main",)
    payload = json.loads((state_path / "configs" / "project-bindings.json").read_text(encoding="utf-8"))
    assert payload["schema_version"] == "project-bindings-v1"
    assert service.load().resolve("demo").content_scopes == ("wiki",)


def test_project_binding_catalog_replaces_duplicate_repository_binding(tmp_path: Path) -> None:
    service, _ = _service(tmp_path)
    service.bind(ProjectBinding(repository_id="demo", vault_ids=("main",), content_scopes=("wiki",)))

    catalog = service.bind(ProjectBinding(repository_id="demo", vault_ids=("main",), content_scopes=("docs",)))

    assert catalog.resolve("demo").content_scopes == ("docs",)


def test_project_binding_catalog_rejects_unregistered_authorities(tmp_path: Path) -> None:
    service, _ = _service(tmp_path)

    with pytest.raises(ValueError, match="unknown vault_id"):
        service.bind(ProjectBinding(repository_id="demo", vault_ids=("missing",)))
    with pytest.raises(ValueError, match="unknown repository_id"):
        service.bind(ProjectBinding(repository_id="missing", vault_ids=("main",)))
