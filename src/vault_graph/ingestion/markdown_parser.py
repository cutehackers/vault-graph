from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

from vault_graph.ingestion.document_models import (
    ContentBlock,
    ContentUnit,
    ExtractionWarning,
    SourceLocator,
)

PARSER_VERSION = "markdown-structural-blocks-v2"

_HEADING_PATTERN = re.compile(r"^(#{1,6})(?:[ \t]+(.*?)|[ \t]*)$")
_FENCE_PATTERN = re.compile(r"^\s*(`{3,}|~{3,})(.*)$")
_LIST_PATTERN = re.compile(r"^\s*(?:[-+*]|\d+[.)])\s+.+$")
_QUOTE_PATTERN = re.compile(r"^\s*> ?.*$")
_TABLE_SEPARATOR_CELL = re.compile(r"^\s*:?-{3,}:?\s*$")


@dataclass(frozen=True)
class MarkdownSection:
    heading: str | None
    anchor: str | None
    text: str


@dataclass(frozen=True)
class _MarkdownLine:
    number: int
    text: str
    start_offset: int
    end_offset: int


def make_anchor(heading: str) -> str:
    lowered = heading.strip().lower()
    slug = re.sub(r"[^a-z0-9가-힣]+", "-", lowered).strip("-")
    return slug or "section"


def parse_markdown_blocks(
    markdown_body: str,
    *,
    line_number_offset: int = 0,
    character_offset: int = 0,
) -> tuple[ContentBlock, ...]:
    blocks, _ = parse_markdown_blocks_with_warnings(
        markdown_body,
        line_number_offset=line_number_offset,
        character_offset=character_offset,
    )
    return blocks


def parse_markdown_blocks_with_warnings(
    markdown_body: str,
    *,
    line_number_offset: int = 0,
    character_offset: int = 0,
) -> tuple[tuple[ContentBlock, ...], tuple[ExtractionWarning, ...]]:
    lines = _lines(
        markdown_body,
        line_number_offset=line_number_offset,
        character_offset=character_offset,
    )
    if not lines:
        return (), ()

    blocks: list[ContentBlock] = []
    warnings: list[ExtractionWarning] = []
    section_path: tuple[str, ...] = ()
    heading_levels: list[str] = []
    current_section_is_heading = False
    current_section_has_block = False
    occurrence_counts: dict[tuple[str, tuple[str, ...], str], int] = {}

    index = 0
    while index < len(lines):
        line = lines[index]
        if not line.text.strip():
            index += 1
            continue

        heading = _heading(line.text)
        if heading is not None:
            if current_section_is_heading and not current_section_has_block:
                blocks.append(
                    _empty_section_block(
                        section_path=section_path,
                        occurrence_counts=occurrence_counts,
                    )
                )
            level, title = heading
            heading_levels = heading_levels[: level - 1]
            heading_levels.append(title)
            section_path = tuple(heading_levels)
            current_section_is_heading = True
            blocks.append(
                _heading_block(
                    section_path=section_path,
                    line=line,
                    occurrence_counts=occurrence_counts,
                )
            )
            current_section_has_block = True
            index += 1
            continue

        if (fence := _fence(line.text)) is not None:
            consumed, closed = _consume_fence(lines, index, fence)
            code_lines = lines[index:consumed]
            blocks.append(
                _make_block(
                    kind="code",
                    section_path=section_path,
                    lines=code_lines,
                    occurrence_counts=occurrence_counts,
                )
            )
            current_section_has_block = True
            if not closed:
                warnings.append(
                    ExtractionWarning(
                        code="unterminated_fence",
                        message="Markdown fence continues to end of document; remaining lines were retained as code.",
                        severity="warning",
                    )
                )
            index = consumed
            continue

        if _is_table_start(lines, index):
            consumed = _consume_table(lines, index)
            blocks.append(
                _make_block(
                    kind="table",
                    section_path=section_path,
                    lines=lines[index:consumed],
                    occurrence_counts=occurrence_counts,
                )
            )
            current_section_has_block = True
            index = consumed
            continue

        kind, consumed = _consume_other_block(lines, index)
        blocks.append(
            _make_block(
                kind=kind,
                section_path=section_path,
                lines=lines[index:consumed],
                occurrence_counts=occurrence_counts,
            )
        )
        current_section_has_block = True
        index = consumed

    if current_section_is_heading and not current_section_has_block:
        blocks.append(
            _empty_section_block(
                section_path=section_path,
                occurrence_counts=occurrence_counts,
            )
        )
    return tuple(blocks), tuple(warnings)


