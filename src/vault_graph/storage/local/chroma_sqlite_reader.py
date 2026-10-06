from __future__ import annotations

import math
import sqlite3
import struct
from pathlib import Path
from typing import Any, cast

from vault_graph.embeddings.text_embeddings import EmbeddingModelSpec
from vault_graph.errors import VectorStoreError
from vault_graph.ingestion.document_authority import DocumentRole
from vault_graph.ingestion.vault_catalog import QueryScope
from vault_graph.storage.interfaces.store_health import StoreHealth
from vault_graph.storage.interfaces.vector_store import VectorHit, VectorManifestRecord, VectorQuery

CHROMA_VECTOR_SCHEMA_VERSION = "chroma-vector-v2"
CHROMA_BACKEND = "chroma"
COLLECTION_PREFIX = "vault_graph"


class ChromaSQLiteReader:
    """Read Chroma's SQLite state without opening a Chroma client or writing files."""

    def __init__(self, database_path: Path) -> None:
        self._database_path = database_path

    def health(self) -> StoreHealth:
        if not self._database_path.exists():
            return StoreHealth(
                ok=False,
                backend=CHROMA_BACKEND,
                schema_version=CHROMA_VECTOR_SCHEMA_VERSION,
                schema_compatible=False,
                message="not initialized",
            )
        try:
            with self._connect_readonly() as connection:
                missing = _missing_tables(connection, {"collections", "collection_metadata"})
                if missing:
                    return StoreHealth(
                        ok=False,
                        backend=CHROMA_BACKEND,
                        schema_version=CHROMA_VECTOR_SCHEMA_VERSION,
                        schema_compatible=False,
                        message=f"schema incompatible: missing {', '.join(sorted(missing))}",
                    )
                metadata_by_collection = _collection_metadata_by_id(connection)
        except sqlite3.Error as exc:
            return StoreHealth(
                ok=False,
                backend=CHROMA_BACKEND,
                schema_version=CHROMA_VECTOR_SCHEMA_VERSION,
                schema_compatible=False,
                message=str(exc),
            )
        for collection_name, metadata in metadata_by_collection.values():
            backend = metadata.get("vault_graph_backend")
            schema_version = metadata.get("vault_graph_schema_version")
            if backend != CHROMA_BACKEND or schema_version != CHROMA_VECTOR_SCHEMA_VERSION:
                return StoreHealth(
                    ok=False,
                    backend=CHROMA_BACKEND,
                    schema_version=CHROMA_VECTOR_SCHEMA_VERSION,
                    schema_compatible=False,
                    message=f"schema incompatible: {collection_name}",
                )
        return StoreHealth(
            ok=True,
            backend=CHROMA_BACKEND,
            schema_version=CHROMA_VECTOR_SCHEMA_VERSION,
            schema_compatible=True,
            message="ok",
        )

    def export_manifest(self, scope: QueryScope) -> tuple[VectorManifestRecord, ...]:
        if not self._database_path.exists():
            return ()
        try:
            with self._connect_readonly() as connection:
                missing = _missing_tables(connection, {"collections", "segments", "embeddings", "embedding_metadata"})
                if missing:
                    return ()
                rows = connection.execute(
                    """
                    SELECT e.embedding_id, em.key, em.string_value, em.int_value, em.float_value, em.bool_value
                    FROM embeddings e
                    INNER JOIN segments s ON s.id = e.segment_id
                    INNER JOIN collections c ON c.id = s.collection
                    INNER JOIN embedding_metadata em ON em.id = e.id
                    WHERE c.name LIKE ?
                    ORDER BY e.embedding_id, em.key
                    """,
                    (f"{COLLECTION_PREFIX}_%",),
                ).fetchall()
        except sqlite3.Error:
            return ()
        metadata_by_vector_id: dict[str, dict[str, Any]] = {}
        for row in rows:
            vector_id = str(row["embedding_id"])
            metadata_by_vector_id.setdefault(vector_id, {})[str(row["key"])] = _metadata_value(row)
        manifest = (
            _manifest_record_from_metadata(vector_id=vector_id, metadata=metadata)
            for vector_id, metadata in metadata_by_vector_id.items()
        )
        return tuple(
            sorted(
                (row for row in manifest if _manifest_record_in_scope(row, scope)),
                key=lambda row: (row.vault_id, row.chunk_id, row.vector_id),
            )
        )

    def _connect_readonly(self) -> sqlite3.Connection:
        connection = sqlite3.connect(f"file:{self._database_path}?mode=ro", uri=True)
        connection.row_factory = sqlite3.Row
        return connection

    def search(self, query: VectorQuery, vector_id_batch_size: int) -> tuple[VectorHit, ...]:
        health = self.health()
        if not health.ok or not health.schema_compatible:
            raise VectorStoreError(f"vector search unavailable: {health.message}")
        manifest = tuple(
            row
            for row in self.export_manifest(query.scope)
            if row.embedding_spec == query.embedding_spec
            and (not query.source_roles or row.source_role in query.source_roles)
        )
        if not manifest:
            return ()
        vector_ids = tuple(row.vector_id for row in manifest)
        vectors = self._active_vectors_by_id(vector_ids, vector_id_batch_size)
        scored: list[tuple[float, VectorManifestRecord]] = []
        for row in manifest:
            values = vectors.get(row.vector_id)
            if values is None:
                raise VectorStoreError(f"vector search unavailable: missing vector payload for {row.vector_id}")
            scored.append((_cosine_similarity(query.query_vector.values, values), row))
        ranked = sorted(scored, key=lambda item: (-item[0], item[1].vault_id, item[1].chunk_id, item[1].vector_id))
        return tuple(
            VectorHit(
                vector_id=row.vector_id,
                vault_id=row.vault_id,
                document_id=row.document_id,
                chunk_id=row.chunk_id,
                content_scope=row.content_scope,
                score=score,
                rank=rank,
                embedding_spec=row.embedding_spec,
                metadata_index_revision=row.metadata_index_revision,
                vector_index_revision=row.vector_index_revision,
                backend=CHROMA_BACKEND,
                source_role=row.source_role,
                provenance_family_id=row.provenance_family_id,
            )
            for rank, (score, row) in enumerate(ranked[: query.limit], start=1)
        )

    def _active_vectors_by_id(
        self, vector_ids: tuple[str, ...], vector_id_batch_size: int
    ) -> dict[str, tuple[float, ...]]:
        if not vector_ids:
            return {}
        vectors: dict[str, tuple[float, ...]] = {}
        try:
            with self._connect_readonly() as connection:
                if "vault_graph_vector_payloads" in {
                    str(row["name"])
                    for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
                }:
                    for batch in _batched(vector_ids, vector_id_batch_size):
                        placeholders = ", ".join("?" for _ in batch)
                        rows = connection.execute(
                            f"SELECT vector_id, vector FROM vault_graph_vector_payloads "
                            f"WHERE vector_id IN ({placeholders})",
                            batch,
                        ).fetchall()
                        vectors.update(
                            {str(row["vector_id"]): _decode_vector_blob(row["vector"], "FLOAT32") for row in rows}
                        )
                    if len(vectors) == len(vector_ids):
                        return vectors
                for batch in _batched(vector_ids, vector_id_batch_size):
                    placeholders = ", ".join("?" for _ in batch)
                    rows = connection.execute(
                        f"""
                        SELECT q.id, q.vector, q.encoding
                        FROM embeddings e
                        INNER JOIN embeddings_queue q ON q.id = e.embedding_id
                        INNER JOIN (
                          SELECT id, MAX(seq_id) AS seq_id
                          FROM embeddings_queue
                          WHERE id IN ({placeholders})
                          GROUP BY id
                        ) latest ON latest.id = q.id AND latest.seq_id = q.seq_id
                        WHERE e.embedding_id IN ({placeholders})
                        """,
                        (*batch, *batch),
                    ).fetchall()
                    vectors.update(
                        {str(row["id"]): _decode_vector_blob(row["vector"], str(row["encoding"])) for row in rows}
                    )
        except sqlite3.Error as exc:
            raise VectorStoreError(f"vector search unavailable: {exc}") from exc
        return vectors


