"""Recall block L3: the brief start and the L3 list (spec 2026-11-05 §4.4.6, §4.4.7, A-25, A-27 S9)."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, cast

import pytest

from tests.test_session_recall import CWD, NOW, FakeDocuments, FakeProposals, FakeScope, FakeUsage, day, doc, ports, run
from tests.test_session_recall import section as block_lines
from vault_graph.context.memory.project_memory import project_l3_list
from vault_graph.context.pack.recall import (
    DEFAULT_RECALL_MAX_CHARS,
    L3_BLOCK_TITLE,
    L3_LIST_TITLES,
    RecallPorts,
    RecallScope,
    recall,
)
from vault_graph.indexing.ingestion.document_normalizer import DocumentSnapshot

DECISION_BODY = """## Claim Evidence

| Claim | Status | Evidence |
|---|---|---|
| Releases ship every Friday. | superseded | [[sources/a]] Superseded by: Releases ship every Tuesday. |
| Releases ship every Tuesday. | stated | [[sources/b]] |
"""

RELEASE = doc("wiki/decisions/release.md", title="Release cadence", type="decision", updated=day(1))
BUDGET = doc("wiki/issues/budget.md", title="Budget question", type="issue", status="open", updated=day(2))
RUFF = doc("wiki/notes/run-ruff.md", title="Run ruff", tags=["rule"], updated=day(3))
NOTE = doc("wiki/notes/plain.md", title="Plain note", type="concept", updated=day(4))
DOCS = (RELEASE, BUDGET, RUFF, NOTE)
BODIES = {RELEASE.document_id: DECISION_BODY}


def headings(text: str) -> list[str]:
    return [line for line in text.splitlines() if line.startswith("## ")]


def test_pinned_page_is_shown_in_block_a_and_not_repeated_in_block_l3() -> None:
    pinned_rule = doc("wiki/notes/run-ruff.md", title="Run ruff", tags=["rule"], pin=True, updated=day(3))

    bundle = run(ports((RELEASE, pinned_rule), bodies=BODIES))

    assert "Run ruff" in "\n".join(block_lines(bundle.text, "## 고정 기억"))
    assert block_lines(bundle.text, L3_BLOCK_TITLE) == [
        "### 현재 결정",
        f"- Release cadence (wiki/decisions/release.md, {day(1)})",
        "  - Releases ship every Tuesday.",
    ]


def test_block_l3_comes_after_block_a_and_before_block_b_with_its_three_lists() -> None:
    pin = doc("wiki/rules/use-uv.md", title="Use uv", type="rule", pin=True, summary="Run uv", updated=day(0))

    bundle = run(ports((*DOCS, pin), bodies=BODIES))

    assert headings(bundle.text) == ["## 고정 기억", L3_BLOCK_TITLE, "## 기억 목록", "## 가져오는 방법"]
    assert block_lines(bundle.text, L3_BLOCK_TITLE) == [
        "### 열린 일",
        f"- Budget question (wiki/issues/budget.md, {day(2)})",
        "### 현재 결정",
        f"- Release cadence (wiki/decisions/release.md, {day(1)})",
        "  - Releases ship every Tuesday.",
        "### 교정·규칙",
        f"- Run ruff (wiki/notes/run-ruff.md, {day(3)})",
    ]


def test_superseded_claim_row_is_left_out_of_block_l3_and_of_the_pinned_excerpt() -> None:
    """A-25: the superseded row's sentence is nowhere in the recall output, the current row is."""
    pinned_rule = doc("wiki/rules/release.md", title="Release rule", type="rule", pin=True, updated=day(1))

    bundle = run(ports((pinned_rule, RELEASE), bodies={**BODIES, pinned_rule.document_id: DECISION_BODY}))

    assert "Releases ship every Friday." not in bundle.text
    assert "Releases ship every Tuesday." in "\n".join(block_lines(bundle.text, "## 고정 기억"))
    assert "Releases ship every Tuesday." in "\n".join(block_lines(bundle.text, L3_BLOCK_TITLE))


def test_block_l3_shows_the_same_list_as_project_l3_list() -> None:
    """A-27 S9: recall and ``summarize_project_memory`` build the list with the same function."""
    other = doc("wiki/decisions/beta.md", title="Beta only", type="decision", project="beta", updated=day(0))
    documents = (*DOCS, other)

    lines = block_lines(run(ports(documents, bodies=BODIES)).text, L3_BLOCK_TITLE)
    expected = project_l3_list(
        {"main": documents},
        project_id="alpha",
        vault_scopes={},
        body_reader=lambda vault_id, document_id: BODIES.get(document_id, ""),
    )

    listed = [line.removeprefix("- ").split(" (")[0] for line in lines if line.startswith("- ")]
    assert listed == [
        entry.title
        for entries in (expected.open_work, expected.decisions, expected.corrections_and_rules)
        for entry in entries
    ]
    assert "Beta only" not in listed


def test_brief_start_comes_first_in_block_l3() -> None:
    brief = doc("wiki/projects/alpha.md", title="Alpha", type="project", project="alpha", updated=day(5))
    body = "# Alpha\n\nAlpha indexes Vault pages for recall.\n\n## Evidence\n\n- [[sources/x]]\n"

    lines = block_lines(run(ports((*DOCS, brief), bodies={**BODIES, brief.document_id: body})).text, L3_BLOCK_TITLE)

    assert lines[0] == "Alpha indexes Vault pages for recall. (wiki/projects/alpha.md)"
    assert lines[1] == "### 열린 일"


