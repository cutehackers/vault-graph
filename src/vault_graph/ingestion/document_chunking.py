"""Compatibility import for :mod:`vault_graph.indexing.ingestion.document_chunking`."""

import re as re
import sys
from dataclasses import dataclass as dataclass
from typing import Protocol as Protocol
from typing import TypeVar as TypeVar
from typing import runtime_checkable as runtime_checkable

from vault_graph.indexing.ingestion import document_chunking as _implementation
from vault_graph.indexing.ingestion.document_chunking import CHUNKER_VERSION as CHUNKER_VERSION
from vault_graph.indexing.ingestion.document_chunking import (
    DEFAULT_DOCUMENT_CHUNK_MAX_TOKENS as DEFAULT_DOCUMENT_CHUNK_MAX_TOKENS,
)
from vault_graph.indexing.ingestion.document_chunking import ChunkDraft as ChunkDraft
from vault_graph.indexing.ingestion.document_chunking import ChunkResultT as ChunkResultT
from vault_graph.indexing.ingestion.document_chunking import DocumentChunker as DocumentChunker
from vault_graph.indexing.ingestion.document_chunking import DocumentWindowChunker as DocumentWindowChunker
from vault_graph.indexing.ingestion.document_chunking import _anchor as _anchor
from vault_graph.indexing.ingestion.document_chunking import _boundary_key as _boundary_key
from vault_graph.indexing.ingestion.document_chunking import _Fragment as _Fragment
from vault_graph.indexing.ingestion.document_chunking import _fragments_for_unit as _fragments_for_unit
from vault_graph.indexing.ingestion.document_chunking import _join_fragments as _join_fragments
from vault_graph.indexing.ingestion.document_chunking import _token_count as _token_count
from vault_graph.indexing.ingestion.document_chunking import chunk_document as chunk_document
from vault_graph.indexing.ingestion.document_chunking import contextual_embedding_text as contextual_embedding_text
from vault_graph.indexing.ingestion.document_models import ContentBlock as ContentBlock
from vault_graph.indexing.ingestion.document_models import ContentUnit as ContentUnit
from vault_graph.indexing.ingestion.document_models import ExtractedDocument as ExtractedDocument
from vault_graph.indexing.ingestion.document_models import SourceLocator as SourceLocator

sys.modules[__name__] = _implementation
