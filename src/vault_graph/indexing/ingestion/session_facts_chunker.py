"""`session-facts-v2`: one `derived` expansion key per exchange from `vault-session-facts/v1` attachments.

Contract: docs/contracts/vault-session-facts-v1.md §3 and §5 (spec 2026-11-16 D21, D28).

A fact attachment sits next to a session part file as `<part name>.facts.md`. Its body lines are
`- <YYYY-MM-DD> <fact> (exchange <id>)`. The lines of one exchange become one chunk (key merging, research X27):
the exchange's user question title from the part file named by frontmatter `source`, then the fact sentences,
one per line. When the part cannot be read or has no such exchange, the chunk holds the facts only. Its
`parent_key` is `<session_id>:<exchange_id>`, the key of the original exchange's windows, and its time columns
run from the first to the last fact day as whole UTC days. These chunks are the `derived` chunks of SPEC §9.2
B-2: search uses them only as keys that lead to the original exchange. A chunk is `derived` when its
`chunker_version` is `SESSION_FACTS_VERSION`.

The attachment is not a session file: it has no session group key and no exchange windows, so the part
file's windows, chunk ids, `source_locators` and embedding inputs do not change when it is added.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from urllib.parse import unquote

from vault_graph.indexing.ingestion.document_chunking import ChunkDraft, DocumentChunkPlan
from vault_graph.indexing.ingestion.document_models import ExtractedDocument
from vault_graph.indexing.ingestion.session_exchange_v2_chunker import (
    SourceLine,
    line_range_locator,
    source_lines,
)

SESSION_FACTS_SCHEMA_PREFIX = "vault-session-facts/"
SESSION_FACTS_SCHEMA_V1 = "vault-session-facts/v1"
# v2: one expansion key per exchange instead of one chunk per fact line (spec 2026-11-16 D21). The version is
# in every chunk id and the index code, so existing indexes read each attachment again.
SESSION_FACTS_VERSION = "session-facts-v2"

_FACT_LINE_RE = re.compile(r"^- (?P<date>\d{4}-\d{2}-\d{2}) (?P<text>\S.*?) \(exchange (?P<exchange>[^\s()]+)\)$")
# Part file exchange heading `## <title> <start time> · <exchange id first 8 chars>` and its meta line
# (session_exchange_v2_chunker module docstring).
_EXCHANGE_HEADING_RE = re.compile(r"^## +(?P<title>\S.*?)\s*$")
_HEADING_SUFFIX_RE = re.compile(r"\s+\d{4}-\d{2}-\d{2}T\S+ · \S+$")
_META_ID_RE = re.compile(r"^<!-- vg:exchange (?:.* )?id=(?P<id>\S+)")


@dataclass
class _ExchangeFacts:
    exchange_id: str
    lines: list[SourceLine] = field(default_factory=list)
    days: list[str] = field(default_factory=list)
    texts: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class SessionFactsChunker:
    """One `derived` expansion key chunk per exchange of a `vault-session-facts/v1` attachment.

    Chunker selection gives it every `vault-session-facts/*` file. Another version gets no chunks and one warning.
    """

    version: str = SESSION_FACTS_VERSION

    def __post_init__(self) -> None:
        if self.version != SESSION_FACTS_VERSION:
            raise ValueError(f"unsupported chunker version: {self.version}")

    def chunk(self, document: ExtractedDocument) -> tuple[ChunkDraft, ...]:
        return self.plan(document).drafts

    def embedding_input(self, section_path: tuple[str, ...], text: str) -> str:
        """`Session: <date>` like a session window, then the key text."""
        session = section_path[0].removeprefix("Session ") if section_path else ""
        return f"Session: {session}\n\n{text}" if session else text

    def plan(self, document: ExtractedDocument) -> DocumentChunkPlan:
        path = document.source.path
        schema = document.frontmatter.data.get("schema")
        if schema != SESSION_FACTS_SCHEMA_V1:
            # Another `vault-session-facts/*` version: its line format is unknown, so nothing is indexed.
            return DocumentChunkPlan(
                drafts=(),
                warnings=(f"unknown_session_facts_schema: {path} has schema {schema}; not indexed",),
            )
        session_id = _text(document.frontmatter.data.get("session_id"))
        if not session_id:
            return DocumentChunkPlan(
                drafts=(),
                warnings=(f"session_facts_invalid: {path}: frontmatter has no session_id; not indexed",),
            )
        exchanges: dict[str, _ExchangeFacts] = {}
        skipped: list[int] = []
        for line in source_lines(document):
            if not line.text.strip():
                continue
            match = _FACT_LINE_RE.match(line.text)
            if match is None or not _is_date(match.group("date")):
                skipped.append(line.number)
                continue
            exchange_id = match.group("exchange")
            group = exchanges.setdefault(exchange_id, _ExchangeFacts(exchange_id=exchange_id))
            group.lines.append(line)
            group.days.append(match.group("date"))
            group.texts.append(match.group("text"))
        titles = _part_titles(document) if exchanges else {}
        drafts: list[ChunkDraft] = []
        for group in exchanges.values():
            title = titles.get(group.exchange_id, "")
            text = "\n".join([title, *group.texts] if title else group.texts)
            first, last = min(group.days), max(group.days)
            section_path = (f"Session {first}",)
            drafts.append(
                ChunkDraft(
                    text=text,
                    token_count=len(text.split()),
                    section=section_path[0],
                    anchor=None,
                    section_path=section_path,
                    source_locators=tuple(line_range_locator(line, line) for line in group.lines),
                    document_order=len(drafts),
                    boundary_key=f"exchange:{group.exchange_id}",
                    parent_key=f"{session_id}:{group.exchange_id}",
                    started_at=f"{first}T00:00:00Z",
                    ended_at=f"{last}T23:59:59Z",
                )
            )
        warnings: tuple[str, ...] = ()
        if skipped:
            lines = ", ".join(str(number) for number in skipped)
            warnings = (
                f"session_facts_line_invalid: {path}: {len(skipped)} lines are not "
                f"`- <YYYY-MM-DD> <fact> (exchange <id>)` (lines {lines}); skipped them",
            )
        return DocumentChunkPlan(drafts=tuple(drafts), warnings=warnings)


def _part_titles(document: ExtractedDocument) -> dict[str, str]:
    """User question title of each exchange id in the part file, or {} when it cannot be read.

    The part is frontmatter `source` (Vault-relative), else `<name>.md` next to `<name>.facts.md`. A path that
    leaves the Vault root is not read.
    """
    root = Path(document.source.root_path)
    source = _text(document.frontmatter.data.get("source"))
    if not source:
        source = document.source.path.removesuffix(".facts.md") + ".md"
    try:
        resolved_root = root.resolve()
        part = (resolved_root / source).resolve()
        if not part.is_relative_to(resolved_root):
            return {}
        text = part.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError, ValueError):
        return {}
    titles: dict[str, str] = {}
    heading = ""
    for line in text.splitlines():
        heading_match = _EXCHANGE_HEADING_RE.match(line)
        if heading_match is not None:
            heading = _HEADING_SUFFIX_RE.sub("", heading_match.group("title")).strip()
            continue
        meta_match = _META_ID_RE.match(line)
        if meta_match is not None and heading:
            titles.setdefault(unquote(meta_match.group("id")), heading)
            heading = ""
    return titles


def _is_date(value: str) -> bool:
    try:
        date.fromisoformat(value)
    except ValueError:
        return False
    return True


def _text(value: object) -> str:
    if value is None or isinstance(value, bool):
        return ""
    return str(value).strip()
