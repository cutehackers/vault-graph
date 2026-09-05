from __future__ import annotations

import hashlib
import json
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from vault_graph.ingestion.document_models import (
    ContentBlock,
    ContentUnit,
    ExtractedDocument,
    ExtractionWarning,
    SourceDocument,
    SourceLocator,
)
from vault_graph.ingestion.vault_frontmatter_reader import FrontmatterProjection


def _source(*, path: str = "notes/example.md", raw: bytes = b"# Example\n") -> SourceDocument:
    return SourceDocument(
        vault_id="demo",
        root_path=Path("/vault"),
        path=path,
        suffix=Path(path).suffix,
        raw_bytes=raw,
        raw_sha256=hashlib.sha256(raw).hexdigest(),
    )


def _unit(*, locator: SourceLocator | None = None, stable_key: str = "unit-1") -> ContentUnit:
    return ContentUnit(
        text="A paragraph.",
        source_locator=locator
        or SourceLocator(
            scheme="markdown",
            coordinates=(("block", "1"),),
        ),
        stable_key=stable_key,
    )


def test_source_locator_accepts_pdf_coordinates_and_serializes_deterministically() -> None:
    locator = SourceLocator(
        scheme="pdf",
        coordinates=(("page", "4"), ("block", "2")),
        start_offset=120,
        end_offset=188,
        offset_unit="char",
    )

    assert locator.coordinates == (("page", "4"), ("block", "2"))
    assert locator.start_offset == 120
    assert locator.end_offset == 188
    assert locator.to_json() == locator.to_json()
    assert json.loads(locator.to_json()) == {
        "coordinates": [["page", "4"], ["block", "2"]],
        "end_offset": 188,
        "offset_unit": "char",
        "scheme": "pdf",
        "start_offset": 120,
    }
    with pytest.raises(FrozenInstanceError):
        locator.scheme = "markdown"  # type: ignore[misc]


@pytest.mark.parametrize(
    ("kwargs", "message"),
    (
        ({"start_offset": -1}, "start_offset must be non-negative"),
        ({"start_offset": 10, "end_offset": 9, "offset_unit": "char"}, "start_offset must not exceed"),
        (
            {"coordinates": (("block", "2"), ("page", "4"))},
            "coordinates must use canonical order",
        ),
    ),
)
def test_source_locator_rejects_invalid_offsets_and_coordinate_order(kwargs: dict[str, object], message: str) -> None:
    base = {
        "scheme": "pdf",
        "coordinates": (("page", "4"), ("block", "2")),
        "offset_unit": "char",
        "start_offset": 120,
        "end_offset": 188,
    }
    base.update(kwargs)

    with pytest.raises(ValueError, match=message):
        SourceLocator(**base)  # type: ignore[arg-type]


def test_content_block_normalizes_section_path_and_requires_units() -> None:
    block = ContentBlock(
        kind="paragraph",
        section_path=(" Architecture ", "", " Retrieval "),
        units=(_unit(),),
        stable_key="block-1",
        searchable_label=" Retrieval ",
    )

    assert block.section_path == ("Architecture", "Retrieval")
    assert block.searchable_label == "Retrieval"

    with pytest.raises(ValueError, match="units must contain at least one"):
        ContentBlock(kind="paragraph", section_path=(), units=(), stable_key="empty")


def test_extracted_document_keeps_pdf_and_docx_like_locators_without_reader_dependencies() -> None:
    pdf_unit = _unit(
        locator=SourceLocator(
            scheme="pdf",
            coordinates=(("page", "4"), ("block", "2")),
            start_offset=120,
            end_offset=188,
            offset_unit="char",
        ),
        stable_key="pdf-unit",
    )
    docx_unit = _unit(
        locator=SourceLocator(
            scheme="docx",
            coordinates=(("table", "1"), ("row", "2")),
        ),
        stable_key="docx-unit",
    )
    document = ExtractedDocument(
        source=_source(path="notes/example.pdf"),
        format="pdf",
        reader_name="fake-pdf-reader",
        reader_version="1",
        parser_version="pdf-parser-v1",
        extraction_options_digest="options-v1",
        frontmatter=FrontmatterProjection(data={}, body="", frontmatter_hash="empty"),
        blocks=(
            ContentBlock(kind="paragraph", section_path=("Architecture",), units=(pdf_unit,), stable_key="pdf"),
            ContentBlock(kind="table", section_path=("Architecture",), units=(docx_unit,), stable_key="docx"),
        ),
        warnings=(ExtractionWarning(code="fixture", message="synthetic fixture", severity="info"),),
    )

    assert document.blocks[0].units[0].source_locator.scheme == "pdf"
    assert document.blocks[1].units[0].source_locator.coordinates == (("table", "1"), ("row", "2"))
    assert document.warnings[0].severity == "info"
