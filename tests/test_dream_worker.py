"""The dream run (spec 2026-11-19 D2, C1 to C7).

The judge and the candidate source are fakes. The memory write service is the real one over a recording
`VaultWriter`, so the tests see the drafts a Vault would receive and no Vault file is ever written.
"""

from __future__ import annotations

import json
from collections.abc import Collection, Sequence
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from tests.test_memory_write_service import REVIEW_PATH, DiskPageReader, FakeVaultMap, RecordingWriter, make_vault
from tests.test_read_only_boundary import file_bytes
from vault_graph.context.memory.memory_candidates import ComparisonPage, MemoryCandidate
from vault_graph.interface.composition.adapters.dream_judge import (
    PROMPT_VERSION,
    DreamAnswer,
    DreamItem,
    DreamJudgeUnavailable,
    DreamJudgment,
    DreamOutputInvalid,
    DreamPage,
)
from vault_graph.interface.composition.adapters.dream_worker import (
    BATCH_SIZE,
    DREAM_WORKER_LOCK,
    DreamPorts,
    read_dream_runs,
    read_exchange_lines,
    read_judged_keys,
    run_dream,
    run_dream_locked,
)
from vault_graph.interface.composition.adapters.temporary_draft_files import TemporaryDraftFiles
from vault_graph.interface.composition.memory_candidate_sources import MemoryCandidatePackage
from vault_graph.operation.memory.memory_ports import WriteOutcome
from vault_graph.operation.memory.memory_write_service import MemoryWriteService
from vault_graph.operation.scope.dream_settings import DreamSettings, dream_judged_path, dream_runs_path
from vault_graph.project.context.project_binding_reader import MappedVault
from vault_graph.storage.local.reviewed_log import JsonlReviewedLog

NOW = datetime(2026, 11, 19, 12, 0, tzinfo=UTC)
ON = DreamSettings(enabled=True)
QUOTE = "임베딩 모델은 arctic-m으로 정했어"
HUMAN = f"아니야, 그 방법 말고\n{QUOTE}. 다음부터 그렇게 해."
PAGE_PATH = "wiki/decisions/embedding-model.md"

MEMORY_PAGE = """---
title: Embedding model
type: decision
status: active
created: 2026-10-01
updated: 2026-10-01
owner: agent
summary: Embedding model
source_count: 1
tags: []
related: []
confidence: medium
---

# Embedding model

The default embedding model is e5-small.

## Evidence

Status: stated

- Evidence: raw/sessions/2026-10-01-s0.md L4-L9
"""

CLAIM_PAGE = """---
title: Search defaults
type: decision
status: active
---

# Search defaults

| Claim | Status | Evidence |
|---|---|---|
| The default embedding model is e5-small | stated | raw/sessions/2026-10-01-s0.md L4-L9 |
"""


def candidate(number: int, *, human: str = HUMAN, pages: Sequence[str] = (), age_days: float = 1.0) -> MemoryCandidate:
    return MemoryCandidate(
        key=f"session:s{number}",
        kind="session_exchange",
        location=f"raw/sessions/2026-11-10-s{number}.md L10-L20",
        comparison=tuple(
            ComparisonPage(
                vault_id="main",
                path=path,
                title=path.rsplit("/", 1)[-1],
                status="active",
                superseded_by=None,
                retired_reason=None,
                evidence_date=None,
            )
            for path in pages
        ),
        signal="decision",
        started_at=NOW - timedelta(days=age_days),
        human_text=human,
    )


def remember(number: int, **overrides: str) -> DreamJudgment:
    fields = {
        "key": f"session:s{number}",
        "action": "remember",
        "quote": QUOTE,
        "title": f"임베딩 모델 결정 {number}",
        "kind": "decision",
        "summary": "기본 임베딩 모델을 arctic-m으로 정했다.",
        "body": "기본 임베딩 모델은 arctic-m이다.",
    }
    fields.update(overrides)
    return DreamJudgment(**fields)


