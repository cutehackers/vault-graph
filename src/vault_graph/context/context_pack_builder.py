"""Compatibility import for :mod:`vault_graph.context.pack.context_pack_builder`."""

import hashlib as hashlib
import sys
from collections.abc import Callable as Callable
from dataclasses import dataclass as dataclass
from dataclasses import replace as replace
from datetime import UTC as UTC
from datetime import datetime as datetime
from pathlib import PurePosixPath as PurePosixPath
from typing import Protocol as Protocol
from typing import cast as cast

from vault_graph.context.pack import context_pack_builder as _implementation
from vault_graph.context.pack.context_evidence_selection import ContextEvidenceSelection as ContextEvidenceSelection
from vault_graph.context.pack.context_pack import CONTEXT_PACK_SCHEMA_VERSION as CONTEXT_PACK_SCHEMA_VERSION
from vault_graph.context.pack.context_pack import DEFAULT_CONTEXT_RETRIEVAL_LIMIT as DEFAULT_CONTEXT_RETRIEVAL_LIMIT
from vault_graph.context.pack.context_pack import DEFAULT_RETRIEVAL_POLICY_VERSION as DEFAULT_RETRIEVAL_POLICY_VERSION
from vault_graph.context.pack.context_pack import ContextEvidence as ContextEvidence
from vault_graph.context.pack.context_pack import ContextEvidenceRef as ContextEvidenceRef
from vault_graph.context.pack.context_pack import ContextPack as ContextPack
from vault_graph.context.pack.context_pack import ContextPackActualScope as ContextPackActualScope
from vault_graph.context.pack.context_pack import ContextPackBackend as ContextPackBackend
from vault_graph.context.pack.context_pack import ContextPackBackendUse as ContextPackBackendUse
from vault_graph.context.pack.context_pack import ContextPackItem as ContextPackItem
from vault_graph.context.pack.context_pack import ContextPackItemType as ContextPackItemType
from vault_graph.context.pack.context_pack import ContextPackRequest as ContextPackRequest
from vault_graph.context.pack.context_pack import ContextPackSignal as ContextPackSignal
from vault_graph.context.pack.context_pack import ContextPackStoreRevision as ContextPackStoreRevision
from vault_graph.context.pack.context_pack import ContextPackStoreRevisionKind as ContextPackStoreRevisionKind
from vault_graph.context.pack.context_pack import ContextPackVault as ContextPackVault
from vault_graph.context.pack.context_pack import ContextPackVaultRevision as ContextPackVaultRevision
from vault_graph.context.pack.context_pack import ContextPackWarning as ContextPackWarning
from vault_graph.context.pack.context_pack import context_scope_from_query_scopes as context_scope_from_query_scopes
from vault_graph.context.pack.context_pack_builder import ContextEvidenceResolver as ContextEvidenceResolver
from vault_graph.context.pack.context_pack_builder import ContextPackBuilder as ContextPackBuilder
from vault_graph.context.pack.context_pack_builder import ContextRetrievalService as ContextRetrievalService
from vault_graph.context.pack.context_pack_builder import (
    MetadataContextEvidenceResolver as MetadataContextEvidenceResolver,
)
from vault_graph.context.pack.context_pack_builder import ResolvedContextEvidence as ResolvedContextEvidence
from vault_graph.context.pack.context_pack_builder import SearchContextPackBuilder as SearchContextPackBuilder
from vault_graph.context.pack.context_pack_builder import (
    _actual_scope_inside_requested as _actual_scope_inside_requested,
)
from vault_graph.context.pack.context_pack_builder import _affected_vault_ids as _affected_vault_ids
from vault_graph.context.pack.context_pack_builder import _backend as _backend
from vault_graph.context.pack.context_pack_builder import _budget_warnings as _budget_warnings
from vault_graph.context.pack.context_pack_builder import (
    _content_scope_inside_requested as _content_scope_inside_requested,
)
from vault_graph.context.pack.context_pack_builder import (
    _context_evidence_from_resolved as _context_evidence_from_resolved,
)
from vault_graph.context.pack.context_pack_builder import _context_item_from_planned as _context_item_from_planned
from vault_graph.context.pack.context_pack_builder import _dedupe_warnings as _dedupe_warnings
from vault_graph.context.pack.context_pack_builder import _first_signal_backend as _first_signal_backend
from vault_graph.context.pack.context_pack_builder import _has_revision as _has_revision
from vault_graph.context.pack.context_pack_builder import _is_valid_evidence_path as _is_valid_evidence_path
from vault_graph.context.pack.context_pack_builder import _item_id as _item_id
from vault_graph.context.pack.context_pack_builder import _item_type as _item_type
from vault_graph.context.pack.context_pack_builder import _items_by_type as _items_by_type
from vault_graph.context.pack.context_pack_builder import (
    _path_is_inside_content_scopes as _path_is_inside_content_scopes,
)
from vault_graph.context.pack.context_pack_builder import _planned_item as _planned_item
from vault_graph.context.pack.context_pack_builder import _planned_item_sort_key as _planned_item_sort_key
from vault_graph.context.pack.context_pack_builder import _PlannedItem as _PlannedItem
from vault_graph.context.pack.context_pack_builder import _resolve_once as _resolve_once
from vault_graph.context.pack.context_pack_builder import _retrieval_limit as _retrieval_limit
from vault_graph.context.pack.context_pack_builder import _retrieval_reasons as _retrieval_reasons
from vault_graph.context.pack.context_pack_builder import _store_revisions as _store_revisions
from vault_graph.context.pack.context_pack_builder import _truncate_excerpt as _truncate_excerpt
from vault_graph.context.pack.context_pack_builder import _validate_response as _validate_response
from vault_graph.context.pack.context_pack_builder import _vault_revisions as _vault_revisions
from vault_graph.context.pack.context_pack_builder import _vaults as _vaults
from vault_graph.context.pack.context_pack_serialization import with_computed_pack_id as with_computed_pack_id
from vault_graph.context.pack.context_pack_warnings import budget_warning as budget_warning
from vault_graph.context.pack.context_pack_warnings import builder_warning as builder_warning
from vault_graph.context.pack.context_pack_warnings import (
    context_warning_from_retrieval as context_warning_from_retrieval,
)
from vault_graph.context.pack.context_pack_warnings import context_warning_from_search as context_warning_from_search
from vault_graph.context.pack.context_pack_warnings import evidence_ref_from_metadata as evidence_ref_from_metadata
from vault_graph.errors import ContextPackError as ContextPackError
from vault_graph.operation.scope.vault_catalog import QueryScope as QueryScope
from vault_graph.operation.scope.vault_catalog import VaultCatalog as VaultCatalog
from vault_graph.retrieval.search.retrieval_result import RetrievalResult as RetrievalResult
from vault_graph.retrieval.search.search_response import SearchOutputFormat as SearchOutputFormat
from vault_graph.retrieval.search.search_response import SearchResponse as SearchResponse
from vault_graph.storage.interfaces.metadata_store import MetadataStore as MetadataStore

sys.modules[__name__] = _implementation
