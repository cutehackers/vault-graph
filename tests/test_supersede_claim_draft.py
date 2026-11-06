"""supersede_claim: one claim row replaced through a Vault ``patch-page`` ``supersede-claim`` edit.

Source: spec 2026-11-05 §4.4.4 "claim 대체 쓰기 경로", 결정43, A-38 (vg side), A-31.
The draft goes out only through publish-draft (``stated``) or review propose (``inferred``).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.test_memory_write_service import (
    RecordingWriter,
    add_page,
    make_service,
    make_vault,
)
from tests.test_read_only_boundary import file_bytes
from vault_graph.operation.memory.memory_drafts import build_supersede_claim_draft
from vault_graph.operation.memory.memory_ports import WriteOutcome
from vault_graph.operation.memory.memory_requests import SupersedeClaimRequest, validate_supersede_claim

PATH = "wiki/systems/index-store.md"

CLAIM_PAGE = """---
title: Index store
type: system
status: active
created: 2026-10-01
updated: 2026-10-01
owner: agent
summary: Index store
source_count: 1
tags: []
related: []
confidence: medium
quality:
  provenance: claim
---

# Index store

| Claim | Status | Evidence |
|---|---|---|
| The index lives in SQLite. | stated | User said so on 2026-10-01. |
"""


def supersede_request(**overrides: object) -> SupersedeClaimRequest:
    values: dict[str, object] = {
        "path": PATH,
        "claim": "The index lives in SQLite.",
        "new_claim": "The index lives in LanceDB.",
        "evidence": "User said so on 2026-11-02.",
        "basis": "stated",
        "vault": "main",
    }
    values.update(overrides)
    return SupersedeClaimRequest(**values)  # type: ignore[arg-type]


def test_draft_is_a_patch_page_with_one_supersede_claim_edit() -> None:
    draft = build_supersede_claim_draft(supersede_request())

    assert draft["operation"] == "patch-page"
    assert draft["path"] == PATH
    assert draft["edits"] == [
        {
            "op": "supersede-claim",
            "claim": "The index lives in SQLite.",
            "by": "The index lives in LanceDB.",
            "status": "stated",
            "evidence": "User said so on 2026-11-02.",
        }
    ]
    assert "body" not in draft
    assert "frontmatter" not in draft
    log = draft["log"]
    assert isinstance(log, dict)
    assert log["items"] == ["Superseded a claim in [[systems/index-store]]: The index lives in SQLite."]


def test_draft_status_follows_basis() -> None:
    draft = build_supersede_claim_draft(supersede_request(basis="inferred"))

    edits = draft["edits"]
    assert isinstance(edits, list)
    assert edits[0]["status"] == "inferred"


def test_draft_strips_cells() -> None:
    draft = build_supersede_claim_draft(
        supersede_request(claim="  The index lives in SQLite. ", new_claim=" New. ", evidence=" E. ")
    )

    edits = draft["edits"]
    assert isinstance(edits, list)
    assert (edits[0]["claim"], edits[0]["by"], edits[0]["evidence"]) == ("The index lives in SQLite.", "New.", "E.")


@pytest.mark.parametrize(
    ("overrides", "field"),
    [
        ({"path": "notes/a.md"}, "path"),
        ({"claim": " "}, "claim"),
        ({"new_claim": ""}, "new_claim"),
        ({"new_claim": "a | b"}, "new_claim"),
        ({"evidence": "line\nbreak"}, "evidence"),
        ({"evidence": ""}, "evidence"),
        ({"new_claim": "The index lives in SQLite."}, "new_claim"),
        ({"basis": "guessed"}, "basis"),
        ({"candidate_key": " "}, "candidate_key"),
    ],
)
def test_validation_names_the_bad_field(overrides: dict[str, object], field: str) -> None:
    problems = validate_supersede_claim(supersede_request(**overrides))

    assert problems
    assert any(problem.startswith(field) for problem in problems)


def test_stated_supersede_is_published_and_vault_files_stay_unchanged(tmp_path: Path) -> None:
    vault = make_vault(tmp_path, "main")
    add_page(vault, PATH, CLAIM_PAGE)
    before = file_bytes(vault.path)
    writer = RecordingWriter(WriteOutcome("published", written_paths=(PATH,)))

    result = make_service(tmp_path, writer, vaults=(vault,)).supersede_claim(supersede_request())

    assert result.status == "published"
    assert result.written_paths == (PATH,)
    assert len(writer.calls) == 1
    assert writer.proposals == []
    assert writer.drafts[0]["operation"] == "patch-page"
    assert file_bytes(vault.path) == before


def test_inferred_supersede_goes_to_review_propose(tmp_path: Path) -> None:
    vault = make_vault(tmp_path, "main")
    add_page(vault, PATH, CLAIM_PAGE)
    writer = RecordingWriter()

    result = make_service(tmp_path, writer, vaults=(vault,)).supersede_claim(supersede_request(basis="inferred"))

    assert result.status == "proposed"
    assert writer.calls == []
    assert len(writer.proposals) == 1
    assert writer.drafts[0]["edits"] == build_supersede_claim_draft(supersede_request(basis="inferred"))["edits"]


def test_missing_page_is_rejected_without_calling_the_vault(tmp_path: Path) -> None:
    writer = RecordingWriter()

    result = make_service(tmp_path, writer).supersede_claim(supersede_request())

    assert result.status == "rejected"
    assert writer.calls == [] and writer.proposals == []
    assert any(PATH in message for message in result.messages)


def test_vault_rejection_keeps_the_vault_message_and_points_to_retire(tmp_path: Path) -> None:
    vault = make_vault(tmp_path, "main")
    add_page(vault, PATH, CLAIM_PAGE.replace("  provenance: claim\n", "  provenance: section\n"))
    vault_message = "Claim edits ['supersede-claim'] need quality.provenance: claim on index-store.md"
    writer = RecordingWriter(WriteOutcome("rejected", messages=(vault_message,), reason="invalid-draft"))

    result = make_service(tmp_path, writer, vaults=(vault,)).supersede_claim(supersede_request())

    assert result.status == "rejected"
    assert vault_message in result.messages
    assert any("retire_memory(replaced_by=" in message for message in result.messages)


def test_invalid_request_is_rejected_without_calling_the_vault(tmp_path: Path) -> None:
    writer = RecordingWriter()

    result = make_service(tmp_path, writer).supersede_claim(supersede_request(claim=""))

    assert result.status == "rejected"
    assert writer.calls == [] and writer.proposals == []
