"""Exchange windows for `vault-session/v1` session files (spec 2026-11-05 §4.2.7, §4.2.6-4·5·7).

A v1 file is a list of turns written by the Vault tool's `sessions capture`:
`## <timestamp> <role>` or `## <timestamp> subagent <agent_id> <role>`, then the turn text,
then an optional last line `Tools: a, b`. This chunker groups the turns into exchanges, cuts each
exchange into windows of at most 160 whitespace tokens without overlap, and leaves tool names out
of the window text. Tool names go to `keyword_metadata` instead.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime

from vault_graph.indexing.ingestion.document_chunking import ChunkDraft
from vault_graph.indexing.ingestion.document_models import ExtractedDocument, SourceLocator

SESSION_EXCHANGE_V1_VERSION = "session-exchange-v1"
MAX_WINDOW_TOKENS = 160
QUESTION_PREVIEW_CHARS = 80
CONTINUED_QUESTION = "(이전 파트에서 이어짐)"
# Claude Code writes a compaction summary as a plain user entry. v1 files lost the `isCompactSummary`
# flag, so this prefix keeps the summary inside the current exchange instead of opening a new one
# (risk A3).
COMPACT_SUMMARY_PREFIX = "This session is being continued from a previous conversation"

_TURN_HEADING = re.compile(
    r"^## (?P<at>\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z) "
    r"(?:subagent (?P<agent>[A-Za-z0-9][A-Za-z0-9_-]*) )?(?P<role>user|assistant)$"
)
_TOOLS_LINE = re.compile(r"^Tools: (?P<names>\S.*)$")
_WORD = re.compile(r"\S+")
_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}")
_SESSION_PREFIX = "Session "
_QUESTION_PREFIX = "Q: "


@dataclass(frozen=True)
class SessionExchangeV1Chunker:
    """`DocumentChunker` for `vault-session/v1` files."""

    version: str = SESSION_EXCHANGE_V1_VERSION

    def __post_init__(self) -> None:
        if self.version != SESSION_EXCHANGE_V1_VERSION:
            raise ValueError(f"unsupported chunker version: {self.version}")

    def chunk(self, document: ExtractedDocument) -> tuple[ChunkDraft, ...]:
        return chunk_session_v1(document)

    def embedding_input(self, section_path: tuple[str, ...], text: str) -> str:
        session = _strip_prefix(section_path[0], _SESSION_PREFIX) if section_path else ""
        question = _strip_prefix(section_path[1], _QUESTION_PREFIX) if len(section_path) > 1 else ""
        return f"Session: {session}\nQuestion: {question}\n\n{text}"


@dataclass(frozen=True)
class _Line:
    number: int
    text: str
    start: int
    end: int


@dataclass(frozen=True)
class _Turn:
    index: int
    heading: str
    role: str
    agent_id: str | None
    heading_line: _Line
    last_line: _Line
    body: tuple[_Line, ...]
    tools: tuple[str, ...]

    @property
    def opens_exchange(self) -> bool:
        """A person's message in its own scope: role user, not tag-wrapped, not a compaction summary."""
        if self.role != "user" or not self.body:
            return False
        first = self.body[0].text.lstrip()
        return not first.startswith("<") and not first.startswith(COMPACT_SUMMARY_PREFIX)


@dataclass
class _Exchange:
    first: _Turn
    question: _Turn | None
    turns: list[_Turn]


@dataclass(frozen=True)
class _Fragment:
    text: str
    token_count: int
    line_number: int
    start: int
    end: int
    turn_index: int
    blank_before: bool


def chunk_session_v1(document: ExtractedDocument) -> tuple[ChunkDraft, ...]:
    """Windows of every exchange in file order of the exchange's first turn."""

    turns = _read_turns(document)
    exchanges = _exchanges(turns)
    session_label = _session_label(document, turns)
    path = document.source.path

    drafts: list[ChunkDraft] = []
    occurrences: dict[str, int] = {}
    for exchange in exchanges:
        occurrence = occurrences.get(exchange.first.heading, 0) + 1
        occurrences[exchange.first.heading] = occurrence
        scope_label = session_label
        if exchange.first.agent_id is not None:
            scope_label = f"{session_label} subagent {exchange.first.agent_id}"
        section_path = (scope_label, _QUESTION_PREFIX + _question_preview(exchange.question))
        parent_key = f"{path}:{exchange.first.heading}:{occurrence}"
        parent_locators = _parent_locators(exchange.turns)
        keyword_metadata = _keyword_metadata(exchange.turns)
        for window_index, window in enumerate(_windows(_fragments(exchange.turns))):
            drafts.append(
                ChunkDraft(
                    text=_join(window),
                    token_count=sum(fragment.token_count for fragment in window),
                    section=section_path[-1],
                    anchor=None,
                    section_path=section_path,
                    source_locators=_window_locators(window),
                    document_order=len(drafts),
                    boundary_key=f"{exchange.first.heading}:{occurrence}:{window_index}",
                    parent_key=parent_key,
                    parent_locators=parent_locators,
                    keyword_metadata=keyword_metadata,
                )
            )
    return tuple(drafts)


