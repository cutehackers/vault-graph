from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass, replace
from datetime import UTC, datetime

from vault_graph.indexing.ingestion.chunker_selection import CHUNKER_VERSIONS
from vault_graph.indexing.ingestion.document_authority import assign_provenance_families, provenance_paths
from vault_graph.indexing.ingestion.document_normalizer import (
    ChunkSnapshot,
    DocumentNormalizer,
    DocumentSnapshot,
    NormalizedDocument,
)
from vault_graph.indexing.ingestion.document_readers import MarkdownDocumentReader
from vault_graph.indexing.ingestion.markdown_parser import PARSER_VERSION
from vault_graph.indexing.ingestion.session_group import (
    SESSION_GROUP_VERSION,
    ExchangeRanges,
    exchange_ranges,
    reprocess_session_groups,
    session_group_key,
)
from vault_graph.indexing.ingestion.vault_loader import LoadedVaultDocument, VaultLoader
from vault_graph.indexing.revision_planner import MetadataIndexPreview, MetadataRevisionPlan
from vault_graph.operation.scope.vault_catalog import QueryScope, VaultCatalog
from vault_graph.storage.interfaces.metadata_store import DocumentState, MetadataStore, SourceStat, SourceStatStore

# Versions of the code that turns a file into documents and chunks. A file read by other code is read
# again even when its size and mtime are unchanged (spec 2026-11-05 §4.3.3). Add any new reader,
# parser version here. Chunker versions come from chunker_selection.CHUNKER_VERSIONS, so a newly
# registered chunker makes every file read again once. SESSION_GROUP_VERSION makes a store written before
# session groups read every file once, so each session file gets its stored group key (§4.2.13).
INDEX_CODE_PARTS: tuple[str, ...] = (
    PARSER_VERSION,
    *CHUNKER_VERSIONS,
    MarkdownDocumentReader.version,
    SESSION_GROUP_VERSION,
)

Key = tuple[str, str]


def index_code(lineage: tuple[str | None, ...]) -> str:
    """Current index code plus the stored lineage of one document (parser, reader, options, chunker).

    A lineage that no longer matches what was recorded (another reader or chunker wrote the row)
    makes the file read again.
    """
    parts = (*INDEX_CODE_PARTS, *(part or "" for part in lineage))
    return hashlib.sha256("\n".join(parts).encode("utf-8")).hexdigest()[:16]


def _state_lineage(state: DocumentState) -> tuple[str | None, ...]:
    return (state.parser_version, state.reader_version, state.extraction_options_digest, state.chunker_version)


def _item_lineage(item: NormalizedDocument) -> tuple[str | None, ...]:
    document = item.document
    return (
        document.parser_version,
        document.reader_version,
        document.extraction_options_digest,
        _document_chunker_version(item),
    )


@dataclass(frozen=True)
class _Plan:
    plan: MetadataRevisionPlan
    normalized: tuple[NormalizedDocument, ...]
    # Size and mtime of each file read in this run, taken before it was read.
    read_stats: dict[Key, tuple[int, int]]
    lineages: dict[Key, tuple[str | None, ...]]


@dataclass(frozen=True)
class _Loaded:
    """Documents read in one run, after provenance families and session group rules."""

    normalized: tuple[NormalizedDocument, ...]
    # Keys whose file is gone.
    gone: tuple[Key, ...]
    # Size and mtime of each file read, taken before the read.
    read_stats: dict[Key, tuple[int, int]]
    # Session group warning lines (spec 2026-11-05 §4.2.13, §6).
    warnings: tuple[str, ...]


