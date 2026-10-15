"""Compatibility import for :mod:`vault_graph.context.pack.context_evidence_selection`."""

import sys
from typing import Literal as Literal

from vault_graph.context.pack import context_evidence_selection as _implementation
from vault_graph.context.pack.context_evidence_selection import ContextEvidenceSelection as ContextEvidenceSelection
from vault_graph.context.pack.context_evidence_selection import EvidenceRefAction as EvidenceRefAction
from vault_graph.context.pack.context_evidence_selection import ItemSelectionStatus as ItemSelectionStatus
from vault_graph.context.pack.context_pack import ContextEvidence as ContextEvidence
from vault_graph.context.pack.context_pack import ContextEvidenceRef as ContextEvidenceRef
from vault_graph.context.pack.context_pack import ContextPackBudget as ContextPackBudget

sys.modules[__name__] = _implementation
