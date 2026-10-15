"""Compatibility import for :mod:`vault_graph.operation.diagnostics.projection_hygiene_service`."""

import sys

from vault_graph.operation.diagnostics import projection_hygiene_service as _implementation
from vault_graph.operation.diagnostics.projection_hygiene_service import (
    ProjectionHygieneReport as ProjectionHygieneReport,
)
from vault_graph.operation.diagnostics.projection_hygiene_service import (
    ProjectionHygieneService as ProjectionHygieneService,
)
from vault_graph.operation.diagnostics.projection_hygiene_service import RoleCount as RoleCount
from vault_graph.operation.diagnostics.projection_hygiene_service import SchemaVersion as SchemaVersion

sys.modules[__name__] = _implementation
