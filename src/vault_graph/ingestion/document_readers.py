"""Read-only document reader contracts and suffix registry."""

from __future__ import annotations

import hashlib
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Protocol, runtime_checkable

from vault_graph.ingestion.document_models import ExtractedDocument, SourceDocument
from vault_graph.ingestion.markdown_parser import PARSER_VERSION, parse_markdown_blocks_with_warnings
from vault_graph.ingestion.vault_frontmatter_reader import read_frontmatter


class DocumentReaderError(ValueError):
    """Raised when a reader or reader registry violates its contract."""


class DuplicateDocumentReaderError(DocumentReaderError):
    """Raised when two readers claim the same normalized suffix."""

    def __init__(self, suffix: str) -> None:
        self.suffix = suffix
        super().__init__(f"document reader suffix is already registered: {suffix}")


class UnsupportedDocumentFormatError(DocumentReaderError):
    """Raised when no registered reader supports a source suffix."""

    def __init__(self, suffix: str, supported_suffixes: tuple[str, ...]) -> None:
        self.suffix = suffix
        self.supported_suffixes = supported_suffixes
        supported = ", ".join(supported_suffixes) or "none"
        super().__init__(f"unsupported document format {suffix!r}; supported suffixes: {supported}")


@runtime_checkable
class DocumentReader(Protocol):
    """Minimal read-only adapter implemented by each document format."""

    @property
    def name(self) -> str: ...

    @property
    def version(self) -> str: ...

    @property
    def suffixes(self) -> tuple[str, ...]: ...

    def read(self, source: SourceDocument) -> ExtractedDocument: ...


class DocumentReaderRegistry:
    """Immutable-by-construction suffix registry for document readers."""

    def __init__(self, readers: Iterable[DocumentReader] = ()) -> None:
        normalized_readers = tuple(readers)
        readers_by_suffix: dict[str, DocumentReader] = {}
        for reader in normalized_readers:
            if not isinstance(reader, DocumentReader):
                raise DocumentReaderError("reader must implement DocumentReader")
            for suffix in _reader_suffixes(reader):
                if suffix in readers_by_suffix:
                    raise DuplicateDocumentReaderError(suffix)
                readers_by_suffix[suffix] = reader
        self._readers = normalized_readers
        self._readers_by_suffix: Mapping[str, DocumentReader] = MappingProxyType(readers_by_suffix)

    @classmethod
    def markdown_default(cls) -> DocumentReaderRegistry:
        """Build the default registry without importing optional readers."""

        default_reader: DocumentReader = MarkdownDocumentReader()
        return cls((default_reader,))

    @property
    def readers(self) -> tuple[DocumentReader, ...]:
        return self._readers

    @property
    def supported_suffixes(self) -> tuple[str, ...]:
        return tuple(sorted(self._readers_by_suffix))

    def register(self, reader: DocumentReader) -> DocumentReaderRegistry:
        """Return a new registry with ``reader`` added."""

        return DocumentReaderRegistry((*self._readers, reader))

    def select(self, suffix: str) -> DocumentReader:
        """Select the reader for a suffix without importing optional adapters."""

        normalized_suffix = _normalize_suffix(suffix)
        reader = self._readers_by_suffix.get(normalized_suffix)
        if reader is None:
            raise UnsupportedDocumentFormatError(normalized_suffix, self.supported_suffixes)
        return reader

    def reader_for(self, source: SourceDocument) -> DocumentReader:
        """Select the reader for an immutable source document."""

        return self.select(source.suffix)

    def read(self, source: SourceDocument) -> ExtractedDocument:
        """Read ``source`` through its selected adapter and validate its output."""

        extracted = self.reader_for(source).read(source)
        if not isinstance(extracted, ExtractedDocument):
            raise DocumentReaderError("reader.read must return an ExtractedDocument")
        if extracted.source != source:
            raise DocumentReaderError("reader output must retain the input SourceDocument")
        return extracted


def _reader_suffixes(reader: DocumentReader) -> tuple[str, ...]:
    suffixes = reader.suffixes
    if not isinstance(suffixes, tuple) or not suffixes:
        raise DocumentReaderError("reader.suffixes must be a non-empty tuple")
    normalized = tuple(_normalize_suffix(suffix) for suffix in suffixes)
    if len(normalized) != len(set(normalized)):
        raise DocumentReaderError("reader.suffixes must not contain duplicates")
    return normalized


def _normalize_suffix(value: str) -> str:
    if not isinstance(value, str):
        raise DocumentReaderError("reader suffix must be a string")
    normalized = value.strip().casefold()
    if normalized and not normalized.startswith("."):
        normalized = f".{normalized}"
    if not normalized or "/" in normalized or "\\" in normalized or normalized == ".":
        raise DocumentReaderError("reader suffix must be a non-empty file extension")
    return normalized


@dataclass(frozen=True)
class MarkdownDocumentReader:
    """Deterministic UTF-8 Markdown adapter for the initial reader set."""

    name: str = "markdown"
    version: str = "markdown-reader-v2"
    suffixes: tuple[str, ...] = (".md",)

    def read(self, source: SourceDocument) -> ExtractedDocument:
        try:
            text = source.raw_bytes.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise DocumentReaderError(f"Markdown source is not valid UTF-8: {source.path}") from exc
        frontmatter = read_frontmatter(text)
        body_start = len(text) - len(frontmatter.body)
        blocks, warnings = parse_markdown_blocks_with_warnings(
            frontmatter.body,
            line_number_offset=text[:body_start].count("\n"),
            character_offset=body_start,
        )
        return ExtractedDocument(
            source=source,
            format="markdown",
            reader_name=self.name,
            reader_version=self.version,
            parser_version=PARSER_VERSION,
            extraction_options_digest=_MARKDOWN_EXTRACTION_OPTIONS_DIGEST,
            frontmatter=frontmatter,
            blocks=blocks,
            warnings=warnings,
        )


_MARKDOWN_EXTRACTION_OPTIONS_DIGEST = hashlib.sha256(
    b"markdown:structural-blocks-v2:fence-aware:table-row-units:utf8"
).hexdigest()
