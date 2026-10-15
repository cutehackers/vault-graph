"""Compatibility import for :mod:`vault_graph.interface.cli.harness_commands`."""

import sys
from pathlib import Path as Path

import typer as typer

from vault_graph.errors import VaultGraphError as VaultGraphError
from vault_graph.interface.cli import harness_commands as _implementation
from vault_graph.interface.cli.harness_commands import _run as _run
from vault_graph.interface.cli.harness_commands import _vault_roots as _vault_roots
from vault_graph.interface.cli.harness_commands import guidance_app as guidance_app
from vault_graph.interface.cli.harness_commands import harness_app as harness_app
from vault_graph.interface.cli.harness_commands import install as install
from vault_graph.interface.cli.harness_commands import preview as preview
from vault_graph.interface.cli.harness_commands import remove as remove
from vault_graph.operation.integration.harness.harness_guidance import HarnessGuidanceRequest as HarnessGuidanceRequest
from vault_graph.operation.runtime.setup_service import SetupService as SetupService
from vault_graph.operation.scope.catalog_service import CatalogService as CatalogService

sys.modules[__name__] = _implementation
