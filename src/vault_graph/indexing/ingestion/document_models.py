"""Format-neutral contracts for read-only document extraction."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Literal

from vault_graph.indexing.ingestion.vault_frontmatter_reader import FrontmatterProjection

BlockKind = Literal[
    "heading",
    "paragraph",
    "list",
    "blockquote",
    "code",
    "table",
    "caption",
    "page_break",
    "other",
]
OffsetUnit = Literal["byte", "char", "line", "none"]
WarningSeverity = Literal["info", "warning", "error"]
Coordinate = tuple[str, str]

_BLOCK_KINDS: frozenset[str] = frozenset(
    {
        "heading",
        "paragraph",
        "list",
        "blockquote",
        "code",
        "table",
        "caption",
        "page_break",
        "other",
    }
)
_OFFSET_UNITS: frozenset[str] = frozenset({"byte", "char", "line", "none"})
_WARNING_SEVERITIES: frozenset[str] = frozenset({"info", "warning", "error"})
_SCHEME_PATTERN = re.compile(r"^[a-z][a-z0-9+.-]*$")
_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")

# Locators are adapter-owned, but common hierarchical coordinates still need a
# deterministic order so their serialized form is stable across readers.
_COORDINATE_KEY_ORDER: tuple[str, ...] = (
    "page",
    "section",
    "block",
    "paragraph",
    "list",
    "table",
    "row",
    "cell",
    "line",
    "byte",
    "char",
    "offset",
)
_COORDINATE_KEY_RANK = {key: rank for rank, key in enumerate(_COORDINATE_KEY_ORDER)}


class DocumentModelError(ValueError):
    """Raised when a format-neutral document model violates its contract."""


@dataclass(frozen=True)
class SourceLocator:
    """A stable, format-specific location for extracted source text."""

    scheme: str
    coordinates: tuple[Coordinate, ...]
    start_offset: int | None = None
    end_offset: int | None = None
    offset_unit: OffsetUnit = "none"

    def __post_init__(self) -> None:
        scheme = _normalize_scheme(self.scheme)
        coordinates = _normalize_coordinates(self.coordinates)
        offset_unit = _normalize_offset_unit(self.offset_unit)
        _validate_offsets(
            start_offset=self.start_offset,
            end_offset=self.end_offset,
            offset_unit=offset_unit,
        )
        object.__setattr__(self, "scheme", scheme)
        object.__setattr__(self, "coordinates", coordinates)
        object.__setattr__(self, "offset_unit", offset_unit)

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-compatible mapping with deterministic coordinate order."""

        return {
            "coordinates": [[key, value] for key, value in self.coordinates],
            "end_offset": self.end_offset,
            "offset_unit": self.offset_unit,
            "scheme": self.scheme,
            "start_offset": self.start_offset,
        }

    def to_json(self) -> str:
        """Serialize the locator without relying on mapping insertion order."""

        return json.dumps(self.to_dict(), ensure_ascii=False, sort_keys=True, separators=(",", ":"))

    @classmethod
    def from_dict(cls, value: object) -> SourceLocator:
        """Restore and validate a locator from the metadata JSON shape."""

        if not isinstance(value, dict):
            raise DocumentModelError("source locator must be a JSON object")
        expected = {"coordinates", "end_offset", "offset_unit", "scheme", "start_offset"}
        if set(value) != expected:
            raise DocumentModelError("source locator has an invalid field set")
        raw_coordinates = value["coordinates"]
        if not isinstance(raw_coordinates, list):
            raise DocumentModelError("source locator coordinates must be a JSON list")
        coordinates: list[Coordinate] = []
        for raw_coordinate in raw_coordinates:
            if not isinstance(raw_coordinate, list) or len(raw_coordinate) != 2:
                raise DocumentModelError("source locator coordinate must be a two-item JSON list")
            key, coordinate_value = raw_coordinate
            if not isinstance(key, str) or not isinstance(coordinate_value, str):
                raise DocumentModelError("source locator coordinate values must be strings")
            coordinates.append((key, coordinate_value))
        scheme = value["scheme"]
        offset_unit = value["offset_unit"]
        if not isinstance(scheme, str) or not isinstance(offset_unit, str):
            raise DocumentModelError("source locator scheme and offset_unit must be strings")
        start_offset = value["start_offset"]
        end_offset = value["end_offset"]
        if start_offset is not None and not isinstance(start_offset, int):
            raise DocumentModelError("source locator start_offset must be an integer or null")
        if end_offset is not None and not isinstance(end_offset, int):
            raise DocumentModelError("source locator end_offset must be an integer or null")
        return cls(
            scheme=scheme,
            coordinates=tuple(coordinates),
            start_offset=start_offset,
            end_offset=end_offset,
            offset_unit=offset_unit,  # type: ignore[arg-type]
        )


