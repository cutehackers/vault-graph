"""End-to-end cleanup writes through the real Vault tools (spec 2026-11-05 §4.4.4, §4.4.5, §4.4.13, risk D12).

Acceptance A-24 (E2E part), A-38 (claim supersede) and A-39 (E2E part). Each test installs Vaults with
the vault-builder named by ``VAULT_BUILDER_ROOT`` into a temporary HOME (``MemoryWorld`` of
``test_long_term_memory_scenarios``) and drives the writes through a real ``vg serve --mcp`` over
stdio, so the MCP tool layer, the M18 write service, the Vault ``publish-draft`` and ``import-source``
and the Graph Home ``memory/reviewed.jsonl`` record all run for real. No fake port.

Without ``VAULT_BUILDER_ROOT`` the tests are skipped.
"""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Iterator
from datetime import date
from pathlib import Path
from typing import Any

import pytest

from tests.e2e.test_long_term_memory_scenarios import (
    BUILDER_ENV,
    PROJECT_ID,
    MemoryWorld,
    file_hashes,
    frontmatter_lines,
    recall_blocks,
)
from vault_graph.context.pack.recall import BLOCK_B_TITLE
from vault_graph.context.pack.recall_pins import PIN_BLOCK_TITLE
from vault_graph.interface.composition.adapters.auto_memory_reader import memory_folder_key

HUMAN_EVIDENCE = "Human instruction in the scenario session."
OLD_CLAIM = "Releases ship every Friday afternoon"
NEW_CLAIM = "Releases ship every Tuesday morning"
OTHER_CLAIMS = ("Release notes go to the quillfeather channel", "Hotfixes skip the release train")


@pytest.fixture(scope="session")
def builder_root() -> Path:
    value = os.environ.get(BUILDER_ENV)
    if not value:
        pytest.skip(f"set {BUILDER_ENV} to a vault-builder checkout to run the cleanup write scenarios")
    root = Path(value).expanduser().resolve()
    if not (root / "tools" / "wiki" / "lib" / "draft_patch.py").is_file():
        pytest.fail(f"{BUILDER_ENV}={value} has no tools/wiki/lib/draft_patch.py")
    return root


