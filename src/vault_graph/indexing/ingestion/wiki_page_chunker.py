"""`wiki-page-window-v1`: chunks of curated wiki pages and `wiki/sources/` pages (spec 2026-11-05 §10.2 원인7·8).

The generic window chunker cuts at every heading, so a 280-word page became 11 chunks of 0 to 54
words, and the template sections every page carries (Claim Evidence, Sources, Related, ...) took the
top of many result lists with near-identical vectors. This chunker instead:

1. Packs the page's sections in order into body windows of about `WIKI_PAGE_WINDOW_MAX_WORDS`
   whitespace words. Most curated pages fit in one window. A window is only closed once it holds
   `WIKI_PAGE_WINDOW_MIN_WORDS` words of text, and a shorter last window joins the one before it, so
   no window is a lone tiny section. A window without any text (headings only) is not written.
   Headings inside a window stay in its text as Markdown heading lines.
2. Packs template sections (`TEMPLATE_SECTION_TITLES`, and every section under one) the same way into
   `template` chunks. Keyword search reads them. The vector index leaves them out, so template text is
   in no embedding input.
3. Adds one `page_card` chunk built from frontmatter values and the file name only (`page_card_text`).
   No text is generated (principle 1). Vectors and keyword search both read it.

Chunk ids follow (chunker version, vault, path, window boundary), like the generic chunker.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import PurePosixPath

from vault_graph.indexing.ingestion.document_chunking import ChunkDraft, contextual_embedding_text
from vault_graph.indexing.ingestion.document_models import ContentBlock, ExtractedDocument, SourceLocator
from vault_graph.indexing.ingestion.document_snapshots import ChunkKind

WIKI_PAGE_CHUNKER_VERSION = "wiki-page-window-v1"

# Word budget of one window: the largest budget whose model inputs all stay within e5's 512 tokens on
# the personal Vault (115 curated and source pages, `passage: ` prefix and section path line counted
# with the model tokenizer). Over 512 tokens: 0% at 160 words, 0.66% at 176, 1.4% at 192, 8.0% at 256,
# because Korean words take about three model tokens each. At 160, 60% of pages are one window.
WIKI_PAGE_WINDOW_MAX_WORDS = 160
# A window closes only after this many words of text, and a shorter last window joins the previous
# one. A quarter of the budget: no window is a lone 4- to 39-word section, and a window is never
# longer than budget + minimum (200 words).
WIKI_PAGE_WINDOW_MIN_WORDS = 40

# Section titles that every page of a kind carries with the same shape (casefolded). Measured on the
# personal Vault: Claim Evidence 46 pages, Registration and Durable Knowledge Links 49 source pages.
TEMPLATE_SECTION_TITLES: frozenset[str] = frozenset(
    {
        "claim evidence",
        "change notes",
        "related",
        "related pages",
        "related concepts",
        "supporting sources",
        "sources",
        "registration",
        "durable knowledge links",
        "관련 페이지",
        "항목별 출처",
    }
)

_STEM_SEPARATORS = re.compile(r"[-_\s]+")


@dataclass(frozen=True)
class WikiPageChunker:
    max_words: int = WIKI_PAGE_WINDOW_MAX_WORDS
    min_words: int = WIKI_PAGE_WINDOW_MIN_WORDS

    def __post_init__(self) -> None:
        if self.max_words <= 0 or self.min_words <= 0:
            raise ValueError("max_words and min_words must be positive")

    @property
    def version(self) -> str:
        return WIKI_PAGE_CHUNKER_VERSION

    def chunk(self, document: ExtractedDocument) -> tuple[ChunkDraft, ...]:
        heading = _page_heading(document.blocks)
        body: list[_Fragment] = []
        template: list[_Fragment] = []
        sequence = 1  # 0 is the page card
        for block in document.blocks:
            for fragment in _fragments(block, max_words=self.max_words, first_order=sequence):
                (template if _is_template(fragment.section_path, heading) else body).append(fragment)
                sequence += 1
        card_text = page_card_text(document.frontmatter.data, path=document.source.path, heading=heading)
        card = ChunkDraft(
            text=card_text,
            token_count=len(card_text.split()),
            section=None,
            anchor=None,
            section_path=(),
            source_locators=(_card_locator(document),),
            document_order=0,
            boundary_key="page_card",
            chunk_kind="page_card",
        )
        windows = (
            *(_draft(window, "body") for window in self._windows(body)),
            *(_draft(window, "template") for window in self._windows(template)),
        )
        return (card, *sorted(windows, key=lambda draft: draft.document_order))

    def embedding_input(self, section_path: tuple[str, ...], text: str) -> str:
        return contextual_embedding_text(section_path=section_path, text=text)

    def _windows(self, fragments: list[_Fragment]) -> list[list[_Fragment]]:
        windows: list[list[_Fragment]] = []
        pending: list[_Fragment] = []
        for fragment in fragments:
            if (
                pending
                and not fragment.is_heading
                and _words(pending) + fragment.word_count > self.max_words
                and _text_words(pending) >= self.min_words
            ):
                # Headings at the end of a full window open the next one with their section.
                split = len(pending)
                while split > 0 and pending[split - 1].is_heading:
                    split -= 1
                windows.append(pending[:split])
                pending = pending[split:]
            pending.append(fragment)
        if pending:
            windows.append(pending)
        # Only the last window can be short: every earlier one closed at the minimum.
        if len(windows) > 1 and _text_words(windows[-1]) < self.min_words:
            last = windows.pop()
            windows[-1] = windows[-1] + last
        return [window for window in windows if _text_words(window) > 0]


def page_card_text(frontmatter: Mapping[str, object], *, path: str, heading: str | None = None) -> str:
    """The page card: title, aliases, summary, description, tags, type and file stem, one per line.

    Values come from frontmatter as written. The title falls back to the page's first `#` heading.
    Non-text values are skipped, and a line equal to an earlier one (ignoring case) is dropped.
    """
    title = _text(frontmatter.get("title")) or (heading or "").strip()
    stem = _STEM_SEPARATORS.sub(" ", PurePosixPath(path).stem).strip()
    lines = (
        title,
        ", ".join(_texts(frontmatter.get("aliases"))),
        _text(frontmatter.get("summary")),
        _text(frontmatter.get("description")),
        ", ".join(_texts(frontmatter.get("tags"))),
        _text(frontmatter.get("type")),
        stem,
    )
    return "\n".join(_unique(line for line in lines if line))


@dataclass(frozen=True)
class _Fragment:
    text: str
    word_count: int
    section_path: tuple[str, ...]
    locator: SourceLocator
    unit_key: str
    block_key: str
    document_order: int
    piece: int
    is_heading: bool


def _fragments(block: ContentBlock, *, max_words: int, first_order: int) -> list[_Fragment]:
    if block.kind == "heading":
        title = block.section_path[-1] if block.section_path else ""
        unit = block.units[0]
        return [
            _Fragment(
                text=title,
                word_count=len(title.split()) + 1,
                section_path=block.section_path,
                locator=unit.source_locator,
                unit_key=unit.stable_key,
                block_key=block.stable_key,
                document_order=first_order,
                piece=0,
                is_heading=True,
            )
        ]
    fragments: list[_Fragment] = []
    for unit in block.units:
        words = unit.text.split()
        if not words:
            continue
        pieces = (
            [unit.text]
            if len(words) <= max_words
            else [" ".join(words[start : start + max_words]) for start in range(0, len(words), max_words)]
        )
        for piece_index, piece in enumerate(pieces):
            fragments.append(
                _Fragment(
                    text=piece,
                    word_count=len(piece.split()),
                    section_path=block.section_path,
                    locator=unit.source_locator,
                    unit_key=unit.stable_key,
                    block_key=block.stable_key,
                    document_order=first_order + len(fragments),
                    piece=piece_index,
                    is_heading=False,
                )
            )
    return fragments


def _draft(window: list[_Fragment], kind: ChunkKind) -> ChunkDraft:
    prefix = _common_prefix(tuple(fragment.section_path for fragment in window))
    text = _join(window, prefix)
    first = window[0]
    last = window[-1]
    return ChunkDraft(
        text=text,
        token_count=len(text.split()),
        section=prefix[-1] if prefix else None,
        anchor=_anchor(prefix[-1]) if prefix else None,
        section_path=prefix,
        source_locators=tuple(dict.fromkeys(fragment.locator for fragment in window)),
        document_order=first.document_order,
        boundary_key="|".join(
            (kind, first.block_key, first.unit_key, str(first.piece), last.block_key, last.unit_key, str(last.piece))
        ),
        chunk_kind=kind,
    )


def _join(window: list[_Fragment], prefix: tuple[str, ...]) -> str:
    """Window text. A heading deeper than the window's section path is kept as a Markdown heading line."""
    result = ""
    previous: _Fragment | None = None
    for fragment in window:
        if fragment.is_heading:
            if len(fragment.section_path) <= len(prefix):
                continue
            if previous is not None and previous.is_heading and previous.section_path == fragment.section_path:
                continue
            text = f"{'#' * min(len(fragment.section_path), 6)} {fragment.text}"
        else:
            text = fragment.text
        if not result:
            result = text
        elif previous is not None and not fragment.is_heading and not previous.is_heading:
            if fragment.unit_key == previous.unit_key:
                result += " " + text
            elif fragment.block_key == previous.block_key:
                result += "\n" + text
            else:
                result += "\n\n" + text
        else:
            result += "\n\n" + text
        previous = fragment
    return result


