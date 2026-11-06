"""SQLite vector manifest table and the vector store adapter that keeps it in step with Chroma."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from pathlib import Path
from typing import Any, cast

from vault_graph.errors import VectorStoreError
from vault_graph.indexing.ingestion.document_authority import DocumentRole
from vault_graph.operation.scope.vault_catalog import QueryScope
from vault_graph.storage.interfaces.store_health import StoreHealth
from vault_graph.storage.interfaces.text_embeddings import EmbeddingModelSpec
from vault_graph.storage.interfaces.vector_manifest_store import (
    VectorBackendListing,
    VectorManifestRead,
    VectorManifestRow,
    VectorManifestStore,
)
from vault_graph.storage.interfaces.vector_store import (
    VectorEmbeddingRecord,
    VectorHit,
    VectorManifestRecord,
    VectorQuery,
    VectorStore,
    VectorTombstone,
)

MANIFEST_FILE_NAME = "manifest.sqlite3"
# Rows read from Chroma per rebuild query. Pages use keyset order, so no query binds more than a few variables.
CHROMA_PAGE_SIZE = 1000

_COLUMNS = (
    "vector_id",
    "vault_id",
    "document_id",
    "chunk_id",
    "content_scope",
    "embedding_model_name",
    "embedding_model_version",
    "embedding_dimensions",
    "embedding_spec_version",
    "source_chunk_hash",
    "chunker_version",
    "metadata_index_revision",
    "vector_index_revision",
    "backend",
    "backend_schema_version",
    "source_role",
    "provenance_family_id",
)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS vector_manifest (
    vector_id TEXT PRIMARY KEY,
    vault_id TEXT NOT NULL,
    document_id TEXT NOT NULL,
    chunk_id TEXT NOT NULL,
    content_scope TEXT NOT NULL,
    embedding_model_name TEXT NOT NULL,
    embedding_model_version TEXT NOT NULL,
    embedding_dimensions INTEGER NOT NULL,
    embedding_spec_version TEXT NOT NULL,
    source_chunk_hash TEXT NOT NULL,
    chunker_version TEXT NOT NULL,
    metadata_index_revision TEXT NOT NULL,
    vector_index_revision TEXT NOT NULL,
    backend TEXT NOT NULL,
    backend_schema_version TEXT NOT NULL,
    source_role TEXT NOT NULL,
    provenance_family_id TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS vector_manifest_vault ON vector_manifest (vault_id);
"""


def manifest_path_for_vector_path(vector_path: Path) -> Path:
    """`<generation>/vector/manifest.sqlite3` for the Chroma path `<generation>/vector/chroma`."""
    return vector_path.parent / MANIFEST_FILE_NAME


