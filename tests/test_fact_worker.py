"""Session fact worker: queue, lock, cache, attachment through the Vault command, failure log.

Spec 2026-11-16 longmemeval-session-memory D16, D20, I2, I7, F7, F8, F9, F10, A15, A16, A19, A25. The Vault command
is a fake `tools/wiki/cli.py` that follows docs/contracts/vault-session-facts-v1.md; the extractor is the conftest fake.
"""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import socket
import subprocess
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, NoReturn

import pytest
from typer.testing import CliRunner

from tests.conftest import FakeFactExtractor, FakeLlamaHealth
from tests.test_cli_setup import _deterministic_text_embeddings
from vault_graph.interface.cli.main import app
from vault_graph.interface.composition.adapters import fact_extractor_selection, fact_worker
from vault_graph.interface.composition.adapters.fact_cache import FactCache, exchange_content_hash, fact_cache_dir
from vault_graph.interface.composition.adapters.fact_extractor import (
    ExtractedFact,
    FactExtractorUnavailable,
    FactOutputInvalid,
)
from vault_graph.interface.composition.adapters.fact_queue import (
    FactJobInvalid,
    enqueue_fact_job,
    list_fact_jobs,
    read_fact_job,
)
from vault_graph.interface.composition.adapters.fact_worker import (
    FACTS_WORKER_LOCK,
    read_fact_failures,
    run_fact_worker,
    start_fact_worker,
)
from vault_graph.interface.composition.adapters.vault_attach_facts_cli import run_attach_facts
from vault_graph.interface.composition.read_only_service_factory import ReadOnlyServiceFactory
from vault_graph.operation.scope.facts_settings import (
    FactsSettings,
    default_facts_settings,
    facts_failures_path,
    facts_settings_path,
    save_facts_settings,
)

runner = CliRunner()
SETTINGS = default_facts_settings("claude")
SESSION_ID = "45d576f0-4bf0-56dd-8201-703456b8e6f4"
START = datetime(2026, 11, 16, 3, 0, tzinfo=UTC)

FAKE_ATTACH = r"""
import argparse, hashlib, json, pathlib, re, sys
LOG = pathlib.Path(__LOG__)
parser = argparse.ArgumentParser()
sub = parser.add_subparsers(dest="group", required=True)
sessions = sub.add_parser("sessions").add_subparsers(dest="command", required=True)
attach = sessions.add_parser("attach-facts")
attach.add_argument("--session", required=True)
attach.add_argument("--facts", required=True)
attach.add_argument("--json", action="store_true")
args = parser.parse_args()
part = pathlib.Path(args.session)
part = part if part.is_absolute() else pathlib.Path.cwd() / part
payload = json.loads(pathlib.Path(args.facts).read_text(encoding="utf-8"))
with LOG.open("a", encoding="utf-8") as log:
    log.write(json.dumps({"argv": sys.argv[1:], "cwd": str(pathlib.Path.cwd()), "input": payload}) + "\n")
target = part.with_name(part.name[:-3] + ".facts.md")
relative = str(target.relative_to(pathlib.Path.cwd()))
def answer(status, code, reason=None):
    print(json.dumps({"status": status, "path": relative, "reason": reason, "facts": len(payload["facts"])}))
    sys.exit(code)
if target.exists():
    answer("exists", 0)
if (LOG.parent / "reject").exists():
    answer("rejected", 1, (LOG.parent / "reject").read_text().strip())
if hashlib.sha256(part.read_bytes()).hexdigest() != payload["source_sha256"]:
    answer("rejected", 1, "source_mismatch")
ids = set(re.findall(r"<!-- vg:exchange id=(\S+)", part.read_text(encoding="utf-8")))
if any(fact["exchange_id"] not in ids for fact in payload["facts"]):
    answer("rejected", 1, "unknown_exchange")
lines = [f"- {f['date']} {f['text']} (exchange {f['exchange_id']})" for f in payload["facts"]]
target.write_text("---\nschema: vault-session-facts/v1\n---\n\n" + "\n".join(lines) + "\n", encoding="utf-8")
answer("written", 0)
"""

OLD_VAULT_CLI = r"""
import argparse
parser = argparse.ArgumentParser()
sub = parser.add_subparsers(dest="group", required=True)
sessions = sub.add_parser("sessions").add_subparsers(dest="command", required=True)
sessions.add_parser("capture")
parser.parse_args()
"""


def exchange(exchange_id: str, started: str, user: str, assistant: str) -> str:
    return (
        f"## {user} {started} · {exchange_id}\n"
        f"<!-- vg:exchange id={exchange_id} scope=main started={started} ended={started} tools= errors=0 "
        "outcome=answered files= -->\n\n"
        f"### user · {started} · {exchange_id}\n\n{user}\n\n"
        f"### assistant · {started} · a-{exchange_id}\n\n{assistant}\n"
    )


def part_text(part: int, *exchanges: str) -> str:
    return (
        "---\nschema: vault-session/v2\nagent: claude-code\n"
        f'session_id: "{SESSION_ID}"\npart: {part}\nfirst_turn_at: "2023-05-20T10:00:00.000Z"\n---\n\n'
        + "\n".join(exchanges)
    )


EX1 = exchange("x0001", "2023-05-20T10:00:00.000Z", "I inherited my grandmother's jewelry.", "Get an appraisal.")
EX2 = exchange("x0002", "2023-05-21T11:00:00.000Z", "Which appraiser is near Busan?", "Try the Haeundae shop.")
EX3 = exchange("x0003", "2023-05-22T09:00:00.000Z", "아버지 가구도 감정할까요?", "네, 같이 보세요.")


