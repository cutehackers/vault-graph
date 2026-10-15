"""Compatibility import for :mod:`vault_graph.indexing.extraction.graph_occurrences`."""

import sys
from dataclasses import dataclass as dataclass

from vault_graph.errors import GraphExtractionError as GraphExtractionError
from vault_graph.indexing.extraction import graph_occurrences as _implementation
from vault_graph.indexing.extraction.graph_occurrences import EntityOccurrence as EntityOccurrence
from vault_graph.indexing.extraction.graph_occurrences import EntityOccurrenceKey as EntityOccurrenceKey
from vault_graph.indexing.extraction.graph_occurrences import GraphExtractionWarning as GraphExtractionWarning
from vault_graph.indexing.extraction.graph_occurrences import RelationshipOccurrence as RelationshipOccurrence
from vault_graph.indexing.extraction.graph_occurrences import _require_entity_key as _require_entity_key
from vault_graph.indexing.extraction.graph_occurrences import _require_non_empty as _require_non_empty
from vault_graph.indexing.extraction.graph_occurrences import entity_occurrence_key as entity_occurrence_key

sys.modules[__name__] = _implementation
