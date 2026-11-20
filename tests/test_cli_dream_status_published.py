"""`vg dream status` counts an accept only when the Vault published it (spec 2026-11-20 D7, I3, F1, A6).

Three dream proposals are on record: one the Vault accepted and published, one whose ``status`` a person set to
``accepted`` by hand, and one rejected. The Vault here is a plain folder under ``tmp_path``.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from vault_graph.interface.cli.main import app
from vault_graph.interface.composition.adapters.vault_review_queue import UNPUBLISHED_FIX

runner = CliRunner()

PUBLISHED = 'resolution: "The user confirmed it. Published: wiki/decisions/a.md, wiki/index.md, wiki/log.md."\n'


@pytest.fixture
def world(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Path]:
    vault = tmp_path / "vaults" / "proj-vault"
    (vault / "wiki").mkdir(parents=True)
    (vault / "wiki" / "page.md").write_text("# Page\n", encoding="utf-8")
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    graph_home = home / ".vault-graph"
    init = runner.invoke(app, ["init", "--vault", str(vault), "--graph-home", str(graph_home)])
    assert init.exit_code == 0, init.output
    return {"vault": vault, "graph_home": graph_home}


def item(vault: Path, name: str, status: str, resolution: str = 'resolution: ""\n') -> str:
    queue = vault / "scratch" / "review"
    queue.mkdir(parents=True, exist_ok=True)
    (queue / name).write_text(
        f"---\ntype: memory-proposal\nstatus: {status}\n{resolution}---\n# item\n", encoding="utf-8"
    )
    return f"scratch/review/{name}"


def record_proposals(world: dict[str, Path], review_paths: list[str]) -> None:
    logs = world["graph_home"] / "logs"
    logs.mkdir(exist_ok=True)
    lines: list[dict[str, object]] = [
        {
            "record": "proposal",
            "project": "project",
            "candidate_key": f"session:s{index}",
            "vault": "proj-vault",
            "vault_root": str(world["vault"]),
            "review_path": path,
        }
        for index, path in enumerate(review_paths)
    ]
    lines.append(
        {
            "record": "run",
            "at": "2026-11-20T01:00:00Z",
            "project": "project",
            "vault": "proj-vault",
            "vault_root": str(world["vault"]),
            "status": "ran",
            "reason": None,
            "judged": 9,
            "proposals": len(review_paths),
        }
    )
    (logs / "dream-runs.jsonl").write_text("".join(json.dumps(line) + "\n" for line in lines), encoding="utf-8")


def status(world: dict[str, Path]) -> str:
    result = runner.invoke(app, ["dream", "status", "--graph-home", str(world["graph_home"])])
    assert result.exit_code == 0, result.output
    return result.output


def test_a_hand_edited_accept_is_left_out_of_the_accepted_count_and_the_rate(world: dict[str, Path]) -> None:
    vault = world["vault"]
    published = item(vault, "a.md", "accepted", PUBLISHED)
    by_hand = item(vault, "b.md", "accepted")
    rejected = item(vault, "c.md", "rejected", "resolution: Not true.\n")
    record_proposals(world, [published, by_hand, rejected])
    before = {path.name: path.read_bytes() for path in (vault / "scratch" / "review").iterdir()}

    output = status(world)

    assert "proposals: sent=3 accepted=1 rejected=1 pending=0 unpublished=1 other=0" in output
    assert "acceptance_rate: 0.50 of 2 resolved" in output
    unpublished = [line for line in output.splitlines() if line.startswith("unpublished:")]
    assert len(unpublished) == 1
    assert "proj-vault" in unpublished[0]
    assert by_hand in unpublished[0]
    assert UNPUBLISHED_FIX in unpublished[0]
    assert published not in "".join(unpublished)
    # Status only reads: putting the item back to pending is the person's work (I1).
    assert {path.name: path.read_bytes() for path in (vault / "scratch" / "review").iterdir()} == before


def test_every_state_is_counted_and_each_unpublished_item_gets_one_line(world: dict[str, Path]) -> None:
    vault = world["vault"]
    paths = [
        item(vault, "a.md", "accepted", PUBLISHED),
        item(vault, "b.md", "accepted"),
        item(vault, "c.md", "accepted", "resolution: Looks right.\n"),
        item(vault, "d.md", "rejected"),
        item(vault, "e.md", "pending"),
        item(vault, "f.md", "resolved"),
        "scratch/review/gone.md",
    ]
    record_proposals(world, paths)

    output = status(world)

    assert "proposals: sent=7 accepted=1 rejected=1 pending=1 unpublished=2 other=2" in output
    assert "acceptance_rate: 0.50 of 2 resolved" in output
    unpublished = [line for line in output.splitlines() if line.startswith("unpublished:")]
    assert len(unpublished) == 2
    assert "scratch/review/b.md" in unpublished[0]
    assert "scratch/review/c.md" in unpublished[1]


def test_no_rate_is_shown_when_only_hand_edited_accepts_exist(world: dict[str, Path]) -> None:
    record_proposals(world, [item(world["vault"], "a.md", "accepted")])

    output = status(world)

    assert "proposals: sent=1 accepted=0 rejected=0 pending=0 unpublished=1 other=0" in output
    assert "acceptance_rate" not in output


def test_the_pending_cap_stop_points_to_vg_review(world: dict[str, Path]) -> None:
    for index in range(10):
        item(world["vault"], f"waiting-{index}.md", "pending")
    record_proposals(world, [])

    output = status(world)

    assert "stopped: pending cap reached in proj-vault (10 waiting, cap 10)" in output
    stopped = next(line for line in output.splitlines() if line.startswith("stopped:"))
    assert "`vg review`" in stopped
    assert "review resolve" not in stopped
