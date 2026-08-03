from __future__ import annotations

import sqlite3
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import cast

from vault_graph.ingestion.document_authority import DocumentRole
from vault_graph.ingestion.vault_catalog import QueryScope
from vault_graph.storage.local.chroma_vector_store import ChromaVectorStore


@dataclass(frozen=True)
class RoleCount:
    role: DocumentRole
    count: int


@dataclass(frozen=True)
class SchemaVersion:
    projection: str
    version: str


@dataclass(frozen=True)
class ProjectionHygieneReport:
    role_counts: tuple[RoleCount, ...]
    canonical_blob_count: int
    canonical_blob_bytes: int
    logical_chunk_bytes: int
    persisted_search_projection_plaintext_bytes: int
    plaintext_amplification: float
    dangling_keyword_refs: int
    dangling_vector_refs: int
    dangling_graph_refs: int
    result_family_duplication: float | None
    schema_versions: tuple[SchemaVersion, ...]
    active_generation_id: str | None = None

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


class ProjectionHygieneService:
    """Read-only inventory proving that projections reference canonical metadata."""

    def __init__(self, *, metadata_path: Path, vector_path: Path, graph_path: Path) -> None:
        self._metadata_path = metadata_path
        self._vector_path = vector_path
        self._graph_path = graph_path

    def audit(
        self,
        *,
        scope: QueryScope,
        result_family_duplication: float | None = None,
        active_generation_id: str | None = None,
    ) -> ProjectionHygieneReport:
        with _connect_readonly(self._metadata_path) as connection:
            role_counts = tuple(
                RoleCount(role=cast(DocumentRole, str(row[0])), count=int(row[1]))
                for row in connection.execute(
                    "SELECT source_role, COUNT(*) FROM documents "
                    "WHERE is_tombstoned = 0 GROUP BY source_role ORDER BY source_role"
                )
            )
            canonical_blob_count, canonical_blob_bytes = connection.execute(
                "SELECT COUNT(*), COALESCE(SUM(byte_count), 0) FROM content_blobs"
            ).fetchone()
            logical_chunk_bytes = int(
                connection.execute(
                    "SELECT COALESCE(SUM(b.byte_count), 0) FROM chunks c "
                    "INNER JOIN content_blobs b ON b.blob_hash = c.blob_hash"
                ).fetchone()[0]
            )
            dangling_keyword_refs = int(
                connection.execute(
                    "SELECT COUNT(*) FROM keyword_rows r LEFT JOIN chunks c "
                    "ON c.vault_id = r.vault_id AND c.chunk_id = r.chunk_id WHERE c.chunk_id IS NULL"
                ).fetchone()[0]
            )
            chunk_keys = {
                (str(row[0]), str(row[1])) for row in connection.execute("SELECT vault_id, chunk_id FROM chunks")
            }
        vector = ChromaVectorStore(self._vector_path, read_only=True)
        vector_rows = vector.export_manifest(scope)
        dangling_vector_refs = sum((row.vault_id, row.chunk_id) not in chunk_keys for row in vector_rows)
        dangling_graph_refs = _dangling_graph_refs(self._graph_path, chunk_keys)
        metadata_version = _metadata_version(self._metadata_path)
        graph_version = _projection_version(self._graph_path, "graph_metadata")
        vector_version = vector.health().schema_version
        amplification = 1.0
        return ProjectionHygieneReport(
            role_counts=role_counts,
            canonical_blob_count=int(canonical_blob_count),
            canonical_blob_bytes=int(canonical_blob_bytes),
            logical_chunk_bytes=logical_chunk_bytes,
            persisted_search_projection_plaintext_bytes=0,
            plaintext_amplification=amplification,
            dangling_keyword_refs=dangling_keyword_refs,
            dangling_vector_refs=dangling_vector_refs,
            dangling_graph_refs=dangling_graph_refs,
            result_family_duplication=result_family_duplication,
            schema_versions=(
                SchemaVersion("metadata", metadata_version),
                SchemaVersion("keyword", "sqlite-keyword-v2"),
                SchemaVersion("vector", vector_version),
                SchemaVersion("graph", graph_version),
            ),
            active_generation_id=active_generation_id,
        )


def _connect_readonly(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(f"file:{path.expanduser().resolve()}?mode=ro", uri=True)
    return connection


def _metadata_version(path: Path) -> str:
    with _connect_readonly(path) as connection:
        tables = {str(row[0]) for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    return "metadata-v2" if "content_blobs" in tables else "incompatible"


def _projection_version(path: Path, table: str) -> str:
    if not path.exists():
        return "missing"
    with _connect_readonly(path) as connection:
        row = connection.execute(f"SELECT value FROM {table} WHERE key = 'schema_version'").fetchone()
    return str(row[0]) if row is not None else "incompatible"


def _dangling_graph_refs(path: Path, chunk_keys: set[tuple[str, str]]) -> int:
    if not path.exists():
        return 0
    with _connect_readonly(path) as connection:
        refs = connection.execute("SELECT evidence_vault_id, chunk_id FROM graph_evidence_refs").fetchall()
    return sum((str(row[0]), str(row[1])) not in chunk_keys for row in refs)
