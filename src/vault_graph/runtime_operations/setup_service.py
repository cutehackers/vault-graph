"""Compatibility import for :mod:`vault_graph.operation.runtime.setup_service`."""

import sys
from dataclasses import dataclass as dataclass
from pathlib import Path as Path

from vault_graph.errors import CatalogError as CatalogError
from vault_graph.errors import SetupError as SetupError
from vault_graph.indexing.index_service import IndexRunReport as IndexRunReport
from vault_graph.operation.integration.harness.harness_guidance import HarnessGuidanceReport as HarnessGuidanceReport
from vault_graph.operation.integration.harness.harness_guidance import HarnessGuidanceRequest as HarnessGuidanceRequest
from vault_graph.operation.integration.harness.harness_guidance import HarnessGuidanceService as HarnessGuidanceService
from vault_graph.operation.integration.mcp.mcp_config_registration import McpAgent as McpAgent
from vault_graph.operation.integration.mcp.mcp_config_registration import McpConfigRegistrar as McpConfigRegistrar
from vault_graph.operation.integration.mcp.mcp_config_registration import McpConfigRenderer as McpConfigRenderer
from vault_graph.operation.integration.mcp.mcp_config_registration import McpConfigRequest as McpConfigRequest
from vault_graph.operation.integration.mcp.mcp_config_registration import McpRegistrationReport as McpRegistrationReport
from vault_graph.operation.integration.mcp.mcp_config_registration import (
    McpRegistrationRequest as McpRegistrationRequest,
)
from vault_graph.operation.runtime import setup_service as _implementation
from vault_graph.operation.runtime.indexing import OperationsIndexFactory as OperationsIndexFactory
from vault_graph.operation.runtime.setup_service import SetupReport as SetupReport
from vault_graph.operation.runtime.setup_service import SetupRequest as SetupRequest
from vault_graph.operation.runtime.setup_service import SetupService as SetupService
from vault_graph.operation.runtime.setup_service import _setup_recovery_hint as _setup_recovery_hint
from vault_graph.operation.scope.catalog_service import CatalogService as CatalogService
from vault_graph.operation.scope.graph_home import GraphHomeResolver as GraphHomeResolver
from vault_graph.operation.scope.vault_catalog import VaultCatalog as VaultCatalog
from vault_graph.operation.scope.vault_catalog import VaultCatalogEntry as VaultCatalogEntry

sys.modules[__name__] = _implementation
