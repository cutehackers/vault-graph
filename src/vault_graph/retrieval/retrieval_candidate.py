from __future__ import annotations

from dataclasses import dataclass

from vault_graph.errors import RetrievalContractError
from vault_graph.retrieval.retrieval_result import RetrievalSignal


@dataclass(frozen=True)
class RetrievalCandidate:
    vault_id: str
    document_id: str
    chunk_id: str
    signals: tuple[RetrievalSignal, ...]

    def __post_init__(self) -> None:
        if not self.vault_id:
            raise RetrievalContractError("retrieval candidate vault_id is required")
        if not self.document_id:
            raise RetrievalContractError("retrieval candidate document_id is required")
        if not self.chunk_id:
            raise RetrievalContractError("retrieval candidate chunk_id is required")
        if not self.signals:
            raise RetrievalContractError("retrieval candidate signals are required")
