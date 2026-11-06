"""`session-exchange-v2`: exchange windows for `vault-session/v2` files (spec 2026-11-05 §4.2.6).

The Vault tool renders the file (vault-builder OPERATING-SCHEMA 16.1 "Session file v2"):

    ## <title> <start time> · <exchange id first 8 chars>
    <!-- vg:exchange id=<id> scope=<scope> started=.. ended=.. tools=<name:n,..> errors=<n> outcome=..
         files=..[ continued=1] -->   (one line in the file)

    ### <role> · <turn time> · <turn id first 8 chars>

    <turn text>

    - <tool> `<target>`[ → 실패: <error first line>]

Turn text never starts a line with `#` or `<!-- vg:` (the renderer escapes both), so a `## ` line is
always an exchange heading and a `### ` line a turn heading.

Shared window helpers for other session chunkers: `SourceLine`, `source_lines`, `WindowLine`,
`ExchangeWindow`, `pack_exchange_windows`, `window_locator`, `line_range_locator`, `action_line_without_target`,
`session_embedding_input`, `exchange_keyword_metadata`, `count_over_model_limit`,
`model_limit_warning`. Cross-file duplicate exchanges: `drop_duplicate_exchanges`. Exchange time ranges
for the v1·v2 overlap pass: `exchange_time_ranges`.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, replace
from urllib.parse import unquote

from vault_graph.indexing.ingestion.document_chunking import ChunkDraft, DocumentChunkPlan
from vault_graph.indexing.ingestion.document_models import ExtractedDocument, SourceLocator
from vault_graph.indexing.ingestion.document_snapshots import NormalizedDocument
from vault_graph.indexing.ingestion.markdown_parser import make_anchor

SESSION_EXCHANGE_V2_VERSION = "session-exchange-v2"
SESSION_WINDOW_MAX_TOKENS = 160
MODEL_TOKEN_LIMIT = 512
QUESTION_CHARS = 80
CONTINUED_QUESTION = "(이전 파트에서 이어짐)"
NO_HUMAN_QUESTION = "(사람 턴 없음)"

_EXCHANGE_HEADING_RE = re.compile(r"^## +(?P<title>\S.*?)\s*$")
_TURN_HEADING_RE = re.compile(r"^### +(?P<role>[^ ·]+)")
_META_PREFIX = "<!-- vg:"
_META_RE = re.compile(r"^<!-- vg:exchange (?P<body>.*) -->$")
_SUBAGENT_HEADING_RE = re.compile(r"^Subagent (?P<agent>\S+) · ")
_ACTION_RE = re.compile(r"^- (?P<tool>\S+)(?: (?P<target>`` .*? ``|`[^`]*`))?(?: → 실패(?::.*)?)?$")
_DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}")
_WORD_RE = re.compile(r"\S+")
_SPACE_RE = re.compile(r"\s+")
_COMMAND_TOOL = "Bash"


@dataclass(frozen=True)
class SourceLine:
    """One file line with its 1-based number and character offsets in the whole file."""

    number: int
    text: str
    start_offset: int
    end_offset: int


@dataclass(frozen=True)
class WindowLine:
    """One body line that goes into exchange windows. `group` changes between paragraphs and turns."""

    text: str
    line: int
    start_offset: int
    end_offset: int
    group: int


@dataclass(frozen=True)
class ExchangeWindow:
    text: str
    token_count: int
    first_line: int
    last_line: int
    start_offset: int
    end_offset: int


@dataclass(frozen=True)
class _Fragment:
    text: str
    tokens: int
    line: int
    start_offset: int
    end_offset: int
    group: int


@dataclass(frozen=True)
class _ExchangeMeta:
    exchange_id: str
    scope: str
    tools: tuple[tuple[str, int], ...]
    errors: int
    outcome: str
    files: tuple[str, ...]
    continued: bool
    started: str = ""
    ended: str = ""


@dataclass(frozen=True)
class _Turn:
    role: str
    paragraphs: tuple[tuple[SourceLine, ...], ...]
    action_paragraph: tuple[SourceLine, ...]


@dataclass(frozen=True)
class _Exchange:
    heading: SourceLine
    title: str
    meta_line: SourceLine | None
    turns: tuple[_Turn, ...]
    lines: tuple[SourceLine, ...]


@dataclass(frozen=True)
class SessionExchangeV2Chunker:
    """Windows of at most 160 whitespace tokens inside one exchange, ids from the exchange.

    spec §4.2.6-7과 다름: 임베딩 입력에 project 없음, 질문 80자(section_path의 Q 값).
    """

    max_tokens: int = SESSION_WINDOW_MAX_TOKENS
    version: str = SESSION_EXCHANGE_V2_VERSION

    def __post_init__(self) -> None:
        if self.max_tokens <= 0:
            raise ValueError("max_tokens must be positive")
        if self.version != SESSION_EXCHANGE_V2_VERSION:
            raise ValueError(f"unsupported chunker version: {self.version}")

    def chunk(self, document: ExtractedDocument) -> tuple[ChunkDraft, ...]:
        return self.plan(document).drafts

    def embedding_input(self, section_path: tuple[str, ...], text: str) -> str:
        return session_embedding_input(section_path, text)

    def plan(self, document: ExtractedDocument) -> DocumentChunkPlan:
        path = document.source.path
        frontmatter = document.frontmatter.data
        session_id = _text(frontmatter.get("session_id"))
        session_label = _session_label(frontmatter, path)
        warnings: list[str] = []
        if not session_id:
            warnings.append(f"session_exchange_meta_invalid: {path}: frontmatter has no session_id; chunked by heading")
        drafts: list[ChunkDraft] = []
        seen_ids: set[str] = set()
        heading_counts: dict[str, int] = {}
        for exchange in _exchanges(source_lines(document)):
            occurrence = heading_counts.get(exchange.title, 0)
            heading_counts[exchange.title] = occurrence + 1
            meta, problem = _parse_meta(exchange.meta_line)
            if meta is not None and session_id:
                if meta.exchange_id in seen_ids:
                    warnings.append(
                        f"session_exchange_duplicate: {path} line {exchange.heading.number}: exchange "
                        f"{meta.exchange_id} appears again in the same file; indexed only the first"
                    )
                    continue
                seen_ids.add(meta.exchange_id)
            elif session_id:
                warnings.append(
                    f"session_exchange_meta_invalid: {path} line {exchange.heading.number}: {problem}; "
                    "chunked by heading"
                )
            drafts.extend(
                self._exchange_drafts(
                    exchange,
                    meta=meta if session_id else None,
                    session_id=session_id,
                    session_label=session_label,
                    path=path,
                    occurrence=occurrence,
                    first_order=len(drafts),
                )
            )
        return DocumentChunkPlan(drafts=tuple(drafts), warnings=tuple(warnings))

    def _exchange_drafts(
        self,
        exchange: _Exchange,
        *,
        meta: _ExchangeMeta | None,
        session_id: str,
        session_label: str,
        path: str,
        occurrence: int,
        first_order: int,
    ) -> list[ChunkDraft]:
        if meta is not None:
            agent_id = meta.scope.split(":", 1)[1] if meta.scope.startswith("subagent:") else None
            continued = meta.continued
            parent_key = f"{session_id}:{meta.exchange_id}"
            keyword_metadata: str | None = exchange_keyword_metadata(
                files=meta.files,
                commands=_commands(exchange),
                tools=meta.tools,
                errors=meta.errors,
                outcome=meta.outcome,
            )
        else:
            match = _SUBAGENT_HEADING_RE.match(exchange.title)
            agent_id = match.group("agent") if match else None
            continued = exchange.title.startswith(CONTINUED_QUESTION)
            parent_key = f"{path}:{exchange.title}:{occurrence}"
            keyword_metadata = None
        label = f"{session_label} subagent {agent_id}" if agent_id else session_label
        section_path = (label, f"Q: {_question(exchange, continued)}")
        parent_locator = line_range_locator(exchange.lines[0], exchange.lines[-1])
        anchor = make_anchor(exchange.title)
        drafts: list[ChunkDraft] = []
        for number, window in enumerate(pack_exchange_windows(_window_lines(exchange), max_tokens=self.max_tokens)):
            if meta is not None:
                id_key = (session_id, meta.exchange_id, meta.scope, str(number))
            else:
                id_key = (path, exchange.title, str(occurrence), str(number))
            drafts.append(
                ChunkDraft(
                    text=window.text,
                    token_count=window.token_count,
                    section=section_path[-1],
                    anchor=anchor,
                    section_path=section_path,
                    source_locators=(window_locator(window),),
                    document_order=first_order + number,
                    boundary_key="|".join(id_key[1:]),
                    parent_key=parent_key,
                    parent_locators=(parent_locator,),
                    keyword_metadata=keyword_metadata,
                    id_key=id_key,
                )
            )
        return drafts


def source_lines(document: ExtractedDocument) -> tuple[SourceLine, ...]:
    """Body lines numbered like the markdown reader: line numbers and char offsets in the whole file."""
    text = document.source.raw_bytes.decode("utf-8")
    body = document.frontmatter.body
    body_start = len(text) - len(body)
    number = text[:body_start].count("\n")
    offset = body_start
    lines: list[SourceLine] = []
    for raw_line in body.splitlines(keepends=True):
        number += 1
        line_text = raw_line.rstrip("\r\n")
        lines.append(SourceLine(number, line_text, offset, offset + len(line_text)))
        offset += len(raw_line)
    return tuple(lines)


def pack_exchange_windows(
    lines: Iterable[WindowLine], *, max_tokens: int = SESSION_WINDOW_MAX_TOKENS
) -> tuple[ExchangeWindow, ...]:
    """Pack lines in order into windows of at most `max_tokens` whitespace tokens, without overlap.

    A line that fits in an empty window is never split. A longer line fills the open window and
    continues in new windows, cut at word boundaries.
    """
    if max_tokens <= 0:
        raise ValueError("max_tokens must be positive")
    windows: list[ExchangeWindow] = []
    pending: list[_Fragment] = []
    pending_tokens = 0

    def flush() -> None:
        nonlocal pending, pending_tokens
        if not pending:
            return
        text = pending[0].text
        for previous, fragment in zip(pending, pending[1:], strict=False):
            text += ("\n" if fragment.group == previous.group else "\n\n") + fragment.text
        windows.append(
            ExchangeWindow(
                text=text,
                token_count=pending_tokens,
                first_line=pending[0].line,
                last_line=pending[-1].line,
                start_offset=pending[0].start_offset,
                end_offset=pending[-1].end_offset,
            )
        )
        pending = []
        pending_tokens = 0

    def add(fragment: _Fragment) -> None:
        nonlocal pending_tokens
        pending.append(fragment)
        pending_tokens += fragment.tokens

    for line in lines:
        words = list(_WORD_RE.finditer(line.text))
        if not words:
            continue
        if pending_tokens + len(words) > max_tokens and len(words) <= max_tokens:
            flush()
        if pending_tokens + len(words) <= max_tokens:
            add(_Fragment(line.text, len(words), line.line, line.start_offset, line.end_offset, line.group))
            continue
        index = 0
        while index < len(words):
            capacity = max_tokens - pending_tokens
            if capacity == 0:
                flush()
                continue
            taken = words[index : index + capacity]
            start, end = taken[0].start(), taken[-1].end()
            add(
                _Fragment(
                    line.text[start:end],
                    len(taken),
                    line.line,
                    line.start_offset + start,
                    line.start_offset + end,
                    line.group,
                )
            )
            index += len(taken)
    flush()
    return tuple(windows)


def window_locator(window: ExchangeWindow) -> SourceLocator:
    return _locator(window.first_line, window.last_line, window.start_offset, window.end_offset)


def line_range_locator(first: SourceLine, last: SourceLine) -> SourceLocator:
    """The markdown reader's locator shape for a run of lines (spec §4.2.6-10)."""
    return _locator(first.number, last.number, first.start_offset, last.end_offset)


