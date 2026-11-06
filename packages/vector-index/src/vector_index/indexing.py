from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Callable, Iterator
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
    # Optional. When both the item and its stored row carry one, a differing value with an equal
    # ``fingerprint`` plans a metadata-only update instead of a re-embedding.
    metadata_fingerprint: str | None = None

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
    metadata_fingerprint: str | None = None

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
    # Items whose stored vector stays valid but whose metadata changed. Empty without metadata fingerprints.
    metadata_updates: tuple[IndexItem, ...] = ()


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
    metadata_updates: list[IndexItem] = []
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
        elif (
            item.metadata_fingerprint is not None
            and existing.metadata_fingerprint is not None
            and existing.metadata_fingerprint != item.metadata_fingerprint
        ):
            metadata_updates.append(item)
        else:
            unchanged += 1
    if input_kind == "snapshot":
        desired = set(desired_keys)
        for row in current:
            if (row.collection_id, row.item_id) not in desired:
                deletions[(row.collection_id, row.record_id, row.space_id)] = row
    return IndexPlan(
        collection_ids,
        space_id,
        input_kind,
        items,
        tuple(upserts),
        tuple(deletions.values()),
        unchanged,
        full,
        tuple(metadata_updates),
    )


def model_space_id(spec: EmbeddingModelSpec, *, preprocessing_id: str = "") -> str:
    serialized = json.dumps([spec.model_name, spec.model_version, spec.dimensions, spec.spec_version, preprocessing_id])
    return hashlib.sha256(serialized.encode()).hexdigest()


DEFAULT_TOKEN_BUDGET = 16_384
DEFAULT_MAX_BATCH_ITEMS = 256


def estimate_tokens_from_bytes(text: str) -> int:
    """Token estimate used when no model tokenizer is available: UTF-8 bytes divided by three, rounded up."""
    return max(1, -(-len(text.encode("utf-8")) // 3))


@dataclass(frozen=True)
class EmbeddingBatch:
    """One provider call. ``vectors[i]`` belongs to ``items[i]`` and has been validated."""

    items: tuple[IndexItem, ...]
    vectors: tuple[EmbeddingVector, ...]
    max_estimated_tokens: int


def iter_embedding_batches(
    items: tuple[IndexItem, ...],
    provider: TextEmbeddings,
    *,
    token_budget: int,
    max_batch_items: int,
    estimate_tokens: Callable[[str], int] | None = None,
) -> Iterator[EmbeddingBatch]:
    """Embed items in batches sorted by estimated tokens.

    Every batch keeps ``len(items) * max_estimated_tokens <= token_budget`` and
    ``len(items) <= max_batch_items``. The only exception is one item whose own
    estimate exceeds the budget: it is embedded alone. Inputs are validated before
    the first provider call, so a duplicate never produces a partial result.
    """
    if token_budget <= 0 or max_batch_items <= 0:
        raise VectorIndexError("token_budget and max_batch_items must be positive")
    keys = [(item.collection_id, item.item_id) for item in items]
    if len(set(keys)) != len(keys):
        raise VectorIndexError("duplicate item_id within a collection")
    estimate = estimate_tokens or estimate_tokens_from_bytes
    ordered = sorted(
        ((max(1, estimate(item.text)), index, item) for index, item in enumerate(items)),
        key=lambda row: (row[0], row[1]),
    )
    expected_spec = provider.model_spec()
    batch: list[IndexItem] = []
    batch_max = 0
    for tokens, _, item in ordered:
        # Sorted ascending, so the new item's estimate is the batch maximum.
        if batch and (len(batch) + 1 > max_batch_items or (len(batch) + 1) * tokens > token_budget):
            yield _embed_batch(tuple(batch), batch_max, provider, expected_spec)
            batch = []
        batch.append(item)
        batch_max = tokens
    if batch:
        yield _embed_batch(tuple(batch), batch_max, provider, expected_spec)


def _embed_batch(
    batch: tuple[IndexItem, ...], max_tokens: int, provider: TextEmbeddings, expected_spec: EmbeddingModelSpec
) -> EmbeddingBatch:
    from text_embeddings import EmbeddingInput

    # Namespaced opaque IDs prevent collisions between collections.
    input_ids = tuple(json.dumps([item.collection_id, item.item_id]) for item in batch)
    outputs = provider.embed(tuple(EmbeddingInput(key, item.text) for key, item in zip(input_ids, batch, strict=True)))
    if len(outputs) != len(batch) or {row.input_id for row in outputs} != set(input_ids):
        raise VectorIndexError("embedding output IDs must match input item IDs")
    output_by_id = {row.input_id: row for row in outputs}
    vectors: list[EmbeddingVector] = []
    for key in input_ids:
        output = output_by_id[key]
        if len(output.values) != expected_spec.dimensions or any(not math.isfinite(value) for value in output.values):
            raise VectorIndexError("embedding values must be finite and match model dimensions")
        if output.model_spec != expected_spec:
            raise VectorIndexError("embedding model spec mismatch")
        vectors.append(output)
    return EmbeddingBatch(batch, tuple(vectors), max_tokens)


def embed_items(
    items: tuple[IndexItem, ...],
    provider: TextEmbeddings,
    *,
    batch_size: int = DEFAULT_MAX_BATCH_ITEMS,
    token_budget: int = DEFAULT_TOKEN_BUDGET,
    estimate_tokens: Callable[[str], int] | None = None,
) -> dict[tuple[str, str], EmbeddingVector]:
    """Collect ``iter_embedding_batches``. ``batch_size`` is the item cap per batch."""
    if batch_size <= 0:
        raise VectorIndexError("batch_size must be positive")
    vectors: dict[tuple[str, str], EmbeddingVector] = {}
    for batch in iter_embedding_batches(
        items, provider, token_budget=token_budget, max_batch_items=batch_size, estimate_tokens=estimate_tokens
    ):
        for item, vector in zip(batch.items, batch.vectors, strict=True):
            vectors[(item.collection_id, item.item_id)] = vector
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
        # IndexStore has no metadata-only write, so metadata updates are written as full records.
        writes = plan.upserts + plan.metadata_updates
        vectors = embed_items(writes, self._embeddings, batch_size=self._batch_size)
        records = tuple(
            IndexedVector(
                IndexedItem(
                    item.collection_id,
                    item.item_id,
                    item.record_id,
                    plan.space_id,
                    item.fingerprint,
                    item.metadata_fingerprint,
                ),
                vectors[(item.collection_id, item.item_id)].values,
            )
            for item in writes
        )
        self._store.apply(records, plan.deletions)
