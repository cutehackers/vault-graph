"""Compatibility import path for Vault Graph's FastEmbed adapter."""

from vault_graph.vault_adapter.text_embeddings import (
    DEFAULT_FASTEMBED_MODEL_SPEC,
    FASTEMBED_ARTIFACT_REPO_ID,
    SOURCE_MODEL_REVISION,
    FastEmbedBackend,
    FastEmbedTextEmbeddings,
    FastEmbedTextEmbeddingsConfig,
    _default_backend_factory,
    _resolve_snapshot,
)

__all__ = [
    "DEFAULT_FASTEMBED_MODEL_SPEC",
    "FASTEMBED_ARTIFACT_REPO_ID",
    "SOURCE_MODEL_REVISION",
    "FastEmbedBackend",
    "FastEmbedTextEmbeddings",
    "FastEmbedTextEmbeddingsConfig",
    "_default_backend_factory",
    "_resolve_snapshot",
]
