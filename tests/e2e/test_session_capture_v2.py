"""End-to-end v2 session capture through the real Vault tools (spec 2026-11-05 §4.2.5, 위험A9, A-3).

Every test installs a temporary Vault with the vault-builder named by ``VAULT_BUILDER_ROOT`` into a
temporary HOME, copies the hook launcher next to that HOME's ``vault-map.json`` and sends hook JSON to
it: the launcher runs ``vg hook capture``, vg normalizes the transcript and runs the launcher again
with ``capture --direct --normalized <file>``. The transcripts are copies of
``tests/fixtures/session_adapter/*/raw`` with the fixture cwd replaced by the temporary project folder.
The project folder name has a space, so the Vault tool percent-encodes the cwd-based paths in the
exchange meta line and vg must decode them.

Without ``VAULT_BUILDER_ROOT`` the tests are skipped.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tarfile
from collections.abc import Iterator
from io import BytesIO
from pathlib import Path

import pytest

from tests.e2e.test_long_term_memory_scenarios import (
    BUILDER_ENV,
    LAUNCHER_ASSET,
    MemoryWorld,
    _run,
    frontmatter_lines,
)
from vault_graph.operation.scope.catalog_service import CatalogService

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "session_adapter"
FIXTURE_CWD = "/work/demo-app"
OPEN_SESSION = "11111111-1111-4111-8111-111111111111"  # with_origin: exchange u-007 is open until SessionEnd
STEP_SESSION = "22222222-2222-4222-8222-222222222222"  # without_origin: three closed exchanges
SUBAGENT_SESSION = "33333333-3333-4333-8333-333333333333"  # subagent_compact
FIXTURE_OF = {OPEN_SESSION: "with_origin", STEP_SESSION: "without_origin", SUBAGENT_SESSION: "subagent_compact"}
VAULT = "proj"
CLAUDE_PROJECT_KEY = "-home-work-demo-app"
CAPTURE_LINE = "vg hook capture: status="


@pytest.fixture(scope="session")
def builder_root() -> Path:
    value = os.environ.get(BUILDER_ENV)
    if not value:
        pytest.skip(f"set {BUILDER_ENV} to a vault-builder checkout to run the session capture scenarios")
    root = Path(value).expanduser().resolve()
    if not (root / "tools" / "wiki" / "lib" / "session_capture.py").is_file():
        pytest.fail(f"{BUILDER_ENV}={value} has no tools/wiki/lib/session_capture.py")
    return root


@pytest.fixture(scope="session")
def shared_cache(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return tmp_path_factory.mktemp("shared-home-cache")


@pytest.fixture(name="world")
def world_fixture(tmp_path: Path, builder_root: Path, shared_cache: Path) -> Iterator[SessionWorld]:
    yield SessionWorld(tmp_path, builder_root=builder_root, shared_cache=shared_cache)


# A-3: v2 file, no file without new turns, open exchange left out, same input same bytes --------------


def test_session_end_hook_writes_a_v2_part_without_the_open_exchange(world: SessionWorld) -> None:
    world.install_project_vault()
    export = world.enable_session_export()
    world.place_transcript(OPEN_SESSION)

    first = world.hook("PreCompact", OPEN_SESSION)

    assert first.returncode == 0, first.stderr
    assert f"{CAPTURE_LINE}written vault={VAULT}" in first.stderr
    assert "input=normalized" in first.stderr
    [part1] = world.session_parts(OPEN_SESSION)
    assert part1.name == f"2026-11-01-{OPEN_SESSION}-part1.md"
    fields = frontmatter(part1)
    assert fields["schema"] == "vault-session/v2"
    assert fields["source_schema"] == "vg-session-jsonl/1"
    assert str(fields["renderer"]).startswith("vg-session-md/2.")
    assert fields["first_exchange_id"] == fields["last_exchange_id"] == "u-001"
    assert fields["part"] == "1"
    text = part1.read_text(encoding="utf-8")
    # The open exchange u-007 (PreCompact keeps the last exchange open) is not in the file.
    assert "id=u-007" not in text
    assert "Now list the docs folder." not in text
    # The same run exported the normalized file to the export folder (A-3 last bullet).
    assert (export / "normalized" / "claude-code" / f"{OPEN_SESSION}.jsonl").is_file()

    again = world.hook("PreCompact", OPEN_SESSION)

    assert again.returncode == 0, again.stderr
    assert f"{CAPTURE_LINE}no-new-turns vault={VAULT}" in again.stderr
    assert world.session_parts(OPEN_SESSION) == [part1]

    ended = world.hook("SessionEnd", OPEN_SESSION)

    assert ended.returncode == 0, ended.stderr
    assert f"{CAPTURE_LINE}written vault={VAULT}" in ended.stderr
    part2 = world.session_parts(OPEN_SESSION)[-1]
    assert part2.name == f"2026-11-01-{OPEN_SESSION}-part2.md"
    fields2 = frontmatter(part2)
    assert fields2["first_exchange_id"] == fields2["last_exchange_id"] == "u-007"
    assert "Now list the docs folder." in part2.read_text(encoding="utf-8")
    assert "id=u-001" not in part2.read_text(encoding="utf-8")


def test_same_normalized_input_renders_the_same_bytes(world: SessionWorld) -> None:
    world.install_project_vault()
    world.place_transcript(SUBAGENT_SESSION)

    assert world.hook("SessionEnd", SUBAGENT_SESSION).returncode == 0
    [part] = world.session_parts(SUBAGENT_SESSION)
    first = part.read_bytes()
    part.unlink()
    assert world.hook("SessionEnd", SUBAGENT_SESSION).returncode == 0
    [again] = world.session_parts(SUBAGENT_SESSION)
    second = again.read_bytes()

    assert again.name == part.name
    # collected_at is the capture time. Every other byte, body_sha256 included, is the same.
    assert without_collected_at(first) == without_collected_at(second)
    assert frontmatter(again)["body_sha256"] == hashlib.sha256(body_bytes(second)).hexdigest()
    text = second.decode("utf-8")
    assert frontmatter(again)["schema"] == "vault-session/v2"
    assert "## Subagent a7f3 · code-reviewer · " in text


def test_vg_reads_the_meta_line_the_vault_tool_writes(world: SessionWorld) -> None:
    """Percent-encoded files, tools, started and ended reach the keyword column and the overlap pass."""
    world.install_project_vault()
    world.place_transcript(OPEN_SESSION)
    assert world.hook("SessionEnd", OPEN_SESSION).returncode == 0
    [part] = world.session_parts(OPEN_SESSION)
    meta = meta_line(part, "u-001")
    encoded_file = f"{world.project}/src/app.py".replace(" ", "%20")
    assert f"files={encoded_file}" in meta
    assert "started=2026-11-01T10:00:00.000Z ended=2026-11-01T10:00:10.000Z" in meta

    report = world.index()

    assert "session_exchange_meta_invalid" not in report
    chunks = world.indexed_chunks()
    first = [chunk for chunk in chunks if chunk.parent_key == f"{OPEN_SESSION}:u-001"]
    assert first, chunks
    metadata = first[0].keyword_metadata
    assert f"files: {world.project}/src/app.py commands:" in metadata
    assert "tools: Bash:1 Edit:1 WebFetch:1 errors: 1 outcome: answered" in metadata
    assert all("vg:exchange" not in chunk.text for chunk in chunks)
    open_exchange = [chunk for chunk in chunks if chunk.parent_key == f"{OPEN_SESSION}:u-007"]
    assert open_exchange and open_exchange[0].section_path[1] == "Q: Now list the docs folder."


# A-3: a Vault tool without --normalized writes v1 and the hook ends 0 ----------------------------------


def test_vault_tool_without_normalized_writes_v1_and_the_hook_ends_zero(world: SessionWorld) -> None:
    world.install_project_vault()
    world.use_vault_tools_before_normalized()
    world.place_transcript(STEP_SESSION)

    result = world.hook("SessionEnd", STEP_SESSION)

    assert result.returncode == 0, result.stderr
    # vg ran --normalized first, got exit 2 and handed the transcript to capture --direct.
    assert f"{CAPTURE_LINE}written vault={VAULT}" in result.stderr
    assert "input=transcript" in result.stderr
    assert "warning" not in result.stderr
    [part] = world.session_parts(STEP_SESSION)
    assert frontmatter(part)["schema"] == "vault-session/v1"
    assert "Try sleeping instead." in part.read_text(encoding="utf-8")


# Helpers ------------------------------------------------------------------------------------------


class IndexedChunk:
    def __init__(self, row: sqlite3.Row) -> None:
        self.path = str(row["path"])
        self.parent_key = str(row["parent_key"]) if row["parent_key"] is not None else ""
        self.keyword_metadata = str(row["keyword_metadata"] or "")
        self.section_path: list[str] = json.loads(row["section_path_json"])
        self.text = str(row["text"] or "")

    def __repr__(self) -> str:
        return f"IndexedChunk({self.path!r}, {self.parent_key!r})"


class SessionWorld(MemoryWorld):
    """MemoryWorld with a project folder whose name has a space, Claude Code transcripts and a launcher."""

    def __init__(self, tmp_path: Path, *, builder_root: Path, shared_cache: Path) -> None:
        super().__init__(tmp_path, builder_root=builder_root, shared_cache=shared_cache)
        self.project = self.home / "work" / "demo app"
        self.project.mkdir(parents=True)
        _run(["git", "init", "-q", str(self.project)], env=self.env(), cwd=self.tmp_path)
        self.claude_projects = self.config_dir / "projects" / CLAUDE_PROJECT_KEY
        self.claude_projects.mkdir(parents=True)
        self.index_home = tmp_path / "index-home"
        self._registered = False

    # Vault

    def install_project_vault(self) -> None:
        self.install(VAULT, role="project")
        self.install_hook_launcher()

    def sessions_dir(self) -> Path:
        return self.vault_root(VAULT) / "raw" / "sessions" / "claude-code"

    def session_parts(self, session_id: str) -> list[Path]:
        folder = self.sessions_dir()
        if not folder.is_dir():
            return []
        found = [path for path in folder.iterdir() if path.is_file() and f"-{session_id}-part" in path.name]
        return sorted(found, key=part_number)

    def use_vault_tools_before_normalized(self) -> None:
        """Replace the Vault's tools/wiki with the vault-builder tree before ``--normalized`` was added."""
        added = _git(self.builder_root, "log", "--format=%H", "--reverse", "-S--normalized", "--", "tools/wiki/cli.py")
        first = added.split()[0]
        archive = subprocess.run(
            ["git", "-C", str(self.builder_root), "archive", "--format=tar", f"{first}^", "tools/wiki"],
            capture_output=True,
            check=True,
        ).stdout
        wiki = self.vault_root(VAULT) / "tools" / "wiki"
        shutil.rmtree(wiki)
        with tarfile.open(fileobj=BytesIO(archive)) as tar:
            tar.extractall(self.vault_root(VAULT), filter="data")
        help_text = self.vault_cli(VAULT, "sessions", "capture", "--help").stdout
        assert "--normalized" not in help_text

    # Claude Code

    def place_transcript(self, session_id: str, *, lines: int | None = None, mtime: float | None = None) -> Path:
        """Copy the fixture transcript (its first ``lines`` lines) with the cwd moved to the project folder."""
        raw = FIXTURES / FIXTURE_OF[session_id] / "raw"
        target = self.claude_projects / f"{session_id}.jsonl"
        text = (raw / f"{session_id}.jsonl").read_text(encoding="utf-8")
        kept = text.splitlines(keepends=True)[:lines] if lines is not None else text.splitlines(keepends=True)
        target.write_text(self._moved("".join(kept)), encoding="utf-8")
        subagents = raw / session_id
        if subagents.is_dir():
            for source in sorted(path for path in subagents.rglob("*") if path.is_file()):
                copy = self.claude_projects / source.relative_to(raw)
                copy.parent.mkdir(parents=True, exist_ok=True)
                copy.write_text(self._moved(source.read_text(encoding="utf-8")), encoding="utf-8")
        if mtime is not None:
            os.utime(target, (mtime, mtime))
        return target

    def _moved(self, text: str) -> str:
        return text.replace(json.dumps(FIXTURE_CWD)[1:-1], json.dumps(str(self.project))[1:-1])

    def transcript_turn_times(self, session_id: str) -> dict[str, str]:
        """uuid -> timestamp of every main user or assistant entry of the placed transcript."""
        turns: dict[str, str] = {}
        for line in (self.claude_projects / f"{session_id}.jsonl").read_text(encoding="utf-8").splitlines():
            try:
                entry = json.loads(line)
            except ValueError:
                continue
            if entry.get("type") in ("user", "assistant") and entry.get("uuid"):
                turns.setdefault(entry["uuid"], entry["timestamp"])
        return turns

    # hooks

    def hook(
        self, event: str, session_id: str, *, direct: bool = False, with_vg: bool = True
    ) -> subprocess.CompletedProcess[str]:
        """Send hook JSON to the installed launcher: ``capture`` (through vg) or ``capture --direct``."""
        hook = {
            "session_id": session_id,
            "transcript_path": str(self.claude_projects / f"{session_id}.jsonl"),
            "cwd": str(self.project),
            "hook_event_name": event,
        }
        env = self.env(VAULT_GRAPH_BIN=str(self.vg_bin) if with_vg else str(self.tmp_path / "missing" / "vg"))
        launcher = self.config_dir / "vault-builder" / LAUNCHER_ASSET.name
        args = ["capture", "--direct"] if direct else ["capture"]
        return _run(
            [sys.executable, "-I", str(launcher), *args],
            env=env,
            cwd=self.project,
            stdin=json.dumps(hook),
            check=False,
        )

    def enable_session_export(self) -> Path:
        export = self.tmp_path / "session-export"
        export.mkdir()
        settings = self.home / ".vault-graph" / "configs" / "session-export.json"
        settings.parent.mkdir(parents=True, exist_ok=True)
        settings.write_text(json.dumps({"path": str(export), "agents": ["claude-code"], "raw": True}), encoding="utf-8")
        return export

    # vg index

    def index(self) -> str:
        if not self._registered:
            self.vg(
                "setup",
                "--vault",
                str(self.vault_root(VAULT)),
                "--vault-id",
                VAULT,
                "--graph-home",
                str(self.index_home),
            )
            self._registered = True
        result = _run(
            [str(self.vg_bin), "index", "--graph-home", str(self.index_home), "--all-vaults", "--no-vector"],
            env=self.env(),
            cwd=self.tmp_path,
        )
        return result.stdout + result.stderr

    def indexed_chunks(self) -> list[IndexedChunk]:
        """Session chunks of the current metadata projection, by path then chunk order."""
        database = CatalogService(graph_home_path=self.index_home).metadata_path
        connection = sqlite3.connect(database)
        connection.row_factory = sqlite3.Row
        try:
            rows = connection.execute(
                "SELECT c.path, c.parent_key, c.keyword_metadata, c.section_path_json, k.text "
                "FROM chunks c LEFT JOIN keyword_rows r ON r.vault_id = c.vault_id AND r.chunk_id = c.chunk_id "
                "LEFT JOIN keyword_chunks k ON k.rowid = r.rowid "
                "WHERE c.path LIKE 'raw/sessions/%' ORDER BY c.path, c.chunk_id"
            ).fetchall()
        finally:
            connection.close()
        return [IndexedChunk(row) for row in rows]


def frontmatter(page: Path) -> dict[str, str]:
    fields: dict[str, str] = {}
    for line in frontmatter_lines(page):
        key, separator, value = line.partition(":")
        if separator and not line.startswith(" "):
            fields[key] = value.strip().strip('"')
    return fields


def body_bytes(data: bytes) -> bytes:
    """The session body as the Vault tool hashes it: everything after the closing frontmatter line."""
    end = data.index(b"\n---\n", 4) + len(b"\n---\n")
    return data[end:]


def without_collected_at(data: bytes) -> bytes:
    return b"".join(line for line in data.splitlines(keepends=True) if not line.startswith(b"collected_at:"))


def meta_line(part: Path, exchange_id: str) -> str:
    for line in part.read_text(encoding="utf-8").splitlines():
        if line.startswith("<!-- vg:exchange ") and f" id={exchange_id} " in f" {line[len('<!-- vg:exchange ') :]}":
            return line
    raise AssertionError(f"no meta line for {exchange_id} in {part.name}")


def part_number(path: Path) -> int:
    return int(path.stem.rsplit("-part", 1)[1])


def sha256_files(paths: list[Path]) -> dict[str, str]:
    return {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in paths}


def _git(root: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True, check=True).stdout
