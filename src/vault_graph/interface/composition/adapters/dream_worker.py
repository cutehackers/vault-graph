"""The dream run: turn waiting session exchanges into quote-backed memory proposals (spec 2026-11-19 D2).

One run handles one project. It asks the cleanup bundle for the project's waiting session exchanges, hands them to
the ``DreamJudge`` in batches, checks every judgment in code, and sends what passes to the Vault review queue
with ``basis="inferred"`` through ``MemoryWriteService`` (write path 2, `review propose`). It never publishes,
never writes a Vault file itself and never writes `raw/`.

What the code checks before a proposal is sent:

- The quote is in what the person typed in that exchange (`evidence_quote.quote_in_text`). The location is the
  candidate's own; the judge never names one.
- A target page is one that was shown for that item, exists in one linked Vault, is current, is not pinned and is
  not the project brief (C6). `pin` is never set and kind `project` is never written.
- `update_memory` only adds to a page that has the shape `remember` writes (one heading, the body, one
  `## Evidence` section), so no part of a page is dropped. The earlier evidence lines are kept.
- `supersede_claim` names a claim text that is in the page.
- The evidence line is built here from the location and the quote, never from other judge text (C5).

After the session exchanges, while the run still has room, one batch of `verify` candidates is judged (D3): a
current page together with an exchange on its topic that started after the page was last written. The judge may
answer `supersede_claim`, `update_memory` (a correction added to a page without a claim table), `retire_memory` or
`none` for these. The same checks apply, and the evidence line also carries the day the exchange started, taken
from the index. This batch runs whether or not the exchange backlog is due.

When a run may start (`manual=False`, the run the capture hook starts):

- dreaming is on,
- the project's last run is older than `interval_hours` (a failed run is tried again after `RETRY_INTERVAL`),
- the write Vault has fewer than `pending_cap` proposals waiting,
- and, for judging session exchanges, exchanges that were never judged number `due_exchanges` or more, or their
  median age is over the backlog goal of 7 days (C3). Page checks do not wait for this.

`manual=True` (`vg dream run`) skips the first, second and fourth check. One run sends at most
`min(proposals_per_run, pending_cap - pending)` proposals (C4).

Records, all in the Graph Home:

- `dream/judged.jsonl`: one line per candidate that was judged and not proposed: `{"candidate_key", "at",
  "outcome", "prompt_version", "model"}`, written after every batch. Only this worker reads it, to leave those
  candidates out of the next run. A line written with another prompt version or model is ignored, so the
  candidate is judged again (C2). It is not `memory/reviewed.jsonl`: a manual cleanup still offers these
  candidates.
- `memory/reviewed.jsonl`: a proposed candidate, with outcome `dream_proposed` (C5), written right after the
  proposal is sent. A proposal from a `verify` candidate also records the `session:` key of its exchange, so the
  same words are not proposed a second time as a session exchange.
- `logs/dream-runs.jsonl`: two kinds of lines. `{"record": "proposal", ...}` is written right after a proposal
  is sent, with its Vault and review path; `vg dream status` counts accepted and rejected proposals from these
  lines only (C8). `{"record": "run", ...}` is written when a run ends: one that judged something, one that
  failed, and a skipped one with reason `nothing_to_judge`, `not_due` or `pending_cap` (the last only once in a
  row). A run that dies midway therefore loses no proposal, and the interval counts from the last `run` line
  that got past the pending cap.

Outcomes of one judgment: `none`, `no_answer` (the judge left the item out), `invalid_answer`, `quote_rejected`,
`target_refused`, `vault_rejected` (all recorded in `dream/judged.jsonl`), `proposed`, and `deferred` or
`vault_error` (not recorded: the candidate comes back in the next run). `deferred` covers a full run or Vault, a
page that changed after the judge read it, a second change to one page in one run, and a candidate a manual
cleanup handled meanwhile. A dry run reports `would_propose` and records nothing.

One worker runs at a time, under an flock on `logs/dream-worker.lock`. `start_dream_worker` starts it as a
detached process the way `start_fact_worker` does.
"""

from __future__ import annotations

import fcntl
import json
import os
import re
import subprocess
import sys
from collections.abc import Callable, Collection, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Protocol

