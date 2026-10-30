"""A-13: remember checks input, picks one Vault, and hands a temporary draft to the publisher.

Source: spec 2026-10-29-local-graph-memory-layer 4.2.4, S5, S6, 6절 remember rows.
"""

from __future__ import annotations

import json
import threading
import time
from datetime import date
from pathlib import Path

import pytest

from tests.test_read_only_boundary import file_bytes
from vault_graph.operation.integration.remember_service import (
    PUBLISH_TIMEOUT_SECONDS,
    PublishOutcome,
    RememberRequest,
    RememberService,
    build_draft,
)
from vault_graph.project.context.project_binding_reader import MappedProjectMatch, MappedVault

TODAY = date(2026, 10, 30)


class FakeVaultMap:
    def __init__(self, vaults: tuple[MappedVault, ...], linked: dict[str, tuple[MappedVault, ...]]) -> None:
        self._vaults = vaults
        self._linked = linked

    @property
    def vaults(self) -> tuple[MappedVault, ...]:
        return self._vaults

    def find_project(self, cwd: Path) -> MappedProjectMatch:
        linked = self._linked.get(str(cwd))
        if linked is None:
            return MappedProjectMatch(None, None, (), reason=f"{cwd} is not linked to a project.")
        return MappedProjectMatch("project", "root", linked)

    def vaults_for(self, cwd: Path) -> tuple[MappedVault, ...]:
        return self.find_project(cwd).vaults


class RecordingPublisher:
    def __init__(self, outcome: PublishOutcome | None = None, *, delay_s: float = 0.0) -> None:
        self.outcome = outcome or PublishOutcome(
            status="published", written_paths=("wiki/decisions/use-sqlite.md",), messages=("Applied draft",)
        )
        self.delay_s = delay_s
        self.calls: list[tuple[Path, Path, float]] = []
        self.drafts: list[dict[str, object]] = []
        self.draft_paths: list[Path] = []
        self.active = 0
        self.max_active = 0
        self._lock = threading.Lock()

    def publish_draft(self, vault_root: Path, draft_path: Path, *, timeout_s: float) -> PublishOutcome:
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


class TimeoutPublisher(RecordingPublisher):
    def publish_draft(self, vault_root: Path, draft_path: Path, *, timeout_s: float) -> PublishOutcome:
        super().publish_draft(vault_root, draft_path, timeout_s=timeout_s)
        return PublishOutcome(status="error", messages=("publish-draft did not finish in time.",))


class RaisingPublisher(RecordingPublisher):
    def publish_draft(self, vault_root: Path, draft_path: Path, *, timeout_s: float) -> PublishOutcome:
        super().publish_draft(vault_root, draft_path, timeout_s=timeout_s)
        raise RuntimeError("publisher crashed")


def make_vault(tmp_path: Path, name: str) -> MappedVault:
    root = tmp_path / name
    (root / "wiki").mkdir(parents=True)
    (root / "wiki" / "index.md").write_text("# Index\n", encoding="utf-8")
    return MappedVault(name=name, path=root, role="project")


def make_request(**overrides: object) -> RememberRequest:
    values: dict[str, object] = {
        "title": "Use SQLite",
        "kind": "decision",
        "body": "We keep the index in SQLite.",
        "evidence": ("User said so in the 2026-10-30 session.",),
        "cwd": None,
        "vault": "main",
    }
    values.update(overrides)
    return RememberRequest(**values)  # type: ignore[arg-type]


def make_service(
    tmp_path: Path,
    publisher: RecordingPublisher,
    *,
    vaults: tuple[MappedVault, ...] | None = None,
    linked: dict[str, tuple[MappedVault, ...]] | None = None,
) -> RememberService:
    selected = vaults if vaults is not None else (make_vault(tmp_path, "main"),)
    temp_root = tmp_path / "os-temp"
    temp_root.mkdir(exist_ok=True)
    return RememberService(
        vault_map=FakeVaultMap(selected, linked or {}),
        publisher=publisher,
        today=lambda: TODAY,
        temp_root=temp_root,
    )


