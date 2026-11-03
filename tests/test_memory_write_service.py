"""MemoryWriteService: add, update and retire stated memories through a VaultWriter port.

Source: spec 2026-11-02-vault-long-term-memory V3, 결정12, 결정S5, 결정S6, 결정S8, 6절, A-2 (unit level), A-8.
The earlier remember rules (spec 2026-10-29 4.2.4, S5, S6) still hold: one Vault, a temporary draft
outside the Vault, one write per Vault at a time.
"""

from __future__ import annotations

import hashlib
import json
import threading
import time
from collections.abc import Callable
from datetime import date
from pathlib import Path
from typing import Any

import pytest

from tests.test_read_only_boundary import file_bytes
from vault_graph.interface.composition.adapters.temporary_draft_files import TemporaryDraftFiles
from vault_graph.operation.memory.memory_ports import PageText, WriteOutcome
from vault_graph.operation.memory.memory_requests import RememberRequest, RetireRequest, UpdateRequest
from vault_graph.operation.memory.memory_write_service import PUBLISH_TIMEOUT_SECONDS, MemoryWriteService
from vault_graph.project.context.project_binding_reader import MappedProjectMatch, MappedVault

TODAY = date(2026, 11, 2)

PAGE = """---
title: Use SQLite
type: decision
status: active
created: 2026-10-01
updated: 2026-10-01
owner: agent
summary: Use SQLite
source_count: 1
tags: []
related: []
confidence: medium
---

# Use SQLite

Old body.
"""


class FakeVaultMap:
    def __init__(
        self,
        vaults: tuple[MappedVault, ...],
        linked: dict[str, tuple[MappedVault, ...]],
        default: MappedVault | None = None,
    ) -> None:
        self._vaults = vaults
        self._linked = linked
        self._default = default

    @property
    def vaults(self) -> tuple[MappedVault, ...]:
        return self._vaults

    def find_project(self, cwd: Path) -> MappedProjectMatch:
        linked = self._linked.get(str(cwd))
        if linked is None:
            return MappedProjectMatch(None, None, (), reason=f"{cwd} is not linked to a project.")
        return MappedProjectMatch("project", "root", linked, default_write_vault=self._default)

    def vaults_for(self, cwd: Path) -> tuple[MappedVault, ...]:
        return self.find_project(cwd).vaults


class DiskPageReader:
    """Reads pages from the temporary Vault folders, like the composition adapter."""

    def __init__(self) -> None:
        self.reads: list[tuple[Path, str]] = []

    def read(self, vault_root: Path, path: str) -> PageText | None:
        self.reads.append((vault_root, path))
        target = vault_root / path
        if not target.is_file():
            return None
        data = target.read_bytes()
        return PageText(text=data.decode("utf-8"), sha256=hashlib.sha256(data).hexdigest())


class ChangingPageReader(DiskPageReader):
    """Returns a different page on every read, as if a person kept editing it."""

    def read(self, vault_root: Path, path: str) -> PageText | None:
        page = super().read(vault_root, path)
        if page is None:
            return page
        changed = page.text + f"\nEdit {len(self.reads)} by a person.\n"
        return PageText(text=changed, sha256=hashlib.sha256(changed.encode()).hexdigest())


REVIEW_PATH = "scratch/review/2026-11-02-memory-1a2b3c4d.md"


class RecordingWriter:
    def __init__(
        self,
        outcome: WriteOutcome | None = None,
        *,
        delay_s: float = 0.0,
        propose_outcome: WriteOutcome | None = None,
    ) -> None:
        self.outcome = outcome or WriteOutcome(
            status="published", written_paths=("wiki/decisions/use-sqlite.md",), messages=()
        )
        self.propose_outcome = propose_outcome or WriteOutcome(status="proposed", review_path=REVIEW_PATH)
        self.delay_s = delay_s
        self.calls: list[tuple[Path, Path, float]] = []
        self.proposals: list[tuple[Path, Path, str, float]] = []
        self.drafts: list[dict[str, object]] = []
        self.draft_paths: list[Path] = []
        self.active = 0
        self.max_active = 0
        self._lock = threading.Lock()

    def publish(self, vault_root: Path, draft_path: Path, *, timeout_s: float) -> WriteOutcome:
        with self._lock:
            self.active += 1
            self.max_active = max(self.max_active, self.active)
        try:
            self.calls.append((vault_root, draft_path, timeout_s))
            self.draft_paths.append(draft_path)
            self.drafts.append(json.loads(draft_path.read_text(encoding="utf-8")))
            if self.delay_s:
                time.sleep(self.delay_s)
            return self.outcome
        finally:
            with self._lock:
                self.active -= 1

    def propose(self, vault_root: Path, draft_path: Path, *, summary: str, timeout_s: float) -> WriteOutcome:
        self.proposals.append((vault_root, draft_path, summary, timeout_s))
        self.draft_paths.append(draft_path)
        self.drafts.append(json.loads(draft_path.read_text(encoding="utf-8")))
        return self.propose_outcome