def none(number: int) -> DreamJudgment:
    return DreamJudgment(key=f"session:s{number}", action="none")


class FakeJudge:
    model = "fake-model"

    def __init__(self, judgments: Sequence[DreamJudgment] = (), *, cost_usd: float | None = None) -> None:
        self.judgments = {judgment.key: judgment for judgment in judgments}
        self.cost_usd = cost_usd
        self.error: Exception | None = None
        self.calls: list[tuple[list[DreamItem], list[DreamPage]]] = []

    def judge(self, items: Sequence[DreamItem], pages: Sequence[DreamPage]) -> DreamAnswer:
        self.calls.append((list(items), list(pages)))
        if self.error is not None:
            raise self.error
        found = tuple(self.judgments[item.key] for item in items if item.key in self.judgments)
        return DreamAnswer(judgments=found, cost_usd=self.cost_usd)

    @property
    def judged_keys(self) -> list[str]:
        return [item.key for items, _ in self.calls for item in items]


class World:
    def __init__(self, tmp_path: Path, candidates: Sequence[MemoryCandidate], judge: FakeJudge) -> None:
        tmp_path.mkdir(exist_ok=True)
        self.graph_home = tmp_path / "graph-home"
        self.graph_home.mkdir()
        self.cwd = tmp_path / "project"
        self.vault = make_vault(tmp_path, "main")
        self.other = make_vault(tmp_path, "other")
        self.candidates = list(candidates)
        self.judge = judge
        self.writer = RecordingWriter()
        self.pending: dict[Path, int] = {}
        self.source_calls: list[tuple[frozenset[str], int | None, bool]] = []
        self.now = NOW
        temp_root = tmp_path / "os-temp"
        temp_root.mkdir()
        self.vault_map = FakeVaultMap(
            (self.vault, self.other), {str(self.cwd): (self.vault, self.other)}, default=self.vault
        )
        self.page_reader = DiskPageReader()
        self.ports = DreamPorts(
            vault_map=self.vault_map,
            candidates=self.source,
            exchange_text=lambda item: f"### user\n{item.human_text}\n### assistant\n네.",
            page_reader=self.page_reader,
            memory=MemoryWriteService(
                vault_map=self.vault_map,
                writer=self.writer,
                page_reader=self.page_reader,
                today=lambda: date(2026, 11, 19),
                drafts=TemporaryDraftFiles(temp_root=temp_root),
            ),
            pending_count=lambda root: self.pending.get(root, 0),
            reviewed_log=JsonlReviewedLog(self.graph_home),
            judge=judge,
        )

    def source(self, skip_keys: Collection[str], limit: int | None, with_comparison: bool) -> MemoryCandidatePackage:
        self.source_calls.append((frozenset(skip_keys), limit, with_comparison))
        left = [item for item in self.candidates if item.key not in skip_keys]
        return MemoryCandidatePackage("project", tuple(left if limit is None else left[:limit]))

    def run(self, settings: DreamSettings = ON, **options: Any) -> Any:
        options.setdefault("manual", True)
        return run_dream(self.graph_home, self.cwd, settings, self.ports, now=lambda: self.now, **options)

    def add_page(self, path: str = PAGE_PATH, text: str = MEMORY_PAGE, vault: MappedVault | None = None) -> None:
        target = (vault or self.vault).path / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")

    def jsonl(self, path: Path) -> list[dict[str, Any]]:
        if not path.is_file():
            return []
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]

    @property
    def judged(self) -> list[dict[str, Any]]:
        return self.jsonl(dream_judged_path(self.graph_home))

    @property
    def reviewed(self) -> list[dict[str, Any]]:
        return self.jsonl(self.graph_home / "memory" / "reviewed.jsonl")


# A proposal


