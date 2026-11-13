"""Convert LongMemEval-S (cleaned) haystack sessions to ``vg-session-jsonl/1`` files (spec 2026-11-11 §4.1.4).

The data file is downloaded by a person and is not in this repository:
  https://huggingface.co/datasets/xiaowu0162/longmemeval-cleaned (``longmemeval_s_cleaned.json``)

The file is a JSON list. Each entry has ``question_id``, ``question_type``, ``question``,
``question_date``, ``answer_session_ids`` and three same-length lists: ``haystack_session_ids``,
``haystack_dates`` and ``haystack_sessions`` (a list of ``{"role": "user"|"assistant", "content": str}``).
A ``question_id`` ending in ``_abs`` is an abstention question with no answer session in the haystack;
the retrieval step skips it, which leaves 470 of 500 questions.

One haystack session becomes one normalized file. Each user turn opens a closed exchange; assistant
turns before the first user turn form their own exchange. U+2028, U+2029 and U+0085 in turn text become
``\n``, because the Vault tool splits the file with ``str.splitlines()``. Turn times are the session date plus one
second per turn. The session id is a UUID made from the haystack id, because the Vault tool accepts
only letters, digits and ``-`` in session ids. vault-graph writes only these files; the Vault tool
``sessions capture --normalized`` writes the Vault (see ``longmemeval_run.py``).
"""

from __future__ import annotations

import hashlib
import json
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

from vault_graph.operation.sessions.models import ExchangeLine, NormalizedLine, SessionLine, TurnLine
from vault_graph.operation.sessions.normalized_jsonl import encode_session

AGENT = "claude-code"  # the only agent the Vault tool archives
ADAPTER = "longmemeval-s/1"
PROJECT = "longmemeval"
ABSTENTION_SUFFIX = "_abs"
ROLES = ("user", "assistant")
_UUID_NAMESPACE = uuid.UUID("6f1d5c1e-1f0e-4b8e-9a51-6c6f6e676d65")
_DATE_FORMAT = "%Y/%m/%d (%a) %H:%M"
# json.dumps(ensure_ascii=False) keeps these raw, and the Vault tool's str.splitlines() breaks a JSON line at them.
_LINE_SEPARATORS = str.maketrans({"\u2028": "\n", "\u2029": "\n", "\x85": "\n"})


@dataclass(frozen=True)
class LmeSession:
    haystack_id: str
    date: str
    turns: tuple[tuple[str, str], ...]  # (role, content)


@dataclass(frozen=True)
class LmeQuestion:
    question_id: str
    question_type: str
    question: str
    answer_session_ids: tuple[str, ...]
    sessions: tuple[LmeSession, ...]

    @property
    def abstention(self) -> bool:
        return self.question_id.endswith(ABSTENTION_SUFFIX)


@dataclass(frozen=True)
class WrittenSessions:
    files: tuple[Path, ...]
    haystack_ids: dict[str, str]  # session UUID -> haystack session id


def load_questions(path: Path) -> tuple[LmeQuestion, ...]:
    """Read the data file as JSON only. A repeated haystack session id keeps its first session."""
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError("LongMemEval file must be a JSON list")
    return tuple(_question(entry, number) for number, entry in enumerate(data, start=1))


def select_questions(questions: Sequence[LmeQuestion], *, limit: int | None = None) -> tuple[LmeQuestion, ...]:
    """Non-abstention questions in a fixed order (sha256 of the id), the first ``limit`` of them.

    The order does not follow the file, so the first 20 or 150 spread over every question type, and
    a shorter run is always the start of a longer one.
    """
    kept = sorted(
        (question for question in questions if not question.abstention),
        key=lambda question: hashlib.sha256(question.question_id.encode("utf-8")).hexdigest(),
    )
    return tuple(kept if limit is None else kept[:limit])


def session_uuid(haystack_id: str) -> str:
    return str(uuid.uuid5(_UUID_NAMESPACE, haystack_id))


