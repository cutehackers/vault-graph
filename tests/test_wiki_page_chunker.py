"""Wiki page chunker: page windows, template sections, page card, hub flag (spec 2026-11-05 §10.2 원인7·8)."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from vault_graph.indexing.ingestion.chunker_selection import (
    CHUNKER_VERSIONS,
    embedding_input_for,
    select_chunker,
)
from vault_graph.indexing.ingestion.document_chunking import CHUNKER_VERSION, DocumentChunker, DocumentWindowChunker
from vault_graph.indexing.ingestion.document_models import ExtractedDocument, SourceDocument
from vault_graph.indexing.ingestion.document_normalizer import DocumentNormalizer
from vault_graph.indexing.ingestion.document_readers import MarkdownDocumentReader
from vault_graph.indexing.ingestion.document_snapshots import document_kind_for_path
from vault_graph.indexing.ingestion.wiki_page_chunker import (
    WIKI_PAGE_CHUNKER_VERSION,
    WIKI_PAGE_WINDOW_MAX_WORDS,
    WIKI_PAGE_WINDOW_MIN_WORDS,
    WikiPageChunker,
    page_card_text,
)
from vault_graph.indexing.metadata_indexer import INDEX_CODE_PARTS

_CONCEPT = """---
title: Compiled Knowledge
type: concept
aliases:
  - compiled wiki
summary: "Durable synthesized knowledge produced from sources."
tags:
  - llm-wiki
  - knowledge-quality
---

# Compiled Knowledge

## Definition

Compiled knowledge is durable synthesis extracted from raw sources and human instructions.

## Why It Matters

It keeps the vault from becoming a passive pile of retrieved chunks.

## Claim Evidence

| Claim | Status | Evidence |
| --- | --- | --- |
| Pages carry provenance | stated | raw/sources/a.md |

## Related Concepts

- [[concepts/source-of-truth]]

## Sources

- Human instruction in `AGENTS.md`.

