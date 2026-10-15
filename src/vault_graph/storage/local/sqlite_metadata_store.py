from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

from vault_graph.errors import MetadataStoreError
from vault_graph.indexing.ingestion.document_authority import DocumentRole
from vault_graph.indexing.ingestion.document_models import DocumentModelError, SourceLocator
from vault_graph.indexing.ingestion.document_normalizer import ChunkSnapshot, DocumentSnapshot
from vault_graph.operation.scope.vault_catalog import QueryScope
from vault_graph.storage.interfaces.metadata_store import DocumentState, EvidenceLookupKey, EvidenceReference
from vault_graph.storage.interfaces.store_health import StoreHealth
from vault_graph.storage.local.sqlite_keyword_index import apply_keyword_revision, ensure_keyword_schema

SCHEMA_VERSION = "metadata-v3"
_EVIDENCE_LOOKUP_BATCH_SIZE = 300

SCHEMA = """
CREATE TABLE IF NOT EXISTS documents (
  vault_id TEXT NOT NULL,
  document_id TEXT NOT NULL,
  path TEXT NOT NULL,
  kind TEXT NOT NULL,
  frontmatter_json TEXT NOT NULL,
  frontmatter_hash TEXT NOT NULL,
  content_hash TEXT NOT NULL,
  raw_sha256 TEXT NOT NULL,
  parser_version TEXT NOT NULL,
  format TEXT NOT NULL DEFAULT 'markdown',
  reader_name TEXT NOT NULL DEFAULT 'legacy-markdown-reader',
  reader_version TEXT NOT NULL DEFAULT 'legacy-v1',
  extraction_options_digest TEXT NOT NULL DEFAULT 'legacy-options-v1',
  last_seen_at TEXT NOT NULL,
  last_indexed_at TEXT,
  vault_revision TEXT,
  index_revision TEXT,
  source_role TEXT NOT NULL,
  provenance_family_id TEXT NOT NULL,
  is_tombstoned INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY (vault_id, path),
  UNIQUE (document_id)
);

CREATE TABLE IF NOT EXISTS content_blobs (
  blob_hash TEXT PRIMARY KEY,
  text TEXT NOT NULL,
  byte_count INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS chunks (
  vault_id TEXT NOT NULL,
  chunk_id TEXT NOT NULL,
  document_id TEXT NOT NULL,
  path TEXT NOT NULL,
  section TEXT,
  anchor TEXT,
  blob_hash TEXT NOT NULL REFERENCES content_blobs(blob_hash),
  token_count INTEGER NOT NULL,
  content_hash TEXT NOT NULL,
  chunker_version TEXT NOT NULL,
  index_revision TEXT,
  source_role TEXT NOT NULL,
  provenance_family_id TEXT NOT NULL,
  section_path_json TEXT NOT NULL DEFAULT '[]',
  source_locators_json TEXT NOT NULL DEFAULT '[]',
  document_order INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY (vault_id, chunk_id)
);

CREATE TABLE IF NOT EXISTS index_revisions (
  index_revision TEXT PRIMARY KEY,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS metadata_projection_metadata (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL
);
"""

_REQUIRED_DOCUMENT_COLUMNS = frozenset(
    {
        "vault_id",
        "document_id",
        "path",
        "kind",
        "frontmatter_json",
        "frontmatter_hash",
        "content_hash",
        "raw_sha256",
        "parser_version",
        "format",
        "reader_name",
        "reader_version",
        "extraction_options_digest",
        "last_seen_at",
        "last_indexed_at",
        "vault_revision",
        "index_revision",
        "source_role",
        "provenance_family_id",
        "is_tombstoned",
    }
)
_REQUIRED_CHUNK_COLUMNS = frozenset(
    {
        "vault_id",
        "chunk_id",
        "document_id",
        "path",
        "section",
        "anchor",
        "blob_hash",
        "token_count",
        "content_hash",
        "chunker_version",
        "index_revision",
        "source_role",
        "provenance_family_id",
        "section_path_json",
        "source_locators_json",
        "document_order",
    }
)