@pytest.fixture(scope="session")
def shared_cache(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return tmp_path_factory.mktemp("shared-home-cache")


@pytest.fixture
def world(tmp_path: Path, builder_root: Path, shared_cache: Path) -> Iterator[MemoryWorld]:
    yield MemoryWorld(tmp_path, builder_root=builder_root, shared_cache=shared_cache)


# A-24: import_auto_memory keeps a copy under raw/imports/claude-memory/ ---------------------------


def test_a24_import_auto_memory_copies_the_note_once_and_leaves_it_untouched(world: MemoryWorld) -> None:
    world.install("proj", role="project")
    world.builder("set-default-write", "--project", PROJECT_ID, "--vault", "proj")
    note = write_l1_note(world, "feedback_release_checklist.md", "Run the marmoset checklist before a release.\n")
    note_sha = hashlib.sha256(note.read_bytes()).hexdigest()
    note_mtime = note.stat().st_mtime_ns
    world.vg_setup()

    listed = world.mcp("list_memory_candidates", cwd=str(world.project), kinds=["l1_note"])
    l1 = [candidate for candidate in listed["candidates"] if candidate["kind"] == "l1_note"]
    assert [(candidate["key"], candidate["location"]) for candidate in l1] == [(f"l1:{note_sha}", str(note))]

    first = world.mcp("import_auto_memory", note=str(note), cwd=str(world.project), candidate_key=f"l1:{note_sha}")
    assert first["status"] == "published", first["messages"]
    assert first["vault"] == "proj"
    raw_path = first["raw_path"]
    assert raw_path.startswith("raw/imports/claude-memory/"), raw_path
    copy = world.vault_root("proj") / raw_path
    assert copy.read_bytes() == note.read_bytes()
    assert (world.vault_root("proj") / first["source_page"]).is_file()
    assert reviewed_keys(world) == [(f"l1:{note_sha}", "published")]

    vault_before = file_hashes(world.vault_root("proj"))
    again = world.mcp("import_auto_memory", note=str(note), cwd=str(world.project))
    assert again["status"] == "published", again["messages"]
    assert (again["raw_path"], again["source_page"]) == (raw_path, first["source_page"])
    assert again["written_paths"] == []
    assert file_hashes(world.vault_root("proj")) == vault_before

    assert hashlib.sha256(note.read_bytes()).hexdigest() == note_sha
    assert note.stat().st_mtime_ns == note_mtime

    world.vg_index()
    after = world.mcp("list_memory_candidates", cwd=str(world.project), kinds=["l1_note"])
    assert [candidate for candidate in after["candidates"] if candidate["kind"] == "l1_note"] == []


# A-38: supersede_claim replaces one claim row --------------------------------------------------------


def test_a38_supersede_claim_marks_the_old_row_and_recall_drops_its_sentence(world: MemoryWorld) -> None:
    world.install("proj", role="project")
    world.builder("set-default-write", "--project", PROJECT_ID, "--vault", "proj")
    path = seed_claim_page(world, "proj")
    page = world.vault_root("proj") / path
    world.vg_setup()
    assert OLD_CLAIM in recall_blocks(world.recall("a38-before"))[PIN_BLOCK_TITLE]
    before = page.read_text(encoding="utf-8")

    result = world.mcp(
        "supersede_claim",
        path=path,
        claim=OLD_CLAIM,
        new_claim=NEW_CLAIM,
        evidence=HUMAN_EVIDENCE,
        basis="stated",
        cwd=str(world.project),
        candidate_key="session:a38-exchange",
    )

    assert result["status"] == "published", result["messages"]
    assert reviewed_keys(world) == [("session:a38-exchange", "published")]
    after = page.read_text(encoding="utf-8")
    before_lines = page_body(before).split("\n")
    after_lines = page_body(after).split("\n")
    old_at = before_lines.index(f"| {OLD_CLAIM} | stated | {HUMAN_EVIDENCE} |")
    assert (
        after_lines[old_at]
        == f"| {OLD_CLAIM} | superseded | {HUMAN_EVIDENCE.rstrip('.')}; Superseded by: {NEW_CLAIM} |"
    )
    assert after_lines[old_at + 1] == f"| {NEW_CLAIM} | stated | {HUMAN_EVIDENCE} |"
    # Every other body line, the other claim rows included, keeps its bytes.
    assert after_lines[:old_at] + after_lines[old_at + 2 :] == before_lines[:old_at] + before_lines[old_at + 1 :]
    for claim in OTHER_CLAIMS:
        assert f"| {claim} | stated | {HUMAN_EVIDENCE} |" in after_lines
    changed = set(frontmatter_lines_of(after)) ^ set(frontmatter_lines_of(before))
    assert {line.split(":", 1)[0] for line in changed} <= {"updated"}, changed

    world.vg_index()
    pinned = recall_blocks(world.recall("a38-after"))[PIN_BLOCK_TITLE]
    assert OLD_CLAIM not in pinned
    assert NEW_CLAIM in pinned


def test_a38_supersede_claim_on_a_page_without_claim_table_is_rejected(world: MemoryWorld) -> None:
    world.install("proj", role="project")
    path = world.seed_page("proj", "Plain section page", updated="2026-09-01", body="No claim table here.")
    world.vg_setup()
    before = (world.vault_root("proj") / path).read_bytes()

    result = world.mcp(
        "supersede_claim",
        path=path,
        claim="No claim table here.",
        new_claim="Still no claim table.",
        evidence=HUMAN_EVIDENCE,
        basis="stated",
        cwd=str(world.project),
        vault="proj",
        candidate_key="session:a38-rejected",
    )

    assert result["status"] == "rejected", result
    assert any("retire_memory" in message for message in result["messages"]), result["messages"]
    assert (world.vault_root("proj") / path).read_bytes() == before
    assert reviewed_keys(world) == []


# A-39 and risk D12: restore_memory changes only the frontmatter --------------------------------------


def test_a39_restore_memory_brings_a_retired_page_back_to_recall_and_search(world: MemoryWorld) -> None:
    world.install("proj", role="project")
    world.builder("set-default-write", "--project", PROJECT_ID, "--vault", "proj")
    today = date.today().isoformat()
    retired_path = world.seed_page(
        "proj", "Use the pangolin cache", updated="2026-09-01", body="Builds read the pangolin cache first."
    )
    replaced_path = world.seed_page(
        "proj", "Use the ocelot mirror", updated="2026-09-02", body="Downloads go through the ocelot mirror."
    )
    world.seed_page("proj", "Use the heron mirror", updated="2026-09-03", body="Downloads go through the heron mirror.")
    world.vg_setup()
    cwd = str(world.project)

    retired = world.mcp("retire_memory", path=retired_path, reason="The cache was removed", basis="stated", cwd=cwd)
    replaced = world.mcp(
        "retire_memory",
        path=replaced_path,
        reason="Moved to the heron mirror",
        basis="stated",
        cwd=cwd,
        replaced_by="wiki/decisions/use-the-heron-mirror.md",
    )
    assert retired["status"] == replaced["status"] == "published", (retired["messages"], replaced["messages"])
    world.vg_index()
    assert retired_path not in world.search_paths("pangolin cache", cwd=world.project)
    listed_before = recall_blocks(world.recall("a39-before"))[BLOCK_B_TITLE]
    assert retired_path not in listed_before and replaced_path not in listed_before, listed_before
    pages = {
        path: (world.vault_root("proj") / path).read_text(encoding="utf-8") for path in (retired_path, replaced_path)
    }

    for path, key in ((retired_path, "retire:a39-retired"), (replaced_path, "retire:a39-replaced")):
        restored = world.mcp(
            "restore_memory", path=path, reason="The user needs it again", basis="stated", cwd=cwd, candidate_key=key
        )
        # Risk D12: the Vault lint must accept an active page that keeps its retire history.
        assert restored["status"] == "published", restored["messages"]
        after = (world.vault_root("proj") / path).read_text(encoding="utf-8")
        assert page_body(after) == page_body(pages[path])
        old_lines = frontmatter_lines_of(pages[path])
        new_lines = frontmatter_lines_of(after)
        assert "status: active" in new_lines
        assert f'restored_at: "{today}"' in new_lines
        assert "restored_reason: The user needs it again" in new_lines
        added = [line for line in new_lines if line not in old_lines]
        removed = [line for line in old_lines if line not in new_lines]
        # ``updated`` already holds today from the retire patch, so it may stay the same line.
        added_fields = {line.split(":", 1)[0] for line in added}
        assert (
            {"status", "restored_at", "restored_reason"}
            <= added_fields
            <= {
                "status",
                "updated",
                "restored_at",
                "restored_reason",
            }
        )
        assert {line.split(":", 1)[0] for line in removed} <= {"status", "updated"}

    retired_lines = frontmatter_lines(world.vault_root("proj") / retired_path)
    assert "retired_reason: The cache was removed" in retired_lines
    replaced_lines = frontmatter_lines(world.vault_root("proj") / replaced_path)
    assert "  - decisions/use-the-heron-mirror" in replaced_lines
    assert reviewed_keys(world) == [("retire:a39-retired", "published"), ("retire:a39-replaced", "published")]

    world.vg_index()
    block_b = recall_blocks(world.recall("a39-after"))[BLOCK_B_TITLE]
    assert "active · Use the pangolin cache" in block_b and retired_path in block_b, block_b
    assert "active · Use the ocelot mirror" in block_b and replaced_path in block_b, block_b
    assert retired_path in world.search_paths("pangolin cache", cwd=world.project)
    assert replaced_path in world.search_paths("ocelot mirror", cwd=world.project)

    before = (world.vault_root("proj") / retired_path).read_bytes()
    refused = world.mcp("restore_memory", path=retired_path, reason="Again", basis="stated", cwd=cwd)
    assert refused["status"] == "rejected", refused
    assert (world.vault_root("proj") / retired_path).read_bytes() == before


# Helpers --------------------------------------------------------------------------------------------


def write_l1_note(world: MemoryWorld, name: str, text: str) -> Path:
    """Write one note into the project's default Claude Code auto-memory folder under the temporary HOME."""
    root = world.vault_map()["projects"][PROJECT_ID]["root"]
    folder = world.config_dir / "projects" / memory_folder_key(root) / "memory"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "MEMORY.md").write_text(f"- [{name}]({name})\n", encoding="utf-8")
    note = folder / name
    note.write_text(f"---\nname: {name}\ntype: feedback\n---\n\n{text}", encoding="utf-8")
    return note