def parse_sections(markdown_body: str) -> tuple[MarkdownSection, ...]:
    """Return the legacy leaf-heading view used by older ingestion callers."""

    sections: list[MarkdownSection] = []
    current_heading: str | None = None
    current_text: list[str] = []
    current_key: tuple[str | None, tuple[str, ...]] | None = None

    def flush_current() -> None:
        if not current_text:
            return
        text = "\n\n".join(current_text).strip()
        if text:
            sections.append(
                MarkdownSection(
                    heading=current_heading,
                    anchor=make_anchor(current_heading) if current_heading is not None else None,
                    text=text,
                )
            )

    for block in parse_markdown_blocks(markdown_body):
        block_heading = block.section_path[-1] if block.section_path else None
        block_key = (block_heading, block.section_path)
        if block.kind == "heading":
            flush_current()
            current_heading = block_heading
            current_text = []
            current_key = block_key
            continue

        text = "\n".join(unit.text for unit in block.units).strip()
        if not text:
            continue
        if current_key != block_key:
            flush_current()
            current_heading = block_heading
            current_text = []
            current_key = block_key
        current_text.append(text)

    flush_current()
    return tuple(sections)


def _lines(
    markdown_body: str,
    *,
    line_number_offset: int,
    character_offset: int,
) -> tuple[_MarkdownLine, ...]:
    if line_number_offset < 0:
        raise ValueError("line_number_offset must be non-negative")
    if character_offset < 0:
        raise ValueError("character_offset must be non-negative")
    if not markdown_body:
        return ()
    output: list[_MarkdownLine] = []
    offset = 0
    for relative_number, raw_line in enumerate(markdown_body.splitlines(keepends=True), start=1):
        text = raw_line.rstrip("\r\n")
        output.append(
            _MarkdownLine(
                number=relative_number + line_number_offset,
                text=text,
                start_offset=character_offset + offset,
                end_offset=character_offset + offset + len(text),
            )
        )
        offset += len(raw_line)
    if offset < len(markdown_body):
        output.append(
            _MarkdownLine(
                number=len(output) + 1 + line_number_offset,
                text=markdown_body[offset:],
                start_offset=character_offset + offset,
                end_offset=character_offset + len(markdown_body),
            )
        )
    return tuple(output)


def _heading(text: str) -> tuple[int, str] | None:
    match = _HEADING_PATTERN.match(text)
    if match is None:
        return None
    title = (match.group(2) or "").strip()
    if not title:
        return None
    return len(match.group(1)), title


def _fence(text: str) -> tuple[str, int] | None:
    match = _FENCE_PATTERN.match(text)
    if match is None:
        return None
    marker = match.group(1)
    return marker[0], len(marker)


def _consume_fence(
    lines: tuple[_MarkdownLine, ...],
    start: int,
    fence: tuple[str, int],
) -> tuple[int, bool]:
    marker, minimum_length = fence
    for index in range(start + 1, len(lines)):
        candidate = lines[index].text.lstrip()
        if candidate.startswith(marker * minimum_length) and set(candidate.rstrip()) <= {marker}:
            return index + 1, True
    return len(lines), False


def _is_table_start(lines: tuple[_MarkdownLine, ...], index: int) -> bool:
    if index + 1 >= len(lines):
        return False
    header = lines[index].text
    separator = lines[index + 1].text
    if "|" not in header or "|" not in separator:
        return False
    cells = _table_cells(separator)
    return bool(cells) and all(_TABLE_SEPARATOR_CELL.match(cell) for cell in cells)


def _consume_table(lines: tuple[_MarkdownLine, ...], start: int) -> int:
    index = start
    while index < len(lines) and lines[index].text.strip() and "|" in lines[index].text:
        index += 1
    return index


def _consume_other_block(lines: tuple[_MarkdownLine, ...], start: int) -> tuple[str, int]:
    first = lines[start].text
    if _LIST_PATTERN.match(first):
        kind = "list"
        predicate = _LIST_PATTERN.match
    elif _QUOTE_PATTERN.match(first):
        kind = "blockquote"
        predicate = _QUOTE_PATTERN.match
    else:
        kind = "paragraph"
        predicate = None

    index = start + 1
    while index < len(lines) and lines[index].text.strip():
        candidate = lines[index].text
        if _heading(candidate) is not None or _fence(candidate) is not None or _is_table_start(lines, index):
            break
        if kind == "paragraph" and (_LIST_PATTERN.match(candidate) or _QUOTE_PATTERN.match(candidate)):
            break
        if predicate is not None and not predicate(candidate) and not candidate.startswith((" ", "\t")):
            break
        index += 1
    return kind, index


