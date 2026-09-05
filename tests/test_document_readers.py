from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

import pytest

from vault_graph.ingestion.document_chunking import DocumentChunker
from vault_graph.ingestion.document_models import (
    ContentBlock,
    ContentUnit,
    ExtractedDocument,
    SourceDocument,
    SourceLocator,
)
from vault_graph.ingestion.document_readers import (
    DocumentReaderRegistry,
    DuplicateDocumentReaderError,
    MarkdownDocumentReader,
    UnsupportedDocumentFormatError,
)
from vault_graph.ingestion.vault_frontmatter_reader import FrontmatterProjection


def _source(path: str) -> SourceDocument:
    raw = b"content"
    return SourceDocument(
        vault_id="demo",
        root_path=Path("/vault"),
        path=path,
        suffix=Path(path).suffix,
        raw_bytes=raw,
        raw_sha256=hashlib.sha256(raw).hexdigest(),
    )


@dataclass(frozen=True)
class FakeReader:
    name: str = "fake-reader"
    version: str = "fake-reader-v1"
    suffixes: tuple[str, ...] = (".md", ".txt")

    def read(self, source: SourceDocument) -> ExtractedDocument:
        unit = ContentUnit(
            text="content",
            source_locator=SourceLocator(scheme="fake", coordinates=(("block", "1"),)),
            stable_key="content-1",
        )
        return ExtractedDocument(
            source=source,
            format="fake",
            reader_name=self.name,
            reader_version=self.version,
            parser_version="fake-parser-v1",
            extraction_options_digest="fake-options-v1",
            frontmatter=FrontmatterProjection(data={}, body="content", frontmatter_hash="empty"),
            blocks=(ContentBlock(kind="paragraph", section_path=(), units=(unit,), stable_key="block-1"),),
            warnings=(),
        )


def test_registry_selects_reader_by_normalized_suffix_and_reads_source() -> None:
    reader = FakeReader()
    registry = DocumentReaderRegistry((reader,))
    source = _source("notes/example.MD")

    assert registry.reader_for(source) is reader
    assert registry.read(source).source == source


def test_registry_rejects_duplicate_suffixes_and_unsupported_formats() -> None:
    with pytest.raises(DuplicateDocumentReaderError, match=r"\.md"):
        DocumentReaderRegistry((FakeReader(), FakeReader(name="other-reader")))

    registry = DocumentReaderRegistry((FakeReader(),))
    with pytest.raises(UnsupportedDocumentFormatError, match=r"\.pdf") as exc_info:
        registry.reader_for(_source("notes/example.pdf"))

    assert exc_info.value.suffix == ".pdf"
    assert exc_info.value.supported_suffixes == (".md", ".txt")


def test_markdown_reader_keeps_locators_relative_to_the_original_source() -> None:
    text = "---\ntitle: Demo\ntype: source\n---\n# Heading\n\nfirst line\nsecond line\n"
    raw = text.encode("utf-8")
    source = SourceDocument(
        vault_id="demo",
        root_path=Path("/vault"),
        path="notes/example.md",
        suffix=".md",
        raw_bytes=raw,
        raw_sha256=hashlib.sha256(raw).hexdigest(),
    )

    extracted = MarkdownDocumentReader().read(source)
    heading_locator = extracted.blocks[0].units[0].source_locator
    paragraph_locator = extracted.blocks[1].units[0].source_locator

    heading_start = text.index("# Heading")
    paragraph_start = text.index("first line")
    paragraph_end = text.index("second line") + len("second line")

    assert heading_locator.coordinates == (("line", "5"),)
    assert heading_locator.start_offset == heading_start
    assert heading_locator.end_offset == heading_start + len("# Heading")
    assert text[heading_locator.start_offset : heading_locator.end_offset] == "# Heading"

    assert paragraph_locator.coordinates == (("line", "7"), ("line_end", "8"))
    assert paragraph_locator.start_offset == paragraph_start
    assert paragraph_locator.end_offset == paragraph_end
    assert text[paragraph_locator.start_offset : paragraph_locator.end_offset] == "first line\nsecond line"


def test_document_chunker_protocol_is_independent_of_chunk_result_shape() -> None:
    @dataclass(frozen=True)
    class FakeChunker:
        version: str = "fake-chunker-v1"

        def chunk(self, document: ExtractedDocument) -> tuple[str, ...]:
            return (document.source.path,)

    chunker = FakeChunker()
    assert isinstance(chunker, DocumentChunker)
    assert chunker.chunk(_source_document()) == ("notes/example.md",)


def _source_document() -> ExtractedDocument:
    return FakeReader().read(_source("notes/example.md"))
