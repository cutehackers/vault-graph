"""Read Chroma SQLite state without importing Chroma or writing store files."""

from __future__ import annotations

import math
import sqlite3
import struct
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from vector_search.contracts import CollectionSpec, ManifestRecord, Metadata, StoreHealth, VectorMatch
from vector_search.errors import VectorSearchError

Predicate = Callable[[Metadata], bool]
TieKey = Callable[[Metadata, str], tuple[Any, ...]]


class ChromaSQLiteReader:
    def __init__(
        self,
        database_path: Path,
        *,
        collection_prefix: str,
        payload_table: str,
        expected_collection_metadata: Metadata,
        schema_version: str,
        payload_key_by_collection: bool,
        dimension_metadata_key: str,
        default_distance_metric: str | None,
    ) -> None:
        self._database_path = database_path
        self._prefix = collection_prefix
        self._payload_table = payload_table
        self._expected = expected_collection_metadata
        self._schema_version = schema_version
        self._payload_key_by_collection = payload_key_by_collection
        self._dimension_metadata_key = dimension_metadata_key
        self._default_distance_metric = default_distance_metric

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(f"file:{self._database_path}?mode=ro", uri=True)
        connection.row_factory = sqlite3.Row
        return connection

    def health(self) -> StoreHealth:
        if not self._database_path.exists():
            return StoreHealth(False, "chroma", self._schema_version, False, "not initialized")
        try:
            with self._connect() as connection:
                missing = _missing_tables(connection, {"collections", "collection_metadata"})
                if missing:
                    return StoreHealth(
                        False,
                        "chroma",
                        self._schema_version,
                        False,
                        f"schema incompatible: missing {', '.join(sorted(missing))}",
                    )
                collections = self._collections(connection)
                for name, metadata in collections.values():
                    if not _matches(metadata, self._expected):
                        return StoreHealth(False, "chroma", self._schema_version, False, f"schema incompatible: {name}")
        except sqlite3.Error as exc:
            return StoreHealth(False, "chroma", self._schema_version, False, str(exc))
        return StoreHealth(True, "chroma", self._schema_version, True, "ok")

    def _collections(self, connection: sqlite3.Connection) -> dict[str, tuple[str, dict[str, Any]]]:
        collections: dict[str, tuple[str, dict[str, Any]]] = {
            str(row["id"]): (str(row["name"]), {})
            for row in connection.execute("SELECT id, name FROM collections").fetchall()
            if str(row["name"]).startswith(f"{self._prefix}_")
        }
        if not collections:
            return collections
        placeholders = ", ".join("?" for _ in collections)
        for row in connection.execute(
            f"SELECT collection_id, key, str_value, int_value, float_value, bool_value "
            f"FROM collection_metadata WHERE collection_id IN ({placeholders})",
            tuple(collections),
        ):
            collections[str(row["collection_id"])][1][str(row["key"])] = _metadata_value(row)
        return collections

    def validate_collection(self, spec: CollectionSpec) -> bool:
        if not self._database_path.exists():
            return False
        with self._connect() as connection:
            collections = self._collections(connection)
        for name, metadata in collections.values():
            if name == spec.name:
                _validate_collection_metadata(
                    spec,
                    metadata,
                    self._expected,
                    self._dimension_metadata_key,
                    self._default_distance_metric,
                )
                return True
        return False

    def export_manifest(self, predicate: Predicate | None = None) -> tuple[ManifestRecord, ...]:
        if not self._database_path.exists():
            return ()
        try:
            with self._connect() as connection:
                missing = _missing_tables(connection, {"collections", "segments", "embeddings", "embedding_metadata"})
                if missing:
                    return ()
                rows = connection.execute(
                    """SELECT c.name AS collection_name, e.embedding_id, em.key,
                       em.string_value, em.int_value, em.float_value, em.bool_value
                       FROM embeddings e
                       JOIN segments s ON s.id = e.segment_id
                       JOIN collections c ON c.id = s.collection
                       JOIN embedding_metadata em ON em.id = e.id
                       WHERE c.name LIKE ?
                       ORDER BY c.name, e.embedding_id, em.key""",
                    (f"{self._prefix}_%",),
                ).fetchall()
        except sqlite3.Error:
            return ()
        grouped: dict[tuple[str, str], dict[str, Any]] = {}
        for row in rows:
            key = (str(row["collection_name"]), str(row["embedding_id"]))
            grouped.setdefault(key, {})[str(row["key"])] = _metadata_value(row)
        return tuple(
            ManifestRecord(name, record_id, metadata)
            for (name, record_id), metadata in sorted(grouped.items())
            if predicate is None or predicate(metadata)
        )

    def search(
        self,
        spec: CollectionSpec,
        values: tuple[float, ...],
        limit: int,
        predicate: Predicate | None,
        tie_key: TieKey | None,
        vector_id_batch_size: int,
    ) -> tuple[VectorMatch, ...]:
        health = self.health()
        if not health.ok:
            raise VectorSearchError(f"vector search unavailable: {health.message}")
        try:
            if not self.validate_collection(spec):
                return ()
        except sqlite3.Error as exc:
            raise VectorSearchError(f"vector search unavailable: {exc}") from exc
        manifest = tuple(row for row in self.export_manifest(predicate) if row.collection_name == spec.name)
        if not manifest:
            return ()
        ids = tuple(row.record_id for row in manifest)
        vectors = self._vectors(spec.name, ids, vector_id_batch_size)
        scored = []
        for row in manifest:
            vector = vectors.get(row.record_id)
            if vector is None:
                raise VectorSearchError(f"vector search unavailable: missing vector payload for {row.record_id}")
            scored.append((_cosine(values, vector), row))
        scored.sort(
            key=lambda item: (
                -item[0],
                *(tie_key(item[1].metadata, item[1].record_id) if tie_key else (item[1].record_id,)),
            )
        )
        return tuple(
            VectorMatch(row.record_id, score, rank, row.metadata) for rank, (score, row) in enumerate(scored[:limit], 1)
        )

    def _vectors(self, collection_name: str, ids: tuple[str, ...], batch_size: int) -> dict[str, tuple[float, ...]]:
        vectors: dict[str, tuple[float, ...]] = {}
        try:
            with self._connect() as connection:
                tables = {
                    str(row["name"])
                    for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
                }
                if self._payload_table in tables:
                    for batch in _batches(ids, batch_size):
                        payload_ids = tuple(self._payload_id(collection_name, record_id) for record_id in batch)
                        placeholders = ", ".join("?" for _ in batch)
                        rows = connection.execute(
                            f'SELECT vector_id, vector FROM "{self._payload_table}" '
                            f"WHERE vector_id IN ({placeholders})",
                            payload_ids,
                        )
                        vectors.update(
                            {
                                self._record_id(collection_name, str(row["vector_id"])): _decode(
                                    row["vector"], "FLOAT32"
                                )
                                for row in rows
                            }
                        )
                    if len(vectors) == len(ids):
                        return vectors
                for batch in _batches(ids, batch_size):
                    placeholders = ", ".join("?" for _ in batch)
                    rows = connection.execute(
                        f"""SELECT q.id, q.vector, q.encoding FROM embeddings e
                            JOIN segments s ON s.id = e.segment_id
                            JOIN collections c ON c.id = s.collection
                            JOIN embeddings_queue q ON q.seq_id = e.seq_id
                              AND q.id = e.embedding_id
                              AND substr(q.topic, -length(c.id) - 1) = '/' || c.id
                            WHERE e.embedding_id IN ({placeholders}) AND c.name = ?""",
                        (*batch, collection_name),
                    )
                    vectors.update({str(row["id"]): _decode(row["vector"], str(row["encoding"])) for row in rows})
        except sqlite3.Error as exc:
            raise VectorSearchError(f"vector search unavailable: {exc}") from exc
        return vectors

    def _payload_id(self, collection_name: str, record_id: str) -> str:
        return f"{len(collection_name)}:{collection_name}{record_id}" if self._payload_key_by_collection else record_id

    def _record_id(self, collection_name: str, payload_id: str) -> str:
        if not self._payload_key_by_collection:
            return payload_id
        return payload_id[len(f"{len(collection_name)}:{collection_name}") :]


