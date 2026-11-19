"""Check that a quote given as evidence is really in the text it cites (spec 2026-11-19 D1).

A memory that cites a session exchange carries the user's words as a quote. ``quote_in_text`` says whether
that quote is in the text of the cited exchange, so a quote a model made up is refused before anything is sent to
a Vault. Both sides are compared after Unicode NFKC and with every whitespace run as one space, so a quote copied
across line breaks, or typed with full-width or decomposed characters, still matches. Korean text needs no other
rule.

A quote shorter than ``MIN_QUOTE_CHARS`` after that is refused: a few characters are in almost any text, so they
prove nothing.

The check proves the quote exists. It does not prove that the memory follows from the quote; a person judges
that. This module is pure: the caller reads the session file and passes the text.
"""

from __future__ import annotations

import unicodedata

MIN_QUOTE_CHARS = 8


def normalize_evidence_text(text: str) -> str:
    """``text`` in NFKC with every whitespace run as one space and none at the ends."""
    return " ".join(unicodedata.normalize("NFKC", text).split())


def quote_in_text(quote: str, text: str) -> bool:
    """True when ``quote`` has at least ``MIN_QUOTE_CHARS`` characters and is part of ``text``."""
    wanted = normalize_evidence_text(quote)
    return len(wanted) >= MIN_QUOTE_CHARS and wanted in normalize_evidence_text(text)


__all__ = ["MIN_QUOTE_CHARS", "normalize_evidence_text", "quote_in_text"]
