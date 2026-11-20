"""Review state of one Vault review item: an accept counts only when the Vault published it (spec D7, F1, R2).

The Vault's accept publishes the draft and then writes ``resolution: "<reason> Published: <paths>."``. An item
whose ``status`` was set to ``accepted`` by hand has no such mark and nothing was published. The last test runs
the real Vault tool from the vault-builder checkout named by ``VAULT_BUILDER_ROOT`` and is skipped without it.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from vault_graph.interface.composition.adapters.vault_review_queue import (
    UNPUBLISHED_FIX,
    pending_proposals,
    review_item_state,
)

BUILDER_ENV = "VAULT_BUILDER_ROOT"
COMMAND_TIMEOUT_S = 300


def write_item(vault: Path, name: str, frontmatter: str) -> str:
    queue = vault / "scratch" / "review"
    queue.mkdir(parents=True, exist_ok=True)
    (queue / name).write_text(f"---\n{frontmatter}---\n\n# Review\n", encoding="utf-8")
    return f"scratch/review/{name}"


@pytest.mark.parametrize(
    ("frontmatter", "expected"),
    [
        ('type: memory-proposal\nstatus: pending\nresolution: ""\n', "pending"),
        ("type: memory-proposal\nstatus: rejected\nresolution: Not true.\n", "rejected"),
        ("type: contradiction\nstatus: resolved\nresolution: Both pages were merged.\n", "resolved"),
        # The line as the Vault renders it: quoted because the value holds a colon and a comma.
        (
            "type: memory-proposal\nstatus: accepted\n"
            'resolution: "The user said \\"yes\\". Published: wiki/decisions/a.md, wiki/index.md, wiki/log.md."\n',
            "accepted",
        ),
        ("type: memory-proposal\nstatus: accepted\nresolution: Published: wiki/decisions/a.md.\n", "accepted"),
        # Edited by hand: the status says accepted, but the Vault never published the draft.
        ('type: memory-proposal\nstatus: accepted\nresolution: ""\n', "unpublished"),
        ("type: memory-proposal\nstatus: accepted\n", "unpublished"),
        ("type: memory-proposal\nstatus: accepted\nresolution: The user confirmed it.\n", "unpublished"),
        ("type: memory-proposal\n", "missing"),
        ("type: memory-proposal\nstatus: done\n", "missing"),
    ],
)
def test_state_follows_the_status_and_the_published_mark(tmp_path: Path, frontmatter: str, expected: str) -> None:
    review_path = write_item(tmp_path, "item.md", frontmatter)

    assert review_item_state(tmp_path, review_path) == expected


def test_state_is_missing_for_a_gone_item_a_file_outside_the_queue_and_a_page_without_frontmatter(
    tmp_path: Path,
) -> None:
    write_item(tmp_path, "item.md", "type: memory-proposal\nstatus: pending\n")
    (tmp_path / "wiki").mkdir()
    (tmp_path / "wiki" / "page.md").write_text("---\nstatus: accepted\n---\n# Page\n", encoding="utf-8")
    (tmp_path / "scratch" / "review" / "plain.md").write_text("# No frontmatter\n", encoding="utf-8")

    assert review_item_state(tmp_path, "scratch/review/gone.md") == "missing"
    assert review_item_state(tmp_path, "wiki/page.md") == "missing"
    assert review_item_state(tmp_path, "scratch/review/../../wiki/page.md") == "missing"
    assert review_item_state(tmp_path, "scratch/review/plain.md") == "missing"


def test_reading_the_state_writes_nothing_and_the_pending_count_is_unchanged(tmp_path: Path) -> None:
    write_item(tmp_path, "a.md", "type: memory-proposal\nstatus: pending\n")
    by_hand = write_item(tmp_path, "b.md", "type: memory-proposal\nstatus: accepted\n")
    write_item(tmp_path, "c.md", "type: contradiction\nstatus: pending\n")
    before = {path.name: path.read_bytes() for path in (tmp_path / "scratch" / "review").iterdir()}

    assert review_item_state(tmp_path, by_hand) == "unpublished"
    assert pending_proposals(tmp_path) == 1
    assert {path.name: path.read_bytes() for path in (tmp_path / "scratch" / "review").iterdir()} == before


def test_the_fix_text_names_both_fields_and_the_command() -> None:
    assert "`status` to `pending`" in UNPUBLISHED_FIX
    assert "`resolution`" in UNPUBLISHED_FIX
    assert "`vg review`" in UNPUBLISHED_FIX


# The real Vault tool (R2) ---------------------------------------------------------------------


@pytest.fixture
def real_vault(tmp_path: Path) -> RealVault:
    value = os.environ.get(BUILDER_ENV)
    if not value:
        pytest.skip(f"set {BUILDER_ENV} to a vault-builder checkout to read an item the real Vault tool wrote")
    builder_root = Path(value).expanduser().resolve()
    if not (builder_root / "tools" / "vault_migration" / "cli.py").is_file():
        pytest.fail(f"{BUILDER_ENV}={value} has no tools/vault_migration/cli.py")
    return RealVault(tmp_path, builder_root)


class RealVault:
    """One Vault installed by vault-builder under a temporary HOME."""

    def __init__(self, tmp_path: Path, builder_root: Path) -> None:
        self.home = tmp_path / "home"
        self.root = self.home / "vaults" / "proj"
        self.drafts = tmp_path / "drafts"
        self.drafts.mkdir(parents=True)
        self.home.mkdir()
        self._run(
            [sys.executable, str(builder_root / "tools" / "vault_migration" / "cli.py")],
            "install",
            str(self.root),
            "--name",
            "proj",
            cwd=tmp_path,
        )

    def cli(self, *args: str) -> str:
        return self._run([sys.executable, "-B", str(self.root / "tools" / "wiki" / "cli.py")], *args, cwd=self.root)

    def propose(self, slug: str, title: str) -> str:
        draft = {
            "version": 1,
            "operation": "upsert-page",
            "path": f"wiki/decisions/{slug}.md",
            "frontmatter": {
                "title": title,
                "type": "decision",
                "status": "active",
                "created": "2026-11-20",
                "updated": "2026-11-20",
                "owner": "human",
                "summary": title,
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
            "body": f"# {title}\n\n{title}.\n\n## Evidence\n\n- Evidence: said in the test session.\n",
            "index": {"section": "Decisions", "target": f"decisions/{slug}", "summary": title},
            "log": {"event_type": "decision", "title": f"Add {title}", "items": [f"Added [[decisions/{slug}]]."]},
        }
        draft_path = self.drafts / f"{slug}.json"
        draft_path.write_text(json.dumps(draft), encoding="utf-8")
        output = self.cli(
            "review", "propose", "--draft", str(draft_path), "--summary", title, "--evidence", "Test session.", "--json"
        )
        result = json.loads(output)
        assert result["status"] == "proposed", output
        review_path: str = result["review_path"]
        return review_path

    def _run(self, command: list[str], *args: str, cwd: Path) -> str:
        environ = dict(os.environ)
        for key in ("CLAUDE_CONFIG_DIR", "VAULT_GRAPH_BIN", "PYTHONPATH"):
            environ.pop(key, None)
        environ.update(HOME=str(self.home), CLAUDE_CONFIG_DIR=str(self.home / ".claude"), PYTHONDONTWRITEBYTECODE="1")
        result = subprocess.run(
            [*command, *args],
            env=environ,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=COMMAND_TIMEOUT_S,
            check=False,
        )
        assert result.returncode == 0, f"{' '.join(args)}\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        return result.stdout


def test_an_item_the_real_vault_tool_accepted_reads_as_accepted_and_a_hand_edit_as_unpublished(
    real_vault: RealVault,
) -> None:
    accepted = real_vault.propose("quokkaflow-cache", "Quokkaflow builds are cached")
    by_hand = real_vault.propose("wombatline-tests", "Wombatline tests are flaky")
    rejected = real_vault.propose("numbat-deploys", "Numbat deploys run at night")
    for path in (accepted, by_hand, rejected):
        assert review_item_state(real_vault.root, path) == "pending"

    # The reason holds a colon, a comma and quotes, so the Vault writes the resolution line in quotes.
    reason = 'The user said: "yes, keep it", after a check.'
    real_vault.cli("review", "resolve", accepted, "--status", "accepted", "--resolution", reason, "--json")
    real_vault.cli("review", "resolve", rejected, "--status", "rejected", "--resolution", "Not true: it runs at noon.")
    item = real_vault.root / by_hand
    item.write_text(
        item.read_text(encoding="utf-8").replace("status: pending", "status: accepted", 1), encoding="utf-8"
    )

    assert (real_vault.root / "wiki" / "decisions" / "quokkaflow-cache.md").is_file()
    assert "Published:" in (real_vault.root / accepted).read_text(encoding="utf-8")
    assert review_item_state(real_vault.root, accepted) == "accepted"
    assert review_item_state(real_vault.root, by_hand) == "unpublished"
    assert review_item_state(real_vault.root, rejected) == "rejected"
