"""Compatibility import for :mod:`vault_graph.interface.mcp.mcp_memory_serialization`."""

import sys
from typing import TYPE_CHECKING as TYPE_CHECKING
from typing import Protocol as Protocol

from vault_graph.context.memory.memory_models import MemoryBackendRevision as MemoryBackendRevision
from vault_graph.context.memory.memory_models import MemoryEvidenceRef as MemoryEvidenceRef
from vault_graph.context.memory.memory_models import MemoryItem as MemoryItem
from vault_graph.context.memory.memory_models import MemoryWarning as MemoryWarning
from vault_graph.context.memory.memory_models import OpenQuestionsProjection as OpenQuestionsProjection
from vault_graph.context.memory.memory_models import OpenQuestionsVault as OpenQuestionsVault
from vault_graph.context.memory.memory_models import ProjectMemoryProjection as ProjectMemoryProjection
from vault_graph.context.memory.memory_models import ProjectMemoryVault as ProjectMemoryVault
from vault_graph.context.memory.timeline_memory import RecentChangesProjection as RecentChangesProjection
from vault_graph.context.memory.timeline_memory import TimelineEvidenceRef as TimelineEvidenceRef
from vault_graph.context.memory.timeline_memory import TimelineItem as TimelineItem
from vault_graph.context.memory.timeline_memory import TimelineVault as TimelineVault
from vault_graph.interface.mcp import mcp_memory_serialization as _implementation
from vault_graph.interface.mcp.mcp_errors import McpErrorPayload as McpErrorPayload
from vault_graph.interface.mcp.mcp_memory_serialization import RuntimeCacheSnapshot as RuntimeCacheSnapshot
from vault_graph.interface.mcp.mcp_memory_serialization import _backend_readiness_to_dict as _backend_readiness_to_dict
from vault_graph.interface.mcp.mcp_memory_serialization import _backend_revision_to_dict as _backend_revision_to_dict
from vault_graph.interface.mcp.mcp_memory_serialization import _evidence_to_dict as _evidence_to_dict
from vault_graph.interface.mcp.mcp_memory_serialization import _items_for_projection as _items_for_projection
from vault_graph.interface.mcp.mcp_memory_serialization import _memory_item_to_dict as _memory_item_to_dict
from vault_graph.interface.mcp.mcp_memory_serialization import (
    _open_questions_vault_to_dict as _open_questions_vault_to_dict,
)
from vault_graph.interface.mcp.mcp_memory_serialization import _project_vault_to_dict as _project_vault_to_dict
from vault_graph.interface.mcp.mcp_memory_serialization import _runtime_cache_record as _runtime_cache_record
from vault_graph.interface.mcp.mcp_memory_serialization import _runtime_cache_to_dict as _runtime_cache_to_dict
from vault_graph.interface.mcp.mcp_memory_serialization import _scale_up_adapter_to_dict as _scale_up_adapter_to_dict
from vault_graph.interface.mcp.mcp_memory_serialization import _timeline_evidence_to_dict as _timeline_evidence_to_dict
from vault_graph.interface.mcp.mcp_memory_serialization import _timeline_item_to_dict as _timeline_item_to_dict
from vault_graph.interface.mcp.mcp_memory_serialization import _timeline_vault_to_dict as _timeline_vault_to_dict
from vault_graph.interface.mcp.mcp_memory_serialization import _unique_links as _unique_links
from vault_graph.interface.mcp.mcp_memory_serialization import (
    health_explorer_report_to_payload as health_explorer_report_to_payload,
)
from vault_graph.interface.mcp.mcp_memory_serialization import memory_warning_to_dict as memory_warning_to_dict
from vault_graph.interface.mcp.mcp_memory_serialization import (
    memory_warning_to_mcp_error as memory_warning_to_mcp_error,
)
from vault_graph.interface.mcp.mcp_memory_serialization import (
    open_questions_projection_to_payload as open_questions_projection_to_payload,
)
from vault_graph.interface.mcp.mcp_memory_serialization import (
    project_memory_projection_to_payload as project_memory_projection_to_payload,
)
from vault_graph.interface.mcp.mcp_memory_serialization import query_scope_to_dict as query_scope_to_dict
from vault_graph.interface.mcp.mcp_memory_serialization import (
    recent_changes_projection_to_payload as recent_changes_projection_to_payload,
)
from vault_graph.interface.mcp.mcp_memory_serialization import (
    resource_links_for_memory_projection as resource_links_for_memory_projection,
)
from vault_graph.interface.mcp.mcp_memory_serialization import (
    resource_links_for_recent_changes as resource_links_for_recent_changes,
)
from vault_graph.interface.mcp.mcp_memory_serialization import (
    runtime_cache_records_for_mcp as runtime_cache_records_for_mcp,
)
from vault_graph.interface.mcp.mcp_memory_serialization import timeline_warnings as timeline_warnings
from vault_graph.interface.mcp.mcp_uri import encode_resource_segment as encode_resource_segment
from vault_graph.operation.diagnostics.health_explorer import BackendReadinessRecord as BackendReadinessRecord
from vault_graph.operation.diagnostics.health_explorer import HealthExplorerReport as HealthExplorerReport
from vault_graph.operation.diagnostics.health_explorer import McpRuntimeCacheRecord as McpRuntimeCacheRecord
from vault_graph.operation.diagnostics.health_explorer import ReadinessStatus as ReadinessStatus
from vault_graph.operation.diagnostics.health_explorer import ScaleUpAdapterReadiness as ScaleUpAdapterReadiness
from vault_graph.operation.scope.vault_catalog import QueryScope as QueryScope

sys.modules[__name__] = _implementation