class SQLiteMetadataStore:
    def __init__(self, database_path: Path, *, initialize: bool = False) -> None:
        self._database_path = database_path.expanduser().resolve()
        self._initialize = initialize
        if initialize:
            self._database_path.parent.mkdir(parents=True, exist_ok=True)
            with self._connect() as connection:
                connection.executescript(SCHEMA)
                _upgrade_schema(connection)
                ensure_keyword_schema(connection)

    def apply_metadata_revision(
        self,
        *,
        index_revision: str,
        documents: list[DocumentSnapshot],
        chunks: list[ChunkSnapshot],
        tombstones: list[tuple[str, str]],
    ) -> None:
        indexed_at = datetime.now(UTC).isoformat()
        with self._connect() as connection:
            connection.execute(
                "INSERT OR REPLACE INTO index_revisions (index_revision, created_at) VALUES (?, ?)",
                (index_revision, indexed_at),
            )
            for document in documents:
                connection.execute(
                    """
                    INSERT INTO documents (
                      vault_id, document_id, path, kind, frontmatter_json, frontmatter_hash,
                      content_hash, raw_sha256, parser_version, format, reader_name, reader_version,
                      extraction_options_digest, last_seen_at, last_indexed_at, vault_revision,
                      index_revision, source_role, provenance_family_id, is_tombstoned
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0)
                    ON CONFLICT(vault_id, path) DO UPDATE SET
                      document_id=excluded.document_id,
                      kind=excluded.kind,
                      frontmatter_json=excluded.frontmatter_json,
                      frontmatter_hash=excluded.frontmatter_hash,
                      content_hash=excluded.content_hash,
                      raw_sha256=excluded.raw_sha256,
                      parser_version=excluded.parser_version,
                      format=excluded.format,
                      reader_name=excluded.reader_name,
                      reader_version=excluded.reader_version,
                      extraction_options_digest=excluded.extraction_options_digest,
                      last_seen_at=excluded.last_seen_at,
                      last_indexed_at=excluded.last_indexed_at,
                      vault_revision=excluded.vault_revision,
                      index_revision=excluded.index_revision,
                      source_role=excluded.source_role,
                      provenance_family_id=excluded.provenance_family_id,
                      is_tombstoned=0
                    """,
                    (
                        document.vault_id,
                        document.document_id,
                        document.path,
                        document.kind,
                        json.dumps(document.frontmatter, sort_keys=True),
                        document.frontmatter_hash,
                        document.content_hash,
                        document.raw_sha256,
                        document.parser_version,
                        document.format,
                        document.reader_name,
                        document.reader_version,
                        document.extraction_options_digest,
                        document.last_seen_at,
                        indexed_at,
                        document.vault_revision,
                        index_revision,
                        document.source_role,
                        document.provenance_family_id,
                    ),
                )
                connection.execute(
                    "DELETE FROM chunks WHERE vault_id = ? AND document_id = ?",
                    (document.vault_id, document.document_id),
                )
            for chunk in chunks:
                connection.execute(
                    "INSERT OR IGNORE INTO content_blobs (blob_hash, text, byte_count) VALUES (?, ?, ?)",
                    (chunk.content_hash, chunk.text, len(chunk.text.encode("utf-8"))),
                )
                connection.execute(
                    """
                    INSERT OR REPLACE INTO chunks (
                      vault_id, chunk_id, document_id, path, section, anchor, blob_hash,
                      token_count, content_hash, chunker_version, index_revision, source_role,
                      provenance_family_id, section_path_json, source_locators_json, document_order
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        chunk.vault_id,
                        chunk.chunk_id,
                        chunk.document_id,
                        chunk.path,
                        chunk.section,
                        chunk.anchor,
                        chunk.content_hash,
                        chunk.token_count,
                        chunk.content_hash,
                        chunk.chunker_version,
                        index_revision,
                        chunk.source_role,
                        chunk.provenance_family_id,
                        _section_path_json(chunk.section_path),
                        _source_locators_json(chunk.source_locators),
                        chunk.document_order,
                    ),
                )
            for vault_id, path in tombstones:
                connection.execute("DELETE FROM chunks WHERE vault_id = ? AND path = ?", (vault_id, path))
                connection.execute(
                    "UPDATE documents SET is_tombstoned = 1, index_revision = ? WHERE vault_id = ? AND path = ?",
                    (index_revision, vault_id, path),
                )
            apply_keyword_revision(
                connection,
                index_revision=index_revision,
                documents=documents,
                chunks=chunks,
                tombstones=tombstones,
            )
            connection.execute(
                "DELETE FROM content_blobs "
                "WHERE NOT EXISTS (SELECT 1 FROM chunks WHERE chunks.blob_hash = content_blobs.blob_hash)"
            )

    def document_state(self, vault_id: str, path: str) -> DocumentState:
        if not self._database_path.exists():
            return _missing_document_state(vault_id=vault_id, path=path)
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT d.vault_id, d.path, d.document_id, d.frontmatter_hash, d.content_hash,
                       d.raw_sha256, d.parser_version, d.format, d.reader_name, d.reader_version,
                       d.extraction_options_digest, c.chunker_version, d.is_tombstoned,
                       d.source_role, d.provenance_family_id
                FROM documents d
                LEFT JOIN chunks c ON c.vault_id = d.vault_id AND c.document_id = d.document_id
                WHERE d.vault_id = ? AND d.path = ?
                LIMIT 1
                """,
                (vault_id, path),
            ).fetchone()
        if row is None:
            return _missing_document_state(vault_id=vault_id, path=path)
        return _document_state_from_row(row)

    def list_document_states(self, vault_ids: tuple[str, ...]) -> tuple[DocumentState, ...]:
        if not vault_ids:
            return ()
        if not self._database_path.exists():
            return ()
        placeholders = ", ".join("?" for _ in vault_ids)
        with self._connect() as connection:
            rows = connection.execute(
                f"""
                WITH first_chunks AS (
                  SELECT vault_id, document_id, chunker_version,
                         ROW_NUMBER() OVER (PARTITION BY vault_id, document_id ORDER BY chunk_id) AS position
                  FROM chunks
                  WHERE vault_id IN ({placeholders})
                )
                SELECT d.vault_id, d.path, d.document_id, d.frontmatter_hash, d.content_hash,
                       d.raw_sha256, d.parser_version, d.format, d.reader_name, d.reader_version,
                       d.extraction_options_digest, c.chunker_version, d.is_tombstoned,
                       d.source_role, d.provenance_family_id
                FROM documents d
                LEFT JOIN first_chunks c
                  ON c.vault_id = d.vault_id AND c.document_id = d.document_id AND c.position = 1
                WHERE d.vault_id IN ({placeholders})
                ORDER BY d.vault_id, d.path
                """,
                (*vault_ids, *vault_ids),
            ).fetchall()
        return tuple(_document_state_from_row(row) for row in rows)

    def list_documents(self, scope: QueryScope) -> tuple[DocumentSnapshot, ...]:
        if not scope.vault_ids:
            return ()
        if not self._database_path.exists():
            return ()
        vault_placeholders = ", ".join("?" for _ in scope.vault_ids)
        with self._connect() as connection:
            rows = connection.execute(
                f"""
                SELECT vault_id, document_id, path, kind, frontmatter_json, frontmatter_hash,
                       content_hash, raw_sha256, parser_version, format, reader_name, reader_version,
                       extraction_options_digest, last_seen_at, last_indexed_at, vault_revision,
                       index_revision, source_role, provenance_family_id
                FROM documents
                WHERE vault_id IN ({vault_placeholders})
                  AND is_tombstoned = 0
                ORDER BY vault_id, path, document_id
                """,
                scope.vault_ids,
            ).fetchall()
        return tuple(
            _document_snapshot_from_row(row)
            for row in rows
            if _path_in_content_scope(path=str(row["path"]), content_scopes=scope.content_scopes)
        )

    def list_recent_documents(
        self,
        scope: QueryScope,
        *,
        since: str | None = None,
        limit: int = 20,
    ) -> tuple[DocumentSnapshot, ...]:
        if len(scope.vault_ids) != 1:
            raise MetadataStoreError("invalid_metadata_scope: list_recent_documents requires exactly one vault_id")
        if limit < 1:
            return ()
        if not self._database_path.exists():
            return ()
        path_clause, path_params = _content_scope_sql_filter(scope.content_scopes)
        params: list[object] = [scope.vault_ids[0], *path_params]
        since_clause = ""
        if since is not None:
            since_clause = "AND COALESCE(last_indexed_at, last_seen_at) > ?"
            params.append(since)
        params.append(limit)
        with self._connect() as connection:
            rows = connection.execute(
                f"""
                SELECT vault_id, document_id, path, kind, frontmatter_json, frontmatter_hash,
                       content_hash, raw_sha256, parser_version, format, reader_name, reader_version,
                       extraction_options_digest, last_seen_at, last_indexed_at, vault_revision,
                       index_revision, source_role, provenance_family_id
                FROM documents
                WHERE vault_id = ?
                  AND is_tombstoned = 0
                  AND ({path_clause})
                  {since_clause}
                ORDER BY COALESCE(last_indexed_at, last_seen_at) DESC, vault_id, path, document_id
                LIMIT ?
                """,
                tuple(params),
            ).fetchall()
        return tuple(_document_snapshot_from_row(row) for row in rows)

    def list_chunks(self, scope: QueryScope) -> tuple[ChunkSnapshot, ...]:
        if not scope.vault_ids:
            return ()
        if not self._database_path.exists():
            return ()
        vault_placeholders = ", ".join("?" for _ in scope.vault_ids)
        with self._connect() as connection:
            rows = connection.execute(
                f"""
                SELECT c.vault_id, c.chunk_id, c.document_id, c.path, c.section, c.anchor,
                       b.text, c.token_count, c.content_hash, c.chunker_version, c.index_revision,
                       c.source_role, c.provenance_family_id, c.section_path_json,
                       c.source_locators_json, c.document_order
                FROM chunks c
                INNER JOIN content_blobs b ON b.blob_hash = c.blob_hash
                INNER JOIN documents d
                  ON d.vault_id = c.vault_id
                 AND d.document_id = c.document_id
                 AND d.path = c.path
                WHERE c.vault_id IN ({vault_placeholders})
                  AND d.is_tombstoned = 0
                ORDER BY c.vault_id, c.path, c.document_order, c.chunk_id
                """,
                scope.vault_ids,
            ).fetchall()
        return tuple(
            _chunk_snapshot_from_row(row)
            for row in rows
            if _path_in_content_scope(path=str(row["path"]), content_scopes=scope.content_scopes)
        )

    def list_document_chunks(
        self,
        *,
        vault_id: str,
        document_id: str,
    ) -> tuple[ChunkSnapshot, ...]:
        if not self._database_path.exists():
            return ()
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT c.vault_id, c.chunk_id, c.document_id, c.path, c.section, c.anchor,
                       b.text, c.token_count, c.content_hash, c.chunker_version, c.index_revision,
                       c.source_role, c.provenance_family_id, c.section_path_json,
                       c.source_locators_json, c.document_order
                FROM chunks c
                INNER JOIN content_blobs b ON b.blob_hash = c.blob_hash
                INNER JOIN documents d
                  ON d.vault_id = c.vault_id
                 AND d.document_id = c.document_id
                 AND d.path = c.path
                WHERE c.vault_id = ?
                  AND c.document_id = ?
                  AND d.is_tombstoned = 0
                ORDER BY c.document_order, c.rowid, c.chunk_id
                """,
                (vault_id, document_id),
            ).fetchall()
        return tuple(_chunk_snapshot_from_row(row) for row in rows)

    def resolve_document(self, document_id: str) -> DocumentSnapshot | None:
        if not self._database_path.exists():
            return None
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT vault_id, document_id, path, kind, frontmatter_json, frontmatter_hash,
                       content_hash, raw_sha256, parser_version, format, reader_name, reader_version,
                       extraction_options_digest, last_seen_at, last_indexed_at, vault_revision,
                       index_revision, source_role, provenance_family_id
                FROM documents
                WHERE document_id = ? AND is_tombstoned = 0
                """,
                (document_id,),
            ).fetchone()
        if row is None:
            return None
        return _document_snapshot_from_row(row)

    def resolve_chunk(self, *, vault_id: str, chunk_id: str) -> ChunkSnapshot | None:
        if not self._database_path.exists():
            return None
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT c.vault_id, c.chunk_id, c.document_id, c.path, c.section, c.anchor, b.text,
                       c.token_count, c.content_hash, c.chunker_version, c.index_revision,
                       c.source_role, c.provenance_family_id, c.section_path_json,
                       c.source_locators_json, c.document_order
                FROM chunks c
                INNER JOIN content_blobs b ON b.blob_hash = c.blob_hash
                WHERE c.vault_id = ? AND c.chunk_id = ?
                """,
                (vault_id, chunk_id),
            ).fetchone()
        if row is None:
            return None
        return _chunk_snapshot_from_row(row)

    def resolve_chunk_evidence(
        self,
        *,
        vault_id: str,
        document_id: str,
        chunk_id: str,
    ) -> EvidenceReference | None:
        if not self._database_path.exists():
            return None
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT d.vault_id, d.document_id, c.chunk_id, d.path, c.section, c.anchor,
                       c.content_hash, d.raw_sha256, c.index_revision, d.vault_revision,
                       c.source_role, c.provenance_family_id, c.section_path_json,
                       c.source_locators_json
                FROM documents d
                INNER JOIN chunks c ON c.vault_id = d.vault_id AND c.document_id = d.document_id AND c.path = d.path
                WHERE d.vault_id = ?
                  AND d.document_id = ?
                  AND c.chunk_id = ?
                  AND d.is_tombstoned = 0
                """,
                (vault_id, document_id, chunk_id),
            ).fetchone()
        if row is None:
            return None
        return _evidence_reference_from_row(row)

    def resolve_chunk_evidence_hashes(self, keys: tuple[EvidenceLookupKey, ...]) -> dict[EvidenceLookupKey, str]:
        """Read live evidence hashes with one connection and bounded SQL batches."""
        if not keys or not self._database_path.exists():
            return {}
        unique_keys = tuple(dict.fromkeys(keys))
        hashes: dict[EvidenceLookupKey, str] = {}
        with self._connect() as connection:
            for start in range(0, len(unique_keys), _EVIDENCE_LOOKUP_BATCH_SIZE):
                batch = unique_keys[start : start + _EVIDENCE_LOOKUP_BATCH_SIZE]
                placeholders = ", ".join("(?, ?, ?)" for _ in batch)
                rows = connection.execute(
                    f"""
                    WITH requested(vault_id, document_id, chunk_id) AS (VALUES {placeholders})
                    SELECT requested.vault_id, requested.document_id, requested.chunk_id, c.content_hash
                    FROM requested
                    INNER JOIN chunks c
                      ON c.vault_id = requested.vault_id
                     AND c.document_id = requested.document_id
                     AND c.chunk_id = requested.chunk_id
                    INNER JOIN documents d
                      ON d.vault_id = c.vault_id
                     AND d.document_id = c.document_id
                     AND d.path = c.path
                    WHERE d.is_tombstoned = 0
                    """,
                    tuple(part for key in batch for part in key),
                ).fetchall()
                hashes.update(
                    {
                        (str(row["vault_id"]), str(row["document_id"]), str(row["chunk_id"])): str(row["content_hash"])
                        for row in rows
                    }
                )
        return hashes

    def health(self) -> StoreHealth:
        if not self._database_path.exists():
            return StoreHealth(
                ok=False,
                backend="sqlite",
                schema_version=SCHEMA_VERSION,
                schema_compatible=False,
                message="not initialized",
            )
        try:
            with self._connect() as connection:
                tables = {
                    str(row["name"])
                    for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
                }
                missing = {
                    "documents",
                    "content_blobs",
                    "chunks",
                    "index_revisions",
                    "metadata_projection_metadata",
                } - tables
                if missing:
                    return StoreHealth(
                        ok=False,
                        backend="sqlite",
                        schema_version=SCHEMA_VERSION,
                        schema_compatible=False,
                        message=f"schema incompatible: missing {', '.join(sorted(missing))}. Run `vg index`.",
                    )
                document_columns = {
                    str(row["name"]) for row in connection.execute("PRAGMA table_info(documents)").fetchall()
                }
                missing_document_columns = _REQUIRED_DOCUMENT_COLUMNS - document_columns
                if missing_document_columns:
                    return StoreHealth(
                        ok=False,
                        backend="sqlite",
                        schema_version=SCHEMA_VERSION,
                        schema_compatible=False,
                        message=(
                            "schema incompatible: missing document columns "
                            + ", ".join(sorted(missing_document_columns))
                            + ". Run `vg index`."
                        ),
                    )
                chunk_columns = {str(row["name"]) for row in connection.execute("PRAGMA table_info(chunks)").fetchall()}
                missing_chunk_columns = _REQUIRED_CHUNK_COLUMNS - chunk_columns
                if missing_chunk_columns:
                    return StoreHealth(
                        ok=False,
                        backend="sqlite",
                        schema_version=SCHEMA_VERSION,
                        schema_compatible=False,
                        message=(
                            "schema incompatible: missing chunk columns "
                            + ", ".join(sorted(missing_chunk_columns))
                            + ". Run `vg index`."
                        ),
                    )
                version_row = connection.execute(
                    "SELECT value FROM metadata_projection_metadata WHERE key = 'schema_version'"
                ).fetchone()
                if version_row is None or str(version_row["value"]) != SCHEMA_VERSION:
                    return StoreHealth(
                        ok=False,
                        backend="sqlite",
                        schema_version=SCHEMA_VERSION,
                        schema_compatible=False,
                        message="schema incompatible: metadata schema version mismatch. Run `vg index`.",
                    )
        except (FileNotFoundError, sqlite3.Error) as exc:
            return StoreHealth(
                ok=False,
                backend="sqlite",
                schema_version=SCHEMA_VERSION,
                schema_compatible=False,
                message=str(exc),
            )
        return StoreHealth(
            ok=True,
            backend="sqlite",
            schema_version=SCHEMA_VERSION,
            schema_compatible=True,
            message="ok",
        )

    def list_family_evidence(self, *, vault_id: str, provenance_family_id: str) -> tuple[EvidenceReference, ...]:
        if not self._database_path.exists():
            return ()
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT d.vault_id, d.document_id, c.chunk_id, d.path, c.section, c.anchor,
                       c.content_hash, d.raw_sha256, c.index_revision, d.vault_revision,
                       c.source_role, c.provenance_family_id, c.section_path_json,
                       c.source_locators_json
                FROM documents d
                INNER JOIN chunks c
                  ON c.vault_id = d.vault_id
                 AND c.document_id = d.document_id
                 AND c.path = d.path
                WHERE d.vault_id = ?
                  AND c.provenance_family_id = ?
                  AND d.is_tombstoned = 0
                ORDER BY d.path, c.document_order, c.chunk_id
                """,
                (vault_id, provenance_family_id),
            ).fetchall()
        return tuple(_evidence_reference_from_row(row) for row in rows)

    def export_documents(self) -> tuple[dict[str, Any], ...]:
        if not self._database_path.exists():
            return ()
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT vault_id, document_id, path, kind, frontmatter_json, frontmatter_hash,
                       content_hash, raw_sha256, parser_version, format, reader_name, reader_version,
                       extraction_options_digest, last_seen_at, last_indexed_at, vault_revision,
                       index_revision, source_role, provenance_family_id
                FROM documents
                WHERE is_tombstoned = 0
                ORDER BY vault_id, path
                """
            ).fetchall()
        return tuple(asdict(_document_snapshot_from_row(row)) for row in rows)

    def connect_for_tests(self) -> sqlite3.Connection:
        return self._connect()

    def _connect(self) -> sqlite3.Connection:
        if not self._initialize and not self._database_path.exists():
            raise FileNotFoundError(self._database_path)
        if self._initialize:
            connection = sqlite3.connect(self._database_path)
        else:
            connection = sqlite3.connect(f"file:{self._database_path}?mode=ro", uri=True)
        connection.row_factory = sqlite3.Row
        return connection


