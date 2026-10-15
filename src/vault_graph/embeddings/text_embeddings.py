"""Compatibility import for :mod:`vault_graph.storage.interfaces.text_embeddings`."""

import sys
from dataclasses import dataclass as dataclass
from typing import Protocol as Protocol

from vault_graph.errors import TextEmbeddingsError as TextEmbeddingsError
from vault_graph.storage.interfaces import text_embeddings as _implementation
from vault_graph.storage.interfaces.text_embeddings import EmbeddingInput as EmbeddingInput
from vault_graph.storage.interfaces.text_embeddings import EmbeddingModelSpec as EmbeddingModelSpec
from vault_graph.storage.interfaces.text_embeddings import EmbeddingVector as EmbeddingVector
from vault_graph.storage.interfaces.text_embeddings import TextEmbeddings as TextEmbeddings
from vault_graph.storage.interfaces.text_embeddings import _require_non_empty as _require_non_empty

sys.modules[__name__] = _implementation
