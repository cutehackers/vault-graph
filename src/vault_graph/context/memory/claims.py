"""Claim rows of a Vault page, and the rule that leaves out ``superseded`` rows (spec 2026-11-05 §4.4.6).

The table format is the Vault's own (``vault-builder:docs/agent/OPERATING-SCHEMA.md:192-200``,
``docs/agent/DRAFTS.md``): the first table whose header has ``Claim``, ``Status`` and ``Evidence``
columns, outside code fences. Row statuses are ``stated``, ``inferred``, ``contested``,
``deprecated`` and ``superseded``. Header matching and row splitting follow the Vault lint
(``vault-builder:tools/wiki/lib/lint.py`` ``claim_evidence_table``).

The body read here is usually the indexed body: chunks joined with ``## <section>`` lines. The
chunker cuts a long table into several chunks of the same section, and only the first keeps the
header. Rows that come right after a repeat of the table's own section heading are read as the same
table.

When the table cannot be read (no separator line under the header, a short row, an unknown status),
the page is used whole: no row is left out, and ``claim_table_warning`` gives one line.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

CLAIM_STATUSES = frozenset({"stated", "inferred", "contested", "deprecated", "superseded"})
SUPERSEDED_CLAIM_STATUS = "superseded"
_REQUIRED_HEADERS = ("claim", "status", "evidence")
_HEADING = re.compile(r"^\s{0,3}#{1,6}\s+(.*?)\s*#*\s*$")
_SEPARATOR_CELL = re.compile(r":?-{3,}:?")
_FENCE_OPEN = re.compile(r"^\s{0,3}(`{3,}|~{3,})(.*)$")
_FENCE_CLOSE = re.compile(r"^\s{0,3}(`{3,}|~{3,})\s*$")


@dataclass(frozen=True)
class ClaimRow:
    claim: str
    status: str
    evidence: str


@dataclass(frozen=True)
class ClaimTable:
    """The page's claim table. ``problem`` is set when the table cannot be read; then use the page whole."""

    rows: tuple[ClaimRow, ...]
    problem: str | None
    superseded_lines: tuple[int, ...] = ()


def read_claim_table(body: str) -> ClaimTable | None:
    """The first claim table of ``body``, or ``None`` when the page has none."""
    lines = body.splitlines()
    fenced = _fenced_line_flags(lines)
    section: str | None = None
    for index, line in enumerate(lines):
        if fenced[index]:
            continue
        heading = _heading_text(line)
        if heading is not None:
            section = heading
            continue
        if not line.lstrip().startswith("|"):
            continue
        headers = [_normalize_header(cell) for cell in _split_row(line)]
        if not set(_REQUIRED_HEADERS).issubset(headers):
            continue
        return _read_table(lines, fenced, index, headers, section)
    return None


def current_claims(body: str) -> tuple[ClaimRow, ...]:
    """Claim rows that are not ``superseded``. Empty when the page has no readable claim table."""
    table = read_claim_table(body)
    if table is None or table.problem is not None:
        return ()
    return tuple(row for row in table.rows if row.status != SUPERSEDED_CLAIM_STATUS)


def without_superseded_claims(body: str) -> str:
    """``body`` without its ``superseded`` claim rows. Unchanged when the table cannot be read."""
    table = read_claim_table(body)
    if table is None or table.problem is not None or not table.superseded_lines:
        return body
    dropped = set(table.superseded_lines)
    return "".join(line for index, line in enumerate(body.splitlines(keepends=True)) if index not in dropped)


def claim_table_warning(location: str, body: str) -> str | None:
    """One warning line when the claim table of the page at ``location`` cannot be read."""
    table = read_claim_table(body)
    if table is None or table.problem is None:
        return None
    return (
        f"Claim table not readable, page used whole without leaving out superseded rows: {location} ({table.problem})"
    )


