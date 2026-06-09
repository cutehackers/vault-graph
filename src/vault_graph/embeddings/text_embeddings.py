from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from vault_graph.errors import TextEmbeddingsError


@dataclass(frozen=True)
class EmbeddingModelSpec:
    model_name: str
    model_version: str
    dimensions: int
    spec_version: str

    def __post_init__(self) -> None:
        _require_non_empty(self.model_name, "model_name")
        _require_non_empty(self.model_version, "model_version")
        _require_non_empty(self.spec_version, "spec_version")
        if self.dimensions <= 0:
            raise TextEmbeddingsError("dimensions must be positive")


@dataclass(frozen=True)
class EmbeddingInput:
    input_id: str
    text: str

    def __post_init__(self) -> None:
        _require_non_empty(self.input_id, "input_id")


@dataclass(frozen=True)
class EmbeddingVector:
    input_id: str
    values: tuple[float, ...]
    model_spec: EmbeddingModelSpec

    def __post_init__(self) -> None:
        _require_non_empty(self.input_id, "input_id")
        if len(self.values) != self.model_spec.dimensions:
            raise TextEmbeddingsError(
                f"embedding dimension mismatch: expected {self.model_spec.dimensions}, got {len(self.values)}"
            )


class TextEmbeddings(Protocol):
    def model_spec(self) -> EmbeddingModelSpec: ...

    def can_embed_without_download(self) -> bool: ...

    def embed(self, inputs: tuple[EmbeddingInput, ...]) -> tuple[EmbeddingVector, ...]: ...


def _require_non_empty(value: str, field_name: str) -> None:
    if not value:
        raise TextEmbeddingsError(f"{field_name} is required")
