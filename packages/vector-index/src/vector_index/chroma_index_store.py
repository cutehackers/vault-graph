"""Index metadata codec over the vector_search store contract."""

from __future__ import annotations

import hashlib
import json

from vector_search import CollectionSpec, StoredVector, VectorDeletion, VectorStore

from vector_index.indexing import IndexedItem, IndexedVector, VectorIndexError


class ChromaIndexStore:
    """Map logical item collections and model spaces into physical vector collections.

    Use a dedicated vector_search store whose collection_prefix matches this codec's
    prefix. Metadata belongs to this codec, not to the vector search implementation.
    """

    def __init__(self, store: VectorStore, *, collection_prefix: str = "vectors") -> None:
        self._store = store
        self._prefix = collection_prefix

    def manifest(self, collection_ids: tuple[str, ...]) -> tuple[IndexedItem, ...]:
        rows = self._store.export_manifest(lambda metadata: metadata.get("collection_id") in collection_ids)
        result: list[IndexedItem] = []
        for row in rows:
            try:
                item = IndexedItem(
                    str(row.metadata["collection_id"]),
                    str(row.metadata["item_id"]),
                    str(row.metadata["record_id"]),
                    str(row.metadata["space_id"]),
                    str(row.metadata["fingerprint"]),
                )
                spec = self._spec(item.space_id, int(row.metadata["dimensions"]))
            except (KeyError, ValueError, TypeError) as exc:
                raise VectorIndexError("invalid index manifest metadata") from exc
            if spec.name != row.collection_name or row.record_id != json.dumps([item.collection_id, item.record_id]):
                raise VectorIndexError("manifest storage identity differs from recorded space or record")
            result.append(item)
        return tuple(result)

    def _spec(self, space_id: str, dimensions: int) -> CollectionSpec:
        digest = hashlib.sha256(space_id.encode()).hexdigest()
        return CollectionSpec(f"{self._prefix}_{digest}", dimensions, metadata={"space_id": space_id})

    def apply(self, records: tuple[IndexedVector, ...], deletions: tuple[IndexedItem, ...]) -> None:
        stored = tuple(
            (
                self._spec(row.item.space_id, len(row.values)),
                StoredVector(
                    json.dumps([row.item.collection_id, row.item.record_id]),
                    row.values,
                    {
                        "record_id": row.item.record_id,
                        "collection_id": row.item.collection_id,
                        "item_id": row.item.item_id,
                        "space_id": row.item.space_id,
                        "fingerprint": row.item.fingerprint,
                        "dimensions": len(row.values),
                    },
                ),
            )
            for row in records
        )
        # Retrieve dimensions from each old space, including spaces other than the
        # current provider's. A missing record is already deleted and is harmless.
        existing = {
            (
                str(row.metadata.get("collection_id")),
                str(row.metadata.get("record_id")),
                str(row.metadata.get("space_id")),
            ): row
            for row in self._store.export_manifest()
        }
        removed: list[VectorDeletion] = []
        for item in deletions:
            row = existing.get((item.collection_id, item.record_id, item.space_id))
            if row is None:
                continue
            if row.collection_name != self._spec(item.space_id, int(row.metadata["dimensions"])).name:
                raise VectorIndexError("manifest physical collection differs from recorded space")
            removed.append(
                VectorDeletion(
                    self._spec(item.space_id, int(row.metadata["dimensions"])),
                    row.record_id,
                    {
                        "collection_id": item.collection_id,
                        "item_id": item.item_id,
                        "space_id": item.space_id,
                        "fingerprint": item.fingerprint,
                    },
                )
            )
        self._store.apply(stored, tuple(removed))

    def collection_spec(self, space_id: str, dimensions: int) -> CollectionSpec:
        """Identify the physical collection for subsequent vector_search queries."""
        return self._spec(space_id, dimensions)
