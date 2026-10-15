"""Compatibility import for :mod:`vault_graph.indexing.ingestion.document_models`."""

import hashlib as hashlib
import json as json
import re as re
import sys
from dataclasses import dataclass as dataclass
from pathlib import Path as Path
from pathlib import PurePosixPath as PurePosixPath
from typing import Literal as Literal

from vault_graph.indexing.ingestion import document_models as _implementation
from vault_graph.indexing.ingestion.document_models import BlockKind as BlockKind
from vault_graph.indexing.ingestion.document_models import ContentBlock as ContentBlock
from vault_graph.indexing.ingestion.document_models import ContentUnit as ContentUnit
from vault_graph.indexing.ingestion.document_models import Coordinate as Coordinate
from vault_graph.indexing.ingestion.document_models import DocumentModelError as DocumentModelError
from vault_graph.indexing.ingestion.document_models import ExtractedDocument as ExtractedDocument
from vault_graph.indexing.ingestion.document_models import ExtractionWarning as ExtractionWarning
from vault_graph.indexing.ingestion.document_models import OffsetUnit as OffsetUnit
from vault_graph.indexing.ingestion.document_models import SourceDocument as SourceDocument
from vault_graph.indexing.ingestion.document_models import SourceLocator as SourceLocator
from vault_graph.indexing.ingestion.document_models import WarningSeverity as WarningSeverity
from vault_graph.indexing.ingestion.document_models import _coordinate_sort_key as _coordinate_sort_key
from vault_graph.indexing.ingestion.document_models import _normalize_coordinates as _normalize_coordinates
from vault_graph.indexing.ingestion.document_models import _normalize_offset_unit as _normalize_offset_unit
from vault_graph.indexing.ingestion.document_models import _normalize_scheme as _normalize_scheme
from vault_graph.indexing.ingestion.document_models import _normalize_section_path as _normalize_section_path
from vault_graph.indexing.ingestion.document_models import _normalize_source_path as _normalize_source_path
from vault_graph.indexing.ingestion.document_models import _normalize_suffix as _normalize_suffix
from vault_graph.indexing.ingestion.document_models import _require_non_empty_string as _require_non_empty_string
from vault_graph.indexing.ingestion.document_models import _validate_offsets as _validate_offsets
from vault_graph.indexing.ingestion.vault_frontmatter_reader import FrontmatterProjection as FrontmatterProjection

sys.modules[__name__] = _implementation
