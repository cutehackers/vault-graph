"""Compatibility import for :mod:`vault_graph.indexing.extraction.vault_graph_document_adapter`."""

import hashlib as hashlib
import json as json
import os as os
import stat as stat
import sys
import tempfile as tempfile
from dataclasses import asdict as asdict
from dataclasses import dataclass as dataclass
from dataclasses import replace as replace
from pathlib import Path as Path
from typing import Any as Any
from typing import cast as cast

from graph_document import Document as Document
from graph_document import DocumentFeatures as DocumentFeatures
from graph_document import DocumentGraphSnapshot as DocumentGraphSnapshot
from graph_document import EntityFact as EntityFact
from graph_document import EntityKey as EntityKey
from graph_document import EvidenceLocation as EvidenceLocation
from graph_document import ExtractedDocument as ExtractedDocument
from graph_document import ExtractionProfile as ExtractionProfile
from graph_document import GraphDocument as GraphDocument
from graph_document import GraphLimits as GraphLimits
from graph_document import LocatedValue as LocatedValue
from graph_document import ReadLimits as ReadLimits
from graph_document import RelationFact as RelationFact
from graph_document import UnknownCollectionError as UnknownCollectionError
from graph_document import extraction_digest as extraction_digest

from vault_graph.indexing.extraction import vault_graph_document_adapter as _implementation
from vault_graph.indexing.extraction.entity_extractor import (
    DeterministicEntityExtractor as DeterministicEntityExtractor,
)
from vault_graph.indexing.extraction.graph_occurrences import EntityOccurrence as EntityOccurrence
from vault_graph.indexing.extraction.graph_occurrences import RelationshipOccurrence as RelationshipOccurrence
from vault_graph.indexing.extraction.graph_occurrences import entity_occurrence_key as entity_occurrence_key
from vault_graph.indexing.extraction.graph_source_store import GraphExtractionContext as GraphExtractionContext
from vault_graph.indexing.extraction.graph_source_store import MetadataGraphSourceStore as MetadataGraphSourceStore
from vault_graph.indexing.extraction.relationship_extractor import (
    DeterministicRelationshipExtractor as DeterministicRelationshipExtractor,
)
from vault_graph.indexing.extraction.vault_graph_document_adapter import RestoredGraph as RestoredGraph
from vault_graph.indexing.extraction.vault_graph_document_adapter import VaultDocumentBatch as VaultDocumentBatch
from vault_graph.indexing.extraction.vault_graph_document_adapter import (
    VaultDocumentContribution as VaultDocumentContribution,
)
from vault_graph.indexing.extraction.vault_graph_document_adapter import (
    VaultDocumentMappingError as VaultDocumentMappingError,
)
from vault_graph.indexing.extraction.vault_graph_document_adapter import (
    VaultGraphDocumentAdapter as VaultGraphDocumentAdapter,
)
from vault_graph.indexing.extraction.vault_graph_document_adapter import (
    VaultProjectionRequest as VaultProjectionRequest,
)
from vault_graph.indexing.extraction.vault_graph_document_adapter import VaultSyncResult as VaultSyncResult
from vault_graph.indexing.extraction.vault_graph_document_adapter import _canonical as _canonical
from vault_graph.indexing.extraction.vault_graph_document_adapter import _digest as _digest
from vault_graph.indexing.extraction.vault_graph_document_adapter import _encoded as _encoded
from vault_graph.indexing.extraction.vault_graph_document_adapter import _entity_key as _entity_key
from vault_graph.indexing.extraction.vault_graph_document_adapter import _LegacyV1Extractor as _LegacyV1Extractor
from vault_graph.indexing.ingestion.document_normalizer import ChunkSnapshot as ChunkSnapshot
from vault_graph.indexing.ingestion.document_normalizer import DocumentSnapshot as DocumentSnapshot
from vault_graph.operation.scope.vault_catalog import QueryScope as QueryScope
from vault_graph.retrieval.graph.graph_contracts import GraphEvidenceRef as GraphEvidenceRef
from vault_graph.retrieval.graph.graph_contracts import GraphExtractionSpec as GraphExtractionSpec
from vault_graph.retrieval.graph.graph_contracts import current_graph_extraction_spec as current_graph_extraction_spec
from vault_graph.retrieval.graph.graph_identity import stable_entity_id as stable_entity_id
from vault_graph.retrieval.graph.graph_identity import stable_evidence_ref_id as stable_evidence_ref_id
from vault_graph.retrieval.graph.graph_identity import stable_relationship_id as stable_relationship_id
from vault_graph.retrieval.graph.projection.graph_projection import GraphProjectionDirection as GraphProjectionDirection
from vault_graph.retrieval.graph.projection.graph_projection import GraphProjectionEdge as GraphProjectionEdge
from vault_graph.retrieval.graph.projection.graph_projection import GraphProjectionInput as GraphProjectionInput
from vault_graph.retrieval.graph.projection.graph_projection import GraphProjectionNode as GraphProjectionNode
from vault_graph.storage.interfaces.metadata_store import MetadataStore as MetadataStore

sys.modules[__name__] = _implementation
