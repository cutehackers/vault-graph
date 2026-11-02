"""End-to-end scenarios ①-⑥ of the long-term memory spec (2026-11-02 §8.1, A-1 to A-6).

Every test builds its own Vaults with the vault-builder named by ``VAULT_BUILDER_ROOT``:
``tools/vault_migration/cli.py install`` into a temporary HOME, then ``link``, ``set-role`` and
``set-default-write``. The tests use only that temporary ``vault-map.json`` and a temporary Graph
Home, and call the real programs as subprocesses: ``vg``, ``vg serve --mcp`` through the MCP stdio
client, the Vault ``tools/wiki/cli.py`` and the hook launcher ``vault_hooks.py``. No fake port.

Without ``VAULT_BUILDER_ROOT`` the tests are skipped. A-1 to A-6 are proven only by a run with it set
(spec risk 11).

The embedding model cache under ``$HOME/.cache`` is shared by every test of one pytest session, so
the model is downloaded at most once per session.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
from collections.abc import Iterator, Mapping, Sequence
from datetime import date
from pathlib import Path
from typing import Any

import pytest

from vault_graph.context.pack.recall import BLOCK_B_TITLE, BLOCK_C_TITLE, estimate_recall_tokens
from vault_graph.context.pack.recall_pins import PIN_BLOCK_TITLE

BUILDER_ENV = "VAULT_BUILDER_ROOT"
PROJECT_ID = "demo"
COMMAND_TIMEOUT_S = 600
LAUNCHER_ASSET = Path("tools/vault_migration/assets/vault-hooks/vault_hooks.py")


@pytest.fixture(scope="session")
def builder_root() -> Path:
    value = os.environ.get(BUILDER_ENV)
    if not value:
        pytest.skip(f"set {BUILDER_ENV} to a vault-builder checkout to run the A-1 to A-6 scenarios")
    root = Path(value).expanduser().resolve()
    if not (root / "tools" / "vault_migration" / "cli.py").is_file():
        pytest.fail(f"{BUILDER_ENV}={value} has no tools/vault_migration/cli.py")
    return root


@pytest.fixture(scope="session")
def shared_cache(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return tmp_path_factory.mktemp("shared-home-cache")


@pytest.fixture
def world(tmp_path: Path, builder_root: Path, shared_cache: Path) -> Iterator[MemoryWorld]:
    yield MemoryWorld(tmp_path, builder_root=builder_root, shared_cache=shared_cache)


# Scenario ① -----------------------------------------------------------------------------------


def test_a1_pinned_memory_comes_first_in_session_start_recall(world: MemoryWorld) -> None:
    world.install("proj", role="project")
    world.install("team", role="team")
    pin = world.seed_page(
        "team",
        "Never push to main without review",
        updated="2026-03-01",
        pin=True,
        memory_kind="rule",
        body="Every change to main goes through a reviewed pull request.",
    )
    newer = [
        world.seed_page("proj", f"Release note {number}", updated=f"2026-10-0{number}", body=f"Release {number} notes.")
        for number in range(1, 6)
    ]
    world.vg_setup()

    text = world.recall("a1-session")

    blocks = recall_blocks(text)
    assert text.startswith(PIN_BLOCK_TITLE + "\n")
    assert list(blocks)[0] == PIN_BLOCK_TITLE
    assert "Never push to main without review" in blocks[PIN_BLOCK_TITLE]
    assert f"team:{pin}" in blocks[PIN_BLOCK_TITLE]
    assert "Never push to main without review" not in blocks[BLOCK_B_TITLE]
    assert pin not in blocks[BLOCK_B_TITLE]
    # The project pages are newer than the pinned page and still come after it.
    assert f"proj:{newer[-1]}" in blocks[BLOCK_B_TITLE]
    assert estimate_recall_tokens(text) <= 1500
    assert len(text) <= 9000
    assert estimate_recall_tokens(blocks[PIN_BLOCK_TITLE]) <= 400


# Scenario ② -----------------------------------------------------------------------------------


def test_a2_stated_memory_is_added_updated_and_retired_through_vault_tools(world: MemoryWorld) -> None:
    world.install("proj", role="project")
    world.install("team", role="team")
    world.builder("set-default-write", "--project", PROJECT_ID, "--vault", "proj")
    locked = world.seed_page(
        "proj",
        "Signed release keys",
        updated="2026-06-10",
        body="<!-- human-locked -->\nOnly the release manager rotates the signing keys.",
    )
    world.vg_setup()
    today = date.today().isoformat()

    added = world.mcp(
        "remember",
        title="Run the checklist before every release",
        kind="decision",
        body="Every release runs the zephyrine checklist first.",
        evidence=["User statement in the scenario session."],
        basis="stated",
        cwd=str(world.project),
        pin=True,
        memory_kind="rule",
    )
    assert added["status"] == "published", added["messages"]
    assert added["vault"] == "proj" and added["vault_role"] == "project"
    path = added["written_paths"][0]
    page = world.vault_root("proj") / path
    assert {"memory_schema: vault-memory/v1", "pin: true", "memory_kind: rule"} <= set(frontmatter_lines(page))

    updated = world.mcp(
        "update_memory",
        path=path,
        body="Every release runs the zephyrine checklist and the smoke test first.",
        evidence=["User correction in the scenario session."],
        basis="stated",
        cwd=str(world.project),
    )
    assert updated["status"] == "published", updated["messages"]
    assert "Every release runs the zephyrine checklist and the smoke test first." in page.read_text(encoding="utf-8")
    assert f'updated: "{today}"' in frontmatter_lines(page)

    world.vg_index()
    before_retire = world.recall("a2-before-retire")
    assert "Run the checklist before every release" in recall_blocks(before_retire)[PIN_BLOCK_TITLE]
    assert path in world.search_paths("zephyrine checklist", cwd=world.project)

    reason = "The release pipeline now runs the checklist"
    retired = world.mcp("retire_memory", path=path, reason=reason, basis="stated", cwd=str(world.project))
    assert retired["status"] == "published", retired["messages"]
    assert page.is_file()
    lines = frontmatter_lines(page)
    assert "status: retired" in lines
    assert f"retired_reason: {reason}" in lines
    assert f'retired_at: "{today}"' in lines

    world.vg_index()
    after_retire = world.recall("a2-after-retire")
    blocks = recall_blocks(after_retire)
    assert path not in blocks.get(PIN_BLOCK_TITLE, "") + blocks.get(BLOCK_B_TITLE, "")
    assert "Run the checklist before every release" not in blocks.get(PIN_BLOCK_TITLE, "")
    assert "Run the checklist before every release" not in blocks.get(BLOCK_B_TITLE, "")
    assert blocks[BLOCK_C_TITLE].count(f"폐기됨: {reason}") == 1
    assert path not in world.search_paths("zephyrine checklist", cwd=world.project)
    assert "폐기됨" not in world.recall("a2-next-session")

    old = world.mcp(
        "remember",
        title="Deploy on Fridays",
        kind="decision",
        body="Deploys happen on Friday afternoons.",
        evidence=["User statement in the scenario session."],
        basis="stated",
        cwd=str(world.project),
    )
    new = world.mcp(
        "remember",
        title="Deploy on Tuesdays",
        kind="decision",
        body="Deploys happen on Tuesday mornings.",
        evidence=["User statement in the scenario session."],
        basis="stated",
        cwd=str(world.project),
    )
    assert old["status"] == new["status"] == "published", (old["messages"], new["messages"])
    replaced = world.mcp(
        "retire_memory",
        path=old["written_paths"][0],
        reason="Moved to Tuesdays",
        basis="stated",
        cwd=str(world.project),
        replaced_by=new["written_paths"][0],
    )
    assert replaced["status"] == "published", replaced["messages"]
    old_lines = frontmatter_lines(world.vault_root("proj") / old["written_paths"][0])
    assert "status: deprecated" in old_lines
    assert "superseded_by:" in old_lines
    assert "  - decisions/deploy-on-tuesdays" in old_lines

    locked_before = (world.vault_root("proj") / locked).read_bytes()
    refused = world.mcp(
        "update_memory",
        path=locked,
        body="Anyone may rotate the signing keys.",
        evidence=["Agent attempt in the scenario session."],
        basis="stated",
        cwd=str(world.project),
    )
    assert refused["status"] == "rejected"
    assert any("human-locked" in message for message in refused["messages"]), refused["messages"]
    assert (world.vault_root("proj") / locked).read_bytes() == locked_before


NAVIGATION_TYPES = ("index", "log", "map", "overview")


def test_a2_stated_memory_shows_in_the_next_session_without_vg_index(world: MemoryWorld) -> None:
    """F1 and F3: the next session start indexes the new page itself and lists memories, not navigation pages."""
    world.install("proj", role="project")
    world.install("team", role="team")
    world.builder("set-default-write", "--project", PROJECT_ID, "--vault", "proj")
    world.vg_setup()
    world.recall("f1-before")

    added = world.mcp(
        "remember",
        title="Tag every release with a signed tag",
        kind="decision",
        body="Every release gets a signed narwhalite tag.",
        evidence=["User statement in the scenario session."],
        basis="stated",
        cwd=str(world.project),
    )
    assert added["status"] == "published", added["messages"]
    path = added["written_paths"][0]

    started = time.monotonic()
    result = world.recall_result("f1-next-session")
    elapsed = time.monotonic() - started

    assert result.returncode == 0, result.stderr
    assert "warning" not in result.stderr, result.stderr
    assert elapsed < 20, elapsed
    block_b = recall_blocks(result.stdout)[BLOCK_B_TITLE]
    assert f"proj:{path}" in block_b
    assert "Tag every release with a signed tag" in block_b
    listed = [line for line in block_b.splitlines() if line.startswith("- [m:")]
    assert listed
    for line in listed:
        assert line.split("] ", 1)[1].split(" · ", 1)[0] not in NAVIGATION_TYPES, line
    for navigation in ("wiki/index.md", "wiki/log.md", "wiki/maps/", "wiki/overview.md"):
        assert navigation not in block_b, block_b
    assert path in world.search_paths("narwhalite tag", cwd=world.project)


# Scenario ③ -----------------------------------------------------------------------------------


def test_a3_inferred_memory_waits_for_review_then_is_published_on_accept(world: MemoryWorld) -> None:
    world.install("proj", role="project")
    world.install("team", role="team")
    world.vg_setup()
    wiki = world.vault_root("proj") / "wiki"
    wiki_before = file_hashes(wiki)

    proposed = world.mcp(
        "remember",
        title="Quokkaflow builds are cached",
        kind="decision",
        body="The agent inferred that quokkaflow builds reuse the shared cache.",
        evidence=["Agent inference from the scenario session."],
        basis="inferred",
        cwd=str(world.project),
        vault="proj",
    )
    assert proposed["status"] == "proposed", proposed["messages"]
    review_path = proposed["review_path"]
    assert review_path.startswith("scratch/review/")
    assert (world.vault_root("proj") / review_path).is_file()
    assert file_hashes(wiki) == wiki_before

    world.vg_index()
    target = "wiki/decisions/quokkaflow-builds-are-cached.md"
    assert target not in world.search_paths("quokkaflow builds cached", cwd=world.project)
    found = world.search("quokkaflow builds cached", cwd=world.project)["results"]
    assert "quokkaflow" not in json.dumps(found).casefold()
    assert "Quokkaflow" not in world.recall("a3-before-accept")

    accepted = world.vault_cli(
        "proj", "review", "resolve", review_path, "--status", "accepted", "--resolution", "The user confirmed it."
    )
    assert accepted.returncode == 0, accepted.stderr + accepted.stdout
    assert (world.vault_root("proj") / target).is_file()
    world.vg_index()
    assert target in world.search_paths("quokkaflow builds cached", cwd=world.project)

    second = world.mcp(
        "remember",
        title="Wombatline tests are flaky",
        kind="decision",
        body="The agent inferred that wombatline tests fail at random.",
        evidence=["Agent inference from the scenario session."],
        basis="inferred",
        cwd=str(world.project),
        vault="proj",
    )
    assert second["status"] == "proposed", second["messages"]
    wiki_before_reject = file_hashes(wiki)
    log_before_reject = (wiki / "log.md").read_text(encoding="utf-8")
    rejected = world.vault_cli(
        "proj", "review", "resolve", second["review_path"], "--status", "rejected", "--resolution", "Not true."
    )
    assert rejected.returncode == 0, rejected.stderr + rejected.stdout
    # spec A-3 and section 6: no wiki page is created or changed. wiki/log.md gains one audit entry.
    assert not (world.vault_root("proj") / "wiki/decisions/wombatline-tests-are-flaky.md").exists()
    wiki_after_reject = file_hashes(wiki)
    assert {key: value for key, value in wiki_after_reject.items() if key != "log.md"} == {
        key: value for key, value in wiki_before_reject.items() if key != "log.md"
    }
    log_after_reject = (wiki / "log.md").read_text(encoding="utf-8")
    assert log_after_reject.startswith(log_before_reject)
    added_log = log_after_reject[len(log_before_reject) :]
    added_entries = [line for line in added_log.splitlines() if line.startswith("## ")]
    assert len(added_entries) == 1 and "Review rejected" in added_entries[0], added_log


# Scenario ④ -----------------------------------------------------------------------------------


def test_a4_session_transcript_is_saved_when_the_session_ends(world: MemoryWorld) -> None:
    world.install("proj", role="project")
    world.install("team", role="team")
    world.install_hook_launcher()
    sessions = world.vault_root("proj") / "raw" / "sessions"
    template_files = session_files(sessions)
    team_before = file_hashes(world.vault_root("team"))

    via_vg = world.capture("SessionEnd", "a4-session-one", "Remember that releases need a checklist.")
    assert via_vg.returncode == 0, via_vg.stderr
    assert "vg hook capture: status=written vault=proj" in via_vg.stderr
    first_files = [path for path in session_files(sessions) if path not in template_files]
    assert len(first_files) == 1
    assert "Remember that releases need a checklist." in first_files[0].read_text(encoding="utf-8")

    again = world.capture("SessionEnd", "a4-session-one", "Remember that releases need a checklist.")
    assert again.returncode == 0, again.stderr
    assert "vg hook capture:" in again.stderr
    assert session_files(sessions) == sorted(template_files + first_files)

    direct = world.capture("SessionEnd", "a4-session-two", "Remember that tags are signed.", without_vg=True)
    assert direct.returncode == 0, direct.stderr
    assert "vg hook capture:" not in direct.stderr
    assert json.loads(direct.stdout)["status"] == "written"
    second_files = [path for path in session_files(sessions) if path not in template_files]
    assert len(second_files) == 2
    assert any("Remember that tags are signed." in path.read_text(encoding="utf-8") for path in second_files)

    compact = world.capture("PreCompact", "a4-session-three", "Remember that builds run nightly.")
    assert compact.returncode == 0, compact.stderr
    assert "vg hook capture: status=written vault=proj" in compact.stderr
    third_files = [path for path in session_files(sessions) if path not in template_files]
    assert len(third_files) == 3
    assert any("Remember that builds run nightly." in path.read_text(encoding="utf-8") for path in third_files)
    assert file_hashes(world.vault_root("team")) == team_before


# Scenario ⑤ -----------------------------------------------------------------------------------


def test_a5_search_results_show_vault_name_and_role(world: MemoryWorld) -> None:
    for name, role in (("mine", "personal"), ("proj", "project"), ("team", "team")):
        world.install(name, role=role)
        world.seed_page(name, f"Deployment freeze for {name}", updated="2026-09-01", body="Deployment freeze rules.")
    world.vg_setup()
    roles = {name: entry["role"] for name, entry in world.vault_map()["vaults"].items()}
    query = "deployment freeze"

    cli_results = world.search(query, cwd=world.project)["results"]
    mcp_payload = world.mcp("search_vault", query=query, cwd=str(world.project), limit=10)
    outside = world.home / "elsewhere"
    outside.mkdir()
    outside_results = world.search(query, cwd=outside)["results"]

    for results in (cli_results, mcp_payload["results"]):
        assert len({result["vault_id"] for result in results}) >= 2
        for result in results:
            assert result["vault_name"] == result["vault_id"]
            assert result["vault_role"] == roles[result["vault_name"]]
    assert outside_results
    assert {result["vault_id"] for result in outside_results} == {world.active_vault()}


# Scenario ⑥ -----------------------------------------------------------------------------------


def test_a6_rebuilding_graph_home_loses_no_memory(world: MemoryWorld) -> None:
    world.install("proj", role="project")
    world.install("team", role="team")
    world.seed_page("team", "Review every schema change", updated="2026-04-01", pin=True, memory_kind="rule")
    world.seed_page("proj", "Prefer small pull requests", updated="2026-05-01", pin=True, memory_kind="preference")
    for number in range(1, 4):
        world.seed_page("proj", f"Incident review {number}", updated=f"2026-08-0{number}", body="Incident notes.")
    world.vg_setup()
    queries = ("schema change review", "small pull requests", "incident review")

    world.recall("a6-first")
    before_blocks = listed_blocks(world.recall("a6-second"))
    before_search = [world.top_results(query) for query in queries]
    before_files = {name: file_hashes(world.vault_root(name)) for name in ("proj", "team")}

    shutil.rmtree(world.graph_home)
    world.vg_setup()
    world.vg_index()

    assert listed_blocks(world.recall("a6-after-rebuild")) == before_blocks
    assert [world.top_results(query) for query in queries] == before_search
    assert {name: file_hashes(world.vault_root(name)) for name in ("proj", "team")} == before_files
    assert PIN_BLOCK_TITLE in before_blocks and BLOCK_B_TITLE in before_blocks


# Helpers --------------------------------------------------------------------------------------


class MemoryWorld:
    """One temporary HOME with Vaults, a project folder, a vault-map.json and a Graph Home."""

    def __init__(self, tmp_path: Path, *, builder_root: Path, shared_cache: Path) -> None:
        self.tmp_path = tmp_path
        self.builder_root = builder_root
        self.shared_cache = shared_cache
        self.home = tmp_path / "home"
        self.config_dir = self.home / ".claude"
        self.map_path = self.config_dir / "vault-builder" / "vault-map.json"
        self.graph_home = tmp_path / "graph-home"
        self.project = self.home / "work" / "demo-app"
        self.drafts = tmp_path / "drafts"
        self.transcripts = tmp_path / "transcripts"
        self.vg_bin = _vg_executable()
        for folder in (self.project, self.drafts, self.transcripts):
            folder.mkdir(parents=True)
        (self.home / ".cache").symlink_to(shared_cache, target_is_directory=True)
        _run(["git", "init", "-q", str(self.project)], env=self.env(), cwd=self.tmp_path)

    def env(self, **overrides: str) -> dict[str, str]:
        environ = dict(os.environ)
        for key in ("CLAUDE_CONFIG_DIR", "VAULT_GRAPH_BIN", "PYTHONPATH"):
            environ.pop(key, None)
        environ.update(
            HOME=str(self.home),
            CLAUDE_CONFIG_DIR=str(self.config_dir),
            VAULT_GRAPH_VAULT_MAP=str(self.map_path),
            PYTHONDONTWRITEBYTECODE="1",
        )
        environ.update(overrides)
        return environ

    # vault-builder

    def builder(self, *args: str) -> None:
        _run([sys.executable, str(self.builder_root / "tools" / "vault_migration" / "cli.py"), *args], env=self.env())

    def install(self, name: str, *, role: str) -> None:
        self.builder("install", str(self.vault_root(name)), "--name", name)
        self.builder("link", name, "--repo", str(self.project), "--project", PROJECT_ID)
        self.builder("set-role", "--vault", name, "--role", role)

    def install_hook_launcher(self) -> None:
        """Put the launcher next to the router, as ``install --with-hooks`` does (contract 6)."""
        target = self.config_dir / "vault-builder" / LAUNCHER_ASSET.name
        shutil.copyfile(self.builder_root / LAUNCHER_ASSET, target)
        assert (target.parent / "llm_wiki_router.py").is_file()

    def vault_map(self) -> dict[str, Any]:
        data: dict[str, Any] = json.loads(self.map_path.read_text(encoding="utf-8"))
        return data

    def vault_root(self, name: str) -> Path:
        return self.home / "vaults" / name

    def vault_cli(self, name: str, *args: str) -> subprocess.CompletedProcess[str]:
        command = [sys.executable, "-B", str(self.vault_root(name) / "tools" / "wiki" / "cli.py"), *args]
        return _run(command, env=self.env(), cwd=self.vault_root(name), check=False)

    def seed_page(
        self,
        vault: str,
        title: str,
        *,
        updated: str,
        body: str = "Seed page body.",
        pin: bool = False,
        memory_kind: str | None = None,
    ) -> str:
        """Publish one decision page with the Vault's own publish-draft and return its Vault path."""
        slug = "-".join(title.lower().split())
        frontmatter: dict[str, object] = {
            "title": title,
            "type": "decision",
            "status": "active",
            "created": updated,
            "updated": updated,
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
        }
        if pin or memory_kind:
            frontmatter.update(memory_schema="vault-memory/v1", pin=pin)
            if memory_kind:
                frontmatter["memory_kind"] = memory_kind
        draft = {
            "version": 1,
            "operation": "upsert-page",
            "path": f"wiki/decisions/{slug}.md",
            "frontmatter": frontmatter,
            "body": f"# {title}\n\n{body}\n\n## Evidence\n\n- Evidence: scenario seed by a person.\n",
            "index": {"section": "Decisions", "target": f"decisions/{slug}", "summary": title},
            "log": {"event_type": "decision", "title": f"Seed {title}", "items": [f"Added [[decisions/{slug}]]."]},
        }
        draft_path = self.drafts / f"{vault}-{slug}.json"
        draft_path.write_text(json.dumps(draft), encoding="utf-8")
        result = self.vault_cli(vault, "publish-draft", str(draft_path), "--json")
        assert result.returncode == 0, result.stdout + result.stderr
        assert json.loads(result.stdout)["status"] == "published"
        return f"wiki/decisions/{slug}.md"

    # vault-graph

    def vg(self, *args: str, cwd: Path | None = None, stdin: str | None = None) -> str:
        return _run([str(self.vg_bin), *args], env=self.env(), cwd=cwd or self.tmp_path, stdin=stdin).stdout

    def vg_setup(self) -> None:
        self.vg("setup", "--graph-home", str(self.graph_home))

    def vg_index(self) -> None:
        self.vg("index", "--graph-home", str(self.graph_home), "--all-vaults")

    def recall(self, session_id: str) -> str:
        return self.recall_result(session_id).stdout

    def recall_result(self, session_id: str) -> subprocess.CompletedProcess[str]:
        hook = {"cwd": str(self.project), "source": "startup", "session_id": session_id}
        command = [str(self.vg_bin), "hook", "session-start", "--graph-home", str(self.graph_home)]
        return _run(command, env=self.env(), cwd=self.tmp_path, stdin=json.dumps(hook))

    def search(self, query: str, *, cwd: Path) -> dict[str, Any]:
        output = self.vg("search", query, "--graph-home", str(self.graph_home), "--format", "json", cwd=cwd)
        data: dict[str, Any] = json.loads(output)
        return data

    def search_paths(self, query: str, *, cwd: Path) -> list[str]:
        return [result_path(result) for result in self.search(query, cwd=cwd)["results"]]

    def top_results(self, query: str) -> list[tuple[str, str]]:
        results = self.search(query, cwd=self.project)["results"][:5]
        return [(result["vault_name"], result_path(result)) for result in results]

    def active_vault(self) -> str:
        for line in self.vg("vault", "list", "--graph-home", str(self.graph_home)).splitlines():
            parts = line.split()
            if len(parts) >= 2 and parts[1] == "active":
                return parts[0]
        raise AssertionError("vg vault list shows no active Vault")

    def mcp(self, tool: str, **arguments: object) -> dict[str, Any]:
        """Call one tool on a real ``vg serve --mcp`` over stdio and return its payload."""
        import anyio
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client

        params = StdioServerParameters(
            command=str(self.vg_bin),
            args=["serve", "--mcp", "--graph-home", str(self.graph_home)],
            env=self.env(),
            cwd=str(self.tmp_path),
        )

        async def call() -> Any:
            with anyio.fail_after(COMMAND_TIMEOUT_S):
                async with stdio_client(params) as (read_stream, write_stream):
                    async with ClientSession(read_stream, write_stream) as session:
                        await session.initialize()
                        return await session.call_tool(tool, dict(arguments))

        result = anyio.run(call)
        assert not result.isError, result.content
        assert result.structuredContent is not None
        payload = result.structuredContent["payload"]
        assert isinstance(payload, dict)
        return payload

    # hooks

    def capture(
        self, event: str, session_id: str, user_text: str, *, without_vg: bool = False
    ) -> subprocess.CompletedProcess[str]:
        """Send one PreCompact or SessionEnd hook JSON to the installed launcher's ``capture``."""
        transcript = self.transcripts / f"{session_id}.jsonl"
        write_transcript(transcript, session_id=session_id, cwd=self.project, user_text=user_text)
        hook = {
            "session_id": session_id,
            "transcript_path": str(transcript),
            "cwd": str(self.project),
            "hook_event_name": event,
        }
        if without_vg:
            path = os.pathsep.join(
                folder for folder in os.environ.get("PATH", "").split(os.pathsep) if not (Path(folder) / "vg").exists()
            )
            env = self.env(VAULT_GRAPH_BIN=str(self.tmp_path / "missing" / "vg"), PATH=path)
        else:
            env = self.env(VAULT_GRAPH_BIN=str(self.vg_bin))
        launcher = self.config_dir / "vault-builder" / LAUNCHER_ASSET.name
        return _run(
            [sys.executable, "-I", str(launcher), "capture"],
            env=env,
            cwd=self.project,
            stdin=json.dumps(hook),
            check=False,
        )


