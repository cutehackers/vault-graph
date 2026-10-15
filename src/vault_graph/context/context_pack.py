"""Compatibility import for :mod:`vault_graph.context.pack.context_pack`."""

import sys
from dataclasses import dataclass as dataclass
from typing import Literal as Literal

from vault_graph.context.pack import context_pack as _implementation
from vault_graph.context.pack.context_pack import CONTEXT_PACK_SCHEMA_VERSION as CONTEXT_PACK_SCHEMA_VERSION
from vault_graph.context.pack.context_pack import (
    DEFAULT_CONTEXT_MAX_EVIDENCE_ITEMS as DEFAULT_CONTEXT_MAX_EVIDENCE_ITEMS,
)
from vault_graph.context.pack.context_pack import (
    DEFAULT_CONTEXT_MAX_EXCERPT_TOKENS as DEFAULT_CONTEXT_MAX_EXCERPT_TOKENS,
)
from vault_graph.context.pack.context_pack import DEFAULT_CONTEXT_MAX_TOKENS as DEFAULT_CONTEXT_MAX_TOKENS
from vault_graph.context.pack.context_pack import DEFAULT_CONTEXT_RETRIEVAL_LIMIT as DEFAULT_CONTEXT_RETRIEVAL_LIMIT
from vault_graph.context.pack.context_pack import DEFAULT_RETRIEVAL_POLICY_VERSION as DEFAULT_RETRIEVAL_POLICY_VERSION
from vault_graph.context.pack.context_pack import ContextEvidence as ContextEvidence
from vault_graph.context.pack.context_pack import ContextEvidenceRef as ContextEvidenceRef
from vault_graph.context.pack.context_pack import ContextPack as ContextPack
from vault_graph.context.pack.context_pack import ContextPackActualScope as ContextPackActualScope
from vault_graph.context.pack.context_pack import ContextPackBackend as ContextPackBackend
from vault_graph.context.pack.context_pack import ContextPackBackendUse as ContextPackBackendUse
from vault_graph.context.pack.context_pack import ContextPackBudget as ContextPackBudget
from vault_graph.context.pack.context_pack import ContextPackItem as ContextPackItem
from vault_graph.context.pack.context_pack import ContextPackItemType as ContextPackItemType
from vault_graph.context.pack.context_pack import ContextPackRequest as ContextPackRequest
from vault_graph.context.pack.context_pack import ContextPackRequestedScope as ContextPackRequestedScope
from vault_graph.context.pack.context_pack import ContextPackRevisionKind as ContextPackRevisionKind
from vault_graph.context.pack.context_pack import ContextPackScope as ContextPackScope
from vault_graph.context.pack.context_pack import ContextPackSignal as ContextPackSignal
from vault_graph.context.pack.context_pack import ContextPackSignalKind as ContextPackSignalKind
from vault_graph.context.pack.context_pack import ContextPackStoreRevision as ContextPackStoreRevision
from vault_graph.context.pack.context_pack import ContextPackStoreRevisionKind as ContextPackStoreRevisionKind
from vault_graph.context.pack.context_pack import ContextPackVault as ContextPackVault
from vault_graph.context.pack.context_pack import ContextPackVaultRevision as ContextPackVaultRevision
from vault_graph.context.pack.context_pack import ContextPackWarning as ContextPackWarning
from vault_graph.context.pack.context_pack import ContextPackWarningSeverity as ContextPackWarningSeverity
from vault_graph.context.pack.context_pack import ContextPackWarningSourceKind as ContextPackWarningSourceKind
from vault_graph.context.pack.context_pack import _require_non_empty as _require_non_empty
from vault_graph.context.pack.context_pack import _require_tuple as _require_tuple
from vault_graph.context.pack.context_pack import context_scope_from_query_scopes as context_scope_from_query_scopes
from vault_graph.context.pack.context_pack import scope_key as scope_key
from vault_graph.errors import ContextPackError as ContextPackError
from vault_graph.operation.scope.vault_catalog import QueryScope as QueryScope

sys.modules[__name__] = _implementation