from vault_graph.context.memory.memory_candidates import (
    NOT_CURRENT_STATUSES,
    SESSION_KEY_PREFIX,
    VERIFY_KEY_PREFIX,
    VERIFY_KIND,
    AnyCandidateKind,
    CandidateKind,
    ComparisonPage,
    MemoryCandidate,
)
from vault_graph.context.pack.recall_backlog import BACKLOG_ALERT_MEDIAN_DAYS, median_age_days
from vault_graph.interface.composition.adapters.dream_judge import (
    EXCHANGE_ACTIONS,
    PROMPT_VERSION,
    VERIFY_ACTIONS,
    DreamItem,
    DreamJudge,
    DreamJudgeUnavailable,
    DreamJudgment,
    DreamOutputInvalid,
    DreamPage,
    judgment_problem,
)
from vault_graph.interface.composition.memory_candidate_sources import MemoryCandidatePackage
from vault_graph.operation.memory.evidence_quote import normalize_evidence_text, quote_in_text
from vault_graph.operation.memory.memory_drafts import parse_frontmatter
from vault_graph.operation.memory.memory_ports import PageText, ReviewedLog, VaultPageReader
from vault_graph.operation.memory.memory_requests import (
    MemoryWriteResult,
    RememberRequest,
    RetireRequest,
    SupersedeClaimRequest,
    UpdateRequest,
)
from vault_graph.operation.memory.memory_target import choose_page_vault, choose_write_vault
from vault_graph.operation.scope.dream_settings import DreamSettings, dream_judged_path, dream_runs_path
from vault_graph.operation.scope.vault_frontmatter import split_frontmatter
from vault_graph.project.context.project_binding_reader import MappedVault, VaultMapReader

DREAM_WORKER_LOCK = Path("logs") / "dream-worker.lock"
DREAM_WORKER_LOG = Path("logs") / "dream-worker.log"
RETRY_INTERVAL = timedelta(hours=1)
DREAM_PROPOSED_OUTCOME = "dream_proposed"
BATCH_SIZE = 8
MAX_PAGES_PER_ITEM = 3
MAX_PAGE_CHARS = 3000
MAX_EXCHANGE_CHARS = 6000
VERIFY_BUNDLE_LIMIT = BATCH_SIZE
# How many times the judge may leave a candidate out of its answer before the candidate is left out of dreaming.
NO_ANSWER_LIMIT = 2
RECORDED_OUTCOMES = frozenset(
    {"none", "no_answer", "invalid_answer", "quote_rejected", "target_refused", "vault_rejected"}
)
RUN_RECORD = "run"
PROPOSAL_RECORD = "proposal"
_FULL_WIDTH_BAR = chr(0xFF5C)
_LOG_MAX_BYTES = 1_000_000
_WORKER_SCRIPT = "from vault_graph.interface.cli.main import app; app()"
_BRIEF_FOLDER = "wiki/projects/"
_DREAM_KINDS: tuple[CandidateKind, ...] = ("session_exchange",)
_VERIFY_KINDS: tuple[AnyCandidateKind, ...] = (VERIFY_KIND,)
_LOCATION = re.compile(r"^(?P<path>.+) L(?P<first>\d+)-L(?P<last>\d+)$")
# The page shape `remember` and `update_memory` write (memory_drafts._body).
_MEMORY_PAGE = re.compile(
    r"\A\s*# [^\n]+\n+(?P<body>.*?)\n+## Evidence\n+Status: [^\n]+\n+(?P<evidence>(?:- Evidence: [^\n]*\n?)+)\s*\Z",
    re.DOTALL,
)

CandidateSource = Callable[[Collection[str], int | None, bool], MemoryCandidatePackage]
"""`(skip_keys, limit, with_comparison)` to the project's waiting session exchanges."""
VerifySource = Callable[[Collection[str], int], MemoryCandidatePackage]
"""`(skip_keys, limit)` to the project's `verify` candidates: a current page and a later exchange on its topic."""


class MemoryWrites(Protocol):
    """The part of ``MemoryWriteService`` a dream run calls."""

    def remember(self, request: RememberRequest) -> MemoryWriteResult: ...

    def update(self, request: UpdateRequest) -> MemoryWriteResult: ...

    def supersede_claim(self, request: SupersedeClaimRequest) -> MemoryWriteResult: ...

    def retire(self, request: RetireRequest) -> MemoryWriteResult: ...


@dataclass(frozen=True)
class DreamPorts:
    vault_map: VaultMapReader
    candidates: CandidateSource
    verify_candidates: VerifySource
    exchange_text: Callable[[MemoryCandidate], str]
    """The lines of the exchange a candidate names, or an empty string when they cannot be read."""
    page_reader: VaultPageReader
    memory: MemoryWrites
    pending_count: Callable[[Path], int]
    """Memory proposals waiting for review in the Vault at that root."""
    reviewed_log: ReviewedLog
    reviewed_keys: Callable[[], Collection[str]]
    """The candidate keys recorded in `memory/reviewed.jsonl` now."""
    judge: DreamJudge


@dataclass(frozen=True)
class DreamProposal:
    candidate_key: str
    action: str
    vault: str
    vault_root: str
    target: str
    """The page path, or the title of a new page."""
    review_path: str | None


