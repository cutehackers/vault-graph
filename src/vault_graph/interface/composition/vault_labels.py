"""Vault name and role shown next to each search result (spec V2, 결정S2) and read tool result (F12).

Search results carry only ``vault_id``. The name and role come from ``vault-map.json``, matched to
Graph Home catalog entries by real path, so retrieval never reads the map. Role is a display string:
nothing here or in callers branches on its value (결정15).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from vault_graph.operation.scope.vault_catalog import VaultCatalog
from vault_graph.project.context.project_binding_reader import VaultMapReader


@dataclass(frozen=True)
class VaultLabel:
    name: str
    role: str


def vault_labels(vault_map: VaultMapReader | None, catalog: VaultCatalog) -> Mapping[str, VaultLabel]:
    """Return the map name and role of each catalog Vault id whose real path is in the map."""
    if vault_map is None:
        return {}
    by_path = {_real(vault.path): VaultLabel(name=vault.name, role=vault.role) for vault in vault_map.vaults}
    labels: dict[str, VaultLabel] = {}
    for entry in catalog.entries():
        label = by_path.get(_real(entry.root_path))
        if label is not None:
            labels[entry.vault_id] = label
    return labels


def label_fields(labels: Mapping[str, VaultLabel], vault_id: str) -> dict[str, str | None]:
    """Return the ``vault_name`` and ``vault_role`` result fields. Both are None for an unmapped Vault."""
    label = labels.get(vault_id)
    return {
        "vault_name": label.name if label is not None else None,
        "vault_role": label.role if label is not None else None,
    }


def label_payload(value: object, labels: Mapping[str, VaultLabel]) -> object:
    """Copy a JSON payload, adding ``vault_name`` and ``vault_role`` to every object with a ``vault_id``.

    Read tools nest results differently (answer citations, context pack items, graph entities), so
    every object that names its Vault gets the label. An object that already has ``vault_name`` keeps it.
    """
    if isinstance(value, dict):
        copied = {key: label_payload(child, labels) for key, child in value.items()}
        vault_id = copied.get("vault_id")
        if isinstance(vault_id, str) and "vault_name" not in copied:
            copied.update(label_fields(labels, vault_id))
        return copied
    if isinstance(value, list):
        return [label_payload(child, labels) for child in value]
    return value


def _real(path: Path) -> Path:
    try:
        return path.expanduser().resolve()
    except (OSError, RuntimeError):
        return path.expanduser().absolute()


__all__ = ["VaultLabel", "label_fields", "label_payload", "vault_labels"]