def seed_claim_page(world: MemoryWorld, vault: str) -> str:
    """Publish a pinned decision page with ``quality.provenance: claim`` and a three-row claim table."""
    slug = "release-cadence"
    rows = "".join(f"| {claim} | stated | {HUMAN_EVIDENCE} |\n" for claim in (OLD_CLAIM, *OTHER_CLAIMS))
    body = (
        "# Release cadence\n\n"
        "The team agreed on how releases ship.\n\n"
        "## Claims\n\n"
        "| Claim | Status | Evidence |\n"
        "|---|---|---|\n"
        f"{rows}\n"
        "## Notes\n\n"
        "The cadence is reviewed every quarter.\n"
    )
    draft = {
        "version": 1,
        "operation": "upsert-page",
        "path": f"wiki/decisions/{slug}.md",
        "frontmatter": {
            "title": "Release cadence",
            "type": "decision",
            "status": "active",
            "created": "2026-09-01",
            "updated": "2026-09-01",
            "owner": "human",
            "summary": "Release cadence",
            "source_count": 1,
            "tags": [],
            "related": [],
            "confidence": "high",
            "quality": {
                "provenance": "claim",
                "links": "unchecked",
                "contradictions": "unchecked",
                "review_required": False,
            },
            "memory_schema": "vault-memory/v1",
            "pin": True,
            "memory_kind": "rule",
        },
        "body": body,
        "index": {"section": "Decisions", "target": f"decisions/{slug}", "summary": "Release cadence"},
        "log": {"event_type": "decision", "title": "Seed Release cadence", "items": [f"Added [[decisions/{slug}]]."]},
    }
    draft_path = world.drafts / f"{vault}-{slug}.json"
    draft_path.write_text(json.dumps(draft), encoding="utf-8")
    result = world.vault_cli(vault, "publish-draft", str(draft_path), "--json")
    assert result.returncode == 0, result.stdout + result.stderr
    assert json.loads(result.stdout)["status"] == "published"
    return f"wiki/decisions/{slug}.md"


def page_body(text: str) -> str:
    """The page text after the closing frontmatter line."""
    assert text.startswith("---\n")
    return text[text.index("\n---\n", 4) + len("\n---\n") :]


def frontmatter_lines_of(text: str) -> list[str]:
    return text[4 : text.index("\n---\n", 4)].splitlines()


def reviewed_keys(world: MemoryWorld) -> list[tuple[str, str]]:
    log = world.graph_home / "memory" / "reviewed.jsonl"
    if not log.is_file():
        return []
    records: list[dict[str, Any]] = [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]
    return [(record["candidate_key"], record["outcome"]) for record in records]