def _common_prefix(paths: tuple[tuple[str, ...], ...]) -> tuple[str, ...]:
    prefix = paths[0]
    for path in paths[1:]:
        size = 0
        while size < min(len(prefix), len(path)) and prefix[size] == path[size]:
            size += 1
        prefix = prefix[:size]
    return prefix


def _card_locator(document: ExtractedDocument) -> SourceLocator:
    """The lines the card is read from: the frontmatter block, or the first heading or block without one."""
    text = document.source.raw_bytes.decode("utf-8", errors="replace")
    body_start = len(text) - len(document.frontmatter.body)
    if body_start > 0:
        last_line = text[:body_start].rstrip("\n").count("\n") + 1
        return SourceLocator(
            scheme="markdown",
            coordinates=(("line", "1"), ("line_end", str(last_line))),
            start_offset=0,
            end_offset=body_start,
            offset_unit="char",
        )
    blocks = [block for block in document.blocks if block.kind == "heading"] or list(document.blocks)
    if blocks:
        return blocks[0].units[0].source_locator
    return SourceLocator(scheme="markdown", coordinates=(("line", "1"),), offset_unit="none")


def _page_heading(blocks: tuple[ContentBlock, ...]) -> str | None:
    """The page's first top-level heading, the title when frontmatter has none."""
    for block in blocks:
        if block.kind == "heading" and len(block.section_path) == 1:
            return block.section_path[0]
    return None


