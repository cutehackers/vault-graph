"""Project context contracts and lazy legacy exports."""

from importlib import import_module
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from vault_graph.operation.integration.project_binding_catalog import (
        PROJECT_BINDING_SCHEMA_VERSION as PROJECT_BINDING_SCHEMA_VERSION,
    )
    from vault_graph.operation.integration.project_binding_catalog import ProjectBindingCatalog as ProjectBindingCatalog
    from vault_graph.operation.integration.project_binding_catalog import (
        ProjectBindingCatalogService as ProjectBindingCatalogService,
    )
    from vault_graph.project.context.project_binding import (
        MAX_PROJECT_BINDING_CONTENT_SCOPES as MAX_PROJECT_BINDING_CONTENT_SCOPES,
    )
    from vault_graph.project.context.project_binding import (
        MAX_PROJECT_BINDING_EVIDENCE_MAPPINGS as MAX_PROJECT_BINDING_EVIDENCE_MAPPINGS,
    )
    from vault_graph.project.context.project_binding import (
        MAX_PROJECT_BINDING_ID_LENGTH as MAX_PROJECT_BINDING_ID_LENGTH,
    )
    from vault_graph.project.context.project_binding import (
        MAX_PROJECT_BINDING_VAULT_IDS as MAX_PROJECT_BINDING_VAULT_IDS,
    )
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
    from vault_graph.project.context.project_context_models import (
        MAX_PROJECT_CONTEXT_DEPTH as MAX_PROJECT_CONTEXT_DEPTH,
    )
    from vault_graph.project.context.project_context_models import (
        MAX_PROJECT_CONTEXT_LIMIT as MAX_PROJECT_CONTEXT_LIMIT,
    )
    from vault_graph.project.context.project_context_models import (
        MAX_PROJECT_CONTEXT_TOKENS as MAX_PROJECT_CONTEXT_TOKENS,
    )
    from vault_graph.project.context.project_context_models import (
        MIN_PROJECT_CONTEXT_TOKENS as MIN_PROJECT_CONTEXT_TOKENS,
    )
    from vault_graph.project.context.project_context_models import (
        PROJECT_CONTEXT_SCHEMA_VERSION as PROJECT_CONTEXT_SCHEMA_VERSION,
    )
    from vault_graph.project.context.project_context_models import (
        ProjectAuthorityFreshness as ProjectAuthorityFreshness,
    )
    from vault_graph.project.context.project_context_models import ProjectContext as ProjectContext
    from vault_graph.project.context.project_context_models import ProjectContextBudget as ProjectContextBudget
    from vault_graph.project.context.project_context_models import ProjectContextRequest as ProjectContextRequest
    from vault_graph.project.context.project_context_models import ProjectContextWarning as ProjectContextWarning
    from vault_graph.project.context.project_context_models import ProjectEvidence as ProjectEvidence
    from vault_graph.project.context.project_context_models import ProjectEvidenceRelation as ProjectEvidenceRelation
    from vault_graph.project.context.project_context_models import ProjectFreshness as ProjectFreshness
    from vault_graph.project.context.project_context_models import combine_freshness as combine_freshness
    from vault_graph.project.context.project_context_models import (
        compact_project_context_value as compact_project_context_value,
    )
    from vault_graph.project.context.project_context_models import (
        estimate_project_context_tokens as estimate_project_context_tokens,
    )

__all__ = [
    "DEFAULT_PROJECT_CONTEXT_DEPTH",
    "DEFAULT_PROJECT_CONTEXT_LIMIT",
    "DEFAULT_PROJECT_CONTEXT_TOKENS",
    "MAX_COMPACT_CONTEXT_SEQUENCE_ITEMS",
    "MAX_COMPACT_CONTEXT_STRING_CHARS",
    "MAX_PROJECT_BINDING_CONTENT_SCOPES",
    "MAX_PROJECT_BINDING_EVIDENCE_MAPPINGS",
    "MAX_PROJECT_BINDING_ID_LENGTH",
    "MAX_PROJECT_BINDING_VAULT_IDS",
    "MAX_PROJECT_CONTEXT_DEPTH",
    "MAX_PROJECT_CONTEXT_LIMIT",
    "MAX_PROJECT_CONTEXT_TOKENS",
    "MIN_PROJECT_CONTEXT_TOKENS",
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
    "compact_project_context_value",
    "estimate_project_context_tokens",
]

