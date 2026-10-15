"""Compatibility import for :mod:`vault_graph.projection_diagnostics.projection_hygiene_service`."""

import sys

from vault_graph.projection_diagnostics import projection_hygiene_service as _implementation
from vault_graph.projection_diagnostics.projection_hygiene_service import (
    ProjectionHygieneReport as ProjectionHygieneReport,
)
from vault_graph.projection_diagnostics.projection_hygiene_service import (
    ProjectionHygieneService as ProjectionHygieneService,
)
from vault_graph.projection_diagnostics.projection_hygiene_service import RoleCount as RoleCount
from vault_graph.projection_diagnostics.projection_hygiene_service import SchemaVersion as SchemaVersion

# Preserve historical module patch targets as well as class identities.
sys.modules[__name__] = _implementation
