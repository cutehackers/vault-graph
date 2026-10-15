"""Compatibility import for :mod:`vault_graph.context.memory.memory_models`."""

import hashlib as hashlib
import json as json
import sys
from dataclasses import dataclass as dataclass
from typing import Literal as Literal

from vault_graph.context.memory import memory_models as _implementation
from vault_graph.context.memory.memory_models import MEMORY_DOCUMENT_RESOURCE_KINDS as MEMORY_DOCUMENT_RESOURCE_KINDS
from vault_graph.context.memory.memory_models import DecisionMemoryProjection as DecisionMemoryProjection
from vault_graph.context.memory.memory_models import DecisionMemoryVault as DecisionMemoryVault
from vault_graph.context.memory.memory_models import MemoryBackendRevision as MemoryBackendRevision
from vault_graph.context.memory.memory_models import MemoryClaimStatus as MemoryClaimStatus
from vault_graph.context.memory.memory_models import MemoryDocumentResourceKind as MemoryDocumentResourceKind
from vault_graph.context.memory.memory_models import MemoryEvidenceRef as MemoryEvidenceRef
from vault_graph.context.memory.memory_models import MemoryFreshness as MemoryFreshness
from vault_graph.context.memory.memory_models import MemoryItem as MemoryItem
from vault_graph.context.memory.memory_models import MemoryItemKind as MemoryItemKind
from vault_graph.context.memory.memory_models import MemoryWarning as MemoryWarning
from vault_graph.context.memory.memory_models import MemoryWarningSeverity as MemoryWarningSeverity
from vault_graph.context.memory.memory_models import OpenQuestionsProjection as OpenQuestionsProjection
from vault_graph.context.memory.memory_models import OpenQuestionsVault as OpenQuestionsVault
from vault_graph.context.memory.memory_models import ProjectMemoryProjection as ProjectMemoryProjection
from vault_graph.context.memory.memory_models import ProjectMemoryVault as ProjectMemoryVault
from vault_graph.context.memory.memory_models import _require_non_empty_string as _require_non_empty_string
from vault_graph.context.memory.memory_models import _require_one_of as _require_one_of
from vault_graph.context.memory.memory_models import _require_tuple as _require_tuple
from vault_graph.context.memory.memory_models import _validate_memory_vault_groups as _validate_memory_vault_groups
from vault_graph.context.memory.memory_models import _validate_projection as _validate_projection
from vault_graph.context.memory.memory_models import stable_memory_item_id as stable_memory_item_id
from vault_graph.errors import MemoryProjectionError as MemoryProjectionError
from vault_graph.operation.scope.vault_catalog import QueryScope as QueryScope

sys.modules[__name__] = _implementation