def session_embedding_input(section_path: tuple[str, ...], text: str) -> str:
    """Model input of one session window (spec §4.2.6-7), built from the stored section path.

    spec §4.2.6-7과 다름: project 없음, 질문 80자(section_path의 Q 값). 메인 세션 결정으로 받아들였다.

    No exchange meta goes in. The question is the section path's `Q:` value.
    """
    session = section_path[0] if section_path else ""
    question = section_path[1] if len(section_path) > 1 else ""
    session = session.removeprefix("Session ")
    question = question.removeprefix("Q: ")
    return f"Session: {session}\nQuestion: {question}\n\n{text}"


def exchange_keyword_metadata(
    *,
    files: Sequence[str],
    commands: Sequence[str],
    tools: Sequence[tuple[str, int]],
    errors: int,
    outcome: str,
) -> str:
    """Exchange meta for the keyword row's frontmatter column only (spec §4.2.6-8)."""
    values = (
        ("files", " ".join(files)),
        ("commands", " ".join(commands)),
        ("tools", " ".join(f"{name}:{count}" for name, count in tools)),
        ("errors", str(errors)),
        ("outcome", outcome),
    )
    return " ".join(f"{key}: {value}" if value else f"{key}:" for key, value in values)


def count_over_model_limit(
    embedding_inputs: Iterable[str],
    count_model_tokens: Callable[[str], int],
    *,
    limit: int = MODEL_TOKEN_LIMIT,
) -> int:
    """Number of windows whose model input is longer than the model reads (spec §4.2.6-11)."""
    return sum(1 for text in embedding_inputs if count_model_tokens(text) > limit)


