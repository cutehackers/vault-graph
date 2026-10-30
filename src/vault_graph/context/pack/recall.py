"""Session start recall: a four-block Markdown memory bundle (spec 4.2.3, S3, S4, S11, S13).

``recall`` reads only document metadata through injected ports. It never searches and never
opens embeddings or a vector store. Blocks print in order A (pinned core), B (memory list),
C (change notices), D (how to open a page). Block A stays empty until Vault pages carry
``pin``/``memory_kind`` (spec 의존5), so its heading is never printed today.

The usage log port stores plain JSON objects. ``injected`` events from one run share the same
``at`` value, which is how a run is told apart from the next one.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Literal, Protocol

from vault_graph.context.memory.issue_memory import EXCLUDED_STATUSES as CLOSED_ISSUE_STATUSES
from vault_graph.context.memory.issue_memory import ISSUE_TYPES
from vault_graph.context.memory.project_memory import STALE_STATUSES
from vault_graph.indexing.ingestion.document_normalizer import DocumentSnapshot

DEFAULT_RECALL_MAX_TOKENS = 1500
DEFAULT_RECALL_MAX_CHARS = 9000
BLOCK_C_MAX_TOKENS = 150
RECALL_HANDOFF_EXIT_CODE = 3
NOTICE_ONLY_SOURCES = frozenset({"resume", "fork"})
NOTICE_STATUSES = ("superseded", "deprecated")
FALLBACK_NOTICE_DAYS = 14
DEMOTE_AFTER_INJECTIONS = 10
# Starting values per spec 4.2.3; adjust after measurement.
CATEGORY_CAPS: Mapping[str, int] = {"question": 8, "decision": 10, "change": 8}
STATUS_MARKS: Mapping[str, str] = {"inferred": "추정", "contested": "논쟁 중"}
UNKNOWN_TYPE = "기타"

BLOCK_B_TITLE = "## 기억 목록"
BLOCK_C_TITLE = "## 변경 알림"
BLOCK_D_TITLE = "## 가져오는 방법"

Category = Literal["question", "decision", "change"]


class RecallUnavailable(Exception):
    """Recall cannot run (hand-off, exit code 3). The message is the one-line reason."""


@dataclass(frozen=True)
class RecallScope:
    """Registered Graph Home Vault ids linked to the working folder."""

    project_id: str | None
    vault_ids: tuple[str, ...]
    reason: str | None = None
    warnings: tuple[str, ...] = ()


class RecallScopeResolver(Protocol):
    def resolve(self, cwd: Path) -> RecallScope: ...


class RecallDocumentReader(Protocol):
    def is_indexed(self, vault_id: str) -> bool: ...

    def documents(self, vault_id: str) -> tuple[DocumentSnapshot, ...]: ...

    def body_tokens(self, vault_id: str, document_id: str) -> int: ...


class UsageLogPort(Protocol):
    """Append-only usage events. Both methods raise ``OSError`` when the log is unusable."""

    def read_events(self) -> Sequence[Mapping[str, object]]: ...

    def append_events(self, events: Sequence[Mapping[str, object]]) -> None: ...


@dataclass(frozen=True)
class RecallPorts:
    scope: RecallScopeResolver
    documents: RecallDocumentReader
    usage: UsageLogPort


@dataclass(frozen=True)
class RecallBundle:
    """``text`` is printed as is. ``reason`` is set only for a hand-off."""

    text: str
    handoff: bool = False
    reason: str | None = None
    warnings: tuple[str, ...] = ()
    injected_count: int = 0

    @property
    def exit_code(self) -> int:
        return RECALL_HANDOFF_EXIT_CODE if self.handoff else 0


def estimate_recall_tokens(text: str) -> int:
    """Whitespace token count, the same estimate the context pack uses for excerpts."""
    return len(text.split())


def memory_item_id(vault_id: str, path: str) -> str:
    """Short stable id that links ``injected`` and ``fetched`` events of one document."""
    return "m:" + hashlib.sha256(f"{vault_id}\0{path}".encode()).hexdigest()[:8]


def fetched_event(*, vault_id: str, path: str, at: datetime, session_id: str | None = None) -> dict[str, object]:
    return {
        "event": "fetched",
        "item_id": memory_item_id(vault_id, path),
        "vault_id": vault_id,
        "path": path,
        "session_id": session_id,
        "at": at.isoformat(),
    }


def recall(
    cwd: Path,
    *,
    source: str,
    session_id: str,
    max_tokens: int = DEFAULT_RECALL_MAX_TOKENS,
    max_chars: int = DEFAULT_RECALL_MAX_CHARS,
    ports: RecallPorts,
    now: datetime | None = None,
) -> RecallBundle:
    moment = now or datetime.now(UTC)
    scope = ports.scope.resolve(cwd)
    if not scope.vault_ids:
        return _handoff(scope.reason or f"No Vault is linked to {cwd}.")
    indexed = tuple(vault_id for vault_id in scope.vault_ids if ports.documents.is_indexed(vault_id))
    if not indexed:
        return _handoff(f"No index for Vault {', '.join(scope.vault_ids)}. Run `vg index`.")
    warnings = list(scope.warnings)
    warnings.extend(
        f"Vault {vault_id} has no index. Run `vg index`." for vault_id in scope.vault_ids if vault_id not in indexed
    )

    library = _Library.load(ports.documents, indexed, project_id=scope.project_id, many_vaults=len(indexed) > 1)
    history: _History | None
    try:
        history = _History.from_events(ports.usage.read_events(), project_id=scope.project_id)
    except OSError as exc:
        history = None
        warnings.append(_one_line(f"Usage log was not read: {exc}"))

    notices = _notices(library, history, today=moment.date())
    if source in NOTICE_ONLY_SOURCES:
        if not notices:
            return RecallBundle(text="", warnings=tuple(warnings))
        layout = _layout(library, notices=notices, items=(), full=False, max_tokens=max_tokens, max_chars=max_chars)
    else:
        items = _block_b_items(library, history)
        if not items and not notices:
            return _handoff("No memory to recall for this project.", warnings)
        layout = _layout(library, notices=notices, items=items, full=True, max_tokens=max_tokens, max_chars=max_chars)

    events = [
        _injected_event(entry, block=block, session_id=session_id, project_id=scope.project_id, at=moment)
        for block, entry in layout.shown
    ]
    try:
        ports.usage.append_events(events)
    except OSError as exc:
        warnings.append(_one_line(f"Usage log was not written: {exc}"))
    return RecallBundle(text=layout.text, warnings=tuple(warnings), injected_count=len(events))


# Documents -----------------------------------------------------------------------------------


@dataclass(frozen=True)
class _Entry:
    item_id: str
    vault_id: str
    document_id: str
    path: str
    title: str
    type: str
    status: str | None
    day: str
    content_hash: str
    in_scope: bool
    supersedes: tuple[str, ...]
    superseded_by: tuple[str, ...]
    category: Category

    @property
    def is_current(self) -> bool:
        return self.status not in STALE_STATUSES


@dataclass
class _Library:
    entries: tuple[_Entry, ...]
    vault_ids: tuple[str, ...]
    many_vaults: bool
    token_reader: Callable[[str, str], int]
    _by_path: dict[tuple[str, str], _Entry] = field(default_factory=dict)
    _by_id: dict[str, _Entry] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self._by_path = {(entry.vault_id, entry.path): entry for entry in self.entries}
        self._by_id = {entry.item_id: entry for entry in self.entries}

    @classmethod
    def load(
        cls,
        reader: RecallDocumentReader,
        vault_ids: tuple[str, ...],
        *,
        project_id: str | None,
        many_vaults: bool,
    ) -> _Library:
        entries = tuple(
            _entry(document, project_id=project_id)
            for vault_id in vault_ids
            for document in reader.documents(vault_id)
            if document.path.startswith("wiki/")
        )
        return cls(entries=entries, vault_ids=vault_ids, many_vaults=many_vaults, token_reader=reader.body_tokens)

    def scoped(self) -> Iterable[_Entry]:
        return (entry for entry in self.entries if entry.in_scope)

    def by_id(self, item_id: str) -> _Entry | None:
        return self._by_id.get(item_id)

    def by_target(self, vault_id: str, target: str) -> _Entry | None:
        return self._by_path.get((vault_id, _target_path(target)))

    def location(self, entry: _Entry) -> str:
        return f"{entry.vault_id}:{entry.path}" if self.many_vaults else entry.path


def _entry(document: DocumentSnapshot, *, project_id: str | None) -> _Entry:
    frontmatter = document.frontmatter
    status = _text(frontmatter.get("status")).casefold() or None
    doc_type = _text(frontmatter.get("type"))
    return _Entry(
        item_id=memory_item_id(document.vault_id, document.path),
        vault_id=document.vault_id,
        document_id=document.document_id,
        path=document.path,
        title=_title(document),
        type=doc_type or UNKNOWN_TYPE,
        status=status,
        day=_day(frontmatter.get("updated")) or (document.last_indexed_at or document.last_seen_at)[:10],
        content_hash=document.content_hash,
        in_scope=_in_project(frontmatter.get("project"), project_id),
        supersedes=_targets(frontmatter.get("supersedes")),
        superseded_by=_targets(frontmatter.get("superseded_by")),
        category=_category(document.path, doc_type.casefold(), status),
    )


def _category(path: str, doc_type: str, status: str | None) -> Category:
    if (path.startswith("wiki/issues/") or doc_type in ISSUE_TYPES) and status not in CLOSED_ISSUE_STATUSES:
        return "question"
    if path.startswith("wiki/decisions/") or doc_type == "decision":
        return "decision"
    return "change"


def _in_project(value: object, project_id: str | None) -> bool:
    """A page without ``project`` belongs to every project of its Vault."""
    if value is None or value == "" or value == []:
        return True
    values = value if isinstance(value, list) else [value]
    return project_id is not None and project_id in {str(item).strip() for item in values}


def _title(document: DocumentSnapshot) -> str:
    for key in ("title", "name"):
        value = _text(document.frontmatter.get(key))
        if value:
            return " ".join(value.split())
    return document.path.rsplit("/", 1)[-1].removesuffix(".md")


def _text(value: object) -> str:
    return value.strip() if isinstance(value, str) else ""


def _day(value: object) -> str | None:
    text = str(value).strip() if isinstance(value, str | date) else ""
    try:
        return date.fromisoformat(text[:10]).isoformat()
    except ValueError:
        return None


def _targets(value: object) -> tuple[str, ...]:
    values = value if isinstance(value, list) else [value] if isinstance(value, str) else []
    return tuple(str(item).strip() for item in values if str(item).strip())


def _target_path(target: str) -> str:
    """Vault lifecycle targets are wiki links: ``decisions/x``, ``wiki/decisions/x.md`` and so on."""
    normalized = target.strip().strip("[]").removeprefix("/").removeprefix("wiki/").removesuffix(".md")
    return f"wiki/{normalized}.md"


# Usage history -------------------------------------------------------------------------------


@dataclass(frozen=True)
class _History:
    base_items: Mapping[str, str]  # item id -> content hash in the last run that printed block B
    has_base: bool
    noticed: frozenset[str]  # block C items already reported after that run
    demoted: frozenset[str]

    @classmethod
    def from_events(cls, events: Sequence[Mapping[str, object]], *, project_id: str | None) -> _History:
        runs: dict[str, list[Mapping[str, object]]] = {}
        fetched: dict[str, list[str]] = {}
        for event in events:
            item_id = str(event.get("item_id", ""))
            at = str(event.get("at", ""))
            if event.get("event") == "fetched":
                fetched.setdefault(item_id, []).append(at)
            elif event.get("event") == "injected" and event.get("project") == project_id:
                runs.setdefault(at, []).append(event)
        b_runs = sorted(at for at, run in runs.items() if any(event.get("block") == "B" for event in run))
        base_at = b_runs[-1] if b_runs else ""
        base_items = {
            str(event.get("item_id")): str(event.get("content_hash", ""))
            for event in runs.get(base_at, ())
            if event.get("block") == "B"
        }
        noticed = frozenset(
            str(event.get("item_id"))
            for at, run in runs.items()
            if at >= base_at
            for event in run
            if event.get("block") == "C"
        )
        injected_at: dict[str, list[str]] = {}
        for at in b_runs:
            for event in runs[at]:
                if event.get("block") == "B":
                    injected_at.setdefault(str(event.get("item_id")), []).append(at)
        demoted = frozenset(
            item_id
            for item_id, times in injected_at.items()
            if len(times) >= DEMOTE_AFTER_INJECTIONS
            and not any(at >= times[-DEMOTE_AFTER_INJECTIONS] for at in fetched.get(item_id, ()))
        )
        return cls(base_items=base_items, has_base=bool(b_runs), noticed=noticed, demoted=demoted)


# Blocks --------------------------------------------------------------------------------------


@dataclass(frozen=True)
class _Notice:
    entry: _Entry
    replacement: str | None


def _notices(library: _Library, history: _History | None, *, today: date) -> tuple[_Notice, ...]:
    if history is not None and history.has_base:
        candidates = [library.by_id(item_id) for item_id in history.base_items]
        changed = [entry for entry in candidates if entry is not None and entry.in_scope]
    else:
        since = (today - timedelta(days=FALLBACK_NOTICE_DAYS)).isoformat()
        changed = [entry for entry in library.scoped() if entry.day >= since]
    noticed = history.noticed if history is not None else frozenset()
    selected = sorted(
        (entry for entry in changed if entry.status in NOTICE_STATUSES and entry.item_id not in noticed),
        key=lambda entry: (entry.day, entry.path),
        reverse=True,
    )
    return tuple(_Notice(entry=entry, replacement=_replacement(library, entry)) for entry in selected)


def _replacement(library: _Library, entry: _Entry) -> str | None:
    if entry.status != "superseded":
        return None
    if entry.superseded_by:
        target = entry.superseded_by[0]
        found = library.by_target(entry.vault_id, target)
        if found is not None and found.in_scope:
            return found.title
        return library.location(found) if found is not None else _target_path(target)
    reverse = [
        other
        for other in library.entries
        if other.vault_id == entry.vault_id and any(_target_path(t) == entry.path for t in other.supersedes)
    ]
    reverse.sort(key=lambda other: (not other.in_scope, other.path))
    if reverse:
        return reverse[0].title if reverse[0].in_scope else library.location(reverse[0])
    return None


def _block_b_items(library: _Library, history: _History | None) -> tuple[_Entry, ...]:
    ordered = sorted(
        (entry for entry in library.scoped() if entry.is_current),
        key=lambda entry: (entry.day, entry.path),
        reverse=True,
    )
    if history is not None:
        changed = [
            e for e in ordered if e.item_id in history.base_items and history.base_items[e.item_id] != e.content_hash
        ]
        ordered = changed + [entry for entry in ordered if entry not in changed]
        for index in range(len(ordered) - 2, -1, -1):
            if ordered[index].item_id in history.demoted:
                ordered[index], ordered[index + 1] = ordered[index + 1], ordered[index]
    counts: dict[str, int] = {}
    selected: list[_Entry] = []
    for entry in ordered:
        if counts.get(entry.category, 0) < CATEGORY_CAPS[entry.category]:
            counts[entry.category] = counts.get(entry.category, 0) + 1
            selected.append(entry)
    return tuple(selected)


@dataclass(frozen=True)
class _Layout:
    text: str
    shown: tuple[tuple[str, _Entry], ...]


def _layout(
    library: _Library,
    *,
    notices: tuple[_Notice, ...],
    items: tuple[_Entry, ...],
    full: bool,
    max_tokens: int,
    max_chars: int,
) -> _Layout:
    def fits(text: str) -> bool:
        return estimate_recall_tokens(text) <= max_tokens and len(text) <= max_chars

    notice_lines: list[str] = []
    for notice in notices:
        candidate = [*notice_lines, _notice_line(notice)]
        if estimate_recall_tokens(_block(BLOCK_C_TITLE, candidate)) > BLOCK_C_MAX_TOKENS:
            break
        notice_lines = candidate
    block_d = _block(BLOCK_D_TITLE, [_how_to_open(library)]) if full else ""
    item_lines = [_item_line(library, entry) for entry in items]

    def render(shown_items: int, shown_notices: int) -> str:
        blocks: list[str] = []
        if items:
            omitted = len(items) - shown_items
            lines = item_lines[:shown_items] + ([f"- {omitted}개 생략"] if omitted else [])
            blocks.append(_block(BLOCK_B_TITLE, lines))
        if shown_notices:
            blocks.append(_block(BLOCK_C_TITLE, notice_lines[:shown_notices]))
        if block_d:
            blocks.append(block_d)
        return "\n".join(blocks)

    shown_notices = len(notice_lines)
    while shown_notices and not fits(render(0, shown_notices)):
        shown_notices -= 1
    shown_items = len(items)
    while shown_items and not fits(render(shown_items, shown_notices)):
        shown_items -= 1
    text = render(shown_items, shown_notices)
    shown = tuple(("B", entry) for entry in items[:shown_items]) + tuple(
        ("C", notice.entry) for notice in notices[:shown_notices]
    )
    return _Layout(text=text if fits(text) else "", shown=shown if fits(text) else ())


def _block(title: str, lines: Sequence[str]) -> str:
    return title + "\n" + "".join(line + "\n" for line in lines)


def _item_line(library: _Library, entry: _Entry) -> str:
    mark = STATUS_MARKS.get(entry.status or "")
    status = f"{entry.status}({mark})" if mark else entry.status or "-"
    tokens = library.token_reader(entry.vault_id, entry.document_id)
    return (
        f"- [{entry.item_id}] {entry.type} · {entry.day} · {status} · {entry.title} "
        f"({library.location(entry)}, ~{tokens}t)"
    )


def _notice_line(notice: _Notice) -> str:
    replacement = notice.replacement or "폐기됨"
    return f"- [{notice.entry.item_id}] {notice.entry.title} → {replacement} ({notice.entry.day})"


def _how_to_open(library: _Library) -> str:
    prefix = " 경로 앞 이름이 vault_id다." if library.many_vaults else ""
    return (
        "- 본문은 MCP 리소스 `vault://{vault_id}/pages/{path}`로 연다(path의 `/`는 `%2F`)."
        f"{prefix} vault_id: {', '.join(library.vault_ids)}"
    )


def _injected_event(
    entry: _Entry, *, block: str, session_id: str, project_id: str | None, at: datetime
) -> dict[str, object]:
    return {
        "event": "injected",
        "item_id": entry.item_id,
        "block": block,
        "vault_id": entry.vault_id,
        "path": entry.path,
        "content_hash": entry.content_hash,
        "session_id": session_id,
        "project": project_id,
        "at": at.isoformat(),
    }


def _handoff(reason: str, warnings: Iterable[str] = ()) -> RecallBundle:
    return RecallBundle(text="", handoff=True, reason=_one_line(reason), warnings=tuple(warnings))


def _one_line(text: str) -> str:
    return " ".join(text.split())


__all__ = [
    "BLOCK_C_MAX_TOKENS",
    "DEFAULT_RECALL_MAX_CHARS",
    "DEFAULT_RECALL_MAX_TOKENS",
    "RECALL_HANDOFF_EXIT_CODE",
    "RecallBundle",
    "RecallDocumentReader",
    "RecallPorts",
    "RecallScope",
    "RecallScopeResolver",
    "RecallUnavailable",
    "UsageLogPort",
    "estimate_recall_tokens",
    "fetched_event",
    "memory_item_id",
    "recall",
]