## Change Notes
"""


def _extracted(path: str, text: str) -> ExtractedDocument:
    raw = text.encode("utf-8")
    source = SourceDocument(
        vault_id="default",
        root_path=Path("/vault"),
        path=path,
        suffix=".md",
        raw_bytes=raw,
        raw_sha256=hashlib.sha256(raw).hexdigest(),
    )
    return MarkdownDocumentReader().read(source)


def _long_page(sections: int, words_per_section: int) -> str:
    body = "\n\n".join(
        f"## Part {index}\n\n" + " ".join(f"p{index}w{word}" for word in range(words_per_section))
        for index in range(sections)
    )
    return f"---\ntitle: Long Page\ntype: concept\n---\n\n# Long Page\n\n{body}\n"


@pytest.mark.parametrize(
    "path",
    ["wiki/concepts/compiled-knowledge.md", "wiki/sources/dev-01.md", "wiki/overview.md", "wiki/inbox.md"],
)
def test_curated_and_source_pages_select_the_wiki_page_chunker(path: str) -> None:
    assert isinstance(select_chunker(_extracted(path, _CONCEPT)), WikiPageChunker)


@pytest.mark.parametrize(
    "path",
    ["raw/sources/a.md", "wiki/index.md", "wiki/log.md", "wiki/maps/topics.md", "docs/guide.md", "notes/a.md"],
)
def test_raw_generated_log_and_non_wiki_documents_keep_the_window_chunker(path: str) -> None:
    assert isinstance(select_chunker(_extracted(path, _CONCEPT)), DocumentWindowChunker)


def test_wiki_page_chunker_is_registered_and_enters_the_index_code() -> None:
    chunker = WikiPageChunker()

    assert isinstance(chunker, DocumentChunker)
    assert chunker.version == WIKI_PAGE_CHUNKER_VERSION != CHUNKER_VERSION
    assert WIKI_PAGE_CHUNKER_VERSION in CHUNKER_VERSIONS
    assert WIKI_PAGE_CHUNKER_VERSION in INDEX_CODE_PARTS


def test_short_page_becomes_one_card_one_body_window_and_one_template_window() -> None:
    normalized = DocumentNormalizer().normalize(_extracted("wiki/concepts/compiled-knowledge.md", _CONCEPT))

    kinds = [chunk.chunk_kind for chunk in normalized.chunks]
    assert kinds == ["page_card", "body", "template"]
    assert all(chunk.chunker_version == WIKI_PAGE_CHUNKER_VERSION for chunk in normalized.chunks)
    card, body, template = normalized.chunks

    assert card.text == (
        "Compiled Knowledge\n"
        "compiled wiki\n"
        "Durable synthesized knowledge produced from sources.\n"
        "llm-wiki, knowledge-quality\n"
        "concept"
    )
    assert body.section_path == ("Compiled Knowledge",)
    assert body.text == (
        "## Definition\n\n"
        "Compiled knowledge is durable synthesis extracted from raw sources and human instructions.\n\n"
        "## Why It Matters\n\n"
        "It keeps the vault from becoming a passive pile of retrieved chunks."
    )
    assert "Claim Evidence" in template.text and "Human instruction" in template.text
    assert "source-of-truth" in template.text
    for chunk in (card, body):
        assert "Claim" not in embedding_input_for(chunk)
        assert "AGENTS.md" not in embedding_input_for(chunk)
    assert embedding_input_for(card) == card.text
    assert embedding_input_for(body).startswith("Section path: Compiled Knowledge\n\n## Definition")
    assert len({chunk.document_order for chunk in normalized.chunks}) == 3
    assert card.document_order == 0
    assert all(chunk.token_count == len(chunk.text.split()) for chunk in normalized.chunks)


def test_page_card_uses_frontmatter_values_and_file_stem_mechanically() -> None:
    frontmatter = {
        "title": "개발 서비스 아이디어",
        "aliases": ["dev ideas", "Dev Ideas"],
        "description": "A list.",
        "tags": "ideas",
        "type": "source",
    }

    assert page_card_text(frontmatter, path="wiki/sources/2026-10-06-development-service-ideas.md") == (
        "개발 서비스 아이디어\ndev ideas\nA list.\nideas\nsource\n2026 10 06 development service ideas"
    )
    assert page_card_text({}, path="wiki/concepts/source-of-truth.md", heading="Source of Truth") == ("Source of Truth")
    assert page_card_text({}, path="wiki/concepts/source-of-truth.md") == "source of truth"
    assert page_card_text({"title": 3, "tags": [None, "a"]}, path="wiki/x.md") == "a\nx"


def test_empty_and_tiny_sections_merge_and_no_window_is_empty() -> None:
    text = (
        "---\ntitle: Tiny\n---\n\n# Tiny\n\n## Empty\n\n## Four\n\none two three four\n\n"
        "## Five\n\none two three four five\n\n## Last\n"
    )

    chunks = DocumentNormalizer().normalize(_extracted("wiki/concepts/tiny.md", text)).chunks
    bodies = [chunk for chunk in chunks if chunk.chunk_kind == "body"]

    assert len(bodies) == 1
    assert bodies[0].text == (
        "## Empty\n\n## Four\n\none two three four\n\n## Five\n\none two three four five\n\n## Last"
    )
    assert all(chunk.text.strip() for chunk in chunks)


def test_page_with_only_headings_keeps_just_its_card() -> None:
    chunks = DocumentNormalizer().normalize(_extracted("wiki/concepts/x.md", "# X\n\n## Change Notes\n")).chunks

    assert [chunk.chunk_kind for chunk in chunks] == ["page_card"]
    assert chunks[0].text == "X"


def test_long_page_is_windowed_within_the_budget_and_a_short_tail_joins_the_previous_window() -> None:
    sections = 7
    words = 60
    chunks = DocumentNormalizer().normalize(_extracted("wiki/concepts/long.md", _long_page(sections, words))).chunks
    bodies = [chunk for chunk in chunks if chunk.chunk_kind == "body"]

    content_words = [word for chunk in bodies for word in chunk.text.split() if word.startswith("p")]
    assert content_words == [f"p{index}w{word}" for index in range(sections) for word in range(words)]
    assert len(bodies) >= 2
    longest = WIKI_PAGE_WINDOW_MAX_WORDS + WIKI_PAGE_WINDOW_MIN_WORDS
    for chunk in bodies:
        assert WIKI_PAGE_WINDOW_MIN_WORDS <= chunk.token_count <= longest
    assert [chunk.document_order for chunk in bodies] == sorted(chunk.document_order for chunk in bodies)


def test_one_section_longer_than_the_budget_is_cut_at_word_boundaries() -> None:
    words = WIKI_PAGE_WINDOW_MAX_WORDS * 2 + 10
    chunks = DocumentNormalizer().normalize(_extracted("wiki/concepts/long.md", _long_page(1, words))).chunks
    bodies = [chunk for chunk in chunks if chunk.chunk_kind == "body"]

    assert len(bodies) == 2
    assert all(chunk.token_count <= WIKI_PAGE_WINDOW_MAX_WORDS + WIKI_PAGE_WINDOW_MIN_WORDS for chunk in bodies)
    assert [w for chunk in bodies for w in chunk.text.split() if w.startswith("p0w")] == [
        f"p0w{index}" for index in range(words)
    ]
    assert bodies[1].section_path == ("Long Page", "Part 0")


def test_same_page_gives_the_same_ids_text_and_locators_and_ids_differ_from_other_vaults() -> None:
    def view(vault_path: str) -> list[tuple[object, ...]]:
        normalized = DocumentNormalizer().normalize(_extracted(vault_path, _CONCEPT))
        return [
            (chunk.chunk_id, chunk.text, chunk.chunk_kind, tuple(loc.to_json() for loc in chunk.source_locators))
            for chunk in normalized.chunks
        ]

    first = view("wiki/concepts/compiled-knowledge.md")
    assert first == view("wiki/concepts/compiled-knowledge.md")
    assert len({row[0] for row in first}) == len(first)
    assert {row[0] for row in first}.isdisjoint({row[0] for row in view("wiki/concepts/other.md")})
    assert all(row[3] for row in first)


@pytest.mark.parametrize(
    ("path", "kind"),
    [
        ("wiki/overview.md", "hub"),
        ("wiki/index.md", "hub"),
        ("wiki/log.md", "hub"),
        ("wiki/inbox.md", "hub"),
        ("wiki/maps/topics.md", "hub"),
        ("wiki/maps/sub/topics.md", "hub"),
        ("wiki/concepts/overview.md", "regular"),
        ("raw/sources/wiki/overview.md", "regular"),
        ("overview.md", "regular"),
    ],
)
def test_hub_pages_are_flagged_on_the_document_and_every_chunk(path: str, kind: str) -> None:
    normalized = DocumentNormalizer().normalize(_extracted(path, _CONCEPT))

    assert document_kind_for_path(path) == kind
    assert normalized.document.document_kind == kind
    assert {chunk.document_kind for chunk in normalized.chunks} == {kind}


def test_page_card_points_at_the_frontmatter_lines_or_the_first_heading() -> None:
    with_frontmatter = DocumentNormalizer().normalize(_extracted("wiki/concepts/compiled-knowledge.md", _CONCEPT))
    without = DocumentNormalizer().normalize(_extracted("wiki/concepts/x.md", "\n# X\n\nBody text here.\n"))

    (card_locator,) = with_frontmatter.chunks[0].source_locators
    assert card_locator.coordinates == (("line", "1"), ("line_end", "10"))
    assert (card_locator.start_offset, card_locator.offset_unit) == (0, "char")
    assert _CONCEPT[: card_locator.end_offset].endswith("---\n")
    (heading_locator,) = without.chunks[0].source_locators
    assert heading_locator.coordinates == (("line", "2"),)
