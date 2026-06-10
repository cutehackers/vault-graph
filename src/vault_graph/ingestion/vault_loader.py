from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

from vault_graph.errors import CatalogError
from vault_graph.ingestion.vault_catalog import QueryScope, VaultCatalogEntry
from vault_graph.ingestion.vault_frontmatter_reader import FrontmatterProjection, read_frontmatter


@dataclass(frozen=True)
class LoadedVaultDocument:
    vault_id: str
    root_path: Path
    path: str
    text: str
    raw_sha256: str
    content_hash: str
    frontmatter: FrontmatterProjection


class VaultLoader:
    def load_documents(self, *, entry: VaultCatalogEntry, scope: QueryScope) -> tuple[LoadedVaultDocument, ...]:
        if entry.vault_id not in scope.vault_ids:
            raise CatalogError(f"entry vault_id is not included in QueryScope: {entry.vault_id}")
        documents: list[LoadedVaultDocument] = []
        for content_scope in _actual_content_scopes(entry=entry, scope=scope):
            scope_root = entry.root_path / content_scope
            if not scope_root.exists():
                continue
            for markdown_path in sorted(scope_root.rglob("*.md")):
                if markdown_path.is_symlink() or not markdown_path.is_file():
                    continue
                relative_path = markdown_path.relative_to(entry.root_path).as_posix()
                text = markdown_path.read_text(encoding="utf-8")
                raw_sha256 = hashlib.sha256(text.encode("utf-8")).hexdigest()
                frontmatter = read_frontmatter(text)
                content_hash = hashlib.sha256(frontmatter.body.encode("utf-8")).hexdigest()
                documents.append(
                    LoadedVaultDocument(
                        vault_id=entry.vault_id,
                        root_path=entry.root_path,
                        path=relative_path,
                        text=text,
                        raw_sha256=raw_sha256,
                        content_hash=content_hash,
                        frontmatter=frontmatter,
                    )
                )
        return tuple(documents)


def _actual_content_scopes(*, entry: VaultCatalogEntry, scope: QueryScope) -> tuple[str, ...]:
    actual: list[str] = []
    for query_scope in scope.content_scopes:
        for entry_scope in entry.content_scopes:
            if _is_same_or_child(path=query_scope, parent=entry_scope):
                actual.append(query_scope)
            elif _is_same_or_child(path=entry_scope, parent=query_scope):
                actual.append(entry_scope)
    return tuple(dict.fromkeys(actual))


def _is_same_or_child(*, path: str, parent: str) -> bool:
    return path == parent or path.startswith(f"{parent}/")
