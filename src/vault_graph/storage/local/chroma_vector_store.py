from __future__ import annotations

import hashlib
import sqlite3
from collections import defaultdict
from pathlib import Path
from typing import Any

from vault_graph.embeddings.text_embeddings import EmbeddingModelSpec
from vault_graph.errors import VectorStoreError
from vault_graph.ingestion.vault_catalog import QueryScope
from vault_graph.storage.interfaces.store_health import StoreHealth
from vault_graph.storage.interfaces.vector_store import (
    VectorEmbeddingRecord,
    VectorHit,
    VectorManifestRecord,
    VectorQuery,
    VectorStore,
    VectorTombstone,
)

CHROMA_VECTOR_SCHEMA_VERSION = "chroma-vector-v1"
CHROMA_BACKEND = "chroma"
COLLECTION_PREFIX = "vault_graph"


class ChromaVectorStore(VectorStore):
    def __init__(self, path: Path, *, initialize: bool = False, read_only: bool = False) -> None:
        self._path = path.expanduser().resolve()
        self._initialize = initialize
        self._read_only = read_only
        self._client: Any | None = None
        if initialize:
            self._path.mkdir(parents=True, exist_ok=True)

    def apply_vector_revision(
        self,
        *,
        vector_index_revision: str,
        records: tuple[VectorEmbeddingRecord, ...],
        tombstones: tuple[VectorTombstone, ...],
    ) -> None:
        if self._read_only:
            raise VectorStoreError("read-only ChromaVectorStore cannot apply vector revisions")
        if not vector_index_revision:
            raise VectorStoreError("vector_index_revision is required")
        for record in records:
            if record.vector_index_revision != vector_index_revision:
                raise VectorStoreError("record vector_index_revision must match revision being applied")
        client = self._require_client()
        for tombstone in tombstones:
            collection = self._get_collection_if_exists(client, tombstone.embedding_spec)
            if collection is None:
                continue
            loaded = collection.get(ids=[tombstone.vector_id], include=["metadatas"])
            metadatas = loaded.get("metadatas") or []
            if metadatas and _metadata_matches_tombstone(metadatas[0], tombstone):
                collection.delete(ids=[tombstone.vector_id])
        for embedding_spec, grouped_records in _group_records_by_spec(records).items():
            collection = self._get_or_create_collection(client, embedding_spec)
            collection.upsert(
                ids=[record.vector_id for record in grouped_records],
                embeddings=[list(record.embedding.values) for record in grouped_records],
                metadatas=[_metadata_for_record(record) for record in grouped_records],
            )

    def search(self, query: VectorQuery) -> tuple[VectorHit, ...]:
        if self._read_only and not self._database_path.exists():
            return ()
        if not self._path.exists() and not self._initialize:
            return ()
        try:
            client = self._require_client()
        except Exception as exc:
            raise VectorStoreError(f"vector search unavailable: {exc}") from exc
        try:
            collection = self._get_collection_if_exists(client, query.embedding_spec)
            if collection is None:
                return ()
            scoped_ids = self._scoped_ids(collection=collection, scope=query.scope)
            if not scoped_ids:
                return ()
            result = collection.query(
                query_embeddings=[list(query.query_vector.values)],
                ids=scoped_ids,
                n_results=min(query.limit, len(scoped_ids)),
                include=["metadatas", "distances"],
            )
            ids = (result.get("ids") or [[]])[0]
            metadatas = (result.get("metadatas") or [[]])[0]
            distances = (result.get("distances") or [[]])[0]
        except Exception as exc:
            raise VectorStoreError(f"vector search unavailable: {exc}") from exc
        hits: list[VectorHit] = []
        for rank, (vector_id, metadata, distance) in enumerate(zip(ids, metadatas, distances, strict=True), start=1):
            hits.append(
                VectorHit(
                    vector_id=str(vector_id),
                    vault_id=str(metadata["vault_id"]),
                    document_id=str(metadata["document_id"]),
                    chunk_id=str(metadata["chunk_id"]),
                    content_scope=str(metadata["content_scope"]),
                    score=1.0 - float(distance),
                    rank=rank,
                    embedding_spec=query.embedding_spec,
                    metadata_index_revision=str(metadata["metadata_index_revision"]),
                    vector_index_revision=str(metadata["vector_index_revision"]),
                    backend=CHROMA_BACKEND,
                )
            )
        return tuple(hits)

    def health(self) -> StoreHealth:
        if self._read_only:
            return self._sqlite_health()
        if not self._database_path.exists() and not self._initialize:
            return StoreHealth(
                ok=False,
                backend=CHROMA_BACKEND,
                schema_version=CHROMA_VECTOR_SCHEMA_VERSION,
                schema_compatible=False,
                message="not initialized",
            )
        try:
            self._require_client()
        except Exception as exc:
            return StoreHealth(
                ok=False,
                backend=CHROMA_BACKEND,
                schema_version=CHROMA_VECTOR_SCHEMA_VERSION,
                schema_compatible=False,
                message=str(exc),
            )
        return StoreHealth(
            ok=True,
            backend=CHROMA_BACKEND,
            schema_version=CHROMA_VECTOR_SCHEMA_VERSION,
            schema_compatible=True,
            message="ok",
        )

    def export_manifest(self, scope: QueryScope) -> tuple[VectorManifestRecord, ...]:
        if self._read_only:
            return self._export_manifest_sqlite(scope)
        if not self._database_path.exists() and not self._initialize:
            return ()
        client = self._client_or_none()
        if client is None:
            return ()
        rows: list[VectorManifestRecord] = []
        for collection in self._vault_graph_collections(client):
            loaded = collection.get(include=["metadatas"])
            for vector_id, metadata in zip(loaded.get("ids") or [], loaded.get("metadatas") or [], strict=True):
                if _metadata_in_scope(metadata, scope):
                    rows.append(_manifest_record_from_metadata(vector_id=str(vector_id), metadata=metadata))
        return tuple(sorted(rows, key=lambda row: (row.vault_id, row.chunk_id, row.vector_id)))

    def _require_client(self) -> Any:
        if self._client is None:
            import chromadb

            self._client = chromadb.PersistentClient(path=str(self._path))
        return self._client

    @property
    def _database_path(self) -> Path:
        return self._path / "chroma.sqlite3"

    def _sqlite_health(self) -> StoreHealth:
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

    def _export_manifest_sqlite(self, scope: QueryScope) -> tuple[VectorManifestRecord, ...]:
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

    def _client_or_none(self) -> Any | None:
        try:
            return self._require_client()
        except Exception:
            return None

    def _get_or_create_collection(self, client: Any, spec: EmbeddingModelSpec) -> Any:
        return client.get_or_create_collection(
            name=_collection_name(spec),
            metadata={
                "vault_graph_backend": CHROMA_BACKEND,
                "vault_graph_schema_version": CHROMA_VECTOR_SCHEMA_VERSION,
                "embedding_model_name": spec.model_name,
                "embedding_model_version": spec.model_version,
                "embedding_dimensions": spec.dimensions,
                "embedding_spec_version": spec.spec_version,
            },
            configuration={"hnsw": {"space": "cosine"}},
            embedding_function=None,
        )

    def _get_collection_if_exists(self, client: Any, spec: EmbeddingModelSpec) -> Any | None:
        collection_name = _collection_name(spec)
        for collection in client.list_collections():
            if collection.name == collection_name:
                return collection
        return None

    def _vault_graph_collections(self, client: Any) -> tuple[Any, ...]:
        return tuple(
            collection for collection in client.list_collections() if collection.name.startswith(COLLECTION_PREFIX)
        )

    def _scoped_ids(self, *, collection: Any, scope: QueryScope) -> list[str]:
        loaded = collection.get(include=["metadatas"])
        return [
            str(vector_id)
            for vector_id, metadata in zip(loaded.get("ids") or [], loaded.get("metadatas") or [], strict=True)
            if _metadata_in_scope(metadata, scope)
        ]