def test_a_quoted_judgment_becomes_an_inferred_proposal(tmp_path: Path) -> None:
    world = World(tmp_path, [candidate(1)], FakeJudge([remember(1, memory_kind="decision")], cost_usd=0.4))
    before = file_bytes(world.vault.path)

    run = world.run()

    assert (run.status, run.reason, run.judged, run.outcomes) == ("ran", None, 1, {"proposed": 1})
    assert run.cost_usd == 0.4
    assert world.writer.calls == []  # nothing is published
    vault_root, _, summary, _ = world.writer.proposals[0]
    assert vault_root == world.vault.path
    assert summary == "Add memory: 임베딩 모델 결정 1"
    draft = world.writer.drafts[0]
    assert draft["path"] == "wiki/decisions/임베딩-모델-결정-1.md"
    body = str(draft["body"])
    assert "Status: inferred" in body
    assert f'- Evidence: raw/sessions/2026-11-10-s1.md L10-L20 "{QUOTE}"' in body
    frontmatter = draft["frontmatter"]
    assert isinstance(frontmatter, dict)
    assert frontmatter["project"] == "project"
    assert frontmatter["memory_kind"] == "decision"
    assert "pin" not in frontmatter
    assert frontmatter["summary"] == "기본 임베딩 모델을 arctic-m으로 정했다."
    assert file_bytes(world.vault.path) == before  # vault-graph wrote no Vault file

    proposal = run.proposals[0]
    assert (proposal.candidate_key, proposal.action, proposal.vault) == ("session:s1", "remember", "main")
    assert proposal.review_path == REVIEW_PATH
    assert [(item["candidate_key"], item["outcome"]) for item in world.reviewed] == [("session:s1", "dream_proposed")]
    assert world.judged == []
    logged = read_dream_runs(world.graph_home)
    assert len(logged) == 1
    assert logged[0]["project"] == "project"
    assert logged[0]["status"] == "ran"
    assert logged[0]["model"] == "fake-model"
    assert logged[0]["prompt_version"] == PROMPT_VERSION
    assert logged[0]["proposals"][0]["review_path"] == REVIEW_PATH
    assert logged[0]["proposals"][0]["vault_root"] == str(world.vault.path)


def test_the_judge_sees_the_user_text_the_exchange_and_only_found_pages(tmp_path: Path) -> None:
    item = candidate(1, pages=(PAGE_PATH, "wiki/decisions/gone.md", "wiki/a.md", "wiki/b.md"))
    world = World(tmp_path, [item], FakeJudge([none(1)]))
    world.add_page()

    world.run()

    items, pages = world.judge.calls[0]
    assert items[0].user_text == HUMAN
    assert items[0].exchange_text.startswith("### user")
    assert items[0].date == "2026-11-18"
    assert items[0].pages == (PAGE_PATH,)  # only the first three are looked at, and only pages that exist
    assert [(page.path, page.changeable) for page in pages] == [(PAGE_PATH, True)]
    assert "The default embedding model is e5-small." in pages[0].text


# The quote check (C1)


def test_a_quote_that_the_person_did_not_type_sends_nothing(tmp_path: Path) -> None:
    world = World(tmp_path, [candidate(1)], FakeJudge([remember(1, quote="임베딩 모델은 e5-small로 정했어")]))

    run = world.run()

    assert run.outcomes == {"quote_rejected": 1}
    assert run.proposals == ()
    assert world.writer.proposals == []
    assert world.reviewed == []
    assert [(item["candidate_key"], item["outcome"]) for item in world.judged] == [("session:s1", "quote_rejected")]


def test_a_quote_from_the_assistant_side_of_the_exchange_is_refused(tmp_path: Path) -> None:
    world = World(tmp_path, [candidate(1, human="그건 나중에 다시 얘기하자 지금은 넘어가")], FakeJudge())
    world.judge.judgments["session:s1"] = remember(1, quote="### assistant")

    assert world.run().outcomes == {"quote_rejected": 1}
    assert world.writer.proposals == []


# Skips never hide a candidate from manual cleanup (C2)


