from __future__ import annotations

import re
from dataclasses import dataclass

HEADING_PATTERN = re.compile(r"^(#{1,6})\s+(.+)$", re.MULTILINE)


@dataclass(frozen=True)
class MarkdownSection:
    heading: str | None
    anchor: str | None
    text: str


def make_anchor(heading: str) -> str:
    lowered = heading.strip().lower()
    slug = re.sub(r"[^a-z0-9가-힣]+", "-", lowered).strip("-")
    return slug or "section"


def parse_sections(markdown_body: str) -> tuple[MarkdownSection, ...]:
    matches = list(HEADING_PATTERN.finditer(markdown_body))
    if not matches:
        stripped = markdown_body.strip()
        return (MarkdownSection(heading=None, anchor=None, text=stripped),) if stripped else ()

    sections: list[MarkdownSection] = []
    preamble = markdown_body[: matches[0].start()].strip()
    if preamble:
        sections.append(MarkdownSection(heading=None, anchor=None, text=preamble))

    for index, match in enumerate(matches):
        heading = match.group(2).strip()
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(markdown_body)
        section_text = markdown_body[start:end].strip()
        if section_text:
            sections.append(MarkdownSection(heading=heading, anchor=make_anchor(heading), text=section_text))
    return tuple(sections)
