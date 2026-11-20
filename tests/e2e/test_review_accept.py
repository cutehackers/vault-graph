"""End-to-end `vg review accept` and `vg review reject` through the real Vault tools (spec 2026-11-20 A9).

The test installs Vaults with the vault-builder named by ``VAULT_BUILDER_ROOT`` into a temporary HOME
(``MemoryWorld`` of ``test_long_term_memory_scenarios``). Three inferred memories are proposed through a real
``vg serve --mcp``. A real ``vg review`` process then accepts one and rejects one, so the Vault's own
``review resolve`` runs for both, and the index that the accept starts is a real detached ``vg index``. The test
edits the ``status`` of the third item by hand, the way a person did on 2026-11-19. No fake port.

Without ``VAULT_BUILDER_ROOT`` the test is skipped.
"""

from __future__ import annotations

import fcntl
import os
import subprocess
import time
from collections.abc import Iterator
from pathlib import Path

import pytest

from tests.e2e.test_long_term_memory_scenarios import (
    BUILDER_ENV,
    COMMAND_TIMEOUT_S,
    MemoryWorld,
    file_hashes,
    frontmatter_lines,
)
from vault_graph.interface.cli.hook_commands import CATCH_UP_LOCK
from vault_graph.interface.composition.adapters.vault_review_queue import (
    PUBLISHED_MARK,
    UNPUBLISHED_FIX,
    review_item_state,
)

VAULT = "proj"
INFERENCE = "Agent inference from the scenario session."
INDEX_WAIT_S = 300


@pytest.fixture(scope="session")
def builder_root() -> Path:
    value = os.environ.get(BUILDER_ENV)
    if not value:
        pytest.skip(f"set {BUILDER_ENV} to a vault-builder checkout to run the vg review scenario")
    root = Path(value).expanduser().resolve()
    if not (root / "tools" / "wiki" / "lib" / "memory_proposal.py").is_file():
        pytest.fail(f"{BUILDER_ENV}={value} has no tools/wiki/lib/memory_proposal.py")
    return root