def _upgrade_schema(connection: sqlite3.Connection) -> None:
    """Upgrade metadata columns only on an explicitly writable open."""

    document_columns = {str(row["name"]) for row in connection.execute("PRAGMA table_info(documents)").fetchall()}
    for column, definition in (
        ("format", "TEXT NOT NULL DEFAULT 'markdown'"),
        ("reader_name", "TEXT NOT NULL DEFAULT 'legacy-markdown-reader'"),
        ("reader_version", "TEXT NOT NULL DEFAULT 'legacy-v1'"),
        ("extraction_options_digest", "TEXT NOT NULL DEFAULT 'legacy-options-v1'"),
    ):
        if column not in document_columns:
            connection.execute(f"ALTER TABLE documents ADD COLUMN {column} {definition}")

    chunk_columns = {str(row["name"]) for row in connection.execute("PRAGMA table_info(chunks)").fetchall()}
    for column, definition in (
        ("section_path_json", "TEXT NOT NULL DEFAULT '[]'"),
        ("source_locators_json", "TEXT NOT NULL DEFAULT '[]'"),
        ("document_order", "INTEGER NOT NULL DEFAULT 0"),
    ):
        if column not in chunk_columns:
            connection.execute(f"ALTER TABLE chunks ADD COLUMN {column} {definition}")
    connection.execute(
        """
        INSERT INTO metadata_projection_metadata (key, value)
        VALUES ('schema_version', ?)
        ON CONFLICT(key) DO UPDATE SET value = excluded.value
        """,
        (SCHEMA_VERSION,),
    )


