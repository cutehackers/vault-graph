"""Compatibility import for :mod:`vault_graph.indexing.ingestion.markdown_parser`."""

import hashlib as hashlib
import re as re
import sys
from dataclasses import dataclass as dataclass

from vault_graph.indexing.ingestion import markdown_parser as _implementation
from vault_graph.indexing.ingestion.document_models import ContentBlock as ContentBlock
from vault_graph.indexing.ingestion.document_models import ContentUnit as ContentUnit
from vault_graph.indexing.ingestion.document_models import ExtractionWarning as ExtractionWarning
from vault_graph.indexing.ingestion.document_models import SourceLocator as SourceLocator
from vault_graph.indexing.ingestion.markdown_parser import PARSER_VERSION as PARSER_VERSION
from vault_graph.indexing.ingestion.markdown_parser import MarkdownSection as MarkdownSection
from vault_graph.indexing.ingestion.markdown_parser import _consume_fence as _consume_fence
from vault_graph.indexing.ingestion.markdown_parser import _consume_other_block as _consume_other_block
from vault_graph.indexing.ingestion.markdown_parser import _consume_table as _consume_table
from vault_graph.indexing.ingestion.markdown_parser import _empty_section_block as _empty_section_block
from vault_graph.indexing.ingestion.markdown_parser import _fence as _fence
from vault_graph.indexing.ingestion.markdown_parser import _heading as _heading
from vault_graph.indexing.ingestion.markdown_parser import _heading_block as _heading_block
from vault_graph.indexing.ingestion.markdown_parser import _is_table_start as _is_table_start
from vault_graph.indexing.ingestion.markdown_parser import _lines as _lines
from vault_graph.indexing.ingestion.markdown_parser import _locator_for_lines as _locator_for_lines
from vault_graph.indexing.ingestion.markdown_parser import _make_block as _make_block
from vault_graph.indexing.ingestion.markdown_parser import _MarkdownLine as _MarkdownLine
from vault_graph.indexing.ingestion.markdown_parser import _next_block_occurrence as _next_block_occurrence
from vault_graph.indexing.ingestion.markdown_parser import _stable_key as _stable_key
from vault_graph.indexing.ingestion.markdown_parser import _table_cells as _table_cells
from vault_graph.indexing.ingestion.markdown_parser import _unit_lines as _unit_lines
from vault_graph.indexing.ingestion.markdown_parser import make_anchor as make_anchor
from vault_graph.indexing.ingestion.markdown_parser import parse_markdown_blocks as parse_markdown_blocks
from vault_graph.indexing.ingestion.markdown_parser import (
    parse_markdown_blocks_with_warnings as parse_markdown_blocks_with_warnings,
)
from vault_graph.indexing.ingestion.markdown_parser import parse_sections as parse_sections

sys.modules[__name__] = _implementation
