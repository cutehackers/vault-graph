"""Format-neutral structural window planning for extracted documents."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Protocol, TypeVar, runtime_checkable

from vault_graph.ingestion.document_models import ContentBlock, ContentUnit, ExtractedDocument, SourceLocator

DEFAULT_DOCUMENT_CHUNK_MAX_TOKENS = 256
CHUNKER_VERSION = "document-block-window-v2"

ChunkResultT = TypeVar("ChunkResultT", covariant=True)


@runtime_checkable
class DocumentChunker(Protocol[ChunkResultT]):
    """Stable boundary for chunk planners independent of source format."""

    version: str

    def chunk(self, document: ExtractedDocument) -> tuple[ChunkResultT, ...]: ...


@dataclass(frozen=True)
class ChunkDraft:
    """Raw, non-overlapping leaf chunk before document identity is assigned."""

    text: str
    token_count: int
    section: str | None
    anchor: str | None
    section_path: tuple[str, ...]
    source_locators: tuple[SourceLocator, ...]
    document_order: int
    boundary_key: str

    def __post_init__(self) -> None:
        if self.token_count < 0:
            raise ValueError("token_count must not be negative")
        if not isinstance(self.section_path, tuple):
            raise ValueError("section_path must be a tuple")
        if not isinstance(self.source_locators, tuple):
            raise ValueError("source_locators must be a tuple")
        if self.document_order < 0:
            raise ValueError("document_order must not be negative")
        if not self.boundary_key:
            raise ValueError("boundary_key is required")


@dataclass(frozen=True)
class DocumentWindowChunker:
    """Concrete planner implementing the shared v2 forward-pass policy."""

    max_tokens: int = DEFAULT_DOCUMENT_CHUNK_MAX_TOKENS
    version: str = CHUNKER_VERSION

    def __post_init__(self) -> None:
        if self.max_tokens <= 0:
            raise ValueError("max_tokens must be positive")
        if self.version != CHUNKER_VERSION:
            raise ValueError(f"unsupported chunker version: {self.version}")

    def chunk(self, document: ExtractedDocument) -> tuple[ChunkDraft, ...]:
        return chunk_document(document, max_tokens=self.max_tokens)


@dataclass(frozen=True)
class _Fragment:
    text: str
    token_count: int
    section_path: tuple[str, ...]
    locator: SourceLocator
    unit_key: str
    block_key: str
    document_order: int
    fragment_index: int


def chunk_document(
    document: ExtractedDocument,
    *,
    max_tokens: int = DEFAULT_DOCUMENT_CHUNK_MAX_TOKENS,
) -> tuple[ChunkDraft, ...]:
    """Pack reader units once, without overlap or format-specific parsing."""

    if max_tokens <= 0:
        raise ValueError("max_tokens must be positive")

    drafts: list[ChunkDraft] = []
    pending: list[_Fragment] = []
    pending_tokens = 0
    sequence = 0

    def flush() -> None:
        nonlocal pending, pending_tokens
        if not pending:
            return
        first = pending[0]
        last = pending[-1]
        drafts.append(
            ChunkDraft(
                text=_join_fragments(tuple(pending)),
                token_count=pending_tokens,
                section=first.section_path[-1] if first.section_path else None,
                anchor=_anchor(first.section_path[-1]) if first.section_path else None,
                section_path=first.section_path,
                source_locators=tuple(dict.fromkeys(fragment.locator for fragment in pending)),
                document_order=first.document_order,
                boundary_key=_boundary_key(first=first, last=last, fragment_count=len(pending)),
            )
        )
        pending = []
        pending_tokens = 0

    for block in document.blocks:
        if block.kind == "heading" and pending:
            flush()
        for unit in block.units:
            fragments = _fragments_for_unit(
                block=block,
                unit=unit,
                max_tokens=max_tokens,
                document_order=sequence,
            )
            sequence += len(fragments)
            for fragment in fragments:
                if pending and fragment.section_path != pending[0].section_path:
                    flush()
                if pending and pending_tokens + fragment.token_count > max_tokens:
                    flush()
                pending.append(fragment)
                pending_tokens += fragment.token_count
    flush()
    return tuple(drafts)


def contextual_embedding_text(*, section_path: tuple[str, ...], text: str) -> str:
    """Add structural context only to a derived embedding projection."""

    breadcrumb = " > ".join(segment.strip() for segment in section_path if segment.strip())
    if not breadcrumb:
        return text
    return f"Section path: {breadcrumb}\n\n{text}"


def _fragments_for_unit(
    *,
    block: ContentBlock,
    unit: ContentUnit,
    max_tokens: int,
    document_order: int,
) -> tuple[_Fragment, ...]:
    block_section_path = block.section_path
    block_key = block.stable_key
    text = unit.text
    token_count = _token_count(text)
    if token_count <= max_tokens or not text.split():
        return (
            _Fragment(
                text=text,
                token_count=token_count,
                section_path=block_section_path,
                locator=unit.source_locator,
                unit_key=unit.stable_key,
                block_key=block_key,
                document_order=document_order,
                fragment_index=0,
            ),
        )

    words = text.split()
    fragments: list[_Fragment] = []
    for fragment_index, start in enumerate(range(0, len(words), max_tokens)):
        fragment_text = " ".join(words[start : start + max_tokens])
        fragments.append(
            _Fragment(
                text=fragment_text,
                token_count=_token_count(fragment_text),
                section_path=block_section_path,
                locator=unit.source_locator,
                unit_key=unit.stable_key,
                block_key=block_key,
                document_order=document_order + fragment_index,
                fragment_index=fragment_index,
            )
        )
    return tuple(fragments)


def _join_fragments(fragments: tuple[_Fragment, ...]) -> str:
    result = fragments[0].text
    previous = fragments[0]
    for fragment in fragments[1:]:
        if not result and fragment.text:
            result = fragment.text
            previous = fragment
            continue
        if fragment.unit_key == previous.unit_key:
            separator = " "
        elif fragment.block_key == previous.block_key:
            separator = "\n"
        else:
            separator = "\n\n"
        result += separator + fragment.text
        previous = fragment
    return result


def _boundary_key(*, first: _Fragment, last: _Fragment, fragment_count: int) -> str:
    section = ">".join(first.section_path)
    return "|".join(
        (
            section,
            first.block_key,
            first.unit_key,
            str(first.fragment_index),
            last.block_key,
            last.unit_key,
            str(last.fragment_index),
            str(fragment_count),
        )
    )


def _token_count(text: str) -> int:
    return len(text.split())


def _anchor(section: str) -> str:
    slug = re.sub(r"[^a-z0-9가-힣]+", "-", section.strip().lower()).strip("-")
    return slug or "section"
