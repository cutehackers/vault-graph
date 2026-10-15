"""Compatibility import for :mod:`vault_graph.interface.mcp.mcp_uri`."""

import sys
from dataclasses import dataclass as dataclass
from pathlib import PurePosixPath as PurePosixPath
from typing import Literal as Literal
from typing import NoReturn as NoReturn
from urllib.parse import quote as quote
from urllib.parse import unquote as unquote
from urllib.parse import urlsplit as urlsplit

from vault_graph.errors import CatalogError as CatalogError
from vault_graph.interface.mcp import mcp_uri as _implementation
from vault_graph.interface.mcp.mcp_errors import McpErrorPayload as McpErrorPayload
from vault_graph.interface.mcp.mcp_errors import McpProtocolError as McpProtocolError
from vault_graph.interface.mcp.mcp_uri import McpResourceKind as McpResourceKind
from vault_graph.interface.mcp.mcp_uri import McpResourceUri as McpResourceUri
from vault_graph.interface.mcp.mcp_uri import _normalize_vault_resource_uri as _normalize_vault_resource_uri
from vault_graph.interface.mcp.mcp_uri import _parse_context_uri as _parse_context_uri
from vault_graph.interface.mcp.mcp_uri import _parse_vault_resource as _parse_vault_resource
from vault_graph.interface.mcp.mcp_uri import _path_parts as _path_parts
from vault_graph.interface.mcp.mcp_uri import _raise_invalid_resource_uri as _raise_invalid_resource_uri
from vault_graph.interface.mcp.mcp_uri import _required_value as _required_value
from vault_graph.interface.mcp.mcp_uri import _resolve_enabled_vault as _resolve_enabled_vault
from vault_graph.interface.mcp.mcp_uri import _same_or_child as _same_or_child
from vault_graph.interface.mcp.mcp_uri import _validate_decoded_value as _validate_decoded_value
from vault_graph.interface.mcp.mcp_uri import _validate_kind_value as _validate_kind_value
from vault_graph.interface.mcp.mcp_uri import decode_resource_segment as decode_resource_segment
from vault_graph.interface.mcp.mcp_uri import encode_resource_segment as encode_resource_segment
from vault_graph.interface.mcp.mcp_uri import parse_mcp_resource_uri as parse_mcp_resource_uri
from vault_graph.operation.scope.vault_catalog import VaultCatalog as VaultCatalog
from vault_graph.operation.scope.vault_catalog import VaultCatalogEntry as VaultCatalogEntry

sys.modules[__name__] = _implementation