def _read_table(
    lines: list[str], fenced: list[bool], header_index: int, headers: list[str], section: str | None
) -> ClaimTable:
    if header_index + 1 >= len(lines) or not _is_separator(_split_row(lines[header_index + 1])):
        return ClaimTable(rows=(), problem="no separator line under the header")
    columns = {name: headers.index(name) for name in _REQUIRED_HEADERS}
    needed = max(columns.values()) + 1
    rows: list[ClaimRow] = []
    superseded: list[int] = []
    index = header_index + 2
    continued = False
    while True:
        while index < len(lines) and not fenced[index] and lines[index].lstrip().startswith("|"):
            cells = _split_row(lines[index])
            if len(cells) < needed:
                if continued:
                    break
                return ClaimTable(rows=(), problem=f"row {len(rows) + 1} has {len(cells)} cells, needs {needed}")
            row = ClaimRow(
                claim=cells[columns["claim"]],
                status=cells[columns["status"]].strip("`* ").casefold(),
                evidence=cells[columns["evidence"]],
            )
            if row.status not in CLAIM_STATUSES:
                return ClaimTable(rows=(), problem=f"unknown claim status {cells[columns['status']]!r}")
            if row.status == SUPERSEDED_CLAIM_STATUS:
                superseded.append(index)
            rows.append(row)
            index += 1
        following = _continuation_start(lines, fenced, index, section, len(headers))
        if following is None:
            break
        index = following
        continued = True
    return ClaimTable(rows=tuple(rows), problem=None, superseded_lines=tuple(superseded))


def _continuation_start(
    lines: list[str], fenced: list[bool], index: int, section: str | None, column_count: int
) -> int | None:
    """Where the next chunk of the same table starts, or ``None`` when the table ends at ``index``."""
    index = _skip_blank(lines, index)
    if section is not None:
        if index >= len(lines) or fenced[index] or _heading_text(lines[index]) != section:
            return None
        index = _skip_blank(lines, index + 1)
    if index >= len(lines) or fenced[index] or not lines[index].lstrip().startswith("|"):
        return None
    if index + 1 < len(lines) and _is_separator(_split_row(lines[index + 1])):
        return None
    if len(_split_row(lines[index])) != column_count:
        return None
    return index


def _skip_blank(lines: list[str], index: int) -> int:
    while index < len(lines) and not lines[index].strip():
        index += 1
    return index


def _heading_text(line: str) -> str | None:
    match = _HEADING.match(line)
    return match.group(1).strip() if match else None


def _split_row(line: str) -> list[str]:
    """Split on unescaped pipes; an escaped pipe stays inside its cell (Vault lint rule)."""
    stripped = line.strip()
    if stripped.startswith("|"):
        stripped = stripped[1:]
    if stripped.endswith("|") and not stripped.endswith("\\|"):
        stripped = stripped[:-1]
    return [cell.strip() for cell in re.split(r"(?<!\\)\|", stripped)]


def _normalize_header(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.strip().lower())


def _is_separator(cells: list[str]) -> bool:
    return bool(cells) and all(_SEPARATOR_CELL.fullmatch(cell.strip()) for cell in cells)


def _fenced_line_flags(lines: list[str]) -> list[bool]:
    """Lines inside fenced code blocks, fence lines included (Vault lint rule)."""
    flags: list[bool] = []
    fence: str | None = None
    for line in lines:
        if fence is None:
            opening = _FENCE_OPEN.match(line)
            if opening and not (opening.group(1)[0] == "`" and "`" in opening.group(2)):
                fence = opening.group(1)
                flags.append(True)
            else:
                flags.append(False)
            continue
        flags.append(True)
        closing = _FENCE_CLOSE.match(line)
        if closing and closing.group(1)[0] == fence[0] and len(closing.group(1)) >= len(fence):
            fence = None
    return flags


__all__ = [
    "CLAIM_STATUSES",
    "ClaimRow",
    "ClaimTable",
    "claim_table_warning",
    "current_claims",
    "read_claim_table",
    "without_superseded_claims",
]
