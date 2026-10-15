"""Compatibility import for :mod:`vault_graph.projection_publication.projection_generation`."""

import sys

from vault_graph.projection_publication import projection_generation as _implementation
from vault_graph.projection_publication.projection_generation import _SAFE_RUN_ID_CHARACTERS as _SAFE_RUN_ID_CHARACTERS
from vault_graph.projection_publication.projection_generation import (
    PROJECTION_BUNDLE_FORMAT as PROJECTION_BUNDLE_FORMAT,
)
from vault_graph.projection_publication.projection_generation import (
    PROJECTION_BUNDLE_SCHEMA_VERSION as PROJECTION_BUNDLE_SCHEMA_VERSION,
)
from vault_graph.projection_publication.projection_generation import (
    PROJECTION_COMPONENT_FORMAT as PROJECTION_COMPONENT_FORMAT,
)
from vault_graph.projection_publication.projection_generation import PROJECTION_COMPONENTS as PROJECTION_COMPONENTS
from vault_graph.projection_publication.projection_generation import (
    ProjectionBundlePublisher as ProjectionBundlePublisher,
)
from vault_graph.projection_publication.projection_generation import (
    ProjectionComponentManifest as ProjectionComponentManifest,
)
from vault_graph.projection_publication.projection_generation import (
    ProjectionGenerationError as ProjectionGenerationError,
)
from vault_graph.projection_publication.projection_generation import (
    ProjectionGenerationManager as ProjectionGenerationManager,
)
from vault_graph.projection_publication.projection_generation import ProjectionLayout as ProjectionLayout

# Preserve historical module patch targets as well as class identities.
sys.modules[__name__] = _implementation
