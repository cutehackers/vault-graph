"""Compatibility import for :mod:`vault_graph.interface.mcp.mcp_resources`."""

import json as json
import sys
from collections.abc import Callable as Callable
from dataclasses import dataclass as dataclass
from typing import TYPE_CHECKING as TYPE_CHECKING
from typing import Literal as Literal
from typing import NoReturn as NoReturn
from typing import Protocol as Protocol

from vault_graph.context.memory.memory_models import MemoryWarning as MemoryWarning
from vault_graph.context.memory.memory_models import ProjectMemoryProjection as ProjectMemoryProjection
from vault_graph.errors import MemoryProjectionError as MemoryProjectionError
from vault_graph.interface.mcp import mcp_resources as _implementation
from vault_graph.interface.mcp.context_pack_resource_cache import ContextPackResourceCache as ContextPackResourceCache
from vault_graph.interface.mcp.mcp_errors import McpErrorPayload as McpErrorPayload
from vault_graph.interface.mcp.mcp_errors import McpProtocolError as McpProtocolError
from vault_graph.interface.mcp.mcp_errors import map_exception_to_mcp_error as map_exception_to_mcp_error
from vault_graph.interface.mcp.mcp_resources import CurrentContextResourceReader as CurrentContextResourceReader
from vault_graph.interface.mcp.mcp_resources import GraphResourceReaderFactory as GraphResourceReaderFactory
from vault_graph.interface.mcp.mcp_resources import LazyGraphResourceReaderFactory as LazyGraphResourceReaderFactory
from vault_graph.interface.mcp.mcp_resources import McpResourceBody as McpResourceBody
from vault_graph.interface.mcp.mcp_resources import McpResourceContentMime as McpResourceContentMime
from vault_graph.interface.mcp.mcp_resources import McpResourceRegistry as McpResourceRegistry
from vault_graph.interface.mcp.mcp_resources import McpResourceRequest as McpResourceRequest
from vault_graph.interface.mcp.mcp_resources import McpResourceServer as McpResourceServer
from vault_graph.interface.mcp.mcp_resources import _domain_error_code as _domain_error_code
from vault_graph.interface.mcp.mcp_resources import _project_memory_warnings as _project_memory_warnings
from vault_graph.interface.mcp.mcp_resources import _project_vault_and_item_warnings as _project_vault_and_item_warnings
from vault_graph.interface.mcp.mcp_resources import _raise_resource_not_available as _raise_resource_not_available
from vault_graph.interface.mcp.mcp_resources import (
    _raise_resource_not_available_for_uri as _raise_resource_not_available_for_uri,
)
from vault_graph.interface.mcp.mcp_resources import _raise_resource_not_found as _raise_resource_not_found
from vault_graph.interface.mcp.mcp_resources import _required_value as _required_value
from vault_graph.interface.mcp.mcp_resources import _resource_not_available_error as _resource_not_available_error
from vault_graph.interface.mcp.mcp_resources import (
    _UnavailableMetadataResourceReader as _UnavailableMetadataResourceReader,
)
from vault_graph.interface.mcp.mcp_resources import _warning_to_dict as _warning_to_dict
from vault_graph.interface.mcp.mcp_resources import register_mcp_resources as register_mcp_resources
from vault_graph.interface.mcp.mcp_service_factory import McpServiceFactory as McpServiceFactory
from vault_graph.interface.mcp.mcp_service_factory import McpServices as McpServices
from vault_graph.interface.mcp.mcp_uri import McpResourceUri as McpResourceUri
from vault_graph.interface.mcp.mcp_uri import parse_mcp_resource_uri as parse_mcp_resource_uri
from vault_graph.operation.scope.vault_catalog import VaultCatalog as VaultCatalog

sys.modules[__name__] = _implementation
