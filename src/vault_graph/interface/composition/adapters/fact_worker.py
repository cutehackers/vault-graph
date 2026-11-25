"""The session fact worker (spec 2026-11-16 D16, D20, I2, I7, F7, F8, F9, F10).

One worker at a time drains `<graph-home>/facts/queue/` while it holds an flock on `logs/facts-worker.lock`.
`start_fact_worker` starts it as a detached process the way `start_catch_up_index` starts the session start
catch-up: the starter takes the lock without waiting, passes the locked descriptor to the child and does not wait.
A lock that is taken means a worker runs, so nothing starts. A worker that dies leaves its jobs in the queue for the
next one.

For each job the worker reads the part file, picks the extractor, hands the exchanges that have no cache entry to the
`FactExtractor`, caches what comes back per exchange, and writes the attachment only through the Vault command
`sessions attach-facts` (`vault_attach_facts_cli.py`). It never writes a Vault file itself.

Picking (spec 2026-11-25-facts-extractor-auto D6, I1, I2, I3). With `auto` every job checks whether llama-server
answers (`llama_health.py`) before it reads the cache, and uses `llama-server` or `claude`. The cache key, the
attachment's `extractor` and `model`, and the last job record hold that real choice, never `auto`. Once llama-server
fails as unavailable in a run, the later `auto` jobs of that run use `claude` without checking. A fixed extractor is
never swapped: once it fails as unavailable, the later jobs of the run fail without calling it.

What the extractor reads (spec 2026-11-25-facts-extractor-auto D1, D2, D3). Tool call lines (`- <tool>` or
`- <tool> <arguments>`, the tool named in the exchange meta `tools=`) outside `### user` turns are left out, and so is
a non-user turn that has nothing else. The cache key stays the hash of the exchange text as written in the part. An
exchange with nothing left goes to the cache as no facts and never to the extractor.

Last job record `logs/facts-last-job.json`, written after each job that picked an extractor:

    {"job": "<job file name>", "status": "<result status>", "extractor": "claude|llama-server",
     "model": "<model>", "finished_at": "<UTC ISO>"}

Failure log `logs/facts-failures.json` is a JSON list with one entry per job that failed last time it ran:

    {"job": "<job file name>", "vault": "<name or null>", "part": "<part path>", "reason": "<code>",
     "message": "<text>", "failed_at": "<UTC ISO>", "retry_after": "<UTC ISO or null>", "closed": false}

Reasons. The job stays in the queue (`closed: false`):
- `extractor_unavailable` (F7) and `extractor_output_invalid` (F8): retried after 30 minutes.
- `facts_writer_failed`: the Vault command ran but gave no usable result. Retried after 30 minutes.
- `facts_writer_missing` (F9): the Vault has no `sessions attach-facts`. Retried at the next run, from the cache.
The job is removed (`closed: true`):
- `attach_rejected`: the Vault command answered `rejected`. `message` holds the Vault reason code.
- `job_invalid`, `part_unreadable`: the job file or the part file cannot be used.
A job that succeeds (`written`, `exists`, or no facts left) removes its entry.
"""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from vault_graph.interface.composition.adapters import llama_health
from vault_graph.interface.composition.adapters.fact_cache import (
    CachedFact,
    FactCache,
    exchange_content_hash,
    fact_cache_dir,
)
from vault_graph.interface.composition.adapters.fact_extractor import (
    ExtractedFact,
    FactExchange,
    FactExtractor,
    FactExtractorUnavailable,
    FactOutputInvalid,
)
from vault_graph.interface.composition.adapters.fact_extractor_selection import select_fact_extractor
from vault_graph.interface.composition.adapters.fact_queue import (
    FactJob,
    FactJobInvalid,
    list_fact_jobs,
    read_fact_job,
    remove_fact_job,
)
from vault_graph.interface.composition.adapters.vault_attach_facts_cli import (
    ATTACH_FACTS_INPUT_SCHEMA,
    AttachFactsOutcome,
    run_attach_facts,
)
from vault_graph.operation.scope.facts_settings import (
    FactsSettings,
    facts_failures_path,
    facts_last_job_path,
    resolve_facts_settings,
)

