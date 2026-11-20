"""`vg review` reads the proposals of every linked Vault and accepts or rejects them.

Spec 2026-11-20 A1, A2, A4, A7, A8.

The Vaults are plain folders under ``tmp_path``. A recording stand-in replaces ``VaultReviewCli``, so no Vault tool
runs, and another replaces ``start_catch_up_index``, so no index process starts.
"""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

import pytest
from typer.testing import CliRunner, Result

from vault_graph.interface.cli import review_commands
from vault_graph.interface.cli.main import app
from vault_graph.interface.composition.adapters.vault_review_cli import ReviewResolveOutcome
from vault_graph.interface.composition.adapters.vault_review_queue import UNPUBLISHED_FIX

runner = CliRunner()
ANSI_ESCAPE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")

QUOTE = 'session 7f3a#12 user: "배포는 금요일에 하지 않는다"'
NEW_PAGE_DRAFT: dict[str, object] = {
    "operation": "upsert-page",
    "path": "wiki/decisions/배포-요일.md",
    "frontmatter": {"title": "배포 요일", "type": "decision", "status": "active"},
    "body": f"# 배포 요일\n\n배포는 금요일에 하지 않는다.\n\n## Evidence\n\nStatus: inferred\n\n- Evidence: {QUOTE}\n",
}
UPDATE_DRAFT: dict[str, object] = {
    "operation": "upsert-page",
    "path": "wiki/page.md",
    "frontmatter": {"title": "Page", "status": "active"},
    "body": '# Page\n\n새 문장이다.\n\n## Evidence\n\n- Evidence: session 1#2 user: "새 문장"\n',
}
RETIRE_DRAFT: dict[str, object] = {
    "operation": "patch-page",
    "path": "wiki/page.md",
    "frontmatter": {"status": "retired", "retired_reason": "더는 맞지 않음"},
}
SUPERSEDE_DRAFT: dict[str, object] = {
    "operation": "patch-page",
    "path": "wiki/page.md",
    "edits": [
        {
            "op": "supersede-claim",
            "claim": "배포는 목요일까지 한다.",
            "by": "배포는 수요일까지 한다.",
            "status": "inferred",
            "evidence": QUOTE,
        }
    ],
}


@dataclass
class FakeReviewCli:
    """Records every resolve call. ``outcomes`` maps a review path to what the Vault would answer."""

    calls: list[dict[str, object]] = field(default_factory=list)
    outcomes: dict[str, ReviewResolveOutcome] = field(default_factory=dict)

    def __call__(self) -> FakeReviewCli:
        return self

    def resolve(self, vault_root: Path, review_path: str, *, status: str, resolution: str) -> ReviewResolveOutcome:
        self.calls.append({"vault": vault_root.name, "path": review_path, "status": status, "resolution": resolution})
        if review_path in self.outcomes:
            return self.outcomes[review_path]
        written = ("wiki/decisions/a.md", "wiki/log.md") if status == "accepted" else ()
        return ReviewResolveOutcome("resolved", written_paths=written)


@dataclass
class FakeCatchUp:
    released: bool = False

    def release(self) -> None:
        self.released = True


@dataclass
class FakeIndexStart:
    calls: list[tuple[Path, tuple[str, ...]]] = field(default_factory=list)
    started: list[FakeCatchUp] = field(default_factory=list)
    busy: bool = False

    def __call__(self, graph_home: Path, index_vault_ids: tuple[str, ...]) -> FakeCatchUp | None:
        self.calls.append((graph_home, index_vault_ids))
        if self.busy:
            return None
        self.started.append(FakeCatchUp())
        return self.started[-1]


@dataclass
class World:
    project: Path
    vault_map: Path
    graph_home: Path
    team: Path
    personal: Path
    cli: FakeReviewCli
    index: FakeIndexStart

    def run(self, *arguments: str, cwd: Path | None = None, stdin: str | None = None) -> Result:
        return runner.invoke(
            app,
            [
                "review",
                *arguments,
                "--cwd",
                str(cwd or self.project),
                "--graph-home",
                str(self.graph_home),
                "--vault-map",
                str(self.vault_map),
            ],
            input=stdin,
        )

    def interactive(self, stdin: str) -> Result:
        return runner.invoke(
            app,
            [
                "review",
                "--cwd",
                str(self.project),
                "--graph-home",
                str(self.graph_home),
                "--vault-map",
                str(self.vault_map),
            ],
            input=stdin,
        )

    def digest(self) -> dict[str, str]:
        """sha256 of every file in both Vaults and the Graph Home."""
        return {
            str(path): hashlib.sha256(path.read_bytes()).hexdigest()
            for root in (self.team, self.personal, self.graph_home)
            for path in sorted(root.rglob("*"))
            if path.is_file()
        }


