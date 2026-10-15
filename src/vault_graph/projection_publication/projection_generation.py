"""Compatibility import for :mod:`vault_graph.indexing.publication.projection_generation`."""

import hashlib as hashlib
import json as json
import os as os
import shutil as shutil
import sys
import tempfile as tempfile
import uuid as uuid
from collections.abc import Mapping as Mapping
from collections.abc import Sequence as Sequence
from dataclasses import dataclass as dataclass
from datetime import UTC as UTC
from datetime import datetime as datetime
from pathlib import Path as Path

from vault_graph.errors import VaultGraphError as VaultGraphError
from vault_graph.indexing.publication import projection_generation as _implementation
from vault_graph.indexing.publication.projection_generation import PROJECTION_BUNDLE_FORMAT as PROJECTION_BUNDLE_FORMAT
from vault_graph.indexing.publication.projection_generation import (
    PROJECTION_BUNDLE_SCHEMA_VERSION as PROJECTION_BUNDLE_SCHEMA_VERSION,
)
from vault_graph.indexing.publication.projection_generation import (
    PROJECTION_COMPONENT_FORMAT as PROJECTION_COMPONENT_FORMAT,
)
from vault_graph.indexing.publication.projection_generation import PROJECTION_COMPONENTS as PROJECTION_COMPONENTS
from vault_graph.indexing.publication.projection_generation import (
    ProjectionBundlePublisher as ProjectionBundlePublisher,
)
from vault_graph.indexing.publication.projection_generation import (
    ProjectionComponentManifest as ProjectionComponentManifest,
)
from vault_graph.indexing.publication.projection_generation import (
    ProjectionGenerationError as ProjectionGenerationError,
)
from vault_graph.indexing.publication.projection_generation import (
    ProjectionGenerationManager as ProjectionGenerationManager,
)
from vault_graph.indexing.publication.projection_generation import ProjectionLayout as ProjectionLayout
from vault_graph.indexing.publication.projection_generation import _atomic_write_json as _atomic_write_json
from vault_graph.indexing.publication.projection_generation import _fsync_directory as _fsync_directory
from vault_graph.indexing.publication.projection_generation import _is_safe_generation_id as _is_safe_generation_id
from vault_graph.indexing.publication.projection_generation import _json_mapping as _json_mapping
from vault_graph.indexing.publication.projection_generation import _layout_from_payload as _layout_from_payload
from vault_graph.indexing.publication.projection_generation import _snapshot_id as _snapshot_id
from vault_graph.indexing.publication.projection_generation import _validate_component_name as _validate_component_name
from vault_graph.indexing.publication.projection_generation import _validate_run_id as _validate_run_id
from vault_graph.operation.scope.graph_home import GraphHomeResolver as GraphHomeResolver

sys.modules[__name__] = _implementation
