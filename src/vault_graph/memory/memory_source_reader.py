"""Compatibility import for :mod:`vault_graph.context.memory.memory_source_reader`."""

import sys
from dataclasses import dataclass as dataclass

from vault_graph.context.memory import memory_source_reader as _implementation
from vault_graph.context.memory.memory_models import MemoryDocumentResourceKind as MemoryDocumentResourceKind
from vault_graph.context.memory.memory_models import MemoryEvidenceRef as MemoryEvidenceRef
from vault_graph.context.memory.memory_models import MemoryWarning as MemoryWarning
from vault_graph.context.memory.memory_source_reader import MemoryDocumentRead as MemoryDocumentRead
from vault_graph.context.memory.memory_source_reader import MemoryHeadingRef as MemoryHeadingRef
from vault_graph.context.memory.memory_source_reader import MemorySourceReader as MemorySourceReader
from vault_graph.context.memory.memory_source_reader import _body_excerpt as _body_excerpt
from vault_graph.context.memory.memory_source_reader import _is_decision as _is_decision
from vault_graph.context.memory.memory_source_reader import _is_issue as _is_issue
from vault_graph.context.memory.memory_source_reader import _is_source as _is_source
from vault_graph.context.memory.memory_source_reader import (
    _memory_evidence_from_metadata as _memory_evidence_from_metadata,
)
from vault_graph.context.memory.memory_source_reader import _warning as _warning
from vault_graph.context.memory.memory_source_reader import (
    document_resource_kinds_for_document as document_resource_kinds_for_document,
)
from vault_graph.errors import MemoryProjectionError as MemoryProjectionError
from vault_graph.indexing.ingestion.document_normalizer import DocumentSnapshot as DocumentSnapshot
from vault_graph.operation.scope.vault_catalog import QueryScope as QueryScope
from vault_graph.storage.interfaces.metadata_store import EvidenceReference as EvidenceReference
from vault_graph.storage.interfaces.metadata_store import MetadataStore as MetadataStore

sys.modules[__name__] = _implementation