def git_project(path: Path) -> Path:
    path.mkdir(parents=True)
    subprocess.run(["git", "init", "-q", str(path)], check=True)
    return path


def make_vault(path: Path) -> Path:
    (path / "wiki").mkdir(parents=True)
    (path / "wiki" / "page.md").write_text(
        "---\ntitle: Page\nstatus: draft\n---\n# Page\n\n옛 문장이다.\n", encoding="utf-8"
    )
    return path


def proposal(
    vault: Path,
    review_id: str,
    draft: object | None,
    *,
    status: str = "pending",
    resolution: str = '""',
    summary: str = "배포 요일을 기억한다",
    review_type: str = "memory-proposal",
) -> str:
    queue = vault / "scratch" / "review"
    queue.mkdir(parents=True, exist_ok=True)
    target = draft.get("path", "") if isinstance(draft, dict) else "wiki/page.md"
    (queue / f"{review_id}.md").write_text(
        f"---\nreview_id: {review_id}\ntype: {review_type}\nstatus: {status}\ncreated: 2026-11-20\n"
        f"updated: 2026-11-20\nsummary: {summary}\nresolution: {resolution}\n"
        f"draft: scratch/review/{review_id}.draft.json\ntarget_path: {target}\n---\n# {summary}\n",
        encoding="utf-8",
    )
    if draft is not None:
        text = draft if isinstance(draft, str) else json.dumps(draft, ensure_ascii=False)
        (queue / f"{review_id}.draft.json").write_text(text, encoding="utf-8")
    return f"scratch/review/{review_id}.md"


