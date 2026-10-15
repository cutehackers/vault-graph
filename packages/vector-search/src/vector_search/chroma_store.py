"""Chroma writer and SQLite read-only vector search."""

from __future__ import annotations

import math
import re
import sqlite3
import struct
from pathlib import Path
from typing import Any

from vector_search.contracts import (
    CollectionSpec,
    ManifestRecord,
    Metadata,
    Scalar,
    StoredVector,
    StoreHealth,
    VectorDeletion,
    VectorMatch,
)
from vector_search.errors import VectorSearchError
from vector_search.sqlite_reader import ChromaSQLiteReader, Predicate, TieKey, _validate_collection_metadata


class ChromaVectorStore:
    def __init__(
        self,
        path: Path,
        *,
        initialize: bool = False,
        read_only: bool = False,
        collection_prefix: str = "vectors",
        payload_table: str = "vector_search_payloads",
        expected_collection_metadata: Metadata | None = None,
        schema_version: str = "chroma-vector-v1",
        payload_key_by_collection: bool = True,
        dimension_metadata_key: str = "_vector_dimensions",
        default_distance_metric: str | None = None,
    ) -> None:
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", payload_table):
            raise VectorSearchError("payload_table must be a SQL identifier")
        self._path = path.expanduser().resolve()
        self._initialize = initialize
        self._read_only = read_only
        self._prefix = collection_prefix
        self._table = payload_table
        self._expected = dict(expected_collection_metadata or {})
        self._schema_version = schema_version
        self._payload_key_by_collection = payload_key_by_collection
        self._dimension_metadata_key = dimension_metadata_key
        self._default_distance_metric = default_distance_metric
        self._client: Any | None = None
        if initialize and not read_only:
            self._path.mkdir(parents=True, exist_ok=True)

    @property
    def _database_path(self) -> Path:
        return self._path / "chroma.sqlite3"

    def _reader(self) -> ChromaSQLiteReader:
        return ChromaSQLiteReader(
            self._database_path,
            collection_prefix=self._prefix,
            payload_table=self._table,
            expected_collection_metadata=self._expected,
            schema_version=self._schema_version,
            payload_key_by_collection=self._payload_key_by_collection,
            dimension_metadata_key=self._dimension_metadata_key,
            default_distance_metric=self._default_distance_metric,
        )

    def _require_client(self) -> Any:
        if self._client is None:
            try:
                import chromadb
            except ImportError as exc:
                raise VectorSearchError("Chroma writes require nolemy-vector-search[chroma]") from exc
            self._client = chromadb.PersistentClient(path=str(self._path))
        return self._client

    def close(self) -> None:
        client = self._client
        self._client = None
        close = getattr(client, "close", None) if client is not None else None
        if callable(close):
            close()

    def _validate_name(self, name: str) -> None:
        if not name.startswith(f"{self._prefix}_"):
            raise VectorSearchError(f"collection name must start with {self._prefix}_")

    def _collection_metadata(self, spec: CollectionSpec) -> dict[str, str | int | float | bool]:
        metadata = dict(spec.metadata)
        required: dict[str, Scalar] = dict(self._expected)
        markers: dict[str, Scalar] = {
            "_vector_dimensions": spec.dimensions,
            "_vector_distance_metric": spec.distance_metric,
        }
        for key, value in markers.items():
            if key in required and required[key] != value:
                raise VectorSearchError(f"collection metadata incompatible: {spec.name}: {key}")
            required[key] = value
        for key, value in required.items():
            if key in metadata and metadata[key] != value:
                raise VectorSearchError(f"collection metadata incompatible: {spec.name}: {key}")
            metadata[key] = value
        return metadata

    def _collection(self, spec: CollectionSpec) -> Any | None:
        for collection in self._require_client().list_collections():
            if collection.name == spec.name:
                _validate_collection_metadata(
                    spec,
                    collection.metadata or {},
                    self._expected,
                    self._dimension_metadata_key,
                    self._default_distance_metric,
                )
                return collection
        return None

    def apply(
        self,
        records: tuple[tuple[CollectionSpec, StoredVector], ...] = (),
        deletions: tuple[VectorDeletion, ...] = (),
    ) -> None:
        if self._read_only:
            raise VectorSearchError("read-only ChromaVectorStore cannot apply vector revisions")
        grouped: dict[str, tuple[CollectionSpec, list[StoredVector]]] = {}
        specs: dict[str, CollectionSpec] = {}
        for spec, record in records:
            self._validate_name(spec.name)
            self._collection_metadata(spec)
            if len(record.values) != spec.dimensions:
                raise VectorSearchError(
                    f"embedding dimension mismatch: expected {spec.dimensions}, got {len(record.values)}"
                )
            if not all(math.isfinite(value) for value in record.values):
                raise VectorSearchError("stored vector values must be finite")
            if spec.name in specs and specs[spec.name] != spec:
                raise VectorSearchError(f"conflicting collection spec: {spec.name}")
            specs[spec.name] = spec
            grouped.setdefault(spec.name, (spec, []))[1].append(record)
        for deletion in deletions:
            self._validate_name(deletion.collection.name)
            self._collection_metadata(deletion.collection)
            if deletion.collection.name in specs and specs[deletion.collection.name] != deletion.collection:
                raise VectorSearchError(f"conflicting collection spec: {deletion.collection.name}")
            specs[deletion.collection.name] = deletion.collection
        if self._database_path.exists():
            reader = self._reader()
            try:
                for spec in specs.values():
                    reader.validate_collection(spec)
            except sqlite3.Error as exc:
                raise VectorSearchError(f"vector store unavailable: {exc}") from exc
        client = self._require_client()
        collections = {name: self._collection(spec) for name, spec in specs.items()}
        matched_deletions: list[VectorDeletion] = []
        for deletion in deletions:
            collection = collections[deletion.collection.name]
            if collection is None:
                continue
            loaded = collection.get(ids=[deletion.record_id], include=["metadatas"])
            metadatas = loaded.get("metadatas") or []
            if metadatas and all(metadatas[0].get(key) == value for key, value in deletion.matches.items()):
                collection.delete(ids=[deletion.record_id])
                matched_deletions.append(deletion)
        for spec, rows in grouped.values():
            collection = collections[spec.name]
            if collection is None:
                collection = client.get_or_create_collection(
                    name=spec.name,
                    metadata=self._collection_metadata(spec),
                    configuration={"hnsw": {"space": spec.distance_metric}},
                    embedding_function=None,
                )
            collection.upsert(
                ids=[row.record_id for row in rows],
                embeddings=[list(row.values) for row in rows],
                metadatas=[dict(row.metadata) for row in rows],
            )
        self._persist_payloads(records, tuple(matched_deletions))

    def _persist_payloads(
        self, records: tuple[tuple[CollectionSpec, StoredVector], ...], deletions: tuple[VectorDeletion, ...]
    ) -> None:
        with sqlite3.connect(self._database_path) as connection:
            connection.execute(
                f'CREATE TABLE IF NOT EXISTS "{self._table}" (vector_id TEXT PRIMARY KEY, vector BLOB NOT NULL)'
            )
            connection.executemany(
                f'DELETE FROM "{self._table}" WHERE vector_id = ?',
                ((self._payload_id(row.collection.name, row.record_id),) for row in deletions),
            )
            connection.executemany(
                f'INSERT INTO "{self._table}"(vector_id, vector) VALUES (?, ?) '
                "ON CONFLICT(vector_id) DO UPDATE SET vector = excluded.vector",
                (
                    (self._payload_id(spec.name, row.record_id), struct.pack(f"<{len(row.values)}f", *row.values))
                    for spec, row in records
                ),
            )

    def _payload_id(self, collection_name: str, record_id: str) -> str:
        return f"{len(collection_name)}:{collection_name}{record_id}" if self._payload_key_by_collection else record_id

    def search(
        self,
        spec: CollectionSpec,
        values: tuple[float, ...],
        limit: int,
        *,
        predicate: Predicate | None = None,
        tie_key: TieKey | None = None,
        vector_id_batch_size: int = 500,
    ) -> tuple[VectorMatch, ...]:
        self._validate_name(spec.name)
        self._collection_metadata(spec)
        if len(values) != spec.dimensions:
            raise VectorSearchError(f"embedding dimension mismatch: expected {spec.dimensions}, got {len(values)}")
        if not all(math.isfinite(value) for value in values):
            raise VectorSearchError("query vector values must be finite")
        if limit <= 0:
            raise VectorSearchError("limit must be positive")
        if self._read_only:
            if not self._database_path.exists():
                return ()
            return self._reader().search(spec, values, limit, predicate, tie_key, vector_id_batch_size)
        if not self._path.exists() and not self._initialize:
            return ()
        try:
            collection = self._collection(spec)
            if collection is None:
                return ()
            loaded = collection.get(include=["metadatas"])
            ids = [
                str(record_id)
                for record_id, metadata in zip(loaded.get("ids") or [], loaded.get("metadatas") or [], strict=True)
                if predicate is None or predicate(metadata)
            ]
            if not ids:
                return ()
            result = collection.query(
                query_embeddings=[list(values)],
                ids=ids,
                n_results=min(limit, len(ids)),
                include=["metadatas", "distances"],
            )
            result_ids = (result.get("ids") or [[]])[0]
            metadatas = (result.get("metadatas") or [[]])[0]
            distances = (result.get("distances") or [[]])[0]
            return tuple(
                VectorMatch(str(record_id), 1.0 - float(distance), rank, metadata)
                for rank, (record_id, metadata, distance) in enumerate(
                    zip(result_ids, metadatas, distances, strict=True), 1
                )
            )
        except VectorSearchError:
            raise
        except Exception as exc:
            raise VectorSearchError(f"vector search unavailable: {exc}") from exc

    def export_manifest(self, predicate: Predicate | None = None) -> tuple[ManifestRecord, ...]:
        if self._read_only:
            return self._reader().export_manifest(predicate)
        if not self._database_path.exists() and not self._initialize:
            return ()
        try:
            client = self._require_client()
        except Exception:
            return ()
        rows: list[ManifestRecord] = []
        for collection in client.list_collections():
            if not collection.name.startswith(f"{self._prefix}_"):
                continue
            loaded = collection.get(include=["metadatas"])
            rows.extend(
                ManifestRecord(collection.name, str(record_id), metadata)
                for record_id, metadata in zip(loaded.get("ids") or [], loaded.get("metadatas") or [], strict=True)
                if predicate is None or predicate(metadata)
            )
        return tuple(sorted(rows, key=lambda row: (row.collection_name, row.record_id)))

    def health(self) -> StoreHealth:
        if self._read_only:
            return self._reader().health()
        if not self._database_path.exists() and not self._initialize:
            return StoreHealth(False, "chroma", self._schema_version, False, "not initialized")
        try:
            self._require_client()
        except Exception as exc:
            return StoreHealth(False, "chroma", self._schema_version, False, str(exc))
        return StoreHealth(True, "chroma", self._schema_version, True, "ok")