@pytest.mark.parametrize(
    ("overrides", "reason"),
    [
        ({"title": "  "}, "title"),
        ({"body": ""}, "body"),
        ({"evidence": ()}, "evidence"),
        ({"evidence": ("  ",)}, "evidence"),
        ({"kind": "inferred"}, "kind"),
        ({"kind": "concept"}, "kind"),
    ],
)
def test_invalid_input_is_rejected_without_calling_the_publisher(
    tmp_path: Path, overrides: dict[str, object], reason: str
) -> None:
    publisher = RecordingPublisher()
    service = make_service(tmp_path, publisher)

    result = service.remember(make_request(**overrides))

    assert result.status == "rejected"
    assert result.written_paths == ()
    assert any(reason in message for message in result.messages)
    assert publisher.calls == []


def test_vault_argument_selects_the_named_vault(tmp_path: Path) -> None:
    main = make_vault(tmp_path, "main")
    other = make_vault(tmp_path, "other")
    publisher = RecordingPublisher()
    service = make_service(tmp_path, publisher, vaults=(main, other), linked={"/repo": (main,)})

    result = service.remember(make_request(vault="other", cwd="/repo"))

    assert result.status == "published"
    assert result.vault == "other"
    assert publisher.calls[0][0] == other.path
    assert publisher.calls[0][2] == PUBLISH_TIMEOUT_SECONDS == 120


def test_unknown_vault_argument_is_an_error(tmp_path: Path) -> None:
    publisher = RecordingPublisher()
    service = make_service(tmp_path, publisher)

    result = service.remember(make_request(vault="missing"))

    assert result.status == "error"
    assert any("missing" in message for message in result.messages)
    assert publisher.calls == []


def test_single_linked_vault_is_used_when_vault_is_not_given(tmp_path: Path) -> None:
    main = make_vault(tmp_path, "main")
    publisher = RecordingPublisher()
    service = make_service(tmp_path, publisher, vaults=(main,), linked={"/repo": (main,)})

    result = service.remember(make_request(vault=None, cwd="/repo"))

    assert result.status == "published"
    assert result.vault == "main"
    assert publisher.calls[0][0] == main.path


@pytest.mark.parametrize("cwd", [None, "/unlinked", "/two"])
def test_no_single_vault_is_an_error_and_nothing_runs(tmp_path: Path, cwd: str | None) -> None:
    main = make_vault(tmp_path, "main")
    other = make_vault(tmp_path, "other")
    publisher = RecordingPublisher()
    service = make_service(tmp_path, publisher, vaults=(main, other), linked={"/two": (main, other)})

    result = service.remember(make_request(vault=None, cwd=cwd))

    assert result.status == "error"
    assert result.vault is None
    assert any("Cannot choose the target Vault" in message for message in result.messages)
    assert publisher.calls == []


def test_missing_vault_map_is_an_error(tmp_path: Path) -> None:
    publisher = RecordingPublisher()
    service = RememberService(vault_map=None, publisher=publisher, today=lambda: TODAY, temp_root=tmp_path)

    result = service.remember(make_request())

    assert result.status == "error"
    assert publisher.calls == []


@pytest.mark.parametrize(
    "publisher",
    [
        RecordingPublisher(),
        RecordingPublisher(PublishOutcome(status="rejected", messages=("Draft failed validation",))),
        TimeoutPublisher(),
        RaisingPublisher(),
    ],
    ids=["published", "rejected", "timeout", "raised"],
)
def test_draft_directory_is_removed_after_every_outcome(tmp_path: Path, publisher: RecordingPublisher) -> None:
    service = make_service(tmp_path, publisher)

    service.remember(make_request())

    draft_path = publisher.draft_paths[0]
    assert draft_path.is_relative_to(tmp_path / "os-temp")
    assert not draft_path.exists()
    assert not draft_path.parent.exists()
    assert list((tmp_path / "os-temp").iterdir()) == []


@pytest.mark.parametrize(
    ("outcome", "status"),
    [
        (PublishOutcome(status="published", written_paths=("wiki/decisions/a.md",), messages=("ok",)), "published"),
        (PublishOutcome(status="rejected", messages=("Draft failed validation",)), "rejected"),
        (PublishOutcome(status="error", messages=("timed out",)), "error"),
    ],
)
def test_publisher_outcome_is_returned_as_is(tmp_path: Path, outcome: PublishOutcome, status: str) -> None:
    service = make_service(tmp_path, RecordingPublisher(outcome))

    result = service.remember(make_request())

    assert result.status == status
    assert result.vault == "main"
    assert result.written_paths == outcome.written_paths
    assert result.messages[: len(outcome.messages)] == outcome.messages