def _section_path_json(section_path: tuple[str, ...]) -> str:
    if not isinstance(section_path, tuple) or any(not isinstance(segment, str) for segment in section_path):
        raise MetadataStoreError("section_path must be a tuple of strings")
    return json.dumps(list(section_path), ensure_ascii=False, separators=(",", ":"))


def _source_locators_json(source_locators: tuple[SourceLocator, ...]) -> str:
    if not isinstance(source_locators, tuple):
        raise MetadataStoreError("source_locators must be a tuple")
    try:
        payload = [locator.to_dict() for locator in source_locators]
    except (AttributeError, TypeError) as exc:
        raise MetadataStoreError("source_locators must contain SourceLocator values") from exc
    if any(not isinstance(locator, SourceLocator) for locator in source_locators):
        raise MetadataStoreError("source_locators must contain SourceLocator values")
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _decode_section_path(raw_value: object) -> tuple[str, ...]:
    try:
        decoded = json.loads(str(raw_value))
    except (TypeError, json.JSONDecodeError) as exc:
        raise MetadataStoreError("metadata section_path_json is malformed") from exc
    if not isinstance(decoded, list) or any(not isinstance(segment, str) for segment in decoded):
        raise MetadataStoreError("metadata section_path_json must be a JSON list of strings")
    return tuple(segment.strip() for segment in decoded if segment.strip())


