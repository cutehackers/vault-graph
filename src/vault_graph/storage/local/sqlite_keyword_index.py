from __future__ import annotations

import json
import re
import sqlite3
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import cast

from vault_graph.errors import KeywordIndexError
from vault_graph.indexing.ingestion.document_authority import DocumentRole
from vault_graph.indexing.ingestion.document_normalizer import ChunkSnapshot, DocumentSnapshot
from vault_graph.indexing.ingestion.hangul_terms import strip_hangul_suffix, word_tokens
from vault_graph.operation.scope.vault_catalog import QueryScope
from vault_graph.storage.interfaces.keyword_index import KeywordHit, KeywordQuery
from vault_graph.storage.interfaces.store_health import StoreHealth

SQLITE_KEYWORD_BACKEND = "sqlite-fts5"
# v3 (spec 2026-11-05 §10.2 원인5): an `aliases` column, and `frontmatter` holds tags and summary only.
KEYWORD_SCHEMA_VERSION = "sqlite-keyword-v3"

# bm25() weight per keyword_chunks column, in column order (spec 2026-11-05 §10.2 원인5). Fields that name
# the page (title, aliases) weigh 10, the file path 5, and the other fields 1. The tiers follow the
# per-column weight example of the SQLite FTS5 manual, `bm25(email, 10.0, 5.0)` with 1.0 for the rest
# (https://www.sqlite.org/fts5.html#the_bm25_function). They are a fixed rule, not fitted to any question set.
KEYWORD_COLUMN_WEIGHTS: tuple[tuple[str, float], ...] = (
    ("path", 5.0),
    ("section", 1.0),
    ("title", 10.0),
    ("aliases", 10.0),
    ("frontmatter", 1.0),
    ("text", 1.0),
)
_BM25 = f"bm25(keyword_chunks, {', '.join(str(weight) for _, weight in KEYWORD_COLUMN_WEIGHTS)})"
# Frontmatter keys whose values the `frontmatter` column keeps, in this order. Title and aliases have columns.
KEYWORD_FRONTMATTER_KEYS: tuple[str, ...] = ("tags", "summary")

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
  aliases,
  frontmatter,
  text,
  content='',
  contentless_delete=1,
  tokenize='unicode61'
);
"""

REQUIRED_KEYWORD_COLUMNS = tuple(column for column, _ in KEYWORD_COLUMN_WEIGHTS)


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
                       {_BM25} AS score
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
            tokens = query_terms(query.query_text)
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
        _insert_keyword_text(
            connection,
            rowid=cast(int, cursor.lastrowid),
            path=chunk.path,
            section=" > ".join(chunk.section_path) or chunk.section or "",
            frontmatter=document.frontmatter,
            keyword_metadata=chunk.keyword_metadata,
            text=chunk.text,
        )


def _insert_keyword_text(
    connection: sqlite3.Connection,
    *,
    rowid: int,
    path: str,
    section: str,
    frontmatter: Mapping[str, object],
    keyword_metadata: str | None,
    text: str,
) -> None:
    connection.execute(
        """
        INSERT INTO keyword_chunks (
          rowid, path, section, title, aliases, frontmatter, text
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            rowid,
            path,
            section,
            _title(frontmatter, path),
            _aliases(frontmatter),
            _slim_frontmatter(frontmatter, keyword_metadata),
            text,
        ),
    )


def keyword_frontmatter(document: DocumentSnapshot, chunk: ChunkSnapshot) -> str:
    """The `frontmatter` column value: tags and summary, then the chunk's keyword metadata line if any.

    Other frontmatter (links, ids, hashes, dates) is left out: it names other pages or nothing a reader
    asks for (spec 2026-11-05 §10.2 원인5). Session windows carry exchange metadata (files, commands, tools,
    errors, outcome) here and not in `text`, so it is searchable without reaching window text or embedding
    input (§4.2.6-8).
    """
    return _slim_frontmatter(document.frontmatter, chunk.keyword_metadata)


def keyword_aliases(document: DocumentSnapshot) -> str:
    """The `aliases` column value: the frontmatter aliases joined by ", "."""
    return _aliases(document.frontmatter)


def _slim_frontmatter(frontmatter: Mapping[str, object], keyword_metadata: str | None) -> str:
    values = [" ".join(_frontmatter_texts(frontmatter.get(key))) for key in KEYWORD_FRONTMATTER_KEYS]
    if keyword_metadata:
        values.append(keyword_metadata)
    return "\n".join(value for value in values if value)


def _aliases(frontmatter: Mapping[str, object]) -> str:
    return ", ".join(_frontmatter_texts(frontmatter.get("aliases")))


def _frontmatter_texts(value: object) -> tuple[str, ...]:
    """Non-empty texts of a scalar or list value, in written order. Nested mappings and lists are skipped."""
    items = value if isinstance(value, list | tuple) else (value,)
    texts = (str(item).strip() for item in items if item is not None and not isinstance(item, dict | list | tuple))
    return tuple(text for text in texts if text)


def ensure_keyword_schema(connection: sqlite3.Connection) -> None:
    """Create the keyword tables, or rebuild them when another schema version wrote them.

    A rebuild drops `keyword_rows` and `keyword_chunks` and refills them from the `documents`, `chunks` and
    `content_blobs` tables of the same database. So a Graph Home written by an older version becomes
    searchable on the next writable open (`vg index`), even when no Vault file changed.
    """
    rebuild = _stored_keyword_schema_version(connection) != KEYWORD_SCHEMA_VERSION
    if rebuild:
        connection.execute("DROP TABLE IF EXISTS keyword_chunks")
        connection.execute("DROP TABLE IF EXISTS keyword_rows")
    connection.executescript(KEYWORD_SCHEMA)
    if rebuild:
        _refill_keyword_rows(connection)
    connection.execute(
        """
        INSERT INTO keyword_projection_metadata (key, value)
        VALUES ('schema_version', ?)
        ON CONFLICT(key) DO UPDATE SET value = excluded.value
        """,
        (KEYWORD_SCHEMA_VERSION,),
    )


