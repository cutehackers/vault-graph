from __future__ import annotations

import threading
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, replace
from pathlib import Path
from types import MappingProxyType
from typing import TYPE_CHECKING, Any, Literal, Protocol

from text_embeddings import EmbeddingInput as GenericEmbeddingInput
from text_embeddings import EmbeddingModelSpec as GenericEmbeddingModelSpec
from text_embeddings import FastEmbedTextEmbeddings as GenericFastEmbedTextEmbeddings
from text_embeddings import TextEmbeddingsError as GenericTextEmbeddingsError
from vector_index.indexing import DEFAULT_TOKEN_BUDGET

from vault_graph.errors import CatalogError, TextEmbeddingsError
from vault_graph.operation.scope.embedding_selection import DEFAULT_MODELS_DIR, load_embedding_selection
from vault_graph.storage.interfaces.text_embeddings import EmbeddingInput, EmbeddingModelSpec, EmbeddingVector

if TYPE_CHECKING:
    from vault_graph.operation.scope.catalog_service import CatalogService


@dataclass(frozen=True)
class EmbeddingPreset:
    """One entry of the model list. Adding a model means adding one entry to ``EMBEDDING_PRESETS``."""

    name: str
    model_name: str
    revision: str
    dimensions: int
    spec_version: str
    repo_id: str
    source_model_revision: str
    files: tuple[str, ...] | None
    fastembed_registration: Literal["builtin", "custom"]
    model_file: str
    pooling: Literal["", "CLS", "MEAN"]
    normalization: bool
    max_tokens: int
    download_mb: int
    summary: str
    query_prefix: str = ""
    document_prefix: str = ""

    def model_spec(self) -> EmbeddingModelSpec:
        return EmbeddingModelSpec(
            model_name=self.model_name,
            model_version=self.revision,
            dimensions=self.dimensions,
            spec_version=self.spec_version,
        )


_TOKENIZER_FILES = ("config.json", "tokenizer.json", "tokenizer_config.json", "special_tokens_map.json")

# Pinned from Hugging Face API metadata on 2026-11-04, without downloading any model file.
# e5-small revision (`sha`): https://huggingface.co/api/models/Xenova/multilingual-e5-small/revision/main
# e5-small files and sizes: https://huggingface.co/api/models/Xenova/multilingual-e5-small/tree/main?recursive=true
EMBEDDING_PRESETS: Mapping[str, EmbeddingPreset] = MappingProxyType(
    {
        preset.name: preset
        for preset in (
            EmbeddingPreset(
                name="e5-small",
                model_name="Xenova/multilingual-e5-small",
                revision="761b726dd34fb83930e26aab4e9ac3899aa1fa78",
                dimensions=384,
                spec_version="fastembed-multilingual-e5-small-int8-mean-qpprefix-v1",
                repo_id="Xenova/multilingual-e5-small",
                source_model_revision="",
                files=("onnx/model_int8.onnx", *_TOKENIZER_FILES),
                fastembed_registration="custom",
                model_file="onnx/model_int8.onnx",
                pooling="MEAN",
                normalization=True,
                max_tokens=512,
                download_mb=135,
                summary="Korean and English coding-agent sessions, small and fast",
                query_prefix="query: ",
                document_prefix="passage: ",
            ),
        )
    }
)
DEFAULT_EMBEDDING_PRESET = "e5-small"

_REGISTERED_CUSTOM_MODELS: set[str] = set()
_REGISTRATION_LOCK = threading.Lock()


class FastEmbedBackend(Protocol):
    def embed(self, documents: list[str], *, batch_size: int, parallel: int | None) -> Iterable[Iterable[float]]: ...


@dataclass(frozen=True)
class FastEmbedTextEmbeddingsConfig:
    preset: EmbeddingPreset
    cache_dir: Path = DEFAULT_MODELS_DIR
    # Item cap per embedding batch.
    embedding_batch_size: int = 256
    # Cap on items x largest estimated tokens per embedding batch (spec 4.3.4).
    embedding_token_budget: int = DEFAULT_TOKEN_BUDGET
    embedding_parallelism: int | None = None
    embedding_lazy_load: bool = True
    local_files_only: bool = False
    # Passed to fastembed as ONNX ``enable_cpu_mem_arena``. The default stays on until
    # the full re-index measurement (spec 4.3.4) shows turning it off costs at most 20%.
    cpu_mem_arena: bool = True

    def __post_init__(self) -> None:
        if self.embedding_batch_size <= 0:
            raise TextEmbeddingsError("embedding_batch_size must be positive")
        if self.embedding_token_budget <= 0:
            raise TextEmbeddingsError("embedding_token_budget must be positive")
        if self.embedding_parallelism is not None and self.embedding_parallelism < 0:
            raise TextEmbeddingsError("embedding_parallelism must be None, 0, or positive")

    def model_spec(self) -> EmbeddingModelSpec:
        return self.preset.model_spec()