class Vault:
    def __init__(self, root: Path, log: Path) -> None:
        self.root = root
        self.log = log

    def add_part(self, relative: str, text: str) -> str:
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return relative

    def install_command(self, source: str = FAKE_ATTACH) -> None:
        cli = self.root / "tools" / "wiki" / "cli.py"
        cli.parent.mkdir(parents=True, exist_ok=True)
        cli.write_text(source.replace("__LOG__", repr(str(self.log))), encoding="utf-8")

    def calls(self) -> list[dict[str, Any]]:
        if not self.log.exists():
            return []
        return [json.loads(line) for line in self.log.read_text(encoding="utf-8").splitlines()]

    def files(self) -> dict[str, bytes]:
        return {
            path.relative_to(self.root).as_posix(): path.read_bytes()
            for path in sorted(self.root.rglob("*"))
            if path.is_file()
        }


@pytest.fixture
def vault(tmp_path: Path) -> Vault:
    (tmp_path / "outside").mkdir()
    created = Vault(tmp_path / "vault", tmp_path / "outside" / "attach-calls.jsonl")
    created.root.mkdir()
    created.install_command()
    return created


@pytest.fixture
def graph_home(tmp_path: Path) -> Path:
    home = tmp_path / "graph-home"
    home.mkdir()
    return home


PART1 = "raw/sessions/longmemeval/2023-05-20-45d576f0-4bf0-56dd-8201-703456b8e6f4-part1.md"
PART2 = "raw/sessions/longmemeval/2023-05-20-45d576f0-4bf0-56dd-8201-703456b8e6f4-part2.md"


def enqueue(graph_home: Path, vault: Vault, part: str) -> Path:
    return enqueue_fact_job(graph_home, vault_root=vault.root, vault="lme", part=part, now=START)


def run(graph_home: Path, at: datetime = START, settings: FactsSettings = SETTINGS) -> fact_worker.FactWorkerRun:
    result = run_fact_worker(graph_home, settings, now=lambda: at)
    assert result is not None
    return result


def fact(text: str, exchange_id: str, day: str = "2023-05-20") -> ExtractedFact:
    return ExtractedFact(text=text, date=day, exchange_id=exchange_id)


# Queue and lock (D16, F10).


def test_job_file_round_trips_and_rejects_paths_outside_the_vault(graph_home: Path, vault: Vault) -> None:
    path = enqueue(graph_home, vault, PART1)
    job = read_fact_job(path)
    assert (job.vault, job.vault_root, job.part) == ("lme", vault.root, PART1)
    assert json.loads(path.read_text())["schema"] == "vault-graph-facts-job/1"
    for bad in ("../x.md", "/abs/x.md", ""):
        with pytest.raises(FactJobInvalid):
            enqueue_fact_job(graph_home, vault_root=vault.root, vault="lme", part=bad)


def test_worker_drains_the_queue_and_writes_through_the_vault_command(
    graph_home: Path, vault: Vault, fake_fact_extractor: FakeFactExtractor
) -> None:
    vault.add_part(PART1, part_text(1, EX1, EX2))
    vault.add_part(PART2, part_text(2, EX3))
    before = vault.files()
    enqueue(graph_home, vault, PART1)
    enqueue(graph_home, vault, PART2)
    fake_fact_extractor.facts = [
        fact("User inherited jewelry.", "x0001"),
        fact("User looks for an appraiser near Busan.", "x0002", "2023-05-21"),
        fact("사용자는 아버지 가구 감정을 고민한다.", "x0003", "2023-05-22"),
    ]

    result = run(graph_home)

    assert [item.status for item in result.results] == ["written", "written"]
    assert list_fact_jobs(graph_home) == []
    after = vault.files()
    changed = {name for name in after if before.get(name) != after[name]}
    assert changed == {PART1[:-3] + ".facts.md", PART2[:-3] + ".facts.md"}
    assert {name: after[name] for name in before} == before
    calls = vault.calls()
    assert [call["cwd"] for call in calls] == [str(vault.root)] * 2
    assert [call["argv"][:4] for call in calls] == [
        ["sessions", "attach-facts", "--session", str(vault.root / PART1)],
        ["sessions", "attach-facts", "--session", str(vault.root / PART2)],
    ]
    assert all(call["argv"][4] == "--facts" and call["argv"][-1] == "--json" for call in calls)
    first = calls[0]["input"]
    assert first == {
        "schema": "vault-session-facts-input/1",
        "session_id": SESSION_ID,
        "source_sha256": hashlib.sha256((vault.root / PART1).read_bytes()).hexdigest(),
        "extractor": "claude",
        "model": SETTINGS.model,
        "facts": [
            {"date": "2023-05-20", "text": "User inherited jewelry.", "exchange_id": "x0001"},
            {"date": "2023-05-21", "text": "User looks for an appraiser near Busan.", "exchange_id": "x0002"},
        ],
    }
    assert calls[1]["input"]["facts"] == [
        {"date": "2023-05-22", "text": "사용자는 아버지 가구 감정을 고민한다.", "exchange_id": "x0003"}
    ]
    assert not facts_failures_path(graph_home).exists() or read_fact_failures(graph_home) == []
    assert list((graph_home / "facts" / "inputs").iterdir()) == []


def test_extractor_gets_exchange_ids_dates_and_text(
    graph_home: Path, vault: Vault, fake_fact_extractor: FakeFactExtractor
) -> None:
    vault.add_part(PART1, part_text(1, EX1, EX3))
    enqueue(graph_home, vault, PART1)
    run(graph_home)
    [call] = fake_fact_extractor.calls
    assert [(item.exchange_id, item.date) for item in call] == [("x0001", "2023-05-20"), ("x0003", "2023-05-22")]
    assert "I inherited my grandmother's jewelry." in call[0].text and "vg:exchange" not in call[0].text
    assert "아버지 가구도 감정할까요?" in call[1].text
    assert fake_fact_extractor.settings == [SETTINGS]


