"""The quote check of stated memory writes that cite a session exchange (spec 2026-11-19 D4)."""

from __future__ import annotations

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
    update_request,
)
from vault_graph.interface.composition.adapters.session_exchange_reader import SessionExchangeFileReader
from vault_graph.interface.composition.adapters.temporary_draft_files import TemporaryDraftFiles
from vault_graph.interface.mcp.mcp_memory_tools import (
    parse_remember_input,
    parse_supersede_claim_input,
    parse_update_memory_input,
)
from vault_graph.operation.memory.memory_requests import SupersedeClaimRequest
from vault_graph.operation.memory.memory_write_service import (
    QUOTE_NOT_FOUND_MESSAGE,
    QUOTE_REQUIRED_MESSAGE,
    QUOTE_UNREADABLE_MESSAGE,
    MemoryWriteService,
)
from vault_graph.project.context.project_binding_reader import MappedVault

PART = "raw/sessions/claude-code/2026-11-10-s1-part1.md"
QUOTE = "임베딩 모델은 arctic-m으로 정했어"
LOCATION = f"{PART} L8-L16"

V2_SESSION = """---
schema: vault-session/v2
session_id: s1
---

# Session s1

## 임베딩 모델 2026-11-10T09:00:00.000Z · u-1
<!-- vg:exchange id=u-1 scope=main started=2026-11-10T09:00:00.000Z outcome=answered -->

### user · 2026-11-10T09:00:00.000Z · u-1

아니야, 그 방법 말고
임베딩 모델은 arctic-m으로 정했어.

### assistant · 2026-11-10T09:00:05.000Z · a-1

알겠습니다. 기본 프리셋은 e5-small에서 arctic-m으로 바꾸겠습니다.

## Subagent a7f3 · reviewer · 2026-11-10T09:01:00.000Z · s-2
<!-- vg:exchange id=s-2 scope=subagent:a7f3 started=2026-11-10T09:01:00.000Z outcome=answered -->

### user · 2026-11-10T09:01:00.000Z · s-2

Review the embedding preset change. Do not edit files.
"""

V1_SESSION = """---
schema: vault-session/v1
---

## 2026-11-10T09:00:00.000Z user

임베딩 모델은 arctic-m으로 정했어.

## 2026-11-10T09:00:05.000Z assistant

알겠습니다. e5-small 대신 arctic-m을 기본으로 둡니다.
"""


class World:
    def __init__(self, tmp_path: Path, *, with_reader: bool = True) -> None:
        self.vault: MappedVault = make_vault(tmp_path, "main")
        session = self.vault.path / PART
        session.parent.mkdir(parents=True)
        session.write_text(V2_SESSION, encoding="utf-8")
        self.writer = RecordingWriter()
        temp_root = tmp_path / "os-temp"
        temp_root.mkdir()
        self.service = MemoryWriteService(
            vault_map=FakeVaultMap((self.vault,), {}),
            writer=self.writer,
            page_reader=DiskPageReader(),
            today=lambda: TODAY,
            drafts=TemporaryDraftFiles(temp_root=temp_root),
            exchange_reader=SessionExchangeFileReader() if with_reader else None,
        )


# remember


def test_stated_with_a_session_exchange_and_the_users_words_is_published(tmp_path: Path) -> None:
    world = World(tmp_path)

    result = world.service.remember(remember_request(evidence=(LOCATION,), quote=QUOTE))

    assert result.status == "published"
    assert len(world.writer.calls) == 1


def test_stated_with_a_session_exchange_needs_a_quote(tmp_path: Path) -> None:
    world = World(tmp_path)

    result = world.service.remember(remember_request(evidence=(LOCATION,)))

    assert result.status == "rejected"
    assert result.messages == (QUOTE_REQUIRED_MESSAGE,)
    assert world.writer.calls == []


@pytest.mark.parametrize(
    "quote",
    [
        "임베딩 모델은 e5-small로 정했어",  # the user did not say it
        "기본 프리셋은 e5-small에서 arctic-m으로 바꾸겠습니다",  # the assistant said it
        "아니야",  # too short to prove anything
    ],
)
def test_a_quote_that_is_not_the_users_words_there_is_rejected(tmp_path: Path, quote: str) -> None:
    world = World(tmp_path)

    result = world.service.remember(remember_request(evidence=(LOCATION,), quote=quote))

    assert result.status == "rejected"
    assert result.messages == (QUOTE_NOT_FOUND_MESSAGE,)
    assert world.writer.calls == []


def test_a_quote_from_another_exchange_of_the_file_is_rejected(tmp_path: Path) -> None:
    world = World(tmp_path)

    result = world.service.remember(
        remember_request(evidence=(f"{PART} L19-L24",), quote="Review the embedding preset change")
    )

    # Lines 19-24 are a subagent exchange: nothing in it was typed by a person.
    assert result.messages == (QUOTE_NOT_FOUND_MESSAGE,)


def test_the_quote_may_be_in_any_one_of_several_cited_exchanges(tmp_path: Path) -> None:
    world = World(tmp_path)

    result = world.service.remember(remember_request(evidence=(f"{PART} L19-L24", LOCATION), quote=QUOTE))

    assert result.status == "published"


def test_a_cited_session_file_that_cannot_be_read_is_rejected(tmp_path: Path) -> None:
    world = World(tmp_path)

    result = world.service.remember(remember_request(evidence=("raw/sessions/2026-11-01-gone.md L1-L9",), quote=QUOTE))

    assert result.status == "rejected"
    assert result.messages == (f"{QUOTE_UNREADABLE_MESSAGE}: raw/sessions/2026-11-01-gone.md L1-L9.",)