def _manifest_record_from_metadata(*, vector_id: str, metadata: dict[str, Any]) -> VectorManifestRecord:
    return VectorManifestRecord(
        vector_id=vector_id,
        vault_id=str(metadata["vault_id"]),
        document_id=str(metadata["document_id"]),
        chunk_id=str(metadata["chunk_id"]),
        content_scope=str(metadata["content_scope"]),
        embedding_spec=_embedding_spec_from_metadata(metadata),
        source_chunk_hash=str(metadata["source_chunk_hash"]),
        chunker_version=str(metadata["chunker_version"]),
        metadata_index_revision=str(metadata["metadata_index_revision"]),
        vector_index_revision=str(metadata["vector_index_revision"]),
        backend=CHROMA_BACKEND,
        backend_schema_version=str(metadata["backend_schema_version"]),
        source_role=cast(DocumentRole, str(metadata["source_role"])),
        provenance_family_id=str(metadata["provenance_family_id"]),
    )


def _embedding_spec_from_metadata(metadata: dict[str, Any]) -> EmbeddingModelSpec:
    return EmbeddingModelSpec(
        model_name=str(metadata["embedding_model_name"]),
        model_version=str(metadata["embedding_model_version"]),
        dimensions=int(metadata["embedding_dimensions"]),
        spec_version=str(metadata["embedding_spec_version"]),
    )


