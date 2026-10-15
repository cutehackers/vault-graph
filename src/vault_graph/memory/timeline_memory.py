"""Compatibility import for :mod:`vault_graph.context.memory.timeline_memory`."""

import hashlib as hashlib
import json as json
import sys
from collections.abc import Callable as Callable
from dataclasses import dataclass as dataclass
from datetime import UTC as UTC
from datetime import datetime as datetime
from typing import TYPE_CHECKING as TYPE_CHECKING
from typing import Literal as Literal

from vault_graph.context.memory import timeline_memory as _implementation
from vault_graph.context.memory.memory_models import MemoryBackendRevision as MemoryBackendRevision
from vault_graph.context.memory.memory_models import MemoryWarning as MemoryWarning
from vault_graph.context.memory.memory_models import MemoryWarningSeverity as MemoryWarningSeverity
from vault_graph.context.memory.memory_request_context import MemoryStatusService as MemoryStatusService
from vault_graph.context.memory.timeline_memory import TIMELINE_FRESHNESS as TIMELINE_FRESHNESS
from vault_graph.context.memory.timeline_memory import TIMELINE_ORIGINS as TIMELINE_ORIGINS
from vault_graph.context.memory.timeline_memory import TIMELINE_SOURCE_KINDS as TIMELINE_SOURCE_KINDS
from vault_graph.context.memory.timeline_memory import RecentChangesProjection as RecentChangesProjection
from vault_graph.context.memory.timeline_memory import TimelineEvidenceRef as TimelineEvidenceRef
from vault_graph.context.memory.timeline_memory import TimelineFreshness as TimelineFreshness
from vault_graph.context.memory.timeline_memory import TimelineItem as TimelineItem
from vault_graph.context.memory.timeline_memory import TimelineMemoryService as TimelineMemoryService
from vault_graph.context.memory.timeline_memory import TimelineOrigin as TimelineOrigin
from vault_graph.context.memory.timeline_memory import TimelineSourceKind as TimelineSourceKind
from vault_graph.context.memory.timeline_memory import TimelineVault as TimelineVault
from vault_graph.context.memory.timeline_memory import _document_item as _document_item
from vault_graph.context.memory.timeline_memory import _filter_and_limit_items as _filter_and_limit_items
from vault_graph.context.memory.timeline_memory import _freshness_for_report as _freshness_for_report
from vault_graph.context.memory.timeline_memory import _graph_items as _graph_items
from vault_graph.context.memory.timeline_memory import _item_order as _item_order
from vault_graph.context.memory.timeline_memory import _metadata_status_item as _metadata_status_item
from vault_graph.context.memory.timeline_memory import _missing_timestamp_warning as _missing_timestamp_warning
from vault_graph.context.memory.timeline_memory import _require_non_empty_string as _require_non_empty_string
from vault_graph.context.memory.timeline_memory import _require_one_of as _require_one_of
from vault_graph.context.memory.timeline_memory import _require_tuple as _require_tuple
from vault_graph.context.memory.timeline_memory import _reverse_time_key as _reverse_time_key
from vault_graph.context.memory.timeline_memory import _scope_key as _scope_key
from vault_graph.context.memory.timeline_memory import _sort_key as _sort_key
from vault_graph.context.memory.timeline_memory import _status_item as _status_item
from vault_graph.context.memory.timeline_memory import _utc_now as _utc_now
from vault_graph.context.memory.timeline_memory import _vault_revisions as _vault_revisions
from vault_graph.context.memory.timeline_memory import _vector_items as _vector_items
from vault_graph.context.memory.timeline_memory import _warning as _warning
from vault_graph.context.memory.timeline_memory import parse_timeline_since as parse_timeline_since
from vault_graph.context.memory.timeline_memory import stable_timeline_item_id as stable_timeline_item_id
from vault_graph.errors import MemoryProjectionError as MemoryProjectionError
from vault_graph.errors import MetadataStoreError as MetadataStoreError
from vault_graph.indexing.ingestion.document_normalizer import DocumentSnapshot as DocumentSnapshot
from vault_graph.operation.scope.catalog_query_scopes import actual_query_scopes as actual_query_scopes
from vault_graph.operation.scope.vault_catalog import QueryScope as QueryScope
from vault_graph.operation.scope.vault_catalog import VaultCatalog as VaultCatalog
from vault_graph.storage.interfaces.metadata_store import MetadataStore as MetadataStore

sys.modules[__name__] = _implementation
