"""Read port for live document evidence references (보완4).

Composition passes the document graph store here so diagnostics need not check its concrete class.
"""

from __future__ import annotations

from typing import Protocol

from vault_graph.retrieval.graph.graph_contracts import GraphEvidenceRef


class DocumentEvidenceRefSource(Protocol):
    def current_document_evidence_refs(self) -> tuple[GraphEvidenceRef, ...]: ...
