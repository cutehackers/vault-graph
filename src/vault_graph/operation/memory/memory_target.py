"""Pick the Vault a memory write goes to (spec 2026-11-02 V3, 결정12, A2).

New pages: an explicit ``vault``, then the project's ``default_write_vault``, then the only linked
Vault. Several linked Vaults and no choice give ``VaultRequired``, whose message also names the
vault-builder ``set-default-write`` command that ends the question for that project (F9).
Neither ``memory_kind`` nor the Vault role takes part in the choice (결정12, 결정15).

Existing pages (update, retire): the linked Vaults that hold the path. The default write Vault
does not apply because the page already lives in one Vault.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from vault_graph.project.context.project_binding_reader import MappedProjectMatch, MappedVault, VaultMapReader


@dataclass(frozen=True)
class VaultRequired:
    """No single Vault can be chosen. The caller must pass one of ``candidates`` as ``vault``."""

    candidates: tuple[MappedVault, ...]
    message: str


@dataclass(frozen=True)
class WriteRefusal:
    status: Literal["rejected", "error"]
    messages: tuple[str, ...]


Choice = MappedVault | VaultRequired | WriteRefusal


def choose_write_vault(vault: str | None, cwd: Path | None, vault_map: VaultMapReader) -> Choice:
    match = _project(cwd, vault_map)
    if vault is not None:
        return _named_vault(vault, match, vault_map)
    if match is None or match.project_id is None:
        return _ask_for_vault_outside_a_project(cwd, match, vault_map)
    if not match.vaults:
        return WriteRefusal("error", (f"Project {match.project_id} links no Vault listed in vault-map.json.",))
    default = match.default_write_vault
    if default is not None and default in match.vaults:
        return default
    if len(match.vaults) == 1:
        return match.vaults[0]
    return VaultRequired(
        match.vaults,
        f"Project {match.project_id} links several Vaults and has no default_write_vault. "
        f"Pass vault as one of: {_names(match.vaults)}. "
        f"To stop asking, a person can set the default once in the vault-builder folder: "
        f"`{set_default_write_command(match.project_id, match.vaults)}`.",
    )


def set_default_write_command(project_id: str, vaults: tuple[MappedVault, ...]) -> str:
    """The vault-builder command that sets the project's ``default_write_vault`` (F9, vault-map 계약5).

    vault-graph only reads ``vault-map.json``, so it names the command and never runs it.
    """
    choices = "|".join(vault.name for vault in vaults)
    return f"python3 tools/vault_migration/cli.py set-default-write --project {project_id} --vault <{choices}>"


def choose_page_vault(
    vault: str | None,
    cwd: Path | None,
    vault_map: VaultMapReader,
    *,
    path: str,
    has_page: Callable[[MappedVault], bool],
) -> Choice:
    match = _project(cwd, vault_map)
    if vault is not None:
        named = _named_vault(vault, match, vault_map)
        if isinstance(named, MappedVault) and not has_page(named):
            return WriteRefusal("rejected", (f"Vault {named.name} has no page at {path}.",))
        return named
    in_project = match is not None and match.project_id is not None
    space = match.vaults if in_project and match is not None else vault_map.vaults
    holders = tuple(candidate for candidate in space if has_page(candidate))
    if len(holders) == 1:
        return holders[0]
    where = f"the Vaults linked to project {match.project_id}" if in_project and match else "vault-map.json Vaults"
    if not holders:
        return WriteRefusal("rejected", (f"No page at {path} in {where} ({_names(space) or 'none'}).",))
    return VaultRequired(holders, f"Several Vaults have a page at {path}. Pass vault as one of: {_names(holders)}.")


def _project(cwd: Path | None, vault_map: VaultMapReader) -> MappedProjectMatch | None:
    return None if cwd is None else vault_map.find_project(Path(cwd))


def _named_vault(vault: str, match: MappedProjectMatch | None, vault_map: VaultMapReader) -> MappedVault | WriteRefusal:
    if match is not None and match.project_id is not None:
        for candidate in match.vaults:
            if candidate.name == vault:
                return candidate
        return WriteRefusal(
            "rejected",
            (
                f"Vault {vault} is not linked to project {match.project_id}. "
                f"Linked Vaults: {_names(match.vaults) or 'none'}.",
            ),
        )
    for candidate in vault_map.vaults:
        if candidate.name == vault:
            return candidate
    return WriteRefusal(
        "rejected", (f"No Vault named {vault} in vault-map.json. Vaults: {_names(vault_map.vaults) or 'none'}.",)
    )


def _ask_for_vault_outside_a_project(
    cwd: Path | None, match: MappedProjectMatch | None, vault_map: VaultMapReader
) -> Choice:
    if not vault_map.vaults:
        return WriteRefusal("error", ("vault-map.json lists no Vault.",))
    if match is None:
        reason = "No cwd was given, so no project is known."
    else:
        reason = match.reason or f"{cwd} is not linked to a project."
    return VaultRequired(vault_map.vaults, f"{reason} Pass vault as one of: {_names(vault_map.vaults)}.")


def _names(vaults: tuple[MappedVault, ...]) -> str:
    return ", ".join(vault.name for vault in vaults)


__all__ = ["Choice", "VaultRequired", "WriteRefusal", "choose_page_vault", "choose_write_vault"]