def test_none_is_recorded_only_in_the_dream_record(tmp_path: Path) -> None:
    world = World(tmp_path, [candidate(1), candidate(2)], FakeJudge([none(1), none(2)]))

    run = world.run()

    assert run.outcomes == {"none": 2}
    assert not (world.graph_home / "memory" / "reviewed.jsonl").exists()
    assert {item["candidate_key"] for item in world.judged} == {"session:s1", "session:s2"}
    assert all(item["prompt_version"] == PROMPT_VERSION and item["model"] == "fake-model" for item in world.judged)
    assert read_judged_keys(world.graph_home, model="fake-model") == {"session:s1", "session:s2"}


def test_judged_candidates_are_left_out_before_the_bundle_is_cut(tmp_path: Path) -> None:
    items = [candidate(number) for number in range(1, 6)]
    world = World(tmp_path, items, FakeJudge([none(number) for number in range(1, 6)]))
    settings = replace(ON, bundle_limit=2)

    world.run(settings)
    world.run(settings)
    world.run(settings)

    assert world.judge.judged_keys == [f"session:s{number}" for number in range(1, 6)]
    assert world.source_calls[-1] == (frozenset({"session:s1", "session:s2", "session:s3", "session:s4"}), 2, True)


def test_a_record_from_another_prompt_version_or_model_is_judged_again(tmp_path: Path) -> None:
    world = World(tmp_path, [candidate(1), candidate(2), candidate(3)], FakeJudge([none(1), none(2), none(3)]))
    path = dream_judged_path(world.graph_home)
    path.parent.mkdir(parents=True)
    records = [
        {"candidate_key": "session:s1", "outcome": "none", "prompt_version": "dream-0", "model": "fake-model"},
        {"candidate_key": "session:s2", "outcome": "none", "prompt_version": PROMPT_VERSION, "model": "old-model"},
        {"candidate_key": "session:s3", "outcome": "none", "prompt_version": PROMPT_VERSION, "model": "fake-model"},
    ]
    path.write_text("".join(json.dumps(record) + "\n" for record in records) + "broken line\n", encoding="utf-8")

    world.run()

    assert world.judge.judged_keys == ["session:s1", "session:s2"]


def test_an_exchange_without_a_judgment_comes_back(tmp_path: Path) -> None:
    world = World(tmp_path, [candidate(1), candidate(2)], FakeJudge([none(1)]))

    run = world.run()

    assert run.judged == 1
    assert [item["candidate_key"] for item in world.judged] == ["session:s1"]


# Limits (C3, C4)


def test_a_full_review_queue_stops_the_run_before_the_judge(tmp_path: Path) -> None:
    world = World(tmp_path, [candidate(1)], FakeJudge([remember(1)]))
    world.pending[world.vault.path] = 10

    run = world.run()

    assert (run.status, run.reason) == ("skipped", "pending_cap")
    assert world.judge.calls == []
    assert read_dream_runs(world.graph_home) == []


def test_a_run_sends_only_what_fits_under_the_pending_cap(tmp_path: Path) -> None:
    world = World(tmp_path, [candidate(n) for n in (1, 2, 3)], FakeJudge([remember(n) for n in (1, 2, 3)]))
    world.pending[world.vault.path] = 8

    run = world.run()

    assert run.outcomes == {"proposed": 2, "deferred": 1}
    assert len(world.writer.proposals) == 2
    assert world.judged == []  # the deferred candidate is judged again in a later run
    assert [item["candidate_key"] for item in world.reviewed] == ["session:s1", "session:s2"]


def test_a_run_sends_at_most_proposals_per_run_and_stops_judging(tmp_path: Path) -> None:
    count = BATCH_SIZE * 2
    world = World(tmp_path, [candidate(n) for n in range(count)], FakeJudge([remember(n) for n in range(count)]))

    run = world.run(replace(ON, proposals_per_run=3))

    assert run.outcomes == {"proposed": 3, "deferred": BATCH_SIZE - 3}
    assert len(world.judge.calls) == 1  # the second batch is not paid for