def _manifest_record_in_scope(row: VectorManifestRecord, scope: QueryScope) -> bool:
    return row.vault_id in scope.vault_ids and _content_scope_in_scope(
        record_scope=row.content_scope,
        query_scopes=scope.content_scopes,
    )


def _content_scope_in_scope(*, record_scope: str, query_scopes: tuple[str, ...]) -> bool:
    return any(
        record_scope == query_scope or record_scope.startswith(f"{query_scope}/") for query_scope in query_scopes
    )


def _missing_tables(connection: sqlite3.Connection, required_tables: set[str]) -> set[str]:
    tables = {
        str(row["name"]) for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
    }
    return required_tables - tables


def _collection_metadata_by_id(connection: sqlite3.Connection) -> dict[str, tuple[str, dict[str, object]]]:
    collections = {
        str(row["id"]): str(row["name"])
        for row in connection.execute(
            "SELECT id, name FROM collections WHERE name LIKE ?",
            (f"{COLLECTION_PREFIX}_%",),
        ).fetchall()
    }
    metadata_by_collection: dict[str, tuple[str, dict[str, object]]] = {
        collection_id: (name, {}) for collection_id, name in collections.items()
    }
    if not collections:
        return {}
    placeholders = ", ".join("?" for _ in collections)
    for row in connection.execute(
        f"SELECT collection_id, key, str_value, int_value, float_value, bool_value FROM collection_metadata "
        f"WHERE collection_id IN ({placeholders})",
        tuple(collections),
    ).fetchall():
        _, metadata = metadata_by_collection[str(row["collection_id"])]
        metadata[str(row["key"])] = _metadata_value(row)
    return metadata_by_collection


def _metadata_value(row: sqlite3.Row) -> object:
    for key in ("str_value", "string_value", "int_value", "float_value", "bool_value"):
        if key in row.keys() and row[key] is not None:
            return row[key]
    return None


def _batched(values: tuple[str, ...], size: int) -> tuple[tuple[str, ...], ...]:
    return tuple(values[index : index + size] for index in range(0, len(values), size))


def _decode_vector_blob(value: object, encoding: str) -> tuple[float, ...]:
    if encoding != "FLOAT32":
        raise VectorStoreError(f"vector search unavailable: unsupported vector encoding {encoding}")
    if not isinstance(value, bytes):
        raise VectorStoreError("vector search unavailable: vector payload must be bytes")
    if len(value) % 4:
        raise VectorStoreError("vector search unavailable: invalid FLOAT32 vector payload")
    return tuple(float(item) for item in struct.unpack(f"<{len(value) // 4}f", value))


def _cosine_similarity(left: tuple[float, ...], right: tuple[float, ...]) -> float:
    if len(left) != len(right):
        raise VectorStoreError(f"embedding dimension mismatch: expected {len(left)}, got {len(right)}")
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    if left_norm == 0 or right_norm == 0:
        return 0.0
    return sum(left_value * right_value for left_value, right_value in zip(left, right, strict=True)) / (
        left_norm * right_norm
    )
