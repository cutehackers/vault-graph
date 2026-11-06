"""End-to-end move of one session from v1 parts to v2 parts (spec 2026-11-05 §4.2.7, §4.2.12, A-37).

The Vault tool from ``VAULT_BUILDER_ROOT`` writes v1 parts 1 and 2 with ``capture --direct`` while the
transcript grows. Part 2 ends inside an exchange. The next hook goes through ``vg hook capture`` and
``--normalized``, so part 3 is v2 and starts with the rest of that exchange. ``vg session export
--recapture`` then writes the whole session again as part 4. After each step ``vg index`` must keep
every transcript turn in exactly one indexed exchange.

Without ``VAULT_BUILDER_ROOT`` the tests are skipped.
"""

from __future__ import annotations

import re
from datetime import datetime

from tests.e2e.test_session_capture_v2 import (
    OPEN_SESSION,
    STEP_SESSION,
    SessionWorld,
    builder_root,  # noqa: F401 - pytest fixture
    frontmatter,
    meta_line,
    sha256_files,
    shared_cache,  # noqa: F401 - pytest fixture
    world_fixture,  # noqa: F401 - pytest fixture
)

V1_HEADING = re.compile(r"^## (?P<at>\d{4}-\d{2}-\d{2}T\S+Z) (?P<role>user|assistant)$")
V2_META = re.compile(r"^<!-- vg:exchange (?P<body>.*) -->$")
# without_origin lines: 1 u-101, 2 u-102, 3 a-101, 4 u-103 (human), 5 a-102 (Bash), 6 u-104, ...
PART1_LINES = 3
PART2_LINES = 4


def test_v1_parts_continue_as_v2_and_recapture_adds_a_full_v2_part(world: SessionWorld) -> None:
    world.install_project_vault()
    # Another, newer session in the same project folder: the step session is not the newest, so
    # recapture treats it as ended and closes its last exchange.
    world.place_transcript(OPEN_SESSION, mtime=1_800_000_000)

    world.place_transcript(STEP_SESSION, lines=PART1_LINES, mtime=1_700_000_000)
    assert world.hook("PreCompact", STEP_SESSION, direct=True).returncode == 0
    world.place_transcript(STEP_SESSION, lines=PART2_LINES, mtime=1_700_000_000)
    assert world.hook("PreCompact", STEP_SESSION, direct=True).returncode == 0
    part1, part2 = world.session_parts(STEP_SESSION)
    assert frontmatter(part1)["schema"] == frontmatter(part2)["schema"] == "vault-session/v1"
    assert frontmatter(part2)["last_turn_uuid"] == "u-103"

    world.place_transcript(STEP_SESSION, mtime=1_700_000_000)
    ended = world.hook("SessionEnd", STEP_SESSION)

    assert ended.returncode == 0, ended.stderr
    assert "input=normalized" in ended.stderr
    part3 = world.session_parts(STEP_SESSION)[-1]
    assert part3.name.endswith("-part3.md")
    fields = frontmatter(part3)
    assert fields["schema"] == "vault-session/v2"
    assert fields["part"] == "3"
    assert fields["first_exchange_id"] == "u-103"
    assert fields["first_turn_uuid"] == "a-102"
    assert fields["last_exchange_id"] == "u-105"
    continued = meta_line(part3, "u-103")
    assert " continued=1 -->" in continued
    assert "started=2026-03-02T08:01:01.000Z" in continued
    assert " continued=1" not in meta_line(part3, "u-105")
    text = part3.read_text(encoding="utf-8")
    assert "Run it for me." not in text
    after_cursor = datetime.fromisoformat(fields["first_turn_at"].replace("Z", "+00:00"))
    assert after_cursor > datetime.fromisoformat(frontmatter(part2)["last_turn_at"].replace("Z", "+00:00"))

    world.index()
    kept = indexed_exchange_ranges(world)
    assert {kind for kind, _ in kept.values()} == {"v1", "v2"}
    assert turn_coverage(world, kept) == dict.fromkeys(world.transcript_turn_times(STEP_SESSION), 1)

    before = sha256_files(world.session_parts(STEP_SESSION))
    export = world.tmp_path / "recapture-export"
    output = world.vg(
        "session",
        "export",
        "--agent",
        "claude-code",
        "--session",
        STEP_SESSION,
        "--out",
        str(export),
        "--recapture",
        "--graph-home",
        str(world.index_home),
    )

    assert f"{STEP_SESSION} recapture=written vault=proj" in output
    parts = world.session_parts(STEP_SESSION)
    assert [path.name.rsplit("-part", 1)[1] for path in parts] == ["1.md", "2.md", "3.md", "4.md"]
    assert sha256_files(parts[:3]) == before
    part4 = frontmatter(parts[3])
    assert part4["schema"] == "vault-session/v2"
    assert (part4["first_exchange_id"], part4["last_exchange_id"]) == ("u-102", "u-105")
    assert "continued=1" not in parts[3].read_text(encoding="utf-8")

    world.index()
    kept = indexed_exchange_ranges(world)
    # Every v1 exchange overlaps a v2 exchange of part 4, so no v1 exchange is left in the index.
    assert {kind for kind, _ in kept.values()} == {"v2"}
    assert turn_coverage(world, kept) == dict.fromkeys(world.transcript_turn_times(STEP_SESSION), 1)


