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
    vault_names: Mapping[str, str] | None = None,
) -> RecallPorts:
    by_vault: dict[str, tuple[DocumentSnapshot, ...]] = {}
    for item in documents:
        by_vault[item.vault_id] = (*by_vault.get(item.vault_id, ()), item)
    return RecallPorts(
        scope=FakeScope(
            RecallScope(project_id=project_id, vault_ids=vault_ids)
            if vault_names is None
            else RecallScope(project_id=project_id, vault_ids=vault_ids, vault_names=vault_names)
        ),
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


def _block_b(bundle: RecallBundle) -> list[str]:
    return section(bundle.text, "## 기억 목록")


def test_usage_history_never_changes_block_b() -> None:
    """A-9: no log, 10 injections with no fetch, changed content hash and unreadable log give the same block B."""
    baseline = _block_b(run(ports(BASE_DOCS)))

    ignored = FakeUsage()
    for hour in range(10, 0, -1):
        run(ports(BASE_DOCS, usage=ignored), now=NOW - timedelta(hours=hour))
    for item in BASE_DOCS[1:]:
        ignored.events.append(fetched_event(vault_id="main", path=item.path, at=NOW - timedelta(minutes=5)))

    changed = FakeUsage()
    run(ports(BASE_DOCS, usage=changed), now=NOW - timedelta(hours=2))
    rehashed = tuple(
        doc(item.path, content_hash="new", **item.frontmatter) if "untyped" in item.path else item for item in BASE_DOCS
    )

    assert _block_b(run(ports(BASE_DOCS, usage=ignored))) == baseline
    assert _block_b(run(ports(rehashed, usage=changed))) == baseline
    assert _block_b(run(ports(BASE_DOCS, usage=FakeUsage(fail_read=True)))) == baseline


def test_block_b_breaks_date_ties_by_vault_then_path_across_vaults() -> None:
    documents = (
        doc("wiki/notes/b.md", vault_id="zeta", title="Zeta B", updated=day(1)),
        doc("wiki/notes/a.md", vault_id="zeta", title="Zeta A", updated=day(1)),
        doc("wiki/notes/z.md", vault_id="alpha", title="Alpha Z", updated=day(1)),
        doc("wiki/notes/new.md", vault_id="zeta", title="Newest", updated=day(0)),
    )

    lines = _block_b(run(ports(documents, vault_ids=("zeta", "alpha"))))

    titles = [line.split(" · ")[3].split(" (")[0] for line in lines]
    assert titles == ["Newest", "Alpha Z", "Zeta A", "Zeta B"]


def test_recall_code_has_no_usage_demotion() -> None:
    import vault_graph.context.pack.recall as recall_module

    assert not hasattr(recall_module, "DEMOTE_AFTER_INJECTIONS")
    assert "DEMOTE_AFTER_INJECTIONS" not in Path(recall_module.__file__).read_text(encoding="utf-8")


def test_retired_status_counts_as_stale_for_project_memory() -> None:
    from vault_graph.context.memory.project_memory import STALE_STATUSES

    assert "retired" in STALE_STATUSES


def _retired() -> DocumentSnapshot:
    return doc(
        "wiki/decisions/use-sqlite.md",
        title="Use SQLite",
        type="decision",
        status="retired",
        retired_reason="no longer stored locally",
        retired_at=day(0),
        updated=day(1),
        content_hash="h2",
    )


def _with_retired() -> tuple[DocumentSnapshot, ...]:
    return (*(item for item in BASE_DOCS if "use-sqlite" not in item.path), _retired())


def test_retired_page_leaves_block_b_and_is_noticed_once_with_its_reason() -> None:
    usage = FakeUsage()
    run(ports(BASE_DOCS, usage=usage), now=NOW - timedelta(hours=2))

    second = run(ports(_with_retired(), usage=usage))
    third = run(ports(_with_retired(), usage=usage), now=NOW + timedelta(hours=1))

    assert "Use SQLite" not in "\n".join(_block_b(second))
    assert section(second.text, "## 변경 알림") == [
        f"- [{memory_item_id('main', 'wiki/decisions/use-sqlite.md')}] Use SQLite → 폐기됨: no longer stored locally "
        f"({day(0)})"
    ]
    assert "## 변경 알림" not in third.text
    assert "Use SQLite" not in third.text


def test_retired_page_is_noticed_by_its_retired_date_without_usage() -> None:
    documents = (
        *(item for item in BASE_DOCS if "use-sqlite" not in item.path),
        doc(
            "wiki/decisions/use-sqlite.md",
            title="Use SQLite",
            status="retired",
            retired_reason="moved",
            retired_at=day(2),
            updated=day(60),
        ),
    )

    lines = section(run(ports(documents)).text, "## 변경 알림")

    assert lines == [
        f"- [{memory_item_id('main', 'wiki/decisions/use-sqlite.md')}] Use SQLite → 폐기됨: moved ({day(2)})"
    ]


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


# Block A: pinned memory (spec 2026-11-02 V4, 결정14, 결정S11) ---------------------------------


def pinned(
    path: str,
    *,
    vault_id: str = "main",
    title: str = "Pinned rule",
    updated: str | None = None,
    **frontmatter: Any,
) -> DocumentSnapshot:
    fields: dict[str, Any] = {
        "title": title,
        "type": "concept",
        "pin": True,
        "memory_schema": "vault-memory/v1",
        "memory_kind": "rule",
        "summary": f"Summary of {title}",
        "updated": updated or day(30),
    }
    fields.update(frontmatter)
    return doc(path, vault_id=vault_id, **fields)


def headings(text: str) -> list[str]:
    return [line for line in text.splitlines() if line.startswith("## ")]


def test_pinned_page_comes_first_as_two_lines_and_leaves_block_b() -> None:
    page = pinned("wiki/rules/use-uv.md", title="Use uv run")

    bundle = run(ports((*BASE_DOCS, page)))

    assert headings(bundle.text) == ["## 고정 기억", "## 기억 목록", "## 가져오는 방법"]
    assert section(bundle.text, "## 고정 기억") == [
        f"- [{memory_item_id('main', 'wiki/rules/use-uv.md')}] rule · Use uv run (wiki/rules/use-uv.md)",
        "  Summary of Use uv run",
    ]
    assert "Use uv run" not in "\n".join(_block_b(bundle))


def test_pinned_page_of_any_linked_vault_comes_before_newer_pages() -> None:
    team = pinned("wiki/rules/team-rule.md", vault_id="team", title="Team rule", updated=day(90))

    bundle = run(ports((*BASE_DOCS, team), vault_ids=("main", "team")))

    assert headings(bundle.text)[0] == "## 고정 기억"
    assert "(team:wiki/rules/team-rule.md)" in section(bundle.text, "## 고정 기억")[0]


def test_kind_falls_back_to_type_without_memory_kind() -> None:
    page = pinned("wiki/rules/plain.md", title="Plain pin", memory_kind=None)

    first = section(run(ports((*BASE_DOCS, page))).text, "## 고정 기억")[0]

    assert "] concept · Plain pin (" in first


def test_quoted_true_is_not_a_pin_and_stays_in_block_b() -> None:
    page = pinned("wiki/rules/quoted.md", title="Quoted pin", pin="true")

    bundle = run(ports((*BASE_DOCS, page)))

    assert "## 고정 기억" not in bundle.text
    assert any("Quoted pin" in line for line in _block_b(bundle))


@pytest.mark.parametrize("status", ["retired", "superseded", "deprecated", "stale"])
def test_closed_pinned_pages_are_not_in_block_a(status: str) -> None:
    page = pinned("wiki/rules/closed.md", title="Closed pin", status=status, retired_reason="gone")

    bundle = run(ports((*BASE_DOCS, page)))

    assert "## 고정 기억" not in bundle.text
    assert "Closed pin" not in "\n".join(_block_b(bundle))


def test_pinned_page_of_another_project_is_not_shown() -> None:
    page = pinned("wiki/rules/beta.md", title="Beta pin", project="beta")

    assert "Beta pin" not in run(ports((*BASE_DOCS, page))).text


def test_pins_are_ordered_newest_first_then_by_path() -> None:
    documents = (
        *BASE_DOCS,
        pinned("wiki/rules/b.md", title="B pin", updated=day(5)),
        pinned("wiki/rules/a.md", title="A pin", updated=day(5)),
        pinned("wiki/rules/new.md", title="New pin", updated=day(1)),
    )

    lines = section(run(ports(documents)).text, "## 고정 기억")

    assert [line.split(" · ")[1].split(" (")[0] for line in lines[::2]] == ["New pin", "A pin", "B pin"]


def test_block_a_over_400_tokens_is_cut_from_the_end_and_block_b_keeps_its_room() -> None:
    long_summary = " ".join(["word"] * 40)
    pins = tuple(
        pinned(f"wiki/rules/r{index:02d}.md", title=f"Rule {index}", summary=long_summary, updated=day(index))
        for index in range(30)
    )
    without_pins = run(ports(BASE_DOCS))

    bundle = run(ports((*BASE_DOCS, *pins)))

    block_a = "## 고정 기억\n" + "".join(line + "\n" for line in section(bundle.text, "## 고정 기억"))
    assert estimate_recall_tokens(block_a) <= 400
    assert re.fullmatch(r"- \d+개 생략", section(bundle.text, "## 고정 기억")[-1])
    assert _block_b(bundle) == _block_b(without_pins)
    assert estimate_recall_tokens(bundle.text) <= DEFAULT_RECALL_MAX_TOKENS
    assert len(bundle.text) <= DEFAULT_RECALL_MAX_CHARS


def test_unknown_memory_schema_is_a_regular_page_with_one_warning() -> None:
    page = pinned("wiki/rules/future.md", title="Future pin", memory_schema="vault-memory/v9")

    bundle = run(ports((*BASE_DOCS, page)))

    assert "## 고정 기억" not in bundle.text
    assert any("Future pin" in line for line in _block_b(bundle))
    assert len(bundle.warnings) == 1
    assert "vault-memory/v9" in bundle.warnings[0]
    assert "\n" not in bundle.warnings[0]


def test_pinned_items_are_logged_as_block_a() -> None:
    usage = FakeUsage()

    run(ports((*BASE_DOCS, pinned("wiki/rules/use-uv.md")), usage=usage))

    assert usage.events[0]["block"] == "A"
    assert usage.events[0]["item_id"] == memory_item_id("main", "wiki/rules/use-uv.md")


def test_only_pinned_pages_still_print_block_a() -> None:
    bundle = run(ports((pinned("wiki/rules/only.md", title="Only pin"),)))

    assert bundle.exit_code == 0
    assert headings(bundle.text) == ["## 고정 기억", "## 가져오는 방법"]


def test_retiring_a_pinned_page_is_noticed_after_it_was_shown() -> None:
    usage = FakeUsage()
    page = pinned("wiki/rules/use-uv.md", title="Use uv run", updated=day(60))
    run(ports((*BASE_DOCS, page), usage=usage), now=NOW - timedelta(hours=2))
    retired = pinned(
        "wiki/rules/use-uv.md", title="Use uv run", updated=day(60), status="retired", retired_reason="moved"
    )

    bundle = run(ports((*BASE_DOCS, retired), usage=usage))

    assert section(bundle.text, "## 변경 알림") == [
        f"- [{memory_item_id('main', 'wiki/rules/use-uv.md')}] Use uv run → 폐기됨: moved ({day(60)})"
    ]


def test_usage_history_never_changes_block_a() -> None:
    """A-9: no log, 10 injections with no fetch, changed content hash and unreadable log give the same block A."""
    documents = (*BASE_DOCS, pinned("wiki/rules/one.md", title="One"), pinned("wiki/rules/two.md", title="Two"))
    baseline = section(run(ports(documents)).text, "## 고정 기억")

    ignored = FakeUsage()
    for hour in range(10, 0, -1):
        run(ports(documents, usage=ignored), now=NOW - timedelta(hours=hour))
    changed = FakeUsage()
    run(ports(documents, usage=changed), now=NOW - timedelta(hours=2))
    rehashed = tuple(
        doc(item.path, content_hash="new", **item.frontmatter) if item.path == "wiki/rules/one.md" else item
        for item in documents
    )

    assert baseline
    assert section(run(ports(documents, usage=ignored)).text, "## 고정 기억") == baseline
    assert section(run(ports(rehashed, usage=changed)).text, "## 고정 기억") == baseline
    assert section(run(ports(documents, usage=FakeUsage(fail_read=True))).text, "## 고정 기억") == baseline


def test_several_vaults_use_the_vault_name_in_every_location() -> None:
    other = doc("wiki/decisions/other.md", vault_id="other", title="Other vault decision", updated=day(0))
    team = pinned("wiki/rules/team-rule.md", vault_id="other", title="Team rule")

    bundle = run(ports((*BASE_DOCS, other, team), vault_ids=("main", "other"), vault_names={"other": "team-wiki"}))

    assert "(team-wiki:wiki/rules/team-rule.md)" in section(bundle.text, "## 고정 기억")[0]
    assert "(team-wiki:wiki/decisions/other.md, ~42t)" in bundle.text
    assert "(main:wiki/decisions/use-sqlite.md, ~42t)" in bundle.text
    assert section(bundle.text, "## 가져오는 방법")[0].endswith(
        "경로 앞은 Vault 이름이다. 이름=vault_id: main, team-wiki=other"
    )


def test_one_vault_shows_the_bare_path_even_with_a_name() -> None:
    page = pinned("wiki/rules/use-uv.md", title="Use uv run")

    bundle = run(ports((*BASE_DOCS, page), vault_names={"main": "personal-notes"}))

    assert "personal-notes" not in bundle.text
    assert "(wiki/rules/use-uv.md)" in section(bundle.text, "## 고정 기억")[0]


def test_block_b_breaks_date_ties_by_vault_name_when_names_differ_from_ids() -> None:
    documents = (
        doc("wiki/notes/a.md", vault_id="alpha", title="Alpha A", updated=day(1)),
        doc("wiki/notes/a.md", vault_id="zeta", title="Zeta A", updated=day(1)),
        doc("wiki/notes/b.md", vault_id="alpha", title="Alpha B", updated=day(1)),
    )

    lines = _block_b(
        run(ports(documents, vault_ids=("alpha", "zeta"), vault_names={"alpha": "zz-later", "zeta": "aa-first"}))
    )

    titles = [line.split(" · ")[3].split(" (")[0] for line in lines]
    assert titles == ["Zeta A", "Alpha A", "Alpha B"]


STRUCTURAL_DOCS = (
    doc("wiki/index.md", title="Wiki Index", type="index", updated=day(0)),
    doc("wiki/log.md", title="Wiki Log", type="log", updated=day(0)),
    doc("wiki/maps/decision-map.md", title="Decision Map", type="map", updated=day(0)),
    doc("wiki/overview.md", title="Overview", type="Overview", updated=day(0)),
)


def test_block_b_leaves_out_navigation_pages_by_type() -> None:
    """F3: every publish rewrites the index, log, maps and overview, so they would fill the list."""
    bundle = run(ports((*BASE_DOCS, *STRUCTURAL_DOCS)))

    joined = "\n".join(_block_b(bundle))
    for title in ("Wiki Index", "Wiki Log", "Decision Map", "Overview"):
        assert title not in joined
    assert _block_b(bundle) == _block_b(run(ports(BASE_DOCS)))


def test_navigation_page_types_are_left_out_in_every_vault_role() -> None:
    """결정15: the filter reads the page type only, never the Vault it came from."""
    team_index = doc("wiki/index.md", vault_id="team", title="Team Index", type="index", updated=day(0))
    team_note = doc("wiki/notes/index-like.md", vault_id="team", title="Team note", type="note", updated=day(0))

    lines = _block_b(run(ports((*BASE_DOCS, team_index, team_note), vault_ids=("main", "team"))))

    assert not any("Team Index" in line for line in lines)
    assert any("Team note" in line for line in lines)


def test_only_navigation_pages_hand_off_and_a_pinned_navigation_page_stays_in_block_a() -> None:
    assert run(ports(STRUCTURAL_DOCS)).handoff

    page = pinned("wiki/index.md", title="Pinned index", type="index")
    bundle = run(ports((*BASE_DOCS, page)))

    assert "Pinned index" in "\n".join(section(bundle.text, "## 고정 기억"))