class SQLiteVectorManifestStore(VectorManifestStore):
    def __init__(self, path: Path) -> None:
        self._path = path

    def exists(self) -> bool:
        if not self._path.exists():
            return False
        with self._connect(create=False) as connection:
            row = connection.execute(
                "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'vector_manifest'"
            ).fetchone()
        return row is not None

    def rows(self, vault_ids: tuple[str, ...]) -> tuple[VectorManifestRow, ...]:
        if not vault_ids or not self.exists():
            return ()
        placeholders = ", ".join("?" for _ in vault_ids)
        with self._connect(create=False) as connection:
            fetched = connection.execute(
                f"SELECT {', '.join(_COLUMNS)} FROM vector_manifest WHERE vault_id IN ({placeholders}) "
                "ORDER BY vault_id, chunk_id, vector_id",
                vault_ids,
            ).fetchall()
        return tuple(_row_from_sql(row) for row in fetched)

    def count(self, vault_id: str) -> int:
        if not self.exists():
            return 0
        with self._connect(create=False) as connection:
            row = connection.execute("SELECT COUNT(*) FROM vector_manifest WHERE vault_id = ?", (vault_id,)).fetchone()
        return int(row[0])

    def apply(
        self,
        upserts: tuple[VectorManifestRow, ...],
        metadata_updates: tuple[VectorManifestRow, ...],
        deletions: tuple[VectorTombstone, ...],
    ) -> None:
        with self._connect(create=True) as connection:
            connection.executemany(
                "DELETE FROM vector_manifest WHERE vector_id = ? AND vault_id = ? AND chunk_id = ? "
                "AND embedding_model_name = ? AND embedding_model_version = ? "
                "AND embedding_dimensions = ? AND embedding_spec_version = ?",
                (
                    (
                        item.vector_id,
                        item.vault_id,
                        item.chunk_id,
                        item.embedding_spec.model_name,
                        item.embedding_spec.model_version,
                        item.embedding_spec.dimensions,
                        item.embedding_spec.spec_version,
                    )
                    for item in deletions
                ),
            )
            _insert_rows(connection, upserts)
            _insert_rows(connection, metadata_updates)

    def replace_vault_rows(self, vault_ids: tuple[str, ...], rows: tuple[VectorManifestRow, ...]) -> None:
        with self._connect(create=True) as connection:
            connection.executemany("DELETE FROM vector_manifest WHERE vault_id = ?", ((vault,) for vault in vault_ids))
            _insert_rows(connection, rows)

    @contextmanager
    def _connect(self, *, create: bool) -> Iterator[sqlite3.Connection]:
        if create:
            self._path.parent.mkdir(parents=True, exist_ok=True)
        try:
            connection = sqlite3.connect(self._path)
        except sqlite3.Error as exc:
            raise VectorStoreError(f"vector manifest unavailable: {exc}") from exc
        try:
            with connection:
                if create:
                    connection.executescript(_SCHEMA)
                yield connection
        except sqlite3.Error as exc:
            raise VectorStoreError(f"vector manifest failed: {exc}") from exc
        finally:
            connection.close()