def model_limit_warning(count: int, *, limit: int = MODEL_TOKEN_LIMIT) -> str | None:
    if count <= 0:
        return None
    return (
        f"session_window_over_model_tokens: {count} session windows have an embedding input over "
        f"{limit} model tokens; the model reads only the first {limit}"
    )


def drop_duplicate_exchanges(
    documents: Sequence[NormalizedDocument],
) -> tuple[tuple[NormalizedDocument, ...], tuple[str, ...]]:
    """Keep each v2 exchange only in one file of the session (spec §4.2.6-9, §6).

    The kept copy is the first file, in part order, that holds the whole exchange. Only when every
    copy is a continued one (`continued=1`, the part starts inside the exchange) is it the first file
    in part order. Part order is the frontmatter `part` number, then the path, so part10 comes after
    part3 (a plain path sort would put it first). A whole copy wins because a v1 exchange that
    overlaps it is left out of the index (§4.2.7): keeping a continued copy then would lose the
    turns before the cut. This happens after
    `vg session export --recapture` writes part N+1 next to a continued part N (A-37).

    Give it the files of one session. Returns the documents in part order and one warning line per
    exchange left out of a file. A document with nothing left out is returned as it is.
    """
    ordered = sorted(documents, key=_part_order)
    owners: dict[str, tuple[str, bool]] = {}
    for document in ordered:
        path = document.document.path
        whole: dict[str, bool] = {}
        for chunk in document.chunks:
            if chunk.chunker_version != SESSION_EXCHANGE_V2_VERSION or chunk.parent_key is None:
                continue
            whole[chunk.parent_key] = whole.get(chunk.parent_key, True) and not _continued(chunk.section_path)
        for key, is_whole in whole.items():
            owner = owners.get(key)
            if owner is None or (is_whole and not owner[1]):
                owners[key] = (path, is_whole)
    kept: list[NormalizedDocument] = []
    warnings: list[str] = []
    for document in ordered:
        path = document.document.path
        chunks = []
        dropped: list[str] = []
        for chunk in document.chunks:
            parent = chunk.parent_key
            if chunk.chunker_version != SESSION_EXCHANGE_V2_VERSION or parent is None or owners[parent][0] == path:
                chunks.append(chunk)
                continue
            if parent not in dropped:
                dropped.append(parent)
        for parent in dropped:
            session_id, _, exchange_id = parent.partition(":")
            owner_path = owners[parent][0]
            warnings.append(
                f"session_exchange_duplicate: exchange {exchange_id} of session {session_id} is in "
                f"{owner_path} and {path}; indexed only from {owner_path}"
            )
        kept.append(replace(document, chunks=tuple(chunks)) if dropped else document)
    return tuple(kept), tuple(warnings)