class TimeoutWriter(RecordingWriter):
    def publish(self, vault_root: Path, draft_path: Path, *, timeout_s: float) -> WriteOutcome:
        super().publish(vault_root, draft_path, timeout_s=timeout_s)
        return WriteOutcome(status="error", messages=("publish-draft did not finish in time.",))


class RaisingWriter(RecordingWriter):
    def publish(self, vault_root: Path, draft_path: Path, *, timeout_s: float) -> WriteOutcome:
        super().publish(vault_root, draft_path, timeout_s=timeout_s)
        raise RuntimeError("writer crashed")


class RaisingProposeWriter(RecordingWriter):
    def propose(self, vault_root: Path, draft_path: Path, *, summary: str, timeout_s: float) -> WriteOutcome:
        super().propose(vault_root, draft_path, summary=summary, timeout_s=timeout_s)
        raise RuntimeError("review propose crashed")


class PageWritingWriter(RecordingWriter):
    """Stands in for publish-draft by creating the target page, as a successful run does."""

    def publish(self, vault_root: Path, draft_path: Path, *, timeout_s: float) -> WriteOutcome:
        outcome = super().publish(vault_root, draft_path, timeout_s=timeout_s)
        target = vault_root / str(self.drafts[-1]["path"])
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("# page\n", encoding="utf-8")
        return outcome


def make_vault(tmp_path: Path, name: str, role: str = "project") -> MappedVault:
    root = tmp_path / name
    (root / "wiki").mkdir(parents=True)
    (root / "wiki" / "index.md").write_text("# Index\n", encoding="utf-8")
    return MappedVault(name=name, path=root, role=role)


def add_page(vault: MappedVault, path: str = "wiki/decisions/use-sqlite.md", text: str = PAGE) -> None:
    target = vault.path / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")


def remember_request(**overrides: object) -> RememberRequest:
    values: dict[str, object] = {
        "title": "Use SQLite",
        "kind": "decision",
        "body": "We keep the index in SQLite.",
        "evidence": ("User said so in the 2026-11-02 session.",),
        "basis": "stated",
        "cwd": None,
        "vault": "main",
    }
    values.update(overrides)
    return RememberRequest(**values)  # type: ignore[arg-type]


def update_request(**overrides: object) -> UpdateRequest:
    values: dict[str, object] = {
        "path": "wiki/decisions/use-sqlite.md",
        "body": "We keep the index in SQLite files.",
        "evidence": ("User correction 2026-11-02",),
        "basis": "stated",
        "vault": "main",
    }
    values.update(overrides)
    return UpdateRequest(**values)  # type: ignore[arg-type]


def retire_request(**overrides: object) -> RetireRequest:
    values: dict[str, object] = {
        "path": "wiki/decisions/use-sqlite.md",
        "reason": "We moved to Postgres.",
        "basis": "stated",
        "vault": "main",
    }
    values.update(overrides)
    return RetireRequest(**values)  # type: ignore[arg-type]


def make_service(
    tmp_path: Path,
    writer: RecordingWriter,
    *,
    vaults: tuple[MappedVault, ...] | None = None,
    linked: dict[str, tuple[MappedVault, ...]] | None = None,
    default: MappedVault | None = None,
    page_reader: DiskPageReader | None = None,
) -> MemoryWriteService:
    selected = vaults if vaults is not None else (make_vault(tmp_path, "main"),)
    temp_root = tmp_path / "os-temp"
    temp_root.mkdir(exist_ok=True)
    return MemoryWriteService(
        vault_map=FakeVaultMap(selected, linked or {}, default),
        writer=writer,
        page_reader=page_reader or DiskPageReader(),
        today=lambda: TODAY,
        drafts=TemporaryDraftFiles(temp_root=temp_root),
    )


