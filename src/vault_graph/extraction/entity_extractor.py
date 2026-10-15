"""Compatibility import for :mod:`vault_graph.indexing.extraction.entity_extractor`."""

import re as re
import sys
from dataclasses import dataclass as dataclass
from pathlib import PurePosixPath as PurePosixPath
from typing import Protocol as Protocol

from vault_graph.indexing.extraction import entity_extractor as _implementation
from vault_graph.indexing.extraction.entity_extractor import (
    FRONTMATTER_RELATIONSHIP_METHODS as FRONTMATTER_RELATIONSHIP_METHODS,
)
from vault_graph.indexing.extraction.entity_extractor import GENERIC_HEADINGS as GENERIC_HEADINGS
from vault_graph.indexing.extraction.entity_extractor import MARKDOWN_LINK_PATTERN as MARKDOWN_LINK_PATTERN
from vault_graph.indexing.extraction.entity_extractor import WIKI_LINK_PATTERN as WIKI_LINK_PATTERN
from vault_graph.indexing.extraction.entity_extractor import (
    DeterministicEntityExtractor as DeterministicEntityExtractor,
)
from vault_graph.indexing.extraction.entity_extractor import EntityExtractor as EntityExtractor
from vault_graph.indexing.extraction.entity_extractor import ParsedLocalLink as ParsedLocalLink
from vault_graph.indexing.extraction.entity_extractor import _aliases as _aliases
from vault_graph.indexing.extraction.entity_extractor import _concept_entity as _concept_entity
from vault_graph.indexing.extraction.entity_extractor import _dedupe_occurrences as _dedupe_occurrences
from vault_graph.indexing.extraction.entity_extractor import _document_entity as _document_entity
from vault_graph.indexing.extraction.entity_extractor import _document_entity_type as _document_entity_type
from vault_graph.indexing.extraction.entity_extractor import _document_name as _document_name
from vault_graph.indexing.extraction.entity_extractor import _excerpt as _excerpt
from vault_graph.indexing.extraction.entity_extractor import _frontmatter_tags as _frontmatter_tags
from vault_graph.indexing.extraction.entity_extractor import (
    _frontmatter_target_entities as _frontmatter_target_entities,
)
from vault_graph.indexing.extraction.entity_extractor import _frontmatter_values as _frontmatter_values
from vault_graph.indexing.extraction.entity_extractor import _generic_heading as _generic_heading
from vault_graph.indexing.extraction.entity_extractor import _heading_entity as _heading_entity
from vault_graph.indexing.extraction.entity_extractor import _link_entities as _link_entities
from vault_graph.indexing.extraction.entity_extractor import _link_is_external_or_anchor as _link_is_external_or_anchor
from vault_graph.indexing.extraction.entity_extractor import _local_links as _local_links
from vault_graph.indexing.extraction.entity_extractor import _scalar_frontmatter as _scalar_frontmatter
from vault_graph.indexing.extraction.entity_extractor import _tag_entities as _tag_entities
from vault_graph.indexing.extraction.graph_occurrences import EntityOccurrence as EntityOccurrence
from vault_graph.indexing.extraction.graph_occurrences import entity_occurrence_key as entity_occurrence_key
from vault_graph.indexing.extraction.graph_source_store import GraphExtractionContext as GraphExtractionContext
from vault_graph.indexing.ingestion.document_normalizer import ChunkSnapshot as ChunkSnapshot
from vault_graph.indexing.ingestion.document_normalizer import DocumentSnapshot as DocumentSnapshot
from vault_graph.operation.scope.vault_catalog import QueryScope as QueryScope
from vault_graph.retrieval.graph.graph_contracts import GraphExtractionSpec as GraphExtractionSpec
from vault_graph.retrieval.graph.graph_identity import normalize_entity_name as normalize_entity_name

sys.modules[__name__] = _implementation
