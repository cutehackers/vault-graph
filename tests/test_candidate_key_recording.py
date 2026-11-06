"""Processed cleanup candidates and the inferred proposal limit of one cleanup.

Source: spec 2026-11-05 §4.4.4 "정리 후보가 목록에서 빠지는 규칙" 1, 결정29, 결정44, §6 (11th inferred),
A-23, A-38 (vg side). A write tool that gets ``candidate_key`` appends ``{candidate_key, at, outcome}``
to the Graph Home review log only when the result is ``published`` or ``proposed``.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from pathlib import Path

import pytest

from tests.test_memory_write_service import (
    TODAY,
    DiskPageReader,
    FakeVaultMap,
    RecordingWriter,
    add_page,
    make_vault,
    remember_request,
    retire_request,
    update_request,
)
from tests.test_restore_draft import RETIRED_PAGE, restore_request
from tests.test_supersede_claim_draft import CLAIM_PAGE, supersede_request
from vault_graph.interface.composition.adapters.temporary_draft_files import TemporaryDraftFiles
from vault_graph.operation.memory.memory_ports import WriteOutcome
from vault_graph.operation.memory.memory_requests import ImportRequest, MemoryWriteResult
from vault_graph.operation.memory.memory_write_service import (
    INFERRED_PROPOSAL_LIMIT,
    InferredProposalBudget,
    MemoryWriteService,
)
from vault_graph.project.context.project_binding_reader import MappedVault
from vault_graph.storage.local.reviewed_log import JsonlReviewedLog

KEY = "session:abc123"
PAGE_PATH = "wiki/decisions/use-sqlite.md"
CLAIM_PATH = "wiki/systems/index-store.md"


class RecordingLog:
    def __init__(self, error: Exception | None = None) -> None:
        self.records: list[tuple[tuple[str, ...], str]] = []
        self.error = error

    def append(self, candidate_keys: Sequence[str], *, outcome: str) -> None:
        if self.error is not None:
            raise self.error
        self.records.append((tuple(candidate_keys), outcome))


class FakeImporter:
    def __init__(self, outcome: WriteOutcome) -> None:
        self.outcome = outcome

    def import_source(self, vault_root: Path, note_path: Path, *, timeout_s: float) -> WriteOutcome:
        return self.outcome


def service(
    tmp_path: Path,
    writer: RecordingWriter,
    *,
    log: object | None = None,
    budget: InferredProposalBudget | None = None,
    importer: object | None = None,
    vault: MappedVault | None = None,
) -> MemoryWriteService:
    if vault is None:
        vault = MappedVault(name="main", path=tmp_path / "main", role="project")
        if not vault.path.exists():
            vault = make_vault(tmp_path, "main")
    temp_root = tmp_path / "os-temp"
    temp_root.mkdir(exist_ok=True)
    return MemoryWriteService(
        vault_map=FakeVaultMap((vault,), {}),
        writer=writer,
        page_reader=DiskPageReader(),
        drafts=TemporaryDraftFiles(temp_root=temp_root),
        today=lambda: TODAY,
        reviewed_log=log,  # type: ignore[arg-type]
        proposal_budget=budget or InferredProposalBudget(),
        importer=importer,  # type: ignore[arg-type]
    )


def vault_with_pages(tmp_path: Path) -> MappedVault:
    vault = make_vault(tmp_path, "main")
    add_page(vault)
    add_page(vault, "wiki/decisions/retired.md", RETIRED_PAGE)
    add_page(vault, CLAIM_PATH, CLAIM_PAGE)
    return vault


def note(tmp_path: Path) -> str:
    path = tmp_path / "l1" / "note.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("note\n", encoding="utf-8")
    return str(path)


Call = Callable[[MemoryWriteService, Path, str], MemoryWriteResult]

TOOL_CALLS: dict[str, Call] = {
    "remember": lambda svc, tmp, basis: svc.remember(
        remember_request(title="New fact", basis=basis, candidate_key=KEY)
    ),
    "update_memory": lambda svc, tmp, basis: svc.update(update_request(basis=basis, candidate_key=KEY)),
    "retire_memory": lambda svc, tmp, basis: svc.retire(retire_request(basis=basis, candidate_key=KEY)),
    "supersede_claim": lambda svc, tmp, basis: svc.supersede_claim(supersede_request(basis=basis, candidate_key=KEY)),
    "restore_memory": lambda svc, tmp, basis: svc.restore(
        restore_request(path="wiki/decisions/retired.md", basis=basis, candidate_key=KEY)
    ),
}


@pytest.mark.parametrize("tool", sorted(TOOL_CALLS))
@pytest.mark.parametrize(("basis", "status"), [("stated", "published"), ("inferred", "proposed")])
def test_published_or_proposed_write_records_the_candidate(tmp_path: Path, tool: str, basis: str, status: str) -> None:
    log = RecordingLog()
    svc = service(tmp_path, RecordingWriter(), log=log, vault=vault_with_pages(tmp_path))

    result = TOOL_CALLS[tool](svc, tmp_path, basis)

    assert result.status == status
    assert log.records == [((KEY,), status)]


@pytest.mark.parametrize("tool", sorted(TOOL_CALLS))
@pytest.mark.parametrize("status", ["rejected", "error"])
def test_rejected_or_error_write_records_nothing(tmp_path: Path, tool: str, status: str) -> None:
    log = RecordingLog()
    writer = RecordingWriter(WriteOutcome(status, messages=("no",)))  # type: ignore[arg-type]
    svc = service(tmp_path, writer, log=log, vault=vault_with_pages(tmp_path))

    result = TOOL_CALLS[tool](svc, tmp_path, "stated")

    assert result.status == status
    assert log.records == []


def test_input_rejection_records_nothing(tmp_path: Path) -> None:
    log = RecordingLog()

    result = service(tmp_path, RecordingWriter(), log=log).remember(remember_request(title=" ", candidate_key=KEY))

    assert result.status == "rejected"
    assert log.records == []


def test_restore_of_an_active_page_records_nothing(tmp_path: Path) -> None:
    log = RecordingLog()
    svc = service(tmp_path, RecordingWriter(), log=log, vault=vault_with_pages(tmp_path))

    result = svc.restore(restore_request(candidate_key=KEY))

    assert result.status == "rejected"
    assert log.records == []


def test_write_without_a_candidate_key_records_nothing(tmp_path: Path) -> None:
    log = RecordingLog()

    result = service(tmp_path, RecordingWriter(), log=log).remember(remember_request(title="New fact"))

    assert result.status == "published"
    assert log.records == []


@pytest.mark.parametrize(("status", "recorded"), [("published", True), ("rejected", False), ("error", False)])
def test_import_records_the_candidate_only_on_success(tmp_path: Path, status: str, recorded: bool) -> None:
    log = RecordingLog()
    importer = FakeImporter(WriteOutcome(status, raw_path="raw/imports/claude-memory/note--1.md"))  # type: ignore[arg-type]
    svc = service(tmp_path, RecordingWriter(), log=log, importer=importer)

    result = svc.import_auto_memory(ImportRequest(note=note(tmp_path), vault="main", candidate_key="l1:abc"))

    assert result.status == status
    assert log.records == ([(("l1:abc",), "published")] if recorded else [])


def test_log_failure_keeps_the_write_result_and_says_so(tmp_path: Path) -> None:
    log = RecordingLog(error=OSError("disk full"))

    result = service(tmp_path, RecordingWriter(), log=log).remember(remember_request(title="New", candidate_key=KEY))

    assert result.status == "published"
    assert any("disk full" in message and KEY in message for message in result.messages)


def test_real_log_gets_one_line_with_key_time_and_outcome(tmp_path: Path) -> None:
    graph_home = tmp_path / "graph-home"
    graph_home.mkdir()
    log = JsonlReviewedLog(graph_home, clock=lambda: datetime(2026, 11, 6, 9, 0, tzinfo=UTC))

    service(tmp_path, RecordingWriter(), log=log).remember(
        remember_request(title="New", basis="inferred", candidate_key=KEY)
    )

    lines = log.path.read_text(encoding="utf-8").splitlines()
    assert [json.loads(line) for line in lines] == [
        {"candidate_key": KEY, "at": "2026-11-06T09:00:00Z", "outcome": "proposed"}
    ]


# Inferred proposal limit


def test_eleventh_inferred_proposal_is_rejected_without_calling_the_vault(tmp_path: Path) -> None:
    writer = RecordingWriter()
    log = RecordingLog()
    svc = service(tmp_path, writer, log=log)

    results = [
        svc.remember(remember_request(title=f"Fact {n}", basis="inferred", candidate_key=f"k{n}")) for n in range(11)
    ]

    assert INFERRED_PROPOSAL_LIMIT == 10
    assert [result.status for result in results] == ["proposed"] * 10 + ["rejected"]
    assert len(writer.proposals) == 10
    assert any("limit" in message for message in results[-1].messages)
    assert ("k10",) not in [keys for keys, _ in log.records]


def test_stated_writes_do_not_use_the_limit(tmp_path: Path) -> None:
    writer = RecordingWriter()
    svc = service(tmp_path, writer)
    for n in range(10):
        svc.remember(remember_request(title=f"Fact {n}", basis="inferred"))

    result = svc.remember(remember_request(title="Stated fact", basis="stated"))

    assert result.status == "published"


def test_a_vault_refused_proposal_does_not_use_the_limit(tmp_path: Path) -> None:
    writer = RecordingWriter(propose_outcome=WriteOutcome("rejected", messages=("bad",)))
    budget = InferredProposalBudget()
    svc = service(tmp_path, writer, budget=budget)
    for n in range(10):
        svc.remember(remember_request(title=f"Fact {n}", basis="inferred"))
    writer.propose_outcome = WriteOutcome("proposed", review_path="scratch/review/x.md")

    result = svc.remember(remember_request(title="Fact 10", basis="inferred"))

    assert result.status == "proposed"


def test_starting_the_next_cleanup_resets_the_limit(tmp_path: Path) -> None:
    budget = InferredProposalBudget(limit=1)
    svc = service(tmp_path, RecordingWriter(), budget=budget)
    assert svc.remember(remember_request(title="A", basis="inferred")).status == "proposed"
    assert svc.remember(remember_request(title="B", basis="inferred")).status == "rejected"

    svc.start_curation()

    assert svc.remember(remember_request(title="C", basis="inferred")).status == "proposed"


def test_the_limit_is_shared_by_services_with_one_budget(tmp_path: Path) -> None:
    budget = InferredProposalBudget(limit=1)
    first = service(tmp_path, RecordingWriter(), budget=budget)
    second = service(tmp_path, RecordingWriter(), budget=budget)

    assert first.remember(remember_request(title="A", basis="inferred")).status == "proposed"
    assert second.remember(remember_request(title="B", basis="inferred")).status == "rejected"
