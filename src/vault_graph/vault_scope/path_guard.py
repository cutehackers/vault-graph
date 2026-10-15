from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

from vault_graph.errors import ReadOnlyBoundaryError


def assert_graph_home_outside_vaults(*, graph_home: Path, vault_roots: Iterable[Path]) -> None:
    resolved_graph_home = graph_home.expanduser().resolve()
    for vault_root in vault_roots:
        resolved_vault = vault_root.expanduser().resolve()
        if resolved_graph_home == resolved_vault or resolved_vault in resolved_graph_home.parents:
            raise ReadOnlyBoundaryError(
                f"Vault Graph Data Home must not be inside a registered Vault: {resolved_graph_home}"
            )


def assert_graph_home_write_target_allowed(*, graph_home: Path, target_path: Path, vault_roots: Iterable[Path]) -> None:
    resolved_graph_home = graph_home.expanduser().resolve()
    resolved_target = target_path.expanduser().resolve(strict=False)
    if resolved_target != resolved_graph_home and resolved_graph_home not in resolved_target.parents:
        raise ReadOnlyBoundaryError(f"Vault Graph write target must stay inside the Data Home: {resolved_target}")
    assert_graph_home_outside_vaults(graph_home=graph_home, vault_roots=vault_roots)
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
