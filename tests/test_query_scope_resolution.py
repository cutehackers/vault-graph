import json
import subprocess
from pathlib import Path

from vault_graph.interface.composition.query_scope_resolution import (
    actual_query_scopes,
    default_query_vault_ids,
    default_query_vaults,
    project_query_selection,
)
from vault_graph.interface.composition.vault_labels import VaultLabel
from vault_graph.operation.scope.vault_catalog import QueryScope, VaultCatalog, VaultCatalogEntry
from vault_graph.project.context.project_binding_reader import MappedProjectMatch, MappedVault


def _entry(tmp_path: Path, vault_id: str, scopes: tuple[str, ...]) -> VaultCatalogEntry:
    root = tmp_path / vault_id
    root.mkdir()
    return VaultCatalogEntry.from_root(vault_id=vault_id, root_path=root, content_scopes=scopes)


def test_actual_scopes_keep_each_vault_narrow(tmp_path: Path) -> None:
    catalog = VaultCatalog.from_entries(
        entries=[
            _entry(tmp_path, "first", ("wiki",)),
            _entry(tmp_path, "second", ("docs",)),
        ],
        active_vault_id="first",
    )

    scopes = actual_query_scopes(
        catalog=catalog,
        scope=QueryScope(vault_ids=("first", "second"), content_scopes=("wiki", "docs")),
    )

    assert tuple(scope.vault_ids for scope in scopes) == (("first",), ("second",))
    assert tuple(scope.content_scopes for scope in scopes) == (("wiki",), ("docs",))


def test_actual_scopes_use_narrower_child_scope(tmp_path: Path) -> None:
    catalog = VaultCatalog.from_entries(
        entries=[_entry(tmp_path, "default", ("wiki",))],
        active_vault_id="default",
    )

    scopes = actual_query_scopes(
        catalog=catalog,
        scope=QueryScope(vault_ids=("default",), content_scopes=("wiki/systems",)),
    )

    assert scopes[0].content_scopes == ("wiki/systems",)


def test_actual_scopes_skip_disjoint_scope_pairs(tmp_path: Path) -> None:
    catalog = VaultCatalog.from_entries(
        entries=[_entry(tmp_path, "default", ("wiki",))],
        active_vault_id="default",
    )

    scopes = actual_query_scopes(
        catalog=catalog,
        scope=QueryScope(vault_ids=("default",), content_scopes=("docs",)),
    )

    assert scopes == ()


# --- default_query_vault_ids: cwd project's registered Vaults, else the active Vault (V2) ---


class FakeVaultMap:
    def __init__(self, vaults: tuple[MappedVault, ...], project: tuple[MappedVault, ...] | None) -> None:
        self._vaults = vaults
        self._project = project

    @property
    def vaults(self) -> tuple[MappedVault, ...]:
        return self._vaults

    def find_project(self, cwd: Path) -> MappedProjectMatch:
        del cwd
        if self._project is None:
            return MappedProjectMatch(None, None, (), reason="not linked")
        return MappedProjectMatch("proj", "root", self._project)

    def vaults_for(self, cwd: Path) -> tuple[MappedVault, ...]:
        return self.find_project(cwd).vaults


def _mapped(tmp_path: Path, name: str, role: str) -> MappedVault:
    path = tmp_path / name
    path.mkdir(exist_ok=True)
    return MappedVault(name=name, path=path.resolve(), role=role)


def _three_vault_catalog(tmp_path: Path, *, disabled: str | None = None) -> VaultCatalog:
    entries = []
    for vault_id, folder in (("active", "elsewhere"), ("p-id", "personal"), ("t-id", "team")):
        root = tmp_path / folder
        root.mkdir(exist_ok=True)
        entries.append(VaultCatalogEntry.from_root(vault_id=vault_id, root_path=root, enabled=vault_id != disabled))
    return VaultCatalog.from_entries(entries=entries, active_vault_id="active")


def test_project_vaults_are_all_registered_linked_vaults_in_map_order(tmp_path: Path) -> None:
    catalog = _three_vault_catalog(tmp_path)
    team, personal = _mapped(tmp_path, "team", "team"), _mapped(tmp_path, "personal", "personal")
    vault_map = FakeVaultMap((personal, team), (team, personal))

    assert default_query_vault_ids(tmp_path, vault_map=vault_map, vault_catalog=catalog) == ("t-id", "p-id")
    assert default_query_vaults(tmp_path, vault_map=vault_map, vault_catalog=catalog).warnings == ()


def test_folder_outside_any_project_falls_back_to_the_active_vault(tmp_path: Path) -> None:
    catalog = _three_vault_catalog(tmp_path)
    vault_map = FakeVaultMap((_mapped(tmp_path, "team", "team"),), None)

    assert default_query_vault_ids(tmp_path, vault_map=vault_map, vault_catalog=catalog) is None
    assert default_query_vault_ids(tmp_path, vault_map=None, vault_catalog=catalog) is None


