"""Compatibility import for :mod:`vault_graph.context.pack.context_pack_warnings`."""

import sys
from typing import TYPE_CHECKING as TYPE_CHECKING
from typing import cast as cast

from vault_graph.context.pack import context_pack_warnings as _implementation
from vault_graph.context.pack.context_pack import ContextEvidenceRef as ContextEvidenceRef
from vault_graph.context.pack.context_pack import ContextPackWarning as ContextPackWarning
from vault_graph.context.pack.context_pack import ContextPackWarningSeverity as ContextPackWarningSeverity
from vault_graph.context.pack.context_pack_warnings import GRAPH_WARNING_CODE_MAP as GRAPH_WARNING_CODE_MAP
from vault_graph.context.pack.context_pack_warnings import SEARCH_WARNING_CODE_MAP as SEARCH_WARNING_CODE_MAP
from vault_graph.context.pack.context_pack_warnings import _severity as _severity
from vault_graph.context.pack.context_pack_warnings import budget_warning as budget_warning
from vault_graph.context.pack.context_pack_warnings import builder_warning as builder_warning
from vault_graph.context.pack.context_pack_warnings import context_warning_from_graph as context_warning_from_graph
from vault_graph.context.pack.context_pack_warnings import (
    context_warning_from_retrieval as context_warning_from_retrieval,
)
from vault_graph.context.pack.context_pack_warnings import context_warning_from_search as context_warning_from_search
from vault_graph.context.pack.context_pack_warnings import evidence_ref_from_metadata as evidence_ref_from_metadata

sys.modules[__name__] = _implementation
