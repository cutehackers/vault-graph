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

``cited_exchanges`` reads the session exchange locations out of evidence lines. A location is a
`raw/sessions/...md` path followed on the same line by a line range: `L12-L40`, `#L12-L40` or `lines 12-40`
(the forms `context/memory/memory_candidates.py` counts as citing an exchange). A path with no line range
cites no exchange.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable
from dataclasses import dataclass

MIN_QUOTE_CHARS = 8

_SESSION_PATH_RE = re.compile(r"raw/sessions/[^\s`|,;)>\]#]+\.md")
_LINE_RANGE_RES = (
    re.compile(r"(?<![\w-])L(\d+)(?:-L?(\d+))?(?!\w)"),
    re.compile(r"\blines? (\d+)(?:-(\d+))?\b", re.IGNORECASE),
)


@dataclass(frozen=True)
class ExchangeCitation:
    """Lines ``line_start`` to ``line_end`` (1-based, both included) of the session file at ``path``."""

    path: str
    line_start: int
    line_end: int

    @property
    def location(self) -> str:
        return f"{self.path} L{self.line_start}-L{self.line_end}"


def normalize_evidence_text(text: str) -> str:
    """``text`` in NFKC with every whitespace run as one space and none at the ends."""
    return " ".join(unicodedata.normalize("NFKC", text).split())


def quote_in_text(quote: str, text: str) -> bool:
    """True when ``quote`` has at least ``MIN_QUOTE_CHARS`` characters and is part of ``text``."""
    wanted = normalize_evidence_text(quote)
    return len(wanted) >= MIN_QUOTE_CHARS and wanted in normalize_evidence_text(text)


def cited_exchanges(evidence: Iterable[str]) -> tuple[ExchangeCitation, ...]:
    """The session exchange locations the evidence lines name, in order, each once."""
    cited: list[ExchangeCitation] = []
    for item in evidence:
        for line in item.splitlines():
            matches = list(_SESSION_PATH_RE.finditer(line))
            for position, match in enumerate(matches):
                end = matches[position + 1].start() if position + 1 < len(matches) else len(line)
                tail = line[match.end() : end]
                for pattern in _LINE_RANGE_RES:
                    for found in pattern.finditer(tail):
                        first = int(found.group(1))
                        last = int(found.group(2)) if found.group(2) else first
                        citation = ExchangeCitation(match.group(0), min(first, last), max(first, last))
                        if citation not in cited:
                            cited.append(citation)
    return tuple(cited)


__all__ = ["MIN_QUOTE_CHARS", "ExchangeCitation", "cited_exchanges", "normalize_evidence_text", "quote_in_text"]
