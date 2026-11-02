from pathlib import Path

from vault_graph.interface.composition.vault_labels import VaultLabel, label_fields, vault_labels
from vault_graph.operation.scope.vault_catalog import VaultCatalog, VaultCatalogEntry
from vault_graph.project.context.project_binding_reader import MappedProjectMatch, MappedVault


class FakeVaultMap:
    def __init__(self, vaults: tuple[MappedVault, ...]) -> None:
        self._vaults = vaults

    @property
    def vaults(self) -> tuple[MappedVault, ...]:
        return self._vaults

    def find_project(self, cwd: Path) -> MappedProjectMatch:
        del cwd
        return MappedProjectMatch(None, None, ())

    def vaults_for(self, cwd: Path) -> tuple[MappedVault, ...]:
        del cwd
        return ()


def _catalog(tmp_path: Path, *roots: tuple[str, Path]) -> VaultCatalog:
    entries = []
    for vault_id, root in roots:
        root.mkdir(parents=True, exist_ok=True)
        entries.append(VaultCatalogEntry.from_root(vault_id=vault_id, root_path=root))
    return VaultCatalog.from_entries(entries=entries, active_vault_id=roots[0][0])


def test_labels_match_catalog_and_map_vaults_by_real_path(tmp_path: Path) -> None:
    real = tmp_path / "real-team"
    real.mkdir()
    link = tmp_path / "team-link"
    link.symlink_to(real)
    catalog = _catalog(tmp_path, ("main", tmp_path / "main"), ("team-id", link))
    vault_map = FakeVaultMap(
        (
            MappedVault(name="personal-vault", path=(tmp_path / "main").resolve(), role="personal"),
            MappedVault(name="team-vault", path=real.resolve(), role="team"),
        )
    )

    labels = vault_labels(vault_map, catalog)

    assert labels == {
        "main": VaultLabel(name="personal-vault", role="personal"),
        "team-id": VaultLabel(name="team-vault", role="team"),
    }


def test_vault_missing_from_map_has_null_name_and_role(tmp_path: Path) -> None:
    catalog = _catalog(tmp_path, ("main", tmp_path / "main"), ("other", tmp_path / "other"))
    vault_map = FakeVaultMap((MappedVault(name="m", path=(tmp_path / "main").resolve(), role="project"),))

    labels = vault_labels(vault_map, catalog)

    assert label_fields(labels, "main") == {"vault_name": "m", "vault_role": "project"}
    assert label_fields(labels, "other") == {"vault_name": None, "vault_role": None}


def test_no_map_gives_no_labels(tmp_path: Path) -> None:
    catalog = _catalog(tmp_path, ("main", tmp_path / "main"))

    assert vault_labels(None, catalog) == {}
    assert label_fields({}, "main") == {"vault_name": None, "vault_role": None}


def test_role_is_passed_through_as_written(tmp_path: Path) -> None:
    catalog = _catalog(tmp_path, ("main", tmp_path / "main"))
    vault_map = FakeVaultMap((MappedVault(name="x", path=(tmp_path / "main").resolve(), role="any-new-role"),))

    assert vault_labels(vault_map, catalog)["main"].role == "any-new-role"
