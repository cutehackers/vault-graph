"""Recall budget split: A 400, L3 500, C and D 150 + 30, the rest to B (spec 2026-11-05 §4.4.6, A-26)."""

from __future__ import annotations

import re
from datetime import timedelta

from tests.test_recall_l3_section import DECISION_BODY, failing_ports
from tests.test_session_recall import NOW, FakeUsage, day, doc, ports, run
from vault_graph.context.pack.recall import (
    DEFAULT_RECALL_MAX_CHARS,
    DEFAULT_RECALL_MAX_TOKENS,
    L3_BLOCK_MAX_TOKENS,
    L3_BLOCK_TITLE,
    RecallBundle,
    estimate_recall_tokens,
)
from vault_graph.context.pack.recall_pins import PIN_BLOCK_MAX_TOKENS
from vault_graph.indexing.ingestion.document_normalizer import DocumentSnapshot

LONG = " ".join(f"word{index}" for index in range(25))


def blocks(text: str) -> dict[str, str]:
    """Each ``## `` block of the output as its own text, heading included."""
    found: dict[str, str] = {}
    title = ""
    for line in text.splitlines(keepends=True):
        if line.startswith("## "):
            title = line.strip()
        found[title] = found.get(title, "") + line
    return found


def crowded() -> tuple[tuple[DocumentSnapshot, ...], dict[str, str]]:
    """Every block has more than its budget: many pins, list pages with claims, notices and long titles."""
    pins = tuple(
        doc(f"wiki/rules/pin{i:02d}.md", title=f"Pin {i}", type="rule", pin=True, summary=LONG, updated=day(i))
        for i in range(20)
    )
    decisions = tuple(
        doc(f"wiki/decisions/d{i:02d}.md", title=f"Decision {i} {LONG}", type="decision", updated=day(i))
        for i in range(12)
    )
    issues = tuple(
        doc(f"wiki/issues/q{i:02d}.md", title=f"Question {i} {LONG}", type="issue", status="open", updated=day(i))
        for i in range(12)
    )
    rules = tuple(
        doc(f"wiki/notes/r{i:02d}.md", title=f"Rule {i} {LONG}", tags=["rule"], updated=day(i)) for i in range(12)
    )
    retired = tuple(
        doc(
            f"wiki/notes/old{i:02d}.md",
            title=f"Old {i} {LONG}",
            type="concept",
            status="retired",
            retired_reason="replaced",
            retired_at=day(0),
            updated=day(0),
        )
        for i in range(12)
    )
    documents = (*pins, *decisions, *issues, *rules, *retired)
    return documents, {document.document_id: DECISION_BODY for document in decisions}


def check_limits(bundle: RecallBundle) -> dict[str, str]:
    found = blocks(bundle.text)
    assert estimate_recall_tokens(bundle.text) <= DEFAULT_RECALL_MAX_TOKENS
    assert len(bundle.text) <= DEFAULT_RECALL_MAX_CHARS
    assert estimate_recall_tokens(found.get("## 고정 기억", "")) <= PIN_BLOCK_MAX_TOKENS
    assert estimate_recall_tokens(found.get(L3_BLOCK_TITLE, "")) <= L3_BLOCK_MAX_TOKENS
    c_and_d = found.get("## 변경 알림", "") + found.get("## 가져오는 방법", "")
    assert estimate_recall_tokens(c_and_d) <= 180
    return found


def test_every_block_stays_inside_its_budget_when_all_are_crowded() -> None:
    documents, bodies = crowded()

    found = check_limits(run(ports(documents, bodies=bodies, proposals={"main": 3})))

    assert set(found) == {"## 고정 기억", L3_BLOCK_TITLE, "## 기억 목록", "## 변경 알림", "## 가져오는 방법"}
    assert re.fullmatch(r"- \d+개 생략", found[L3_BLOCK_TITLE].strip().splitlines()[-1])


def test_without_block_l3_block_b_takes_its_room_and_the_other_blocks_stay() -> None:
    documents, _ = crowded()
    decision_ids = {document.document_id for document in documents if document.path.startswith("wiki/decisions/")}

    with_l3 = run(ports(documents))
    without_l3 = run(failing_ports(documents, failing=decision_ids))

    shown, missing = blocks(with_l3.text), blocks(without_l3.text)
    check_limits(without_l3)
    assert L3_BLOCK_TITLE in shown
    assert L3_BLOCK_TITLE not in missing
    for title in ("## 고정 기억", "## 변경 알림", "## 가져오는 방법"):
        assert missing[title] == shown[title]
    b_with, b_without = (
        [line for line in found["## 기억 목록"].splitlines() if line and not line.endswith("개 생략")]
        for found in (shown, missing)
    )
    assert len(b_without) > len(b_with)
    assert b_without[: len(b_with)] == b_with


def test_usage_history_does_not_change_blocks_a_l3_and_b() -> None:
    documents, bodies = crowded()
    usage = FakeUsage()
    run(ports(documents, bodies=bodies, usage=usage), now=NOW - timedelta(days=1))

    fresh = blocks(run(ports(documents, bodies=bodies)).text)
    with_history = blocks(run(ports(documents, bodies=bodies, usage=usage)).text)

    for title in ("## 고정 기억", L3_BLOCK_TITLE, "## 기억 목록"):
        assert with_history[title] == fresh[title]
