"""Compatibility import for :mod:`vault_graph.context.memory.issue_memory`."""

import sys
from collections.abc import Callable as Callable
from datetime import datetime as datetime

from vault_graph.context.memory import issue_memory as _implementation
from vault_graph.context.memory.issue_memory import ACTIVE_STATUSES as ACTIVE_STATUSES
from vault_graph.context.memory.issue_memory import EXCLUDED_STATUSES as EXCLUDED_STATUSES
from vault_graph.context.memory.issue_memory import ISSUE_TYPES as ISSUE_TYPES
from vault_graph.context.memory.issue_memory import OPEN_HEADING_TERMS as OPEN_HEADING_TERMS
from vault_graph.context.memory.issue_memory import IssueMemoryService as IssueMemoryService
from vault_graph.context.memory.issue_memory import _candidate_read_limit as _candidate_read_limit
from vault_graph.context.memory.issue_memory import _document_issue_signals as _document_issue_signals
from vault_graph.context.memory.issue_memory import _freshness_from_status as _freshness_from_status
from vault_graph.context.memory.issue_memory import _frontmatter_text as _frontmatter_text
from vault_graph.context.memory.issue_memory import _frontmatter_value as _frontmatter_value
from vault_graph.context.memory.issue_memory import _is_canonical_issue_document as _is_canonical_issue_document
from vault_graph.context.memory.issue_memory import _is_issue_candidate_document as _is_issue_candidate_document
from vault_graph.context.memory.issue_memory import _matching_heading_chunk_ids as _matching_heading_chunk_ids
from vault_graph.context.memory.issue_memory import _scope_key as _scope_key
from vault_graph.context.memory.issue_memory import _status as _status
from vault_graph.context.memory.issue_memory import _store_revisions_from_documents as _store_revisions_from_documents
from vault_graph.context.memory.issue_memory import _title as _title
from vault_graph.context.memory.issue_memory import _validate_limit as _validate_limit
from vault_graph.context.memory.issue_memory import _warning as _warning
from vault_graph.context.memory.memory_models import MemoryBackendRevision as MemoryBackendRevision
from vault_graph.context.memory.memory_models import MemoryClaimStatus as MemoryClaimStatus
from vault_graph.context.memory.memory_models import MemoryFreshness as MemoryFreshness
from vault_graph.context.memory.memory_models import MemoryItem as MemoryItem
from vault_graph.context.memory.memory_models import MemoryWarning as MemoryWarning
from vault_graph.context.memory.memory_models import OpenQuestionsProjection as OpenQuestionsProjection
from vault_graph.context.memory.memory_models import OpenQuestionsVault as OpenQuestionsVault
from vault_graph.context.memory.memory_models import stable_memory_item_id as stable_memory_item_id
from vault_graph.context.memory.memory_request_context import MemoryRequestContext as MemoryRequestContext
from vault_graph.context.memory.memory_request_context import MemoryStatusService as MemoryStatusService
from vault_graph.context.memory.memory_request_context import (
    build_memory_request_context as build_memory_request_context,
)
from vault_graph.context.memory.memory_source_reader import MemoryDocumentRead as MemoryDocumentRead
from vault_graph.context.memory.memory_source_reader import MemorySourceReader as MemorySourceReader
from vault_graph.context.memory.memory_source_reader import (
    document_resource_kinds_for_document as document_resource_kinds_for_document,
)
from vault_graph.errors import MemoryProjectionError as MemoryProjectionError
from vault_graph.indexing.ingestion.document_normalizer import DocumentSnapshot as DocumentSnapshot
from vault_graph.operation.scope.vault_catalog import QueryScope as QueryScope
from vault_graph.operation.scope.vault_catalog import VaultCatalog as VaultCatalog

sys.modules[__name__] = _implementation
