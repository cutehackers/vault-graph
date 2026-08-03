from __future__ import annotations

import json
import re
import sqlite3
from pathlib import Path, PurePosixPath
from typing import cast

from vault_graph.errors import KeywordIndexError
from vault_graph.ingestion.document_authority import DocumentRole
from vault_graph.ingestion.document_normalizer import ChunkSnapshot, DocumentSnapshot
from vault_graph.ingestion.vault_catalog import QueryScope
from vault_graph.storage.interfaces.keyword_index import KeywordHit, KeywordQuery
from vault_graph.storage.interfaces.store_health import StoreHealth

SQLITE_KEYWORD_BACKEND = "sqlite-fts5"
KEYWORD_SCHEMA_VERSION = "sqlite-keyword-v2"

KEYWORD_SCHEMA = """
CREATE TABLE IF NOT EXISTS keyword_projection_metadata (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS keyword_rows (
  rowid INTEGER PRIMARY KEY,
  vault_id TEXT NOT NULL,
  document_id TEXT NOT NULL,
  chunk_id TEXT NOT NULL,
  path TEXT NOT NULL,
  content_scope TEXT NOT NULL,
  source_role TEXT NOT NULL,
  provenance_family_id TEXT NOT NULL,
  index_revision TEXT NOT NULL,
  UNIQUE (vault_id, chunk_id)
);

CREATE VIRTUAL TABLE IF NOT EXISTS keyword_chunks USING fts5(
  path,
  section,
  title,
  frontmatter,
  text,
  content='',
  contentless_delete=1,
  tokenize='unicode61'
);
"""

REQUIRED_KEYWORD_COLUMNS = (
    "path",
    "section",
    "title",
    "frontmatter",
    "text",
)