def _is_template(section_path: tuple[str, ...], page_heading: str | None) -> bool:
    """A section titled like a template section, or one under it. The page title itself never counts."""
    segments = section_path[1:] if section_path and section_path[0] == page_heading else section_path
    return any(segment.strip().casefold() in TEMPLATE_SECTION_TITLES for segment in segments)


def _words(window: list[_Fragment]) -> int:
    return sum(fragment.word_count for fragment in window)


def _text_words(window: list[_Fragment]) -> int:
    return sum(fragment.word_count for fragment in window if not fragment.is_heading)


def _text(value: object) -> str:
    return " ".join(value.split()) if isinstance(value, str) else ""


def _texts(value: object) -> tuple[str, ...]:
    values = [value] if isinstance(value, str) else value if isinstance(value, list) else []
    return _unique(_text(item) for item in values if _text(item))


def _unique(values: Iterable[str]) -> tuple[str, ...]:
    seen: set[str] = set()
    kept: list[str] = []
    for value in values:
        key = value.casefold()
        if key not in seen:
            seen.add(key)
            kept.append(value)
    return tuple(kept)


def _anchor(section: str) -> str:
    slug = re.sub(r"[^a-z0-9가-힣]+", "-", section.strip().lower()).strip("-")
    return slug or "section"