@pytest.fixture(scope="session")
def shared_cache(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return tmp_path_factory.mktemp("shared-home-cache")


@pytest.fixture
def world(tmp_path: Path, builder_root: Path, shared_cache: Path) -> Iterator[MemoryWorld]:
    yield MemoryWorld(tmp_path, builder_root=builder_root, shared_cache=shared_cache)


def test_a9_vg_review_accepts_and_rejects_through_the_real_vault_tools(world: MemoryWorld) -> None:
    world.install(VAULT, role="project")
    world.install("team", role="team")
    world.vg_setup()
    vault_root = world.vault_root(VAULT)
    wiki = vault_root / "wiki"

    accept_item = propose(world, "Quokkaflow builds are cached", "Quokkaflow builds reuse the shared cache.")
    reject_item = propose(world, "Wombatline tests are flaky", "Wombatline tests fail at random.")
    hand_item = propose(world, "Numbatgrid deploys are manual", "Numbatgrid deploys are started by hand.")
    accept_target = "wiki/decisions/quokkaflow-builds-are-cached.md"
    reject_target = "wiki/decisions/wombatline-tests-are-flaky.md"
    hand_target = "wiki/decisions/numbatgrid-deploys-are-manual.md"
    for item in (accept_item, reject_item, hand_item):
        assert review_item_state(vault_root, item) == "pending"
    for target in (accept_target, reject_target, hand_target):
        assert not (vault_root / target).exists()

    world.vg_index()
    assert accept_target not in world.search_paths("quokkaflow builds cached", cwd=world.project)
    listed = review(world, "list")
    assert listed.returncode == 0, listed.stdout + listed.stderr
    for item in (accept_item, reject_item, hand_item):
        assert f"[{VAULT}] {Path(item).stem}" in listed.stdout

    # Accept: the Vault publishes the page and the item says so.
    accepted = review(world, "accept", Path(accept_item).stem, "--reason", "The user confirmed it.")
    assert accepted.returncode == 0, accepted.stdout + accepted.stderr
    assert f"accepted: [{VAULT}] {Path(accept_item).stem} {accept_target}" in accepted.stdout
    assert "published: " in accepted.stdout and accept_target in accepted.stdout
    assert "index: started in the background" in accepted.stdout, accepted.stdout
    assert (vault_root / accept_target).is_file()
    assert PUBLISHED_MARK in resolution_of(vault_root / accept_item)
    assert review_item_state(vault_root, accept_item) == "accepted"

    # The accept started the index itself. Nothing here runs `vg index`.
    wait_for_background_index(world.graph_home)
    assert accept_target in world.search_paths("quokkaflow builds cached", cwd=world.project)

    # Reject: no wiki page is created or changed. wiki/log.md gains the Vault's audit entry.
    wiki_before_reject = file_hashes(wiki)
    rejected = review(world, "reject", Path(reject_item).stem, "--reason", "Not true.")
    assert rejected.returncode == 0, rejected.stdout + rejected.stderr
    assert f"rejected: [{VAULT}] {Path(reject_item).stem}" in rejected.stdout
    assert "published: " not in rejected.stdout
    assert "index: " not in rejected.stdout
    assert not (vault_root / reject_target).exists()
    assert review_item_state(vault_root, reject_item) == "rejected"
    assert "Not true." in resolution_of(vault_root / reject_item)
    wiki_after_reject = file_hashes(wiki)
    assert without_log(wiki_after_reject) == without_log(wiki_before_reject)
    assert wiki_after_reject["log.md"] != wiki_before_reject["log.md"]

    # A status set by hand publishes nothing, so it is unpublished and vg review does not send it to the Vault.
    hand_file = vault_root / hand_item
    hand_text = hand_file.read_text(encoding="utf-8")
    assert hand_text.count("\nstatus: pending\n") == 1, hand_text
    hand_file.write_text(hand_text.replace("\nstatus: pending\n", "\nstatus: accepted\n"), encoding="utf-8")
    assert review_item_state(vault_root, hand_item) == "unpublished"
    assert not (vault_root / hand_target).exists()
    vault_before_refusal = file_hashes(vault_root)
    listed_after = review(world, "list")
    assert listed_after.returncode == 0, listed_after.stdout + listed_after.stderr
    assert "unpublished accepts: 1" in listed_after.stdout
    assert f"unpublished: [{VAULT}] {Path(hand_item).stem}" in listed_after.stdout
    refused = review(world, "accept", Path(hand_item).stem)
    assert refused.returncode == 1, refused.stdout + refused.stderr
    assert UNPUBLISHED_FIX in refused.stdout
    assert file_hashes(vault_root) == vault_before_refusal
    assert review_item_state(vault_root, hand_item) == "unpublished"


# Helpers --------------------------------------------------------------------------------------


def propose(world: MemoryWorld, title: str, body: str) -> str:
    """Put one inferred memory in the review queue through ``remember`` and return its Vault review path."""
    proposed = world.mcp(
        "remember",
        title=title,
        kind="decision",
        body=f"The agent inferred this: {body}",
        evidence=[INFERENCE],
        basis="inferred",
        cwd=str(world.project),
        vault=VAULT,
    )
    assert proposed["status"] == "proposed", proposed["messages"]
    review_path = str(proposed["review_path"])
    assert review_path.startswith("scratch/review/")
    assert (world.vault_root(VAULT) / review_path).is_file()
    return review_path


def review(world: MemoryWorld, *args: str) -> subprocess.CompletedProcess[str]:
    """Run a real ``vg review`` in the project folder. Standard input is not a terminal, as in a script."""
    return subprocess.run(
        [str(world.vg_bin), "review", *args, "--graph-home", str(world.graph_home)],
        env=world.env(),
        cwd=world.project,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=COMMAND_TIMEOUT_S,
        check=False,
    )


def resolution_of(item: Path) -> str:
    lines = [line for line in frontmatter_lines(item) if line.startswith("resolution:")]
    assert len(lines) == 1, lines
    return lines[0]


def without_log(hashes: dict[str, str]) -> dict[str, str]:
    return {path: digest for path, digest in hashes.items() if path != "log.md"}


def wait_for_background_index(graph_home: Path) -> None:
    """Wait until the detached index process ends. It holds a flock on the catch-up lock file for as long as it runs."""
    lock_path = graph_home / CATCH_UP_LOCK
    assert lock_path.is_file(), f"{lock_path} is missing, so no background index was started"
    deadline = time.monotonic() + INDEX_WAIT_S
    descriptor = os.open(lock_path, os.O_RDWR)
    try:
        while True:
            try:
                fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                assert time.monotonic() < deadline, f"the background index still runs after {INDEX_WAIT_S}s"
                time.sleep(0.5)
                continue
            fcntl.flock(descriptor, fcntl.LOCK_UN)
            return
    finally:
        os.close(descriptor)
