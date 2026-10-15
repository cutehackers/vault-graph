"""Compatibility import for :mod:`vault_graph.interface.mcp.mcp_errors`."""

import re as re
import sys
from dataclasses import dataclass as dataclass
from pathlib import Path as Path
from typing import Literal as Literal

from vault_graph.errors import CatalogError as CatalogError
from vault_graph.errors import ContextPackError as ContextPackError
from vault_graph.errors import DataHomeManifestError as DataHomeManifestError
from vault_graph.errors import DataHomeNotInitializedError as DataHomeNotInitializedError
from vault_graph.errors import GraphStoreError as GraphStoreError
from vault_graph.errors import KeywordIndexError as KeywordIndexError
from vault_graph.errors import LegacyDataHomeDetectedError as LegacyDataHomeDetectedError
from vault_graph.errors import MemoryProjectionError as MemoryProjectionError
from vault_graph.errors import ReadOnlyBoundaryError as ReadOnlyBoundaryError
from vault_graph.errors import ResultExplanationError as ResultExplanationError
from vault_graph.errors import SearchError as SearchError
from vault_graph.errors import TextEmbeddingsError as TextEmbeddingsError
from vault_graph.errors import VaultGraphError as VaultGraphError
from vault_graph.errors import VectorStoreError as VectorStoreError
from vault_graph.interface.mcp import mcp_errors as _implementation
from vault_graph.interface.mcp.mcp_errors import ABSOLUTE_PATH_RE as ABSOLUTE_PATH_RE
from vault_graph.interface.mcp.mcp_errors import McpErrorPayload as McpErrorPayload
from vault_graph.interface.mcp.mcp_errors import McpErrorSeverity as McpErrorSeverity
from vault_graph.interface.mcp.mcp_errors import McpProtocolError as McpProtocolError
from vault_graph.interface.mcp.mcp_errors import McpProtocolErrorKind as McpProtocolErrorKind
from vault_graph.interface.mcp.mcp_errors import _code_for_domain_error as _code_for_domain_error
from vault_graph.interface.mcp.mcp_errors import _error as _error
from vault_graph.interface.mcp.mcp_errors import _kind_for_domain_code as _kind_for_domain_code
from vault_graph.interface.mcp.mcp_errors import _sanitize_error_message as _sanitize_error_message
from vault_graph.interface.mcp.mcp_errors import _sanitize_internal_message as _sanitize_internal_message
from vault_graph.interface.mcp.mcp_errors import map_exception_to_mcp_error as map_exception_to_mcp_error

sys.modules[__name__] = _implementation