def test_published_result_says_search_waits_for_the_next_index(tmp_path: Path) -> None:
    result = make_service(tmp_path, RecordingPublisher()).remember(make_request())

    assert any("next index" in message for message in result.messages)


def test_publisher_exception_becomes_error(tmp_path: Path) -> None:
    result = make_service(tmp_path, RaisingPublisher()).remember(make_request())

    assert result.status == "error"
    assert any("publisher crashed" in message for message in result.messages)


def test_calls_for_the_same_vault_run_one_at_a_time(tmp_path: Path) -> None:
    main = make_vault(tmp_path, "main")
    publisher = RecordingPublisher(delay_s=0.05)
    service = make_service(tmp_path, publisher, vaults=(main,))
    other_service = make_service(tmp_path, publisher, vaults=(main,))
    threads = [
        threading.Thread(target=(service if index % 2 else other_service).remember, args=(make_request(),))
        for index in range(4)
    ]

    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert len(publisher.calls) == 4
    assert publisher.max_active == 1


def test_remember_creates_no_file_under_the_vault_root(tmp_path: Path) -> None:
    main = make_vault(tmp_path, "main")
    before = file_bytes(main.path)
    publisher = RecordingPublisher()
    service = make_service(tmp_path, publisher, vaults=(main,))

    service.remember(make_request())

    assert not publisher.draft_paths[0].is_relative_to(main.path)
    assert file_bytes(main.path) == before


def test_existing_target_page_is_rejected_without_calling_the_publisher(tmp_path: Path) -> None:
    main = make_vault(tmp_path, "main")
    (main.path / "wiki" / "decisions").mkdir()
    (main.path / "wiki" / "decisions" / "use-sqlite.md").write_text("# Human page\n", encoding="utf-8")
    publisher = RecordingPublisher()
    service = make_service(tmp_path, publisher, vaults=(main,))

    result = service.remember(make_request())

    assert result.status == "rejected"
    assert any("wiki/decisions/use-sqlite.md" in message for message in result.messages)
    assert publisher.calls == []


def test_draft_follows_the_vault_upsert_page_format() -> None:
    draft = build_draft(make_request(evidence=("Session note A", "Session note B")), today=TODAY)

    assert draft == {
        "version": 1,
        "operation": "upsert-page",
        "path": "wiki/decisions/use-sqlite.md",
        "frontmatter": {
            "title": "Use SQLite",
            "type": "decision",
            "status": "active",
            "created": "2026-10-30",
            "updated": "2026-10-30",
            "owner": "agent",
            "summary": "Use SQLite",
            "source_count": 2,
            "tags": [],
            "related": [],
            "confidence": "medium",
            "quality": {
                "provenance": "section",
                "links": "unchecked",
                "contradictions": "unchecked",
                "review_required": False,
            },
        },
        "body": (
            "# Use SQLite\n\nWe keep the index in SQLite.\n\n## Evidence\n\nStatus: stated\n\n"
            "- Evidence: Session note A\n- Evidence: Session note B\n"
        ),
        "index": {"section": "Decisions", "target": "decisions/use-sqlite", "summary": "Use SQLite"},
        "log": {
            "event_type": "decision",
            "title": "Remember decision: Use SQLite",
            "items": ["Added [[decisions/use-sqlite]]."],
        },
    }


def test_system_draft_goes_to_wiki_systems() -> None:
    draft = build_draft(make_request(kind="system", title="Index Watcher"), today=TODAY)

    assert draft["path"] == "wiki/systems/index-watcher.md"
    assert draft["index"] == {"section": "Systems", "target": "systems/index-watcher", "summary": "Index Watcher"}
    assert draft["log"]["event_type"] == "manual-note"  # type: ignore[index]


def test_draft_is_deterministic_and_keeps_korean_titles() -> None:
    request = make_request(title="결정: 색인은 SQLite에 둔다")

    first = build_draft(request, today=TODAY)
    second = build_draft(request, today=TODAY)

    assert first == second
    assert first["path"] == "wiki/decisions/결정-색인은-sqlite에-둔다.md"


def test_title_without_word_characters_gets_a_stable_hash_slug() -> None:
    first = build_draft(make_request(title="!!!"), today=TODAY)
    second = build_draft(make_request(title="!!!"), today=TODAY)

    assert first["path"] == second["path"]
    assert str(first["path"]).startswith("wiki/decisions/memory-")
