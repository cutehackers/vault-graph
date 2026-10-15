"""context features and lazy legacy exports."""

from importlib import import_module
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from vault_graph.context.pack.context_pack import CONTEXT_PACK_SCHEMA_VERSION as CONTEXT_PACK_SCHEMA_VERSION
    from vault_graph.context.pack.context_pack import (
        DEFAULT_CONTEXT_MAX_EVIDENCE_ITEMS as DEFAULT_CONTEXT_MAX_EVIDENCE_ITEMS,
    )
    from vault_graph.context.pack.context_pack import (
        DEFAULT_CONTEXT_MAX_EXCERPT_TOKENS as DEFAULT_CONTEXT_MAX_EXCERPT_TOKENS,
    )
    from vault_graph.context.pack.context_pack import DEFAULT_CONTEXT_MAX_TOKENS as DEFAULT_CONTEXT_MAX_TOKENS
    from vault_graph.context.pack.context_pack import DEFAULT_CONTEXT_RETRIEVAL_LIMIT as DEFAULT_CONTEXT_RETRIEVAL_LIMIT
    from vault_graph.context.pack.context_pack import (
        DEFAULT_RETRIEVAL_POLICY_VERSION as DEFAULT_RETRIEVAL_POLICY_VERSION,
    )
    from vault_graph.context.pack.context_pack import ContextEvidence as ContextEvidence
    from vault_graph.context.pack.context_pack import ContextEvidenceRef as ContextEvidenceRef
    from vault_graph.context.pack.context_pack import ContextPack as ContextPack
    from vault_graph.context.pack.context_pack import ContextPackActualScope as ContextPackActualScope
    from vault_graph.context.pack.context_pack import ContextPackBackend as ContextPackBackend
    from vault_graph.context.pack.context_pack import ContextPackBackendUse as ContextPackBackendUse
    from vault_graph.context.pack.context_pack import ContextPackBudget as ContextPackBudget
    from vault_graph.context.pack.context_pack import ContextPackItem as ContextPackItem
    from vault_graph.context.pack.context_pack import ContextPackRequest as ContextPackRequest
    from vault_graph.context.pack.context_pack import ContextPackRequestedScope as ContextPackRequestedScope
    from vault_graph.context.pack.context_pack import ContextPackScope as ContextPackScope
    from vault_graph.context.pack.context_pack import ContextPackSignal as ContextPackSignal
    from vault_graph.context.pack.context_pack import ContextPackStoreRevision as ContextPackStoreRevision
    from vault_graph.context.pack.context_pack import ContextPackVault as ContextPackVault
    from vault_graph.context.pack.context_pack import ContextPackVaultRevision as ContextPackVaultRevision
    from vault_graph.context.pack.context_pack import ContextPackWarning as ContextPackWarning
    from vault_graph.context.pack.context_pack import context_scope_from_query_scopes as context_scope_from_query_scopes
    from vault_graph.context.pack.context_pack import scope_key as scope_key
    from vault_graph.context.pack.context_pack_builder import ContextEvidenceResolver as ContextEvidenceResolver
    from vault_graph.context.pack.context_pack_builder import ContextPackBuilder as ContextPackBuilder
    from vault_graph.context.pack.context_pack_builder import ContextRetrievalService as ContextRetrievalService
    from vault_graph.context.pack.context_pack_builder import (
        MetadataContextEvidenceResolver as MetadataContextEvidenceResolver,
    )
    from vault_graph.context.pack.context_pack_builder import ResolvedContextEvidence as ResolvedContextEvidence
    from vault_graph.context.pack.context_pack_builder import SearchContextPackBuilder as SearchContextPackBuilder
    from vault_graph.context.pack.context_pack_renderer import ContextPackRenderer as ContextPackRenderer
    from vault_graph.context.pack.context_pack_renderer import DefaultContextPackRenderer as DefaultContextPackRenderer
    from vault_graph.context.pack.context_pack_serialization import compute_pack_id as compute_pack_id
    from vault_graph.context.pack.context_pack_serialization import (
        context_pack_identity_dict as context_pack_identity_dict,
    )
    from vault_graph.context.pack.context_pack_serialization import context_pack_to_dict as context_pack_to_dict
    from vault_graph.context.pack.context_pack_serialization import render_context_pack_json as render_context_pack_json
    from vault_graph.context.pack.context_pack_serialization import with_computed_pack_id as with_computed_pack_id
    from vault_graph.context.pack.context_pack_warnings import GRAPH_WARNING_CODE_MAP as GRAPH_WARNING_CODE_MAP
    from vault_graph.context.pack.context_pack_warnings import SEARCH_WARNING_CODE_MAP as SEARCH_WARNING_CODE_MAP
    from vault_graph.context.pack.context_pack_warnings import budget_warning as budget_warning
    from vault_graph.context.pack.context_pack_warnings import builder_warning as builder_warning
    from vault_graph.context.pack.context_pack_warnings import context_warning_from_graph as context_warning_from_graph
    from vault_graph.context.pack.context_pack_warnings import (
        context_warning_from_retrieval as context_warning_from_retrieval,
    )
    from vault_graph.context.pack.context_pack_warnings import (
        context_warning_from_search as context_warning_from_search,
    )
    from vault_graph.context.pack.context_pack_warnings import evidence_ref_from_metadata as evidence_ref_from_metadata

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

