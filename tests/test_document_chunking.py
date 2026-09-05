from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from vault_graph.ingestion.document_chunking import (
    CHUNKER_VERSION,
    ChunkDraft,
    chunk_document,
    contextual_embedding_text,
)
from vault_graph.ingestion.document_models import (
    ContentBlock,
    ContentUnit,
    ExtractedDocument,
    SourceDocument,
    SourceLocator,
)
from vault_graph.ingestion.markdown_parser import (
    MarkdownSection,
    parse_markdown_blocks,
    parse_markdown_blocks_with_warnings,
    parse_sections,
)
from vault_graph.ingestion.vault_frontmatter_reader import FrontmatterProjection


def _source(path: str, raw: bytes = b"fixture") -> SourceDocument:
    return SourceDocument(
        vault_id="default",
        root_path=Path("/vault"),
        path=path,
        suffix=Path(path).suffix,
        raw_bytes=raw,
        raw_sha256=hashlib.sha256(raw).hexdigest(),
    )


def _document(
    blocks: tuple[ContentBlock, ...],
    *,
    path: str = "wiki/page.md",
    format_name: str = "markdown",
) -> ExtractedDocument:
    return ExtractedDocument(
        source=_source(path),
        format=format_name,
        reader_name=f"{format_name}-fixture-reader",
        reader_version="v1",
        parser_version="fixture-parser-v1",
        extraction_options_digest="fixture-options-v1",
        frontmatter=FrontmatterProjection(data={}, body="", frontmatter_hash="empty"),
        blocks=blocks,
        warnings=(),
    )


def _unit(text: str, *, key: str, scheme: str = "markdown", coordinate: tuple[str, str] = ("line", "1")) -> ContentUnit:
    return ContentUnit(
        text=text,
        source_locator=SourceLocator(scheme=scheme, coordinates=(coordinate,)),
        stable_key=key,
    )


def test_fenced_heading_is_not_parsed_as_heading() -> None:
    blocks = parse_markdown_blocks("```python\n# not a heading\n```\n")

    assert len(blocks) == 1
    assert blocks[0].kind == "code"
    assert blocks[0].section_path == ()
    assert [unit.text for unit in blocks[0].units] == ["```python", "# not a heading", "```"]


def test_nested_headings_and_heading_only_sections_are_structural() -> None:
    blocks = parse_markdown_blocks("# A\n## B\n내용\n")

    assert [block.section_path for block in blocks] == [("A",), ("A", "B"), ("A", "B")]
    assert blocks[0].units[0].text == ""
    assert blocks[-1].units[0].text == "내용"


def test_tables_emit_row_safe_units_and_locators() -> None:
    blocks = parse_markdown_blocks("| A | B |\n| --- | --- |\n| 1 | 2 |\n")

    assert len(blocks) == 1
    assert blocks[0].kind == "table"
    assert len(blocks[0].units) == 3
    assert blocks[0].units[0].source_locator.coordinates == (("line", "1"),)


def test_unterminated_fence_is_retained_with_warning() -> None:
    blocks, warnings = parse_markdown_blocks_with_warnings("~~~\n# code\n")

    assert blocks[0].kind == "code"
    assert blocks[0].units[-1].text == "# code"
    assert warnings[0].code == "unterminated_fence"


def test_parse_sections_preserves_one_legacy_section_per_heading() -> None:
    sections = parse_sections("# A\n\none\n\ntwo\n## B\nthree\n# A\nagain\n")

    assert sections == (
        MarkdownSection(heading="A", anchor="a", text="one\n\ntwo"),
        MarkdownSection(heading="B", anchor="b", text="three"),
        MarkdownSection(heading="A", anchor="a", text="again"),
    )


def test_chunker_is_format_neutral_and_preserves_all_locators() -> None:
    pdf_locator = SourceLocator(scheme="pdf", coordinates=(("page", "4"), ("block", "2")))
    docx_locator = SourceLocator(scheme="docx", coordinates=(("paragraph", "3"),))
    blocks = (
        ContentBlock(
            kind="paragraph",
            section_path=("Architecture",),
            units=(
                ContentUnit(text="first", source_locator=pdf_locator, stable_key="pdf-1"),
                ContentUnit(text="second", source_locator=docx_locator, stable_key="docx-1"),
            ),
            stable_key="block-1",
        ),
    )

    drafts = chunk_document(_document(blocks, path="wiki/mixed.md"), max_tokens=10)

    assert drafts == (
        ChunkDraft(
            text="first\nsecond",
            token_count=2,
            section="Architecture",
            anchor="architecture",
            section_path=("Architecture",),
            source_locators=(pdf_locator, docx_locator),
            document_order=0,
            boundary_key=drafts[0].boundary_key,
        ),
    )
    assert contextual_embedding_text(section_path=drafts[0].section_path, text=drafts[0].text) == (
        "Section path: Architecture\n\nfirst\nsecond"
    )


def test_oversized_unit_is_split_without_overlap() -> None:
    document = _document(
        (
            ContentBlock(
                kind="paragraph",
                section_path=(),
                units=(_unit("one two three four five", key="large"),),
                stable_key="large-block",
            ),
        )
    )

    drafts = chunk_document(document, max_tokens=2)

    assert [draft.text for draft in drafts] == ["one two", "three four", "five"]
    assert all(draft.token_count <= 2 for draft in drafts)
    assert [draft.document_order for draft in drafts] == [0, 1, 2]


@pytest.mark.parametrize(
    ("format_name", "path", "locators"),
    (
        (
            "plaintext",
            "docs/note.txt",
            (SourceLocator(scheme="plaintext", coordinates=(("line", "2"),)),),
        ),
        (
            "pdf",
            "docs/report.pdf",
            (
                SourceLocator(scheme="pdf", coordinates=(("page", "1"), ("offset", "10"))),
                SourceLocator(scheme="pdf", coordinates=(("page", "2"), ("offset", "20"))),
            ),
        ),
        (
            "docx",
            "docs/report.docx",
            (SourceLocator(scheme="docx", coordinates=(("table", "1"), ("row", "2"))),),
        ),
    ),
)
def test_same_planner_accepts_future_reader_locator_shapes(
    format_name: str,
    path: str,
    locators: tuple[SourceLocator, ...],
) -> None:
    block = ContentBlock(
        kind="paragraph",
        section_path=("Report",),
        units=tuple(
            ContentUnit(text=f"unit-{index}", source_locator=locator, stable_key=f"unit-{index}")
            for index, locator in enumerate(locators)
        ),
        stable_key="report-block",
    )

    drafts = chunk_document(_document((block,), path=path, format_name=format_name), max_tokens=10)

    assert len(drafts) == 1
    assert drafts[0].source_locators == locators
    assert drafts[0].section_path == ("Report",)


def test_repeated_planning_is_stable_and_does_not_use_document_order_in_boundary() -> None:
    document = _document(
        (
            ContentBlock(
                kind="paragraph",
                section_path=("A",),
                units=(_unit("body", key="stable-unit"),),
                stable_key="stable-block",
            ),
        )
    )

    first = chunk_document(document)
    second = chunk_document(document)

    assert first == second
    assert first[0].boundary_key == "|".join(
        ("A", "stable-block", "stable-unit", "0", "stable-block", "stable-unit", "0", "1")
    )
    assert CHUNKER_VERSION == "document-block-window-v2"