_EXPORTS = {
    "PROJECT_BINDING_SCHEMA_VERSION": (
        "vault_graph.operation.integration.project_binding_catalog",
        "PROJECT_BINDING_SCHEMA_VERSION",
    ),
    "ProjectBindingCatalog": ("vault_graph.operation.integration.project_binding_catalog", "ProjectBindingCatalog"),
    "ProjectBindingCatalogService": (
        "vault_graph.operation.integration.project_binding_catalog",
        "ProjectBindingCatalogService",
    ),
    "MAX_PROJECT_BINDING_CONTENT_SCOPES": (
        "vault_graph.project.context.project_binding",
        "MAX_PROJECT_BINDING_CONTENT_SCOPES",
    ),
    "MAX_PROJECT_BINDING_EVIDENCE_MAPPINGS": (
        "vault_graph.project.context.project_binding",
        "MAX_PROJECT_BINDING_EVIDENCE_MAPPINGS",
    ),
    "MAX_PROJECT_BINDING_ID_LENGTH": ("vault_graph.project.context.project_binding", "MAX_PROJECT_BINDING_ID_LENGTH"),
    "MAX_PROJECT_BINDING_VAULT_IDS": ("vault_graph.project.context.project_binding", "MAX_PROJECT_BINDING_VAULT_IDS"),
    "ProjectBinding": ("vault_graph.project.context.project_binding", "ProjectBinding"),
    "DEFAULT_PROJECT_CONTEXT_DEPTH": (
        "vault_graph.project.context.project_context_models",
        "DEFAULT_PROJECT_CONTEXT_DEPTH",
    ),
    "DEFAULT_PROJECT_CONTEXT_LIMIT": (
        "vault_graph.project.context.project_context_models",
        "DEFAULT_PROJECT_CONTEXT_LIMIT",
    ),
    "DEFAULT_PROJECT_CONTEXT_TOKENS": (
        "vault_graph.project.context.project_context_models",
        "DEFAULT_PROJECT_CONTEXT_TOKENS",
    ),
    "MAX_COMPACT_CONTEXT_SEQUENCE_ITEMS": (
        "vault_graph.project.context.project_context_models",
        "MAX_COMPACT_CONTEXT_SEQUENCE_ITEMS",
    ),
    "MAX_COMPACT_CONTEXT_STRING_CHARS": (
        "vault_graph.project.context.project_context_models",
        "MAX_COMPACT_CONTEXT_STRING_CHARS",
    ),
    "MAX_PROJECT_CONTEXT_DEPTH": ("vault_graph.project.context.project_context_models", "MAX_PROJECT_CONTEXT_DEPTH"),
    "MAX_PROJECT_CONTEXT_LIMIT": ("vault_graph.project.context.project_context_models", "MAX_PROJECT_CONTEXT_LIMIT"),
    "MAX_PROJECT_CONTEXT_TOKENS": ("vault_graph.project.context.project_context_models", "MAX_PROJECT_CONTEXT_TOKENS"),
    "MIN_PROJECT_CONTEXT_TOKENS": ("vault_graph.project.context.project_context_models", "MIN_PROJECT_CONTEXT_TOKENS"),
    "PROJECT_CONTEXT_SCHEMA_VERSION": (
        "vault_graph.project.context.project_context_models",
        "PROJECT_CONTEXT_SCHEMA_VERSION",
    ),
    "ProjectAuthorityFreshness": ("vault_graph.project.context.project_context_models", "ProjectAuthorityFreshness"),
    "ProjectContext": ("vault_graph.project.context.project_context_models", "ProjectContext"),
    "ProjectContextBudget": ("vault_graph.project.context.project_context_models", "ProjectContextBudget"),
    "ProjectContextRequest": ("vault_graph.project.context.project_context_models", "ProjectContextRequest"),
    "ProjectContextWarning": ("vault_graph.project.context.project_context_models", "ProjectContextWarning"),
    "ProjectEvidence": ("vault_graph.project.context.project_context_models", "ProjectEvidence"),
    "ProjectEvidenceRelation": ("vault_graph.project.context.project_context_models", "ProjectEvidenceRelation"),
    "ProjectFreshness": ("vault_graph.project.context.project_context_models", "ProjectFreshness"),
    "combine_freshness": ("vault_graph.project.context.project_context_models", "combine_freshness"),
    "compact_project_context_value": (
        "vault_graph.project.context.project_context_models",
        "compact_project_context_value",
    ),
    "estimate_project_context_tokens": (
        "vault_graph.project.context.project_context_models",
        "estimate_project_context_tokens",
    ),
}


def __getattr__(name: str) -> Any:
    if name not in _EXPORTS:
        raise AttributeError(name)
    module, symbol = _EXPORTS[name]
    return getattr(import_module(module), symbol)


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(__all__))
