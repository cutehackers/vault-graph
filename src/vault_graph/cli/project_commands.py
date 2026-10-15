"""Compatibility import for :mod:`vault_graph.interface.cli.project_commands`."""

import json as json
import sys
from dataclasses import asdict as asdict
from dataclasses import is_dataclass as is_dataclass
from pathlib import Path as Path
from typing import Any as Any
from typing import cast as cast

import typer as typer

from vault_graph.errors import VaultGraphError as VaultGraphError
from vault_graph.interface.cli import project_commands as _implementation
from vault_graph.interface.cli.project_commands import _binding_service as _binding_service
from vault_graph.interface.cli.project_commands import _json_value as _json_value
from vault_graph.interface.cli.project_commands import _parse_evidence_mappings as _parse_evidence_mappings
from vault_graph.interface.cli.project_commands import _render as _render
from vault_graph.interface.cli.project_commands import _validate_format as _validate_format
from vault_graph.interface.cli.project_commands import bind as bind
from vault_graph.interface.cli.project_commands import bindings as bindings
from vault_graph.interface.cli.project_commands import project_app as project_app
from vault_graph.interface.composition.code_index_factory import CodeIndexFactory as CodeIndexFactory
from vault_graph.operation.integration.project_binding_catalog import (
    ProjectBindingCatalogService as ProjectBindingCatalogService,
)
from vault_graph.operation.scope.catalog_service import CatalogService as CatalogService
from vault_graph.project.context.project_binding import ProjectBinding as ProjectBinding

sys.modules[__name__] = _implementation
