"""Compatibility import for :mod:`vault_graph.interface.mcp.metadata_resource_reader`."""

import sys
from collections.abc import Callable as Callable
from dataclasses import dataclass as dataclass
from typing import NoReturn as NoReturn

from vault_graph.indexing.ingestion.document_normalizer import ChunkSnapshot as ChunkSnapshot
from vault_graph.indexing.ingestion.document_normalizer import DocumentSnapshot as DocumentSnapshot
from vault_graph.interface.mcp import metadata_resource_reader as _implementation
from vault_graph.interface.mcp.mcp_errors import McpErrorPayload as McpErrorPayload
from vault_graph.interface.mcp.mcp_errors import McpProtocolError as McpProtocolError
from vault_graph.interface.mcp.mcp_resources import McpResourceBody as McpResourceBody
from vault_graph.interface.mcp.mcp_uri import McpResourceUri as McpResourceUri
from vault_graph.interface.mcp.metadata_resource_reader import MetadataResourceRead as MetadataResourceRead
from vault_graph.interface.mcp.metadata_resource_reader import MetadataResourceReader as MetadataResourceReader
from vault_graph.interface.mcp.metadata_resource_reader import _document_metadata as _document_metadata
from vault_graph.interface.mcp.metadata_resource_reader import _ensure_metadata_available as _ensure_metadata_available
from vault_graph.interface.mcp.metadata_resource_reader import _evidence_dict as _evidence_dict
from vault_graph.interface.mcp.metadata_resource_reader import _is_decision as _is_decision
from vault_graph.interface.mcp.metadata_resource_reader import _is_issue as _is_issue
from vault_graph.interface.mcp.metadata_resource_reader import _is_page as _is_page
from vault_graph.interface.mcp.metadata_resource_reader import _is_source as _is_source
from vault_graph.interface.mcp.metadata_resource_reader import _raise_not_found as _raise_not_found
from vault_graph.interface.mcp.metadata_resource_reader import _render_markdown as _render_markdown
from vault_graph.interface.mcp.metadata_resource_reader import _required_value as _required_value
from vault_graph.interface.mcp.metadata_resource_reader import _warning as _warning
from vault_graph.operation.scope.vault_catalog import VaultCatalog as VaultCatalog
from vault_graph.storage.interfaces.metadata_store import EvidenceReference as EvidenceReference
from vault_graph.storage.interfaces.metadata_store import MetadataStore as MetadataStore

sys.modules[__name__] = _implementation