def exchange_time_ranges(document: ExtractedDocument) -> dict[str, tuple[str, str]]:
    """First and last turn time of each exchange by its chunk `parent_key` (spec §4.2.7 last bullet)."""

    path = document.source.path
    ranges: dict[str, tuple[str, str]] = {}
    occurrences: dict[str, int] = {}
    for exchange in _exchanges(_read_turns(document)):
        occurrence = occurrences.get(exchange.first.heading, 0) + 1
        occurrences[exchange.first.heading] = occurrence
        times = sorted((turn.heading.split(" ", 1)[0] for turn in exchange.turns), key=_heading_time)
        ranges[f"{path}:{exchange.first.heading}:{occurrence}"] = (times[0], times[-1])
    return ranges


def _heading_time(value: str) -> datetime:
    return datetime.fromisoformat(value.removesuffix("Z") + "+00:00")


def _read_turns(document: ExtractedDocument) -> tuple[_Turn, ...]:
    text = document.source.raw_bytes.decode("utf-8")
    body = document.frontmatter.body
    body_start = len(text) - len(body)
    lines = _lines(body, line_offset=text[:body_start].count("\n"), char_offset=body_start)

    turns: list[_Turn] = []
    heading: _Line | None = None
    match: re.Match[str] | None = None
    pending: list[_Line] = []

    def close() -> None:
        if heading is None or match is None:
            return
        turns.append(_turn(len(turns), heading, match, pending))

    for line in lines:
        heading_match = _TURN_HEADING.match(line.text)
        if heading_match is None:
            if heading is not None:
                pending.append(line)
            continue
        close()
        heading, match, pending = line, heading_match, []
    close()
    return tuple(turns)


def _turn(index: int, heading: _Line, match: re.Match[str], lines: list[_Line]) -> _Turn:
    body = _trim_blank(lines)
    last_line = body[-1] if body else heading
    tools: tuple[str, ...] = ()
    if body:
        tools_match = _TOOLS_LINE.match(body[-1].text)
        if tools_match is not None and (len(body) == 1 or not body[-2].text.strip()):
            tools = tuple(name.strip() for name in tools_match.group("names").split(",") if name.strip())
            body = _trim_blank(body[:-1])
    return _Turn(
        index=index,
        heading=heading.text[3:],
        role=match.group("role"),
        agent_id=match.group("agent"),
        heading_line=heading,
        last_line=last_line,
        body=tuple(body),
        tools=tools,
    )


def _trim_blank(lines: list[_Line]) -> list[_Line]:
    start, end = 0, len(lines)
    while start < end and not lines[start].text.strip():
        start += 1
    while end > start and not lines[end - 1].text.strip():
        end -= 1
    return lines[start:end]


def _exchanges(turns: tuple[_Turn, ...]) -> list[_Exchange]:
    """Split each scope (main agent, each subagent) at the turns that open an exchange."""

    exchanges: list[_Exchange] = []
    current: dict[str | None, _Exchange] = {}
    for turn in turns:
        scope = turn.agent_id
        exchange = current.get(scope)
        if turn.opens_exchange or exchange is None:
            exchange = _Exchange(first=turn, question=turn if turn.opens_exchange else None, turns=[])
            current[scope] = exchange
            exchanges.append(exchange)
        exchange.turns.append(turn)
    return exchanges


def _fragments(turns: list[_Turn]) -> list[_Fragment]:
    fragments: list[_Fragment] = []
    for turn in turns:
        previous_number: int | None = None
        for line in turn.body:
            words = list(_WORD.finditer(line.text))
            if not words:
                continue
            blank_before = previous_number is not None and line.number != previous_number + 1
            previous_number = line.number
            if len(words) <= MAX_WINDOW_TOKENS:
                fragments.append(
                    _Fragment(line.text, len(words), line.number, line.start, line.end, turn.index, blank_before)
                )
                continue
            for piece_start in range(0, len(words), MAX_WINDOW_TOKENS):
                piece = words[piece_start : piece_start + MAX_WINDOW_TOKENS]
                fragments.append(
                    _Fragment(
                        " ".join(word.group() for word in piece),
                        len(piece),
                        line.number,
                        line.start + piece[0].start(),
                        line.start + piece[-1].end(),
                        turn.index,
                        blank_before and piece_start == 0,
                    )
                )
    return fragments


