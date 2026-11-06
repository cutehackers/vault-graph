"""``vaults.<name>.sharable`` and the linked projects of a Vault in ``vault-map.json`` (spec §4.4.2, §6)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from vault_graph.operation.integration.vault_map import (
    MappedVaultScope,
    load_vault_map,
    open_vault_map,
)


def _write(tmp_path: Path, vaults: dict[str, dict[str, object]], projects: dict[str, list[str]]) -> Path:
    data = {
        "version": 2,
        "vaults": {
            name: {"path": str(tmp_path / "vaults" / name), "role": "personal", **extra}
            for name, extra in vaults.items()
        },
        "projects": {pid: {"root": str(tmp_path / "repos" / pid), "vaults": names} for pid, names in projects.items()},
    }
    path = tmp_path / "vault-map.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def test_scope_lists_every_project_linked_to_the_vault(tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        {"personal": {"sharable": True}, "alpha-vault": {}},
        {"alpha": ["alpha-vault", "personal"], "beta": ["personal", "personal"]},
    )

    vault_map = load_vault_map(path)

    assert vault_map.project_scope("personal") == MappedVaultScope(
        linked_projects=frozenset({"alpha", "beta"}), sharable=True
    )
    assert vault_map.project_scope("alpha-vault") == MappedVaultScope(
        linked_projects=frozenset({"alpha"}), sharable=False
    )


def test_unknown_vault_name_has_no_links_and_is_not_sharable(tmp_path: Path) -> None:
    vault_map = load_vault_map(_write(tmp_path, {"personal": {}}, {"alpha": ["personal"]}))

    assert vault_map.project_scope("ghost") == MappedVaultScope(linked_projects=frozenset(), sharable=False)


@pytest.mark.parametrize(("extra", "expected"), [({}, False), ({"sharable": False}, False), ({"sharable": True}, True)])
def test_absent_field_is_false_without_a_warning(tmp_path: Path, extra: dict[str, object], expected: bool) -> None:
    vault_map = load_vault_map(_write(tmp_path, {"personal": extra}, {"alpha": ["personal"], "beta": ["personal"]}))

    assert vault_map.project_scope("personal").sharable is expected
    assert vault_map.warnings == ()


@pytest.mark.parametrize("value", ["true", 1, 0, None, ["yes"]])
def test_non_boolean_field_is_ignored_with_a_warning_and_read_as_false(tmp_path: Path, value: object) -> None:
    opened = open_vault_map(_write(tmp_path, {"personal": {"sharable": value}}, {"alpha": ["personal"]}))

    assert opened.state == "loaded"
    assert opened.vault_map is not None
    assert opened.vault_map.project_scope("personal").sharable is False
    (warning,) = opened.vault_map.warnings
    assert "personal" in warning and "sharable" in warning and "not a boolean" in warning


def test_map_without_any_sharable_field_still_loads(tmp_path: Path) -> None:
    opened = open_vault_map(_write(tmp_path, {"personal": {}, "team": {}}, {"alpha": ["personal", "team"]}))

    assert opened.state == "loaded"
    assert opened.vault_map is not None
    assert opened.vault_map.warnings == ()
