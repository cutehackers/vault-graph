"""Compatibility import for :mod:`vault_graph.project.context.project_context_models`."""

import json as json
import sys
from dataclasses import asdict as asdict
from dataclasses import dataclass as dataclass
from hashlib import sha256 as sha256
from typing import Literal as Literal

from vault_graph.project.context import project_context_models as _implementation
from vault_graph.project.context.project_binding import ProjectBinding as ProjectBinding
from vault_graph.project.context.project_context_models import (
    DEFAULT_PROJECT_CONTEXT_DEPTH as DEFAULT_PROJECT_CONTEXT_DEPTH,
)
from vault_graph.project.context.project_context_models import (
    DEFAULT_PROJECT_CONTEXT_LIMIT as DEFAULT_PROJECT_CONTEXT_LIMIT,
)
from vault_graph.project.context.project_context_models import (
    DEFAULT_PROJECT_CONTEXT_TOKENS as DEFAULT_PROJECT_CONTEXT_TOKENS,
)
from vault_graph.project.context.project_context_models import (
    MAX_COMPACT_CONTEXT_SEQUENCE_ITEMS as MAX_COMPACT_CONTEXT_SEQUENCE_ITEMS,
)
from vault_graph.project.context.project_context_models import (
    MAX_COMPACT_CONTEXT_STRING_CHARS as MAX_COMPACT_CONTEXT_STRING_CHARS,
)
from vault_graph.project.context.project_context_models import MAX_PROJECT_CONTEXT_DEPTH as MAX_PROJECT_CONTEXT_DEPTH
from vault_graph.project.context.project_context_models import MAX_PROJECT_CONTEXT_LIMIT as MAX_PROJECT_CONTEXT_LIMIT
from vault_graph.project.context.project_context_models import MAX_PROJECT_CONTEXT_TOKENS as MAX_PROJECT_CONTEXT_TOKENS
from vault_graph.project.context.project_context_models import MIN_PROJECT_CONTEXT_TOKENS as MIN_PROJECT_CONTEXT_TOKENS
from vault_graph.project.context.project_context_models import (
    PROJECT_CONTEXT_SCHEMA_VERSION as PROJECT_CONTEXT_SCHEMA_VERSION,
)
from vault_graph.project.context.project_context_models import ProjectAuthorityFreshness as ProjectAuthorityFreshness
from vault_graph.project.context.project_context_models import ProjectAuthorityKind as ProjectAuthorityKind
from vault_graph.project.context.project_context_models import ProjectContext as ProjectContext
from vault_graph.project.context.project_context_models import ProjectContextBudget as ProjectContextBudget
from vault_graph.project.context.project_context_models import ProjectContextRequest as ProjectContextRequest
from vault_graph.project.context.project_context_models import ProjectContextWarning as ProjectContextWarning
from vault_graph.project.context.project_context_models import ProjectEvidence as ProjectEvidence
from vault_graph.project.context.project_context_models import ProjectEvidenceRelation as ProjectEvidenceRelation
from vault_graph.project.context.project_context_models import ProjectFreshness as ProjectFreshness
from vault_graph.project.context.project_context_models import ProjectRelationStatus as ProjectRelationStatus
from vault_graph.project.context.project_context_models import _compact_sequence as _compact_sequence
from vault_graph.project.context.project_context_models import _require_bounded as _require_bounded
from vault_graph.project.context.project_context_models import _require_freshness as _require_freshness
from vault_graph.project.context.project_context_models import _require_non_empty as _require_non_empty
from vault_graph.project.context.project_context_models import combine_freshness as combine_freshness
from vault_graph.project.context.project_context_models import (
    compact_project_context_value as compact_project_context_value,
)
from vault_graph.project.context.project_context_models import (
    estimate_project_context_tokens as estimate_project_context_tokens,
)

sys.modules[__name__] = _implementation