@dataclass(frozen=True)
class ContentUnit:
    """Smallest reader-emitted unit that the generic chunker may pack."""

    text: str
    source_locator: SourceLocator
    stable_key: str

    def __post_init__(self) -> None:
        if not isinstance(self.text, str):
            raise DocumentModelError("ContentUnit.text must be a string")
        if not isinstance(self.source_locator, SourceLocator):
            raise DocumentModelError("ContentUnit.source_locator must be a SourceLocator")
        object.__setattr__(self, "stable_key", _require_non_empty_string(self.stable_key, "stable_key"))


@dataclass(frozen=True)
class ContentBlock:
    """Reader-emitted structural block containing one or more safe units."""

    kind: BlockKind
    section_path: tuple[str, ...]
    units: tuple[ContentUnit, ...]
    stable_key: str
    searchable_label: str | None = None

    def __post_init__(self) -> None:
        if self.kind not in _BLOCK_KINDS:
            raise DocumentModelError(f"unsupported ContentBlock.kind: {self.kind!r}")
        section_path = _normalize_section_path(self.section_path)
        if not isinstance(self.units, tuple):
            raise DocumentModelError("ContentBlock.units must be a tuple")
        if not self.units:
            raise DocumentModelError("ContentBlock.units must contain at least one unit")
        for unit in self.units:
            if not isinstance(unit, ContentUnit):
                raise DocumentModelError("ContentBlock.units must contain ContentUnit values")
        searchable_label = self.searchable_label
        if searchable_label is not None:
            searchable_label = searchable_label.strip()
            if not searchable_label:
                raise DocumentModelError("searchable_label must contain non-whitespace text")
        object.__setattr__(self, "section_path", section_path)
        object.__setattr__(self, "stable_key", _require_non_empty_string(self.stable_key, "stable_key"))
        object.__setattr__(self, "searchable_label", searchable_label)


@dataclass(frozen=True)
class SourceDocument:
    """Immutable source bytes and identity passed from the loader to a reader."""

    vault_id: str
    root_path: Path
    path: str
    suffix: str
    raw_bytes: bytes
    raw_sha256: str

    def __post_init__(self) -> None:
        vault_id = _require_non_empty_string(self.vault_id, "vault_id")
        if not isinstance(self.root_path, Path):
            raise DocumentModelError("root_path must be a pathlib.Path")
        path = _normalize_source_path(self.path)
        suffix = _normalize_suffix(self.suffix)
        if not isinstance(self.raw_bytes, bytes):
            raise DocumentModelError("raw_bytes must be bytes")
        raw_sha256 = self.raw_sha256.strip().casefold() if isinstance(self.raw_sha256, str) else ""
        if not _SHA256_PATTERN.fullmatch(raw_sha256):
            raise DocumentModelError("raw_sha256 must be a lowercase SHA-256 digest")
        actual_sha256 = hashlib.sha256(self.raw_bytes).hexdigest()
        if raw_sha256 != actual_sha256:
            raise DocumentModelError("raw_sha256 does not match raw_bytes")
        object.__setattr__(self, "vault_id", vault_id)
        object.__setattr__(self, "path", path)
        object.__setattr__(self, "suffix", suffix)
        object.__setattr__(self, "raw_sha256", raw_sha256)


@dataclass(frozen=True)
class ExtractionWarning:
    """Non-fatal diagnostic emitted by a reader while preserving read-only flow."""

    code: str
    message: str
    severity: WarningSeverity = "warning"

    def __post_init__(self) -> None:
        if self.severity not in _WARNING_SEVERITIES:
            raise DocumentModelError(f"unsupported extraction warning severity: {self.severity!r}")
        object.__setattr__(self, "code", _require_non_empty_string(self.code, "code"))
        object.__setattr__(self, "message", _require_non_empty_string(self.message, "message"))


@dataclass(frozen=True)
class ExtractedDocument:
    """Common reader output consumed by the format-neutral chunker."""

    source: SourceDocument
    format: str
    reader_name: str
    reader_version: str
    parser_version: str
    extraction_options_digest: str
    frontmatter: FrontmatterProjection
    blocks: tuple[ContentBlock, ...]
    warnings: tuple[ExtractionWarning, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.source, SourceDocument):
            raise DocumentModelError("source must be a SourceDocument")
        if not isinstance(self.frontmatter, FrontmatterProjection):
            raise DocumentModelError("frontmatter must be a FrontmatterProjection")
        if not isinstance(self.blocks, tuple):
            raise DocumentModelError("blocks must be a tuple")
        if not isinstance(self.warnings, tuple):
            raise DocumentModelError("warnings must be a tuple")
        for block in self.blocks:
            if not isinstance(block, ContentBlock):
                raise DocumentModelError("blocks must contain ContentBlock values")
        for warning in self.warnings:
            if not isinstance(warning, ExtractionWarning):
                raise DocumentModelError("warnings must contain ExtractionWarning values")
        block_keys = tuple(block.stable_key for block in self.blocks)
        if len(block_keys) != len(set(block_keys)):
            raise DocumentModelError("blocks must have unique stable_key values")
        object.__setattr__(self, "format", _require_non_empty_string(self.format, "format").casefold())
        object.__setattr__(self, "reader_name", _require_non_empty_string(self.reader_name, "reader_name"))
        object.__setattr__(self, "reader_version", _require_non_empty_string(self.reader_version, "reader_version"))
        object.__setattr__(self, "parser_version", _require_non_empty_string(self.parser_version, "parser_version"))
        object.__setattr__(
            self,
            "extraction_options_digest",
            _require_non_empty_string(self.extraction_options_digest, "extraction_options_digest"),
        )


