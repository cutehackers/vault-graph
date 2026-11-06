"""Claim rows of a Vault page and the rule that drops ``superseded`` rows (spec 2026-11-05 §4.4.6, 위험D3).

The table format is the Vault rule: ``vault-builder:docs/agent/OPERATING-SCHEMA.md:192-200`` and
``vault-builder:docs/agent/DRAFTS.md``. Columns ``Claim``, ``Status``, ``Evidence``; a ``superseded``
row names its replacement with ``Superseded by:`` in its evidence.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from vault_graph.context.memory.claims import (
    ClaimRow,
    claim_table_warning,
    current_claims,
    read_claim_table,
    without_superseded_claims,
)
from vault_graph.indexing.ingestion.document_chunking import chunk_document
from vault_graph.indexing.ingestion.document_models import SourceDocument
from vault_graph.indexing.ingestion.document_readers import MarkdownDocumentReader

# The row shape a Vault `supersede-claim` patch leaves behind (DRAFTS.md:19, OPERATING-SCHEMA.md 2.3.1).
SUPERSEDED_ROW = (
    "| Releases ship every Friday. | superseded | [[sources/meeting-2026-09-01]] "
    "Superseded by: Releases ship every Tuesday. |"
)
SUPERSEDED_PAGE = f"""# Release cadence

## Claim Evidence