# Input checks


@pytest.mark.parametrize(
    ("overrides", "reason"),
    [
        ({"title": "  "}, "title"),
        ({"body": ""}, "body"),
        ({"evidence": ()}, "evidence"),
        ({"evidence": ("  ",)}, "evidence"),
        ({"kind": "inferred"}, "kind"),
        ({"kind": "concept"}, "kind"),
        ({"basis": "guessed"}, "basis"),
        ({"basis": None}, "basis"),
        ({"memory_kind": "habit"}, "memory_kind"),
        ({"pin": "yes"}, "pin"),
    ],
)
def test_invalid_remember_input_is_rejected_without_calling_the_writer(
    tmp_path: Path, overrides: dict[str, object], reason: str
) -> None:
    writer = RecordingWriter()
    result = make_service(tmp_path, writer).remember(remember_request(**overrides))

    assert result.status == "rejected"
    assert result.written_paths == ()
    assert any(reason in message for message in result.messages)
    assert writer.calls == []


@pytest.mark.parametrize(
    "overrides",
    [
        {"path": "../outside.md"},
        {"path": "/abs/wiki/a.md"},
        {"path": "raw/a.md"},
        {"path": "wiki/a.txt"},
        {"path": "wiki/../raw/a.md"},
        {"body": " "},
        {"evidence": ()},
        {"memory_kind": "habit"},
        {"pin": "true"},
        {"title": " "},
    ],
)
def test_invalid_update_input_is_rejected_without_calling_the_writer(
    tmp_path: Path, overrides: dict[str, object]
) -> None:
    writer = RecordingWriter()
    result = make_service(tmp_path, writer).update(update_request(**overrides))

    assert result.status == "rejected"
    assert writer.calls == []


@pytest.mark.parametrize(
    "overrides",
    [
        {"reason": " "},
        {"reason": "two\nlines"},
        {"path": "wiki/a.txt"},
        {"replaced_by": "raw/b.md"},
        {"replaced_by": "wiki/decisions/use-sqlite.md"},
    ],
)
def test_invalid_retire_input_is_rejected_without_calling_the_writer(
    tmp_path: Path, overrides: dict[str, object]
) -> None:
    writer = RecordingWriter()
    result = make_service(tmp_path, writer).retire(retire_request(**overrides))

    assert result.status == "rejected"
    assert writer.calls == []


# Inferred path (V3 basis, 계약4, A-3 unit level): a proposal waits in Vault review.

APPROVAL_LINE = f'review resolve {REVIEW_PATH} --status accepted --resolution "<reason>"'


def inferred_requests() -> dict[str, object]:
    return {
        "remember": remember_request(basis="inferred", title="Another"),
        "update": update_request(basis="inferred"),
        "retire": retire_request(basis="inferred"),
    }


@pytest.mark.parametrize(
    ("operation", "operation_name", "summary"),
    [
        ("remember", "upsert-page", "Add memory: Another"),
        ("update", "upsert-page", "Update memory wiki/decisions/use-sqlite.md"),
        ("retire", "patch-page", "Retire memory wiki/decisions/use-sqlite.md: We moved to Postgres."),
    ],
)
def test_inferred_basis_is_proposed_for_review_instead_of_published(
    tmp_path: Path, operation: str, operation_name: str, summary: str
) -> None:
    main = make_vault(tmp_path, "main")
    add_page(main)
    writer = RecordingWriter()
    service = make_service(tmp_path, writer, vaults=(main,))

    result = getattr(service, operation)(inferred_requests()[operation])

    assert result.status == "proposed"
    assert result.review_path == REVIEW_PATH
    assert (result.vault, result.vault_role) == ("main", "project")
    assert result.written_paths == ()
    assert writer.calls == []
    assert len(writer.proposals) == 1
    vault_root, _, sent_summary, timeout_s = writer.proposals[0]
    assert (vault_root, sent_summary, timeout_s) == (main.path, summary, PUBLISH_TIMEOUT_SECONDS)
    assert writer.drafts[0]["operation"] == operation_name
    assert sum(APPROVAL_LINE in message for message in result.messages) == 1
    assert not any("next index" in message for message in result.messages)


