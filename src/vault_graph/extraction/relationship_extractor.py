"""Compatibility import for :mod:`vault_graph.indexing.extraction.relationship_extractor`."""

import sys
from typing import Protocol as Protocol

from vault_graph.indexing.extraction import relationship_extractor as _implementation
from vault_graph.indexing.extraction.graph_occurrences import EntityOccurrence as EntityOccurrence
from vault_graph.indexing.extraction.graph_occurrences import RelationshipOccurrence as RelationshipOccurrence
from vault_graph.indexing.extraction.graph_occurrences import entity_occurrence_key as entity_occurrence_key
from vault_graph.indexing.extraction.graph_source_store import GraphExtractionContext as GraphExtractionContext
from vault_graph.indexing.extraction.relationship_extractor import (
    MENTION_METHOD_CONFIDENCE as MENTION_METHOD_CONFIDENCE,
)
from vault_graph.indexing.extraction.relationship_extractor import (
    RELATIONSHIP_METHOD_RULES as RELATIONSHIP_METHOD_RULES,
)
from vault_graph.indexing.extraction.relationship_extractor import (
    DeterministicRelationshipExtractor as DeterministicRelationshipExtractor,
)
from vault_graph.indexing.extraction.relationship_extractor import RelationshipExtractor as RelationshipExtractor
from vault_graph.indexing.extraction.relationship_extractor import _dedupe_relationships as _dedupe_relationships
from vault_graph.indexing.extraction.relationship_extractor import _document_entity as _document_entity
from vault_graph.indexing.extraction.relationship_extractor import _excerpt as _excerpt
from vault_graph.indexing.extraction.relationship_extractor import _mention_relationships as _mention_relationships
from vault_graph.indexing.extraction.relationship_extractor import _relationship as _relationship
from vault_graph.indexing.extraction.relationship_extractor import _typed_relationships as _typed_relationships
from vault_graph.indexing.ingestion.document_normalizer import ChunkSnapshot as ChunkSnapshot
from vault_graph.indexing.ingestion.document_normalizer import DocumentSnapshot as DocumentSnapshot
from vault_graph.operation.scope.vault_catalog import QueryScope as QueryScope
from vault_graph.retrieval.graph.graph_contracts import GraphExtractionSpec as GraphExtractionSpec

sys.modules[__name__] = _implementation
