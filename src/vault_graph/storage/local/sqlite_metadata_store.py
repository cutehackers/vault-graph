from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from vault_graph.ingestion.document_normalizer import ChunkSnapshot, DocumentSnapshot
from vault_graph.ingestion.vault_catalog import QueryScope
from vault_graph.storage.interfaces.metadata_store import DocumentState, EvidenceReference
from vault_graph.storage.interfaces.store_health import StoreHealth
from vault_graph.storage.local.sqlite_keyword_index import apply_keyword_revision, ensure_keyword_schema

SCHEMA_VERSION = "metadata-v1"

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
  last_seen_at TEXT NOT NULL,
  last_indexed_at TEXT,
  vault_revision TEXT,
  index_revision TEXT,
  is_tombstoned INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY (vault_id, path),
  UNIQUE (document_id)
);

CREATE TABLE IF NOT EXISTS chunks (
  vault_id TEXT NOT NULL,
  chunk_id TEXT NOT NULL,
  document_id TEXT NOT NULL,
  path TEXT NOT NULL,
  section TEXT,
  anchor TEXT,
  text TEXT NOT NULL,
  token_count INTEGER NOT NULL,
  content_hash TEXT NOT NULL,
  chunker_version TEXT NOT NULL,
  index_revision TEXT,
  PRIMARY KEY (vault_id, chunk_id)
);

CREATE TABLE IF NOT EXISTS index_revisions (
  index_revision TEXT PRIMARY KEY,
  created_at TEXT NOT NULL
);
"""


class SQLiteMetadataStore:
    def __init__(self, database_path: Path, *, initialize: bool = False) -> None:
        self._database_path = database_path.expanduser().resolve()
        self._initialize = initialize
        if initialize:
            self._database_path.parent.mkdir(parents=True, exist_ok=True)
            with self._connect() as connection:
                connection.executescript(SCHEMA)
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
                      content_hash, raw_sha256, parser_version, last_seen_at, last_indexed_at,
                      vault_revision, index_revision, is_tombstoned
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0)
                    ON CONFLICT(vault_id, path) DO UPDATE SET
                      document_id=excluded.document_id,
                      kind=excluded.kind,
                      frontmatter_json=excluded.frontmatter_json,
                      frontmatter_hash=excluded.frontmatter_hash,
                      content_hash=excluded.content_hash,
                      raw_sha256=excluded.raw_sha256,
                      parser_version=excluded.parser_version,
                      last_seen_at=excluded.last_seen_at,
                      last_indexed_at=excluded.last_indexed_at,
                      vault_revision=excluded.vault_revision,
                      index_revision=excluded.index_revision,
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
                        document.last_seen_at,
                        indexed_at,
                        document.vault_revision,
                        index_revision,
                    ),
                )
                connection.execute(
                    "DELETE FROM chunks WHERE vault_id = ? AND document_id = ?",
                    (document.vault_id, document.document_id),
                )
            for chunk in chunks:
                connection.execute(
                    """
                    INSERT OR REPLACE INTO chunks (
                      vault_id, chunk_id, document_id, path, section, anchor, text,
                      token_count, content_hash, chunker_version, index_revision
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        chunk.vault_id,
                        chunk.chunk_id,
                        chunk.document_id,
                        chunk.path,
                        chunk.section,
                        chunk.anchor,
                        chunk.text,
                        chunk.token_count,
                        chunk.content_hash,
                        chunk.chunker_version,
                        index_revision,
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

    def document_state(self, vault_id: str, path: str) -> DocumentState:
        if not self._database_path.exists():
            return _missing_document_state(vault_id=vault_id, path=path)
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT d.vault_id, d.path, d.document_id, d.frontmatter_hash, d.content_hash,
                       d.raw_sha256, d.parser_version, c.chunker_version, d.is_tombstoned
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
                SELECT d.vault_id, d.path, d.document_id, d.frontmatter_hash, d.content_hash,
                       d.raw_sha256, d.parser_version, c.chunker_version, d.is_tombstoned
                FROM documents d
                LEFT JOIN chunks c ON c.vault_id = d.vault_id AND c.document_id = d.document_id
                WHERE d.vault_id IN ({placeholders})
                GROUP BY d.vault_id, d.path
                ORDER BY d.vault_id, d.path
                """,
                vault_ids,
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
                       content_hash, raw_sha256, parser_version, last_seen_at, last_indexed_at,
                       vault_revision, index_revision
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
                       c.text, c.token_count, c.content_hash, c.chunker_version, c.index_revision
                FROM chunks c
                INNER JOIN documents d
                  ON d.vault_id = c.vault_id
                 AND d.document_id = c.document_id
                 AND d.path = c.path
                WHERE c.vault_id IN ({vault_placeholders})
                  AND d.is_tombstoned = 0
                ORDER BY c.vault_id, c.path, c.chunk_id
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
                       c.text, c.token_count, c.content_hash, c.chunker_version, c.index_revision
                FROM chunks c
                INNER JOIN documents d
                  ON d.vault_id = c.vault_id
                 AND d.document_id = c.document_id
                 AND d.path = c.path
                WHERE c.vault_id = ?
                  AND c.document_id = ?
                  AND d.is_tombstoned = 0
                ORDER BY c.rowid
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
                       content_hash, raw_sha256, parser_version, last_seen_at, last_indexed_at,
                       vault_revision, index_revision
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
                SELECT vault_id, chunk_id, document_id, path, section, anchor, text,
                       token_count, content_hash, chunker_version, index_revision
                FROM chunks
                WHERE vault_id = ? AND chunk_id = ?
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
                       c.content_hash, d.raw_sha256, c.index_revision, d.vault_revision
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
                missing = {"documents", "chunks", "index_revisions"} - tables
                if missing:
                    return StoreHealth(
                        ok=False,
                        backend="sqlite",
                        schema_version=SCHEMA_VERSION,
                        schema_compatible=False,
                        message=f"schema incompatible: missing {', '.join(sorted(missing))}",
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

    def export_documents(self) -> tuple[dict[str, Any], ...]:
        if not self._database_path.exists():
            return ()
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT vault_id, document_id, path, kind, frontmatter_json, frontmatter_hash,
                       content_hash, raw_sha256, parser_version, last_seen_at, last_indexed_at,
                       vault_revision, index_revision
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
        chunker_version=str(row["chunker_version"]) if row["chunker_version"] is not None else None,
        is_tombstoned=bool(row["is_tombstoned"]),
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
        last_seen_at=str(row["last_seen_at"]),
        last_indexed_at=str(row["last_indexed_at"]) if row["last_indexed_at"] is not None else None,
        vault_revision=str(row["vault_revision"]) if row["vault_revision"] is not None else None,
        index_revision=str(row["index_revision"]) if row["index_revision"] is not None else None,
    )


def _chunk_snapshot_from_row(row: sqlite3.Row) -> ChunkSnapshot:
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
    )


def _path_in_content_scope(*, path: str, content_scopes: tuple[str, ...]) -> bool:
    return any(path == content_scope or path.startswith(f"{content_scope}/") for content_scope in content_scopes)


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
    )