class ChromaSQLiteListing(VectorBackendListing):
    """Counts and pages Chroma's own SQLite rows without the Chroma client.

    Counting needs no listing call, and rebuild pages by row id, so neither binds one SQL
    variable per vector (the cause of Chroma's "too many SQL variables").
    """

    def __init__(self, chroma_path: Path, *, collection_prefix: str, backend: str) -> None:
        self._database_path = chroma_path / "chroma.sqlite3"
        self._collection_pattern = f"{collection_prefix}_%"
        self._backend = backend

    def counts(self, vault_ids: tuple[str, ...]) -> Mapping[str, int]:
        counts = dict.fromkeys(vault_ids, 0)
        if not vault_ids or not self._database_path.exists():
            return counts
        placeholders = ", ".join("?" for _ in vault_ids)
        with self._connect() as connection:
            if connection is None:
                return counts
            for row in connection.execute(
                f"""SELECT vm.string_value, COUNT(*) FROM embeddings e
                   JOIN segments s ON s.id = e.segment_id
                   JOIN collections c ON c.id = s.collection
                   JOIN embedding_metadata vm ON vm.id = e.id AND vm.key = 'vault_id'
                   WHERE c.name LIKE ? AND vm.string_value IN ({placeholders})
                   GROUP BY vm.string_value""",
                (self._collection_pattern, *vault_ids),
            ):
                counts[str(row[0])] = int(row[1])
        return counts

    def rows(self, vault_ids: tuple[str, ...]) -> tuple[VectorManifestRecord, ...]:
        if not vault_ids or not self._database_path.exists():
            return ()
        records: list[VectorManifestRecord] = []
        with self._connect() as connection:
            if connection is None:
                return ()
            for vault_id in vault_ids:
                after = -1
                while True:
                    page = connection.execute(
                        """SELECT p.id, p.embedding_id, em.key, em.string_value, em.int_value,
                              em.float_value, em.bool_value
                           FROM (
                               SELECT e.id, e.embedding_id FROM embeddings e
                               JOIN segments s ON s.id = e.segment_id
                               JOIN collections c ON c.id = s.collection
                               JOIN embedding_metadata vm ON vm.id = e.id AND vm.key = 'vault_id'
                               WHERE c.name LIKE ? AND vm.string_value = ? AND e.id > ?
                               ORDER BY e.id LIMIT ?
                           ) p
                           JOIN embedding_metadata em ON em.id = p.id
                           ORDER BY p.id""",
                        (self._collection_pattern, vault_id, after, CHROMA_PAGE_SIZE),
                    ).fetchall()
                    if not page:
                        break
                    grouped: dict[int, tuple[str, dict[str, Any]]] = {}
                    for row in page:
                        entry = grouped.setdefault(int(row[0]), (str(row[1]), {}))
                        entry[1][str(row[2])] = _metadata_value(row[3:])
                    records.extend(
                        _record_from_metadata(record_id, metadata, self._backend)
                        for record_id, metadata in grouped.values()
                    )
                    after = max(grouped)
                    if len(grouped) < CHROMA_PAGE_SIZE:
                        break
        return tuple(sorted(records, key=lambda row: (row.vault_id, row.chunk_id, row.vector_id)))

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection | None]:
        try:
            connection = sqlite3.connect(f"file:{self._database_path}?mode=ro", uri=True)
        except sqlite3.Error as exc:
            raise VectorStoreError(f"vector store unavailable: {exc}") from exc
        try:
            tables = {str(row[0]) for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
            if not {"collections", "segments", "embeddings", "embedding_metadata"} <= tables:
                yield None
            else:
                yield connection
        except sqlite3.Error as exc:
            raise VectorStoreError(f"vector store read failed: {exc}") from exc
        finally:
            connection.close()


class ManifestTrackedVectorStore(VectorStore):
    """A vector store whose manifest table follows every successful write.

    The table is written only after the wrapped store accepted the batch. The plan reads
    `manifest_rows`, which rebuilds a vault's rows from the backend listing when the table is
    missing or its row count differs from the backend's.
    """

    def __init__(
        self,
        inner: VectorStore,
        *,
        manifest: VectorManifestStore,
        listing: VectorBackendListing,
        backend: str,
    ) -> None:
        self._inner = inner
        self._manifest = manifest
        self._listing = listing
        self._backend = backend

    def apply_vector_revision(
        self,
        *,
        vector_index_revision: str,
        records: tuple[VectorEmbeddingRecord, ...],
        tombstones: tuple[VectorTombstone, ...],
    ) -> None:
        self._inner.apply_vector_revision(
            vector_index_revision=vector_index_revision, records=records, tombstones=tombstones
        )
        self._manifest.apply(tuple(self._row_for_record(record) for record in records), (), tombstones)

    def manifest_rows(self, vault_ids: tuple[str, ...]) -> VectorManifestRead:
        vault_ids = tuple(dict.fromkeys(vault_ids))
        present = self._manifest.exists()
        backend_counts = self._listing.counts(vault_ids)
        stale = tuple(
            vault for vault in vault_ids if not present or self._manifest.count(vault) != backend_counts.get(vault, 0)
        )
        warnings: tuple[str, ...] = ()
        if stale:
            rebuilt = tuple(VectorManifestRow.from_record(row) for row in self._listing.rows(stale))
            self._manifest.replace_vault_rows(stale, rebuilt)
            reason = "table missing" if not present else "row count differs from the vector store"
            warnings = (f"vector manifest table rebuilt from the vector store for {', '.join(stale)}: {reason}",)
        return VectorManifestRead(rows=self._manifest.rows(vault_ids), warnings=warnings)

    def search(self, query: VectorQuery) -> tuple[VectorHit, ...]:
        return self._inner.search(query)

    def health(self) -> StoreHealth:
        return self._inner.health()

    def export_manifest(self, scope: QueryScope) -> tuple[VectorManifestRecord, ...]:
        return self._inner.export_manifest(scope)

    def close(self) -> None:
        close = getattr(self._inner, "close", None)
        if callable(close):
            close()

    def _row_for_record(self, record: VectorEmbeddingRecord) -> VectorManifestRow:
        return VectorManifestRow(
            vector_id=record.vector_id,
            vault_id=record.vault_id,
            document_id=record.document_id,
            chunk_id=record.chunk_id,
            content_scope=record.content_scope,
            embedding_spec=record.embedding.model_spec,
            source_chunk_hash=record.source_chunk_hash,
            chunker_version=record.chunker_version,
            metadata_index_revision=record.metadata_index_revision,
            vector_index_revision=record.vector_index_revision,
            backend=self._backend,
            backend_schema_version=record.backend_schema_version,
            source_role=record.source_role,
            provenance_family_id=record.provenance_family_id,
        )


def _insert_rows(connection: sqlite3.Connection, rows: tuple[VectorManifestRow, ...]) -> None:
    connection.executemany(
        f"INSERT OR REPLACE INTO vector_manifest ({', '.join(_COLUMNS)}) VALUES ({', '.join('?' for _ in _COLUMNS)})",
        (_row_to_sql(row) for row in rows),
    )


def _row_to_sql(row: VectorManifestRow) -> tuple[str | int, ...]:
    return (
        row.vector_id,
        row.vault_id,
        row.document_id,
        row.chunk_id,
        row.content_scope,
        row.embedding_spec.model_name,
        row.embedding_spec.model_version,
        row.embedding_spec.dimensions,
        row.embedding_spec.spec_version,
        row.source_chunk_hash,
        row.chunker_version,
        row.metadata_index_revision,
        row.vector_index_revision,
        row.backend,
        row.backend_schema_version,
        row.source_role,
        row.provenance_family_id,
    )


def _row_from_sql(row: tuple[Any, ...]) -> VectorManifestRow:
    values = dict(zip(_COLUMNS, row, strict=True))
    return VectorManifestRow(
        vector_id=str(values["vector_id"]),
        vault_id=str(values["vault_id"]),
        document_id=str(values["document_id"]),
        chunk_id=str(values["chunk_id"]),
        content_scope=str(values["content_scope"]),
        embedding_spec=EmbeddingModelSpec(
            model_name=str(values["embedding_model_name"]),
            model_version=str(values["embedding_model_version"]),
            dimensions=int(values["embedding_dimensions"]),
            spec_version=str(values["embedding_spec_version"]),
        ),
        source_chunk_hash=str(values["source_chunk_hash"]),
        chunker_version=str(values["chunker_version"]),
        metadata_index_revision=str(values["metadata_index_revision"]),
        vector_index_revision=str(values["vector_index_revision"]),
        backend=str(values["backend"]),
        backend_schema_version=str(values["backend_schema_version"]),
        source_role=cast(DocumentRole, str(values["source_role"])),
        provenance_family_id=str(values["provenance_family_id"]),
    )


def _record_from_metadata(record_id: str, metadata: Mapping[str, Any], backend: str) -> VectorManifestRecord:
    return VectorManifestRecord(
        vector_id=record_id,
        vault_id=str(metadata["vault_id"]),
        document_id=str(metadata["document_id"]),
        chunk_id=str(metadata["chunk_id"]),
        content_scope=str(metadata["content_scope"]),
        embedding_spec=EmbeddingModelSpec(
            model_name=str(metadata["embedding_model_name"]),
            model_version=str(metadata["embedding_model_version"]),
            dimensions=int(metadata["embedding_dimensions"]),
            spec_version=str(metadata["embedding_spec_version"]),
        ),
        source_chunk_hash=str(metadata["source_chunk_hash"]),
        chunker_version=str(metadata["chunker_version"]),
        metadata_index_revision=str(metadata["metadata_index_revision"]),
        vector_index_revision=str(metadata["vector_index_revision"]),
        backend=backend,
        backend_schema_version=str(metadata["backend_schema_version"]),
        source_role=cast(DocumentRole, str(metadata["source_role"])),
        provenance_family_id=str(metadata["provenance_family_id"]),
    )


def _metadata_value(values: tuple[Any, ...]) -> object:
    string_value, int_value, float_value, bool_value = values
    for value in (string_value, int_value, float_value):
        if value is not None:
            return value
    return bool(bool_value) if bool_value is not None else None