def _decode_source_locators(raw_value: object) -> tuple[SourceLocator, ...]:
    try:
        decoded = json.loads(str(raw_value))
    except (TypeError, json.JSONDecodeError) as exc:
        raise MetadataStoreError("metadata source_locators_json is malformed") from exc
    if not isinstance(decoded, list):
        raise MetadataStoreError("metadata source_locators_json must be a JSON list")
    try:
        return tuple(SourceLocator.from_dict(item) for item in decoded)
    except (DocumentModelError, TypeError, ValueError) as exc:
        raise MetadataStoreError("metadata source_locators_json contains an invalid locator") from exc


def _missing_document_state(*, vault_id: str, path: str) -> DocumentState:
    return DocumentState(
        vault_id=vault_id,
        path=path,
        document_id=None,
        frontmatter_hash=None,
        content_hash=None,
        raw_sha256=None,
        parser_version=None,
        chunker_version=None,
        is_tombstoned=True,
        source_role=None,
        provenance_family_id=None,
        format=None,
        reader_name=None,
        reader_version=None,
        extraction_options_digest=None,
    )


def _document_state_from_row(row: sqlite3.Row) -> DocumentState:
    return DocumentState(
        vault_id=str(row["vault_id"]),
        path=str(row["path"]),
        document_id=str(row["document_id"]),
        frontmatter_hash=str(row["frontmatter_hash"]),
        content_hash=str(row["content_hash"]),
        raw_sha256=str(row["raw_sha256"]),
        parser_version=str(row["parser_version"]),
        format=str(row["format"]),
        reader_name=str(row["reader_name"]),
        reader_version=str(row["reader_version"]),
        extraction_options_digest=str(row["extraction_options_digest"]),
        chunker_version=str(row["chunker_version"]) if row["chunker_version"] is not None else None,
        is_tombstoned=bool(row["is_tombstoned"]),
        source_role=cast(DocumentRole, str(row["source_role"])),
        provenance_family_id=str(row["provenance_family_id"]),
    )