def _windows(fragments: list[_Fragment]) -> list[list[_Fragment]]:
    windows: list[list[_Fragment]] = []
    pending: list[_Fragment] = []
    pending_tokens = 0
    for fragment in fragments:
        if pending and pending_tokens + fragment.token_count > MAX_WINDOW_TOKENS:
            windows.append(pending)
            pending, pending_tokens = [], 0
        pending.append(fragment)
        pending_tokens += fragment.token_count
    if pending:
        windows.append(pending)
    return windows


def _join(window: list[_Fragment]) -> str:
    result = window[0].text
    for previous, fragment in zip(window, window[1:], strict=False):
        if fragment.turn_index != previous.turn_index or fragment.blank_before:
            separator = "\n\n"
        elif fragment.line_number == previous.line_number:
            separator = " "
        else:
            separator = "\n"
        result += separator + fragment.text
    return result


def _window_locators(window: list[_Fragment]) -> tuple[SourceLocator, ...]:
    """One locator per turn the window touches, so windows of interleaved exchanges never share lines."""

    groups: list[list[_Fragment]] = []
    for fragment in window:
        if groups and groups[-1][-1].turn_index == fragment.turn_index:
            groups[-1].append(fragment)
        else:
            groups.append([fragment])
    return tuple(
        _locator(group[0].line_number, group[-1].line_number, group[0].start, group[-1].end) for group in groups
    )


def _parent_locators(turns: list[_Turn]) -> tuple[SourceLocator, ...]:
    """The exchange's line ranges. Turns of the exchange that follow each other in the file share one range."""

    runs: list[list[_Turn]] = []
    for turn in turns:
        if runs and runs[-1][-1].index + 1 == turn.index:
            runs[-1].append(turn)
        else:
            runs.append([turn])
    return tuple(
        _locator(
            run[0].heading_line.number,
            run[-1].last_line.number,
            run[0].heading_line.start,
            run[-1].last_line.end,
        )
        for run in runs
    )


def _locator(first_line: int, last_line: int, start: int, end: int) -> SourceLocator:
    coordinates = [("line", str(first_line))]
    if last_line != first_line:
        coordinates.append(("line_end", str(last_line)))
    return SourceLocator(
        scheme="markdown",
        coordinates=tuple(coordinates),
        start_offset=start,
        end_offset=end,
        offset_unit="char",
    )


def _keyword_metadata(turns: list[_Turn]) -> str | None:
    names = tuple(dict.fromkeys(name for turn in turns for name in turn.tools))
    if not names:
        return None
    return "tools: " + ", ".join(names)


def _question_preview(question: _Turn | None) -> str:
    if question is None:
        return CONTINUED_QUESTION
    collapsed = " ".join(" ".join(line.text for line in question.body).split())
    return collapsed[:QUESTION_PREVIEW_CHARS].strip()


def _session_label(document: ExtractedDocument, turns: tuple[_Turn, ...]) -> str:
    data = document.frontmatter.data
    day = _day(data.get("first_turn_at"))
    if day is None and turns:
        day = turns[0].heading[:10]
    label = _SESSION_PREFIX + (day or "unknown-date")
    part = data.get("part")
    if isinstance(part, int) and not isinstance(part, bool):
        label += f" part{part}"
    return label


def _day(value: object) -> str | None:
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, str) and _DATE.match(value.strip()):
        return value.strip()[:10]
    return None


def _strip_prefix(value: str, prefix: str) -> str:
    return value[len(prefix) :] if value.startswith(prefix) else value


def _lines(body: str, *, line_offset: int, char_offset: int) -> tuple[_Line, ...]:
    """Body lines numbered like the markdown reader: 1-based file lines, character offsets in the file."""

    lines: list[_Line] = []
    offset = 0
    for number, raw_line in enumerate(body.splitlines(keepends=True), start=1):
        text = raw_line.rstrip("\r\n")
        lines.append(_Line(number + line_offset, text, char_offset + offset, char_offset + offset + len(text)))
        offset += len(raw_line)
    return tuple(lines)