@pytest.mark.parametrize("operation", ["remember", "update"])
def test_inferred_draft_records_basis_inferred_in_the_evidence_section(tmp_path: Path, operation: str) -> None:
    main = make_vault(tmp_path, "main")
    add_page(main)
    writer = RecordingWriter()

    getattr(make_service(tmp_path, writer, vaults=(main,)), operation)(inferred_requests()[operation])

    assert "Status: inferred" in str(writer.drafts[0]["body"])


def test_stated_basis_never_proposes(tmp_path: Path) -> None:
    writer = RecordingWriter()

    result = make_service(tmp_path, writer).remember(remember_request())

    assert result.status == "published"
    assert result.review_path is None
    assert writer.proposals == []


@pytest.mark.parametrize(
    ("outcome", "status"),
    [
        (WriteOutcome(status="rejected", messages=("Memory proposal already exists",)), "rejected"),
        (WriteOutcome(status="error", messages=("Migrate the Vault",)), "error"),
    ],
)
def test_proposal_that_is_not_proposed_has_no_review_path_or_approval_line(
    tmp_path: Path, outcome: WriteOutcome, status: str
) -> None:
    writer = RecordingWriter(propose_outcome=outcome)

    result = make_service(tmp_path, writer).remember(remember_request(basis="inferred"))

    assert result.status == status
    assert result.review_path is None
    assert result.messages[: len(outcome.messages)] == outcome.messages
    assert not any("review resolve" in message for message in result.messages)


def test_proposed_outcome_without_review_path_is_an_error(tmp_path: Path) -> None:
    writer = RecordingWriter(propose_outcome=WriteOutcome(status="proposed"))

    result = make_service(tmp_path, writer).remember(remember_request(basis="inferred"))

    assert result.status == "error"
    assert result.review_path is None


def test_propose_exception_becomes_error_and_removes_the_draft(tmp_path: Path) -> None:
    writer = RaisingProposeWriter()

    result = make_service(tmp_path, writer).remember(remember_request(basis="inferred"))

    assert result.status == "error"
    assert any("review propose crashed" in message for message in result.messages)
    assert not writer.draft_paths[0].parent.exists()
    assert list((tmp_path / "os-temp").iterdir()) == []


def test_inferred_update_is_not_proposed_when_the_page_changes(tmp_path: Path) -> None:
    main = make_vault(tmp_path, "main")
    add_page(main)
    writer = RecordingWriter()
    service = make_service(tmp_path, writer, vaults=(main,), page_reader=ChangingPageReader())

    result = service.update(update_request(basis="inferred"))

    assert result.status == "rejected"
    assert writer.proposals == []


def test_inferred_remember_of_an_existing_page_is_rejected_before_proposing(tmp_path: Path) -> None:
    main = make_vault(tmp_path, "main")
    add_page(main)
    writer = RecordingWriter()

    result = make_service(tmp_path, writer, vaults=(main,)).remember(remember_request(basis="inferred"))

    assert result.status == "rejected"
    assert writer.proposals == []


# Write Vault choice (결정12, A-8)


@pytest.mark.parametrize("memory_kind", [None, "rule", "correction", "decision", "preference"])
def test_memory_kind_does_not_change_the_chosen_vault(tmp_path: Path, memory_kind: str | None) -> None:
    personal = make_vault(tmp_path, "personal", role="personal")
    team = make_vault(tmp_path, "team", role="team")
    writer = RecordingWriter()
    service = make_service(tmp_path, writer, vaults=(personal, team), linked={"/repo": (personal, team)}, default=team)

    result = service.remember(remember_request(vault=None, cwd="/repo", memory_kind=memory_kind))

    assert result.status == "published"
    assert (result.vault, result.vault_role) == ("team", "team")
    assert writer.calls[0][0] == team.path