_EXPORTS = {
    "CONTEXT_PACK_SCHEMA_VERSION": ("vault_graph.context.pack.context_pack", "CONTEXT_PACK_SCHEMA_VERSION"),
    "DEFAULT_CONTEXT_MAX_EVIDENCE_ITEMS": (
        "vault_graph.context.pack.context_pack",
        "DEFAULT_CONTEXT_MAX_EVIDENCE_ITEMS",
    ),
    "DEFAULT_CONTEXT_MAX_EXCERPT_TOKENS": (
        "vault_graph.context.pack.context_pack",
        "DEFAULT_CONTEXT_MAX_EXCERPT_TOKENS",
    ),
    "DEFAULT_CONTEXT_MAX_TOKENS": ("vault_graph.context.pack.context_pack", "DEFAULT_CONTEXT_MAX_TOKENS"),
    "DEFAULT_CONTEXT_RETRIEVAL_LIMIT": ("vault_graph.context.pack.context_pack", "DEFAULT_CONTEXT_RETRIEVAL_LIMIT"),
    "DEFAULT_RETRIEVAL_POLICY_VERSION": ("vault_graph.context.pack.context_pack", "DEFAULT_RETRIEVAL_POLICY_VERSION"),
    "ContextEvidence": ("vault_graph.context.pack.context_pack", "ContextEvidence"),
    "ContextEvidenceRef": ("vault_graph.context.pack.context_pack", "ContextEvidenceRef"),
    "ContextPack": ("vault_graph.context.pack.context_pack", "ContextPack"),
    "ContextPackActualScope": ("vault_graph.context.pack.context_pack", "ContextPackActualScope"),
    "ContextPackBackend": ("vault_graph.context.pack.context_pack", "ContextPackBackend"),
    "ContextPackBackendUse": ("vault_graph.context.pack.context_pack", "ContextPackBackendUse"),
    "ContextPackBudget": ("vault_graph.context.pack.context_pack", "ContextPackBudget"),
    "ContextPackItem": ("vault_graph.context.pack.context_pack", "ContextPackItem"),
    "ContextPackRequest": ("vault_graph.context.pack.context_pack", "ContextPackRequest"),
    "ContextPackRequestedScope": ("vault_graph.context.pack.context_pack", "ContextPackRequestedScope"),
    "ContextPackScope": ("vault_graph.context.pack.context_pack", "ContextPackScope"),
    "ContextPackSignal": ("vault_graph.context.pack.context_pack", "ContextPackSignal"),
    "ContextPackStoreRevision": ("vault_graph.context.pack.context_pack", "ContextPackStoreRevision"),
    "ContextPackVault": ("vault_graph.context.pack.context_pack", "ContextPackVault"),
    "ContextPackVaultRevision": ("vault_graph.context.pack.context_pack", "ContextPackVaultRevision"),
    "ContextPackWarning": ("vault_graph.context.pack.context_pack", "ContextPackWarning"),
    "context_scope_from_query_scopes": ("vault_graph.context.pack.context_pack", "context_scope_from_query_scopes"),
    "scope_key": ("vault_graph.context.pack.context_pack", "scope_key"),
    "ContextPackRenderer": ("vault_graph.context.pack.context_pack_renderer", "ContextPackRenderer"),
    "DefaultContextPackRenderer": ("vault_graph.context.pack.context_pack_renderer", "DefaultContextPackRenderer"),
    "compute_pack_id": ("vault_graph.context.pack.context_pack_serialization", "compute_pack_id"),
    "context_pack_identity_dict": ("vault_graph.context.pack.context_pack_serialization", "context_pack_identity_dict"),
    "context_pack_to_dict": ("vault_graph.context.pack.context_pack_serialization", "context_pack_to_dict"),
    "render_context_pack_json": ("vault_graph.context.pack.context_pack_serialization", "render_context_pack_json"),
    "with_computed_pack_id": ("vault_graph.context.pack.context_pack_serialization", "with_computed_pack_id"),
    "GRAPH_WARNING_CODE_MAP": ("vault_graph.context.pack.context_pack_warnings", "GRAPH_WARNING_CODE_MAP"),
    "SEARCH_WARNING_CODE_MAP": ("vault_graph.context.pack.context_pack_warnings", "SEARCH_WARNING_CODE_MAP"),
    "budget_warning": ("vault_graph.context.pack.context_pack_warnings", "budget_warning"),
    "builder_warning": ("vault_graph.context.pack.context_pack_warnings", "builder_warning"),
    "context_warning_from_graph": ("vault_graph.context.pack.context_pack_warnings", "context_warning_from_graph"),
    "context_warning_from_retrieval": (
        "vault_graph.context.pack.context_pack_warnings",
        "context_warning_from_retrieval",
    ),
    "context_warning_from_search": ("vault_graph.context.pack.context_pack_warnings", "context_warning_from_search"),
    "evidence_ref_from_metadata": ("vault_graph.context.pack.context_pack_warnings", "evidence_ref_from_metadata"),
    "ContextEvidenceResolver": ("vault_graph.context.pack.context_pack_builder", "ContextEvidenceResolver"),
    "ContextPackBuilder": ("vault_graph.context.pack.context_pack_builder", "ContextPackBuilder"),
    "ContextRetrievalService": ("vault_graph.context.pack.context_pack_builder", "ContextRetrievalService"),
    "MetadataContextEvidenceResolver": (
        "vault_graph.context.pack.context_pack_builder",
        "MetadataContextEvidenceResolver",
    ),
    "ResolvedContextEvidence": ("vault_graph.context.pack.context_pack_builder", "ResolvedContextEvidence"),
    "SearchContextPackBuilder": ("vault_graph.context.pack.context_pack_builder", "SearchContextPackBuilder"),
    "context_pack_builder": ("vault_graph.context", "context_pack_builder"),
}


def __getattr__(name: str) -> Any:
    if name not in _EXPORTS:
        raise AttributeError(name)
    module, symbol = _EXPORTS[name]
    return getattr(import_module(module), symbol)


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(__all__))
