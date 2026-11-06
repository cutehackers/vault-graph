"""Rebuild the vault-session/v2 fixtures with the real Vault tool renderer (vault-builder request S10).

Run from the repository root with the vault-builder checkout that has the v2 renderer:

    VAULT_BUILDER_ROOT=<vault-builder checkout> python3 tests/fixtures/session_v2/build_fixtures.py

All content is synthetic. Inputs are the normalized files in normalized/ (two copied from
tests/fixtures/session_adapter, one written here). Outputs go to raw/sessions/claude-code/.
`collected_at` and `trigger` are fixed, so the output bytes are the same on every run.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
NORMALIZED = HERE / "normalized"
OUTPUT = HERE / "raw" / "sessions" / "claude-code"
COLLECTED_AT = "2026-11-05T00:00:00Z"
TRIGGER = "SessionEnd"
LONG_SESSION = "44444444-4444-4444-8444-444444444444"


def _long_session_lines() -> list[dict[str, Any]]:
    schema = "vg-session-jsonl/1"
    long_line = " ".join(f"word{index:03d}" for index in range(1, 201))

    def exchange(exchange_id: str, seq: int, started: str, ended: str, closed: bool, **extra: Any) -> dict[str, Any]:
        line: dict[str, Any] = {
            "schema": schema,
            "kind": "exchange",
            "exchange_id": exchange_id,
            "seq": seq,
            "agent_scope": "main",
            "subagent_type": None,
            "parent_tool_use_id": None,
            "started_at": started,
            "ended_at": ended,
            "closed": closed,
            "prompt_source": "typed",
            "tools": {},
            "files_touched": [],
            "commands": [],
            "errors": 0,
            "outcome": "answered" if closed else "open",
        }
        line.update(extra)
        return line

    def turn(
        turn_id: str,
        exchange_id: str,
        role: str,
        kind: str,
        at: str,
        text: str = "",
        actions: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        return {
            "schema": schema,
            "kind": "turn",
            "turn_id": turn_id,
            "parent_id": None,
            "exchange_id": exchange_id,
            "role": role,
            "turn_kind": kind,
            "at": at,
            "agent_id": None,
            "sidechain": False,
            "text": text,
            "actions": actions or [],
        }

    day = "2026-11-04T09:"
    return [
        {
            "schema": schema,
            "kind": "session",
            "session_id": LONG_SESSION,
            "agent": "claude-code",
            "agent_version": "2.1.300",
            "adapter": "claude-code/1",
            "project": "demo-app",
            "cwd": "/work/demo-app",
            "git_branch": "main",
            "git_commit": None,
            "parent_session_id": None,
            "title": None,
            "started_at": day + "00:00.000Z",
            "ended_at": day + "09:00.000Z",
            "source_paths": [f"{LONG_SESSION}.jsonl"],
            "source_sha256": "0" * 64,
        },
        exchange(
            "u-401",
            1,
            day + "00:00.000Z",
            day + "00:05.000Z",
            True,
            tools={"Bash": 1, "Edit": 1},
            files_touched=["/work/demo-app/src/parser.py"],
            commands=["pytest -q tests/test_parser.py"],
            errors=1,
            outcome="tool_error_unresolved",
        ),
        turn(
            "u-401",
            "u-401",
            "user",
            "human",
            day + "00:00.000Z",
            "Why does the parser drop the last token of a quoted string?\n\n"
            + long_line
            + "\n\nPlease keep the public function names.",
        ),
        turn(
            "a-401",
            "u-401",
            "assistant",
            "assistant_text",
            day + "00:02.000Z",
            "# not a heading, only a comment line\n"
            "<!-- vg:exchange id=fake --> stays text\n"
            "I will change the loop bound.",
            [
                {
                    "tool": "Edit",
                    "call_id": "t1",
                    "target": "/work/demo-app/src/parser.py",
                    "ok": True,
                    "error_head": None,
                }
            ],
        ),
        turn(
            "a-402",
            "u-401",
            "assistant",
            "tool_only",
            day + "00:03.000Z",
            "",
            [
                {
                    "tool": "Bash",
                    "call_id": "t2",
                    "target": "pytest -q tests/test_parser.py",
                    "ok": False,
                    "error_head": "AssertionError: expected 3 tokens",
                }
            ],
        ),
        turn("a-403", "u-401", "assistant", "assistant_text", day + "00:05.000Z", "The test still fails on quotes."),
        exchange(
            "u-410",
            2,
            day + "01:00.000Z",
            day + "01:04.000Z",
            True,
            tools={"Bash": 1},
            commands=["ls src"],
        ),
        turn("u-410", "u-410", "user", "human", day + "01:00.000Z", "Where is the tokenizer module?"),
        turn("a-410", "u-410", "assistant", "assistant_text", day + "01:02.000Z", "Let me list the source folder."),
        turn(
            "a-411",
            "u-410",
            "assistant",
            "tool_only",
            day + "01:03.000Z",
            "",
            [{"tool": "Bash", "call_id": "t3", "target": "ls src", "ok": True, "error_head": None}],
        ),
        turn("a-412", "u-410", "assistant", "assistant_text", day + "01:04.000Z", "It is src/tokenizer.py."),
        exchange("u-420", 3, day + "02:00.000Z", day + "02:01.000Z", True),
        turn("u-420", "u-420", "user", "human", day + "02:00.000Z", "Thanks, that is all."),
        turn("a-420", "u-420", "assistant", "assistant_text", day + "02:01.000Z", "Done."),
        exchange("u-430", 4, day + "09:00.000Z", day + "09:00.000Z", False),
        turn("u-430", "u-430", "user", "human", day + "09:00.000Z", "One more open question."),
    ]


def main() -> None:
    root = os.environ.get("VAULT_BUILDER_ROOT")
    if not root:
        raise SystemExit("Set VAULT_BUILDER_ROOT to a vault-builder checkout with the v2 renderer.")
    sys.path.insert(0, str(Path(root)))
    from tools.wiki.lib import session_capture as capture

    long_path = NORMALIZED / "long_continued.jsonl"
    long_path.write_text(
        "".join(json.dumps(line, ensure_ascii=False, separators=(",", ":")) + "\n" for line in _long_session_lines()),
        encoding="utf-8",
    )

    def render(name: str, part: int, *, last_turn_uuid: str | None = None) -> None:
        session = capture.read_normalized(NORMALIZED / name, capture.parse_turn_at)
        chosen = capture.select_part_exchanges(
            session, last_exchange_id=None, last_turn_uuid=last_turn_uuid, last_turn_at=None
        )
        body, redactions = capture.render_v2_body(chosen, capture.format_turn_at, capture.redact, capture._clean_text)
        first_turn = chosen[0].turns[0]
        last_turn = chosen[-1].turns[-1]
        frontmatter: dict[str, Any] = {
            "schema": capture.SESSION_SCHEMA_V2,
            "renderer": capture.RENDERER,
            "source_schema": capture.SOURCE_SCHEMA,
            "agent": session.agent,
            "session_id": session.session_id,
            "project": session.project or "",
            "cwd": session.cwd or "",
            "part": part,
            "first_exchange_id": chosen[0].exchange.exchange_id,
            "last_exchange_id": chosen[-1].exchange.exchange_id,
            "first_turn_uuid": first_turn.turn_id,
            "first_turn_at": capture.format_turn_at(first_turn.at),
            "last_turn_uuid": last_turn.turn_id,
            "last_turn_at": capture.format_turn_at(last_turn.at),
            "exchange_count": len(chosen),
            "turn_count": sum(len(item.turns) for item in chosen),
            "collected_at": COLLECTED_AT,
            "trigger": TRIGGER,
            "redactions": redactions,
            "body_sha256": "",
        }
        text = capture._session_text(frontmatter, body)
        OUTPUT.mkdir(parents=True, exist_ok=True)
        target = OUTPUT / f"{first_turn.at.date().isoformat()}-{session.session_id}-part{part}.md"
        target.write_bytes(text.encode("utf-8"))

    render("with_origin.jsonl", 1)
    render("subagent_compact.jsonl", 1)
    # Part 1 holds every closed exchange. Part 3 continues after a v1 part 2 whose cursor was the
    # second turn of u-410, so u-410 is a continued exchange there, and u-410 and u-420 are in two files.
    render("long_continued.jsonl", 1)
    render("long_continued.jsonl", 3, last_turn_uuid="a-410")


if __name__ == "__main__":
    main()
