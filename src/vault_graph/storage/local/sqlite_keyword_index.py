from __future__ import annotations

import json
import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import cast

from vault_graph.errors import KeywordIndexError
from vault_graph.indexing.ingestion.document_authority import DocumentRole
from vault_graph.indexing.ingestion.document_normalizer import ChunkSnapshot, DocumentSnapshot
from vault_graph.operation.scope.vault_catalog import QueryScope
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
                " > ".join(chunk.section_path) or chunk.section or "",
                _title_for_document(document),
                keyword_frontmatter(document, chunk),
                chunk.text,
            ),
        )


def keyword_frontmatter(document: DocumentSnapshot, chunk: ChunkSnapshot) -> str:
    """The `frontmatter` column value: document frontmatter, then the chunk's keyword metadata line if any.

    Session windows carry exchange metadata (files, commands, tools, errors, outcome) here and not in
    `text`, so it is searchable without reaching window text or embedding input (spec 2026-11-05 §4.2.6-8).
    """
    frontmatter = json.dumps(document.frontmatter, sort_keys=True)
    if not chunk.keyword_metadata:
        return frontmatter
    return f"{frontmatter}\n{chunk.keyword_metadata}"


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


@dataclass(frozen=True)
class QueryTerm:
    """One FTS5 query term. ``prefix`` terms match every indexed token that starts with ``text``."""

    text: str
    prefix: bool = False

    def fts_expression(self, column: str | None = None) -> str:
        quoted = f'"{self.text.replace('"', '""')}"'
        term = f"{quoted}*" if self.prefix else quoted
        return f"{column}:{term}" if column else term


# Spec 2026-11-05 §10.2 원인6. `unicode61` keeps a Korean word and its particle as one token ("아이디어를"),
# so the query side drops one trailing particle or common ending and matches Hangul stems by prefix.
# The particle list extends the Vault's own wiki search list (`tools/wiki/lib/search.py`). Longest first.
HANGUL_QUERY_SUFFIXES: tuple[str, ...] = tuple(
    sorted(
        {
            # particles
            "에서는",
            "에서도",
            "으로는",
            "으로서",
            "으로써",
            "에게서",
            "이라는",
            "이라고",
            "에서",
            "에게",
            "한테",
            "으로",
            "로서",
            "로써",
            "까지",
            "부터",
            "보다",
            "처럼",
            "마다",
            "이나",
            "이랑",
            "라는",
            "라고",
            "들을",
            "들이",
            "들의",
            "들은",
            "은",
            "는",
            "이",
            "가",
            "을",
            "를",
            "의",
            "에",
            "로",
            "와",
            "과",
            "도",
            "만",
            "랑",
            "들",
            # common endings
            "했습니다",
            "합니다",
            "하려면",
            "하려는",
            "하는",
            "하기",
            "하고",
            "하면",
            "해서",
            "했다",
            "한다",
            "하다",
            "된다",
            "되는",
            "된",
            "한",
        },  # fmt: skip
        key=lambda suffix: (-len(suffix), suffix),
    )
)
# A stem keeps at least this many letters, so "회의" is not read as "회" + "의".
HANGUL_STEM_MIN_LETTERS = 2
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
        stem = _strip_hangul_suffix(token)
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


def _strip_hangul_suffix(token: str) -> str:
    for suffix in HANGUL_QUERY_SUFFIXES:
        if token.endswith(suffix) and len(token) - len(suffix) >= HANGUL_STEM_MIN_LETTERS:
            return token[: -len(suffix)]
    return token


def _match_query(query_text: str) -> str:
    terms = query_terms(query_text)
    if not terms:
        raise KeywordIndexError("query_text has no searchable tokens")
    return " OR ".join(term.fts_expression() for term in terms)


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
    tokens: tuple[QueryTerm, ...],
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


def _title_for_document(document: DocumentSnapshot) -> str:
    title = document.frontmatter.get("title")
    return str(title) if title is not None else PurePosixPath(document.path).stem


def _content_scope_for_path(path: str) -> str:
    parent = PurePosixPath(path).parent.as_posix()
    if parent == ".":
        return path.split("/", 1)[0]
    return parent