class SQLiteKeywordIndex:
    def __init__(self, database_path: Path) -> None:
        self._database_path = database_path.expanduser().resolve()

    def search(self, query: KeywordQuery) -> tuple[KeywordHit, ...]:
        health = self.health()
        if not health.ok or not health.schema_compatible:
            raise KeywordIndexError(f"keyword index unavailable: {health.message}. Run `vg index`.")
        match_query = _match_query(query.query_text)
        vault_placeholders = ", ".join("?" for _ in query.scope.vault_ids)
        path_clause, path_args = _content_scope_clause(query.scope.content_scopes)
        role_clause, role_args = _source_role_clause(query.source_roles)
        with self._connect_readonly() as connection:
            rows = connection.execute(
                f"""
                SELECT r.rowid, r.vault_id, r.document_id, r.chunk_id, r.path,
                       r.source_role, r.provenance_family_id, r.index_revision,
                       bm25(keyword_chunks) AS score
                FROM keyword_chunks
                INNER JOIN keyword_rows r ON r.rowid = keyword_chunks.rowid
                WHERE keyword_chunks MATCH ?
                  AND r.vault_id IN ({vault_placeholders})
                  AND ({path_clause})
                  AND ({role_clause})
                ORDER BY score ASC, r.vault_id ASC, r.path ASC, r.chunk_id ASC
                LIMIT ?
                """,
                (match_query, *query.scope.vault_ids, *path_args, *role_args, query.limit),
            ).fetchall()
            tokens = _query_tokens(query.query_text)
            return tuple(
                _keyword_hit_from_row(
                    rank=rank,
                    row=row,
                    matched_fields=_matched_fields(connection, rowid=int(row["rowid"]), tokens=tokens),
                )
                for rank, row in enumerate(rows, start=1)
            )

    def index_revision(self, scope: QueryScope) -> str:
        health = self.health()
        if not health.ok or not health.schema_compatible:
            raise KeywordIndexError(f"keyword index unavailable: {health.message}. Run `vg index`.")
        vault_placeholders = ", ".join("?" for _ in scope.vault_ids)
        path_clause, path_args = _content_scope_clause(scope.content_scopes)
        with self._connect_readonly() as connection:
            rows = connection.execute(
                f"""
                SELECT DISTINCT index_revision
                FROM keyword_rows r
                WHERE vault_id IN ({vault_placeholders})
                  AND ({path_clause})
                ORDER BY index_revision
                """,
                (*scope.vault_ids, *path_args),
            ).fetchall()
        revisions = tuple(str(row["index_revision"]) for row in rows if row["index_revision"])
        return ",".join(revisions) if revisions else f"empty:{KEYWORD_SCHEMA_VERSION}"

    def health(self) -> StoreHealth:
        if not self._database_path.exists():
            return StoreHealth(
                ok=False,
                backend=SQLITE_KEYWORD_BACKEND,
                schema_version=KEYWORD_SCHEMA_VERSION,
                schema_compatible=False,
                message="not initialized",
            )
        try:
            with self._connect_readonly() as connection:
                tables = {
                    str(row["name"])
                    for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
                }
                missing = {"keyword_projection_metadata", "keyword_rows", "keyword_chunks"} - tables
                if missing:
                    return StoreHealth(
                        ok=False,
                        backend=SQLITE_KEYWORD_BACKEND,
                        schema_version=KEYWORD_SCHEMA_VERSION,
                        schema_compatible=False,
                        message=f"schema incompatible: missing {', '.join(sorted(missing))}",
                    )
                version = connection.execute(
                    "SELECT value FROM keyword_projection_metadata WHERE key = 'schema_version'"
                ).fetchone()
                if version is None or str(version["value"]) != KEYWORD_SCHEMA_VERSION:
                    return StoreHealth(
                        ok=False,
                        backend=SQLITE_KEYWORD_BACKEND,
                        schema_version=KEYWORD_SCHEMA_VERSION,
                        schema_compatible=False,
                        message="schema incompatible: keyword schema version mismatch",
                    )
                columns = {
                    str(row["name"]) for row in connection.execute("PRAGMA table_info(keyword_chunks)").fetchall()
                }
                missing_columns = set(REQUIRED_KEYWORD_COLUMNS) - columns
                if missing_columns:
                    return StoreHealth(
                        ok=False,
                        backend=SQLITE_KEYWORD_BACKEND,
                        schema_version=KEYWORD_SCHEMA_VERSION,
                        schema_compatible=False,
                        message=f"schema incompatible: missing keyword columns {', '.join(sorted(missing_columns))}",
                    )
        except sqlite3.Error as exc:
            return StoreHealth(
                ok=False,
                backend=SQLITE_KEYWORD_BACKEND,
                schema_version=KEYWORD_SCHEMA_VERSION,
                schema_compatible=False,
                message=str(exc),
            )
        return StoreHealth(
            ok=True,
            backend=SQLITE_KEYWORD_BACKEND,
            schema_version=KEYWORD_SCHEMA_VERSION,
            schema_compatible=True,
            message="ok",
        )

    def _connect_readonly(self) -> sqlite3.Connection:
        connection = sqlite3.connect(f"file:{self._database_path}?mode=ro", uri=True)
        connection.row_factory = sqlite3.Row
        return connection


def apply_keyword_revision(
    connection: sqlite3.Connection,
    *,
    index_revision: str,
    documents: list[DocumentSnapshot],
    chunks: list[ChunkSnapshot],
    tombstones: list[tuple[str, str]],
) -> None:
    ensure_keyword_schema(connection)
    for document in documents:
        _delete_keyword_rows(connection, vault_id=document.vault_id, document_id=document.document_id)
    for vault_id, path in tombstones:
        _delete_keyword_rows(connection, vault_id=vault_id, path=path)
    documents_by_id = {(document.vault_id, document.document_id): document for document in documents}
    for chunk in chunks:
        document = documents_by_id[(chunk.vault_id, chunk.document_id)]
        cursor = connection.execute(
            """
            INSERT INTO keyword_rows (
              vault_id, document_id, chunk_id, path, content_scope, source_role,
              provenance_family_id, index_revision
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                chunk.vault_id,
                chunk.document_id,
                chunk.chunk_id,
                chunk.path,
                _content_scope_for_path(chunk.path),
                chunk.source_role,
                chunk.provenance_family_id,
                index_revision,
            ),
        )
        connection.execute(
            """
            INSERT INTO keyword_chunks (
              rowid, path, section, title, frontmatter, text
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                cursor.lastrowid,
                chunk.path,
                chunk.section or "",
                _title_for_document(document),
                json.dumps(document.frontmatter, sort_keys=True),
                chunk.text,
            ),
        )


