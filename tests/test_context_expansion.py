from dataclasses import replace
from typing import cast

import pytest

from vault_graph.errors import RetrievalContractError
from vault_graph.ingestion.document_normalizer import ChunkSnapshot
from vault_graph.ingestion.vault_catalog import QueryScope
from vault_graph.retrieval.context_expansion import CONTEXT_POLICY_VERSION, ContextExpander
from vault_graph.retrieval.retrieval_result import RetrievalWarning
from vault_graph.storage.interfaces.metadata_store import MetadataStore


class FakeMetadataStore:
    def __init__(self, chunks: tuple[ChunkSnapshot, ...]) -> None:
        self._chunks = chunks
        self.calls: list[tuple[str, str]] = []

    def list_document_chunks(self, *, vault_id: str, document_id: str) -> tuple[ChunkSnapshot, ...]:
        self.calls.append((vault_id, document_id))
        return self._chunks


def _chunk(
    *,
    chunk_id: str,
    document_order: int,
    section_path: tuple[str, ...],
    text: str = "body",
    token_count: int = 1,
    vault_id: str = "vault-a",
    document_id: str = "document-a",
    path: str = "docs/page.md",
) -> ChunkSnapshot:
    return ChunkSnapshot(
        vault_id=vault_id,
        chunk_id=chunk_id,
        document_id=document_id,
        path=path,
        section=section_path[-1] if section_path else None,
        anchor=chunk_id,
        text=text,
        token_count=token_count,
        content_hash=f"hash:{chunk_id}",
        chunker_version="document-block-window-v2",
        index_revision="metadata-1",
        section_path=section_path,
        document_order=document_order,
    )


def _scope(*, vault_id: str = "vault-a", content_scope: str = "docs") -> QueryScope:
    return QueryScope(vault_ids=(vault_id,), content_scopes=(content_scope,))


def _expander(store: FakeMetadataStore) -> ContextExpander:
    return ContextExpander(metadata_store=cast(MetadataStore, store))


def test_expands_ordered_neighbors_and_selects_longest_parent_prefix() -> None:
    chunks = (
        _chunk(chunk_id="chunk-0", document_order=0, section_path=("A",)),
        _chunk(chunk_id="chunk-1", document_order=1, section_path=("A",)),
        _chunk(chunk_id="chunk-2", document_order=2, section_path=("A", "B")),
        _chunk(chunk_id="chunk-3", document_order=3, section_path=("C",)),
    )
    store = FakeMetadataStore((chunks[3], chunks[1], chunks[2], chunks[0]))

    expansion = _expander(store).expand(
        matched_chunk=chunks[2],
        scope=_scope(),
        max_tokens=20,
        neighbor_radius=1,
    )

    assert expansion.matched_chunk_id == "chunk-2"
    assert expansion.context_chunk_ids == ("chunk-1", "chunk-3")
    assert expansion.parent_section_path == ("A",)
    assert expansion.reason
    assert expansion.policy_version == CONTEXT_POLICY_VERSION
    assert expansion.warnings == ()
    assert store.calls == [("vault-a", "document-a")]


def test_scope_filters_candidates_and_rejects_matched_chunk_outside_scope() -> None:
    matched = _chunk(chunk_id="matched", document_order=1, section_path=("A",))
    other_vault = _chunk(
        chunk_id="other-vault",
        document_order=0,
        section_path=("A",),
        vault_id="vault-b",
    )
    other_scope = _chunk(
        chunk_id="other-scope",
        document_order=2,
        section_path=("A",),
        path="wiki/page.md",
    )
    store = FakeMetadataStore((other_vault, matched, other_scope))

    expansion = _expander(store).expand(
        matched_chunk=matched,
        scope=_scope(),
        max_tokens=10,
    )

    assert expansion.context_chunk_ids == ()
    assert all(chunk_id not in expansion.context_chunk_ids for chunk_id in ("other-vault", "other-scope"))
    assert expansion.warnings == ()

    with pytest.raises(RetrievalContractError, match="outside QueryScope"):
        _expander(store).expand(
            matched_chunk=replace(matched, vault_id="vault-b"),
            scope=_scope(),
            max_tokens=10,
        )


def test_budget_omission_is_bounded_and_visible() -> None:
    chunks = (
        _chunk(chunk_id="previous", document_order=0, section_path=("A",), token_count=4),
        _chunk(chunk_id="matched", document_order=1, section_path=("A",), token_count=3),
        _chunk(chunk_id="next", document_order=2, section_path=("A",), token_count=5),
    )

    expansion = _expander(FakeMetadataStore(chunks)).expand(
        matched_chunk=chunks[1],
        scope=_scope(),
        max_tokens=4,
    )

    assert expansion.context_chunk_ids == ("previous",)
    selected_tokens = sum(chunk.token_count for chunk in chunks if chunk.chunk_id in expansion.context_chunk_ids)
    assert selected_tokens <= 4
    assert len(expansion.warnings) == 1
    warning = expansion.warnings[0]
    assert isinstance(warning, RetrievalWarning)
    assert warning.code == "budget_omitted"
    assert warning.severity == "warning"
    assert "next" in warning.message


def test_missing_matched_chunk_returns_warning_without_expanding_unrelated_chunks() -> None:
    matched = _chunk(chunk_id="matched", document_order=1, section_path=("A",))
    unrelated = _chunk(chunk_id="unrelated", document_order=0, section_path=("A",))

    expansion = _expander(FakeMetadataStore((unrelated,))).expand(
        matched_chunk=matched,
        scope=_scope(),
        max_tokens=10,
    )

    assert expansion.context_chunk_ids == ()
    assert expansion.parent_section_path == matched.section_path
    assert [warning.code for warning in expansion.warnings] == ["matched_chunk_missing"]


@pytest.mark.parametrize(
    ("max_tokens", "neighbor_radius"),
    [(0, 1), (-1, 1), (1, -1)],
)
def test_invalid_arguments_raise_retrieval_contract_error(max_tokens: int, neighbor_radius: int) -> None:
    matched = _chunk(chunk_id="matched", document_order=0, section_path=("A",))

    with pytest.raises(RetrievalContractError):
        _expander(FakeMetadataStore((matched,))).expand(
            matched_chunk=matched,
            scope=_scope(),
            max_tokens=max_tokens,
            neighbor_radius=neighbor_radius,
        )
