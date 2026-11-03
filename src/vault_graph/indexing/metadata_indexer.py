from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime

from vault_graph.indexing.ingestion.document_authority import assign_provenance_families, provenance_paths
from vault_graph.indexing.ingestion.document_normalizer import (
    ChunkSnapshot,
    DocumentNormalizer,
    DocumentSnapshot,
    NormalizedDocument,
)
from vault_graph.indexing.ingestion.vault_loader import VaultLoader
from vault_graph.indexing.revision_planner import MetadataIndexPreview, MetadataRevisionPlan
from vault_graph.operation.scope.vault_catalog import QueryScope, VaultCatalog
from vault_graph.storage.interfaces.metadata_store import DocumentState, MetadataStore


class MetadataIndexer:
    def __init__(self, *, catalog: VaultCatalog, metadata_store: MetadataStore) -> None:
        self._catalog = catalog
        self._metadata_store = metadata_store
        self._loader = VaultLoader()
        self._normalizer = DocumentNormalizer()

    def plan(self, *, scope: QueryScope, full: bool = False) -> MetadataRevisionPlan:
        plan, _ = self._build_plan(scope=scope, full=full)
        return plan

    def preview(self, *, scope: QueryScope, full: bool = False) -> MetadataIndexPreview:
        plan, normalized = self._build_plan(scope=scope, full=full)
        changed_keys = set(plan.changed_paths)
        unchanged_keys = set(plan.unchanged_paths)
        changed_documents = tuple(
            replace(item.document, index_revision=plan.index_revision)
            for item in normalized
            if (item.document.vault_id, item.document.path) in changed_keys
        )
        unchanged_documents = tuple(
            document
            for state in self._metadata_store.list_document_states(scope.vault_ids)
            if (state.vault_id, state.path) in unchanged_keys
            and state.document_id is not None
            and (document := self._metadata_store.resolve_document(state.document_id)) is not None
            and document.vault_id == state.vault_id
        )
        changed_chunks = tuple(
            replace(chunk, index_revision=plan.index_revision)
            for item in normalized
            if (item.document.vault_id, item.document.path) in changed_keys
            for chunk in item.chunks
        )
        unchanged_chunks = tuple(
            chunk for chunk in self._metadata_store.list_chunks(scope) if (chunk.vault_id, chunk.path) in unchanged_keys
        )
        return MetadataIndexPreview(
            plan=plan,
            chunks_after_apply=tuple(sorted(changed_chunks + unchanged_chunks, key=_chunk_sort_key)),
            documents_after_apply=tuple(
                sorted(changed_documents + unchanged_documents, key=_document_sort_key),
            ),
        )

    def apply(self, *, scope: QueryScope, full: bool = False) -> MetadataRevisionPlan:
        plan, normalized = self._build_plan(scope=scope, full=full)
        changed_keys = set(plan.changed_paths)
        changed_documents = [
            item.document for item in normalized if (item.document.vault_id, item.document.path) in changed_keys
        ]
        changed_chunks = [
            chunk
            for item in normalized
            if (item.document.vault_id, item.document.path) in changed_keys
            for chunk in item.chunks
        ]
        self._metadata_store.apply_metadata_revision(
            index_revision=plan.index_revision,
            documents=changed_documents,
            chunks=changed_chunks,
            tombstones=list(plan.deleted_paths),
        )
        return plan

    def apply_paths(
        self,
        *,
        scope: QueryScope,
        changed_paths: tuple[tuple[str, str], ...],
        deleted_paths: tuple[tuple[str, str], ...],
    ) -> MetadataRevisionPlan:
        """Index only the listed ``(vault_id, path)`` files, so the cost follows the list, not the Vault.

        A listed changed file that is gone is deleted. Paths outside ``scope`` are ignored.

        Provenance families need every member, so the listed files are read together with their
        family: the pages they name in a provenance field (``supersedes`` and so on), and the pages
        that shared an indexed family with them. Without that, a new page that supersedes an
        unlisted one splits the family until the next whole-Vault ``apply`` and search shows both
        (2026-11-03 발견13). Family members whose result is the same are reported unchanged.
        """
        index_revision = f"metadata-{datetime.now(UTC).strftime('%Y%m%d%H%M%S%f')}"
        loaded: list[NormalizedDocument] = []
        gone: list[tuple[str, str]] = []
        members: dict[str, list[tuple[str, str]]] | None = None
        pending = sorted(key for key in set(changed_paths) if _key_in_scope(vault_id=key[0], path=key[1], scope=scope))
        seen = set(pending)
        while pending:
            vault_id, path = pending.pop(0)
            document = self._loader.load_path(entry=self._catalog.resolve(vault_id), path=path)
            linked: list[tuple[str, str]] = []
            if document is None:
                gone.append((vault_id, path))
            else:
                item = self._normalizer.normalize(document)
                loaded.append(item)
                linked.extend((vault_id, target) for target in provenance_paths(item.document.frontmatter))
            family_id = self._metadata_store.document_state(vault_id, path).provenance_family_id
            if family_id:
                if members is None:
                    members = _family_members(self._metadata_store.list_document_states(scope.vault_ids))
                linked.extend(members.get(family_id, ()))
            for key in linked:
                if key not in seen and _key_in_scope(vault_id=key[0], path=key[1], scope=scope):
                    seen.add(key)
                    pending.append(key)
        normalized = assign_provenance_families(tuple(loaded))
        changed: list[tuple[str, str]] = []
        unchanged: list[tuple[str, str]] = []
        for item in normalized:
            key = (item.document.vault_id, item.document.path)
            current = self._metadata_store.document_state(*key)
            if current.document_id is None or _document_changed(current=current, item=item):
                changed.append(key)
            else:
                unchanged.append(key)
        deleted = sorted(
            key
            for key in set(deleted_paths) | set(gone)
            if _key_in_scope(vault_id=key[0], path=key[1], scope=scope)
            and (state := self._metadata_store.document_state(*key)).document_id is not None
            and not state.is_tombstoned
        )
        changed_keys = set(changed)
        changed_items = [item for item in normalized if (item.document.vault_id, item.document.path) in changed_keys]
        self._metadata_store.apply_metadata_revision(
            index_revision=index_revision,
            documents=[item.document for item in changed_items],
            chunks=[chunk for item in changed_items for chunk in item.chunks],
            tombstones=deleted,
        )
        return MetadataRevisionPlan(
            index_revision=index_revision,
            mode="paths",
            vault_ids=scope.vault_ids,
            changed_paths=tuple(sorted(changed)),
            unchanged_paths=tuple(sorted(unchanged)),
            deleted_paths=tuple(deleted),
            warnings=tuple(f"{item.document.path}: {warning}" for item in normalized for warning in item.warnings),
        )

    def _build_plan(
        self,
        *,
        scope: QueryScope,
        full: bool,
    ) -> tuple[MetadataRevisionPlan, tuple[NormalizedDocument, ...]]:
        index_revision = f"metadata-{datetime.now(UTC).strftime('%Y%m%d%H%M%S%f')}"
        normalized = self._load_normalized(scope)
        current_by_key = {
            (state.vault_id, state.path): state
            for state in self._metadata_store.list_document_states(scope.vault_ids)
            if _state_in_scope(state=state, scope=scope)
        }
        loaded_by_key = {(item.document.vault_id, item.document.path): item for item in normalized}
        changed: list[tuple[str, str]] = []
        unchanged: list[tuple[str, str]] = []
        for key, item in loaded_by_key.items():
            current = current_by_key.get(key)
            if full or current is None or _document_changed(current=current, item=item):
                changed.append(key)
            else:
                unchanged.append(key)
        deleted = [key for key, state in current_by_key.items() if key not in loaded_by_key and not state.is_tombstoned]
        plan = MetadataRevisionPlan(
            index_revision=index_revision,
            mode="full" if full else "incremental",
            vault_ids=scope.vault_ids,
            changed_paths=tuple(sorted(changed)),
            unchanged_paths=tuple(sorted(unchanged)),
            deleted_paths=tuple(sorted(deleted)),
            warnings=tuple(f"{item.document.path}: {warning}" for item in normalized for warning in item.warnings),
        )
        return plan, normalized

    def _load_normalized(self, scope: QueryScope) -> tuple[NormalizedDocument, ...]:
        normalized: list[NormalizedDocument] = []
        for vault_id in scope.vault_ids:
            entry = self._catalog.resolve(vault_id)
            for loaded in self._loader.load_documents(entry=entry, scope=scope):
                normalized.append(self._normalizer.normalize(loaded))
        return assign_provenance_families(tuple(normalized))


