"""Compatibility import for :mod:`vault_graph.interface.mcp.mcp_scope`."""

import sys
from dataclasses import dataclass as dataclass

from vault_graph.errors import CatalogError as CatalogError
from vault_graph.interface.mcp import mcp_scope as _implementation
from vault_graph.interface.mcp.mcp_scope import McpScopeInput as McpScopeInput
from vault_graph.interface.mcp.mcp_scope import _reject_disabled_entries as _reject_disabled_entries
from vault_graph.interface.mcp.mcp_scope import _validate_content_scope_narrowing as _validate_content_scope_narrowing
from vault_graph.interface.mcp.mcp_scope import scope_from_mcp_input as scope_from_mcp_input
from vault_graph.operation.scope.catalog_query_scopes import actual_query_scopes as actual_query_scopes
from vault_graph.operation.scope.vault_catalog import QueryScope as QueryScope
from vault_graph.operation.scope.vault_catalog import VaultCatalog as VaultCatalog
from vault_graph.operation.scope.vault_catalog import VaultCatalogEntry as VaultCatalogEntry

sys.modules[__name__] = _implementation