FACTS_WORKER_LOCK = Path("logs") / "facts-worker.lock"
FACTS_WORKER_LOG = Path("logs") / "facts-worker.log"
RETRY_INTERVAL = timedelta(minutes=30)
MAX_FACT_CHARS = 400
_LOG_MAX_BYTES = 1_000_000
_WORKER_SCRIPT = "from vault_graph.interface.cli.main import app; app()"

_EXCHANGE_HEADING = re.compile(r"^## +\S")
_EXCHANGE_META = re.compile(r"^<!-- vg:exchange (?P<body>.*) -->$")
_META_ID = re.compile(r"(?:^|\s)id=(?P<value>\S+)")
_META_STARTED = re.compile(r"(?:^|\s)started=(?P<value>\S+)")
_FRONT_VALUE = re.compile(r'^(?P<key>[A-Za-z_]+):\s*"?(?P<value>[^"]*?)"?\s*$')
_FILE_DATE = re.compile(r"^(\d{4}-\d{2}-\d{2})-")
_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_SPACE = re.compile(r"\s+")
_META_TOOLS = re.compile(r"(?:^|\s)tools=(?P<value>\S*)")
_TURN_HEADING = re.compile(r"^### +(?P<role>\S+)")
_TOOL_LINE = re.compile(r"^- (?P<name>[^\s`]+)(?: .*)?$")

AttachRunner = Callable[[Path, Path, Path], AttachFactsOutcome]


@dataclass(frozen=True)
class FactJobResult:
    job: str
    status: str
    """`written`, `exists`, `no_facts`, `waiting` (kept for a retry) or `closed` (removed without attachment)."""
    reason: str | None = None
    message: str | None = None


@dataclass(frozen=True)
class FactWorkerRun:
    results: tuple[FactJobResult, ...]
    held_back: tuple[str, ...]
    """Jobs left alone because their retry time has not come."""


@dataclass(frozen=True)
class FactFailure:
    job: str
    vault: str | None
    part: str | None
    reason: str
    message: str
    failed_at: str
    retry_after: str | None
    closed: bool


@dataclass(frozen=True)
class _Exchange:
    exchange_id: str
    date: str
    text: str
    tools: frozenset[str] = frozenset()
    """Tool names of the exchange meta `tools=`."""


@dataclass(frozen=True)
class _Part:
    session_id: str
    sha256: str
    exchanges: tuple[_Exchange, ...]


class _JobFailed(Exception):
    def __init__(self, reason: str, message: str, *, closed: bool, retry: bool) -> None:
        super().__init__(message)
        self.reason = reason
        self.message = message
        self.closed = closed
        self.retry = retry


@dataclass
class _Extraction:
    """Picks the extractor of each job and builds each extractor once, only when an exchange misses the cache."""

    settings: FactsSettings
    extractors: dict[tuple[str, str], FactExtractor] = field(default_factory=dict)
    down: dict[str, str] = field(default_factory=dict)
    """Why an extractor could not run earlier in this run, by name. Later jobs do not call it again."""

    def choose(self) -> FactsSettings:
        """The settings of the extractor this job uses (D6). Checks llama-server only for `auto`."""
        if self.settings.extractor == "auto" and "llama-server" in self.down:
            return resolve_facts_settings(self.settings, local_answers=lambda endpoint: False)
        return resolve_facts_settings(self.settings, local_answers=_local_answers)

    def extract(self, chosen: FactsSettings, exchanges: list[FactExchange]) -> list[ExtractedFact]:
        if chosen.extractor in self.down:
            raise FactExtractorUnavailable(self.down[chosen.extractor])
        key = (chosen.extractor, chosen.model)
        extractor = self.extractors.get(key)
        if extractor is None:
            extractor = self.extractors[key] = select_fact_extractor(chosen)
        try:
            return extractor.extract(exchanges)
        except FactExtractorUnavailable as exc:
            self.down[chosen.extractor] = str(exc)
            raise


def _local_answers(endpoint: str) -> bool:
    return llama_health.llama_server_answers(endpoint, timeout_seconds=llama_health.WORKER_HEALTH_TIMEOUT_SECONDS)


