"""Claude Code session adapter ``claude-code/1`` (spec 2026-11-05 §4.2.2, 위험A2).

The Claude Code transcript format is not a public contract. These rules follow transcripts written
by Claude Code 2.1.x: one JSON object per line, turn records have ``type`` ``user`` or ``assistant``,
and subagent conversations live in ``<session_id>/subagents/agent-<id>.jsonl`` with an
``agent-<id>.meta.json`` next to them. When the source format changes, raise the adapter version.

Same source records and the same adapter version give the same lines. Times are copied from the
source as they are. Tool result bodies, thinking, attachments and API request records are left out.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from collections.abc import Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Literal

from vault_graph.operation.sessions.models import (
    Action,
    ExchangeLine,
    NormalizedLine,
    NormalizedSession,
    Outcome,
    SessionLine,
    SessionTitle,
    SourceRecord,
    TurnKind,
    TurnLine,
)
from vault_graph.operation.sessions.redact import redact

CLAUDE_CODE_ADAPTER_VERSION = "claude-code/1"
CLAUDE_CODE_AGENT = "claude-code"

# tool_use.input keys that name what the action worked on, in the order they are tried.
_TARGET_KEYS = ("file_path", "command", "url", "query", "subagent_type")
_TARGET_LIMIT = 160
_ERROR_HEAD_LIMIT = 200
_INTERRUPTED_PREFIX = "[Request interrupted"

# Record types this adapter knows and leaves out. Any other type is counted as unknown (위험A2).
_KNOWN_RECORD_TYPES = frozenset(
    {
        "user",
        "assistant",
        "system",
        "attachment",
        "summary",
        "ai-title",
        "custom-title",
        "agent-name",
        "last-prompt",
        "continued-in",
        "queue-operation",
        "file-history-snapshot",
        "file-history-delta",
        "api-request",
        "api-request-blob",
        "api-request-shape",
        "tools-used",
        "cost-state",
        "mode",
        "permission-mode",
        "bridge-session",
        "relocated",
        "atis-latch",
        "pr-link",
        "session-owner",
        "frame-link",
        "artifact-comment-monitor",
        "artifact-autoreact-ledger",
    }
)

_SUBAGENT_PATH = re.compile(r"(?:^|/)subagents/agent-(?P<agent_id>[^/]+?)\.(?P<suffix>jsonl|meta\.json)$")
_MAIN_SCOPE = "main"


@dataclass(frozen=True)
class _Result:
    is_error: bool
    interrupted: bool
    text: str


@dataclass(frozen=True)
class _Action:
    action: Action
    target_key: str | None
    interrupted: bool


@dataclass(frozen=True)
class _Turn:
    uuid: str
    parent_id: str | None
    role: Literal["user", "assistant"]
    kind: TurnKind
    at: str | None
    agent_id: str | None
    sidechain: bool
    text: str
    actions: tuple[_Action, ...]
    prompt_source: str | None
    version: str | None
    cwd: str | None
    git_branch: str | None


@dataclass(frozen=True)
class _Scope:
    name: str
    turns: tuple[_Turn, ...]
    finished: bool
    subagent_type: str | None = None
    parent_tool_use_id: str | None = None


@dataclass
class _ParsedFile:
    path: str
    records: list[dict[str, object]]


class ClaudeCodeAdapter:
    """Normalize one Claude Code session: the main transcript plus its subagent files.

    ``session_ended`` says the caller knows the session is over (SessionEnd hook or export of an old
    session). Then the last exchange of every scope is closed. Otherwise the last main exchange stays
    open, and a subagent's last exchange closes only when its meta file says it finished.
    """

    agent = CLAUDE_CODE_AGENT
    version = CLAUDE_CODE_ADAPTER_VERSION

    def __init__(self, *, session_ended: bool = False) -> None:
        self._session_ended = session_ended

    def normalize(self, records: Iterable[SourceRecord]) -> Iterator[NormalizedLine]:
        return iter(self.normalize_session(records).lines)

    def normalize_session(self, records: Iterable[SourceRecord]) -> NormalizedSession:
        ordered = sorted(records, key=lambda record: (record.source_path, record.line_no))
        invalid = 0
        unknown: Counter[str] = Counter()
        main_files: list[_ParsedFile] = []
        subagent_files: dict[str, _ParsedFile] = {}
        subagent_meta: dict[str, Mapping[str, object]] = {}

        for path, file_records in _group_by_path(ordered):
            match = _SUBAGENT_PATH.search(path)
            if match and match.group("suffix") == "meta.json":
                meta = _parse_object("".join(record.text for record in file_records))
                if meta is None:
                    invalid += 1
                else:
                    subagent_meta[match.group("agent_id")] = meta
                continue
            if not path.endswith(".jsonl"):
                continue
            parsed = _ParsedFile(path=path, records=[])
            for record in file_records:
                if not record.text.strip():
                    continue
                data = _parse_object(record.text)
                if data is None:
                    invalid += 1
                    continue
                record_type = data.get("type")
                if not isinstance(record_type, str) or record_type not in _KNOWN_RECORD_TYPES:
                    unknown[str(record_type)] += 1
                parsed.records.append(data)
            if match:
                subagent_files[match.group("agent_id")] = parsed
            else:
                main_files.append(parsed)

        seen: set[str] = set()
        main_records = [record for parsed in main_files for record in parsed.records]
        main_scope = _Scope(name=_MAIN_SCOPE, turns=_ordered_turns(main_records, seen), finished=self._session_ended)
        subagent_scopes: list[_Scope] = []
        for agent_id in sorted(subagent_files):
            agent_meta = subagent_meta.get(agent_id, {})
            subagent_scopes.append(
                _Scope(
                    name=f"subagent:{agent_id}",
                    turns=_ordered_turns(subagent_files[agent_id].records, seen),
                    finished=self._session_ended or agent_meta.get("finished") is True,
                    subagent_type=_text(agent_meta.get("agentType")),
                    parent_tool_use_id=_text(agent_meta.get("toolUseId")),
                )
            )
        subagent_scopes.sort(key=lambda scope: (_first_time(scope.turns), scope.name))

        session = _session_line(
            main_records=main_records,
            subagent_records=[record for _, parsed in sorted(subagent_files.items()) for record in parsed.records],
            main_turns=main_scope.turns,
            all_turns=[turn for scope in (main_scope, *subagent_scopes) for turn in scope.turns],
            source_paths=tuple(dict.fromkeys(record.source_path for record in ordered)),
            source_sha256=_source_sha256(ordered),
            first_path=main_files[0].path if main_files else None,
        )
        lines: list[NormalizedLine] = [session]
        seq = 0
        for scope in (main_scope, *subagent_scopes):
            exchanges = _split_exchanges(scope.turns)
            for index, turns in enumerate(exchanges):
                seq += 1
                closed = index < len(exchanges) - 1 or scope.finished
                exchange = _exchange_line(scope, turns, seq=seq, closed=closed)
                lines.append(exchange)
                lines.extend(_turn_line(turn, exchange.exchange_id) for turn in turns)
        return NormalizedSession(
            lines=tuple(lines),
            invalid_lines=invalid,
            unknown_record_types=dict(sorted(unknown.items())),
        )


def _group_by_path(records: Sequence[SourceRecord]) -> Iterator[tuple[str, list[SourceRecord]]]:
    group: list[SourceRecord] = []
    for record in records:
        if group and group[0].source_path != record.source_path:
            yield group[0].source_path, group
            group = []
        group.append(record)
    if group:
        yield group[0].source_path, group


def _parse_object(text: str) -> dict[str, object] | None:
    try:
        value = json.loads(text)
    except ValueError:
        return None
    return value if isinstance(value, dict) else None


def _source_sha256(records: Sequence[SourceRecord]) -> str:
    digest = hashlib.sha256()
    for record in records:
        digest.update(f"{record.source_path}\0{record.line_no}\0{record.text}\n".encode())
    return digest.hexdigest()


def _text(value: object) -> str | None:
    return value if isinstance(value, str) and value else None


def _first_time(turns: Sequence[_Turn]) -> str:
    times = [turn.at for turn in turns if turn.at]
    return min(times) if times else ""


# Ordering: walk the parentUuid tree depth first. Siblings and roots go by (timestamp, file position).


def _ordered_turns(records: Sequence[dict[str, object]], seen: set[str]) -> tuple[_Turn, ...]:
    results = _tool_results(records)
    nodes: dict[str, tuple[int, dict[str, object]]] = {}
    for position, record in enumerate(records):
        uuid = _text(record.get("uuid"))
        if uuid is None or uuid in nodes or uuid in seen:
            continue
        nodes[uuid] = (position, record)
    seen.update(nodes)

    def sort_key(uuid: str) -> tuple[str, int]:
        position, record = nodes[uuid]
        return (_text(record.get("timestamp")) or "", position)

    children: dict[str | None, list[str]] = {}
    for uuid, (_, record) in nodes.items():
        parent = _text(record.get("parentUuid"))
        children.setdefault(parent if parent in nodes else None, []).append(uuid)
    for siblings in children.values():
        siblings.sort(key=sort_key)

    turns: list[_Turn] = []
    visited: set[str] = set()
    pending_roots = list(children.get(None, []))
    # Nodes in a parentUuid cycle have no root; visit them afterwards in sort order.
    reachable = _reachable(children)
    pending_roots.extend(sorted((uuid for uuid in nodes if uuid not in reachable), key=sort_key))
    for root in pending_roots:
        stack: list[tuple[str, str | None]] = [(root, None)]
        while stack:
            uuid, parent_turn = stack.pop()
            if uuid in visited:
                continue
            visited.add(uuid)
            turn = _build_turn(uuid, nodes[uuid][1], parent_turn, results)
            if turn is not None:
                turns.append(turn)
                parent_turn = turn.uuid
            stack.extend((child, parent_turn) for child in reversed(children.get(uuid, [])))
    return tuple(turns)


def _reachable(children: Mapping[str | None, list[str]]) -> set[str]:
    reached: set[str] = set()
    stack = list(children.get(None, []))
    while stack:
        uuid = stack.pop()
        if uuid not in reached:
            reached.add(uuid)
            stack.extend(children.get(uuid, []))
    return reached


def _tool_results(records: Sequence[dict[str, object]]) -> dict[str, _Result]:
    results: dict[str, _Result] = {}
    for record in records:
        if record.get("type") != "user":
            continue
        tool_use_result = record.get("toolUseResult")
        interrupted = isinstance(tool_use_result, dict) and tool_use_result.get("interrupted") is True
        for block in _blocks(record):
            if block.get("type") != "tool_result":
                continue
            call_id = _text(block.get("tool_use_id"))
            if call_id is None or call_id in results:
                continue
            results[call_id] = _Result(
                is_error=block.get("is_error") is True,
                interrupted=interrupted,
                text=_content_text(block.get("content")),
            )
    return results


def _blocks(record: Mapping[str, object]) -> list[dict[str, object]]:
    message = record.get("message")
    content = message.get("content") if isinstance(message, dict) else None
    if not isinstance(content, list):
        return []
    return [block for block in content if isinstance(block, dict)]


def _content_text(content: object) -> str:
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""
    return "\n".join(
        block["text"]
        for block in content
        if isinstance(block, dict) and block.get("type") == "text" and isinstance(block.get("text"), str)
    )


def _build_turn(
    uuid: str, record: Mapping[str, object], parent_id: str | None, results: Mapping[str, _Result]
) -> _Turn | None:
    role = record.get("type")
    if role not in ("user", "assistant"):
        return None
    message = record.get("message")
    content = message.get("content") if isinstance(message, dict) else None
    blocks = _blocks(record)
    raw_text = content if isinstance(content, str) else _content_text(blocks)
    actions: tuple[_Action, ...] = ()
    if role == "assistant":
        actions = tuple(_action(block, results) for block in blocks if block.get("type") == "tool_use")
        if not raw_text.strip() and not actions:
            return None  # thinking-only or empty record
        kind: TurnKind = "assistant_text" if raw_text.strip() else "tool_only"
    else:
        kind = _user_turn_kind(record, raw_text, has_result=any(block.get("type") == "tool_result" for block in blocks))
    return _Turn(
        uuid=uuid,
        parent_id=parent_id,
        role=role,
        kind=kind,
        at=_text(record.get("timestamp")),
        agent_id=_text(record.get("agentId")),
        sidechain=record.get("isSidechain") is True,
        text=redact(raw_text).text,
        actions=actions,
        prompt_source=_text(record.get("promptSource")),
        version=_text(record.get("version")),
        cwd=_text(record.get("cwd")),
        git_branch=_text(record.get("gitBranch")),
    )


def _user_turn_kind(record: Mapping[str, object], text: str, *, has_result: bool) -> TurnKind:
    # A compact summary can carry turnOrigin "human", so it is checked first.
    if record.get("isCompactSummary") is True:
        return "compact_summary"
    if has_result:
        return "tool_only"
    if record.get("isMeta") is True:
        return "meta"
    origin_field = record.get("origin")
    origin = _text(record.get("turnOrigin")) or (
        _text(origin_field.get("kind")) if isinstance(origin_field, dict) else None
    )
    if origin is not None:
        return "human" if origin == "human" else "notification"
    # Older records have no origin field: a person's message does not start with "<".
    stripped = text.lstrip()
    if stripped.startswith("<task-notification"):
        return "notification"
    if not stripped or stripped.startswith("<") or stripped.startswith(_INTERRUPTED_PREFIX):
        return "meta"
    return "human"


def _action(block: Mapping[str, object], results: Mapping[str, _Result]) -> _Action:
    call_id = _text(block.get("id")) or ""
    tool_input = block.get("input")
    target_key: str | None = None
    target: str | None = None
    if isinstance(tool_input, dict):
        for key in _TARGET_KEYS:
            value = _text(tool_input.get(key))
            if value is not None:
                target_key, target = key, redact(value).text[:_TARGET_LIMIT]
                break
    result = results.get(call_id)
    ok: bool | None = None
    error_head: str | None = None
    if result is not None:
        ok = not (result.is_error or result.interrupted)
        if not ok:
            error_head = _error_head(result.text)
    return _Action(
        action=Action(
            tool=_text(block.get("name")) or "",
            call_id=call_id,
            target=target,
            ok=ok,
            error_head=error_head,
        ),
        target_key=target_key,
        interrupted=result is not None and result.interrupted,
    )


def _error_head(text: str) -> str | None:
    for line in text.splitlines():
        if line.strip():
            return redact(line.strip()).text[:_ERROR_HEAD_LIMIT]
    return None


# Exchanges: an exchange starts at a human turn and is named after it. Turns before the first human
# turn of a scope (slash commands, reminders) join the first exchange. A scope without any human
# turn is one exchange named after its first turn.


def _split_exchanges(turns: Sequence[_Turn]) -> list[list[_Turn]]:
    exchanges: list[list[_Turn]] = []
    leading: list[_Turn] = []
    for turn in turns:
        if turn.kind == "human":
            exchanges.append([*leading, turn])
            leading = []
        elif exchanges:
            exchanges[-1].append(turn)
        else:
            leading.append(turn)
    return exchanges or ([leading] if leading else [])


def _exchange_line(scope: _Scope, turns: Sequence[_Turn], *, seq: int, closed: bool) -> ExchangeLine:
    actions = [action for turn in turns for action in turn.actions]
    times = [turn.at for turn in turns if turn.at]
    tools = Counter(action.action.tool for action in actions)
    human = next((turn for turn in turns if turn.kind == "human"), None)
    return ExchangeLine(
        exchange_id=human.uuid if human else turns[0].uuid,
        seq=seq,
        agent_scope=scope.name,
        subagent_type=scope.subagent_type,
        parent_tool_use_id=scope.parent_tool_use_id,
        started_at=min(times) if times else None,
        ended_at=max(times) if times else None,
        closed=closed,
        prompt_source=human.prompt_source if human else None,
        tools=dict(sorted(tools.items())),
        files_touched=tuple(sorted(set(_targets(actions, "file_path")))),
        commands=tuple(dict.fromkeys(_targets(actions, "command"))),
        errors=sum(1 for action in actions if action.action.ok is False),
        outcome=_outcome(turns, actions, closed=closed),
    )


def _targets(actions: Sequence[_Action], key: str) -> list[str]:
    return [action.action.target for action in actions if action.target_key == key and action.action.target]


def _outcome(turns: Sequence[_Turn], actions: Sequence[_Action], *, closed: bool) -> Outcome:
    if not closed:
        return "open"
    assistant_turns = [turn for turn in turns if turn.role == "assistant"]
    if assistant_turns and assistant_turns[-1].kind == "assistant_text":
        return "answered"
    if actions and actions[-1].interrupted:
        return "interrupted"
    if actions and actions[-1].action.ok is False:
        return "tool_error_unresolved"
    # Closed without a final answer: the person moved on or stopped the agent.
    return "interrupted"


def _turn_line(turn: _Turn, exchange_id: str) -> TurnLine:
    return TurnLine(
        turn_id=turn.uuid,
        parent_id=turn.parent_id,
        exchange_id=exchange_id,
        role=turn.role,
        turn_kind=turn.kind,
        at=turn.at,
        agent_id=turn.agent_id,
        sidechain=turn.sidechain,
        text=turn.text,
        actions=tuple(action.action for action in turn.actions),
    )


def _session_line(
    *,
    main_records: Sequence[Mapping[str, object]],
    subagent_records: Sequence[Mapping[str, object]],
    main_turns: Sequence[_Turn],
    all_turns: Sequence[_Turn],
    source_paths: tuple[str, ...],
    source_sha256: str,
    first_path: str | None,
) -> SessionLine:
    # The session id is the main transcript's file name: Claude Code names the file after the session
    # its hooks report, and the Vault's v1 capture, its cursor and part file names all use that id. A
    # resumed session keeps the records' original `sessionId`, which then differs; it is kept as the
    # parent session id. Without a file name, the records' id is used.
    record_session_id = next(
        (value for record in (*main_records, *subagent_records) if (value := _text(record.get("sessionId")))),
        None,
    )
    session_id = PurePosixPath(first_path).stem if first_path else (record_session_id or "unknown")
    parent_session_id = record_session_id if record_session_id not in (None, session_id) else None
    titles = [
        title for record in main_records if record.get("type") == "ai-title" and (title := _text(record.get("aiTitle")))
    ]
    cwd = next((turn.cwd for turn in main_turns if turn.cwd), None)
    times = [turn.at for turn in all_turns if turn.at]
    return SessionLine(
        session_id=session_id,
        agent=CLAUDE_CODE_AGENT,
        agent_version=next((turn.version for turn in reversed(main_turns) if turn.version), None),
        adapter=CLAUDE_CODE_ADAPTER_VERSION,
        project=PurePosixPath(cwd).name or None if cwd else None,
        cwd=cwd,
        git_branch=next((turn.git_branch for turn in reversed(main_turns) if turn.git_branch), None),
        git_commit=None,  # Claude Code transcripts do not record the commit
        parent_session_id=parent_session_id,
        title=SessionTitle(text=redact(titles[-1]).text, source="ai-title") if titles else None,
        started_at=min(times) if times else None,
        ended_at=max(times) if times else None,
        source_paths=source_paths,
        source_sha256=source_sha256,
    )