def test_the_hook_run_needs_dreaming_on(tmp_path: Path) -> None:
    world = World(tmp_path, [candidate(n) for n in range(30)], FakeJudge())

    run = world.run(DreamSettings(enabled=False), manual=False)

    assert (run.status, run.reason) == ("skipped", "off")
    assert world.judge.calls == []


def test_the_hook_run_waits_until_enough_exchanges_wait_or_they_are_old(tmp_path: Path) -> None:
    few = World(tmp_path / "few", [candidate(n) for n in range(19)], FakeJudge())
    assert few.run(manual=False).reason == "not_due"
    assert few.judge.calls == []

    many = World(tmp_path / "many", [candidate(n) for n in range(20)], FakeJudge())
    assert many.run(manual=False).status == "ran"

    old = World(tmp_path / "old", [candidate(n, age_days=8.0) for n in range(3)], FakeJudge())
    assert old.run(manual=False).status == "ran"

    manual = World(tmp_path / "manual", [candidate(1)], FakeJudge())
    assert manual.run(manual=True).status == "ran"


def test_the_hook_run_runs_once_per_interval_for_a_project(tmp_path: Path) -> None:
    world = World(tmp_path, [candidate(n) for n in range(30)], FakeJudge([none(n) for n in range(30)]))
    settings = replace(ON, bundle_limit=5)

    assert world.run(settings, manual=False).status == "ran"
    world.now = NOW + timedelta(hours=23)
    assert world.run(settings, manual=False).reason == "interval"
    assert world.run(settings, manual=True).status == "ran"  # a manual run does not wait
    world.now = NOW + timedelta(hours=48)
    assert world.run(settings, manual=False).status == "ran"


def test_a_failed_run_is_tried_again_after_an_hour(tmp_path: Path) -> None:
    world = World(tmp_path, [candidate(n) for n in range(30)], FakeJudge())
    world.judge.error = DreamJudgeUnavailable("claude cannot run")

    failed = world.run(manual=False)

    assert (failed.status, failed.reason, failed.message) == ("failed", "judge_unavailable", "claude cannot run")
    assert read_dream_runs(world.graph_home)[0]["status"] == "failed"
    assert world.judged == []
    world.judge.error = None
    world.now = NOW + timedelta(minutes=30)
    assert world.run(manual=False).reason == "interval"
    world.now = NOW + timedelta(minutes=61)
    assert world.run(manual=False).status == "ran"


def test_an_answer_off_the_schema_fails_the_run(tmp_path: Path) -> None:
    world = World(tmp_path, [candidate(1)], FakeJudge())
    world.judge.error = DreamOutputInvalid("not JSON")

    run = world.run()

    assert (run.status, run.reason) == ("failed", "judge_output_invalid")
    assert world.writer.proposals == []


def test_a_folder_outside_a_project_or_without_one_write_vault_is_skipped(tmp_path: Path) -> None:
    world = World(tmp_path, [candidate(1)], FakeJudge([remember(1)]))

    outside = run_dream(world.graph_home, tmp_path / "elsewhere", ON, world.ports, manual=True)
    assert (outside.status, outside.reason) == ("skipped", "no_project")

    no_default = FakeVaultMap((world.vault, world.other), {str(world.cwd): (world.vault, world.other)})
    run = run_dream(world.graph_home, world.cwd, ON, replace(world.ports, vault_map=no_default), manual=True)
    assert (run.status, run.reason) == ("skipped", "no_write_vault")
    assert world.judge.calls == []


# The always-injected layer (C6) and page changes


def test_a_brief_or_an_unknown_kind_is_an_invalid_answer(tmp_path: Path) -> None:
    world = World(
        tmp_path, [candidate(1), candidate(2)], FakeJudge([remember(1, kind="project"), remember(2, title="")])
    )

    run = world.run()

    assert run.outcomes == {"invalid_answer": 2}
    assert world.writer.proposals == []
    assert {item["outcome"] for item in world.judged} == {"invalid_answer"}


def update(number: int, path: str = PAGE_PATH) -> DreamJudgment:
    return DreamJudgment(
        key=f"session:s{number}",
        action="update_memory",
        quote=QUOTE,
        path=path,
        addition="2026-11-18부터 기본 임베딩 모델은 arctic-m이다.",
    )


