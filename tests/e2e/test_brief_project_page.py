"""End-to-end project brief through the real Vault tools (spec 2026-11-05 §4.4.7, §4.4.4 brief candidate, risk D5).

Acceptance A-27 (S12), A-35 (E2E part) and A-29 (S12 record). Each test installs Vaults with the
vault-builder named by ``VAULT_BUILDER_ROOT`` into a temporary HOME (``MemoryWorld`` of
``test_long_term_memory_scenarios``) and drives the writes through a real ``vg serve --mcp`` over stdio.
The vault-builder must have request S9: page type ``project`` at ``wiki/projects/<project>.md`` and a
``recall.sh`` that prints the brief under ``## Project Brief``.

The embedding model folder ``$HOME/llm/models`` and ``$HOME/.cache`` are shared by every test of one
pytest session, so the model is downloaded at most once per session.

Without ``VAULT_BUILDER_ROOT`` the tests are skipped.
"""

from __future__ import annotations

import json
import os
import re
from collections.abc import Iterable, Iterator
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import pytest

from tests.e2e.test_long_term_memory_scenarios import (
    BUILDER_ENV,
    PROJECT_ID,
    MemoryWorld,
    _run,
    file_hashes,
    frontmatter_lines,
    recall_blocks,
)
from vault_graph.context.pack.recall import BLOCK_D_TITLE, L3_BLOCK_TITLE

RECALL_SCRIPT = Path("tools/vault_migration/assets/project-memory/scripts/recall.sh")
BRIEF_PATH = f"wiki/projects/{PROJECT_ID}.md"
BRIEF_KEY = re.compile(rf"^brief:{re.escape(PROJECT_ID)}:[0-9a-f]{{12}}$")
EVIDENCE = ["User statement in the scenario session."]
FIRST_BRIEF = "Goal: ship the kestrel importer before the winter release."
UPDATED_BRIEF = "Goal: ship the kestrel importer and the osprey exporter before the winter release."


def brief_line(count: int) -> str:
    return f'- brief 갱신 필요: brief 이후 새 결정 {count}개. "기억 정리해"로 갱신하세요.'


@pytest.fixture(scope="session")
def builder_root() -> Path:
    value = os.environ.get(BUILDER_ENV)
    if not value:
        pytest.skip(f"set {BUILDER_ENV} to a vault-builder checkout to run the project brief scenarios")
    root = Path(value).expanduser().resolve()
    asset = root / RECALL_SCRIPT
    if not asset.is_file() or "## Project Brief" not in asset.read_text(encoding="utf-8"):
        pytest.fail(f"{BUILDER_ENV}={value} has no recall.sh that reads the project brief (request S9)")
    return root


