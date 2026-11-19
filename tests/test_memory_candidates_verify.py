"""The `verify` cleanup candidate: a current page and a later exchange on its topic (spec 2026-11-19 D3)."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any, cast

from vault_graph.context.memory.memory_candidates import (
    CANDIDATE_KINDS,
    VERIFY_EXCHANGES_PER_PAGE,
    VERIFY_KIND,
    CandidateKind,
    MemoryCandidate,
    MemoryPage,
    SessionExchange,
    SimilarPage,
    build_memory_candidates,
)
from vault_graph.context.memory.project_scope import FixedVaultProjectScope
from vault_graph.errors import VaultGraphError
from vault_graph.indexing.ingestion.document_models import SourceLocator
from vault_graph.interface.composition.memory_candidate_sources import SearchService, topic_exchanges
from vault_graph.operation.scope.vault_catalog import QueryScope

NOW = datetime(2026, 11, 19, 12, 0, tzinfo=UTC)
PROJECT_SCOPE = FixedVaultProjectScope(linked_projects=frozenset({"demo"}))
OTHER_SCOPE = FixedVaultProjectScope(linked_projects=frozenset({"other"}))
VERIFY_ONLY: tuple[CandidateKind, ...] = (VERIFY_KIND,)
PAGE_PATH = "wiki/decisions/embedding-model.md"


class NoFinder:
    def find_similar(self, query: str, *, limit: int) -> Sequence[SimilarPage]:
        raise AssertionError("a verify candidate needs no similarity search")


def page(
    path: str = PAGE_PATH,
    *,
    frontmatter: Mapping[str, object] | None = None,
    scope: FixedVaultProjectScope = PROJECT_SCOPE,
    text: str = "The default embedding model is e5-small.",
) -> MemoryPage:
    fields: dict[str, object] = {"type": "decision", "status": "active", "updated": "2026-11-01"}
    fields.update(frontmatter or {})
    return MemoryPage(
        vault_id="demo-vault",
        path=path,
        title="Embedding model",
        frontmatter=fields,
        vault_scope=scope,
        text=text,
        evidence_date="2026-10-20",
    )


def exchange(
    name: str, day: str, *, human: str = "임베딩 모델은 arctic-m으로 바꿨어", line: int = 10
) -> SessionExchange:
    return SessionExchange(
        parent_key=f"pk-{name}",
        path=f"raw/sessions/{day}-{name}.md",
        line_start=line,
        line_end=line + 10,
        started_at=datetime.fromisoformat(f"{day}T09:00:00+00:00"),
        human_text=human,
        exchange_id=f"id-{name}",
    )


def build(
    pages: Sequence[MemoryPage],
    page_exchanges: Mapping[tuple[str, str], Sequence[SessionExchange]],
    *,
    kinds: Sequence[CandidateKind] | None = VERIFY_ONLY,
    reviewed: Sequence[str] = (),
) -> tuple[MemoryCandidate, ...]:
    return build_memory_candidates(
        project_id="demo",
        l1_notes=(),
        imported_raw_sha256=(),
        exchanges=(),
        wiki_pages=(),
        reviewed_keys=frozenset(reviewed),
        similar_pages=NoFinder(),
        now=NOW,
        memory_pages=pages,
        kinds=kinds,
        page_exchanges=page_exchanges,
    )


def test_a_later_exchange_on_the_topic_makes_one_candidate() -> None:
    target = page()
    later = exchange("s2", "2026-11-10")

    (candidate,) = build([target], {target.key: [later]})

    assert candidate.kind == "verify"
    assert candidate.key == f"verify:demo-vault:{PAGE_PATH}:pk-s2"
    assert candidate.location == "raw/sessions/2026-11-10-s2.md L10-L20"
    assert candidate.human_text == "임베딩 모델은 arctic-m으로 바꿨어"
    assert candidate.started_at == later.started_at
    assert [item.path for item in candidate.targets] == [PAGE_PATH]
    assert candidate.comparison == candidate.targets


def test_verify_is_built_only_when_asked_for() -> None:
    target = page()

    assert "verify" not in CANDIDATE_KINDS
    assert build([target], {target.key: [exchange("s2", "2026-11-10")]}, kinds=None) == ()


def test_an_exchange_from_the_same_day_or_before_the_page_is_not_later() -> None:
    target = page()
    found = [exchange("same", "2026-11-01"), exchange("before", "2026-10-25")]

    assert build([target], {target.key: found}) == ()


def test_the_page_day_falls_back_to_created_then_the_evidence_date() -> None:
    created = page(frontmatter={"updated": None, "created": "2026-11-05"})
    dated_by_evidence = page("wiki/decisions/other.md", frontmatter={"updated": "not a date"})
    undated = MemoryPage(
        vault_id="demo-vault",
        path="wiki/decisions/undated.md",
        title="Undated",
        frontmatter={"type": "decision", "status": "active"},
        vault_scope=PROJECT_SCOPE,
        text="text",
    )
    found = [exchange("s2", "2026-11-03")]

    candidates = build(
        [created, dated_by_evidence, undated],
        {created.key: found, dated_by_evidence.key: found, undated.key: found},
    )

    assert [item.targets[0].path for item in candidates] == ["wiki/decisions/other.md"]


def test_pinned_retired_foreign_and_navigation_pages_are_never_checked() -> None:
    later = [exchange("s2", "2026-11-10")]
    pages = [
        page("wiki/decisions/pinned.md", frontmatter={"pin": True}),
        page("wiki/decisions/retired.md", frontmatter={"status": "retired"}),
        page("wiki/decisions/foreign.md", scope=OTHER_SCOPE),
        page("wiki/index.md", frontmatter={"type": "index"}),
    ]

    assert build(pages, {item.key: later for item in pages}) == ()


def test_an_exchange_the_page_already_cites_or_without_user_text_is_left_out() -> None:
    cited = page(text="Model is arctic-m.\n\n- Evidence: raw/sessions/2026-11-10-s2.md L10-L20")
    silent = page("wiki/decisions/silent.md")

    candidates = build(
        [cited, silent],
        {cited.key: [exchange("s2", "2026-11-10")], silent.key: [exchange("s3", "2026-11-11", human="")]},
    )

    assert candidates == ()


def test_at_most_two_exchanges_per_page_newest_first_and_reviewed_ones_are_skipped() -> None:
    target = page()
    found = [exchange(f"s{day}", f"2026-11-{day:02d}") for day in (5, 6, 7, 8)]

    candidates = build([target], {target.key: found}, reviewed=[f"verify:demo-vault:{PAGE_PATH}:pk-s8"])

    assert VERIFY_EXCHANGES_PER_PAGE == 2
    assert [item.key.rsplit(":", 1)[-1] for item in candidates] == ["pk-s7", "pk-s6"]


def test_an_exchange_older_than_the_candidate_age_limit_is_left_out() -> None:
    target = page(frontmatter={"updated": "2026-01-01"})
    old = SessionExchange(
        parent_key="pk-old",
        path="raw/sessions/2026-02-01-old.md",
        line_start=1,
        line_end=5,
        started_at=NOW - timedelta(days=200),
        human_text="임베딩 모델은 arctic-m으로 바꿨어",
    )

    assert build([target], {target.key: [old]}) == ()


# Finding the exchanges on a page's topic


def locator(first: int, last: int) -> SourceLocator:
    return SourceLocator(scheme="line", coordinates=(("line", str(first)), ("line_end", str(last))))


class FakeSearch:
    def __init__(self, evidence: Sequence[Any] = (), error: Exception | None = None) -> None:
        self.evidence = evidence
        self.error = error
        self.calls: list[dict[str, Any]] = []

    def search(self, **arguments: Any) -> Any:
        self.calls.append(arguments)
        if self.error is not None:
            raise self.error
        return SimpleNamespace(results=tuple(SimpleNamespace(evidence=(item,)) for item in self.evidence))


def search_service(fake: FakeSearch) -> SearchService:
    return cast(SearchService, fake)


SCOPE = cast(QueryScope, object())


def test_search_results_map_to_the_exchanges_whose_lines_they_overlap() -> None:
    target = page()
    first = exchange("s2", "2026-11-10", line=10)
    second = exchange("s2", "2026-11-10", line=40)
    second = SessionExchange(**{**second.__dict__, "parent_key": "pk-second"})
    fake = FakeSearch(
        [
            SimpleNamespace(path=first.path, source_locators=(locator(12, 14),)),
            SimpleNamespace(path="wiki/decisions/other.md", source_locators=(locator(1, 5),)),
            SimpleNamespace(path=first.path, source_locators=()),
        ]
    )
    warnings: list[str] = []

    found = topic_exchanges([target], [first, second], search=search_service(fake), scope=SCOPE, warnings=warnings)

    assert found == {target.key: (first,)}
    assert warnings == []
    call = fake.calls[0]
    assert call["mode"] == "evidence"
    assert call["query_text"].startswith("Embedding model The default embedding model")


def test_no_search_or_a_failed_search_gives_no_exchanges() -> None:
    target = page()
    later = exchange("s2", "2026-11-10")
    warnings: list[str] = []

    assert topic_exchanges([target], [later], search=None, scope=SCOPE, warnings=warnings) == {}
    failing = FakeSearch(error=VaultGraphError("index is locked"))
    assert topic_exchanges([target], [later], search=search_service(failing), scope=SCOPE, warnings=warnings) == {}
    assert warnings == ["Search for later exchanges failed: index is locked"]
