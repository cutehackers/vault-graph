"""Compatibility import for :mod:`vault_graph.interface.cli.code_commands`."""

import json as json
import sys
from collections.abc import Callable as Callable
from dataclasses import asdict as asdict
from dataclasses import is_dataclass as is_dataclass
from functools import wraps as wraps
from pathlib import Path as Path
from typing import Any as Any
from typing import cast as cast

import typer as typer

from vault_graph.errors import VaultGraphError as VaultGraphError
from vault_graph.interface.cli import code_commands as _implementation
from vault_graph.interface.cli.code_commands import _add_repository as _add_repository
from vault_graph.interface.cli.code_commands import _code_operation as _code_operation
from vault_graph.interface.cli.code_commands import _json_value as _json_value
from vault_graph.interface.cli.code_commands import _query as _query
from vault_graph.interface.cli.code_commands import _render as _render
from vault_graph.interface.cli.code_commands import _render_code_errors as _render_code_errors
from vault_graph.interface.cli.code_commands import _services as _services
from vault_graph.interface.cli.code_commands import _traversal_command as _traversal_command
from vault_graph.interface.cli.code_commands import _validate_format as _validate_format
from vault_graph.interface.cli.code_commands import callees as callees
from vault_graph.interface.cli.code_commands import callers as callers
from vault_graph.interface.cli.code_commands import code_app as code_app
from vault_graph.interface.cli.code_commands import impact as impact
from vault_graph.interface.cli.code_commands import index as index
from vault_graph.interface.cli.code_commands import outline as outline
from vault_graph.interface.cli.code_commands import repository_add as repository_add
from vault_graph.interface.cli.code_commands import repository_app as repository_app
from vault_graph.interface.cli.code_commands import repository_list as repository_list
from vault_graph.interface.cli.code_commands import repository_remove as repository_remove
from vault_graph.interface.cli.code_commands import search as search
from vault_graph.interface.cli.code_commands import status as status
from vault_graph.interface.cli.code_commands import symbol as symbol
from vault_graph.interface.composition.code_index_factory import CodeIndexFactory as CodeIndexFactory
from vault_graph.interface.composition.code_index_factory import CodeIndexServices as CodeIndexServices
from vault_graph.project.code.code_models import CodeFileOutlineRequest as CodeFileOutlineRequest
from vault_graph.project.code.code_models import CodeFreshnessRequest as CodeFreshnessRequest
from vault_graph.project.code.code_models import CodeImpactRequest as CodeImpactRequest
from vault_graph.project.code.code_models import CodeIndexRequest as CodeIndexRequest
from vault_graph.project.code.code_models import CodeOutputFormat as CodeOutputFormat
from vault_graph.project.code.code_models import CodeRepositoryEntry as CodeRepositoryEntry
from vault_graph.project.code.code_models import CodeSymbolRequest as CodeSymbolRequest
from vault_graph.project.code.code_models import CodeSymbolSearchRequest as CodeSymbolSearchRequest
from vault_graph.project.code.code_models import CodeTraversalRequest as CodeTraversalRequest
from vault_graph.project.code.code_query_service import CodeQueryService as CodeQueryService

sys.modules[__name__] = _implementation