def _document_snapshot_from_row(row: sqlite3.Row) -> DocumentSnapshot:
    return DocumentSnapshot(
        vault_id=str(row["vault_id"]),
        document_id=str(row["document_id"]),
        path=str(row["path"]),
        kind=str(row["kind"]),
        frontmatter=json.loads(str(row["frontmatter_json"])),
        frontmatter_hash=str(row["frontmatter_hash"]),
        content_hash=str(row["content_hash"]),
        raw_sha256=str(row["raw_sha256"]),
        parser_version=str(row["parser_version"]),
        format=str(row["format"]),
        reader_name=str(row["reader_name"]),
        reader_version=str(row["reader_version"]),
        extraction_options_digest=str(row["extraction_options_digest"]),
        last_seen_at=str(row["last_seen_at"]),
        last_indexed_at=str(row["last_indexed_at"]) if row["last_indexed_at"] is not None else None,
        vault_revision=str(row["vault_revision"]) if row["vault_revision"] is not None else None,
        index_revision=str(row["index_revision"]) if row["index_revision"] is not None else None,
        source_role=cast(DocumentRole, str(row["source_role"])),
        provenance_family_id=str(row["provenance_family_id"]),
    )


def _chunk_snapshot_from_row(row: sqlite3.Row) -> ChunkSnapshot:
    section_path = _decode_section_path(row["section_path_json"])
    source_locators = _decode_source_locators(row["source_locators_json"])
    return ChunkSnapshot(
        vault_id=str(row["vault_id"]),
        chunk_id=str(row["chunk_id"]),
        document_id=str(row["document_id"]),
        path=str(row["path"]),
        section=str(row["section"]) if row["section"] is not None else None,
        anchor=str(row["anchor"]) if row["anchor"] is not None else None,
        text=str(row["text"]),
        token_count=int(row["token_count"]),
        content_hash=str(row["content_hash"]),
        chunker_version=str(row["chunker_version"]),
        index_revision=str(row["index_revision"]) if row["index_revision"] is not None else None,
        source_role=cast(DocumentRole, str(row["source_role"])),
        provenance_family_id=str(row["provenance_family_id"]),
        section_path=section_path,
        source_locators=source_locators,
        document_order=int(row["document_order"]),
    )


