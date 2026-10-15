"""Domain-neutral vector storage records."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Protocol

from vector_search.errors import VectorSearchError

type Scalar = str | int | float | bool
type Metadata = Mapping[str, Scalar]


@dataclass(frozen=True)
class CollectionSpec:
    name: str
    dimensions: int
    distance_metric: str = "cosine"
    metadata: Metadata = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.name:
            raise VectorSearchError("collection name is required")
        if self.dimensions <= 0:
            raise VectorSearchError("dimensions must be positive")
        if self.distance_metric != "cosine":
            raise VectorSearchError(f"unsupported distance metric: {self.distance_metric}")


@dataclass(frozen=True)
class StoredVector:
    record_id: str
    values: tuple[float, ...]
    metadata: Metadata = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.record_id:
            raise VectorSearchError("record_id is required")


@dataclass(frozen=True)
class VectorDeletion:
    collection: CollectionSpec
    record_id: str
    matches: Metadata = field(default_factory=dict)


@dataclass(frozen=True)
class VectorMatch:
    record_id: str
    score: float
    rank: int
    metadata: Metadata


@dataclass(frozen=True)
class ManifestRecord:
    collection_name: str
    record_id: str
    metadata: Metadata


@dataclass(frozen=True)
class StoreHealth:
    ok: bool
    backend: str
    schema_version: str
    schema_compatible: bool
    message: str


class VectorStore(Protocol):
    """Store boundary for already-computed vectors and opaque scalar metadata."""

    def apply(
        self,
        records: tuple[tuple[CollectionSpec, StoredVector], ...] = (),
        deletions: tuple[VectorDeletion, ...] = (),
    ) -> None: ...

    def search(
        self,
        spec: CollectionSpec,
        values: tuple[float, ...],
        limit: int,
        *,
        predicate: Callable[[Metadata], bool] | None = None,
        tie_key: Callable[[Metadata, str], tuple[object, ...]] | None = None,
        vector_id_batch_size: int = 500,
    ) -> tuple[VectorMatch, ...]: ...

    def export_manifest(self, predicate: Callable[[Metadata], bool] | None = None) -> tuple[ManifestRecord, ...]: ...

    def health(self) -> StoreHealth: ...

    def close(self) -> None: ...