def test_update_adds_to_the_page_and_keeps_its_evidence(tmp_path: Path) -> None:
    world = World(tmp_path, [candidate(1, pages=(PAGE_PATH,))], FakeJudge([update(1)]))
    world.add_page()

    run = world.run()

    assert run.outcomes == {"proposed": 1}
    assert run.proposals[0].target == PAGE_PATH
    draft = world.writer.drafts[0]
    assert draft["path"] == PAGE_PATH
    body = str(draft["body"])
    assert "The default embedding model is e5-small.\n\n2026-11-18부터 기본 임베딩 모델은 arctic-m이다." in body
    assert "- Evidence: raw/sessions/2026-10-01-s0.md L4-L9\n" in body
    assert f'- Evidence: raw/sessions/2026-11-10-s1.md L10-L20 "{QUOTE}"' in body
    assert "Status: inferred" in body
    frontmatter = draft["frontmatter"]
    assert isinstance(frontmatter, dict)
    assert "pin" not in frontmatter


@pytest.mark.parametrize(
    ("path", "text"),
    [
        (PAGE_PATH, MEMORY_PAGE.replace("status: active", "status: active\npin: true")),
        (PAGE_PATH, MEMORY_PAGE.replace("status: active", "status: retired")),
        (PAGE_PATH, MEMORY_PAGE.replace("type: decision", "type: project")),
        ("wiki/projects/project.md", MEMORY_PAGE),
        (PAGE_PATH, MEMORY_PAGE + "\n## Notes\n\nA person added this section.\n"),
        (PAGE_PATH, CLAIM_PAGE),
    ],
)
def test_update_refuses_pinned_brief_retired_and_other_shaped_pages(tmp_path: Path, path: str, text: str) -> None:
    world = World(tmp_path, [candidate(1, pages=(path,))], FakeJudge([update(1, path)]))
    world.add_page(path, text)

    run = world.run()

    assert run.outcomes == {"target_refused": 1}
    assert world.writer.proposals == []
    assert [item["outcome"] for item in world.judged] == ["target_refused"]


def test_pinned_pages_are_shown_as_not_changeable(tmp_path: Path) -> None:
    world = World(tmp_path, [candidate(1, pages=(PAGE_PATH,))], FakeJudge([none(1)]))
    world.add_page(text=MEMORY_PAGE.replace("status: active", "status: active\npin: true"))

    world.run()

    assert world.judge.calls[0][1][0].changeable is False


def test_a_page_that_was_not_shown_for_the_item_cannot_be_named(tmp_path: Path) -> None:
    world = World(tmp_path, [candidate(1)], FakeJudge([update(1)]))
    world.add_page()

    assert world.run().outcomes == {"invalid_answer": 1}
    assert world.writer.proposals == []


def supersede(claim: str) -> DreamJudgment:
    return DreamJudgment(
        key="session:s1",
        action="supersede_claim",
        quote=QUOTE,
        path=PAGE_PATH,
        claim=claim,
        new_claim="The default embedding model is arctic-m",
    )


def test_supersede_replaces_a_claim_that_is_in_the_page(tmp_path: Path) -> None:
    judge = FakeJudge([supersede("The default embedding model is e5-small")])
    world = World(tmp_path, [candidate(1, pages=(PAGE_PATH,))], judge)
    world.add_page(text=CLAIM_PAGE)

    run = world.run()

    assert run.outcomes == {"proposed": 1}
    edit = world.writer.drafts[0]["edits"]
    assert isinstance(edit, list)
    assert edit[0] == {
        "op": "supersede-claim",
        "claim": "The default embedding model is e5-small",
        "by": "The default embedding model is arctic-m",
        "status": "inferred",
        "evidence": f'raw/sessions/2026-11-10-s1.md L10-L20 "{QUOTE}"',
    }


