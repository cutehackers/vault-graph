"""SQLite/FTS5 storage for the rebuildable code projection.

Only structural metadata is persisted.  Complete source text remains in the
registered repository and is intentionally not represented by any table in
this module.
"""

from __future__ import annotations

import json
import re
import sqlite3
from collections import deque
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast
from urllib.parse import quote

from vault_graph.code_index.code_models import (
    CODE_PARSER_SPEC_VERSION,
    CODE_PROJECTION_SCHEMA_VERSION,
    CodeApplyResult,
    CodeEdgeRecord,
    CodeExtractionStatus,
    CodeFileSnapshot,
    CodeManifest,
    CodeReconcilePlan,
    CodeSymbolHit,
    CodeSymbolQuery,
    CodeSymbolRecord,
    CodeTraversalQuery,
    CodeTraversalResult,
)
from vault_graph.storage.interfaces.store_health import StoreHealth

CODE_SQLITE_BACKEND = "sqlite-code"

REQUIRED_TABLES = {
    "code_metadata",
    "repositories",
    "files",
    "symbols",
    "edges",
    "pending_references",
    "symbol_fts",
    "projection_runs",
    "file_fingerprints",
}

SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS code_metadata (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS repositories (
  repository_id TEXT PRIMARY KEY,
  source_revision TEXT NOT NULL,
  policy_revision TEXT NOT NULL,
  parser_spec_version TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS files (
  file_id TEXT PRIMARY KEY,
  repository_id TEXT NOT NULL REFERENCES repositories(repository_id),
  relative_path TEXT NOT NULL,
  language TEXT NOT NULL,
  content_hash TEXT NOT NULL,
  byte_count INTEGER NOT NULL,
  line_count INTEGER NOT NULL,
  source_revision TEXT NOT NULL,
  is_test_file INTEGER NOT NULL CHECK (is_test_file IN (0, 1)),
  parser_spec_version TEXT NOT NULL,
  UNIQUE (repository_id, relative_path)
);

CREATE TABLE IF NOT EXISTS symbols (
  symbol_id TEXT PRIMARY KEY,
  repository_id TEXT NOT NULL REFERENCES repositories(repository_id),
  file_id TEXT NOT NULL REFERENCES files(file_id),
  kind TEXT NOT NULL,
  language_kind TEXT NOT NULL,
  name TEXT NOT NULL,
  qualified_name TEXT NOT NULL,
  signature TEXT,
  start_line INTEGER NOT NULL,
  end_line INTEGER NOT NULL,
  start_column INTEGER NOT NULL,
  end_column INTEGER NOT NULL,
  content_hash TEXT NOT NULL,
  source_revision TEXT NOT NULL,
  parser_spec_version TEXT NOT NULL,
  UNIQUE (repository_id, file_id, qualified_name, start_line, start_column)
);

CREATE TABLE IF NOT EXISTS edges (
  edge_id TEXT PRIMARY KEY,
  repository_id TEXT NOT NULL REFERENCES repositories(repository_id),
  source_symbol_id TEXT NOT NULL REFERENCES symbols(symbol_id),
  relation_kind TEXT NOT NULL,
  target_symbol_id TEXT REFERENCES symbols(symbol_id),
  unresolved_target_key TEXT,
  extraction_status TEXT NOT NULL,
  anchor_start_line INTEGER NOT NULL,
  anchor_start_column INTEGER NOT NULL,
  parser_spec_version TEXT NOT NULL,
  CHECK (target_symbol_id IS NOT NULL OR unresolved_target_key IS NOT NULL)
);

CREATE TABLE IF NOT EXISTS pending_references (
  pending_id TEXT PRIMARY KEY,
  repository_id TEXT NOT NULL REFERENCES repositories(repository_id),
  reference_id TEXT NOT NULL,
  source_revision TEXT NOT NULL,
  relation_kind TEXT NOT NULL,
  target_key TEXT NOT NULL,
  reason TEXT NOT NULL,
  parser_spec_version TEXT NOT NULL,
  UNIQUE (repository_id, reference_id)
);

CREATE VIRTUAL TABLE IF NOT EXISTS symbol_fts USING fts5(
  relative_path,
  name,
  qualified_name,
  signature,
  language,
  kind,
  content='',
  contentless_delete=1,
  tokenize='unicode61'
);

CREATE TABLE IF NOT EXISTS projection_runs (
  run_id TEXT PRIMARY KEY,
  generation_id TEXT NOT NULL,
  status TEXT NOT NULL,
  repository_ids_json TEXT NOT NULL,
  file_count INTEGER NOT NULL,
  symbol_count INTEGER NOT NULL,
  edge_count INTEGER NOT NULL,
  pending_reference_count INTEGER NOT NULL,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS file_fingerprints (
  file_id TEXT PRIMARY KEY REFERENCES files(file_id),
  content_hash TEXT NOT NULL,
  source_revision TEXT NOT NULL,
  parser_spec_version TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_code_files_repository_path ON files(repository_id, relative_path);
CREATE INDEX IF NOT EXISTS idx_code_symbols_repository_name ON symbols(repository_id, name, qualified_name);
CREATE INDEX IF NOT EXISTS idx_code_symbols_file ON symbols(repository_id, file_id, start_line, start_column);
CREATE INDEX IF NOT EXISTS idx_code_edges_source ON edges(repository_id, source_symbol_id, edge_id);
CREATE INDEX IF NOT EXISTS idx_code_edges_target ON edges(repository_id, target_symbol_id, edge_id);
CREATE INDEX IF NOT EXISTS idx_code_pending_repository ON pending_references(repository_id, target_key, pending_id);
"""

_REQUIRED_COLUMNS: dict[str, set[str]] = {
    "code_metadata": {"key", "value"},
    "repositories": {"repository_id", "source_revision", "policy_revision", "parser_spec_version"},
    "files": {
        "file_id",
        "repository_id",
        "relative_path",
        "language",
        "content_hash",
        "byte_count",
        "line_count",
        "source_revision",
        "is_test_file",
        "parser_spec_version",
    },
    "symbols": {
        "symbol_id",
        "repository_id",
        "file_id",
        "kind",
        "language_kind",
        "name",
        "qualified_name",
        "signature",
        "start_line",
        "end_line",
        "start_column",
        "end_column",
        "content_hash",
        "source_revision",
        "parser_spec_version",
    },
    "edges": {
        "edge_id",
        "repository_id",
        "source_symbol_id",
        "relation_kind",
        "target_symbol_id",
        "unresolved_target_key",
        "extraction_status",
        "anchor_start_line",
        "anchor_start_column",
        "parser_spec_version",
    },
    "pending_references": {
        "pending_id",
        "repository_id",
        "reference_id",
        "source_revision",
        "relation_kind",
        "target_key",
        "reason",
        "parser_spec_version",
    },
    "symbol_fts": {"relative_path", "name", "qualified_name", "signature", "language", "kind"},
    "projection_runs": {
        "run_id",
        "generation_id",
        "status",
        "repository_ids_json",
        "file_count",
        "symbol_count",
        "edge_count",
        "pending_reference_count",
        "created_at",
    },
    "file_fingerprints": {"file_id", "content_hash", "source_revision", "parser_spec_version"},
}

_QUERY_TOKEN = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


class SQLiteCodeProjectionStore:
    """Transactional code projection store with explicit writable/read-only modes."""

    def __init__(
        self,
        database_path: Path,
        *,
        initialize: bool = False,
        read_only: bool = False,
        parser_spec_version: str = CODE_PARSER_SPEC_VERSION,
        policy_revision: str | None = None,
    ) -> None:
        self._database_path = database_path.expanduser().resolve()
        self._read_only = read_only
        self._expected_parser_spec_version = parser_spec_version
        self._expected_policy_revision = policy_revision
        if initialize and read_only:
            raise ValueError("a read-only store cannot initialize state")
        if initialize:
            self._database_path.parent.mkdir(parents=True, exist_ok=True)
            with self._connect() as connection:
                connection.executescript(SCHEMA)
                _set_metadata(connection, "schema_version", CODE_PROJECTION_SCHEMA_VERSION)
                _set_metadata(connection, "parser_spec_version", parser_spec_version)
                if policy_revision is not None:
                    _set_metadata(connection, "policy_revision", policy_revision)

    @classmethod
    def open_writable(
        cls,
        database_path: Path,
        *,
        parser_spec_version: str = CODE_PARSER_SPEC_VERSION,
        policy_revision: str | None = None,
    ) -> SQLiteCodeProjectionStore:
        return cls(
            database_path,
            initialize=True,
            parser_spec_version=parser_spec_version,
            policy_revision=policy_revision,
        )

    @classmethod
    def open_read_only(
        cls,
        database_path: Path,
        *,
        parser_spec_version: str = CODE_PARSER_SPEC_VERSION,
        policy_revision: str | None = None,
    ) -> SQLiteCodeProjectionStore:
        return cls(
            database_path,
            read_only=True,
            parser_spec_version=parser_spec_version,
            policy_revision=policy_revision,
        )

    @property
    def database_path(self) -> Path:
        return self._database_path

    def health(self) -> StoreHealth:
        if not self._database_path.exists():
            return StoreHealth(
                ok=False,
                backend=CODE_SQLITE_BACKEND,
                schema_version=CODE_PROJECTION_SCHEMA_VERSION,
                schema_compatible=False,
                message="not initialized",
            )
        try:
            with self._connect_readonly() as connection:
                tables = {
                    str(row["name"])
                    for row in connection.execute(
                        "SELECT name FROM sqlite_master WHERE type IN ('table', 'virtual table')"
                    ).fetchall()
                }
                missing = REQUIRED_TABLES - tables
                if missing:
                    return self._incompatible(f"missing {', '.join(sorted(missing))}")
                for table, required_columns in _REQUIRED_COLUMNS.items():
                    columns = {str(row["name"]) for row in connection.execute(f"PRAGMA table_info({table})").fetchall()}
                    missing_columns = required_columns - columns
                    if missing_columns:
                        return self._incompatible(f"missing {table} columns {', '.join(sorted(missing_columns))}")
                schema_version = _metadata(connection, "schema_version")
                if schema_version != CODE_PROJECTION_SCHEMA_VERSION:
                    return self._incompatible("schema version mismatch")
                parser_spec = _metadata(connection, "parser_spec_version")
                if parser_spec != self._expected_parser_spec_version:
                    return self._incompatible("parser spec version mismatch")
                if self._expected_policy_revision is not None and _metadata(connection, "policy_revision") != (
                    self._expected_policy_revision
                ):
                    return self._incompatible("policy revision mismatch")
                manifest_json = _metadata(connection, "manifest_json")
                if manifest_json is not None:
                    try:
                        manifest = _manifest_from_json(manifest_json)
                    except (TypeError, ValueError, json.JSONDecodeError) as exc:
                        return self._incompatible(f"manifest is invalid: {exc}")
                    manifest_issue = self._manifest_integrity_issue(connection, manifest)
                    if manifest_issue is not None:
                        return self._incompatible(f"manifest {manifest_issue}")
                dangling = connection.execute(
                    """
                    SELECT e.edge_id
                    FROM edges e
                    LEFT JOIN symbols source ON source.symbol_id = e.source_symbol_id
                    LEFT JOIN symbols target ON target.symbol_id = e.target_symbol_id
                    WHERE source.symbol_id IS NULL
                       OR (e.target_symbol_id IS NOT NULL AND target.symbol_id IS NULL)
                       OR source.repository_id <> e.repository_id
                       OR (target.symbol_id IS NOT NULL AND target.repository_id <> e.repository_id)
                    LIMIT 1
                    """
                ).fetchone()
                if dangling is not None:
                    return self._incompatible(f"dangling resolved endpoint: {dangling['edge_id']}")
                return StoreHealth(
                    ok=True,
                    backend=CODE_SQLITE_BACKEND,
                    schema_version=CODE_PROJECTION_SCHEMA_VERSION,
                    schema_compatible=True,
                    message="ok",
                )
        except sqlite3.Error as exc:
            return self._incompatible(str(exc))

    def _manifest_integrity_issue(
        self,
        connection: sqlite3.Connection,
        manifest: CodeManifest,
    ) -> str | None:
        if len(set(manifest.repository_ids)) != len(manifest.repository_ids):
            return "contains duplicate repository IDs"
        if len(set(manifest.file_ids)) != len(manifest.file_ids):
            return "contains duplicate file IDs"
        manifest_revisions = dict(manifest.source_revisions)
        if manifest.schema_version != CODE_PROJECTION_SCHEMA_VERSION:
            return "schema version mismatch"
        if manifest.parser_spec_version != self._expected_parser_spec_version:
            return "parser spec version mismatch"
        metadata_policy = _metadata(connection, "policy_revision")
        if metadata_policy != manifest.policy_revision:
            return "policy revision mismatch"
        if len(manifest_revisions) != len(manifest.source_revisions):
            return "contains duplicate source revisions"
        if set(manifest_revisions) - set(manifest.repository_ids):
            return "contains an out-of-scope source revision"
        placeholders = ",".join("?" for _ in manifest.repository_ids)
        repositories = connection.execute(
            f"SELECT repository_id, source_revision FROM repositories WHERE repository_id IN ({placeholders})",
            manifest.repository_ids,
        ).fetchall()
        repository_rows = {str(row["repository_id"]): str(row["source_revision"]) for row in repositories}
        missing_repositories = set(manifest.repository_ids) - set(repository_rows)
        if missing_repositories:
            return f"references missing repositories: {', '.join(sorted(missing_repositories))}"
        for repository_id, source_revision in manifest_revisions.items():
            if repository_rows[repository_id] != source_revision:
                return f"source revision mismatch for repository {repository_id}"
        file_rows = connection.execute(
            f"SELECT file_id, repository_id, source_revision FROM files WHERE repository_id IN ({placeholders})",
            manifest.repository_ids,
        ).fetchall()
        actual_file_ids = {str(row["file_id"]) for row in file_rows}
        if actual_file_ids != set(manifest.file_ids):
            return "file IDs do not match stored files"
        for row in file_rows:
            repository_id = str(row["repository_id"])
            expected_revision = manifest_revisions.get(repository_id)
            if expected_revision is not None and str(row["source_revision"]) != expected_revision:
                return f"source revision mismatch for file {row['file_id']}"
        repository_policy_rows = connection.execute("SELECT DISTINCT policy_revision FROM repositories").fetchall()
        if any(
            metadata_policy is not None and str(row["policy_revision"]) != metadata_policy
            for row in repository_policy_rows
        ):
            return "policy revision mismatch in repositories"
        symbol_source_mismatch = connection.execute(
            """
            SELECT s.symbol_id
            FROM symbols s JOIN files f ON f.file_id = s.file_id
            WHERE s.repository_id <> f.repository_id
               OR s.content_hash <> f.content_hash
               OR s.source_revision <> f.source_revision
               OR s.parser_spec_version <> f.parser_spec_version
            LIMIT 1
            """
        ).fetchone()
        if symbol_source_mismatch is not None:
            return f"symbol source identity mismatch for {symbol_source_mismatch['symbol_id']}"
        parser_tables = ("repositories", "files", "symbols", "edges", "pending_references", "file_fingerprints")
        for table in parser_tables:
            parser_rows = connection.execute(f"SELECT DISTINCT parser_spec_version FROM {table}").fetchall()
            if any(str(row["parser_spec_version"]) != manifest.parser_spec_version for row in parser_rows):
                return f"parser spec version mismatch in {table}"
        return None

    def current_manifest(self, repository_ids: tuple[str, ...]) -> CodeManifest:
        health = self.health()
        if not health.schema_compatible:
            return _empty_manifest(repository_ids)
        requested = _normalize_repository_ids(repository_ids)
        with self._connect_readonly() as connection:
            serialized = _metadata(connection, "manifest_json")
            if serialized is None:
                all_ids = tuple(
                    str(row["repository_id"])
                    for row in connection.execute("SELECT repository_id FROM repositories ORDER BY repository_id")
                )
                manifest = _empty_manifest(all_ids)
            else:
                try:
                    manifest = _manifest_from_json(serialized)
                except (TypeError, ValueError, json.JSONDecodeError):
                    return _empty_manifest(requested)
            if not requested:
                return manifest
            if not set(requested).issubset(manifest.repository_ids):
                return _empty_manifest(requested)
            file_ids = tuple(
                str(row["file_id"])
                for row in connection.execute(
                    (
                        "SELECT file_id FROM files WHERE repository_id IN ({}) ORDER BY repository_id, relative_path"
                    ).format(",".join("?" for _ in requested)),
                    requested,
                )
            )
            source_revisions = tuple(
                (str(row["repository_id"]), str(row["source_revision"]))
                for row in connection.execute(
                    (
                        "SELECT repository_id, source_revision FROM repositories "
                        "WHERE repository_id IN ({}) ORDER BY repository_id"
                    ).format(",".join("?" for _ in requested)),
                    requested,
                )
            )
            return CodeManifest(
                generation_id=manifest.generation_id,
                schema_version=manifest.schema_version,
                parser_spec_version=manifest.parser_spec_version,
                repository_ids=requested,
                policy_revision=manifest.policy_revision,
                source_revisions=source_revisions,
                file_ids=file_ids,
            )

    def apply_reconcile_plan(self, plan: CodeReconcilePlan) -> CodeApplyResult:
        if self._read_only:
            raise PermissionError("code projection store is read-only")
        if not isinstance(plan, CodeReconcilePlan):
            raise ValueError("plan must be a CodeReconcilePlan")
        self._validate_plan(plan)
        with self._connect() as connection:
            try:
                connection.execute("BEGIN IMMEDIATE")
                self._apply_plan_transaction(connection, plan)
                connection.commit()
            except Exception:
                connection.rollback()
                raise
        return CodeApplyResult(
            generation_id=plan.manifest.generation_id,
            repository_ids=plan.manifest.repository_ids,
            activated=False,
            file_count=self._count_rows("files", plan.manifest.repository_ids),
            symbol_count=self._count_rows("symbols", plan.manifest.repository_ids),
            edge_count=self._count_rows("edges", plan.manifest.repository_ids),
            pending_reference_count=self._count_rows("pending_references", plan.manifest.repository_ids),
        )

    def search_symbols(self, query: CodeSymbolQuery) -> tuple[CodeSymbolHit, ...]:
        health = self.health()
        if not health.schema_compatible:
            return ()
        terms = tuple(_QUERY_TOKEN.findall(query.query_text))
        if not terms:
            return ()
        match = " AND ".join(f'"{term.replace(chr(34), chr(34) * 2)}"' for term in terms)
        clauses = ["symbol_fts MATCH ?"]
        args: list[object] = [match]
        if query.repository_ids:
            clauses.append("s.repository_id IN ({})".format(",".join("?" for _ in query.repository_ids)))
            args.extend(query.repository_ids)
        if query.kinds:
            clauses.append("s.kind IN ({})".format(",".join("?" for _ in query.kinds)))
            args.extend(query.kinds)
        if query.path_prefix:
            clauses.append("f.relative_path LIKE ?")
            args.append(f"{query.path_prefix.rstrip('/')}%")
        args.append(query.limit)
        with self._connect_readonly() as connection:
            rows = connection.execute(
                f"""
                SELECT s.symbol_id, s.repository_id, s.file_id, f.relative_path,
                       s.kind, s.language_kind, s.name, s.qualified_name, s.signature,
                       s.start_line, s.end_line, s.content_hash, s.source_revision,
                       s.parser_spec_version, bm25(symbol_fts) AS score
                FROM symbol_fts
                JOIN symbols s ON s.rowid = symbol_fts.rowid
                JOIN files f ON f.file_id = s.file_id
                WHERE {" AND ".join(clauses)}
                ORDER BY score ASC, s.repository_id ASC, f.relative_path ASC,
                         s.start_line ASC, s.start_column ASC, s.symbol_id ASC
                LIMIT ?
                """,
                args,
            ).fetchall()
        return tuple(_symbol_hit_from_row(row) for row in rows)

    def get_symbol(self, symbol_id: str) -> CodeSymbolRecord | None:
        if not isinstance(symbol_id, str) or not symbol_id.strip():
            raise ValueError("symbol_id is required")
        if not self.health().schema_compatible:
            return None
        with self._connect_readonly() as connection:
            row = connection.execute("SELECT * FROM symbols WHERE symbol_id = ?", (symbol_id,)).fetchone()
        return _symbol_from_row(row) if row is not None else None

    def traverse(self, query: CodeTraversalQuery) -> CodeTraversalResult:
        if not self.health().schema_compatible:
            return CodeTraversalResult(root_symbol_id=query.symbol_id, direction=query.direction, hits=())
        with self._connect_readonly() as connection:
            root = connection.execute("SELECT * FROM symbols WHERE symbol_id = ?", (query.symbol_id,)).fetchone()
            if root is None:
                return CodeTraversalResult(root_symbol_id=query.symbol_id, direction=query.direction, hits=())
            visited = {query.symbol_id}
            frontier: deque[tuple[str, int]] = deque([(query.symbol_id, 0)])
            hits: list[CodeSymbolHit] = []
            edges: list[CodeEdgeRecord] = []
            warnings: list[str] = []
            while frontier and len(hits) < query.limit:
                current, depth = frontier.popleft()
                if depth >= query.depth:
                    continue
                if query.direction == "outbound":
                    rows = connection.execute(
                        "SELECT * FROM edges WHERE source_symbol_id = ? ORDER BY edge_id", (current,)
                    ).fetchall()
                    target_column = "target_symbol_id"
                else:
                    rows = connection.execute(
                        "SELECT * FROM edges WHERE target_symbol_id = ? ORDER BY edge_id", (current,)
                    ).fetchall()
                    target_column = "source_symbol_id"
                for row in rows:
                    edge = _edge_from_row(row)
                    if edge.extraction_status not in ("extracted", "inferred"):
                        if query.include_uncertain:
                            warnings.append(f"uncertain edge excluded from traversal: {edge.edge_id}")
                        continue
                    target_id = row[target_column]
                    if target_id is None or target_id in visited:
                        continue
                    target = connection.execute(
                        """
                        SELECT s.*, f.relative_path
                        FROM symbols s JOIN files f ON f.file_id = s.file_id
                        WHERE s.symbol_id = ?
                        """,
                        (target_id,),
                    ).fetchone()
                    if target is None:
                        continue
                    if query.repository_id and target["repository_id"] != query.repository_id:
                        continue
                    visited.add(str(target_id))
                    hits.append(_symbol_hit_from_row(target))
                    edges.append(edge)
                    frontier.append((str(target_id), depth + 1))
                    if len(hits) >= query.limit:
                        break
        return CodeTraversalResult(
            root_symbol_id=query.symbol_id,
            direction=query.direction,
            hits=tuple(hits),
            edges=tuple(edges),
            max_depth=query.depth,
            warnings=tuple(sorted(set(warnings))),
        )

    def _apply_plan_transaction(self, connection: sqlite3.Connection, plan: CodeReconcilePlan) -> None:
        repository_ids = plan.manifest.repository_ids
        for repository_id in repository_ids:
            source_revision = dict(plan.manifest.source_revisions).get(repository_id, "unknown")
            connection.execute(
                """
                INSERT INTO repositories (repository_id, source_revision, policy_revision, parser_spec_version)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(repository_id) DO UPDATE SET
                  source_revision=excluded.source_revision,
                  policy_revision=excluded.policy_revision,
                  parser_spec_version=excluded.parser_spec_version
                """,
                (repository_id, source_revision, plan.manifest.policy_revision, plan.manifest.parser_spec_version),
            )
        deleted_file_ids = set(plan.deleted_file_ids)
        for file_id in deleted_file_ids:
            self._delete_file(connection, file_id)
        touched_file_ids: set[str] = set()
        for file_snapshot in sorted(plan.files, key=lambda item: (item.repository_id, item.relative_path)):
            old = connection.execute(
                "SELECT file_id FROM files WHERE repository_id = ? AND relative_path = ?",
                (file_snapshot.repository_id, file_snapshot.relative_path),
            ).fetchone()
            if old is not None and str(old["file_id"]) != _file_id(file_snapshot):
                self._delete_file(connection, str(old["file_id"]))
            file_id = _file_id(file_snapshot)
            connection.execute(
                """
                INSERT INTO files (
                  file_id, repository_id, relative_path, language, content_hash, byte_count,
                  line_count, source_revision, is_test_file, parser_spec_version
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(file_id) DO UPDATE SET
                  repository_id=excluded.repository_id, relative_path=excluded.relative_path,
                  language=excluded.language, content_hash=excluded.content_hash,
                  byte_count=excluded.byte_count, line_count=excluded.line_count,
                  source_revision=excluded.source_revision, is_test_file=excluded.is_test_file,
                  parser_spec_version=excluded.parser_spec_version
                """,
                (
                    file_id,
                    file_snapshot.repository_id,
                    file_snapshot.relative_path,
                    file_snapshot.language,
                    file_snapshot.content_hash,
                    file_snapshot.byte_count,
                    file_snapshot.line_count,
                    file_snapshot.source_revision,
                    int(file_snapshot.is_test_file),
                    file_snapshot.parser_spec_version,
                ),
            )
            self._delete_file_symbols(connection, file_id)
            touched_file_ids.add(file_id)
            connection.execute(
                """
                INSERT INTO file_fingerprints (file_id, content_hash, source_revision, parser_spec_version)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(file_id) DO UPDATE SET
                  content_hash=excluded.content_hash, source_revision=excluded.source_revision,
                  parser_spec_version=excluded.parser_spec_version
                """,
                (file_id, file_snapshot.content_hash, file_snapshot.source_revision, file_snapshot.parser_spec_version),
            )
        for symbol in sorted(
            plan.symbols,
            key=lambda item: (item.repository_id, item.file_id, item.start_line, item.symbol_id),
        ):
            if symbol.file_id not in touched_file_ids and symbol.file_id not in {
                _file_id(file_snapshot) for file_snapshot in plan.files
            }:
                continue
            connection.execute(
                """
                INSERT INTO symbols (
                  symbol_id, repository_id, file_id, kind, language_kind, name, qualified_name,
                  signature, start_line, end_line, start_column, end_column, content_hash,
                  source_revision, parser_spec_version
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(symbol_id) DO UPDATE SET
                  repository_id=excluded.repository_id, file_id=excluded.file_id, kind=excluded.kind,
                  language_kind=excluded.language_kind, name=excluded.name,
                  qualified_name=excluded.qualified_name, signature=excluded.signature,
                  start_line=excluded.start_line, end_line=excluded.end_line,
                  start_column=excluded.start_column, end_column=excluded.end_column,
                  content_hash=excluded.content_hash, source_revision=excluded.source_revision,
                  parser_spec_version=excluded.parser_spec_version
                """,
                _symbol_values(symbol),
            )
        touched_symbols = {symbol.symbol_id for symbol in plan.symbols if symbol.file_id in touched_file_ids}
        if touched_symbols:
            placeholders = ",".join("?" for _ in touched_symbols)
            connection.execute(
                f"DELETE FROM edges WHERE source_symbol_id IN ({placeholders}) OR target_symbol_id IN ({placeholders})",
                (*touched_symbols, *touched_symbols),
            )
        for edge in sorted(plan.edges, key=lambda item: (item.repository_id, item.edge_id)):
            connection.execute(
                """
                INSERT INTO edges (
                  edge_id, repository_id, source_symbol_id, relation_kind, target_symbol_id,
                  unresolved_target_key, extraction_status, anchor_start_line,
                  anchor_start_column, parser_spec_version
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(edge_id) DO UPDATE SET
                  repository_id=excluded.repository_id, source_symbol_id=excluded.source_symbol_id,
                  relation_kind=excluded.relation_kind, target_symbol_id=excluded.target_symbol_id,
                  unresolved_target_key=excluded.unresolved_target_key,
                  extraction_status=excluded.extraction_status,
                  anchor_start_line=excluded.anchor_start_line,
                  anchor_start_column=excluded.anchor_start_column,
                  parser_spec_version=excluded.parser_spec_version
                """,
                _edge_values(edge),
            )
        for pending in sorted(plan.pending_references, key=lambda item: (item.repository_id, item.pending_id)):
            connection.execute(
                """
                INSERT INTO pending_references (
                  pending_id, repository_id, reference_id, source_revision,
                  relation_kind, target_key, reason, parser_spec_version
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(pending_id) DO UPDATE SET
                  repository_id=excluded.repository_id, reference_id=excluded.reference_id,
                  source_revision=excluded.source_revision, relation_kind=excluded.relation_kind,
                  target_key=excluded.target_key, reason=excluded.reason,
                  parser_spec_version=excluded.parser_spec_version
                """,
                (
                    pending.pending_id,
                    pending.repository_id,
                    pending.reference_id,
                    pending.source_revision,
                    pending.relation_kind,
                    pending.target_key,
                    pending.reason,
                    pending.parser_spec_version,
                ),
            )
        manifest = plan.manifest
        _set_metadata(connection, "schema_version", manifest.schema_version)
        _set_metadata(connection, "parser_spec_version", manifest.parser_spec_version)
        _set_metadata(connection, "policy_revision", manifest.policy_revision)
        _set_metadata(connection, "manifest_json", json.dumps(_manifest_payload(manifest), sort_keys=True))
        run_id = plan.run_id or f"run-{manifest.generation_id}"
        connection.execute(
            """
            INSERT OR REPLACE INTO projection_runs (
              run_id, generation_id, status, repository_ids_json, file_count,
              symbol_count, edge_count, pending_reference_count, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_id,
                manifest.generation_id,
                "fresh",
                json.dumps(list(repository_ids)),
                len(plan.files),
                len(plan.symbols),
                len(plan.edges),
                len(plan.pending_references),
                datetime.now(UTC).isoformat(),
            ),
        )
        self._rebuild_fts(connection)
        self._validate_integrity(connection)

    def _delete_file(self, connection: sqlite3.Connection, file_id: str) -> None:
        self._delete_file_symbols(connection, file_id)
        connection.execute("DELETE FROM file_fingerprints WHERE file_id = ?", (file_id,))
        connection.execute("DELETE FROM files WHERE file_id = ?", (file_id,))

    def _delete_file_symbols(self, connection: sqlite3.Connection, file_id: str) -> None:
        symbols = [
            str(row["symbol_id"])
            for row in connection.execute("SELECT symbol_id FROM symbols WHERE file_id = ?", (file_id,)).fetchall()
        ]
        if symbols:
            placeholders = ",".join("?" for _ in symbols)
            connection.execute(
                f"DELETE FROM edges WHERE source_symbol_id IN ({placeholders}) OR target_symbol_id IN ({placeholders})",
                (*symbols, *symbols),
            )
            connection.execute(f"DELETE FROM symbols WHERE symbol_id IN ({placeholders})", symbols)

    def _rebuild_fts(self, connection: sqlite3.Connection) -> None:
        connection.execute("DELETE FROM symbol_fts")
        connection.execute(
            """
            INSERT INTO symbol_fts (rowid, relative_path, name, qualified_name, signature, language, kind)
            SELECT s.rowid, f.relative_path, s.name, s.qualified_name, COALESCE(s.signature, ''),
                   f.language, s.kind
            FROM symbols s JOIN files f ON f.file_id = s.file_id
            ORDER BY s.repository_id, f.relative_path, s.start_line, s.start_column, s.symbol_id
            """,
        )

    def _validate_plan(self, plan: CodeReconcilePlan) -> None:
        if plan.manifest.schema_version != CODE_PROJECTION_SCHEMA_VERSION:
            raise ValueError("plan schema version is incompatible")
        if plan.manifest.parser_spec_version != self._expected_parser_spec_version:
            raise ValueError("plan parser spec version is incompatible")
        if (
            self._expected_policy_revision is not None
            and plan.manifest.policy_revision != self._expected_policy_revision
        ):
            raise ValueError("plan policy revision is incompatible")
        if len(set(plan.manifest.repository_ids)) != len(plan.manifest.repository_ids):
            raise ValueError("duplicate manifest repository IDs")
        if len(set(plan.manifest.file_ids)) != len(plan.manifest.file_ids):
            raise ValueError("duplicate manifest file IDs")
        symbols_by_id: dict[str, CodeSymbolRecord] = {}
        files_by_id: dict[str, CodeFileSnapshot] = {}
        edge_ids: set[str] = set()
        logical_edge_keys: set[tuple[str, str, str | None, str | None, int, int]] = set()
        pending_ids: set[str] = set()
        manifest_revisions: dict[str, str] = {}
        for repository_id, source_revision in plan.manifest.source_revisions:
            if repository_id in manifest_revisions:
                raise ValueError(f"duplicate manifest source revision: {repository_id}")
            if repository_id not in plan.manifest.repository_ids:
                raise ValueError("manifest source revision repository is outside repository scope")
            manifest_revisions[repository_id] = source_revision
        existing_symbol_repositories = self._existing_identity_repositories("symbols", "symbol_id")
        existing_edge_repositories = self._existing_identity_repositories("edges", "edge_id")
        existing_pending_repositories = self._existing_identity_repositories("pending_references", "pending_id")
        for file_snapshot in plan.files:
            file_id = _file_id(file_snapshot)
            if file_id in files_by_id:
                raise ValueError(f"duplicate file identity: {file_id}")
            if file_snapshot.parser_spec_version != plan.manifest.parser_spec_version:
                raise ValueError("file parser spec version is incompatible with manifest")
            expected_revision = manifest_revisions.get(file_snapshot.repository_id)
            if expected_revision is not None and file_snapshot.source_revision != expected_revision:
                raise ValueError("file source revision is incompatible with manifest")
            files_by_id[file_id] = file_snapshot
        for deleted_file_id in plan.deleted_file_ids:
            existing_repository = self._existing_file_repository(deleted_file_id)
            if existing_repository is None or existing_repository not in plan.manifest.repository_ids:
                raise ValueError("deleted file is outside manifest repository scope")
        desired_file_ids = self._desired_file_ids(plan, files_by_id)
        if desired_file_ids != set(plan.manifest.file_ids):
            raise ValueError("manifest file IDs do not match desired files")
        for symbol in plan.symbols:
            if symbol.symbol_id in symbols_by_id:
                raise ValueError(f"duplicate symbol identity: {symbol.symbol_id}")
            if symbol.file_id not in files_by_id:
                raise ValueError(f"symbol file_id is not present in plan: {symbol.file_id}")
            source_file = files_by_id[symbol.file_id]
            if source_file.repository_id != symbol.repository_id:
                raise ValueError("symbol and file must belong to the same repository")
            if symbol.parser_spec_version != plan.manifest.parser_spec_version:
                raise ValueError("symbol parser spec version is incompatible with manifest")
            if (
                symbol.content_hash != source_file.content_hash
                or symbol.source_revision != source_file.source_revision
                or symbol.file_id != _file_id(source_file)
            ):
                raise ValueError("symbol source identity does not match file")
            existing_repository = existing_symbol_repositories.get(symbol.symbol_id)
            if existing_repository is not None and existing_repository != symbol.repository_id:
                raise ValueError("symbol identity is owned by another repository")
            symbols_by_id[symbol.symbol_id] = symbol
        for edge in plan.edges:
            if edge.edge_id in edge_ids:
                raise ValueError(f"duplicate edge identity: {edge.edge_id}")
            edge_ids.add(edge.edge_id)
            logical_edge_key = (
                edge.source_symbol_id,
                edge.relation_kind,
                edge.target_symbol_id,
                edge.unresolved_target_key,
                edge.anchor_start_line,
                edge.anchor_start_column,
            )
            if logical_edge_key in logical_edge_keys:
                raise ValueError(f"duplicate logical edge: {edge.edge_id}")
            logical_edge_keys.add(logical_edge_key)
            if edge.parser_spec_version != plan.manifest.parser_spec_version:
                raise ValueError("edge parser spec version is incompatible with manifest")
            existing_repository = existing_edge_repositories.get(edge.edge_id)
            if existing_repository is not None and existing_repository != edge.repository_id:
                raise ValueError("edge identity is owned by another repository")
            source = symbols_by_id.get(edge.source_symbol_id)
            if source is None:
                source_repository = existing_symbol_repositories.get(edge.source_symbol_id)
                if source_repository is None:
                    raise ValueError(f"edge source_symbol_id is missing: {edge.source_symbol_id}")
                if source_repository != edge.repository_id:
                    raise ValueError("edge source must belong to the same repository")
            if source is not None and source.repository_id != edge.repository_id:
                raise ValueError("edge source must belong to the same repository")
            if edge.target_symbol_id is not None:
                target = symbols_by_id.get(edge.target_symbol_id)
                if target is None:
                    target_repository = existing_symbol_repositories.get(edge.target_symbol_id)
                    if target_repository is None:
                        raise ValueError(f"edge target_symbol_id is missing: {edge.target_symbol_id}")
                    if target_repository != edge.repository_id:
                        raise ValueError("edge target must belong to the same repository")
                elif target.repository_id != edge.repository_id:
                    raise ValueError("edge target must belong to the same repository")
        for pending in plan.pending_references:
            if pending.pending_id in pending_ids:
                raise ValueError(f"duplicate pending reference identity: {pending.pending_id}")
            pending_ids.add(pending.pending_id)
            if pending.parser_spec_version != plan.manifest.parser_spec_version:
                raise ValueError("pending reference parser spec version is incompatible with manifest")
            expected_revision = manifest_revisions.get(pending.repository_id)
            if expected_revision is not None and pending.source_revision != expected_revision:
                raise ValueError("pending reference source revision is incompatible with manifest")
            existing_repository = existing_pending_repositories.get(pending.pending_id)
            if existing_repository is not None and existing_repository != pending.repository_id:
                raise ValueError("pending reference identity is owned by another repository")

    def _existing_identity_repositories(self, table: str, identity_column: str) -> dict[str, str]:
        if not self._database_path.exists():
            return {}
        try:
            with self._connect_readonly() as connection:
                return {
                    str(row[identity_column]): str(row["repository_id"])
                    for row in connection.execute(f"SELECT {identity_column}, repository_id FROM {table}")
                }
        except sqlite3.Error:
            return {}

    def _existing_file_repository(self, file_id: str) -> str | None:
        if not self._database_path.exists():
            return None
        try:
            with self._connect_readonly() as connection:
                row = connection.execute("SELECT repository_id FROM files WHERE file_id = ?", (file_id,)).fetchone()
                return str(row["repository_id"]) if row is not None else None
        except sqlite3.Error:
            return None

    def _desired_file_ids(
        self,
        plan: CodeReconcilePlan,
        files_by_id: dict[str, CodeFileSnapshot],
    ) -> set[str]:
        if not self._database_path.exists():
            current_by_path: dict[tuple[str, str], str] = {}
        else:
            try:
                with self._connect_readonly() as connection:
                    placeholders = ",".join("?" for _ in plan.manifest.repository_ids)
                    rows = connection.execute(
                        (
                            "SELECT file_id, repository_id, relative_path FROM files "
                            f"WHERE repository_id IN ({placeholders})"
                        ),
                        plan.manifest.repository_ids,
                    ).fetchall()
                current_by_path = {
                    (str(row["repository_id"]), str(row["relative_path"])): str(row["file_id"]) for row in rows
                }
            except sqlite3.Error:
                current_by_path = {}
        for deleted_file_id in plan.deleted_file_ids:
            for path_key, current_file_id in tuple(current_by_path.items()):
                if current_file_id == deleted_file_id:
                    del current_by_path[path_key]
                    break
        for file_id, file_snapshot in files_by_id.items():
            current_by_path[(file_snapshot.repository_id, file_snapshot.relative_path)] = file_id
        return set(current_by_path.values())

    def _validate_integrity(self, connection: sqlite3.Connection) -> None:
        dangling = connection.execute(
            """
            SELECT e.edge_id FROM edges e
            LEFT JOIN symbols source ON source.symbol_id = e.source_symbol_id
            LEFT JOIN symbols target ON target.symbol_id = e.target_symbol_id
            WHERE source.symbol_id IS NULL
               OR (e.target_symbol_id IS NOT NULL AND target.symbol_id IS NULL)
               OR source.repository_id <> e.repository_id
               OR (target.symbol_id IS NOT NULL AND target.repository_id <> e.repository_id)
            LIMIT 1
            """
        ).fetchone()
        if dangling is not None:
            raise ValueError(f"dangling resolved endpoint: {dangling['edge_id']}")

    def _count_rows(self, table: str, repository_ids: tuple[str, ...]) -> int:
        if not self._database_path.exists() or not repository_ids:
            return 0
        with self._connect_readonly() as connection:
            placeholders = ",".join("?" for _ in repository_ids)
            return int(
                connection.execute(
                    f"SELECT COUNT(*) FROM {table} WHERE repository_id IN ({placeholders})", repository_ids
                ).fetchone()[0]
            )

    def _incompatible(self, message: str) -> StoreHealth:
        return StoreHealth(
            ok=False,
            backend=CODE_SQLITE_BACKEND,
            schema_version=CODE_PROJECTION_SCHEMA_VERSION,
            schema_compatible=False,
            message=f"schema incompatible: {message}",
        )

    def _connect(self) -> sqlite3.Connection:
        if self._read_only:
            return self._connect_readonly()
        connection = sqlite3.connect(self._database_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def _connect_readonly(self) -> sqlite3.Connection:
        if not self._database_path.exists():
            raise sqlite3.OperationalError("database does not exist")
        uri = f"file:{quote(str(self._database_path), safe='/')}?mode=ro"
        connection = sqlite3.connect(uri, uri=True)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA query_only = ON")
        connection.execute("PRAGMA foreign_keys = ON")
        return connection


def _set_metadata(connection: sqlite3.Connection, key: str, value: str) -> None:
    connection.execute(
        "INSERT INTO code_metadata (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (key, value),
    )


def _metadata(connection: sqlite3.Connection, key: str) -> str | None:
    row = connection.execute("SELECT value FROM code_metadata WHERE key = ?", (key,)).fetchone()
    return str(row["value"]) if row is not None else None


def _manifest_payload(manifest: CodeManifest) -> dict[str, Any]:
    return {
        "generation_id": manifest.generation_id,
        "schema_version": manifest.schema_version,
        "parser_spec_version": manifest.parser_spec_version,
        "repository_ids": list(manifest.repository_ids),
        "policy_revision": manifest.policy_revision,
        "source_revisions": [list(item) for item in manifest.source_revisions],
        "file_ids": list(manifest.file_ids),
    }


def _manifest_from_json(serialized: str) -> CodeManifest:
    payload = json.loads(serialized)
    return CodeManifest(
        generation_id=str(payload["generation_id"]),
        schema_version=str(payload["schema_version"]),
        parser_spec_version=str(payload["parser_spec_version"]),
        repository_ids=tuple(str(item) for item in payload["repository_ids"]),
        policy_revision=str(payload["policy_revision"]),
        source_revisions=tuple((str(item[0]), str(item[1])) for item in payload.get("source_revisions", ())),
        file_ids=tuple(str(item) for item in payload.get("file_ids", ())),
    )


def _empty_manifest(repository_ids: Iterable[str]) -> CodeManifest:
    return CodeManifest(
        generation_id="empty",
        schema_version=CODE_PROJECTION_SCHEMA_VERSION,
        parser_spec_version=CODE_PARSER_SPEC_VERSION,
        repository_ids=tuple(repository_ids),
        policy_revision="empty",
    )


def _normalize_repository_ids(repository_ids: object) -> tuple[str, ...]:
    if not isinstance(repository_ids, (tuple, list)):
        raise ValueError("repository_ids must be a tuple or list")
    values = tuple(str(item).strip() for item in repository_ids)
    if any(not value for value in values) or len(set(values)) != len(values):
        raise ValueError("repository_ids must be unique non-empty strings")
    return values


def _file_id(snapshot: CodeFileSnapshot) -> str:
    from vault_graph.code_index.code_models import code_file_identity

    return code_file_identity(snapshot.repository_id, snapshot.relative_path)


def _symbol_values(symbol: CodeSymbolRecord) -> tuple[object, ...]:
    return (
        symbol.symbol_id,
        symbol.repository_id,
        symbol.file_id,
        symbol.kind,
        symbol.language_kind,
        symbol.name,
        symbol.qualified_name,
        symbol.signature,
        symbol.start_line,
        symbol.end_line,
        symbol.start_column,
        symbol.end_column,
        symbol.content_hash,
        symbol.source_revision,
        symbol.parser_spec_version,
    )


def _edge_values(edge: CodeEdgeRecord) -> tuple[object, ...]:
    return (
        edge.edge_id,
        edge.repository_id,
        edge.source_symbol_id,
        edge.relation_kind,
        edge.target_symbol_id,
        edge.unresolved_target_key,
        edge.extraction_status,
        edge.anchor_start_line,
        edge.anchor_start_column,
        edge.parser_spec_version,
    )


def _symbol_from_row(row: sqlite3.Row) -> CodeSymbolRecord:
    return CodeSymbolRecord(
        symbol_id=str(row["symbol_id"]),
        repository_id=str(row["repository_id"]),
        file_id=str(row["file_id"]),
        kind=str(row["kind"]),
        language_kind=str(row["language_kind"]),
        name=str(row["name"]),
        qualified_name=str(row["qualified_name"]),
        signature=str(row["signature"]) if row["signature"] is not None else None,
        start_line=int(row["start_line"]),
        end_line=int(row["end_line"]),
        start_column=int(row["start_column"]),
        end_column=int(row["end_column"]),
        content_hash=str(row["content_hash"]),
        source_revision=str(row["source_revision"]),
        parser_spec_version=str(row["parser_spec_version"]),
    )


def _edge_from_row(row: sqlite3.Row) -> CodeEdgeRecord:
    return CodeEdgeRecord(
        edge_id=str(row["edge_id"]),
        repository_id=str(row["repository_id"]),
        source_symbol_id=str(row["source_symbol_id"]),
        relation_kind=str(row["relation_kind"]),
        target_symbol_id=str(row["target_symbol_id"]) if row["target_symbol_id"] is not None else None,
        unresolved_target_key=(str(row["unresolved_target_key"]) if row["unresolved_target_key"] is not None else None),
        extraction_status=cast(CodeExtractionStatus, str(row["extraction_status"])),
        anchor_start_line=int(row["anchor_start_line"]),
        anchor_start_column=int(row["anchor_start_column"]),
        parser_spec_version=str(row["parser_spec_version"]),
    )


def _symbol_hit_from_row(row: sqlite3.Row) -> CodeSymbolHit:
    return CodeSymbolHit(
        symbol_id=str(row["symbol_id"]),
        repository_id=str(row["repository_id"]),
        file_id=str(row["file_id"]),
        relative_path=str(row["relative_path"]),
        kind=str(row["kind"]),
        language_kind=str(row["language_kind"]),
        name=str(row["name"]),
        qualified_name=str(row["qualified_name"]),
        signature=str(row["signature"]) if row["signature"] is not None else None,
        start_line=int(row["start_line"]),
        end_line=int(row["end_line"]),
        score=float(row["score"]) if "score" in row.keys() and row["score"] is not None else 0.0,
        content_hash=str(row["content_hash"]) if row["content_hash"] is not None else None,
        source_revision=str(row["source_revision"]) if row["source_revision"] is not None else None,
        parser_spec_version=str(row["parser_spec_version"]),
    )