@dataclass(frozen=True)
class DreamRun:
    status: str
    """`ran`, `skipped` (nothing was judged) or `failed` (the judge could not be used)."""
    reason: str | None = None
    project_id: str | None = None
    vault: str | None = None
    judged: int = 0
    proposals: tuple[DreamProposal, ...] = ()
    outcomes: Mapping[str, int] = field(default_factory=dict)
    cost_usd: float | None = None
    dry_run: bool = False
    message: str | None = None


@dataclass(frozen=True)
class _Target:
    vault: MappedVault
    page: PageText
    frontmatter: Mapping[str, Any]

    def refusal(self, path: str) -> str | None:
        """Why a dream run may not change this page (C6), or None."""
        if path.startswith(_BRIEF_FOLDER) or self.frontmatter.get("type") == "project":
            return "the project brief is not changed by a dream run"
        if self.frontmatter.get("pin") is True:
            return "a pinned page is not changed by a dream run"
        if self.frontmatter.get("status") in NOT_CURRENT_STATUSES:
            return "the page is not current"
        return None


@dataclass
class _Tally:
    """What one run did so far."""

    budget: int
    proposals: list[DreamProposal] = field(default_factory=list)
    outcomes: dict[str, int] = field(default_factory=dict)
    recorded: list[tuple[str, str]] = field(default_factory=list)
    """Judged, not proposed, and not yet written to `dream/judged.jsonl`."""
    sent_by_vault: dict[str, int] = field(default_factory=dict)
    proposed_locations: set[str] = field(default_factory=set)
    changed_pages: set[tuple[str, str]] = field(default_factory=set)
    judged: int = 0
    cost_usd: float | None = None

    def count(self, key: str, outcome: str) -> None:
        self.outcomes[outcome] = self.outcomes.get(outcome, 0) + 1
        if outcome in RECORDED_OUTCOMES:
            self.recorded.append((key, outcome))

    @property
    def room(self) -> bool:
        return len(self.proposals) < self.budget


@dataclass
class _Work:
    """What every judgment of one run needs."""

    graph_home: Path
    cwd: Path
    project_id: str
    write_vault: MappedVault
    settings: DreamSettings
    ports: DreamPorts
    tally: _Tally
    pending_by_vault: dict[str, int]
    dry_run: bool
    clock: Callable[[], datetime]


def run_dream(
    graph_home: Path,
    cwd: Path,
    settings: DreamSettings,
    ports: DreamPorts,
    *,
    manual: bool = False,
    dry_run: bool = False,
    now: Callable[[], datetime] | None = None,
) -> DreamRun:
    """Run one dream for the ``cwd`` project. The caller holds the worker lock."""
    clock = now or (lambda: datetime.now(UTC))
    match = ports.vault_map.find_project(cwd)
    if match.project_id is None:
        return DreamRun("skipped", "no_project", message=match.reason)
    project_id = match.project_id
    write_vault = choose_write_vault(None, cwd, ports.vault_map)
    if not isinstance(write_vault, MappedVault):
        return DreamRun(
            "skipped", "no_write_vault", project_id=project_id, message=getattr(write_vault, "message", None)
        )

    def skipped(reason: str, message: str | None = None, *, log: bool = False) -> DreamRun:
        run = DreamRun(
            "skipped", reason, project_id=project_id, vault=write_vault.name, dry_run=dry_run, message=message
        )
        if log and not dry_run:
            _log_run(graph_home, cwd, write_vault, run, ports.judge.model, clock())
        return run

    runs = read_dream_runs(graph_home)
    if not manual:
        if not settings.enabled:
            return skipped("off")
        if _ran_recently(runs, project_id, settings, clock()):
            return skipped("interval")
    pending = ports.pending_count(write_vault.path)
    if pending >= settings.pending_cap:
        # Logged once, so `vg dream status` can say why dreaming stopped before any proposal exists.
        return skipped("pending_cap", log=_last_run(runs, project_id).get("reason") != "pending_cap")

    judged_keys = read_judged_keys(graph_home, model=ports.judge.model)
    waiting = ports.candidates(judged_keys, None, False)
    if waiting.project_id is None:
        return skipped("no_project", waiting.reason)
    unjudged = [candidate for candidate in waiting.candidates if candidate.human_text]
    exchanges_due = manual or _is_due(unjudged, settings, clock())
    bundle: list[MemoryCandidate] = []
    if unjudged and exchanges_due:
        bundle = [
            candidate
            for candidate in ports.candidates(judged_keys, settings.bundle_limit, True).candidates
            if candidate.human_text
        ]

    tally = _Tally(budget=min(settings.proposals_per_run, settings.pending_cap - pending))
    work = _Work(
        graph_home=graph_home,
        cwd=cwd,
        project_id=project_id,
        write_vault=write_vault,
        settings=settings,
        ports=ports,
        tally=tally,
        pending_by_vault={write_vault.name: pending},
        dry_run=dry_run,
        clock=clock,
    )
    failure = _judge_all(work, bundle)
    checks: list[MemoryCandidate] = []
    if failure is None and tally.room:
        # D3: pages that a later exchange on the same topic may have made wrong. One batch per run. It runs
        # whether or not the exchange backlog is due, so pages are still checked when few exchanges wait.
        checks = [
            candidate
            for candidate in ports.verify_candidates(_check_keys(judged_keys), VERIFY_BUNDLE_LIMIT).candidates
            if candidate.human_text and candidate.targets and candidate.location not in tally.proposed_locations
        ]
        failure = _judge_all(work, checks)
    if not bundle and not checks and failure is None:
        # Logged, so the next hook run waits one interval before it searches for page checks again.
        return skipped("not_due" if unjudged and not exchanges_due else "nothing_to_judge", log=True)

    run = DreamRun(
        status="failed" if failure is not None and not tally.judged else "ran",
        reason=failure[0] if failure is not None else None,
        project_id=project_id,
        vault=write_vault.name,
        judged=tally.judged,
        proposals=tuple(tally.proposals),
        outcomes=dict(tally.outcomes),
        cost_usd=tally.cost_usd,
        dry_run=dry_run,
        message=failure[1] if failure is not None else None,
    )
    if not dry_run:
        _log_run(graph_home, cwd, write_vault, run, ports.judge.model, clock())
    return run