def _part_order(item: NormalizedDocument) -> tuple[int, str]:
    part = item.document.frontmatter.get("part")
    number = part if isinstance(part, int) and not isinstance(part, bool) else None
    if isinstance(part, str) and part.isdigit():
        number = int(part)
    return (number if number is not None else 1_000_000, item.document.path)


def _continued(section_path: tuple[str, ...]) -> bool:
    """True for a window of a continued exchange: the chunker sets its question to `CONTINUED_QUESTION`."""
    return len(section_path) > 1 and section_path[1] == f"Q: {CONTINUED_QUESTION}"


def exchange_time_ranges(document: ExtractedDocument) -> dict[str, tuple[str, str] | None]:
    """`started`·`ended` of each exchange by its chunk `parent_key` (spec §4.2.7 last bullet).

    None when the meta line lacks either time or is broken (§6: the overlap pass then removes no v1
    exchange). Keys follow `SessionExchangeV2Chunker.plan`; an exchange id seen again keeps its first range.
    """
    path = document.source.path
    session_id = _text(document.frontmatter.data.get("session_id"))
    ranges: dict[str, tuple[str, str] | None] = {}
    heading_counts: dict[str, int] = {}
    for exchange in _exchanges(source_lines(document)):
        occurrence = heading_counts.get(exchange.title, 0)
        heading_counts[exchange.title] = occurrence + 1
        meta, _ = _parse_meta(exchange.meta_line)
        if meta is None or not session_id:
            ranges.setdefault(f"{path}:{exchange.title}:{occurrence}", None)
            continue
        times = (meta.started, meta.ended) if meta.started and meta.ended else None
        ranges.setdefault(f"{session_id}:{meta.exchange_id}", times)
    return ranges