def _document_changed(*, current: DocumentState, item: NormalizedDocument) -> bool:
    return (
        current.is_tombstoned
        or current.frontmatter_hash != item.document.frontmatter_hash
        or current.content_hash != item.document.content_hash
        or current.raw_sha256 != item.document.raw_sha256
        or current.parser_version != item.document.parser_version
        or current.format != item.document.format
        or current.reader_name != item.document.reader_name
        or current.reader_version != item.document.reader_version
        or current.extraction_options_digest != item.document.extraction_options_digest
        or current.chunker_version != _document_chunker_version(item)
        or current.source_role != item.document.source_role
        or current.provenance_family_id != item.document.provenance_family_id
    )


def _document_chunker_version(item: NormalizedDocument) -> str | None:
    return item.chunks[0].chunker_version if item.chunks else None


def _chunk_sort_key(chunk: ChunkSnapshot) -> tuple[str, str, str]:
    return (chunk.vault_id, chunk.path, chunk.chunk_id)


def _document_sort_key(document: DocumentSnapshot) -> tuple[str, str, str]:
    return (document.vault_id, document.path, document.document_id)


def _family_members(states: tuple[DocumentState, ...]) -> dict[str, list[tuple[str, str]]]:
    """Indexed ``(vault_id, path)`` keys by provenance family id."""
    members: dict[str, list[tuple[str, str]]] = {}
    for state in states:
        if state.provenance_family_id and state.document_id is not None and not state.is_tombstoned:
            members.setdefault(state.provenance_family_id, []).append((state.vault_id, state.path))
    return members


def _key_in_scope(*, vault_id: str, path: str, scope: QueryScope) -> bool:
    return vault_id in scope.vault_ids and any(
        path == content_scope or path.startswith(f"{content_scope}/") for content_scope in scope.content_scopes
    )


def _state_in_scope(*, state: DocumentState, scope: QueryScope) -> bool:
    return any(
        state.path == content_scope or state.path.startswith(f"{content_scope}/")
        for content_scope in scope.content_scopes
    )