def test_a_second_worker_does_nothing_while_the_lock_is_held(
    graph_home: Path, vault: Vault, fake_fact_extractor: FakeFactExtractor
) -> None:
    vault.add_part(PART1, part_text(1, EX1))
    job = enqueue(graph_home, vault, PART1)
    (graph_home / "logs").mkdir()
    holder = os.open(graph_home / FACTS_WORKER_LOCK, os.O_RDWR | os.O_CREAT, 0o644)
    try:
        fcntl.flock(holder, fcntl.LOCK_EX | fcntl.LOCK_NB)
        assert run_fact_worker(graph_home, SETTINGS, now=lambda: START) is None
    finally:
        os.close(holder)
    assert job.exists() and fake_fact_extractor.calls == [] and vault.calls() == []
    run(graph_home)
    assert not job.exists()


def test_jobs_added_while_the_worker_runs_are_taken_in_the_same_run(
    graph_home: Path, vault: Vault, fake_fact_extractor: FakeFactExtractor
) -> None:
    vault.add_part(PART1, part_text(1, EX1))
    vault.add_part(PART2, part_text(2, EX2))
    enqueue(graph_home, vault, PART1)
    added: list[bool] = []

    def extract_and_enqueue(exchanges: object) -> list[ExtractedFact]:
        if not added:
            added.append(True)
            enqueue(graph_home, vault, PART2)
        return [fact("A fact.", "x0001"), fact("Another fact.", "x0002")]

    fake_fact_extractor.extract = extract_and_enqueue  # type: ignore[method-assign]
    result = run(graph_home)
    assert [item.status for item in result.results] == ["written", "written"]
    assert list_fact_jobs(graph_home) == []