| Claim | Status | Evidence |
|---|---|---|
{SUPERSEDED_ROW}
| Releases ship every Tuesday. | stated | [[sources/meeting-2026-10-02]] |
| Hotfixes skip the release train. | inferred | [[sources/meeting-2026-09-01]] |
"""

# Copied from a real Vault page (`$HOME/vault/wiki/comparisons/rail-authority-models.md`, 2026-11-06).
REAL_ROWS = (
    (
        "Rail should own governance while Codex owns agent execution in the 2026-04-21 boundary design.",
        "`raw/sources/rail-historical-spec-2026-04-21-codex-boundary-actor-backend-design.md` lines 20-45",
    ),
    (
        "The actor executor port design says Rail remains governance and Codex remains the agent execution runtime.",
        "`raw/sources/rail-historical-spec-2026-04-27-actor-backend-port-and-result-projection-design.md` lines 12-23",
    ),
    (
        "The brokered architecture rejects raw shell as normal actor capability and makes authority flow through"
        " artifacts.",
        "`raw/sources/rail-historical-spec-2026-05-04-control-plane-brokered-actor-architecture-design.md`"
        " lines 3-43 and 70-92",
    ),
)
REAL_PAGE = (
    "## Durable Boundary\n\nThe durable boundary is not a specific runtime technology.\n\n"
    "## Claim Evidence\n\n| Claim | Status | Evidence |\n|---|---|---|\n"
    + "".join(f"| {claim} | stated | {evidence} |\n" for claim, evidence in REAL_ROWS)
)


def test_superseded_row_is_dropped_and_current_rows_stay() -> None:
    assert current_claims(SUPERSEDED_PAGE) == (
        ClaimRow(claim="Releases ship every Tuesday.", status="stated", evidence="[[sources/meeting-2026-10-02]]"),
        ClaimRow(
            claim="Hotfixes skip the release train.", status="inferred", evidence="[[sources/meeting-2026-09-01]]"
        ),
    )


def test_real_vault_page_rows_are_read() -> None:
    table = read_claim_table(REAL_PAGE)

    assert table is not None
    assert table.problem is None
    assert [row.status for row in table.rows] == ["stated", "stated", "stated"]
    assert table.rows[0].claim.startswith("Rail should own governance")
    assert table.rows[2].evidence.endswith("lines 3-43 and 70-92")
    assert len(current_claims(REAL_PAGE)) == 3


def test_status_case_and_backticks_do_not_matter() -> None:
    body = (
        "| Claim | Status | Evidence |\n|---|---|---|\n"
        "| Old. | `Superseded` | a Superseded by: New. |\n| New. | Stated | b |\n"
    )

    assert [row.claim for row in current_claims(body)] == ["New."]


def test_escaped_pipe_stays_inside_the_cell() -> None:
    body = "| Claim | Status | Evidence |\n|---|---|---|\n| a \\| b | stated | c |\n"

    assert current_claims(body) == (ClaimRow(claim="a \\| b", status="stated", evidence="c"),)


def test_page_without_claim_table_has_no_rows_and_no_warning() -> None:
    body = "# Note\n\n| Model | Shape |\n|---|---|\n| a | b |\n"

    assert read_claim_table(body) is None
    assert current_claims(body) == ()
    assert without_superseded_claims(body) == body
    assert claim_table_warning("wiki/note.md", body) is None


def test_claim_table_inside_a_code_fence_is_not_read() -> None:
    body = "```\n| Claim | Status | Evidence |\n|---|---|---|\n| x | superseded | y |\n```\n"

    assert read_claim_table(body) is None
    assert without_superseded_claims(body) == body


def test_without_superseded_claims_removes_only_the_superseded_line() -> None:
    text = without_superseded_claims(SUPERSEDED_PAGE)

    assert "Releases ship every Friday." not in text
    assert text == SUPERSEDED_PAGE.replace(SUPERSEDED_ROW + "\n", "")


def test_unknown_status_makes_the_table_unreadable_and_the_page_stays_whole() -> None:
    body = "| Claim | Status | Evidence |\n|---|---|---|\n| Old. | superseded | a |\n| New. | maybe | b |\n"

    table = read_claim_table(body)

    assert table is not None
    assert table.problem is not None
    assert current_claims(body) == ()
    assert without_superseded_claims(body) == body
    warning = claim_table_warning("wiki/decisions/x.md", body)
    assert warning is not None
    assert "\n" not in warning
    assert "wiki/decisions/x.md" in warning


def test_short_row_makes_the_table_unreadable() -> None:
    body = "| Claim | Status | Evidence |\n|---|---|---|\n| Only claim |\n"

    table = read_claim_table(body)

    assert table is not None
    assert table.problem is not None


def test_header_without_separator_line_is_unreadable() -> None:
    # A table flattened into one line, as the chunker does to an oversized unit.
    body = "| Claim | Status | Evidence | |---|---|---| | Old. | superseded | a |\n"

    table = read_claim_table(body)

    assert table is not None
    assert table.problem is not None
    assert without_superseded_claims(body) == body


def test_table_split_by_the_chunker_is_read_as_one_table(tmp_path: Path) -> None:
    """The chunker cuts a long table into chunks of the same section; only the first keeps the header."""
    rows = [f"| Claim number {index} is still true here. | stated | [[sources/s{index}]] |" for index in range(60)]
    rows.insert(45, "| The old claim that was replaced. | superseded | [[sources/s0]] Superseded by: Claim number 1. |")
    page = "# Long\n\n## Claim Evidence\n\n| Claim | Status | Evidence |\n|---|---|---|\n" + "\n".join(rows) + "\n"
    body = _indexed_body(tmp_path, page)
    assert body.count("## Claim Evidence") >= 2, "the fixture must span more than one chunk"

    claims = current_claims(body)

    assert len(claims) == 60
    assert all(row.status == "stated" for row in claims)
    assert "The old claim that was replaced." not in without_superseded_claims(body)
    assert "Claim number 59 is still true here." in without_superseded_claims(body)


def test_real_vault_page_through_the_indexer_keeps_its_rows(tmp_path: Path) -> None:
    body = _indexed_body(tmp_path, REAL_PAGE)

    assert [row.claim for row in current_claims(body)] == [row.claim for row in current_claims(REAL_PAGE)]


def _indexed_body(tmp_path: Path, page: str) -> str:
    """The page as the index returns it: chunks joined with their section headings (body_text)."""
    raw = page.encode()
    source = SourceDocument(
        vault_id="v",
        root_path=tmp_path,
        path="wiki/page.md",
        suffix=".md",
        raw_bytes=raw,
        raw_sha256=hashlib.sha256(raw).hexdigest(),
    )
    chunks = chunk_document(MarkdownDocumentReader().read(source))
    return "\n\n".join(f"## {chunk.section}\n\n{chunk.text}" if chunk.section else chunk.text for chunk in chunks)