def _exchanges(lines: tuple[SourceLine, ...]) -> list[_Exchange]:
    starts = [index for index, line in enumerate(lines) if _EXCHANGE_HEADING_RE.match(line.text)]
    exchanges: list[_Exchange] = []
    for position, start in enumerate(starts):
        end = starts[position + 1] if position + 1 < len(starts) else len(lines)
        block = lines[start:end]
        heading = block[0]
        title_match = _EXCHANGE_HEADING_RE.match(heading.text)
        title = title_match.group("title") if title_match else heading.text
        rest = block[1:]
        meta_line = None
        if rest and rest[0].text.startswith(_META_PREFIX):
            meta_line = rest[0]
            rest = rest[1:]
        used = [line for line in block if line.text.strip()]
        exchanges.append(
            _Exchange(heading=heading, title=title, meta_line=meta_line, turns=_turns(rest), lines=tuple(used))
        )
    return exchanges


def _turns(lines: tuple[SourceLine, ...]) -> tuple[_Turn, ...]:
    turns: list[_Turn] = []
    role = ""
    body: list[SourceLine] = []

    def close() -> None:
        paragraphs = _paragraphs(body)
        if not paragraphs and not role:
            return
        action: tuple[SourceLine, ...] = ()
        if paragraphs and all(_ACTION_RE.match(line.text) for line in paragraphs[-1]):
            action = paragraphs[-1]
        turns.append(_Turn(role=role, paragraphs=paragraphs, action_paragraph=action))

    for line in lines:
        match = _TURN_HEADING_RE.match(line.text)
        if match is None:
            body.append(line)
            continue
        close()
        role = match.group("role")
        body = []
    close()
    return tuple(turns)


def _paragraphs(lines: list[SourceLine]) -> tuple[tuple[SourceLine, ...], ...]:
    paragraphs: list[tuple[SourceLine, ...]] = []
    current: list[SourceLine] = []
    for line in lines:
        if line.text.strip():
            current.append(line)
            continue
        if current:
            paragraphs.append(tuple(current))
            current = []
    if current:
        paragraphs.append(tuple(current))
    return tuple(paragraphs)


def _window_lines(exchange: _Exchange) -> list[WindowLine]:
    lines: list[WindowLine] = []
    group = 0
    for turn in exchange.turns:
        for paragraph in turn.paragraphs:
            for line in paragraph:
                text = action_line_without_target(line.text) if paragraph == turn.action_paragraph else line.text
                lines.append(WindowLine(text, line.number, line.start_offset, line.end_offset, group))
            group += 1
    return lines