@pytest.fixture(scope="session")
def shared_cache(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return tmp_path_factory.mktemp("shared-home-cache")


@pytest.fixture(scope="session")
def shared_models(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return tmp_path_factory.mktemp("shared-home-llm")


@pytest.fixture
def world(tmp_path: Path, builder_root: Path, shared_cache: Path, shared_models: Path) -> Iterator[MemoryWorld]:
    made = MemoryWorld(tmp_path, builder_root=builder_root, shared_cache=shared_cache)
    # The default embedding model folder is ~/llm/models (operation/scope/embedding_selection.py).
    (made.home / "llm").symlink_to(shared_models, target_is_directory=True)
    yield made


# A-27 (S12) and A-29: the first brief, the second refused, the update accepted -----------------------


def test_a27_remember_project_writes_the_brief_and_recall_shows_it_first_in_block_l3(world: MemoryWorld) -> None:
    world.install("proj", role="project")
    world.builder("set-default-write", "--project", PROJECT_ID, "--vault", "proj")
    # A-29 needs one pinned memory in the fixed Vault.
    world.seed_page(
        "proj",
        "Review every release",
        updated="2026-09-01",
        pin=True,
        memory_kind="rule",
        body="Releases get a review.",
    )
    world.vg_setup()
    cwd = str(world.project)

    first = world.mcp(
        "remember",
        title="Demo app brief",
        kind="project",
        body=FIRST_BRIEF,
        evidence=EVIDENCE,
        basis="stated",
        cwd=cwd,
    )
    assert first["status"] == "published", first["messages"]
    assert first["vault"] == "proj"
    assert BRIEF_PATH in first["written_paths"]
    brief = world.vault_root("proj") / BRIEF_PATH
    assert {"type: project", f"project: {PROJECT_ID}"} <= set(frontmatter_lines(brief))
    assert FIRST_BRIEF in brief.read_text(encoding="utf-8")

    world.vg_index()
    assert l3_first_line(world.recall("a27-after-remember")).startswith(FIRST_BRIEF)

    before = brief.read_bytes()
    second = world.mcp(
        "remember",
        title="Another brief",
        kind="project",
        body="Goal: something else.",
        evidence=EVIDENCE,
        basis="stated",
        cwd=cwd,
    )
    assert second["status"] == "rejected", second
    assert brief.read_bytes() == before

    updated = world.mcp(
        "update_memory", path=BRIEF_PATH, body=UPDATED_BRIEF, evidence=EVIDENCE, basis="stated", cwd=cwd
    )
    assert updated["status"] == "published", updated["messages"]
    assert UPDATED_BRIEF in brief.read_text(encoding="utf-8")
    assert "type: project" in frontmatter_lines(brief)

    world.vg_index()
    vg_text = world.recall("a27-after-update")
    assert l3_first_line(vg_text).startswith(UPDATED_BRIEF)

    # A-29: both recall paths give non-empty output. The first lines are printed for the PR record.
    script_text = run_recall_script(world)
    assert "## Project Brief" in script_text
    assert UPDATED_BRIEF in script_text
    vg_first = vg_text.splitlines()[0]
    script_first = script_text.splitlines()[0]
    assert vg_first.strip() and script_first.strip()
    print(f"A-29 vg recall first line: {vg_first}")
    print(f"A-29 recall.sh first line: {script_first}")


# A-35: the brief update line and candidate appear at five new decisions and leave on update -------------


def test_a35_update_memory_on_the_brief_removes_the_line_and_the_candidate(world: MemoryWorld) -> None:
    world.install("proj", role="project")
    world.builder("set-default-write", "--project", PROJECT_ID, "--vault", "proj")
    seed_old_brief(world)
    decisions = seed_decisions(world, range(1, 5))
    world.vg_setup()

    assert brief_line(4) not in world.recall("a35-four")
    assert brief_candidates(world) == []

    decisions += seed_decisions(world, [5])
    world.vg_index()
    hashes = file_hashes(world.vault_root("proj"))
    text = world.recall("a35-five")
    candidates = brief_candidates(world)
    assert file_hashes(world.vault_root("proj")) == hashes

    assert text.count(brief_line(5)) == 1
    assert brief_line(5) in recall_blocks(text)[BLOCK_D_TITLE]
    assert len(candidates) == 1, candidates
    candidate = candidates[0]
    assert BRIEF_KEY.match(candidate["key"]), candidate
    assert candidate["location"] == BRIEF_PATH
    assert sorted(page["path"] for page in candidate["comparison"]) == sorted(decisions)

    updated = world.mcp(
        "update_memory",
        path=BRIEF_PATH,
        body=UPDATED_BRIEF,
        evidence=EVIDENCE,
        basis="stated",
        cwd=str(world.project),
        candidate_key=candidate["key"],
    )
    assert updated["status"] == "published", updated["messages"]

    world.vg_index()
    hashes = file_hashes(world.vault_root("proj"))
    text = world.recall("a35-after-update")
    assert "brief 갱신 필요" not in text
    assert brief_candidates(world) == []
    assert l3_first_line(text).startswith(UPDATED_BRIEF)
    assert file_hashes(world.vault_root("proj")) == hashes


def test_a35_skipped_brief_candidate_leaves_and_comes_back_with_one_more_decision(world: MemoryWorld) -> None:
    world.install("proj", role="project")
    world.builder("set-default-write", "--project", PROJECT_ID, "--vault", "proj")
    seed_old_brief(world)
    seed_decisions(world, range(1, 6))
    world.vg_setup()

    hashes = file_hashes(world.vault_root("proj"))
    [first] = brief_candidates(world)
    skipped = world.mcp("mark_candidates_reviewed", keys=[first["key"]], cwd=str(world.project))
    assert skipped == {"recorded": [first["key"]], "outcome": "skipped"}

    assert brief_candidates(world) == []
    # The line stays while the rule says the brief needs an update.
    assert world.recall("a35-skipped").count(brief_line(5)) == 1
    assert file_hashes(world.vault_root("proj")) == hashes

    seed_decisions(world, [6])
    world.vg_index()
    hashes = file_hashes(world.vault_root("proj"))
    [again] = brief_candidates(world)
    assert BRIEF_KEY.match(again["key"]) and again["key"] != first["key"], (first["key"], again["key"])
    assert world.recall("a35-one-more").count(brief_line(6)) == 1
    assert file_hashes(world.vault_root("proj")) == hashes


# Helpers --------------------------------------------------------------------------------------------


def days_ago(days: int) -> str:
    return (date.today() - timedelta(days=days)).isoformat()


def seed_old_brief(world: MemoryWorld) -> None:
    """Publish a brief dated 60 days ago with the Vault's own publish-draft, as an agent wrote it back then."""
    day = days_ago(60)
    target = f"projects/{PROJECT_ID}"
    draft = {
        "version": 1,
        "operation": "upsert-page",
        "path": BRIEF_PATH,
        "frontmatter": {
            "title": "Demo app brief",
            "type": "project",
            "project": PROJECT_ID,
            "status": "active",
            "created": day,
            "updated": day,
            "owner": "human",
            "summary": "Demo app brief",
            "source_count": 1,
            "tags": [],
            "related": [],
            "confidence": "high",
            "quality": {
                "provenance": "section",
                "links": "unchecked",
                "contradictions": "unchecked",
                "review_required": False,
            },
        },
        "body": f"# Demo app brief\n\n{FIRST_BRIEF}\n\n## Evidence\n\n- Evidence: scenario seed by a person.\n",
        "index": {"section": "Projects", "target": target, "summary": "Demo app brief"},
        "log": {"event_type": "manual-note", "title": "Seed Demo app brief", "items": [f"Added [[{target}]]."]},
    }
    draft_path = world.drafts / "proj-brief.json"
    draft_path.write_text(json.dumps(draft), encoding="utf-8")
    result = world.vault_cli("proj", "publish-draft", str(draft_path), "--json")
    assert result.returncode == 0, result.stdout + result.stderr
    assert json.loads(result.stdout)["status"] == "published"


def seed_decisions(world: MemoryWorld, numbers: Iterable[int]) -> list[str]:
    """Decision pages dated after the old brief, one day apart, so each one counts."""
    return [
        world.seed_page(
            "proj", f"Brief decision {number}", updated=days_ago(40 - number), body=f"Decision {number} of the brief."
        )
        for number in numbers
    ]


def brief_candidates(world: MemoryWorld) -> list[dict[str, Any]]:
    listed = world.mcp("list_memory_candidates", cwd=str(world.project), kinds=["brief"])
    return [candidate for candidate in listed["candidates"] if candidate["kind"] == "brief"]


def l3_first_line(text: str) -> str:
    """The first line under the block L3 heading."""
    block = recall_blocks(text)[L3_BLOCK_TITLE]
    return block.splitlines()[1]


def run_recall_script(world: MemoryWorld) -> str:
    """Run the recall.sh that install put under the temporary config folder, from the project folder."""
    script = world.config_dir / "skills" / "project-memory" / "scripts" / "recall.sh"
    assert script.is_file(), script
    return _run([str(script)], env=world.env(), cwd=world.project).stdout
