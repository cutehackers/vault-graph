"""Embedding cache: embedding key -> vector, in Graph Home `cache/embeddings.sqlite3` (spec 4.3.5).

The cache lives outside projection generations (decision 20), so a rebuilt generation reuses
vectors and a run that died part way resumes from the vectors it already computed. Deleting
the file only means the next run embeds again.
"""

from __future__ import annotations

import math
import sqlite3
import sys
from array import array
from collections.abc import Callable, Collection, Iterator, Mapping
from contextlib import contextmanager
from pathlib import Path

from vault_graph.errors import VectorStoreError
from vault_graph.storage.interfaces.text_embeddings import (
    EmbeddingInput,
    EmbeddingModelSpec,
    EmbeddingVector,
    TextEmbeddings,
)

CACHE_DIR_NAME = "cache"
CACHE_FILE_NAME = "embeddings.sqlite3"
# Keys bound per lookup query, below SQLite's variable limit.
_LOOKUP_PAGE_SIZE = 500

_SCHEMA = """
CREATE TABLE IF NOT EXISTS embeddings (
    embedding_key TEXT PRIMARY KEY,
    dimensions INTEGER NOT NULL,
    vector BLOB NOT NULL,
    last_used_run TEXT NOT NULL
);
"""


def embedding_cache_path(graph_home_path: Path) -> Path:
    return graph_home_path / CACHE_DIR_NAME / CACHE_FILE_NAME


class SQLiteEmbeddingCache:
    """Float32 vectors by embedding key. Every method raises `VectorStoreError` when the file is unusable."""

    def __init__(self, path: Path) -> None:
        self._path = path

    @property
    def path(self) -> Path:
        return self._path

    def get(self, keys: Collection[str], *, dimensions: int, run_id: str) -> dict[str, tuple[float, ...]]:
        """Vectors stored for `keys`. A row with other dimensions is a miss. Hits get `run_id`."""
        if not keys or not self._path.exists():
            return {}
        found: dict[str, tuple[float, ...]] = {}
        ordered = tuple(dict.fromkeys(keys))
        with self._connect() as connection:
            for start in range(0, len(ordered), _LOOKUP_PAGE_SIZE):
                page = ordered[start : start + _LOOKUP_PAGE_SIZE]
                rows = connection.execute(
                    "SELECT embedding_key, dimensions, vector FROM embeddings "
                    f"WHERE embedding_key IN ({','.join('?' * len(page))})",
                    page,
                ).fetchall()
                for key, stored_dimensions, blob in rows:
                    values = _vector_from_blob(blob)
                    if stored_dimensions == dimensions and len(values) == dimensions:
                        found[str(key)] = values
            connection.executemany(
                "UPDATE embeddings SET last_used_run = ? WHERE embedding_key = ?",
                ((run_id, key) for key in found),
            )
        return found

    def put(self, vectors: Mapping[str, tuple[float, ...]], *, run_id: str) -> None:
        if not vectors:
            return
        with self._connect() as connection:
            connection.executemany(
                "INSERT OR REPLACE INTO embeddings (embedding_key, dimensions, vector, last_used_run) "
                "VALUES (?, ?, ?, ?)",
                ((key, len(values), array("f", values).tobytes(), run_id) for key, values in vectors.items()),
            )

    def retain(self, keys: Collection[str]) -> int:
        """Delete every row whose key is not in `keys`. Returns the number of deleted rows."""
        if not self._path.exists():
            return 0
        with self._connect() as connection:
            connection.execute("CREATE TEMP TABLE kept (embedding_key TEXT PRIMARY KEY)")
            connection.executemany("INSERT OR IGNORE INTO kept VALUES (?)", ((key,) for key in keys))
            cursor = connection.execute(
                "DELETE FROM embeddings WHERE embedding_key NOT IN (SELECT embedding_key FROM kept)"
            )
            connection.execute("DROP TABLE kept")
            return cursor.rowcount

    def count(self) -> int:
        if not self._path.exists():
            return 0
        with self._connect() as connection:
            row = connection.execute("SELECT COUNT(*) FROM embeddings").fetchone()
        return int(row[0])

    def remove_files(self) -> None:
        """Delete the cache file and its SQLite side files, so the next run builds a new cache."""
        for path in (self._path, Path(f"{self._path}-wal"), Path(f"{self._path}-shm"), Path(f"{self._path}-journal")):
            path.unlink(missing_ok=True)

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            connection = sqlite3.connect(self._path)
        except (OSError, sqlite3.Error) as exc:
            raise VectorStoreError(f"embedding cache unavailable: {exc}") from exc
        try:
            with connection:
                connection.executescript(_SCHEMA)
                yield connection
        except sqlite3.Error as exc:
            raise VectorStoreError(f"embedding cache failed: {exc}") from exc
        finally:
            connection.close()