def ensure_keyword_schema(connection: sqlite3.Connection) -> None:
    connection.executescript(KEYWORD_SCHEMA)
    connection.execute(
        """
        INSERT INTO keyword_projection_metadata (key, value)
        VALUES ('schema_version', ?)
        ON CONFLICT(key) DO UPDATE SET value = excluded.value
        """,
        (KEYWORD_SCHEMA_VERSION,),
    )


def _match_query(query_text: str) -> str:
    tokens = _query_tokens(query_text)
    if not tokens:
        raise KeywordIndexError("query_text has no searchable tokens")
    return " OR ".join(f'"{token.replace('"', '""')}"' for token in tokens)


def _query_tokens(query_text: str) -> tuple[str, ...]:
    return tuple(re.findall(r"[\w가-힣]+", query_text, flags=re.UNICODE))


def _content_scope_clause(content_scopes: tuple[str, ...]) -> tuple[str, tuple[str, ...]]:
    clauses: list[str] = []
    args: list[str] = []
    for content_scope in content_scopes:
        clauses.append("(r.path = ? OR r.path LIKE ?)")
        args.extend((content_scope, f"{content_scope}/%"))
    return " OR ".join(clauses), tuple(args)


def _keyword_hit_from_row(*, rank: int, row: sqlite3.Row, matched_fields: tuple[str, ...]) -> KeywordHit:
    return KeywordHit(
        vault_id=str(row["vault_id"]),
        document_id=str(row["document_id"]),
        chunk_id=str(row["chunk_id"]),
        rank=rank,
        score=float(row["score"]),
        backend=SQLITE_KEYWORD_BACKEND,
        index_revision=str(row["index_revision"]),
        matched_fields=matched_fields,
        source_role=cast(DocumentRole, str(row["source_role"])),
        provenance_family_id=str(row["provenance_family_id"]),
    )


def _matched_fields(
    connection: sqlite3.Connection,
    *,
    rowid: int,
    tokens: tuple[str, ...],
) -> tuple[str, ...]:
    matched = tuple(
        field
        for field in ("title", "section", "frontmatter", "text", "path")
        if _row_matches_field(connection, rowid=rowid, field=field, tokens=tokens)
    )
    return matched or ("text",)


def _row_matches_field(
    connection: sqlite3.Connection,
    *,
    rowid: int,
    field: str,
    tokens: tuple[str, ...],
) -> bool:
    expression = " OR ".join(f'{field}:"{token.replace(chr(34), chr(34) * 2)}"' for token in tokens)
    row = connection.execute(
        "SELECT 1 FROM keyword_chunks WHERE rowid = ? AND keyword_chunks MATCH ?",
        (rowid, expression),
    ).fetchone()
    return row is not None


def _source_role_clause(source_roles: tuple[DocumentRole, ...]) -> tuple[str, tuple[str, ...]]:
    if not source_roles:
        return "1", ()
    return f"r.source_role IN ({', '.join('?' for _ in source_roles)})", tuple(source_roles)


def _delete_keyword_rows(
    connection: sqlite3.Connection,
    *,
    vault_id: str,
    document_id: str | None = None,
    path: str | None = None,
) -> None:
    if document_id is not None:
        rows = connection.execute(
            "SELECT rowid FROM keyword_rows WHERE vault_id = ? AND document_id = ?",
            (vault_id, document_id),
        ).fetchall()
    elif path is not None:
        rows = connection.execute(
            "SELECT rowid FROM keyword_rows WHERE vault_id = ? AND path = ?",
            (vault_id, path),
        ).fetchall()
    else:
        raise KeywordIndexError("document_id or path is required")
    for row in rows:
        connection.execute("DELETE FROM keyword_chunks WHERE rowid = ?", (int(row["rowid"]),))
        connection.execute("DELETE FROM keyword_rows WHERE rowid = ?", (int(row["rowid"]),))


def _title_for_document(document: DocumentSnapshot) -> str:
    title = document.frontmatter.get("title")
    return str(title) if title is not None else PurePosixPath(document.path).stem


def _content_scope_for_path(path: str) -> str:
    parent = PurePosixPath(path).parent.as_posix()
    if parent == ".":
        return path.split("/", 1)[0]
    return parent