def write_transcript(path: Path, *, session_id: str, cwd: Path, user_text: str) -> None:
    """A two-turn Claude Code transcript in the JSONL shape ``sessions capture`` reads."""
    entries = [
        {
            "type": "user",
            "uuid": f"{session_id}-u1",
            "timestamp": "2026-11-02T01:00:00.000Z",
            "sessionId": session_id,
            "cwd": str(cwd),
            "message": {"role": "user", "content": user_text},
        },
        {
            "type": "assistant",
            "uuid": f"{session_id}-a1",
            "timestamp": "2026-11-02T01:00:05.000Z",
            "sessionId": session_id,
            "cwd": str(cwd),
            "message": {"role": "assistant", "content": [{"type": "text", "text": "Noted."}]},
        },
    ]
    path.write_text("".join(json.dumps(entry) + "\n" for entry in entries), encoding="utf-8")


def recall_blocks(text: str) -> dict[str, str]:
    """Split recall output into ``## `` blocks, keyed by heading line, in output order."""
    blocks: dict[str, str] = {}
    current: str | None = None
    for line in text.splitlines(keepends=True):
        if line.startswith("## "):
            current = line.rstrip("\n")
            blocks[current] = ""
        if current is not None:
            blocks[current] += line
    return blocks


def listed_blocks(text: str) -> dict[str, str]:
    """Recall blocks A and B, which must survive a Graph Home rebuild byte for byte."""
    blocks = recall_blocks(text)
    return {title: blocks[title] for title in (PIN_BLOCK_TITLE, BLOCK_B_TITLE) if title in blocks}


