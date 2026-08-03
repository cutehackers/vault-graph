"""Bounded, read-only composition of code and Vault evidence."""

from vault_graph.project_context.project_binding import ProjectBinding
from vault_graph.project_context.project_binding_catalog import (
    PROJECT_BINDING_SCHEMA_VERSION,
    ProjectBindingCatalog,
    ProjectBindingCatalogService,
)
from vault_graph.project_context.project_context_models import (
    DEFAULT_PROJECT_CONTEXT_DEPTH,
    DEFAULT_PROJECT_CONTEXT_LIMIT,
    DEFAULT_PROJECT_CONTEXT_TOKENS,
    MAX_PROJECT_CONTEXT_DEPTH,
    MAX_PROJECT_CONTEXT_LIMIT,
    MAX_PROJECT_CONTEXT_TOKENS,
    PROJECT_CONTEXT_SCHEMA_VERSION,
    ProjectAuthorityFreshness,
    ProjectContext,
    ProjectContextBudget,
    ProjectContextRequest,
    ProjectContextWarning,
    ProjectEvidence,
    ProjectEvidenceRelation,
    ProjectFreshness,
    combine_freshness,
)

__all__ = [
    "DEFAULT_PROJECT_CONTEXT_DEPTH",
    "DEFAULT_PROJECT_CONTEXT_LIMIT",
    "DEFAULT_PROJECT_CONTEXT_TOKENS",
    "MAX_PROJECT_CONTEXT_DEPTH",
    "MAX_PROJECT_CONTEXT_LIMIT",
    "MAX_PROJECT_CONTEXT_TOKENS",
    "PROJECT_BINDING_SCHEMA_VERSION",
    "PROJECT_CONTEXT_SCHEMA_VERSION",
    "ProjectAuthorityFreshness",
    "ProjectBinding",
    "ProjectBindingCatalog",
    "ProjectBindingCatalogService",
    "ProjectContext",
    "ProjectContextBudget",
    "ProjectContextRequest",
    "ProjectContextWarning",
    "ProjectEvidence",
    "ProjectEvidenceRelation",
    "ProjectFreshness",
    "combine_freshness",
]