def _vector_from_blob(blob: bytes) -> tuple[float, ...]:
    values = array("f")
    if len(blob) % values.itemsize:
        return ()
    values.frombytes(blob)
    return tuple(values)


def _stderr_line(message: str) -> None:
    print(" ".join(message.split()), file=sys.stderr)


class CachedTextEmbeddings:
    """Document embeddings that read the cache first and send only misses to the model.

    New vectors go to the cache in the same call, so each embedding batch is saved as soon as it
    is computed. Every returned vector holds float32 values, so a cached and a fresh vector are
    equal. When the cache cannot be read or written, embedding goes on without it after one
    warning line, and `cache_failed` turns true. Query embeddings never touch the cache.
    """

    def __init__(
        self,
        inner: TextEmbeddings,
        cache: SQLiteEmbeddingCache,
        *,
        key_for: Callable[[EmbeddingModelSpec, str], str],
        run_id: str,
        warn: Callable[[str], None] = _stderr_line,
    ) -> None:
        self._inner = inner
        self._cache = cache
        self._key_for = key_for
        self._run_id = run_id
        self._warn = warn
        self._cache_failed = False

    @property
    def cache(self) -> SQLiteEmbeddingCache:
        return self._cache

    @property
    def cache_failed(self) -> bool:
        return self._cache_failed

    def model_spec(self) -> EmbeddingModelSpec:
        return self._inner.model_spec()

    def can_embed_without_download(self) -> bool:
        return self._inner.can_embed_without_download()

    def embed_query(self, text: str) -> EmbeddingVector:
        return self._inner.embed_query(text)

    def embed(self, inputs: tuple[EmbeddingInput, ...]) -> tuple[EmbeddingVector, ...]:
        if not inputs:
            return ()
        spec = self._inner.model_spec()
        keys = {item.input_id: self._key_for(spec, item.text) for item in inputs}
        cached = self._lookup(set(keys.values()), dimensions=spec.dimensions)
        misses = tuple(item for item in inputs if keys[item.input_id] not in cached)
        fresh = {vector.input_id: vector for vector in self._inner.embed(misses)} if misses else {}
        computed = {keys[input_id]: _float32(vector.values) for input_id, vector in fresh.items() if input_id in keys}
        # Only vectors the caller would accept are kept, so a bad vector is never served again.
        self._store(
            {
                key: values
                for key, values in computed.items()
                if len(values) == spec.dimensions and all(math.isfinite(value) for value in values)
            }
        )
        results: list[EmbeddingVector] = []
        for item in inputs:
            key = keys[item.input_id]
            if key in cached:
                results.append(EmbeddingVector(item.input_id, cached[key], spec))
            elif item.input_id in fresh:
                vector = fresh[item.input_id]
                results.append(EmbeddingVector(item.input_id, computed[key], vector.model_spec))
        # Unknown or missing IDs from the model are left for the caller's ID check to reject.
        results.extend(vector for input_id, vector in fresh.items() if input_id not in keys)
        return tuple(results)

    def _lookup(self, keys: set[str], *, dimensions: int) -> dict[str, tuple[float, ...]]:
        if self._cache_failed:
            return {}
        try:
            return self._cache.get(keys, dimensions=dimensions, run_id=self._run_id)
        except VectorStoreError as exc:
            self._fail(exc)
            return {}

    def _store(self, vectors: Mapping[str, tuple[float, ...]]) -> None:
        if self._cache_failed or not vectors:
            return
        try:
            self._cache.put(vectors, run_id=self._run_id)
        except VectorStoreError as exc:
            self._fail(exc)

    def _fail(self, exc: VectorStoreError) -> None:
        self._cache_failed = True
        self._warn(f"vault-graph: warning: {exc}; this run embeds without it")


def _float32(values: tuple[float, ...]) -> tuple[float, ...]:
    return tuple(array("f", values))