# Helpers ------------------------------------------------------------------------------------------


Ranges = dict[tuple[str, str], tuple[str, tuple[datetime, datetime]]]
"""(Vault path, chunk ``parent_key``) -> (``v1`` or ``v2``, first and last turn time of the exchange)."""


def turn_coverage(world: SessionWorld, kept: Ranges) -> dict[str, int]:
    """For each transcript turn uuid, how many indexed exchanges hold its time."""
    counts: dict[str, int] = {}
    for uuid, at in world.transcript_turn_times(STEP_SESSION).items():
        moment = _time(at)
        counts[uuid] = sum(1 for _, (start, end) in kept.values() if start <= moment <= end)
    return counts


def indexed_exchange_ranges(world: SessionWorld) -> Ranges:
    """The exchanges that have chunks in the index, with the time range of the indexed copy."""
    every = _exchange_ranges(world)
    indexed = {(chunk.path, chunk.parent_key) for chunk in world.indexed_chunks()}
    unknown = indexed - set(every)
    assert not unknown, f"indexed exchanges the test cannot place: {sorted(unknown)}"
    return {key: value for key, value in every.items() if key in indexed}


def _exchange_ranges(world: SessionWorld) -> Ranges:
    ranges: Ranges = {}
    for part in world.session_parts(STEP_SESSION):
        relative = part.relative_to(world.vault_root("proj")).as_posix()
        lines = part.read_text(encoding="utf-8").splitlines()
        if frontmatter(part)["schema"] == "vault-session/v2":
            for line in lines:
                match = V2_META.match(line)
                if match is None:
                    continue
                fields = dict(item.split("=", 1) for item in match.group("body").split(" "))
                times = (_time(fields["started"]), _time(fields["ended"]))
                ranges[(relative, f"{STEP_SESSION}:{fields['id']}")] = ("v2", times)
            continue
        for key, heading_times in _v1_exchanges(relative, lines).items():
            ranges[(relative, key)] = ("v1", (_time(heading_times[0]), _time(heading_times[-1])))
    return ranges


def _v1_exchanges(relative: str, lines: list[str]) -> dict[str, list[str]]:
    """v1 exchanges by ``parent_key`` (spec §4.2.7). A user turn whose text does not start with ``<`` opens one."""
    turns: list[tuple[str, str, str]] = []  # heading, role, first body line
    for index, line in enumerate(lines):
        match = V1_HEADING.match(line)
        if match is None:
            continue
        body = next((text for text in lines[index + 1 :] if text.strip()), "")
        turns.append((line[len("## ") :], match.group("role"), body))
    exchanges: dict[str, list[str]] = {}
    occurrences: dict[str, int] = {}
    current: list[str] | None = None
    for heading, role, body in turns:
        if current is None or (role == "user" and not body.startswith("<")):
            occurrences[heading] = occurrences.get(heading, 0) + 1
            current = exchanges.setdefault(f"{relative}:{heading}:{occurrences[heading]}", [])
        current.append(heading.split(" ", 1)[0])
    return exchanges


def _time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))