class MetadataIndexer:
    def __init__(self, *, catalog: VaultCatalog, metadata_store: MetadataStore) -> None:
        self._catalog = catalog
        self._metadata_store = metadata_store
        self._loader = VaultLoader()
        self._normalizer = DocumentNormalizer()

    def plan(self, *, scope: QueryScope, full: bool = False) -> MetadataRevisionPlan:
        return self._build_plan(scope=scope, full=full).plan

    def preview(self, *, scope: QueryScope, full: bool = False) -> MetadataIndexPreview:
        built = self._build_plan(scope=scope, full=full)
        plan, normalized = built.plan, built.normalized
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
        built = self._build_plan(scope=scope, full=full)
        plan, normalized = built.plan, built.normalized
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
        self._record_stats(built.read_stats, built.lineages, removed=plan.deleted_paths)
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
        loaded = self._load_with_families(
            scope, sorted(key for key in set(changed_paths) if _key_in_scope(vault_id=key[0], path=key[1], scope=scope))
        )
        normalized, gone, read_stats = loaded.normalized, loaded.gone, loaded.read_stats
        changed: list[tuple[str, str]] = []
        unchanged: list[tuple[str, str]] = []
        for item in normalized:
            key = (item.document.vault_id, item.document.path)
            current = self._metadata_store.document_state(*key)
            if current.document_id is None or self._changed(current=current, item=item):
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
        self._record_stats(
            read_stats,
            {(item.document.vault_id, item.document.path): _item_lineage(item) for item in normalized},
            removed=tuple(deleted),
        )
        return MetadataRevisionPlan(
            index_revision=index_revision,
            mode="paths",
            vault_ids=scope.vault_ids,
            changed_paths=tuple(sorted(changed)),
            unchanged_paths=tuple(sorted(unchanged)),
            deleted_paths=tuple(deleted),
            warnings=_plan_warnings(loaded),
        )

    def _build_plan(self, *, scope: QueryScope, full: bool) -> _Plan:
        index_revision = f"metadata-{datetime.now(UTC).strftime('%Y%m%d%H%M%S%f')}"
        current_by_key = {
            (state.vault_id, state.path): state
            for state in self._metadata_store.list_document_states(scope.vault_ids)
            if _state_in_scope(state=state, scope=scope)
        }
        on_disk = self._stat_files(scope)
        stat_store = self._metadata_store if isinstance(self._metadata_store, SourceStatStore) else None
        skipped: set[Key] = set()
        if full or stat_store is None:
            loaded = self._load_normalized(scope)
            normalized = loaded.normalized
            read_stats = {
                key: on_disk[key]
                for item in normalized
                if (key := (item.document.vault_id, item.document.path)) in on_disk
            }
        else:
            # Spec 2026-11-05 §4.3.3: read only files whose size, mtime or index code changed, plus
            # the provenance family and session group of each, so both stay whole (§4.2.13, as
            # apply_paths does). Skipped files join a group through their stored group key.
            recorded = stat_store.list_source_stats(scope.vault_ids)
            for key, (size, mtime_ns) in on_disk.items():
                state = current_by_key.get(key)
                stat = recorded.get(key)
                if (
                    state is not None
                    and not state.is_tombstoned
                    and stat is not None
                    and (stat.size, stat.mtime_ns) == (size, mtime_ns)
                    and stat.index_code == index_code(_state_lineage(state))
                ):
                    skipped.add(key)
            missing = [key for key, state in current_by_key.items() if key not in on_disk and not state.is_tombstoned]
            loaded = self._load_with_families(scope, sorted(set(on_disk) - skipped) + sorted(missing))
            normalized, read_stats = loaded.normalized, loaded.read_stats
        loaded_by_key = {(item.document.vault_id, item.document.path): item for item in normalized}
        changed: list[tuple[str, str]] = []
        unchanged: list[tuple[str, str]] = [key for key in skipped if key not in loaded_by_key]
        for key, item in loaded_by_key.items():
            current = current_by_key.get(key)
            if full or current is None or self._changed(current=current, item=item):
                changed.append(key)
            else:
                unchanged.append(key)
        deleted = [
            key
            for key, state in current_by_key.items()
            if key not in loaded_by_key and key not in skipped and not state.is_tombstoned
        ]
        plan = MetadataRevisionPlan(
            index_revision=index_revision,
            mode="full" if full else "incremental",
            vault_ids=scope.vault_ids,
            changed_paths=tuple(sorted(changed)),
            unchanged_paths=tuple(sorted(unchanged)),
            deleted_paths=tuple(sorted(deleted)),
            warnings=_plan_warnings(loaded),
        )
        return _Plan(
            plan=plan,
            normalized=normalized,
            read_stats=read_stats,
            lineages={(item.document.vault_id, item.document.path): _item_lineage(item) for item in normalized},
        )

    def _stat_files(self, scope: QueryScope) -> dict[Key, tuple[int, int]]:
        found: dict[Key, tuple[int, int]] = {}
        for vault_id in scope.vault_ids:
            entry = self._catalog.resolve(vault_id)
            for path in self._loader.list_paths(entry=entry, scope=scope):
                try:
                    stat = os.stat(entry.root_path / path)
                except OSError:
                    continue
                found[(vault_id, path)] = (stat.st_size, stat.st_mtime_ns)
        return found

    def _load_with_families(self, scope: QueryScope, keys: list[Key]) -> _Loaded:
        """Load ``keys``, every page their provenance links or indexed families reach, and every file of
        their session groups (spec 2026-11-05 §4.2.13).

        A session group is found from the read frontmatter and from the stored group key, so a deleted
        file and a file skipped by the precheck both open their group. A group member that is read only
        because of its group and cannot be read leaves the group incomplete: the session rules keep
        every v1 exchange and warn (§6), and the file's stored rows stay.
        """
        loaded: list[NormalizedDocument] = []
        gone: list[Key] = []
        read_stats: dict[Key, tuple[int, int]] = {}
        ranges: dict[Key, ExchangeRanges] = {}
        incomplete: dict[Key, list[str]] = {}
        members: dict[str, list[Key]] | None = None
        groups: dict[Key, list[Key]] | None = None
        pending = list(dict.fromkeys(keys))
        seen = set(pending)
        # Keys read only because a session group named them, with that group.
        pulled_by_group: dict[Key, Key] = {}
        while pending:
            vault_id, path = pending.pop(0)
            entry = self._catalog.resolve(vault_id)
            try:
                stat = os.stat(entry.root_path / path)
            except OSError:
                stat = None
            try:
                document = self._loader.load_path(entry=entry, path=path)
            except (OSError, UnicodeDecodeError):
                group_id = pulled_by_group.get((vault_id, path))
                if group_id is None:
                    raise
                incomplete.setdefault(group_id, []).append(path)
                continue
            linked: list[Key] = []
            group_ids: list[Key] = []
            if document is None:
                gone.append((vault_id, path))
            else:
                if stat is not None:
                    read_stats[(vault_id, path)] = (stat.st_size, stat.st_mtime_ns)
                item = self._normalizer.normalize(document)
                loaded.append(item)
                _add_ranges(ranges, document)
                linked.extend((vault_id, target) for target in provenance_paths(item.document.frontmatter))
                if (group := session_group_key(item.document.frontmatter)) is not None:
                    group_ids.append((vault_id, group))
            state = self._metadata_store.document_state(vault_id, path)
            family_id = state.provenance_family_id
            if family_id:
                if members is None:
                    members = _family_members(self._metadata_store.list_document_states(scope.vault_ids))
                linked.extend(members.get(family_id, ()))
            if state.session_group_key and not state.is_tombstoned:
                group_ids.append((vault_id, state.session_group_key))
            for key in linked:
                if key not in seen and _key_in_scope(vault_id=key[0], path=key[1], scope=scope):
                    seen.add(key)
                    pending.append(key)
            if group_ids and groups is None:
                groups = _group_members(self._metadata_store.list_document_states(scope.vault_ids))
            for group_id in dict.fromkeys(group_ids):
                for key in (groups or {}).get(group_id, ()):
                    if key not in seen and _key_in_scope(vault_id=key[0], path=key[1], scope=scope):
                        seen.add(key)
                        pending.append(key)
                        pulled_by_group[key] = group_id
        normalized, warnings = reprocess_session_groups(
            assign_provenance_families(tuple(loaded)), ranges, incomplete_groups=incomplete
        )
        return _Loaded(normalized=normalized, gone=tuple(gone), read_stats=read_stats, warnings=warnings)

    def _record_stats(
        self,
        read_stats: dict[Key, tuple[int, int]],
        lineages: dict[Key, tuple[str | None, ...]],
        *,
        removed: tuple[Key, ...],
    ) -> None:
        if not isinstance(self._metadata_store, SourceStatStore):
            return
        self._metadata_store.record_source_stats(
            tuple(
                SourceStat(
                    vault_id=key[0], path=key[1], size=size, mtime_ns=mtime_ns, index_code=index_code(lineages[key])
                )
                for key, (size, mtime_ns) in sorted(read_stats.items())
                if key in lineages
            ),
            removed=tuple(removed),
        )

    def _load_normalized(self, scope: QueryScope) -> _Loaded:
        normalized: list[NormalizedDocument] = []
        ranges: dict[Key, ExchangeRanges] = {}
        for vault_id in scope.vault_ids:
            entry = self._catalog.resolve(vault_id)
            for loaded in self._loader.load_documents(entry=entry, scope=scope):
                normalized.append(self._normalizer.normalize(loaded))
                _add_ranges(ranges, loaded)
        documents, warnings = reprocess_session_groups(assign_provenance_families(tuple(normalized)), ranges)
        return _Loaded(normalized=documents, gone=(), read_stats={}, warnings=warnings)

    def _changed(self, *, current: DocumentState, item: NormalizedDocument) -> bool:
        """Whether ``item`` differs from its stored row, chunks of a session file included.

        Session group rules can remove chunks of a file whose bytes did not change, so a session file
        also compares its chunk ids with the stored ones.
        """
        if _document_changed(current=current, item=item):
            return True
        if session_group_key(item.document.frontmatter) is None:
            return False
        stored = self._metadata_store.list_document_chunks(
            vault_id=item.document.vault_id, document_id=item.document.document_id
        )
        return sorted(chunk.chunk_id for chunk in stored) != sorted(chunk.chunk_id for chunk in item.chunks)


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
        or current.session_group_key != session_group_key(item.document.frontmatter)
    )