def _matches(actual: Mapping[str, Any], expected: Metadata) -> bool:
    return all(actual.get(key) == value for key, value in expected.items())


def _validate_collection_metadata(
    spec: CollectionSpec,
    actual: Mapping[str, Any],
    expected: Metadata,
    dimension_metadata_key: str,
    default_distance_metric: str | None,
) -> None:
    if not _matches(actual, expected) or not _matches(actual, spec.metadata):
        raise VectorSearchError(f"collection metadata incompatible: {spec.name}")
    dimensions = actual.get("_vector_dimensions", actual.get(dimension_metadata_key))
    if dimensions != spec.dimensions:
        raise VectorSearchError(f"collection dimensions incompatible: {spec.name}")
    metric = actual.get("_vector_distance_metric", default_distance_metric)
    if metric != spec.distance_metric:
        raise VectorSearchError(f"collection distance metric incompatible: {spec.name}")


def _missing_tables(connection: sqlite3.Connection, required: set[str]) -> set[str]:
    actual = {str(row["name"]) for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    return required - actual


def _metadata_value(row: sqlite3.Row) -> object:
    for key in ("str_value", "string_value", "int_value", "float_value", "bool_value"):
        if key in row.keys() and row[key] is not None:
            return row[key]
    return None


def _batches(values: tuple[str, ...], size: int) -> tuple[tuple[str, ...], ...]:
    if size <= 0:
        raise VectorSearchError("vector_id_batch_size must be positive")
    return tuple(values[index : index + size] for index in range(0, len(values), size))


def _decode(value: object, encoding: str) -> tuple[float, ...]:
    if encoding != "FLOAT32":
        raise VectorSearchError(f"vector search unavailable: unsupported vector encoding {encoding}")
    if not isinstance(value, bytes):
        raise VectorSearchError("vector search unavailable: vector payload must be bytes")
    if len(value) % 4:
        raise VectorSearchError("vector search unavailable: invalid FLOAT32 vector payload")
    return tuple(float(item) for item in struct.unpack(f"<{len(value) // 4}f", value))


def _cosine(left: tuple[float, ...], right: tuple[float, ...]) -> float:
    if len(left) != len(right):
        raise VectorSearchError(f"embedding dimension mismatch: expected {len(left)}, got {len(right)}")
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    if left_norm == 0 or right_norm == 0:
        return 0.0
    return sum(a * b for a, b in zip(left, right, strict=True)) / (left_norm * right_norm)