def test_supersede_refuses_a_claim_that_is_not_in_the_page(tmp_path: Path) -> None:
    world = World(tmp_path, [candidate(1, pages=(PAGE_PATH,))], FakeJudge([supersede("The model is bge-large")]))
    world.add_page(text=CLAIM_PAGE)

    assert world.run().outcomes == {"target_refused": 1}
    assert world.writer.proposals == []


def test_a_page_in_another_linked_vault_is_proposed_there_under_its_own_cap(tmp_path: Path) -> None:
    world = World(tmp_path, [candidate(1, pages=(PAGE_PATH,)), candidate(2, pages=(PAGE_PATH,))], FakeJudge())
    world.judge.judgments = {"session:s1": update(1), "session:s2": update(2)}
    world.add_page(vault=world.other)
    world.pending[world.other.path] = 9

    run = world.run()

    assert run.outcomes == {"proposed": 1, "deferred": 1}
    assert world.writer.proposals[0][0] == world.other.path
    assert run.proposals[0].vault == "other"


# Vault answers


def test_a_draft_the_vault_rejects_is_recorded_and_an_error_is_tried_again(tmp_path: Path) -> None:
    world = World(tmp_path, [candidate(1)], FakeJudge([remember(1)]))
    world.writer.propose_outcome = WriteOutcome(status="rejected", messages=("bad draft",))
    assert world.run().outcomes == {"vault_rejected": 1}
    assert [item["outcome"] for item in world.judged] == ["vault_rejected"]
    assert world.reviewed == []

    again = World(tmp_path / "again", [candidate(1)], FakeJudge([remember(1)]))
    again.writer.propose_outcome = WriteOutcome(status="error", messages=("timed out",))
    run = again.run()
    assert run.outcomes == {"vault_error": 1}
    assert run.proposals == ()
    assert again.judged == []


# Dry run and the lock


def test_a_dry_run_judges_and_writes_nothing(tmp_path: Path) -> None:
    world = World(tmp_path, [candidate(1), candidate(2)], FakeJudge([remember(1), none(2)]))

    run = world.run(dry_run=True)

    assert run.dry_run is True
    assert run.outcomes == {"would_propose": 1, "none": 1}
    assert run.proposals[0].review_path is None
    assert world.writer.proposals == []
    assert not dream_judged_path(world.graph_home).exists()
    assert not dream_runs_path(world.graph_home).exists()
    assert not (world.graph_home / "memory").exists()


def test_only_one_dream_run_holds_the_lock(tmp_path: Path) -> None:
    import fcntl
    import os

    world = World(tmp_path, [candidate(1)], FakeJudge([none(1)]))
    lock = world.graph_home / DREAM_WORKER_LOCK
    lock.parent.mkdir(parents=True)
    descriptor = os.open(lock, os.O_RDWR | os.O_CREAT, 0o644)
    fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
    try:
        assert run_dream_locked(world.graph_home, world.cwd, ON, world.ports, manual=True) is None
        assert world.judge.calls == []
    finally:
        os.close(descriptor)

    run = run_dream_locked(world.graph_home, world.cwd, ON, world.ports, manual=True)
    assert run is not None and run.status == "ran"


# Reading the cited lines


def test_exchange_lines_come_from_the_first_vault_that_has_the_file(tmp_path: Path) -> None:
    first, second = tmp_path / "a", tmp_path / "b"
    (second / "raw" / "sessions").mkdir(parents=True)
    first.mkdir()
    (second / "raw" / "sessions" / "s1.md").write_text("one\ntwo\nthree\nfour\n", encoding="utf-8")
    (tmp_path / "secret.md").write_text("secret\n", encoding="utf-8")

    assert read_exchange_lines("raw/sessions/s1.md L2-L3", [first, second]) == "two\nthree"
    assert read_exchange_lines("raw/sessions/none.md L1-L2", [first, second]) == ""
    assert read_exchange_lines("../secret.md L1-L1", [first]) == ""
    assert read_exchange_lines("raw/sessions/s1.md", [second]) == ""
