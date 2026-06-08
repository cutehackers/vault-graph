from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

from vault_graph.errors import ReadOnlyBoundaryError


def assert_state_outside_vaults(*, state_path: Path, vault_roots: Iterable[Path]) -> None:
    resolved_state = state_path.expanduser().resolve()
    for vault_root in vault_roots:
        resolved_vault = vault_root.expanduser().resolve()
        if resolved_state == resolved_vault or resolved_vault in resolved_state.parents:
            raise ReadOnlyBoundaryError(
                f"Vault Graph state path must not be inside a registered Vault: {resolved_state}"
            )


def assert_write_target_allowed(*, state_path: Path, target_path: Path, vault_roots: Iterable[Path]) -> None:
    resolved_state = state_path.expanduser().resolve()
    resolved_target = target_path.expanduser().resolve(strict=False)
    if resolved_target != resolved_state and resolved_state not in resolved_target.parents:
        raise ReadOnlyBoundaryError(f"Vault Graph write target must stay inside the state path: {resolved_target}")
    assert_state_outside_vaults(state_path=state_path, vault_roots=vault_roots)
    for vault_root in vault_roots:
        resolved_vault = vault_root.expanduser().resolve()
        if resolved_target == resolved_vault or resolved_vault in resolved_target.parents:
            raise ReadOnlyBoundaryError(
                f"Vault Graph write target must not be inside a registered Vault: {resolved_target}"
            )


def assert_target_outside_vaults(*, target_path: Path, vault_roots: Iterable[Path]) -> None:
    resolved_target = target_path.expanduser().resolve(strict=False)
    for vault_root in vault_roots:
        resolved_vault = vault_root.expanduser().resolve()
        if resolved_target == resolved_vault or resolved_vault in resolved_target.parents:
            raise ReadOnlyBoundaryError(
                f"Vault Graph target path must not be inside a registered Vault: {resolved_target}"
            )
