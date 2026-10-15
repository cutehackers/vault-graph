"""Compatibility import for :mod:`vault_graph.interface.composition.adapters.text_embeddings`."""

import sys

from vault_graph.interface.composition.adapters import text_embeddings as _implementation
from vault_graph.interface.composition.adapters.text_embeddings import (
    DEFAULT_FASTEMBED_MODEL_SPEC as DEFAULT_FASTEMBED_MODEL_SPEC,
)
from vault_graph.interface.composition.adapters.text_embeddings import (
    FASTEMBED_ARTIFACT_REPO_ID as FASTEMBED_ARTIFACT_REPO_ID,
)
from vault_graph.interface.composition.adapters.text_embeddings import SOURCE_MODEL_REVISION as SOURCE_MODEL_REVISION
from vault_graph.interface.composition.adapters.text_embeddings import FastEmbedBackend as FastEmbedBackend
from vault_graph.interface.composition.adapters.text_embeddings import (
    FastEmbedTextEmbeddings as FastEmbedTextEmbeddings,
)
from vault_graph.interface.composition.adapters.text_embeddings import (
    FastEmbedTextEmbeddingsConfig as FastEmbedTextEmbeddingsConfig,
)
from vault_graph.interface.composition.adapters.text_embeddings import (
    _default_backend_factory as _default_backend_factory,
)
from vault_graph.interface.composition.adapters.text_embeddings import _resolve_snapshot as _resolve_snapshot

sys.modules[__name__] = _implementation
