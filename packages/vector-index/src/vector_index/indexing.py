from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal, Protocol

if TYPE_CHECKING:
    from text_embeddings import EmbeddingModelSpec, EmbeddingVector, TextEmbeddings


class VectorIndexError(Exception):
    """Invalid indexing inputs or an incompatible embedding response."""


@dataclass(frozen=True)
class IndexItem:
    collection_id: str
    item_id: str
    record_id: str
    text: str
    fingerprint: str

    def __post_init__(self) -> None:
        if not all((self.collection_id, self.item_id, self.record_id, self.fingerprint)):
            raise VectorIndexError("collection_id, item_id, record_id and fingerprint are required")


@dataclass(frozen=True)
class IndexedItem:
    collection_id: str
    item_id: str
    record_id: str
    space_id: str
    fingerprint: str

    def __post_init__(self) -> None:
        if not all((self.collection_id, self.item_id, self.record_id, self.space_id, self.fingerprint)):
            raise VectorIndexError("indexed item identifiers, space_id and fingerprint are required")


@dataclass(frozen=True)
class IndexedVector:
    item: IndexedItem
    values: tuple[float, ...]


@dataclass(frozen=True)
class IndexPlan:
    collection_ids: tuple[str, ...]
    space_id: str
    input_kind: Literal["snapshot", "changes"]
    items: tuple[IndexItem, ...]
    upserts: tuple[IndexItem, ...]
    deletions: tuple[IndexedItem, ...]
    unchanged_count: int
    full: bool = False


def plan_index(
    items: tuple[IndexItem, ...],
    current: tuple[IndexedItem, ...],
    *,
    collection_ids: tuple[str, ...],
    input_kind: Literal["snapshot", "changes"],
    space_id: str,
    full: bool = False,
) -> IndexPlan:
    """Plan without side effects. Only a complete snapshot authorizes absent-item deletion."""
    if input_kind not in ("snapshot", "changes") or not space_id:
        raise VectorIndexError("input_kind must be snapshot or changes and space_id is required")
    if (
        not collection_ids
        or any(not value for value in collection_ids)
        or len(set(collection_ids)) != len(collection_ids)
    ):
        raise VectorIndexError("collection_ids must be nonempty and unique")
    allowed = set(collection_ids)
    if any(item.collection_id not in allowed for item in items) or any(
        row.collection_id not in allowed for row in current
    ):
        raise VectorIndexError("item outside declared collection_ids")
    desired_keys = [(item.collection_id, item.item_id) for item in items]
    if len(set(desired_keys)) != len(items):
        raise VectorIndexError("duplicate item_id within a collection")
    desired_records = [(item.collection_id, item.record_id) for item in items]
    if len(set(desired_records)) != len(items):
        raise VectorIndexError("duplicate record_id within a collection")
    current_keys = [(item.collection_id, item.record_id, item.space_id) for item in current]
    if len(set(current_keys)) != len(current):
        raise VectorIndexError("duplicate current record_id within a collection")
    by_record = dict(zip(current_keys, current, strict=True))
    by_item: dict[tuple[str, str], list[IndexedItem]] = {}
    for row in current:
        by_item.setdefault((row.collection_id, row.item_id), []).append(row)
    upserts: list[IndexItem] = []
    deletions: dict[tuple[str, str, str], IndexedItem] = {}
    unchanged = 0
    for item in items:
        key = (item.collection_id, item.item_id)
        existing = by_record.get((item.collection_id, item.record_id, space_id))
        if existing is not None and existing.item_id != item.item_id:
            raise VectorIndexError("record_id belongs to a different item")
        for row in by_item.get(key, ()):
            if row.space_id != space_id or row.record_id != item.record_id:
                deletions[(row.collection_id, row.record_id, row.space_id)] = row
        if full or existing is None or existing.space_id != space_id or existing.fingerprint != item.fingerprint:
            if existing is not None:
                deletions[(existing.collection_id, existing.record_id, existing.space_id)] = existing
            upserts.append(item)
        else:
            unchanged += 1
    if input_kind == "snapshot":
        desired = set(desired_keys)
        for row in current:
            if (row.collection_id, row.item_id) not in desired:
                deletions[(row.collection_id, row.record_id, row.space_id)] = row
    return IndexPlan(
        collection_ids, space_id, input_kind, items, tuple(upserts), tuple(deletions.values()), unchanged, full
    )