def test_two_linked_vaults_without_default_return_vault_required(tmp_path: Path) -> None:
    main = make_vault(tmp_path, "main")
    other = make_vault(tmp_path, "other", role="team")
    writer = RecordingWriter()
    service = make_service(tmp_path, writer, vaults=(main, other), linked={"/repo": (main, other)})

    result = service.remember(remember_request(vault=None, cwd="/repo"))

    assert result.status == "vault_required"
    assert result.vault is None
    assert [(candidate.name, candidate.role) for candidate in result.candidates] == [
        ("main", "project"),
        ("other", "team"),
    ]
    assert writer.calls == []


def test_vault_not_linked_to_the_cwd_project_is_rejected_with_the_linked_list(tmp_path: Path) -> None:
    main = make_vault(tmp_path, "main")
    other = make_vault(tmp_path, "other")
    writer = RecordingWriter()
    service = make_service(tmp_path, writer, vaults=(main, other), linked={"/repo": (main,)})

    result = service.remember(remember_request(vault="other", cwd="/repo"))

    assert result.status == "rejected"
    assert any("not linked" in message and "main" in message for message in result.messages)
    assert writer.calls == []


def test_vault_argument_selects_the_named_vault_inside_the_project(tmp_path: Path) -> None:
    main = make_vault(tmp_path, "main")
    other = make_vault(tmp_path, "other")
    writer = RecordingWriter()
    service = make_service(tmp_path, writer, vaults=(main, other), linked={"/repo": (main, other)}, default=main)

    result = service.remember(remember_request(vault="other", cwd="/repo"))

    assert result.status == "published"
    assert result.vault == "other"
    assert writer.calls[0][0] == other.path
    assert writer.calls[0][2] == PUBLISH_TIMEOUT_SECONDS == 120


def test_missing_vault_map_is_an_error(tmp_path: Path) -> None:
    writer = RecordingWriter()
    service = MemoryWriteService(
        vault_map=None,
        writer=writer,
        page_reader=DiskPageReader(),
        today=lambda: TODAY,
        drafts=TemporaryDraftFiles(temp_root=tmp_path),
    )

    for result in (
        service.remember(remember_request()),
        service.update(update_request()),
        service.retire(retire_request()),
    ):
        assert result.status == "error"
    assert writer.calls == []


# Add


def test_existing_target_page_is_rejected_and_points_to_update_memory(tmp_path: Path) -> None:
    main = make_vault(tmp_path, "main")
    add_page(main)
    writer = RecordingWriter()
    service = make_service(tmp_path, writer, vaults=(main,))

    result = service.remember(remember_request())

    assert result.status == "rejected"
    assert any("wiki/decisions/use-sqlite.md" in message and "update_memory" in message for message in result.messages)
    assert writer.calls == []


def test_remember_publishes_the_memory_fields(tmp_path: Path) -> None:
    writer = RecordingWriter()

    result = make_service(tmp_path, writer).remember(remember_request(pin=True, memory_kind="rule"))

    assert result.status == "published"
    frontmatter = writer.drafts[0]["frontmatter"]
    assert isinstance(frontmatter, dict)
    assert (frontmatter["memory_schema"], frontmatter["pin"], frontmatter["memory_kind"]) == (
        "vault-memory/v1",
        True,
        "rule",
    )


# Update


def test_update_publishes_the_new_body_in_the_vault_that_has_the_page(tmp_path: Path) -> None:
    main = make_vault(tmp_path, "main")
    other = make_vault(tmp_path, "other")
    add_page(other)
    writer = RecordingWriter()
    service = make_service(tmp_path, writer, vaults=(main, other), linked={"/repo": (main, other)}, default=main)

    result = service.update(update_request(vault=None, cwd="/repo"))

    assert result.status == "published"
    assert result.vault == "other"
    assert writer.calls[0][0] == other.path
    draft = writer.drafts[0]
    assert draft["operation"] == "upsert-page"
    assert "We keep the index in SQLite files." in str(draft["body"])
    assert draft["frontmatter"]["updated"] == "2026-11-02"  # type: ignore[index]


