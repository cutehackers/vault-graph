"""Compatibility import for :mod:`vault_graph.indexing.ingestion.document_readers`."""

import hashlib as hashlib
import sys
from collections.abc import Iterable as Iterable
from collections.abc import Mapping as Mapping
from dataclasses import dataclass as dataclass
from types import MappingProxyType as MappingProxyType
from typing import Protocol as Protocol
from typing import runtime_checkable as runtime_checkable

from vault_graph.indexing.ingestion import document_readers as _implementation
from vault_graph.indexing.ingestion.document_models import ExtractedDocument as ExtractedDocument
from vault_graph.indexing.ingestion.document_models import SourceDocument as SourceDocument
from vault_graph.indexing.ingestion.document_readers import DocumentReader as DocumentReader
from vault_graph.indexing.ingestion.document_readers import DocumentReaderError as DocumentReaderError
from vault_graph.indexing.ingestion.document_readers import DocumentReaderRegistry as DocumentReaderRegistry
from vault_graph.indexing.ingestion.document_readers import DuplicateDocumentReaderError as DuplicateDocumentReaderError
from vault_graph.indexing.ingestion.document_readers import MarkdownDocumentReader as MarkdownDocumentReader
from vault_graph.indexing.ingestion.document_readers import (
    UnsupportedDocumentFormatError as UnsupportedDocumentFormatError,
)
from vault_graph.indexing.ingestion.document_readers import _normalize_suffix as _normalize_suffix
from vault_graph.indexing.ingestion.document_readers import _reader_suffixes as _reader_suffixes
from vault_graph.indexing.ingestion.markdown_parser import PARSER_VERSION as PARSER_VERSION
from vault_graph.indexing.ingestion.markdown_parser import (
    parse_markdown_blocks_with_warnings as parse_markdown_blocks_with_warnings,
)
from vault_graph.indexing.ingestion.vault_frontmatter_reader import read_frontmatter as read_frontmatter

sys.modules[__name__] = _implementation