def normalize_session(session: LmeSession, *, cwd: str) -> tuple[NormalizedLine, ...]:
    started = _parse_date(session.date)
    groups: list[list[tuple[int, str, str]]] = []
    for position, (role, content) in enumerate(session.turns):
        if role == "user" or not groups:
            groups.append([])
        groups[-1].append((position, role, content))
    exchanges: list[NormalizedLine] = []
    for seq, group in enumerate(groups, start=1):
        exchange_id = f"x{seq:04d}"
        exchanges.append(
            ExchangeLine(
                exchange_id=exchange_id,
                seq=seq,
                agent_scope="main",
                subagent_type=None,
                parent_tool_use_id=None,
                started_at=_at(started, group[0][0]),
                ended_at=_at(started, group[-1][0]),
                closed=True,
                prompt_source=None,
                tools={},
                files_touched=(),
                commands=(),
                errors=0,
                outcome="answered",
            )
        )
        exchanges.extend(
            TurnLine(
                turn_id=f"t{position + 1:04d}",
                parent_id=None,
                exchange_id=exchange_id,
                role="user" if role == "user" else "assistant",
                turn_kind="human" if role == "user" else "assistant_text",
                at=_at(started, position),
                agent_id=None,
                sidechain=False,
                text=content.translate(_LINE_SEPARATORS),
                actions=(),
            )
            for position, role, content in group
        )
    header = SessionLine(
        session_id=session_uuid(session.haystack_id),
        agent=AGENT,
        agent_version=None,
        adapter=ADAPTER,
        project=PROJECT,
        cwd=cwd,
        git_branch=None,
        git_commit=None,
        parent_session_id=None,
        title=None,
        started_at=_at(started, 0),
        ended_at=_at(started, max(len(session.turns) - 1, 0)),
        source_paths=(session.haystack_id,),
        source_sha256=hashlib.sha256(
            json.dumps(session.turns, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        ).hexdigest(),
    )
    return (header, *exchanges)


def encode_session_file(session: LmeSession, *, cwd: str) -> str:
    return encode_session(normalize_session(session, cwd=cwd))


def write_question_sessions(question: LmeQuestion, folder: Path, *, cwd: str) -> WrittenSessions:
    """Write one ``<session uuid>.jsonl`` per haystack session into ``folder`` (outside every Vault)."""
    folder.mkdir(parents=True, exist_ok=True)
    files: list[Path] = []
    haystack_ids: dict[str, str] = {}
    for session in question.sessions:
        name = session_uuid(session.haystack_id)
        path = folder / f"{name}.jsonl"
        path.write_text(encode_session_file(session, cwd=cwd), encoding="utf-8")
        files.append(path)
        haystack_ids[name] = session.haystack_id
    return WrittenSessions(files=tuple(files), haystack_ids=haystack_ids)


def _question(entry: object, number: int) -> LmeQuestion:
    if not isinstance(entry, dict):
        raise ValueError(f"entry {number}: must be a JSON object")
    for key in ("question_id", "question_type", "question"):
        if not isinstance(entry.get(key), str):
            raise ValueError(f"entry {number}: {key} must be a string")
    answers = entry.get("answer_session_ids")
    if not isinstance(answers, list) or not all(isinstance(item, str) for item in answers):
        raise ValueError(f"entry {number}: answer_session_ids must be a list of strings")
    ids, dates, sessions = (entry.get(key) for key in ("haystack_session_ids", "haystack_dates", "haystack_sessions"))
    if not (isinstance(ids, list) and isinstance(dates, list) and isinstance(sessions, list)):
        raise ValueError(f"entry {number}: haystack_session_ids, haystack_dates and haystack_sessions must be lists")
    if not len(ids) == len(dates) == len(sessions):
        raise ValueError(f"entry {number}: the three haystack lists must have the same length")
    seen: set[str] = set()
    kept: list[LmeSession] = []
    for haystack_id, date, turns in zip(ids, dates, sessions, strict=True):
        if not isinstance(haystack_id, str) or not isinstance(date, str):
            raise ValueError(f"entry {number}: haystack ids and dates must be strings")
        _parse_date(date)
        parsed = _turns(turns, number)
        if haystack_id in seen:
            continue
        seen.add(haystack_id)
        kept.append(LmeSession(haystack_id=haystack_id, date=date, turns=parsed))
    return LmeQuestion(
        question_id=entry["question_id"],
        question_type=entry["question_type"],
        question=entry["question"],
        answer_session_ids=tuple(answers),
        sessions=tuple(kept),
    )


def _turns(value: object, number: int) -> tuple[tuple[str, str], ...]:
    if not isinstance(value, list):
        raise ValueError(f"entry {number}: a haystack session must be a list of turns")
    turns: list[tuple[str, str]] = []
    for turn in value:
        role = turn.get("role") if isinstance(turn, dict) else None
        content = turn.get("content") if isinstance(turn, dict) else None
        if role not in ROLES or not isinstance(content, str):
            raise ValueError(f"entry {number}: each turn needs role user or assistant and string content")
        turns.append((role, content))
    return tuple(turns)


def _parse_date(value: str) -> datetime:
    try:
        return datetime.strptime(value, _DATE_FORMAT)
    except ValueError:
        raise ValueError(f"haystack date {value!r} is not like '2023/05/20 (Sat) 02:21'") from None


def _at(started: datetime, offset_seconds: int) -> str:
    return (started + timedelta(seconds=offset_seconds)).strftime("%Y-%m-%dT%H:%M:%S.000Z")


__all__ = [
    "LmeQuestion",
    "LmeSession",
    "WrittenSessions",
    "encode_session_file",
    "load_questions",
    "normalize_session",
    "select_questions",
    "session_uuid",
    "write_question_sessions",
]
