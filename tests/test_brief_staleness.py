"""Brief update rule ``brief_staleness`` (spec 2026-11-05 §4.4.7, §4.4.4 rule 4, A-35)."""

from __future__ import annotations

import ast
from datetime import date, datetime
from pathlib import Path
from typing import Any

import pytest

import vault_graph.context.memory.brief as brief_module
from tests.test_session_recall import doc
from vault_graph.context.memory.brief import (
    BRIEF_STALE_THRESHOLD,
    brief_staleness,
    project_brief_staleness,
)
from vault_graph.context.memory.project_scope import FixedVaultProjectScope
from vault_graph.indexing.ingestion.document_normalizer import DocumentSnapshot

BRIEF_PATH = "wiki/projects/alpha.md"
ALPHA = FixedVaultProjectScope(linked_projects=frozenset({"alpha"}))
SHARED = FixedVaultProjectScope(linked_projects=frozenset({"alpha", "beta"}))


def _brief(updated: object = "2026-11-01", **frontmatter: Any) -> DocumentSnapshot:
    return doc(BRIEF_PATH, type="project", project="alpha", updated=updated, **frontmatter)


def _decisions(count: int, *, day: str = "2026-11-03", prefix: str = "d", **frontmatter: Any) -> list[DocumentSnapshot]:
    fields: dict[str, Any] = {"type": "decision", "updated": day, **frontmatter}
    return [doc(f"wiki/decisions/{prefix}{index}.md", **fields) for index in range(count)]


def test_threshold_is_five() -> None:
    assert BRIEF_STALE_THRESHOLD == 5


@pytest.mark.parametrize(
    ("brief", "count", "stale"),
    [
        (None, 4, False),
        (None, 5, True),
        ("2026-11-01", 4, False),
        ("2026-11-01", 5, True),
    ],
    ids=["no-brief-4", "no-brief-5", "after-brief-4", "after-brief-5"],
)
def test_table(brief: str | None, count: int, stale: bool) -> None:
    result = brief_staleness(
        _brief(brief) if brief is not None else None, _decisions(count), threshold=BRIEF_STALE_THRESHOLD
    )

    assert result.count == count
    assert result.stale is stale


def test_decisions_on_or_before_the_brief_day_do_not_count() -> None:
    older = _decisions(3, day="2026-10-20", prefix="old")
    same_day = _decisions(3, day="2026-11-01", prefix="same")
    newer = _decisions(4, prefix="new")

    result = brief_staleness(_brief(), [*older, *same_day, *newer], threshold=5)

    assert result.count == 4
    assert not result.stale
    assert [document.path for document in result.new_decisions] == [f"wiki/decisions/new{i}.md" for i in range(4)]


def test_memory_kind_decision_counts_and_other_pages_do_not() -> None:
    pages = [
        *_decisions(4),
        doc("wiki/notes/m.md", type="note", memory_kind="decision", updated="2026-11-03"),
        doc("wiki/concepts/c.md", type="concept", updated="2026-11-03"),
    ]

    result = brief_staleness(_brief(), pages, threshold=5)

    assert result.count == 5
    assert "wiki/concepts/c.md" not in [document.path for document in result.new_decisions]


@pytest.mark.parametrize("status", ["superseded", "retired", "deprecated", "stale"])
def test_superseded_and_retired_decisions_do_not_count(status: str) -> None:
    pages = [*_decisions(4), *_decisions(3, prefix="gone", status=status)]

    result = brief_staleness(_brief(), pages, threshold=5)

    assert result.count == 4
    assert not result.stale


def test_decisions_of_another_project_do_not_count() -> None:
    documents = {
        "main": (
            _brief(),
            *_decisions(4, project="alpha"),
            *_decisions(3, prefix="beta", project="beta"),
        )
    }

    result = project_brief_staleness(documents, project_id="alpha", vault_scopes={"main": SHARED})

    assert result.staleness.count == 4
    assert not result.stale


def test_unlabelled_decisions_follow_the_vault_scope_rule() -> None:
    documents = {"main": (*_decisions(5),)}

    linked_alone = project_brief_staleness(documents, project_id="alpha", vault_scopes={"main": ALPHA})
    shared_not_sharable = project_brief_staleness(documents, project_id="alpha", vault_scopes={"main": SHARED})

    assert linked_alone.stale
    assert not shared_not_sharable.stale


def test_project_rule_finds_the_brief_and_does_not_count_it() -> None:
    documents = {"main": (_brief(), *_decisions(5, day="2026-10-01"))}

    result = project_brief_staleness(documents, project_id="alpha", vault_scopes={"main": ALPHA})

    assert result.staleness.brief is not None
    assert result.staleness.brief.path == BRIEF_PATH
    assert result.staleness.count == 0
    assert result.brief_path == BRIEF_PATH


