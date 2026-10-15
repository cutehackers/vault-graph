"""Compatibility import for :mod:`vault_graph.interface.composition.code_index_factory`."""

import sys
from dataclasses import dataclass as dataclass
from functools import partial as partial
from pathlib import Path as Path
from typing import TYPE_CHECKING as TYPE_CHECKING

from vault_graph.errors import VaultGraphError as VaultGraphError
from vault_graph.interface.composition import code_index_factory as _implementation
from vault_graph.interface.composition.adapters.code_projection_storage import (
    open_code_projection_reader as open_code_projection_reader,
)
from vault_graph.interface.composition.adapters.code_projection_storage import (
    open_code_projection_writer as open_code_projection_writer,
)
from vault_graph.interface.composition.code_index_factory import CodeIndexFactory as CodeIndexFactory
from vault_graph.interface.composition.code_index_factory import CodeIndexServiceFactory as CodeIndexServiceFactory
from vault_graph.interface.composition.code_index_factory import CodeIndexServices as CodeIndexServices
from vault_graph.operation.scope.catalog_service import CatalogService as CatalogService
from vault_graph.project.code.code_freshness import CodeFreshnessService as CodeFreshnessService
from vault_graph.project.code.code_generation import CodeProjectionGenerationManager as CodeProjectionGenerationManager
from vault_graph.project.code.code_models import CODE_PARSER_SPEC_VERSION as CODE_PARSER_SPEC_VERSION
from vault_graph.project.code.code_projection_service import CodeProjectionService as CodeProjectionService
from vault_graph.project.code.code_query_service import CodeQueryService as CodeQueryService
from vault_graph.project.code.dart_parser import DartCodeParserAdapter as DartCodeParserAdapter
from vault_graph.project.code.python_parser import PythonCodeParserAdapter as PythonCodeParserAdapter
from vault_graph.project.code.reference_resolution import CodeReferenceResolver as CodeReferenceResolver
from vault_graph.project.code.repository_catalog import CodeRepositoryCatalog as CodeRepositoryCatalog
from vault_graph.project.code.repository_catalog import CodeRepositoryCatalogService as CodeRepositoryCatalogService
from vault_graph.project.code.source_scanning import CodeSourceScanner as CodeSourceScanner
from vault_graph.storage.local.sqlite_code_projection_store import (
    SQLiteCodeProjectionStore as SQLiteCodeProjectionStore,
)

sys.modules[__name__] = _implementation
