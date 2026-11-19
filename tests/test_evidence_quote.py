"""The evidence quote check (spec 2026-11-19 D1)."""

from __future__ import annotations

import unicodedata

from vault_graph.operation.memory.evidence_quote import (
    MIN_QUOTE_CHARS,
    ExchangeCitation,
    cited_exchanges,
    normalize_evidence_text,
    quote_in_text,
    session_files,
)

HUMAN_TURN = "아니야, 그 방법 말고\n임베딩 모델은   arctic-m으로 정했어.\nUse the review queue for anything inferred."


def test_a_quote_copied_from_the_text_passes() -> None:
    assert quote_in_text("임베딩 모델은 arctic-m으로 정했어", HUMAN_TURN)
    assert quote_in_text("Use the review queue for anything inferred.", HUMAN_TURN)


def test_a_quote_across_line_breaks_and_extra_spaces_passes() -> None:
    assert quote_in_text("그 방법 말고 임베딩 모델은 arctic-m으로", HUMAN_TURN)
    assert quote_in_text("  임베딩   모델은\narctic-m으로  정했어 ", HUMAN_TURN)


def test_unicode_forms_of_the_same_characters_match() -> None:
    decomposed = unicodedata.normalize("NFD", "임베딩 모델은 arctic-m으로")
    assert decomposed != "임베딩 모델은 arctic-m으로"
    assert quote_in_text(decomposed, HUMAN_TURN)
    full_width = "arctic-m으로 정했어".translate({ord(letter): ord(letter) + 0xFEE0 for letter in "arctic"})
    assert quote_in_text(full_width, HUMAN_TURN)


def test_a_quote_that_is_not_in_the_text_fails() -> None:
    assert not quote_in_text("임베딩 모델은 e5-small로 정했어", HUMAN_TURN)
    assert not quote_in_text("use the review queue for anything inferred.", HUMAN_TURN)  # the case differs


def test_a_quote_too_short_to_prove_anything_fails() -> None:
    short = "아니야"
    assert short in HUMAN_TURN
    assert len(normalize_evidence_text(short)) < MIN_QUOTE_CHARS
    assert not quote_in_text(short, HUMAN_TURN)
    assert not quote_in_text("   ", HUMAN_TURN)
    assert not quote_in_text("", "")


def test_normalize_collapses_whitespace() -> None:
    assert normalize_evidence_text("  a\n\tb   c ") == "a b c"


# Session exchange locations in evidence lines (D4)

PART = "raw/sessions/claude-code/2026-11-10-s1-part1.md"


def test_the_location_form_vault_graph_shows_is_read() -> None:
    assert cited_exchanges([f"{PART} L10-L20"]) == (ExchangeCitation(PART, 10, 20),)
    assert cited_exchanges([f'{PART} L10-L20 "임베딩 모델은 arctic-m으로 정했어"'])[0].location == f"{PART} L10-L20"


def test_other_line_range_forms_and_a_sha_suffix_are_read() -> None:
    assert cited_exchanges([f"{PART}#sha256=abc L7"]) == (ExchangeCitation(PART, 7, 7),)
    assert cited_exchanges([f"{PART}#L12-L40"]) == (ExchangeCitation(PART, 12, 40),)
    assert cited_exchanges([f"see {PART} lines 40-12"]) == (ExchangeCitation(PART, 12, 40),)


def test_a_path_without_a_line_range_cites_no_exchange() -> None:
    assert cited_exchanges([PART, "User said so on 2026-11-10.", "wiki/decisions/a.md L3-L9"]) == ()


def test_several_locations_are_read_in_order_and_once() -> None:
    other = "raw/sessions/2026-11-11-s2.md"

    cited = cited_exchanges([f"{PART} L10-L20 and {other} L1-L5", f"{PART} L10-L20\n{other} L30-L31"])

    assert cited == (ExchangeCitation(PART, 10, 20), ExchangeCitation(other, 1, 5), ExchangeCitation(other, 30, 31))


def test_session_files_lists_every_named_session_file_with_or_without_a_range() -> None:
    other = "raw/sessions/2026-11-11-s2.md"

    assert session_files([PART, f"{other} L1-L5 and again {PART}:3-9", "wiki/decisions/a.md"]) == (PART, other)
    assert session_files(["User said so on 2026-11-10."]) == ()