def start_fact_worker(graph_home: Path, *, cache_dir: Path | None = None) -> bool:
    """Start the worker in a detached process. False when a worker holds the lock, so none starts.

    The child is `vg facts worker --graph-home <graph home> --lock-fd <fd>`. It inherits this process's flock on
    `logs/facts-worker.lock` and holds it until it ends. Its output goes to `logs/facts-worker.log`.
    """
    logs = graph_home / FACTS_WORKER_LOCK.parent
    logs.mkdir(parents=True, exist_ok=True)
    lock_descriptor = os.open(graph_home / FACTS_WORKER_LOCK, os.O_RDWR | os.O_CREAT, 0o644)
    try:
        try:
            fcntl.flock(lock_descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return False
        arguments = [
            sys.executable,
            "-c",
            _WORKER_SCRIPT,
            "facts",
            "worker",
            "--graph-home",
            str(graph_home),
            "--lock-fd",
            str(lock_descriptor),
        ]
        if cache_dir is not None:
            arguments += ["--cache-dir", str(cache_dir)]
        log_path = graph_home / FACTS_WORKER_LOG
        mode = "wb" if log_path.exists() and log_path.stat().st_size > _LOG_MAX_BYTES else "ab"
        with log_path.open(mode) as log:
            subprocess.Popen(
                arguments,
                stdin=subprocess.DEVNULL,
                stdout=log,
                stderr=subprocess.STDOUT,
                start_new_session=True,
                close_fds=True,
                pass_fds=(lock_descriptor,),
            )
    finally:
        # The child holds the same open lock, so closing this copy keeps it locked while the child lives.
        os.close(lock_descriptor)
    return True


def run_fact_worker(
    graph_home: Path,
    settings: FactsSettings,
    *,
    cache_dir: Path | None = None,
    lock_fd: int | None = None,
    now: Callable[[], datetime] | None = None,
    attach: AttachRunner = run_attach_facts,
) -> FactWorkerRun | None:
    """Drain the queue under the worker lock. None when another worker holds the lock.

    `lock_fd` is a descriptor of `logs/facts-worker.lock` that is already locked, passed by `start_fact_worker`.
    Each job runs at most once per call. Jobs added while the worker runs are taken too.
    """
    clock = now or (lambda: datetime.now(UTC))
    descriptor = lock_fd
    if descriptor is None:
        (graph_home / FACTS_WORKER_LOCK.parent).mkdir(parents=True, exist_ok=True)
        descriptor = os.open(graph_home / FACTS_WORKER_LOCK, os.O_RDWR | os.O_CREAT, 0o644)
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            os.close(descriptor)
            return None
    try:
        return _drain(graph_home, settings, FactCache(cache_dir or fact_cache_dir(graph_home)), clock, attach)
    finally:
        os.close(descriptor)


def read_fact_failures(graph_home: Path) -> list[FactFailure]:
    """Entries of the failure log. A missing or unreadable file reads as no entries."""
    try:
        payload = json.loads(facts_failures_path(graph_home).read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return []
    if not isinstance(payload, list):
        return []
    failures: list[FactFailure] = []
    for item in payload:
        if not isinstance(item, dict) or not isinstance(item.get("job"), str):
            continue
        failures.append(
            FactFailure(
                job=item["job"],
                vault=_text_or_none(item.get("vault")),
                part=_text_or_none(item.get("part")),
                reason=str(item.get("reason", "")),
                message=str(item.get("message", "")),
                failed_at=str(item.get("failed_at", "")),
                retry_after=_text_or_none(item.get("retry_after")),
                closed=item.get("closed") is True,
            )
        )
    return failures


def _drain(
    graph_home: Path, settings: FactsSettings, cache: FactCache, clock: Callable[[], datetime], attach: AttachRunner
) -> FactWorkerRun:
    extraction = _Extraction(settings)
    failures = {failure.job: failure for failure in read_fact_failures(graph_home)}
    seen: set[str] = set()
    held_back: list[str] = []
    results: list[FactJobResult] = []
    while True:
        pending = [path for path in list_fact_jobs(graph_home) if path.name not in seen]
        if not pending:
            break
        for path in pending:
            seen.add(path.name)
            previous = failures.get(path.name)
            if previous is not None and _waiting(previous, clock()):
                held_back.append(path.name)
                continue
            result, failure, chosen = _run_job(graph_home, path, cache, extraction, clock, attach)
            results.append(result)
            if chosen is not None:
                _write_last_job(graph_home, result, chosen, clock())
            if failure is None:
                failures.pop(path.name, None)
            else:
                failures[path.name] = failure
            _write_failures(graph_home, list(failures.values()))
    return FactWorkerRun(results=tuple(results), held_back=tuple(held_back))


def _run_job(
    graph_home: Path,
    path: Path,
    cache: FactCache,
    extraction: _Extraction,
    clock: Callable[[], datetime],
    attach: AttachRunner,
) -> tuple[FactJobResult, FactFailure | None, FactsSettings | None]:
    """Run one job. The third value is the extractor the job picked, or None when it failed before picking."""
    job: FactJob | None = None
    chosen: FactsSettings | None = None
    try:
        try:
            job = read_fact_job(path)
        except FactJobInvalid as exc:
            raise _JobFailed("job_invalid", str(exc), closed=True, retry=False) from exc
        part = _read_part(job.part_path)
        chosen = extraction.choose()
        facts = _facts_for_part(part, chosen, cache, extraction)
        if not facts:
            remove_fact_job(path)
            return FactJobResult(job=path.name, status="no_facts"), None, chosen
        outcome = _attach(graph_home, job, part, chosen, facts, attach)
    except _JobFailed as failed:
        if failed.closed:
            remove_fact_job(path)
        failure = _failure(path.name, job, failed, clock())
        status = "closed" if failed.closed else "waiting"
        result = FactJobResult(job=path.name, status=status, reason=failed.reason, message=failed.message)
        return result, failure, chosen
    remove_fact_job(path)
    return FactJobResult(job=path.name, status=outcome.status), None, chosen


def _read_part(part_path: Path) -> _Part:
    try:
        raw = part_path.read_bytes()
    except OSError as exc:
        raise _JobFailed(
            "part_unreadable", f"cannot read {part_path}: {exc.strerror}", closed=True, retry=False
        ) from exc
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise _JobFailed("part_unreadable", f"{part_path} is not UTF-8", closed=True, retry=False) from exc
    front, body = _split_frontmatter(text)
    if front.get("schema") != "vault-session/v2" or not front.get("session_id"):
        raise _JobFailed(
            "part_unreadable", f"{part_path} is not a vault-session/v2 file with a session_id", closed=True, retry=False
        )
    fallback = (front.get("first_turn_at") or "")[:10]
    if not _real_date(fallback):
        match = _FILE_DATE.match(part_path.name)
        fallback = match.group(1) if match else ""
    return _Part(
        session_id=front["session_id"],
        sha256=hashlib.sha256(raw).hexdigest(),
        exchanges=tuple(_exchanges(body, fallback)),
    )


def _split_frontmatter(text: str) -> tuple[dict[str, str], list[str]]:
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}, lines
    front: dict[str, str] = {}
    for index in range(1, len(lines)):
        if lines[index].strip() == "---":
            return front, lines[index + 1 :]
        if match := _FRONT_VALUE.match(lines[index]):
            front[match.group("key")] = match.group("value")
    return {}, lines


def _exchanges(lines: list[str], fallback_date: str) -> list[_Exchange]:
    """Exchanges with a `vg:exchange` meta line, in file order. Text is the lines after the meta line."""
    starts: list[tuple[int, str, str, frozenset[str]]] = []
    for index in range(len(lines) - 1):
        if not _EXCHANGE_HEADING.match(lines[index]):
            continue
        meta = _EXCHANGE_META.match(lines[index + 1].strip())
        if meta is None or (id_match := _META_ID.search(meta.group("body"))) is None:
            continue
        started = _META_STARTED.search(meta.group("body"))
        day = started.group("value")[:10] if started else ""
        tools_match = _META_TOOLS.search(meta.group("body"))
        tools = frozenset(
            item.split(":", 1)[0] for item in (tools_match.group("value") if tools_match else "").split(",") if item
        )
        starts.append((index, id_match.group("value"), day if _real_date(day) else fallback_date, tools))
    exchanges: list[_Exchange] = []
    for position, (index, exchange_id, day, tools) in enumerate(starts):
        end = starts[position + 1][0] if position + 1 < len(starts) else len(lines)
        text = "\n".join(lines[index + 2 : end]).strip()
        if text and day:
            exchanges.append(_Exchange(exchange_id=exchange_id, date=day, text=text, tools=tools))
    return exchanges


def extractor_text(text: str, tools: frozenset[str]) -> str:
    """`text` as the extractor reads it: without tool call lines and the non-user turns they leave empty (D1, D3).

    A tool call line is `- <name>` or `- <name> <arguments>` with `<name>` in `tools`, outside a `### user` turn.
    Returns an empty string when no turn text is left.
    """
    turns: list[tuple[str | None, list[str]]] = [(None, [])]
    for line in text.splitlines():
        if _TURN_HEADING.match(line) is not None:
            turns.append((line, []))
        else:
            turns[-1][1].append(line)
    kept: list[str] = []
    has_text = False
    for heading, body in turns:
        match = _TURN_HEADING.match(heading) if heading is not None else None
        user = match is not None and match.group("role") == "user"
        if not user:
            body = [line for line in body if not _tool_call_line(line, tools)]
        filled = any(line.strip() for line in body)
        if heading is not None and not user and not filled:
            continue
        has_text = has_text or filled
        if heading is not None:
            kept.append(heading)
        kept.extend(body)
    if not has_text:
        return ""
    return re.sub(r"\n{3,}", "\n\n", "\n".join(kept)).strip()


def _tool_call_line(line: str, tools: frozenset[str]) -> bool:
    match = _TOOL_LINE.match(line)
    return match is not None and match.group("name") in tools


def _facts_for_part(
    part: _Part, settings: FactsSettings, cache: FactCache, extraction: _Extraction
) -> list[ExtractedFact]:
    """Facts of every exchange of the part, from the cache, extracting only the misses (D20, F8)."""
    hashes = {exchange.exchange_id: exchange_content_hash(exchange.text) for exchange in part.exchanges}
    known: dict[str, list[CachedFact]] = {}
    misses: list[_Exchange] = []
    for exchange in part.exchanges:
        if exchange.exchange_id in known:
            continue
        cached = cache.get(settings.extractor, settings.model, hashes[exchange.exchange_id])
        if cached is None:
            misses.append(exchange)
        else:
            known[exchange.exchange_id] = cached
    if misses:
        extracted = _extract(misses, settings, extraction)
        for exchange in misses:
            found = extracted.get(exchange.exchange_id, [])
            cache.put(settings.extractor, settings.model, hashes[exchange.exchange_id], found)
            known[exchange.exchange_id] = found
    facts: list[ExtractedFact] = []
    emitted: set[str] = set()
    for exchange in part.exchanges:
        if exchange.exchange_id in emitted:
            continue
        emitted.add(exchange.exchange_id)
        facts.extend(
            ExtractedFact(text=fact.text, date=fact.date, exchange_id=exchange.exchange_id)
            for fact in known.get(exchange.exchange_id, [])
        )
    return facts


def _extract(misses: list[_Exchange], chosen: FactsSettings, extraction: _Extraction) -> dict[str, list[CachedFact]]:
    inputs = [
        FactExchange(exchange_id=item.exchange_id, date=item.date, text=text)
        for item in misses
        if (text := extractor_text(item.text, item.tools))
    ]
    if not inputs:
        return {}
    try:
        answer = extraction.extract(chosen, inputs)
    except FactExtractorUnavailable as exc:
        raise _JobFailed("extractor_unavailable", str(exc), closed=False, retry=True) from exc
    except FactOutputInvalid as exc:
        raise _JobFailed("extractor_output_invalid", str(exc), closed=False, retry=True) from exc
    wanted = {item.exchange_id for item in inputs}
    found: dict[str, list[CachedFact]] = {}
    for index, fact in enumerate(answer):
        text = _SPACE.sub(" ", fact.text).strip() if isinstance(fact.text, str) else ""
        if len(text) > MAX_FACT_CHARS:
            raise _JobFailed(
                "extractor_output_invalid",
                f"fact {index} text is longer than {MAX_FACT_CHARS} characters",
                closed=False,
                retry=True,
            )
        if not isinstance(fact.date, str) or not _real_date(fact.date):
            message = f"fact {index} date is not YYYY-MM-DD: {fact.date!r}"
            raise _JobFailed("extractor_output_invalid", message, closed=False, retry=True)
        # F8: only facts naming an exchange that is not in the part, or with no text, are dropped.
        if not text or fact.exchange_id not in wanted:
            continue
        found.setdefault(fact.exchange_id, []).append(CachedFact(text=text, date=fact.date))
    return found


def _attach(
    graph_home: Path,
    job: FactJob,
    part: _Part,
    settings: FactsSettings,
    facts: list[ExtractedFact],
    attach: AttachRunner,
) -> AttachFactsOutcome:
    payload = {
        "schema": ATTACH_FACTS_INPUT_SCHEMA,
        "session_id": part.session_id,
        "source_sha256": part.sha256,
        "extractor": settings.extractor,
        "model": settings.model,
        "facts": [{"date": fact.date, "text": fact.text, "exchange_id": fact.exchange_id} for fact in facts],
    }
    folder = graph_home / "facts" / "inputs"
    folder.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", dir=folder, prefix=f"{job.name}.", suffix=".json", delete=False
    ) as stream:
        input_path = Path(stream.name)
        json.dump(payload, stream, ensure_ascii=False)
    try:
        outcome = attach(job.vault_root, job.part_path, input_path)
    finally:
        input_path.unlink(missing_ok=True)
    if outcome.status in ("written", "exists"):
        return outcome
    if outcome.status == "rejected":
        raise _JobFailed("attach_rejected", outcome.reason or "unknown", closed=True, retry=False)
    if outcome.status == "writer_missing":
        raise _JobFailed("facts_writer_missing", outcome.message or "", closed=False, retry=False)
    raise _JobFailed("facts_writer_failed", outcome.message or "", closed=False, retry=True)


