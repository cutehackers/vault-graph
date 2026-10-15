"""Compatibility import for :mod:`vault_graph.project.context.project_binding`."""

import sys
from dataclasses import dataclass as dataclass
from pathlib import PurePosixPath as PurePosixPath

from vault_graph.project.context import project_binding as _implementation
from vault_graph.project.context.project_binding import (
    MAX_PROJECT_BINDING_CONTENT_SCOPES as MAX_PROJECT_BINDING_CONTENT_SCOPES,
)
from vault_graph.project.context.project_binding import (
    MAX_PROJECT_BINDING_EVIDENCE_MAPPINGS as MAX_PROJECT_BINDING_EVIDENCE_MAPPINGS,
)
from vault_graph.project.context.project_binding import MAX_PROJECT_BINDING_ID_LENGTH as MAX_PROJECT_BINDING_ID_LENGTH
from vault_graph.project.context.project_binding import MAX_PROJECT_BINDING_VAULT_IDS as MAX_PROJECT_BINDING_VAULT_IDS
from vault_graph.project.context.project_binding import ProjectBinding as ProjectBinding
from vault_graph.project.context.project_binding import _require_identifier as _require_identifier
from vault_graph.project.context.project_binding import _validate_code_evidence_id as _validate_code_evidence_id
from vault_graph.project.context.project_binding import _validate_content_scope as _validate_content_scope
from vault_graph.project.context.project_binding import _validate_vault_evidence_id as _validate_vault_evidence_id

sys.modules[__name__] = _implementation
