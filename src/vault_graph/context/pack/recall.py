"""Session start recall: a four-block Markdown memory bundle (spec 4.2.3, S3, S4, S11, S13).

``recall`` reads only document metadata through injected ports. It never searches and never
opens embeddings or a vector store. Blocks print in order A (pinned memory, ``recall_pins``),
B (memory list), C (change notices), D (how to open a page and, on startup, how many inferred
facts wait in the Vault review queues, F11). Block A takes current in-scope pages
with ``pin: true`` from every linked Vault, has its own 400-token budget, and its pages are not
repeated in block B (spec 2026-11-02 V4, 결정14).

The usage log port stores plain JSON objects. ``injected`` events from one run share the same
``at`` value, which is how a run is told apart from the next one. Usage events never change the
order of block B (§0 rule 5). They are read only to avoid repeating a block C notice.
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
from vault_graph.context.memory.project_scope import UNMAPPED_VAULT_SCOPE, VaultProjectScope, page_in_project
from vault_graph.context.pack.recall_pins import (
    PIN_BLOCK_MAX_TOKENS,
    PinBlock,
    PinEntry,
    is_pinned,
    pin_block,
    pin_line,
    unknown_memory_schema,
)
from vault_graph.indexing.ingestion.document_normalizer import DocumentSnapshot

DEFAULT_RECALL_MAX_TOKENS = 1500
DEFAULT_RECALL_MAX_CHARS = 9000
BLOCK_C_MAX_TOKENS = 150
RECALL_HANDOFF_EXIT_CODE = 3
NOTICE_ONLY_SOURCES = frozenset({"resume", "fork"})
NOTICE_STATUSES = ("superseded", "deprecated", "retired")
FALLBACK_NOTICE_DAYS = 14
# Starting values per spec 4.2.3; adjust after measurement.
CATEGORY_CAPS: Mapping[str, int] = {"question": 8, "decision": 10, "change": 8}
STATUS_MARKS: Mapping[str, str] = {"inferred": "추정", "contested": "논쟁 중"}
# Navigation pages that every Vault publish rewrites. They are not memories, so block B leaves
# them out by page type, whatever the Vault role (결정15). Block A still shows them when pinned.
NAVIGATION_PAGE_TYPES = frozenset({"index", "log", "map", "overview"})
UNKNOWN_TYPE = "기타"

# Vault ``tools/wiki/cli.py`` lists review items by status; ``memory-proposal`` items are the inferred facts.
PENDING_PROPOSALS_COMMAND = "python3 tools/wiki/cli.py review list --status pending"

BLOCK_B_TITLE = "## 기억 목록"
BLOCK_C_TITLE = "## 변경 알림"
BLOCK_D_TITLE = "## 가져오는 방법"

Category = Literal["question", "decision", "change"]


class RecallUnavailable(Exception):
    """Recall cannot run (hand-off, exit code 3). The message is the one-line reason."""


@dataclass(frozen=True)
class RecallScope:
    """Registered Graph Home Vault ids linked to the working folder.

    ``vault_names`` maps a Vault id to its ``vault-map.json`` name. With two or more Vaults the
    name replaces the id in page locations. Ids without a name keep the id.

    ``vault_scopes`` maps a Vault id to its linked projects and ``sharable`` value for the project
    scope rule (spec 2026-11-05 §4.4.2). A Vault without one is treated as linked to this project only.
    """

    project_id: str | None
    vault_ids: tuple[str, ...]
    reason: str | None = None
    warnings: tuple[str, ...] = ()
    vault_names: Mapping[str, str] = field(default_factory=dict)
    vault_scopes: Mapping[str, VaultProjectScope] = field(default_factory=dict)


class RecallScopeResolver(Protocol):
    def resolve(self, cwd: Path) -> RecallScope: ...


class RecallDocumentReader(Protocol):
    def is_indexed(self, vault_id: str) -> bool: ...

    def documents(self, vault_id: str) -> tuple[DocumentSnapshot, ...]: ...

    def body_tokens(self, vault_id: str, document_id: str) -> int: ...

    def body_text(self, vault_id: str, document_id: str) -> str:
        """Indexed body as Markdown, section headings included. Empty when nothing is indexed."""
        ...


class UsageLogPort(Protocol):
    """Append-only usage events. Both methods raise ``OSError`` when the log is unusable."""

    def read_events(self) -> Sequence[Mapping[str, object]]: ...

    def append_events(self, events: Sequence[Mapping[str, object]]) -> None: ...


class ProposalCounter(Protocol):
    """Pending ``memory-proposal`` items in a Vault review queue. Raises ``OSError`` when unreadable."""

    def pending_count(self, vault_id: str) -> int: ...


@dataclass(frozen=True)
class RecallPorts:
    scope: RecallScopeResolver
    documents: RecallDocumentReader
    usage: UsageLogPort
    proposals: ProposalCounter | None = None


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

    library = _Library.load(
        ports.documents,
        indexed,
        project_id=scope.project_id,
        many_vaults=len(indexed) > 1,
        vault_names=scope.vault_names,
        vault_scopes=scope.vault_scopes,
    )
    warnings.extend(_schema_warnings(library))
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
        layout = _layout(
            library, pins=None, notices=notices, items=(), full=False, max_tokens=max_tokens, max_chars=max_chars
        )
    else:
        pins = _block_a(library, max_tokens=min(PIN_BLOCK_MAX_TOKENS, max_tokens))
        items = _block_b_items(library)
        if not items and not notices and not pins.text:
            return _handoff("No memory to recall for this project.", warnings)
        layout = _layout(
            library,
            pins=pins,
            notices=notices,
            items=items,
            full=True,
            max_tokens=max_tokens,
            max_chars=max_chars,
            proposals=_pending_proposals(ports.proposals, indexed, warnings),
        )

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
    retired_reason: str | None = None
    retired_day: str | None = None
    pinned: bool = False
    memory_kind: str | None = None
    summary: str | None = None
    unknown_schema: str | None = None

    @property
    def is_current(self) -> bool:
        return self.status not in STALE_STATUSES

    @property
    def is_pinned_current(self) -> bool:
        return self.pinned and self.is_current

    @property
    def notice_day(self) -> str:
        """A retired page is reported on the day it was retired, which may be later than ``updated``."""
        return self.retired_day if self.status == "retired" and self.retired_day else self.day


@dataclass
class _Library:
    entries: tuple[_Entry, ...]
    vault_ids: tuple[str, ...]
    many_vaults: bool
    token_reader: Callable[[str, str], int]
    body_reader: Callable[[str, str], str]
    vault_names: Mapping[str, str] = field(default_factory=dict)
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
        vault_names: Mapping[str, str],
        vault_scopes: Mapping[str, VaultProjectScope],
    ) -> _Library:
        entries = tuple(
            _entry(
                document,
                project_id=project_id,
                vault_scope=vault_scopes.get(vault_id, UNMAPPED_VAULT_SCOPE),
            )
            for vault_id in vault_ids
            for document in reader.documents(vault_id)
            if document.path.startswith("wiki/")
        )
        return cls(
            entries=entries,
            vault_ids=vault_ids,
            many_vaults=many_vaults,
            token_reader=reader.body_tokens,
            body_reader=reader.body_text,
            vault_names=vault_names,
        )

    def scoped(self) -> Iterable[_Entry]:
        return (entry for entry in self.entries if entry.in_scope)

    def by_id(self, item_id: str) -> _Entry | None:
        return self._by_id.get(item_id)

    def by_target(self, vault_id: str, target: str) -> _Entry | None:
        return self._by_path.get((vault_id, _target_path(target)))

    def location(self, entry: _Entry) -> str:
        return f"{self.label(entry.vault_id)}:{entry.path}" if self.many_vaults else entry.path

    def label(self, vault_id: str) -> str:
        """The map name of a Vault, or its id when the map has no name for it."""
        return self.vault_names.get(vault_id) or vault_id


def _entry(document: DocumentSnapshot, *, project_id: str | None, vault_scope: VaultProjectScope) -> _Entry:
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
        in_scope=page_in_project(frontmatter, project_id, vault_scope=vault_scope),
        supersedes=_targets(frontmatter.get("supersedes")),
        superseded_by=_targets(frontmatter.get("superseded_by")),
        category=_category(document.path, doc_type.casefold(), status),
        retired_reason=_one_line(_text(frontmatter.get("retired_reason"))) or None,
        retired_day=_day(frontmatter.get("retired_at")),
        pinned=is_pinned(frontmatter),
        memory_kind=_text(frontmatter.get("memory_kind")) or None,
        summary=_one_line(_text(frontmatter.get("summary"))) or None,
        unknown_schema=unknown_memory_schema(frontmatter),
    )


def _category(path: str, doc_type: str, status: str | None) -> Category:
    if (path.startswith("wiki/issues/") or doc_type in ISSUE_TYPES) and status not in CLOSED_ISSUE_STATUSES:
        return "question"
    if path.startswith("wiki/decisions/") or doc_type == "decision":
        return "decision"
    return "change"


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

_LISTED_BLOCKS = frozenset({"A", "B"})


@dataclass(frozen=True)
class _History:
    base_items: Mapping[str, str]  # item id -> content hash in the last run that printed block A or B
    has_base: bool
    noticed: frozenset[str]  # block C items already reported after that run

    @classmethod
    def from_events(cls, events: Sequence[Mapping[str, object]], *, project_id: str | None) -> _History:
        runs: dict[str, list[Mapping[str, object]]] = {}
        for event in events:
            if event.get("event") == "injected" and event.get("project") == project_id:
                runs.setdefault(str(event.get("at", "")), []).append(event)
        b_runs = sorted(at for at, run in runs.items() if any(event.get("block") in _LISTED_BLOCKS for event in run))
        base_at = b_runs[-1] if b_runs else ""
        base_items = {
            str(event.get("item_id")): str(event.get("content_hash", ""))
            for event in runs.get(base_at, ())
            if event.get("block") in _LISTED_BLOCKS
        }
        noticed = frozenset(
            str(event.get("item_id"))
            for at, run in runs.items()
            if at >= base_at
            for event in run
            if event.get("block") == "C"
        )
        return cls(base_items=base_items, has_base=bool(b_runs), noticed=noticed)


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
        changed = [entry for entry in library.scoped() if entry.notice_day >= since]
    noticed = history.noticed if history is not None else frozenset()
    selected = sorted(
        (entry for entry in changed if entry.status in NOTICE_STATUSES and entry.item_id not in noticed),
        key=lambda entry: (entry.notice_day, entry.path),
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


def _schema_warnings(library: _Library) -> list[str]:
    """One line for every in-scope page whose ``memory_schema`` is unknown. Those pages stay regular."""
    unknown = sorted((entry for entry in library.scoped() if entry.unknown_schema), key=lambda e: (e.vault_id, e.path))
    if not unknown:
        return []
    pages = ", ".join(f"{library.location(entry)} ({entry.unknown_schema})" for entry in unknown)
    return [_one_line(f"Unknown memory_schema, shown as regular pages: {pages}")]


def _block_a(library: _Library, *, max_tokens: int) -> PinBlock:
    pins = tuple(
        PinEntry(
            item_id=entry.item_id,
            kind=entry.memory_kind or entry.type,
            title=entry.title,
            summary=pin_line(
                title=entry.title,
                summary=entry.summary,
                body=library.body_reader(entry.vault_id, entry.document_id),
            ),
            location=library.location(entry),
            day=entry.day,
            path=entry.path,
        )
        for entry in library.scoped()
        if entry.is_pinned_current
    )
    return pin_block(pins, max_tokens=max_tokens)


def _block_b_items(library: _Library) -> tuple[_Entry, ...]:
    """Newest ``updated`` first across every linked Vault, ties by (Vault name, path). Usage is not read.

    The Vault name is the map name, or the Vault id without one. The id breaks any remaining tie.

    Pinned pages belong to block A, including the ones block A had to leave out for its budget.
    Navigation pages (``NAVIGATION_PAGE_TYPES``) are never listed.
    """
    current = sorted(
        (
            entry
            for entry in library.scoped()
            if entry.is_current and not entry.pinned and entry.type.casefold() not in NAVIGATION_PAGE_TYPES
        ),
        key=lambda e: (library.label(e.vault_id), e.path, e.vault_id),
    )
    ordered = sorted(current, key=lambda entry: entry.day, reverse=True)
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
    pins: PinBlock | None,
    notices: tuple[_Notice, ...],
    items: tuple[_Entry, ...],
    full: bool,
    max_tokens: int,
    max_chars: int,
    proposals: Mapping[str, int] | None = None,
) -> _Layout:
    def fits(text: str) -> bool:
        return estimate_recall_tokens(text) <= max_tokens and len(text) <= max_chars

    notice_lines: list[str] = []
    for notice in notices:
        candidate = [*notice_lines, _notice_line(notice)]
        if estimate_recall_tokens(_block(BLOCK_C_TITLE, candidate)) > BLOCK_C_MAX_TOKENS:
            break
        notice_lines = candidate
    block_d = _block(BLOCK_D_TITLE, [_how_to_open(library), *_proposal_lines(library, proposals or {})]) if full else ""
    item_lines = [_item_line(library, entry) for entry in items]

    def render(shown_items: int, shown_notices: int) -> str:
        blocks: list[str] = [pins.text] if pins is not None and pins.text else []
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
    pinned_shown = tuple(("A", library.by_id(pin.item_id)) for pin in pins.shown) if pins is not None else ()
    shown = (
        tuple((block, entry) for block, entry in pinned_shown if entry is not None)
        + tuple(("B", entry) for entry in items[:shown_items])
        + tuple(("C", notice.entry) for notice in notices[:shown_notices])
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
    entry = notice.entry
    if notice.replacement:
        replacement = notice.replacement
    elif entry.status == "retired" and entry.retired_reason:
        replacement = f"폐기됨: {entry.retired_reason}"
    else:
        replacement = "폐기됨"
    return f"- [{entry.item_id}] {entry.title} → {replacement} ({entry.notice_day})"


def _how_to_open(library: _Library) -> str:
    renamed = library.many_vaults and any(library.label(vault_id) != vault_id for vault_id in library.vault_ids)
    if renamed:
        prefix = " 경로 앞은 Vault 이름이다. 이름=vault_id:"
        ids = ", ".join(
            f"{library.label(vault_id)}={vault_id}" if library.label(vault_id) != vault_id else vault_id
            for vault_id in library.vault_ids
        )
    else:
        prefix = " 경로 앞 이름이 vault_id다. vault_id:" if library.many_vaults else " vault_id:"
        ids = ", ".join(library.vault_ids)
    return f"- 본문은 MCP 리소스 `vault://{{vault_id}}/pages/{{path}}`로 연다(path의 `/`는 `%2F`).{prefix} {ids}"


def _pending_proposals(
    counter: ProposalCounter | None, vault_ids: Sequence[str], warnings: list[str]
) -> dict[str, int]:
    """Pending proposal count per Vault, for block D (F11). An unreadable queue only warns."""
    if counter is None:
        return {}
    counts: dict[str, int] = {}
    for vault_id in vault_ids:
        try:
            counts[vault_id] = counter.pending_count(vault_id)
        except OSError as exc:
            warnings.append(_one_line(f"Review queue of Vault {vault_id} was not read: {exc}"))
    return counts


def _proposal_lines(library: _Library, counts: Mapping[str, int]) -> list[str]:
    """One line when inferred facts wait for a person in any linked Vault review queue."""
    waiting = ", ".join(f"{library.label(vault_id)} {counts[vault_id]}개" for vault_id in counts if counts[vault_id])
    if not waiting:
        return []
    return [f"- 승인을 기다리는 추론 제안: {waiting}. 확인은 그 Vault 폴더에서 `{PENDING_PROPOSALS_COMMAND}`"]


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
    "NAVIGATION_PAGE_TYPES",
    "PENDING_PROPOSALS_COMMAND",
    "RECALL_HANDOFF_EXIT_CODE",
    "ProposalCounter",
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