def text_embeddings_for(catalog_service: CatalogService, *, local_files_only: bool) -> FastEmbedTextEmbeddings:
    """The only place that builds the embedding config. It reads the settings file on every call."""
    path = catalog_service.embedding_config_path
    try:
        selection = load_embedding_selection(path)
    except CatalogError as exc:
        raise TextEmbeddingsError(str(exc)) from exc
    name = selection.model or DEFAULT_EMBEDDING_PRESET
    preset = EMBEDDING_PRESETS.get(name)
    if preset is None:
        raise TextEmbeddingsError(
            f"embedding settings file names unknown model {name!r}; available: {', '.join(EMBEDDING_PRESETS)}: {path}"
        )
    return FastEmbedTextEmbeddings(
        config=FastEmbedTextEmbeddingsConfig(
            preset=preset,
            cache_dir=selection.models_dir.expanduser(),
            local_files_only=local_files_only,
        )
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
        spec = config.model_spec()
        try:
            self._provider = GenericFastEmbedTextEmbeddings(
                model_spec=GenericEmbeddingModelSpec(
                    spec.model_name, spec.model_version, spec.dimensions, spec.spec_version
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
        """Embed documents. The preset's document prefix goes in front of each text."""
        prefix = self._config.preset.document_prefix
        return self._embed(tuple(GenericEmbeddingInput(item.input_id, prefix + item.text) for item in inputs))

    def embed_query(self, text: str) -> EmbeddingVector:
        """Embed one search query. The preset's query prefix goes in front of the text."""
        return self._embed((GenericEmbeddingInput("query", self._config.preset.query_prefix + text),))[0]

    def _embed(self, inputs: tuple[GenericEmbeddingInput, ...]) -> tuple[EmbeddingVector, ...]:
        try:
            vectors = self._provider.embed(inputs)
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
        return replace(self._config, local_files_only=True)


def embedding_model_downloaded(preset: EmbeddingPreset, models_dir: Path) -> bool:
    """Return whether `models_dir` already holds the preset's files. Never downloads."""
    config = FastEmbedTextEmbeddingsConfig(preset=preset, cache_dir=models_dir, local_files_only=True)
    return FastEmbedTextEmbeddings(config=config).can_embed_without_download()


def download_embedding_model(preset: EmbeddingPreset, models_dir: Path) -> Path:
    """Download the preset's pinned files into `models_dir` and return the snapshot folder."""
    return _resolve_snapshot(FastEmbedTextEmbeddingsConfig(preset=preset, cache_dir=models_dir))


def _resolve_snapshot(config: FastEmbedTextEmbeddingsConfig) -> Path:
    preset = config.preset
    try:
        from huggingface_hub import snapshot_download

        return Path(
            snapshot_download(
                repo_id=preset.repo_id,
                revision=preset.revision,
                cache_dir=str(config.cache_dir.expanduser()),
                local_files_only=config.local_files_only,
                allow_patterns=list(preset.files) if preset.files is not None else None,
            )
        )
    except Exception as exc:
        raise TextEmbeddingsError(f"embedding model unavailable: {exc}") from exc


def _default_backend_factory(config: FastEmbedTextEmbeddingsConfig, snapshot_path: Path) -> FastEmbedBackend:
    from fastembed import TextEmbedding

    preset = config.preset
    if preset.fastembed_registration == "custom":
        _register_custom_model(TextEmbedding, preset)
    return TextEmbedding(
        model_name=preset.model_name,
        specific_model_path=str(snapshot_path),
        cache_dir=str(config.cache_dir.expanduser()),
        lazy_load=config.embedding_lazy_load,
        enable_cpu_mem_arena=config.cpu_mem_arena,
    )


def _register_custom_model(text_embedding: Any, preset: EmbeddingPreset) -> None:
    """Register a custom preset with fastembed once per process."""
    from fastembed.common.model_description import ModelSource, PoolingType

    with _REGISTRATION_LOCK:
        if preset.model_name in _REGISTERED_CUSTOM_MODELS:
            return
        text_embedding.add_custom_model(
            model=preset.model_name,
            pooling=PoolingType(preset.pooling),
            normalization=preset.normalization,
            sources=ModelSource(hf=preset.repo_id),
            dim=preset.dimensions,
            model_file=preset.model_file,
        )
        _REGISTERED_CUSTOM_MODELS.add(preset.model_name)