def test_retired_brief_counts_as_no_brief() -> None:
    documents = {"main": (_brief(status="retired"), *_decisions(5, day="2026-10-01"))}

    result = project_brief_staleness(documents, project_id="alpha", vault_scopes={"main": ALPHA})

    assert result.staleness.brief is None
    assert result.stale


def test_brief_in_two_vaults_uses_the_first_and_warns_once() -> None:
    documents = {
        "main": (_brief("2026-11-05"), *_decisions(5)),
        "team": (doc(BRIEF_PATH, vault_id="team", type="project", project="alpha", updated="2026-10-01"),),
    }

    result = project_brief_staleness(documents, project_id="alpha", vault_scopes={"main": ALPHA, "team": ALPHA})

    assert result.staleness.brief is not None
    assert result.staleness.brief.vault_id == "main"
    assert result.staleness.count == 0
    assert len(result.warnings) == 1


def test_brief_without_updated_counts_every_decision_and_undated_decisions_never_count_after_a_dated_brief() -> None:
    undated = [doc("wiki/decisions/u.md", type="decision")]

    without_date = brief_staleness(_brief(updated=None), [*_decisions(4), *undated], threshold=5)
    dated = brief_staleness(_brief(), [*_decisions(4), *undated], threshold=5)

    assert without_date.count == 5
    assert dated.count == 4


def test_yaml_dates_and_times_compare_like_strings() -> None:
    brief = _brief(updated=date(2026, 11, 1))
    decisions = [
        doc("wiki/decisions/a.md", type="decision", updated=date(2026, 11, 2)),
        doc("wiki/decisions/b.md", type="decision", updated=datetime(2026, 11, 1, 23, 0)),
        doc("wiki/decisions/c.md", type="decision", created="2026-11-04"),
    ]

    result = brief_staleness(brief, decisions, threshold=5)

    assert [document.path for document in result.new_decisions] == ["wiki/decisions/a.md", "wiki/decisions/c.md"]
    timed = brief_staleness(_brief(updated="2026-11-01T10:00:00+00:00"), decisions, threshold=5)
    assert [document.path for document in timed.new_decisions] == [
        "wiki/decisions/a.md",
        "wiki/decisions/b.md",
        "wiki/decisions/c.md",
    ]
    late = brief_staleness(
        _brief(updated="2026-11-01T10:00:00+00:00"),
        [doc("wiki/decisions/t.md", type="decision", updated="2026-11-01T11:00:00+00:00")],
        threshold=5,
    )
    assert late.count == 1


def test_key_hashes_counted_paths_and_dates_and_changes_with_a_new_decision() -> None:
    documents = {"main": (_brief(), *_decisions(5))}
    first = project_brief_staleness(documents, project_id="alpha", vault_scopes={"main": ALPHA})
    again = project_brief_staleness(
        {"main": tuple(reversed(documents["main"]))}, project_id="alpha", vault_scopes={"main": ALPHA}
    )
    same_day_more = project_brief_staleness(
        {"main": (*documents["main"], *_decisions(1, prefix="extra"))},
        project_id="alpha",
        vault_scopes={"main": ALPHA},
    )
    changed_date = project_brief_staleness(
        {"main": (_brief(), *_decisions(4), doc("wiki/decisions/d4.md", type="decision", updated="2026-11-04"))},
        project_id="alpha",
        vault_scopes={"main": ALPHA},
    )

    prefix, project, digest = first.key.split(":")
    assert (prefix, project) == ("brief", "alpha")
    assert len(digest) == 12 and int(digest, 16) >= 0
    assert again.key == first.key
    assert same_day_more.key != first.key
    assert changed_date.key != first.key


def test_threshold_must_be_positive() -> None:
    with pytest.raises(ValueError):
        brief_staleness(None, (), threshold=0)


def test_brief_module_has_no_write_path() -> None:
    source = Path(brief_module.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    called = {
        node.func.attr if isinstance(node.func, ast.Attribute) else getattr(node.func, "id", "")
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
    }
    assert not called & {"open", "write_text", "write_bytes", "unlink", "rename", "mkdir", "run", "touch"}
    imported = {
        alias.name if isinstance(node, ast.Import) else node.module or ""
        for node in ast.walk(tree)
        if isinstance(node, ast.Import | ast.ImportFrom)
        for alias in node.names
    }
    forbidden = ("vault_graph.operation", "vault_graph.interface", "subprocess")
    assert not any(name.startswith(forbidden) for name in imported)
