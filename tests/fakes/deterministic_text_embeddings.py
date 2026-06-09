from __future__ import annotations

import hashlib

from vault_graph.embeddings.text_embeddings import EmbeddingInput, EmbeddingModelSpec, EmbeddingVector
from vault_graph.errors import TextEmbeddingsError


class DeterministicTextEmbeddings:
    def __init__(self, model_spec: EmbeddingModelSpec) -> None:
        self._model_spec = model_spec

    def model_spec(self) -> EmbeddingModelSpec:
        return self._model_spec

    def can_embed_without_download(self) -> bool:
        return True

    def embed(self, inputs: tuple[EmbeddingInput, ...]) -> tuple[EmbeddingVector, ...]:
        _validate_unique_input_ids(inputs)
        return tuple(
            EmbeddingVector(
                input_id=item.input_id,
                values=_values_for_text(text=item.text, dimensions=self._model_spec.dimensions),
                model_spec=self._model_spec,
            )
            for item in inputs
        )


def _values_for_text(*, text: str, dimensions: int) -> tuple[float, ...]:
    digest = hashlib.sha256(text.encode("utf-8")).digest()
    return tuple(round((digest[index % len(digest)] / 255.0) * 2.0 - 1.0, 6) for index in range(dimensions))


def _validate_unique_input_ids(inputs: tuple[EmbeddingInput, ...]) -> None:
    seen: set[str] = set()
    for item in inputs:
        if item.input_id in seen:
            raise TextEmbeddingsError("input_id must be unique within one embedding call")
        seen.add(item.input_id)
