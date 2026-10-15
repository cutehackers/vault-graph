"""Compatibility import for :mod:`vault_graph.context.memory.project_memory`."""

import sys
from collections.abc import Callable as Callable
from datetime import datetime as datetime

from vault_graph.context.memory import project_memory as _implementation
from vault_graph.context.memory.decision_memory import DecisionMemoryService as DecisionMemoryService
from vault_graph.context.memory.issue_memory import IssueMemoryService as IssueMemoryService
from vault_graph.context.memory.memory_models import MemoryBackendRevision as MemoryBackendRevision
from vault_graph.context.memory.memory_models import MemoryClaimStatus as MemoryClaimStatus
from vault_graph.context.memory.memory_models import MemoryFreshness as MemoryFreshness
from vault_graph.context.memory.memory_models import MemoryItem as MemoryItem
from vault_graph.context.memory.memory_models import MemoryItemKind as MemoryItemKind
from vault_graph.context.memory.memory_models import MemoryWarning as MemoryWarning
from vault_graph.context.memory.memory_models import ProjectMemoryProjection as ProjectMemoryProjection
from vault_graph.context.memory.memory_models import ProjectMemoryVault as ProjectMemoryVault
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
from vault_graph.context.memory.project_memory import CONSTRAINT_PATH_TERMS as CONSTRAINT_PATH_TERMS
from vault_graph.context.memory.project_memory import CONSTRAINT_TERMS as CONSTRAINT_TERMS
from vault_graph.context.memory.project_memory import CURRENT_STATE_PATH_TERMS as CURRENT_STATE_PATH_TERMS
from vault_graph.context.memory.project_memory import CURRENT_STATE_TYPES as CURRENT_STATE_TYPES
from vault_graph.context.memory.project_memory import PRIORITY_FRONTMATTER_TERMS as PRIORITY_FRONTMATTER_TERMS
from vault_graph.context.memory.project_memory import PRIORITY_TERMS as PRIORITY_TERMS
from vault_graph.context.memory.project_memory import STALE_PATH_TERMS as STALE_PATH_TERMS
from vault_graph.context.memory.project_memory import STALE_STATUSES as STALE_STATUSES
from vault_graph.context.memory.project_memory import ProjectMemoryService as ProjectMemoryService
from vault_graph.context.memory.project_memory import _candidate_read_limit as _candidate_read_limit
from vault_graph.context.memory.project_memory import _freshness_from_status as _freshness_from_status
from vault_graph.context.memory.project_memory import _frontmatter_text as _frontmatter_text
from vault_graph.context.memory.project_memory import _frontmatter_value as _frontmatter_value
from vault_graph.context.memory.project_memory import _group_name_for_kind as _group_name_for_kind
from vault_graph.context.memory.project_memory import _is_root_readme as _is_root_readme
from vault_graph.context.memory.project_memory import _matching_heading_chunk_ids as _matching_heading_chunk_ids
from vault_graph.context.memory.project_memory import (
    _memory_item_for_project_document as _memory_item_for_project_document,
)
from vault_graph.context.memory.project_memory import _project_matches as _project_matches
from vault_graph.context.memory.project_memory import _project_signals as _project_signals
from vault_graph.context.memory.project_memory import _scope_key as _scope_key
from vault_graph.context.memory.project_memory import _status as _status
from vault_graph.context.memory.project_memory import _store_revisions_from_documents as _store_revisions_from_documents
from vault_graph.context.memory.project_memory import _title as _title
from vault_graph.context.memory.project_memory import _validate_limit as _validate_limit
from vault_graph.context.memory.project_memory import _warning as _warning
from vault_graph.errors import MemoryProjectionError as MemoryProjectionError
from vault_graph.indexing.ingestion.document_normalizer import DocumentSnapshot as DocumentSnapshot
from vault_graph.operation.scope.vault_catalog import QueryScope as QueryScope
from vault_graph.operation.scope.vault_catalog import VaultCatalog as VaultCatalog

sys.modules[__name__] = _implementation
