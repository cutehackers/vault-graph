"""Compatibility import for :mod:`vault_graph.context.pack.context_pack_renderer`."""

import sys
from typing import Protocol as Protocol

from vault_graph.context.pack import context_pack_renderer as _implementation
from vault_graph.context.pack.context_pack import ContextEvidence as ContextEvidence
from vault_graph.context.pack.context_pack import ContextEvidenceRef as ContextEvidenceRef
from vault_graph.context.pack.context_pack import ContextPack as ContextPack
from vault_graph.context.pack.context_pack import ContextPackActualScope as ContextPackActualScope
from vault_graph.context.pack.context_pack import ContextPackItem as ContextPackItem
from vault_graph.context.pack.context_pack import ContextPackWarning as ContextPackWarning
from vault_graph.context.pack.context_pack_renderer import ContextPackRenderer as ContextPackRenderer
from vault_graph.context.pack.context_pack_renderer import DefaultContextPackRenderer as DefaultContextPackRenderer
from vault_graph.context.pack.context_pack_renderer import _actual_scope_label as _actual_scope_label
from vault_graph.context.pack.context_pack_renderer import _evidence_location as _evidence_location
from vault_graph.context.pack.context_pack_renderer import _evidence_ref_label as _evidence_ref_label
from vault_graph.context.pack.context_pack_renderer import _joined as _joined
from vault_graph.context.pack.context_pack_renderer import _markdown_code_span as _markdown_code_span
from vault_graph.context.pack.context_pack_renderer import _markdown_fence as _markdown_fence
from vault_graph.context.pack.context_pack_renderer import _markdown_text as _markdown_text
from vault_graph.context.pack.context_pack_renderer import _render_backend_use as _render_backend_use
from vault_graph.context.pack.context_pack_renderer import _render_evidence as _render_evidence
from vault_graph.context.pack.context_pack_renderer import _render_item as _render_item
from vault_graph.context.pack.context_pack_renderer import _render_warning as _render_warning
from vault_graph.context.pack.context_pack_serialization import render_context_pack_json as render_context_pack_json

sys.modules[__name__] = _implementation