def _normalize_scheme(value: str) -> str:
    if not isinstance(value, str):
        raise DocumentModelError("scheme must be a string")
    normalized = value.strip().casefold()
    if not _SCHEME_PATTERN.fullmatch(normalized):
        raise DocumentModelError("scheme must be a URI-like lowercase identifier")
    return normalized


def _normalize_coordinates(value: tuple[Coordinate, ...]) -> tuple[Coordinate, ...]:
    if not isinstance(value, tuple):
        raise DocumentModelError("coordinates must be a tuple")
    if not value:
        raise DocumentModelError("coordinates must contain at least one coordinate")
    normalized: list[Coordinate] = []
    seen_keys: set[str] = set()
    for coordinate in value:
        if not isinstance(coordinate, tuple) or len(coordinate) != 2:
            raise DocumentModelError("each coordinate must be a (key, value) tuple")
        key, coordinate_value = coordinate
        key = _require_non_empty_string(key, "coordinate key").casefold()
        coordinate_value = _require_non_empty_string(coordinate_value, "coordinate value")
        if key in seen_keys:
            raise DocumentModelError(f"coordinate key must be unique: {key!r}")
        seen_keys.add(key)
        normalized.append((key, coordinate_value))
    result = tuple(normalized)
    if result != tuple(sorted(result, key=_coordinate_sort_key)):
        raise DocumentModelError("coordinates must use canonical order")
    return result


def _coordinate_sort_key(coordinate: Coordinate) -> tuple[int, str, str]:
    key, value = coordinate
    return (_COORDINATE_KEY_RANK.get(key, len(_COORDINATE_KEY_ORDER)), key, value)


def _normalize_offset_unit(value: OffsetUnit) -> OffsetUnit:
    if value not in _OFFSET_UNITS:
        raise DocumentModelError(f"unsupported offset_unit: {value!r}")
    return value


def _validate_offsets(*, start_offset: int | None, end_offset: int | None, offset_unit: OffsetUnit) -> None:
    for name, offset in (("start_offset", start_offset), ("end_offset", end_offset)):
        if offset is not None and (not isinstance(offset, int) or isinstance(offset, bool) or offset < 0):
            raise DocumentModelError(f"{name} must be non-negative integer or None")
    if start_offset is not None and end_offset is not None and start_offset > end_offset:
        raise DocumentModelError("start_offset must not exceed end_offset")
    if offset_unit == "none" and (start_offset is not None or end_offset is not None):
        raise DocumentModelError("offset_unit must describe provided offsets")
    if offset_unit != "none" and start_offset is None and end_offset is None:
        raise DocumentModelError("offset_unit requires at least one offset")


def _normalize_section_path(value: tuple[str, ...]) -> tuple[str, ...]:
    if not isinstance(value, tuple):
        raise DocumentModelError("section_path must be a tuple")
    normalized: list[str] = []
    for segment in value:
        if not isinstance(segment, str):
            raise DocumentModelError("section_path segments must be strings")
        segment = segment.strip()
        if segment:
            normalized.append(segment)
    return tuple(normalized)


def _normalize_source_path(value: str) -> str:
    if not isinstance(value, str):
        raise DocumentModelError("path must be a string")
    normalized = value.strip().replace("\\", "/")
    if not normalized or normalized.startswith("/") or "\x00" in normalized:
        raise DocumentModelError("path must be a non-empty relative path")
    path = PurePosixPath(normalized)
    if any(part in {"", ".", ".."} for part in normalized.split("/")) or path.is_absolute():
        raise DocumentModelError("path must not contain empty, '.', or '..' segments")
    return path.as_posix()


def _normalize_suffix(value: str) -> str:
    if not isinstance(value, str):
        raise DocumentModelError("suffix must be a string")
    normalized = value.strip().casefold()
    if normalized and not normalized.startswith("."):
        normalized = f".{normalized}"
    if normalized and ("/" in normalized or "\\" in normalized or normalized == "."):
        raise DocumentModelError("suffix must be a file extension")
    return normalized


def _require_non_empty_string(value: str, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise DocumentModelError(f"{field_name} must contain non-whitespace text")
    return value.strip()
