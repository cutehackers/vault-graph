"""Find the files of linked Vaults that changed since the last index (2026-11-02 발견8, 정리 발견2).

Reads the same ``*.md`` files as ``VaultLoader`` but does not parse or chunk them: each file's
SHA-256 is compared with the indexed ``raw_sha256``, so a time limit can be checked after every
file. A change only ``vg index`` sees (a new parser version) is left to ``vg index``.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from dataclasses import dataclass
from time import monotonic

from vault_graph.operation.scope.vault_catalog import VaultCatalog
from vault_graph.storage.interfaces.metadata_store import MetadataStore


@dataclass(frozen=True)
class ChangeScan:
    """``changes`` maps each Vault id to (changed paths, deleted paths). ``documents`` counts indexed files."""

    changes: dict[str, tuple[set[str], set[str]]]
    documents: int


def scan_changes(
    catalog: VaultCatalog,
    metadata_store: MetadataStore,
    vault_ids: tuple[str, ...],
    *,
    deadline: float,
    clock: Callable[[], float] = monotonic,
) -> ChangeScan | None:
    """Changed and deleted paths per Vault and the indexed document count. None when time ran out."""
    states = metadata_store.list_document_states(vault_ids)
    changes: dict[str, tuple[set[str], set[str]]] = {}
    documents = 0
    for vault_id in vault_ids:
        entry = catalog.resolve(vault_id)
        known = {
            state.path: state
            for state in states
            if state.vault_id == vault_id and _in_scopes(state.path, entry.content_scopes)
        }
        seen: set[str] = set()
        changed: set[str] = set()
        for content_scope in entry.content_scopes:
            scope_root = entry.root_path / content_scope
            if not scope_root.exists():
                continue
            for markdown_path in scope_root.rglob("*.md"):
                if clock() > deadline:
                    return None
                if markdown_path.is_symlink() or not markdown_path.is_file():
                    continue
                relative = markdown_path.relative_to(entry.root_path).as_posix()
                if relative in seen:
                    continue
                seen.add(relative)
                state = known.get(relative)
                digest = hashlib.sha256(markdown_path.read_bytes()).hexdigest()
                if state is None or state.is_tombstoned or state.raw_sha256 != digest:
                    changed.add(relative)
        deleted = {path for path, state in known.items() if path not in seen and not state.is_tombstoned}
        changes[vault_id] = (changed, deleted)
        documents += sum(1 for state in known.values() if not state.is_tombstoned)
    return ChangeScan(changes=changes, documents=documents)


def _in_scopes(path: str, content_scopes: tuple[str, ...]) -> bool:
    return any(path == scope or path.startswith(f"{scope}/") for scope in content_scopes)


__all__ = ["ChangeScan", "scan_changes"]
