from __future__ import annotations

from pathlib import PurePosixPath
from typing import Protocol

from vault_graph.ingestion.document_normalizer import ChunkSnapshot, DocumentSnapshot
from vault_graph.ingestion.vault_catalog import ALLOWED_CONTENT_ROOTS, QueryScope
from vault_graph.storage.interfaces.metadata_store import MetadataStore


class GraphSourceStore(Protocol):
    def list_chunks(self, scope: QueryScope) -> tuple[ChunkSnapshot, ...]: ...

    def resolve_document(self, *, vault_id: str, document_id: str) -> DocumentSnapshot | None: ...


class MetadataGraphSourceStore:
    def __init__(self, metadata_store: MetadataStore) -> None:
        self._metadata_store = metadata_store

    def list_chunks(self, scope: QueryScope) -> tuple[ChunkSnapshot, ...]:
        return self._metadata_store.list_chunks(scope)

    def resolve_document(self, *, vault_id: str, document_id: str) -> DocumentSnapshot | None:
        document = self._metadata_store.resolve_document(document_id)
        if document is None or document.vault_id != vault_id:
            return None
        return document


class PreviewGraphSourceStore:
    def __init__(self, *, chunks: tuple[ChunkSnapshot, ...], documents: tuple[DocumentSnapshot, ...]) -> None:
        self._chunks = chunks
        self._documents = {(document.vault_id, document.document_id): document for document in documents}

    def list_chunks(self, scope: QueryScope) -> tuple[ChunkSnapshot, ...]:
        return tuple(
            chunk
            for chunk in self._chunks
            if chunk.vault_id in scope.vault_ids
            and any(
                chunk.path == content_scope or chunk.path.startswith(f"{content_scope}/")
                for content_scope in scope.content_scopes
            )
        )

    def resolve_document(self, *, vault_id: str, document_id: str) -> DocumentSnapshot | None:
        return self._documents.get((vault_id, document_id))


class GraphExtractionContext:
    def __init__(
        self,
        *,
        scope: QueryScope,
        current_documents: tuple[DocumentSnapshot, ...],
        source_store: GraphSourceStore,
    ) -> None:
        self.scope = scope
        self.source_store = source_store
        self.current_document_paths = tuple(sorted(document.path for document in current_documents))
        self._documents_by_path = {(document.vault_id, document.path): document for document in current_documents}
        self._documents_by_basename = _basename_index(current_documents)

    def resolve_local_document_link(self, source_path: str, raw_target: str) -> DocumentSnapshot | None:
        target_path = _normalize_link_target(source_path=source_path, raw_target=raw_target)
        if target_path is None:
            return None
        vault_id = self.scope.vault_ids[0]
        exact = self._documents_by_path.get((vault_id, target_path))
        if exact is not None:
            return exact
        if "/" not in target_path:
            matches = self._documents_by_basename.get((vault_id, _ensure_md_suffix(target_path)), ())
            if len(matches) == 1:
                return matches[0]
        return None


def _normalize_link_target(*, source_path: str, raw_target: str) -> str | None:
    target = raw_target.strip()
    if not target or target.startswith("#") or "://" in target or target.startswith("mailto:"):
        return None
    target = target.split("|", 1)[0].split("#", 1)[0].strip()
    if not target:
        return None
    if target.startswith("/"):
        target = target.removeprefix("/")
    target = _ensure_md_suffix(target)
    parts = PurePosixPath(target).parts
    if not parts:
        return None
    if parts[0] in ALLOWED_CONTENT_ROOTS:
        return _normalize_vault_relative_path(target)
    if "/" not in target:
        return target
    return _normalize_vault_relative_path(str(PurePosixPath(source_path).parent / target))


def _ensure_md_suffix(path: str) -> str:
    return path if path.endswith(".md") else f"{path}.md"


def _basename_index(
    documents: tuple[DocumentSnapshot, ...],
) -> dict[tuple[str, str], tuple[DocumentSnapshot, ...]]:
    indexed: dict[tuple[str, str], list[DocumentSnapshot]] = {}
    for document in documents:
        key = (document.vault_id, PurePosixPath(document.path).name)
        indexed.setdefault(key, []).append(document)
    return {
        key: tuple(sorted(value, key=lambda document: (document.vault_id, document.path, document.document_id)))
        for key, value in indexed.items()
    }


def _normalize_vault_relative_path(path: str) -> str | None:
    stack: list[str] = []
    for part in PurePosixPath(path).parts:
        if part in {"", "."}:
            continue
        if part == "..":
            if not stack:
                return None
            stack.pop()
            continue
        stack.append(part)
    if not stack or stack[0] not in ALLOWED_CONTENT_ROOTS:
        return None
    return "/".join(stack)