def _failure(name: str, job: FactJob | None, failed: _JobFailed, now: datetime) -> FactFailure:
    return FactFailure(
        job=name,
        vault=job.vault if job is not None else None,
        part=job.part if job is not None else None,
        reason=failed.reason,
        message=failed.message,
        failed_at=_iso(now),
        retry_after=_iso(now + RETRY_INTERVAL) if failed.retry else None,
        closed=failed.closed,
    )


def _waiting(failure: FactFailure, now: datetime) -> bool:
    if failure.closed or failure.retry_after is None:
        return False
    try:
        retry_after = datetime.fromisoformat(failure.retry_after.replace("Z", "+00:00"))
    except ValueError:
        return False
    return now < retry_after


def _write_failures(graph_home: Path, failures: list[FactFailure]) -> None:
    path = facts_failures_path(graph_home)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = [
        {
            "job": failure.job,
            "vault": failure.vault,
            "part": failure.part,
            "reason": failure.reason,
            "message": failure.message,
            "failed_at": failure.failed_at,
            "retry_after": failure.retry_after,
            "closed": failure.closed,
        }
        for failure in failures
    ]
    temporary: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=path.parent, prefix=".facts-failures-", suffix=".tmp", delete=False
        ) as stream:
            temporary = stream.name
            json.dump(payload, stream, ensure_ascii=False, indent=1)
        os.replace(temporary, path)
        temporary = None
    finally:
        if temporary is not None and os.path.exists(temporary):
            os.unlink(temporary)


def _write_last_job(graph_home: Path, result: FactJobResult, chosen: FactsSettings, now: datetime) -> None:
    path = facts_last_job_path(graph_home)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "job": result.job,
        "status": result.status,
        "extractor": chosen.extractor,
        "model": chosen.model,
        "finished_at": _iso(now),
    }
    temporary: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=path.parent, prefix=".facts-last-job-", suffix=".tmp", delete=False
        ) as stream:
            temporary = stream.name
            json.dump(payload, stream, ensure_ascii=False)
        os.replace(temporary, path)
        temporary = None
    finally:
        if temporary is not None and os.path.exists(temporary):
            os.unlink(temporary)


def _real_date(value: str) -> bool:
    if not _DATE.match(value):
        return False
    try:
        date.fromisoformat(value)
    except ValueError:
        return False
    return True


def _iso(moment: datetime) -> str:
    return moment.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _text_or_none(value: object) -> str | None:
    return value if isinstance(value, str) else None


__all__ = [
    "FACTS_WORKER_LOCK",
    "FACTS_WORKER_LOG",
    "RETRY_INTERVAL",
    "FactFailure",
    "FactJobResult",
    "FactWorkerRun",
    "read_fact_failures",
    "run_fact_worker",
    "start_fact_worker",
]