@pytest.fixture
def world(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> World:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.delenv("VAULT_GRAPH_FACTS_CHILD", raising=False)
    project = git_project(tmp_path / "project")
    team = make_vault(tmp_path / "vaults" / "team-vault")
    personal = make_vault(tmp_path / "vaults" / "personal-vault")
    vault_map = tmp_path / "vault-map.json"
    vault_map.write_text(
        json.dumps(
            {
                "version": 2,
                "vaults": {
                    "team-vault": {"path": str(team), "role": "team"},
                    "personal-vault": {"path": str(personal), "role": "personal"},
                },
                "projects": {"project": {"root": str(project), "vaults": ["team-vault", "personal-vault"]}},
            }
        ),
        encoding="utf-8",
    )
    # Only the team Vault is registered in the Graph Home. The personal Vault is linked but not registered.
    graph_home = home / ".vault-graph"
    init = runner.invoke(app, ["init", "--vault", str(team), "--graph-home", str(graph_home), "--vault-id", "team"])
    assert init.exit_code == 0, init.output
    cli = FakeReviewCli()
    index = FakeIndexStart()
    monkeypatch.setattr(review_commands, "VaultReviewCli", cli)
    monkeypatch.setattr(review_commands, "start_catch_up_index", index)
    return World(project, vault_map, graph_home, team, personal, cli, index)


# A1: every linked Vault is read, and reading changes nothing.


def test_list_shows_the_proposals_of_both_vaults_and_only_counts_other_review_items(world: World) -> None:
    proposal(world.team, "2026-11-20-memory-aaaa1111", NEW_PAGE_DRAFT)
    proposal(world.personal, "2026-11-20-memory-bbbb2222", RETIRE_DRAFT, summary="페이지를 폐기한다")
    proposal(world.team, "2026-11-19-contradiction", None, review_type="contradiction", summary="두 주장이 다르다")
    proposal(world.team, "2026-11-18-memory-done", NEW_PAGE_DRAFT, status="rejected", resolution="Not true.")
    before = world.digest()

    result = world.run("list")

    assert result.exit_code == 0, result.output
    lines = result.output.splitlines()
    assert lines[0].startswith("[personal-vault] 2026-11-20-memory-bbbb2222 wiki/page.md")
    assert "페이지를 폐기한다" in lines[0]
    assert lines[1].startswith("[team-vault] 2026-11-20-memory-aaaa1111 wiki/decisions/배포-요일.md")
    assert "배포 요일을 기억한다" in lines[1]
    assert "other pending review items in team-vault: 1" in result.output
    assert "2026-11-19-contradiction" not in result.output
    assert "두 주장이 다르다" not in result.output
    assert "2026-11-18-memory-done" not in result.output
    assert world.digest() == before
    assert world.cli.calls == []


def test_show_and_list_leave_every_vault_and_graph_home_file_unchanged(world: World) -> None:
    proposal(world.team, "p1", NEW_PAGE_DRAFT)
    proposal(world.personal, "p2", UPDATE_DRAFT)
    before = world.digest()

    assert world.run("list").exit_code == 0
    assert world.run("show", "p1").exit_code == 0
    assert world.run("show", "p2").exit_code == 0
    assert world.run().exit_code == 0

    assert world.digest() == before
    assert world.cli.calls == []
    assert world.index.calls == []


def test_a_folder_with_no_linked_vault_points_to_vg_setup_and_exits_1(world: World, tmp_path: Path) -> None:
    other = git_project(tmp_path / "other-project")

    result = world.run("list", cwd=other)

    assert result.exit_code == 1
    assert "no linked Vault" in result.output
    assert "`vg setup`" in result.output


def test_a_missing_vault_map_points_to_vg_setup_and_exits_1(world: World) -> None:
    world.vault_map.unlink()

    result = world.run("list")

    assert result.exit_code == 1
    assert "`vg setup`" in result.output


def test_no_pending_proposal_says_so_and_exits_0(world: World) -> None:
    for arguments in (("list",), ()):
        result = world.run(*arguments)
        assert result.exit_code == 0, result.output
        assert "No pending proposals." in result.output
        assert "terminal" not in result.output


def test_an_unknown_id_exits_1_without_running_the_vault(world: World) -> None:
    proposal(world.team, "p1", NEW_PAGE_DRAFT)

    for arguments in (("show", "nope"), ("accept", "nope"), ("reject", "nope", "--reason", "틀림")):
        result = world.run(*arguments)
        assert result.exit_code == 1, result.output
        assert "no proposal with ID nope" in result.output
    assert world.cli.calls == []


def test_an_id_in_two_vaults_names_both_and_asks_for_the_vault_option(world: World) -> None:
    proposal(world.team, "same-id", NEW_PAGE_DRAFT)
    proposal(world.personal, "same-id", RETIRE_DRAFT)

    for arguments in (("show", "same-id"), ("accept", "same-id"), ("reject", "same-id", "--reason", "틀림")):
        result = world.run(*arguments)
        assert result.exit_code == 1, result.output
        assert "personal-vault, team-vault" in result.output
        assert "--vault" in result.output
    assert world.cli.calls == []

    picked = world.run("accept", "same-id", "--vault", "personal-vault")

    assert picked.exit_code == 0, picked.output
    assert [call["vault"] for call in world.cli.calls] == ["personal-vault"]


def test_a_vault_name_that_is_not_linked_exits_1(world: World) -> None:
    proposal(world.team, "p1", NEW_PAGE_DRAFT)

    result = world.run("accept", "p1", "--vault", "elsewhere")

    assert result.exit_code == 1
    assert "elsewhere is not linked" in result.output
    assert world.cli.calls == []


def test_the_common_options_are_also_read_before_the_command_name(world: World) -> None:
    proposal(world.team, "p1", NEW_PAGE_DRAFT)

    result = runner.invoke(app, ["review", "--cwd", str(world.project), "--vault-map", str(world.vault_map), "list"])

    assert result.exit_code == 0, result.output
    assert "[team-vault] p1" in result.output


# A2: the changed text and the evidence, per draft shape.


def test_show_prints_the_whole_new_page_with_korean_text_and_the_quote(world: World) -> None:
    proposal(world.team, "p1", NEW_PAGE_DRAFT)

    result = world.run("show", "p1")

    assert result.exit_code == 0, result.output
    assert "vault: team-vault" in result.output
    assert "target: wiki/decisions/배포-요일.md" in result.output
    assert "summary: 배포 요일을 기억한다" in result.output
    assert "created: 2026-11-20" in result.output
    assert "New page: wiki/decisions/배포-요일.md" in result.output
    assert "title: 배포 요일" in result.output
    assert "배포는 금요일에 하지 않는다." in result.output
    assert f"- {QUOTE}" in result.output


def test_show_prints_the_body_diff_and_the_changed_frontmatter_keys_of_an_existing_page(world: World) -> None:
    proposal(world.team, "p1", UPDATE_DRAFT)

    result = world.run("show", "p1")

    assert result.exit_code == 0, result.output
    assert "Changed page: wiki/page.md" in result.output
    assert "status: draft -> active" in result.output
    assert "-옛 문장이다." in result.output
    assert "+새 문장이다." in result.output
    assert '- session 1#2 user: "새 문장"' in result.output


def test_show_prints_the_frontmatter_keys_a_retire_draft_sets(world: World) -> None:
    proposal(world.team, "p1", RETIRE_DRAFT)

    result = world.run("show", "p1")

    assert result.exit_code == 0, result.output
    assert "Patch to page: wiki/page.md" in result.output
    assert "status: retired" in result.output
    assert "retired_reason: 더는 맞지 않음" in result.output


def test_show_prints_the_old_claim_the_new_claim_and_the_evidence_of_a_supersede_draft(world: World) -> None:
    proposal(world.team, "p1", SUPERSEDE_DRAFT)

    result = world.run("show", "p1")

    assert result.exit_code == 0, result.output
    assert "old claim: 배포는 목요일까지 한다." in result.output
    assert "new claim: 배포는 수요일까지 한다." in result.output
    assert f"- {QUOTE}" in result.output


@pytest.mark.parametrize(
    ("draft", "why"),
    [
        (None, "scratch/review/p1.draft.json is missing."),
        ("{not json", "is not JSON"),
        ({"operation": "delete-page", "path": "wiki/page.md"}, "'delete-page' is not upsert-page or patch-page"),
    ],
    ids=["missing", "not-json", "unknown-operation"],
)
def test_a_proposal_with_an_unreadable_draft_is_listed_with_the_reason_and_cannot_be_accepted(
    world: World, draft: object | None, why: str
) -> None:
    proposal(world.team, "p1", draft)

    listed = world.run("list")
    shown = world.run("show", "p1")
    accepted = world.run("accept", "p1")

    assert listed.exit_code == 0, listed.output
    assert "[team-vault] p1" in listed.output
    assert "draft cannot be read" in listed.output
    assert why in listed.output
    assert shown.exit_code == 0, shown.output
    assert why in shown.output
    assert accepted.exit_code == 1
    assert "draft cannot be read" in accepted.output
    assert world.cli.calls == []

    rejected = world.run("reject", "p1", "--reason", "초안이 깨졌다")

    assert rejected.exit_code == 0, rejected.output
    assert world.cli.calls == [
        {"vault": "team-vault", "path": "scratch/review/p1.md", "status": "rejected", "resolution": "초안이 깨졌다"}
    ]


# F1: an accept nothing was published for.


def test_a_hand_edited_accept_is_listed_apart_and_accept_refuses_it_without_running_the_vault(world: World) -> None:
    proposal(world.team, "by-hand", NEW_PAGE_DRAFT, status="accepted")
    proposal(
        world.team, "published", NEW_PAGE_DRAFT, status="accepted", resolution='"ok Published: wiki/decisions/a.md."'
    )

    listed = world.run("list")
    accepted = world.run("accept", "by-hand")

    assert listed.exit_code == 0, listed.output
    assert "No pending proposals." in listed.output
    assert "unpublished accepts: 1" in listed.output
    unpublished = [line for line in listed.output.splitlines() if line.startswith("unpublished: ")]
    assert len(unpublished) == 1
    assert "[team-vault] by-hand" in unpublished[0]
    assert "scratch/review/by-hand.md" in unpublished[0]
    assert UNPUBLISHED_FIX in unpublished[0]
    assert accepted.exit_code == 1
    assert UNPUBLISHED_FIX in accepted.output
    assert world.cli.calls == []
    assert world.index.calls == []


def test_a_proposal_that_is_already_resolved_is_not_sent_to_the_vault_again(world: World) -> None:
    proposal(world.team, "done", NEW_PAGE_DRAFT, status="rejected", resolution="Not true.")

    result = world.run("accept", "done")

    assert result.exit_code == 1
    assert "already rejected" in result.output
    assert world.cli.calls == []


# A4: only a terminal is asked, and a child session is refused.


def test_without_a_terminal_the_bare_command_lists_and_says_a_terminal_is_needed(world: World) -> None:
    proposal(world.team, "p1", NEW_PAGE_DRAFT)

    result = world.interactive("a\n")

    assert result.exit_code == 0, result.output
    assert "[team-vault] p1" in result.output
    assert "Interactive review needs a terminal." in result.output
    assert world.cli.calls == []
    assert world.index.calls == []


@pytest.mark.parametrize(
    "arguments",
    [(), ("list",), ("show", "p1"), ("accept", "p1"), ("reject", "p1", "--reason", "틀림")],
    ids=["bare", "list", "show", "accept", "reject"],
)
def test_a_fact_or_dream_child_session_is_refused_before_anything_is_read(
    world: World, monkeypatch: pytest.MonkeyPatch, arguments: tuple[str, ...]
) -> None:
    proposal(world.team, "p1", NEW_PAGE_DRAFT)
    monkeypatch.setenv("VAULT_GRAPH_FACTS_CHILD", "1")
    monkeypatch.setattr(review_commands, "_is_terminal", lambda: True)
    before = world.digest()

    result = world.run(*arguments, stdin="a\n")

    assert result.exit_code == 1
    assert "refused" in result.output
    assert "p1" not in result.output
    assert world.cli.calls == []
    assert world.index.calls == []
    assert world.digest() == before


# D2: the interactive flow.


def test_in_a_terminal_each_proposal_is_shown_in_vault_then_id_order_and_the_choice_is_carried_out(
    world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    proposal(world.team, "t2", RETIRE_DRAFT)
    proposal(world.team, "t1", NEW_PAGE_DRAFT)
    proposal(world.personal, "p1", SUPERSEDE_DRAFT)
    monkeypatch.setattr(review_commands, "_is_terminal", lambda: True)

    # personal-vault p1: skip. team-vault t1: accept. team-vault t2: reject, first with a blank reason.
    result = world.interactive("s\na\nr\n\nr\n근거가 약하다\n")

    assert result.exit_code == 0, result.output
    assert result.output.index("id: p1") < result.output.index("id: t1") < result.output.index("id: t2")
    assert "New page: wiki/decisions/배포-요일.md" in result.output
    assert "Not rejected: a reject needs a reason." in result.output
    assert world.cli.calls == [
        {
            "vault": "team-vault",
            "path": "scratch/review/t1.md",
            "status": "accepted",
            "resolution": "Accepted in vg review.",
        },
        {"vault": "team-vault", "path": "scratch/review/t2.md", "status": "rejected", "resolution": "근거가 약하다"},
    ]
    assert "accepted: [team-vault] t1" in result.output
    assert "rejected: [team-vault] t2" in result.output
    assert "review: accepted=1 rejected=1 skipped=1" in result.output
    assert world.index.calls == [(world.graph_home.resolve(), ("team",))]


def test_skip_and_quit_change_nothing_and_run_nothing(world: World, monkeypatch: pytest.MonkeyPatch) -> None:
    proposal(world.team, "t1", NEW_PAGE_DRAFT)
    proposal(world.team, "t2", RETIRE_DRAFT)
    proposal(world.personal, "p1", SUPERSEDE_DRAFT)
    monkeypatch.setattr(review_commands, "_is_terminal", lambda: True)
    before = world.digest()

    result = world.interactive("s\nq\n")

    assert result.exit_code == 0, result.output
    assert "review: accepted=0 rejected=0 skipped=1" in result.output
    assert "id: t2" not in result.output
    assert world.cli.calls == []
    assert world.index.calls == []
    assert world.digest() == before
    # A skipped proposal is shown again by the next run.
    assert "[personal-vault] p1" in world.run("list").output


def test_input_that_ends_early_is_a_quit(world: World, monkeypatch: pytest.MonkeyPatch) -> None:
    proposal(world.team, "t1", NEW_PAGE_DRAFT)
    monkeypatch.setattr(review_commands, "_is_terminal", lambda: True)

    result = world.interactive("")

    assert result.exit_code == 0, result.output
    assert "review: accepted=0 rejected=0 skipped=0" in result.output
    assert world.cli.calls == []


def test_the_interactive_accept_of_an_unreadable_draft_is_refused_and_the_same_proposal_is_asked_again(
    world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    proposal(world.team, "t1", None)
    monkeypatch.setattr(review_commands, "_is_terminal", lambda: True)

    result = world.interactive("a\ns\n")

    assert result.exit_code == 0, result.output
    assert "draft cannot be read" in result.output
    assert "review: accepted=0 rejected=0 skipped=1" in result.output
    assert world.cli.calls == []


def test_a_failed_interactive_accept_is_counted_as_failed_and_the_exit_code_is_1(
    world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    proposal(world.team, "t1", NEW_PAGE_DRAFT)
    world.cli.outcomes["scratch/review/t1.md"] = ReviewResolveOutcome(
        "rejected", reason="lint-failed", messages=("[error] 깨진 링크",)
    )
    monkeypatch.setattr(review_commands, "_is_terminal", lambda: True)

    result = world.interactive("a\n")

    assert result.exit_code == 1
    assert "accepted: " not in result.output
    assert "review: accepted=0 rejected=0 skipped=0 failed=1" in result.output
    assert world.index.calls == []


def test_an_accept_refused_because_the_page_changed_asks_again_so_it_can_be_rejected(
    world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    proposal(world.team, "t1", NEW_PAGE_DRAFT)
    refused = ReviewResolveOutcome(
        "rejected", reason="target-changed", messages=("Target page changed.",), guidance=("Reject it.",)
    )
    answers = iter([refused, ReviewResolveOutcome("resolved")])
    statuses: list[str] = []

    class Cli:
        def resolve(self, vault_root: Path, review_path: str, *, status: str, resolution: str) -> ReviewResolveOutcome:
            statuses.append(status)
            return next(answers)

    monkeypatch.setattr(review_commands, "VaultReviewCli", Cli)
    monkeypatch.setattr(review_commands, "_is_terminal", lambda: True)

    result = world.interactive("a\nr\npage changed\n")

    assert result.exit_code == 1, result.output  # I5: the refused accept is a failure of the run
    assert statuses == ["accepted", "rejected"]
    assert "Reject it." in result.output
    assert "review: accepted=0 rejected=1 skipped=0 failed=1" in result.output


# I5: only what the Vault resolved is reported as accepted or rejected.


@pytest.mark.parametrize(
    "outcome",
    [
        ReviewResolveOutcome(
            "rejected",
            reason="target-changed",
            messages=("Target page changed.",),
            guidance=("Reject it, then propose.",),
        ),
        ReviewResolveOutcome("error", messages=("review resolve did not finish.",), guidance=("Run vg review list.",)),
    ],
    ids=["vault-refused", "no-contract-answer"],
)
def test_an_accept_the_vault_did_not_resolve_is_a_failure_with_the_vault_lines_and_no_index(
    world: World, outcome: ReviewResolveOutcome
) -> None:
    proposal(world.team, "p1", NEW_PAGE_DRAFT)
    world.cli.outcomes["scratch/review/p1.md"] = outcome

    result = world.run("accept", "p1")

    assert result.exit_code == 1
    assert "accepted: " not in result.output
    assert "failed: [team-vault] p1 was not accepted" in result.output
    for line in (*outcome.messages, *outcome.guidance):
        assert line in result.output
    assert world.index.calls == []


def test_a_reject_the_vault_did_not_resolve_is_a_failure(world: World) -> None:
    proposal(world.team, "p1", NEW_PAGE_DRAFT)
    world.cli.outcomes["scratch/review/p1.md"] = ReviewResolveOutcome(
        "rejected", reason="review-invalid", messages=("Review resolution aborted.",)
    )

    result = world.run("reject", "p1", "--reason", "틀림")

    assert result.exit_code == 1
    assert "rejected: " not in result.output
    assert "failed: [team-vault] p1 was not rejected (review-invalid)" in result.output
    assert "Review resolution aborted." in result.output


# A7: the index of a Vault that published starts once, and the command does not wait.


def test_two_accepts_in_one_vault_start_its_index_once(world: World, monkeypatch: pytest.MonkeyPatch) -> None:
    proposal(world.team, "t1", NEW_PAGE_DRAFT)
    proposal(world.team, "t2", RETIRE_DRAFT)
    monkeypatch.setattr(review_commands, "_is_terminal", lambda: True)

    result = world.interactive("a\na\n")

    assert result.exit_code == 0, result.output
    assert "review: accepted=2 rejected=0 skipped=0" in result.output
    assert world.index.calls == [(world.graph_home.resolve(), ("team",))]
    # The detached process waits for the gate, so the command opens it and leaves.
    assert [catch_up.released for catch_up in world.index.started] == [True]
    assert "index: started in the background for team" in result.output


def test_an_accept_starts_the_index_of_that_vault(world: World) -> None:
    proposal(world.team, "p1", NEW_PAGE_DRAFT)

    result = world.run("accept", "p1")

    assert result.exit_code == 0, result.output
    assert "accepted: [team-vault] p1 wiki/decisions/배포-요일.md" in result.output
    assert "published: wiki/decisions/a.md, wiki/log.md" in result.output
    assert world.index.calls == [(world.graph_home.resolve(), ("team",))]


def test_a_reject_starts_no_index(world: World) -> None:
    proposal(world.team, "p1", NEW_PAGE_DRAFT)

    result = world.run("reject", "p1", "--reason", "틀린 추론")

    assert result.exit_code == 0, result.output
    assert "rejected: [team-vault] p1" in result.output
    assert world.index.calls == []


def test_an_accept_that_wrote_no_path_starts_no_index(world: World) -> None:
    proposal(world.team, "p1", NEW_PAGE_DRAFT)
    world.cli.outcomes["scratch/review/p1.md"] = ReviewResolveOutcome("resolved")

    result = world.run("accept", "p1")

    assert result.exit_code == 0, result.output
    assert world.index.calls == []


def test_an_index_that_cannot_start_gives_the_vg_index_command_and_exit_code_0(world: World) -> None:
    proposal(world.team, "p1", NEW_PAGE_DRAFT)
    world.index.busy = True

    result = world.run("accept", "p1")

    assert result.exit_code == 0, result.output
    assert "accepted: [team-vault] p1" in result.output
    assert "`vg index --vault-id team`" in result.output
    assert "index: started" not in result.output


def test_an_accept_in_a_vault_that_is_not_registered_gives_the_vg_index_hint_and_exit_code_0(world: World) -> None:
    proposal(world.personal, "p1", RETIRE_DRAFT)

    result = world.run("accept", "p1")

    assert result.exit_code == 0, result.output
    assert "accepted: [personal-vault] p1" in result.output
    assert "Vault personal-vault is not registered in the Graph Home" in result.output
    assert "vg index --vault-id" in result.output
    assert world.index.calls == []


def test_an_accept_without_a_graph_home_still_resolves_and_gives_the_vg_index_hint(
    world: World, tmp_path: Path
) -> None:
    proposal(world.team, "p1", NEW_PAGE_DRAFT)

    result = runner.invoke(
        app,
        [
            "review",
            "accept",
            "p1",
            "--cwd",
            str(world.project),
            "--graph-home",
            str(tmp_path / "no-graph-home"),
            "--vault-map",
            str(world.vault_map),
        ],
    )

    assert result.exit_code == 0, result.output
    assert "accepted: [team-vault] p1" in result.output
    assert "vg index --vault-id" in result.output
    assert world.index.calls == []
    assert not (tmp_path / "no-graph-home").exists()


# A8: a reject needs a reason, an accept has a default one.


@pytest.mark.parametrize("reason", [(), ("--reason", ""), ("--reason", "   ")], ids=["none", "empty", "blank"])
def test_a_reject_without_a_reason_is_a_usage_error_and_the_vault_is_not_run(
    world: World, reason: tuple[str, ...]
) -> None:
    proposal(world.team, "p1", NEW_PAGE_DRAFT)

    result = world.run("reject", "p1", *reason)

    assert result.exit_code == 2
    # On CI the usage error is styled, and the style codes split the option name.
    assert "--reason" in ANSI_ESCAPE.sub("", result.output)
    assert world.cli.calls == []


def test_an_accept_without_a_reason_passes_the_default_text_as_the_resolution(world: World) -> None:
    proposal(world.team, "p1", NEW_PAGE_DRAFT)

    result = world.run("accept", "p1")

    assert result.exit_code == 0, result.output
    assert world.cli.calls == [
        {
            "vault": "team-vault",
            "path": "scratch/review/p1.md",
            "status": "accepted",
            "resolution": "Accepted in vg review.",
        }
    ]


def test_an_accept_passes_the_given_reason(world: World) -> None:
    proposal(world.team, "p1", NEW_PAGE_DRAFT)

    result = world.run("accept", "p1", "--reason", "사용자가 확인함")

    assert result.exit_code == 0, result.output
    assert world.cli.calls[0]["resolution"] == "사용자가 확인함"