def model_space_id(spec: EmbeddingModelSpec, *, preprocessing_id: str = "") -> str:
    serialized = json.dumps([spec.model_name, spec.model_version, spec.dimensions, spec.spec_version, preprocessing_id])
    return hashlib.sha256(serialized.encode()).hexdigest()


def embed_items(
    items: tuple[IndexItem, ...], provider: TextEmbeddings, *, batch_size: int = 256
) -> dict[tuple[str, str], EmbeddingVector]:
    from text_embeddings import EmbeddingInput

    if batch_size <= 0:
        raise VectorIndexError("batch_size must be positive")
    keys = [(item.collection_id, item.item_id) for item in items]
    if len(set(keys)) != len(keys):
        raise VectorIndexError("duplicate item_id within a collection")
    vectors: dict[tuple[str, str], EmbeddingVector] = {}
    expected_spec = provider.model_spec()
    for offset in range(0, len(items), batch_size):
        batch = items[offset : offset + batch_size]
        # Namespaced opaque IDs prevent collisions between collections.
        input_ids = tuple(json.dumps([item.collection_id, item.item_id]) for item in batch)
        outputs = provider.embed(
            tuple(EmbeddingInput(key, item.text) for key, item in zip(input_ids, batch, strict=True))
        )
        if len(outputs) != len(batch) or {row.input_id for row in outputs} != set(input_ids):
            raise VectorIndexError("embedding output IDs must match input item IDs")
        output_by_id = {row.input_id: row for row in outputs}
        for key, item in zip(input_ids, batch, strict=True):
            output = output_by_id[key]
            if len(output.values) != expected_spec.dimensions or any(
                not math.isfinite(value) for value in output.values
            ):
                raise VectorIndexError("embedding values must be finite and match model dimensions")
            if output.model_spec != expected_spec:
                raise VectorIndexError("embedding model spec mismatch")
            vectors[(item.collection_id, item.item_id)] = output
    return vectors


class IndexStore(Protocol):
    def manifest(self, collection_ids: tuple[str, ...]) -> tuple[IndexedItem, ...]: ...

    def apply(self, records: tuple[IndexedVector, ...], deletions: tuple[IndexedItem, ...]) -> None: ...


class VectorIndex:
    """Prepare and apply a revision using injected storage and embedding providers.

    Storage failures propagate. Backend rollback and writer serialization belong to
    the caller. All embeddings are validated before any storage mutation starts.
    """

    def __init__(
        self, store: IndexStore, embeddings: TextEmbeddings, *, batch_size: int = 256, preprocessing_id: str = ""
    ) -> None:
        if batch_size <= 0:
            raise VectorIndexError("batch_size must be positive")
        self._store = store
        self._embeddings = embeddings
        self._batch_size = batch_size
        self._preprocessing_id = preprocessing_id

    def plan(
        self,
        items: tuple[IndexItem, ...],
        *,
        collection_ids: tuple[str, ...],
        input_kind: Literal["snapshot", "changes"],
        full: bool = False,
    ) -> IndexPlan:
        return plan_index(
            items,
            self._store.manifest(collection_ids),
            collection_ids=collection_ids,
            input_kind=input_kind,
            space_id=model_space_id(self._embeddings.model_spec(), preprocessing_id=self._preprocessing_id),
            full=full,
        )

    def apply(self, plan: IndexPlan) -> None:
        if plan.space_id != model_space_id(self._embeddings.model_spec(), preprocessing_id=self._preprocessing_id):
            raise VectorIndexError("plan vector space differs from embedding provider")
        expected = self.plan(plan.items, collection_ids=plan.collection_ids, input_kind=plan.input_kind, full=plan.full)
        if expected != plan:
            raise VectorIndexError("invalid or stale index plan")
        vectors = embed_items(plan.upserts, self._embeddings, batch_size=self._batch_size)
        records = tuple(
            IndexedVector(
                IndexedItem(item.collection_id, item.item_id, item.record_id, plan.space_id, item.fingerprint),
                vectors[(item.collection_id, item.item_id)].values,
            )
            for item in plan.upserts
        )
        self._store.apply(records, plan.deletions)