@pytest.mark.parametrize(
    ("holders", "status"),
    [((), "rejected"), (("main", "other"), "vault_required")],
    ids=["none", "two"],
)
def test_update_target_vault_count(tmp_path: Path, holders: tuple[str, ...], status: str) -> None:
    vaults = {name: make_vault(tmp_path, name) for name in ("main", "other")}
    for name in holders:
        add_page(vaults[name])
    writer = RecordingWriter()
    service = make_service(tmp_path, writer, vaults=tuple(vaults.values()), linked={"/repo": tuple(vaults.values())})

    result = service.update(update_request(vault=None, cwd="/repo"))

    assert result.status == status
    assert writer.calls == []


def test_update_is_rejected_when_the_page_changes_before_publish(tmp_path: Path) -> None:
    main = make_vault(tmp_path, "main")
    add_page(main)
    writer = RecordingWriter()
    reader = ChangingPageReader()
    service = make_service(tmp_path, writer, vaults=(main,), page_reader=reader)

    result = service.update(update_request())

    assert result.status == "rejected"
    assert any("changed" in message and "read it again" in message for message in result.messages)
    assert writer.calls == []


def test_update_rechecks_the_page_hash_right_before_publish(tmp_path: Path) -> None:
    main = make_vault(tmp_path, "main")
    add_page(main)
    order: list[str] = []

    class OrderReader(DiskPageReader):
        def read(self, vault_root: Path, path: str) -> PageText | None:
            order.append("read")
            return super().read(vault_root, path)

    class OrderWriter(RecordingWriter):
        def publish(self, vault_root: Path, draft_path: Path, *, timeout_s: float) -> WriteOutcome:
            order.append("draft written" if draft_path.is_file() else "no draft")
            order.append("publish")
            return super().publish(vault_root, draft_path, timeout_s=timeout_s)

    result = make_service(tmp_path, OrderWriter(), vaults=(main,), page_reader=OrderReader()).update(update_request())

    assert result.status == "published"
    assert order.count("read") >= 2
    assert order[-3:] == ["read", "draft written", "publish"]


def test_update_of_a_page_without_frontmatter_is_rejected(tmp_path: Path) -> None:
    main = make_vault(tmp_path, "main")
    add_page(main, text="# Human page\n")
    writer = RecordingWriter()

    result = make_service(tmp_path, writer, vaults=(main,)).update(update_request())

    assert result.status == "rejected"
    assert writer.calls == []


# Retire


def test_retire_publishes_a_frontmatter_only_patch(tmp_path: Path) -> None:
    main = make_vault(tmp_path, "main")
    add_page(main)
    writer = RecordingWriter()

    result = make_service(tmp_path, writer, vaults=(main,)).retire(retire_request())

    assert result.status == "published"
    assert writer.drafts[0]["operation"] == "patch-page"
    assert writer.drafts[0]["frontmatter"] == {
        "status": "retired",
        "retired_reason": "We moved to Postgres.",
        "retired_at": "2026-11-02",
    }


def test_retire_of_a_missing_page_is_rejected(tmp_path: Path) -> None:
    writer = RecordingWriter()

    result = make_service(tmp_path, writer).retire(retire_request())

    assert result.status == "rejected"
    assert writer.calls == []


def test_retire_replacement_must_be_in_the_same_vault(tmp_path: Path) -> None:
    main = make_vault(tmp_path, "main")
    other = make_vault(tmp_path, "other")
    add_page(main)
    add_page(other, "wiki/decisions/use-postgres.md")
    writer = RecordingWriter()
    service = make_service(tmp_path, writer, vaults=(main, other), linked={"/repo": (main, other)})

    result = service.retire(retire_request(vault="main", cwd="/repo", replaced_by="wiki/decisions/use-postgres.md"))

    assert result.status == "rejected"
    assert any("use-postgres" in message for message in result.messages)
    assert writer.calls == []


def test_retire_with_replacement_in_the_same_vault_publishes(tmp_path: Path) -> None:
    main = make_vault(tmp_path, "main")
    add_page(main)
    add_page(main, "wiki/decisions/use-postgres.md")
    writer = RecordingWriter()

    result = make_service(tmp_path, writer, vaults=(main,)).retire(
        retire_request(replaced_by="wiki/decisions/use-postgres.md")
    )

    assert result.status == "published"
    assert writer.drafts[0]["frontmatter"] == {"status": "deprecated", "superseded_by": ["decisions/use-postgres"]}


