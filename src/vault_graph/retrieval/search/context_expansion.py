from __future__ import annotations

from dataclasses import dataclass

from vault_graph.errors import RetrievalContractError
from vault_graph.indexing.ingestion.document_normalizer import ChunkSnapshot
from vault_graph.operation.scope.vault_catalog import QueryScope
from vault_graph.retrieval.search.retrieval_result import RetrievalWarning
from vault_graph.storage.interfaces.metadata_store import MetadataStore

CONTEXT_POLICY_VERSION = "parent-neighbor-v1"


@dataclass(frozen=True)
class ContextExpansion:
    matched_chunk_id: str
    context_chunk_ids: tuple[str, ...]
    parent_section_path: tuple[str, ...]
    reason: str
    policy_version: str
    warnings: tuple[RetrievalWarning, ...]

    def __post_init__(self) -> None:
        if not self.matched_chunk_id:
            raise RetrievalContractError("matched_chunk_id is required")
        if not isinstance(self.context_chunk_ids, tuple):
            raise RetrievalContractError("context_chunk_ids must be an immutable tuple")
        if any(not isinstance(chunk_id, str) or not chunk_id for chunk_id in self.context_chunk_ids):
            raise RetrievalContractError("context_chunk_ids must contain non-empty strings")
        if self.matched_chunk_id in self.context_chunk_ids:
            raise RetrievalContractError("context_chunk_ids must not contain matched_chunk_id")
        if len(set(self.context_chunk_ids)) != len(self.context_chunk_ids):
            raise RetrievalContractError("context_chunk_ids must not contain duplicates")
        if not isinstance(self.parent_section_path, tuple) or any(
            not isinstance(part, str) for part in self.parent_section_path
        ):
            raise RetrievalContractError("parent_section_path must be a tuple of strings")
        if not self.reason:
            raise RetrievalContractError("reason is required")
        if not self.policy_version:
            raise RetrievalContractError("policy_version is required")
        if not isinstance(self.warnings, tuple):
            raise RetrievalContractError("warnings must be an immutable tuple")
        if any(not isinstance(warning, RetrievalWarning) for warning in self.warnings):
            raise RetrievalContractError("warnings must contain RetrievalWarning records")


class ContextExpander:
    """Expands a matched metadata leaf into bounded same-document context."""

    def __init__(self, *, metadata_store: MetadataStore) -> None:
        self._metadata_store = metadata_store

    def expand(
        self,
        *,
        matched_chunk: ChunkSnapshot,
        scope: QueryScope,
        max_tokens: int,
        neighbor_radius: int = 1,
    ) -> ContextExpansion:
        _validate_arguments(max_tokens=max_tokens, neighbor_radius=neighbor_radius)
        if not _chunk_in_scope(matched_chunk, scope):
            raise RetrievalContractError("matched chunk is outside QueryScope")

        ordered_chunks = self._ordered_document_chunks(matched_chunk=matched_chunk, scope=scope)
        matched_index = _find_chunk_index(ordered_chunks, matched_chunk.chunk_id)
        if matched_index is None:
            return ContextExpansion(
                matched_chunk_id=matched_chunk.chunk_id,
                context_chunk_ids=(),
                parent_section_path=matched_chunk.section_path,
                reason="matched leaf was not present in the metadata document listing",
                policy_version=CONTEXT_POLICY_VERSION,
                warnings=(
                    _warning(
                        code="matched_chunk_missing",
                        message=(
                            "MetadataStore did not return the matched chunk for "
                            f"document {matched_chunk.document_id}: {matched_chunk.chunk_id}"
                        ),
                    ),
                ),
            )

        candidates = _neighbor_candidates(
            ordered_chunks=ordered_chunks,
            matched_index=matched_index,
            neighbor_radius=neighbor_radius,
        )
        parent_section_path = _longest_parent_prefix(
            matched_section_path=matched_chunk.section_path,
            candidates=candidates,
        )
        context_chunk_ids: list[str] = []
        warnings: list[RetrievalWarning] = []
        used_tokens = 0
        for candidate in candidates:
            if candidate.token_count < 0:
                raise RetrievalContractError(f"context chunk token_count must not be negative: {candidate.chunk_id}")
            if used_tokens + candidate.token_count > max_tokens:
                warnings.append(
                    _warning(
                        code="budget_omitted",
                        message=(
                            f"Context chunk omitted because the {max_tokens}-token budget would be exceeded: "
                            f"{candidate.chunk_id}"
                        ),
                    )
                )
                continue
            context_chunk_ids.append(candidate.chunk_id)
            used_tokens += candidate.token_count

        return ContextExpansion(
            matched_chunk_id=matched_chunk.chunk_id,
            context_chunk_ids=tuple(context_chunk_ids),
            parent_section_path=parent_section_path,
            reason="ordered same-document parent and neighbor context",
            policy_version=CONTEXT_POLICY_VERSION,
            warnings=tuple(warnings),
        )

    def _ordered_document_chunks(
        self,
        *,
        matched_chunk: ChunkSnapshot,
        scope: QueryScope,
    ) -> tuple[ChunkSnapshot, ...]:
        chunks = self._metadata_store.list_document_chunks(
            vault_id=matched_chunk.vault_id,
            document_id=matched_chunk.document_id,
        )
        return tuple(
            sorted(
                (
                    chunk
                    for chunk in chunks
                    if chunk.vault_id == matched_chunk.vault_id
                    and chunk.document_id == matched_chunk.document_id
                    and _chunk_in_scope(chunk, scope)
                ),
                key=lambda chunk: (chunk.document_order, chunk.chunk_id),
            )
        )


