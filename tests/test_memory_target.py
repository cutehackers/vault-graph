"""A-8: pick the write Vault by 결정12, and find the Vault of an existing page for update and retire.

Source: spec 2026-11-02-vault-long-term-memory V3 (저장 Vault 고르기, 수정·폐기 대상 페이지 찾기), 6절.
"""

from __future__ import annotations

import inspect
from collections.abc import Callable
from pathlib import Path

import pytest

from vault_graph.operation.memory.memory_target import (
    VaultRequired,
    WriteRefusal,
    choose_page_vault,
    choose_write_vault,
)
from vault_graph.project.context.project_binding_reader import MappedProjectMatch, MappedVault

PERSONAL = MappedVault(name="personal", path=Path("/vaults/personal"), role="personal")
PROJECT = MappedVault(name="project", path=Path("/vaults/project"), role="project")
TEAM = MappedVault(name="team", path=Path("/vaults/team"), role="team")


class FakeVaultMap:
    def __init__(
        self,
        vaults: tuple[MappedVault, ...],
        projects: dict[str, tuple[tuple[MappedVault, ...], MappedVault | None]],
    ) -> None:
        self._vaults = vaults
        self._projects = projects

    @property
    def vaults(self) -> tuple[MappedVault, ...]:
        return self._vaults

    def find_project(self, cwd: Path) -> MappedProjectMatch:
        linked = self._projects.get(str(cwd))
        if linked is None:
            return MappedProjectMatch(None, None, (), reason=f"{cwd} is not linked to a project.")
        vaults, default = linked
        return MappedProjectMatch("demo", "root", vaults, default_write_vault=default)

    def vaults_for(self, cwd: Path) -> tuple[MappedVault, ...]:
        return self.find_project(cwd).vaults


def make_map(default: MappedVault | None = None, linked: tuple[MappedVault, ...] = (PROJECT, TEAM)) -> FakeVaultMap:
    return FakeVaultMap(
        (PERSONAL, PROJECT, TEAM),
        {"/repo": (linked, default), "/solo": ((PROJECT,), None)},
    )


# A-8 table


def test_two_linked_vaults_without_default_or_vault_ask_for_a_vault() -> None:
    chosen = choose_write_vault(None, Path("/repo"), make_map())

    assert isinstance(chosen, VaultRequired)
    assert chosen.candidates == (PROJECT, TEAM)


def test_default_write_vault_is_used() -> None:
    assert choose_write_vault(None, Path("/repo"), make_map(default=TEAM)) == TEAM


def test_vault_not_linked_to_the_project_is_rejected_with_the_linked_list() -> None:
    chosen = choose_write_vault("personal", Path("/repo"), make_map())

    assert isinstance(chosen, WriteRefusal)
    assert chosen.status == "rejected"
    assert any("not linked" in message and "project, team" in message for message in chosen.messages)


def test_single_linked_vault_is_used() -> None:
    assert choose_write_vault(None, Path("/solo"), make_map()) == PROJECT


# Other 결정12 rows


def test_vault_argument_beats_the_default() -> None:
    assert choose_write_vault("project", Path("/repo"), make_map(default=TEAM)) == PROJECT


def test_vault_argument_is_looked_up_in_the_whole_map_without_a_project() -> None:
    assert choose_write_vault("personal", None, make_map()) == PERSONAL
    assert choose_write_vault("personal", Path("/elsewhere"), make_map()) == PERSONAL


def test_unknown_vault_without_a_project_is_rejected() -> None:
    chosen = choose_write_vault("missing", None, make_map())

    assert isinstance(chosen, WriteRefusal)
    assert chosen.status == "rejected"
    assert any("missing" in message for message in chosen.messages)


def test_no_project_and_no_vault_asks_for_a_vault_from_the_whole_map() -> None:
    chosen = choose_write_vault(None, Path("/elsewhere"), make_map())

    assert isinstance(chosen, VaultRequired)
    assert chosen.candidates == (PERSONAL, PROJECT, TEAM)
    assert "/elsewhere is not linked" in chosen.message


def test_default_outside_the_linked_vaults_is_ignored() -> None:
    chosen = choose_write_vault(None, Path("/repo"), make_map(default=PERSONAL))

    assert isinstance(chosen, VaultRequired)


def test_project_whose_vaults_are_not_in_the_map_is_an_error() -> None:
    chosen = choose_write_vault(None, Path("/repo"), make_map(linked=()))

    assert isinstance(chosen, WriteRefusal)
    assert chosen.status == "error"


def test_choice_takes_no_memory_kind_or_role_input() -> None:
    assert list(inspect.signature(choose_write_vault).parameters) == ["vault", "cwd", "vault_map"]


@pytest.mark.parametrize("role", ["personal", "team", "project", "other"])
def test_roles_do_not_change_the_choice(role: str) -> None:
    first = MappedVault(name="a", path=Path("/vaults/a"), role=role)
    second = MappedVault(name="b", path=Path("/vaults/b"), role="project")
    vault_map = FakeVaultMap((first, second), {"/repo": ((first, second), None)})

    chosen = choose_write_vault(None, Path("/repo"), vault_map)

    assert isinstance(chosen, VaultRequired)
    assert chosen.candidates == (first, second)


# Update and retire target


def has_page_in(*names: str) -> Callable[[MappedVault], bool]:
    return lambda vault: vault.name in names


@pytest.mark.parametrize(
    ("holders", "expected"),
    [
        ((), "rejected"),
        (("team",), TEAM),
        (("project", "team"), "vault_required"),
    ],
    ids=["none", "one", "two"],
)
def test_page_vault_follows_how_many_linked_vaults_have_the_path(holders: tuple[str, ...], expected: object) -> None:
    chosen = choose_page_vault(
        None, Path("/repo"), make_map(default=PROJECT), path="wiki/decisions/a.md", has_page=has_page_in(*holders)
    )

    if expected == "rejected":
        assert isinstance(chosen, WriteRefusal)
        assert chosen.status == "rejected"
        assert any("wiki/decisions/a.md" in message for message in chosen.messages)
    elif expected == "vault_required":
        assert isinstance(chosen, VaultRequired)
        assert chosen.candidates == (PROJECT, TEAM)
    else:
        assert chosen == expected


def test_page_vault_ignores_vaults_not_linked_to_the_project() -> None:
    chosen = choose_page_vault(
        None, Path("/repo"), make_map(), path="wiki/decisions/a.md", has_page=has_page_in("personal")
    )

    assert isinstance(chosen, WriteRefusal)
    assert chosen.status == "rejected"


def test_named_page_vault_must_hold_the_page() -> None:
    chosen = choose_page_vault(
        "project", Path("/repo"), make_map(), path="wiki/decisions/a.md", has_page=has_page_in("team")
    )

    assert isinstance(chosen, WriteRefusal)
    assert chosen.status == "rejected"


def test_named_page_vault_outside_the_project_is_rejected() -> None:
    chosen = choose_page_vault(
        "personal", Path("/repo"), make_map(), path="wiki/decisions/a.md", has_page=has_page_in("personal")
    )

    assert isinstance(chosen, WriteRefusal)
    assert any("not linked" in message for message in chosen.messages)


def test_named_page_vault_with_the_page_is_used() -> None:
    chosen = choose_page_vault(
        "team", Path("/repo"), make_map(), path="wiki/decisions/a.md", has_page=has_page_in("project", "team")
    )

    assert chosen == TEAM