def test_start_fact_worker_starts_nothing_while_the_lock_is_held(
    graph_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def refuse(*args: object, **kwargs: object) -> None:
        raise AssertionError("no worker may start while the lock is held")

    monkeypatch.setattr(subprocess, "Popen", refuse)
    (graph_home / "logs").mkdir()
    holder = os.open(graph_home / FACTS_WORKER_LOCK, os.O_RDWR | os.O_CREAT, 0o644)
    try:
        fcntl.flock(holder, fcntl.LOCK_EX | fcntl.LOCK_NB)
        assert start_fact_worker(graph_home) is False
    finally:
        os.close(holder)


def test_start_fact_worker_detaches_a_process_that_holds_the_lock(
    graph_home: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    marker = tmp_path / "child-argv.json"
    # The child only records its arguments and sleeps, so no real extractor can run in it.
    script = f"import json, sys, time; open({str(marker)!r}, 'w').write(json.dumps(sys.argv[1:])); time.sleep(1.5)"
    monkeypatch.setattr(fact_worker, "_WORKER_SCRIPT", script)

    started = time.monotonic()
    assert start_fact_worker(graph_home, cache_dir=tmp_path / "shared-cache") is True
    assert time.monotonic() - started < 1.0
    assert start_fact_worker(graph_home) is False
    deadline = time.monotonic() + 5
    while not marker.exists() and time.monotonic() < deadline:
        time.sleep(0.05)
    argv = json.loads(marker.read_text())
    assert argv[:4] == ["facts", "worker", "--graph-home", str(graph_home)]
    assert argv[4] == "--lock-fd" and argv[6:] == ["--cache-dir", str(tmp_path / "shared-cache")]
    probe = os.open(graph_home / FACTS_WORKER_LOCK, os.O_RDWR)
    try:
        deadline = time.monotonic() + 10
        while True:
            try:
                fcntl.flock(probe, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                assert time.monotonic() < deadline, "the child never released the lock"
                time.sleep(0.05)
    finally:
        os.close(probe)


# Cache (D20).


def test_an_exchange_seen_before_is_not_extracted_again_in_a_new_part(
    graph_home: Path, vault: Vault, fake_fact_extractor: FakeFactExtractor
) -> None:
    vault.add_part(PART1, part_text(1, EX1))
    enqueue(graph_home, vault, PART1)
    fake_fact_extractor.facts = [fact("User inherited jewelry.", "x0001")]
    run(graph_home)

    vault.add_part(PART2, part_text(2, EX1, EX2))
    enqueue(graph_home, vault, PART2)
    fake_fact_extractor.facts = [fact("User looks for an appraiser.", "x0002", "2023-05-21")]
    run(graph_home)

    assert [[item.exchange_id for item in call] for call in fake_fact_extractor.calls] == [["x0001"], ["x0002"]]
    assert [item["exchange_id"] for item in vault.calls()[1]["input"]["facts"]] == ["x0001", "x0002"]


def test_cache_key_is_extractor_model_schema_version_and_content(tmp_path: Path) -> None:
    cache = FactCache(tmp_path / "cache")
    content = exchange_content_hash("text")
    cache.put("claude", "m1", content, [])
    assert cache.get("claude", "m1", content) == []
    assert cache.get("claude", "m2", content) is None
    assert cache.get("llama-server", "m1", content) is None
    assert cache.get("claude", "m1", exchange_content_hash("other")) is None


def test_a_shared_cache_folder_serves_another_graph_home(
    tmp_path: Path, vault: Vault, fake_fact_extractor: FakeFactExtractor
) -> None:
    shared = tmp_path / "shared-cache"
    vault.add_part(PART1, part_text(1, EX1))
    vault.add_part(PART2, part_text(2, EX1))
    fake_fact_extractor.facts = [fact("User inherited jewelry.", "x0001")]
    for index, part in enumerate((PART1, PART2)):
        home = tmp_path / f"home-{index}"
        enqueue_fact_job(home, vault_root=vault.root, vault="lme", part=part)
        assert run_fact_worker(home, SETTINGS, cache_dir=shared) is not None
    assert len(fake_fact_extractor.calls) == 1
    assert not fact_cache_dir(tmp_path / "home-0").exists()


def test_a_different_model_misses_the_cache(
    graph_home: Path, vault: Vault, fake_fact_extractor: FakeFactExtractor
) -> None:
    vault.add_part(PART1, part_text(1, EX1))
    vault.add_part(PART2, part_text(2, EX1))
    enqueue(graph_home, vault, PART1)
    run(graph_home)
    enqueue(graph_home, vault, PART2)
    run(graph_home, settings=default_facts_settings("llama-server"))
    assert len(fake_fact_extractor.calls) == 2


# Extractor failures (F7, F8).


def test_extractor_unavailable_keeps_the_job_and_waits_30_minutes(
    graph_home: Path, vault: Vault, fake_fact_extractor: FakeFactExtractor
) -> None:
    vault.add_part(PART1, part_text(1, EX1))
    job = enqueue(graph_home, vault, PART1)
    fake_fact_extractor.error = FactExtractorUnavailable("claude is not logged in")

    first = run(graph_home)
    assert [(item.status, item.reason) for item in first.results] == [("waiting", "extractor_unavailable")]
    assert job.exists()
    [failure] = read_fact_failures(graph_home)
    assert (failure.job, failure.vault, failure.part, failure.reason) == (
        job.name,
        "lme",
        PART1,
        "extractor_unavailable",
    )
    assert failure.message == "claude is not logged in"
    assert (failure.failed_at, failure.retry_after, failure.closed) == (
        "2026-11-16T03:00:00Z",
        "2026-11-16T03:30:00Z",
        False,
    )
    assert isinstance(json.loads(facts_failures_path(graph_home).read_text()), list)

    held = run(graph_home, START + timedelta(minutes=29))
    assert held.results == () and held.held_back == (job.name,)
    assert len(fake_fact_extractor.calls) == 1

    fake_fact_extractor.error = None
    fake_fact_extractor.facts = [fact("User inherited jewelry.", "x0001")]
    retried = run(graph_home, START + timedelta(minutes=30))
    assert [item.status for item in retried.results] == ["written"]
    assert not job.exists() and read_fact_failures(graph_home) == []


def test_after_the_extractor_fails_the_same_run_does_not_call_it_again(
    graph_home: Path, vault: Vault, fake_fact_extractor: FakeFactExtractor
) -> None:
    vault.add_part(PART1, part_text(1, EX1))
    vault.add_part(PART2, part_text(2, EX2))
    enqueue(graph_home, vault, PART1)
    enqueue(graph_home, vault, PART2)
    fake_fact_extractor.error = FactExtractorUnavailable("usage limit")
    result = run(graph_home)
    assert [item.reason for item in result.results] == ["extractor_unavailable"] * 2
    assert len(fake_fact_extractor.calls) == 1
    assert len(list_fact_jobs(graph_home)) == 2


def test_schema_error_fails_the_job(graph_home: Path, vault: Vault, fake_fact_extractor: FakeFactExtractor) -> None:
    vault.add_part(PART1, part_text(1, EX1))
    job = enqueue(graph_home, vault, PART1)
    fake_fact_extractor.error = FactOutputInvalid("fact extractor answer is not JSON")
    result = run(graph_home)
    assert [(item.status, item.reason) for item in result.results] == [("waiting", "extractor_output_invalid")]
    assert job.exists() and vault.calls() == []
    [failure] = read_fact_failures(graph_home)
    assert failure.retry_after == "2026-11-16T03:30:00Z"


@pytest.mark.parametrize(
    "bad", [fact("x" * 401, "x0001"), fact("Bad date.", "x0001", "2023-02-30"), fact("Bad date.", "x0001", "May 20")]
)
def test_facts_off_the_schema_fail_the_job(
    graph_home: Path, vault: Vault, fake_fact_extractor: FakeFactExtractor, bad: ExtractedFact
) -> None:
    vault.add_part(PART1, part_text(1, EX1))
    job = enqueue(graph_home, vault, PART1)
    fake_fact_extractor.facts = [bad]
    result = run(graph_home)
    assert [item.reason for item in result.results] == ["extractor_output_invalid"]
    assert job.exists() and vault.calls() == []


def test_unknown_exchange_ids_and_empty_texts_are_dropped(
    graph_home: Path, vault: Vault, fake_fact_extractor: FakeFactExtractor
) -> None:
    vault.add_part(PART1, part_text(1, EX1))
    enqueue(graph_home, vault, PART1)
    fake_fact_extractor.facts = [
        fact("Kept.", "x0001"),
        fact("Not in this part.", "x0999"),
        fact("   ", "x0001"),
        fact("Two\nlines.", "x0001"),
    ]
    result = run(graph_home)
    assert [item.status for item in result.results] == ["written"]
    assert [item["text"] for item in vault.calls()[0]["input"]["facts"]] == ["Kept.", "Two lines."]


def test_no_facts_left_means_no_command_call_and_a_no_facts_cache_entry(
    graph_home: Path, vault: Vault, fake_fact_extractor: FakeFactExtractor
) -> None:
    vault.add_part(PART1, part_text(1, EX1))
    job = enqueue(graph_home, vault, PART1)
    fake_fact_extractor.facts = [fact("Not in this part.", "x0999")]
    result = run(graph_home)
    assert [item.status for item in result.results] == ["no_facts"]
    assert vault.calls() == [] and not job.exists() and read_fact_failures(graph_home) == []
    assert (
        FactCache(fact_cache_dir(graph_home)).get("claude", SETTINGS.model, exchange_content_hash(_exchange_text(EX1)))
        == []
    )

    vault.add_part(PART2, part_text(2, EX1))
    enqueue(graph_home, vault, PART2)
    run(graph_home)
    assert len(fake_fact_extractor.calls) == 1 and vault.calls() == []


def _exchange_text(block: str) -> str:
    return "\n".join(block.splitlines()[2:]).strip()


# Vault command (F9, I7).


@pytest.mark.parametrize("old_command", [None, OLD_VAULT_CLI])
def test_missing_command_records_writer_missing_and_later_writes_from_the_cache(
    graph_home: Path, vault: Vault, fake_fact_extractor: FakeFactExtractor, old_command: str | None
) -> None:
    cli = vault.root / "tools" / "wiki" / "cli.py"
    if old_command is None:
        cli.unlink()
    else:
        vault.install_command(old_command)
    vault.add_part(PART1, part_text(1, EX1))
    job = enqueue(graph_home, vault, PART1)
    fake_fact_extractor.facts = [fact("User inherited jewelry.", "x0001")]

    first = run(graph_home)
    assert [(item.status, item.reason) for item in first.results] == [("waiting", "facts_writer_missing")]
    [failure] = read_fact_failures(graph_home)
    assert (failure.reason, failure.retry_after, failure.closed) == ("facts_writer_missing", None, False)
    assert job.exists()

    vault.install_command()
    fake_fact_extractor.facts = []
    second = run(graph_home, START + timedelta(minutes=1))
    assert [item.status for item in second.results] == ["written"]
    assert len(fake_fact_extractor.calls) == 1
    assert vault.calls()[0]["input"]["facts"][0]["text"] == "User inherited jewelry."
    assert read_fact_failures(graph_home) == []


def test_rejected_closes_the_job_with_the_reason(
    graph_home: Path, vault: Vault, fake_fact_extractor: FakeFactExtractor
) -> None:
    vault.add_part(PART1, part_text(1, EX1))
    job = enqueue(graph_home, vault, PART1)
    (vault.log.parent / "reject").write_text("secret\n")
    fake_fact_extractor.facts = [fact("password is hunter2", "x0001")]
    result = run(graph_home)
    assert [(item.status, item.reason, item.message) for item in result.results] == [
        ("closed", "attach_rejected", "secret")
    ]
    assert not job.exists()
    [failure] = read_fact_failures(graph_home)
    assert (failure.reason, failure.message, failure.closed, failure.retry_after) == (
        "attach_rejected",
        "secret",
        True,
        None,
    )


def test_a_changed_part_is_rejected_by_the_vault_command(
    graph_home: Path, vault: Vault, fake_fact_extractor: FakeFactExtractor, monkeypatch: pytest.MonkeyPatch
) -> None:
    vault.add_part(PART1, part_text(1, EX1))
    enqueue(graph_home, vault, PART1)
    fake_fact_extractor.facts = [fact("User inherited jewelry.", "x0001")]
    real = run_attach_facts

    def change_then_attach(vault_root: Path, part_path: Path, input_path: Path) -> object:
        part_path.write_text(part_path.read_text() + "\nchanged\n")
        return real(vault_root, part_path, input_path)

    result = run_fact_worker(graph_home, SETTINGS, now=lambda: START, attach=change_then_attach)  # type: ignore[arg-type]
    assert result is not None
    assert [(item.status, item.message) for item in result.results] == [("closed", "source_mismatch")]


def test_exists_is_success(graph_home: Path, vault: Vault, fake_fact_extractor: FakeFactExtractor) -> None:
    vault.add_part(PART1, part_text(1, EX1))
    vault.add_part(PART1[:-3] + ".facts.md", "already there\n")
    before = vault.files()
    job = enqueue(graph_home, vault, PART1)
    fake_fact_extractor.facts = [fact("User inherited jewelry.", "x0001")]
    result = run(graph_home)
    assert [item.status for item in result.results] == ["exists"]
    assert not job.exists() and read_fact_failures(graph_home) == []
    assert vault.files() == before


def test_command_without_result_line_keeps_the_job_for_30_minutes(
    graph_home: Path, vault: Vault, fake_fact_extractor: FakeFactExtractor
) -> None:
    vault.install_command("import sys\nprint('Traceback: boom', file=sys.stderr)\nsys.exit(1)\n")
    vault.add_part(PART1, part_text(1, EX1))
    job = enqueue(graph_home, vault, PART1)
    fake_fact_extractor.facts = [fact("User inherited jewelry.", "x0001")]
    result = run(graph_home)
    assert [(item.status, item.reason) for item in result.results] == [("waiting", "facts_writer_failed")]
    assert job.exists()
    assert read_fact_failures(graph_home)[0].retry_after == "2026-11-16T03:30:00Z"


def test_missing_part_or_broken_job_is_closed(
    graph_home: Path, vault: Vault, fake_fact_extractor: FakeFactExtractor
) -> None:
    enqueue(graph_home, vault, PART1)
    broken = graph_home / "facts" / "queue" / "zz-broken.json"
    broken.write_text("{not json", encoding="utf-8")
    result = run(graph_home)
    assert sorted((item.status, item.reason) for item in result.results) == [
        ("closed", "job_invalid"),
        ("closed", "part_unreadable"),
    ]
    assert list_fact_jobs(graph_home) == [] and fake_fact_extractor.calls == [] and vault.calls() == []


# CLI.


def initialized_home(tmp_path: Path, vault: Vault) -> Path:
    home = tmp_path / "state"
    result = runner.invoke(app, ["init", "--vault", str(vault.root), "--graph-home", str(home)])
    assert result.exit_code == 0, result.output
    return home


def test_vg_facts_worker_drains_the_queue_and_status_reads_the_failure_log(
    tmp_path: Path, vault: Vault, fake_fact_extractor: FakeFactExtractor
) -> None:
    home = initialized_home(tmp_path, vault)
    vault.add_part(PART1, part_text(1, EX1))
    vault.add_part(PART2, part_text(2, EX2))
    enqueue(home, vault, PART1)
    (vault.log.parent / "reject").write_text("secret\n")
    fake_fact_extractor.facts = [fact("A fact.", "x0001")]

    result = runner.invoke(app, ["facts", "worker", "--graph-home", str(home)])
    assert result.exit_code == 0, result.output
    assert "closed attach_rejected: secret" in result.output

    status = runner.invoke(app, ["facts", "status", "--graph-home", str(home)])
    assert "queue: 0" in status.output and "failures: 1" in status.output


def test_vg_facts_worker_does_nothing_when_facts_are_off(
    tmp_path: Path, vault: Vault, fake_fact_extractor: FakeFactExtractor
) -> None:
    home = initialized_home(tmp_path, vault)
    save_facts_settings(facts_settings_path(home), FactsSettings(False, "claude", None, SETTINGS.model))
    vault.add_part(PART1, part_text(1, EX1))
    job = enqueue(home, vault, PART1)
    result = runner.invoke(app, ["facts", "worker", "--graph-home", str(home)])
    assert result.exit_code == 0 and "off" in result.output
    assert job.exists() and fake_fact_extractor.calls == []


# A25: tests never reach a real extractor.


def test_building_a_real_extractor_fails_the_test() -> None:
    with pytest.raises(pytest.fail.Exception, match="real fact extractor"):
        fact_extractor_selection.construct_real_fact_extractor(SETTINGS)


# A15: search, index, MCP search and session start call no model.


def test_search_index_mcp_and_session_start_pass_with_processes_and_network_blocked(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from vault_graph.interface.mcp.context_pack_resource_cache import ContextPackResourceCache
    from vault_graph.interface.mcp.mcp_service_factory import McpServiceFactory
    from vault_graph.interface.mcp.mcp_tools import McpToolRegistry, parse_ask_vault_input, parse_search_vault_input
    from vault_graph.interface.mcp.result_explanation_cache import ResultExplanationCache

    monkeypatch.setattr("vault_graph.interface.cli.main._text_embeddings", _deterministic_text_embeddings)
    monkeypatch.setattr(
        ReadOnlyServiceFactory, "_search_text_embeddings", lambda _self, config: _deterministic_text_embeddings(config)
    )
    vault_root = tmp_path / "vault"
    (vault_root / "wiki").mkdir(parents=True)
    (vault_root / "wiki" / "jewelry.md").write_text("# Jewelry\nThe appraisal of inherited jewelry.\n")
    parts = vault_root / PART1
    parts.parent.mkdir(parents=True)
    parts.write_text(part_text(1, EX1), encoding="utf-8")
    (vault_root / (PART1[:-3] + ".facts.md")).write_text(
        "---\nschema: vault-session-facts/v1\nagent: claude-code\n"
        f'session_id: "{SESSION_ID}"\npart: 1\nsource: {PART1}\nsource_sha256: "0"\nextractor: claude\n'
        'model: claude-sonnet-5-5\ngenerated_at: "2026-11-16T03:00:00Z"\nfact_count: 1\n---\n\n'
        "- 2023-05-20 User inherited jewelry. (exchange x0001)\n",
        encoding="utf-8",
    )
    home = tmp_path / "state"
    initialized = runner.invoke(
        app, ["init", "--vault", str(vault_root), "--vault-id", "main", "--graph-home", str(home)]
    )
    assert initialized.exit_code == 0, initialized.output
    on = runner.invoke(app, ["facts", "on", "--graph-home", str(home)])
    assert on.exit_code == 0, on.output
    repo = tmp_path.resolve() / "repo"
    repo.mkdir()
    subprocess.run(["git", "-C", str(repo), "init", "-q"], check=True)
    vault_map = tmp_path / "map" / "vault-map.json"
    vault_map.parent.mkdir()
    vault_map.write_text(
        json.dumps(
            {
                "version": 2,
                "vaults": {"main": {"path": str(vault_root.resolve()), "role": "personal", "sharable": True}},
                "projects": {"repo": {"root": str(repo), "vaults": ["main"]}},
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / "claude"))

    attempts: list[str] = []
    real_popen, real_run = subprocess.Popen, subprocess.run

    def is_git(args: tuple[object, ...]) -> bool:
        command = args[0] if args else None
        return isinstance(command, list | tuple) and bool(command) and Path(str(command[0])).name == "git"

    def blocked(*args: object, **kwargs: object) -> NoReturn:
        attempts.append(repr(args[:1]))
        raise OSError("blocked by test: no subprocess or network")

    def popen(*args: Any, **kwargs: Any) -> object:
        # Session start finds the project root with `git`. Every other process is refused.
        return real_popen(*args, **kwargs) if is_git(args) else blocked(*args)

    def run_process(*args: Any, **kwargs: Any) -> object:
        return real_run(*args, **kwargs) if is_git(args) else blocked(*args)

    monkeypatch.setattr(subprocess, "Popen", popen)
    monkeypatch.setattr(subprocess, "run", run_process)
    monkeypatch.setattr(socket.socket, "connect", blocked)
    monkeypatch.setattr(socket.socket, "connect_ex", blocked)
    monkeypatch.setattr(socket, "create_connection", blocked)
    monkeypatch.setattr(socket, "getaddrinfo", blocked)

    indexed = runner.invoke(app, ["index", "--graph-home", str(home)])
    assert indexed.exit_code == 0, indexed.output
    searched = runner.invoke(app, ["search", "--graph-home", str(home), "inherited jewelry"])
    assert searched.exit_code == 0, searched.output
    assert "jewelry" in searched.output.lower()

    factory = McpServiceFactory(graph_home_path=home)
    registry = McpToolRegistry(
        services=factory.open_read_only(),
        service_factory=factory,
        context_pack_cache=ContextPackResourceCache(),
        result_explanation_cache=ResultExplanationCache(),
    )
    assert registry.search_vault(parse_search_vault_input(query="inherited jewelry")).payload["results"]
    assert registry.ask_vault(parse_ask_vault_input(question="What was inherited?")).payload is not None

    session_start = runner.invoke(
        app,
        ["hook", "session-start", "--graph-home", str(home), "--vault-map", str(vault_map)],
        input=json.dumps({"cwd": str(repo), "session_id": "s-1", "source": "startup"}),
    )
    assert session_start.exit_code == 0, session_start.output
    # The only refused process is the session start catch-up `vg index`. No model and no connection was tried.
    assert attempts and all("run_catch_up_index" in attempt for attempt in attempts), attempts


# Tool call lines (spec 2026-11-25-facts-extractor-auto D1, D2, D3, F7, F8, A1, A2).

TOOL_EXCHANGE_ID = "x0004"
TOOL_STARTED = "2023-05-23T09:00:00.000Z"
TOOL_EXCHANGE = (
    f"## Fix the build {TOOL_STARTED} · {TOOL_EXCHANGE_ID}\n"
    f"<!-- vg:exchange id={TOOL_EXCHANGE_ID} scope=main started={TOOL_STARTED} ended={TOOL_STARTED} "
    "tools=Bash:2,Read:1,mcp__ccd_turn__update_plan:1 errors=1 outcome=answered files= -->\n\n"
    f"### user · {TOOL_STARTED} · u-{TOOL_EXCHANGE_ID}\n\n"
    "Fix the build.\n- Read the error first\n- Bash is fine\n\n"
    f"### assistant · {TOOL_STARTED} · a1-{TOOL_EXCHANGE_ID}\n\n"
    "- mcp__ccd_turn__update_plan\n- Bash `uv run pytest -q`\n\n"
    f"### assistant · {TOOL_STARTED} · a2-{TOOL_EXCHANGE_ID}\n\n"
    "The build failed because of a missing import. Tools: none needed beyond pytest.\n"
    "- Readme stays\n- Grep not in meta\n\n"
    "- Read `src/app.py`\n- Bash `uv run pytest -q` ✗: ImportError: no module named x\n"
)
ONLY_TOOLS_ID = "x0005"
ONLY_TOOLS_EXCHANGE = (
    f"## (continued) {TOOL_STARTED} · {ONLY_TOOLS_ID}\n"
    f"<!-- vg:exchange id={ONLY_TOOLS_ID} scope=main started={TOOL_STARTED} ended={TOOL_STARTED} "
    "tools=Bash:1 errors=0 outcome=answered continued=1 files= -->\n\n"
    f"### assistant · {TOOL_STARTED} · a-{ONLY_TOOLS_ID}\n\n- Bash `git status`\n"
)


def test_extractor_text_drops_tool_call_lines_outside_user_turns() -> None:
    body = TOOL_EXCHANGE.split("-->\n", 1)[1].strip()

    text = fact_worker.extractor_text(body, frozenset({"Bash", "Read", "mcp__ccd_turn__update_plan"}))

    assert text == (
        f"### user · {TOOL_STARTED} · u-{TOOL_EXCHANGE_ID}\n\n"
        "Fix the build.\n- Read the error first\n- Bash is fine\n\n"
        f"### assistant · {TOOL_STARTED} · a2-{TOOL_EXCHANGE_ID}\n\n"
        "The build failed because of a missing import. Tools: none needed beyond pytest.\n"
        "- Readme stays\n- Grep not in meta"
    )


def test_extractor_text_keeps_everything_without_meta_tools() -> None:
    body = TOOL_EXCHANGE.split("-->\n", 1)[1].strip()

    assert fact_worker.extractor_text(body, frozenset()) == body


def test_extractor_text_of_tool_lines_only_is_empty() -> None:
    body = ONLY_TOOLS_EXCHANGE.split("-->\n", 1)[1].strip()

    assert fact_worker.extractor_text(body, frozenset({"Bash"})) == ""


def test_worker_sends_less_text_and_keeps_ids_facts_and_cache_keys(
    graph_home: Path, vault: Vault, fake_fact_extractor: FakeFactExtractor
) -> None:
    from vault_graph.interface.composition.adapters.claude_fact_extractor import build_facts_prompt
    from vault_graph.interface.composition.adapters.fact_extractor import FactExchange

    vault.add_part(PART1, part_text(1, EX1, TOOL_EXCHANGE, ONLY_TOOLS_EXCHANGE))
    enqueue(graph_home, vault, PART1)
    fake_fact_extractor.facts = [
        fact("User inherited jewelry.", "x0001"),
        fact("The build failed on a missing import.", TOOL_EXCHANGE_ID, "2023-05-23"),
    ]

    result = run(graph_home)

    assert [item.status for item in result.results] == ["written"]
    [call] = fake_fact_extractor.calls
    assert [item.exchange_id for item in call] == ["x0001", TOOL_EXCHANGE_ID]
    raw = {item.exchange_id: item.text for item in fact_worker._read_part(vault.root / PART1).exchanges}
    unfiltered = [
        FactExchange(exchange_id=key, date=item.date, text=raw[key]) for key, item in zip(raw, call, strict=False)
    ]
    assert len(build_facts_prompt(call).encode()) < len(build_facts_prompt(unfiltered).encode())
    assert "uv run pytest" not in call[1].text and "missing import" in call[1].text
    assert len(vault.calls()[0]["input"]["facts"]) == 2
    cache = FactCache(fact_cache_dir(graph_home))
    for text in raw.values():
        assert cache.get("claude", SETTINGS.model, exchange_content_hash(text)) is not None
    assert cache.get("claude", SETTINGS.model, exchange_content_hash(raw[ONLY_TOOLS_ID])) == []


def test_a_part_of_tool_lines_only_never_calls_the_extractor(
    graph_home: Path, vault: Vault, fake_fact_extractor: FakeFactExtractor
) -> None:
    vault.add_part(PART1, part_text(1, ONLY_TOOLS_EXCHANGE))
    enqueue(graph_home, vault, PART1)

    result = run(graph_home)

    assert [item.status for item in result.results] == ["no_facts"]
    assert fake_fact_extractor.calls == []
    assert vault.calls() == []


# Picking the extractor per job (spec 2026-11-25-facts-extractor-auto D6, I1, I2, I3, F1, F2, F3, A5, A6).

AUTO = default_facts_settings("auto")
CLAUDE_NOW = FactsSettings(enabled=True, extractor="claude", endpoint=None, model=SETTINGS.model)
LLAMA_NOW = FactsSettings(enabled=True, extractor="llama-server", endpoint=AUTO.endpoint, model=AUTO.model)


def _last_job(graph_home: Path) -> dict[str, Any]:
    record: dict[str, Any] = json.loads((graph_home / "logs" / "facts-last-job.json").read_text(encoding="utf-8"))
    return record


def test_auto_uses_claude_when_llama_server_does_not_answer(
    graph_home: Path, vault: Vault, fake_fact_extractor: FakeFactExtractor, fake_llama_health: FakeLlamaHealth
) -> None:
    vault.add_part(PART1, part_text(1, EX1))
    vault.add_part(PART2, part_text(2, EX2))
    enqueue(graph_home, vault, PART1)
    enqueue(graph_home, vault, PART2)
    fake_fact_extractor.facts = [fact("User inherited jewelry.", "x0001"), fact("Busan appraiser.", "x0002")]

    result = run(graph_home, settings=AUTO)

    assert [item.status for item in result.results] == ["written", "written"]
    assert fake_llama_health.calls == [(AUTO.endpoint, 2.0), (AUTO.endpoint, 2.0)]
    assert fake_fact_extractor.settings == [CLAUDE_NOW]
    assert [(call["input"]["extractor"], call["input"]["model"]) for call in vault.calls()] == [
        ("claude", SETTINGS.model)
    ] * 2
    assert (
        FactCache(fact_cache_dir(graph_home)).get(
            "claude",
            SETTINGS.model,
            exchange_content_hash(fact_worker._read_part(vault.root / PART1).exchanges[0].text),
        )
        is not None
    )
    last = _last_job(graph_home)
    assert (last["status"], last["extractor"], last["model"], last["finished_at"]) == (
        "written",
        "claude",
        SETTINGS.model,
        "2026-11-16T03:00:00Z",
    )


def test_auto_uses_llama_server_when_it_answers(
    graph_home: Path, vault: Vault, fake_fact_extractor: FakeFactExtractor, fake_llama_health: FakeLlamaHealth
) -> None:
    vault.add_part(PART1, part_text(1, EX1))
    enqueue(graph_home, vault, PART1)
    fake_llama_health.up = True
    fake_fact_extractor.facts = [fact("User inherited jewelry.", "x0001")]

    run(graph_home, settings=AUTO)

    assert fake_fact_extractor.settings == [LLAMA_NOW]
    [call] = vault.calls()
    assert (call["input"]["extractor"], call["input"]["model"]) == ("llama-server", AUTO.model)
    assert (_last_job(graph_home)["extractor"], _last_job(graph_home)["model"]) == ("llama-server", AUTO.model)


def test_auto_job_fails_when_llama_server_stops_and_the_next_job_uses_claude(
    graph_home: Path,
    vault: Vault,
    monkeypatch: pytest.MonkeyPatch,
    fake_llama_health: FakeLlamaHealth,
) -> None:
    built: list[FactsSettings] = []

    class Extractor:
        def __init__(self, settings: FactsSettings) -> None:
            self.settings = settings

        def extract(self, exchanges: Any) -> list[ExtractedFact]:
            if self.settings.extractor == "llama-server":
                raise FactExtractorUnavailable("llama-server stopped")
            return [fact("Fact.", item.exchange_id) for item in exchanges]

    def construct(settings: FactsSettings) -> Extractor:
        built.append(settings)
        return Extractor(settings)

    monkeypatch.setattr(fact_extractor_selection, "_construct", construct)
    vault.add_part(PART1, part_text(1, EX1))
    vault.add_part(PART2, part_text(2, EX2))
    first_job = enqueue(graph_home, vault, PART1)
    enqueue(graph_home, vault, PART2)
    fake_llama_health.up = True

    result = run(graph_home, settings=AUTO)

    assert [(item.status, item.reason) for item in result.results] == [
        ("waiting", "extractor_unavailable"),
        ("written", None),
    ]
    assert built == [LLAMA_NOW, CLAUDE_NOW]
    assert len(fake_llama_health.calls) == 1
    assert first_job.exists()
    assert vault.calls()[0]["input"]["extractor"] == "claude"

    retried = run(graph_home, START + timedelta(minutes=30), settings=AUTO)
    assert len(fake_llama_health.calls) == 2
    assert [item.reason for item in retried.results] == ["extractor_unavailable"]


def test_fixed_llama_server_never_falls_back_to_claude(
    graph_home: Path, vault: Vault, fake_fact_extractor: FakeFactExtractor, fake_llama_health: FakeLlamaHealth
) -> None:
    llama = default_facts_settings("llama-server")
    vault.add_part(PART1, part_text(1, EX1))
    vault.add_part(PART2, part_text(2, EX2))
    enqueue(graph_home, vault, PART1)
    enqueue(graph_home, vault, PART2)
    fake_fact_extractor.error = FactExtractorUnavailable("llama-server did not answer")

    result = run(graph_home, settings=llama)

    assert [item.reason for item in result.results] == ["extractor_unavailable"] * 2
    assert fake_fact_extractor.settings == [llama]
    assert len(fake_fact_extractor.calls) == 1
    assert fake_llama_health.calls == []
    assert _last_job(graph_home)["extractor"] == "llama-server"


def test_fixed_claude_never_checks_llama_server(
    graph_home: Path, vault: Vault, fake_fact_extractor: FakeFactExtractor, fake_llama_health: FakeLlamaHealth
) -> None:
    vault.add_part(PART1, part_text(1, EX1))
    enqueue(graph_home, vault, PART1)
    fake_llama_health.up = True

    run(graph_home)

    assert fake_llama_health.calls == []
    assert fake_fact_extractor.settings == [SETTINGS]


def test_a_job_that_fails_before_picking_writes_no_last_job(graph_home: Path, vault: Vault) -> None:
    enqueue(graph_home, vault, "raw/sessions/longmemeval/missing-part1.md")

    run(graph_home, settings=AUTO)

    assert not (graph_home / "logs" / "facts-last-job.json").exists()
