"""Compatibility import for :mod:`vault_graph.operation.integration.project_binding_catalog`."""

import json as json
import os as os
import sys
from collections.abc import Iterable as Iterable
from typing import Any as Any
from typing import Protocol as Protocol

from vault_graph.operation.integration import project_binding_catalog as _implementation
from vault_graph.operation.integration.project_binding_catalog import (
    PROJECT_BINDING_SCHEMA_VERSION as PROJECT_BINDING_SCHEMA_VERSION,
)
from vault_graph.operation.integration.project_binding_catalog import ProjectBindingCatalog as ProjectBindingCatalog
from vault_graph.operation.integration.project_binding_catalog import (
    ProjectBindingCatalogService as ProjectBindingCatalogService,
)
from vault_graph.operation.integration.project_binding_catalog import RepositoryCatalog as RepositoryCatalog
from vault_graph.operation.integration.project_binding_catalog import _ProjectBindingCatalog as _ProjectBindingCatalog
from vault_graph.operation.scope.catalog_service import CatalogService as CatalogService
from vault_graph.operation.scope.vault_catalog import VaultCatalog as VaultCatalog
from vault_graph.project.context.project_binding import ProjectBinding as ProjectBinding

sys.modules[__name__] = _implementation
