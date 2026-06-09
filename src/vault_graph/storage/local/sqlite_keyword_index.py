from __future__ import annotations

import json
import re
import sqlite3
from pathlib import Path, PurePosixPath

from vault_graph.errors import KeywordIndexError
from vault_graph.ingestion.document_normalizer import ChunkSnapshot, DocumentSnapshot
from vault_graph.ingestion.vault_catalog import QueryScope
from vault_graph.storage.interfaces.keyword_index import KeywordHit, KeywordQuery
from vault_graph.storage.interfaces.store_health import StoreHealth

SQLITE_KEYWORD_BACKEND = "sqlite-fts5"
KEYWORD_SCHEMA_VERSION = "sqlite-keyword-v1"

KEYWORD_SCHEMA = """
CREATE TABLE IF NOT EXISTS keyword_projection_metadata (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL
);

CREATE VIRTUAL TABLE IF NOT EXISTS keyword_chunks USING fts5(
  vault_id UNINDEXED,
  document_id UNINDEXED,
  chunk_id UNINDEXED,
  path,
  section,
  anchor UNINDEXED,
  title,
  frontmatter,
  text,
  content_scope UNINDEXED,
  index_revision UNINDEXED,
  tokenize='unicode61'
);
"""

REQUIRED_KEYWORD_COLUMNS = (
    "vault_id",
    "document_id",
    "chunk_id",
    "path",
    "section",
    "anchor",
    "title",
    "frontmatter",
    "text",
    "content_scope",
    "index_revision",
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
        with self._connect_readonly() as connection:
            rows = connection.execute(
                f"""
                SELECT vault_id, document_id, chunk_id, path, section, title, frontmatter, text,
                       index_revision, bm25(keyword_chunks) AS score
                FROM keyword_chunks
                WHERE keyword_chunks MATCH ?
                  AND vault_id IN ({vault_placeholders})
                  AND ({path_clause})
                ORDER BY score ASC, vault_id ASC, path ASC, chunk_id ASC
                LIMIT ?
                """,
                (match_query, *query.scope.vault_ids, *path_args, query.limit),
            ).fetchall()
        tokens = _query_tokens(query.query_text)
        return tuple(_keyword_hit_from_row(rank=rank, row=row, tokens=tokens) for rank, row in enumerate(rows, start=1))

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
                FROM keyword_chunks
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
                missing = {"keyword_projection_metadata", "keyword_chunks"} - tables
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
        connection.execute(
            "DELETE FROM keyword_chunks WHERE vault_id = ? AND document_id = ?",
            (document.vault_id, document.document_id),
        )
    for vault_id, path in tombstones:
        connection.execute("DELETE FROM keyword_chunks WHERE vault_id = ? AND path = ?", (vault_id, path))
    documents_by_id = {(document.vault_id, document.document_id): document for document in documents}
    for chunk in chunks:
        document = documents_by_id[(chunk.vault_id, chunk.document_id)]
        connection.execute(
            """
            INSERT INTO keyword_chunks (
              vault_id, document_id, chunk_id, path, section, anchor, title, frontmatter,
              text, content_scope, index_revision
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                chunk.vault_id,
                chunk.document_id,
                chunk.chunk_id,
                chunk.path,
                chunk.section or "",
                chunk.anchor or "",
                _title_for_document(document),
                json.dumps(document.frontmatter, sort_keys=True),
                chunk.text,
                _content_scope_for_path(chunk.path),
                index_revision,
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
        clauses.append("(path = ? OR path LIKE ?)")
        args.extend((content_scope, f"{content_scope}/%"))
    return " OR ".join(clauses), tuple(args)


def _keyword_hit_from_row(*, rank: int, row: sqlite3.Row, tokens: tuple[str, ...]) -> KeywordHit:
    return KeywordHit(
        vault_id=str(row["vault_id"]),
        document_id=str(row["document_id"]),
        chunk_id=str(row["chunk_id"]),
        rank=rank,
        score=float(row["score"]),
        backend=SQLITE_KEYWORD_BACKEND,
        index_revision=str(row["index_revision"]),
        matched_fields=_matched_fields(row, tokens=tokens),
    )


def _matched_fields(row: sqlite3.Row, *, tokens: tuple[str, ...]) -> tuple[str, ...]:
    lowered_tokens = tuple(token.casefold() for token in tokens)
    matched = tuple(
        field
        for field in ("title", "section", "frontmatter", "text", "path")
        if _field_matches_tokens(value=str(row[field] or ""), lowered_tokens=lowered_tokens)
    )
    return matched or ("text",)


def _field_matches_tokens(*, value: str, lowered_tokens: tuple[str, ...]) -> bool:
    lowered_value = value.casefold()
    return any(token in lowered_value for token in lowered_tokens)


def _title_for_document(document: DocumentSnapshot) -> str:
    title = document.frontmatter.get("title")
    return str(title) if title is not None else PurePosixPath(document.path).stem


def _content_scope_for_path(path: str) -> str:
    parent = PurePosixPath(path).parent.as_posix()
    if parent == ".":
        return path.split("/", 1)[0]
    return parent
