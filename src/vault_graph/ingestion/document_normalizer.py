"""Compatibility import for :mod:`vault_graph.indexing.ingestion.document_normalizer`."""

import hashlib as hashlib
import sys
from dataclasses import dataclass as dataclass
from datetime import UTC as UTC
from datetime import datetime as datetime
from typing import Any as Any

from vault_graph.indexing.ingestion import document_normalizer as _implementation
from vault_graph.indexing.ingestion.document_authority import DocumentRole as DocumentRole
from vault_graph.indexing.ingestion.document_authority import classify_document_role as classify_document_role
from vault_graph.indexing.ingestion.document_chunking import CHUNKER_VERSION as CHUNKER_VERSION
from vault_graph.indexing.ingestion.document_chunking import chunk_document as chunk_document
from vault_graph.indexing.ingestion.document_models import ExtractedDocument as ExtractedDocument
from vault_graph.indexing.ingestion.document_models import SourceDocument as SourceDocument
from vault_graph.indexing.ingestion.document_models import SourceLocator as SourceLocator
from vault_graph.indexing.ingestion.document_normalizer import PARSER_VERSION as PARSER_VERSION
from vault_graph.indexing.ingestion.document_normalizer import ChunkSnapshot as ChunkSnapshot
from vault_graph.indexing.ingestion.document_normalizer import DocumentNormalizer as DocumentNormalizer
from vault_graph.indexing.ingestion.document_normalizer import DocumentSnapshot as DocumentSnapshot
from vault_graph.indexing.ingestion.document_normalizer import NormalizedDocument as NormalizedDocument
from vault_graph.indexing.ingestion.document_normalizer import _extracted_input as _extracted_input
from vault_graph.indexing.ingestion.document_normalizer import stable_id as stable_id
from vault_graph.indexing.ingestion.document_readers import MarkdownDocumentReader as MarkdownDocumentReader
from vault_graph.indexing.ingestion.vault_loader import LoadedVaultDocument as LoadedVaultDocument

sys.modules[__name__] = _implementation
