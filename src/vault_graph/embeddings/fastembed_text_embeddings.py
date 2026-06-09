from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

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
        _validate_unique_input_ids(inputs)
        if not inputs:
            return ()
        backend = self._backend or self._load_backend()
        self._backend = backend
        raw_vectors = tuple(
            backend.embed(
                [item.text for item in inputs],
                batch_size=self._config.embedding_batch_size,
                parallel=self._config.embedding_parallelism,
            )
        )
        if len(raw_vectors) != len(inputs):
            raise TextEmbeddingsError("embedding output count must match input count")
        return tuple(
            EmbeddingVector(
                input_id=item.input_id,
                values=tuple(float(value) for value in values),
                model_spec=self.model_spec(),
            )
            for item, values in zip(inputs, raw_vectors, strict=True)
        )

    def _load_backend(self) -> FastEmbedBackend:
        snapshot_path = self._snapshot_resolver(self._config)
        try:
            return self._backend_factory(self._config, snapshot_path)
        except Exception as exc:
            raise TextEmbeddingsError(f"embedding model unavailable: {exc}") from exc

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


def _validate_unique_input_ids(inputs: tuple[EmbeddingInput, ...]) -> None:
    seen: set[str] = set()
    for item in inputs:
        if item.input_id in seen:
            raise TextEmbeddingsError("input_id must be unique within one embedding call")
        seen.add(item.input_id)


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

    return TextEmbedding(
        model_name=config.model_name,
        specific_model_path=str(snapshot_path),
        cache_dir=str(config.cache_dir.expanduser()),
        lazy_load=config.embedding_lazy_load,
    )
