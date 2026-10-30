"""Vector run status port. Composition injects the local JSON store (보완4)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from vault_graph.operation.scope.vault_catalog import QueryScope
from vault_graph.storage.interfaces.text_embeddings import EmbeddingModelSpec


@dataclass(frozen=True)
class VectorRunStatus:
    scope_key: str
    embedding_spec_key: str
    last_success_revision: str | None = None
    last_success_at: str | None = None
    last_error: str | None = None
    last_error_at: str | None = None


class VectorStatusStore(Protocol):
    def read(self, *, scope_key: str, embedding_spec_key: str) -> VectorRunStatus: ...

    def record_success(self, *, scope_key: str, embedding_spec_key: str, vector_index_revision: str) -> None: ...

    def record_failure(self, *, scope_key: str, embedding_spec_key: str, error: str) -> None: ...


def embedding_spec_key(spec: EmbeddingModelSpec) -> str:
    return "|".join((spec.model_name, spec.model_version, str(spec.dimensions), spec.spec_version))


def scope_key_for_status(scope: QueryScope) -> str:
    return f"{','.join(scope.vault_ids)}:{','.join(scope.content_scopes)}"