def _stored_keyword_schema_version(connection: sqlite3.Connection) -> str | None:
    table = connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'keyword_projection_metadata'"
    ).fetchone()
    if table is None:
        return None
    row = connection.execute("SELECT value FROM keyword_projection_metadata WHERE key = 'schema_version'").fetchone()
    return None if row is None else str(row[0])


def _refill_keyword_rows(connection: sqlite3.Connection) -> None:
    """Write one keyword row per stored chunk of a live document. Does nothing before the metadata tables exist.

    The version row is written after this in the same transaction, so a rebuild that stops halfway runs again.
    """
    tables = {
        str(row[0]) for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
    }
    if not {"documents", "chunks", "content_blobs"} <= tables:
        return
    chunk_columns = {str(row[1]) for row in connection.execute("PRAGMA table_info(chunks)").fetchall()}
    keyword_metadata = "c.keyword_metadata" if "keyword_metadata" in chunk_columns else "NULL"
    rows = connection.execute(
        f"""
        SELECT c.vault_id, c.document_id, c.chunk_id, c.path, c.section, c.section_path_json,
               c.source_role, c.provenance_family_id,
               COALESCE(c.index_revision, d.index_revision, '') AS index_revision,
               d.frontmatter_json, b.text, {keyword_metadata} AS keyword_metadata
        FROM chunks c
        INNER JOIN documents d ON d.vault_id = c.vault_id AND d.document_id = c.document_id
        INNER JOIN content_blobs b ON b.blob_hash = c.blob_hash
        WHERE d.is_tombstoned = 0
        ORDER BY c.vault_id, c.path, c.document_order, c.chunk_id
        """
    ).fetchall()
    for row in rows:
        path = str(row[3])
        cursor = connection.execute(
            """
            INSERT INTO keyword_rows (
              vault_id, document_id, chunk_id, path, content_scope, source_role,
              provenance_family_id, index_revision
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (row[0], row[1], row[2], path, _content_scope_for_path(path), row[6], row[7], row[8]),
        )
        section_path = json.loads(row[5] or "[]")
        frontmatter = json.loads(row[9] or "{}")
        _insert_keyword_text(
            connection,
            rowid=cast(int, cursor.lastrowid),
            path=path,
            section=" > ".join(str(part) for part in section_path) or row[4] or "",
            frontmatter=frontmatter if isinstance(frontmatter, dict) else {},
            keyword_metadata=row[11],
            text=str(row[10]),
        )


@dataclass(frozen=True)
class QueryTerm:
    """One FTS5 query term. ``prefix`` terms match every indexed token that starts with ``text``."""

    text: str
    prefix: bool = False

    def fts_expression(self, column: str | None = None) -> str:
        quoted = f'"{self.text.replace('"', '""')}"'
        term = f"{quoted}*" if self.prefix else quoted
        return f"{column}:{term}" if column else term


# Spec 2026-11-05 §10.2 원인6: the query side drops one Korean particle or ending (`hangul_terms`) and
# matches Hangul stems by prefix.
# Hangul terms this long or longer match by prefix. Shorter ones stay exact: a two-letter prefix matches
# too many unrelated words.
HANGUL_PREFIX_MIN_LETTERS = 3
_HANGUL_WORD = re.compile(r"[가-힣]+")


def query_terms(query_text: str) -> tuple[QueryTerm, ...]:
    """Deterministic FTS5 terms of a query: each word, plus its stem without a Korean particle or ending.

    A Hangul-only term of ``HANGUL_PREFIX_MIN_LETTERS`` or more letters is a prefix term. When a stem is a
    prefix term the original word is left out, because the stem already matches it.
    """
    terms: list[QueryTerm] = []
    for token in _query_tokens(query_text):
        stem = strip_hangul_suffix(token)
        stem_term = _term(stem)
        if stem == token:
            terms.append(stem_term)
        elif stem_term.prefix:
            terms.append(stem_term)
        else:
            terms.extend((_term(token), stem_term))
    return tuple(dict.fromkeys(terms))


def _term(text: str) -> QueryTerm:
    return QueryTerm(
        text=text,
        prefix=_HANGUL_WORD.fullmatch(text) is not None and len(text) >= HANGUL_PREFIX_MIN_LETTERS,
    )


def _match_query(query_text: str) -> str:
    terms = query_terms(query_text)
    if not terms:
        raise KeywordIndexError("query_text has no searchable tokens")
    return " OR ".join(term.fts_expression() for term in terms)


def _query_tokens(query_text: str) -> tuple[str, ...]:
    return word_tokens(query_text)


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
    tokens: tuple[QueryTerm, ...],
) -> tuple[str, ...]:
    matched = tuple(
        field
        for field in ("title", "aliases", "section", "frontmatter", "text", "path")
        if _row_matches_field(connection, rowid=rowid, field=field, tokens=tokens)
    )
    return matched or ("text",)


def _row_matches_field(
    connection: sqlite3.Connection,
    *,
    rowid: int,
    field: str,
    tokens: tuple[QueryTerm, ...],
) -> bool:
    expression = " OR ".join(token.fts_expression(field) for token in tokens)
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


def _title(frontmatter: Mapping[str, object], path: str) -> str:
    title = frontmatter.get("title")
    return str(title) if title is not None else PurePosixPath(path).stem


def _content_scope_for_path(path: str) -> str:
    parent = PurePosixPath(path).parent.as_posix()
    if parent == ".":
        return path.split("/", 1)[0]
    return parent
