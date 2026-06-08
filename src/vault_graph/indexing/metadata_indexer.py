from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime

from vault_graph.indexing.revision_planner import MetadataIndexPreview, MetadataRevisionPlan
from vault_graph.ingestion.document_normalizer import ChunkSnapshot, DocumentNormalizer, NormalizedDocument
from vault_graph.ingestion.vault_catalog import QueryScope, VaultCatalog
from vault_graph.ingestion.vault_loader import VaultLoader
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
        changed_chunks = tuple(
            replace(chunk, index_revision=plan.index_revision)
            for item in normalized
            if (item.document.vault_id, item.document.path) in changed_keys
            for chunk in item.chunks
        )
        unchanged_chunks = tuple(
            chunk
            for chunk in self._metadata_store.list_chunks(scope)
            if (chunk.vault_id, chunk.path) in unchanged_keys
        )
        return MetadataIndexPreview(
            plan=plan,
            chunks_after_apply=tuple(sorted(changed_chunks + unchanged_chunks, key=_chunk_sort_key)),
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
            warnings=(),
        )
        return plan, normalized

    def _load_normalized(self, scope: QueryScope) -> tuple[NormalizedDocument, ...]:
        normalized: list[NormalizedDocument] = []
        for vault_id in scope.vault_ids:
            entry = self._catalog.resolve(vault_id)
            for loaded in self._loader.load_documents(entry=entry, scope=scope):
                normalized.append(self._normalizer.normalize(loaded))
        return tuple(normalized)


def _document_changed(*, current: DocumentState, item: NormalizedDocument) -> bool:
    return (
        current.is_tombstoned
        or current.frontmatter_hash != item.document.frontmatter_hash
        or current.content_hash != item.document.content_hash
        or current.raw_sha256 != item.document.raw_sha256
        or current.parser_version != item.document.parser_version
        or current.chunker_version != _document_chunker_version(item)
    )


def _document_chunker_version(item: NormalizedDocument) -> str | None:
    return item.chunks[0].chunker_version if item.chunks else None


def _chunk_sort_key(chunk: ChunkSnapshot) -> tuple[str, str, str]:
    return (chunk.vault_id, chunk.path, chunk.chunk_id)


def _state_in_scope(*, state: DocumentState, scope: QueryScope) -> bool:
    return any(
        state.path == content_scope or state.path.startswith(f"{content_scope}/")
        for content_scope in scope.content_scopes
    )
