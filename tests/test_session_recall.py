"""Session start recall bundle with in-memory ports (spec 4.2.3, S3, S4, S11, S13, A-10)."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from vault_graph.context.pack.recall import (
    DEFAULT_RECALL_MAX_CHARS,
    DEFAULT_RECALL_MAX_TOKENS,
    RecallBundle,
    RecallPorts,
    RecallScope,
    estimate_recall_tokens,
    fetched_event,
    memory_item_id,
    recall,
)
from vault_graph.indexing.ingestion.document_normalizer import DocumentSnapshot

NOW = datetime(2026, 10, 30, 9, 0, tzinfo=UTC)
CWD = Path("/repos/alpha")


def day(offset: int) -> str:
    return (NOW - timedelta(days=offset)).date().isoformat()


def doc(path: str, *, vault_id: str = "main", content_hash: str = "h1", **frontmatter: Any) -> DocumentSnapshot:
    return DocumentSnapshot(
        vault_id=vault_id,
        document_id=f"{vault_id}:{path}",
        path=path,
        kind=path.split("/", 1)[0],
        frontmatter=frontmatter,
        frontmatter_hash="fm",
        content_hash=content_hash,
        raw_sha256="raw",
        parser_version="parser",
        last_seen_at="2026-01-01T00:00:00+00:00",
        last_indexed_at=None,
        vault_revision=None,
        index_revision=None,
    )


@dataclass
class FakeScope:
    scope: RecallScope

    def resolve(self, cwd: Path) -> RecallScope:
        return self.scope


@dataclass
class FakeDocuments:
    by_vault: dict[str, tuple[DocumentSnapshot, ...]]
    indexed: set[str] | None = None
    tokens: int = 42

    def is_indexed(self, vault_id: str) -> bool:
        return vault_id in (self.indexed if self.indexed is not None else set(self.by_vault))

    def documents(self, vault_id: str) -> tuple[DocumentSnapshot, ...]:
        return self.by_vault.get(vault_id, ())

    def body_tokens(self, vault_id: str, document_id: str) -> int:
        return self.tokens


@dataclass
class FakeUsage:
    events: list[dict[str, object]] = field(default_factory=list)
    fail_read: bool = False
    fail_write: bool = False

    def read_events(self) -> tuple[Mapping[str, object], ...]:
        if self.fail_read:
            raise PermissionError("usage unreadable")
        return tuple(self.events)

    def append_events(self, events: Sequence[Mapping[str, object]]) -> None:
        if self.fail_write:
            raise PermissionError("usage read-only")
        self.events.extend(dict(event) for event in events)


def ports(
    documents: Sequence[DocumentSnapshot],
    *,
    usage: FakeUsage | None = None,
    vault_ids: tuple[str, ...] = ("main",),
    project_id: str | None = "alpha",
    indexed: set[str] | None = None,
) -> RecallPorts:
    by_vault: dict[str, tuple[DocumentSnapshot, ...]] = {}
    for item in documents:
        by_vault[item.vault_id] = (*by_vault.get(item.vault_id, ()), item)
    return RecallPorts(
        scope=FakeScope(RecallScope(project_id=project_id, vault_ids=vault_ids)),
        documents=FakeDocuments(by_vault, indexed=indexed),
        usage=usage if usage is not None else FakeUsage(),
    )


def run(
    recall_ports: RecallPorts,
    *,
    source: str = "startup",
    max_tokens: int = DEFAULT_RECALL_MAX_TOKENS,
    now: datetime = NOW,
) -> RecallBundle:
    return recall(
        CWD,
        source=source,
        session_id="s-1",
        max_tokens=max_tokens,
        max_chars=DEFAULT_RECALL_MAX_CHARS,
        ports=recall_ports,
        now=now,
    )


def section(text: str, title: str) -> list[str]:
    lines = text.splitlines()
    start = lines.index(title)
    end = next((index for index in range(start + 1, len(lines)) if lines[index].startswith("## ")), len(lines))
    return [line for line in lines[start + 1 : end] if line]


BASE_DOCS = (
    doc("wiki/decisions/use-sqlite.md", title="Use SQLite", type="decision", status="active", updated=day(1)),
    doc("wiki/issues/open-budget.md", title="Budget question", type="issue", status="open", updated=day(2)),
    doc("wiki/concepts/guess.md", title="Guessed rule", type="concept", status="inferred", updated=day(3)),
    doc("wiki/concepts/argued.md", title="Argued rule", type="concept", status="contested", updated=day(4)),
    doc("wiki/workflows/alpha-flow.md", title="Alpha flow", type="workflow", project="alpha", updated=day(5)),
    doc("wiki/workflows/beta-flow.md", title="Beta flow", type="workflow", project=["beta"], updated=day(1)),
    doc("wiki/notes/untyped.md", title="Untyped note", updated=day(6)),
    doc("wiki/decisions/old.md", title="Old choice", type="decision", status="superseded", updated=day(60)),
    doc("wiki/decisions/stale.md", title="Stale choice", type="decision", status="stale", updated=day(1)),
    doc("wiki/decisions/dropped.md", title="Dropped choice", type="decision", status="deprecated", updated=day(90)),
    doc("raw/sources/a.md", title="Raw source", type="source", updated=day(0)),
)


def test_startup_prints_blocks_b_and_d_without_empty_a_or_c_within_limits() -> None:
    bundle = run(ports(BASE_DOCS))

    assert bundle.exit_code == 0
    headings = [line for line in bundle.text.splitlines() if line.startswith("## ")]
    assert headings == ["## 기억 목록", "## 가져오는 방법"]
    assert estimate_recall_tokens(bundle.text) <= DEFAULT_RECALL_MAX_TOKENS
    assert len(bundle.text) <= DEFAULT_RECALL_MAX_CHARS
    assert "vault://{vault_id}/pages/{path}" in bundle.text


def test_block_b_lines_carry_every_field_and_skip_closed_or_foreign_documents() -> None:
    lines = section(run(ports(BASE_DOCS)).text, "## 기억 목록")

    line_pattern = re.compile(r"^- \[m:[0-9a-f]{8}\] \S+ · \d{4}-\d{2}-\d{2} · .+ · .+ \(wiki/\S+\.md, ~\d+t\)$")
    assert lines and all(line_pattern.match(line) for line in lines), lines
    joined = "\n".join(lines)
    for title in ("Old choice", "Stale choice", "Dropped choice", "Beta flow", "Raw source"):
        assert title not in joined
    assert lines[0] == (
        f"- [{memory_item_id('main', 'wiki/decisions/use-sqlite.md')}] decision · {day(1)} · active · "
        "Use SQLite (wiki/decisions/use-sqlite.md, ~42t)"
    )
    assert any("inferred(추정) · Guessed rule" in line for line in lines)
    assert any("contested(논쟁 중) · Argued rule" in line for line in lines)
    assert any("] 기타 · " in line and "Untyped note" in line for line in lines)
    assert any("Alpha flow" in line for line in lines)


def test_block_b_is_newest_first() -> None:
    lines = section(run(ports(BASE_DOCS)).text, "## 기억 목록")

    dates = [line.split(" · ")[1] for line in lines]
    assert dates == sorted(dates, reverse=True)


def test_documents_of_vaults_outside_the_project_are_not_read() -> None:
    other = doc("wiki/decisions/other.md", vault_id="other", title="Other vault decision", updated=day(0))

    bundle = run(ports((*BASE_DOCS, other)))

    assert "Other vault decision" not in bundle.text


def test_several_vaults_prefix_paths_with_the_vault_id() -> None:
    other = doc("wiki/decisions/other.md", vault_id="other", title="Other vault decision", updated=day(0))

    bundle = run(ports((*BASE_DOCS, other), vault_ids=("main", "other")))

    assert "(other:wiki/decisions/other.md, ~42t)" in bundle.text
    assert "(main:wiki/decisions/use-sqlite.md, ~42t)" in bundle.text
    assert "main, other" in section(bundle.text, "## 가져오는 방법")[0]


def test_type_caps_limit_questions_decisions_and_changes() -> None:
    documents = (
        *(doc(f"wiki/issues/q{i}.md", title=f"Q{i}", type="issue", status="open", updated=day(i)) for i in range(12)),
        *(doc(f"wiki/decisions/d{i}.md", title=f"D{i}", type="decision", updated=day(i)) for i in range(12)),
        *(doc(f"wiki/notes/n{i}.md", title=f"N{i}", type="concept", updated=day(i)) for i in range(12)),
    )

    lines = section(run(ports(documents), max_tokens=100_000).text, "## 기억 목록")

    assert sum("] issue · " in line for line in lines) == 8
    assert sum("] decision · " in line for line in lines) == 10
    assert sum("] concept · " in line for line in lines) == 8


def test_injected_events_match_printed_items() -> None:
    usage = FakeUsage()

    bundle = run(ports(BASE_DOCS, usage=usage))

    printed = re.findall(r"\[(m:[0-9a-f]{8})\]", bundle.text)
    assert [event["item_id"] for event in usage.events] == printed
    assert all(event["event"] == "injected" for event in usage.events)
    assert {event["session_id"] for event in usage.events} == {"s-1"}
    assert {event["project"] for event in usage.events} == {"alpha"}
    assert {event["block"] for event in usage.events} == {"B"}
    assert bundle.injected_count == len(printed)


def _after_change(usage: FakeUsage) -> tuple[DocumentSnapshot, ...]:
    changed = doc(
        "wiki/decisions/use-sqlite.md",
        title="Use SQLite",
        type="decision",
        status="superseded",
        superseded_by=["decisions/use-duckdb"],
        updated=day(0),
        content_hash="h2",
    )
    replacement = doc("wiki/decisions/use-duckdb.md", title="Use DuckDB", type="decision", updated=day(0))
    return (*(item for item in BASE_DOCS if item.path != changed.path), changed, replacement)


def test_block_c_reports_an_injected_item_that_became_superseded_once() -> None:
    usage = FakeUsage()
    run(ports(BASE_DOCS, usage=usage), now=NOW - timedelta(hours=2))

    second = run(ports(_after_change(usage), usage=usage))
    third = run(ports(_after_change(usage), usage=usage), now=NOW + timedelta(hours=1))

    assert section(second.text, "## 변경 알림") == [
        f"- [{memory_item_id('main', 'wiki/decisions/use-sqlite.md')}] Use SQLite → Use DuckDB ({day(0)})"
    ]
    assert [line.startswith("## ") for line in second.text.splitlines()].count(True) == 3
    assert "## 변경 알림" not in third.text


def test_block_c_names_the_path_when_the_new_document_is_outside_the_project() -> None:
    usage = FakeUsage()
    run(ports(BASE_DOCS, usage=usage), now=NOW - timedelta(hours=2))
    documents = tuple(
        doc(item.path, title="Use DuckDB", project="beta", updated=day(0)) if "use-duckdb" in item.path else item
        for item in _after_change(usage)
    )

    lines = section(run(ports(documents, usage=usage)).text, "## 변경 알림")

    assert lines == [
        f"- [{memory_item_id('main', 'wiki/decisions/use-sqlite.md')}] Use SQLite → wiki/decisions/use-duckdb.md "
        f"({day(0)})"
    ]


def test_block_c_finds_the_new_document_by_its_supersedes_field() -> None:
    usage = FakeUsage()
    run(ports(BASE_DOCS, usage=usage), now=NOW - timedelta(hours=2))
    documents = (
        *(item for item in BASE_DOCS if "use-sqlite" not in item.path),
        doc("wiki/decisions/use-sqlite.md", title="Use SQLite", status="superseded", updated=day(0)),
        doc("wiki/decisions/new.md", title="New store", supersedes=["wiki/decisions/use-sqlite.md"], updated=day(0)),
    )

    lines = section(run(ports(documents, usage=usage)).text, "## 변경 알림")

    assert lines == [f"- [{memory_item_id('main', 'wiki/decisions/use-sqlite.md')}] Use SQLite → New store ({day(0)})"]


def test_block_c_marks_deprecated_items_as_dropped() -> None:
    usage = FakeUsage()
    run(ports(BASE_DOCS, usage=usage), now=NOW - timedelta(hours=2))
    documents = tuple(
        doc(item.path, title="Use SQLite", status="deprecated", superseded_by=["decisions/x"], updated=day(0))
        if "use-sqlite" in item.path
        else item
        for item in BASE_DOCS
    )

    lines = section(run(ports(documents, usage=usage)).text, "## 변경 알림")

    assert lines == [f"- [{memory_item_id('main', 'wiki/decisions/use-sqlite.md')}] Use SQLite → 폐기됨 ({day(0)})"]


def test_block_c_falls_back_to_the_last_14_days_without_usage() -> None:
    lines = section(run(ports(_after_change(FakeUsage()))).text, "## 변경 알림")

    assert lines == [f"- [{memory_item_id('main', 'wiki/decisions/use-sqlite.md')}] Use SQLite → Use DuckDB ({day(0)})"]


def test_unreadable_usage_falls_back_and_warns() -> None:
    bundle = run(ports(_after_change(FakeUsage()), usage=FakeUsage(fail_read=True)))

    assert "Use SQLite → Use DuckDB" in bundle.text
    assert len(bundle.warnings) == 1


def test_usage_write_failure_keeps_text_and_warns_once() -> None:
    plain = run(ports(BASE_DOCS))
    failing = run(ports(BASE_DOCS, usage=FakeUsage(fail_write=True)))

    assert failing.text == plain.text
    assert failing.exit_code == 0
    assert len(failing.warnings) == 1
    assert "\n" not in failing.warnings[0]


def many_documents(count: int, *, title_length: int = 0) -> tuple[DocumentSnapshot, ...]:
    def title(index: int) -> str:
        return ("가" * title_length) + str(index) if title_length else f"Decision number {index} with words"

    return (
        tuple(
            doc(f"wiki/decisions/d{i:02d}.md", title=title(i), type="decision", updated=day(i % 30)) for i in range(10)
        )
        + tuple(
            doc(f"wiki/issues/q{i:02d}.md", title=title(i), type="issue", status="open", updated=day(i % 30))
            for i in range(8)
        )
        + tuple(doc(f"wiki/notes/n{i:02d}.md", title=title(i), type="concept", updated=day(i % 30)) for i in range(8))
    )


def test_small_token_limit_shortens_block_b_and_counts_omitted_items() -> None:
    documents = (*many_documents(26), *_after_change(FakeUsage())[-2:])

    bundle = run(ports(documents), max_tokens=300)

    assert estimate_recall_tokens(bundle.text) <= 300
    lines = section(bundle.text, "## 기억 목록")
    match = re.fullmatch(r"- (\d+)개 생략", lines[-1])
    assert match is not None
    # 10 decisions (cap) + 8 questions + 8 changes are selected before the budget cut.
    assert len(lines) - 1 + int(match.group(1)) == 26
    assert section(bundle.text, "## 변경 알림")
    assert section(bundle.text, "## 가져오는 방법")


def test_character_limit_stops_output_even_inside_the_token_limit() -> None:
    bundle = run(ports(many_documents(26, title_length=600)), max_tokens=100_000)

    assert len(bundle.text) <= DEFAULT_RECALL_MAX_CHARS
    assert re.fullmatch(r"- \d+개 생략", section(bundle.text, "## 기억 목록")[-1])


@pytest.mark.parametrize("source", ["resume", "fork"])
def test_resume_without_changes_prints_nothing(source: str) -> None:
    usage = FakeUsage()
    run(ports(BASE_DOCS, usage=usage), now=NOW - timedelta(hours=2))
    recorded = len(usage.events)

    bundle = run(ports(BASE_DOCS, usage=usage), source=source)

    assert (bundle.exit_code, bundle.text) == (0, "")
    assert len(usage.events) == recorded


@pytest.mark.parametrize("source", ["resume", "fork"])
def test_resume_with_a_change_prints_only_block_c(source: str) -> None:
    usage = FakeUsage()
    run(ports(BASE_DOCS, usage=usage), now=NOW - timedelta(hours=2))

    bundle = run(ports(_after_change(usage), usage=usage), source=source)

    assert bundle.exit_code == 0
    assert [line for line in bundle.text.splitlines() if line.startswith("## ")] == ["## 변경 알림"]
    assert usage.events[-1]["block"] == "C"


@pytest.mark.parametrize("source", ["clear", "compact", "weird", ""])
def test_other_sources_print_the_full_bundle(source: str) -> None:
    assert "## 기억 목록" in run(ports(BASE_DOCS), source=source).text


def test_no_linked_vault_hands_off() -> None:
    bundle = run(ports(BASE_DOCS, vault_ids=(), project_id=None))

    assert (bundle.exit_code, bundle.text) == (3, "")
    assert bundle.reason


def test_unindexed_vault_hands_off_without_usage() -> None:
    usage = FakeUsage()

    bundle = run(ports(BASE_DOCS, usage=usage, indexed=set()))

    assert (bundle.exit_code, bundle.text) == (3, "")
    assert "vg index" in (bundle.reason or "")
    assert usage.events == []


def test_startup_with_nothing_to_show_hands_off() -> None:
    usage = FakeUsage()
    only_closed = tuple(item for item in BASE_DOCS if item.frontmatter.get("status") in {"stale", "deprecated"})

    bundle = run(ports(only_closed, usage=usage))

    assert (bundle.exit_code, bundle.text) == (3, "")
    assert usage.events == []


def test_item_changed_since_the_last_injection_moves_up() -> None:
    usage = FakeUsage()
    run(ports(BASE_DOCS, usage=usage), now=NOW - timedelta(hours=2))
    documents = tuple(
        doc(item.path, content_hash="new", **item.frontmatter) if "untyped" in item.path else item for item in BASE_DOCS
    )

    lines = section(run(ports(documents, usage=usage)).text, "## 기억 목록")

    assert "Untyped note" in lines[0]


def test_item_injected_ten_times_and_never_opened_moves_down_one_step() -> None:
    usage = FakeUsage()
    for hour in range(10, 0, -1):
        run(ports(BASE_DOCS, usage=usage), now=NOW - timedelta(hours=hour))
    for item_path in BASE_DOCS[1:]:
        usage.events.append(fetched_event(vault_id="main", path=item_path.path, at=NOW - timedelta(minutes=5)))

    lines = section(run(ports(BASE_DOCS, usage=usage)).text, "## 기억 목록")

    assert "Use SQLite" in lines[1]
    assert "Budget question" in lines[0]


def test_memory_item_id_is_stable_and_short() -> None:
    first = memory_item_id("main", "wiki/a.md")

    assert first == memory_item_id("main", "wiki/a.md")
    assert first != memory_item_id("other", "wiki/a.md")
    assert re.fullmatch(r"m:[0-9a-f]{8}", first)


def test_fetched_event_shape() -> None:
    event = fetched_event(vault_id="main", path="wiki/a.md", at=NOW)

    assert event == {
        "event": "fetched",
        "item_id": memory_item_id("main", "wiki/a.md"),
        "vault_id": "main",
        "path": "wiki/a.md",
        "session_id": None,
        "at": NOW.isoformat(),
    }