def _group_records_by_spec(
    records: tuple[VectorEmbeddingRecord, ...],
) -> dict[EmbeddingModelSpec, tuple[VectorEmbeddingRecord, ...]]:
    grouped: dict[EmbeddingModelSpec, list[VectorEmbeddingRecord]] = defaultdict(list)
    for record in records:
        grouped[record.embedding.model_spec].append(record)
    return {spec: tuple(grouped_records) for spec, grouped_records in grouped.items()}


def _collection_name(spec: EmbeddingModelSpec) -> str:
    digest = hashlib.sha256(_embedding_spec_key(spec).encode("utf-8")).hexdigest()[:32]
    return f"{COLLECTION_PREFIX}_{digest}"


def _embedding_spec_key(spec: EmbeddingModelSpec) -> str:
    return "|".join((spec.model_name, spec.model_version, str(spec.dimensions), spec.spec_version))


def _metadata_for_record(record: VectorEmbeddingRecord) -> dict[str, str | int]:
    return {
        "vector_id": record.vector_id,
        "vault_id": record.vault_id,
        "document_id": record.document_id,
        "chunk_id": record.chunk_id,
        "content_scope": record.content_scope,
        "embedding_model_name": record.embedding.model_spec.model_name,
        "embedding_model_version": record.embedding.model_spec.model_version,
        "embedding_dimensions": record.embedding.model_spec.dimensions,
        "embedding_spec_version": record.embedding.model_spec.spec_version,
        "source_chunk_hash": record.source_chunk_hash,
        "chunker_version": record.chunker_version,
        "metadata_index_revision": record.metadata_index_revision,
        "vector_index_revision": record.vector_index_revision,
        "backend_schema_version": CHROMA_VECTOR_SCHEMA_VERSION,
    }


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
    )


def _embedding_spec_from_metadata(metadata: dict[str, Any]) -> EmbeddingModelSpec:
    return EmbeddingModelSpec(
        model_name=str(metadata["embedding_model_name"]),
        model_version=str(metadata["embedding_model_version"]),
        dimensions=int(metadata["embedding_dimensions"]),
        spec_version=str(metadata["embedding_spec_version"]),
    )


def _metadata_matches_tombstone(metadata: dict[str, Any], tombstone: VectorTombstone) -> bool:
    return (
        str(metadata.get("vector_id")) == tombstone.vector_id
        and str(metadata.get("vault_id")) == tombstone.vault_id
        and str(metadata.get("chunk_id")) == tombstone.chunk_id
        and _embedding_spec_from_metadata(metadata) == tombstone.embedding_spec
    )


def _metadata_in_scope(metadata: dict[str, Any], scope: QueryScope) -> bool:
    return str(metadata["vault_id"]) in scope.vault_ids and _content_scope_in_scope(
        record_scope=str(metadata["content_scope"]),
        query_scopes=scope.content_scopes,
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