def _make_block(
    *,
    kind: str,
    section_path: tuple[str, ...],
    lines: tuple[_MarkdownLine, ...],
    occurrence_counts: dict[tuple[str, tuple[str, ...], str], int],
) -> ContentBlock:
    units: list[ContentUnit] = []
    for fragment_index, line in enumerate(_unit_lines(kind, lines)):
        text = line.text
        key = (kind, section_path, text)
        occurrence = occurrence_counts.get(key, 0)
        occurrence_counts[key] = occurrence + 1
        locator_lines = lines if kind not in {"code", "table"} else (line,)
        units.append(
            ContentUnit(
                text=text,
                source_locator=_locator_for_lines(lines=locator_lines),
                stable_key=_stable_key("unit", kind, section_path, text, occurrence, fragment_index),
            )
        )
    block_text = "\n".join(unit.text for unit in units)
    block_occurrence = _next_block_occurrence(occurrence_counts, kind, section_path, block_text)
    block_key = _stable_key("block", kind, section_path, block_text, block_occurrence)
    return ContentBlock(
        kind=kind,  # type: ignore[arg-type]
        section_path=section_path,
        units=tuple(units),
        stable_key=block_key,
        searchable_label=section_path[-1] if section_path else None,
    )


def _empty_section_block(
    *,
    section_path: tuple[str, ...],
    occurrence_counts: dict[tuple[str, tuple[str, ...], str], int],
) -> ContentBlock:
    key = ("heading", section_path, "")
    occurrence = occurrence_counts.get(key, 0)
    occurrence_counts[key] = occurrence + 1
    unit = ContentUnit(
        text="",
        source_locator=SourceLocator(
            scheme="markdown",
            coordinates=(("section", ">".join(section_path)),),
            offset_unit="none",
        ),
        stable_key=_stable_key("unit", "heading", section_path, "", occurrence, 0),
    )
    return ContentBlock(
        kind="heading",
        section_path=section_path,
        units=(unit,),
        stable_key=_stable_key("block", "heading", section_path, "", occurrence),
        searchable_label=section_path[-1] if section_path else None,
    )


def _heading_block(
    *,
    section_path: tuple[str, ...],
    line: _MarkdownLine,
    occurrence_counts: dict[tuple[str, tuple[str, ...], str], int],
) -> ContentBlock:
    title = section_path[-1] if section_path else ""
    key = ("heading", section_path, title)
    occurrence = occurrence_counts.get(key, 0)
    occurrence_counts[key] = occurrence + 1
    unit = ContentUnit(
        text="",
        source_locator=_locator_for_lines(lines=(line,)),
        stable_key=_stable_key("unit", "heading", section_path, title, occurrence),
    )
    return ContentBlock(
        kind="heading",
        section_path=section_path,
        units=(unit,),
        stable_key=_stable_key("block", "heading", section_path, title, occurrence),
        searchable_label=title or None,
    )


def _unit_lines(kind: str, lines: tuple[_MarkdownLine, ...]) -> tuple[_MarkdownLine, ...]:
    if kind in {"code", "table"}:
        return lines
    return (
        _MarkdownLine(
            number=lines[0].number,
            text="\n".join(line.text for line in lines),
            start_offset=lines[0].start_offset,
            end_offset=lines[-1].end_offset,
        ),
    )


def _locator_for_lines(*, lines: tuple[_MarkdownLine, ...]) -> SourceLocator:
    coordinates = [("line", str(lines[0].number))]
    if lines[-1].number != lines[0].number:
        coordinates.append(("line_end", str(lines[-1].number)))
    return SourceLocator(
        scheme="markdown",
        coordinates=tuple(coordinates),
        start_offset=lines[0].start_offset,
        end_offset=lines[-1].end_offset,
        offset_unit="char",
    )


def _table_cells(text: str) -> tuple[str, ...]:
    stripped = text.strip()
    if stripped.startswith("|"):
        stripped = stripped[1:]
    if stripped.endswith("|"):
        stripped = stripped[:-1]
    return tuple(cell.strip() for cell in stripped.split("|"))


def _next_block_occurrence(
    occurrence_counts: dict[tuple[str, tuple[str, ...], str], int],
    kind: str,
    section_path: tuple[str, ...],
    text: str,
) -> int:
    key = (f"block:{kind}", section_path, text)
    occurrence = occurrence_counts.get(key, 0)
    occurrence_counts[key] = occurrence + 1
    return occurrence


def _stable_key(
    prefix: str,
    kind: str,
    section_path: tuple[str, ...],
    text: str,
    occurrence: int,
    fragment: int = 0,
) -> str:
    payload = "\x1f".join((prefix, kind, "\x1e".join(section_path), text, str(occurrence), str(fragment)))
    return f"markdown-{hashlib.sha256(payload.encode('utf-8')).hexdigest()}"