# Shared behavior


@pytest.mark.parametrize(
    "writer",
    [
        RecordingWriter(),
        RecordingWriter(WriteOutcome(status="rejected", messages=("Draft failed validation",))),
        TimeoutWriter(),
        RaisingWriter(),
    ],
    ids=["published", "rejected", "timeout", "raised"],
)
def test_draft_directory_is_removed_after_every_outcome(tmp_path: Path, writer: RecordingWriter) -> None:
    make_service(tmp_path, writer).remember(remember_request())

    draft_path = writer.draft_paths[0]
    assert draft_path.is_relative_to(tmp_path / "os-temp")
    assert not draft_path.parent.exists()
    assert list((tmp_path / "os-temp").iterdir()) == []


@pytest.mark.parametrize(
    ("outcome", "status"),
    [
        (WriteOutcome(status="published", written_paths=("wiki/decisions/a.md",), messages=("ok",)), "published"),
        (WriteOutcome(status="rejected", messages=("Target page is human-locked",), reason="human-locked"), "rejected"),
        (WriteOutcome(status="error", messages=("timed out",)), "error"),
    ],
)
def test_writer_outcome_is_returned_as_is(tmp_path: Path, outcome: WriteOutcome, status: str) -> None:
    result = make_service(tmp_path, RecordingWriter(outcome)).remember(remember_request())

    assert result.status == status
    assert (result.vault, result.vault_role) == ("main", "project")
    assert result.written_paths == outcome.written_paths
    assert result.messages[: len(outcome.messages)] == outcome.messages


def test_published_result_says_search_waits_for_the_next_index(tmp_path: Path) -> None:
    result = make_service(tmp_path, RecordingWriter()).remember(remember_request())

    assert any("next index" in message for message in result.messages)


def test_writer_exception_becomes_error(tmp_path: Path) -> None:
    result = make_service(tmp_path, RaisingWriter()).remember(remember_request())

    assert result.status == "error"
    assert any("writer crashed" in message for message in result.messages)


def test_calls_for_the_same_vault_run_one_at_a_time(tmp_path: Path) -> None:
    main = make_vault(tmp_path, "main")
    add_page(main, "wiki/decisions/existing.md")
    writer = RecordingWriter(delay_s=0.05)
    service = make_service(tmp_path, writer, vaults=(main,))
    other_service = make_service(tmp_path, writer, vaults=(main,))
    calls: list[tuple[Callable[[Any], object], object]] = [
        (service.remember, remember_request(title="Decision 1")),
        (other_service.remember, remember_request(title="Decision 2")),
        (service.update, update_request(path="wiki/decisions/existing.md")),
        (other_service.retire, retire_request(path="wiki/decisions/existing.md")),
    ]
    threads = [threading.Thread(target=call, args=(request,)) for call, request in calls]

    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert len(writer.calls) == 4
    assert writer.max_active == 1


def test_concurrent_calls_for_the_same_page_publish_once(tmp_path: Path) -> None:
    main = make_vault(tmp_path, "main")
    writer = PageWritingWriter(delay_s=0.05)
    service = make_service(tmp_path, writer, vaults=(main,))
    other_service = make_service(tmp_path, writer, vaults=(main,))
    results: list[str] = []

    def call(target_service: MemoryWriteService) -> None:
        results.append(target_service.remember(remember_request()).status)

    threads = [threading.Thread(target=call, args=(service if index % 2 else other_service,)) for index in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert len(writer.calls) == 1
    assert sorted(results) == ["published", "rejected", "rejected", "rejected"]


def test_writes_create_no_file_under_the_vault_root(tmp_path: Path) -> None:
    main = make_vault(tmp_path, "main")
    add_page(main)
    before = file_bytes(main.path)
    writer = RecordingWriter()
    service = make_service(tmp_path, writer, vaults=(main,))

    service.remember(remember_request(title="New"))
    service.update(update_request())
    service.retire(retire_request())

    assert len(writer.calls) == 3
    assert not any(path.is_relative_to(main.path) for path in writer.draft_paths)
    assert file_bytes(main.path) == before