def result_path(result: Mapping[str, Any]) -> str:
    evidence: Sequence[Mapping[str, Any]] = result["evidence"]
    return str(evidence[0]["path"])


def frontmatter_lines(page: Path) -> list[str]:
    text = page.read_text(encoding="utf-8")
    assert text.startswith("---\n"), page
    return text[4 : text.index("\n---\n", 4)].splitlines()


def file_hashes(root: Path) -> dict[str, str]:
    return {
        path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(root.rglob("*"))
        if path.is_file() and "__pycache__" not in path.parts
    }


def session_files(sessions: Path) -> list[Path]:
    return sorted(path for path in sessions.rglob("*") if path.is_file()) if sessions.is_dir() else []


def _vg_executable() -> Path:
    beside = Path(sys.executable).parent / "vg"
    if beside.is_file():
        return beside
    found = shutil.which("vg")
    if found is None:
        pytest.fail("vg is not installed next to this Python or on PATH; run through `uv run`.")
    return Path(found)


def _run(
    command: Sequence[str],
    *,
    env: Mapping[str, str],
    cwd: Path | None = None,
    stdin: str | None = None,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        list(command),
        env=dict(env),
        cwd=cwd,
        input=stdin,
        capture_output=True,
        text=True,
        timeout=COMMAND_TIMEOUT_S,
        check=False,
    )
    if check and result.returncode != 0:
        raise AssertionError(
            f"{' '.join(command)} ended with {result.returncode}\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )
    return result
