from typing import TYPE_CHECKING

from vault_graph.context.context_pack import (
    CONTEXT_PACK_SCHEMA_VERSION,
    DEFAULT_CONTEXT_MAX_EVIDENCE_ITEMS,
    DEFAULT_CONTEXT_MAX_EXCERPT_TOKENS,
    DEFAULT_CONTEXT_MAX_TOKENS,
    DEFAULT_CONTEXT_RETRIEVAL_LIMIT,
    DEFAULT_RETRIEVAL_POLICY_VERSION,
    ContextEvidence,
    ContextEvidenceRef,
    ContextPack,
    ContextPackActualScope,
    ContextPackBackend,
    ContextPackBackendUse,
    ContextPackBudget,
    ContextPackItem,
    ContextPackRequest,
    ContextPackRequestedScope,
    ContextPackScope,
    ContextPackSignal,
    ContextPackStoreRevision,
    ContextPackVault,
    ContextPackVaultRevision,
    ContextPackWarning,
    context_scope_from_query_scopes,
    scope_key,
)
from vault_graph.context.context_pack_renderer import ContextPackRenderer, DefaultContextPackRenderer
from vault_graph.context.context_pack_serialization import (
    compute_pack_id,
    context_pack_identity_dict,
    context_pack_to_dict,
    render_context_pack_json,
    with_computed_pack_id,
)
from vault_graph.context.context_pack_warnings import (
    GRAPH_WARNING_CODE_MAP,
    SEARCH_WARNING_CODE_MAP,
    budget_warning,
    builder_warning,
    context_warning_from_graph,
    context_warning_from_retrieval,
    context_warning_from_search,
    evidence_ref_from_metadata,
)

if TYPE_CHECKING:
    from vault_graph.context.context_pack_builder import (
        ContextEvidenceResolver,
        ContextPackBuilder,
        ContextRetrievalService,
        MetadataContextEvidenceResolver,
        ResolvedContextEvidence,
        SearchContextPackBuilder,
    )

__all__ = [
    "CONTEXT_PACK_SCHEMA_VERSION",
    "DEFAULT_CONTEXT_MAX_EVIDENCE_ITEMS",
    "DEFAULT_CONTEXT_MAX_EXCERPT_TOKENS",
    "DEFAULT_CONTEXT_MAX_TOKENS",
    "DEFAULT_CONTEXT_RETRIEVAL_LIMIT",
    "DEFAULT_RETRIEVAL_POLICY_VERSION",
    "GRAPH_WARNING_CODE_MAP",
    "SEARCH_WARNING_CODE_MAP",
    "ContextEvidence",
    "ContextEvidenceRef",
    "ContextEvidenceResolver",
    "ContextPack",
    "ContextPackActualScope",
    "ContextPackBackend",
    "ContextPackBackendUse",
    "ContextPackBudget",
    "ContextPackBuilder",
    "ContextPackItem",
    "ContextPackRenderer",
    "ContextPackRequest",
    "ContextPackRequestedScope",
    "ContextPackScope",
    "ContextPackSignal",
    "ContextPackStoreRevision",
    "ContextPackVault",
    "ContextPackVaultRevision",
    "ContextPackWarning",
    "ContextRetrievalService",
    "DefaultContextPackRenderer",
    "MetadataContextEvidenceResolver",
    "ResolvedContextEvidence",
    "SearchContextPackBuilder",
    "builder_warning",
    "budget_warning",
    "compute_pack_id",
    "context_pack_identity_dict",
    "context_pack_to_dict",
    "context_scope_from_query_scopes",
    "context_warning_from_graph",
    "context_warning_from_retrieval",
    "context_warning_from_search",
    "evidence_ref_from_metadata",
    "render_context_pack_json",
    "scope_key",
    "with_computed_pack_id",
]

_LAZY_BUILDER_EXPORTS = {
    "ContextEvidenceResolver",
    "ContextPackBuilder",
    "ContextRetrievalService",
    "MetadataContextEvidenceResolver",
    "ResolvedContextEvidence",
    "SearchContextPackBuilder",
}


def __getattr__(name: str) -> object:
    if name in _LAZY_BUILDER_EXPORTS:
        from vault_graph.context import context_pack_builder

        return getattr(context_pack_builder, name)
    raise AttributeError(f"module 'vault_graph.context' has no attribute {name!r}")


def __dir__() -> list[str]:
    return sorted(set(globals()) | _LAZY_BUILDER_EXPORTS)