def action_line_without_target(line: str) -> str:
    """Drop the code-quoted target of an action line, keep the tool and the result (결정12, A-6).

    Example: "- Bash <quoted command> → 실패: e" becomes "- Bash → 실패: e".

    Targets (paths, commands, urls, queries) go only to `keyword_metadata`. Other lines stay as they are.
    """
    match = _ACTION_RE.match(line)
    if match is None or match.group("target") is None:
        return line
    return line[: match.start("target") - 1] + line[match.end("target") :]


def _question(exchange: _Exchange, continued: bool) -> str:
    if continued:
        return CONTINUED_QUESTION
    for turn in exchange.turns:
        if turn.role != "user":
            continue
        text = " ".join(
            line.text for paragraph in turn.paragraphs if paragraph != turn.action_paragraph for line in paragraph
        )
        question = _SPACE_RE.sub(" ", text).strip()[:QUESTION_CHARS].rstrip()
        if question:
            return question
    return NO_HUMAN_QUESTION


def _commands(exchange: _Exchange) -> tuple[str, ...]:
    commands: list[str] = []
    for turn in exchange.turns:
        for line in turn.action_paragraph:
            match = _ACTION_RE.match(line.text)
            if match is None or match.group("tool") != _COMMAND_TOOL or not match.group("target"):
                continue
            target = match.group("target")
            commands.append(target[3:-3] if target.startswith("`` ") else target[1:-1])
    return tuple(commands)


def _parse_meta(line: SourceLine | None) -> tuple[_ExchangeMeta | None, str]:
    if line is None:
        return None, "exchange meta line is missing"
    match = _META_RE.match(line.text)
    if match is None:
        return None, "exchange meta line is not closed"
    fields: dict[str, str] = {}
    for token in match.group("body").split(" "):
        key, separator, value = token.partition("=")
        if not separator or not key or key in fields:
            return None, f"exchange meta field {token!r} is not one key=value"
        fields[key] = value
    exchange_id = unquote(fields.get("id", ""))
    scope = unquote(fields.get("scope", ""))
    if not exchange_id or not scope:
        return None, "exchange meta line has no id or scope"
    if scope != "main" and not (scope.startswith("subagent:") and len(scope) > len("subagent:")):
        return None, f"exchange meta scope {scope!r} is not main or subagent:<id>"
    tools: list[tuple[str, int]] = []
    for item in filter(None, fields.get("tools", "").split(",")):
        name, separator, count = item.rpartition(":")
        if not separator or not name or not count.isdigit():
            return None, f"exchange meta tool {item!r} is not name:count"
        tools.append((unquote(name), int(count)))
    errors = fields.get("errors", "0")
    if not errors.isdigit():
        return None, f"exchange meta errors {errors!r} is not a number"
    return (
        _ExchangeMeta(
            exchange_id=exchange_id,
            scope=scope,
            tools=tuple(tools),
            errors=int(errors),
            outcome=unquote(fields.get("outcome", "")),
            files=tuple(unquote(item) for item in fields.get("files", "").split(",") if item),
            continued=fields.get("continued") == "1",
            started=unquote(fields.get("started", "")),
            ended=unquote(fields.get("ended", "")),
        ),
        "",
    )


def _session_label(frontmatter: dict[str, object], path: str) -> str:
    match = _DATE_RE.search(_text(frontmatter.get("first_turn_at")))
    if match is None:
        match = _DATE_RE.match(path.rsplit("/", 1)[-1])
    date = match.group(0) if match else "unknown-date"
    part = _text(frontmatter.get("part"))
    return f"Session {date} part{part}" if part else f"Session {date}"


def _text(value: object) -> str:
    if value is None or isinstance(value, bool):
        return ""
    return str(value).strip()


def _locator(first_line: int, last_line: int, start_offset: int, end_offset: int) -> SourceLocator:
    coordinates: tuple[tuple[str, str], ...] = (("line", str(first_line)),)
    if last_line != first_line:
        coordinates = (*coordinates, ("line_end", str(last_line)))
    return SourceLocator(
        scheme="markdown",
        coordinates=coordinates,
        start_offset=start_offset,
        end_offset=end_offset,
        offset_unit="char",
    )