def _project_runs(runs: Sequence[Mapping[str, Any]], project_id: str) -> list[Mapping[str, Any]]:
    """The `run` lines of one project, oldest first. Proposal lines are left out."""
    return [run for run in runs if run.get("record") == RUN_RECORD and run.get("project") == project_id]


def _last_run(runs: Sequence[Mapping[str, Any]], project_id: str) -> Mapping[str, Any]:
    found = _project_runs(runs, project_id)
    return found[-1] if found else {}


def _ran_recently(runs: Sequence[Mapping[str, Any]], project_id: str, settings: DreamSettings, now: datetime) -> bool:
    """True while the project's last run that got past the pending cap is younger than its wait time."""
    for run in reversed(_project_runs(runs, project_id)):
        if run.get("reason") == "pending_cap":
            continue
        at = _moment(run.get("at"))
        if at is None:
            continue
        wait = RETRY_INTERVAL if run.get("status") == "failed" else timedelta(hours=settings.interval_hours)
        return now - at < wait
    return False


def _is_due(unjudged: Sequence[MemoryCandidate], settings: DreamSettings, now: datetime) -> bool:
    if len(unjudged) >= settings.due_exchanges:
        return True
    age = median_age_days((item.started_at for item in unjudged if item.started_at is not None), now=now)
    return age is not None and age > BACKLOG_ALERT_MEDIAN_DAYS


def _judge_all(work: _Work, candidates: Sequence[MemoryCandidate]) -> tuple[str, str] | None:
    """Judge ``candidates`` in batches while the run has room. Returns the judge failure that stopped it, if any."""
    tally, ports = work.tally, work.ports
    for start in range(0, len(candidates), BATCH_SIZE):
        if not tally.room:
            break
        batch = candidates[start : start + BATCH_SIZE]
        targets = _targets(batch, work.cwd, ports)
        items = [_item(candidate, targets, ports) for candidate in batch]
        try:
            answer = ports.judge.judge(items, _pages(batch, targets))
        except DreamJudgeUnavailable as exc:
            return ("judge_unavailable", str(exc))
        except DreamOutputInvalid as exc:
            return ("judge_output_invalid", str(exc))
        if answer.cost_usd is not None:
            tally.cost_usd = (tally.cost_usd or 0.0) + answer.cost_usd
        judgments = {judgment.key: judgment for judgment in answer.judgments}
        for candidate, item in zip(batch, items, strict=True):
            judgment = judgments.get(candidate.key)
            if judgment is None:
                # Recorded. After NO_ANSWER_LIMIT such records the item is left out, so it is not paid for forever.
                tally.count(candidate.key, "no_answer")
                continue
            tally.judged += 1
            tally.count(candidate.key, _handle(judgment, candidate, item, targets, work))
        _flush_judged(work)
    return None


def _check_keys(judged_keys: Collection[str]) -> frozenset[str]:
    """The judged page checks. An exchange judged `none` on its own is still checked against a page later: the
    page it contradicts may not have been among the pages the judge saw with it."""
    return frozenset(key for key in judged_keys if key.startswith(VERIFY_KEY_PREFIX))