def _path_in_content_scope(*, path: str, content_scopes: tuple[str, ...]) -> bool:
    return any(path == content_scope or path.startswith(f"{content_scope}/") for content_scope in content_scopes)


def _content_scope_sql_filter(content_scopes: tuple[str, ...]) -> tuple[str, tuple[object, ...]]:
    clauses: list[str] = []
    params: list[object] = []
    for content_scope in content_scopes:
        prefix = f"{content_scope}/"
        clauses.append("(path = ? OR substr(path, 1, ?) = ?)")
        params.extend((content_scope, len(prefix), prefix))
    if not clauses:
        return "0", ()
    return " OR ".join(clauses), tuple(params)


def _evidence_reference_from_row(row: sqlite3.Row) -> EvidenceReference:
    return EvidenceReference(
        vault_id=str(row["vault_id"]),
        document_id=str(row["document_id"]),
        chunk_id=str(row["chunk_id"]),
        path=str(row["path"]),
        section=str(row["section"]) if row["section"] is not None else None,
        anchor=str(row["anchor"]) if row["anchor"] is not None else None,
        content_hash=str(row["content_hash"]),
        raw_sha256=str(row["raw_sha256"]),
        metadata_index_revision=str(row["index_revision"]) if row["index_revision"] is not None else None,
        vault_revision=str(row["vault_revision"]) if row["vault_revision"] is not None else None,
        source_role=cast(DocumentRole, str(row["source_role"])),
        provenance_family_id=str(row["provenance_family_id"]),
        section_path=_decode_section_path(row["section_path_json"]),
        source_locators=_decode_source_locators(row["source_locators_json"]),
    )
