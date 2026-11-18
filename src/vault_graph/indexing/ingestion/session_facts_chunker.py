"""`session-facts-v1`: `derived` chunks from `vault-session-facts/v1` fact attachments.

Contract: docs/contracts/vault-session-facts-v1.md §3 and §5 (spec 2026-11-16 D28).

A fact attachment sits next to a session part file as `<part name>.facts.md`. Each body line
`- <YYYY-MM-DD> <fact> (exchange <id>)` becomes one chunk. Its `parent_key` is `<session_id>:<exchange_id>`,
the key of the original exchange's windows, and its time columns are that date as a whole UTC day.
These chunks are the `derived` chunks of SPEC §9.2 B-2: search uses them only as keys that lead to the
original exchange. A chunk is `derived` when its `chunker_version` is `SESSION_FACTS_VERSION`.

The attachment is not a session file: it has no session group key and no exchange windows, so the part
file's windows, chunk ids, `source_locators` and embedding inputs do not change when it is added.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date

from vault_graph.indexing.ingestion.document_chunking import ChunkDraft, DocumentChunkPlan
from vault_graph.indexing.ingestion.document_models import ExtractedDocument
from vault_graph.indexing.ingestion.session_exchange_v2_chunker import line_range_locator, source_lines

SESSION_FACTS_SCHEMA_PREFIX = "vault-session-facts/"
SESSION_FACTS_SCHEMA_V1 = "vault-session-facts/v1"
SESSION_FACTS_VERSION = "session-facts-v1"

_FACT_LINE_RE = re.compile(r"^- (?P<date>\d{4}-\d{2}-\d{2}) (?P<text>\S.*?) \(exchange (?P<exchange>[^\s()]+)\)$")


@dataclass(frozen=True)
class SessionFactsChunker:
    """One `derived` chunk per fact line of a `vault-session-facts/v1` attachment.

    Chunker selection gives it every `vault-session-facts/*` file. Another version gets no chunks and one warning.
    """

    version: str = SESSION_FACTS_VERSION

    def __post_init__(self) -> None:
        if self.version != SESSION_FACTS_VERSION:
            raise ValueError(f"unsupported chunker version: {self.version}")

    def chunk(self, document: ExtractedDocument) -> tuple[ChunkDraft, ...]:
        return self.plan(document).drafts

    def embedding_input(self, section_path: tuple[str, ...], text: str) -> str:
        """`Session: <date>` like a session window, then the fact sentence."""
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
        drafts: list[ChunkDraft] = []
        skipped: list[int] = []
        for line in source_lines(document):
            if not line.text.strip():
                continue
            match = _FACT_LINE_RE.match(line.text)
            if match is None or not _is_date(match.group("date")):
                skipped.append(line.number)
                continue
            day = match.group("date")
            exchange_id = match.group("exchange")
            text = match.group("text")
            section_path = (f"Session {day}",)
            drafts.append(
                ChunkDraft(
                    text=text,
                    token_count=len(text.split()),
                    section=section_path[0],
                    anchor=None,
                    section_path=section_path,
                    source_locators=(line_range_locator(line, line),),
                    document_order=len(drafts),
                    boundary_key=f"fact:{line.number}",
                    parent_key=f"{session_id}:{exchange_id}",
                    started_at=f"{day}T00:00:00Z",
                    ended_at=f"{day}T23:59:59Z",
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