def _flush_judged(work: _Work) -> None:
    """Write the judged records of the batch now, so a run that dies later does not pay for them again."""
    if work.dry_run or not work.tally.recorded:
        return
    at = _iso(work.clock())
    model = work.ports.judge.model
    _append_jsonl(
        dream_judged_path(work.graph_home),
        [
            {"candidate_key": key, "at": at, "outcome": outcome, "prompt_version": PROMPT_VERSION, "model": model}
            for key, outcome in work.tally.recorded
        ],
    )
    work.tally.recorded.clear()


def _shown(candidate: MemoryCandidate) -> tuple[ComparisonPage, ...]:
    """The pages the judge sees for a candidate: the page a verify candidate checks, else the comparison pages."""
    return (candidate.targets if candidate.kind == VERIFY_KIND else candidate.comparison)[:MAX_PAGES_PER_ITEM]


def _targets(batch: Sequence[MemoryCandidate], cwd: Path, ports: DreamPorts) -> dict[str, _Target]:
    """The shown pages of the batch that exist in exactly one linked Vault, by page path."""
    targets: dict[str, _Target] = {}
    for candidate in batch:
        for comparison in _shown(candidate):
            if comparison.path not in targets and (target := _target(comparison.path, cwd, ports)) is not None:
                targets[comparison.path] = target
    return targets


def _target(path: str, cwd: Path, ports: DreamPorts) -> _Target | None:
    chosen = choose_page_vault(
        None,
        cwd,
        ports.vault_map,
        path=path,
        has_page=lambda vault: ports.page_reader.read(vault.path, path) is not None,
    )
    if not isinstance(chosen, MappedVault):
        return None
    page = ports.page_reader.read(chosen.path, path)
    if page is None:
        return None
    return _Target(vault=chosen, page=page, frontmatter=parse_frontmatter(page.text) or {})


def _item(candidate: MemoryCandidate, targets: Mapping[str, _Target], ports: DreamPorts) -> DreamItem:
    shown = tuple(page.path for page in _shown(candidate) if page.path in targets)
    exchange = ports.exchange_text(candidate) or candidate.human_text
    return DreamItem(
        key=candidate.key,
        date=_day(candidate),
        # A pasted log can make one turn very long. The judge sees its start; the quote is checked against all of it.
        user_text=candidate.human_text[:MAX_EXCHANGE_CHARS],
        exchange_text=exchange[:MAX_EXCHANGE_CHARS],
        pages=shown,
        actions=VERIFY_ACTIONS if candidate.kind == VERIFY_KIND else EXCHANGE_ACTIONS,
    )


def _day(candidate: MemoryCandidate) -> str:
    """The day the exchange started, from the index, never from the judge."""
    return candidate.started_at.date().isoformat() if candidate.started_at is not None else ""


def _pages(batch: Sequence[MemoryCandidate], targets: Mapping[str, _Target]) -> list[DreamPage]:
    pages: dict[str, DreamPage] = {}
    for candidate in batch:
        for comparison in _shown(candidate):
            target = targets.get(comparison.path)
            if target is None or comparison.path in pages:
                continue
            pages[comparison.path] = DreamPage(
                path=comparison.path,
                title=comparison.title,
                text=target.page.text[:MAX_PAGE_CHARS],
                status=comparison.status,
                changeable=target.refusal(comparison.path) is None,
            )
    return list(pages.values())


