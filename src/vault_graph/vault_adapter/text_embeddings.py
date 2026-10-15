from __future__ import annotations

import warnings
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from text_embeddings import EmbeddingInput as GenericEmbeddingInput
from text_embeddings import EmbeddingModelSpec as GenericEmbeddingModelSpec
from text_embeddings import FastEmbedTextEmbeddings as GenericFastEmbedTextEmbeddings
from text_embeddings import TextEmbeddingsError as GenericTextEmbeddingsError

from vault_graph.embeddings.text_embeddings import EmbeddingInput, EmbeddingModelSpec, EmbeddingVector
from vault_graph.errors import TextEmbeddingsError

DEFAULT_FASTEMBED_MODEL_SPEC = EmbeddingModelSpec(
    model_name="sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
    model_version="faf4aa4225822f3bc6376869cb1164e8e3feedd0",
    dimensions=384,
    spec_version="fastembed-multilingual-minilm-l12-v2-cosine-v1",
)

FASTEMBED_ARTIFACT_REPO_ID = "qdrant/paraphrase-multilingual-MiniLM-L12-v2-onnx-Q"
SOURCE_MODEL_REVISION = "e8f8c211226b894fcb81acc59f3b34ba3efd5f42"


class FastEmbedBackend(Protocol):
    def embed(self, documents: list[str], *, batch_size: int, parallel: int | None) -> Iterable[Iterable[float]]: ...


@dataclass(frozen=True)
class FastEmbedTextEmbeddingsConfig:
    model_name: str = DEFAULT_FASTEMBED_MODEL_SPEC.model_name
    model_version: str = DEFAULT_FASTEMBED_MODEL_SPEC.model_version
    dimensions: int = DEFAULT_FASTEMBED_MODEL_SPEC.dimensions
    spec_version: str = DEFAULT_FASTEMBED_MODEL_SPEC.spec_version
    artifact_repo_id: str = FASTEMBED_ARTIFACT_REPO_ID
    source_model_revision: str = SOURCE_MODEL_REVISION
    cache_dir: Path = Path("~/.cache/vault-graph/embeddings")
    embedding_batch_size: int = 256
    embedding_parallelism: int | None = None
    embedding_lazy_load: bool = True
    local_files_only: bool = False

    def __post_init__(self) -> None:
        if self.embedding_batch_size <= 0:
            raise TextEmbeddingsError("embedding_batch_size must be positive")
        if self.embedding_parallelism is not None and self.embedding_parallelism < 0:
            raise TextEmbeddingsError("embedding_parallelism must be None, 0, or positive")

    def model_spec(self) -> EmbeddingModelSpec:
        return EmbeddingModelSpec(
            model_name=self.model_name,
            model_version=self.model_version,
            dimensions=self.dimensions,
            spec_version=self.spec_version,
        )


class FastEmbedTextEmbeddings:
    def __init__(
        self,
        *,
        config: FastEmbedTextEmbeddingsConfig,
        backend_factory: Callable[[FastEmbedTextEmbeddingsConfig, Path], FastEmbedBackend] | None = None,
        snapshot_resolver: Callable[[FastEmbedTextEmbeddingsConfig], Path] | None = None,
    ) -> None:
        self._config = config
        self._backend_factory = backend_factory or _default_backend_factory
        self._snapshot_resolver = snapshot_resolver or _resolve_snapshot
        self._backend: FastEmbedBackend | None = None
        if not config.embedding_lazy_load:
            self._backend = self._load_backend()
        try:
            self._provider = GenericFastEmbedTextEmbeddings(
                model_spec=GenericEmbeddingModelSpec(
                    config.model_name, config.model_version, config.dimensions, config.spec_version
                ),
                batch_size=config.embedding_batch_size,
                parallelism=config.embedding_parallelism,
                backend_factory=self._backend_for_provider,
            )
        except GenericTextEmbeddingsError as exc:
            raise TextEmbeddingsError(str(exc)) from exc

    @property
    def config(self) -> FastEmbedTextEmbeddingsConfig:
        return self._config

    def model_spec(self) -> EmbeddingModelSpec:
        return self._config.model_spec()

    def can_embed_without_download(self) -> bool:
        try:
            self._snapshot_resolver(self._config_for_local_files_only())
        except Exception:
            return False
        return True

    def embed(self, inputs: tuple[EmbeddingInput, ...]) -> tuple[EmbeddingVector, ...]:
        try:
            vectors = self._provider.embed(tuple(GenericEmbeddingInput(item.input_id, item.text) for item in inputs))
        except GenericTextEmbeddingsError as exc:
            raise TextEmbeddingsError(str(exc)) from exc
        return tuple(EmbeddingVector(vector.input_id, vector.values, self.model_spec()) for vector in vectors)

    def _load_backend(self) -> FastEmbedBackend:
        snapshot_path = self._snapshot_resolver(self._config)
        try:
            return self._backend_factory(self._config, snapshot_path)
        except Exception as exc:
            raise TextEmbeddingsError(f"embedding model unavailable: {exc}") from exc

    def _backend_for_provider(self) -> FastEmbedBackend:
        if self._backend is None:
            try:
                self._backend = self._load_backend()
            except TextEmbeddingsError as exc:
                raise GenericTextEmbeddingsError(str(exc)) from exc
        return self._backend

    def _config_for_local_files_only(self) -> FastEmbedTextEmbeddingsConfig:
        return FastEmbedTextEmbeddingsConfig(
            model_name=self._config.model_name,
            model_version=self._config.model_version,
            dimensions=self._config.dimensions,
            spec_version=self._config.spec_version,
            artifact_repo_id=self._config.artifact_repo_id,
            source_model_revision=self._config.source_model_revision,
            cache_dir=self._config.cache_dir,
            embedding_batch_size=self._config.embedding_batch_size,
            embedding_parallelism=self._config.embedding_parallelism,
            embedding_lazy_load=self._config.embedding_lazy_load,
            local_files_only=True,
        )


def _resolve_snapshot(config: FastEmbedTextEmbeddingsConfig) -> Path:
    try:
        from huggingface_hub import snapshot_download

        return Path(
            snapshot_download(
                repo_id=config.artifact_repo_id,
                revision=config.model_version,
                cache_dir=str(config.cache_dir.expanduser()),
                local_files_only=config.local_files_only,
            )
        )
    except Exception as exc:
        raise TextEmbeddingsError(f"embedding model unavailable: {exc}") from exc


def _default_backend_factory(config: FastEmbedTextEmbeddingsConfig, snapshot_path: Path) -> FastEmbedBackend:
    from fastembed import TextEmbedding

    with warnings.catch_warnings():
        warnings.filterwarnings(
            "ignore",
            message=(
                r"The model sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2 "
                r"now uses mean pooling instead of CLS embedding.*"
            ),
            category=UserWarning,
        )
        return TextEmbedding(
            model_name=config.model_name,
            specific_model_path=str(snapshot_path),
            cache_dir=str(config.cache_dir.expanduser()),
            lazy_load=config.embedding_lazy_load,
        )
