"""The evidence quote check (spec 2026-11-19 D1)."""

from __future__ import annotations

import unicodedata

from vault_graph.operation.memory.evidence_quote import MIN_QUOTE_CHARS, normalize_evidence_text, quote_in_text

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