def _handle(
    judgment: DreamJudgment,
    candidate: MemoryCandidate,
    item: DreamItem,
    shown: Mapping[str, _Target],
    work: _Work,
) -> str:
    """Check one judgment and send it when it passes. Returns its outcome."""
    cwd, ports, tally, write_vault = work.cwd, work.ports, work.tally, work.write_vault
    if judgment_problem(judgment, item) is not None:
        return "invalid_answer"
    if judgment.action == "none":
        return "none"
    if not quote_in_text(judgment.quote, candidate.human_text):
        return "quote_rejected"
    quote = " ".join(judgment.quote.split())
    # A verify proposal says a later exchange overrules the page, so its evidence also carries that exchange's day.
    dated = f" ({_day(candidate)})" if candidate.kind == VERIFY_KIND else ""
    evidence = f'{candidate.location}{dated} "{quote}"'

    vault = write_vault
    send: Callable[[], MemoryWriteResult]
    if judgment.action == "remember":
        target_name = judgment.title.strip()
        remember = RememberRequest(
            title=judgment.title,
            kind=judgment.kind,
            body=judgment.body,
            evidence=(evidence,),
            basis="inferred",
            cwd=str(cwd),
            vault=write_vault.name,
            pin=False,
            memory_kind=judgment.memory_kind or None,
            project_id=work.project_id,
            summary=judgment.summary.strip(),
        )

        def send() -> MemoryWriteResult:
            return ports.memory.remember(remember)
    else:
        target_name = judgment.path
        target = _target(judgment.path, cwd, ports)
        if target is None or target.refusal(judgment.path) is not None:
            return "target_refused"
        vault = target.vault
        seen = shown.get(judgment.path)
        if seen is None or seen.page.sha256 != target.page.sha256:
            # The page changed after the judge read it. The candidate is judged again against the new text.
            return "deferred"
        if (vault.name, judgment.path) in tally.changed_pages:
            # Each proposal is built from the page as it is now, so a second one would undo the first when
            # both are accepted. The candidate waits for a later run.
            return "deferred"
        if judgment.action == "update_memory":
            parts = memory_page_parts(target.page.text)
            if parts is None:
                return "target_refused"
            body, earlier_evidence = parts
            update = UpdateRequest(
                path=judgment.path,
                body=f"{body}\n\n{judgment.addition.strip()}",
                evidence=(*earlier_evidence, evidence),
                basis="inferred",
                vault=vault.name,
                cwd=str(cwd),
            )

            def send() -> MemoryWriteResult:
                return ports.memory.update(update)
        elif judgment.action == "supersede_claim":
            if normalize_evidence_text(judgment.claim) not in normalize_evidence_text(target.page.text):
                return "target_refused"
            supersede = SupersedeClaimRequest(
                path=judgment.path,
                claim=judgment.claim,
                new_claim=judgment.new_claim,
                # The evidence is one table cell. NFKC turns the full-width bar back into "|", so the quote
                # still matches the exchange.
                evidence=evidence.replace("|", _FULL_WIDTH_BAR),
                basis="inferred",
                vault=vault.name,
                cwd=str(cwd),
            )

            def send() -> MemoryWriteResult:
                return ports.memory.supersede_claim(supersede)
        else:
            retire = RetireRequest(
                path=judgment.path,
                reason=f"{judgment.reason.strip()} ({evidence})",
                basis="inferred",
                vault=vault.name,
                cwd=str(cwd),
            )

            def send() -> MemoryWriteResult:
                return ports.memory.retire(retire)

    if not tally.room:
        return "deferred"
    if vault.name not in work.pending_by_vault:
        work.pending_by_vault[vault.name] = ports.pending_count(vault.path)
    if work.pending_by_vault[vault.name] + tally.sent_by_vault.get(vault.name, 0) >= work.settings.pending_cap:
        return "deferred"
    review_path: str | None = None
    if not work.dry_run:
        # A manual cleanup may have handled the candidate while the judge ran.
        if candidate.key in ports.reviewed_keys():
            return "deferred"
        result = send()
        if result.status == "rejected":
            return "vault_rejected"
        if result.status != "proposed":
            return "vault_error"
        review_path = result.review_path
    proposal = DreamProposal(
        candidate_key=candidate.key,
        action=judgment.action,
        vault=vault.name,
        vault_root=str(vault.path),
        target=target_name,
        review_path=review_path,
    )
    tally.sent_by_vault[vault.name] = tally.sent_by_vault.get(vault.name, 0) + 1
    tally.proposals.append(proposal)
    tally.proposed_locations.add(candidate.location)
    if judgment.action != "remember":
        tally.changed_pages.add((vault.name, judgment.path))
    if work.dry_run:
        return "would_propose"
    _record_proposal(work, candidate, proposal)
    return "proposed"


def _record_proposal(work: _Work, candidate: MemoryCandidate, proposal: DreamProposal) -> None:
    """Record a sent proposal at once, so a run that dies later neither sends it again nor loses its review path."""
    keys = [candidate.key]
    if candidate.kind == VERIFY_KIND and candidate.targets:
        # The same exchange is also a session exchange candidate. What it says is in the review queue now.
        target = candidate.targets[0]
        prefix = f"{VERIFY_KEY_PREFIX}{target.vault_id}:{target.path}:"
        if candidate.key.startswith(prefix):
            keys.append(f"{SESSION_KEY_PREFIX}{candidate.key.removeprefix(prefix)}")
    work.ports.reviewed_log.append(keys, outcome=DREAM_PROPOSED_OUTCOME)
    _append_jsonl(
        dream_runs_path(work.graph_home),
        [
            {
                "record": PROPOSAL_RECORD,
                "at": _iso(work.clock()),
                "project": work.project_id,
                "candidate_key": proposal.candidate_key,
                "action": proposal.action,
                "vault": proposal.vault,
                "vault_root": proposal.vault_root,
                "target": proposal.target,
                "review_path": proposal.review_path,
            }
        ],
    )


