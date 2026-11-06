"""The L3 list: open work, current decisions, corrections and rules (spec 2026-11-05 §4.4.7, A-25, A-27 S9).

The list is computed from the index when asked and is never stored. Recall and the project memory
service build it with the same function, ``project_l3_list``.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from tests.test_project_memory_service import make_service
from tests.test_sqlite_metadata_store import make_document
from vault_graph.context.memory.project_memory import ProjectL3List, project_l3_list
from vault_graph.context.memory.project_scope import FixedVaultProjectScope
from vault_graph.indexing.ingestion.document_normalizer import DocumentSnapshot
from vault_graph.operation.scope.vault_catalog import QueryScope

DECISION_BODY = """## Claim Evidence

| Claim | Status | Evidence |
|---|---|---|
| Releases ship every Friday. | superseded | [[sources/a]] Superseded by: Releases ship every Tuesday. |
| Releases ship every Tuesday. | stated | [[sources/b]] |
"""


def page(path: str, *, vault_id: str = "main", **frontmatter: object) -> DocumentSnapshot:
    return replace(make_document(vault_id, path, f"hash:{path}"), frontmatter=dict(frontmatter))


def bodies(texts: dict[str, str]):  # type: ignore[no-untyped-def]
    return lambda vault_id, document_id: texts.get(document_id, "")


def build(
    documents: list[DocumentSnapshot],
    texts: dict[str, str] | None = None,
    *,
    project_id: str | None = "alpha",
    scopes: dict[str, FixedVaultProjectScope] | None = None,
    limit: int = 10,
) -> ProjectL3List:
    by_vault: dict[str, list[DocumentSnapshot]] = {}
    for document in documents:
        by_vault.setdefault(document.vault_id, []).append(document)
    return project_l3_list(
        by_vault,
        project_id=project_id,
        vault_scopes=scopes or {},
        body_reader=bodies(texts or {}),
        limit=limit,
    )


def test_superseded_claim_row_is_left_out_and_the_current_row_stays() -> None:
    decision = page("wiki/decisions/release.md", type="decision", title="Release cadence", project="alpha")

    result = build([decision], {decision.document_id: DECISION_BODY})

    assert [entry.title for entry in result.decisions] == ["Release cadence"]
    claims = [row.claim for row in result.decisions[0].claims]
    assert claims == ["Releases ship every Tuesday."]
    assert result.warnings == ()


def test_lists_open_work_current_decisions_and_corrections_and_rules() -> None:
    documents = [
        page("wiki/issues/flaky-test.md", type="issue", status="open", title="Flaky test"),
        page("wiki/issues/old.md", type="issue", status="resolved", title="Old issue"),
        page("wiki/decisions/use-sqlite.md", type="decision", status="active", title="Use SQLite"),
        page("wiki/notes/no-mocks.md", type="note", tags=["correction"], title="No mocks"),
        page("wiki/memory/run-ruff.md", type="note", memory_kind="rule", title="Run ruff"),
        page("wiki/notes/plain.md", type="note", title="Plain note"),
    ]

    result = build(documents)

    assert [entry.title for entry in result.open_work] == ["Flaky test"]
    assert [entry.title for entry in result.decisions] == ["Use SQLite"]
    assert sorted(entry.title for entry in result.corrections_and_rules) == ["No mocks", "Run ruff"]


def test_replaced_and_retired_pages_are_left_out() -> None:
    documents = [
        page("wiki/decisions/a.md", type="decision", status="superseded", title="A"),
        page("wiki/decisions/b.md", type="decision", status="deprecated", title="B"),
        page("wiki/notes/c.md", tags=["rule"], status="retired", title="C"),
        page("wiki/decisions/d.md", type="decision", title="D"),
    ]

    result = build(documents)

    assert [entry.title for entry in result.decisions] == ["D"]
    assert result.corrections_and_rules == ()


def test_project_scope_rule_picks_the_pages() -> None:
    shared = FixedVaultProjectScope(linked_projects=frozenset({"alpha", "beta"}), sharable=False)
    documents = [
        page("wiki/decisions/mine.md", type="decision", project="alpha", title="Mine"),
        page("wiki/decisions/theirs.md", type="decision", project="beta", title="Theirs"),
        page("wiki/decisions/unowned.md", type="decision", title="Unowned"),
    ]

    not_shared = build(documents, scopes={"main": shared})
    shared_result = build(documents, scopes={"main": replace(shared, sharable=True)})

    assert [entry.title for entry in not_shared.decisions] == ["Mine"]
    assert sorted(entry.title for entry in shared_result.decisions) == ["Mine", "Unowned"]


def test_pages_outside_wiki_are_not_listed() -> None:
    result = build([page("raw/sources/decision.md", type="decision", title="Raw")])

    assert result.decisions == ()


def test_newest_first_and_limit_per_list() -> None:
    documents = [
        page(f"wiki/decisions/d{index}.md", type="decision", title=f"D{index}", updated=f"2026-10-0{index}")
        for index in range(1, 6)
    ]

    result = build(documents, limit=2)

    assert [entry.title for entry in result.decisions] == ["D5", "D4"]
    assert [entry.day for entry in result.decisions] == ["2026-10-05", "2026-10-04"]


def test_unreadable_claim_table_keeps_the_page_and_gives_one_warning_line() -> None:
    decision = page("wiki/decisions/odd.md", type="decision", title="Odd")
    body = "| Claim | Status | Evidence |\n|---|---|---|\n| Old. | superseded | a |\n| New. | maybe | b |\n"

    result = build([decision], {decision.document_id: body})

    assert [entry.title for entry in result.decisions] == ["Odd"]
    assert result.decisions[0].claims == ()
    assert len(result.warnings) == 1
    assert "wiki/decisions/odd.md" in result.warnings[0]
    assert "\n" not in result.warnings[0]


def test_service_and_recall_get_the_same_list_and_nothing_is_written(tmp_path: Path) -> None:
    """A-27 S9: the service builds the list with ``project_l3_list``, and no file appears anywhere."""
    decision = page("wiki/decisions/release.md", type="decision", title="Release cadence", project="alpha")
    rule = page("wiki/notes/run-ruff.md", tags=["rule"], title="Run ruff", project="alpha")
    other = page("wiki/decisions/beta.md", type="decision", title="Beta only", project="beta")
    service = make_service(tmp_path, documents=(decision, rule, other))
    graph_home = tmp_path / "graph-home"
    graph_home.mkdir()
    before = sorted(path.relative_to(tmp_path) for path in tmp_path.rglob("*"))

    from_service = service.l3_list(
        requested_scope=QueryScope(vault_ids=("main",), content_scopes=("wiki",)),
        project_id="alpha",
        vault_scopes={},
        body_reader=lambda vault_id, document_id: DECISION_BODY if document_id == decision.document_id else "",
    )
    direct = build(
        [decision, rule, other],
        {decision.document_id: DECISION_BODY},
    )

    assert from_service == direct
    assert [row.claim for row in from_service.decisions[0].claims] == ["Releases ship every Tuesday."]
    assert sorted(path.relative_to(tmp_path) for path in tmp_path.rglob("*")) == before
