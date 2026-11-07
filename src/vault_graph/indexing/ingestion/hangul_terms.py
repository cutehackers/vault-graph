"""Korean particle and ending stripping shared by keyword queries and title matching.

Spec 2026-11-05 §10.2 원인6. `unicode61` keeps a Korean word and its particle as one token ("아이디어를"),
so the query side drops one trailing particle or common ending. The keyword index (`sqlite_keyword_index`)
and the exact-title signal (`retrieval.search.candidate_ranking`) use the same list, so both read a query
the same way.
"""

from __future__ import annotations

import re
import unicodedata

# The particle list extends the Vault's own wiki search list (`tools/wiki/lib/search.py`). Longest first.
HANGUL_QUERY_SUFFIXES: tuple[str, ...] = tuple(
    sorted(
        {
            # particles
            "에서는",
            "에서도",
            "으로는",
            "으로서",
            "으로써",
            "에게서",
            "이라는",
            "이라고",
            "에서",
            "에게",
            "한테",
            "으로",
            "로서",
            "로써",
            "까지",
            "부터",
            "보다",
            "처럼",
            "마다",
            "이나",
            "이랑",
            "라는",
            "라고",
            "들을",
            "들이",
            "들의",
            "들은",
            "은",
            "는",
            "이",
            "가",
            "을",
            "를",
            "의",
            "에",
            "로",
            "와",
            "과",
            "도",
            "만",
            "랑",
            "들",
            # common endings
            "했습니다",
            "합니다",
            "하려면",
            "하려는",
            "하는",
            "하기",
            "하고",
            "하면",
            "해서",
            "했다",
            "한다",
            "하다",
            "된다",
            "되는",
            "된",
            "한",
        },  # fmt: skip
        key=lambda suffix: (-len(suffix), suffix),
    )
)
# A stem keeps at least this many letters, so "회의" is not read as "회" + "의".
HANGUL_STEM_MIN_LETTERS = 2

_WORD = re.compile(r"[\w가-힣]+", flags=re.UNICODE)


def word_tokens(text: str) -> tuple[str, ...]:
    """Words of ``text`` as the keyword query reads them: runs of letters, digits and underscores."""
    return tuple(_WORD.findall(text))


def strip_hangul_suffix(token: str) -> str:
    """``token`` without one trailing particle or ending from ``HANGUL_QUERY_SUFFIXES``.

    The stem keeps at least ``HANGUL_STEM_MIN_LETTERS`` letters. A token without a listed suffix returns as is.
    """
    for suffix in HANGUL_QUERY_SUFFIXES:
        if token.endswith(suffix) and len(token) - len(suffix) >= HANGUL_STEM_MIN_LETTERS:
            return token[: -len(suffix)]
    return token


def name_terms(text: str) -> tuple[str, ...]:
    """Comparable terms of a title, alias or query: NFKC, case folded, one Korean suffix dropped per word."""
    folded = unicodedata.normalize("NFKC", text).casefold()
    return tuple(strip_hangul_suffix(token) for token in word_tokens(folded))