def memory_page_parts(text: str) -> tuple[str, tuple[str, ...]] | None:
    """The body and the evidence items of a page in the shape `remember` writes, else None."""
    block = split_frontmatter(text)
    if block is None:
        return None
    match = _MEMORY_PAGE.match(block[1])
    if match is None or "\n## Evidence" in match.group("body"):
        return None
    evidence = tuple(
        line.removeprefix("- Evidence:").strip() for line in match.group("evidence").splitlines() if line.strip()
    )
    if not all(evidence):
        return None
    return match.group("body").strip(), evidence


# Records ----------------------------------------------------------------------------------------


def read_judged_keys(graph_home: Path, *, model: str) -> frozenset[str]:
    """Candidate keys judged and not proposed with this prompt version and model. A missing file means none.

    A candidate the judge left out of its answer counts only after ``NO_ANSWER_LIMIT`` such records, so one
    miscopied key or one short answer does not hide it.
    """
    keys: set[str] = set()
    unanswered: dict[str, int] = {}
    for record in _read_jsonl(dream_judged_path(graph_home)):
        key = record.get("candidate_key")
        if (
            isinstance(key, str)
            and key
            and record.get("prompt_version") == PROMPT_VERSION
            and record.get("model") == model
        ):
            if record.get("outcome") == "no_answer":
                unanswered[key] = unanswered.get(key, 0) + 1
                if unanswered[key] < NO_ANSWER_LIMIT:
                    continue
            keys.add(key)
    return frozenset(keys)


def read_dream_runs(graph_home: Path) -> list[Mapping[str, Any]]:
    """Lines of `logs/dream-runs.jsonl`, oldest first. A missing or unreadable file reads as no runs."""
    return _read_jsonl(dream_runs_path(graph_home))


def _read_jsonl(path: Path) -> list[Mapping[str, Any]]:
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []
    records: list[Mapping[str, Any]] = []
    for line in lines:
        try:
            value = json.loads(line)
        except ValueError:
            continue
        if isinstance(value, dict):
            records.append(value)
    return records


def _log_run(graph_home: Path, cwd: Path, vault: MappedVault, run: DreamRun, model: str, now: datetime) -> None:
    """Append the `run` line of one run. Its proposals already have their own lines."""
    _append_jsonl(
        dream_runs_path(graph_home),
        [
            {
                "record": RUN_RECORD,
                "at": _iso(now),
                "project": run.project_id,
                "cwd": str(cwd),
                "vault": vault.name,
                "vault_root": str(vault.path),
                "status": run.status,
                "reason": run.reason,
                "message": run.message,
                "model": model,
                "prompt_version": PROMPT_VERSION,
                "judged": run.judged,
                "outcomes": dict(run.outcomes),
                "cost_usd": run.cost_usd,
                "proposals": len(run.proposals),
            }
        ],
    )