def test_brief_of_another_project_is_not_shown() -> None:
    brief = doc("wiki/projects/beta.md", title="Beta", type="project", project="beta", updated=day(5))

    lines = block_lines(
        run(ports((*DOCS, brief), bodies={**BODIES, brief.document_id: "Beta brief."})).text, L3_BLOCK_TITLE
    )

    assert "Beta brief." not in "\n".join(lines)


def test_brief_alone_still_makes_block_l3() -> None:
    brief = doc("wiki/projects/alpha.md", title="Alpha", type="project", project="alpha", updated=day(5))

    bundle = run(ports((brief, NOTE), bodies={brief.document_id: "Alpha in one line."}))

    assert block_lines(bundle.text, L3_BLOCK_TITLE) == ["Alpha in one line. (wiki/projects/alpha.md)"]


def test_no_brief_and_no_list_leaves_block_l3_out() -> None:
    bundle = run(ports((NOTE,)))

    assert L3_BLOCK_TITLE not in bundle.text
    assert bundle.warnings == ()


@dataclass
class FailingL3Documents(FakeDocuments):
    """Reading the body of a listed page fails, so block L3 cannot be built."""

    failing: set[str] = field(default_factory=set)

    def body_text(self, vault_id: str, document_id: str) -> str:
        if document_id in self.failing:
            raise OSError("chunk table locked")
        return super().body_text(vault_id, document_id)


def failing_ports(documents: tuple[DocumentSnapshot, ...], failing: set[str] | None = None) -> RecallPorts:
    return RecallPorts(
        scope=FakeScope(RecallScope(project_id="alpha", vault_ids=("main",))),
        documents=FailingL3Documents({"main": documents}, failing=failing or {RELEASE.document_id}),
        usage=FakeUsage(),
        proposals=FakeProposals({}),
    )


def test_block_l3_error_leaves_only_block_l3_out_with_one_warning() -> None:
    bundle = recall(
        CWD, source="startup", session_id="s-1", ports=failing_ports(DOCS), now=NOW, max_chars=DEFAULT_RECALL_MAX_CHARS
    )

    assert bundle.exit_code == 0
    assert headings(bundle.text) == ["## 기억 목록", "## 가져오는 방법"]
    assert len(bundle.warnings) == 1
    assert "chunk table locked" in bundle.warnings[0]
    assert "\n" not in bundle.warnings[0]


def test_resume_prints_no_block_l3() -> None:
    assert run(ports(DOCS, bodies=BODIES), source="resume").text == ""


def test_block_l3_is_not_logged_as_injected_items() -> None:
    usage = FakeUsage()

    run(ports(DOCS, usage=usage, bodies=BODIES))

    assert {event["block"] for event in usage.events} == {"B"}


def test_recall_block_l3_and_mcp_summary_give_the_same_l3_list(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A-27 S9: block L3 and ``summarize_project_memory`` show the same ``project_l3_list`` result."""
    from tests.test_decision_memory_service import FakeMetadataStore
    from tests.test_mcp_tools import _registry, fake_factory, fake_services
    from tests.test_project_memory_service import make_service
    from tests.test_sqlite_metadata_store import make_chunk
    from vault_graph.interface.composition.read_only_service_factory import metadata_body_reader
    from vault_graph.interface.mcp.mcp_tools import SummarizeProjectMemoryInput
    from vault_graph.operation.integration.vault_map import VAULT_MAP_ENV

    monkeypatch.setenv(VAULT_MAP_ENV, str(tmp_path / "no-map.json"))
    chunks = tuple(
        make_chunk("main", item.document_id, item.path, text=BODIES.get(item.document_id, "Body")) for item in DOCS
    )
    store = FakeMetadataStore(DOCS, chunks)
    factory = fake_factory()
    factory.project_memory_service = make_service(tmp_path, documents=DOCS, metadata_store=store)  # type: ignore[assignment]
    services = replace(fake_services(tmp_path), metadata_store=cast(Any, store))
    outside = tmp_path / "outside"
    outside.mkdir()

    payload = (
        _registry(services, factory).summarize_project_memory(SummarizeProjectMemoryInput(cwd=str(outside))).payload
    )
    body_text = metadata_body_reader(store)  # type: ignore[arg-type]
    bundle = recall(
        CWD,
        source="startup",
        session_id="s-1",
        now=NOW,
        ports=RecallPorts(
            scope=FakeScope(RecallScope(project_id=None, vault_ids=("main",))),
            documents=FakeDocuments(
                {"main": DOCS}, bodies={item.document_id: body_text("main", item.document_id) for item in DOCS}
            ),
            usage=FakeUsage(),
        ),
    )

    l3_list = payload["l3_list"]
    assert isinstance(l3_list, dict)
    from_mcp: list[str] = []
    for key, title in zip(("open_work", "decisions", "corrections_and_rules"), L3_LIST_TITLES, strict=True):
        from_mcp.append(title)
        for entry in l3_list[key]:
            from_mcp.append(f"- {entry['title']} ({entry['path']}, {entry['day']})")
            from_mcp.extend(f"  - {row['claim']}" for row in entry["claims"])
    assert block_lines(bundle.text, L3_BLOCK_TITLE) == from_mcp
    assert [row["claim"] for row in l3_list["decisions"][0]["claims"]] == ["Releases ship every Tuesday."]