def test_evidence_that_names_no_session_exchange_is_not_checked(tmp_path: Path) -> None:
    world = World(tmp_path)

    plain = world.service.remember(remember_request(title="A", evidence=("User said so on 2026-11-10.",)))
    path_only = world.service.remember(remember_request(title="B", evidence=(PART,), quote="anything at all"))

    assert (plain.status, path_only.status) == ("published", "published")


def test_inferred_needs_no_quote_but_a_given_quote_is_checked(tmp_path: Path) -> None:
    world = World(tmp_path)

    without = world.service.remember(remember_request(title="A", basis="inferred", evidence=(LOCATION,)))
    wrong = world.service.remember(
        remember_request(title="B", basis="inferred", evidence=(LOCATION,), quote="임베딩 모델은 e5-small로 정했어")
    )

    assert without.status == "proposed"
    assert (wrong.status, wrong.messages) == ("rejected", (QUOTE_NOT_FOUND_MESSAGE,))
    assert len(world.writer.proposals) == 1


def test_a_service_without_a_reader_checks_nothing(tmp_path: Path) -> None:
    world = World(tmp_path, with_reader=False)

    assert world.service.remember(remember_request(evidence=(LOCATION,))).status == "published"


def test_an_empty_quote_is_a_field_problem(tmp_path: Path) -> None:
    world = World(tmp_path)

    result = world.service.remember(remember_request(evidence=(LOCATION,), quote="  "))

    assert result.status == "rejected"
    assert "quote must be a non-empty string when given." in result.messages


# update_memory and supersede_claim


def test_update_and_supersede_follow_the_same_rule(tmp_path: Path) -> None:
    world = World(tmp_path)
    add_page(world.vault)

    refused = world.service.update(update_request(evidence=(LOCATION,)))
    updated = world.service.update(update_request(evidence=(LOCATION,), quote=QUOTE))
    superseded = world.service.supersede_claim(
        SupersedeClaimRequest(
            path="wiki/decisions/use-sqlite.md",
            claim="old claim",
            new_claim="new claim",
            evidence=LOCATION,
            basis="stated",
            vault="main",
        )
    )

    assert (refused.status, refused.messages) == ("rejected", (QUOTE_REQUIRED_MESSAGE,))
    assert updated.status == "published"
    assert (superseded.status, superseded.messages) == ("rejected", (QUOTE_REQUIRED_MESSAGE,))
    assert len(world.writer.calls) == 1


# The session file reader


def test_the_reader_returns_only_what_the_person_typed(tmp_path: Path) -> None:
    world = World(tmp_path)
    reader = SessionExchangeFileReader()

    assert (
        reader.human_text(world.vault.path, PART, 8, 16) == "아니야, 그 방법 말고\n임베딩 모델은 arctic-m으로 정했어."
    )
    assert reader.human_text(world.vault.path, PART, 19, 24) == ""  # a subagent exchange
    assert reader.human_text(world.vault.path, PART, 500, 510) is None
    assert reader.human_text(world.vault.path, "raw/sessions/none.md", 1, 5) is None


def test_the_reader_reads_v1_files_with_the_v1_rules(tmp_path: Path) -> None:
    vault = make_vault(tmp_path, "main")
    (vault.path / "raw" / "sessions").mkdir(parents=True)
    (vault.path / "raw" / "sessions" / "2026-11-10-old.md").write_text(V1_SESSION, encoding="utf-8")

    text = SessionExchangeFileReader().human_text(vault.path, "raw/sessions/2026-11-10-old.md", 5, 11)

    assert text == "임베딩 모델은 arctic-m으로 정했어."


def test_the_reader_stays_inside_raw_sessions_of_the_vault(tmp_path: Path) -> None:
    world = World(tmp_path)
    (tmp_path / "outside.md").write_text(V2_SESSION, encoding="utf-8")
    (world.vault.path / "raw" / "sessions" / "link.md").symlink_to(tmp_path / "outside.md")
    reader = SessionExchangeFileReader()

    assert reader.human_text(world.vault.path, "wiki/index.md", 1, 1) is None
    assert reader.human_text(world.vault.path, "raw/sessions/../../../outside.md", 8, 16) is None
    assert reader.human_text(world.vault.path, "raw/sessions/link.md", 8, 16) is None


# MCP tool arguments


def test_the_three_write_tools_take_an_optional_quote() -> None:
    remembered = parse_remember_input(
        title="t", kind="decision", body="b", evidence=[LOCATION], basis="stated", quote=QUOTE
    )
    updated = parse_update_memory_input(path="wiki/a.md", body="b", evidence=[LOCATION], basis="stated", quote=QUOTE)
    superseded = parse_supersede_claim_input(
        path="wiki/a.md", claim="a", new_claim="b", evidence=LOCATION, basis="stated", quote=QUOTE
    )

    assert (remembered.quote, updated.quote, superseded.quote) == (QUOTE, QUOTE, QUOTE)
    assert parse_remember_input(title="t", kind="decision", body="b", evidence=["e"], basis="stated").quote is None
    with pytest.raises(Exception, match="quote must be a string"):
        parse_remember_input(
            title="t",
            kind="decision",
            body="b",
            evidence=["e"],
            basis="stated",
            quote=3,  # type: ignore[arg-type]
        )