def _append_jsonl(path: Path, records: Sequence[Mapping[str, Any]]) -> None:
    if not records:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = "".join(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n" for record in records)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(payload)


def _moment(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _iso(moment: datetime) -> str:
    return moment.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


# Process ----------------------------------------------------------------------------------------


def start_dream_worker(graph_home: Path, cwd: Path, *, vault_map_file: Path | None = None) -> bool:
    """Start one dream run for ``cwd`` in a detached process. False when a worker holds the lock.

    The child is `vg dream worker --graph-home <graph home> --cwd <cwd> --lock-fd <fd>`, with `--vault-map` when
    ``vault_map_file`` is given. It inherits this process's flock on `logs/dream-worker.lock` and holds it until
    it ends. Its output goes to `logs/dream-worker.log`.
    """
    logs = graph_home / DREAM_WORKER_LOCK.parent
    logs.mkdir(parents=True, exist_ok=True)
    lock_descriptor = os.open(graph_home / DREAM_WORKER_LOCK, os.O_RDWR | os.O_CREAT, 0o644)
    try:
        try:
            fcntl.flock(lock_descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return False
        arguments = [
            sys.executable,
            "-c",
            _WORKER_SCRIPT,
            "dream",
            "worker",
            "--graph-home",
            str(graph_home),
            "--cwd",
            str(cwd),
            "--lock-fd",
            str(lock_descriptor),
        ]
        if vault_map_file is not None:
            arguments += ["--vault-map", str(vault_map_file)]
        log_path = graph_home / DREAM_WORKER_LOG
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


def run_dream_locked(
    graph_home: Path,
    cwd: Path,
    settings: DreamSettings,
    ports: DreamPorts,
    *,
    lock_fd: int | None = None,
    manual: bool = False,
    dry_run: bool = False,
) -> DreamRun | None:
    """``run_dream`` under the worker lock. None when another worker holds the lock.

    ``lock_fd`` is a descriptor of `logs/dream-worker.lock` that is already locked, passed by `start_dream_worker`.
    """
    descriptor = lock_fd
    if descriptor is None:
        (graph_home / DREAM_WORKER_LOCK.parent).mkdir(parents=True, exist_ok=True)
        descriptor = os.open(graph_home / DREAM_WORKER_LOCK, os.O_RDWR | os.O_CREAT, 0o644)
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            os.close(descriptor)
            return None
    try:
        return run_dream(graph_home, cwd, settings, ports, manual=manual, dry_run=dry_run)
    finally:
        os.close(descriptor)


def open_dream_ports(
    graph_home: Path, cwd: Path, settings: DreamSettings, *, vault_map_file: Path | None = None
) -> DreamPorts | str:
    """The real ports of a dream run, or the reason none can be built (no usable `vault-map.json`)."""
    from vault_graph.interface.composition.adapters.claude_dream_judge import ClaudeDreamJudge
    from vault_graph.interface.composition.adapters.temporary_draft_files import TemporaryDraftFiles
    from vault_graph.interface.composition.adapters.vault_page_reader import VaultPageFileReader
    from vault_graph.interface.composition.adapters.vault_publish_cli import VaultPublishCli
    from vault_graph.interface.composition.adapters.vault_review_queue import pending_proposals
    from vault_graph.interface.composition.memory_candidate_sources import memory_candidate_package
    from vault_graph.operation.integration.vault_map import open_vault_map, vault_map_path
    from vault_graph.operation.memory.memory_write_service import InferredProposalBudget, MemoryWriteService
    from vault_graph.storage.local.reviewed_log import JsonlReviewedLog

    opening = open_vault_map(vault_map_path(vault_map_file))
    vault_map = opening.vault_map
    if vault_map is None:
        return opening.warning or f"no vault-map.json at {opening.path}"
    page_reader = VaultPageFileReader()
    reviewed_log = JsonlReviewedLog(graph_home)

    def candidates(skip_keys: Collection[str], limit: int | None, with_comparison: bool) -> MemoryCandidatePackage:
        return memory_candidate_package(
            graph_home,
            cwd,
            kinds=_DREAM_KINDS,
            limit=limit,
            vault_map_file=vault_map_file,
            with_comparison=with_comparison,
            skip_keys=skip_keys,
        )

    def verify_candidates(skip_keys: Collection[str], limit: int) -> MemoryCandidatePackage:
        return memory_candidate_package(
            graph_home,
            cwd,
            kinds=_VERIFY_KINDS,
            limit=limit,
            vault_map_file=vault_map_file,
            with_comparison=False,
            skip_keys=skip_keys,
        )

    def exchange_text(candidate: MemoryCandidate) -> str:
        return read_exchange_lines(candidate.location, [vault.path for vault in vault_map.vaults_for(cwd)])

    return DreamPorts(
        vault_map=vault_map,
        candidates=candidates,
        verify_candidates=verify_candidates,
        exchange_text=exchange_text,
        page_reader=page_reader,
        # The run counts its own proposals (C4). The service budget only repeats the per-run limit, and the
        # service records nothing: the worker records a proposed candidate as `dream_proposed` (C5).
        memory=MemoryWriteService(
            vault_map=vault_map,
            writer=VaultPublishCli(),
            page_reader=page_reader,
            drafts=TemporaryDraftFiles(),
            proposal_budget=InferredProposalBudget(limit=settings.proposals_per_run),
        ),
        pending_count=pending_proposals,
        reviewed_log=reviewed_log,
        reviewed_keys=reviewed_log.reviewed_keys,
        judge=ClaudeDreamJudge(model=settings.model),
    )


def read_exchange_lines(location: str, vault_roots: Sequence[Path]) -> str:
    """The lines an exchange location (`<path> L<first>-L<last>`) names, from the first Vault that has the file."""
    match = _LOCATION.match(location)
    if match is None:
        return ""
    first, last = int(match.group("first")), int(match.group("last"))
    for vault_root in vault_roots:
        root = vault_root.resolve()
        target = (root / match.group("path")).resolve()
        if not target.is_relative_to(root) or not target.is_file():
            continue
        try:
            lines = target.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue
        return "\n".join(lines[max(first - 1, 0) : last])
    return ""


__all__ = [
    "BATCH_SIZE",
    "DREAM_PROPOSED_OUTCOME",
    "DREAM_WORKER_LOCK",
    "DREAM_WORKER_LOG",
    "PROPOSAL_RECORD",
    "RETRY_INTERVAL",
    "RUN_RECORD",
    "DreamPorts",
    "DreamProposal",
    "DreamRun",
    "MemoryWrites",
    "memory_page_parts",
    "open_dream_ports",
    "read_dream_runs",
    "read_exchange_lines",
    "read_judged_keys",
    "run_dream",
    "run_dream_locked",
    "start_dream_worker",
]