def _validate_arguments(*, max_tokens: int, neighbor_radius: int) -> None:
    if isinstance(max_tokens, bool) or not isinstance(max_tokens, int) or max_tokens <= 0:
        raise RetrievalContractError("max_tokens must be a positive integer")
    if isinstance(neighbor_radius, bool) or not isinstance(neighbor_radius, int) or neighbor_radius < 0:
        raise RetrievalContractError("neighbor_radius must be a non-negative integer")


def _chunk_in_scope(chunk: ChunkSnapshot, scope: QueryScope) -> bool:
    if chunk.vault_id not in scope.vault_ids:
        return False
    return any(
        chunk.path == content_scope or chunk.path.startswith(f"{content_scope}/")
        for content_scope in scope.content_scopes
    )


def _find_chunk_index(chunks: tuple[ChunkSnapshot, ...], chunk_id: str) -> int | None:
    for index, chunk in enumerate(chunks):
        if chunk.chunk_id == chunk_id:
            return index
    return None


def _neighbor_candidates(
    *,
    ordered_chunks: tuple[ChunkSnapshot, ...],
    matched_index: int,
    neighbor_radius: int,
) -> tuple[ChunkSnapshot, ...]:
    start = max(0, matched_index - neighbor_radius)
    end = min(len(ordered_chunks), matched_index + neighbor_radius + 1)
    return tuple(chunk for index, chunk in enumerate(ordered_chunks[start:end], start=start) if index != matched_index)


def _longest_parent_prefix(
    *,
    matched_section_path: tuple[str, ...],
    candidates: tuple[ChunkSnapshot, ...],
) -> tuple[str, ...]:
    if not candidates:
        return matched_section_path
    common_prefixes = (_common_prefix(matched_section_path, candidate.section_path) for candidate in candidates)
    return max(common_prefixes, key=lambda prefix: (len(prefix), prefix))


def _common_prefix(first: tuple[str, ...], second: tuple[str, ...]) -> tuple[str, ...]:
    length = 0
    for first_part, second_part in zip(first, second, strict=False):
        if first_part != second_part:
            break
        length += 1
    return first[:length]


def _warning(*, code: str, message: str) -> RetrievalWarning:
    return RetrievalWarning(code=code, message=message, severity="warning")