def _document_chunker_version(item: NormalizedDocument) -> str | None:
    return item.chunks[0].chunker_version if item.chunks else None


def _chunk_sort_key(chunk: ChunkSnapshot) -> tuple[str, str, str]:
    return (chunk.vault_id, chunk.path, chunk.chunk_id)


def _document_sort_key(document: DocumentSnapshot) -> tuple[str, str, str]:
    return (document.vault_id, document.path, document.document_id)


def _plan_warnings(loaded: _Loaded) -> tuple[str, ...]:
    return (
        *(f"{item.document.path}: {warning}" for item in loaded.normalized for warning in item.warnings),
        *loaded.warnings,
    )


def _add_ranges(ranges: dict[Key, ExchangeRanges], loaded: LoadedVaultDocument) -> None:
    """Exchange time ranges of a session file, for the session group rules. Other files add nothing."""
    if loaded.extracted_document is not None and session_group_key(loaded.frontmatter.data) is not None:
        ranges[(loaded.vault_id, loaded.path)] = exchange_ranges(loaded.extracted_document)


def _group_members(states: tuple[DocumentState, ...]) -> dict[Key, list[Key]]:
    """Indexed ``(vault_id, path)`` keys by ``(vault_id, session group key)``."""
    members: dict[Key, list[Key]] = {}
    for state in states:
        if state.session_group_key and state.document_id is not None and not state.is_tombstoned:
            members.setdefault((state.vault_id, state.session_group_key), []).append((state.vault_id, state.path))
    return members


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
