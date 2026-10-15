from __future__ import annotations

from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Protocol

from text_embeddings.contracts import EmbeddingInput, EmbeddingModelSpec, EmbeddingVector, TextEmbeddingsError


class FastEmbedBackend(Protocol):
    def embed(self, documents: list[str], *, batch_size: int, parallel: int | None) -> Iterable[Iterable[float]]: ...


class FastEmbedTextEmbeddings:
    def __init__(
        self,
        *,
        model_spec: EmbeddingModelSpec,
        batch_size: int = 256,
        parallelism: int | None = None,
        backend_factory: Callable[[], FastEmbedBackend] | None = None,
        model_path: Path | None = None,
        lazy_load: bool = True,
    ) -> None:
        if batch_size <= 0:
            raise TextEmbeddingsError("embedding_batch_size must be positive")
        if parallelism is not None and parallelism < 0:
            raise TextEmbeddingsError("embedding_parallelism must be None, 0, or positive")
        if backend_factory is None and model_path is None:
            raise TextEmbeddingsError("backend_factory or local model_path is required")
        if model_path is not None and not model_path.is_dir():
            raise TextEmbeddingsError("model_path must be an existing local directory")
        self._model_spec = model_spec
        self._batch_size = batch_size
        self._parallelism = parallelism
        self._backend_factory = backend_factory or self._default_backend_factory
        self._model_path = model_path
        self._backend: FastEmbedBackend | None = None
        if not lazy_load:
            self._backend = self._load_backend()

    def model_spec(self) -> EmbeddingModelSpec:
        return self._model_spec

    def embed(self, inputs: tuple[EmbeddingInput, ...]) -> tuple[EmbeddingVector, ...]:
        seen: set[str] = set()
        for item in inputs:
            if item.input_id in seen:
                raise TextEmbeddingsError("input_id must be unique within one embedding call")
            seen.add(item.input_id)
        if not inputs:
            return ()
        backend = self._backend or self._load_backend()
        self._backend = backend
        raw_vectors = tuple(
            backend.embed([item.text for item in inputs], batch_size=self._batch_size, parallel=self._parallelism)
        )
        if len(raw_vectors) != len(inputs):
            raise TextEmbeddingsError("embedding output count must match input count")
        return tuple(
            EmbeddingVector(item.input_id, tuple(float(value) for value in values), self._model_spec)
            for item, values in zip(inputs, raw_vectors, strict=True)
        )

    def _load_backend(self) -> FastEmbedBackend:
        try:
            return self._backend_factory()
        except TextEmbeddingsError:
            raise
        except Exception as exc:
            raise TextEmbeddingsError(f"embedding model unavailable: {exc}") from exc

    def _default_backend_factory(self) -> FastEmbedBackend:
        try:
            from fastembed import TextEmbedding
        except ImportError as exc:
            raise TextEmbeddingsError("install nolemy-text-embeddings[fastembed] to use FastEmbed") from exc
        assert self._model_path is not None
        return TextEmbedding(
            model_name=self._model_spec.model_name,
            specific_model_path=str(self._model_path),
            local_files_only=True,
        )