def test_project_without_registered_vault_gives_empty_ids_and_setup_warning(tmp_path: Path) -> None:
    catalog = _three_vault_catalog(tmp_path)
    missing = _mapped(tmp_path, "unregistered", "project")
    vault_map = FakeVaultMap((missing,), (missing,))

    resolved = default_query_vaults(tmp_path, vault_map=vault_map, vault_catalog=catalog)

    assert resolved.vault_ids == ()
    assert len(resolved.warnings) == 1
    assert "unregistered" in resolved.warnings[0]
    assert "vg setup" in resolved.warnings[0]


def test_partly_registered_project_names_the_missing_vault(tmp_path: Path) -> None:
    catalog = _three_vault_catalog(tmp_path)
    team, missing = _mapped(tmp_path, "team", "team"), _mapped(tmp_path, "unregistered", "project")
    vault_map = FakeVaultMap((team, missing), (team, missing))

    resolved = default_query_vaults(tmp_path, vault_map=vault_map, vault_catalog=catalog)

    assert resolved.vault_ids == ("t-id",)
    assert any("unregistered" in warning and "vg setup" in warning for warning in resolved.warnings)


def test_registered_but_unindexed_vault_is_named_in_a_warning(tmp_path: Path) -> None:
    catalog = _three_vault_catalog(tmp_path)
    team, personal = _mapped(tmp_path, "team", "team"), _mapped(tmp_path, "personal", "personal")
    vault_map = FakeVaultMap((team, personal), (team, personal))

    resolved = default_query_vaults(
        tmp_path, vault_map=vault_map, vault_catalog=catalog, is_indexed=lambda vault_id: vault_id == "t-id"
    )

    assert resolved.vault_ids == ("t-id", "p-id")
    assert any("personal" in warning and "vg index" in warning for warning in resolved.warnings)
    assert not any("team" in warning for warning in resolved.warnings)


def test_disabled_vault_is_left_out_and_named(tmp_path: Path) -> None:
    catalog = _three_vault_catalog(tmp_path, disabled="p-id")
    team, personal = _mapped(tmp_path, "team", "team"), _mapped(tmp_path, "personal", "personal")
    vault_map = FakeVaultMap((team, personal), (team, personal))

    resolved = default_query_vaults(tmp_path, vault_map=vault_map, vault_catalog=catalog)

    assert resolved.vault_ids == ("t-id",)
    assert any("personal" in warning and "disabled" in warning for warning in resolved.warnings)


def _write_map(path: Path, vaults: dict[str, tuple[Path, str]], projects: dict[str, dict[str, object]]) -> Path:
    path.write_text(
        json.dumps(
            {
                "version": 2,
                "vaults": {name: {"path": str(root), "role": role} for name, (root, role) in vaults.items()},
                "projects": projects,
            }
        ),
        encoding="utf-8",
    )
    return path


def test_selection_reads_the_map_file_and_labels_every_vault(tmp_path: Path) -> None:
    catalog = _three_vault_catalog(tmp_path)
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "-C", str(repo), "init", "-q"], check=True)
    map_file = _write_map(
        tmp_path / "vault-map.json",
        {"team": (tmp_path / "team", "team"), "personal": (tmp_path / "personal", "personal")},
        {"repo": {"root": str(repo), "vaults": ["personal", "team"]}},
    )

    selection = project_query_selection(repo, catalog=catalog, vault_map_file=map_file)
    outside = project_query_selection(tmp_path / "elsewhere", catalog=catalog, vault_map_file=map_file)
    explicit = project_query_selection(None, catalog=catalog, vault_map_file=map_file)

    assert selection.vault_ids == ("p-id", "t-id")
    assert selection.labels["t-id"] == VaultLabel(name="team", role="team")
    assert "active" not in selection.labels
    assert outside.vault_ids is None
    assert explicit.vault_ids is None
    assert explicit.labels == selection.labels


def test_selection_without_a_map_file_uses_the_active_vault_and_no_labels(tmp_path: Path) -> None:
    catalog = _three_vault_catalog(tmp_path)

    selection = project_query_selection(tmp_path, catalog=catalog, vault_map_file=tmp_path / "missing.json")

    assert selection.vault_ids is None
    assert selection.labels == {}
    assert selection.warnings == ()


def test_damaged_map_file_warns_and_uses_the_active_vault(tmp_path: Path) -> None:
    catalog = _three_vault_catalog(tmp_path)
    damaged = tmp_path / "vault-map.json"
    damaged.write_text("{", encoding="utf-8")

    selection = project_query_selection(tmp_path, catalog=catalog, vault_map_file=damaged)

    assert selection.vault_ids is None
    assert len(selection.warnings) == 1
